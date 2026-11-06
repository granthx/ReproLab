"""Academic Document Parser for ReproLab (Milestone 2).

Provides:
- PDF Magic-byte validation (%PDF- header verification)
- 10MB file size ceiling to mitigate denial-of-wallet / token bombs (LLM06)
- Academic section segmentation (Abstract, Methodology, Results, Tables)
- OpenTelemetry instrumentation on stage2.parser.docling
"""

from dataclasses import dataclass
import io
import re
from typing import List, Optional

from pypdf import PdfReader

from reprolab.core.telemetry import trace_span


class DocumentParsingError(Exception):
    """Base exception for document parsing failures."""
    pass


class DocumentSecurityError(DocumentParsingError):
    """Raised when an uploaded file violates security or size constraints."""
    pass


@dataclass
class ParsedDocument:
    """Structured representation of an academic research paper."""
    title: str
    abstract: str
    methodology: str
    results: str
    raw_text: str
    page_count: int
    tables: List[str]


class AcademicDocumentParser:
    """Hardened academic document parser with security bounds and section segmentation."""

    PDF_MAGIC_BYTES = b"%PDF"

    def __init__(self, max_bytes: int = 10 * 1024 * 1024):
        self.max_bytes = max_bytes

    def validate_magic_bytes(self, data: bytes) -> bool:
        """Verify that the payload begins with %PDF- and does not exceed size limits."""
        if len(data) > self.max_bytes:
            raise DocumentSecurityError(
                f"File size ({len(data)} bytes) exceeds maximum allowed limit of {self.max_bytes} bytes (10MB)."
            )
        if not data.startswith(self.PDF_MAGIC_BYTES):
            raise DocumentSecurityError(
                f"Invalid PDF magic bytes. Expected payload to start with '%PDF', got {data[:8]!r}"
            )
        return True

    def parse_pdf_bytes(self, pdf_bytes: bytes, case_id: Optional[str] = None) -> ParsedDocument:
        """Validate, extract text from pages, and segment sections."""
        with trace_span("stage2.parser.docling", case_id=case_id) as span:
            self.validate_magic_bytes(pdf_bytes)

            try:
                reader = PdfReader(io.BytesIO(pdf_bytes))
                page_count = len(reader.pages)
                extracted_pages = []

                for idx, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ""
                    extracted_pages.append(page_text)

                full_text = "\n\n".join(extracted_pages).strip()
                span.set_attribute("doc.page_count", page_count)
                span.set_attribute("doc.character_count", len(full_text))

                parsed = self.parse_text(full_text)
                parsed.page_count = page_count
                return parsed

            except Exception as exc:
                if isinstance(exc, DocumentSecurityError):
                    raise
                raise DocumentParsingError(f"Failed to parse PDF document: {exc}") from exc

    def parse_text(self, text: str) -> ParsedDocument:
        """Segment raw text into structured academic sections."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        title = lines[0] if lines else "Untitled Document"

        # Section segmentation regex patterns
        abstract_match = re.search(
            r"(?:abstract|overview)\b[:\s]*(.*?)(?=(?:1\.?\s+|introduction|methodology|background|$))",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        abstract = abstract_match.group(1).strip() if abstract_match else ""

        methodology_match = re.search(
            r"(?:methodology|methods|training\s+protocol|experimental\s+setup|model\s+architecture)\b[:\s]*(.*?)(?=(?:results|experiments|evaluation|discussion|$))",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        methodology = methodology_match.group(1).strip() if methodology_match else ""

        results_match = re.search(
            r"(?:results|empirical\s+comparison|benchmark\s+results|evaluation)\b[:\s]*(.*?)(?=(?:discussion|conclusion|related\s+work|references|$))",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        results = results_match.group(1).strip() if results_match else ""

        # Extract markdown-like or tabular patterns
        tables = re.findall(r"(?:Table\s+\d+[:\s].*?)(?=\n\n|\Z)", text, re.IGNORECASE | re.DOTALL)

        return ParsedDocument(
            title=title,
            abstract=abstract,
            methodology=methodology,
            results=results,
            raw_text=text,
            page_count=1,
            tables=tables,
        )

