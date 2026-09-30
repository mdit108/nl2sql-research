"""Grant the executor role SELECT on olist only.

The role itself (read-only transactions, statement timeout, search_path=olist)
is created by scripts/init_db.sql, because that needs superuser.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT USAGE ON SCHEMA olist TO nl2sql_readonly")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA olist TO nl2sql_readonly")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA olist GRANT SELECT ON TABLES TO nl2sql_readonly")
    op.execute("REVOKE ALL ON SCHEMA nl2sql FROM nl2sql_readonly")


def downgrade() -> None:
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA olist REVOKE SELECT ON TABLES FROM nl2sql_readonly")
    op.execute("REVOKE SELECT ON ALL TABLES IN SCHEMA olist FROM nl2sql_readonly")
    op.execute("REVOKE USAGE ON SCHEMA olist FROM nl2sql_readonly")
