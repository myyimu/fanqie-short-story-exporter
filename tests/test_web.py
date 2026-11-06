import io
import json
import sys
import tempfile
import threading
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fanqie_short_story.client import DownloadError, Story
from fanqie_short_story.cli import main as cli_main
from fanqie_short_story.web import LocalServer, prepare_batch_export, prepare_export


LINK = (
    "https://changdunovel.com/ug/pages/short-story-share"
    "?post_id=123456&post_type=13&aid=1967&update_version_code=74332"
    "&forum_book_id=0&percent=30&share_code=test%3D"
    "&user_id=private-user&did=private-device&share_token=private-token"
)
HTML = '<p>开头。</p><p><img src="https://p3-reading-sign.fqnovelpic.com/image.jpg"></p><p>结尾。</p>'
STORY = Story("示例故事", "作者", "123456", "789", HTML, "开头。结尾。")
SECOND_LINK = LINK.replace("post_id=123456", "post_id=654321")
SECOND_STORY = Story("第二篇", "作者二", "654321", "987", "<p>第二篇正文。</p>", "第二篇正文。")


def fake_images(_blocks, output_dir, stem, *, timeout):
    relative = f"{stem}_assets/image-001.jpg"
    target = output_dir / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"image-bytes")
    return {1: relative}


class PrepareExportTests(unittest.TestCase):
    def test_single_text_is_direct_download_without_link_identifiers(self):
        with patch("fanqie_short_story.exporter.fetch_story", return_value=STORY) as fetch:
            result = prepare_export(LINK, ["txt"], "remote")
        self.assertEqual(fetch.call_args.args[0].percent, 100)
        self.assertEqual(result.name, "示例故事-123456.txt")
        self.assertIn("开头。", result.data.decode("utf-8"))
        self.assertNotIn(b"private-token", result.data)

    def test_two_formats_and_offline_image_form_zip(self):
        with patch("fanqie_short_story.exporter.fetch_story", return_value=STORY):
            with patch("fanqie_short_story.exporter.download_images", side_effect=fake_images):
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
        with patch("fanqie_short_story.exporter.fetch_story") as fetch:
            for formats, images in (([], "remote"), (["txt", "txt"], "remote"), (["md"], [])):
                with self.assertRaises(ValueError):
                    prepare_export(LINK, formats, images)
            fetch.assert_not_called()

    def test_web_and_cli_export_identical_files_with_offline_image(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("fanqie_short_story.exporter.fetch_story", return_value=STORY):
                with patch("fanqie_short_story.exporter.download_images", side_effect=fake_images):
                    web_result = prepare_export(LINK, ["txt", "md"], "download")
                    with redirect_stdout(io.StringIO()):
                        cli_code = cli_main(
                            [LINK, "--output-dir", directory, "--images", "download"]
                        )
            self.assertEqual(cli_code, 0)
            with zipfile.ZipFile(io.BytesIO(web_result.data)) as bundle:
                self.assertEqual(len(bundle.namelist()), 3)
                for filename in bundle.namelist():
                    self.assertEqual(bundle.read(filename), (Path(directory) / filename).read_bytes())

    def test_epub_is_direct_download_with_valid_package_and_no_remote_image(self):
        story = Story("示例 & 故事", "作者", "123456", "789", HTML, "开头。结尾。")
        with patch("fanqie_short_story.exporter.fetch_story", return_value=story):
            result = prepare_export(LINK, ["epub"], "remote")
        self.assertEqual(result.content_type, "application/epub+zip")
        self.assertTrue(result.name.endswith(".epub"))
        with zipfile.ZipFile(io.BytesIO(result.data)) as bundle:
            self.assertEqual(bundle.namelist()[0], "mimetype")
            self.assertEqual(bundle.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
            self.assertEqual(bundle.read("mimetype"), b"application/epub+zip")
            package = ET.fromstring(bundle.read("OEBPS/content.opf"))
            chapter = ET.fromstring(bundle.read("OEBPS/chapter.xhtml"))
            ET.fromstring(bundle.read("OEBPS/nav.xhtml"))
            self.assertEqual(chapter.find(".//{http://www.w3.org/1999/xhtml}h1").text, story.title)
            self.assertIsNotNone(package.find(".//{http://www.idpf.org/2007/opf}spine"))
            self.assertIn("[插图 1]", bundle.read("OEBPS/chapter.xhtml").decode("utf-8"))
            self.assertNotIn(b"private-token", result.data)
            self.assertNotIn(b"https://p3-reading-sign", result.data)

    def test_epub_embeds_downloaded_image_without_separate_assets(self):
        with patch("fanqie_short_story.exporter.fetch_story", return_value=STORY):
            with patch("fanqie_short_story.exporter.download_images", side_effect=fake_images):
                result = prepare_export(LINK, ["epub"], "download")
        self.assertTrue(result.name.endswith(".epub"))
        with zipfile.ZipFile(io.BytesIO(result.data)) as bundle:
            self.assertEqual(bundle.read("OEBPS/images/image-001.jpg"), b"image-bytes")
            self.assertIn(b'images/image-001.jpg', bundle.read("OEBPS/chapter.xhtml"))
            self.assertIn(b'image/jpeg', bundle.read("OEBPS/content.opf"))

    def test_batch_exports_two_stories_into_one_zip(self):
        with patch("fanqie_short_story.exporter.fetch_story", side_effect=[STORY, SECOND_STORY]):
            result = prepare_batch_export([LINK, SECOND_LINK], ["txt", "epub"], "skip")
        self.assertEqual(result.content_type, "application/zip")
        self.assertEqual(result.failures, 0)
        with zipfile.ZipFile(io.BytesIO(result.data)) as bundle:
            names = bundle.namelist()
            self.assertEqual(sum(name.endswith(".txt") for name in names), 2)
            self.assertEqual(sum(name.endswith(".epub") for name in names), 2)
            self.assertNotIn("export-report.txt", names)

    def test_batch_reports_failure_by_position_without_link(self):
        with patch("fanqie_short_story.exporter.fetch_story", side_effect=[STORY, DownloadError("站点未返回正文")]):
            result = prepare_batch_export([LINK, SECOND_LINK], ["txt"], "remote")
        self.assertEqual(result.failures, 1)
        with zipfile.ZipFile(io.BytesIO(result.data)) as bundle:
            report = bundle.read("export-report.txt").decode("utf-8")
            self.assertEqual(sum(name.endswith(".txt") for name in bundle.namelist()), 2)
            self.assertIn("第 2 条", report)
            self.assertNotIn("private-token", report)
            self.assertNotIn("post_id=", report)

    def test_batch_skips_duplicate_link_without_refetching(self):
        with patch("fanqie_short_story.exporter.fetch_story", return_value=STORY) as fetch:
            result = prepare_batch_export([LINK, LINK], ["txt"], "remote")
        self.assertEqual(fetch.call_count, 1)
        with zipfile.ZipFile(io.BytesIO(result.data)) as bundle:
            self.assertIn("重复链接", bundle.read("export-report.txt").decode("utf-8"))

    def test_batch_rejects_too_many_links_before_fetch(self):
        with patch("fanqie_short_story.exporter.fetch_story") as fetch:
            with self.assertRaises(ValueError):
                prepare_batch_export([LINK] * 11, ["txt"], "remote")
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
        self.assertIn('value="epub"', html)

        with patch("fanqie_short_story.exporter.fetch_story") as fetch:
            for path, data in (
                ("/api/export", {"url": LINK, "formats": ["txt"], "images": "remote"}),
                ("/api/export-batch", {"urls": [LINK, SECOND_LINK], "formats": ["txt"], "images": "remote"}),
            ):
                request = Request(
                    self.server.origin + path,
                    data=json.dumps(data).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Origin": "https://example.com",
                        "X-Local-Token": self.server.token,
                    },
                    method="POST",
                )
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
        with patch("fanqie_short_story.exporter.fetch_story", return_value=STORY):
            with urlopen(request, timeout=5) as response:
                content = response.read()
                headers = str(response.headers)
                self.assertEqual(response.status, 200)
        self.assertIn("开头。", content.decode("utf-8"))
        self.assertNotIn("private-token", headers)
        self.assertNotIn(b"private-token", content)

    def test_same_origin_batch_request_returns_zip(self):
        request = Request(
            self.server.origin + "/api/export-batch",
            data=json.dumps({"urls": [LINK, SECOND_LINK], "formats": ["txt"], "images": "skip"}).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": self.server.origin,
                "X-Local-Token": self.server.token,
            },
            method="POST",
        )
        with patch("fanqie_short_story.exporter.fetch_story", side_effect=[STORY, SECOND_STORY]):
            with urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), "application/zip")
                self.assertEqual(response.headers.get("X-Export-Failures"), "0")
                data = response.read()
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            self.assertEqual(len(bundle.namelist()), 2)
        self.assertNotIn(b"private-token", data)

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
