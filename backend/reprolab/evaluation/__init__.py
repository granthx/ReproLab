"""Scientific Evaluation package for ReproLab."""

from reprolab.evaluation.engine import (
    run_scientific_evaluation,
    score_extraction_quality,
    score_scientific_claim_verification,
    score_technical_reproducibility,
)

__all__ = [
    "run_scientific_evaluation",
    "score_extraction_quality",
    "score_technical_reproducibility",
    "score_scientific_claim_verification",
]

