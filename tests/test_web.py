import io
import json
import sys
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fanqie_short_story.client import Story
from fanqie_short_story.web import LocalServer, prepare_export


LINK = (
    "https://changdunovel.com/ug/pages/short-story-share"
    "?post_id=123456&post_type=13&aid=1967&update_version_code=74332"
    "&forum_book_id=0&percent=30&share_code=test%3D"
    "&user_id=private-user&did=private-device&share_token=private-token"
)
HTML = '<p>开头。</p><p><img src="https://p3-reading-sign.fqnovelpic.com/image.jpg"></p><p>结尾。</p>'
STORY = Story("示例故事", "作者", "123456", "789", HTML, "开头。结尾。")


class PrepareExportTests(unittest.TestCase):
    def test_single_text_is_direct_download_without_link_identifiers(self):
        with patch("fanqie_short_story.web.fetch_story", return_value=STORY) as fetch:
            result = prepare_export(LINK, ["txt"], "remote")
        self.assertEqual(fetch.call_args.args[0].percent, 100)
        self.assertEqual(result.name, "示例故事-123456.txt")
        self.assertIn("开头。", result.data.decode("utf-8"))
        self.assertNotIn(b"private-token", result.data)

    def test_two_formats_and_offline_image_form_zip(self):
        def fake_images(_blocks, output_dir, stem):
            relative = f"{stem}_assets/image-001.jpg"
            target = output_dir / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(b"image-bytes")
            return {1: relative}

        with patch("fanqie_short_story.web.fetch_story", return_value=STORY):
            with patch("fanqie_short_story.web.download_images", side_effect=fake_images):
                result = prepare_export(LINK, ["txt", "md"], "download")
        self.assertTrue(result.name.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(result.data)) as bundle:
            names = bundle.namelist()
            self.assertEqual(len(names), 3)
            self.assertTrue(any(name.endswith(".txt") for name in names))
            markdown = next(name for name in names if name.endswith(".md"))
            self.assertIn("_assets/image-001.jpg", bundle.read(markdown).decode("utf-8"))
            self.assertIn(b"image-bytes", bundle.read(next(name for name in names if name.endswith(".jpg"))))

    def test_invalid_options_are_rejected_before_fetch(self):
        with patch("fanqie_short_story.web.fetch_story") as fetch:
            for formats, images in (([], "remote"), (["txt", "txt"], "remote"), (["md"], [])):
                with self.assertRaises(ValueError):
                    prepare_export(LINK, formats, images)
            fetch.assert_not_called()


class LocalServerTests(unittest.TestCase):
    def setUp(self):
        self.server = LocalServer(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_page_has_token_and_rejects_cross_origin_export(self):
        with urlopen(self.server.origin, timeout=5) as response:
            html = response.read().decode("utf-8")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn(self.server.token, html)
        self.assertIn("仅供学习与技术研究", html)

        request = Request(
            self.server.origin + "/api/export",
            data=json.dumps({"url": LINK, "formats": ["txt"], "images": "remote"}).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": "https://example.com",
                "X-Local-Token": self.server.token,
            },
            method="POST",
        )
        with patch("fanqie_short_story.web.fetch_story") as fetch:
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=5)
            self.assertEqual(error.exception.code, 403)
            fetch.assert_not_called()

    def test_same_origin_request_downloads_without_echoing_private_url(self):
        request = Request(
            self.server.origin + "/api/export",
            data=json.dumps({"url": LINK, "formats": ["md"], "images": "skip"}).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": self.server.origin,
                "X-Local-Token": self.server.token,
            },
            method="POST",
        )
        with patch("fanqie_short_story.web.fetch_story", return_value=STORY):
            with urlopen(request, timeout=5) as response:
                content = response.read()
                headers = str(response.headers)
                self.assertEqual(response.status, 200)
        self.assertIn("开头。", content.decode("utf-8"))
        self.assertNotIn("private-token", headers)
        self.assertNotIn(b"private-token", content)

    def test_shutdown_requires_same_origin_and_token(self):
        rejected = Request(
            self.server.origin + "/api/shutdown",
            data=b"",
            headers={"Origin": "https://example.com", "X-Local-Token": self.server.token},
            method="POST",
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(rejected, timeout=5)
        self.assertEqual(error.exception.code, 403)
        self.assertTrue(self.thread.is_alive())

        accepted = Request(
            self.server.origin + "/api/shutdown",
            data=b"",
            headers={"Origin": self.server.origin, "X-Local-Token": self.server.token},
            method="POST",
        )
        with urlopen(accepted, timeout=5) as response:
            self.assertEqual(response.status, 200)
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())


if __name__ == "__main__":
    unittest.main()
