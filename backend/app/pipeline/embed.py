import asyncio
import google.generativeai as genai
from app.config import settings
from app.pipeline.chunking import Chunk

genai.configure(api_key=settings.GOOGLE_API_KEY)


async def embed_chunks(chunks: list[Chunk]) -> list[list[float]]:
    texts = [c.text for c in chunks]
    embeddings = []

    for i in range(0, len(texts), settings.EMBED_BATCH_SIZE):
        batch = texts[i: i + settings.EMBED_BATCH_SIZE]
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda b=batch: genai.embed_content(
                model=settings.EMBEDDING_MODEL,
                content=b,
                task_type="retrieval_document",
                output_dimensionality=settings.EMBEDDING_DIMS,
            ),
        )
        embeddings.extend(result["embedding"])

    return embeddings