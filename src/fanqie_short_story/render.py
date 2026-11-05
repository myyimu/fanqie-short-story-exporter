"""Turn short-story HTML into plain text and Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .client import Story


@dataclass(frozen=True)
class Block:
    kind: str
    value: str


class _StoryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.parts: list[str] = []
        self.skip_depth = 0

    def _flush(self) -> None:
        value = "".join(self.parts).strip()
        self.parts.clear()
        if value:
            self.blocks.append(Block("text", value))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"p", "div", "section", "h1", "h2", "h3"}:
            self._flush()
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "img":
            self._flush()
            attributes = dict(attrs)
            src = attributes.get("src") or attributes.get("data-src") or ""
            if src.startswith("//"):
                src = "https:" + src
            if urlsplit(src).scheme == "https":
                self.blocks.append(Block("image", src))

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if not self.skip_depth and tag in {"p", "div", "section", "h1", "h2", "h3"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def parse_blocks(html_content: str) -> list[Block]:
    parser = _StoryParser()
    parser.feed(html_content)
    parser.close()
    parser._flush()
    return parser.blocks


def _escape_markdown(text: str) -> str:
    text = text.replace("\\", "\\\\")
    for marker in ("*", "_", "[", "]", "`"):
        text = text.replace(marker, "\\" + marker)
    return "\n".join(re.sub(r"^([#>+-])", r"\\\1", line) for line in text.split("\n"))


def render_txt(story: Story, blocks: list[Block]) -> str:
    header = [story.title]
    if story.author:
        header.append(f"作者：{story.author}")
    lines = ["\n".join(header)]
    image_number = 0
    for block in blocks:
        if block.kind == "image":
            image_number += 1
            lines.append(f"[插图 {image_number}]")
        else:
            lines.append(block.value)
    return "\n\n".join(lines).rstrip() + "\n"


def render_markdown(
    story: Story, blocks: list[Block], image_paths: dict[int, str] | None = None
) -> str:
    lines = [f"# {_escape_markdown(story.title)}"]
    if story.author:
        lines.append(f"作者：{_escape_markdown(story.author)}")
    image_number = 0
    for block in blocks:
        if block.kind == "image":
            image_number += 1
            src = (image_paths or {}).get(image_number, block.value)
            src = src.replace("<", "%3C").replace(">", "%3E").replace("\n", "")
            lines.append(f"![插图 {image_number}](<{src}>)")
        elif re.fullmatch(r"\d+[.、]", block.value):
            lines.append(f"## {block.value}")
        else:
            lines.append(_escape_markdown(block.value))
    return "\n\n".join(lines).rstrip() + "\n"
