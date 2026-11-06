"""Stage 4 governed provider boundary (Google Gemini & deterministic source-grounded).

Enforces constitution model routing rules and ROLE_MAX_MODEL_CALLS ceilings:
- Deterministic roles (`max_calls == 0` or `required == False`, such as `atlas`,
  `curie`, `franklin`) never invoke an LLM and record `skipped_deterministic`.
- Conditional roles (`quill`, `sagan`, `hypatia`, `turing`, `popper`) record
  `skipped_conditional_not_needed` in `source_grounded` mode, or invoke Google
  Gemini (`google-genai`) in `gemini` mode within their role ceiling.
- If Gemini is requested (`provider_mode="gemini"`) and the API key is missing,
  the call budget is exceeded, or the provider fails, the failure is recorded
  as `failed_provider_error` or `blocked_budget` and never replaced with
  invented/fabricated output.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Protocol

from reprolab.core.config import Settings, get_settings
from reprolab.governance.contracts import ROLE_MAX_MODEL_CALLS
from reprolab.scientists.registry import get_constitutions


DETERMINISTIC_STAGE4_ROLES = frozenset({"atlas", "curie", "franklin"})
CONDITIONAL_STAGE4_ROLES = frozenset({"quill", "sagan", "hypatia", "turing", "popper"})
FORBIDDEN_STAGE4_ROLES = frozenset({"faraday", "fisher", "shannon", "noether"})
DETERMINISTIC_REPRODUCTION_ROLES = frozenset({"atlas", "curie", "faraday", "fisher", "franklin"})
CONDITIONAL_REPRODUCTION_ROLES = frozenset({"quill", "sagan", "hypatia", "turing", "popper", "shannon", "noether"})
FORBIDDEN_STAGE4_TOOLS = frozenset({
    "idempotent_runner_submit",
    "runner_status",
    "runner_cancel",
    "collect_artifacts",
    "independent_runner",
    "execute_code",
    "shell",
    "emit_measurement",
})


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ModelCallResult:
    provider: str
    model_name: str
    routing_category: str
    call_index: int
    max_calls_ceiling: int
    status: str
    prompt_sha256: str
    response_sha256: str | None
    input_tokens: int
    output_tokens: int
    summary_note: str | None = None
    error_detail: str | None = None


class WorkflowModelAdapter(Protocol):
    def generate(
        self,
        *,
        role_id: str,
        routing_category: str,
        prompt: str,
        model_name: str,
    ) -> tuple[str, int, int]:
        ...


class GoogleGenAIAdapter:
    """Thin wrapper around the official `google-genai` SDK."""

    def __init__(self, api_key: str | None) -> None:
        self._api_key = (api_key or "").strip()

    def generate(
        self,
        *,
        role_id: str,
        routing_category: str,
        prompt: str,
        model_name: str,
    ) -> tuple[str, int, int]:
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY / REPROLAB_GEMINI_API_KEY is not configured.")
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=400,
                system_instruction=(
                    f"You are recording a bounded source-grounded note for role '{role_id}' "
                    f"({routing_category}). Never invent claims, numbers, parameters, or "
                    "experimental results. Keep output under 300 characters."
                ),
            ),
        )
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            raise RuntimeError("Gemini provider returned an empty response.")
        usage = getattr(response, "usage_metadata", None)
        input_tokens = max(0, int(getattr(usage, "prompt_token_count", 0) or 0))
        output_tokens = max(0, int(getattr(usage, "candidates_token_count", 0) or 0))
        return text[:1000], input_tokens, output_tokens


def assert_stage4_role_and_tool_allowed(role_id: str, tool_id: str | None = None) -> None:
    """Enforce Stage 4's analysis-only boundary before any node executes."""

    if role_id in FORBIDDEN_STAGE4_ROLES:
        raise ValueError(
            f"Role {role_id!r} requires isolated execution or production measurements "
            "and is blocked in the Stage 4 analysis-only workflow."
        )
    if role_id not in (DETERMINISTIC_STAGE4_ROLES | CONDITIONAL_STAGE4_ROLES):
        raise ValueError(f"Role {role_id!r} is not permitted in the Stage 4 analysis workflow.")
    if tool_id is not None and tool_id in FORBIDDEN_STAGE4_TOOLS:
        raise ValueError(
            f"Tool {tool_id!r} is forbidden in the Stage 4 analysis-only workflow."
        )


def assert_reproduction_role_and_tool_allowed(role_id: str, tool_id: str | None = None) -> None:
    """Validate role permissions in the Stage 8 full reproduction workflow."""
    if role_id not in (DETERMINISTIC_REPRODUCTION_ROLES | CONDITIONAL_REPRODUCTION_ROLES):
        raise ValueError(f"Role {role_id!r} is not permitted in the reproduction workflow.")


def execute_governed_model_step(
    *,
    role_id: str,
    provider_mode: str,
    prompt: str,
    existing_calls_for_assignment: int,
    settings: Settings | None = None,
    adapter: WorkflowModelAdapter | None = None,
    workflow_kind: str = "analysis_only_v1",
) -> ModelCallResult:
    """Execute or deterministically skip a model call under constitution bounds."""

    if workflow_kind == "full_reproduction_v1":
        assert_reproduction_role_and_tool_allowed(role_id)
        deterministic_roles = DETERMINISTIC_REPRODUCTION_ROLES
    else:
        assert_stage4_role_and_tool_allowed(role_id)
        deterministic_roles = DETERMINISTIC_STAGE4_ROLES

    settings = settings or get_settings()
    constitutions = get_constitutions()
    constitution = constitutions.get(role_id)
    if constitution is None:
        routing_category = "deterministic"
    elif isinstance(constitution.model, dict):
        routing_category = str(constitution.model.get("routing") or "deterministic")
    else:
        routing_category = str(getattr(constitution.model, "routing", "deterministic"))
    ceiling = int(ROLE_MAX_MODEL_CALLS.get(role_id, 0))
    call_index = existing_calls_for_assignment + 1
    prompt_hash = _sha256(prompt)

    if role_id in deterministic_roles or ceiling == 0:
        return ModelCallResult(
            provider="deterministic_none",
            model_name="none",
            routing_category=routing_category,
            call_index=call_index,
            max_calls_ceiling=0,
            status="skipped_deterministic",
            prompt_sha256=prompt_hash,
            response_sha256=None,
            input_tokens=0,
            output_tokens=0,
            summary_note=None,
        )

    if provider_mode == "source_grounded":
        return ModelCallResult(
            provider="deterministic_none",
            model_name="none",
            routing_category=routing_category,
            call_index=call_index,
            max_calls_ceiling=ceiling,
            status="skipped_conditional_not_needed",
            prompt_sha256=prompt_hash,
            response_sha256=None,
            input_tokens=0,
            output_tokens=0,
            summary_note=None,
        )

    if call_index > ceiling:
        return ModelCallResult(
            provider="gemini",
            model_name=settings.gemini_model,
            routing_category=routing_category,
            call_index=call_index,
            max_calls_ceiling=ceiling,
            status="blocked_budget",
            prompt_sha256=prompt_hash,
            response_sha256=None,
            input_tokens=0,
            output_tokens=0,
            error_detail=(
                f"Role {role_id!r} exceeded its call ceiling ({ceiling}) for this assignment."
            ),
        )

    active_adapter = adapter or GoogleGenAIAdapter(settings.gemini_api_key)
    try:
        text, input_tokens, output_tokens = active_adapter.generate(
            role_id=role_id,
            routing_category=routing_category,
            prompt=prompt,
            model_name=settings.gemini_model,
        )
    except Exception as exc:
        return ModelCallResult(
            provider="gemini",
            model_name=settings.gemini_model,
            routing_category=routing_category,
            call_index=call_index,
            max_calls_ceiling=ceiling,
            status="failed_provider_error",
            prompt_sha256=prompt_hash,
            response_sha256=None,
            input_tokens=0,
            output_tokens=0,
            error_detail=str(exc)[:500] or "Gemini provider call failed.",
        )

    return ModelCallResult(
        provider="gemini",
        model_name=settings.gemini_model,
        routing_category=routing_category,
        call_index=call_index,
        max_calls_ceiling=ceiling,
        status="succeeded",
        prompt_sha256=prompt_hash,
        response_sha256=_sha256(text),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        summary_note=text,
    )
