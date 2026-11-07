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


def tap(view_id: str) -> None:
    for _ in range(4):
        node = screen().find(f".//node[@resource-id='{PACKAGE}:id/{view_id}']")
        if node is not None:
            left, top, right, bottom = map(int, re.findall(r"\d+", node.attrib["bounds"]))
            adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))
            return
        width, height = map(int, re.findall(r"\d+", adb("shell", "wm", "size").decode())[-2:])
        adb(
            "shell", "input", "swipe", str(width // 2), str(height * 4 // 5),
            str(width // 2), str(height // 5), "350",
        )
    raise AssertionError(f"Missing UI control: {view_id}")


def main() -> None:
    title = screen().find(".//node[@text='番茄短故事导出器']")
    if title is None:
        raise AssertionError("Android main screen did not appear")

    tap("story_input")
    adb("shell", "input", "text", "invalid")
    adb("shell", "input", "keyevent", "4")  # Hide the keyboard.
    tap("export_button")

    expected = "请粘贴番茄短故事分享链接或分享文案"
    for _ in range(12):
        node = screen().find(f".//node[@resource-id='{PACKAGE}:id/status_text']")
        if node is not None and node.attrib.get("text") == expected:
            print("Android UI and packaged Python export bridge responded correctly")
            return
        time.sleep(2)
    raise AssertionError(f"Expected Python validation message; got {node.attrib if node is not None else 'no status'}")


if __name__ == "__main__":
    main()
