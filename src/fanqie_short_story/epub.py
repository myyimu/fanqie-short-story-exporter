"""Build a small, self-contained EPUB 3 book from one short story."""

from __future__ import annotations

import io
import mimetypes
import re
import uuid
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .client import DownloadError, Story
from .render import Block


SUPPORTED_IMAGES = {"image/gif", "image/jpeg", "image/png", "image/webp"}
MIMETYPE = b"application/epub+zip"


def _xml(value: str) -> str:
    valid = "".join(
        character
        for character in value
        if character in "\t\n\r"
        or 0x20 <= ord(character) <= 0xD7FF
        or 0xE000 <= ord(character) <= 0xFFFD
        or 0x10000 <= ord(character) <= 0x10FFFF
    )
    return escape(valid, quote=True)


def _paragraph(value: str) -> str:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "<p>" + "<br/>".join(_xml(line) for line in lines) + "</p>"


def render_epub(
    story: Story,
    blocks: list[Block],
    image_paths: dict[int, str] | None = None,
    assets_root: Path | None = None,
) -> bytes:
    """Embed downloaded images; otherwise mark their positions without remote URLs."""
    embedded: dict[int, tuple[str, str, Path]] = {}
    if image_paths:
        if assets_root is None:
            raise ValueError("缺少 EPUB 插图目录")
        for number, relative in image_paths.items():
            source = assets_root / relative
            media_type = mimetypes.guess_type(source.name)[0]
            if media_type not in SUPPORTED_IMAGES:
                raise DownloadError(f"插图 {number} 的格式不受 EPUB 支持")
            embedded[number] = (f"images/image-{number:03d}{source.suffix.lower()}", media_type, source)

    title = _xml(story.title)
    author = _xml(story.author)
    body = [f"<h1>{title}</h1>"]
    if author:
        body.append(f"<p class=\"author\">作者：{author}</p>")
    image_number = 0
    for block in blocks:
        if block.kind == "image":
            image_number += 1
            if image_number in embedded:
                href = embedded[image_number][0]
                body.append(f'<figure><img src="{href}" alt="插图 {image_number}"/></figure>')
            else:
                body.append(f"<p>[插图 {image_number}]</p>")
        elif re.fullmatch(r"\d+[.、]", block.value):
            body.append(f"<h2>{_xml(block.value)}</h2>")
        else:
            body.append(_paragraph(block.value))

    chapter = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">'
        f"<head><title>{title}</title></head>"
        f"<body>{''.join(body)}</body></html>"
    )
    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="zh-CN">'
        f"<head><title>目录 · {title}</title></head>"
        '<body><nav epub:type="toc" id="toc"><h1>目录</h1><ol>'
        '<li><a href="chapter.xhtml">正文</a></li></ol></nav></body></html>'
    )
    identifier = uuid.uuid5(uuid.NAMESPACE_URL, f"https://changdunovel.com/post/{story.post_id}")
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    creator = f"<dc:creator>{author}</dc:creator>" if author else ""
    image_manifest = "".join(
        f'<item id="image-{number}" href="{href}" media-type="{media_type}"/>'
        for number, (href, media_type, _) in sorted(embedded.items())
    )
    package = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id" xml:lang="zh-CN">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="book-id">urn:uuid:{identifier}</dc:identifier>'
        f"<dc:title>{title}</dc:title><dc:language>zh-CN</dc:language>{creator}"
        f'<meta property="dcterms:modified">{modified}</meta></metadata>'
        '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>'
        f"{image_manifest}</manifest><spine><itemref idref=\"chapter\"/></spine></package>"
    )
    container = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles></container>'
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        for name, content in (
            ("META-INF/container.xml", container),
            ("OEBPS/content.opf", package),
            ("OEBPS/nav.xhtml", nav),
            ("OEBPS/chapter.xhtml", chapter),
        ):
            archive.writestr(name, content.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        for href, _, source in embedded.values():
            archive.write(source, f"OEBPS/{href}", compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()
