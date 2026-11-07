(() => {
  const bridge = window.AndroidExporter;
  if (!bridge) return;

  const toggle = document.getElementById('library-toggle');
  const workspace = document.querySelector('.workspace');
  const library = document.getElementById('library-view');
  const listView = document.getElementById('library-list-view');
  const archiveView = document.getElementById('archive-view');
  const readerView = document.getElementById('reader-view');
  const list = document.getElementById('library-list');
  const archiveList = document.getElementById('archive-list');
  const content = document.getElementById('reader-content');
  const chapterSelect = document.getElementById('reader-chapter');
  const messages = ['library-message', 'archive-message', 'reader-message']
    .map(id => document.getElementById(id));
  let view = 'export';
  let pendingRead = null;
  let pendingArchive = null;
  let pendingItem = null;
  let pendingChapter = null;
  let bookInfo = null;
  let readerOrigin = 'library';
  let currentChapter = -1;
  let scrollTimer = null;
  let restorePermille = 0;
  let remainingImages = 0;

  document.body.classList.add('android-app');
  toggle.hidden = false;

  function showMessage(text, isError = false) {
    for (const message of messages) {
      message.textContent = text;
      message.classList.toggle('is-error', isError);
      message.hidden = !text;
    }
  }

  function showView(next) {
    if (view === 'reader' && next !== 'reader') savePosition();
    if (next === 'export') {
      pendingRead = null;
      pendingArchive = null;
      pendingItem = null;
      pendingChapter = null;
    }
    view = next;
    workspace.hidden = next !== 'export';
    library.hidden = next === 'export';
    listView.hidden = next !== 'library';
    archiveView.hidden = next !== 'archive';
    readerView.hidden = next !== 'reader';
    toggle.textContent = next === 'export' ? '下载记录' : '返回导出';
    if (next === 'library') bridge.listDownloads();
    window.scrollTo(0, 0);
  }

  window.showAndroidExportView = () => showView('export');
  window.showAndroidLibraryView = () => showView('library');
  window.handleAndroidBack = () => {
    if (view === 'reader') showView(readerOrigin);
    else if (view === 'archive') showView('library');
    else if (view === 'library') showView('export');
    else return false;
    return true;
  };
  window.refreshAndroidDownloads = () => bridge.listDownloads();

  function actionButton(label, action, name) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = label;
    button.setAttribute('aria-label', `${label}：${name}`);
    button.addEventListener('click', action);
    return button;
  }

  const typeLabels = { txt: 'TXT', md: 'Markdown', epub: 'EPUB', zip: 'ZIP' };
  window.onAndroidDownloads = records => {
    list.replaceChildren();
    if (!records.length) {
      const empty = document.createElement('p');
      empty.className = 'library-empty';
      empty.textContent = '还没有下载记录。保存故事后会出现在这里，也可以添加之前保存的文件。';
      list.append(empty);
      return;
    }
    for (const record of records) {
      const card = document.createElement('article');
      card.className = 'library-card';
      const icon = document.createElement('span');
      icon.className = `library-file-icon type-${record.type}`;
      icon.textContent = (typeLabels[record.type] || '文件').slice(0, 1);
      const details = document.createElement('div');
      details.className = 'library-details';
      const title = document.createElement('strong');
      title.textContent = record.name;
      const meta = document.createElement('span');
      meta.textContent = `${typeLabels[record.type] || '文件'} · ${new Date(record.savedAt).toLocaleString('zh-CN')}`;
      details.append(title, meta);
      const actions = document.createElement('div');
      actions.className = 'library-actions';
      actions.append(actionButton(record.type === 'zip' ? '查看内容' : '阅读', () => {
        showMessage('正在读取文件…');
        if (record.type === 'txt' || record.type === 'md') {
          pendingRead = record.id;
          bridge.readDownload(record.id);
        } else {
          pendingArchive = record.id;
          bridge.inspectArchive(record.id);
        }
      }, record.name));
      actions.append(actionButton('用其他应用打开', () => bridge.openDownload(record.id), record.name));
      const remove = actionButton('移除记录', () => {
        showMessage('已移除记录，原文件仍保留。');
        bridge.removeDownload(record.id);
      }, record.name);
      remove.className = 'remove-record';
      actions.append(remove);
      card.append(icon, details, actions);
      list.append(card);
    }
  };

  function appendInline(parent, source) {
    const pattern = /(!?\[([^\]]*)\]\(([^)]+)\)|\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`|\*([^*]+)\*|_([^_]+)_)/g;
    let offset = 0;
    for (const match of source.matchAll(pattern)) {
      parent.append(document.createTextNode(source.slice(offset, match.index)));
      let node;
      if (match[2] !== undefined) {
        node = document.createElement('span');
        node.className = 'reader-reference';
        node.textContent = match[1].startsWith('!')
          ? `[图片：${match[2] || '未命名'}]`
          : `${match[2]}（${match[3]}）`;
      } else if (match[4] || match[5]) {
        node = document.createElement('strong');
        node.textContent = match[4] || match[5];
      } else if (match[6]) {
        node = document.createElement('code');
        node.textContent = match[6];
      } else {
        node = document.createElement('em');
        node.textContent = match[7] || match[8];
      }
      parent.append(node);
      offset = match.index + match[0].length;
    }
    parent.append(document.createTextNode(source.slice(offset)));
  }

  function renderMarkdown(container, source) {
    let paragraph = [];
    let listNode = null;
    let codeLines = null;
    const flushParagraph = () => {
      if (!paragraph.length) return;
      const node = document.createElement('p');
      appendInline(node, paragraph.join(' '));
      container.append(node);
      paragraph = [];
    };
    for (const line of source.split(/\r?\n/)) {
      if (/^\s*```/.test(line)) {
        flushParagraph();
        listNode = null;
        if (codeLines) {
          const pre = document.createElement('pre');
          pre.textContent = codeLines.join('\n');
          container.append(pre);
          codeLines = null;
        } else codeLines = [];
        continue;
      }
      if (codeLines) {
        codeLines.push(line);
        continue;
      }
      if (!line.trim()) {
        flushParagraph();
        listNode = null;
        continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        listNode = null;
        const node = document.createElement(`h${Math.min(heading[1].length + 1, 6)}`);
        appendInline(node, heading[2]);
        container.append(node);
        continue;
      }
      if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) {
        flushParagraph();
        listNode = null;
        container.append(document.createElement('hr'));
        continue;
      }
      const quote = line.match(/^>\s?(.*)$/);
      if (quote) {
        flushParagraph();
        listNode = null;
        const node = document.createElement('blockquote');
        appendInline(node, quote[1]);
        container.append(node);
        continue;
      }
      const bullet = line.match(/^\s*[-*+]\s+(.+)$/);
      const numbered = line.match(/^\s*\d+\.\s+(.+)$/);
      if (bullet || numbered) {
        flushParagraph();
        const tag = bullet ? 'ul' : 'ol';
        if (!listNode || listNode.tagName.toLowerCase() !== tag) {
          listNode = document.createElement(tag);
          container.append(listNode);
        }
        const item = document.createElement('li');
        appendInline(item, (bullet || numbered)[1]);
        listNode.append(item);
        continue;
      }
      listNode = null;
      paragraph.push(line.trim());
    }
    flushParagraph();
    if (codeLines) {
      const pre = document.createElement('pre');
      pre.textContent = codeLines.join('\n');
      container.append(pre);
    }
  }

  function showText(result, origin) {
    bookInfo = null;
    currentChapter = -1;
    readerOrigin = origin;
    document.getElementById('reader-back').textContent = origin === 'archive' ? '← 压缩包' : '← 下载记录';
    document.getElementById('reader-title').textContent = result.name;
    document.getElementById('reader-type').textContent = typeLabels[result.type] || '文件';
    document.getElementById('reader-author').hidden = true;
    document.getElementById('reader-navigation').hidden = true;
    content.replaceChildren();
    if (result.type === 'md') renderMarkdown(content, result.text);
    else {
      const text = document.createElement('div');
      text.className = 'reader-plain';
      text.textContent = result.text;
      content.append(text);
    }
    showMessage('');
    showView('reader');
  }

  function savePosition() {
    if (!bookInfo || currentChapter < 0 || view !== 'reader') return;
    const range = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    const permille = Math.max(0, Math.min(1000, Math.round(window.scrollY / range * 1000)));
    bridge.saveReadingPosition(bookInfo.id, bookInfo.sourceIndex, currentChapter, permille);
  }

  function requestChapter(index, permille = 0) {
    if (!bookInfo || index < 0 || index >= bookInfo.chapters.length) return;
    savePosition();
    pendingChapter = { index, permille };
    showMessage('正在读取章节…');
    bridge.readArchiveChapter(bookInfo.id, index);
  }

  function openBook(info, origin) {
    bookInfo = info;
    readerOrigin = origin;
    currentChapter = -1;
    document.getElementById('reader-back').textContent = origin === 'archive' ? '← 压缩包' : '← 下载记录';
    document.getElementById('reader-type').textContent = 'EPUB';
    document.getElementById('reader-title').textContent = info.title || info.name;
    const author = document.getElementById('reader-author');
    author.textContent = info.author ? `作者：${info.author}` : '';
    author.hidden = !info.author;
    chapterSelect.replaceChildren();
    for (const [index, chapter] of info.chapters.entries()) {
      const option = document.createElement('option');
      option.value = String(index);
      option.textContent = chapter.label || `第 ${index + 1} 章`;
      chapterSelect.append(option);
    }
    document.getElementById('reader-navigation').hidden = false;
    content.replaceChildren();
    showView('reader');
    const resume = Math.min(Math.max(0, info.resumeChapter || 0), info.chapters.length - 1);
    requestChapter(resume, info.resumePermille || 0);
  }

  function renderArchive(info) {
    document.getElementById('archive-title').textContent = info.name;
    archiveList.replaceChildren();
    if (!info.items.length) {
      const empty = document.createElement('p');
      empty.className = 'library-empty';
      empty.textContent = '这个 ZIP 没有可阅读的 TXT、Markdown、EPUB 或导出报告。';
      archiveList.append(empty);
    }
    for (const [index, item] of info.items.entries()) {
      const card = document.createElement('article');
      card.className = 'library-card';
      const icon = document.createElement('span');
      icon.className = `library-file-icon type-${item.type}`;
      icon.textContent = (typeLabels[item.type] || '文件').slice(0, 1);
      const details = document.createElement('div');
      details.className = 'library-details';
      const name = document.createElement('strong');
      name.textContent = item.name;
      const meta = document.createElement('span');
      meta.textContent = item.name.endsWith('export-report.txt')
        ? '导出报告' : `${typeLabels[item.type]} · ${Math.max(1, Math.ceil(item.size / 1024))} KB`;
      details.append(name, meta);
      const actions = document.createElement('div');
      actions.className = 'library-actions';
      actions.append(actionButton('阅读', () => {
        pendingItem = { id: info.id, index };
        showMessage('正在读取文件…');
        bridge.readArchiveItem(info.id, index);
      }, item.name));
      card.append(icon, details, actions);
      archiveList.append(card);
    }
    showMessage('');
    showView('archive');
  }

  const safeEpubTags = new Set([
    'section', 'article', 'div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'blockquote', 'ul', 'ol', 'li', 'strong', 'b', 'em', 'i', 'code', 'pre',
    'span', 'figure', 'figcaption', 'br', 'hr', 'img',
  ]);
  function appendEpubNode(parent, item) {
    if (typeof item === 'string') {
      parent.append(document.createTextNode(item));
      return;
    }
    if (!item || !safeEpubTags.has(item.tag)) return;
    const node = document.createElement(item.tag);
    if (item.id) node.dataset.epubAnchor = item.id;
    if (item.class === 'reader-reference') node.className = 'reader-reference';
    if (item.tag === 'img') {
      node.alt = item.alt || '插图';
      node.dataset.imageIndex = String(item.image);
    } else {
      for (const child of item.children || []) appendEpubNode(node, child);
    }
    parent.append(node);
  }

  function scrollToChapterPosition(anchor, permille) {
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (permille > 0) {
        const range = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
        window.scrollTo(0, Math.round(range * permille / 1000));
      } else if (anchor) {
        const target = [...content.querySelectorAll('[data-epub-anchor]')]
          .find(node => node.dataset.epubAnchor === anchor);
        if (target) target.scrollIntoView();
        else window.scrollTo(0, 0);
      } else window.scrollTo(0, 0);
    }));
  }

  window.onAndroidReaderResult = result => {
    if (view !== 'library' || pendingRead !== result.id) return;
    pendingRead = null;
    showText(result, 'library');
  };

  window.onAndroidArchiveResult = result => {
    if (view !== 'library' || pendingArchive !== result.id) return;
    pendingArchive = null;
    if (result.kind === 'zip') renderArchive(result);
    else if (result.kind === 'epub') openBook(result, 'library');
  };

  window.onAndroidArchiveItemResult = result => {
    if (view !== 'archive' || !pendingItem
        || pendingItem.id !== result.id || pendingItem.index !== result.sourceIndex) return;
    pendingItem = null;
    if (result.kind === 'text') showText(result, 'archive');
    else if (result.kind === 'epub') openBook(result, 'archive');
  };

  window.onAndroidChapterResult = result => {
    if (view !== 'reader' || !bookInfo || !pendingChapter
        || bookInfo.id !== result.id || bookInfo.sourceIndex !== result.sourceIndex
        || pendingChapter.index !== result.index) return;
    const { permille } = pendingChapter;
    pendingChapter = null;
    currentChapter = result.index;
    chapterSelect.value = String(currentChapter);
    document.getElementById('reader-previous').disabled = currentChapter === 0;
    document.getElementById('reader-next').disabled = currentChapter === bookInfo.chapters.length - 1;
    document.getElementById('reader-progress').textContent = `${currentChapter + 1} / ${bookInfo.chapters.length}`;
    content.replaceChildren();
    for (const node of result.nodes || []) appendEpubNode(content, node);
    showMessage('');
    restorePermille = permille;
    const images = [...content.querySelectorAll('img[data-image-index]')];
    remainingImages = images.length;
    scrollToChapterPosition(result.anchor, permille);
    for (const image of images) {
      bridge.readArchiveImage(bookInfo.id, currentChapter, Number(image.dataset.imageIndex));
    }
    bridge.saveReadingPosition(bookInfo.id, bookInfo.sourceIndex, currentChapter, permille);
  };

  window.onAndroidImageResult = result => {
    if (view !== 'reader' || !bookInfo || bookInfo.id !== result.id
        || bookInfo.sourceIndex !== result.sourceIndex || currentChapter !== result.chapter) return;
    const image = [...content.querySelectorAll('img[data-image-index]')]
      .find(node => Number(node.dataset.imageIndex) === result.image);
    if (image && /^data:image\/(jpeg|png|gif|webp);base64,/.test(result.data || '')) {
      image.src = result.data;
    }
    remainingImages = Math.max(0, remainingImages - 1);
    if (!remainingImages && restorePermille > 0) {
      const saved = restorePermille;
      restorePermille = 0;
      setTimeout(() => scrollToChapterPosition('', saved), 100);
    }
  };
  window.onAndroidLibraryError = error => showMessage(error, true);

  toggle.addEventListener('click', () => showView(view === 'export' ? 'library' : 'export'));
  document.getElementById('reader-back').addEventListener('click', () => showView(readerOrigin));
  document.getElementById('archive-back').addEventListener('click', () => showView('library'));
  chapterSelect.addEventListener('change', () => requestChapter(Number(chapterSelect.value)));
  document.getElementById('reader-previous').addEventListener('click', () => requestChapter(currentChapter - 1));
  document.getElementById('reader-next').addEventListener('click', () => requestChapter(currentChapter + 1));
  window.addEventListener('scroll', () => {
    if (!bookInfo || currentChapter < 0 || view !== 'reader') return;
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(savePosition, 300);
  }, { passive: true });
  document.getElementById('library-add').addEventListener('click', () => {
    showMessage('');
    bridge.pickExistingFile();
  });
  bridge.listDownloads();
})();
