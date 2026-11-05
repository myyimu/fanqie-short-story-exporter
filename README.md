# 番茄短故事导出器

将**你提供的短故事分享链接当前返回的内容**保存成 UTF-8 TXT、Markdown 文件。版本：**0.1.0**。项目代码采用 [MIT 许可证](LICENSE)。

## 安装与使用

需要 Python 3.10 或更新版本。在项目目录执行：

```bash
python -m pip install -e .
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
- 请仅导出你有权保存的内容，勿传播未获授权的作品文本。

## 开发

```bash
python -m unittest discover -s tests -v
```

网络接口由平台维护，字段或访问方式可能变化。遇到错误时工具会停止，不会自动重试或改变链接参数。
