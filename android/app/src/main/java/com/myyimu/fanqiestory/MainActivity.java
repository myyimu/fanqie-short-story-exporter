package com.myyimu.fanqiestory;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.webkit.WebViewAssetLoader;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int CREATE_DOCUMENT_REQUEST = 1001;
    private static final String ASSET_HOST = "appassets.androidplatform.net";
    private static final String APP_URL = "https://" + ASSET_HOST + "/assets/index.html";
    private static final String LAST_SAVE_URI = "last_save_uri";

    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private WebView webView;
    private boolean pageReady;
    private String sharedText;
    private File pendingFile;
    private String pendingName;
    private String pendingMime;
    private Uri lastSaveUri;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
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
        if (pageReady) webView.evaluateJavascript("window." + event + "(" + json + ")", null);
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

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != CREATE_DOCUMENT_REQUEST) return;
        if (resultCode != RESULT_OK || data == null || data.getData() == null) {
            sendEvent("onAndroidSaveResult", "{\"status\":\"cancelled\"}");
            return;
        }

        File source = pendingFile;
        String name = pendingName;
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
                runOnUiThread(() -> {
                    lastSaveUri = destination;
                    getPreferences(MODE_PRIVATE).edit().putString(LAST_SAVE_URI, destination.toString()).apply();
                    sendEvent("onAndroidSaveResult", "{\"status\":\"saved\",\"name\":"
                        + JSONObject.quote(name) + "}");
                });
            } catch (IOException error) {
                runOnUiThread(() -> sendEvent("onAndroidSaveResult", "{\"status\":\"error\",\"message\":\"保存文件失败，请重试\"}"));
            }
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
        worker.shutdown();
        if (pendingFile != null && !isChangingConfigurations()) pendingFile.delete();
        webView.destroy();
        super.onDestroy();
    }
}
