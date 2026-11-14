// 知衡 · 个人健康助手 v1.0 —— 前端逻辑
(function () {
  'use strict';

  // ---------- DOM 工具 ----------
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  // ---------- 导航 ----------
  const views = {
    chat: $('#view-chat'),
    profile: $('#view-profile'),
    image: $('#view-image'),
    settings: $('#view-settings'),
    about: $('#view-about'),
  };
  const navBtns = $$('#nav button');

  function switchView(name) {
    navBtns.forEach(b => b.classList.toggle('active', b.dataset.nav === name));
    Object.keys(views).forEach(k => views[k].classList.toggle('active', k === name));
  }
  navBtns.forEach(b => b.addEventListener('click', () => switchView(b.dataset.nav)));

  // ---------- 工具：文本渲染 ----------
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function inline(s) {
    s = escapeHtml(s);
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
    s = s.replace(/\*([^*]+)\*/g, '<i>$1</i>');
    return s;
  }

  function renderTable(rows) {
    let out = '<table>';
    rows.forEach((r, i) => {
      const cells = r.replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
      const tag = i === 0 ? 'th' : 'td';
      out += '<tr>' + cells.map(c => '<' + tag + '>' + inline(c) + '</' + tag + '>').join('') + '</tr>';
    });
    return out + '</table>';
  }

  function renderMarkdown(text) {
    const lines = String(text).replace(/\r\n/g, '\n').split('\n');
    const html = [];
    let list = null;
    let tableRows = [];
    let inTable = false;

    const flushList = () => { if (list) { html.push('</' + list + '>'); list = null; } };
    const flushTable = () => { if (inTable) { html.push(renderTable(tableRows)); inTable = false; tableRows = []; } };

    for (let line of lines) {
      const t = line.trim();

      if (/^\|.*\|$/.test(t)) {
        flushList();
        if (/^\|[\s:\-|]+\|$/.test(t) && tableRows.length > 0) { /* 表头分隔行，跳过 */ }
        else { if (!inTable) inTable = true; tableRows.push(t); }
        continue;
      } else {
        flushTable();
      }

      if (t === '') { flushList(); html.push(''); continue; }

      let m = t.match(/^(#{1,4})\s+(.*)$/);
      if (m) { flushList(); const lv = m[1].length + 1; html.push('<h' + lv + '>' + inline(m[2]) + '</h' + lv + '>'); continue; }

      m = t.match(/^[-*+]\s+(.*)$/);
      if (m) { if (list !== 'ul') { flushList(); html.push('<ul>'); list = 'ul'; } html.push('<li>' + inline(m[1]) + '</li>'); continue; }

      m = t.match(/^\d+[.)]\s+(.*)$/);
      if (m) { if (list !== 'ol') { flushList(); html.push('<ol>'); list = 'ol'; } html.push('<li>' + inline(m[1]) + '</li>'); continue; }

      if (t.startsWith('>')) { flushList(); html.push('<blockquote>' + inline(t.replace(/^>\s?/, '')) + '</blockquote>'); continue; }

      if (/^(-{3,}|\*{3,})$/.test(t)) { flushList(); html.push('<hr>'); continue; }

      flushList();
      html.push('<p>' + inline(t) + '</p>');
    }
    flushList();
    flushTable();
    return html.join('\n');
  }

  // ---------- 对话 ----------
  const messagesEl = $('#messages');
  const inputEl = $('#input');
  const sendBtn = $('#sendBtn');
  const deepModeEl = $('#deepMode');
  const clearBtn = $('#clearBtn');
  let sending = false;

  // ---------- 图片（发图给助手看） ----------
  const imgBtn = $('#imgBtn');
  const imgFile = $('#imgFile');
  const imgPreview = $('#imgPreview');
  let pendingImages = [];

  function renderPendingImages() {
    imgPreview.innerHTML = '';
    imgPreview.style.display = pendingImages.length ? 'flex' : 'none';
    pendingImages.forEach(function (url, idx) {
      const wrap = document.createElement('div');
      wrap.className = 'thumb';
      const im = document.createElement('img');
      im.src = url;
      wrap.appendChild(im);
      const del = document.createElement('button');
      del.className = 'thumb-del';
      del.textContent = '×';
      del.title = '移除这张图';
      del.addEventListener('click', function () {
        pendingImages.splice(idx, 1);
        renderPendingImages();
      });
      wrap.appendChild(del);
      imgPreview.appendChild(wrap);
    });
  }

  function compressImage(file, maxSide, quality) {
    maxSide = maxSide || 1280;
    quality = quality || 0.85;
    return new Promise(function (resolve) {
      if (!file.type || file.type.indexOf('image/') !== 0) { resolve(null); return; }
      const reader = new FileReader();
      reader.onload = function () {
        const img = new Image();
        img.onload = function () {
          let w = img.naturalWidth || img.width;
          let h = img.naturalHeight || img.height;
          const scale = Math.min(1, maxSide / Math.max(w, h));
          w = Math.max(1, Math.round(w * scale));
          h = Math.max(1, Math.round(h * scale));
          const canvas = document.createElement('canvas');
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext('2d');
          ctx.fillStyle = '#fff';
          ctx.fillRect(0, 0, w, h);
          ctx.drawImage(img, 0, 0, w, h);
          resolve(canvas.toDataURL('image/jpeg', quality));
        };
        img.onerror = function () { resolve(null); };
        img.src = reader.result;
      };
      reader.onerror = function () { resolve(null); };
      reader.readAsDataURL(file);
    });
  }

  async function addImageFiles(files) {
    const list = Array.from(files || []).slice(0, 4 - pendingImages.length);
    for (const f of list) {
      const url = await compressImage(f);
      if (url) pendingImages.push(url);
    }
    renderPendingImages();
  }

  imgBtn.addEventListener('click', function () { imgFile.click(); });
  imgFile.addEventListener('change', function () {
    addImageFiles(imgFile.files);
    imgFile.value = '';
  });
  inputEl.addEventListener('paste', function (e) {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    const files = [];
    for (const it of items) {
      if (it.kind === 'file' && it.type && it.type.indexOf('image/') === 0) {
        const f = it.getAsFile();
        if (f) files.push(f);
      }
    }
    if (files.length) {
      e.preventDefault();
      addImageFiles(files);
    }
  });

  function scrollBottom() { messagesEl.scrollTop = messagesEl.scrollHeight; }

  function addMessage(role, contentHtml, raw) {
    const wrap = document.createElement('div');
    wrap.className = 'msg ' + role;
    const who = document.createElement('div');
    who.className = 'who';
    who.textContent = role === 'user' ? '我' : '知衡';
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    if (raw) bubble.innerHTML = contentHtml;
    else bubble.textContent = contentHtml;
    wrap.appendChild(who);
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    scrollBottom();
    return { el: wrap, bubble: bubble };
  }

  const WELCOME = '你好，我是「知衡」🌿\n\n我会按**长期健康优先**的原则，结合你的档案，客观、全面、靠谱地回答健康问题。\n\n- 直接告诉我你的情况，我会给出可执行的建议\n- 去「我的档案」补一点身体数据，我会更懂你\n- 记得先在「设置」里填好 API Key\n\n*我不做诊断、不开处方，急症请直接拨打 120。*';

  function showWelcome() {
    messagesEl.innerHTML = '';
    const m = addMessage('assistant', '', true);
    m.bubble.innerHTML = renderMarkdown(WELCOME);
  }

  function appendMarkdownMessage(role, md) {
    const m = addMessage('assistant', '', true);
    m.bubble.innerHTML = renderMarkdown(md);
    return m;
  }

  function appendUserMessage(text, imageUrls) {
    const m = addMessage('user', '', true);
    let html = '';
    if (imageUrls && imageUrls.length) {
      html += '<div class="msg-imgs">' + imageUrls.map(function (u) {
        return '<img src="' + u + '" alt="图片">';
      }).join('') + '</div>';
    }
    if (text) {
      html += '<div class="msg-text">' + escapeHtml(text).replace(/\n/g, '<br>') + '</div>';
    }
    m.bubble.innerHTML = html;
    return m;
  }

  async function sendMessage() {
    const text = inputEl.value.trim();
    const imageUrls = pendingImages.slice();
    if ((!text && !imageUrls.length) || sending) return;
    sending = true;
    sendBtn.disabled = true;
    inputEl.value = '';
    pendingImages = [];
    renderPendingImages();
    const mode = deepModeEl.checked ? 'deep' : 'fast';

    appendUserMessage(text, imageUrls);
    const asst = addMessage('assistant', '<span class="typing">正在思考…</span>', true);

    let buffer = '';
    let safety = false;
    let err = false;
    let sseBuf = '';

    const handleDelta = (delta, isSafety) => {
      buffer += delta;
      if (isSafety) safety = true;
      asst.bubble.innerHTML = escapeHtml(buffer).replace(/\n/g, '<br>') + '<span class="typing">▍</span>';
      scrollBottom();
    };
    const handleError = (msg) => {
      err = true;
      buffer = msg;
    };

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, mode: mode, images: imageUrls }),
      });
      if (!resp.ok) {
        buffer = '请求失败（HTTP ' + resp.status + '）。请确认服务正在运行。';
        err = true;
      } else {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let streamDone = false;
        while (!streamDone) {
          const { value, done } = await reader.read();
          if (done) break;
          sseBuf += decoder.decode(value, { stream: true });
          // 处理完整的 \n\n 事件
          let idx;
          while ((idx = sseBuf.indexOf('\n\n')) !== -1) {
            const event = sseBuf.slice(0, idx);
            sseBuf = sseBuf.slice(idx + 2);
            const dataLine = event.split('\n').find(l => l.trim().startsWith('data:'));
            if (!dataLine) continue;
            const data = dataLine.slice(5).trim();
            if (data === '[DONE]') { streamDone = true; break; }
            try {
              const obj = JSON.parse(data);
              if (obj.done) { streamDone = true; break; }
              if (obj.error) { handleError(obj.delta || obj.error); continue; }
              if (obj.delta !== undefined) handleDelta(obj.delta, !!obj.safety);
            } catch (e) { /* 忽略 */ }
          }
        }
      }
    } catch (e) {
      err = true;
      buffer = '请求失败：' + e.message + '。请确认服务正在运行、网络正常。';
    }

    // 最终渲染
    if (buffer) {
      asst.bubble.innerHTML = renderMarkdown(buffer);
    } else {
      asst.bubble.innerHTML = '<span class="muted">（没有收到回复）</span>';
    }
    if (safety) asst.el.classList.add('safety');
    sending = false;
    sendBtn.disabled = false;
    scrollBottom();
  }

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  clearBtn.addEventListener('click', async () => {
    if (!confirm('确定要清空当前对话历史吗？')) return;
    await fetch('/api/clear', { method: 'POST' });
    showWelcome();
  });

  // 深度分析开关状态持久化
  deepModeEl.checked = localStorage.getItem('deepMode') === '1';
  deepModeEl.addEventListener('change', () => localStorage.setItem('deepMode', deepModeEl.checked ? '1' : '0'));

  // ---------- 档案收集 / 回填 ----------
  function prune(obj) {
    if (Array.isArray(obj)) {
      const a = obj.map(prune).filter(v => v !== undefined && v !== null && v !== '' &&
        !(typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0));
      return a;
    }
    if (obj && typeof obj === 'object') {
      const out = {};
      for (const k in obj) {
        const v = prune(obj[k]);
        if (v === undefined || v === null || v === '') continue;
        if (typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length === 0) continue;
        if (Array.isArray(v) && v.length === 0) continue;
        out[k] = v;
      }
      return out;
    }
    return obj;
  }

  function collectNested(container) {
    const obj = {};
    $$('[data-k]', container).forEach(el => {
      const k = el.dataset.k;
      const v = el.value.trim();
      const parts = k.split('.');
      let cur = obj;
      for (let i = 0; i < parts.length - 1; i++) {
        cur[parts[i]] = cur[parts[i]] || {};
        cur = cur[parts[i]];
      }
      cur[parts[parts.length - 1]] = v;
    });
    return prune(obj);
  }

  function fillNested(container, profile) {
    $$('[data-k]', container).forEach(el => {
      const k = el.dataset.k;
      let v = profile;
      for (const p of k.split('.')) { v = (v && typeof v === 'object') ? v[p] : undefined; }
      if (v !== undefined && v !== null) el.value = v;
    });
  }

  // ---------- 体检指标动态行 ----------
  const labsEl = $('#labs');

  function labRowHtml(d) {
    d = d || {};
    return '<div class="lab-row">' +
      '<input class="l-date" placeholder="日期 如 2026-08-15" value="' + escapeHtml(d['日期'] || '') + '">' +
      '<input class="l-name" placeholder="指标 如 空腹血糖" value="' + escapeHtml(d['指标'] || '') + '">' +
      '<input class="l-val" placeholder="数值 如 5.2" value="' + escapeHtml(d['数值'] || '') + '">' +
      '<input class="l-unit" placeholder="单位 如 mmol/L" value="' + escapeHtml(d['单位'] || '') + '">' +
      '<input class="l-ref" placeholder="参考范围 3.9–6.1" value="' + escapeHtml(d['参考范围'] || '') + '">' +
      '<button type="button" class="l-del" title="删除这一条">✕</button>' +
      '</div>';
  }

  function collectLabs() {
    const rows = [];
    $$('.lab-row', labsEl).forEach(row => {
      const d = {
        '日期': $('.l-date', row).value.trim(),
        '指标': $('.l-name', row).value.trim(),
        '数值': $('.l-val', row).value.trim(),
        '单位': $('.l-unit', row).value.trim(),
        '参考范围': $('.l-ref', row).value.trim(),
      };
      if (d['指标'] && d['数值']) rows.push(d);
    });
    return rows;
  }

  $('#addLab').addEventListener('click', () => {
    labsEl.appendChild((() => { const t = document.createElement('div'); t.innerHTML = labRowHtml(); return t.firstChild; })());
  });
  labsEl.addEventListener('click', (e) => {
    if (e.target.classList.contains('l-del')) e.target.closest('.lab-row').remove();
  });

  // ---------- 档案保存 / 加载 ----------
  $('#saveProfile').addEventListener('click', async () => {
    try {
      const profile = collectNested($('#profileForm'));
      profile['体检指标'] = collectLabs();
      const resp = await fetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: profile }),
      });
      flash($('#profileStatus'), resp.ok ? '已保存 ✓' : '保存失败');
    } catch (err) {
      console.error('保存档案失败:', err);
      flash($('#profileStatus'), '保存出错：' + (err && err.message ? err.message : err));
    }
  });

  function flash(el, text) {
    el.textContent = text;
    el.classList.remove('err');
    if (text.includes('失败')) el.classList.add('err');
    setTimeout(() => { if (el.textContent === text) el.textContent = ''; }, 2500);
  }

  async function loadProfile() {
    try {
      const r = await fetch('/api/profile');
      const data = await r.json();
      const profile = data.profile || {};
      fillNested($('#profileForm'), profile);
      // 体检指标
      labsEl.innerHTML = '';
      (profile['体检指标'] || []).forEach(d => {
        labsEl.appendChild((() => { const t = document.createElement('div'); t.innerHTML = labRowHtml(d); return t.firstChild; })());
      });

      return profile;
    } catch (e) {
      return {};
    }
  }

  // ---------- 设置 ----------
  const cfgKey = $('#cfgKey');
  const cfgBase = $('#cfgBase');
  const cfgFast = $('#cfgFast');
  const cfgDeep = $('#cfgDeep');
  const cfgTemp = $('#cfgTemp');
  const cfgAccessPw = $('#cfgAccessPw');
  const keyHint = $('#keyHint');
  const accessPwHint = $('#accessPwHint');
  const cfgStatus = $('#cfgStatus');

  async function loadConfig() {
    try {
      const r = await fetch('/api/config');
      const c = await r.json();
      cfgBase.value = c.base_url || '';
      cfgFast.value = c.model_fast || '';
      cfgDeep.value = c.model_deep || '';
      cfgTemp.value = c.temperature != null ? c.temperature : '';
      if (c.api_key_set) {
        keyHint.textContent = '已设置 Key（尾号 ' + c.api_key_tail + '），留空表示不修改';
      } else {
        keyHint.textContent = '尚未设置 Key，请填入后保存';
      }
      if (c.access_password_set) {
        accessPwHint.textContent = '已设置密码，留空表示不修改；忘记密码可在启动窗口里查看';
      } else {
        accessPwHint.textContent = '尚未设置密码，填入 6 位数字后保存即可生效';
      }
      return c;
    } catch (e) {
      return {};
    }
  }

  $('#saveCfg').addEventListener('click', async () => {
    const body = {
      base_url: cfgBase.value.trim(),
      model_fast: cfgFast.value.trim(),
      model_deep: cfgDeep.value.trim(),
      temperature: cfgTemp.value,
    };
    if (cfgKey.value.trim()) body.api_key = cfgKey.value.trim();
    if (cfgAccessPw.value.trim()) body.access_password = cfgAccessPw.value.trim();
    const resp = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (resp.ok) {
      cfgKey.value = '';
      cfgAccessPw.value = '';
      flash(cfgStatus, '已保存 ✓');
      await loadConfig();
    } else {
      flash(cfgStatus, '保存失败');
    }
  });

  $('#clearKey').addEventListener('click', async () => {
    if (!confirm('确定要清除已保存的 API Key 吗？')) return;
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clear_api_key: true }),
    });
    cfgKey.value = '';
    flash(cfgStatus, '已清除 Key');
    await loadConfig();
  });

  // ---------- 我的画像 ----------
  const autoRefineEl = $('#autoRefine');
  const refineNowBtn = $('#refineNow');
  const refineStatusEl = $('#refineStatus');
  const refineHintEl = $('#refineHint');
  const imageListEl = $('#imageList');
  const recentListEl = $('#recentList');
  const newImageContentEl = $('#newImageContent');
  const newImageDomainEl = $('#newImageDomain');
  const addImageBtn = $('#addImage');

  function domainTag(d) {
    return '<span class="tag">' + escapeHtml(d || '其他') + '</span>';
  }

  function imageItemHtml(it, editable) {
    const meta = '<span class="muted small">' + escapeHtml(it.source || '') + '</span>';
    const actions = editable
      ? '<button type="button" class="img-edit ghost">编辑</button><button type="button" class="img-del ghost">删除</button>'
      : '<button type="button" class="img-del ghost">删除</button>';
    return '<div class="image-item" data-id="' + it.id + '" data-content="' + escapeHtml(it.content) + '" data-domain="' + escapeHtml(it.domain || '其他') + '">' +
      '<div class="image-item-text"><span class="image-content">' + escapeHtml(it.content) + '</span> ' + domainTag(it.domain) + ' ' + meta + '</div>' +
      '<div class="image-item-actions">' + actions + '</div></div>';
  }

  function renderImageList(items, container, editable) {
    container.innerHTML = '';
    if (!items.length) {
      container.innerHTML = '<p class="muted">（暂无内容）</p>';
      return;
    }
    items.forEach(it => {
      const t = document.createElement('div');
      t.innerHTML = imageItemHtml(it, editable);
      container.appendChild(t.firstChild);
    });
  }

  async function loadImage() {
    try {
      const r = await fetch('/api/image');
      const data = await r.json();
      autoRefineEl.checked = data.auto_refine !== false;
      renderImageList(data.images || [], imageListEl, true);
      renderImageList(data.recent || [], recentListEl, false);
      const n = data.counter || 0;
      const th = data.threshold || 5;
      refineHintEl.textContent = (data.auto_refine !== false)
        ? ('自动提炼已开启：已累计 ' + n + ' / ' + th + ' 条消息，满 ' + th + ' 条自动提炼。')
        : '自动提炼已关闭，可点「立即提炼」手动更新。';
    } catch (e) {
      refineHintEl.textContent = '加载失败：' + (e && e.message ? e.message : e);
    }
  }

  refineNowBtn.addEventListener('click', async () => {
    refineNowBtn.disabled = true;
    flash(refineStatusEl, '正在提炼…');
    try {
      const resp = await fetch('/api/refine', { method: 'POST' });
      const data = await resp.json();
      if (data.ok) {
        if (data.added_long || data.added_recent) {
          flash(refineStatusEl, '已提炼：长期 +' + (data.added_long || 0) + '，近期 +' + (data.added_recent || 0));
        } else if (data.skipped) {
          flash(refineStatusEl, '没有可提炼的对话记录');
        } else {
          flash(refineStatusEl, '这次没有提炼到新内容');
        }
        await loadImage();
      } else {
        flash(refineStatusEl, '提炼失败：' + (data.error || '未知错误'));
      }
    } catch (e) {
      flash(refineStatusEl, '提炼出错：' + (e && e.message ? e.message : e));
    }
    refineNowBtn.disabled = false;
  });

  autoRefineEl.addEventListener('change', async () => {
    await fetch('/api/refine_config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto_refine: autoRefineEl.checked }),
    });
    await loadImage();
  });

  addImageBtn.addEventListener('click', async () => {
    const content = newImageContentEl.value.trim();
    if (!content) { flash(refineStatusEl, '请先填写内容'); return; }
    const domain = newImageDomainEl.value.trim() || '其他';
    const resp = await fetch('/api/image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'add', content: content, domain: domain }),
    });
    if (resp.ok) {
      newImageContentEl.value = '';
      newImageDomainEl.value = '';
      flash(refineStatusEl, '已添加 ✓');
      await loadImage();
    } else {
      flash(refineStatusEl, '添加失败');
    }
  });

  imageListEl.addEventListener('click', async (e) => {
    const item = e.target.closest('.image-item');
    if (!item) return;
    const id = Number(item.dataset.id);
    if (e.target.classList.contains('img-del')) {
      if (!confirm('确定删除这条画像吗？')) return;
      await fetch('/api/image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id: id }),
      });
      await loadImage();
    } else if (e.target.classList.contains('img-edit')) {
      const newContent = prompt('修改画像内容：', item.dataset.content || '');
      if (newContent !== null && newContent.trim()) {
        await fetch('/api/image', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'update', id: id, content: newContent.trim(), domain: item.dataset.domain || '其他' }),
        });
        await loadImage();
      }
    }
  });

  recentListEl.addEventListener('click', async (e) => {
    const item = e.target.closest('.image-item');
    if (!item || !e.target.classList.contains('img-del')) return;
    if (!confirm('确定删除这条近期状态吗？')) return;
    await fetch('/api/recent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'delete', id: Number(item.dataset.id) }),
    });
    await loadImage();
  });

  // ---------- 首次引导 ----------
  async function initOnboard(profile) {
    const hasProfile = profile && Object.keys(profile).length > 0;
    if (hasProfile || localStorage.getItem('onboardSkipped') === '1') {
      $('#onboard').classList.add('hidden');
    } else {
      $('#onboard').classList.remove('hidden');
    }
  }

  $('#goProfile').addEventListener('click', () => {
    $('#onboard').classList.add('hidden');
    switchView('profile');
  });
  $('#skipOnboard').addEventListener('click', () => {
    localStorage.setItem('onboardSkipped', '1');
    $('#onboard').classList.add('hidden');
    switchView('chat');
  });

  // ---------- 初始化 ----------
  async function init() {
    const profile = await loadProfile();
    await loadConfig();
    await loadImage();
    await initOnboard(profile);

    // 恢复历史（若有），否则显示欢迎语
    try {
      const r = await fetch('/api/messages');
      const data = await r.json();
      const msgs = data.messages || [];
      if (msgs.length) {
        messagesEl.innerHTML = '';
        msgs.forEach(m => {
          if (m.role === 'user') {
            const urls = (m.images || []).map(n => '/api/images/' + encodeURIComponent(n));
            appendUserMessage(m.content, urls);
          } else {
            appendMarkdownMessage('assistant', m.content);
          }
        });
        scrollBottom();
      } else {
        showWelcome();
      }
    } catch (e) {
      showWelcome();
    }
  }

  init();
})();
