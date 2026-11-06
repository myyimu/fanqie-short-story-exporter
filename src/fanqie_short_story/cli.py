"""Command line interface."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import __version__
from .client import DownloadError
from .exporter import load_export, render_export, safe_stem


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fanqie-short-story",
        description="将番茄短故事分享链接当前返回的正文导出为 TXT、Markdown 或 EPUB。",
    )
    parser.add_argument("url", help="短故事分享链接；用 - 从标准输入读取")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path.cwd(), help="保存目录")
    parser.add_argument("-f", "--format", action="append", choices=("txt", "md", "epub"), help="输出格式，可重复；默认 TXT 和 Markdown")
    parser.add_argument("--images", choices=("remote", "download", "skip"), default="remote", help="Markdown/EPUB 插图处理方式")
    parser.add_argument("--timeout", type=float, default=20, help="单次请求超时秒数")
    parser.add_argument("--force", action="store_true", help="覆盖同名文件")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    formats = list(dict.fromkeys(args.format or ["txt", "md"]))
    raw_url = sys.stdin.readline().strip() if args.url == "-" else args.url

    try:
        job = load_export(raw_url, formats, args.images, timeout=args.timeout)
        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        targets = {fmt: output_dir / f"{job.stem}.{fmt}" for fmt in formats}
        if not args.force:
            existing = [path.name for path in targets.values() if path.exists()]
            if existing:
                raise DownloadError("文件已存在；如需覆盖请加 --force")

        with render_export(job) as files:
            for relative_path, source in files.images.items():
                destination = output_dir / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            for filename, content in files.text.items():
                (output_dir / filename).write_bytes(content)
    except (ValueError, DownloadError, OSError) as error:
        print(f"导出失败：{error}", file=sys.stderr)
        return 1

    print(f"已导出：{job.story.title}（{job.characters} 字符）")
    for path in targets.values():
        print(path)
    return 0
