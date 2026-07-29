import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.storage import storage
from app.pipeline.extract import extract_pdf
from app.pipeline.chunking import FixedChunker
from app.pipeline.embed import embed_chunks


async def process_document(document_id: str, db: AsyncSession) -> None:
    async def set_status(status: str, error: str = None):
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
        for chunk, embedding in zip(chunks, embeddings):
            await db.execute(
                text("""
                    INSERT INTO chunks
                        (id, document_id, chunk_index, text, token_count,
                         page_number, char_start, char_end, chunking_strategy, embedding)
                    VALUES
                        (:id, :doc_id, :idx, :text, :tc,
                         :page, :cs, :ce, :strategy, :emb)
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
                    "strategy": chunk.chunking_strategy,
                    "emb": str(embedding),
                },
            )
        await db.commit()

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
        await set_status("failed", str(e))
        raise