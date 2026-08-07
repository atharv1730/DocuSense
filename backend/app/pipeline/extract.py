import re
import fitz  # PyMuPDF
from dataclasses import dataclass
from typing import BinaryIO
from app.config import settings

# Matches a numbered/lettered/keyword heading marker at the start of a
# line, e.g. "8.", "12)", "(3)", "b.", "Section 2", "Problem 7", "Q3".
# Anchored at the start so it doesn't match numbers appearing mid-sentence.
HEADING_NUMBERING_RE = re.compile(
    r"^(?:"
    r"\d{1,3}[\.\)]"
    r"|\(\d{1,3}\)"
    r"|[A-Za-z][\.\)]"
    r"|Section\s+\d+"
    r"|Chapter\s+\d+"
    r"|Part\s+\d+"
    r"|Problem\s+\d+"
    r"|Question\s+\d+"
    r"|Article\s+\d+"
    r"|Q\d+"
    r")(?:\s|$)",
    re.IGNORECASE,
)


def _sanitize_text(text: str) -> str:
    """Strips NUL bytes and other invalid characters that some PDFs embed
    in their text streams. Postgres' text/varchar columns reject NUL
    bytes outright (CharacterNotInRepertoireError), which otherwise
    aborts the whole insert transaction partway through processing.
    """
    return text.replace("\x00", "")


@dataclass
class PageSpan:
    page_number: int
    char_start: int
    char_end: int


@dataclass
class ExtractResult:
    full_text: str
    page_spans: list[PageSpan]
    page_count: int


def extract_pdf(file: BinaryIO) -> ExtractResult:
    data = file.read()
    doc = fitz.open(stream=data, filetype="pdf")

    full_text = ""
    page_spans = []

    for page_num, page in enumerate(doc, start=1):
        page_text = _sanitize_text(page.get_text())
        char_start = len(full_text)
        full_text += page_text
        char_end = len(full_text)
        page_spans.append(PageSpan(
            page_number=page_num,
            char_start=char_start,
            char_end=char_end,
        ))

    page_count = len(doc)
    doc.close()
    return ExtractResult(
        full_text=full_text,
        page_spans=page_spans,
        page_count=page_count,
    )


def char_offset_to_page(char_offset: int, page_spans: list[PageSpan]) -> int:
    for span in page_spans:
        if span.char_start <= char_offset < span.char_end:
            return span.page_number
    return page_spans[-1].page_number if page_spans else 1


@dataclass
class TextBlock:
    """A single block of text (roughly a paragraph or heading) with its
    dominant font size, as reported by PyMuPDF's dict-mode extraction.
    Used by SemanticChunker to detect headings and section boundaries.
    """
    text: str
    font_size: float
    page_number: int
    char_start: int
    char_end: int


@dataclass
class BlockExtractResult:
    full_text: str
    page_spans: list[PageSpan]
    blocks: list[TextBlock]
    page_count: int


def extract_pdf_blocks(file: BinaryIO) -> BlockExtractResult:
    """Block-level extraction with font size metadata, for semantic
    chunking. Builds full_text by joining block text with blank lines so
    that paragraph boundaries (double newlines) are well defined for the
    semantic chunker's oversized-section splitting.
    """
    data = file.read()
    doc = fitz.open(stream=data, filetype="pdf")

    full_text = ""
    page_spans = []
    blocks: list[TextBlock] = []

    for page_num, page in enumerate(doc, start=1):
        page_char_start = len(full_text)
        page_dict = page.get_text("dict")

        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue  # skip images/non-text blocks

            lines_info: list[tuple[str, float]] = []
            for line in block.get("lines", []):
                line_text = ""
                sizes = []
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    if not span_text:
                        continue
                    line_text += span_text
                    sizes.append(span.get("size", 0.0))
                if line_text.strip():
                    lines_info.append((line_text, max(sizes) if sizes else 0.0))

            if not lines_info:
                continue

            # A numbered/lettered heading that starts a paragraph (e.g.
            # "8. Determine whether...") is visually a heading even though
            # PyMuPDF groups it with its body text as a single block, and
            # even when it shares the body's font size. Split it into its
            # own block so downstream heading detection can treat it as a
            # section boundary.
            first_text, _ = lines_info[0]
            splits_off_heading = (
                len(lines_info) > 1
                and len(first_text.strip()) <= settings.SEMANTIC_HEADING_NUMBERING_MAX_CHARS
                and HEADING_NUMBERING_RE.match(first_text.strip())
            )
            groups = [[lines_info[0]], lines_info[1:]] if splits_off_heading else [lines_info]

            for group in groups:
                group_text = _sanitize_text("\n".join(t for t, _ in group).strip())
                group_sizes = [s for _, s in group]
                if not group_text or not group_sizes:
                    continue

                font_size = max(group_sizes)
                char_start = len(full_text)
                full_text += group_text + "\n\n"
                char_end = len(full_text)

                blocks.append(TextBlock(
                    text=group_text,
                    font_size=font_size,
                    page_number=page_num,
                    char_start=char_start,
                    char_end=char_end,
                ))

        page_char_end = len(full_text)
        page_spans.append(PageSpan(
            page_number=page_num,
            char_start=page_char_start,
            char_end=page_char_end,
        ))

    page_count = len(doc)
    doc.close()
    return BlockExtractResult(
        full_text=full_text,
        page_spans=page_spans,
        blocks=blocks,
        page_count=page_count,
    )