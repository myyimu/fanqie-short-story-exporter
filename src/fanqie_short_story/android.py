"""Small Android boundary around the shared export pipeline."""

from __future__ import annotations

from pathlib import Path

from .client import DownloadError
from .link import extract_share_urls
from .web import MAX_BATCH_REQUEST_BYTES, MAX_BATCH_STORIES, prepare_batch_export, prepare_export


def prepare_android_export(
    share_text: str, formats_csv: str, images: str, cache_path: str
) -> tuple[str, str, str, int, int]:
    """Export pasted text into an app-owned cache file for Android's file picker.

    The return tuple is (status, name_or_message, MIME type, character count,
    failed story count). Keeping file bytes in Python avoids an extra Java copy.
    """
    try:
        if not isinstance(share_text, str) or len(share_text.encode("utf-8")) > MAX_BATCH_REQUEST_BYTES:
            raise ValueError("分享文案过长")
        urls = extract_share_urls(share_text)
        if not urls:
            raise ValueError("请粘贴番茄短故事分享链接或分享文案")
        if len(urls) > MAX_BATCH_STORIES:
            raise ValueError(f"一次最多处理 {MAX_BATCH_STORIES} 篇故事")

        formats = formats_csv.split(",")
        if len(urls) == 1:
            result = prepare_export(urls[0], formats, images)
        else:
            result = prepare_batch_export(urls, formats, images)
        Path(cache_path).write_bytes(result.data)
        return ("ok", result.name, result.content_type, result.characters, result.failures)
    except (ValueError, DownloadError) as error:
        return ("error", str(error), "", 0, 0)
    except OSError:
        return ("error", "生成文件时出错", "", 0, 0)
    except Exception:
        return ("error", "导出失败，请稍后重试", "", 0, 0)
