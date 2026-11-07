"""Exercise the Android UI and its packaged Python bridge in CI."""

from __future__ import annotations

import re
import io
import os
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


PACKAGE = "com.myyimu.fanqiestory"
SCREENSHOT_DIR = os.environ.get("FANQIE_SCREENSHOT_DIR")


def sample_epub() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as book:
        book.writestr("META-INF/container.xml",
                      '<container><rootfile full-path="OEBPS/content.opf"/></container>')
        book.writestr("OEBPS/content.opf", """
            <package><metadata><title>模拟器测试书</title><creator>测试作者</creator></metadata>
            <manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
            <item id="one" href="one.xhtml" media-type="application/xhtml+xml"/>
            <item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest>
            <spine><itemref idref="one"/><itemref idref="two"/></spine></package>
        """)
        book.writestr("OEBPS/nav.xhtml", """
            <html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>
            <li><a href="one.xhtml">第一章</a></li><li><a href="two.xhtml">第二章</a></li>
            </ol></nav></body></html>
        """)
        book.writestr("OEBPS/one.xhtml", "<html><body><p>模拟器第一章内容</p></body></html>")
        book.writestr("OEBPS/two.xhtml", "<html><body><p>模拟器第二章内容</p></body></html>")
    return output.getvalue()


def adb(*args: str) -> bytes:
    return subprocess.check_output(["adb", *args])


def capture(name: str) -> None:
    if SCREENSHOT_DIR:
        destination = Path(SCREENSHOT_DIR)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / name).write_bytes(adb("exec-out", "screencap", "-p"))


def screen() -> ET.Element:
    for attempt in range(4):
        try:
            subprocess.run(
                ["adb", "shell", "uiautomator", "dump", "/sdcard/window.xml"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            return ET.fromstring(adb("shell", "cat", "/sdcard/window.xml"))
        except subprocess.CalledProcessError:
            if attempt == 3:
                raise
            time.sleep(2)
    raise AssertionError("Could not read Android UI")


def tap_text(
    label: str, direction: str = "down", attempts: int = 4,
    button_only: bool = False, exact_text: bool = False,
) -> None:
    for _ in range(attempts):
        root = screen()
        for node in root.iter("node"):
            if node.attrib.get("class") == "android.webkit.WebView":
                continue
            if button_only and node.attrib.get("class") != "android.widget.Button":
                continue
            if exact_text and node.attrib.get("text") != label:
                continue
            text = node.attrib.get("text", "") + node.attrib.get("content-desc", "")
            if label in text:
                left, top, right, bottom = map(int, re.findall(r"\d+", node.attrib["bounds"]))
                if right <= left or bottom <= top:
                    continue
                adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))
                return
        width, height = map(int, re.findall(r"\d+", adb("shell", "wm", "size").decode())[-2:])
        start, end = (height * 4 // 5, height // 5) if direction == "down" else (height // 5, height * 4 // 5)
        adb(
            "shell", "input", "swipe", str(width // 2), str(start),
            str(width // 2), str(end), "350",
        )
    raise AssertionError(f"Missing UI text: {label}\n{ET.tostring(root, encoding='unicode')}")


def wait_text(label: str, attempts: int = 10) -> None:
    for _ in range(attempts):
        root = screen()
        if any(label in node.attrib.get("text", "") for node in root.iter("node")):
            return
        time.sleep(1)
    raise AssertionError(f"Missing UI text: {label}\n{ET.tostring(root, encoding='unicode')}")


def open_library(expected_file: str | None = None) -> None:
    for _ in range(12):
        root = screen()
        if any("添加已有文件" in node.attrib.get("text", "") for node in root.iter("node")):
            if expected_file is None or any(
                expected_file in node.attrib.get("text", "") for node in root.iter("node")
            ):
                return
            time.sleep(1)
            continue
        try:
            tap_text("下载记录", direction="up", attempts=12, button_only=True, exact_text=True)
        except AssertionError:
            pass
        time.sleep(1)
    raise AssertionError(f"Download library did not show {expected_file or 'its controls'}")


def import_download(name: str) -> None:
    tap_text("添加已有文件")
    root = screen()
    if not any(node.attrib.get("text") == name for node in root.iter("node")):
        tap_text("Show roots")
        tap_text("Downloads")
    tap_text(name, exact_text=True)
    for _ in range(10):
        root = screen()
        if any(node.attrib.get("package") == PACKAGE
               and node.attrib.get("text") == name for node in root.iter("node")):
            return
        time.sleep(1)
    raise AssertionError(f"Imported file did not appear: {name}")


def main() -> None:
    for _ in range(12):
        root = screen()
        if any(node.attrib.get("text") == "下载故事" for node in root.iter("node")):
            break
        time.sleep(1)
    else:
        raise AssertionError("Android export screen did not load")
    capture("01-export.png")
    open_library()
    for _ in range(8):
        root = screen()
        if any("还没有下载记录" in node.attrib.get("text", "") for node in root.iter("node")):
            break
        time.sleep(1)
    else:
        raise AssertionError(
            "Android download library did not show its empty state: "
            + ET.tostring(root, encoding="unicode")
        )
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory) / "fanqie-reader-smoke.txt"
        fixture.write_text("持久阅读验证", encoding="utf-8")
        adb("push", str(fixture), "/sdcard/Download/fanqie-reader-smoke.txt")
        epub = Path(directory) / "fanqie-reader-smoke.epub"
        epub.write_bytes(sample_epub())
        adb("push", str(epub), "/sdcard/Download/fanqie-reader-smoke.epub")
        bundle = Path(directory) / "fanqie-reader-smoke.zip"
        with zipfile.ZipFile(bundle, "w") as archive:
            archive.writestr("压缩书.txt", "包内 TXT 内容".encode())
            archive.writestr("压缩书.epub", sample_epub())
            archive.writestr("export-report.txt", "导出报告内容".encode())
        adb("push", str(bundle), "/sdcard/Download/fanqie-reader-smoke.zip")
    import_download("fanqie-reader-smoke.txt")
    for _ in range(10):
        root = screen()
        if any(
            node.attrib.get("package") == PACKAGE
            and "fanqie-reader-smoke.txt" in node.attrib.get("text", "")
            for node in root.iter("node")
        ):
            break
        time.sleep(1)
    else:
        raise AssertionError("Imported TXT did not appear in the download library: "
            + ET.tostring(root, encoding="unicode"))

    adb("shell", "am", "force-stop", PACKAGE)
    adb("shell", "am", "start", "-W", "-n", f"{PACKAGE}/.MainActivity")
    time.sleep(3)
    open_library("fanqie-reader-smoke.txt")
    tap_text("阅读：fanqie-reader-smoke.txt", attempts=12, button_only=True)
    for _ in range(10):
        root = screen()
        if any("持久阅读验证" in node.attrib.get("text", "") for node in root.iter("node")):
            break
        time.sleep(1)
    else:
        raise AssertionError("Imported TXT could not be read after restarting the app")
    print("TXT persisted across restart and opened")
    tap_text("下载记录", button_only=True)
    import_download("fanqie-reader-smoke.epub")
    tap_text("阅读：fanqie-reader-smoke.epub", button_only=True)
    wait_text("模拟器第一章内容")
    capture("03-epub-reader.png")
    tap_text("下一章", button_only=True)
    wait_text("模拟器第二章内容")
    print("EPUB chapter navigation opened the second chapter")

    adb("shell", "am", "force-stop", PACKAGE)
    adb("shell", "am", "start", "-W", "-n", f"{PACKAGE}/.MainActivity")
    time.sleep(3)
    open_library("fanqie-reader-smoke.epub")
    tap_text("阅读：fanqie-reader-smoke.epub", button_only=True)
    wait_text("模拟器第二章内容")
    print("EPUB reading position persisted across restart")
    tap_text("下载记录", button_only=True)
    import_download("fanqie-reader-smoke.zip")
    capture("02-library.png")
    tap_text("查看内容：fanqie-reader-smoke.zip", button_only=True)
    wait_text("export-report.txt")
    capture("04-zip-contents.png")
    tap_text("阅读：压缩书.epub", button_only=True)
    wait_text("模拟器第一章内容")
    tap_text("压缩包", button_only=True)
    tap_text("阅读：export-report.txt", button_only=True)
    wait_text("导出报告内容")
    print("ZIP inventory, nested EPUB, and export report opened")
    tap_text("返回导出")
    adb(
        "shell", "am", "start", "-W", "-a", "android.intent.action.SEND",
        "-t", "text/plain", "--es", "android.intent.extra.TEXT",
        "https://changdunovel.com/not-a-share/", "-n", f"{PACKAGE}/.MainActivity",
    )
    time.sleep(2)
    tap_text("下载故事")

    expected = "链接不是短故事分享页"
    for _ in range(12):
        root = screen()
        if any(expected in node.attrib.get("text", "") for node in root.iter("node")):
            print("Android UI and packaged Python export bridge responded correctly")
            return
        time.sleep(2)
    raise AssertionError(f"Expected Python validation message; got {ET.tostring(root, encoding='unicode')}")


if __name__ == "__main__":
    main()
