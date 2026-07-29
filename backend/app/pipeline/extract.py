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