"""Unit tests for SemanticChunker (Phase 6).

These construct TextBlock lists directly (rather than going through a
real PDF) to simulate the output of app.pipeline.extract.extract_pdf_blocks
with known font sizes, mirroring how a PyMuPDF page dict would be parsed.
"""

import pytest
from app.pipeline.chunking import SemanticChunker
from app.pipeline.extract import PageSpan, TextBlock


def make_blocks_and_text(items: list[tuple[str, float, int]]):
    """items: list of (text, font_size, page_number), in document order.
    Mirrors how extract_pdf_blocks joins block text with blank lines.
    """
    full_text = ""
    blocks = []
    page_ranges: dict[int, list[int]] = {}

    for block_text, font_size, page in items:
        char_start = len(full_text)
        full_text += block_text + "\n\n"
        char_end = len(full_text)
        blocks.append(TextBlock(
            text=block_text,
            font_size=font_size,
            page_number=page,
            char_start=char_start,
            char_end=char_end,
        ))
        if page not in page_ranges:
            page_ranges[page] = [char_start, char_end]
        else:
            page_ranges[page][1] = char_end

    page_spans = [
        PageSpan(page_number=p, char_start=r[0], char_end=r[1])
        for p, r in sorted(page_ranges.items())
    ]
    return full_text, page_spans, blocks


def test_heading_detection():
    items = [
        ("Section One", 18, 1),
        ("This is the first body paragraph of section one.", 12, 1),
        ("This is the second body paragraph of section one.", 12, 1),
    ]
    full_text, page_spans, blocks = make_blocks_and_text(items)

    chunker = SemanticChunker()
    heading_indices = chunker._detect_headings(blocks)

    assert heading_indices == {0}

    chunks = chunker.chunk(full_text, page_spans, blocks=blocks)
    assert len(chunks) == 1
    assert chunks[0].section_title == "Section One"
    assert chunks[0].chunking_strategy == "semantic"
    assert "first body paragraph" in chunks[0].text
    assert "second body paragraph" in chunks[0].text


def test_max_token_cap():
    max_tokens = 50
    body_paragraphs = [
        (f"This is body paragraph number {i} with some extra padding words to add tokens.", 12, 1)
        for i in range(12)
    ]
    items = [("Long Section", 18, 1)] + body_paragraphs
    full_text, page_spans, blocks = make_blocks_and_text(items)

    chunker = SemanticChunker(max_tokens=max_tokens)
    chunks = chunker.chunk(full_text, page_spans, blocks=blocks)

    assert len(chunks) > 1, "oversized section should be split into multiple chunks"
    for c in chunks:
        assert c.token_count <= max_tokens
        assert c.section_title == "Long Section"


def test_section_title_recorded():
    items = [
        ("This paragraph appears before any heading is detected.", 12, 1),
        ("Introduction", 18, 1),
        ("Body text under the introduction heading.", 12, 1),
        ("More body text under the introduction heading.", 12, 1),
        ("Methodology", 18, 2),
        ("Body text under the methodology heading.", 12, 2),
        ("More body text under the methodology heading.", 12, 2),
    ]
    full_text, page_spans, blocks = make_blocks_and_text(items)

    chunker = SemanticChunker()
    chunks = chunker.chunk(full_text, page_spans, blocks=blocks)

    assert len(chunks) == 3

    untitled, intro, methodology = chunks
    assert untitled.section_title is None
    assert "before any heading" in untitled.text

    assert intro.section_title == "Introduction"
    assert intro.page_number == 1

    assert methodology.section_title == "Methodology"
    assert methodology.page_number == 2
