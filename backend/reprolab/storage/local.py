import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile


class UploadValidationError(ValueError):
    pass


class StorageIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class StoredUpload:
    storage_key: str
    sha256: str
    size_bytes: int
    content_type: str
    original_filename: str


@dataclass(frozen=True)
class StoredResearchArtifact:
    storage_key: str
    sha256: str
    size_bytes: int
    content_type: str
    created: bool


class LocalPrivateStorage:
    """Private filesystem storage. The root is intentionally not exposed as static web content."""

    def __init__(self, root: Path, max_upload_bytes: int):
        self.max_upload_bytes = max_upload_bytes
        try:
            self.root = root.resolve()
            (self.root / ".tmp").mkdir(parents=True, exist_ok=True)
            (self.root / "papers").mkdir(parents=True, exist_ok=True)
            (self.root / "research").mkdir(parents=True, exist_ok=True)
        except OSError:
            import tempfile
            self.root = Path(tempfile.gettempdir()) / "reprolab_storage"
            (self.root / ".tmp").mkdir(parents=True, exist_ok=True)
            (self.root / "papers").mkdir(parents=True, exist_ok=True)
            (self.root / "research").mkdir(parents=True, exist_ok=True)

    async def store_pdf(self, upload: UploadFile) -> StoredUpload:
        filename = upload.filename or "paper.pdf"
        if Path(filename).suffix.lower() != ".pdf":
            raise UploadValidationError("Only .pdf files are accepted.")
        if upload.content_type not in {"application/pdf", "application/octet-stream", None}:
            raise UploadValidationError("The uploaded file must have a PDF content type.")

        temp_path = self.root / ".tmp" / f"{uuid4().hex}.upload"
        digest = hashlib.sha256()
        size = 0
        header = b""
        try:
            with temp_path.open("wb") as destination:
                while chunk := await upload.read(1024 * 1024):
                    if not header:
                        header = chunk[:5]
                    size += len(chunk)
                    if size > self.max_upload_bytes:
                        raise UploadValidationError(
                            f"The PDF exceeds the {self.max_upload_bytes // (1024 * 1024)} MiB limit."
                        )
                    digest.update(chunk)
                    destination.write(chunk)
            if size == 0 or header != b"%PDF-":
                raise UploadValidationError("The uploaded file is not a valid PDF signature.")

            sha256 = digest.hexdigest()
            storage_key = f"papers/{sha256[:2]}/{sha256}.pdf"
            final_path = self.resolve(storage_key)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            if not final_path.exists():
                temp_path.replace(final_path)
            return StoredUpload(storage_key, sha256, size, "application/pdf", filename)
        finally:
            temp_path.unlink(missing_ok=True)

    def resolve(self, storage_key: str) -> Path:
        if not re.fullmatch(r"papers/[0-9a-f]{2}/[0-9a-f]{64}\.pdf", storage_key):
            raise ValueError("Invalid storage key")
        candidate = (self.root / storage_key).resolve()
        if self.root not in candidate.parents:
            raise ValueError("Storage key escaped storage root")
        return candidate

    def resolve_research(self, storage_key: str) -> Path:
        if not re.fullmatch(r"research/[0-9a-f]{2}/[0-9a-f]{64}\.(csv|json|log|txt|manifest)", storage_key):
            raise ValueError("Invalid research storage key")
        candidate = (self.root / storage_key).resolve()
        if self.root not in candidate.parents or self.root in candidate.parents and "research" not in candidate.relative_to(self.root).parts:
            raise ValueError("Research storage key escaped research namespace")
        return candidate

    def store_research_bytes(
        self,
        content: bytes,
        *,
        content_type: str,
        extension: str,
        expected_sha256: str | None = None,
    ) -> StoredResearchArtifact:
        if not isinstance(content, bytes):
            raise TypeError("Research artifact content must be bytes")
        extension = extension.lower().lstrip(".")
        if extension not in {"csv", "json", "log", "txt", "manifest"}:
            raise ValueError("Research artifact extension is not allowlisted")
        sha256 = hashlib.sha256(content).hexdigest()
        if expected_sha256 is not None and expected_sha256 != sha256:
            raise StorageIntegrityError("Expected research artifact hash does not match content")
        storage_key = f"research/{sha256[:2]}/{sha256}.{extension}"
        final_path = self.resolve_research(storage_key)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        if final_path.exists():
            existing = final_path.read_bytes()
            if hashlib.sha256(existing).hexdigest() != sha256:
                raise StorageIntegrityError("Content-addressed research artifact is corrupted")
            return StoredResearchArtifact(storage_key, sha256, len(existing), content_type, False)

        temp_path = self.root / ".tmp" / f"{sha256}.{extension}.{uuid4().hex}.upload"
        try:
            with temp_path.open("xb") as destination:
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temp_path, final_path)
            stored = final_path.read_bytes()
            if hashlib.sha256(stored).hexdigest() != sha256:
                raise StorageIntegrityError("Research artifact changed during atomic write")
            return StoredResearchArtifact(storage_key, sha256, len(stored), content_type, True)
        finally:
            temp_path.unlink(missing_ok=True)

    def read_research_bytes(self, storage_key: str, *, expected_sha256: str) -> bytes:
        path = self.resolve_research(storage_key)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise StorageIntegrityError("Research artifact is unavailable") from exc
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != expected_sha256:
            raise StorageIntegrityError("Research artifact hash verification failed; stored bytes may be corrupted")
        return content

    def delete_research(self, storage_key: str) -> None:
        self.resolve_research(storage_key).unlink(missing_ok=True)
