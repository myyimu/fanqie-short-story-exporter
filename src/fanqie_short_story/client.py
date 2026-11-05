"""Read the detail response used by the public share page."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .link import ShareLink


class DownloadError(Exception):
    """A safe-to-display download failure without URLs or credentials."""


@dataclass(frozen=True)
class Story:
    title: str
    author: str
    post_id: str
    book_id: str
    html_content: str
    plain_content: str


def fetch_story(
    link: ShareLink,
    *,
    timeout: float = 20,
    opener: Callable[..., object] = urlopen,
) -> Story:
    request = Request(
        link.detail_url,
        headers={
            "Accept": "application/json",
            "X-XS-From-Web": "1",
            "Share-Code": link.share_code,
            "Percent": str(link.percent),
            "Referer": link.referer,
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                raise DownloadError(f"站点返回 HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8-sig"))
    except HTTPError as error:
        raise DownloadError(f"站点返回 HTTP {error.code}") from None
    except (URLError, TimeoutError) as error:
        raise DownloadError("连接站点失败或超时") from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DownloadError("站点响应不是有效的 JSON") from error

    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise DownloadError("站点未返回可导出的正文")
    data = payload.get("data")
    if not isinstance(data, dict) or str(data.get("post_id")) != link.post_id:
        raise DownloadError("站点响应的作品 ID 与链接不一致")

    html_content = data.get("html_content")
    text_exts = data.get("text_exts") or []
    plain_content = ""
    if text_exts and isinstance(text_exts[0], dict):
        plain_content = text_exts[0].get("text") or ""
    if not isinstance(html_content, str) or not html_content.strip():
        raise DownloadError("站点响应没有正文")
    if not isinstance(plain_content, str):
        plain_content = ""

    user_info = data.get("user_info") or {}
    if not isinstance(user_info, dict):
        user_info = {}
    return Story(
        title=str(data.get("title") or "未命名短故事"),
        author=str(user_info.get("user_name") or ""),
        post_id=link.post_id,
        book_id=str(data.get("relate_book_id") or ""),
        html_content=html_content,
        plain_content=plain_content,
    )
