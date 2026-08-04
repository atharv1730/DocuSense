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
    
    # Retrieval
    RETRIEVE_K: int = 20
    RERANK_N: int = 5
    EMBED_BATCH_SIZE: int = 64
    MAX_UPLOAD_MB: int = 50
    
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()