import uuid
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.storage import storage
from app.pipeline.extract import extract_pdf, extract_pdf_blocks
from app.pipeline.chunking import Chunk, FixedChunker, SemanticChunker
from app.pipeline.embed import embed_chunks


def _clean_error_message(e: Exception) -> str:
    """DBAPIError's default str() includes the failing SQL statement and
    every bound parameter (which, for a chunk insert, means dumping raw
    embedding vectors) -- not something to show a user. Fall back to just
    the driver's own error message in that case.
    """
    if isinstance(e, DBAPIError) and e.orig is not None:
        return str(e.orig)
    return str(e)


async def _insert_chunks(db: AsyncSession, document_id: str, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
    for chunk, embedding in zip(chunks, embeddings):
        await db.execute(
            text("""
                INSERT INTO chunks
                    (id, document_id, chunk_index, text, token_count,
                     page_number, char_start, char_end, section_title,
                     chunking_strategy, embedding)
                VALUES
                    (:id, :doc_id, :idx, :text, :tc,
                     :page, :cs, :ce, :section_title, :strategy, :emb)
            """),
            {
                "id": str(uuid.uuid4()),
                "doc_id": document_id,
                "idx": chunk.chunk_index,
                "text": chunk.text,
                "tc": chunk.token_count,
                "page": chunk.page_number,
                "cs": chunk.char_start,
                "ce": chunk.char_end,
                "section_title": chunk.section_title,
                "strategy": chunk.chunking_strategy,
                "emb": str(embedding),
            },
        )
    await db.commit()


async def process_document(document_id: str, db: AsyncSession) -> None:
    async def set_status(status: str, error: str = None):
        # A prior statement in this session may have failed and left the
        # transaction aborted (Postgres refuses any further commands until
        # it's rolled back); without this, the "failed" status update below
        # would itself raise and the document would be stuck showing its
        # last in-progress status forever.
        await db.rollback()
        await db.execute(
            text("UPDATE documents SET status = :s, error_message = :e, updated_at = now() WHERE id = :id"),
            {"s": status, "e": error, "id": document_id},
        )
        await db.commit()

    try:
        # Get document record
        result = await db.execute(
            text("SELECT storage_path FROM documents WHERE id = :id"),
            {"id": document_id},
        )
        row = result.mappings().one()
        storage_path = row["storage_path"]

        # Extract
        await set_status("extracting")
        with storage.open(storage_path) as f:
            extract_result = extract_pdf(f)

        await db.execute(
            text("UPDATE documents SET page_count = :pc, updated_at = now() WHERE id = :id"),
            {"pc": extract_result.page_count, "id": document_id},
        )
        await db.commit()

        # Chunk
        await set_status("chunking")
        chunker = FixedChunker()
        chunks = chunker.chunk(extract_result.full_text, extract_result.page_spans)

        # Embed
        await set_status("embedding")
        embeddings = await embed_chunks(chunks)

        # Store chunks
        await _insert_chunks(db, document_id, chunks, embeddings)

        # Update chunking_strategies array and set ready
        await db.execute(
            text("""
                UPDATE documents
                SET status = 'ready',
                    chunking_strategies = array_append(chunking_strategies, 'fixed'),
                    updated_at = now()
                WHERE id = :id
            """),
            {"id": document_id},
        )
        await db.commit()

    except Exception as e:
        await set_status("failed", _clean_error_message(e))
        raise


async def run_semantic_chunking(document_id: str, db: AsyncSession) -> None:
    """Runs the semantic (structure-aware) chunking strategy against a
    document that has already been through fixed chunking, adding a
    second, independent chunk set. Re-extracts the PDF using block-level
    (font-size-aware) extraction, since fixed chunking only kept plain text.
    """
    async def set_status(status: str, error: str = None):
        await db.rollback()
        await db.execute(
            text("UPDATE documents SET status = :s, error_message = :e, updated_at = now() WHERE id = :id"),
            {"s": status, "e": error, "id": document_id},
        )
        await db.commit()

    try:
        result = await db.execute(
            text("SELECT storage_path, chunking_strategies FROM documents WHERE id = :id"),
            {"id": document_id},
        )
        row = result.mappings().one()
        storage_path = row["storage_path"]

        if "semantic" in (row["chunking_strategies"] or []):
            # Already run; nothing to do (defensive, router should also check).
            await set_status("ready")
            return

        await set_status("chunking")
        with storage.open(storage_path) as f:
            extract_result = extract_pdf_blocks(f)

        chunker = SemanticChunker()
        chunks = chunker.chunk(
            extract_result.full_text,
            extract_result.page_spans,
            blocks=extract_result.blocks,
        )

        await set_status("embedding")
        embeddings = await embed_chunks(chunks)

        await _insert_chunks(db, document_id, chunks, embeddings)

        await db.execute(
            text("""
                UPDATE documents
                SET status = 'ready',
                    chunking_strategies = array_append(chunking_strategies, 'semantic'),
                    updated_at = now()
                WHERE id = :id
            """),
            {"id": document_id},
        )
        await db.commit()

    except Exception as e:
        await set_status("failed", _clean_error_message(e))
        raise