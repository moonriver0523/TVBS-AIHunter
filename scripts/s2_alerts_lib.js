'use strict';
/**
 * 快訊守護純函式（可測、無 IO 決策除外 isEnabled 讀檔）。
 * 瀏覽器／ntfy 在 s2_alerts.js。
 */

function parseRtMessages(payload) {
  const msgs = payload && payload.messages;
  if (!Array.isArray(msgs)) return [];
  const out = [];
  for (const m of msgs) {
    if (!m || m._type !== 'breaking-news' || !m.messageId) continue;
    out.push({
      id: 'RT:' + String(m.messageId),
      site: 'RT',
      type: 'breaking-news',
      text: String(m.msg || '').trim(),
      ts: m.created,
    });
  }
  return out;
}

function parseApBreaking(payload) {
  if (!Array.isArray(payload)) return [];
  const out = [];
  for (const x of payload) {
    if (!x || !x.itemid) continue;
    if (!/NewsAlert/i.test(String(x.slugline || ''))) continue;
    out.push({
      id: 'AP:' + String(x.itemid),
      site: 'AP',
      type: String(x.slugline),
      text: String(x.headline || '').trim(),
      ts: x.arrivaldatetime,
    });
  }
  return out;
}

function diffNew(seen, items) {
  const s = seen || {};
  return (items || []).filter((it) => it && it.id && !s[it.id]);
}

function stampSeen(seen, items, nowIso) {
  const next = Object.assign({}, seen || {});
  const ts = nowIso || new Date().toISOString();
  for (const it of items || []) {
    if (it && it.id) next[it.id] = ts;
  }
  return next;
}

/** seen 空且這輪有料＝首次基準，一則都不推。 */
function applyCycle(seen, items) {
  const list = items || [];
  const prev = seen || {};
  const empty = Object.keys(prev).length === 0;
  if (empty && list.length > 0) {
    return { notify: [], seen: stampSeen({}, list), seeded: true };
  }
  const neu = diffNew(prev, list);
  return { notify: neu, seen: stampSeen(prev, neu), seeded: false };
}

function isEnabled(flagPath) {
  try {
    return !!(flagPath && require('fs').existsSync(flagPath));
  } catch (_) {
    return false;
  }
}

function formatPush(item) {
  const site = item.site || '?';
  const text = item.text || '(no text)';
  return {
    title: 'S2 alert ' + site,
    body: '[' + site + '] ' + text,
    tags: site === 'AP' ? 'us,warning' : 'newspaper,warning',
    priority: 'high',
  };
}

module.exports = {
  parseRtMessages,
  parseApBreaking,
  diffNew,
  stampSeen,
  applyCycle,
  isEnabled,
  formatPush,
};
