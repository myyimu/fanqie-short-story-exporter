# Fanqie Short Story Exporter

[![最新版本](https://img.shields.io/github/v/release/myyimu/fanqie-short-story-exporter?label=release)](https://github.com/myyimu/fanqie-short-story-exporter/releases/latest)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![MIT License](https://img.shields.io/badge/license-MIT-6C7C59)](LICENSE)

**番茄短篇下载器**：将你有权访问的番茄小说短故事分享页内容保存为 UTF-8 TXT 或 Markdown。无需登录账号；粘贴链接、选择格式、点击下载。支持本机浏览器界面和命令行。

![Fanqie Short Story Exporter 项目封面](docs/images/cover.png)

## 快速开始

### Windows：下载免安装版

1. [下载 Windows ZIP](https://github.com/myyimu/fanqie-short-story-exporter/releases/download/v0.2.0/FanqieShortStoryExporter-0.2.0-Windows.zip) 并解压。
2. 双击 `FanqieShortStoryExporter.exe`。程序会自动在浏览器中打开本机界面，无需另装 Python。
3. 用完后点击界面右上角的「退出」。当前 EXE 未做代码签名，运行前请核对下载来源。

### 从源码运行

需要 Python 3.10 或更新版本。点击仓库的 **Code → Download ZIP** 下载源码并解压，在项目目录打开终端，运行：

```bash
python -m pip install -e .
fanqie-short-story-ui
```

浏览器会自动打开本机页面。如果没有打开，请访问终端显示的地址。默认地址是 `http://127.0.0.1:8765`；端口被占用时可运行 `fanqie-short-story-ui --port 0`。界面只监听本机。

要自己制作 Windows EXE，可在 PowerShell 中运行 `.\packaging\build_windows.ps1`；详见 [打包说明](packaging/README.md)。

## 界面预览

![Fanqie Short Story Exporter 桌面界面，左侧填写分享链接和导出选项，右侧显示书本预览](docs/images/desktop.png)

## 使用教程

1. 复制一条番茄短故事分享链接，页面地址应以 `https://changdunovel.com/ug/pages/short-story-share` 开头。将完整链接粘贴到「短故事分享链接」输入框。
2. 选择 TXT、Markdown 或两者；再选择正文图片的处理方式。默认同时生成 TXT 和 Markdown，并在 Markdown 中保留在线图片地址。
3. 点击「下载故事」。文件由浏览器保存到你的下载目录：只选一种文本格式时直接下载该文件；同时选两种格式或选择「下载图片」时下载 ZIP。

TXT 无法嵌入图片，会标记图片在正文中的位置。若只选择 TXT，「下载图片」不可选。在线图片地址可能过期；需要离线阅读图片时，请选择 Markdown 和「下载图片」（界面最多支持 12 张正文图片）。下载完成后可点「再次下载」，结束使用时点右上角「退出」。

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
```

图片选项为 `remote`（默认，保留在线地址）、`download`（下载到本地）和 `skip`（不保留图片）。已有同名文件时，命令行会停止；确认覆盖时可加 `--force`。完整参数可运行 `fanqie-short-story --help` 查看。

## 使用范围与注意事项

- 一次处理一条 `changdunovel.com` 短故事分享链接。工具使用链接原有的 `percent` 值；站点返回多少内容，就导出多少，不能据此保证一定是全文。
- 无需登录或提供账号密码，不读取浏览器 Cookie；不模拟广告解锁，不绕过付费、访问控制或反爬，也不提供批量发现功能。
- 程序不会主动记录分享链接，导出文件也不包含原链接。粘贴时输入框会显示完整链接，请勿在截图中公开个人或设备标识。

## 免责声明

**无需登录不等于无封号风险。** 工具仍会访问平台，不能保证账号、设备或访问权限不会受到限制。下载、保存或传播作品，以及规避广告等行为，可能违反[番茄小说网《用户协议》](https://fanqienovel.com/protocal/agreement)、链接实际来源平台（如红果）的适用协议或版权规则。

本项目是非官方开源工具，与番茄小说、红果无关联，仅供学习与技术研究。请只处理你有权访问和保存的内容；安装使用前自行核对平台规则并评估风险，不要未经授权传播作品文本。

## 开发与许可

```bash
python -m unittest discover -s tests -v
```

项目采用 [MIT 许可证](LICENSE)。网络接口由平台维护，字段或访问方式可能变化；遇到错误时工具会停止，不会自动重试或改变链接参数。
