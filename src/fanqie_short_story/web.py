"""A loopback-only browser interface for the existing exporter."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import tempfile
import threading
import webbrowser
import zipfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import quote

from . import __version__
from .client import DownloadError
from .exporter import load_export, render_export
from .limits import MAX_SINGLE_EXPORT_BYTES


MAX_REQUEST_BYTES = 32 * 1024
MAX_OFFLINE_IMAGES = 12
MAX_BATCH_STORIES = 10
MAX_BATCH_REQUEST_BYTES = 192 * 1024
MAX_BATCH_OUTPUT_BYTES = 64 * 1024 * 1024
STATIC_TYPES = {
    "/app.css": "text/css; charset=utf-8",
    "/app.js": "text/javascript; charset=utf-8",
    "/library.js": "text/javascript; charset=utf-8",
}


@dataclass(frozen=True)
class ExportResult:
    name: str
    content_type: str
    data: bytes
    title: str
    author: str
    characters: int
    failures: int = 0


def prepare_export(raw_url: object, formats: object, images: object) -> ExportResult:
    """Create one downloadable file from the response for the supplied link."""
    job = load_export(raw_url, formats, images)
    with render_export(
        job, max_images=MAX_OFFLINE_IMAGES, max_output_bytes=MAX_SINGLE_EXPORT_BYTES
    ) as exported:
        if len(exported.text) == 1 and not exported.images:
            name, data = next(iter(exported.text.items()))
            content_type = (
                "application/epub+zip" if name.endswith(".epub")
                else "text/markdown; charset=utf-8" if name.endswith(".md")
                else "text/plain; charset=utf-8"
            )
        else:
            name = f"{job.stem}.zip"
            content_type = "application/zip"
            with tempfile.TemporaryFile() as buffer:
                with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                    for filename, content in exported.text.items():
                        bundle.writestr(filename, content)
                    for relative_path, source in exported.images.items():
                        bundle.write(source, arcname=relative_path)
                if buffer.tell() > MAX_SINGLE_EXPORT_BYTES:
                    raise DownloadError("单篇导出超过大小限制")
                buffer.seek(0)
                data = buffer.read()

    if len(data) > MAX_SINGLE_EXPORT_BYTES:
        raise DownloadError("单篇导出超过大小限制")

    return ExportResult(
        name, content_type, data, job.story.title, job.story.author, job.characters
    )


def prepare_batch_export(raw_urls: object, formats: object, images: object) -> ExportResult:
    """Export a small, sequential user-supplied queue as one ZIP."""
    if (
        not isinstance(raw_urls, list)
        or not 2 <= len(raw_urls) <= MAX_BATCH_STORIES
        or not all(isinstance(url, str) and url.strip() for url in raw_urls)
    ):
        raise ValueError(f"请粘贴 2–{MAX_BATCH_STORIES} 条短故事链接，每行一条")

    failures: list[str] = []
    seen_urls: set[str] = set()
    seen_stems: set[str] = set()
    total_bytes = 0
    total_characters = 0
    success_count = 0
    with tempfile.TemporaryFile() as buffer:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for index, raw_url in enumerate(raw_urls, 1):
                try:
                    if raw_url.strip() in seen_urls:
                        failures.append(f"第 {index} 条：重复链接")
                        continue
                    seen_urls.add(raw_url.strip())
                    job = load_export(raw_url, formats, images)
                    if job.stem in seen_stems:
                        failures.append(f"第 {index} 条：重复作品")
                        continue
                    with render_export(
                        job,
                        max_images=MAX_OFFLINE_IMAGES,
                        max_output_bytes=MAX_SINGLE_EXPORT_BYTES,
                    ) as exported:
                        size = sum(len(content) for content in exported.text.values())
                        size += sum(source.stat().st_size for source in exported.images.values())
                        if total_bytes + size > MAX_BATCH_OUTPUT_BYTES:
                            failures.append(f"第 {index} 条：批量文件超过大小限制")
                            continue
                        for filename, content in exported.text.items():
                            bundle.writestr(filename, content)
                        for relative_path, source in exported.images.items():
                            bundle.write(source, arcname=relative_path)
                        total_bytes += size
                    seen_stems.add(job.stem)
                    total_characters += job.characters
                    success_count += 1
                except (ValueError, DownloadError) as error:
                    failures.append(f"第 {index} 条：{error}")
            if not success_count:
                detail = failures[0] if failures else "没有可导出的故事"
                raise DownloadError(f"没有成功导出的故事：{detail}")
            if failures:
                report = f"成功 {success_count} 篇，未完成 {len(failures)} 篇\n\n" + "\n".join(failures) + "\n"
                bundle.writestr("export-report.txt", report.encode("utf-8"))
        if buffer.tell() > MAX_BATCH_OUTPUT_BYTES:
            raise DownloadError("批量文件超过大小限制")
        buffer.seek(0)
        archive_data = buffer.read()

    return ExportResult(
        f"Fanqie-Short-Stories-{success_count}.zip",
        "application/zip",
        archive_data,
        f"已导出 {success_count} 篇故事",
        "",
        total_characters,
        len(failures),
    )


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int = 8765):
        super().__init__(("127.0.0.1", port), LocalHandler)
        self.token = secrets.token_urlsafe(32)
        self.origin = f"http://127.0.0.1:{self.server_port}"


class LocalHandler(BaseHTTPRequestHandler):
    server: LocalServer

    def log_message(self, _format: str, *_args: object) -> None:
        # The submitted URL must never appear in terminal or server logs.
        return

    def _host_is_local(self) -> bool:
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def _send(self, status: int, data: bytes, content_type: str, **headers: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'",
        )
        for name, value in headers.items():
            self.send_header(name.replace("_", "-"), value)
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, message: str) -> None:
        data = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self._send(status, data, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if not self._host_is_local():
            self._error(403, "请求来源无效")
            return
        if self.path == "/":
            html = (
                files("fanqie_short_story")
                .joinpath("web", "index.html")
                .read_text(encoding="utf-8")
                .replace("__LOCAL_TOKEN__", self.server.token)
                .replace("__APP_VERSION__", __version__)
            )
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path in STATIC_TYPES:
            filename = self.path.lstrip("/")
            data = files("fanqie_short_story").joinpath("web", filename).read_bytes()
            self._send(200, data, STATIC_TYPES[self.path])
        else:
            self._error(404, "页面不存在")

    def do_POST(self) -> None:
        if self.path not in {"/api/export", "/api/export-batch", "/api/shutdown"}:
            self._error(404, "接口不存在")
            return
        if (
            not self._host_is_local()
            or self.headers.get("Origin") != self.server.origin
            or self.headers.get("X-Local-Token") != self.server.token
        ):
            self._error(403, "请求来源无效")
            return
        if self.path == "/api/shutdown":
            self._send(200, b'{"ok":true}', "application/json; charset=utf-8")
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self._error(415, "请求格式无效")
            return
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._error(400, "请求长度无效")
            return
        max_size = MAX_BATCH_REQUEST_BYTES if self.path == "/api/export-batch" else MAX_REQUEST_BYTES
        if size <= 0 or size > max_size:
            self._error(413, "链接过长")
            return
        try:
            request = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("请求格式无效")
            if self.path == "/api/export-batch":
                result = prepare_batch_export(
                    request.get("urls"), request.get("formats"), request.get("images")
                )
            else:
                result = prepare_export(
                    request.get("url"), request.get("formats"), request.get("images")
                )
        except (UnicodeError, json.JSONDecodeError):
            self._error(400, "请求格式无效")
            return
        except (ValueError, DownloadError) as error:
            self._error(400, str(error))
            return
        except OSError:
            self._error(500, "保存文件时出错")
            return

        self._send(
            200,
            result.data,
            result.content_type,
            Content_Disposition=f"attachment; filename=download; filename*=UTF-8''{quote(result.name)}",
            X_Download_Name=quote(result.name),
            X_Story_Title=quote(result.title[:120]),
            X_Story_Author=quote(result.author[:120]),
            X_Story_Characters=str(result.characters),
            X_Export_Failures=str(result.failures),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动番茄短故事导出器的本机浏览器界面")
    parser.add_argument("--port", type=int, default=8765, help="本机端口，默认 8765；0 表示随机端口")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--version", action="version", version=f"fanqie-short-story-ui {__version__}")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port 必须在 0–65535 之间")
    try:
        with LocalServer(args.port) as server:
            if sys.stdout is not None:
                print(f"本机界面：{server.origin}", flush=True)
                print("按 Ctrl+C 退出。", flush=True)
            if not args.no_open:
                webbrowser.open(server.origin)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    except OSError:
        if sys.stdout is not None:
            print("本机界面启动失败：端口可能已被占用。可用 --port 0 自动选择端口。")
        elif sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, "本机端口被占用，无法启动。", "番茄短篇下载器", 0)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
