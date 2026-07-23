"""Create Phase 2 vault ingest and lexical structures.

Revision ID: 0002_phase2_ingest
Revises: 0001_phase1_jobs
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_phase2_ingest"
down_revision: str | None = "0001_phase1_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vaults",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("path_case_mode", sa.String(20), server_default="sensitive", nullable=False),
        sa.Column(
            "include_globs",
            postgresql.JSONB(),
            server_default=sa.text("'[\"**/*.md\"]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "exclude_globs",
            postgresql.JSONB(),
            server_default=sa.text('\'[".obsidian/**", ".trash/**"]\'::jsonb'),
            nullable=False,
        ),
        sa.Column("internal_uri_prefix", sa.Text(), nullable=False),
        sa.Column("obsidian_uri_template", sa.Text()),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "path_case_mode IN ('sensitive', 'insensitive')",
            name=op.f("ck_vaults_valid_path_case_mode"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled', 'error')",
            name=op.f("ck_vaults_valid_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vaults")),
        sa.UniqueConstraint("name", name=op.f("uq_vaults_name")),
        sa.UniqueConstraint("root_path", name=op.f("uq_vaults_root_path")),
    )
    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vault_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("scan_type", sa.String(20), nullable=False),
        sa.Column("scanner_version", sa.String(50), nullable=False),
        sa.Column("discovered_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("hashed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("new_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("modified_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("renamed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deleted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unchanged_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("markdown_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "warnings_json",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("error_summary", sa.Text()),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name=op.f("ck_scan_runs_valid_status"),
        ),
        sa.CheckConstraint(
            "scan_type IN ('incremental', 'full_rehash', 'measure')",
            name=op.f("ck_scan_runs_valid_scan_type"),
        ),
        sa.ForeignKeyConstraint(
            ["vault_id"],
            ["vaults.id"],
            name=op.f("fk_scan_runs_vault_id_vaults"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scan_runs")),
    )
    op.create_index("ix_scan_runs_vault_started", "scan_runs", ["vault_id", "started_at"])
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vault_id", sa.Uuid(), nullable=False),
        sa.Column("current_relative_path", sa.Text(), nullable=False),
        sa.Column("path_key", sa.Text(), nullable=False),
        sa.Column("current_version_id", sa.Uuid()),
        sa.Column("title", sa.Text()),
        sa.Column("lifecycle_status", sa.String(20), server_default="active", nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "lifecycle_status IN ('active', 'deleted', 'error')",
            name=op.f("ck_documents_valid_lifecycle_status"),
        ),
        sa.ForeignKeyConstraint(
            ["vault_id"],
            ["vaults.id"],
            name=op.f("fk_documents_vault_id_vaults"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("vault_id", "path_key", name="uq_documents_vault_path_key"),
    )
    op.create_index("ix_documents_vault_lifecycle", "documents", ["vault_id", "lifecycle_status"])
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=False),
        sa.Column("source_encoding", sa.String(30), server_default="utf-8", nullable=False),
        sa.Column("parser_name", sa.String(100), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("chunker_name", sa.String(100), nullable=False),
        sa.Column("chunker_version", sa.String(50), nullable=False),
        sa.Column(
            "frontmatter_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "quality_flags_json",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("processing_status", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "processing_status IN ('discovered', 'parsing', 'ready', 'failed', 'superseded')",
            name=op.f("ck_document_versions_valid_processing_status"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_versions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        sa.UniqueConstraint(
            "document_id",
            "content_sha256",
            name="uq_document_versions_document_hash",
        ),
    )
    op.create_index(
        "ix_document_versions_document_created",
        "document_versions",
        ["document_id", "created_at"],
    )
    op.create_foreign_key(
        "fk_documents_current_version_id_document_versions",
        "documents",
        "document_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "vault_file_states",
        sa.Column("vault_id", sa.Uuid(), nullable=False),
        sa.Column("relative_path_key", sa.Text(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("last_seen_scan_id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["vault_id"], ["vaults.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_seen_scan_id"], ["scan_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("vault_id", "relative_path_key", name=op.f("pk_vault_file_states")),
    )
    op.create_index("ix_vault_file_states_document", "vault_file_states", ["document_id"])
    op.create_index(
        "ix_vault_file_states_hash",
        "vault_file_states",
        ["vault_id", "content_sha256"],
    )
    op.create_table(
        "scan_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("vault_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid()),
        sa.Column("change_kind", sa.String(30), nullable=False),
        sa.Column("old_relative_path", sa.Text()),
        sa.Column("new_relative_path", sa.Text()),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column(
            "detail_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "change_kind IN ('created', 'modified', 'renamed', 'deleted', "
            "'ambiguous_rename', 'read_failed')",
            name=op.f("ck_scan_changes_valid_change_kind"),
        ),
        sa.ForeignKeyConstraint(["scan_id"], ["scan_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vault_id"], ["vaults.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scan_changes")),
    )
    op.create_index("ix_scan_changes_scan_kind", "scan_changes", ["scan_id", "change_kind"])
    op.create_table(
        "sections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("parent_section_id", sa.Uuid()),
        sa.Column("heading_level", sa.Integer(), nullable=False),
        sa.Column("heading_text", sa.Text(), nullable=False),
        sa.Column("heading_path_json", postgresql.JSONB(), nullable=False),
        sa.Column("heading_occurrence", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_start >= 0 AND char_end >= char_start", name=op.f("ck_sections_valid_span")
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["parent_section_id"], ["sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sections")),
        sa.UniqueConstraint("document_version_id", "ordinal", name="uq_sections_version_ordinal"),
    )
    op.create_index(
        "ix_sections_version_parent", "sections", ["document_version_id", "parent_section_id"]
    )
    op.create_table(
        "content_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("block_type", sa.String(30), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("code_language", sa.String(100)),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_start >= 0 AND char_end >= char_start", name=op.f("ck_content_blocks_valid_span")
        ),
        sa.CheckConstraint(
            "block_type IN ('paragraph', 'list', 'table', 'fenced_code', "
            "'indented_code', 'blockquote', 'heading', 'thematic_break', 'html', 'other')",
            name=op.f("ck_content_blocks_valid_block_type"),
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_blocks")),
        sa.UniqueConstraint(
            "document_version_id",
            "ordinal",
            name="uq_content_blocks_version_ordinal",
        ),
    )
    op.create_index(
        "ix_content_blocks_section_ordinal", "content_blocks", ["section_id", "ordinal"]
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("chunker_version", sa.String(50), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("token_count", sa.Integer()),
        sa.Column("projection_generation", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_start >= 0 AND char_end >= char_start", name=op.f("ck_chunks_valid_span")
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["section_id"], ["sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        sa.UniqueConstraint(
            "document_version_id",
            "char_start",
            "char_end",
            "chunker_version",
            name="uq_chunks_version_span_chunker",
        ),
    )
    op.create_index("ix_chunks_version_ordinal", "chunks", ["document_version_id", "ordinal"])
    op.create_index("ix_chunks_section_ordinal", "chunks", ["section_id", "ordinal"])
    op.create_index("ix_chunks_content_sha256", "chunks", ["content_sha256"])
    op.create_index("ix_chunks_search_vector", "chunks", ["search_vector"], postgresql_using="gin")
    op.create_table(
        "document_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_document_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_chunk_id", sa.Uuid()),
        sa.Column("link_kind", sa.String(20), nullable=False),
        sa.Column("raw_target", sa.Text(), nullable=False),
        sa.Column("target_path", sa.Text()),
        sa.Column("target_heading", sa.Text()),
        sa.Column("target_block_id", sa.Text()),
        sa.Column("alias", sa.Text()),
        sa.Column("resolved_document_id", sa.Uuid()),
        sa.Column("resolution_status", sa.String(20), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "link_kind IN ('wikilink', 'markdown', 'embed')",
            name=op.f("ck_document_links_valid_link_kind"),
        ),
        sa.CheckConstraint(
            "resolution_status IN ('resolved', 'unresolved', 'ambiguous', 'external')",
            name=op.f("ck_document_links_valid_resolution_status"),
        ),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"], ["document_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_links")),
    )
    op.create_index(
        "ix_document_links_source_version", "document_links", ["source_document_version_id"]
    )
    op.create_index(
        "ix_document_links_resolved_document", "document_links", ["resolved_document_id"]
    )


def downgrade() -> None:
    op.drop_table("document_links")
    op.drop_table("chunks")
    op.drop_table("content_blocks")
    op.drop_table("sections")
    op.drop_table("scan_changes")
    op.drop_table("vault_file_states")
    op.drop_constraint(
        "fk_documents_current_version_id_document_versions",
        "documents",
        type_="foreignkey",
    )
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("scan_runs")
    op.drop_table("vaults")
