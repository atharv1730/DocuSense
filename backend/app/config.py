# Single file where all the configurable constants live.

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
    # Auth
    NEXTAUTH_SECRET: str
    
    # Gemini
    GOOGLE_API_KEY: str
    
    # Models
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    EMBEDDING_DIMS: int = 768
    # gemini-2.0-flash was deprecated 2026-03-03 (zero free-tier quota).
    # The whole gemini-2.5-* line is now restricted to accounts that used
    # it before this cutoff; new projects get a 404. Google's guidance for
    # new projects is gemini-3.1-flash-lite or gemini-3.5-flash.
    GENERATION_MODEL: str = "gemini-3.1-flash-lite"
    CROSS_ENCODER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    # Chunking
    CHUNK_SIZE_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 64
    SEMANTIC_MAX_TOKENS: int = 512
    SEMANTIC_HEADING_SIZE_MULTIPLIER: float = 1.2
    SEMANTIC_MIN_FONT_SIZE: float = 6.0
    # Headings like "8.", "Section 2", "Problem 3" are visually distinct
    # even when printed at body-text size (common in exam-style PDFs),
    # so they're detected by pattern instead of relying on font size alone.
    SEMANTIC_HEADING_NUMBERING_MAX_CHARS: int = 80
    
    # Retrieval
    RETRIEVE_K: int = 20
    RERANK_N: int = 5
    EMBED_BATCH_SIZE: int = 64
    MAX_UPLOAD_MB: int = 50

    # Document comparison
    COMPARE_TITLE_MATCH_THRESHOLD: float = 0.6
    COMPARE_EMBEDDING_MATCH_THRESHOLD: float = 0.75
    COMPARE_SECTION_PREVIEW_CHARS: int = 300
    
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()