import csv
import hashlib
import io
import json
import math
from dataclasses import asdict, dataclass
from statistics import NormalDist
from typing import Any

from reprolab.experiments.contracts import FixtureSpec, FrozenProtocolSnapshot
from reprolab.experiments.fixture_loader import EXPECTED_EXPERIMENT_TYPE
from reprolab.experiments.synthetic_binary_classification import ADAPTER_VERSION
from reprolab.schemas.research import ProtocolDefinition
from reprolab.services.protocols import protocol_hash

SCORER_VERSION = "trusted_accuracy_scorer@1.0.0"


class ScoringValidationError(ValueError):
    pass


@dataclass(frozen=True)
class TrustedMeasurement:
    metric_name: str
    value: float
    unit: str
    sample_size: int
    analysis_unit: str
    seed: int
    confidence_level: float
    interval_lower: float
    interval_upper: float
    scoring_method: str
    scorer_version: str
    prediction_artifact_sha256: str
    manifest_artifact_sha256: str
    protocol_hash: str
    dataset_hash: str
    split_hash: str
    adapter_version: str
    source_kind: str
    claim_assessment: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def wilson_interval(successes: int, sample_size: int, confidence_level: float = 0.95) -> tuple[float, float]:
    if sample_size <= 0 or successes < 0 or successes > sample_size:
        raise ScoringValidationError("Wilson interval requires 0 <= successes <= sample_size and sample_size > 0")
    if not 0 < confidence_level < 1:
        raise ScoringValidationError("confidence_level must be between 0 and 1")
    z = NormalDist().inv_cdf(1 - (1 - confidence_level) / 2)
    proportion = successes / sample_size
    denominator = 1 + z * z / sample_size
    center = (proportion + z * z / (2 * sample_size)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / sample_size
            + z * z / (4 * sample_size * sample_size)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _require_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise ScoringValidationError(message)


def _validate_frozen_protocol(protocol: FrozenProtocolSnapshot, fixture: FixtureSpec) -> tuple[ProtocolDefinition, str]:
    if protocol.status != "frozen":
        raise ScoringValidationError("Scoring requires a frozen protocol")
    actual_protocol_hash = protocol_hash(protocol.canonical_protocol_json)
    _require_equal(actual_protocol_hash, protocol.protocol_hash, "Stored protocol hash does not match its contents")
    try:
        definition = ProtocolDefinition.model_validate(protocol.canonical_protocol_json)
    except Exception as exc:
        raise ScoringValidationError("Frozen protocol contents are invalid") from exc

    _require_equal(definition.source_kind, "synthetic_framework_test", "Scoring accepts synthetic framework protocols only")
    _require_equal(definition.experiment_type, EXPECTED_EXPERIMENT_TYPE, "Protocol experiment type is not allowlisted")
    _require_equal(definition.implementation.mode, "synthetic_adapter", "Protocol implementation is not the synthetic adapter")
    _require_equal(
        definition.implementation.adapter_version,
        ADAPTER_VERSION,
        "Protocol adapter version does not match the registered adapter",
    )
    _require_equal(definition.dataset.content_hash, fixture.dataset_sha256, "Protocol dataset hash does not match fixture")
    _require_equal(definition.split.split_hash, fixture.split_sha256, "Protocol split hash does not match fixture")
    _require_equal(definition.random_seeds, [fixture.seed], "Protocol seed configuration does not match fixture")
    _require_equal(definition.primary_metric.name, "accuracy", "Protocol metric is not accuracy")
    _require_equal(definition.primary_metric.direction, "maximize", "Protocol metric direction is invalid")
    _require_equal(definition.primary_metric.unit, "proportion", "Protocol metric unit is invalid")
    _require_equal(definition.primary_metric.analysis_unit, "evaluation row", "Protocol analysis unit is invalid")
    _require_equal(definition.model.name, fixture.model_name, "Protocol model does not match fixture")
    hyperparameters = definition.model.hyperparameters
    try:
        threshold = float(hyperparameters["threshold"])
        positive_if_sum_gte_threshold = bool(hyperparameters["positive_if_sum_gte_threshold"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ScoringValidationError("Protocol classifier configuration is incomplete") from exc
    _require_equal(threshold, fixture.threshold, "Protocol threshold does not match fixture")
    _require_equal(
        positive_if_sum_gte_threshold,
        fixture.positive_if_sum_gte_threshold,
        "Protocol classifier direction does not match fixture",
    )
    return definition, actual_protocol_hash


def _validate_manifest(
    manifest_bytes: bytes,
    *,
    expected_manifest_sha256: str,
    protocol_hash_value: str,
    fixture: FixtureSpec,
) -> dict[str, Any]:
    actual_manifest_sha256 = _sha256(manifest_bytes)
    _require_equal(actual_manifest_sha256, expected_manifest_sha256, "Manifest artifact hash does not match its contents")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScoringValidationError("Manifest artifact is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise ScoringValidationError("Manifest artifact must contain a JSON object")
    _require_equal(manifest.get("experiment_type"), EXPECTED_EXPERIMENT_TYPE, "Manifest experiment type is invalid")
    _require_equal(manifest.get("adapter_version"), ADAPTER_VERSION, "Manifest adapter version is invalid")
    _require_equal(manifest.get("protocol_hash"), protocol_hash_value, "Manifest protocol hash is invalid")
    _require_equal(manifest.get("dataset_sha256"), fixture.dataset_sha256, "Manifest dataset hash is invalid")
    _require_equal(manifest.get("split_sha256"), fixture.split_sha256, "Manifest split hash is invalid")
    _require_equal(manifest.get("seed"), fixture.seed, "Manifest seed is invalid")
    return manifest


def _validated_prediction_rows(prediction_bytes: bytes, fixture: FixtureSpec) -> list[dict[str, Any]]:
    try:
        text = prediction_bytes.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""))
    except UnicodeDecodeError as exc:
        raise ScoringValidationError("Prediction artifact is not valid UTF-8") from exc
    if tuple(reader.fieldnames or ()) != fixture.prediction_columns:
        raise ScoringValidationError("Prediction artifact columns do not match the required schema")
    raw_rows = list(reader)
    if len(raw_rows) != len(fixture.test_ids):
        raise ScoringValidationError("Prediction artifact row count does not match evaluation rows")
    expected_ids = list(fixture.test_ids)
    actual_ids = [row.get("row_id", "") for row in raw_rows]
    if len(set(actual_ids)) != len(actual_ids):
        raise ScoringValidationError("Prediction artifact contains duplicate row identifiers")
    if actual_ids != expected_ids:
        raise ScoringValidationError("Prediction artifact evaluation rows do not exactly match the declared split")

    trusted_rows = fixture.rows_by_id
    validated: list[dict[str, Any]] = []
    for row in raw_rows:
        row_id = row["row_id"]
        try:
            y_true = int(row["y_true"])
            y_pred = int(row["y_pred"])
            score = float(row["score"])
        except (TypeError, ValueError) as exc:
            raise ScoringValidationError("Prediction artifact contains malformed numeric values") from exc
        if y_true not in fixture.target_values or y_pred not in fixture.target_values:
            raise ScoringValidationError("Prediction labels are outside the declared target values")
        if not math.isfinite(score):
            raise ScoringValidationError("Prediction scores must be finite")
        if y_true != trusted_rows[row_id].target:
            raise ScoringValidationError("Prediction artifact ground-truth label does not match trusted fixture data")
        validated.append({"row_id": row_id, "y_true": y_true, "y_pred": y_pred, "score": score})
    return validated


def score_synthetic_output(
    protocol: FrozenProtocolSnapshot,
    fixture: FixtureSpec,
    *,
    prediction_bytes: bytes,
    prediction_artifact_sha256: str,
    manifest_bytes: bytes,
    manifest_artifact_sha256: str,
) -> TrustedMeasurement:
    """Validate artifacts and recompute accuracy without accepting adapter metrics."""
    definition, actual_protocol_hash = _validate_frozen_protocol(protocol, fixture)
    actual_prediction_hash = _sha256(prediction_bytes)
    _require_equal(actual_prediction_hash, prediction_artifact_sha256, "Prediction artifact hash does not match its contents")
    _validate_manifest(
        manifest_bytes,
        expected_manifest_sha256=manifest_artifact_sha256,
        protocol_hash_value=actual_protocol_hash,
        fixture=fixture,
    )
    rows = _validated_prediction_rows(prediction_bytes, fixture)
    successes = sum(row["y_true"] == row["y_pred"] for row in rows)
    value = successes / len(rows)
    confidence_level = definition.statistical_analysis.confidence_level
    lower, upper = wilson_interval(successes, len(rows), confidence_level)
    return TrustedMeasurement(
        metric_name="accuracy",
        value=value,
        unit="proportion",
        sample_size=len(rows),
        analysis_unit="evaluation row",
        seed=fixture.seed,
        confidence_level=confidence_level,
        interval_lower=lower,
        interval_upper=upper,
        scoring_method="trusted accuracy recomputation with Wilson score interval",
        scorer_version=SCORER_VERSION,
        prediction_artifact_sha256=actual_prediction_hash,
        manifest_artifact_sha256=manifest_artifact_sha256,
        protocol_hash=actual_protocol_hash,
        dataset_hash=fixture.dataset_sha256,
        split_hash=fixture.split_sha256,
        adapter_version=ADAPTER_VERSION,
        source_kind="synthetic_framework_test",
        claim_assessment="framework_test_only",
    )


def calculate_accuracy(
    *,
    protocol: FrozenProtocolSnapshot,
    prediction_bytes: bytes,
    manifest_bytes: bytes,
    fixture: FixtureSpec | None = None,
) -> TrustedMeasurement:
    """Convenience scorer wrapper computing artifact hashes directly."""
    pred_hash = _sha256(prediction_bytes)
    man_hash = _sha256(manifest_bytes)
    exp_type = protocol.canonical_protocol_json.get("experiment_type", EXPECTED_EXPERIMENT_TYPE)
    if exp_type == "tabular_benchmark_classification_v1":
        return score_tabular_output(
            protocol=protocol,
            prediction_bytes=prediction_bytes,
            prediction_artifact_sha256=pred_hash,
            manifest_bytes=manifest_bytes,
            manifest_artifact_sha256=man_hash,
        )
    if fixture is None:
        fixture = load_fixture()
    return score_synthetic_output(
        protocol=protocol,
        fixture=fixture,
        prediction_bytes=prediction_bytes,
        prediction_artifact_sha256=pred_hash,
        manifest_bytes=manifest_bytes,
        manifest_artifact_sha256=man_hash,
    )


TABULAR_EXPERIMENT_TYPE = "tabular_benchmark_classification_v1"
TABULAR_ADAPTER_VERSION = "tabular_benchmark_classification_adapter@1.0.0"


def score_tabular_output(
    protocol: FrozenProtocolSnapshot,
    *,
    prediction_bytes: bytes,
    prediction_artifact_sha256: str,
    manifest_bytes: bytes,
    manifest_artifact_sha256: str,
) -> TrustedMeasurement:
    """Validate tabular benchmark output and recompute accuracy independently."""
    if protocol.status != "frozen":
        raise ScoringValidationError("Scoring requires a frozen protocol")
    actual_proto_hash = protocol_hash(protocol.canonical_protocol_json)
    _require_equal(actual_proto_hash, protocol.protocol_hash, "Stored protocol hash does not match its contents")

    actual_pred_hash = _sha256(prediction_bytes)
    _require_equal(actual_pred_hash, prediction_artifact_sha256, "Prediction artifact hash does not match its contents")

    actual_man_hash = _sha256(manifest_bytes)
    _require_equal(actual_man_hash, manifest_artifact_sha256, "Manifest artifact hash does not match its contents")

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except Exception as exc:
        raise ScoringValidationError("Manifest artifact is not valid UTF-8 JSON") from exc

    _require_equal(manifest.get("experiment_type"), TABULAR_EXPERIMENT_TYPE, "Manifest experiment type is invalid")
    _require_equal(manifest.get("adapter_version"), TABULAR_ADAPTER_VERSION, "Manifest adapter version is invalid")
    _require_equal(manifest.get("protocol_hash"), actual_proto_hash, "Manifest protocol hash is invalid")

    try:
        reader = csv.DictReader(io.StringIO(prediction_bytes.decode("utf-8"), newline=""))
    except Exception as exc:
        raise ScoringValidationError("Prediction artifact is not valid UTF-8 CSV") from exc

    expected_cols = ("row_id", "y_true", "y_pred", "score")
    if tuple(reader.fieldnames or ()) != expected_cols:
        raise ScoringValidationError(f"Prediction artifact columns do not match expected schema {expected_cols}")

    rows = list(reader)
    if not rows:
        raise ScoringValidationError("Prediction artifact contains no rows")

    successes = 0
    for r in rows:
        try:
            yt = int(r["y_true"])
            yp = int(r["y_pred"])
            sc = float(r["score"])
        except (ValueError, TypeError) as exc:
            raise ScoringValidationError("Prediction artifact contains invalid numeric values") from exc
        if yt not in (0, 1) or yp not in (0, 1):
            raise ScoringValidationError("Prediction labels must be 0 or 1")
        if not math.isfinite(sc):
            raise ScoringValidationError("Prediction score must be finite")
        if yt == yp:
            successes += 1

    sample_size = len(rows)
    acc = successes / sample_size
    conf_level = float(protocol.canonical_protocol_json.get("statistical_analysis", {}).get("confidence_level", 0.95))
    lower, upper = wilson_interval(successes, sample_size, conf_level)

    dataset_hash = str(manifest.get("dataset_sha256", "tabular_benchmark_sha256"))
    split_hash = str(manifest.get("split_sha256", "fixed_split_sha256"))
    seed = int(manifest.get("seed", 42))

    return TrustedMeasurement(
        metric_name="accuracy",
        value=acc,
        unit="proportion",
        sample_size=sample_size,
        analysis_unit="evaluation row",
        seed=seed,
        confidence_level=conf_level,
        interval_lower=lower,
        interval_upper=upper,
        scoring_method="trusted tabular accuracy recomputation with Wilson score interval",
        scorer_version=SCORER_VERSION,
        prediction_artifact_sha256=actual_pred_hash,
        manifest_artifact_sha256=actual_man_hash,
        protocol_hash=actual_proto_hash,
        dataset_hash=dataset_hash,
        split_hash=split_hash,
        adapter_version=TABULAR_ADAPTER_VERSION,
        source_kind="tabular_framework_test",
        claim_assessment="framework_test_only",
    )

