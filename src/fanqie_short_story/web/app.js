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
const maxBatchStories = 10;
let lastDownload = null;

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
  if (lastDownload) URL.revokeObjectURL(lastDownload.href);
});

form.addEventListener('submit', async event => {
  event.preventDefault();
  errorBox.hidden = true;
  const urls = urlField.value.split(/\r?\n/).map(url => url.trim()).filter(Boolean);
  const formats = [...document.querySelectorAll('input[name="format"]:checked')].map(input => input.value);
  const images = document.querySelector('input[name="images"]:checked').value;
  if (!urls.length) {
    showError('请先粘贴分享链接。');
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
  try {
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
    const name = decodeURIComponent(response.headers.get('X-Download-Name') || 'short-story.zip');
    const title = decodeURIComponent(response.headers.get('X-Story-Title') || '导出完成');
    const author = decodeURIComponent(response.headers.get('X-Story-Author') || '');
    const failures = Number(response.headers.get('X-Export-Failures') || 0);
    if (lastDownload) URL.revokeObjectURL(lastDownload.href);
    lastDownload = { href: URL.createObjectURL(blob), name };
    downloadAgain();

    const coverTitle = document.getElementById('book-title');
    coverTitle.textContent = title.length > 28 ? title.slice(0, 28) + '…' : title;
    coverTitle.classList.add('is-real');
    document.getElementById('book-author').textContent = author || '已保存到本地';
    document.getElementById('result-title').textContent = title;
    const type = name.endsWith('.zip') ? 'ZIP' : name.endsWith('.epub') ? 'EPUB' : name.endsWith('.md') ? 'Markdown' : 'TXT';
    document.getElementById('result-meta').textContent = failures
      ? `${failures} 篇未完成 · 详见 ZIP 内报告`
      : `${type} 文件已生成`;
    resultPanel.hidden = false;
    preview.classList.add('has-result');
    statusLine.textContent = '文件已生成，下载已开始。';
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
