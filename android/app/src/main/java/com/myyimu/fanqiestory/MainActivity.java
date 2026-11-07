package com.myyimu.fanqiestory;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.RadioButton;
import android.widget.TextView;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

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
    private static final String PENDING_PATH = "pending_path";
    private static final String PENDING_NAME = "pending_name";
    private static final String PENDING_MIME = "pending_mime";

    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private EditText storyInput;
    private CheckBox formatTxt;
    private CheckBox formatMd;
    private CheckBox formatEpub;
    private RadioButton imagesRemote;
    private RadioButton imagesDownload;
    private RadioButton imagesSkip;
    private Button exportButton;
    private TextView statusText;
    private File pendingFile;
    private String pendingName;
    private String pendingMime;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.activity_main);

        storyInput = findViewById(R.id.story_input);
        formatTxt = findViewById(R.id.format_txt);
        formatMd = findViewById(R.id.format_md);
        formatEpub = findViewById(R.id.format_epub);
        imagesRemote = findViewById(R.id.images_remote);
        imagesDownload = findViewById(R.id.images_download);
        imagesSkip = findViewById(R.id.images_skip);
        exportButton = findViewById(R.id.export_button);
        statusText = findViewById(R.id.status_text);

        View.OnClickListener updateImages = view -> updateImageChoices();
        formatTxt.setOnClickListener(updateImages);
        formatMd.setOnClickListener(updateImages);
        formatEpub.setOnClickListener(updateImages);
        updateImageChoices();
        exportButton.setOnClickListener(view -> startExport());

        if (state != null && state.getString(PENDING_PATH) != null) {
            pendingFile = new File(state.getString(PENDING_PATH));
            pendingName = state.getString(PENDING_NAME);
            pendingMime = state.getString(PENDING_MIME);
        }
        acceptSharedText(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        acceptSharedText(intent);
    }

    private void acceptSharedText(Intent intent) {
        if (Intent.ACTION_SEND.equals(intent.getAction()) && "text/plain".equals(intent.getType())) {
            CharSequence shared = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
            if (shared != null) {
                storyInput.setText(shared);
                storyInput.setSelection(storyInput.length());
            }
        }
    }

    private void updateImageChoices() {
        boolean canDownload = formatMd.isChecked() || formatEpub.isChecked();
        imagesDownload.setEnabled(canDownload);
        if (!canDownload && imagesDownload.isChecked()) {
            imagesRemote.setChecked(true);
        }
    }

    private String selectedFormats() {
        StringBuilder formats = new StringBuilder();
        if (formatTxt.isChecked()) formats.append("txt");
        if (formatMd.isChecked()) formats.append(formats.length() == 0 ? "md" : ",md");
        if (formatEpub.isChecked()) formats.append(formats.length() == 0 ? "epub" : ",epub");
        return formats.toString();
    }

    private void startExport() {
        String shareText = storyInput.getText().toString();
        String formats = selectedFormats();
        if (shareText.trim().isEmpty()) {
            showError("请先粘贴短故事分享文案或链接");
            storyInput.requestFocus();
            return;
        }
        if (formats.isEmpty()) {
            showError("请至少选择一种保存格式");
            return;
        }

        String images = imagesDownload.isChecked() ? "download" : imagesSkip.isChecked() ? "skip" : "remote";
        exportButton.setEnabled(false);
        showStatus("正在整理故事…");
        worker.execute(() -> {
            File cacheFile;
            try {
                cacheFile = File.createTempFile("fanqie-export-", ".tmp", getCacheDir());
            } catch (IOException error) {
                runOnUiThread(() -> finishWithError("无法准备保存文件"));
                return;
            }

            try {
                PyObject response = Python.getInstance()
                    .getModule("fanqie_short_story.android")
                    .callAttr("prepare_android_export", shareText, formats, images, cacheFile.getAbsolutePath());
                List<PyObject> values = response.asList();
                if (!"ok".equals(values.get(0).toString())) {
                    cacheFile.delete();
                    String message = values.get(1).toString();
                    runOnUiThread(() -> finishWithError(message));
                    return;
                }

                String fileName = values.get(1).toString();
                String mimeType = values.get(2).toString().split(";", 2)[0];
                int failures = values.get(4).toInt();
                runOnUiThread(() -> {
                    pendingFile = cacheFile;
                    pendingName = fileName;
                    pendingMime = mimeType;
                    showStatus(failures == 0 ? "文件已生成，请选择保存位置。"
                        : "文件已生成；部分故事未完成，详情见 ZIP 内报告。请选择保存位置。");
                    openSavePicker();
                });
            } catch (Exception error) {
                cacheFile.delete();
                runOnUiThread(() -> finishWithError("导出失败，请稍后重试"));
            }
        });
    }

    private void openSavePicker() {
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType(pendingMime);
        intent.putExtra(Intent.EXTRA_TITLE, pendingName);
        try {
            startActivityForResult(intent, CREATE_DOCUMENT_REQUEST);
        } catch (ActivityNotFoundException error) {
            clearPendingFile();
            finishWithError("无法打开系统文件选择器");
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != CREATE_DOCUMENT_REQUEST) return;

        File source = pendingFile;
        String name = pendingName;
        pendingFile = null;
        pendingName = null;
        pendingMime = null;
        if (source == null || resultCode != RESULT_OK || data == null || data.getData() == null) {
            if (source != null) source.delete();
            exportButton.setEnabled(true);
            showStatus("已取消保存。");
            return;
        }

        Uri destination = data.getData();
        showStatus("正在保存文件…");
        worker.execute(() -> {
            try (InputStream input = new FileInputStream(source);
                 OutputStream output = getContentResolver().openOutputStream(destination, "w")) {
                if (output == null) throw new IOException("No output stream");
                byte[] buffer = new byte[16 * 1024];
                int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
                output.flush();
                runOnUiThread(() -> {
                    exportButton.setEnabled(true);
                    showStatus("已保存：" + name);
                });
            } catch (IOException error) {
                runOnUiThread(() -> finishWithError("保存文件失败，请重试"));
            } finally {
                source.delete();
            }
        });
    }

    private void clearPendingFile() {
        if (pendingFile != null) pendingFile.delete();
        pendingFile = null;
        pendingName = null;
        pendingMime = null;
    }

    private void finishWithError(String message) {
        exportButton.setEnabled(true);
        showError(message);
    }

    private void showError(String message) {
        statusText.setTextColor(Color.rgb(167, 66, 52));
        statusText.setText(message);
    }

    private void showStatus(String message) {
        statusText.setTextColor(Color.rgb(92, 98, 90));
        statusText.setText(message);
    }

    @Override
    protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        if (pendingFile != null) {
            state.putString(PENDING_PATH, pendingFile.getAbsolutePath());
            state.putString(PENDING_NAME, pendingName);
            state.putString(PENDING_MIME, pendingMime);
        }
    }

    @Override
    protected void onDestroy() {
        worker.shutdown();
        super.onDestroy();
    }
}
