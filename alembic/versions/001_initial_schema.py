"""Initial schema: api_keys, documents, parse_jobs, batch_jobs

Revision ID: 001
Revises:
Create Date: 2025-03-03 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)

    # documents table
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("document_type", sa.String(30), nullable=True),
        sa.Column("document_hint", sa.String(30), nullable=True),
        sa.Column("s3_key", sa.String(500), nullable=False),
        sa.Column("s3_bucket", sa.String(255), nullable=False),
        sa.Column(
            "extracted_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column(
            "has_validation_errors",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "validation_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "api_key_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("api_keys.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_hash", "documents", ["hash"], unique=True)
    op.create_index("ix_documents_api_key_id", "documents", ["api_key_id"])

    # parse_jobs table
    op.create_table(
        "parse_jobs",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("documents.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(50), nullable=True),
        sa.Column("webhook_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_parse_jobs_status", "parse_jobs", ["status"])
    op.create_index("ix_parse_jobs_document_id", "parse_jobs", ["document_id"])

    # batch_jobs table
    op.create_table(
        "batch_jobs",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column(
            "parse_job_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_batch_jobs_status", "batch_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("batch_jobs")
    op.drop_index("ix_parse_jobs_document_id", table_name="parse_jobs")
    op.drop_index("ix_parse_jobs_status", table_name="parse_jobs")
    op.drop_table("parse_jobs")
    op.drop_index("ix_documents_api_key_id", table_name="documents")
    op.drop_index("ix_documents_hash", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
