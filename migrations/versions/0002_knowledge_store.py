"""Semantic knowledge store (pgvector).

Lives in its own schema so the read-only executor role cannot see it:
generated SQL must never be able to read the answer key or the context.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS nl2sql")
    # Dimension-less `vector`: the store is ~50 rows, so exact (sequential) cosine search
    # is instant and we can switch embedding models without a migration.
    op.execute("""
    CREATE TABLE nl2sql.knowledge_items (
        id               text PRIMARY KEY,
        knowledge_type   text NOT NULL CHECK (knowledge_type IN
                             ('business_entity', 'metric', 'domain_rule', 'example')),
        name             text NOT NULL,
        content          text NOT NULL,
        metadata         jsonb NOT NULL DEFAULT '{}'::jsonb,
        embedding        vector NOT NULL,
        embedding_model  text NOT NULL,
        content_hash     text NOT NULL,
        updated_at       timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_knowledge_type ON nl2sql.knowledge_items (knowledge_type)")


def downgrade() -> None:
    op.execute("DROP SCHEMA nl2sql CASCADE")
