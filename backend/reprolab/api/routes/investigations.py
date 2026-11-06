from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.db.session import get_db
from reprolab.models.artifact import ResearchArtifact, ResearchArtifactReference
from reprolab.models.evaluation import ScientificEvaluation
from reprolab.models.execution import ProductionMeasurement
from reprolab.models.paper import Artifact, Paper
from reprolab.models.research import Claim, EvidenceItem, EvidenceReview, Investigation, ProtocolVersion
from reprolab.schemas.research import (
    ApprovalRequest,
    ClaimCreate,
    ClaimRead,
    EvidenceCreate,
    EvidenceRead,
    EvidenceReviewCreate,
    EvidenceReviewRead,
    EvidenceVerifyRequest,
    InvestigationCreate,
    InvestigationRead,
    InvestigationSummaryRead,
    ProtocolCreate,
    ProtocolRead,
    RailMetrics,
    ResearchArtifactRead,
)
from reprolab.services.protocols import canonical_protocol, protocol_hash
from reprolab.services.protocol_integrity import validate_protocol_record

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])
protocol_router = APIRouter(prefix="/api/v1", tags=["protocols", "evidence"])


def _storage(request: Request):
    return request.app.state.storage


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _investigation_or_404(db: AsyncSession, investigation_id: str) -> Investigation:
    investigation = await db.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status_code=404, detail="Investigation not found.")
    return investigation


def _protocol_read(protocol: ProtocolVersion) -> ProtocolRead:
    return ProtocolRead(
        id=protocol.id,
        investigation_id=protocol.investigation_id,
        parent_protocol_id=protocol.parent_protocol_id,
        version_number=protocol.version_number,
        status=protocol.status,
        protocol_hash=protocol.protocol_hash,
        protocol=protocol.canonical_protocol_json,
        approved_by=protocol.approved_by,
        approved_at=protocol.approved_at,
        frozen_at=protocol.frozen_at,
        created_at=protocol.created_at,
    )


@router.post("", response_model=InvestigationRead, status_code=status.HTTP_201_CREATED)
async def create_investigation(
    payload: InvestigationCreate,
    db: AsyncSession = Depends(get_db),
) -> Investigation:
    if payload.paper_id is not None:
        paper = await db.get(Paper, payload.paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found.")

    investigation = Investigation(
        name=payload.name,
        paper_id=payload.paper_id,
        source_kind=payload.source_kind,
        status="protocol_pending",
        execution_status="not_started",
        claim_assessment="framework_test_only" if payload.source_kind == "synthetic_framework_test" else "not_assessed",
    )
    db.add(investigation)
    await db.commit()
    await db.refresh(investigation)
    return investigation


@router.get("", response_model=list[InvestigationRead])
async def list_investigations(db: AsyncSession = Depends(get_db)) -> list[Investigation]:
    result = await db.scalars(select(Investigation).order_by(Investigation.created_at.desc()))
    return list(result.all())


@router.get("/{investigation_id}", response_model=InvestigationRead)
async def get_investigation(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> Investigation:
    return await _investigation_or_404(db, investigation_id)


@router.get("/{investigation_id}/summary", response_model=InvestigationSummaryRead)
async def get_investigation_summary(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> InvestigationSummaryRead:
    investigation = await _investigation_or_404(db, investigation_id)

    # Fetch primary claim if available
    claims = list(await db.scalars(
        select(Claim)
        .where(Claim.investigation_id == investigation_id)
        .order_by(Claim.created_at.desc())
    ))
    primary_claim = claims[0] if claims else None

    # Fetch latest production measurement if available
    measurements = list(await db.scalars(
        select(ProductionMeasurement)
        .where(ProductionMeasurement.investigation_id == investigation_id)
        .order_by(ProductionMeasurement.recorded_at.desc())
    ))
    latest_measurement = measurements[0] if measurements else None

    # Fetch latest scientific evaluation if available
    evaluations = list(await db.scalars(
        select(ScientificEvaluation)
        .where(ScientificEvaluation.investigation_id == investigation_id)
        .order_by(ScientificEvaluation.evaluated_at.desc())
    ))
    latest_eval = evaluations[0] if evaluations else None

    # Determine reproduction verdict
    if latest_eval:
        verdict = latest_eval.verdict
    elif investigation.claim_assessment and investigation.claim_assessment != "not_assessed":
        verdict = investigation.claim_assessment
    else:
        verdict = "not_assessed"

    # Assemble Rail Metrics
    claimed_val = primary_claim.reported_value if primary_claim else None
    metric = primary_claim.metric_name if primary_claim else (
        latest_measurement.metric_name if latest_measurement else "accuracy"
    )
    measured_val = latest_measurement.value if latest_measurement else None
    lower_val = latest_measurement.interval_lower if latest_measurement else None
    upper_val = latest_measurement.interval_upper if latest_measurement else None
    sample_sz = latest_measurement.sample_size if latest_measurement else None

    rail_metrics = RailMetrics(
        claimed_mean=claimed_val,
        replicated_mean=measured_val,
        wilson_ci_lower=lower_val,
        wilson_ci_upper=upper_val,
        sample_size=sample_sz,
        metric_name=metric,
    )

    # Bilingual plain-language and technical summaries
    if measured_val is not None and claimed_val is not None:
        plain_en = (
            f"The published paper claimed {claimed_val * 100:.1f}% for {metric}. "
            f"In our independent execution across {sample_sz or 0} trials, the replicated result was "
            f"{measured_val * 100:.1f}% with an honest 95% Wilson confidence interval of "
            f"[{lower_val * 100:.1f}%, {upper_val * 100:.1f}%]. Verdict: {verdict.replace('_', ' ').title()}."
        )
        plain_hi = (
            f"प्रकाशित शोध पत्र में {metric} का दावा {claimed_val * 100:.1f}% था। "
            f"हमारे स्वतंत्र सैंडबॉक्स परीक्षण ({sample_sz or 0} परीक्षणों पर) में वास्तविक परिणाम "
            f"{measured_val * 100:.1f}% रहा (95% विल्सन विश्वास अंतराल: "
            f"[{lower_val * 100:.1f}%, {upper_val * 100:.1f}%])। परिणाम: {verdict}।"
        )
    elif claimed_val is not None:
        plain_en = (
            f"Investigation for '{investigation.name}'. Paper claims '{primary_claim.statement}' "
            f"with reported {metric} of {claimed_val * 100:.1f}%. Execution pending or in progress."
        )
        plain_hi = (
            f"जांच मामला: '{investigation.name}'। शोध पत्र का दावा: '{primary_claim.statement}', "
            f"रिपोर्ट किया गया मान: {claimed_val * 100:.1f}%। प्रायोगिक सत्यापन लंबित है।"
        )
    else:
        plain_en = f"Investigation '{investigation.name}'. Status: {investigation.status.replace('_', ' ')}."
        plain_hi = f"जांच मामला: '{investigation.name}'। वर्तमान स्थिति: {investigation.status}।"

    tech_en = (
        f"Investigation UUID: {investigation.id} | Source Kind: {investigation.source_kind} | "
        f"Status: {investigation.status} | Execution: {investigation.execution_status} | "
        f"Primary Metric: {metric} | Claimed: {claimed_val} | Replicated: {measured_val} | "
        f"Wilson 95% CI: [{lower_val}, {upper_val}] | Sample Size: {sample_sz} | Verdict: {verdict}"
    )
    tech_hi = (
        f"जांच आईडी: {investigation.id} | स्रोत प्रकार: {investigation.source_kind} | "
        f"स्थिति: {investigation.status} | परीक्षण: {investigation.execution_status} | "
        f"मुख्य पैमाना: {metric} | दावा: {claimed_val} | मापा गया: {measured_val} | "
        f"95% विल्सन अंतराल: [{lower_val}, {upper_val}] | नमूना आकार: {sample_sz} | अंतिम निष्कर्ष: {verdict}"
    )

    return InvestigationSummaryRead(
        investigation_id=investigation.id,
        name=investigation.name,
        source_kind=investigation.source_kind,
        status=investigation.status,
        execution_status=investigation.execution_status,
        claim_assessment=investigation.claim_assessment,
        reproduction_verdict=verdict,
        plain_english_summary=plain_en,
        plain_hindi_summary=plain_hi,
        technical_dossier_en=tech_en,
        technical_dossier_hi=tech_hi,
        rail_metrics=rail_metrics,
    )


@router.post("/{investigation_id}/claims", response_model=ClaimRead, status_code=status.HTTP_201_CREATED)
async def create_claim(
    investigation_id: str,
    payload: ClaimCreate,
    db: AsyncSession = Depends(get_db),
) -> Claim:
    investigation = await _investigation_or_404(db, investigation_id)
    if payload.source_kind != investigation.source_kind:
        raise HTTPException(status_code=409, detail="Claim source_kind does not match the investigation.")
    claim = Claim(
        investigation_id=investigation.id,
        statement=payload.statement,
        metric_name=payload.metric_name,
        reported_value=payload.reported_value,
        metric_direction=payload.metric_direction,
        source_kind=payload.source_kind,
        source_locator=payload.source_locator,
        published=payload.published,
    )
    db.add(claim)
    await db.commit()
    await db.refresh(claim)
    return claim


@router.get("/{investigation_id}/claims", response_model=list[ClaimRead])
async def list_claims(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[Claim]:
    await _investigation_or_404(db, investigation_id)
    result = await db.scalars(
        select(Claim).where(Claim.investigation_id == investigation_id).order_by(Claim.created_at.asc())
    )
    return list(result.all())


@router.post("/{investigation_id}/evidence", response_model=EvidenceRead, status_code=status.HTTP_201_CREATED)
async def create_evidence(
    investigation_id: str,
    payload: EvidenceCreate,
    db: AsyncSession = Depends(get_db),
) -> EvidenceItem:
    investigation = await _investigation_or_404(db, investigation_id)
    if payload.claim_id is not None:
        claim = await db.get(Claim, payload.claim_id)
        if claim is None or claim.investigation_id != investigation.id:
            raise HTTPException(status_code=409, detail="Evidence claim does not belong to the investigation.")

    artifact_hash: str | None = None
    if payload.artifact_id is not None:
        artifact = await db.get(Artifact, payload.artifact_id)
        if artifact is None:
            raise HTTPException(status_code=404, detail="Evidence artifact not found.")
        if investigation.paper_id is not None and artifact.paper_id != investigation.paper_id:
            raise HTTPException(status_code=409, detail="Evidence artifact is outside the investigation paper.")
        artifact_hash = artifact.sha256
        if payload.sha256 is not None and payload.sha256 != artifact.sha256:
            raise HTTPException(status_code=409, detail="Evidence hash does not match the artifact.")

    evidence = EvidenceItem(
        investigation_id=investigation.id,
        claim_id=payload.claim_id,
        artifact_id=payload.artifact_id,
        source_url=str(payload.source_url) if payload.source_url is not None else None,
        source_locator=payload.source_locator,
        quoted_text=payload.quoted_text,
        sha256=payload.sha256 or artifact_hash,
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)
    return evidence


@router.get("/{investigation_id}/evidence", response_model=list[EvidenceRead])
async def list_evidence(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[EvidenceItem]:
    await _investigation_or_404(db, investigation_id)
    result = await db.scalars(
        select(EvidenceItem).where(EvidenceItem.investigation_id == investigation_id).order_by(EvidenceItem.created_at.asc())
    )
    return list(result.all())


async def _evidence_or_404(db: AsyncSession, evidence_id: str) -> EvidenceItem:
    evidence = await db.get(EvidenceItem, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence item not found.")
    return evidence


@router.get("/{investigation_id}/evidence/{evidence_id}/reviews", response_model=list[EvidenceReviewRead])
async def list_evidence_reviews(
    investigation_id: str,
    evidence_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[EvidenceReview]:
    await _investigation_or_404(db, investigation_id)
    evidence = await _evidence_or_404(db, evidence_id)
    if evidence.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Evidence not found in this investigation.")
    result = await db.scalars(
        select(EvidenceReview)
        .where(EvidenceReview.evidence_item_id == evidence_id)
        .order_by(EvidenceReview.reviewed_at.asc())
    )
    return list(result.all())


@router.get("/{investigation_id}/protocols", response_model=list[ProtocolRead])
async def list_protocols(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ProtocolRead]:
    await _investigation_or_404(db, investigation_id)
    result = await db.scalars(
        select(ProtocolVersion)
        .where(ProtocolVersion.investigation_id == investigation_id)
        .order_by(ProtocolVersion.version_number.asc())
    )
    return [_protocol_read(protocol) for protocol in result.all()]


@router.get("/{investigation_id}/artifacts", response_model=list[ResearchArtifactRead])
async def list_research_artifacts(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ResearchArtifactReference]:
    await _investigation_or_404(db, investigation_id)
    result = await db.scalars(
        select(ResearchArtifactReference)
        .where(ResearchArtifactReference.investigation_id == investigation_id)
        .order_by(ResearchArtifactReference.created_at.asc())
    )
    references = list(result.all())
    legacy_result = await db.scalars(
        select(ResearchArtifact).where(ResearchArtifact.investigation_id == investigation_id)
    )
    return [*references, *legacy_result.all()]


@router.get("/{investigation_id}/artifacts/{artifact_id}", response_model=ResearchArtifactRead)
async def get_research_artifact(
    investigation_id: str,
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
) -> ResearchArtifactReference:
    await _investigation_or_404(db, investigation_id)
    artifact = await db.get(ResearchArtifactReference, artifact_id)
    if artifact is None:
        artifact = await db.get(ResearchArtifact, artifact_id)
    if artifact is None or artifact.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Research artifact not found.")
    return artifact


@router.get("/{investigation_id}/artifacts/{artifact_id}/download")
async def download_research_artifact(
    investigation_id: str,
    artifact_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    await _investigation_or_404(db, investigation_id)
    artifact = await db.get(ResearchArtifactReference, artifact_id)
    if artifact is None:
        artifact = await db.get(ResearchArtifact, artifact_id)
    if artifact is None or artifact.investigation_id != investigation_id:
        raise HTTPException(status_code=404, detail="Research artifact not found.")
    storage = _storage(request)
    try:
        path = storage.resolve_research(artifact.storage_key)
        storage.read_research_bytes(artifact.storage_key, expected_sha256=artifact.sha256)
    except Exception as exc:
        raise HTTPException(status_code=409, detail="Research artifact failed hash verification.") from exc
    return FileResponse(path, media_type=artifact.content_type, filename=artifact.storage_key.rsplit("/", 1)[-1])


@router.post("/{investigation_id}/protocols", response_model=ProtocolRead, status_code=status.HTTP_201_CREATED)
async def create_protocol(
    investigation_id: str,
    payload: ProtocolCreate,
    db: AsyncSession = Depends(get_db),
) -> ProtocolRead:
    investigation = await _investigation_or_404(db, investigation_id)
    protocol = payload.protocol
    if protocol.source_kind != investigation.source_kind:
        raise HTTPException(status_code=409, detail="Protocol source_kind does not match the investigation.")
    if protocol.paper_id != investigation.paper_id:
        raise HTTPException(status_code=409, detail="Protocol paper_id does not match the investigation.")

    claim = await db.get(Claim, protocol.claim_id)
    if claim is None or claim.investigation_id != investigation.id:
        raise HTTPException(status_code=409, detail="Protocol claim does not belong to the investigation.")
    if claim.statement != protocol.claim_text:
        raise HTTPException(status_code=409, detail="Protocol claim_text must match the stored claim.")
    if claim.metric_name != protocol.primary_metric.name:
        raise HTTPException(status_code=409, detail="Protocol metric must match the stored claim.")
    if claim.metric_direction != protocol.primary_metric.direction:
        raise HTTPException(status_code=409, detail="Protocol metric direction must match the stored claim.")
    if claim.reported_value != protocol.reported_result.value:
        raise HTTPException(status_code=409, detail="Protocol reported result must match the stored claim.")

    evidence_result = await db.scalars(select(EvidenceItem).where(EvidenceItem.id.in_(protocol.evidence_reference_ids)))
    evidence_items = list(evidence_result.all())
    if len(evidence_items) != len(set(protocol.evidence_reference_ids)):
        raise HTTPException(status_code=409, detail="One or more protocol evidence references do not exist.")
    if any(item.investigation_id != investigation.id for item in evidence_items):
        raise HTTPException(status_code=409, detail="Protocol evidence references must belong to the investigation.")
    if any(item.claim_id not in {None, claim.id} for item in evidence_items):
        raise HTTPException(status_code=409, detail="Protocol evidence references another claim.")

    existing_max = await db.scalar(
        select(func.max(ProtocolVersion.version_number)).where(
            ProtocolVersion.investigation_id == investigation.id
        )
    )
    next_version = int(existing_max or 0) + 1
    if next_version > 1 and payload.parent_protocol_id is None:
        raise HTTPException(status_code=409, detail="A subsequent protocol version requires parent_protocol_id.")
    if payload.parent_protocol_id is not None:
        parent = await db.get(ProtocolVersion, payload.parent_protocol_id)
        if parent is None or parent.investigation_id != investigation.id:
            raise HTTPException(status_code=409, detail="parent_protocol_id is outside the investigation.")

    protocol_json = canonical_protocol(protocol)
    protocol_record = ProtocolVersion(
        investigation_id=investigation.id,
        parent_protocol_id=payload.parent_protocol_id,
        version_number=next_version,
        status="draft",
        canonical_protocol_json=protocol_json,
        protocol_hash=protocol_hash(protocol_json),
    )
    investigation.status = "protocol_pending"
    investigation.updated_at = _now()
    db.add(protocol_record)
    await db.commit()
    await db.refresh(protocol_record)
    return _protocol_read(protocol_record)


@protocol_router.post("/evidence/{evidence_id}/verify", response_model=EvidenceRead)
async def verify_evidence(
    evidence_id: str,
    payload: EvidenceVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> EvidenceItem:
    evidence = await _evidence_or_404(db, evidence_id)
    review = EvidenceReview(
        evidence_item_id=evidence.id,
        review_method="manual_review",
        outcome="accepted_for_protocol",
        reviewer_label="manual compatibility review",
        notes=payload.notes,
    )
    db.add(review)
    evidence.verification_status = "manually_reviewed"
    evidence.verification_notes = payload.notes
    await db.commit()
    await db.refresh(evidence)
    return evidence


@protocol_router.post("/evidence/{evidence_id}/reviews", response_model=EvidenceReviewRead, status_code=status.HTTP_201_CREATED)
async def create_evidence_review(
    evidence_id: str,
    payload: EvidenceReviewCreate,
    db: AsyncSession = Depends(get_db),
) -> EvidenceReview:
    evidence = await _evidence_or_404(db, evidence_id)
    if payload.review_method != "manual_review":
        raise HTTPException(
            status_code=409,
            detail="Automated evidence verification is not available in Stage 1; use manual_review.",
        )
    review = EvidenceReview(
        evidence_item_id=evidence.id,
        review_method=payload.review_method,
        outcome=payload.outcome,
        reviewer_id=payload.reviewer_id,
        reviewer_label=payload.reviewer_label,
        notes=payload.notes,
        source_snapshot_hash=payload.source_snapshot_hash,
    )
    db.add(review)
    if payload.outcome == "accepted_for_protocol":
        evidence.verification_status = (
            "automatically_verified"
            if payload.review_method != "manual_review"
            else "manually_reviewed"
        )
    elif payload.outcome == "rejected":
        evidence.verification_status = "rejected"
    else:
        evidence.verification_status = "unresolved"
    evidence.verification_notes = payload.notes
    await db.commit()
    await db.refresh(review)
    return review


@protocol_router.get("/protocols/{protocol_id}", response_model=ProtocolRead)
async def get_protocol(protocol_id: str, db: AsyncSession = Depends(get_db)) -> ProtocolRead:
    protocol = await db.get(ProtocolVersion, protocol_id)
    if protocol is None:
        raise HTTPException(status_code=404, detail="Protocol not found.")
    return _protocol_read(protocol)


@protocol_router.post("/protocols/{protocol_id}/approve", response_model=ProtocolRead)
async def approve_protocol(
    protocol_id: str,
    payload: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
) -> ProtocolRead:
    protocol_record = await db.get(ProtocolVersion, protocol_id)
    if protocol_record is None:
        raise HTTPException(status_code=404, detail="Protocol not found.")
    if protocol_record.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft protocols can be approved.")

    await validate_protocol_record(db, protocol_record, require_accepted_evidence=True)

    now = _now()
    protocol_record.status = "approved"
    protocol_record.approved_by = payload.approved_by
    protocol_record.approved_at = now
    investigation = await db.get(Investigation, protocol_record.investigation_id)
    if investigation is not None:
        investigation.status = "approved"
        investigation.updated_at = now
    await db.commit()
    await db.refresh(protocol_record)
    return _protocol_read(protocol_record)


@protocol_router.post("/protocols/{protocol_id}/freeze", response_model=ProtocolRead)
async def freeze_protocol(protocol_id: str, db: AsyncSession = Depends(get_db)) -> ProtocolRead:
    protocol_record = await db.get(ProtocolVersion, protocol_id)
    if protocol_record is None:
        raise HTTPException(status_code=404, detail="Protocol not found.")
    if protocol_record.status != "approved":
        raise HTTPException(status_code=409, detail="Only approved protocols can be frozen.")

    await validate_protocol_record(db, protocol_record, require_accepted_evidence=True)

    now = _now()
    protocol_record.status = "frozen"
    protocol_record.frozen_at = now
    investigation = await db.get(Investigation, protocol_record.investigation_id)
    if investigation is not None:
        investigation.status = "approved"
        investigation.updated_at = now
    await db.commit()
    await db.refresh(protocol_record)
    return _protocol_read(protocol_record)
