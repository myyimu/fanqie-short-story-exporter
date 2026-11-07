"""Read saved EPUB books and export bundles for the Android WebView reader.

Archive members are read in memory with limits. Nothing in a user-selected ZIP is
extracted to the filesystem or passed to the WebView as executable markup.
"""

from __future__ import annotations

import base64
import io
import json
import posixpath
import zipfile
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET


MAX_ARCHIVE_ENTRIES = 500
MAX_ARCHIVE_CONTENTS = 256 * 1024 * 1024
MAX_TEXT_BYTES = 4 * 1024 * 1024
MAX_EPUB_BYTES = 64 * 1024 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024
IMAGE_TYPES = {
    "image/jpeg": "image/jpeg",
    "image/png": "image/png",
    "image/gif": "image/gif",
    "image/webp": "image/webp",
}
SAFE_TAGS = {
    "section", "article", "div", "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "ul", "ol", "li", "strong", "b", "em", "i", "code",
    "pre", "span", "figure", "figcaption", "br", "hr",
}
DROP_TAGS = {"script", "style", "iframe", "object", "embed", "form", "svg", "math"}


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((item for item in element if _local(item.tag) == name), None)


def _safe_path(base: str, href: str) -> tuple[str, str]:
    parts = urlsplit(href)
    if parts.scheme or parts.netloc or (not parts.path and not parts.fragment) or parts.path.startswith("/"):
        raise ValueError("EPUB 包含不支持的资源路径")
    decoded = unquote(parts.path) if parts.path else posixpath.basename(base)
    if "\\" in decoded or "\0" in decoded:
        raise ValueError("EPUB 包含不支持的资源路径")
    path = posixpath.normpath(posixpath.join(posixpath.dirname(base), decoded))
    if path == ".." or path.startswith("../") or path.startswith("/"):
        raise ValueError("EPUB 资源路径超出书籍范围")
    return path, unquote(parts.fragment)


def _check_archive(archive: zipfile.ZipFile) -> None:
    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_ENTRIES:
        raise ValueError("压缩包文件数量过多")
    if sum(item.file_size for item in members) > MAX_ARCHIVE_CONTENTS:
        raise ValueError("压缩包展开后过大")
    names = [item.filename for item in members]
    if len(names) != len(set(names)):
        raise ValueError("压缩包包含重名文件")


def _read(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    try:
        item = archive.getinfo(name)
    except KeyError as error:
        raise ValueError("压缩包缺少必需文件") from error
    if item.file_size > limit:
        raise ValueError("文件过大，请用其他应用打开")
    with archive.open(item) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("文件过大，请用其他应用打开")
    return data


def _xml(data: bytes) -> ET.Element:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("EPUB 包含不支持的 XML 声明")
    return ET.fromstring(data)


def _epub(archive: zipfile.ZipFile) -> dict:
    _check_archive(archive)
    container = _xml(_read(archive, "META-INF/container.xml", MAX_TEXT_BYTES))
    rootfile = next((node for node in container.iter() if _local(node.tag) == "rootfile"), None)
    if rootfile is None:
        raise ValueError("EPUB 缺少书籍目录")
    package_path = rootfile.get("full-path", "")
    package_path, _ = _safe_path("", package_path)
    package = _xml(_read(archive, package_path, MAX_TEXT_BYTES))
    metadata = _child(package, "metadata")
    manifest = _child(package, "manifest")
    spine = _child(package, "spine")
    if manifest is None or spine is None:
        raise ValueError("EPUB 缺少章节清单")

    title = ""
    author = ""
    if metadata is not None:
        for node in metadata:
            if _local(node.tag) == "title" and not title:
                title = "".join(node.itertext()).strip()
            if _local(node.tag) == "creator" and not author:
                author = "".join(node.itertext()).strip()
    items: dict[str, dict] = {}
    images: dict[str, str] = {}
    nav_path = ""
    for node in manifest:
        if _local(node.tag) != "item":
            continue
        item_id = node.get("id", "")
        href = node.get("href", "")
        if not item_id or not href:
            continue
        path, _ = _safe_path(package_path, href)
        media = node.get("media-type", "")
        items[item_id] = {"path": path, "media": media}
        if media in IMAGE_TYPES:
            images[path] = media
        if "nav" in node.get("properties", "").split():
            nav_path = path

    toc: dict[str, list[tuple[str, str]]] = {}
    if nav_path:
        navigation = _xml(_read(archive, nav_path, MAX_TEXT_BYTES))
        nav = next((node for node in navigation.iter()
                    if _local(node.tag) == "nav"
                    and any(_local(key) == "type" and "toc" in value.split()
                            for key, value in node.attrib.items())), None)
        if nav is not None:
            for link in nav.iter():
                if _local(link.tag) != "a" or not link.get("href"):
                    continue
                try:
                    path, anchor = _safe_path(nav_path, link.get("href", ""))
                except ValueError:
                    continue
                label = "".join(link.itertext()).strip()
                if label:
                    toc.setdefault(path, []).append((anchor, label[:120]))

    chapters = []
    for ref in spine:
        if _local(ref.tag) != "itemref" or ref.get("linear", "yes") == "no":
            continue
        item = items.get(ref.get("idref", ""))
        if not item or item["media"] not in {"application/xhtml+xml", "text/html"}:
            continue
        path = item["path"]
        for anchor, label in toc.get(path, [("", posixpath.basename(path))]):
            chapters.append({"path": path, "anchor": anchor, "label": label})
    if not chapters:
        raise ValueError("EPUB 没有可阅读的章节")
    return {"title": title or "未命名书籍", "author": author,
            "chapters": chapters, "images": images}


def _zip_entries(archive: zipfile.ZipFile) -> list[dict]:
    _check_archive(archive)
    entries = []
    for item in archive.infolist():
        if item.is_dir():
            continue
        lower = item.filename.lower()
        kind = ("epub" if lower.endswith(".epub") else
                "md" if lower.endswith((".md", ".markdown")) else
                "txt" if lower.endswith(".txt") else "")
        if kind:
            entries.append({"name": item.filename, "type": kind, "size": item.file_size})
    return entries


def _epub_source(path: str, nested_name: str = "") -> tuple[zipfile.ZipFile, io.BytesIO | None]:
    if not nested_name:
        return zipfile.ZipFile(path), None
    with zipfile.ZipFile(path) as outer:
        _check_archive(outer)
        if not any(item["name"] == nested_name and item["type"] == "epub"
                   for item in _zip_entries(outer)):
            raise ValueError("ZIP 中找不到这本 EPUB")
        data = _read(outer, nested_name, MAX_EPUB_BYTES)
    buffer = io.BytesIO(data)
    return zipfile.ZipFile(buffer), buffer


def _safe_nodes(body: ET.Element, chapter_path: str, images: dict[str, str]) -> tuple[list, list[dict]]:
    image_items: list[dict] = []

    def walk(element: ET.Element) -> dict | None:
        tag = _local(element.tag).lower()
        if tag in DROP_TAGS:
            return None
        if tag == "img":
            try:
                path, _ = _safe_path(chapter_path, element.get("src", ""))
            except ValueError:
                path = ""
            alt = element.get("alt", "插图")[:120]
            if path not in images:
                return {"tag": "span", "children": [f"[图片：{alt}]"], "class": "reader-reference"}
            index = len(image_items)
            image_items.append({"path": path, "mime": images[path]})
            return {"tag": "img", "image": index, "alt": alt}
        rendered_tag = tag if tag in SAFE_TAGS else "span"
        node: dict = {"tag": rendered_tag}
        identifier = element.get("id", "")[:120]
        if identifier:
            node["id"] = identifier
        if rendered_tag not in {"br", "hr"}:
            children: list = []
            if element.text:
                children.append(element.text)
            for child in element:
                rendered = walk(child)
                if rendered is not None:
                    children.append(rendered)
                if child.tail:
                    children.append(child.tail)
            node["children"] = children
        return node

    nodes: list = []
    if body.text:
        nodes.append(body.text)
    for child in body:
        rendered = walk(child)
        if rendered is not None:
            nodes.append(rendered)
        if child.tail:
            nodes.append(child.tail)
    return nodes, image_items


def _inspect(path: str, kind: str, nested_name: str = "") -> dict:
    if kind == "zip" and not nested_name:
        with zipfile.ZipFile(path) as archive:
            return {"kind": "zip", "items": _zip_entries(archive)}
    archive, buffer = _epub_source(path, nested_name)
    try:
        book = _epub(archive)
        return {"kind": "epub", "title": book["title"], "author": book["author"],
                "chapters": [{"label": item["label"]} for item in book["chapters"]]}
    finally:
        archive.close()
        if buffer is not None:
            buffer.close()


def _zip_item(path: str, index: int) -> dict:
    with zipfile.ZipFile(path) as archive:
        entries = _zip_entries(archive)
        if not 0 <= index < len(entries):
            raise ValueError("找不到压缩包中的文件")
        item = entries[index]
        if item["type"] == "epub":
            result = _inspect(path, "epub", item["name"])
            result["name"] = item["name"]
            return result
        raw = _read(archive, item["name"], MAX_TEXT_BYTES)
        return {"kind": "text", "name": item["name"], "type": item["type"],
                "text": raw.decode("utf-8-sig", errors="replace")}


def _chapter(path: str, index: int, nested_name: str = "") -> dict:
    archive, buffer = _epub_source(path, nested_name)
    try:
        book = _epub(archive)
        if not 0 <= index < len(book["chapters"]):
            raise ValueError("找不到这章")
        chapter = book["chapters"][index]
        document = _xml(_read(archive, chapter["path"], MAX_TEXT_BYTES))
        body = next((item for item in document.iter() if _local(item.tag) == "body"), None)
        if body is None:
            raise ValueError("章节没有正文")
        nodes, images = _safe_nodes(body, chapter["path"], book["images"])
        return {"kind": "chapter", "index": index, "anchor": chapter["anchor"],
                "nodes": nodes, "images": images}
    finally:
        archive.close()
        if buffer is not None:
            buffer.close()


def _image(path: str, nested_name: str, image_path: str) -> dict:
    archive, buffer = _epub_source(path, nested_name)
    try:
        book = _epub(archive)
        mime = book["images"].get(image_path)
        if mime not in IMAGE_TYPES:
            raise ValueError("图片不受支持")
        raw = _read(archive, image_path, MAX_IMAGE_BYTES)
        return {"data": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"}
    finally:
        archive.close()
        if buffer is not None:
            buffer.close()


def _reply(action, *args) -> str:
    try:
        return json.dumps(action(*args), ensure_ascii=False)
    except (ValueError, OSError, UnicodeError, zipfile.BadZipFile, ET.ParseError) as error:
        message = str(error) if isinstance(error, ValueError) else "文件不是可读取的 EPUB 或 ZIP"
        return json.dumps({"error": message}, ensure_ascii=False)


def inspect_archive(path: str, kind: str, nested_name: str = "") -> str:
    return _reply(_inspect, path, kind, nested_name)


def read_zip_item(path: str, index: int) -> str:
    return _reply(_zip_item, path, index)


def read_epub_chapter(path: str, index: int, nested_name: str = "") -> str:
    return _reply(_chapter, path, index, nested_name)


def read_epub_image(path: str, nested_name: str, image_path: str) -> str:
    return _reply(_image, path, nested_name, image_path)
