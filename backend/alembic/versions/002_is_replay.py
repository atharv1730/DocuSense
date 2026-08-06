"""Add is_replay flag to retrieval_logs.

Distinguishes logs written by the eval replay endpoint (retrieval-only,
no generation call) from logs written by real chat queries, so the eval
dashboard can filter them independently.
"""

from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'retrieval_logs',
        sa.Column('is_replay', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade():
    op.drop_column('retrieval_logs', 'is_replay')
