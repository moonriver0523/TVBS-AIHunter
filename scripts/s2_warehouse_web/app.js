'use strict';
const $ = id => document.getElementById(id);
const node = (tag, cls = '', text = '') => { const e = document.createElement(tag); e.className = cls; e.textContent = text; return e; };
const button = (text, fn, cls = '') => { const b = node('button', cls, text); b.type = 'button'; b.onclick = fn; return b; };
const asciiLower = text => String(text).replace(/[A-Z]/g, c => c.toLowerCase());
const PAGE_SIZE = 50;
let manifest, view = 'handoff', results = [], pageNumber = 1, token = 0, controller, timelineOpen = false;
const cache = new Map();
const state = () => ({ source: new Set(), T: new Set(), C: new Set(), keyword: '', notes: false, unknown: false, from: '', to: '', shift: '', page: 1 });
const states = { handoff: state(), archive: state() }; states.handoff.notes = true;
const current = () => states[view];
const qualities = { ingestion_fallback: '入庫日代替', embedded_verified: '內文日期已辨識', inferred_recording: '側錄日期推定', structured_source: '來源結構化日期', source_created_fallback: '建立日代替', ambiguous: '多日期待確認', unknown: '日期未知' };
const setStatus = (text, error = false) => { $('status').textContent = text; $('status').className = error ? 'error' : ''; $('retry').hidden = !error; };
const fmt = n => n.toLocaleString('zh-TW');
const offsetDay = (day, delta) => { const d = new Date(day + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + delta); return d.toISOString().slice(0, 10); };

async function getJSON(path, sha, signal) {
  const key = path + ':' + (sha || 'manifest');
  if (sha && cache.has(key)) { const value = cache.get(key); cache.delete(key); cache.set(key, value); return value; }
  const response = await fetch('data/' + path, { cache: 'no-store', signal });
  if (!response.ok) throw new Error(`無法載入 ${path}（HTTP ${response.status}）`);
  const bytes = await response.arrayBuffer();
  if (sha) {
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
    if (hash !== sha) throw new Error(`分片版本不一致：${path}。請重新整理或重新匯出。`);
  }
  const data = JSON.parse(new TextDecoder().decode(bytes));
  if (sha) { cache.set(key, data); while (cache.size > 16) cache.delete(cache.keys().next().value); }
  return data;
}

function remember() {
  const s = current();
  Object.assign(s, { keyword: $('keyword').value, notes: $('notes').checked, unknown: $('unknown').checked,
    from: $('from').value, to: $('to').value, shift: $('shift').value, page: pageNumber });
}

function createFilters() {
  $('filterGroups').replaceChildren();
  for (const [key, title, values] of [['source', '來源', manifest.vocabulary.sources], ['T', 'T · 議題', manifest.vocabulary.T], ['C', 'C · 地區', manifest.vocabulary.C]]) {
    const group = node('details', 'filter-group'); group.open = key === 'source';
    group.append(node('summary', '', title)); const choices = node('div', 'choices');
    for (const value of values) {
      const label = node('label', 'check'), input = document.createElement('input'); input.type = 'checkbox'; input.checked = current()[key].has(value);
      input.dataset.axis = key; input.value = value;
      input.onchange = () => { const set = current()[key]; input.checked ? set.add(value) : set.delete(value); load(); };
      label.append(input, document.createTextNode(value)); choices.append(label);
    }
    group.append(choices); $('filterGroups').append(group);
  }
}

function drawTimeline() {
  $('timeline').replaceChildren();
  const selected = current().shift, all = manifest.shifts;
  const i = Math.max(0, all.findIndex(e => e.date === selected));
  const visible = matchMedia('(max-width:800px)').matches ? 4 : 7;
  const start = Math.max(0, Math.min(i - Math.floor(visible / 2), all.length - visible));
  const shown = timelineOpen ? all : all.slice(start, start + visible);
  for (const entry of shown) {
    const b = button(entry.date.slice(5).replace('-', '/'), () => { $('shift').value = entry.date; current().shift = entry.date; drawTimeline(); load(); }, 'day');
    b.setAttribute('aria-pressed', String(entry.date === selected)); b.setAttribute('aria-label', `${entry.date} 班，${entry.count} 則`);
    b.append(node('span', '', `${fmt(entry.count)} 則`)); $('timeline').append(b);
  }
  $('timelineToggle').textContent = timelineOpen ? '收合班次時間軸' : `展開全部 ${all.length} 班`;
  $('timelineToggle').setAttribute('aria-expanded', String(timelineOpen));
  const entry = all.find(e => e.date === selected);
  $('shiftHint').textContent = entry ? `${entry.date} 晚班 · ${fmt(entry.count)} 筆觀測（含備註） · ${entry.snapshot_count} 份快照` : '沒有可瀏覽的班次。';
}

function restore() {
  const s = current();
  pageNumber = s.page;
  for (const id of ['keyword', 'from', 'to', 'shift']) $(id).value = s[id];
  $('notes').checked = s.notes; $('unknown').checked = s.unknown;
  $('shiftPanel').hidden = view !== 'handoff'; $('rangePanel').hidden = view !== 'archive'; $('unknownLabel').hidden = view !== 'archive';
  $('from').required = $('to').required = view === 'archive';
  $('handoffTab').setAttribute('aria-pressed', String(view === 'handoff')); $('archiveTab').setAttribute('aria-pressed', String(view === 'archive'));
  $('title').textContent = view === 'handoff' ? '晚班交接' : '跨日檢索';
  $('subtitle').textContent = view === 'handoff' ? '依班次回看收到的素材，從清單開始校閱。' : '依素材日期尋找線索，跨班次回查手上的素材。';
  $('listTitle').textContent = view === 'handoff' ? '本班素材' : '檢索結果';
  $('keyword').placeholder = view === 'handoff' ? '搜尋本班素材代碼與完整中文摘要' : '搜尋素材代碼、中文摘要、已存來源原文';
  createFilters(); drawTimeline();
}

function switchView(next) { if (!manifest || view === next) return; remember(); view = next; restore(); load(true); }
function pass(row, s) {
  return (s.notes || row.kind !== 'note') && (!s.source.size || s.source.has(row.source_family)) &&
    ['T', 'C'].every(k => !s[k].size || (row.tc[k] || []).some(v => s[k].has(v))) &&
    (!s.keyword || asciiLower(row.search_text || row.id + '\n' + row.raw_entry).includes(asciiLower(s.keyword)));
}

function drawSelection() {
  $('selection').replaceChildren(); let count = 0;
  for (const key of ['source', 'T', 'C']) for (const value of current()[key]) {
    count++; $('selection').append(button(`${key === 'source' ? '來源' : key}：${value} ×`, () => { current()[key].delete(value); createFilters(); load(); }, 'chip'));
  }
  $('filterCount').textContent = count ? `（${count}）` : '';
}

async function load(keepPage = false) {
  if (!manifest) return;
  remember(); const s = current(); const request = ++token; controller?.abort(); controller = new AbortController();
  if (!keepPage) s.page = 1; pageNumber = s.page;
  results = []; $('results').replaceChildren(); $('pagination').replaceChildren(); $('resultCount').textContent = '';
  $('matrixBody').replaceChildren(); drawSelection();
  if (view === 'archive' && (!s.from || !s.to || s.from > s.to)) { setStatus('請確認日期區間，起日不可晚於迄日。', true); return; }
  const entries = view === 'handoff' ? manifest.shifts.filter(e => e.date === s.shift) :
    manifest.days.filter(e => e.date === 'unknown' ? s.unknown : e.date >= s.from && e.date <= s.to);
  const parts = entries.flatMap(e => e.parts); let done = 0;
  $('results').setAttribute('aria-busy', 'true');
  try {
    for (const part of parts) {
      setStatus(`正在搜尋分片 ${done + 1}／${parts.length}… 完成後顯示精確總數。`);
      const data = await getJSON(part.path, part.sha256, controller.signal);
      if (request !== token) return;
      for (const row of data.items) if (pass(row, s)) results.push(row);
      done++;
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    if (request !== token) return;
    if (view === 'archive') results.sort((a, b) => (b.material_date || '').localeCompare(a.material_date || '') || (a.material_id < b.material_id ? -1 : a.material_id > b.material_id ? 1 : 0));
    $('resultCount').textContent = `${fmt(results.length)} 則`;
    setStatus(view === 'archive' ? `已完整搜尋 ${s.from}～${s.to}${s.unknown ? '＋日期未知' : ''} · ${entries.length} 個日期分片組。關鍵字包含完整已存來源原文。` : `已讀取本班全部 ${parts.length} 個分片 · ${s.notes ? '含備註' : '已排除備註'}。`);
    if (!results.length) setStatus('查無符合條件的素材。可放寬日期或清除篩選後再試。');
    renderPage(); if ($('matrix').open) renderMatrix();
  } catch (error) {
    if (request !== token || error.name === 'AbortError') return;
    results = []; $('results').replaceChildren(); $('pagination').replaceChildren(); $('resultCount').textContent = '搜尋未完成';
    setStatus(error.message + ' 本次結果未完整，請重試。', true);
  } finally { if (request === token) $('results').setAttribute('aria-busy', 'false'); }
}

function tagFilter(axis, value) { current()[axis].has(value) ? current()[axis].delete(value) : current()[axis].add(value); createFilters(); load(); }
function renderItem(row) {
  const item = node('article', 'item'); item.dataset.materialId = row.material_id;
  const source = node('div', 'source'); source.append(node('strong', '', row.source_family), node('span', 'code', row.id));
  const date = node('time', '', row.material_date || '日期未知'); if (row.material_date) date.dateTime = row.material_date; source.append(date);
  const url = row.source_link?.url;
  if (url && /^https:\/\//.test(url)) { const a = node('a', '', '開啟來源 ↗'); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; source.append(a); }
  else { const missing = node('span', '', '來源連結未建立'); missing.title = row.source_link?.missing_reason || '無可用來源連結'; source.append(missing); }
  const body = node('div', 'body'), dates = node('div', 'dates');
  const quality = qualities[row.date_quality] || row.date_quality;
  dates.append(node('span', row.date_quality === 'ingestion_fallback' || row.date_quality === 'unknown' || row.date_quality === 'ambiguous' ? 'quality' : '', quality),
    node('span', '', `班次 ${row.shift_date || '未知'}`));
  if (row.first_seen_taipei) dates.append(node('span', '', '首次入庫 ' + row.first_seen_taipei.slice(0, 16).replace('T', ' ')));
  if (row.material_date_range) dates.append(node('span', 'quality', '候選日期 ' + row.material_date_range.join('～')));
  if (row.kind === 'note') dates.append(node('span', 'quality', '備註素材'));
  body.append(dates);
  const text = row.raw_entry || row.id;
  body.append(node('p', 'item-text', text.length > 320 ? text.slice(0, 320) + '…' : text));
  if (text.length > 320) { const details = node('details', 'item-more'); details.append(node('summary', '', '展開完整摘要'), node('p', 'item-text', text)); body.append(details); }
  const tags = node('div', 'item-tags');
  for (const axis of ['T', 'C']) for (const value of row.tc[axis] || []) {
    const b = button(`${axis} · ${value}`, () => tagFilter(axis, value), 'chip ' + axis.toLowerCase());
    b.setAttribute('aria-pressed', String(current()[axis].has(value))); tags.append(b);
  }
  body.append(tags); item.append(source, body); return item;
}

function renderPage() {
  const pages = Math.max(1, Math.ceil(results.length / PAGE_SIZE)); pageNumber = Math.min(pageNumber, pages); current().page = pageNumber;
  $('results').replaceChildren(...results.slice((pageNumber - 1) * PAGE_SIZE, pageNumber * PAGE_SIZE).map(renderItem));
  $('pagination').replaceChildren(); if (!results.length) return;
  const move = delta => { pageNumber += delta; renderPage(); $('listTitle').scrollIntoView({ block: 'start' }); };
  const previous = button('← 上一頁', () => move(-1)); previous.disabled = pageNumber === 1;
  const next = button('下一頁 →', () => move(1)); next.disabled = pageNumber === pages;
  $('pagination').append(previous, node('span', '', `${pageNumber}／${fmt(pages)} 頁 · 每頁 ${PAGE_SIZE} 則`), next);
}

function renderMatrix() {
  $('matrixBody').replaceChildren();
  const counts = new Map(), ts = new Set(), cs = new Set();
  for (const row of results) for (const t of row.tc.T || []) for (const c of row.tc.C || []) {
    ts.add(t); cs.add(c); const key = JSON.stringify([t, c]); counts.set(key, (counts.get(key) || 0) + 1);
  }
  if (!counts.size) { $('matrixBody').append(node('p', 'hint', '目前結果沒有 T／C 交集。')); return; }
  const table = document.createElement('table'), head = document.createElement('thead'), tr = document.createElement('tr');
  const columns = [...cs].sort(); tr.append(node('th', '', 'T 議題／C 地區')); for (const c of columns) tr.append(node('th', '', c)); head.append(tr); table.append(head);
  const body = document.createElement('tbody');
  for (const t of [...ts].sort()) {
    const row = document.createElement('tr'); const th = node('th', '', t); th.scope = 'row'; row.append(th);
    for (const c of columns) {
      const td = document.createElement('td'), n = counts.get(JSON.stringify([t, c]));
      if (n) { const b = button(String(n), () => { current().T = new Set([t]); current().C = new Set([c]); createFilters(); load(); }); b.setAttribute('aria-label', `${t}、${c}，${n} 則`); td.append(b); }
      row.append(td);
    }
    body.append(row);
  }
  table.append(body); $('matrixBody').append(table);
}

function preset(days) { $('to').value = manifest.default_end_date; $('from').value = offsetDay(manifest.default_end_date, -(days - 1)); load(); }
function applyTheme(theme) { document.documentElement.dataset.theme = theme; $('theme').textContent = theme === 'dark' ? '切換淺色' : '切換深色'; }
try { applyTheme(localStorage.getItem('s2-online-theme') || 'dark'); } catch (_) { applyTheme('dark'); }
$('theme').onclick = () => { const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; applyTheme(theme); try { localStorage.setItem('s2-online-theme', theme); } catch (_) {} };
$('handoffTab').onclick = () => switchView('handoff'); $('archiveTab').onclick = () => switchView('archive');
$('searchForm').onsubmit = event => { event.preventDefault(); load(); };
$('shift').onchange = () => { remember(); drawTimeline(); load(); };
$('timelineToggle').onclick = () => { timelineOpen = !timelineOpen; drawTimeline(); };
$('notes').onchange = $('unknown').onchange = () => load();
$('week').onclick = () => preset(7); $('month').onclick = () => preset(30);
$('reset').onclick = () => { const s = current(); s.source.clear(); s.T.clear(); s.C.clear(); $('keyword').value = ''; $('notes').checked = view === 'handoff'; $('unknown').checked = false; createFilters(); load(); };
$('matrix').ontoggle = () => { if ($('matrix').open) renderMatrix(); };
$('retry').onclick = () => manifest ? load() : init();

async function init() {
  try {
    manifest = await getJSON('manifest.json');
    if (manifest.format_version !== 1 || !manifest.default_end_date) throw new Error('發布清單版本不支援或尚無班次資料');
    $('coverage').textContent = `${manifest.shifts.length} 班 · ${fmt(manifest.material_count)} 筆素材 · ${manifest.shifts[0].date}～${manifest.default_end_date}`;
    $('publicationInfo').textContent = '發布時間 ' + new Date(manifest.generated_at).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' }) + '（臺灣時間）';
    $('generation').textContent = '發布版次 ' + manifest.generation.slice(0, 12);
    $('shift').replaceChildren(...[...manifest.shifts].reverse().map(e => { const option = node('option', '', `${e.date} · ${fmt(e.count)} 則`); option.value = e.date; return option; }));
    for (const s of Object.values(states)) { s.shift = manifest.default_end_date; s.to = manifest.default_end_date; s.from = offsetDay(s.to, -6); }
    if (matchMedia('(max-width:800px)').matches) $('filters').open = false;
    restore(); await load();
  } catch (error) { manifest = undefined; setStatus(error.message + '。請使用 serve.cmd 開啟本機網站。', true); }
}
init();
