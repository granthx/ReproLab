"""Small test-only helpers shared by Stage 1 tests."""

from typing import Any

from fastapi.testclient import TestClient

from reprolab.experiments.fixture_loader import load_fixture
from reprolab.experiments.synthetic_binary_classification import ADAPTER_VERSION
from reprolab.experiments.contracts import FrozenProtocolSnapshot


def _protocol_payload(claim_id: str, evidence_id: str, fixture) -> dict[str, Any]:
    return {
        "protocol": {
            "source_kind": "synthetic_framework_test",
            "experiment_type": fixture.experiment_type,
            "paper_id": None,
            "claim_id": claim_id,
            "claim_text": "The registered synthetic adapter produces a deterministic binary-classification output.",
            "evidence_reference_ids": [evidence_id],
            "dataset": {"name": "reprolab-synthetic-binary-classification-v1", "version": fixture.fixture_version, "source_url": None, "content_hash": fixture.dataset_sha256, "license": "ReproLab test fixture"},
            "split": {"strategy": "fixed explicit split", "train_fraction": 0.6, "test_fraction": 0.4, "random_seed": fixture.seed, "split_hash": fixture.split_sha256},
            "preprocessing": {"steps": ["none; fixture values are already numeric"], "fit_on_training_only": True},
            "implementation": {"mode": "synthetic_adapter", "adapter_version": ADAPTER_VERSION, "repository_url": None, "commit_hash": None, "code_hash": "d" * 64, "deviations": []},
            "model": {"name": fixture.model_name, "hyperparameters": {"threshold": fixture.threshold, "positive_if_sum_gte_threshold": fixture.positive_if_sum_gte_threshold}},
            "random_seeds": [fixture.seed],
            "primary_metric": {"name": "accuracy", "direction": "maximize", "unit": "proportion", "analysis_unit": "evaluation row"},
            "reported_result": {"value": 0.75, "source_locator": "synthetic fixture specification", "is_published": False},
            "comparison": {"method": "absolute_tolerance", "tolerance": 0.05, "rationale": "Framework validation only."},
            "statistical_analysis": {"method": "Wilson interval for fixed evaluation rows", "confidence_level": 0.95, "repetitions": 1, "seed_unit": "declared deterministic adapter seed"},
            "resource_limits": {"cpu_millis": 1000, "memory_mb": 512, "wall_time_seconds": 60, "max_output_bytes": 1024 * 1024},
            "stopping_rules": {"max_attempts": 1, "timeout_action": "stop_and_mark_timeout"},
            "assumptions": ["Framework test only."], "limitations": ["No published claim."], "known_deviations": [],
        }
    }


def create_fixture_context(client: TestClient, review: bool = False, finalize: bool = True) -> dict[str, str]:
    fixture = load_fixture()
    investigation = client.post("/api/v1/investigations", json={"name": "Stage 1 test", "source_kind": "synthetic_framework_test"})
    investigation_id = investigation.json()["id"]
    claim = client.post(f"/api/v1/investigations/{investigation_id}/claims", json={"statement": "The registered synthetic adapter produces a deterministic binary-classification output.", "metric_name": "accuracy", "reported_value": 0.75, "metric_direction": "maximize", "source_kind": "synthetic_framework_test", "source_locator": "fixture", "published": False})
    claim_id = claim.json()["id"]
    evidence = client.post(f"/api/v1/investigations/{investigation_id}/evidence", json={"claim_id": claim_id, "source_url": "https://reprolab.local/fixture", "source_locator": "fixture", "quoted_text": "fixture"})
    evidence_id = evidence.json()["id"]
    client.post(f"/api/v1/evidence/{evidence_id}/verify", json={"notes": "Manual review for test."})
    protocol = client.post(f"/api/v1/investigations/{investigation_id}/protocols", json=_protocol_payload(claim_id, evidence_id, fixture))
    protocol_id = protocol.json()["id"]
    if finalize:
        client.post(f"/api/v1/protocols/{protocol_id}/approve", json={"approved_by": "test"})
        client.post(f"/api/v1/protocols/{protocol_id}/freeze")
    return {"investigation_id": investigation_id, "claim_id": claim_id, "evidence_id": evidence_id, "protocol_id": protocol_id}


async def create_fixture_context_async(app) -> dict[str, str]:
    # Keep the helper API-level and deterministic while allowing async artifact tests.
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        fixture = load_fixture()
        investigation = await client.post("/api/v1/investigations", json={"name": "Stage 1 async test", "source_kind": "synthetic_framework_test"})
        investigation_id = investigation.json()["id"]
        claim = await client.post(f"/api/v1/investigations/{investigation_id}/claims", json={"statement": "The registered synthetic adapter produces a deterministic binary-classification output.", "metric_name": "accuracy", "reported_value": 0.75, "metric_direction": "maximize", "source_kind": "synthetic_framework_test", "source_locator": "fixture", "published": False})
        claim_id = claim.json()["id"]
        evidence = await client.post(f"/api/v1/investigations/{investigation_id}/evidence", json={"claim_id": claim_id, "source_url": "https://reprolab.local/fixture", "source_locator": "fixture", "quoted_text": "fixture"})
        evidence_id = evidence.json()["id"]
        await client.post(f"/api/v1/evidence/{evidence_id}/verify", json={"notes": "Manual review for test."})
        protocol = await client.post(f"/api/v1/investigations/{investigation_id}/protocols", json=_protocol_payload(claim_id, evidence_id, fixture))
        protocol_id = protocol.json()["id"]
        await client.post(f"/api/v1/protocols/{protocol_id}/approve", json={"approved_by": "test"})
        await client.post(f"/api/v1/protocols/{protocol_id}/freeze")
        return {"investigation_id": investigation_id, "claim_id": claim_id, "evidence_id": evidence_id, "protocol_id": protocol_id}
