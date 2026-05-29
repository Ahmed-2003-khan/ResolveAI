"""add language-agnostic simple-config tsvector for Roman-Urdu BM25

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-30

The original content_tsv uses the 'english' config, which stems and drops
stopwords — fatal for Roman-Urdu queries whose terms aren't English words.
This adds a STORED generated column built with the 'simple' config (no
stemming, no stopword removal) plus a GIN index. Being generated, it
backfills existing rows automatically and stays in sync on insert/update,
so no re-ingestion is required.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE kb_chunks ADD COLUMN content_tsv_simple tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_kb_chunks_content_tsv_simple "
        "ON kb_chunks USING gin(content_tsv_simple)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_content_tsv_simple")
    op.execute("ALTER TABLE kb_chunks DROP COLUMN IF EXISTS content_tsv_simple")
