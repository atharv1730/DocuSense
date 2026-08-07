"""Add rewritten flag to retrieval_logs.

Marks logs whose stored `query` is a standalone rewrite of a follow-up
question (produced by rewrite_query) rather than the user's original text,
so the eval dashboard and debugging tools can tell the two apart.
"""

from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'retrieval_logs',
        sa.Column('rewritten', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade():
    op.drop_column('retrieval_logs', 'rewritten')
