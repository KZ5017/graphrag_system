from __future__ import annotations

import hashlib
from collections import defaultdict
from uuid import UUID, uuid5

from graphrag_service.domain.markdown import (
    ParsedBlock,
    ParsedChunk,
    ParsedSection,
)

CHUNKER_NAME = "structural-block-chunker"
CHUNKER_VERSION = "1.1.0"
STRUCTURAL_BLOCK_TYPES = frozenset({"heading", "thematic_break"})


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class StructuralChunker:
    def __init__(self, *, target_chars: int = 4000, hard_max_chars: int = 12000) -> None:
        if target_chars <= 0 or hard_max_chars < target_chars:
            raise ValueError("invalid chunk size limits")
        self._target_chars = target_chars
        self._hard_max_chars = hard_max_chars

    def chunk(
        self,
        source: str,
        version_id: UUID,
        sections: tuple[ParsedSection, ...],
        blocks: tuple[ParsedBlock, ...],
    ) -> tuple[ParsedChunk, ...]:
        blocks_by_section: dict[UUID, list[ParsedBlock]] = defaultdict(list)
        for block in blocks:
            blocks_by_section[block.section_id].append(block)
        chunks: list[ParsedChunk] = []
        section_by_id = {section.id: section for section in sections}

        for section in sections:
            section_blocks = blocks_by_section.get(section.id, [])
            group: list[ParsedBlock] = []
            for block in section_blocks:
                if block.char_end - block.char_start > self._hard_max_chars:
                    if group:
                        chunks.append(
                            self._from_group(
                                source,
                                version_id,
                                section_by_id[group[0].section_id],
                                group,
                                len(chunks),
                            )
                        )
                        group = []
                    chunks.extend(
                        self._split_large_block(source, version_id, section, block, len(chunks))
                    )
                    continue
                if group and block.char_end - group[0].char_start > self._target_chars:
                    chunks.append(self._from_group(source, version_id, section, group, len(chunks)))
                    group = []
                group.append(block)
            if group:
                chunks.append(self._from_group(source, version_id, section, group, len(chunks)))
        return tuple(chunks)

    @staticmethod
    def _from_group(
        source: str,
        version_id: UUID,
        section: ParsedSection,
        blocks: list[ParsedBlock],
        ordinal: int,
    ) -> ParsedChunk:
        start = blocks[0].char_start
        end = blocks[-1].char_end
        text = source[start:end]
        return ParsedChunk(
            id=uuid5(
                version_id,
                f"chunk:{section.id}:{start}:{end}:{CHUNKER_VERSION}",
            ),
            section_id=section.id,
            ordinal=ordinal,
            char_start=start,
            char_end=end,
            text=text,
            content_sha256=_sha256(text),
            metadata={
                "heading_path": section.heading_path,
                "block_ids": [str(block.id) for block in blocks],
                "retrieval_role": _retrieval_role(blocks),
            },
        )

    def _split_large_block(
        self,
        source: str,
        version_id: UUID,
        section: ParsedSection,
        block: ParsedBlock,
        first_ordinal: int,
    ) -> list[ParsedChunk]:
        chunks: list[ParsedChunk] = []
        start = block.char_start
        while start < block.char_end:
            proposed_end = min(start + self._hard_max_chars, block.char_end)
            if proposed_end < block.char_end:
                newline = source.rfind("\n", start, proposed_end)
                if newline > start:
                    proposed_end = newline + 1
            text = source[start:proposed_end]
            chunks.append(
                ParsedChunk(
                    id=uuid5(
                        version_id,
                        f"chunk:{section.id}:{start}:{proposed_end}:{CHUNKER_VERSION}",
                    ),
                    section_id=section.id,
                    ordinal=first_ordinal + len(chunks),
                    char_start=start,
                    char_end=proposed_end,
                    text=text,
                    content_sha256=_sha256(text),
                    metadata={
                        "heading_path": section.heading_path,
                        "block_ids": [str(block.id)],
                        "hard_split": True,
                        "retrieval_role": _retrieval_role([block]),
                    },
                )
            )
            start = proposed_end
        return chunks


def _retrieval_role(blocks: list[ParsedBlock]) -> str:
    if all(block.block_type in STRUCTURAL_BLOCK_TYPES for block in blocks):
        return "structural_anchor"
    return "content_evidence"
