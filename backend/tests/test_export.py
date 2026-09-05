import io
import pytest
import docx
from httpx import AsyncClient, ASGITransport
from app.services.export_service import generate_docx, generate_pdf, parse_markdown_blocks
from app.main import app

SAMPLE_ARTICLE = """# The Product Strategy Stack

## Hook
Most product teams confuse roadmap items with actual strategy. This creates endless feature ship loops with zero compounding growth.

## Problem
Teams spend quarters building what users request without understanding the foundational mission, vision, and strategic moats.

## Insight
Ravi Mehta introduced the Product Strategy Stack to cleanly separate mission, company strategy, product strategy, roadmap, and goals.

## Lesson
Never build a roadmap feature without tracing its line of sight up to the product strategy and company mission.

## Application
At Tinder and Facebook, implementing this hierarchy reduced wasted sprint cycles by over 40%.

## Action Steps
1. Define your 3-year product vision in one sentence.
2. Identify the top 2 strategic pillars.
3. Review current roadmap items against pillars.

## Conclusion
Strategy is not a list of features; it is the coherent set of choices that enables durable advantage.

## Sources
- **Ravi Mehta** — *"How to build your product strategy stack | Ravi Mehta"* (Lenny's Podcast)
"""


def test_parse_markdown_blocks():
    blocks = parse_markdown_blocks(SAMPLE_ARTICLE)
    block_types = [b[0] for b in blocks]
    assert "title" in block_types
    assert "h2" in block_types
    assert "paragraph" in block_types
    assert "number" in block_types or "bullet" in block_types


def test_generate_docx_validity():
    docx_bytes = generate_docx(SAMPLE_ARTICLE, "Product Strategy Stack")
    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 1000

    # Parse with python-docx to ensure it is valid
    doc = docx.Document(io.BytesIO(docx_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text]
    assert any("Product Strategy Stack" in p for p in paragraphs)
    assert any("Hook" in p for p in paragraphs)
    assert any("Sources" in p for p in paragraphs)


def test_generate_pdf_validity():
    pdf_bytes = generate_pdf(SAMPLE_ARTICLE, "Product Strategy Stack")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_api_export_docx_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/export/docx",
            json={"markdown": SAMPLE_ARTICLE, "title": "Product Strategy Stack"}
        )
        assert response.status_code == 200
        assert "wordprocessingml" in response.headers["content-type"]
        assert "product-strategy-stack.docx" in response.headers.get("content-disposition", "")
        assert len(response.content) > 1000


@pytest.mark.asyncio
async def test_api_export_pdf_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/export/pdf",
            json={"markdown": SAMPLE_ARTICLE, "title": "Product Strategy Stack"}
        )
        assert response.status_code == 200
        assert "application/pdf" in response.headers["content-type"]
        assert "product-strategy-stack.pdf" in response.headers.get("content-disposition", "")
        assert len(response.content) > 1000

