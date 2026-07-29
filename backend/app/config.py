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
    GENERATION_MODEL: str = "gemini-2.0-flash"
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