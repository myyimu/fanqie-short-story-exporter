# Windows 免安装版

在 Windows PowerShell 中运行：

```powershell
.\packaging\build_windows.ps1
```

首次运行会在 `build/windows/venv` 安装固定版本的 PyInstaller。生成的 `dist/FanqieShortStoryExporter.exe` 可独立运行，不需要目标电脑另装 Python。也会生成包含 EXE、说明和 MIT 许可证的 ZIP 包。双击 EXE 后会启动本机服务并打开浏览器；点击页面右上角「退出」即可关闭程序。

单文件 EXE 启动时需要先解压内置资源，因此比直接运行 Python 略慢。此版本没有代码签名。
