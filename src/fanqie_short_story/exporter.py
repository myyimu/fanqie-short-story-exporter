"""Shared story loading and rendering for the browser and command line."""

from __future__ import annotations

import re
import tempfile
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .assets import download_images
from .client import DownloadError, Story, fetch_story
from .link import resolve_share_link
from .render import Block, parse_blocks, render_markdown, render_txt


@dataclass(frozen=True)
class ExportJob:
    story: Story
    stem: str
    blocks: tuple[Block, ...]
    formats: tuple[str, ...]
    images: str
    characters: int
    timeout: float


@dataclass(frozen=True)
class ExportFiles:
    text: dict[str, bytes]
    images: dict[str, Path]


def safe_stem(title: str, post_id: str) -> str:
    normalized = unicodedata.normalize("NFKC", title)
    stem = re.sub(r'[/\\<>:"|?*\x00-\x1f]', "_", normalized).strip(" ._")
    stem = re.sub(r"\s+", " ", stem)[:72].rstrip(" .") or "short-story"
    if stem.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        stem += "_"
    return f"{stem}-{post_id}"


def load_export(
    raw_url: object,
    formats: object,
    images: object,
    *,
    timeout: float = 20,
) -> ExportJob:
    """Validate options, fetch once, and prepare the story for either output."""
    if not isinstance(raw_url, str) or not raw_url or len(raw_url) > 16384:
        raise ValueError("请粘贴一条有效的短故事分享链接")
    if (
        not isinstance(formats, (list, tuple))
        or not formats
        or not all(isinstance(value, str) for value in formats)
        or set(formats) - {"txt", "md"}
    ):
        raise ValueError("请选择 TXT 或 Markdown 格式")
    if len(formats) != len(set(formats)) or len(formats) > 2:
        raise ValueError("导出格式重复")
    if not isinstance(images, str) or images not in {"remote", "download", "skip"}:
        raise ValueError("请选择有效的插图方式")

    link = resolve_share_link(raw_url, timeout=timeout)
    story = fetch_story(link, timeout=timeout)
    blocks = parse_blocks(story.html_content)
    if not any(block.kind == "text" for block in blocks):
        raise DownloadError("页面没有可导出的文字正文")
    if images == "skip":
        blocks = [block for block in blocks if block.kind != "image"]

    characters = len(story.plain_content) or sum(
        len(block.value) for block in blocks if block.kind == "text"
    )
    return ExportJob(
        story,
        safe_stem(story.title, story.post_id),
        tuple(blocks),
        tuple(formats),
        images,
        characters,
        timeout,
    )


@contextmanager
def render_export(job: ExportJob, *, max_images: int | None = None) -> Iterator[ExportFiles]:
    """Render text and optional images, keeping temporary images until consumed."""
    with tempfile.TemporaryDirectory(prefix="fanqie-export-") as temporary:
        blocks = list(job.blocks)
        image_paths: dict[int, str] = {}
        if "md" in job.formats and job.images == "download":
            image_count = sum(block.kind == "image" for block in blocks)
            if max_images is not None and image_count > max_images:
                raise DownloadError(f"离线插图最多支持 {max_images} 张")
            image_paths = download_images(
                blocks, Path(temporary), job.stem, timeout=job.timeout
            )

        text_files: dict[str, bytes] = {}
        if "txt" in job.formats:
            text_files[f"{job.stem}.txt"] = render_txt(job.story, blocks).encode("utf-8")
        if "md" in job.formats:
            text_files[f"{job.stem}.md"] = render_markdown(
                job.story, blocks, image_paths
            ).encode("utf-8")
        images = {relative: Path(temporary) / relative for relative in image_paths.values()}
        yield ExportFiles(text_files, images)
