from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.db.session import get_db
from reprolab.models.reports import Report, ReportEvent, ReportExport, ReportVersion
from reprolab.schemas.reports import (
    ReportCreate,
    ReportEventCreate,
    ReportEventRead,
    ReportExportRead,
    ReportRead,
    ReportTransitionRequest,
    ReportVersionCreate,
    ReportVersionRead,
)
from reprolab.services.record_integrity import _not_found
from reprolab.services.report_integrity import (
    create_export,
    create_report,
    create_report_version,
    record_report_event,
    report_event_read,
    report_read,
    report_version_read,
    verify_export_bytes,
)


router = APIRouter(prefix="/api/v1/investigations", tags=["reports"])


async def _investigation_or_404(db: AsyncSession, investigation_id: str):
    from reprolab.models.research import Investigation

    investigation = await db.get(Investigation, investigation_id)
    if investigation is None:
        raise _not_found("Investigation not found.")
    return investigation


async def _report_or_404(
    db: AsyncSession,
    investigation_id: str,
    report_id: str,
) -> Report:
    report = await db.get(Report, report_id)
    if report is None or report.investigation_id != investigation_id:
        raise _not_found("Report not found in this investigation.")
    return report


async def _version_or_404(
    db: AsyncSession,
    investigation_id: str,
    report_id: str,
    version_id: str,
) -> ReportVersion:
    version = await db.get(ReportVersion, version_id)
    if (
        version is None
        or version.report_id != report_id
        or version.investigation_id != investigation_id
    ):
        raise _not_found("Report version not found in this investigation.")
    return version


async def _export_or_404(
    db: AsyncSession,
    investigation_id: str,
    report_id: str,
    version_id: str,
    export_id: str,
) -> ReportExport:
    export = await db.get(ReportExport, export_id)
    if (
        export is None
        or export.investigation_id != investigation_id
        or export.report_version_id != version_id
    ):
        raise _not_found("Report export not found in this investigation.")
    version = await _version_or_404(db, investigation_id, report_id, version_id)
    if version.content_hash != export.report_content_hash:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="Report export target hash no longer matches its version.")
    verify_export_bytes(export)
    return export


@router.post(
    "/{investigation_id}/reports",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_report_route(
    investigation_id: str,
    payload: ReportCreate,
    db: AsyncSession = Depends(get_db),
) -> ReportRead:
    report = await create_report(db, investigation_id, payload)
    return await report_read(db, report)


@router.get(
    "/{investigation_id}/reports",
    response_model=list[ReportRead],
)
async def list_reports(
    investigation_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ReportRead]:
    await _investigation_or_404(db, investigation_id)
    reports = await db.scalars(
        select(Report)
        .where(Report.investigation_id == investigation_id)
        .order_by(Report.created_at.asc())
    )
    return [await report_read(db, report) for report in reports.all()]


@router.post(
    "/{investigation_id}/reports/{report_id}/versions",
    response_model=ReportVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_report_version_route(
    investigation_id: str,
    report_id: str,
    payload: ReportVersionCreate,
    db: AsyncSession = Depends(get_db),
) -> ReportVersionRead:
    version = await create_report_version(db, investigation_id, report_id, payload)
    return await report_version_read(db, version)


@router.get(
    "/{investigation_id}/reports/{report_id}/versions/{version_id}",
    response_model=ReportVersionRead,
)
async def get_report_version(
    investigation_id: str,
    report_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReportVersionRead:
    version = await _version_or_404(db, investigation_id, report_id, version_id)
    return await report_version_read(db, version)


@router.post(
    "/{investigation_id}/reports/{report_id}/versions/{version_id}/exports",
    response_model=ReportExportRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_report_export(
    investigation_id: str,
    report_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReportExportRead:
    export = await create_export(db, investigation_id, report_id, version_id)
    return ReportExportRead.model_validate(export, from_attributes=True)


@router.get(
    "/{investigation_id}/reports/{report_id}/versions/{version_id}/exports",
    response_model=list[ReportExportRead],
)
async def list_report_exports(
    investigation_id: str,
    report_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ReportExportRead]:
    await _version_or_404(db, investigation_id, report_id, version_id)
    exports = await db.scalars(
        select(ReportExport)
        .where(
            ReportExport.investigation_id == investigation_id,
            ReportExport.report_version_id == version_id,
        )
        .order_by(ReportExport.created_at.asc())
    )
    return [ReportExportRead.model_validate(item, from_attributes=True) for item in exports.all()]


@router.get(
    "/{investigation_id}/reports/{report_id}/versions/{version_id}/exports/{export_id}/json",
)
async def download_report_json(
    investigation_id: str,
    report_id: str,
    version_id: str,
    export_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    export = await _export_or_404(db, investigation_id, report_id, version_id, export_id)
    return Response(
        content=export.json_bytes,
        media_type="application/json",
        headers={
            "ETag": f'"{export.json_sha256}"', "X-Content-SHA256": export.json_sha256,
            "Content-Disposition": f'attachment; filename="report-{version_id}.json"',
            "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        },
    )


@router.get(
    "/{investigation_id}/reports/{report_id}/versions/{version_id}/exports/{export_id}/markdown",
)
async def download_report_markdown(
    investigation_id: str,
    report_id: str,
    version_id: str,
    export_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    export = await _export_or_404(db, investigation_id, report_id, version_id, export_id)
    return Response(
        content=export.markdown_bytes,
        media_type="text/markdown",
        headers={
            "ETag": f'"{export.markdown_sha256}"',
            "X-Content-SHA256": export.markdown_sha256,
            "Content-Disposition": f'attachment; filename="report-{version_id}.md"',
            "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        },
    )


@router.post(
    "/{investigation_id}/reports/{report_id}/events",
    response_model=ReportEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_report_event(
    investigation_id: str,
    report_id: str,
    payload: ReportEventCreate,
    db: AsyncSession = Depends(get_db),
) -> ReportEventRead:
    event = await record_report_event(db, investigation_id, report_id, payload)
    return await report_event_read(db, event)


@router.post(
    "/{investigation_id}/reports/{report_id}/publish",
    response_model=ReportEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def publish_report(
    investigation_id: str,
    report_id: str,
    payload: ReportTransitionRequest,
    db: AsyncSession = Depends(get_db),
) -> ReportEventRead:
    event = await record_report_event(
        db,
        investigation_id,
        report_id,
        ReportEventCreate(
            attribution=payload.attribution,
            event_type="published",
            report_version_id=payload.report_version_id,
            notes=payload.notes,
        ),
    )
    return await report_event_read(db, event)


@router.post(
    "/{investigation_id}/reports/{report_id}/withdraw",
    response_model=ReportEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def withdraw_report(
    investigation_id: str,
    report_id: str,
    payload: ReportTransitionRequest,
    db: AsyncSession = Depends(get_db),
) -> ReportEventRead:
    event = await record_report_event(
        db,
        investigation_id,
        report_id,
        ReportEventCreate(
            attribution=payload.attribution,
            event_type="withdrawn",
            report_version_id=payload.report_version_id,
            notes=payload.notes,
        ),
    )
    return await report_event_read(db, event)


@router.get(
    "/{investigation_id}/reports/{report_id}/events",
    response_model=list[ReportEventRead],
)
async def list_report_events(
    investigation_id: str,
    report_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ReportEventRead]:
    await _report_or_404(db, investigation_id, report_id)
    events = await db.scalars(
        select(ReportEvent)
        .where(
            ReportEvent.report_id == report_id,
            ReportEvent.investigation_id == investigation_id,
        )
        .order_by(ReportEvent.sequence_number.asc())
    )
    return [await report_event_read(db, event) for event in events.all()]


@router.get(
    "/{investigation_id}/reports/{report_id}",
    response_model=ReportRead,
)
async def get_report(
    investigation_id: str,
    report_id: str,
    db: AsyncSession = Depends(get_db),
) -> ReportRead:
    report = await _report_or_404(db, investigation_id, report_id)
    return await report_read(db, report)
