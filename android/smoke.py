"""Exercise the Android UI and its packaged Python bridge in CI."""

from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET


PACKAGE = "com.myyimu.fanqiestory"


def adb(*args: str) -> bytes:
    return subprocess.check_output(["adb", *args])


def screen() -> ET.Element:
    subprocess.run(
        ["adb", "shell", "uiautomator", "dump", "/sdcard/window.xml"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return ET.fromstring(adb("shell", "cat", "/sdcard/window.xml"))


def tap_text(label: str) -> None:
    for _ in range(4):
        root = screen()
        for node in root.iter("node"):
            text = node.attrib.get("text", "") + node.attrib.get("content-desc", "")
            if label in text:
                left, top, right, bottom = map(int, re.findall(r"\d+", node.attrib["bounds"]))
                adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))
                return
        width, height = map(int, re.findall(r"\d+", adb("shell", "wm", "size").decode())[-2:])
        adb(
            "shell", "input", "swipe", str(width // 2), str(height * 4 // 5),
            str(width // 2), str(height // 5), "350",
        )
    raise AssertionError(f"Missing UI text: {label}\n{ET.tostring(root, encoding='unicode')}")


def main() -> None:
    tap_text("Fanqie Short Story Exporter")
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
