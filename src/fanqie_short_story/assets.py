"""Optional local copies of images already present in a share response."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .client import DownloadError
from .limits import MAX_OFFLINE_IMAGE_BYTES
from .render import Block


MAX_IMAGE_BYTES = 12 * 1024 * 1024
ALLOWED_IMAGE_HOSTS = ("fqnovelpic.com", "byteimg.com")


def _allowed_image_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and parsed.port is None and any(
        host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_IMAGE_HOSTS
    )


def download_images(
    blocks: list[Block],
    output_dir: Path,
    stem: str,
    *,
    timeout: float = 20,
    opener: Callable[..., object] = urlopen,
    max_total_bytes: int = MAX_OFFLINE_IMAGE_BYTES,
) -> dict[int, str]:
    asset_dir = output_dir / f"{stem}_assets"
    paths: dict[int, str] = {}
    image_number = 0
    total_bytes = 0
    for block in blocks:
        if block.kind != "image":
            continue
        image_number += 1
        if not _allowed_image_url(block.value):
            raise DownloadError(f"插图 {image_number} 的来源不是受支持的图片站点")
        request = Request(block.value, headers={"Accept": "image/*"})
        try:
            with opener(request, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
                if not content_type.startswith("image/"):
                    raise DownloadError(f"插图 {image_number} 的响应不是图片")
                data = response.read(MAX_IMAGE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError) as error:
            raise DownloadError(f"插图 {image_number} 下载失败") from error
        if len(data) > MAX_IMAGE_BYTES:
            raise DownloadError(f"插图 {image_number} 超过大小限制")
        total_bytes += len(data)
        if total_bytes > max_total_bytes:
            raise DownloadError("离线插图总量超过大小限制")
        extension = mimetypes.guess_extension(content_type) or ".img"
        if extension == ".jpe":
            extension = ".jpg"
        asset_dir.mkdir(parents=True, exist_ok=True)
        filename = f"image-{image_number:03d}{extension}"
        (asset_dir / filename).write_bytes(data)
        paths[image_number] = f"{asset_dir.name}/{filename}"
    return paths
