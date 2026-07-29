from dataclasses import dataclass
from typing import Protocol
import tiktoken
from app.pipeline.extract import PageSpan, char_offset_to_page
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