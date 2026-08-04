"""
Answer generation: builds a grounded prompt from retrieved chunks,
streams tokens from Gemini, and parses [N] citation markers back to
chunk metadata once the stream completes.
"""

import asyncio
import re
import time
import google.generativeai as genai
from app.config import settings

genai.configure(api_key=settings.GOOGLE_API_KEY)

SYSTEM_PROMPT = """You are DocuSense, an assistant that answers questions using ONLY the context excerpts provided below, which come from the user's own documents.

Rules:
- Answer strictly from the context. Do not use outside knowledge or make assumptions beyond what is written.
- Cite every factual claim with the bracketed source number(s) it came from, e.g. [1] or [1][3].
- The context may contain excerpts from multiple different documents. When answering from multiple documents, clearly attribute each fact to its source using [N] citations. If documents contain conflicting information, explicitly note the conflict and cite both sources.
- If the context does not contain enough information to answer the question, respond with EXACTLY this and nothing else:
  ABSTAIN: I could not find an answer to this question in the provided documents.
- Be concise and precise. Do not repeat the context verbatim; synthesize it."""

CITATION_RE = re.compile(r"\[(\d+)\]")


def build_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, start=1):
        parts.append(f"[{i}] ({chunk['filename']}, p.{chunk['page_number']})\n{chunk['text']}")
    return "\n\n".join(parts)


def parse_citations(answer: str, chunks: list[dict]) -> list[dict]:
    seen: dict[int, dict] = {}
    for match in CITATION_RE.finditer(answer):
        idx = int(match.group(1))
        if idx in seen or idx < 1 or idx > len(chunks):
            continue
        chunk = chunks[idx - 1]
        seen[idx] = {
            "index": idx,
            "filename": chunk["filename"],
            "page_number": chunk["page_number"],
            "text": chunk["text"][:300],
        }
    return [seen[i] for i in sorted(seen)]


async def generate_answer_stream(query: str, chunks: list[dict]):
    """Async generator yielding {"type": "token", ...} then a final
    {"type": "done", ...} event once the model finishes streaming."""
    start = time.perf_counter()
    context = build_context(chunks)
    prompt = f"{SYSTEM_PROMPT}\n\nContext:\n{context}\n\nQuestion: {query}\n\nAnswer:"

    model = genai.GenerativeModel(settings.GENERATION_MODEL)

    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    SENTINEL = object()

    def _run_stream():
        try:
            response = model.generate_content(prompt, stream=True)
            for part in response:
                piece = getattr(part, "text", None)
                if piece:
                    loop.call_soon_threadsafe(queue.put_nowait, piece)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller below
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, SENTINEL)

    # generate_content(stream=True) is synchronous/blocking; run it on a
    # worker thread so tokens can be pushed to the queue as they arrive.
    loop.run_in_executor(None, _run_stream)

    full_text = ""
    while True:
        item = await queue.get()
        if item is SENTINEL:
            break
        if isinstance(item, Exception):
            raise item
        full_text += item
        yield {"type": "token", "text": item}

    abstained = full_text.strip().startswith("ABSTAIN")
    citations = [] if abstained else parse_citations(full_text, chunks)
    latency_ms_generate = int((time.perf_counter() - start) * 1000)

    yield {
        "type": "done",
        "answer": full_text,
        "citations": citations,
        "abstained": abstained,
        "latency_ms_generate": latency_ms_generate,
    }
