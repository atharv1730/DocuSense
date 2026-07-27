# Single file where all the configurable constants live.

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
    # Auth
    NEXTAUTH_SECRET: str
    
    # OpenAI
    OPENAI_API_KEY: str
    
    # Models
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    GENERATION_MODEL: str = "gpt-4.1"
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