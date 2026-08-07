/**
 * NS 保活：載入一次 /landing，把 1 小時的滑動 JWT 續期。
 *
 * 為什麼要有這支（2026-08-07）：
 * NS 的登入態**只存在 localStorage 那顆 1 小時 JWT**——沒有任何 cookie 後備
 * （AP 有 7 天的 session_user、RT 有 23 小時的 mexlogin，NS 一個都沒有）。
 * 只要還沒過期，載入頁面就會換一顆新的、重新算 1 小時；**一旦過期就只能人工重登**。
 *
 * 原本規則是「掃帶 agent 在兩輪之間自己顧」，但**改用 Windows 工作排程器之後，
 * agent 跑完就退出了，根本沒有在等待的 agent**——這支就是補這個破口。
 *
 * ⚡ 刻意不叫 Claude：這件事只是「開一個頁面」，用 Playwright 直接做**零 token**、
 *    約 10 秒。一天要跑 48 次，用 `claude -p` 的話成本會很可觀。
 *
 * ⚠️ **一定要用 MCP 同一個 user-data-dir 與同一個瀏覽器版本**：
 *    - profile 不同 → 讀不到登入態（2026-08-07 實錯：加了 `channel:'chrome'`
 *      變成用 Google Chrome 開同一個資料夾，看起來像「沒載入 cookie」）
 *    - chromium 版本不符 → launch 後 context 立刻關閉（協定對不上）
 *
 * 離開碼：0＝已續期；3＝NS 已登出（需人工重登）；1＝其他錯誤。
 */
'use strict';

const PROFILE = 'C:/Users/User/.playwright-mcp-profile';
const URL = 'https://newsource.ns.cnn.com/landing';

// @playwright/mcp 是用 npx 跑的，套件躺在 npm 的 _npx 快取裡（路徑含雜湊）。
// 寫死雜湊會在快取被清掉時壞掉，所以用搜尋的——找不到才報錯。
function resolvePlaywright() {
  const fs = require('fs');
  const path = require('path');
  const base = path.join(process.env.LOCALAPPDATA || '', 'npm-cache', '_npx');
  for (const dir of (fs.existsSync(base) ? fs.readdirSync(base) : [])) {
    const p = path.join(base, dir, 'node_modules', 'playwright');
    if (fs.existsSync(p)) return require(p);
  }
  try { return require('playwright'); } catch (_) { /* fallthrough */ }
  throw new Error('找不到 playwright——npx 快取被清掉了？跑一次 npx @playwright/mcp 重建');
}

(async () => {
  const { chromium } = resolvePlaywright();
  const t0 = Date.now();
  const ctx = await chromium.launchPersistentContext(PROFILE, { headless: true });
  try {
    const page = ctx.pages()[0] || await ctx.newPage();
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(6000);          // 等 SPA 換完 token，不是隨便抓的數字
    const r = await page.evaluate(() => {
      const s = localStorage.getItem('newsourceSession');
      if (!s) return { ok: false, url: location.href };
      const p = JSON.parse(atob(JSON.parse(s).token.split('.')[1]));
      return { ok: true, remainMin: Math.round((p.exp - Date.now() / 1000) / 60) };
    });
    const secs = ((Date.now() - t0) / 1000).toFixed(1);
    if (!r.ok) {
      console.log(`LOGGED_OUT url=${r.url} secs=${secs} ——NS 已登出，只能人工重登`);
      process.exit(3);
    }
    console.log(`OK remain=${r.remainMin}min secs=${secs}`);
  } finally {
    await ctx.close();
  }
})().catch(e => {
  console.error('ERR ' + String(e.message || e).split('\n')[0]);
  process.exit(1);
});
