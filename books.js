(() => {
  'use strict';
  const data = window.BOOKS_DATA || { books: [] };
  const course = window.COURSE_DATA || { lessons: [] };
  const books = Array.isArray(data.books) ? data.books : [];
  const lessons = new Map((Array.isArray(course.lessons) ? course.lessons : []).map(lesson => [String(lesson.id), lesson]));
  const $ = selector => document.querySelector(selector);
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const localPath = value => { const path = String(value || '').trim(); return path && !/^(?:[a-z][a-z\d+.-]*:|\/\/|\\)/i.test(path) && !/[\u0000-\u001f]/.test(path) ? path : ''; };
  const sourceUrl = value => { try { const url = new URL(value); return /^https?:$/.test(url.protocol) ? url.href : ''; } catch { return ''; } };
  const externalLink = (url, text) => sourceUrl(url) ? `<a href="${escape(sourceUrl(url))}" target="_blank" rel="noopener noreferrer">${escape(text)}</a>` : '';
  const evidenceLabel = kind => ({'lesson-title':'课名明确提及',spoken:'课堂讲述提及','spoken-title':'课堂讲述提及',visual:'画面展示',shown:'画面展示','visible-cover':'画面展示','spoken-and-visible-cover':'讲述与画面展示','reading-match':'朗读内容匹配',reading:'课堂阅读片段',series:'系列提及'}[kind] || '课程提及');
  const evidenceFor = book => Array.isArray(book.mentionEvidence) ? book.mentionEvidence : [];
  const seriesFor = book => String(book.series || '').trim();
  const authorFor = book => Array.isArray(book.author) ? book.author.join(' · ') : String(book.author || '').trim();
  const idsFor = book => [...new Set([...(Array.isArray(book.lessonIds) ? book.lessonIds : []), ...evidenceFor(book).map(e => e.lessonId)].filter(Boolean).map(String))];
  const timeSeconds = value => { if (value === undefined || value === null || value === '') return NaN; if (typeof value === 'string' && /^\d+(?::\d{1,2}){1,2}$/.test(value)) return value.split(':').reduce((total, part) => total * 60 + Number(part), 0); const seconds = Number(value); return Number.isFinite(seconds) && seconds >= 0 ? seconds : NaN; };
  const lessonLink = (id, label, time) => lessons.has(String(id)) ? `<a href="index.html#lesson=${encodeURIComponent(id)}${Number.isFinite(timeSeconds(time)) ? `&amp;t=${timeSeconds(time)}` : ''}">${escape(label || lessons.get(String(id)).title)}</a>` : '';
  const timeLabel = value => { if (value === undefined || value === null || value === '') return ''; if (typeof value === 'string' && !/^\d+(\.\d+)?$/.test(value)) return value; const seconds = Math.floor(Number(value)); if (!Number.isFinite(seconds) || seconds < 0) return ''; return seconds >= 3600 ? `${Math.floor(seconds / 3600)}:${String(Math.floor(seconds % 3600 / 60)).padStart(2,'0')}:${String(seconds % 60).padStart(2,'0')}` : `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2,'0')}`; };
  const series = [...new Set(books.map(seriesFor).filter(Boolean))].sort((a,b) => a.localeCompare(b));
  for (const name of series) { const option = document.createElement('option'); option.value = name; option.textContent = name; $('#book-series').append(option); }
  $('#book-total').textContent = books.length;
  const seriesCount = books.filter(book => book.kind === 'series').length;
  const categoryCount = books.filter(book => book.kind === 'category').length;
  if (seriesCount || categoryCount) $('#book-total-label').textContent = `项课程书目${seriesCount ? `（含 ${seriesCount} 个系列）` : ''}`;
  $('#book-course-title').textContent = course.title || '课程绘本书架';
  if (typeof data.scopeNote === 'string' && data.scopeNote.trim()) $('#book-scope').textContent = data.scopeNote;
  const updated = data.updatedAt ? new Date(data.updatedAt) : null;
  if (updated && Number.isFinite(updated.getTime())) $('#books-updated').textContent = `整理于 ${updated.toLocaleDateString('zh-CN', {year:'numeric',month:'2-digit',day:'2-digit'})}`;
  function card(book) {
    const cover = localPath(book.cover);
    const title = book.title || '书名待核实';
    const author = authorFor(book);
    const related = idsFor(book).filter(id => lessons.has(id));
    const evidence = evidenceFor(book);
    const evidenceHtml = evidence.length ? `<details class="book-evidence"><summary>课程中的提及记录 · ${evidence.length}</summary><ol>${evidence.map(item => `<li>${lessonLink(String(item.lessonId), undefined, item.time) || '<span>课程位置待核实</span>'}${timeLabel(item.time) ? `<span> · ${escape(timeLabel(item.time))}</span>` : ''}<br><span>${escape(evidenceLabel(item.kind))}</span>${item.quote ? `<blockquote>「${escape(item.quote)}」</blockquote>` : ''}${item.note ? `<p class="evidence-note">${escape(item.note)}</p>` : ''}</li>`).join('')}</ol>${book.isbn ? `<p class="book-isbn">ISBN ${escape(book.isbn)}</p>` : ''}</details>` : book.isbn ? `<p class="book-isbn">ISBN ${escape(book.isbn)}</p>` : '';
    return `<article class="book-entry"${book.id ? ` id="book-${escape(book.id)}"` : ''}><div class="book-cover-wrap">${cover ? `<a class="book-cover-link" href="${escape(cover)}" target="_blank" rel="noopener" aria-label="查看《${escape(title)}》封面大图"><img class="book-cover" src="${escape(cover)}" alt="${escape(title)} 封面" loading="lazy"></a><span class="cover-label">本地封面 · 点击放大</span>` : `<div class="cover-missing"><span aria-hidden="true">Aa</span>封面暂未取得<small>书目信息已保留</small></div>`}</div><p class="book-series-name">${book.kind === 'series' ? '<span class="book-kind">系列</span> ' : book.kind === 'category' ? '<span class="book-kind">类别</span> ' : ''}${escape(seriesFor(book) || (book.kind === 'series' ? '课程提及的绘本系列' : '系列未标注'))}</p><h2>${escape(title)}</h2><p class="book-author">${escape(author || '作者待核实')}</p>${related.length ? `<div class="book-lesson-links" aria-label="关联课程">${related.map(id => lessonLink(id)).join('')}</div>` : '<p class="book-unknown-course">关联课程待核实</p>'}${[...new Set([book.note, book.editionNote].filter(value => typeof value === 'string' && value.trim()))].map(note => `<p class="book-note">${escape(note)}</p>`).join('')}${evidenceHtml}<div class="book-source-links">${externalLink(book.sourceUrl, '书目信息 ↗')}${cover ? `<a href="${escape(cover)}" download>下载封面 ↓</a>` : ''}${!book.sourceUrl && sourceUrl(book.coverSourceUrl) ? externalLink(book.coverSourceUrl, '封面来源 ↗') : ''}</div></article>`;
  }
function renderReferences(query) {
  const groups = [
    { key: 'seriesMentions', title: '课程提及的系列', note: '按系列保留课程中的阅读线索。' },
    { key: 'uncertainMentions', title: '版本或书名待核实', note: '保留已出现的故事与阅读片段；尚未确认的信息以每条说明为准。' },
    { key: 'otherReferences', title: '课程中的其他阅读参考', note: '小说、文字读物及其他参考单独列在这里。' },
  ];
  let matches = 0;
  const output = groups.map(group => {
    const entries = (Array.isArray(data[group.key]) ? data[group.key] : []).filter(entry => !query || `${entry.title || entry.name || ''} ${entry.note || ''} ${entry.reason || ''} ${entry.author || ''}`.toLocaleLowerCase().includes(query));
    matches += entries.length;
    if (!entries.length) return '';
    return `<details class="reference-group"${group.key === 'uncertainMentions' || query ? ' open' : ''}><summary>${escape(group.title)}<span>${entries.length}</span></summary><p class="reference-group-note">${escape(group.note)}</p><div class="reference-items">${entries.map(entry => {
      const name = entry.title || entry.name || '书名待核实';
      const notes = [...new Set([entry.note, entry.reason, entry.editionNote].filter(value => typeof value === 'string' && value.trim()))];
      const evidence = evidenceFor(entry);
      const related = idsFor(entry).filter(id => lessons.has(id));
      return `<article class="reference-item${localPath(entry.cover) ? ' has-cover' : ''}">${localPath(entry.cover) ? `<a class="reference-cover" href="${escape(localPath(entry.cover))}" target="_blank" rel="noopener" aria-label="查看${escape(name)}代表封面"><img src="${escape(localPath(entry.cover))}" alt="${escape(name)}代表封面" loading="lazy"></a>` : ''}<div class="reference-copy"><h3>${escape(name)}</h3>${entry.author ? `<p class="reference-author">${escape(authorFor(entry))}</p>` : ''}${notes.map(note => `<p>${escape(note)}</p>`).join('')}${evidence.length ? `<ul class="reference-evidence">${evidence.map(item => `<li>${lessonLink(String(item.lessonId), undefined, item.time) || '<span>课程位置待核实</span>'}${timeLabel(item.time) ? ` <span>· ${escape(timeLabel(item.time))}</span>` : ''}${item.quote ? `<blockquote>「${escape(item.quote)}」</blockquote>` : ''}${item.note ? `<p class="evidence-note">${escape(item.note)}</p>` : ''}</li>`).join('')}</ul>` : related.length ? `<div class="book-lesson-links">${related.map(id => lessonLink(id)).join('')}</div>` : ''}${externalLink(entry.sourceUrl, '查看书目信息 ↗')}</div></article>`;
    }).join('')}</div></details>`;
  }).join('');
  $('#book-references').innerHTML = output;
  $('#book-references').hidden = !matches;
  return matches;
}
  function render() {
    const query = $('#book-search').value.trim().toLocaleLowerCase();
    const selectedSeries = $('#book-series').value;
    const selectedEvidence = $('#book-evidence').value;
    const filtered = books.filter(book => (!query || `${book.title || ''} ${authorFor(book)} ${seriesFor(book)} ${book.isbn || ''}`.toLocaleLowerCase().includes(query)) && (selectedSeries === 'all' || seriesFor(book) === selectedSeries) && (selectedEvidence === 'all' || evidenceFor(book).some(item => selectedEvidence === 'visual' ? ['visual','shown','visible-cover','spoken-and-visible-cover'].includes(item.kind) : selectedEvidence === 'spoken' ? ['spoken','spoken-title','spoken-and-visible-cover'].includes(item.kind) : item.kind === selectedEvidence)));
    $('#book-grid').innerHTML = filtered.map(card).join('');
    const referenceMatches = renderReferences(query);
    $('#book-results').textContent = `${filtered.length} / ${books.length} ${seriesCount || categoryCount ? '项书目' : '本绘本'}${query && referenceMatches ? ` · ${referenceMatches} 条补充提及` : ''}`;
    $('#book-empty').hidden = filtered.length > 0;
    $('#book-empty').classList.toggle('has-references', referenceMatches > 0);
    $('#book-empty h2').textContent = '已确认绘本中没有匹配项';
    $('#book-empty p').textContent = referenceMatches ? `下方还有 ${referenceMatches} 条课程提及线索，可以继续查看。` : '试试更短的书名，或清除筛选条件。';
    if (!books.length) { $('#book-empty h2').textContent = '书目正在整理'; $('#book-empty p').textContent = '已确认的书目与本地封面会出现在这里。'; $('#book-reset').hidden = true; }
    for (const image of document.querySelectorAll('.book-cover')) image.addEventListener('error', () => { const wrap = image.closest('.book-cover-wrap'); image.closest('.book-entry')?.querySelector('.book-source-links a[download]')?.remove(); wrap.innerHTML = '<div class="cover-missing"><span aria-hidden="true">Aa</span>本地封面无法读取<small>书目信息与课程入口仍可查看</small></div>'; }, { once:true });
  }
  $('#book-search').addEventListener('input', render);
  $('#book-series').addEventListener('change', render);
  $('#book-evidence').addEventListener('change', render);
  $('#book-reset').addEventListener('click', () => { $('#book-search').value = ''; $('#book-series').value = 'all'; $('#book-evidence').value = 'all'; render(); $('#book-search').focus(); });
  render();
})();
