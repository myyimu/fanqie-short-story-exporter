# Fanqie Short Story Exporter

[![最新版本](https://img.shields.io/github/v/release/myyimu/fanqie-short-story-exporter?label=release)](https://github.com/myyimu/fanqie-short-story-exporter/releases/latest)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![MIT License](https://img.shields.io/badge/license-MIT-6C7C59)](LICENSE)

**番茄短篇下载器**：将你有权访问的番茄小说短故事分享页内容保存为 TXT、Markdown 或 EPUB。无需登录账号；粘贴链接、选择格式、点击下载。支持本机浏览器界面和命令行。

![Fanqie Short Story Exporter 项目封面](docs/images/cover.png)

## 快速开始

### Windows：下载免安装版

1. [下载 Windows ZIP](https://github.com/myyimu/fanqie-short-story-exporter/releases/download/v0.3.0/FanqieShortStoryExporter-0.3.0-Windows.zip) 并解压。
2. 双击 `FanqieShortStoryExporter.exe`。程序会自动在浏览器中打开本机界面，无需另装 Python。
3. 用完后点击界面右上角的「退出」。当前 EXE 未做代码签名，运行前请核对下载来源。

### Android：安装测试版 APK

在 GitHub Actions 的 **Build Android APK** 运行记录中，下载 `fanqie-short-story-android-phone-debug` 构建产物并安装其中的 APK。该手机包仅包含 `arm64-v8a`，支持 Android 7.0 及更新版本的 64 位手机。模拟器另有独立的 `x86_64` 构建产物。此 APK 是用于试用的调试签名版本，正式分发请使用下方固定签名的构建。

仓库另有手动触发的 **Build signed Android APK** 工作流，使用固定的发布签名并校验证书指纹。后续正式版 APK 应从该工作流构建并上传到 GitHub Release；调试版与发布版的签名不同，不能直接覆盖安装。

Android 与桌面版共用同一份页面文件。打开应用后可粘贴分享文案，也可在其他应用中使用「分享」发送给番茄短故事导出器。选择 TXT、Markdown 或 EPUB 后点击「下载故事」，再用系统文件选择器指定保存位置；保存后可从结果卡片打开保存位置。多篇仍限 10 条链接。

Android 0.4.3 起可在「下载记录」阅读已保存的 TXT、Markdown 和 EPUB，也可打开 ZIP 并选择其中的故事、EPUB 或导出报告阅读。EPUB 支持目录、上一章／下一章、内嵌图片和跨重启阅读位置。可添加之前保存的文件；所有格式仍可交给其他应用打开。ZIP 是多篇或多格式导出时生成的合集，不会在应用内自动解压。[阅读功能与限制](docs/android-reading-roadmap.md)。

### 从源码运行

需要 Python 3.10 或更新版本。点击仓库的 **Code → Download ZIP** 下载源码并解压，在项目目录打开终端，运行：

```bash
python -m pip install -e .
fanqie-short-story-ui
```

浏览器会自动打开本机页面。如果没有打开，请访问终端显示的地址。默认地址是 `http://127.0.0.1:8765`；端口被占用时可运行 `fanqie-short-story-ui --port 0`。界面只监听本机。

要自己制作 Windows EXE，可在 PowerShell 中运行 `.\packaging\build_windows.ps1`；详见 [打包说明](packaging/README.md)。

## 界面预览

![桌面界面示例：选择 TXT、Markdown 或 EPUB](docs/images/desktop.png)

## 使用教程

1. 粘贴短故事分享链接或整段分享文案：`/t/.../` 短链接和完整分享页链接都可以；可一次粘贴多篇，最多识别 10 条链接。
2. 选择 TXT、Markdown、EPUB 和正文图片处理方式。界面默认只选 TXT。
3. 点击「下载故事」。单篇单格式且无需附带独立图片文件时直接下载；多格式、多篇，或 Markdown 选择「下载图片」时生成 ZIP。部分作品失败时，ZIP 中会有 `export-report.txt`。

TXT 会标记图片位置；Markdown 可保留在线图片地址。EPUB 默认也标记图片位置，选择「下载图片」后会内嵌图片。浏览器界面每篇最多下载 12 张正文图片。下载完成后可点「再次下载」，结束使用时点右上角「退出」。

## 命令行

安装完成后，在终端运行：

```bash
fanqie-short-story - -o downloads
```

程序会等待你粘贴分享链接并按回车。用 `-` 从标准输入读取链接，可避免链接出现在命令历史和进程参数中。默认同时生成 TXT 和 Markdown，保存到 `downloads` 目录。

```bash
# 只保存 TXT
fanqie-short-story - -o downloads -f txt

# 保存 Markdown，并下载正文图片
fanqie-short-story - -o downloads -f md --images download

# 保存 EPUB，并内嵌正文图片
fanqie-short-story - -o downloads -f epub --images download
```

图片选项为 `remote`（默认）、`download`（下载图片）和 `skip`（不保留图片）。已有同名文件时，命令行会停止；确认覆盖时可加 `--force`。完整参数可运行 `fanqie-short-story --help` 查看。

## 使用范围与注意事项

- 浏览器可顺序处理最多 10 条手动粘贴的 `changdunovel.com` 短故事链接；命令行每次处理一条。下载时将请求中的 `percent` 设为 `100`；仅导出站点实际返回的内容，不保证每条链接都是全文。
- 无需登录或提供账号密码，不读取浏览器 Cookie，也不提供自动发现作品功能。
- 程序不会主动记录分享链接，导出文件也不包含原链接。粘贴时输入框会显示完整链接，请勿在截图中公开个人或设备标识。

## 免责声明

本项目为非官方工具，仅供学习与技术研究。无需登录仍可能受到平台限制；请确认自己有权保存内容，遵守[番茄小说《用户协议》](https://fanqienovel.com/protocal/agreement)等适用协议与版权规定，勿未经授权传播。

## 开发与许可

```bash
python -m unittest discover -s tests -v
```

项目采用 [MIT 许可证](LICENSE)。网络接口由平台维护，字段或访问方式可能变化；遇到错误时工具会停止，不会自动重试。
