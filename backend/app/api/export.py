import re
import urllib.parse
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.export_service import generate_docx, generate_pdf

router = APIRouter(prefix="/export", tags=["export"])


class ExportRequest(BaseModel):
    markdown: str = Field(..., min_length=1, description="Markdown article content to export")
    title: Optional[str] = Field(None, description="Optional document title for filename and header")


def _sanitize_filename(title: Optional[str], default: str = "ship30-article") -> str:
    if not title:
        return default
    # Clean non-alphanumeric chars
    clean = re.sub(r"[^\w\s-]", "", title).strip()
    clean = re.sub(r"[-\s]+", "-", clean).lower()
    return clean[:60] or default


@router.post("/docx", summary="Export markdown article as a styled DOCX document")
async def export_to_docx(payload: ExportRequest):
    """
    Generates and returns a professionally formatted Microsoft Word document (.docx).
    """
    try:
        docx_bytes = generate_docx(payload.markdown, payload.title)
        filename = f"{_sanitize_filename(payload.title)}.docx"
        ascii_filename = urllib.parse.quote(filename)

        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{ascii_filename}',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate Word document: {str(exc)}"
        )


@router.post("/pdf", summary="Export markdown article as a styled PDF document")
async def export_to_pdf(payload: ExportRequest):
    """
    Generates and returns a publication-ready PDF document (.pdf).
    """
    try:
        pdf_bytes = generate_pdf(payload.markdown, payload.title)
        filename = f"{_sanitize_filename(payload.title)}.pdf"
        ascii_filename = urllib.parse.quote(filename)

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{ascii_filename}',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF document: {str(exc)}"
        )
