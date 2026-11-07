(() => {
  const bridge = window.AndroidExporter;
  if (!bridge) return;

  const toggle = document.getElementById('library-toggle');
  const workspace = document.querySelector('.workspace');
  const library = document.getElementById('library-view');
  const listView = document.getElementById('library-list-view');
  const readerView = document.getElementById('reader-view');
  const list = document.getElementById('library-list');
  const message = document.getElementById('library-message');
  let view = 'export';
  let pendingRead = null;

  document.body.classList.add('android-app');
  toggle.hidden = false;

  function showMessage(text, isError = false) {
    message.textContent = text;
    message.classList.toggle('is-error', isError);
    message.hidden = !text;
  }

  function showView(next) {
    if (next === 'export') pendingRead = null;
    view = next;
    workspace.hidden = next !== 'export';
    library.hidden = next === 'export';
    listView.hidden = next === 'reader';
    readerView.hidden = next !== 'reader';
    toggle.textContent = next === 'export' ? '下载记录' : '返回导出';
    if (next === 'library') bridge.listDownloads();
    window.scrollTo(0, 0);
  }

  window.showAndroidExportView = () => showView('export');
  window.showAndroidLibraryView = () => showView('library');
  window.handleAndroidBack = () => {
    if (view === 'reader') showView('library');
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
      if (record.type === 'txt' || record.type === 'md') {
        actions.append(actionButton('阅读', () => {
          showMessage('正在读取文件…');
          pendingRead = record.id;
          bridge.readDownload(record.id);
        }, record.name));
      }
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

  window.onAndroidReaderResult = result => {
    if (view !== 'library' || pendingRead !== result.id) return;
    pendingRead = null;
    document.getElementById('reader-title').textContent = result.name;
    document.getElementById('reader-type').textContent = typeLabels[result.type] || '文件';
    const content = document.getElementById('reader-content');
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
  };
  window.onAndroidLibraryError = error => showMessage(error, true);

  toggle.addEventListener('click', () => showView(view === 'export' ? 'library' : 'export'));
  document.getElementById('reader-back').addEventListener('click', () => showView('library'));
  document.getElementById('library-add').addEventListener('click', () => {
    showMessage('');
    bridge.pickExistingFile();
  });
  bridge.listDownloads();
})();
