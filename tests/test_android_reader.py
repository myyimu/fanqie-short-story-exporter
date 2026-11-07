"""Exercise EPUB navigation and the exact ZIP bundles the Android reader opens."""

from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from fanqie_short_story import android_reader


PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lXcAAAAASUVORK5CYII="
)


def sample_epub() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as book:
        book.writestr("META-INF/container.xml", """
            <container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>
        """)
        book.writestr("OEBPS/content.opf", """
            <package><metadata><title xmlns="http://purl.org/dc/elements/1.1/">测试书</title>
            <creator xmlns="http://purl.org/dc/elements/1.1/">作者</creator></metadata>
            <manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
            <item id="one" href="one.xhtml" media-type="application/xhtml+xml"/>
            <item id="two" href="two.xhtml" media-type="application/xhtml+xml"/>
            <item id="image" href="images/pixel.png" media-type="image/png"/></manifest>
            <spine><itemref idref="one"/><itemref idref="two"/></spine></package>
        """)
        book.writestr("OEBPS/nav.xhtml", """
            <html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>
            <li><a href="one.xhtml">第一章</a></li><li><a href="two.xhtml#second">第二章</a></li>
            </ol></nav></body></html>
        """)
        book.writestr("OEBPS/one.xhtml", "<html><body><h1>开头</h1><p>第一段</p></body></html>")
        book.writestr("OEBPS/two.xhtml", """
            <html><body><h1 id="second">后续</h1><script>alert(1)</script>
            <p>正文<strong>加粗</strong></p><figure><img src="images/pixel.png" alt="插图"/></figure>
            <img src="https://example.com/tracker.png" alt="远程图"/></body></html>
        """)
        book.writestr("OEBPS/images/pixel.png", PIXEL)
    return output.getvalue()


class AndroidReaderTests(unittest.TestCase):
    def test_epub_book_chapter_navigation_and_safe_images(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.epub"
            path.write_bytes(sample_epub())
            metadata = json.loads(android_reader.inspect_archive(str(path), "epub"))
            self.assertEqual(metadata["title"], "测试书")
            self.assertEqual(metadata["author"], "作者")
            self.assertEqual([item["label"] for item in metadata["chapters"]], ["第一章", "第二章"])

            chapter = json.loads(android_reader.read_epub_chapter(str(path), 1))
            self.assertEqual(chapter["anchor"], "second")
            self.assertEqual(chapter["images"], [{"path": "OEBPS/images/pixel.png", "mime": "image/png"}])
            rendered = json.dumps(chapter["nodes"], ensure_ascii=False)
            self.assertIn("正文", rendered)
            self.assertIn("加粗", rendered)
            self.assertNotIn("alert(1)", rendered)
            self.assertNotIn("tracker.png", rendered)
            image = json.loads(android_reader.read_epub_image(
                str(path), "", chapter["images"][0]["path"]
            ))
            self.assertEqual(image["data"], "data:image/png;base64," + base64.b64encode(PIXEL).decode())

    def test_zip_inventory_text_report_and_nested_epub(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.zip"
            with zipfile.ZipFile(path, "w") as bundle:
                bundle.writestr("小说.txt", "第一篇内容".encode())
                bundle.writestr("小说.md", "# 第一篇".encode())
                bundle.writestr("小说.epub", sample_epub())
                bundle.writestr("export-report.txt", "第二篇失败".encode())
                bundle.writestr("images/image.png", PIXEL)
            inventory = json.loads(android_reader.inspect_archive(str(path), "zip"))
            self.assertEqual([item["type"] for item in inventory["items"]],
                             ["txt", "md", "epub", "txt"])
            self.assertEqual(json.loads(android_reader.read_zip_item(str(path), 0))["text"], "第一篇内容")
            self.assertEqual(json.loads(android_reader.read_zip_item(str(path), 3))["text"], "第二篇失败")
            nested = json.loads(android_reader.read_zip_item(str(path), 2))
            self.assertEqual(nested["kind"], "epub")
            self.assertEqual(nested["title"], "测试书")
            chapter = json.loads(android_reader.read_epub_chapter(str(path), 1, "小说.epub"))
            self.assertEqual(chapter["anchor"], "second")
            image = json.loads(android_reader.read_epub_image(
                str(path), "小说.epub", chapter["images"][0]["path"]
            ))
            self.assertTrue(image["data"].startswith("data:image/png;base64,"))

    def test_missing_epub_files_and_escaping_path_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.epub"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("META-INF/container.xml",
                                 '<container><rootfile full-path="../../outside.opf"/></container>')
            result = json.loads(android_reader.inspect_archive(str(path), "epub"))
            self.assertIn("error", result)
            self.assertIn("范围", result["error"])


if __name__ == "__main__":
    unittest.main()
