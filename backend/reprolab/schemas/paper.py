from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    storage_key: str
    sha256: str
    size_bytes: int
    content_type: str
    created_at: datetime


class PaperRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    original_filename: str
    content_type: str
    file_size: int
    sha256: str
    status: str
    created_at: datetime
    updated_at: datetime
    download_url: str | None = None


class PaperDetail(PaperRead):
    artifact: ArtifactRead


class PaperUploadResponse(PaperDetail):
    created: bool = Field(description="False when the uploaded bytes already existed")
