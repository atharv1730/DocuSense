"""
Section-aligned document comparison.

Full-document prompting breaks down on long PDFs (context limits, cost,
and the model losing track of which clause is which). Instead this
pipeline:

  1. Groups each document's semantic chunks into sections, keyed by the
     heading detected during semantic chunking (`extract_section_outline`).
  2. Aligns sections across the two documents by title similarity, falling
     back to embedding similarity when titles diverge (`align_sections`).
  3. Runs one small, targeted LLM call per aligned section pair to surface
     concrete differences, instead of one call over the whole document
     (`compare_section_pair`).

`compare_documents` wires the three steps together into a ComparisonResult.
"""

import asyncio
import difflib
import json
import numpy as np
import google.generativeai as genai
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings
from app.schemas.compare import ComparisonResult, DocumentRef, AlignedSection, SectionSummary

genai.configure(api_key=settings.GOOGLE_API_KEY)

UNTITLED_SECTION = "Untitled sections"

COMPARE_PROMPT_TEMPLATE = """Compare these two sections, which come from two versions of a document, or two related documents.

List:
- differences: specific factual or textual differences between the sections
- changed_clauses: specific clauses or sentences whose terms/meaning changed (quote or closely paraphrase both versions)

Cite page numbers whenever you reference a specific piece of text. Be specific and concise.
If the two sections are substantively identical (same meaning, no material changes), set "identical" to true and leave "differences" and "changed_clauses" empty.

Section A ({title_a}, page {page_a}):
{text_a}

Section B ({title_b}, page {page_b}):
{text_b}

Respond as JSON with exactly this shape, and nothing else:
{{"identical": boolean, "differences": [string], "changed_clauses": [string]}}
"""


class NoSemanticChunksError(Exception):
    """Raised when a document has no semantic chunks yet, which are
    required to build a section outline for comparison."""


def _parse_embedding(raw: str) -> np.ndarray:
    return np.array([float(x) for x in raw.strip("[]").split(",")], dtype=float)


def _title_similarity(title_a: str | None, title_b: str | None) -> float:
    return difflib.SequenceMatcher(None, (title_a or "").lower(), (title_b or "").lower()).ratio()


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


async def extract_section_outline(document_id: str, db: AsyncSession) -> list[dict]:
    """Groups this document's semantic chunks into sections by
    section_title, preserving document order. Raises NoSemanticChunksError
    if semantic chunking hasn't been run for this document.

    Each returned dict has: section_title, page_number, chunk_ids,
    text (full joined section text, used for the LLM comparison call),
    text_preview (truncated, for display), and embedding (the section's
    chunks' embeddings averaged into a single vector, used for the
    embedding-similarity alignment fallback).
    """
    result = await db.execute(
        text("""
            SELECT id, text, page_number, section_title, chunk_index,
                   embedding::text AS embedding
            FROM chunks
            WHERE document_id = :doc_id AND chunking_strategy = 'semantic'
            ORDER BY chunk_index
        """),
        {"doc_id": document_id},
    )
    rows = [dict(r) for r in result.mappings().all()]

    if not rows:
        raise NoSemanticChunksError(
            f"Document {document_id} has no semantic chunks. Run semantic chunking first."
        )

    sections: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        title = row["section_title"] or UNTITLED_SECTION
        if title not in sections:
            sections[title] = {
                "section_title": title,
                "page_number": row["page_number"],
                "chunk_ids": [],
                "texts": [],
                "embeddings": [],
            }
            order.append(title)
        section = sections[title]
        section["chunk_ids"].append(str(row["id"]))
        section["texts"].append(row["text"])
        section["embeddings"].append(_parse_embedding(row["embedding"]))

    outline = []
    for title in order:
        section = sections[title]
        full_text = "\n\n".join(section["texts"])
        outline.append({
            "section_title": section["section_title"],
            "page_number": section["page_number"],
            "chunk_ids": section["chunk_ids"],
            "text": full_text,
            "text_preview": full_text[: settings.COMPARE_SECTION_PREVIEW_CHARS],
            "embedding": np.mean(section["embeddings"], axis=0),
        })
    return outline


def align_sections(outline_a: list[dict], outline_b: list[dict]) -> dict:
    """Greedily matches each section in A to the best available section in
    B: first by fuzzy title match, falling back to embedding similarity
    when titles are too different. Each B section is used at most once.

    Returns {"aligned": [{section_a, section_b, match_type, similarity}],
             "unmatched_a": [...], "unmatched_b": [...]}.
    """
    available_b = list(range(len(outline_b)))
    aligned: list[dict] = []
    unmatched_a: list[dict] = []

    for sec_a in outline_a:
        if not available_b:
            unmatched_a.append(sec_a)
            continue

        title_scores = [
            (idx, _title_similarity(sec_a["section_title"], outline_b[idx]["section_title"]))
            for idx in available_b
        ]
        best_idx, best_score = max(title_scores, key=lambda t: t[1])

        if best_score >= settings.COMPARE_TITLE_MATCH_THRESHOLD:
            match_type, similarity = "title", best_score
        else:
            embed_scores = [
                (idx, _cosine_similarity(sec_a["embedding"], outline_b[idx]["embedding"]))
                for idx in available_b
            ]
            best_idx, best_score = max(embed_scores, key=lambda t: t[1])
            if best_score >= settings.COMPARE_EMBEDDING_MATCH_THRESHOLD:
                match_type, similarity = "embedding", best_score
            else:
                unmatched_a.append(sec_a)
                continue

        aligned.append({
            "section_a": sec_a,
            "section_b": outline_b[best_idx],
            "match_type": match_type,
            "similarity": similarity,
        })
        available_b.remove(best_idx)

    unmatched_b = [outline_b[idx] for idx in available_b]
    return {"aligned": aligned, "unmatched_a": unmatched_a, "unmatched_b": unmatched_b}


async def compare_section_pair(section_a: dict, section_b: dict, query: str | None = None) -> dict:
    """Single LLM call comparing two section texts. `query` is an optional
    extra instruction appended to the prompt (e.g. to focus the comparison
    on a specific concern); it is unused by the default full-document
    comparison flow.

    Returns {differences, changed_clauses, identical, citations_a, citations_b}.
    """
    # Exact-text sections never need a model call, and let self-comparisons
    # (or truly unchanged sections) resolve instantly instead of burning
    # an LLM call per pair.
    if section_a["text"].strip() == section_b["text"].strip():
        return {
            "differences": [],
            "changed_clauses": [],
            "identical": True,
            "citations_a": [{"page": section_a["page_number"]}],
            "citations_b": [{"page": section_b["page_number"]}],
        }

    prompt = COMPARE_PROMPT_TEMPLATE.format(
        title_a=section_a["section_title"],
        page_a=section_a["page_number"],
        text_a=section_a["text"],
        title_b=section_b["section_title"],
        page_b=section_b["page_number"],
        text_b=section_b["text"],
    )
    if query:
        prompt += f"\nAdditional focus for this comparison: {query}\n"

    model = genai.GenerativeModel(settings.GENERATION_MODEL)
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(response_mime_type="application/json"),
        ),
    )

    try:
        parsed = json.loads(response.text)
    except (ValueError, AttributeError, TypeError):
        parsed = {"identical": False, "differences": ["Comparison could not be parsed."], "changed_clauses": []}

    identical = bool(parsed.get("identical", False))
    return {
        "differences": [] if identical else list(parsed.get("differences") or []),
        "changed_clauses": [] if identical else list(parsed.get("changed_clauses") or []),
        "identical": identical,
        "citations_a": [{"page": section_a["page_number"]}],
        "citations_b": [{"page": section_b["page_number"]}],
    }


async def compare_documents(doc_id_a: str, doc_id_b: str, db: AsyncSession) -> ComparisonResult:
    """Full comparison pipeline: outline both documents, align their
    sections, run one LLM call per aligned pair, and collect unmatched
    sections as "only in A" / "only in B"."""
    doc_rows = await db.execute(
        text("SELECT id, filename FROM documents WHERE id = ANY(:ids)"),
        {"ids": [doc_id_a, doc_id_b]},
    )
    filenames = {str(r["id"]): r["filename"] for r in doc_rows.mappings().all()}

    outline_a = await extract_section_outline(doc_id_a, db)
    outline_b = await extract_section_outline(doc_id_b, db)

    alignment = align_sections(outline_a, outline_b)

    aligned_sections: list[AlignedSection] = []
    identical_count = 0
    diff_count = 0

    for pair in alignment["aligned"]:
        sec_a, sec_b = pair["section_a"], pair["section_b"]
        result = await compare_section_pair(sec_a, sec_b)

        if result["identical"]:
            identical_count += 1
        else:
            diff_count += 1

        title = sec_a["section_title"]
        if sec_a["section_title"] != sec_b["section_title"]:
            title = f'{sec_a["section_title"]} / {sec_b["section_title"]}'

        aligned_sections.append(AlignedSection(
            section_title=title,
            identical=result["identical"],
            differences=result["differences"],
            changed_clauses=result["changed_clauses"],
            match_type=pair["match_type"],
            similarity=pair["similarity"],
            page_a=sec_a["page_number"],
            page_b=sec_b["page_number"],
        ))

    only_in_a = [
        SectionSummary(section_title=s["section_title"], page_number=s["page_number"])
        for s in alignment["unmatched_a"]
    ]
    only_in_b = [
        SectionSummary(section_title=s["section_title"], page_number=s["page_number"])
        for s in alignment["unmatched_b"]
    ]

    return ComparisonResult(
        document_a=DocumentRef(id=doc_id_a, filename=filenames.get(doc_id_a, "")),
        document_b=DocumentRef(id=doc_id_b, filename=filenames.get(doc_id_b, "")),
        aligned_sections=aligned_sections,
        only_in_a=only_in_a,
        only_in_b=only_in_b,
        identical_count=identical_count,
        diff_count=diff_count,
    )
