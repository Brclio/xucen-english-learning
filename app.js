(() => {
  'use strict';
  const data = window.COURSE_DATA || { title: '课程学习室', lessons: [] };
  const lessons = (Array.isArray(data.lessons) ? data.lessons : []).map((lesson, index) => ({ ...lesson, id: String(lesson.id || `lesson-${index + 1}`), index: lesson.index ?? index + 1 }));
  const $ = (selector) => document.querySelector(selector);
  const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const localPath = value => {
    const path = String(value || '').trim();
    if (!path || /^(?:[a-z][a-z\d+.-]*:|\/\/|\\)/i.test(path) || /[\u0000-\u001f]/.test(path)) return '';
    return path;
  };
  const externalUrl = value => { try { const url = new URL(value); return /^https?:$/.test(url.protocol) ? url.href : ''; } catch { return ''; } };
  const link = (path, label, cls = '', download = false) => localPath(path) ? `<a class="${cls}" href="${escape(localPath(path))}"${download ? ' download' : ''}>${label}</a>` : '';
  const originalLink = (url, label = '查看原课程 ↗', cls = '') => externalUrl(url) ? `<a class="${cls}" href="${escape(externalUrl(url))}" target="_blank" rel="noopener noreferrer">${label}</a>` : '';
  const safeHTML = (html) => {
    const source = new DOMParser().parseFromString(String(html || ''), 'text/html');
    const allowed = new Set(['P','DIV','SPAN','BR','HR','H1','H2','H3','H4','H5','H6','STRONG','B','EM','I','U','S','DEL','SUP','SUB','BLOCKQUOTE','PRE','CODE','UL','OL','LI','TABLE','THEAD','TBODY','TFOOT','TR','TH','TD','A','IMG','FIGURE','FIGCAPTION','VIDEO','AUDIO','SOURCE']);
    const remove = new Set(['SCRIPT','STYLE','IFRAME','OBJECT','EMBED','FORM','INPUT','BUTTON','TEXTAREA','SELECT','LINK','META','BASE','SVG','MATH','TEMPLATE']);
    for (const element of [...source.body.querySelectorAll('*')]) {
      if (remove.has(element.tagName)) { element.remove(); continue; }
      if (!allowed.has(element.tagName)) { element.replaceWith(...element.childNodes); continue; }
      const attrs = Object.fromEntries([...element.attributes].map(a => [a.name, a.value]));
      for (const attr of [...element.attributes]) element.removeAttribute(attr.name);
      if (element.tagName === 'A') {
        const href = localPath(attrs.href) || externalUrl(attrs.href);
        if (href) element.setAttribute('href', href);
        if (externalUrl(href)) { element.setAttribute('target', '_blank'); element.setAttribute('rel', 'noopener noreferrer'); }
      }
      if (['IMG','VIDEO','AUDIO','SOURCE'].includes(element.tagName)) {
        const src = localPath(attrs.src);
        if (!src && element.tagName === 'IMG') { element.replaceWith(source.createTextNode(attrs.alt || '（图片尚未下载）')); continue; }
        if (src) element.setAttribute('src', src);
        if (element.tagName === 'IMG') { element.setAttribute('alt', attrs.alt || '课程配图'); element.setAttribute('loading', 'lazy'); }
        if (['VIDEO','AUDIO'].includes(element.tagName)) { element.setAttribute('controls', ''); element.setAttribute('preload', 'metadata'); }
        if (element.tagName === 'VIDEO' && localPath(attrs.poster)) element.setAttribute('poster', localPath(attrs.poster));
        if (element.tagName === 'SOURCE' && /^\w+\/[\w.+-]+$/.test(attrs.type || '')) element.setAttribute('type', attrs.type);
      }
      if (['TD','TH'].includes(element.tagName)) for (const attr of ['colspan','rowspan']) if (/^\d{1,2}$/.test(attrs[attr] || '')) element.setAttribute(attr, attrs[attr]);
    }
    return source.body.innerHTML;
  };
  const title = data.title || '课程学习室';
  document.title = `${title} · 本地学习室`;
  $('#course-title').textContent = title;
  const storageKey = `local-course:${data.sourceUrl || title}:v1`;
  let state = { done: {}, notes: {}, positions: {}, lastLesson: null };
  let storageAvailable = true;
  try { const stored = JSON.parse(localStorage.getItem(storageKey) || 'null'); if (stored && typeof stored === 'object') for (const key of ['done','notes','positions']) if (stored[key] && typeof stored[key] === 'object') state[key] = stored[key]; if (stored?.lastLesson) state.lastLesson = stored.lastLesson; } catch { storageAvailable = false; }
  const save = () => { try { localStorage.setItem(storageKey, JSON.stringify(state)); return true; } catch { storageAvailable = false; return false; } };
  let activeId = null;
  let pendingDeepLink = null;
  let toastTimer;
  const toast = message => { $('#toast').textContent = message; $('#toast').classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 2800); };
  const type = lesson => lesson.videoPath || /video|视频|^3$/i.test(lesson.type || '') ? 'video' : lesson.audioPath || /audio|音频|^2$/i.test(lesson.type || '') ? 'audio' : 'text';
  const typeNames = { video: '视频', audio: '音频', text: '图文' };
  const statusNames = { downloaded: '完整保存', partial: '部分保存', locked: '需登录 / 购买', pending: '待下载', failed: '下载未完成' };
  const complete = lesson => lesson.status === 'downloaded' && lesson.videoStatus !== 'drm';
  const available = lesson => complete(lesson) || lesson.status === 'partial' && hasContent(lesson);
  const hasContent = lesson => !!(localPath(lesson.videoPath) || localPath(lesson.audioPath) || lesson.descriptionHtml || localPath(lesson.markdownPath) || (lesson.attachments || []).some(a => localPath(a.path)));
  const duration = value => { if (value === undefined || value === null || value === '') return ''; if (typeof value === 'string' && !/^\d+(\.\d+)?$/.test(value)) return value; const n = Math.round(Number(value)); if (!n) return ''; return n >= 3600 ? `${Math.floor(n / 3600)}:${String(Math.floor(n % 3600 / 60)).padStart(2, '0')}:${String(n % 60).padStart(2,'0')}` : `${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`; };
  const quality = value => typeof value === 'object' && value !== null ? value.label || value.name || (value.height ? `${value.height}p` : '') : value || '';
  const labelFor = lesson => statusNames[lesson.status] || '待下载';
  function updateProgress() {
    const count = lessons.filter(l => state.done[l.id]).length;
    $('#progress-label').textContent = `${count} / ${lessons.length}`;
    $('#progress').max = Math.max(lessons.length, 1);
    $('#progress').value = count;
  }
  function renderList() {
    const query = $('#search').value.trim().toLocaleLowerCase();
    const selectedType = $('#type-filter').value;
    const selectedStatus = $('#status-filter').value;
    const filtered = lessons.filter(l => (!query || `${l.title || ''} ${l.index}`.toLocaleLowerCase().includes(query)) && (selectedType === 'all' || type(l) === selectedType) && (selectedStatus === 'all' || selectedStatus === 'available' && available(l) || selectedStatus === 'unfinished' && !state.done[l.id] || selectedStatus === 'done' && state.done[l.id] || selectedStatus === 'pending' && !complete(l) || selectedStatus === 'partial' && l.status === 'partial'));
    $('#list-caption').textContent = query || selectedType !== 'all' || selectedStatus !== 'all' ? `找到 ${filtered.length} 节课程` : `共 ${lessons.length} 节课程`;
    $('#lesson-list').innerHTML = filtered.length ? filtered.map(l => `<button class="lesson-button${l.id === activeId ? ' active' : ''}" data-id="${escape(l.id)}"${l.id === activeId ? ' aria-current="page"' : ''}><span class="lesson-number">${escape(String(l.index).padStart(2,'0'))}</span><span class="lesson-main"><span class="lesson-name">${escape(l.title || '未命名课程')}</span><span class="lesson-meta"><span>${typeNames[type(l)]}${duration(l.duration) ? ` · ${escape(duration(l.duration))}` : ''}</span><span class="${available(l) ? 'downloaded' : ''}">${escape(labelFor(l))}</span></span></span>${state.done[l.id] ? '<span class="done-icon" aria-label="已学完">✓</span>' : ''}</button>`).join('') : `<p class="empty">${lessons.length ? '没有匹配的课程。<br>换一个关键词或筛选条件试试。' : '课程目录尚未导入。<br>下载完成后重新打开本页即可查看。'}</p>`;
    $('#lesson-list').querySelectorAll('[data-id]').forEach(button => button.addEventListener('click', () => showLesson(button.dataset.id)));
    updateProgress();
  }
  function setMenu(open) { $('#sidebar').classList.toggle('is-open', open); $('#menu-button').setAttribute('aria-expanded', String(open)); $('#menu-button').textContent = open ? '收起目录' : '课程目录'; }
  function topOfContent() { if (matchMedia('(max-width: 760px)').matches) setMenu(false); window.scrollTo({ top: 0, behavior: 'instant' }); }
  function showOverview() {
    activeId = null;
    try { history.replaceState(null, '', location.pathname + location.search + '#overview'); } catch { /* file mode can restrict history */ }
    renderList();
    const downloaded = lessons.filter(complete).length;
    const videoCount = lessons.filter(l => localPath(l.videoPath)).length;
    const audioCount = lessons.filter(l => localPath(l.audioPath)).length;
    const summaryMessage = typeof data.summary?.message === 'string' ? data.summary.message : '';
    const summaryHtml = summaryMessage ? escape(summaryMessage).replace(/\n/g, '<br>') : '';
    const done = lessons.filter(l => state.done[l.id]).length;
    const next = lessons.find(l => l.id === state.lastLesson && hasContent(l)) || lessons.find(l => available(l) && !state.done[l.id]) || lessons.find(hasContent) || lessons[0];
    const cover = localPath(data.cover);
    const courseAttachments = (Array.isArray(data.attachments) ? data.attachments : []).filter(a => localPath(a.path));
    const documents = courseAttachments.filter(a => a.kind !== 'image');
    const courseImages = courseAttachments.filter(a => a.kind === 'image');
    const resourcesHtml = courseAttachments.length ? `<section class="overview-section course-resources"><h3>课程资料</h3><div class="resource-documents">${documents.map(a => link(a.path, `${escape(a.name || '课程资料')} ↓`, 'button', true)).join('')}</div>${courseImages.length ? `<details class="image-resources"><summary>查看全部 ${courseImages.length} 张课程图片</summary><div class="resource-images">${courseImages.map(a => link(a.path, `<img src="${escape(localPath(a.path))}" alt="${escape(a.name || '课程图片')}" loading="lazy"><span>${escape(a.name || '课程图片')}<small>${a.bytes ? `${(Number(a.bytes) / 1024 / 1024).toFixed(2)} MB · ` : ''}下载原文件 ↓</small></span>`, 'resource-image', true)).join('')}</div></details>` : ''}</section>` : '';
    const updated = data.updatedAt ? new Date(data.updatedAt) : null;
    const updateLabel = updated && !Number.isNaN(updated.getTime()) ? updated.toLocaleString('zh-CN', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' }) : '';
    $('#content').innerHTML = `<div class="breadcrumb"><span>我的学习室</span><span>/</span><span>课程总览</span></div><section class="overview-header ${cover ? '' : 'no-cover'}"><div><div class="lesson-kicker">一份可以随时翻开的学习资料</div><h2 class="overview-heading">${escape(title)}</h2><p class="overview-subtitle">从一节课开始，按自己的节奏学习。已保存的课程资料与学习记录，都在这里。</p><div class="overview-actions">${next ? `<button class="button primary" id="start-learning">${state.lastLesson ? '继续学习' : '开始学习'} <span aria-hidden="true">→</span></button>` : ''}<a class="button subtle" href="books.html">绘本书架 →</a>${originalLink(data.sourceUrl, '原课程页面 ↗', 'button subtle')}</div></div>${cover ? `<img class="overview-cover" src="${escape(cover)}" alt="${escape(title)}课程封面">` : ''}</section><div class="overview-stats"><span><strong>${lessons.length}</strong>节课程</span><span><strong>${videoCount}</strong>个本地视频</span><span><strong>${audioCount}</strong>个本地音频</span><span><strong>${downloaded}</strong>节完整保存</span><span><strong>${done}</strong>节已学完</span></div>${summaryHtml || downloaded < lessons.length || !lessons.length ? `<div class="notice download-status"><span class="notice-icon" aria-hidden="true">i</span><div><h3>${lessons.length ? downloaded < lessons.length ? '课程资料已部分保存' : '本地资料状态' : '等待课程资料导入'}</h3><p>${summaryHtml || (lessons.length ? `当前 ${downloaded} / ${lessons.length} 节完整保存。本地视频 ${videoCount} 个，本地音频 ${audioCount} 个；部分保存的课程会保留在目录中，并标明实际状态。` : '本页会展示实际获取的课程目录与资料；目前还没有可显示的课程。')}${updateLabel ? `<br>资料更新时间：${escape(updateLabel)}` : ''}</p></div></div>` : updateLabel ? `<p class="archive-summary" style="margin-top:18px">资料更新时间：${escape(updateLabel)}</p>` : ''}${resourcesHtml}${data.descriptionHtml ? `<section class="overview-section"><h3>关于这门课</h3><div class="prose">${safeHTML(data.descriptionHtml)}</div></section>` : ''}<section class="overview-section"><h3>让每一次学习留下记录</h3><div class="archive-summary"><p>选择左侧课程即可播放本地视频、收听音频或阅读图文。课程中的 Markdown 与附件可直接保存。完成一节课后，点击「标记学完」记录进度。</p><p>在「学习笔记」里记下新词、例句与疑问。笔记和播放位置保存在当前浏览器，可随时导出全部笔记。更换浏览器或清理浏览器数据前，请先导出备份。</p>${!storageAvailable ? '<p>当前浏览器无法持久保存记录，请及时导出笔记。</p>' : ''}</div></section>`;
    if (next) $('#start-learning').addEventListener('click', () => showLesson(next.id));
    topOfContent();
  }
  function showLesson(id) {
    const lesson = lessons.find(l => l.id === id);
    if (!lesson) return showOverview();
    activeId = id; state.lastLesson = id; save();
    try { history.replaceState(null, '', `${location.pathname}${location.search}#lesson=${encodeURIComponent(id)}`); } catch { /* history may be restricted */ }
    renderList();
    const video = localPath(lesson.videoPath), audio = localPath(lesson.audioPath), poster = localPath(lesson.poster), attachments = Array.isArray(lesson.attachments) ? lesson.attachments.filter(a => localPath(a.path)) : [];
    const content = safeHTML(lesson.descriptionHtml);
    const index = lessons.indexOf(lesson), previous = lessons[index - 1], next = lessons[index + 1];
    $('#content').innerHTML = `<div class="breadcrumb"><button id="breadcrumb-home">课程总览</button><span>/</span><span>第 ${escape(lesson.index)} 课</span></div><header class="lesson-header"><div><div class="lesson-kicker"><span>${escape(String(lesson.index).padStart(2,'0'))}</span> / ${typeNames[type(lesson)]}课程</div><h2>${escape(lesson.title || '未命名课程')}</h2><div class="metadata"><span>${escape(labelFor(lesson))}</span>${duration(lesson.duration) ? `<span>时长 ${escape(duration(lesson.duration))}</span>` : ''}${lesson.videoStatus === 'drm' ? '<span>平台视频受 DRM 保护</span>' : quality(lesson.quality) ? `<span>${escape(quality(lesson.quality))}</span>` : ''}</div></div><button class="button mark-done${state.done[id] ? ' completed' : ''}" id="mark-done" aria-pressed="${!!state.done[id]}">${state.done[id] ? '✓ 已学完' : '○ 标记学完'}</button></header>${!complete(lesson) ? `<div class="notice"><span class="notice-icon" aria-hidden="true">i</span><div><h3>${escape(labelFor(lesson))}</h3><p>${lesson.videoStatus === 'drm' ? `${audio ? '音频已本地保存；' : ''}视频受 DRM 保护，需前往课程平台观看。` : lesson.status === 'partial' ? '本节已保存部分资料，可在下方学习。其余内容尚未完整下载。' : lesson.status === 'locked' ? '本节完整内容需要在原课程平台登录具有访问权限的账号后获取。已取得的文字与附件仍可在下方查看。' : lesson.status === 'failed' ? '本节资料尚未完整下载，已获取的内容保留在下方。可稍后补充下载。' : '本节尚未完成下载。目录信息已保留，已获取的资料可在下方查看。'}</p>${originalLink(lesson.sourceUrl || data.sourceUrl)}</div></div>` : ''}${video ? `<div class="player-shell"><video id="main-media" controls playsinline preload="metadata"${poster ? ` poster="${escape(poster)}"` : ''} src="${escape(video)}"></video></div><div class="player-footer"><span>本地视频 · 自动记住播放位置</span>${link(video, '打开视频文件 ↗', '', false)}</div>` : audio ? `<div class="player-shell audio-player"><div class="audio-art" aria-hidden="true">♫</div><div class="audio-main"><p>戴上耳机，进入这一课。</p><audio id="main-media" controls preload="metadata" src="${escape(audio)}"></audio></div></div><div class="player-footer"><span>本地音频 · 自动记住播放位置</span>${link(audio, '打开音频文件 ↗')}</div>` : ''}${video && audio ? `<div class="attachment-list">${link(audio, '<span class="attachment-icon">音频</span><span class="attachment-name">本课音频</span><span class="attachment-arrow">↗</span>', 'attachment')}</div>` : ''}<div class="content-tabs" role="tablist" aria-label="课程资料"><button id="tab-content" role="tab" aria-selected="true" aria-controls="panel-content" tabindex="0">课程内容</button><button id="tab-attachments" role="tab" aria-selected="false" aria-controls="panel-attachments" tabindex="-1">资料附件${attachments.length ? ` · ${attachments.length}` : ''}</button><button id="tab-notes" role="tab" aria-selected="false" aria-controls="panel-notes" tabindex="-1">学习笔记${state.notes[id] ? ' ·' : ''}</button></div><section class="panel" id="panel-content" role="tabpanel" aria-labelledby="tab-content"><div class="panel-heading"><h3>本课图文</h3>${link(lesson.markdownPath, '下载 Markdown ↓', 'text-button', true)}</div>${content ? `<article class="prose">${content}</article>` : `<p class="reading-empty">${video || audio ? '本节暂未提供可阅读的图文内容。你可以播放上方课程，并在「学习笔记」里记录自己的收获。' : '本节尚无可离线阅读的图文内容。已下载的其他资料可在「资料附件」中查看。'}</p>`}</section><section class="panel" id="panel-attachments" role="tabpanel" aria-labelledby="tab-attachments" hidden><div class="panel-heading"><h3>本地资料</h3></div>${attachments.length ? `<div class="attachment-list">${attachments.map(a => link(a.path, `<span class="attachment-icon">${escape((a.name || a.path).split('.').pop().slice(0,5).toUpperCase())}</span><span class="attachment-name">${escape(a.name || a.path.split('/').pop())}</span><span class="attachment-arrow">↓</span>`, 'attachment', true)).join('')}</div>` : '<p class="reading-empty">本节暂无已下载的独立附件。</p>'}${localPath(lesson.markdownPath) ? `<p style="margin-top:20px">${link(lesson.markdownPath, '下载本课 Markdown 文稿 ↓', 'text-button', true)}</p>` : ''}</section><section class="panel" id="panel-notes" role="tabpanel" aria-labelledby="tab-notes" hidden><div class="panel-heading"><h3>我的学习笔记</h3></div><p class="notes-intro">记下一句想学会的表达，或一个还没想明白的问题。</p><label class="sr-only" for="notes-text">本课学习笔记</label><textarea class="notes-text" id="notes-text" placeholder="今天学到了什么？\n\n新词 / 例句 / 我的理解…">${escape(state.notes[id] || '')}</textarea><div class="notes-footer"><span id="notes-status">${storageAvailable ? '输入后自动保存到当前浏览器' : '浏览器无法保存记录，请及时导出'}</span><button id="export-lesson-note" class="text-button">导出本课笔记 ↓</button></div></section><nav class="lesson-navigation" aria-label="相邻课程"><button id="previous-lesson" ${previous ? '' : 'disabled'}><span>← 上一课</span><strong>${escape(previous?.title || '已经是第一课')}</strong></button><button id="next-lesson" ${next ? '' : 'disabled'}><span>下一课 →</span><strong>${escape(next?.title || '已经是最后一课')}</strong></button></nav>`;
    $('#breadcrumb-home').addEventListener('click', showOverview);
    $('#mark-done').addEventListener('click', () => { state.done[id] = !state.done[id]; const saved = save(); const button = $('#mark-done'); button.classList.toggle('completed', !!state.done[id]); button.setAttribute('aria-pressed', String(!!state.done[id])); button.textContent = state.done[id] ? '✓ 已学完' : '○ 标记学完'; renderList(); toast(saved ? state.done[id] ? '已记录完成，继续保持。' : '已取消完成标记' : '当前浏览器无法保存进度'); });
    if (previous) $('#previous-lesson').addEventListener('click', () => showLesson(previous.id));
    if (next) $('#next-lesson').addEventListener('click', () => showLesson(next.id));
    const tabs = [...document.querySelectorAll('[role=tab]')];
    function selectTab(tab) { tabs.forEach(t => { const selected = t === tab; t.setAttribute('aria-selected', String(selected)); t.tabIndex = selected ? 0 : -1; document.getElementById(t.getAttribute('aria-controls')).hidden = !selected; }); }
    tabs.forEach((tab, i) => { tab.addEventListener('click', () => selectTab(tab)); tab.addEventListener('keydown', event => { let target; if (event.key === 'ArrowRight') target = tabs[(i+1)%tabs.length]; else if (event.key === 'ArrowLeft') target = tabs[(i+tabs.length-1)%tabs.length]; else if (event.key === 'Home') target = tabs[0]; else if (event.key === 'End') target = tabs.at(-1); if (target) { event.preventDefault(); selectTab(target); target.focus(); } }); });
    $('#notes-text').addEventListener('input', event => { state.notes[id] = event.target.value; $('#notes-status').textContent = save() ? '已保存到当前浏览器' : '保存失败，请导出笔记备份'; $('#tab-notes').textContent = `学习笔记${event.target.value ? ' ·' : ''}`; });
    $('#export-lesson-note').addEventListener('click', () => downloadNotes([lesson]));
    const media = $('#main-media');
    if (media) {
      let lastSave = 0;
      media.addEventListener('loadedmetadata', () => {
        if (pendingDeepLink?.id === id) {
          media.currentTime = Math.max(0, Math.min(pendingDeepLink.time, Math.max(0, media.duration - 0.25)));
          pendingDeepLink = null;
          return;
        }
        const position = Number(state.positions[id]);
        if (position > 0 && position < media.duration - 3) media.currentTime = position;
      });
      const savePosition = () => { state.positions[id] = media.currentTime; save(); };
      media.addEventListener('timeupdate', () => { if (Date.now() - lastSave > 4000) { savePosition(); lastSave = Date.now(); } });
      media.addEventListener('pause', savePosition);
      media.addEventListener('ended', () => { state.positions[id] = 0; save(); toast('本课播放完毕，可点击「标记学完」记录进度'); });
      media.addEventListener('error', () => toast('本地媒体无法播放，请检查文件是否完整，或用本地播放器打开'));
    }
    topOfContent();
  }
  function downloadNotes(selectedLessons) {
    const withNotes = selectedLessons.filter(l => String(state.notes[l.id] || '').trim());
    if (!withNotes.length) { toast('还没有笔记，先写下你的第一条学习记录吧。'); return; }
    const content = `# ${title} · 学习笔记\n\n导出时间：${new Date().toLocaleString('zh-CN')}\n\n` + withNotes.map(l => `## ${l.index}. ${l.title || '未命名课程'}\n\n${state.notes[l.id]}\n`).join('\n---\n\n');
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${title}${selectedLessons.length === 1 ? `-${selectedLessons[0].title || selectedLessons[0].index}` : ''}-学习笔记.md`.replace(/[\\/:*?"<>|]/g, '_'); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast('笔记已导出为 Markdown');
  }
  $('#home-button').addEventListener('click', showOverview);
  $('#overview-button').addEventListener('click', showOverview);
  $('#menu-button').addEventListener('click', () => setMenu(!$('#sidebar').classList.contains('is-open')));
  $('#search').addEventListener('input', renderList);
  $('#type-filter').addEventListener('change', renderList);
  $('#status-filter').addEventListener('change', renderList);
  $('#export-notes').addEventListener('click', () => downloadNotes(lessons));
  const hashParams = new URLSearchParams(location.hash.slice(1));
  const hashId = hashParams.get('lesson') || '';
  const requestedTime = hashParams.has('t') ? Number(hashParams.get('t')) : NaN;
  if (hashId && Number.isFinite(requestedTime) && requestedTime >= 0) pendingDeepLink = { id: hashId, time: requestedTime };
  if (hashId && lessons.some(l => l.id === hashId)) showLesson(hashId); else showOverview();
})();
