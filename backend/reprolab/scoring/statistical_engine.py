"""Statistical Verification Engine for ReproLab (Milestone 3).

Provides:
- Wilson 95% Score Confidence Intervals (Z = 1.95996... ~ 1.96)
- Delta metrics between claimed benchmark, baseline, and replicated results
- Categorical classification: VERIFIED_REPRODUCED, PARTIALLY_REPRODUCED, FAILED_TO_REPRODUCE, EXECUTION_FAILED
- "The Rail" SVG reproducibility gauge score calculation (0.0 to 100.0)
- OpenTelemetry span instrumentation on stage10.stat_engine.wilson_ci
"""

from dataclasses import dataclass
import math
from statistics import NormalDist
from typing import Optional, Tuple

from reprolab.core.telemetry import trace_span
from reprolab.schemas.contracts import EmpiricalClaimContract, ReproductionVerdict


@dataclass
class VerificationAssessment:
    """Full quantitative assessment of a reproduction run against claimed metrics."""
    verdict: ReproductionVerdict
    rail_gauge_score: float  # 0.0 to 100.0
    replicated_mean: float
    replicated_wilson_ci: Tuple[float, float]
    absolute_delta: float
    relative_delta_pct: float
    replicated_within_ci: bool
    beats_baseline: bool
    notes: str


class StatisticalVerificationEngine:
    """Computes exact statistical confidence intervals and determines reproduction verdicts."""

    def calculate_wilson_95_ci(
        self,
        successes: int,
        sample_size: int,
        confidence_level: float = 0.95,
    ) -> Tuple[float, float]:
        """Compute the Wilson score interval for a binomial proportion.
        
        Formula:
            center = (p + z^2 / (2n)) / (1 + z^2 / n)
            margin = (z * sqrt(p*(1-p)/n + z^2 / (4n^2))) / (1 + z^2 / n)
        """
        if sample_size <= 0:
            return (0.0, 0.0)
        
        # Clamp successes to valid range
        s = max(0, min(successes, sample_size))
        z = NormalDist().inv_cdf(1 - (1 - confidence_level) / 2)  # ~1.95996 for 95%
        
        p = s / sample_size
        denom = 1 + (z * z) / sample_size
        center = (p + (z * z) / (2 * sample_size)) / denom
        margin = (
            z * math.sqrt((p * (1 - p) / sample_size) + (z * z) / (4 * sample_size * sample_size))
        ) / denom

        low = max(0.0, center - margin)
        high = min(1.0, center + margin)
        return (round(low, 4), round(high, 4))

    def assess_reproduction(
        self,
        claim: EmpiricalClaimContract,
        replicated_mean: float,
        replicated_sample_size: int = 1000,
        execution_exit_code: int = 0,
        error_message: Optional[str] = None,
        case_id: Optional[str] = None,
    ) -> VerificationAssessment:
        """Evaluate replicated empirical measurements against paper claims and baseline."""
        with trace_span("stage10.stat_engine.wilson_ci", case_id=case_id) as span:
            # 1. Execution failure check
            if execution_exit_code != 0:
                span.set_attribute("verification.verdict", "EXECUTION_FAILED")
                span.set_attribute("verification.rail_score", 0.0)
                return VerificationAssessment(
                    verdict="EXECUTION_FAILED",
                    rail_gauge_score=0.0,
                    replicated_mean=0.0,
                    replicated_wilson_ci=(0.0, 0.0),
                    absolute_delta=0.0,
                    relative_delta_pct=0.0,
                    replicated_within_ci=False,
                    beats_baseline=False,
                    notes=f"Execution process terminated abnormally (exit code {execution_exit_code}): {error_message or 'Unknown error'}",
                )

            # 2. Compute Wilson 95% CI on replicated measurements
            est_successes = int(round(replicated_mean * replicated_sample_size))
            replicated_ci = self.calculate_wilson_95_ci(est_successes, replicated_sample_size)

            # 3. Calculate deltas
            abs_delta = round(replicated_mean - claim.claimed_mean, 4)
            rel_delta_pct = 0.0
            if claim.baseline_value and claim.baseline_value > 0:
                rel_delta_pct = round(((replicated_mean - claim.baseline_value) / claim.baseline_value) * 100, 2)

            # 4. Check CI containment
            claimed_low = claim.claimed_ci_low if claim.claimed_ci_low is not None else (claim.claimed_mean - 0.02)
            claimed_high = claim.claimed_ci_high if claim.claimed_ci_high is not None else (claim.claimed_mean + 0.02)
            within_ci = (claimed_low <= replicated_mean <= claimed_high)

            # 5. Check baseline comparison
            beats_baseline = True
            if claim.baseline_value is not None:
                if claim.direction == "maximize":
                    beats_baseline = (replicated_mean > claim.baseline_value)
                else:
                    beats_baseline = (replicated_mean < claim.baseline_value)

            # 6. Classification & "The Rail" Score
            # The Rail gauge score (0.0 to 100.0) synthesizes CI overlap and baseline margin
            if within_ci and beats_baseline:
                verdict: ReproductionVerdict = "VERIFIED_REPRODUCED"
                rail_score = round(min(100.0, 90.0 + (10.0 * (1.0 - abs(abs_delta) / 0.05))), 1)
                notes = (
                    f"Replication verified: replicated {claim.metric_name} ({replicated_mean}) "
                    f"falls within claimed 95% CI [{claimed_low}, {claimed_high}] and surpasses baseline ({claim.baseline_value})."
                )
            elif beats_baseline and abs(abs_delta) <= 0.05:
                verdict = "PARTIALLY_REPRODUCED"
                rail_score = round(max(50.0, min(89.9, 75.0 - (abs_delta * 100))), 1)
                notes = (
                    f"Partially reproduced: replicated {claim.metric_name} ({replicated_mean}) surpasses baseline ({claim.baseline_value}) "
                    f"with minor deviation (delta: {abs_delta}) from claimed mean ({claim.claimed_mean})."
                )
            else:
                verdict = "FAILED_TO_REPRODUCE"
                rail_score = round(max(0.0, 45.0 - (abs(abs_delta) * 100)), 1)
                notes = (
                    f"Failed to reproduce: replicated {claim.metric_name} ({replicated_mean}) failed to replicate claimed result "
                    f"({claim.claimed_mean}) or fell below baseline ({claim.baseline_value})."
                )

            span.set_attribute("verification.verdict", verdict)
            span.set_attribute("verification.rail_score", rail_score)
            span.set_attribute("verification.within_ci", within_ci)
            span.set_attribute("verification.abs_delta", abs_delta)

            return VerificationAssessment(
                verdict=verdict,
                rail_gauge_score=rail_score,
                replicated_mean=replicated_mean,
                replicated_wilson_ci=replicated_ci,
                absolute_delta=abs_delta,
                relative_delta_pct=rel_delta_pct,
                replicated_within_ci=within_ci,
                beats_baseline=beats_baseline,
                notes=notes,
            )

