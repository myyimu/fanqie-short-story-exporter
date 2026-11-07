# Windows 免安装版

在 Windows PowerShell 中运行：

```powershell
.\packaging\build_windows.ps1
```

首次运行会在 `build/windows/venv` 安装固定版本的 PyInstaller。生成的 `dist/FanqieShortStoryExporter.exe` 可独立运行，不需要目标电脑另装 Python。也会生成包含 EXE、说明和 MIT 许可证的 ZIP 包。双击 EXE 后会启动本机服务并打开浏览器；点击页面右上角「退出」即可关闭程序。

单文件 EXE 启动时需要先解压内置资源，因此比直接运行 Python 略慢。此版本没有代码签名。

## Android 测试版 APK

`android/` 是 Android WebView 外壳，直接打包 `src/fanqie_short_story/web` 的网页界面，并通过 Chaquopy 复用同目录中的 Python 导出逻辑。Android 仅负责接收分享文本和调用系统文件选择器保存。构建需要 JDK 17、Python 3.13、Android SDK 35 和 Gradle 8.13：

```bash
gradle --project-dir android :app:assembleDebug
```

APK 位于 `android/app/build/outputs/apk/debug/app-debug.apk`。GitHub Actions 的 **Build Android APK** 工作流也会生成可下载的 APK 构建产物。调试签名 APK 可用于安装试用，但不同构建的调试密钥可能不同；即使 `versionCode` 已递增，也可能需要先卸载旧测试版。正式发布前应配置固定的发布签名，之后同一应用 ID、相同签名且更高版本号的 APK 才能覆盖安装。
