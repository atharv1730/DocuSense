from collections import Counter
from dataclasses import dataclass
from typing import Protocol
import tiktoken
from app.pipeline.extract import PageSpan, TextBlock, char_offset_to_page
from app.config import settings


@dataclass
class Chunk:
    text: str
    chunk_index: int
    page_number: int
    char_start: int
    char_end: int
    token_count: int
    chunking_strategy: str
    section_title: str | None = None


class Chunker(Protocol):
    def chunk(self, text: str, page_spans: list[PageSpan]) -> list[Chunk]: ...


class FixedChunker:
    def __init__(
        self,
        chunk_size: int = None,
        overlap: int = None,
    ):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE_TOKENS
        self.overlap = overlap or settings.CHUNK_OVERLAP_TOKENS
        self.enc = tiktoken.get_encoding("cl100k_base")

    def chunk(self, text: str, page_spans: list[PageSpan]) -> list[Chunk]:
        tokens = self.enc.encode(text)
        chunks = []
        start = 0
        index = 0

        while start < len(tokens):
            end = min(start + self.chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.enc.decode(chunk_tokens)

            # Find char offset of this chunk in the original text
            char_start = len(self.enc.decode(tokens[:start]))
            char_end = char_start + len(chunk_text)

            page_number = char_offset_to_page(char_start, page_spans)

            chunks.append(Chunk(
                text=chunk_text,
                chunk_index=index,
                page_number=page_number,
                char_start=char_start,
                char_end=char_end,
                token_count=len(chunk_tokens),
                chunking_strategy="fixed",
            ))

            index += 1
            start += self.chunk_size - self.overlap

        return chunks


@dataclass
class _Section:
    title: str | None
    text: str
    char_start: int
    char_end: int


def _modal_font_size(blocks: list[TextBlock], min_size: float) -> float | None:
    sizes = [round(b.font_size, 1) for b in blocks if b.font_size >= min_size]
    if not sizes:
        return None
    return Counter(sizes).most_common(1)[0][0]


class SemanticChunker:
    """Splits on document structure (headings, paragraphs) instead of
    fixed token windows. Requires block-level text with font size
    metadata (see app.pipeline.extract.extract_pdf_blocks), grouped by
    page, so it does not use the plain `Chunker` protocol's page_spans
    alone -- callers must pass `blocks` explicitly.
    """

    def __init__(self, max_tokens: int = None, heading_multiplier: float = None, min_font_size: float = None):
        self.max_tokens = max_tokens or settings.SEMANTIC_MAX_TOKENS
        self.heading_multiplier = heading_multiplier or settings.SEMANTIC_HEADING_SIZE_MULTIPLIER
        self.min_font_size = min_font_size if min_font_size is not None else settings.SEMANTIC_MIN_FONT_SIZE
        self.enc = tiktoken.get_encoding("cl100k_base")

    def _detect_headings(self, blocks: list[TextBlock]) -> set[int]:
        """Returns the set of block indices considered heading candidates,
        comparing each block's font size to the modal size of its own page.
        """
        by_page: dict[int, list[TextBlock]] = {}
        for b in blocks:
            by_page.setdefault(b.page_number, []).append(b)

        modal_by_page = {
            page: _modal_font_size(page_blocks, self.min_font_size)
            for page, page_blocks in by_page.items()
        }

        heading_indices = set()
        for i, b in enumerate(blocks):
            modal = modal_by_page.get(b.page_number)
            if modal is None or b.font_size < self.min_font_size:
                continue
            # Single-line blocks that are meaningfully larger than the
            # page's body text are heading candidates. Multi-line blocks
            # are almost never headings even if bumped in size.
            is_short = len(b.text) <= 200 and "\n" not in b.text.strip()
            if is_short and b.font_size >= modal * self.heading_multiplier:
                heading_indices.add(i)
        return heading_indices

    def _build_sections(self, blocks: list[TextBlock]) -> list[_Section]:
        if not blocks:
            return []

        heading_indices = self._detect_headings(blocks)

        sections: list[_Section] = []
        current_title: str | None = None
        current_parts: list[str] = []
        current_start: int | None = None
        current_end: int | None = None

        def flush():
            if current_parts:
                sections.append(_Section(
                    title=current_title,
                    text="\n\n".join(current_parts).strip(),
                    char_start=current_start,
                    char_end=current_end,
                ))

        for i, b in enumerate(blocks):
            if i in heading_indices:
                flush()
                current_title = b.text.strip()
                current_parts = []
                current_start = b.char_start
                current_end = b.char_end
            else:
                if current_start is None:
                    current_start = b.char_start
                current_parts.append(b.text)
                current_end = b.char_end

        flush()
        return [s for s in sections if s.text]

    def _split_oversized(self, section: _Section, page_spans: list[PageSpan]) -> list[tuple[str, int, int]]:
        """Greedily splits a section's text at paragraph boundaries
        (double newlines) to keep each piece under max_tokens. Returns
        list of (text, char_start, char_end) relative to full_text offsets,
        approximated by walking through the section's paragraphs in order.
        """
        paragraphs = section.text.split("\n\n")
        pieces: list[tuple[str, int, int]] = []

        cursor = section.char_start
        current_text_parts: list[str] = []
        current_tokens = 0
        piece_start = cursor

        def token_len(s: str) -> int:
            return len(self.enc.encode(s))

        for para in paragraphs:
            para_tokens = token_len(para)
            if current_text_parts and current_tokens + para_tokens > self.max_tokens:
                joined = "\n\n".join(current_text_parts)
                pieces.append((joined, piece_start, piece_start + len(joined)))
                cursor = piece_start + len(joined) + 2
                piece_start = cursor
                current_text_parts = []
                current_tokens = 0

            current_text_parts.append(para)
            current_tokens += para_tokens
            cursor += len(para) + 2

        if current_text_parts:
            joined = "\n\n".join(current_text_parts)
            pieces.append((joined, piece_start, piece_start + len(joined)))

        return pieces if pieces else [(section.text, section.char_start, section.char_end)]

    def chunk(self, text: str, page_spans: list[PageSpan], blocks: list[TextBlock] | None = None) -> list[Chunk]:
        """`text` and `page_spans` should come from the same block-level
        extraction pass that produced `blocks` (see extract_pdf_blocks),
        so char offsets line up. `blocks` is required for real use; it's
        keyword-optional only so the signature stays compatible with the
        generic Chunker protocol.
        """
        if not blocks:
            return []

        sections = self._build_sections(blocks)
        chunks: list[Chunk] = []
        index = 0

        for section in sections:
            token_count = len(self.enc.encode(section.text))
            if token_count <= self.max_tokens:
                pieces = [(section.text, section.char_start, section.char_end)]
            else:
                pieces = self._split_oversized(section, page_spans)

            for piece_text, char_start, char_end in pieces:
                if not piece_text.strip():
                    continue
                page_number = char_offset_to_page(char_start, page_spans)
                chunks.append(Chunk(
                    text=piece_text,
                    chunk_index=index,
                    page_number=page_number,
                    char_start=char_start,
                    char_end=char_end,
                    token_count=len(self.enc.encode(piece_text)),
                    chunking_strategy="semantic",
                    section_title=section.title,
                ))
                index += 1

        return chunks