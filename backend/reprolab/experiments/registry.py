from collections.abc import Callable

from reprolab.experiments.contracts import AdapterOutput, FixtureSpec, FrozenProtocolSnapshot
from reprolab.experiments.synthetic_binary_classification import run as run_synthetic
from reprolab.experiments.tabular_benchmark_classification import run as run_tabular

Adapter = Callable[[FrozenProtocolSnapshot, FixtureSpec | None], AdapterOutput]

_ADAPTERS: dict[str, Adapter] = {
    "synthetic_binary_classification_v1": run_synthetic,
    "tabular_benchmark_classification_v1": run_tabular,
}


def get_adapter(experiment_type: str) -> Adapter:
    try:
        return _ADAPTERS[experiment_type]
    except KeyError as exc:
        raise ValueError(f"Experiment type is not allowlisted: {experiment_type}") from exc


def list_experiment_types() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))
