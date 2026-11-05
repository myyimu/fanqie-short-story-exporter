# Fanqie Short Story Exporter

将**你提供的短故事分享链接当前返回的内容**保存成 UTF-8 TXT、Markdown 文件。版本：**0.2.0**。项目代码采用 [MIT 许可证](LICENSE)。

## 图形界面

需要 Python 3.10 或更新版本。在项目目录安装并启动：

```bash
python -m pip install -e .
fanqie-short-story-ui
```

浏览器会自动打开本机界面。粘贴一条分享链接，选择 TXT、Markdown 和正文图片的处理方式，点击「下载故事」。单一文本格式直接下载；同时选择两种格式，或下载图片时，会得到 ZIP 文件包。界面只监听 `127.0.0.1`，不会把分享链接放进浏览器地址栏或导出文件。右上角「退出」可关闭程序；若浏览器没有自动打开，可访问终端显示的本机地址。

## Windows 免安装版

可将图形界面打包为单文件 EXE，双击后自动打开浏览器；打包步骤见 [Windows 说明](packaging/README.md)。

## 命令行

```bash
fanqie-short-story - -o downloads
```

运行后粘贴一条 `https://changdunovel.com/ug/pages/short-story-share?...` 链接并按回车。用 `-` 从标准输入读取链接，可避免它出现在命令历史和进程参数中。默认同时导出 TXT 与 Markdown。

常用选项：

```bash
fanqie-short-story - -o downloads -f txt
fanqie-short-story - -o downloads -f md --images download
fanqie-short-story - -o downloads --force
fanqie-short-story --version
```

`--images remote` 是默认值，Markdown 直接引用页面图片地址；这些地址可能过期。`--images download` 把正文插图保存到相邻的资源目录，更适合离线阅读。`--images skip` 不输出插图。TXT 无法嵌入图片，会用 `[插图 N]` 标明位置。

## 范围

- 支持 `changdunovel.com` 的 `short-story-share` 链接，一次处理一篇。
- 使用链接**原有**的 `percent` 值，不增加预览比例；站点返回多少内容，就导出多少内容。工具不能证明输出一定是全文。
- 不使用登录态、不模拟广告解锁、不绕过访问控制或反爬，不提供批量发现与下载功能。
- 不记录、展示或写入链接中的 `user_id`、`did`、`share_token` 等个人或设备标识。导出文件也不保存原分享链接。
- 本项目仅供学习与技术研究。请仅处理你有权访问和保存的内容，尊重作品版权，并遵守适用法律及平台规则；请勿未经授权传播作品文本。

## 开发

```bash
python -m unittest discover -s tests -v
```

网络接口由平台维护，字段或访问方式可能变化。遇到错误时工具会停止，不会自动重试或改变链接参数。
