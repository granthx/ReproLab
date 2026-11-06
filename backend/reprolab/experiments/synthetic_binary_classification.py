import csv
import io
import json

from reprolab.experiments.contracts import AdapterOutput, FixtureSpec, FrozenProtocolSnapshot
from reprolab.experiments.fixture_loader import EXPECTED_EXPERIMENT_TYPE, load_fixture
from reprolab.services.protocols import protocol_hash

ADAPTER_VERSION = "synthetic_binary_classification_adapter@1.0.0"


def run(protocol: FrozenProtocolSnapshot, fixture: FixtureSpec | None = None) -> AdapterOutput:
    """Generate fixture artifacts for internal tests; this is not a runner or API operation."""
    fixture = fixture or load_fixture()
    protocol_json = protocol.canonical_protocol_json
    if protocol.status != "frozen":
        raise ValueError("The fixture adapter requires a frozen protocol.")
    if protocol_json.get("experiment_type") != EXPECTED_EXPERIMENT_TYPE:
        raise ValueError("The fixture adapter received an unsupported experiment type.")
    if protocol_json.get("dataset", {}).get("content_hash") != fixture.dataset_sha256:
        raise ValueError("The fixture adapter received a mismatched dataset hash.")
    if protocol_json.get("split", {}).get("split_hash") != fixture.split_sha256:
        raise ValueError("The fixture adapter received a mismatched split hash.")
    if protocol_json.get("implementation", {}).get("mode") != "synthetic_adapter":
        raise ValueError("The fixture adapter requires synthetic_adapter implementation mode.")
    if protocol_json.get("implementation", {}).get("adapter_version") != ADAPTER_VERSION:
        raise ValueError("The fixture adapter version is not declared in the protocol.")

    rows_by_id = fixture.rows_by_id
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(fixture.prediction_columns), lineterminator="\n")
    writer.writeheader()
    for row_id in fixture.test_ids:
        row = rows_by_id[row_id]
        score = row.feature_a + row.feature_b
        prediction = int(score >= fixture.threshold) if fixture.positive_if_sum_gte_threshold else int(score > fixture.threshold)
        writer.writerow({"row_id": row.row_id, "y_true": row.target, "y_pred": prediction, "score": score})

    manifest = {
        "manifest_version": "1.0.0",
        "experiment_type": EXPECTED_EXPERIMENT_TYPE,
        "adapter_version": ADAPTER_VERSION,
        "protocol_hash": protocol_hash(protocol_json),
        "dataset_sha256": fixture.dataset_sha256,
        "split_sha256": fixture.split_sha256,
        "seed": fixture.seed,
        "prediction_artifact_kind": "prediction_output",
        "self_reported_metrics": {"accuracy": 0.0},
    }
    return AdapterOutput(
        prediction_csv=output.getvalue().encode("utf-8"),
        manifest_json=json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        adapter_version=ADAPTER_VERSION,
    )
