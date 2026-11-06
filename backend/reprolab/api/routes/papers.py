from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from reprolab.db.session import get_db
from reprolab.models.paper import Artifact, Paper
from reprolab.schemas.paper import PaperDetail, PaperRead, PaperUploadResponse
from reprolab.storage.local import LocalPrivateStorage, UploadValidationError

router = APIRouter(prefix="/api/v1/papers", tags=["papers"])


def _download_url(paper_id: str) -> str:
    return f"/api/v1/papers/{quote(paper_id, safe='')}/download"


def get_storage(request: Request) -> LocalPrivateStorage:
    return request.app.state.storage


async def _detail(db: AsyncSession, paper: Paper) -> PaperDetail:
    artifact = await db.scalar(select(Artifact).where(Artifact.paper_id == paper.id))
    if artifact is None:
        raise HTTPException(status_code=500, detail="Paper artifact metadata is missing.")
    data = PaperRead.model_validate(paper).model_copy(update={"download_url": _download_url(paper.id)})
    return PaperDetail(**data.model_dump(), artifact=artifact)


@router.post("", response_model=PaperUploadResponse)
async def upload_paper(
    response: Response,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    storage: LocalPrivateStorage = Depends(get_storage),
) -> PaperUploadResponse:
    clean_title = (title or Path(file.filename or "paper.pdf").stem).strip()
    if not clean_title:
        clean_title = "Untitled paper"
    if len(clean_title) > 500:
        raise HTTPException(status_code=422, detail="Title must be 500 characters or fewer.")

    try:
        stored = await storage.store_pdf(file)
    except UploadValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = await db.scalar(select(Paper).where(Paper.sha256 == stored.sha256))
    if existing is not None:
        detail = await _detail(db, existing)
        response.status_code = 200
        return PaperUploadResponse(**detail.model_dump(), created=False)

    paper = Paper(
        title=clean_title,
        original_filename=stored.original_filename,
        content_type=stored.content_type,
        file_size=stored.size_bytes,
        sha256=stored.sha256,
        storage_key=stored.storage_key,
    )
    db.add(paper)
    await db.flush()
    db.add(
        Artifact(
            paper_id=paper.id,
            kind="paper_pdf",
            storage_key=stored.storage_key,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            content_type=stored.content_type,
        )
    )
    await db.commit()
    await db.refresh(paper)
    detail = await _detail(db, paper)
    response.status_code = 201
    return PaperUploadResponse(**detail.model_dump(), created=True)


@router.get("", response_model=list[PaperRead])
async def list_papers(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[PaperRead]:
    result = await db.scalars(select(Paper).order_by(Paper.created_at.desc()).offset(offset).limit(limit))
    return [
        PaperRead.model_validate(paper).model_copy(update={"download_url": _download_url(paper.id)})
        for paper in result.all()
    ]


@router.get("/count")
async def paper_count(db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    count = await db.scalar(select(func.count()).select_from(Paper))
    return {"count": int(count or 0)}


@router.get("/{paper_id}", response_model=PaperDetail)
async def get_paper(paper_id: str, db: AsyncSession = Depends(get_db)) -> PaperDetail:
    paper = await db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found.")
    return await _detail(db, paper)


@router.get("/{paper_id}/download")
async def download_paper(
    paper_id: str,
    db: AsyncSession = Depends(get_db),
    storage: LocalPrivateStorage = Depends(get_storage),
) -> FileResponse:
    paper = await db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found.")
    try:
        path = storage.resolve(paper.storage_key)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Paper storage metadata is invalid.") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Paper file is not available.")
    return FileResponse(path, media_type="application/pdf", filename=paper.original_filename)
