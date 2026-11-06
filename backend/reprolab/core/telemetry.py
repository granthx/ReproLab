"""OpenTelemetry GenAI Instrumentation & Telemetry Core for ReproLab (Milestone 1).

Complies with:
- OpenTelemetry GenAI Semantic Conventions (Development status, v1.42.0+)
- docs/observability-plan.md span tree specifications
- Context propagation and token cost attribution
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
import time
from typing import Any, Dict, Iterator, Optional

# Structured logger
logger = logging.getLogger("reprolab.telemetry")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        json.dumps({
            "timestamp": "%(asctime)s",
            "level": "%(levelname)s",
            "logger": "%(name)s",
            "message": "%(message)s",
        })
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Pricing table per 1M tokens (from ADR-0001 & docs/observability-plan.md)
MODEL_PRICING = {
    "gemini-2.5-flash": {"input_per_m": 0.10, "cached_input_per_m": 0.025, "output_per_m": 0.40},
    "gemini-3.1-flash-lite": {"input_per_m": 0.05, "cached_input_per_m": 0.0125, "output_per_m": 0.20},
    "gemini-3.1-pro-preview": {"input_per_m": 1.25, "cached_input_per_m": 0.3125, "output_per_m": 5.00},
}

# Prometheus Metrics (docs/observability-plan.md §3)
CASES_STARTED = Counter(
    "reprolab_cases_started_total",
    "Total reproduction cases initiated",
    ["source_kind"],
)
CASES_COMPLETED = Counter(
    "reprolab_cases_completed_total",
    "Total reproduction cases completed",
    ["verdict"],
)
SANDBOX_ACTIVE = Gauge(
    "reprolab_sandbox_active_containers",
    "Current concurrent containers in execution",
)
GENAI_TOKENS = Counter(
    "gen_ai_client_tokens_total",
    "Tokens processed by foundation models",
    ["token_type", "model"],
)
EXTRACTION_PRECISION = Gauge(
    "reprolab_eval_extraction_precision",
    "Running precision of claim extraction",
)
PERSONA_ENTROPY = Gauge(
    "reprolab_eval_persona_entropy",
    "Shannon entropy measuring divergence across 12 personas",
)
DAILY_SPEND_USD = Counter(
    "reprolab_cost_spend_usd_total",
    "Cumulative spend on LLM inference in USD",
    ["model"],
)
AST_VIOLATIONS_TOTAL = Counter(
    "reprolab_security_ast_violations_total",
    "Total AST security check violations detected",
    ["rule_id"],
)


def generate_prometheus_metrics() -> bytes:
    """Export all registered Prometheus metrics in text format."""
    return generate_latest()


def calculate_token_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """Compute exact USD inference cost based on token counts and model pricing."""
    pricing = MODEL_PRICING.get(model_id, {"input_per_m": 0.10, "cached_input_per_m": 0.025, "output_per_m": 0.40})
    standard_input = max(0, input_tokens - cached_tokens)
    cost = (
        (standard_input * pricing["input_per_m"] / 1_000_000)
        + (cached_tokens * pricing["cached_input_per_m"] / 1_000_000)
        + (output_tokens * pricing["output_per_m"] / 1_000_000)
    )
    return round(cost, 6)


class SpanRecorder:
    """Records span timing, attributes, and events for tracing and structured logs."""

    def __init__(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.name = name
        self.attributes: Dict[str, Any] = attributes or {}
        self.events: list[dict] = []
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.duration_ms: int = 0
        self.status: str = "UNSET"
        self.error: Optional[str] = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        self.events.append({
            "name": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "attributes": attributes or {},
        })

    def record_exception(self, exc: Exception) -> None:
        self.status = "ERROR"
        self.error = str(exc)
        self.set_attribute("error.type", type(exc).__name__)
        self.set_attribute("error.message", str(exc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_name": self.name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": self.events,
            "error": self.error,
        }


@contextmanager
def trace_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    case_id: Optional[str] = None,
) -> Iterator[SpanRecorder]:
    """Context manager for tracing operational and database spans."""
    span = SpanRecorder(name, attributes)
    if case_id:
        span.set_attribute("app.reprolab.case_id", case_id)

    span.start_time = time.time()
    try:
        yield span
        span.status = "OK"
    except Exception as exc:
        span.record_exception(exc)
        raise
    finally:
        span.end_time = time.time()
        span.duration_ms = round((span.end_time - span.start_time) * 1000)
        logger.info(json.dumps(span.to_dict()))


@contextmanager
def genai_span(
    operation: str,
    model_id: str,
    case_id: Optional[str] = None,
    stage_node: Optional[str] = None,
) -> Iterator[SpanRecorder]:
    """Specialized context manager complying with OpenTelemetry GenAI Semantic Conventions."""
    attrs = {
        "gen_ai.provider.name": "google",
        "gen_ai.operation.name": operation,
        "gen_ai.request.model": model_id,
    }
    if stage_node:
        attrs["app.reprolab.stage_node"] = stage_node

    with trace_span(f"gen_ai.{operation} {model_id}", attributes=attrs, case_id=case_id) as span:
        yield span

