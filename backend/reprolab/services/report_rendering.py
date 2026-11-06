import json
import html
import re
from copy import deepcopy
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.models.reports import ReportVersion
from reprolab.services.report_integrity import validate_report_version


async def _render_model(db: AsyncSession, version: ReportVersion) -> dict[str, Any]:
    canonical, links = await validate_report_version(db, version)
    context = deepcopy(canonical["source_context"])
    snapshots = {item["finding_version_id"]: item for item in context["findings"]}
    findings: list[dict[str, Any]] = []
    for report_link in links:
        item: dict[str, Any] = {
            "finding_version_id": report_link.finding_version_id,
            "finding_content_hash": report_link.finding_content_hash,
            "section": report_link.section,
            "position": report_link.position,
            "disposition": report_link.disposition,
            "exclusion_reason": report_link.exclusion_reason,
        }
        if report_link.disposition == "included":
            snapshot = snapshots[report_link.finding_version_id]
            item["finding"] = snapshot["finding"]
            item["attribution"] = snapshot["attribution"]
            item["evidence_snapshots"] = snapshot["evidence_snapshots"]
        findings.append(item)

    return {
        "schema_version": "report-export.v1",
        "report": {
            "id": version.report_id,
            "investigation_id": version.investigation_id,
            "version_id": version.id,
            "version_number": version.version_number,
            "report_kind": version.report_kind,
            "title": version.title,
            "content_hash": version.content_hash,
        },
        "scope": {
            "claim_ids": list(version.scope_claim_ids),
            "claims": context["claims"],
        },
        "investigation_snapshot": context["investigation"],
        "findings": findings,
        "limitations": list(version.limitations),
        "unresolved_questions": list(version.unresolved_questions),
        "integrity_notice": (
            "This is an analysis/record report. It does not assert that an experiment "
            "occurred or convert framework-test scoring into scientific evidence."
        ),
    }


def _canonical_export_json(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _markdown_line(value: Any) -> str:
    # Exported source text is data, never active HTML or Markdown structure.
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return re.sub(r"([\\`*_{\[\]}()#!|>])", r"\\\1", html.escape(text, quote=False))


def _render_markdown(value: dict[str, Any]) -> str:
    report = value["report"]
    scope = value["scope"]
    lines = [
        f"# {_markdown_line(report['title'])}",
        "",
        "**Report type:** analysis/record",
        "**Lifecycle status:** consult the report's append-only events; not part of this immutable export.",
        f"**Version:** {_markdown_line(report['version_number'])}",
        f"**Content hash:** `{_markdown_line(report['content_hash'])}`",
        "",
        "> This is an analysis/record report. It does not assert that an experiment occurred or convert framework-test scoring into scientific evidence.",
        "",
        "## Scope claims",
        "",
    ]
    if scope["claims"]:
        for claim in scope["claims"]:
            source = f" — source: {_markdown_line(claim['source_locator'])}" if claim["source_locator"] else ""
            lines.append(
                f"- `{_markdown_line(claim['id'])}`: {_markdown_line(claim['statement'])}{source}"
            )
    else:
        lines.append("- No scope claims were selected.")

    lines.extend(["", "## Findings", ""])
    if not value["findings"]:
        lines.append("No finding versions were selected.")
    for item in value["findings"]:
        heading = (
            f"### {_markdown_line(item['section'])} — position {_markdown_line(item['position'])}"
        )
        lines.extend([heading, ""])
        if item["disposition"] == "excluded_with_reason":
            lines.extend([
                f"- **Disposition:** excluded",
                f"- **Reason:** {_markdown_line(item['exclusion_reason'])}",
                f"- **Pinned finding version:** `{_markdown_line(item['finding_version_id'])}`",
                f"- **Pinned finding hash:** `{_markdown_line(item['finding_content_hash'])}`",
                "",
            ])
            continue
        finding = item["finding"]
        lines.extend([
            f"- **Title:** {_markdown_line(finding['title'])}",
            f"- **Kind:** {_markdown_line(finding['record_kind'])}",
            f"- **Finding version:** `{_markdown_line(item['finding_version_id'])}`",
            f"- **Finding hash:** `{_markdown_line(item['finding_content_hash'])}`",
            "",
        ])
        for assertion in finding["assertions"]:
            lines.append(
                f"- **{_markdown_line(assertion['key'])}:** {_markdown_line(assertion['text'])}"
            )
            if assertion["citation_keys"]:
                lines.append("  - Citations: " + ", ".join(_markdown_line(key) for key in assertion["citation_keys"]))
            if assertion["grounding"] == "unresolved":
                lines.append(
                    f"  - Unresolved reason: {_markdown_line(assertion['unresolved_reason'])}"
                )
            for number in assertion["numbers"]:
                uncertainty = (
                    f"; uncertainty: {_markdown_line(number['uncertainty_as_reported'])}"
                    if number["uncertainty_as_reported"]
                    else ""
                )
                lines.append(
                    f"  - Numeric `{_markdown_line(number['metric_name'])}`: "
                    f"{_markdown_line(number['value'])} {_markdown_line(number['unit'])} "
                    f"(source `{_markdown_line(number['source_lexeme'])}`)"
                    f"{uncertainty}"
                )
                lines.append(
                    f"    - Citation: {_markdown_line(number['citation_key'])}; "
                    f"span: {number['source_start']}:{number['source_end']}; "
                    f"normalization: {_markdown_line(number['normalization'])}; "
                    f"context: {_markdown_line(number['context'])}"
                )
        if finding["limitations"]:
            lines.append("- Limitations:")
            lines.extend(f"  - {_markdown_line(item)}" for item in finding["limitations"])
        if item["evidence_snapshots"]:
            lines.append("- Evidence snapshots:")
            for evidence in item["evidence_snapshots"]:
                snapshot = evidence["source_snapshot"]
                lines.append(
                    f"  - `{_markdown_line(evidence['citation_key'])}` "
                    f"({_markdown_line(evidence['relationship'])}) "
                    f"{_markdown_line(snapshot.get('source_locator'))}: "
                    f"{_markdown_line(snapshot.get('quoted_text'))} "
                    f"[snapshot `{_markdown_line(evidence['snapshot_hash'])}`]"
                )
                lines.append(
                    f"    - URL: {_markdown_line(snapshot.get('source_url') or 'not recorded')}; "
                    f"verification state: {_markdown_line(snapshot.get('verification_status'))}; "
                    f"rationale: {_markdown_line(evidence['rationale'])}"
                )
        attribution = item["attribution"]
        lines.append(
            f"- Recorded by: {_markdown_line(attribution['recorder_label'])} "
            "(manual entry; caller-asserted identity, not authenticated)."
        )
        lines.append("")

    lines.extend(["## Report limitations", ""])
    if value["limitations"]:
        lines.extend(f"- {_markdown_line(item)}" for item in value["limitations"])
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Unresolved questions", ""])
    if value["unresolved_questions"]:
        lines.extend(f"- {_markdown_line(item)}" for item in value["unresolved_questions"])
    else:
        lines.append("- None recorded.")
    return "\n".join(lines).rstrip() + "\n"


async def render_report_json(db: AsyncSession, version: ReportVersion) -> str:
    return _canonical_export_json(await _render_model(db, version))


async def render_report_markdown(db: AsyncSession, version: ReportVersion) -> str:
    return _render_markdown(await _render_model(db, version))


async def render_report_exports(db: AsyncSession, version: ReportVersion) -> tuple[bytes, bytes]:
    """Render both formats from the same validated, immutable snapshot."""
    model = await _render_model(db, version)
    return _canonical_export_json(model).encode("utf-8"), _render_markdown(model).encode("utf-8")
