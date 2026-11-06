"""Scientific Evaluation Engine for ReproLab.

Rigorously separates and scores:
1. Extraction Quality (claim & protocol fidelity from paper intake)
2. Technical Reproducibility (hermetic execution success, artifact schema integrity)
3. Scientific Claim Verification & Statistical Independence (independent trusted scorer vs paper claims)

Execution failures are strictly classified as 'execution_failed', never confused with scientific disconfirmation.
"""

from datetime import datetime, timezone
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.models.evaluation import ScientificEvaluation
from reprolab.models.execution import AttemptRecord, ExperimentJob, ProductionMeasurement
from reprolab.models.research import Claim, Investigation, ProtocolVersion


def score_extraction_quality(
    claim: Claim | None,
    protocol: ProtocolVersion | None,
) -> tuple[float, dict[str, Any]]:
    """
    Score the fidelity, completeness, and structure of extracted claims and protocols.
    """
    breakdown: dict[str, Any] = {
        "claim_present": claim is not None,
        "protocol_present": protocol is not None,
        "metric_defined": False,
        "direction_defined": False,
        "numerical_claim_valid": False,
        "protocol_frozen": False,
        "protocol_steps_complete": False,
    }

    if not claim and not protocol:
        return 0.0, breakdown

    points = 0.0
    total_points = 5.0

    if claim:
        if claim.metric_name:
            breakdown["metric_defined"] = True
            points += 1.0
        if claim.metric_direction:
            breakdown["direction_defined"] = True
            points += 1.0
        if claim.reported_value is not None and claim.reported_value >= 0.0:
            breakdown["numerical_claim_valid"] = True
            points += 1.0

    if protocol:
        if protocol.status == "frozen":
            breakdown["protocol_frozen"] = True
            points += 1.0
        # Check protocol steps completeness
        payload = protocol.canonical_protocol_json
        if payload and isinstance(payload, dict):
            if "dataset" in payload or "model" in payload or "steps" in payload or "tasks" in payload:
                breakdown["protocol_steps_complete"] = True
                points += 1.0

    score = round(points / total_points, 4)
    return score, breakdown


def score_technical_reproducibility(
    job: ExperimentJob | None,
    attempt: AttemptRecord | None,
    measurements: list[ProductionMeasurement],
) -> tuple[float, dict[str, Any]]:
    """
    Score whether the computation executed cleanly without crash/timeout in the sandbox,
    and produced valid, schema-compliant artifacts.
    """
    breakdown: dict[str, Any] = {
        "job_present": job is not None,
        "job_status": job.status if job else None,
        "attempt_succeeded": False,
        "exit_code_zero": False,
        "artifacts_generated": False,
        "measurements_computed": False,
    }

    if not job or not attempt:
        return 0.0, breakdown

    points = 0.0
    total_points = 4.0

    if job.status == "completed" and attempt.status == "completed":
        breakdown["attempt_succeeded"] = True
        points += 1.0

    if attempt.exit_code == 0:
        breakdown["exit_code_zero"] = True
        points += 1.0

    if attempt.output_artifact_ids and len(attempt.output_artifact_ids) >= 1:
        breakdown["artifacts_generated"] = True
        points += 1.0

    if len(measurements) > 0:
        breakdown["measurements_computed"] = True
        points += 1.0

    score = round(points / total_points, 4)
    return score, breakdown


def score_scientific_claim_verification(
    claim: Claim | None,
    job: ExperimentJob | None,
    measurements: list[ProductionMeasurement],
) -> tuple[float, str, dict[str, Any]]:
    """
    Statistically evaluate independent trusted production measurements against original paper claims.
    Returns: (score, verdict, breakdown)
    Verdicts: 'reproduced', 'disconfirmed', 'inconclusive', 'execution_failed'
    """
    breakdown: dict[str, Any] = {
        "claimed_value": claim.reported_value if claim else None,
        "target_metric": claim.metric_name if claim else None,
        "direction": claim.metric_direction if claim else None,
        "measured_value": None,
        "interval_lower": None,
        "interval_upper": None,
        "sample_size": None,
        "statistical_verdict": None,
        "verdict_reason": "",
    }

    # Boundary rule: If technical execution failed, scientific claim cannot be assessed as disconfirmed
    if not job or job.status != "completed":
        breakdown["statistical_verdict"] = "execution_failed"
        breakdown["verdict_reason"] = f"Execution job status is '{job.status if job else 'none'}'; technical execution must complete before scientific claims can be tested."
        return 0.0, "execution_failed", breakdown

    if not claim or claim.reported_value is None:
        breakdown["statistical_verdict"] = "inconclusive"
        breakdown["verdict_reason"] = "No quantitative baseline claim found to verify."
        return 0.5, "inconclusive", breakdown

    if not measurements:
        breakdown["statistical_verdict"] = "inconclusive"
        breakdown["verdict_reason"] = "No production measurements available for statistical verification."
        return 0.5, "inconclusive", breakdown

    # Find matching measurement for the claim's target metric
    target_metric = (claim.metric_name or "accuracy").lower()
    matching_measurement = next(
        (m for m in measurements if target_metric in m.metric_name.lower() or m.metric_name.lower() in target_metric),
        measurements[0]
    )

    claimed_val = claim.reported_value
    measured_val = matching_measurement.value
    l_bound = matching_measurement.interval_lower
    u_bound = matching_measurement.interval_upper
    sample_size = matching_measurement.sample_size

    breakdown["measured_value"] = measured_val
    breakdown["interval_lower"] = l_bound
    breakdown["interval_upper"] = u_bound
    breakdown["sample_size"] = sample_size

    # Check sample size adequacy (e.g. at least 4 items for minimal statistical confidence)
    if sample_size is not None and sample_size < 4:
        breakdown["statistical_verdict"] = "inconclusive"
        breakdown["verdict_reason"] = f"Sample size {sample_size} is insufficient for statistically sound verification."
        return 0.5, "inconclusive", breakdown

    # Interval evaluation:
    # 1. If interval bounds exist, test if claimed value falls within confidence interval [L, U]
    #    or if measured value equals or exceeds claimed value (for 'higher_is_better' / 'gte')
    direction = (claim.metric_direction or "higher_is_better").lower()

    if l_bound is not None and u_bound is not None:
        if l_bound <= claimed_val <= u_bound:
            # Claimed value is directly consistent with independent confidence interval
            breakdown["statistical_verdict"] = "reproduced"
            breakdown["verdict_reason"] = f"Claimed value {claimed_val} falls inside the 95% Wilson confidence interval [{l_bound:.4f}, {u_bound:.4f}] around measured value {measured_val:.4f}."
            return 1.0, "reproduced", breakdown

        if direction in {"higher_is_better", "gte", "max"} and measured_val >= claimed_val:
            # Measured performance exceeds or matches claim
            breakdown["statistical_verdict"] = "reproduced"
            breakdown["verdict_reason"] = f"Measured performance {measured_val:.4f} satisfies threshold claim >= {claimed_val}."
            return 1.0, "reproduced", breakdown

        if direction in {"higher_is_better", "gte", "max"} and claimed_val > u_bound:
            # Significant underperformance outside confidence interval
            breakdown["statistical_verdict"] = "disconfirmed"
            breakdown["verdict_reason"] = f"Claimed value {claimed_val} significantly exceeds the 95% Wilson upper confidence bound ({u_bound:.4f}) of independent measurement {measured_val:.4f}."
            return 0.0, "disconfirmed", breakdown

    # Fallback to direct numerical comparison with 5% tolerance margin
    diff = abs(measured_val - claimed_val)
    if diff <= 0.05 or (direction in {"higher_is_better", "gte"} and measured_val >= claimed_val):
        breakdown["statistical_verdict"] = "reproduced"
        breakdown["verdict_reason"] = f"Measured value {measured_val:.4f} is within acceptable tolerance of claimed value {claimed_val}."
        return 1.0, "reproduced", breakdown
    else:
        breakdown["statistical_verdict"] = "disconfirmed"
        breakdown["verdict_reason"] = f"Measured value {measured_val:.4f} deviates significantly from claimed value {claimed_val} (diff: {diff:.4f})."
        return 0.0, "disconfirmed", breakdown


async def run_scientific_evaluation(
    investigation_id: str,
    db: AsyncSession,
    job_id: str | None = None,
    claim_id: str | None = None,
    summary_notes: str | None = None,
    commit: bool = True,
) -> ScientificEvaluation:
    """
    Run an end-to-end scientific evaluation across Extraction, Technical Reproducibility,
    and Claim Verification, persisting the immutable audit record.
    """
    # 1. Fetch investigation and paper
    investigation = await db.get(Investigation, investigation_id)
    if not investigation:
        raise ValueError(f"Investigation {investigation_id} not found.")

    # 2. Fetch claim
    claim: Claim | None = None
    if claim_id:
        claim = await db.get(Claim, claim_id)
    if not claim:
        claims_stmt = select(Claim).where(Claim.investigation_id == investigation_id).order_by(Claim.created_at.desc())
        claim = (await db.execute(claims_stmt)).scalars().first()

    # 3. Fetch protocol
    protocol_stmt = select(ProtocolVersion).where(ProtocolVersion.investigation_id == investigation_id).order_by(ProtocolVersion.created_at.desc())
    protocol = (await db.execute(protocol_stmt)).scalars().first()

    # 4. Fetch job and attempt
    job: ExperimentJob | None = None
    attempt: AttemptRecord | None = None
    if job_id:
        job = await db.get(ExperimentJob, job_id)
    if not job:
        job_stmt = select(ExperimentJob).where(ExperimentJob.investigation_id == investigation_id).order_by(ExperimentJob.created_at.desc())
        job = (await db.execute(job_stmt)).scalars().first()

    measurements: list[ProductionMeasurement] = []
    if job:
        attempt_stmt = select(AttemptRecord).where(AttemptRecord.job_id == job.id).order_by(AttemptRecord.attempt_number.desc())
        attempt = (await db.execute(attempt_stmt)).scalars().first()

        measurements_stmt = select(ProductionMeasurement).where(ProductionMeasurement.job_id == job.id)
        measurements = list((await db.execute(measurements_stmt)).scalars().all())

    # 5. Compute the three dimension scores
    extraction_score, extraction_breakdown = score_extraction_quality(claim, protocol)
    tech_score, tech_breakdown = score_technical_reproducibility(job, attempt, measurements)
    claim_score, verdict, claim_breakdown = score_scientific_claim_verification(claim, job, measurements)

    # 6. Construct evaluation record
    evaluation = ScientificEvaluation(
        id=str(uuid.uuid4()),
        investigation_id=investigation_id,
        job_id=job.id if job else None,
        claim_id=claim.id if claim else None,
        evaluation_version="1.0.0",
        status="completed",
        verdict=verdict,
        extraction_quality_score=extraction_score,
        extraction_quality_breakdown=extraction_breakdown,
        technical_reproducibility_score=tech_score,
        technical_reproducibility_breakdown=tech_breakdown,
        claim_verification_score=claim_score,
        claim_verification_breakdown=claim_breakdown,
        summary_notes=summary_notes or f"Tri-partite scientific evaluation: Extraction={extraction_score}, Technical={tech_score}, ClaimVerification={verdict}.",
        evaluated_at=datetime.now(timezone.utc),
    )

    db.add(evaluation)
    if commit:
        await db.commit()
        await db.refresh(evaluation)
    else:
        await db.flush()
    return evaluation
