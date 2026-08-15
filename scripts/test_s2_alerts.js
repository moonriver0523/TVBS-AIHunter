'use strict';
/**
 * 快訊守護：解析／去重／首次基準／旗標 迴歸（零瀏覽器、零 token）。
 * 用法：node scripts/test_s2_alerts.js
 */
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const os = require('os');
const lib = require('./s2_alerts_lib');

let failed = 0;
function check(name, fn) {
  try {
    fn();
    console.log('[PASS] ' + name);
  } catch (e) {
    failed += 1;
    console.log('[FAIL] ' + name + ' — ' + (e.message || e));
  }
}

const rtPayload = {
  success: true,
  messages: [
    { messageId: 'm1', _type: 'breaking-news', msg: 'CARRIER TO MIDDLE EAST', created: 1786650000, is_read: 0 },
    { messageId: 'm2', _type: 'calendar-event', msg: 'WEBINAR', created: 1786650001, is_read: 0 },
    { messageId: 'm3', _type: 'breaking-news', msg: 'JUDGE DISMISSES SUIT', created: 1786650002, is_read: 1 },
  ],
};

const apPayload = [
  { itemid: 'aaa', slugline: 'AP-US-APNewsAlert', arrivaldatetime: '2026-08-13T19:12:51Z', headline: 'Mangione expected to plead' },
  { itemid: 'bbb', slugline: 'AP-US-SomethingElse', arrivaldatetime: '2026-08-13T18:00:00Z', headline: 'not an alert' },
  { itemid: 'ccc', slugline: 'AP-US-APNewsAlert', arrivaldatetime: '2026-08-13T19:00:00Z', headline: 'Ryanair window shattered' },
];

check('RT 只收 breaking-news，略過 calendar-event', () => {
  const items = lib.parseRtMessages(rtPayload);
  assert.strictEqual(items.length, 2);
  assert.deepStrictEqual(items.map((x) => x.id), ['RT:m1', 'RT:m3']);
  assert.strictEqual(items[0].site, 'RT');
  assert.ok(items[0].text.includes('CARRIER'));
});

check('RT 壞 payload 回空陣列、不炸', () => {
  assert.deepStrictEqual(lib.parseRtMessages(null), []);
  assert.deepStrictEqual(lib.parseRtMessages({}), []);
  assert.deepStrictEqual(lib.parseRtMessages({ messages: 'nope' }), []);
});

check('AP 只收 APNewsAlert slug', () => {
  const items = lib.parseApBreaking(apPayload);
  assert.strictEqual(items.length, 2);
  assert.deepStrictEqual(items.map((x) => x.id), ['AP:aaa', 'AP:ccc']);
  assert.strictEqual(items[0].site, 'AP');
});

check('AP 壞 payload 回空陣列、不炸', () => {
  assert.deepStrictEqual(lib.parseApBreaking(null), []);
  assert.deepStrictEqual(lib.parseApBreaking({ Items: [] }), []);
});

check('首次（seen 空）只建基準、一則都不推——避免啟動洗 65 則', () => {
  const items = lib.parseRtMessages(rtPayload).concat(lib.parseApBreaking(apPayload));
  const r = lib.applyCycle({}, items);
  assert.strictEqual(r.notify.length, 0);
  assert.ok(r.seen['RT:m1']);
  assert.ok(r.seen['AP:aaa']);
  assert.strictEqual(r.seeded, true);
});

check('第二次只推新 ID', () => {
  const first = lib.applyCycle({}, lib.parseRtMessages(rtPayload));
  const nextPayload = {
    success: true,
    messages: [
      rtPayload.messages[0],
      { messageId: 'm9', _type: 'breaking-news', msg: 'NEW WELL ONLINE', created: 1786659999, is_read: 0 },
    ],
  };
  const r = lib.applyCycle(first.seen, lib.parseRtMessages(nextPayload));
  assert.strictEqual(r.notify.length, 1);
  assert.strictEqual(r.notify[0].id, 'RT:m9');
  assert.strictEqual(r.seeded, false);
});

check('同一 ID 不重複推', () => {
  const items = lib.parseApBreaking(apPayload);
  const a = lib.applyCycle({}, items);
  const b = lib.applyCycle(a.seen, items);
  assert.strictEqual(b.notify.length, 0);
});

check('旗標檔不存在＝關閉（預設 OFF）', () => {
  const missing = path.join(os.tmpdir(), 's2-alerts-flag-missing-' + Date.now());
  assert.strictEqual(lib.isEnabled(missing), false);
});

check('旗標檔存在＝開啟', () => {
  const f = path.join(os.tmpdir(), 's2-alerts-flag-' + Date.now());
  fs.writeFileSync(f, 'on', 'utf8');
  try {
    assert.strictEqual(lib.isEnabled(f), true);
  } finally {
    fs.unlinkSync(f);
  }
});

check('ntfy 內文含站別與快訊、title 只 ASCII', () => {
  const p = lib.formatPush({ id: 'RT:m1', site: 'RT', text: 'CARRIER TO MIDDLE EAST', type: 'breaking-news' });
  assert.strictEqual(p.title, 'S2 alert RT');
  assert.ok(p.body.indexOf('RT') !== -1);
  assert.ok(p.body.indexOf('CARRIER') !== -1);
  assert.ok(/^[\x00-\x7F]+$/.test(p.title));
});

if (failed) {
  console.log('\n' + failed + ' failed');
  process.exit(1);
}
console.log('\nall passed');
