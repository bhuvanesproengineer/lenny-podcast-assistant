import io
import re
from typing import List, Tuple, Optional
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    KeepTogether,
)
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and display total page count."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count: int):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#64748B"))
        # Top rule and text
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(612 - 54, 36, page_text)
        self.drawString(54, 36, "Lenny's Growth Assistant · Ship30 Article")
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(54, 48, 612 - 54, 48)
        self.restoreState()


def parse_markdown_blocks(markdown_text: str) -> List[Tuple[str, str]]:
    """
    Parses a markdown string into a list of (block_type, content) tuples.
    Types: 'title' (H1), 'h2', 'h3', 'bullet', 'number', 'paragraph', 'quote'.
    """
    lines = markdown_text.strip().split("\n")
    blocks: List[Tuple[str, str]] = []
    current_paragraph: List[str] = []

    def flush_paragraph():
        if current_paragraph:
            text = " ".join(current_paragraph).strip()
            if text:
                blocks.append(("paragraph", text))
            current_paragraph.clear()

    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            flush_paragraph()
            continue

        if trimmed.startswith("# "):
            flush_paragraph()
            blocks.append(("title", trimmed[2:].strip()))
        elif trimmed.startswith("## "):
            flush_paragraph()
            blocks.append(("h2", trimmed[3:].strip()))
        elif trimmed.startswith("### "):
            flush_paragraph()
            blocks.append(("h3", trimmed[4:].strip()))
        elif trimmed.startswith("- ") or trimmed.startswith("* "):
            flush_paragraph()
            blocks.append(("bullet", trimmed[2:].strip()))
        elif re.match(r"^\d+\.\s+", trimmed):
            flush_paragraph()
            match = re.match(r"^\d+\.\s+(.*)$", trimmed)
            blocks.append(("number", match.group(1).strip() if match else trimmed))
        elif trimmed.startswith("> "):
            flush_paragraph()
            blocks.append(("quote", trimmed[2:].strip()))
        else:
            current_paragraph.append(trimmed)

    flush_paragraph()
    return blocks


def clean_markdown_inline(text: str) -> str:
    """Removes basic inline markdown syntax (bold/italics/code) for plain-text export."""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


# =============================================================================
# DOCX Generation
# =============================================================================

def generate_docx(markdown_content: str, title: Optional[str] = None) -> bytes:
    """
    Generates a clean, professionally styled Microsoft Word (.docx) document
    from markdown content using python-docx.
    """
    doc = docx.Document()

    # Set page margins to 1 inch
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Base styles
    normal_style = doc.styles["Normal"]
    normal_font = normal_style.font
    normal_font.name = "Calibri"
    normal_font.size = Pt(11)
    normal_font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)  # Slate 800

    blocks = parse_markdown_blocks(markdown_content)

    # If title not provided, extract from first H1 or first block
    doc_title = title
    if not doc_title:
        for b_type, b_text in blocks:
            if b_type == "title":
                doc_title = clean_markdown_inline(b_text)
                break
    if not doc_title:
        doc_title = "Ship30 Growth Article"

    # Add header title
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(0)
    title_p.paragraph_format.space_after = Pt(18)
    title_p.paragraph_format.line_spacing = 1.15
    title_run = title_p.add_run(doc_title)
    title_run.font.name = "Calibri"
    title_run.font.size = Pt(24)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)  # Slate 900

    # Subtitle / attribution
    meta_p = doc.add_paragraph()
    meta_p.paragraph_format.space_after = Pt(20)
    meta_run = meta_p.add_run("Lenny's Growth Assistant · Ship30 for 30 Article")
    meta_run.font.size = Pt(10)
    meta_run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)  # Slate 500
    meta_run.font.italic = True

    # Render blocks
    has_rendered_title = False
    for b_type, b_text in blocks:
        if b_type == "title":
            if not has_rendered_title:
                has_rendered_title = True
                continue  # Already rendered as doc_title

        if b_type == "h2":
            h2_p = doc.add_paragraph()
            h2_p.paragraph_format.space_before = Pt(16)
            h2_p.paragraph_format.space_after = Pt(6)
            h2_p.paragraph_format.keep_with_next = True
            run = h2_p.add_run(clean_markdown_inline(b_text))
            run.font.name = "Calibri"
            run.font.size = Pt(14)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0xD9, 0x77, 0x06)  # Amber 600

        elif b_type == "h3":
            h3_p = doc.add_paragraph()
            h3_p.paragraph_format.space_before = Pt(12)
            h3_p.paragraph_format.space_after = Pt(4)
            h3_p.paragraph_format.keep_with_next = True
            run = h3_p.add_run(clean_markdown_inline(b_text))
            run.font.name = "Calibri"
            run.font.size = Pt(12)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

        elif b_type == "bullet":
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            _add_formatted_runs_docx(p, b_text)

        elif b_type == "number":
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            _add_formatted_runs_docx(p, b_text)

        elif b_type == "quote":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.4)
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(clean_markdown_inline(b_text))
            run.font.italic = True
            run.font.color.rgb = RGBColor(0x47, 0x55, 0x69)

        else:  # paragraph
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(8)
            p.paragraph_format.line_spacing = 1.2
            _add_formatted_runs_docx(p, b_text)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _add_formatted_runs_docx(paragraph, text: str):
    """Parses basic inline bold tags and adds runs to paragraph."""
    parts = re.split(r"(\*\*[^*]+\*\*)", text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.font.bold = True
        else:
            # check italics
            subparts = re.split(r"(\*[^*]+\*)", part)
            for sub in subparts:
                if sub.startswith("*") and sub.endswith("*"):
                    r = paragraph.add_run(sub[1:-1])
                    r.font.italic = True
                else:
                    paragraph.add_run(sub)


# =============================================================================
# PDF Generation
# =============================================================================

def generate_pdf(markdown_content: str, title: Optional[str] = None) -> bytes:
    """
    Generates a high-quality, beautifully formatted PDF from markdown content
    using reportlab.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=60,
    )

    styles = getSampleStyleSheet()

    # Custom ReportLab Paragraph Styles
    title_style = ParagraphStyle(
        "Ship30Title",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
        keepWithNext=True,
    )

    subtitle_style = ParagraphStyle(
        "Ship30Subtitle",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748B"),
        spaceAfter=14,
    )

    h2_style = ParagraphStyle(
        "Ship30H2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#D97706"),  # Amber 600
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True,
    )

    h3_style = ParagraphStyle(
        "Ship30H3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "Ship30Body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14.5,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=7,
    )

    bullet_style = ParagraphStyle(
        "Ship30Bullet",
        parent=body_style,
        leftIndent=16,
        firstLineIndent=-10,
        spaceAfter=3,
    )

    quote_style = ParagraphStyle(
        "Ship30Quote",
        parent=body_style,
        fontName="Helvetica-Oblique",
        leftIndent=20,
        textColor=colors.HexColor("#475569"),
        spaceBefore=4,
        spaceAfter=6,
    )

    blocks = parse_markdown_blocks(markdown_content)

    doc_title = title
    if not doc_title:
        for b_type, b_text in blocks:
            if b_type == "title":
                doc_title = clean_markdown_inline(b_text)
                break
    if not doc_title:
        doc_title = "Ship30 Growth Article"

    story = []

    # Title & subtitle
    story.append(Paragraph(_escape_xml(doc_title), title_style))
    story.append(Paragraph("Lenny's Growth Assistant · Ship30 for 30 Article", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#E2E8F0"), spaceAfter=14))

    has_rendered_title = False
    for b_type, b_text in blocks:
        if b_type == "title":
            if not has_rendered_title:
                has_rendered_title = True
                continue

        if b_type == "h2":
            story.append(Spacer(1, 4))
            story.append(Paragraph(_format_markdown_for_reportlab(b_text), h2_style))

        elif b_type == "h3":
            story.append(Paragraph(_format_markdown_for_reportlab(b_text), h3_style))

        elif b_type == "bullet":
            bullet_html = f"&bull; {_format_markdown_for_reportlab(b_text)}"
            story.append(Paragraph(bullet_html, bullet_style))

        elif b_type == "number":
            number_html = f"&bull; {_format_markdown_for_reportlab(b_text)}"
            story.append(Paragraph(number_html, bullet_style))

        elif b_type == "quote":
            story.append(Paragraph(_format_markdown_for_reportlab(b_text), quote_style))

        else:  # paragraph
            story.append(Paragraph(_format_markdown_for_reportlab(b_text), body_style))

    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()


def _escape_xml(text: str) -> str:
    """Escapes XML entities for ReportLab paragraphs."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_markdown_for_reportlab(text: str) -> str:
    """Converts basic markdown inline bold and italics to ReportLab XML tags (<b>, <i>)."""
    escaped = _escape_xml(text)
    # Convert **bold** to <b>bold</b>
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    # Convert *italic* to <i>italic</i>
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped)
    return escaped
