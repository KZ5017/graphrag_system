from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from graphrag_service.adapters.postgres.base import Base


class VaultModel(Base):
    __tablename__ = "vaults"
    __table_args__ = (
        CheckConstraint(
            "path_case_mode IN ('sensitive', 'insensitive')",
            name="valid_path_case_mode",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled', 'error')",
            name="valid_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    root_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    path_case_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'sensitive'")
    )
    include_globs: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sql_text("'[\"**/*.md\"]'::jsonb")
    )
    exclude_globs: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=sql_text('\'[".obsidian/**", ".trash/**"]\'::jsonb'),
    )
    internal_uri_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    obsidian_uri_template: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'active'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ScanRunModel(Base):
    __tablename__ = "scan_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="valid_status",
        ),
        CheckConstraint(
            "scan_type IN ('incremental', 'full_rehash', 'measure')",
            name="valid_scan_type",
        ),
        Index("ix_scan_runs_vault_started", "vault_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    vault_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    scan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scanner_version: Mapped[str] = mapped_column(String(50), nullable=False)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hashed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    modified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    renamed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    markdown_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    warnings_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentModel(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("vault_id", "path_key", name="uq_documents_vault_path_key"),
        CheckConstraint(
            "lifecycle_status IN ('active', 'deleted', 'error')",
            name="valid_lifecycle_status",
        ),
        Index("ix_documents_vault_lifecycle", "vault_id", "lifecycle_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    vault_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False
    )
    current_relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    path_key: Mapped[str] = mapped_column(Text, nullable=False)
    current_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "document_versions.id",
            name="fk_documents_current_version_id_document_versions",
            use_alter=True,
            ondelete="SET NULL",
        ),
    )
    title: Mapped[str | None] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'active'")
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentVersionModel(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "content_sha256",
            name="uq_document_versions_document_hash",
        ),
        CheckConstraint(
            "processing_status IN ('discovered', 'parsing', 'ready', 'failed', 'superseded')",
            name="valid_processing_status",
        ),
        Index("ix_document_versions_document_created", "document_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mtime_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_encoding: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=sql_text("'utf-8'")
    )
    parser_name: Mapped[str] = mapped_column(String(100), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    chunker_name: Mapped[str] = mapped_column(String(100), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(50), nullable=False)
    frontmatter_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    quality_flags_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VaultFileStateModel(Base):
    __tablename__ = "vault_file_states"
    __table_args__ = (
        Index("ix_vault_file_states_document", "document_id"),
        Index("ix_vault_file_states_hash", "vault_id", "content_sha256"),
    )

    vault_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vaults.id", ondelete="CASCADE"),
        primary_key=True,
    )
    relative_path_key: Mapped[str] = mapped_column(Text, primary_key=True)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mtime_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    last_seen_scan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ScanChangeModel(Base):
    __tablename__ = "scan_changes"
    __table_args__ = (
        CheckConstraint(
            "change_kind IN "
            "('created', 'modified', 'renamed', 'deleted', "
            "'ambiguous_rename', 'read_failed')",
            name="valid_change_kind",
        ),
        Index("ix_scan_changes_scan_kind", "scan_id", "change_kind"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    scan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("scan_runs.id", ondelete="CASCADE"), nullable=False
    )
    vault_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    change_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    old_relative_path: Mapped[str | None] = mapped_column(Text)
    new_relative_path: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SectionModel(Base):
    __tablename__ = "sections"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "ordinal",
            name="uq_sections_version_ordinal",
        ),
        CheckConstraint("char_start >= 0 AND char_end >= char_start", name="valid_span"),
        Index("ix_sections_version_parent", "document_version_id", "parent_section_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_section_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE")
    )
    heading_level: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_text: Mapped[str] = mapped_column(Text, nullable=False)
    heading_path_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    heading_occurrence: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ContentBlockModel(Base):
    __tablename__ = "content_blocks"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "ordinal",
            name="uq_content_blocks_version_ordinal",
        ),
        CheckConstraint("char_start >= 0 AND char_end >= char_start", name="valid_span"),
        CheckConstraint(
            "block_type IN "
            "('paragraph', 'list', 'table', 'fenced_code', 'indented_code', "
            "'blockquote', 'heading', 'thematic_break', 'html', 'other')",
            name="valid_block_type",
        ),
        Index("ix_content_blocks_section_ordinal", "section_id", "ordinal"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False
    )
    block_type: Mapped[str] = mapped_column(String(30), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    code_language: Mapped[str | None] = mapped_column(String(100))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ChunkModel(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "char_start",
            "char_end",
            "chunker_version",
            name="uq_chunks_version_span_chunker",
        ),
        CheckConstraint("char_start >= 0 AND char_end >= char_start", name="valid_span"),
        CheckConstraint(
            "retrieval_role IN ('structural_anchor', 'content_evidence')",
            name="valid_retrieval_role",
        ),
        Index("ix_chunks_version_ordinal", "document_version_id", "ordinal"),
        Index("ix_chunks_section_ordinal", "section_id", "ordinal"),
        Index("ix_chunks_content_sha256", "content_sha256"),
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sections.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(50), nullable=False)
    retrieval_role: Mapped[str] = mapped_column(String(30), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    token_count: Mapped[int | None] = mapped_column(Integer)
    projection_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sql_text("1")
    )
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True),
        nullable=False,
    )


class DocumentLinkModel(Base):
    __tablename__ = "document_links"
    __table_args__ = (
        CheckConstraint(
            "link_kind IN ('wikilink', 'markdown', 'embed')",
            name="valid_link_kind",
        ),
        CheckConstraint(
            "resolution_status IN ('resolved', 'unresolved', 'ambiguous', 'external')",
            name="valid_resolution_status",
        ),
        Index("ix_document_links_source_version", "source_document_version_id"),
        Index("ix_document_links_resolved_document", "resolved_document_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    source_document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_chunk_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE")
    )
    link_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_target: Mapped[str] = mapped_column(Text, nullable=False)
    target_path: Mapped[str | None] = mapped_column(Text)
    target_heading: Mapped[str | None] = mapped_column(Text)
    target_block_id: Mapped[str | None] = mapped_column(Text)
    alias: Mapped[str | None] = mapped_column(Text)
    resolved_document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    resolution_status: Mapped[str] = mapped_column(String(20), nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
