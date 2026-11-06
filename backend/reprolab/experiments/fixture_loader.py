import csv
import hashlib
import json
from pathlib import Path

from reprolab.experiments.contracts import FixtureRow, FixtureSpec


class FixtureIntegrityError(ValueError):
    pass


EXPECTED_EXPERIMENT_TYPE = "synthetic_binary_classification_v1"
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / EXPECTED_EXPERIMENT_TYPE


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_csv(path: Path, required_columns: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            if tuple(reader.fieldnames or ()) != required_columns:
                raise FixtureIntegrityError(f"Unexpected columns in {path.name}.")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise FixtureIntegrityError(f"Could not read fixture file {path.name}.") from exc
    if not rows:
        raise FixtureIntegrityError(f"Fixture file {path.name} is empty.")
    return rows


def load_fixture(root: Path = FIXTURE_ROOT) -> FixtureSpec:
    try:
        metadata = json.loads((root / "fixture.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FixtureIntegrityError("Fixture metadata is unreadable.") from exc

    if metadata.get("experiment_type") != EXPECTED_EXPERIMENT_TYPE:
        raise FixtureIntegrityError("Fixture experiment type is not allowlisted.")
    dataset_path = root / metadata.get("dataset_file", "")
    split_path = root / metadata.get("split_file", "")
    try:
        dataset_bytes = dataset_path.read_bytes()
        split_bytes = split_path.read_bytes()
    except OSError as exc:
        raise FixtureIntegrityError("Fixture data files are unavailable.") from exc
    actual_dataset_hash = sha256_bytes(dataset_bytes)
    actual_split_hash = sha256_bytes(split_bytes)
    if actual_dataset_hash != metadata.get("dataset_sha256"):
        raise FixtureIntegrityError("Fixture dataset hash does not match fixture metadata.")
    if actual_split_hash != metadata.get("split_sha256"):
        raise FixtureIntegrityError("Fixture split hash does not match fixture metadata.")
    if metadata.get("row_id_column") != "row_id":
        raise FixtureIntegrityError("Fixture row identifier metadata is invalid.")
    if tuple(metadata.get("feature_columns", ())) != ("feature_a", "feature_b"):
        raise FixtureIntegrityError("Fixture feature metadata is invalid.")
    if metadata.get("target_column") != "target":
        raise FixtureIntegrityError("Fixture target metadata is invalid.")

    dataset_rows = _read_csv(dataset_path, ("row_id", "feature_a", "feature_b", "target"))
    split_rows = _read_csv(split_path, ("row_id", "split"))
    rows: list[FixtureRow] = []
    seen_ids: set[str] = set()
    for raw in dataset_rows:
        row_id = raw["row_id"]
        if not row_id or row_id in seen_ids:
            raise FixtureIntegrityError("Fixture row identifiers must be non-empty and unique.")
        seen_ids.add(row_id)
        try:
            feature_a = int(raw["feature_a"])
            feature_b = int(raw["feature_b"])
            target = int(raw["target"])
        except (TypeError, ValueError) as exc:
            raise FixtureIntegrityError("Fixture feature and target values must be integers.") from exc
        if target not in {0, 1}:
            raise FixtureIntegrityError("Fixture targets must be binary.")
        rows.append(FixtureRow(row_id, feature_a, feature_b, target))

    split_ids: set[str] = set()
    train_ids: list[str] = []
    test_ids: list[str] = []
    for raw in split_rows:
        row_id = raw["row_id"]
        if row_id in split_ids or row_id not in seen_ids:
            raise FixtureIntegrityError("Fixture split identifiers must match dataset identifiers exactly once.")
        split_ids.add(row_id)
        if raw["split"] == metadata.get("train_label"):
            train_ids.append(row_id)
        elif raw["split"] == metadata.get("test_label"):
            test_ids.append(row_id)
        else:
            raise FixtureIntegrityError("Fixture split contains an unknown split label.")
    if split_ids != seen_ids or not train_ids or not test_ids:
        raise FixtureIntegrityError("Fixture split must cover every dataset row with train and test rows.")

    model = metadata.get("model") or {}
    prediction_schema = metadata.get("prediction_schema") or {}
    if model.get("name") != "deterministic_linear_threshold" or model.get("threshold") != 0.5:
        raise FixtureIntegrityError("Fixture model metadata is invalid.")
    if model.get("positive_if_sum_gte_threshold") is not True:
        raise FixtureIntegrityError("Fixture classifier direction metadata is invalid.")
    if tuple(prediction_schema.get("required_columns", ())) != ("row_id", "y_true", "y_pred", "score"):
        raise FixtureIntegrityError("Fixture prediction schema metadata is invalid.")
    if tuple(prediction_schema.get("target_values", ())) != (0, 1):
        raise FixtureIntegrityError("Fixture prediction target metadata is invalid.")
    try:
        return FixtureSpec(
            experiment_type=EXPECTED_EXPERIMENT_TYPE,
            fixture_version=str(metadata["fixture_version"]),
            dataset_sha256=actual_dataset_hash,
            split_sha256=actual_split_hash,
            row_id_column=str(metadata["row_id_column"]),
            feature_columns=tuple(metadata["feature_columns"]),
            target_column=str(metadata["target_column"]),
            train_ids=tuple(train_ids),
            test_ids=tuple(test_ids),
            model_name=str(model["name"]),
            threshold=float(model["threshold"]),
            positive_if_sum_gte_threshold=bool(model["positive_if_sum_gte_threshold"]),
            seed=int(metadata["seed"]),
            prediction_columns=tuple(prediction_schema["required_columns"]),
            target_values=tuple(int(value) for value in prediction_schema["target_values"]),
            rows=tuple(rows),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FixtureIntegrityError("Fixture metadata is incomplete or malformed.") from exc
