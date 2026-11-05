"""Validate a share link and derive the page's ordinary detail request."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit


SHARE_PATH = "/ug/pages/short-story-share"
DETAIL_PATH = "/reading/ugc/postdata/detail/v1/"
ORIGIN = "https://changdunovel.com"
EXPORT_PERCENT = 100


def _one(query: dict[str, list[str]], name: str, default: str = "") -> str:
    values = query.get(name, [])
    if len(values) > 1:
        raise ValueError(f"链接中的 {name} 参数重复")
    return values[0] if values else default


@dataclass(frozen=True)
class ShareLink:
    post_id: str
    share_code: str
    percent: int
    aid: str
    version_code: str
    forum_book_id: str

    @classmethod
    def parse(cls, raw_url: str) -> "ShareLink":
        parsed = urlsplit(raw_url.strip())
        if parsed.scheme != "https" or parsed.hostname != "changdunovel.com":
            raise ValueError("只支持 changdunovel.com 的 HTTPS 短故事分享链接")
        if parsed.port is not None or parsed.path != SHARE_PATH:
            raise ValueError("链接不是短故事分享页")

        query = parse_qs(parsed.query, keep_blank_values=True)
        if _one(query, "post_type") != "13":
            raise ValueError("链接不是受支持的短故事类型")

        post_id = _one(query, "post_id")
        if not post_id.isascii() or not post_id.isdecimal():
            raise ValueError("链接缺少有效的 post_id")
        share_code = _one(query, "share_code")
        if not share_code or "\r" in share_code or "\n" in share_code:
            raise ValueError("链接缺少有效的分享代码")

        raw_percent = _one(query, "percent")
        try:
            input_percent = int(raw_percent)
        except ValueError as error:
            raise ValueError("链接缺少有效的 percent") from error
        if not 1 <= input_percent <= 100:
            raise ValueError("只接受链接中 1–100 的预览比例")

        aid = _one(query, "aid")
        version_code = _one(query, "update_version_code")
        forum_book_id = _one(query, "forum_book_id", "0")
        for name, value in (
            ("aid", aid),
            ("update_version_code", version_code),
            ("forum_book_id", forum_book_id),
        ):
            if not value.isascii() or not value.isdecimal():
                raise ValueError(f"链接缺少有效的 {name}")

        # Use the full share-page percentage for both the request header and Referer.
        return cls(post_id, share_code, EXPORT_PERCENT, aid, version_code, forum_book_id)

    @property
    def detail_url(self) -> str:
        query = urlencode(
            {
                "aid": self.aid,
                "post_id": self.post_id,
                "source_type": "28",
                "forum_book_id": self.forum_book_id,
                "update_version_code": self.version_code,
            }
        )
        return f"{ORIGIN}{DETAIL_PATH}?{query}"

    @property
    def referer(self) -> str:
        # Keep only fields needed by the share page. Never forward user_id, did,
        # share_token, tracking fields, or a nested redirect URL.
        query = urlencode(
            {
                "post_id": self.post_id,
                "post_type": "13",
                "aid": self.aid,
                "update_version_code": self.version_code,
                "forum_book_id": self.forum_book_id,
                "share_code": self.share_code,
                "percent": self.percent,
            }
        )
        return f"{ORIGIN}{SHARE_PATH}?{query}"
