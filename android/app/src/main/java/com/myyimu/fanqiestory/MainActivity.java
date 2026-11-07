package com.myyimu.fanqiestory;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.webkit.WebViewAssetLoader;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int CREATE_DOCUMENT_REQUEST = 1001;
    private static final int IMPORT_DOCUMENT_REQUEST = 1002;
    private static final int MAX_READER_BYTES = 4 * 1024 * 1024;
    private static final String ASSET_HOST = "appassets.androidplatform.net";
    private static final String APP_URL = "https://" + ASSET_HOST + "/assets/index.html";
    private static final String LAST_SAVE_URI = "last_save_uri";

    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private WebView webView;
    private boolean pageReady;
    private boolean destroyed;
    private String sharedText;
    private File pendingFile;
    private String pendingName;
    private String pendingMime;
    private Uri lastSaveUri;
    private DownloadHistory downloadHistory;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        downloadHistory = new DownloadHistory(this);
        String savedUri = getPreferences(MODE_PRIVATE).getString(LAST_SAVE_URI, null);
        if (savedUri != null) lastSaveUri = Uri.parse(savedUri);
        if (state != null && state.getString("pending_path") != null) {
            pendingFile = new File(state.getString("pending_path"));
            pendingName = state.getString("pending_name");
            pendingMime = state.getString("pending_mime");
        }

        WebViewAssetLoader assets = new WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
            .build();
        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(245, 240, 231));
        webView.setFitsSystemWindows(true);
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setAllowFileAccess(false);
        webView.getSettings().setAllowContentAccess(false);
        webView.getSettings().setAllowFileAccessFromFileURLs(false);
        webView.getSettings().setAllowUniversalAccessFromFileURLs(false);
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("https".equals(uri.getScheme()) && ASSET_HOST.equals(uri.getHost())) {
                    WebResourceResponse response = assets.shouldInterceptRequest(uri);
                    if (response != null) return response;
                }
                return new WebResourceResponse(
                    "text/plain", "UTF-8", new ByteArrayInputStream(new byte[0])
                );
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !APP_URL.equals(request.getUrl().toString());
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                if (APP_URL.equals(url)) {
                    pageReady = true;
                    deliverSharedText();
                }
            }
        });
        webView.addJavascriptInterface(new AndroidBridge(), "AndroidExporter");
        setContentView(webView);
        acceptSharedText(getIntent());
        webView.loadUrl(APP_URL);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        acceptSharedText(intent);
    }

    private void acceptSharedText(Intent intent) {
        if (Intent.ACTION_SEND.equals(intent.getAction()) && "text/plain".equals(intent.getType())) {
            CharSequence incoming = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
            if (incoming != null) {
                sharedText = incoming.toString();
                deliverSharedText();
            }
        }
    }

    private void deliverSharedText() {
        if (pageReady && sharedText != null) {
            webView.evaluateJavascript(
                "window.setAndroidShareText(" + JSONObject.quote(sharedText) + ")", null
            );
            sharedText = null;
        }
    }

    private void sendEvent(String event, String json) {
        if (pageReady && !destroyed) {
            webView.evaluateJavascript("window." + event + "(" + json + ")", null);
        }
    }

    private void sendExportError(String message) {
        sendEvent("onAndroidExportResult", "{\"status\":\"error\",\"message\":"
            + JSONObject.quote(message) + "}");
    }

    private final class AndroidBridge {
        @JavascriptInterface
        public void startExport(String shareText, String formats, String images) {
            worker.execute(() -> prepareExport(shareText, formats, images));
        }

        @JavascriptInterface
        public void savePrepared() {
            runOnUiThread(() -> {
                if (pendingFile != null && pendingFile.isFile()) openSavePicker();
                else sendEvent("onAndroidSaveResult", "{\"status\":\"error\",\"message\":\"文件已失效，请重新导出\"}");
            });
        }

        @JavascriptInterface
        public void openSavedLocation() {
            runOnUiThread(() -> openSavedLocationPicker());
        }

        @JavascriptInterface
        public void listDownloads() {
            worker.execute(() -> sendDownloads());
        }

        @JavascriptInterface
        public void readDownload(String id) {
            worker.execute(() -> readDownloadText(id));
        }

        @JavascriptInterface
        public void openDownload(String id) {
            worker.execute(() -> openDownloadFile(id));
        }

        @JavascriptInterface
        public void removeDownload(String id) {
            worker.execute(() -> removeDownloadRecord(id));
        }

        @JavascriptInterface
        public void pickExistingFile() {
            runOnUiThread(() -> openImportPicker());
        }
    }

    private void prepareExport(String shareText, String formats, String images) {
        File output;
        try {
            output = File.createTempFile("fanqie-export-", ".tmp", getCacheDir());
        } catch (IOException error) {
            runOnUiThread(() -> sendExportError("无法准备保存文件"));
            return;
        }

        try {
            PyObject response = Python.getInstance()
                .getModule("fanqie_short_story.android")
                .callAttr("prepare_android_export", shareText, formats, images, output.getAbsolutePath());
            List<PyObject> values = response.asList();
            if (!"ok".equals(values.get(0).toString())) {
                output.delete();
                String message = values.get(1).toString();
                runOnUiThread(() -> sendExportError(message));
                return;
            }

            String name = values.get(1).toString();
            String mime = values.get(2).toString().split(";", 2)[0];
            int failures = values.get(4).toInt();
            String title = values.get(5).toString();
            String author = values.get(6).toString();
            runOnUiThread(() -> {
                if (destroyed) {
                    output.delete();
                    return;
                }
                if (pendingFile != null) pendingFile.delete();
                pendingFile = output;
                pendingName = name;
                pendingMime = mime;
                sendEvent("onAndroidExportResult", "{\"status\":\"ok\",\"name\":"
                    + JSONObject.quote(name) + ",\"title\":" + JSONObject.quote(title)
                    + ",\"author\":" + JSONObject.quote(author)
                    + ",\"failures\":" + failures + "}");
            });
        } catch (Exception error) {
            output.delete();
            runOnUiThread(() -> sendExportError("导出失败，请稍后重试"));
        }
    }

    private void openSavePicker() {
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType(pendingMime);
        intent.putExtra(Intent.EXTRA_TITLE, pendingName);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        if (lastSaveUri != null && Build.VERSION.SDK_INT >= 26) {
            intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI, lastSaveUri);
        }
        try {
            startActivityForResult(intent, CREATE_DOCUMENT_REQUEST);
        } catch (ActivityNotFoundException error) {
            sendEvent("onAndroidSaveResult", "{\"status\":\"error\",\"message\":\"无法打开系统文件选择器\"}");
        }
    }

    private void openSavedLocationPicker() {
        if (lastSaveUri == null) return;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        if (Build.VERSION.SDK_INT >= 26) {
            intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI, lastSaveUri);
        }
        try {
            startActivity(intent);
        } catch (ActivityNotFoundException error) {
            sendEvent("onAndroidSaveResult", "{\"status\":\"error\",\"message\":\"无法打开保存位置\"}");
        }
    }

    private void openImportPicker() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            startActivityForResult(intent, IMPORT_DOCUMENT_REQUEST);
        } catch (ActivityNotFoundException error) {
            sendLibraryError("无法打开系统文件选择器");
        }
    }

    private boolean persistReadPermission(Uri uri, Intent result) {
        if ((result.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION) == 0) return false;
        try {
            getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION);
            return true;
        } catch (SecurityException error) {
            return false;
        }
    }

    private String displayName(Uri uri, String fallback) {
        try (Cursor cursor = getContentResolver().query(uri,
            new String[] {OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                String name = cursor.getString(0);
                if (name != null && !name.isEmpty()) return name;
            }
        } catch (RuntimeException ignored) {
            // Some document providers cannot return a display name.
        }
        return fallback;
    }

    private String fileType(String name, String mime) {
        String lower = name.toLowerCase(Locale.ROOT);
        if (lower.endsWith(".txt")) return "txt";
        if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "md";
        if (lower.endsWith(".epub")) return "epub";
        if (lower.endsWith(".zip")) return "zip";
        if ("text/markdown".equals(mime)) return "md";
        if ("text/plain".equals(mime)) return "txt";
        if ("application/epub+zip".equals(mime)) return "epub";
        if ("application/zip".equals(mime)) return "zip";
        return null;
    }

    private String mimeType(String type) {
        switch (type) {
            case "txt": return "text/plain";
            case "md": return "text/markdown";
            case "epub": return "application/epub+zip";
            default: return "application/zip";
        }
    }

    private void sendDownloads() {
        JSONArray entries = downloadHistory.publicEntries();
        runOnUiThread(() -> sendEvent("onAndroidDownloads", entries.toString()));
    }

    private void sendLibraryError(String message) {
        sendEvent("onAndroidLibraryError", JSONObject.quote(message));
    }

    private void readDownloadText(String id) {
        JSONObject record = downloadHistory.find(id);
        if (record == null) {
            runOnUiThread(() -> sendLibraryError("找不到这条下载记录"));
            return;
        }
        String type = record.optString("type");
        if (!"txt".equals(type) && !"md".equals(type)) {
            runOnUiThread(() -> sendLibraryError("此格式暂不支持应用内阅读，可用其他应用打开"));
            return;
        }
        try (InputStream input = getContentResolver().openInputStream(Uri.parse(record.optString("uri")))) {
            if (input == null) throw new IOException("No input stream");
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[16 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (output.size() + count > MAX_READER_BYTES) {
                    runOnUiThread(() -> sendLibraryError("文件过大，请用其他应用打开"));
                    return;
                }
                output.write(buffer, 0, count);
            }
            String content = new String(output.toByteArray(), StandardCharsets.UTF_8);
            if (content.startsWith("\uFEFF")) content = content.substring(1);
            String json = "{\"id\":" + JSONObject.quote(id)
                + ",\"name\":" + JSONObject.quote(record.optString("name"))
                + ",\"type\":" + JSONObject.quote(type)
                + ",\"text\":" + JSONObject.quote(content) + "}";
            runOnUiThread(() -> sendEvent("onAndroidReaderResult", json));
        } catch (IOException | SecurityException error) {
            runOnUiThread(() -> sendLibraryError("无法读取文件。文件可能已移动、删除或失去访问授权，请重新添加"));
        }
    }

    private void openDownloadFile(String id) {
        JSONObject record = downloadHistory.find(id);
        if (record == null) {
            runOnUiThread(() -> sendLibraryError("找不到这条下载记录"));
            return;
        }
        Uri uri = Uri.parse(record.optString("uri"));
        try (InputStream input = getContentResolver().openInputStream(uri)) {
            if (input == null) throw new IOException("No input stream");
        } catch (IOException | SecurityException error) {
            runOnUiThread(() -> sendLibraryError("无法打开文件。文件可能已移动、删除或失去访问授权，请重新添加"));
            return;
        }
        runOnUiThread(() -> {
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(uri, mimeType(record.optString("type")));
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            try {
                startActivity(Intent.createChooser(intent, "打开文件"));
            } catch (ActivityNotFoundException error) {
                sendLibraryError("没有可打开此格式的应用");
            }
        });
    }

    private void removeDownloadRecord(String id) {
        Uri removed = downloadHistory.remove(id);
        if (removed == null) {
            runOnUiThread(() -> sendLibraryError("移除记录失败，请重试"));
            return;
        }
        try {
            getContentResolver().releasePersistableUriPermission(removed, Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (SecurityException ignored) {
            // The file provider may have already revoked access.
        }
        sendDownloads();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == IMPORT_DOCUMENT_REQUEST) {
            if (resultCode == RESULT_OK && data != null && data.getData() != null) {
                Uri selected = data.getData();
                worker.execute(() -> {
                    String name = displayName(selected, "文件");
                    String mime;
                    try {
                        mime = getContentResolver().getType(selected);
                    } catch (RuntimeException error) {
                        mime = "";
                    }
                    String type = fileType(name, mime);
                    if (type == null) {
                        runOnUiThread(() -> sendLibraryError("仅支持添加 TXT、Markdown、EPUB 或 ZIP 文件"));
                    } else if (!persistReadPermission(selected, data)) {
                        runOnUiThread(() -> sendLibraryError("无法取得该文件的长期访问授权"));
                    } else if (!downloadHistory.add(selected, name, type)) {
                        runOnUiThread(() -> sendLibraryError("保存下载记录失败，请重试"));
                    } else {
                        sendDownloads();
                    }
                });
            }
            return;
        }
        if (requestCode != CREATE_DOCUMENT_REQUEST) return;
        if (resultCode != RESULT_OK || data == null || data.getData() == null) {
            sendEvent("onAndroidSaveResult", "{\"status\":\"cancelled\"}");
            return;
        }

        File source = pendingFile;
        String name = pendingName;
        String mime = pendingMime;
        Uri destination = data.getData();
        if (source == null || !source.isFile()) {
            sendEvent("onAndroidSaveResult", "{\"status\":\"error\",\"message\":\"文件已失效，请重新导出\"}");
            return;
        }
        worker.execute(() -> {
            try (InputStream input = new FileInputStream(source);
                 OutputStream output = getContentResolver().openOutputStream(destination, "w")) {
                if (output == null) throw new IOException("No output stream");
                byte[] buffer = new byte[16 * 1024];
                int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                output.flush();
                String actualName = displayName(destination, name);
                String type = fileType(actualName, mime);
                boolean recorded = type != null && persistReadPermission(destination, data)
                    && downloadHistory.add(destination, actualName, type);
                runOnUiThread(() -> {
                    lastSaveUri = destination;
                    getPreferences(MODE_PRIVATE).edit().putString(LAST_SAVE_URI, destination.toString()).apply();
                    sendEvent("onAndroidSaveResult", "{\"status\":\"saved\",\"name\":"
                        + JSONObject.quote(actualName) + ",\"recorded\":" + recorded + "}");
                });
                if (recorded) sendDownloads();
            } catch (IOException | SecurityException error) {
                runOnUiThread(() -> sendEvent("onAndroidSaveResult", "{\"status\":\"error\",\"message\":\"保存文件失败，请重试\"}"));
            }
        });
    }

    @Override
    public void onBackPressed() {
        if (!pageReady || destroyed) {
            super.onBackPressed();
            return;
        }
        webView.evaluateJavascript("window.handleAndroidBack ? window.handleAndroidBack() : false", value -> {
            if (!"true".equals(value)) MainActivity.super.onBackPressed();
        });
    }

    @Override
    protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        if (pendingFile != null) {
            state.putString("pending_path", pendingFile.getAbsolutePath());
            state.putString("pending_name", pendingName);
            state.putString("pending_mime", pendingMime);
        }
    }

    @Override
    protected void onDestroy() {
        destroyed = true;
        pageReady = false;
        worker.shutdown();
        if (pendingFile != null && !isChangingConfigurations()) pendingFile.delete();
        webView.destroy();
        super.onDestroy();
    }
}
