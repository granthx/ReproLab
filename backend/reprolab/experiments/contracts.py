from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AdapterOutput:
    prediction_csv: bytes
    manifest_json: bytes
    adapter_version: str


@dataclass(frozen=True)
class FixtureRow:
    row_id: str
    feature_a: int
    feature_b: int
    target: int


@dataclass(frozen=True)
class FixtureSpec:
    experiment_type: str
    fixture_version: str
    dataset_sha256: str
    split_sha256: str
    row_id_column: str
    feature_columns: tuple[str, ...]
    target_column: str
    train_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    model_name: str
    threshold: float
    positive_if_sum_gte_threshold: bool
    seed: int
    prediction_columns: tuple[str, ...]
    target_values: tuple[int, ...]
    rows: tuple[FixtureRow, ...]

    @property
    def rows_by_id(self) -> dict[str, FixtureRow]:
        return {row.row_id: row for row in self.rows}


@dataclass(frozen=True)
class FrozenProtocolSnapshot:
    id: str
    status: str
    canonical_protocol_json: dict[str, Any]
    protocol_hash: str
