# Windows 免安装版

在 Windows PowerShell 中运行：

```powershell
.\packaging\build_windows.ps1
```

首次运行会在 `build/windows/venv` 安装固定版本的 PyInstaller。生成的 `dist/FanqieShortStoryExporter.exe` 可独立运行，不需要目标电脑另装 Python。也会生成包含 EXE、说明和 MIT 许可证的 ZIP 包。双击 EXE 后会启动本机服务并打开浏览器；点击页面右上角「退出」即可关闭程序。

单文件 EXE 启动时需要先解压内置资源，因此比直接运行 Python 略慢。此版本没有代码签名。

## Android APK

`android/` 是 Android WebView 外壳，直接打包 `src/fanqie_short_story/web` 的网页界面，并通过 Chaquopy 复用同目录中的 Python 导出逻辑。Android 负责接收分享文本、通过系统文件选择器保存，以及管理下载记录和本地阅读。构建需要 JDK 17、Python 3.13、Android SDK 35 和 Gradle 8.13：

保存后应用会通过 Storage Access Framework 保留文件的读取授权，并将文件名、格式、时间和 URI 记入私有下载记录。记录跨应用与设备重启保留；移动或删除原文件后可能失效，可移除记录并重新添加。TXT 与 Markdown 可在应用内阅读；EPUB 阅读器提供目录、章节导航、内嵌图片和跨重启阅读位置；ZIP 可列出故事文件与导出报告，选择单篇阅读（包括包内 EPUB）。文件与章节的大小限制见[阅读说明](../docs/android-reading-roadmap.md)。移除记录不会删除原文件。

```bash
gradle --project-dir android :app:assemblePhoneDebug
```

手机调试 APK 位于 `android/app/build/outputs/apk/phone/debug/app-phone-debug.apk`。`emulator` 构建另含 `x86_64`，供 CI 模拟器检查。GitHub Actions 的 **Build Android APK** 工作流也会生成可下载的调试包。调试签名可能随构建变化，正式安装请使用 [Android 0.4.4 发布页](https://github.com/myyimu/fanqie-short-story-exporter/releases/tag/v0.4.4)上的固定签名 APK。

### 固定发布签名

**Build signed Android APK** 工作流仅在 `main` 上手动触发，并从所选发布标签检出源码。它从仓库 Secrets `ANDROID_RELEASE_KEYSTORE_B64` 和 `ANDROID_RELEASE_PASSWORD` 恢复发布密钥，运行测试、构建 `phoneRelease`，并用 `android/release-cert.sha256` 校验 APK 的签名证书。密钥文件和密码不在 Git 仓库中。签名后的 APK 作为 `fanqie-short-story-android-phone-signed` 构建产物保留，并自动上传到对应的 GitHub Release。

本机签名时设置 `FANQIE_RELEASE_KEYSTORE` 为 keystore 的绝对路径、`FANQIE_RELEASE_PASSWORD` 为密码，然后运行 `gradle --project-dir android :app:assemblePhoneRelease`。后续每次发布都保留相同应用 ID 和证书，同时提高 `versionCode`。从先前调试签名版切换到发布签名版，需要先卸载调试版。
