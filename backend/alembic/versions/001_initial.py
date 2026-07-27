from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table('users',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(), nullable=False, unique=True),
        sa.Column('name', sa.String()),
        sa.Column('image', sa.String()),
        sa.Column('provider', sa.String()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table('workspaces',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table('documents',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', sa.UUID(), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('storage_path', sa.String()),
        sa.Column('page_count', sa.Integer()),
        sa.Column('size_bytes', sa.BigInteger()),
        sa.Column('status', sa.String(), nullable=False, server_default='uploaded'),
        sa.Column('error_message', sa.Text()),
        sa.Column('chunking_strategies', sa.ARRAY(sa.String()), server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table('chunks',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('document_id', sa.UUID(), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('token_count', sa.Integer()),
        sa.Column('page_number', sa.Integer()),
        sa.Column('char_start', sa.Integer()),
        sa.Column('char_end', sa.Integer()),
        sa.Column('section_title', sa.String()),
        sa.Column('chunking_strategy', sa.String(), nullable=False),
        sa.Column('embedding', Vector(1536)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # HNSW index on embeddings
    op.execute("""
        CREATE INDEX chunks_embedding_hnsw_idx
        ON chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # btree index for filtered retrieval
    op.create_index('chunks_document_strategy_idx', 'chunks', ['document_id', 'chunking_strategy'])

    op.create_table('conversations',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', sa.UUID(), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table('messages',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('conversation_id', sa.UUID(), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('citations', sa.JSON()),
        sa.Column('retrieval_log_id', sa.UUID()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table('retrieval_logs',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', sa.UUID(), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=True),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('chunking_strategy', sa.String()),
        sa.Column('rerank_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('stage1_chunk_ids', sa.ARRAY(sa.UUID())),
        sa.Column('stage2_chunk_ids', sa.ARRAY(sa.UUID())),
        sa.Column('final_chunk_ids', sa.ARRAY(sa.UUID())),
        sa.Column('answer', sa.Text()),
        sa.Column('abstained', sa.Boolean(), server_default='false'),
        sa.Column('latency_ms_stage1', sa.Integer()),
        sa.Column('latency_ms_stage2', sa.Integer()),
        sa.Column('latency_ms_generate', sa.Integer()),
        sa.Column('model', sa.String()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table('chunk_ratings',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('retrieval_log_id', sa.UUID(), sa.ForeignKey('retrieval_logs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_id', sa.UUID(), sa.ForeignKey('chunks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('rating', sa.SmallInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('retrieval_log_id', 'chunk_id', name='uq_rating_log_chunk'),
    )

def downgrade():
    op.drop_table('chunk_ratings')
    op.drop_table('retrieval_logs')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_index('chunks_document_strategy_idx')
    op.drop_index('chunks_embedding_hnsw_idx')
    op.drop_table('chunks')
    op.drop_table('documents')
    op.drop_table('workspaces')
    op.drop_table('users')
    op.execute("DROP EXTENSION IF EXISTS vector")