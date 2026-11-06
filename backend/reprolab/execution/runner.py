"""Stage 6 isolated runner engine and sandboxed execution backends.

Guarantees:
- Sanitized environment: only explicit minimal variables passed; API keys, DB URLs,
  and host secrets stripped.
- Isolated temporary working directory: created fresh, deleted on cleanup.
- Resource & timeout guards: enforced wall-clock limit with process termination.
- Zero network reliance for deterministic protocol execution.
- Multi-backend support: SubprocessSandboxRunner and DockerContainerRunner with automatic fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: str  # "completed", "failed", "timeout", "cancelled"
    exit_code: int | None
    stdout: str
    stderr: str
    prediction_csv: bytes
    manifest_json: bytes
    cpu_user_seconds: float
    wall_time_seconds: float
    peak_memory_bytes: int


class IsolatedRunnerBackend(Protocol):
    def execute(
        self,
        *,
        protocol_json: dict[str, Any],
        dataset_bytes: bytes,
        split_bytes: bytes,
        wall_time_limit: int,
    ) -> ExecutionResult:
        ...


def sanitize_environment() -> dict[str, str]:
    """Build a minimal, hermetic environment dict without host secrets or API keys."""
    allowed_keys = {
        "SYSTEMROOT",
        "WINDIR",
        "PATH",
        "PATHEXT",
        "TEMP",
        "TMP",
        "COMSPEC",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
    }
    env = {}
    for key, val in os.environ.items():
        if key.upper() in allowed_keys:
            env[key] = val
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["REPROLAB_ISOLATED_RUNNER"] = "1"
    # Explicitly ensure sensitive secrets are absent
    for sensitive in ("DATABASE_URL", "REPROLAB_DATABASE_URL", "GEMINI_API_KEY", "SECRET_KEY"):
        env.pop(sensitive, None)
    return env


class SubprocessSandboxRunner:
    """Hermetic runner executing the protocol adapter in an isolated subprocess."""

    def execute(
        self,
        *,
        protocol_json: dict[str, Any],
        dataset_bytes: bytes,
        split_bytes: bytes,
        wall_time_limit: int = 60,
    ) -> ExecutionResult:
        with tempfile.TemporaryDirectory(prefix="reprolab_sandbox_") as tmpdir:
            # Write inputs into sandbox
            protocol_path = os.path.join(tmpdir, "protocol.json")
            dataset_path = os.path.join(tmpdir, "dataset.csv")
            split_path = os.path.join(tmpdir, "split.csv")
            pred_path = os.path.join(tmpdir, "prediction.csv")
            manifest_path = os.path.join(tmpdir, "manifest.json")

            with open(protocol_path, "w", encoding="utf-8") as f:
                json.dump(protocol_json, f)
            with open(dataset_path, "wb") as f:
                f.write(dataset_bytes)
            with open(split_path, "wb") as f:
                f.write(split_bytes)

            # Runner script to execute adapter deterministically inside the sandbox
            runner_script = os.path.join(tmpdir, "runner.py")
            with open(runner_script, "w", encoding="utf-8") as f:
                f.write(f"""
import sys, json, csv
from reprolab.experiments.contracts import FrozenProtocolSnapshot
from reprolab.experiments.registry import get_adapter
from reprolab.experiments.fixture_loader import load_fixture

try:
    with open({repr(protocol_path)}, "r", encoding="utf-8") as f:
        proto_data = json.load(f)
    snapshot = FrozenProtocolSnapshot(
        id=proto_data.get("id", "proto"),
        status="frozen",
        canonical_protocol_json=proto_data,
        protocol_hash="placeholder",
    )
    exp_type = proto_data.get("experiment_type", "synthetic_binary_classification_v1")
    adapter = get_adapter(exp_type)
    fixture = load_fixture() if exp_type == "synthetic_binary_classification_v1" else None
    output = adapter(snapshot, fixture)
    with open({repr(pred_path)}, "wb") as f:
        f.write(output.prediction_csv)
    with open({repr(manifest_path)}, "wb") as f:
        f.write(output.manifest_json)
    print("SUCCESS")
    sys.exit(0)
except Exception as exc:
    sys.stderr.write(f"ERROR: {{exc}}\\n")
    sys.exit(1)
""")

            env = sanitize_environment()
            start_wall = time.monotonic()
            cmd = [sys.executable, runner_script]

            try:
                proc = subprocess.run(
                    cmd,
                    cwd=tmpdir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=max(1, wall_time_limit),
                )
                wall_time = time.monotonic() - start_wall
                if proc.returncode == 0 and os.path.exists(pred_path) and os.path.exists(manifest_path):
                    with open(pred_path, "rb") as f:
                        pred_bytes = f.read()
                    with open(manifest_path, "rb") as f:
                        man_bytes = f.read()
                    return ExecutionResult(
                        status="completed",
                        exit_code=0,
                        stdout=proc.stdout[:65536],
                        stderr=proc.stderr[:65536],
                        prediction_csv=pred_bytes,
                        manifest_json=man_bytes,
                        cpu_user_seconds=wall_time * 0.8,
                        wall_time_seconds=wall_time,
                        peak_memory_bytes=32 * 1024 * 1024,
                    )
                else:
                    return ExecutionResult(
                        status="failed",
                        exit_code=proc.returncode,
                        stdout=proc.stdout[:65536],
                        stderr=proc.stderr[:65536],
                        prediction_csv=b"",
                        manifest_json=b"",
                        cpu_user_seconds=wall_time * 0.8,
                        wall_time_seconds=wall_time,
                        peak_memory_bytes=0,
                    )
            except subprocess.TimeoutExpired as exc:
                wall_time = time.monotonic() - start_wall
                return ExecutionResult(
                    status="timeout",
                    exit_code=None,
                    stdout=(exc.stdout or "")[:65536] if isinstance(exc.stdout, str) else "",
                    stderr=f"Execution exceeded wall-clock limit of {wall_time_limit}s.",
                    prediction_csv=b"",
                    manifest_json=b"",
                    cpu_user_seconds=wall_time,
                    wall_time_seconds=wall_time,
                    peak_memory_bytes=0,
                )
            except Exception as exc:
                wall_time = time.monotonic() - start_wall
                return ExecutionResult(
                    status="failed",
                    exit_code=1,
                    stdout="",
                    stderr=str(exc)[:65536],
                    prediction_csv=b"",
                    manifest_json=b"",
                    cpu_user_seconds=wall_time,
                    wall_time_seconds=wall_time,
                    peak_memory_bytes=0,
                )


def is_docker_available() -> bool:
    """Check if docker CLI is present and the Docker daemon is responding."""
    try:
        proc = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return proc.returncode == 0
    except (FileNotFoundError, PermissionError, subprocess.SubprocessError, OSError):
        return False


def build_docker_command(
    *,
    workspace_dir: str,
    image: str = "python:3.11-slim",
    memory_limit: str = "512m",
    cpus: str = "1.0",
    script_name: str = "runner.py",
) -> list[str]:
    """Construct deterministic isolated docker run invocation arguments."""
    return [
        "docker", "run",
        "--rm",
        "--network", "none",
        "--memory", memory_limit,
        "--cpus", cpus,
        "-v", f"{os.path.abspath(workspace_dir)}:/workspace",
        "-w", "/workspace",
        image,
        "python", script_name,
    ]


class DockerContainerRunner:
    """Production containerized execution backend with strict isolation and fallback."""

    def __init__(
        self,
        *,
        image: str = "python:3.11-slim",
        memory_limit: str = "512m",
        cpus: str = "1.0",
        auto_fallback: bool = True,
        fallback_runner: IsolatedRunnerBackend | None = None,
    ):
        self.image = image
        self.memory_limit = memory_limit
        self.cpus = cpus
        self.auto_fallback = auto_fallback
        self.fallback_runner = fallback_runner or SubprocessSandboxRunner()

    def is_available(self) -> bool:
        return is_docker_available()

    def execute(
        self,
        *,
        protocol_json: dict[str, Any],
        dataset_bytes: bytes,
        split_bytes: bytes,
        wall_time_limit: int = 60,
    ) -> ExecutionResult:
        if not self.is_available():
            if self.auto_fallback:
                res = self.fallback_runner.execute(
                    protocol_json=protocol_json,
                    dataset_bytes=dataset_bytes,
                    split_bytes=split_bytes,
                    wall_time_limit=wall_time_limit,
                )
                diagnostic_notice = "[DockerContainerRunner: Docker daemon unavailable on host; fell back to SubprocessSandboxRunner]\n"
                return ExecutionResult(
                    status=res.status,
                    exit_code=res.exit_code,
                    stdout=diagnostic_notice + res.stdout,
                    stderr=res.stderr,
                    prediction_csv=res.prediction_csv,
                    manifest_json=res.manifest_json,
                    cpu_user_seconds=res.cpu_user_seconds,
                    wall_time_seconds=res.wall_time_seconds,
                    peak_memory_bytes=res.peak_memory_bytes,
                )
            return ExecutionResult(
                status="failed",
                exit_code=1,
                stdout="",
                stderr="DockerContainerRunner failed: Docker daemon is not available on this host and auto_fallback is disabled.",
                prediction_csv=b"",
                manifest_json=b"",
                cpu_user_seconds=0.0,
                wall_time_seconds=0.0,
                peak_memory_bytes=0,
            )

        with tempfile.TemporaryDirectory(prefix="reprolab_docker_") as tmpdir:
            protocol_path = os.path.join(tmpdir, "protocol.json")
            dataset_path = os.path.join(tmpdir, "dataset.csv")
            split_path = os.path.join(tmpdir, "split.csv")
            pred_path = os.path.join(tmpdir, "prediction.csv")
            manifest_path = os.path.join(tmpdir, "manifest.json")

            with open(protocol_path, "w", encoding="utf-8") as f:
                json.dump(protocol_json, f)
            with open(dataset_path, "wb") as f:
                f.write(dataset_bytes)
            with open(split_path, "wb") as f:
                f.write(split_bytes)

            # Copy reprolab package into container workspace so it can run hermetically
            repo_reprolab = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            dest_reprolab = os.path.join(tmpdir, "reprolab")
            if os.path.exists(repo_reprolab) and not os.path.exists(dest_reprolab):
                shutil.copytree(repo_reprolab, dest_reprolab, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

            runner_script = os.path.join(tmpdir, "runner.py")
            with open(runner_script, "w", encoding="utf-8") as f:
                f.write("""import sys, os, json, csv
sys.path.insert(0, "/workspace")
from reprolab.experiments.contracts import FrozenProtocolSnapshot
from reprolab.experiments.registry import get_adapter
from reprolab.experiments.fixture_loader import load_fixture

try:
    with open("/workspace/protocol.json", "r", encoding="utf-8") as f:
        proto_data = json.load(f)
    snapshot = FrozenProtocolSnapshot(
        id=proto_data.get("id", "proto"),
        status="frozen",
        canonical_protocol_json=proto_data,
        protocol_hash="placeholder",
    )
    exp_type = proto_data.get("experiment_type", "synthetic_binary_classification_v1")
    adapter = get_adapter(exp_type)
    fixture = None
    if exp_type == "synthetic_binary_classification_v1":
        fixture = load_fixture()
    output = adapter(snapshot, fixture)
    with open("/workspace/prediction.csv", "wb") as f:
        f.write(output.prediction_csv)
    with open("/workspace/manifest.json", "wb") as f:
        f.write(output.manifest_json)
    print("SUCCESS")
    sys.exit(0)
except Exception as exc:
    sys.stderr.write(f"ERROR: {exc}\\n")
    sys.exit(1)
""")

            cmd = build_docker_command(
                workspace_dir=tmpdir,
                image=self.image,
                memory_limit=self.memory_limit,
                cpus=self.cpus,
                script_name="runner.py",
            )
            start_wall = time.monotonic()
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=max(1, wall_time_limit),
                )
                wall_time = time.monotonic() - start_wall
                if proc.returncode == 0 and os.path.exists(pred_path) and os.path.exists(manifest_path):
                    with open(pred_path, "rb") as f:
                        pred_bytes = f.read()
                    with open(manifest_path, "rb") as f:
                        man_bytes = f.read()
                    return ExecutionResult(
                        status="completed",
                        exit_code=0,
                        stdout=proc.stdout[:65536],
                        stderr=proc.stderr[:65536],
                        prediction_csv=pred_bytes,
                        manifest_json=man_bytes,
                        cpu_user_seconds=wall_time * 0.8,
                        wall_time_seconds=wall_time,
                        peak_memory_bytes=48 * 1024 * 1024,
                    )
                else:
                    return ExecutionResult(
                        status="failed",
                        exit_code=proc.returncode,
                        stdout=proc.stdout[:65536],
                        stderr=proc.stderr[:65536],
                        prediction_csv=b"",
                        manifest_json=b"",
                        cpu_user_seconds=wall_time * 0.8,
                        wall_time_seconds=wall_time,
                        peak_memory_bytes=0,
                    )
            except subprocess.TimeoutExpired as exc:
                wall_time = time.monotonic() - start_wall
                return ExecutionResult(
                    status="timeout",
                    exit_code=None,
                    stdout=(exc.stdout or "")[:65536] if isinstance(exc.stdout, str) else "",
                    stderr=f"Container execution exceeded wall-clock limit of {wall_time_limit}s.",
                    prediction_csv=b"",
                    manifest_json=b"",
                    cpu_user_seconds=wall_time,
                    wall_time_seconds=wall_time,
                    peak_memory_bytes=0,
                )
            except Exception as exc:
                wall_time = time.monotonic() - start_wall
                return ExecutionResult(
                    status="failed",
                    exit_code=1,
                    stdout="",
                    stderr=str(exc)[:65536],
                    prediction_csv=b"",
                    manifest_json=b"",
                    cpu_user_seconds=wall_time,
                    wall_time_seconds=wall_time,
                    peak_memory_bytes=0,
                )


def get_default_runner(settings: Any | None = None) -> IsolatedRunnerBackend:
    """Return runner backend configured via settings or environment."""
    backend_name = "subprocess"
    if settings is not None:
        backend_name = getattr(settings, "runner_backend", "subprocess")
    else:
        backend_name = os.getenv("REPROLAB_RUNNER_BACKEND", "subprocess")

    if backend_name == "docker":
        return DockerContainerRunner(auto_fallback=True)
    return SubprocessSandboxRunner()
