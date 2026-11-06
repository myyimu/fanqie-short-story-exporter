import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fanqie_short_story.assets import download_images
from fanqie_short_story.cli import main, safe_stem
from fanqie_short_story.client import DownloadError, Story, fetch_story
from fanqie_short_story.link import ShareLink, resolve_share_link
from fanqie_short_story.render import parse_blocks, render_markdown, render_txt


LINK = (
    "https://changdunovel.com/ug/pages/short-story-share"
    "?post_id=123456&post_type=13&aid=1967&update_version_code=74332"
    "&forum_book_id=0&percent=30&share_code=test%3D"
    "&user_id=private-user&did=private-device&share_token=private-token"
)
SHORT_LINK = "https://changdunovel.com/t/example123/"
HTML = '<p>1.</p><p>第一段。</p><p class="picture"><img src="https://p3-reading-sign.fqnovelpic.com/image.jpg?x=1&amp;y=2"></p><p>结尾。</p>'


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.payload


class FakeImageResponse:
    headers = {"Content-Type": "image/jpeg"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return b"fake-image"


class ShareLinkTests(unittest.TestCase):
    def test_short_link_uses_only_validated_redirect_fields(self):
        with patch("fanqie_short_story.link.build_opener") as build:
            build.return_value.open.side_effect = HTTPError(
                SHORT_LINK, 302, "Found", {"Location": LINK}, None
            )
            link = resolve_share_link(SHORT_LINK)
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, SHORT_LINK)
        self.assertEqual(link.percent, 100)
        for secret in ("private-user", "private-device", "private-token"):
            self.assertNotIn(secret, link.referer)
            self.assertNotIn(secret, link.detail_url)

    def test_short_link_rejects_other_pages(self):
        with patch("fanqie_short_story.link.build_opener") as build:
            build.return_value.open.side_effect = HTTPError(
                SHORT_LINK, 302, "Found", {"Location": "https://changdunovel.com/ug/pages/book-share"}, None
            )
            with self.assertRaises(ValueError):
                resolve_share_link(SHORT_LINK)

    def test_link_requests_100_percent_without_forwarding_tracking(self):
        link = ShareLink.parse(LINK)
        self.assertEqual(link.percent, 100)
        self.assertIn("post_id=123456", link.detail_url)
        self.assertIn("percent=100", link.referer)
        self.assertNotIn("percent=30", link.referer)
        for secret in ("private-user", "private-device", "private-token"):
            self.assertNotIn(secret, link.referer)
            self.assertNotIn(secret, link.detail_url)

    def test_rejects_untrusted_host_and_out_of_range_percent(self):
        with self.assertRaises(ValueError):
            ShareLink.parse(LINK.replace("changdunovel.com", "example.com"))
        with self.assertRaises(ValueError):
            ShareLink.parse(LINK.replace("percent=30", "percent=300"))


class ClientTests(unittest.TestCase):
    def test_fetches_detail_response_with_100_percent_request(self):
        link = ShareLink.parse(LINK)
        seen = {}

        def opener(request, *, timeout):
            seen["headers"] = dict(request.header_items())
            seen["timeout"] = timeout
            return FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "post_id": "123456",
                        "relate_book_id": "789",
                        "title": "示例故事",
                        "user_info": {"user_name": "作者"},
                        "html_content": HTML,
                        "text_exts": [{"text": "1.第一段。结尾。"}],
                    },
                }
            )

        story = fetch_story(link, opener=opener)
        self.assertEqual(story.title, "示例故事")
        self.assertEqual(story.book_id, "789")
        self.assertEqual(seen["headers"]["Percent"], "100")
        self.assertIn("percent=100", seen["headers"]["Referer"])
        self.assertEqual(seen["headers"]["Share-code"], "test=")
        self.assertEqual(seen["timeout"], 20)

    def test_rejects_mismatched_post_id(self):
        link = ShareLink.parse(LINK)

        def opener(*_, **__):
            return FakeResponse({"code": 0, "data": {"post_id": "other"}})

        with self.assertRaises(DownloadError):
            fetch_story(link, opener=opener)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.story = Story("示例故事", "作者", "123456", "789", HTML, "1.第一段。结尾。")

    def test_text_and_markdown_include_story_and_image_position(self):
        blocks = parse_blocks(HTML)
        self.assertEqual([b.kind for b in blocks], ["text", "text", "image", "text"])
        txt = render_txt(self.story, blocks)
        md = render_markdown(self.story, blocks, {1: "assets/image-001.jpg"})
        self.assertIn("第一段。", txt)
        self.assertIn("[插图 1]", txt)
        self.assertIn("## 1.", md)
        self.assertIn("![插图 1](<assets/image-001.jpg>)", md)
        self.assertIn("结尾。", md)

    def test_safe_filename(self):
        self.assertEqual(safe_stem("A/B: C", "123"), "A_B_ C-123")
        self.assertEqual(safe_stem("CON", "123"), "CON_-123")

    def test_local_image_download_uses_safe_filename(self):
        blocks = parse_blocks(HTML)
        with tempfile.TemporaryDirectory() as directory:
            paths = download_images(
                blocks,
                Path(directory),
                "example",
                opener=lambda _request, *, timeout: FakeImageResponse(),
            )
            self.assertEqual(paths, {1: "example_assets/image-001.jpg"})
            self.assertEqual((Path(directory) / paths[1]).read_bytes(), b"fake-image")

    def test_cli_writes_both_files_without_source_url(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("fanqie_short_story.exporter.fetch_story", return_value=self.story) as fetch:
                with redirect_stdout(io.StringIO()):
                    code = main([LINK, "--output-dir", directory])
            self.assertEqual(code, 0)
            self.assertEqual(fetch.call_args.args[0].percent, 100)
            exported = list(Path(directory).iterdir())
            self.assertEqual({p.suffix for p in exported}, {".txt", ".md"})
            for path in exported:
                content = path.read_text(encoding="utf-8")
                self.assertIn("示例故事", content)
                self.assertNotIn("private-token", content)

    def test_cli_accepts_short_story_link(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("fanqie_short_story.link.build_opener") as build:
                build.return_value.open.side_effect = HTTPError(
                    SHORT_LINK, 302, "Found", {"Location": LINK}, None
                )
                with patch("fanqie_short_story.exporter.fetch_story", return_value=self.story):
                    with redirect_stdout(io.StringIO()):
                        code = main([SHORT_LINK, "--output-dir", directory, "-f", "txt"])
            self.assertEqual(code, 0)
            self.assertEqual(len(list(Path(directory).glob("*.txt"))), 1)


if __name__ == "__main__":
    unittest.main()
