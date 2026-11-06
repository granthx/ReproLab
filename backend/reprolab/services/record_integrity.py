import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.models.records import (
    Finding,
    FindingEvidenceLink,
    FindingRelation,
    FindingVersion,
    RecordAttribution,
    RecordReview,
    ScientistConstitutionSnapshot,
)
from reprolab.models.research import Claim, EvidenceItem, EvidenceReview, Investigation, ProtocolVersion
from reprolab.schemas.records import (
    AttributionInput,
    ConstitutionSnapshotRead,
    FindingCreate,
    FindingDefinition,
    FindingEvidenceLinkRead,
    FindingRelationCreate,
    FindingRelationRead,
    FindingRead,
    FindingSummary,
    FindingVersionCreate,
    FindingVersionRead,
    RecordAttributionRead,
    RecordReviewCreate,
    RecordReviewRead,
)
from reprolab.scientists.registry import get_constitutions


def canonical_json_hash(content: dict[str, Any]) -> str:
    """Hash JSON using the same canonical serialization as Stage 1 protocols."""

    serialized = json.dumps(
        content,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def canonical_finding_content(finding: FindingDefinition) -> dict[str, Any]:
    return finding.model_dump(mode="json")


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail=message)


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


async def _constitution_snapshot(
    db: AsyncSession,
    role_id: str,
) -> ScientistConstitutionSnapshot:
    constitution = get_constitutions().get(role_id)
    if constitution is None:
        raise _conflict("associated_role_id is not a registered scientist role")
    content = constitution.model_dump(mode="json")
    content_hash = canonical_json_hash(content)
    snapshot = await db.scalar(
        select(ScientistConstitutionSnapshot).where(
            ScientistConstitutionSnapshot.role_id == role_id,
            ScientistConstitutionSnapshot.constitution_version == constitution.version,
            ScientistConstitutionSnapshot.constitution_hash == content_hash,
        )
    )
    if snapshot is None:
        snapshot = ScientistConstitutionSnapshot(
            id=str(uuid4()),
            role_id=role_id,
            constitution_version=constitution.version,
            constitution_json=content,
            constitution_hash=content_hash,
        )
        db.add(snapshot)
        await db.flush()
    return snapshot


async def create_attribution(
    db: AsyncSession,
    investigation_id: str,
    payload: AttributionInput,
) -> RecordAttribution:
    snapshot = None
    if payload.associated_role_id is not None:
        snapshot = await _constitution_snapshot(db, payload.associated_role_id)
    attribution = RecordAttribution(
        id=str(uuid4()),
        investigation_id=investigation_id,
        recorder_id=payload.recorder_id,
        recorder_label=payload.recorder_label,
        entry_method=payload.entry_method,
        associated_role_id=payload.associated_role_id,
        role_association_note=payload.role_association_note,
        identity_assurance="caller_asserted",
        constitution_snapshot_id=snapshot.id if snapshot is not None else None,
    )
    db.add(attribution)
    await db.flush()
    return attribution


async def _validate_finding_references(
    db: AsyncSession,
    investigation_id: str,
    finding: FindingDefinition,
) -> list[tuple[Any, EvidenceReview | None]]:
    if finding.claim_id is not None:
        claim = await db.get(Claim, finding.claim_id)
        if claim is None:
            raise _not_found("Finding claim not found.")
        if claim.investigation_id != investigation_id:
            raise _conflict("Finding claim is outside the investigation.")

    if finding.protocol_version_id is not None:
        protocol = await db.get(ProtocolVersion, finding.protocol_version_id)
        if protocol is None:
            raise _not_found("Finding protocol version not found.")
        if protocol.investigation_id != investigation_id:
            raise _conflict("Finding protocol version is outside the investigation.")

    evidence_ids = [link.evidence_item_id for link in finding.evidence_links]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise _conflict("A finding cannot cite the same evidence item more than once.")
    if not evidence_ids:
        return []

    evidence_result = await db.scalars(
        select(EvidenceItem).where(EvidenceItem.id.in_(evidence_ids))
    )
    evidence_by_id = {item.id: item for item in evidence_result.all()}
    if len(evidence_by_id) != len(evidence_ids):
        raise _not_found("One or more finding evidence items were not found.")
    if any(item.investigation_id != investigation_id for item in evidence_by_id.values()):
        raise _conflict("Finding evidence is outside the investigation.")

    review_by_id: dict[str, EvidenceReview] = {}
    review_ids = [link.evidence_review_id for link in finding.evidence_links if link.evidence_review_id]
    if review_ids:
        reviews = await db.scalars(
            select(EvidenceReview).where(EvidenceReview.id.in_(review_ids))
        )
        review_by_id = {review.id: review for review in reviews.all()}
        if len(review_by_id) != len(set(review_ids)):
            raise _not_found("One or more pinned evidence reviews were not found.")
        evidence_item_ids = {item.id for item in evidence_by_id.values()}
        if any(review.evidence_item_id not in evidence_item_ids for review in review_by_id.values()):
            raise _conflict("A pinned evidence review does not belong to the cited evidence item.")

    validated: list[tuple[Any, EvidenceReview | None]] = []
    for link in finding.evidence_links:
        item = evidence_by_id[link.evidence_item_id]
        review = review_by_id.get(link.evidence_review_id) if link.evidence_review_id else None
        if review is not None and review.evidence_item_id != item.id:
            raise _conflict("A pinned evidence review does not belong to its cited evidence item.")
        if finding.claim_id is not None and item.claim_id not in {None, finding.claim_id}:
            raise _conflict("Finding evidence references another claim.")
        validated.append((item, review))
    _validate_numeric_assertions(finding, validated)
    return validated


def _source_snapshot(evidence: EvidenceItem, review: EvidenceReview | None) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "evidence_item_id": evidence.id,
        "source_url": evidence.source_url,
        "source_locator": evidence.source_locator,
        "quoted_text": evidence.quoted_text,
        "sha256": evidence.sha256,
        "verification_status": evidence.verification_status,
        "verification_notes": evidence.verification_notes,
        "created_at": evidence.created_at.isoformat() if evidence.created_at else None,
    }
    if review is not None:
        snapshot["evidence_review"] = {
            "id": review.id,
            "review_method": review.review_method,
            "outcome": review.outcome,
            "reviewer_id": review.reviewer_id,
            "reviewer_label": review.reviewer_label,
            "notes": review.notes,
            "source_snapshot_hash": review.source_snapshot_hash,
            "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        }
    return snapshot


def _validate_numeric_assertions(
    finding: FindingDefinition,
    validated_evidence: list[tuple[Any, EvidenceReview | None]],
) -> None:
    evidence_by_id = {item.id: item for item, _review in validated_evidence}
    links_by_key = {
        link.key: evidence_by_id[link.evidence_item_id]
        for link in finding.evidence_links
    }
    for assertion in finding.assertions:
        for number in assertion.numbers:
            evidence = links_by_key.get(number.citation_key)
            if evidence is None:
                raise _conflict("Numeric assertion cites an unknown evidence key.")
            quote = evidence.quoted_text
            if not quote:
                raise _conflict("Numeric assertions require quoted evidence text.")
            if (
                number.source_end > len(quote)
                or quote[number.source_start:number.source_end] != number.source_lexeme
            ):
                raise _conflict("Numeric assertion source span does not match the cited quotation.")
            if (
                number.normalization == "percent_to_fraction"
                and not number.source_lexeme.strip().endswith("%")
            ):
                raise _conflict("percent_to_fraction requires a percent source lexeme.")


def _validate_stored_version(version: FindingVersion) -> FindingDefinition:
    if canonical_json_hash(version.canonical_content_json) != version.content_hash:
        raise _conflict("Stored finding version hash does not match its canonical contents.")
    try:
        definition = FindingDefinition.model_validate(version.canonical_content_json)
    except Exception as exc:
        raise _conflict("Stored finding version contents are invalid.") from exc
    if canonical_finding_content(definition) != version.canonical_content_json:
        raise _conflict("Stored finding version is not in canonical form.")
    return definition


async def _add_evidence_links(
    db: AsyncSession,
    investigation_id: str,
    version: FindingVersion,
    finding: FindingDefinition,
    validated_evidence: list[tuple[Any, EvidenceReview | None]],
) -> None:
    by_id = {item.id: (item, review) for item, review in validated_evidence}
    for link in finding.evidence_links:
        evidence, review = by_id[link.evidence_item_id]
        snapshot = _source_snapshot(evidence, review)
        db.add(
            FindingEvidenceLink(
                id=str(uuid4()),
                finding_version_id=version.id,
                evidence_item_id=evidence.id,
                investigation_id=investigation_id,
                citation_key=link.key,
                evidence_review_id=review.id if review is not None else None,
                relationship=link.relationship,
                rationale=link.rationale,
                source_snapshot_json=snapshot,
                snapshot_hash=canonical_json_hash(snapshot),
            )
        )


async def create_finding(
    db: AsyncSession,
    investigation_id: str,
    payload: FindingCreate,
) -> Finding:
    investigation = await db.get(Investigation, investigation_id)
    if investigation is None:
        raise _not_found("Investigation not found.")
    validated_evidence = await _validate_finding_references(db, investigation_id, payload.finding)
    attribution = await create_attribution(db, investigation_id, payload.attribution)
    finding = Finding(
        id=str(uuid4()),
        investigation_id=investigation_id,
        created_by_attribution_id=attribution.id,
    )
    db.add(finding)
    await db.flush()
    content = canonical_finding_content(payload.finding)
    version = FindingVersion(
        id=str(uuid4()),
        finding_id=finding.id,
        investigation_id=investigation_id,
        parent_version_id=None,
        version_number=1,
        record_kind=payload.finding.record_kind,
        claim_id=payload.finding.claim_id,
        protocol_version_id=payload.finding.protocol_version_id,
        canonical_content_json=content,
        content_hash=canonical_json_hash(content),
        schema_version="finding.v1",
        created_by_attribution_id=attribution.id,
    )
    db.add(version)
    await db.flush()
    await _add_evidence_links(db, investigation_id, version, payload.finding, validated_evidence)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Finding could not be persisted without violating investigation isolation.") from exc
    await db.refresh(finding)
    return finding


async def create_finding_version(
    db: AsyncSession,
    investigation_id: str,
    finding_id: str,
    payload: FindingVersionCreate,
) -> FindingVersion:
    finding = await db.scalar(
        select(Finding)
        .where(Finding.id == finding_id, Finding.investigation_id == investigation_id)
        .with_for_update()
    )
    if finding is None:
        raise _not_found("Finding not found in this investigation.")
    parent = await db.get(FindingVersion, payload.parent_version_id)
    if parent is None:
        raise _not_found("Parent finding version not found.")
    if parent.finding_id != finding_id or parent.investigation_id != investigation_id:
        raise _conflict("Parent finding version is outside the investigation or finding.")
    validated_evidence = await _validate_finding_references(db, investigation_id, payload.finding)
    current_max = await db.scalar(
        select(func.max(FindingVersion.version_number)).where(FindingVersion.finding_id == finding_id)
    )
    content = canonical_finding_content(payload.finding)
    attribution = await create_attribution(db, investigation_id, payload.attribution)
    version = FindingVersion(
        id=str(uuid4()),
        finding_id=finding_id,
        investigation_id=investigation_id,
        parent_version_id=parent.id,
        version_number=int(current_max or 0) + 1,
        record_kind=payload.finding.record_kind,
        claim_id=payload.finding.claim_id,
        protocol_version_id=payload.finding.protocol_version_id,
        canonical_content_json=content,
        content_hash=canonical_json_hash(content),
        schema_version="finding.v1",
        created_by_attribution_id=attribution.id,
    )
    db.add(version)
    await db.flush()
    await _add_evidence_links(db, investigation_id, version, payload.finding, validated_evidence)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Finding version could not be persisted; retry from the latest version.") from exc
    await db.refresh(version)
    return version


async def create_relation(
    db: AsyncSession,
    investigation_id: str,
    payload: FindingRelationCreate,
) -> FindingRelation:
    if payload.from_finding_version_id == payload.to_finding_version_id:
        raise _conflict("Finding relations cannot point to the same version.")
    versions = await db.scalars(
        select(FindingVersion).where(
            FindingVersion.id.in_([
                payload.from_finding_version_id,
                payload.to_finding_version_id,
            ])
        )
    )
    by_id = {version.id: version for version in versions.all()}
    if len(by_id) != 2:
        raise _not_found("One or more finding relation endpoints were not found.")
    if any(version.investigation_id != investigation_id for version in by_id.values()):
        raise _conflict("Finding relation endpoints must belong to this investigation.")
    attribution = await create_attribution(db, investigation_id, payload.attribution)
    relation = FindingRelation(
        id=str(uuid4()),
        investigation_id=investigation_id,
        from_finding_version_id=payload.from_finding_version_id,
        to_finding_version_id=payload.to_finding_version_id,
        relation_kind=payload.relation_kind,
        rationale=payload.rationale,
        created_by_attribution_id=attribution.id,
    )
    db.add(relation)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Finding relation could not be persisted.") from exc
    await db.refresh(relation)
    return relation


async def create_review(
    db: AsyncSession,
    investigation_id: str,
    finding_version_id: str,
    payload: RecordReviewCreate,
    *,
    commit: bool = True,
) -> RecordReview:
    # Share the version lock with report publication so eligibility cannot race
    # a newly committed exact-hash review.
    version = await db.scalar(
        select(FindingVersion).where(FindingVersion.id == finding_version_id).with_for_update()
    )
    if version is None or version.investigation_id != investigation_id:
        raise _not_found("Finding version not found in this investigation.")
    definition = _validate_stored_version(version)
    if version.content_hash != payload.expected_content_hash:
        raise _conflict("Review target hash does not match the stored finding version.")
    if payload.outcome == "accepted_for_inclusion":
        if not payload.citations_checked:
            raise _conflict("Accepted finding reviews require citations_checked=true.")
        if not payload.limitations_checked:
            raise _conflict("Accepted finding reviews require limitations_checked=true.")
        if not payload.execution_wording_checked:
            raise _conflict("Accepted finding reviews require execution_wording_checked=true.")
        if any(assertion.numbers for assertion in definition.assertions) and payload.numeric_transcription_checked is not True:
            raise _conflict(
                "Accepted finding reviews with numeric assertions require numeric_transcription_checked=true."
            )
    attribution = await create_attribution(db, investigation_id, payload.attribution)
    review = RecordReview(
        id=str(uuid4()),
        investigation_id=investigation_id,
        finding_version_id=finding_version_id,
        target_content_hash=payload.expected_content_hash,
        reviewer_attribution_id=attribution.id,
        review_method=payload.review_method,
        outcome=payload.outcome,
        notes=payload.notes,
        citations_checked=payload.citations_checked,
        numeric_transcription_checked=payload.numeric_transcription_checked,
        limitations_checked=payload.limitations_checked,
        execution_wording_checked=payload.execution_wording_checked,
        dependency_disclosures=payload.dependency_disclosures,
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(review)
    try:
        await db.flush()
        if commit:
            await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Finding review could not be persisted.") from exc
    if commit:
        await db.refresh(review)
    return review


async def _attribution_read(db: AsyncSession, attribution: RecordAttribution) -> RecordAttributionRead:
    snapshot = None
    if attribution.constitution_snapshot_id is not None:
        snapshot_record = await db.get(ScientistConstitutionSnapshot, attribution.constitution_snapshot_id)
        if snapshot_record is not None:
            snapshot = ConstitutionSnapshotRead.model_validate(snapshot_record, from_attributes=True)
    return RecordAttributionRead(
        id=attribution.id,
        investigation_id=attribution.investigation_id,
        recorder_id=attribution.recorder_id,
        recorder_label=attribution.recorder_label,
        entry_method=attribution.entry_method,
        associated_role_id=attribution.associated_role_id,
        role_association_note=attribution.role_association_note,
        identity_assurance=attribution.identity_assurance,
        constitution_snapshot=snapshot,
        created_at=attribution.created_at,
    )


async def finding_version_read(
    db: AsyncSession,
    version: FindingVersion,
) -> FindingVersionRead:
    attribution = await db.get(RecordAttribution, version.created_by_attribution_id)
    if attribution is None:
        raise _conflict("Finding attribution is missing.")
    definition = _validate_stored_version(version)
    links = await db.scalars(
        select(FindingEvidenceLink)
        .where(FindingEvidenceLink.finding_version_id == version.id)
        .order_by(FindingEvidenceLink.citation_key.asc())
    )
    link_reads = [FindingEvidenceLinkRead.model_validate(link, from_attributes=True) for link in links.all()]
    return FindingVersionRead(
        id=version.id,
        finding_id=version.finding_id,
        investigation_id=version.investigation_id,
        parent_version_id=version.parent_version_id,
        version_number=version.version_number,
        record_kind=version.record_kind,
        claim_id=version.claim_id,
        protocol_version_id=version.protocol_version_id,
        schema_version=version.schema_version,
        canonical_content_json=version.canonical_content_json,
        content_hash=version.content_hash,
        finding=definition,
        attribution=await _attribution_read(db, attribution),
        evidence_links=link_reads,
        created_at=version.created_at,
    )


async def finding_read(db: AsyncSession, finding: Finding) -> FindingRead:
    versions = await db.scalars(
        select(FindingVersion)
        .where(
            FindingVersion.finding_id == finding.id,
            FindingVersion.investigation_id == finding.investigation_id,
        )
        .order_by(FindingVersion.version_number.asc())
    )
    return FindingRead(
        id=finding.id,
        investigation_id=finding.investigation_id,
        created_at=finding.created_at,
        versions=[await finding_version_read(db, version) for version in versions.all()],
    )


async def finding_summary(db: AsyncSession, finding: Finding) -> FindingSummary:
    latest = await db.scalar(
        select(FindingVersion)
        .where(
            FindingVersion.finding_id == finding.id,
            FindingVersion.investigation_id == finding.investigation_id,
        )
        .order_by(FindingVersion.version_number.desc())
    )
    if latest is None:
        raise _conflict("Finding has no version.")
    content = FindingDefinition.model_validate(latest.canonical_content_json)
    return FindingSummary(
        id=finding.id,
        investigation_id=finding.investigation_id,
        latest_version_id=latest.id,
        latest_version_number=latest.version_number,
        record_kind=latest.record_kind,
        title=content.title,
        content_hash=latest.content_hash,
        created_at=finding.created_at,
    )


async def review_read(db: AsyncSession, review: RecordReview) -> RecordReviewRead:
    attribution = await db.get(RecordAttribution, review.reviewer_attribution_id)
    if attribution is None:
        raise _conflict("Finding review attribution is missing.")
    return RecordReviewRead(
        id=review.id,
        investigation_id=review.investigation_id,
        finding_version_id=review.finding_version_id,
        target_content_hash=review.target_content_hash,
        reviewer_attribution=await _attribution_read(db, attribution),
        review_method=review.review_method,
        outcome=review.outcome,
        notes=review.notes,
        citations_checked=review.citations_checked,
        numeric_transcription_checked=review.numeric_transcription_checked,
        limitations_checked=review.limitations_checked,
        execution_wording_checked=review.execution_wording_checked,
        dependency_disclosures=review.dependency_disclosures,
        reviewed_at=review.reviewed_at,
    )


async def relation_read(db: AsyncSession, relation: FindingRelation) -> FindingRelationRead:
    attribution = await db.get(RecordAttribution, relation.created_by_attribution_id)
    if attribution is None:
        raise _conflict("Finding relation attribution is missing.")
    return FindingRelationRead(
        id=relation.id,
        investigation_id=relation.investigation_id,
        from_finding_version_id=relation.from_finding_version_id,
        to_finding_version_id=relation.to_finding_version_id,
        relation_kind=relation.relation_kind,
        rationale=relation.rationale,
        attribution=await _attribution_read(db, attribution),
        created_at=relation.created_at,
    )
