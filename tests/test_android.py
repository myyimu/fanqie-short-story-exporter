"""Exercise the Android boundary without requiring an Android device."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fanqie_short_story.android import prepare_android_export
from fanqie_short_story.web import ExportResult


SHORT_A = "https://changdunovel.com/t/example123/"
SHORT_B = "https://changdunovel.com/t/another456/"


class AndroidExportTests(unittest.TestCase):
    def test_copied_single_story_creates_file(self):
        text = f"推荐一章短篇《示例》{SHORT_A}\u00a0  “"
        result = ExportResult("example.txt", "text/plain", b"story", "示例", "", 5, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.tmp"
            with patch("fanqie_short_story.android.prepare_export", return_value=result) as export:
                response = prepare_android_export(text, "txt", "skip", str(path))
            self.assertEqual(response, ("ok", "example.txt", "text/plain", 5, 0, "示例", ""))
            self.assertEqual(path.read_bytes(), b"story")
            export.assert_called_once_with(SHORT_A, ["txt"], "skip")

    def test_multiple_stories_use_batch_and_keep_limit(self):
        text = f"第一篇：{SHORT_A}。\n第二篇：{SHORT_B}！"
        result = ExportResult("stories.zip", "application/zip", b"zip", "合集", "", 8, 0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.tmp"
            with patch("fanqie_short_story.android.prepare_batch_export", return_value=result) as export:
                response = prepare_android_export(text, "txt,epub", "remote", str(path))
            self.assertEqual(response[:3], ("ok", "stories.zip", "application/zip"))
            export.assert_called_once_with([SHORT_A, SHORT_B], ["txt", "epub"], "remote")

    def test_missing_link_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.tmp"
            response = prepare_android_export("只有标题，没有链接", "txt", "skip", str(path))
            self.assertEqual(response[0], "error")
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
