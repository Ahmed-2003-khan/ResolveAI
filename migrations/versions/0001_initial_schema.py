"""initial schema — all tables, pgvector extension, and indexes

Revision ID: 0001
Revises:
Create Date: 2026-05-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Extensions                                                           #
    # ------------------------------------------------------------------ #
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------ #
    # users                                                                #
    # ------------------------------------------------------------------ #
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("plan_tier", sa.String(50), nullable=True),
        sa.Column(
            "account_status",
            sa.String(50),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "language_pref",
            sa.String(10),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.UniqueConstraint("phone", name="uq_users_phone"),
    )

    # ------------------------------------------------------------------ #
    # conversations                                                        #
    # ------------------------------------------------------------------ #
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("assigned_human", sa.String(100), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_activity",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_conversations_status", "conversations", ["status"])
    op.create_index(
        "ix_conversations_last_activity", "conversations", ["last_activity"]
    )

    # ------------------------------------------------------------------ #
    # messages                                                             #
    # ------------------------------------------------------------------ #
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("sender_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_redacted", sa.Text(), nullable=True),
        sa.Column("channel_msg_id", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        "ix_messages_conv_created",
        "messages",
        ["conversation_id", "created_at"],
    )

    # ------------------------------------------------------------------ #
    # kb_chunks                                                            #
    # ------------------------------------------------------------------ #
    op.create_table(
        "kb_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("product_area", sa.String(50), nullable=True),
        sa.Column(
            "confidentiality",
            sa.String(20),
            nullable=False,
            server_default="public",
        ),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )
    # tsvector and vector columns — added via raw SQL (special pg types)
    op.execute("ALTER TABLE kb_chunks ADD COLUMN content_tsv tsvector")
    op.execute("ALTER TABLE kb_chunks ADD COLUMN embedding vector(1536)")
    # GIN index for full-text search
    op.execute(
        "CREATE INDEX ix_kb_chunks_content_tsv ON kb_chunks USING gin(content_tsv)"
    )
    # IVFFlat index for approximate nearest-neighbour search
    op.execute(
        "CREATE INDEX ix_kb_chunks_embedding ON kb_chunks"
        " USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.create_index("ix_kb_chunks_source_type", "kb_chunks", ["source_type"])
    op.create_index("ix_kb_chunks_product_area", "kb_chunks", ["product_area"])

    # ------------------------------------------------------------------ #
    # semantic_cache                                                       #
    # ------------------------------------------------------------------ #
    op.create_table(
        "semantic_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("query_normalized", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column(
            "hit_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "ALTER TABLE semantic_cache ADD COLUMN query_embedding vector(1536)"
    )
    op.execute(
        "CREATE INDEX ix_semantic_cache_embedding ON semantic_cache"
        " USING ivfflat (query_embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # ------------------------------------------------------------------ #
    # audit_log                                                            #
    # ------------------------------------------------------------------ #
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id"),
            nullable=True,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id"),
            nullable=True,
        ),
        sa.Column("node_name", sa.String(50), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_redacted", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_audit_log_conv_created",
        "audit_log",
        ["conversation_id", "created_at"],
    )

    # ------------------------------------------------------------------ #
    # eval_runs                                                            #
    # ------------------------------------------------------------------ #
    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("git_sha", sa.String(40), nullable=True),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("total_cases", sa.Integer(), nullable=True),
        sa.Column("passed", sa.Integer(), nullable=True),
        sa.Column("failed", sa.Integer(), nullable=True),
        sa.Column("groundedness", sa.Numeric(4, 3), nullable=True),
        sa.Column("helpfulness", sa.Numeric(4, 3), nullable=True),
        sa.Column("policy_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )

    # ------------------------------------------------------------------ #
    # eval_results                                                         #
    # ------------------------------------------------------------------ #
    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id"),
            nullable=False,
        ),
        sa.Column("case_id", sa.String(100), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("actual_response", sa.Text(), nullable=True),
        sa.Column("expected_response", sa.Text(), nullable=True),
        sa.Column("judge_scores", postgresql.JSONB, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
    op.drop_table("audit_log")
    op.drop_table("semantic_cache")
    op.drop_table("kb_chunks")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("users")
    op.execute("DROP EXTENSION IF EXISTS vector")
