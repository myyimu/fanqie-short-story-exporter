"""Command line interface."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

from . import __version__
from .assets import download_images
from .client import DownloadError, fetch_story
from .link import ShareLink
from .render import parse_blocks, render_markdown, render_txt


def safe_stem(title: str, post_id: str) -> str:
    normalized = unicodedata.normalize("NFKC", title)
    stem = re.sub(r'[/\\<>:"|?*\x00-\x1f]', "_", normalized).strip(" ._")
    stem = re.sub(r"\s+", " ", stem)[:72].rstrip(" .") or "short-story"
    if stem.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        stem += "_"
    return f"{stem}-{post_id}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fanqie-short-story",
        description="将番茄短故事分享链接当前返回的正文导出为 TXT、Markdown。",
    )
    parser.add_argument("url", help="短故事分享链接；用 - 从标准输入读取")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path.cwd(), help="保存目录")
    parser.add_argument("-f", "--format", action="append", choices=("txt", "md"), help="输出格式，可重复；默认两种")
    parser.add_argument("--images", choices=("remote", "download", "skip"), default="remote", help="Markdown 插图处理方式")
    parser.add_argument("--timeout", type=float, default=20, help="单次请求超时秒数")
    parser.add_argument("--force", action="store_true", help="覆盖同名文件")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    formats = list(dict.fromkeys(args.format or ["txt", "md"]))
    raw_url = sys.stdin.readline().strip() if args.url == "-" else args.url

    try:
        link = ShareLink.parse(raw_url)
        story = fetch_story(link, timeout=args.timeout)
        blocks = parse_blocks(story.html_content)
        if not any(block.kind == "text" for block in blocks):
            raise DownloadError("页面没有可导出的文字正文")

        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = safe_stem(story.title, story.post_id)
        targets = {fmt: output_dir / f"{stem}.{fmt}" for fmt in formats}
        if not args.force:
            existing = [path.name for path in targets.values() if path.exists()]
            if existing:
                raise DownloadError("文件已存在；如需覆盖请加 --force")

        if args.images == "skip":
            blocks = [block for block in blocks if block.kind != "image"]
        image_paths = {}
        if args.images == "download" and "md" in formats:
            image_paths = download_images(blocks, output_dir, stem, timeout=args.timeout)

        if "txt" in targets:
            targets["txt"].write_text(render_txt(story, blocks), encoding="utf-8")
        if "md" in targets:
            targets["md"].write_text(render_markdown(story, blocks, image_paths), encoding="utf-8")
    except (ValueError, DownloadError, OSError) as error:
        print(f"导出失败：{error}", file=sys.stderr)
        return 1

    print(f"已导出：{story.title}（{len(story.plain_content)} 字符）")
    for path in targets.values():
        print(path)
    return 0
