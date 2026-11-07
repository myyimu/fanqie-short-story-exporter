"""Exercise the Android UI and its packaged Python bridge in CI."""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path


PACKAGE = "com.myyimu.fanqiestory"


def adb(*args: str) -> bytes:
    return subprocess.check_output(["adb", *args])


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


def main() -> None:
    for _ in range(12):
        root = screen()
        if any(node.attrib.get("text") == "下载故事" for node in root.iter("node")):
            break
        time.sleep(1)
    else:
        raise AssertionError("Android export screen did not load")
    tap_text("下载记录", direction="up")
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
    tap_text("添加已有文件")
    tap_text("Show roots")
    tap_text("Downloads")
    tap_text("fanqie-reader-smoke.txt", exact_text=True)
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
    tap_text("下载记录", direction="up", attempts=12)
    tap_text("阅读", attempts=12, button_only=True)
    for _ in range(10):
        root = screen()
        if any("持久阅读验证" in node.attrib.get("text", "") for node in root.iter("node")):
            break
        time.sleep(1)
    else:
        raise AssertionError("Imported TXT could not be read after restarting the app")
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
