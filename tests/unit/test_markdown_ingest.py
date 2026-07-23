from __future__ import annotations

from uuid import uuid4

from graphrag_service.adapters.markdown.parser import SourceMappedMarkdownParser
from graphrag_service.application.chunker import StructuralChunker

SOURCE = """---
title: Frontmatter title
tags:
  - telecom
---
# Hálózat

Bekezdés [[CMTS#Interfész|fejállomás]] és [leírás](docs/info.md). #access

## Eszközök

- CMTS
  - downstream

| Típus | Név |
| --- | --- |
| ONT | EG8145V5 |

```text
exact code
```

![[diagram.png]]

## Eszközök

Második azonos heading ^block-id
"""


def test_parser_produces_exact_global_spans_and_structures() -> None:
    version_id = uuid4()
    parsed = SourceMappedMarkdownParser().parse(SOURCE, version_id)

    assert parsed.title == "Hálózat"
    assert parsed.frontmatter["tags"] == ["telecom"]
    assert [section.heading_text for section in parsed.sections[1:]] == [
        "Hálózat",
        "Eszközök",
        "Eszközök",
    ]
    repeated = [section for section in parsed.sections if section.heading_text == "Eszközök"]
    assert [section.heading_occurrence for section in repeated] == [0, 1]
    assert {"heading", "paragraph", "list", "table", "fenced_code"} <= {
        block.block_type for block in parsed.blocks
    }
    for block in parsed.blocks:
        exact = SOURCE[block.char_start : block.char_end]
        assert exact
    assert {link.link_kind for link in parsed.links} == {
        "wikilink",
        "markdown",
        "embed",
    }
    wikilink = next(link for link in parsed.links if link.link_kind == "wikilink")
    assert SOURCE[wikilink.char_start : wikilink.char_end] == "[[CMTS#Interfész|fejállomás]]"
    assert wikilink.target_path == "CMTS"
    assert wikilink.target_heading == "Interfész"
    assert wikilink.alias == "fejállomás"
    assert any(tag.value == "access" for tag in parsed.tags)


def test_structural_chunks_are_source_exact_and_deterministic() -> None:
    version_id = uuid4()
    parsed = SourceMappedMarkdownParser().parse(SOURCE, version_id)
    chunker = StructuralChunker(target_chars=120, hard_max_chars=300)
    first = chunker.chunk(SOURCE, version_id, parsed.sections, parsed.blocks)
    second = chunker.chunk(SOURCE, version_id, parsed.sections, parsed.blocks)

    assert [chunk.id for chunk in first] == [chunk.id for chunk in second]
    assert len(first) > 1
    for chunk in first:
        assert chunk.text == SOURCE[chunk.char_start : chunk.char_end]
