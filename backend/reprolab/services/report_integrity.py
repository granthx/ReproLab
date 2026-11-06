import hashlib
import re
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.models.records import (
    FindingEvidenceLink,
    FindingVersion,
    RecordAttribution,
    RecordReview,
    ScientistConstitutionSnapshot,
)
from reprolab.models.reports import (
    Report,
    ReportEvent,
    ReportExport,
    ReportFindingLink,
    ReportVersion,
)
from reprolab.models.research import Claim, EvidenceItem, EvidenceReview, Investigation, ProtocolVersion
from reprolab.schemas.records import FindingDefinition
from reprolab.schemas.reports import (
    ReportCreate,
    ReportEventCreate,
    ReportFindingLinkInput,
    ReportSourceContext,
    ReportVersionCreate,
    ReportVersionDefinition,
)
from reprolab.services.record_integrity import (
    _attribution_read,
    _validate_stored_version,
    canonical_json_hash,
    create_attribution,
)


MAX_EXPORT_BYTES = 2 * 1024 * 1024


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail=message)


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def canonical_report_content(
    *,
    report_kind: str,
    title: str,
    scope_claim_ids: Iterable[str],
    limitations: Iterable[str],
    unresolved_questions: Iterable[str],
    finding_links: Iterable[dict[str, Any] | ReportFindingLinkInput],
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the immutable report manifest that is hashed and persisted.

    The canonical form deliberately contains references and hashes rather than a
    copy of mutable finding rows. Rendering resolves those references and checks
    the pinned hashes before producing an export.
    """

    normalized_links: list[dict[str, Any]] = []
    for link in finding_links:
        if isinstance(link, ReportFindingLinkInput):
            item = link.model_dump(mode="json")
        elif isinstance(link, ReportFindingLink):
            item = {
                "finding_version_id": link.finding_version_id,
                "finding_content_hash": link.finding_content_hash,
                "section": link.section,
                "position": link.position,
                "disposition": link.disposition,
                "exclusion_reason": link.exclusion_reason,
            }
        else:
            item = {
                "finding_version_id": link["finding_version_id"],
                "finding_content_hash": link["finding_content_hash"],
                "section": link["section"],
                "position": link["position"],
                "disposition": link["disposition"],
                "exclusion_reason": link.get("exclusion_reason"),
            }
        normalized_links.append(item)
    normalized_links.sort(
        key=lambda item: (
            item["section"],
            item["position"],
            item["finding_version_id"],
        )
    )
    return {
        "report_kind": report_kind,
        "title": title,
        "scope_claim_ids": sorted(scope_claim_ids),
        "finding_links": normalized_links,
        "limitations": list(limitations),
        "unresolved_questions": list(unresolved_questions),
        "source_context": deepcopy(source_context or {}),
    }


def report_hash(content: dict[str, Any]) -> str:
    """Hash a report manifest with the project's canonical json.dumps rules."""

    return canonical_json_hash(content)


async def _investigation_or_404(db: AsyncSession, investigation_id: str) -> Investigation:
    investigation = await db.get(Investigation, investigation_id)
    if investigation is None:
        raise _not_found("Investigation not found.")
    return investigation


async def _validate_scope_claims(
    db: AsyncSession,
    investigation_id: str,
    claim_ids: list[str],
) -> list[str]:
    if len(claim_ids) != len(set(claim_ids)):
        raise _conflict("Report scope claim IDs must be unique.")
    if not claim_ids:
        return []
    claims = await db.scalars(select(Claim).where(Claim.id.in_(claim_ids)))
    by_id = {claim.id: claim for claim in claims.all()}
    if len(by_id) != len(claim_ids):
        raise _not_found("One or more report scope claims were not found.")
    if any(claim.investigation_id != investigation_id for claim in by_id.values()):
        raise _conflict("Report scope claims must belong to this investigation.")
    return sorted(claim_ids)


async def _validate_finding_version_evidence(
    db: AsyncSession,
    investigation_id: str,
    version: FindingVersion,
) -> FindingDefinition:
    """Recheck the source snapshots and numeric spans of a stored finding."""

    definition = _validate_stored_version(version)
    if (
        version.investigation_id != investigation_id
        or version.record_kind != definition.record_kind
        or version.claim_id != definition.claim_id
        or version.protocol_version_id != definition.protocol_version_id
    ):
        raise _conflict("Stored finding metadata does not match its canonical contents.")
    for model, identifier in ((Claim, definition.claim_id), (ProtocolVersion, definition.protocol_version_id)):
        if identifier is not None:
            reference = await db.get(model, identifier)
            if reference is None or reference.investigation_id != investigation_id:
                raise _conflict("Stored finding claim or protocol is outside the investigation.")
    links_result = await db.scalars(
        select(FindingEvidenceLink).where(
            FindingEvidenceLink.finding_version_id == version.id,
            FindingEvidenceLink.investigation_id == investigation_id,
        )
    )
    links = list(links_result.all())
    by_key = {link.citation_key: link for link in links}
    if len(by_key) != len(links):
        raise _conflict("Stored finding evidence citation keys are not unique.")

    for link in links:
        if not isinstance(link.source_snapshot_json, dict) or canonical_json_hash(link.source_snapshot_json) != link.snapshot_hash:
            raise _conflict("Stored finding evidence snapshot hash does not match its contents.")
        evidence = await db.get(EvidenceItem, link.evidence_item_id)
        if evidence is None or evidence.investigation_id != investigation_id:
            raise _conflict("Stored finding evidence is outside the investigation.")
        if link.source_snapshot_json.get("evidence_item_id") != link.evidence_item_id:
            raise _conflict("Stored finding evidence snapshot identity does not match its link.")
        pinned_review = link.source_snapshot_json.get("evidence_review")
        if pinned_review is not None and not isinstance(pinned_review, dict):
            raise _conflict("Stored finding evidence review snapshot is invalid.")
        if (pinned_review or {}).get("id") != link.evidence_review_id:
            raise _conflict("Stored finding evidence review does not match its source snapshot.")
        if link.evidence_review_id is not None:
            review = await db.get(EvidenceReview, link.evidence_review_id)
            if review is None or review.evidence_item_id != link.evidence_item_id:
                raise _conflict("Stored finding evidence review belongs to different evidence.")

    for evidence_link in definition.evidence_links:
        stored_link = by_key.get(evidence_link.key)
        if stored_link is None or (
            stored_link.evidence_item_id != evidence_link.evidence_item_id
            or stored_link.evidence_review_id != evidence_link.evidence_review_id
            or stored_link.relationship != evidence_link.relationship
            or stored_link.rationale != evidence_link.rationale
        ):
            raise _conflict("Stored finding evidence links do not match the finding contents.")
    if set(by_key) != {link.key for link in definition.evidence_links}:
        raise _conflict("Stored finding evidence links do not match the finding contents.")

    for assertion in definition.assertions:
        for number in assertion.numbers:
            if number.citation_key not in assertion.citation_keys:
                raise _conflict("Numeric citations must also be cited by their containing assertion.")
            stored_link = by_key.get(number.citation_key)
            if stored_link is None:
                raise _conflict("A report includes a finding with an unresolved numeric citation.")
            quoted_text = stored_link.source_snapshot_json.get("quoted_text")
            if not isinstance(quoted_text, str):
                raise _conflict("A report includes a numeric finding without quoted source text.")
            if (
                number.source_end > len(quoted_text)
                or quoted_text[number.source_start:number.source_end] != number.source_lexeme
            ):
                raise _conflict("A report includes a numeric finding whose source span no longer matches.")
            if (
                number.normalization == "percent_to_fraction"
                and not number.source_lexeme.strip().endswith("%")
            ):
                raise _conflict("percent_to_fraction requires a percent source lexeme.")
            validate_numeric_value(number.value, number.source_lexeme, number.normalization)
    return definition


def validate_numeric_value(value: str, source_lexeme: str, normalization: str) -> None:
    """Compare finite decimal values exactly, without float/context rounding."""
    source = source_lexeme.strip()
    if normalization == "percent_to_fraction":
        if not source.endswith("%"):
            raise _conflict("percent_to_fraction requires a percent source lexeme.")
        source = source[:-1].strip()
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", source, flags=re.ASCII):
        raise _conflict("Numeric source lexeme is not an unambiguous decimal number.")
    try:
        reported, expected = Decimal(value), Decimal(source)
        if not reported.is_finite() or not expected.is_finite():
            raise ValueError("Nonfinite numeric value")
        parts = expected.as_tuple()
        if normalization == "percent_to_fraction":
            expected = Decimal((parts.sign, parts.digits, parts.exponent - 2))
        if reported != expected:
            raise _conflict("Numeric value does not match its declared source normalization.")
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise _conflict("Numeric source lexeme or value cannot be represented exactly.") from exc


async def _validate_selected_findings(
    db: AsyncSession,
    investigation_id: str,
    links: list[ReportFindingLinkInput],
) -> dict[str, FindingVersion]:
    ids = [link.finding_version_id for link in links]
    if len(ids) != len(set(ids)):
        raise _conflict("A report cannot select the same finding version twice.")
    if not ids:
        return {}
    result = await db.scalars(select(FindingVersion).where(FindingVersion.id.in_(ids)))
    versions = {version.id: version for version in result.all()}
    if len(versions) != len(ids):
        raise _not_found("One or more selected finding versions were not found.")
    if any(version.investigation_id != investigation_id for version in versions.values()):
        raise _conflict("Selected finding versions must belong to this investigation.")
    for link in links:
        version = versions[link.finding_version_id]
        if version.content_hash != link.finding_content_hash:
            raise _conflict("A selected finding version hash does not match the stored version.")
        await _validate_finding_version_evidence(db, investigation_id, version)
    return versions


async def _validate_definition(
    db: AsyncSession,
    investigation_id: str,
    definition: ReportVersionDefinition,
) -> tuple[list[str], dict[str, FindingVersion]]:
    investigation = await _investigation_or_404(db, investigation_id)
    if investigation.execution_status != "not_started" or investigation.claim_assessment not in {"not_assessed", "framework_test_only"}:
        raise _conflict("Analysis-record reports cannot assert experimental execution or assessment.")
    claim_ids = await _validate_scope_claims(db, investigation_id, definition.scope_claim_ids)
    versions = await _validate_selected_findings(
        db,
        investigation_id,
        definition.finding_links,
    )
    return claim_ids, versions


def _version_definition(version: ReportVersion, links: list[ReportFindingLink]) -> dict[str, Any]:
    if not isinstance(version.canonical_content_json, dict):
        raise _conflict("Stored report version contents are invalid.")
    return canonical_report_content(
        report_kind=version.report_kind,
        title=version.title,
        scope_claim_ids=version.scope_claim_ids,
        limitations=version.limitations,
        unresolved_questions=version.unresolved_questions,
        finding_links=links,
        source_context=version.canonical_content_json.get("source_context"),
    )


async def validate_report_version(
    db: AsyncSession,
    version: ReportVersion,
) -> tuple[dict[str, Any], list[ReportFindingLink]]:
    links_result = await db.scalars(
        select(ReportFindingLink)
        .where(
            ReportFindingLink.report_version_id == version.id,
            ReportFindingLink.investigation_id == version.investigation_id,
        )
        .order_by(ReportFindingLink.section.asc(), ReportFindingLink.position.asc())
    )
    links = list(links_result.all())
    canonical = _version_definition(version, links)
    if canonical_json_hash(version.canonical_content_json) != version.content_hash:
        raise _conflict("Stored report version hash does not match its canonical contents.")
    if version.canonical_content_json != canonical:
        raise _conflict("Stored report version is not in canonical form.")
    try:
        ReportVersionDefinition.model_validate({key: value for key, value in canonical.items() if key != "source_context"})
        context = ReportSourceContext.model_validate(canonical["source_context"])
    except ValueError as exc:
        raise _conflict("Stored report version contents are invalid.") from exc
    snapshot_investigation = context.investigation
    if snapshot_investigation.id != version.investigation_id:
        raise _conflict("Report investigation snapshot identity does not match its version.")
    assessment = "framework_test_only" if snapshot_investigation.source_kind == "synthetic_framework_test" else "not_assessed"
    if snapshot_investigation.claim_assessment != assessment:
        raise _conflict("Report investigation snapshot has an unsupported scientific assessment.")
    claim_ids = [claim.id for claim in context.claims]
    if len(set(claim_ids)) != len(claim_ids) or sorted(claim_ids) != sorted(version.scope_claim_ids):
        raise _conflict("Report claim snapshots do not match its scope claim identities.")
    snapshots = canonical["source_context"]["findings"]
    snapshots_by_id = {item["finding_version_id"]: item for item in snapshots}
    if len(snapshots_by_id) != len(snapshots) or set(snapshots_by_id) != {link.finding_version_id for link in links}:
        raise _conflict("Stored report source context does not match its selected findings.")
    for link in links:
        finding_version = await db.get(FindingVersion, link.finding_version_id)
        if (
            finding_version is None
            or finding_version.investigation_id != version.investigation_id
        ):
            raise _conflict("Stored report finding link points outside the investigation.")
        if finding_version.content_hash != link.finding_content_hash:
            raise _conflict("Stored report finding hash does not match its finding version.")
        await _validate_finding_version_evidence(
            db,
            version.investigation_id,
            finding_version,
        )
        snapshot = snapshots_by_id[link.finding_version_id]
        if snapshot.get("finding") != finding_version.canonical_content_json or snapshot.get("finding_content_hash") != link.finding_content_hash:
            raise _conflict("Stored report finding snapshot does not match its pinned version.")
        attribution = snapshot["attribution"]
        if (
            snapshot["finding_id"] != finding_version.finding_id
            or attribution["id"] != finding_version.created_by_attribution_id
            or attribution["investigation_id"] != version.investigation_id
            or attribution["identity_assurance"] != "caller_asserted"
            or attribution["entry_method"] != "manual_entry"
        ):
            raise _conflict("Report finding attribution snapshot has invalid identity or ownership.")
        constitution = attribution["constitution_snapshot"]
        bound_attribution = await db.get(RecordAttribution, finding_version.created_by_attribution_id)
        if bound_attribution is None or (
            attribution["associated_role_id"] != bound_attribution.associated_role_id
            or (constitution["id"] if constitution is not None else None) != bound_attribution.constitution_snapshot_id
        ):
            raise _conflict("Report constitution snapshot is not bound to its finding attribution.")
        if constitution is not None and (
            canonical_json_hash(constitution["constitution_json"]) != constitution["constitution_hash"]
            or constitution["role_id"] != attribution["associated_role_id"]
        ):
            raise _conflict("Report attribution constitution snapshot failed integrity verification.")
        if constitution is not None:
            bound_constitution = await db.get(ScientistConstitutionSnapshot, constitution["id"])
            if bound_constitution is None or (
                bound_constitution.constitution_hash != constitution["constitution_hash"]
                or bound_constitution.role_id != constitution["role_id"]
                or bound_constitution.constitution_version != constitution["constitution_version"]
            ):
                raise _conflict("Report constitution snapshot does not match its persisted binding.")
        evidence = await db.scalars(select(FindingEvidenceLink).where(FindingEvidenceLink.finding_version_id == finding_version.id))
        current_hashes = {item.citation_key: item.snapshot_hash for item in evidence.all()}
        pinned = snapshot["evidence_snapshots"]
        pinned_hashes = {item["citation_key"]: item["snapshot_hash"] for item in pinned}
        if len(pinned_hashes) != len(pinned) or current_hashes != pinned_hashes:
            raise _conflict("Stored report source snapshots do not match the pinned evidence hashes.")
        definitions = {item["key"]: item for item in snapshot["finding"]["evidence_links"]}
        for item in pinned:
            source = item["source_snapshot"]
            definition = definitions[item["citation_key"]]
            if (
                canonical_json_hash(source) != item["snapshot_hash"]
                or source.get("evidence_item_id") != definition["evidence_item_id"]
                or (source.get("evidence_review") or {}).get("id") != definition["evidence_review_id"]
                or item["relationship"] != definition["relationship"]
                or item["rationale"] != definition["rationale"]
            ):
                raise _conflict("Report evidence snapshot contents do not match their pinned hash or citation.")
    await _validate_scope_claims(db, version.investigation_id, list(version.scope_claim_ids))
    return canonical, links


async def _snapshot_source_context(
    db: AsyncSession, investigation_id: str, claim_ids: list[str],
    selections: list[ReportFindingLinkInput],
) -> dict[str, Any]:
    investigation = await _investigation_or_404(db, investigation_id)
    claims = []
    for claim_id in claim_ids:
        claim = await db.get(Claim, claim_id)
        claims.append({
            "id": claim.id, "statement": claim.statement, "metric_name": claim.metric_name,
            "reported_value": claim.reported_value, "metric_direction": claim.metric_direction,
            "source_kind": claim.source_kind, "source_locator": claim.source_locator,
            "published": claim.published, "verification_status": claim.verification_status,
        })
    findings = []
    for selection in sorted(selections, key=lambda item: item.finding_version_id):
        version = await db.get(FindingVersion, selection.finding_version_id)
        attribution = await db.get(RecordAttribution, version.created_by_attribution_id)
        if attribution is None or attribution.investigation_id != investigation_id:
            raise _conflict("Finding attribution is missing or outside the investigation.")
        evidence = await db.scalars(
            select(FindingEvidenceLink).where(FindingEvidenceLink.finding_version_id == version.id)
            .order_by(FindingEvidenceLink.citation_key.asc())
        )
        findings.append({
            "finding_version_id": version.id, "finding_id": version.finding_id,
            "finding_content_hash": version.content_hash,
            "finding": deepcopy(version.canonical_content_json),
            "attribution": (await _attribution_read(db, attribution)).model_dump(mode="json"),
            "evidence_snapshots": [{
                "citation_key": item.citation_key, "relationship": item.relationship,
                "rationale": item.rationale, "snapshot_hash": item.snapshot_hash,
                "source_snapshot": deepcopy(item.source_snapshot_json),
            } for item in evidence.all()],
        })
    return {
        "investigation": {
            "id": investigation.id, "source_kind": investigation.source_kind,
            "paper_id": investigation.paper_id,
            "execution_status": investigation.execution_status,
            "claim_assessment": investigation.claim_assessment,
        },
        "claims": claims, "findings": findings,
    }


def _definition_from_create(payload: ReportCreate) -> ReportVersionDefinition:
    if payload.version is None:
        raise _conflict("Report version definition is missing.")
    return payload.version


def _definition_from_version_create(payload: ReportVersionCreate) -> ReportVersionDefinition:
    if payload.version is None:
        raise _conflict("Report version definition is missing.")
    return payload.version


async def _insert_version(
    db: AsyncSession,
    *,
    report: Report,
    definition: ReportVersionDefinition,
    attribution_id: str,
    parent_version_id: str | None,
    version_number: int,
    scope_claim_ids: list[str],
) -> ReportVersion:
    source_context = await _snapshot_source_context(db, report.investigation_id, scope_claim_ids, definition.finding_links)
    canonical = canonical_report_content(
        report_kind=definition.report_kind,
        title=definition.title,
        scope_claim_ids=scope_claim_ids,
        limitations=definition.limitations,
        unresolved_questions=definition.unresolved_questions,
        finding_links=definition.finding_links,
        source_context=source_context,
    )
    version = ReportVersion(
        id=str(uuid4()),
        report_id=report.id,
        investigation_id=report.investigation_id,
        parent_version_id=parent_version_id,
        version_number=version_number,
        report_kind=definition.report_kind,
        title=definition.title,
        scope_claim_ids=scope_claim_ids,
        limitations=list(definition.limitations),
        unresolved_questions=list(definition.unresolved_questions),
        canonical_content_json=canonical,
        content_hash=report_hash(canonical),
        schema_version="report.v1",
        created_by_attribution_id=attribution_id,
    )
    db.add(version)
    await db.flush()
    for link in definition.finding_links:
        db.add(
            ReportFindingLink(
                id=str(uuid4()),
                report_version_id=version.id,
                finding_version_id=link.finding_version_id,
                investigation_id=report.investigation_id,
                finding_content_hash=link.finding_content_hash,
                section=link.section,
                position=link.position,
                disposition=link.disposition,
                exclusion_reason=link.exclusion_reason,
            )
        )
    await db.flush()
    return version


async def create_report(
    db: AsyncSession,
    investigation_id: str,
    payload: ReportCreate,
) -> Report:
    await _investigation_or_404(db, investigation_id)
    definition = _definition_from_create(payload)
    claim_ids, _versions = await _validate_definition(db, investigation_id, definition)
    attribution = await create_attribution(db, investigation_id, payload.attribution)
    report = Report(
        id=str(uuid4()),
        investigation_id=investigation_id,
        created_by_attribution_id=attribution.id,
        status="draft",
    )
    db.add(report)
    await db.flush()
    await _insert_version(
        db,
        report=report,
        definition=definition,
        attribution_id=attribution.id,
        parent_version_id=None,
        version_number=1,
        scope_claim_ids=claim_ids,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Report could not be persisted without violating investigation isolation.") from exc
    await db.refresh(report)
    return report


async def create_report_version(
    db: AsyncSession,
    investigation_id: str,
    report_id: str,
    payload: ReportVersionCreate,
) -> ReportVersion:
    report = await db.scalar(
        select(Report)
        .where(Report.id == report_id, Report.investigation_id == investigation_id)
        .with_for_update()
    )
    if report is None:
        raise _not_found("Report not found in this investigation.")
    if report.status != "draft":
        raise _conflict("Published or withdrawn reports cannot receive new versions.")
    definition = _definition_from_version_create(payload)
    claim_ids, _versions = await _validate_definition(db, investigation_id, definition)
    parent = await db.get(ReportVersion, payload.parent_version_id)
    if (
        parent is None
        or parent.report_id != report_id
        or parent.investigation_id != investigation_id
    ):
        raise _conflict("Parent report version is outside the investigation or report.")
    current = await db.scalar(
        select(ReportVersion)
        .where(
            ReportVersion.report_id == report_id,
            ReportVersion.investigation_id == investigation_id,
        )
        .order_by(ReportVersion.version_number.desc())
    )
    if current is None or current.id != parent.id:
        raise _conflict("A report version must be based on the latest report version.")
    attribution = await create_attribution(db, investigation_id, payload.attribution)
    version = await _insert_version(
        db,
        report=report,
        definition=definition,
        attribution_id=attribution.id,
        parent_version_id=parent.id,
        version_number=parent.version_number + 1,
        scope_claim_ids=claim_ids,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Report version could not be persisted; retry from the latest version.") from exc
    await db.refresh(version)
    return version


async def latest_report_version(
    db: AsyncSession,
    investigation_id: str,
    report_id: str,
) -> ReportVersion:
    version = await db.scalar(
        select(ReportVersion)
        .where(
            ReportVersion.report_id == report_id,
            ReportVersion.investigation_id == investigation_id,
        )
        .order_by(ReportVersion.version_number.desc())
    )
    if version is None:
        raise _conflict("Report has no version.")
    return version


async def record_report_event(
    db: AsyncSession,
    investigation_id: str,
    report_id: str,
    payload: ReportEventCreate,
) -> ReportEvent:
    report = await db.scalar(
        select(Report)
        .where(Report.id == report_id, Report.investigation_id == investigation_id)
        .with_for_update()
    )
    if report is None:
        raise _not_found("Report not found in this investigation.")
    latest_event = await db.scalar(
        select(ReportEvent).where(ReportEvent.report_id == report_id)
        .order_by(ReportEvent.sequence_number.desc()).limit(1)
    )
    if payload.event_type == "withdrawn":
        if report.status != "published" or latest_event is None or latest_event.event_type != "published":
            raise _conflict("Only published reports can be withdrawn.")
        if payload.report_version_id is not None and payload.report_version_id != latest_event.report_version_id:
            raise _conflict("Withdrawal must target the published report version.")
        target_id = latest_event.report_version_id
    else:
        target_id = payload.report_version_id
    version = (
        await db.get(ReportVersion, target_id)
        if target_id is not None
        else await latest_report_version(db, investigation_id, report_id)
    )
    if (
        version is None
        or version.report_id != report_id
        or version.investigation_id != investigation_id
    ):
        raise _not_found("Report version not found in this investigation.")
    if payload.event_type == "published":
        if report.status != "draft":
            raise _conflict("Only draft reports can be published.")
        await validate_report_version(db, version)
        included_links = await db.scalars(
            select(ReportFindingLink).where(
                ReportFindingLink.report_version_id == version.id,
                ReportFindingLink.disposition == "included",
            )
        )
        included = list(included_links.all())
        if not included:
            raise _conflict("Published reports require at least one included finding.")
        # Lock in one stable order, shared with manual review insertion. A newer
        # review either commits before eligibility is read or waits until after
        # publication; it cannot slip between the check and the event commit.
        locked = await db.scalars(
            select(FindingVersion).where(FindingVersion.id.in_([item.finding_version_id for item in included]))
            .order_by(FindingVersion.id.asc()).with_for_update()
        )
        locked.all()
        for link in included:
            review = await db.scalar(
                select(RecordReview)
                .where(
                    RecordReview.investigation_id == investigation_id,
                    RecordReview.finding_version_id == link.finding_version_id,
                    RecordReview.target_content_hash == link.finding_content_hash,
                )
                .order_by(RecordReview.reviewed_at.desc(), RecordReview.id.desc())
                .limit(1)
            )
            if review is None or review.outcome != "accepted_for_inclusion":
                raise _conflict(
                    "Published reports require the latest exact-hash review to accept every included finding."
                )
            definition = _validate_stored_version(await db.get(FindingVersion, link.finding_version_id))
            if not (review.citations_checked and review.limitations_checked and review.execution_wording_checked):
                raise _conflict("The accepted finding review is missing required checks.")
            if any(assertion.numbers for assertion in definition.assertions) and review.numeric_transcription_checked is not True:
                raise _conflict("Numeric findings require a checked numeric transcription review.")
        report.status = "published"
    else:
        if report.status != "published":
            raise _conflict("Only published reports can be withdrawn.")
        report.status = "withdrawn"

    attribution = await create_attribution(db, investigation_id, payload.attribution)
    event = ReportEvent(
        id=str(uuid4()),
        report_id=report_id,
        report_version_id=version.id,
        investigation_id=investigation_id,
        sequence_number=latest_event.sequence_number + 1 if latest_event is not None else 1,
        target_content_hash=version.content_hash,
        event_type=payload.event_type,
        attribution_id=attribution.id,
        notes=payload.notes,
    )
    db.add(event)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Report event could not be persisted.") from exc
    await db.refresh(event)
    return event


async def create_export(
    db: AsyncSession,
    investigation_id: str,
    report_id: str,
    version_id: str,
) -> ReportExport:
    report = await db.scalar(
        select(Report).where(Report.id == report_id, Report.investigation_id == investigation_id).with_for_update()
    )
    if report is None:
        raise _not_found("Report not found in this investigation.")
    version = await db.get(ReportVersion, version_id)
    if (
        version is None
        or version.report_id != report_id
        or version.investigation_id != investigation_id
    ):
        raise _not_found("Report version not found in this investigation.")
    await validate_report_version(db, version)
    existing = await db.scalar(select(ReportExport).where(ReportExport.report_version_id == version.id))
    if existing is not None:
        verify_export_bytes(existing)
        return existing
    from reprolab.services.report_rendering import render_report_exports

    json_bytes, markdown_bytes = await render_report_exports(db, version)
    if len(json_bytes) > MAX_EXPORT_BYTES or len(markdown_bytes) > MAX_EXPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Each report export format is limited to 2 MiB.",
        )
    export = ReportExport(
        id=str(uuid4()),
        report_version_id=version.id,
        investigation_id=investigation_id,
        report_content_hash=version.content_hash,
        json_bytes=json_bytes,
        markdown_bytes=markdown_bytes,
        json_size_bytes=len(json_bytes),
        markdown_size_bytes=len(markdown_bytes),
        json_sha256=hashlib.sha256(json_bytes).hexdigest(),
        markdown_sha256=hashlib.sha256(markdown_bytes).hexdigest(),
    )
    db.add(export)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Report export could not be persisted atomically.") from exc
    await db.refresh(export)
    return export


def verify_export_bytes(export: ReportExport) -> None:
    for name in ("json", "markdown"):
        content = getattr(export, f"{name}_bytes")
        if (
            len(content) > MAX_EXPORT_BYTES
            or len(content) != getattr(export, f"{name}_size_bytes")
            or hashlib.sha256(content).hexdigest() != getattr(export, f"{name}_sha256")
        ):
            raise _conflict("Stored report export bytes failed integrity verification.")


async def report_version_read(db: AsyncSession, version: ReportVersion):
    attribution = await db.get(RecordAttribution, version.created_by_attribution_id)
    if attribution is None:
        raise _conflict("Report version attribution is missing.")
    links = await db.scalars(
        select(ReportFindingLink)
        .where(ReportFindingLink.report_version_id == version.id)
        .order_by(ReportFindingLink.section.asc(), ReportFindingLink.position.asc())
    )
    from reprolab.schemas.reports import ReportFindingLinkRead, ReportVersionRead

    return ReportVersionRead(
        id=version.id,
        report_id=version.report_id,
        investigation_id=version.investigation_id,
        parent_version_id=version.parent_version_id,
        version_number=version.version_number,
        report_kind=version.report_kind,
        title=version.title,
        scope_claim_ids=version.scope_claim_ids,
        limitations=version.limitations,
        unresolved_questions=version.unresolved_questions,
        schema_version=version.schema_version,
        canonical_content_json=version.canonical_content_json,
        content_hash=version.content_hash,
        finding_links=[ReportFindingLinkRead.model_validate(link, from_attributes=True) for link in links.all()],
        attribution=await _attribution_read(db, attribution),
        created_at=version.created_at,
    )


async def report_event_read(db: AsyncSession, event: ReportEvent):
    attribution = await db.get(RecordAttribution, event.attribution_id)
    if attribution is None:
        raise _conflict("Report event attribution is missing.")
    from reprolab.schemas.reports import ReportEventRead

    return ReportEventRead(
        id=event.id,
        report_id=event.report_id,
        report_version_id=event.report_version_id,
        investigation_id=event.investigation_id,
        event_type=event.event_type,
        sequence_number=event.sequence_number,
        target_content_hash=event.target_content_hash,
        attribution=await _attribution_read(db, attribution),
        notes=event.notes,
        created_at=event.created_at,
    )


async def report_read(db: AsyncSession, report: Report):
    from reprolab.schemas.reports import ReportRead

    creator = await db.get(RecordAttribution, report.created_by_attribution_id)
    if creator is None:
        raise _conflict("Report attribution is missing.")
    versions = await db.scalars(
        select(ReportVersion)
        .where(
            ReportVersion.report_id == report.id,
            ReportVersion.investigation_id == report.investigation_id,
        )
        .order_by(ReportVersion.version_number.asc())
    )
    events = await db.scalars(
        select(ReportEvent)
        .where(
            ReportEvent.report_id == report.id,
            ReportEvent.investigation_id == report.investigation_id,
        )
        .order_by(ReportEvent.sequence_number.asc())
    )
    return ReportRead(
        id=report.id,
        investigation_id=report.investigation_id,
        status=report.status,
        created_by_attribution=await _attribution_read(db, creator),
        versions=[await report_version_read(db, version) for version in versions.all()],
        events=[await report_event_read(db, event) for event in events.all()],
        created_at=report.created_at,
    )
