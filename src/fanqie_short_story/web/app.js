const form = document.getElementById('export-form');
const urlField = document.getElementById('story-url');
const exportButton = document.getElementById('export-button');
const buttonText = document.getElementById('button-text');
const errorBox = document.getElementById('error-box');
const statusLine = document.getElementById('status-line');
const loading = document.getElementById('loading');
const resultPanel = document.getElementById('result-panel');
const preview = document.getElementById('preview');
const previewEmpty = document.getElementById('preview-empty');
const mobileLoader = document.getElementById('mobile-book-loader');
const downloadRadio = document.querySelector('input[name="images"][value="download"]');
const token = document.querySelector('meta[name="local-token"]').content;
const isAndroid = typeof window.AndroidExporter !== 'undefined';
const maxBatchStories = 10;
const shareUrlPattern = /https:\/\/changdunovel\.com\/[^\s<>"'“”‘’]+/gi;
const trailingPunctuation = /[.,;:!?，。；：！？、)\]}）】》」』]+$/u;
let lastDownload = null;
let androidRequest = null;

if (isAndroid) document.getElementById('exit-button').hidden = true;

window.setAndroidShareText = text => {
  window.showAndroidExportView?.();
  urlField.value = text;
  urlField.dispatchEvent(new Event('input'));
};

window.onAndroidExportResult = result => {
  if (!androidRequest) return;
  const request = androidRequest;
  androidRequest = null;
  if (result.status === 'ok') request.resolve(result);
  else request.reject(new Error(result.message || '导出失败，请稍后重试。'));
};

window.onAndroidSaveResult = result => {
  if (result.status === 'saved') {
    const message = result.recorded ? `已保存：${result.name}` : `已保存：${result.name} · 此位置未提供长期读取授权`;
    statusLine.textContent = message;
    document.getElementById('result-meta').textContent = message;
    document.getElementById('open-folder-button').hidden = false;
    document.getElementById('show-library-button').hidden = !result.recorded;
  } else if (result.status === 'cancelled') {
    statusLine.textContent = '已取消保存，可点击再次下载。';
    document.getElementById('result-meta').textContent = '未保存 · 可点击再次下载';
  } else {
    showError(result.message || '保存失败，请重试。');
  }
};

function requestAndroidExport(text, formats, images) {
  return new Promise((resolve, reject) => {
    androidRequest = { resolve, reject };
    window.AndroidExporter.startExport(text, formats.join(','), images);
  });
}

async function requestWebExport(urls, formats, images) {
  const isBatch = urls.length > 1;
  const response = await fetch(isBatch ? '/api/export-batch' : '/api/export', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Local-Token': token },
    body: JSON.stringify(isBatch ? { urls, formats, images } : { url: urls[0], formats, images }),
    cache: 'no-store',
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.error || '导出失败，请稍后重试。');
  }

  const blob = await response.blob();
  return {
    name: decodeURIComponent(response.headers.get('X-Download-Name') || 'short-story.zip'),
    title: decodeURIComponent(response.headers.get('X-Story-Title') || '导出完成'),
    author: decodeURIComponent(response.headers.get('X-Story-Author') || ''),
    failures: Number(response.headers.get('X-Export-Failures') || 0),
    href: URL.createObjectURL(blob),
  };
}

function shareUrlsFromText(text) {
  return (text.match(shareUrlPattern) || []).map(url => url.replace(trailingPunctuation, ''));
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.hidden = false;
  statusLine.textContent = message;
}

function updateImageOptions() {
  const markdown = document.querySelector('input[name="format"][value="md"]').checked;
  const epub = document.querySelector('input[name="format"][value="epub"]').checked;
  downloadRadio.disabled = !(markdown || epub);
  document.getElementById('remote-image-label').textContent = markdown ? '保留在线图片' : '标记图片位置';
  if (!markdown && !epub && downloadRadio.checked) {
    document.querySelector('input[name="images"][value="remote"]').checked = true;
  }
}

function downloadAgain() {
  if (!lastDownload) return;
  if (isAndroid) {
    window.AndroidExporter.savePrepared();
    return;
  }
  const anchor = document.createElement('a');
  anchor.href = lastDownload.href;
  anchor.download = lastDownload.name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

document.querySelectorAll('input[name="format"], input[name="images"]').forEach(input => {
  input.addEventListener('change', () => {
    errorBox.hidden = true;
    updateImageOptions();
  });
});
urlField.addEventListener('input', () => { errorBox.hidden = true; });
document.getElementById('again-button').addEventListener('click', downloadAgain);
document.getElementById('open-folder-button').addEventListener('click', () => {
  if (isAndroid) window.AndroidExporter.openSavedLocation();
});
document.getElementById('show-library-button').addEventListener('click', () => {
  window.showAndroidLibraryView?.();
});
document.getElementById('exit-button').addEventListener('click', async () => {
  try {
    await fetch('/api/shutdown', {
      method: 'POST',
      headers: { 'X-Local-Token': token },
      cache: 'no-store',
    });
    document.querySelector('.workspace').hidden = true;
    document.getElementById('exit-state').hidden = false;
    statusLine.textContent = '程序已退出，可以关闭页面。';
  } catch {
    showError('退出失败，请关闭程序后重试。');
  }
});
window.addEventListener('beforeunload', () => {
  if (lastDownload?.href) URL.revokeObjectURL(lastDownload.href);
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  errorBox.hidden = true;
  const urls = shareUrlsFromText(urlField.value);
  const formats = [...document.querySelectorAll('input[name="format"]:checked')].map(input => input.value);
  const images = document.querySelector('input[name="images"]:checked').value;
  if (!urls.length) {
    showError('请先粘贴短故事分享链接或分享文案。');
    urlField.focus();
    return;
  }
  if (urls.length > maxBatchStories) {
    showError(`一次最多处理 ${maxBatchStories} 篇故事。`);
    return;
  }
  if (!formats.length) {
    showError('请至少选择一种格式。');
    return;
  }

  exportButton.disabled = true;
  buttonText.textContent = '正在导出…';
  const isBatch = urls.length > 1;
  const hadResult = !resultPanel.hidden;
  preview.classList.add('is-loading');
  preview.classList.remove('has-result');
  previewEmpty.hidden = true;
  resultPanel.hidden = true;
  loading.hidden = false;
  loading.querySelector('strong').textContent = isBatch ? `正在整理 ${urls.length} 篇…` : '正在整理…';
  mobileLoader.hidden = false;
  statusLine.textContent = isBatch ? `正在导出 ${urls.length} 篇故事。` : '正在导出故事。';
  document.getElementById('open-folder-button').hidden = true;
  document.getElementById('show-library-button').hidden = true;
  try {
    const result = isAndroid
      ? await requestAndroidExport(urlField.value, formats, images)
      : await requestWebExport(urls, formats, images);
    const { name, title, author, failures } = result;
    if (lastDownload?.href) URL.revokeObjectURL(lastDownload.href);
    lastDownload = isAndroid ? { name } : { href: result.href, name };

    const coverTitle = document.getElementById('book-title');
    coverTitle.textContent = title.length > 28 ? title.slice(0, 28) + '…' : title;
    coverTitle.classList.add('is-real');
    document.getElementById('book-author').textContent = author || '已保存到本地';
    document.getElementById('result-title').textContent = title;
    const type = name.endsWith('.zip') ? 'ZIP' : name.endsWith('.epub') ? 'EPUB' : name.endsWith('.md') ? 'Markdown' : 'TXT';
    document.getElementById('result-meta').textContent = failures
      ? `${failures} 篇未完成 · 详见 ZIP 内报告`
      : isAndroid ? `${type} 文件已生成，请选择保存位置` : `${type} 文件已生成`;
    resultPanel.hidden = false;
    preview.classList.add('has-result');
    statusLine.textContent = isAndroid ? '文件已生成，请选择保存位置。' : '文件已生成，下载已开始。';
    downloadAgain();
  } catch (error) {
    showError(error instanceof Error ? error.message : '导出失败，请稍后重试。');
    if (hadResult) {
      resultPanel.hidden = false;
      preview.classList.add('has-result');
    }
    else previewEmpty.hidden = false;
  } finally {
    preview.classList.remove('is-loading');
    loading.hidden = true;
    mobileLoader.hidden = true;
    exportButton.disabled = false;
    buttonText.textContent = '下载故事';
  }
});

updateImageOptions();
