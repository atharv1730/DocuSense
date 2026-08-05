import fitz  # PyMuPDF
from dataclasses import dataclass
from typing import BinaryIO


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
        page_text = page.get_text()
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

            block_text_parts = []
            sizes = []
            for line in block.get("lines", []):
                line_text = ""
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    if not span_text:
                        continue
                    line_text += span_text
                    sizes.append(span.get("size", 0.0))
                if line_text.strip():
                    block_text_parts.append(line_text)

            block_text = "\n".join(block_text_parts).strip()
            if not block_text or not sizes:
                continue

            font_size = max(sizes)
            char_start = len(full_text)
            full_text += block_text + "\n\n"
            char_end = len(full_text)

            blocks.append(TextBlock(
                text=block_text,
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