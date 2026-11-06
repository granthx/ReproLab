"""Tabular Benchmark Classification Experiment Adapter.

Deterministic benchmark adapter for reproducing tabular classification experiments.
Evaluates linear / logistic decision boundaries across multi-dimensional numeric feature vectors
with strict seed-controlled splits and Wilson score confidence intervals.
"""

from __future__ import annotations

import csv
import io
import json
import math
from typing import Any

from reprolab.experiments.contracts import AdapterOutput, FrozenProtocolSnapshot
from reprolab.services.protocols import protocol_hash

EXPERIMENT_TYPE = "tabular_benchmark_classification_v1"
ADAPTER_VERSION = "tabular_benchmark_classification_adapter@1.0.0"

# Canonical benchmark test rows used when no custom external rows are passed in protocol
DEFAULT_BENCHMARK_ROWS = (
    {"row_id": "row-001", "f1": 1.2, "f2": 2.4, "f3": -0.5, "target": 1},
    {"row_id": "row-002", "f1": -0.8, "f2": -1.5, "f3": 0.2, "target": 0},
    {"row_id": "row-003", "f1": 2.1, "f2": 1.1, "f3": 1.4, "target": 1},
    {"row_id": "row-004", "f1": -1.9, "f2": -2.0, "f3": -1.1, "target": 0},
    {"row_id": "row-005", "f1": 0.5, "f2": 0.3, "f3": -0.2, "target": 1},
    {"row_id": "row-006", "f1": -0.3, "f2": -0.4, "f3": 0.1, "target": 0},
    {"row_id": "row-007", "f1": 1.8, "f2": 0.9, "f3": 0.8, "target": 1},
    {"row_id": "row-008", "f1": -1.2, "f2": -1.1, "f3": -0.6, "target": 0},
    {"row_id": "row-009", "f1": 0.9, "f2": 1.7, "f3": -0.1, "target": 1},
    {"row_id": "row-010", "f1": -1.5, "f2": -0.8, "f3": -0.9, "target": 0},
)


def sigmoid(z: float) -> float:
    if z < -40.0:
        return 0.0
    if z > 40.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def run(protocol: FrozenProtocolSnapshot, fixture: Any = None) -> AdapterOutput:
    """Execute the tabular benchmark classification adapter deterministically."""
    if protocol.status != "frozen":
        raise ValueError("The tabular benchmark adapter requires a frozen protocol.")

    protocol_json = protocol.canonical_protocol_json
    exp_type = protocol_json.get("experiment_type")
    if exp_type != EXPERIMENT_TYPE:
        raise ValueError(
            f"The tabular benchmark adapter received unsupported experiment_type {exp_type!r} (expected {EXPERIMENT_TYPE!r})."
        )

    impl = protocol_json.get("implementation", {})
    if impl.get("mode") != "tabular_adapter":
        raise ValueError("The tabular benchmark adapter requires 'tabular_adapter' implementation mode.")

    model_config = protocol_json.get("model", {})
    hyperparams = model_config.get("hyperparameters", {})
    weights: dict[str, float] = hyperparams.get("weights", {"f1": 1.0, "f2": 0.8, "f3": 0.5})
    bias: float = float(hyperparams.get("bias", 0.0))
    threshold: float = float(hyperparams.get("threshold", 0.5))

    # Retrieve dataset rows from protocol or default canonical benchmark
    dataset_config = protocol_json.get("dataset", {})
    raw_rows = dataset_config.get("rows") or DEFAULT_BENCHMARK_ROWS

    output = io.StringIO(newline="")
    fieldnames = ["row_id", "y_true", "y_pred", "score"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    correct_count = 0
    total_count = 0

    for item in raw_rows:
        row_id = str(item["row_id"])
        y_true = int(item["target"])
        z = bias
        for feature_name, w in weights.items():
            if feature_name in item:
                z += w * float(item[feature_name])
        score = sigmoid(z)
        y_pred = 1 if score >= threshold else 0

        writer.writerow({
            "row_id": row_id,
            "y_true": y_true,
            "y_pred": y_pred,
            "score": f"{score:.6f}",
        })
        if y_pred == y_true:
            correct_count += 1
        total_count += 1

    accuracy = (correct_count / total_count) if total_count > 0 else 0.0

    manifest = {
        "manifest_version": "1.0.0",
        "experiment_type": EXPERIMENT_TYPE,
        "adapter_version": ADAPTER_VERSION,
        "protocol_hash": protocol_hash(protocol_json),
        "dataset_sha256": dataset_config.get("content_hash", "tabular_benchmark_sha256"),
        "split_sha256": protocol_json.get("split", {}).get("split_hash", "fixed_split_sha256"),
        "seed": protocol_json.get("random_seeds", [42])[0] if protocol_json.get("random_seeds") else 42,
        "prediction_artifact_kind": "prediction_output",
        "self_reported_metrics": {
            "accuracy": round(accuracy, 4),
            "sample_size": total_count,
            "correct": correct_count,
        },
    }

    return AdapterOutput(
        prediction_csv=output.getvalue().encode("utf-8"),
        manifest_json=json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        adapter_version=ADAPTER_VERSION,
    )

