from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid5

import marko
import yaml

from graphrag_service.domain.markdown import (
    ParsedBlock,
    ParsedDocument,
    ParsedLink,
    ParsedSection,
    ParsedTag,
)

PARSER_NAME = "marko-gfm-source-mapper"
PARSER_VERSION = "1.0.0"
_FRONTMATTER_LIMIT = 256 * 1024
_ATX_HEADING = re.compile(r"^( {0,3})(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_LIST = re.compile(r"^ {0,3}(?:[-+*]|\d+[.)])[ \t]+")
_BLOCKQUOTE = re.compile(r"^ {0,3}>")
_THEMATIC = re.compile(r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
_TABLE_DELIMITER = re.compile(
    r"^ {0,3}\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)+\|?[ \t]*$"
)
_WIKILINK = re.compile(r"(!)?\[\[([^\]\n]+)\]\]")
_MARKDOWN_LINK = re.compile(r"(!)?\[([^\]\n]*)\]\(([^)\s]+)(?:\s+[^)]*)?\)")
_TAG = re.compile(r"(?<![\w/])#([^\s#.,;:!?()\[\]{}]+)")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    raise TypeError(f"unsupported YAML value type: {type(value).__name__}")


class SourceMappedMarkdownParser:
    """Use Marko for GFM AST validation and a source-faithful mapper for spans."""

    def __init__(self) -> None:
        self._markdown = marko.Markdown(extensions=["gfm"])

    def parse(self, source: str, document_version_id: UUID) -> ParsedDocument:
        quality_flags: list[dict[str, Any]] = []
        frontmatter, body_start = self._frontmatter(source, quality_flags)
        body = source[body_start:]
        try:
            self._markdown.parse(body)
        except Exception as exc:
            quality_flags.append({"code": "marko_parse_failed", "error_type": type(exc).__name__})

        line_spans = self._line_spans(source, body_start)
        raw_blocks = self._scan_blocks(source, line_spans, quality_flags)
        sections, block_sections = self._sections(
            source, document_version_id, body_start, raw_blocks
        )
        blocks = tuple(
            ParsedBlock(
                id=uuid5(
                    document_version_id,
                    f"block:{item['start']}:{item['end']}:{item['type']}:{PARSER_VERSION}",
                ),
                section_id=block_sections[index],
                block_type=str(item["type"]),
                ordinal=index,
                char_start=int(item["start"]),
                char_end=int(item["end"]),
                content_sha256=_sha256(source[int(item["start"]) : int(item["end"])]),
                code_language=item.get("language"),
                metadata=dict(item.get("metadata", {})),
            )
            for index, item in enumerate(raw_blocks)
        )
        links = self._links(source, document_version_id)
        tags = tuple(
            ParsedTag(
                value=match.group(1),
                char_start=match.start(),
                char_end=match.end(),
            )
            for match in _TAG.finditer(source)
            if not source[max(0, match.start() - 2) : match.start()].endswith("[")
        )
        title = next(
            (section.heading_text for section in sections if section.heading_level == 1),
            None,
        )
        if title is None and isinstance(frontmatter.get("title"), str):
            title = frontmatter["title"]
        return ParsedDocument(
            title=title,
            frontmatter=frontmatter,
            sections=tuple(sections),
            blocks=blocks,
            links=links,
            tags=tags,
            quality_flags=tuple(quality_flags),
        )

    def _frontmatter(
        self, source: str, quality_flags: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], int]:
        if not source.startswith("---"):
            return {}, 0
        first_end = source.find("\n")
        if first_end < 0 or source[:first_end].rstrip("\r") != "---":
            return {}, 0
        position = first_end + 1
        closing_end = -1
        while position <= min(len(source), _FRONTMATTER_LIMIT):
            line_end = source.find("\n", position)
            if line_end < 0:
                line_end = len(source)
            marker = source[position:line_end].rstrip("\r")
            if marker in {"---", "..."}:
                closing_end = line_end + (1 if line_end < len(source) else 0)
                break
            if line_end >= len(source):
                break
            position = line_end + 1
        if closing_end < 0:
            quality_flags.append({"code": "frontmatter_unclosed"})
            return {}, 0
        yaml_text = source[first_end + 1 : position]
        try:
            loaded = yaml.safe_load(yaml_text)
            if loaded is None:
                return {}, closing_end
            if not isinstance(loaded, dict):
                raise TypeError("frontmatter root must be a mapping")
            return _json_safe(loaded), closing_end
        except (yaml.YAMLError, TypeError) as exc:
            quality_flags.append({"code": "frontmatter_invalid", "error_type": type(exc).__name__})
            return {}, closing_end

    @staticmethod
    def _line_spans(source: str, start: int) -> list[tuple[int, int, str]]:
        spans: list[tuple[int, int, str]] = []
        position = start
        while position < len(source):
            end = source.find("\n", position)
            if end < 0:
                end = len(source)
            else:
                end += 1
            spans.append((position, end, source[position:end].rstrip("\r\n")))
            position = end
        return spans

    def _scan_blocks(
        self,
        source: str,
        lines: list[tuple[int, int, str]],
        quality_flags: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        index = 0
        while index < len(lines):
            start, end, text = lines[index]
            if not text.strip():
                index += 1
                continue
            heading = _ATX_HEADING.match(text)
            if heading:
                blocks.append(
                    {
                        "type": "heading",
                        "start": start,
                        "end": end,
                        "level": len(heading.group(2)),
                        "heading": heading.group(3).strip(),
                    }
                )
                index += 1
                continue
            if index + 1 < len(lines) and _SETEXT.match(lines[index + 1][2]):
                underline = lines[index + 1]
                blocks.append(
                    {
                        "type": "heading",
                        "start": start,
                        "end": underline[1],
                        "level": 1 if underline[2].lstrip().startswith("=") else 2,
                        "heading": text.strip(),
                        "metadata": {"style": "setext"},
                    }
                )
                index += 2
                continue
            fence = _FENCE.match(text)
            if fence:
                marker = fence.group(1)
                info = fence.group(2).strip().split(maxsplit=1)
                language = info[0] if info else None
                closing = index + 1
                while closing < len(lines):
                    candidate = lines[closing][2].lstrip()
                    if candidate.startswith(marker[0] * len(marker)):
                        closing += 1
                        break
                    closing += 1
                if closing > len(lines) or (
                    closing == len(lines)
                    and not lines[-1][2].lstrip().startswith(marker[0] * len(marker))
                ):
                    quality_flags.append({"code": "unclosed_fence", "char_start": start})
                block_end = lines[min(closing, len(lines)) - 1][1]
                blocks.append(
                    {
                        "type": "fenced_code",
                        "start": start,
                        "end": block_end,
                        "language": language,
                    }
                )
                index = closing
                continue
            if text.startswith(("    ", "\t")):
                closing = index + 1
                while closing < len(lines) and (
                    lines[closing][2].startswith(("    ", "\t")) or not lines[closing][2].strip()
                ):
                    closing += 1
                blocks.append(
                    {
                        "type": "indented_code",
                        "start": start,
                        "end": lines[closing - 1][1],
                    }
                )
                index = closing
                continue
            if (
                index + 1 < len(lines)
                and "|" in text
                and _TABLE_DELIMITER.match(lines[index + 1][2])
            ):
                closing = index + 2
                while closing < len(lines) and "|" in lines[closing][2]:
                    closing += 1
                blocks.append({"type": "table", "start": start, "end": lines[closing - 1][1]})
                index = closing
                continue
            if _LIST.match(text):
                closing = index + 1
                while closing < len(lines):
                    candidate = lines[closing][2]
                    if not candidate.strip() or _LIST.match(candidate):
                        closing += 1
                        continue
                    if candidate.startswith((" ", "\t")):
                        closing += 1
                        continue
                    break
                blocks.append({"type": "list", "start": start, "end": lines[closing - 1][1]})
                index = closing
                continue
            if _BLOCKQUOTE.match(text):
                closing = index + 1
                while closing < len(lines) and (
                    _BLOCKQUOTE.match(lines[closing][2]) or not lines[closing][2].strip()
                ):
                    closing += 1
                blocks.append(
                    {
                        "type": "blockquote",
                        "start": start,
                        "end": lines[closing - 1][1],
                    }
                )
                index = closing
                continue
            if _THEMATIC.match(text):
                blocks.append({"type": "thematic_break", "start": start, "end": end})
                index += 1
                continue
            if text.lstrip().startswith("<"):
                blocks.append({"type": "html", "start": start, "end": end})
                index += 1
                continue

            closing = index + 1
            while closing < len(lines):
                candidate = lines[closing][2]
                if not candidate.strip() or self._starts_block(lines, closing):
                    break
                closing += 1
            blocks.append({"type": "paragraph", "start": start, "end": lines[closing - 1][1]})
            index = closing
        return blocks

    @staticmethod
    def _starts_block(lines: list[tuple[int, int, str]], index: int) -> bool:
        text = lines[index][2]
        return bool(
            _ATX_HEADING.match(text)
            or _FENCE.match(text)
            or _LIST.match(text)
            or _BLOCKQUOTE.match(text)
            or _THEMATIC.match(text)
            or text.startswith(("    ", "\t"))
            or (
                index + 1 < len(lines)
                and "|" in text
                and _TABLE_DELIMITER.match(lines[index + 1][2])
            )
        )

    def _sections(
        self,
        source: str,
        version_id: UUID,
        body_start: int,
        blocks: list[dict[str, Any]],
    ) -> tuple[list[ParsedSection], dict[int, UUID]]:
        root_id = uuid5(version_id, f"section:root:{PARSER_VERSION}")
        root = ParsedSection(
            id=root_id,
            parent_id=None,
            heading_level=0,
            heading_text="",
            heading_path=[],
            heading_occurrence=0,
            char_start=body_start,
            char_end=len(source),
            content_sha256=_sha256(source[body_start:]),
            ordinal=0,
            metadata={"synthetic_root": True},
        )
        sections = [root]
        stack: list[ParsedSection] = [root]
        occurrences: dict[tuple[str, ...], int] = defaultdict(int)
        block_sections: dict[int, UUID] = {}

        for index, block in enumerate(blocks):
            if block["type"] != "heading":
                block_sections[index] = stack[-1].id
                continue
            level = int(block["level"])
            while len(stack) > 1 and stack[-1].heading_level >= level:
                closing = stack.pop()
                closing.char_end = int(block["start"])
                closing.content_sha256 = _sha256(source[closing.char_start : closing.char_end])
            parent = stack[-1]
            heading_text = str(block["heading"])
            heading_path = [*parent.heading_path, heading_text]
            occurrence_key = tuple(heading_path)
            occurrence = occurrences[occurrence_key]
            occurrences[occurrence_key] += 1
            section_id = uuid5(
                version_id,
                "section:"
                + "/".join(heading_path)
                + f":{occurrence}:{block['start']}:{PARSER_VERSION}",
            )
            section = ParsedSection(
                id=section_id,
                parent_id=parent.id,
                heading_level=level,
                heading_text=heading_text,
                heading_path=heading_path,
                heading_occurrence=occurrence,
                char_start=int(block["start"]),
                char_end=len(source),
                content_sha256="",
                ordinal=len(sections),
                metadata=dict(block.get("metadata", {})),
            )
            sections.append(section)
            stack.append(section)
            block_sections[index] = section.id
        while len(stack) > 1:
            closing = stack.pop()
            closing.content_sha256 = _sha256(source[closing.char_start : closing.char_end])
        return sections, block_sections

    @staticmethod
    def _links(source: str, version_id: UUID) -> tuple[ParsedLink, ...]:
        links: list[ParsedLink] = []
        occupied: list[tuple[int, int]] = []
        for match in _WIKILINK.finditer(source):
            embed = bool(match.group(1))
            raw = match.group(2)
            target, separator, alias = raw.partition("|")
            path_part, hash_separator, fragment = target.partition("#")
            heading: str | None = fragment if hash_separator else None
            block_id: str | None = None
            if heading and "^" in heading:
                heading, _, block_id = heading.partition("^")
            elif "^" in path_part:
                path_part, _, block_id = path_part.partition("^")
            links.append(
                ParsedLink(
                    id=uuid5(
                        version_id,
                        f"link:{match.start()}:{match.end()}:{PARSER_VERSION}",
                    ),
                    link_kind="embed" if embed else "wikilink",
                    raw_target=target,
                    target_path=path_part or None,
                    target_heading=heading or None,
                    target_block_id=block_id or None,
                    alias=alias if separator else None,
                    char_start=match.start(),
                    char_end=match.end(),
                )
            )
            occupied.append((match.start(), match.end()))
        for match in _MARKDOWN_LINK.finditer(source):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            target = match.group(3)
            external = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target)
            links.append(
                ParsedLink(
                    id=uuid5(
                        version_id,
                        f"link:{match.start()}:{match.end()}:{PARSER_VERSION}",
                    ),
                    link_kind="embed" if match.group(1) else "markdown",
                    raw_target=target,
                    target_path=None if external else target,
                    target_heading=None,
                    target_block_id=None,
                    alias=match.group(2) or None,
                    char_start=match.start(),
                    char_end=match.end(),
                )
            )
        return tuple(sorted(links, key=lambda item: item.char_start))
