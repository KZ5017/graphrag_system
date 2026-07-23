from __future__ import annotations

from uuid import uuid4

from graphrag_service.adapters.markdown.parser import SourceMappedMarkdownParser


def test_fenced_code_without_language_is_valid() -> None:
    source = "# Note\n\n```\ncommand\n```\n"
    parsed = SourceMappedMarkdownParser().parse(source, uuid4())

    fenced = next(block for block in parsed.blocks if block.block_type == "fenced_code")
    assert fenced.code_language is None
    assert source[fenced.char_start : fenced.char_end] == "```\ncommand\n```\n"
