/**
 * 保活：載入首頁，把登入態續期。
 *
 * 為什麼要有這支（2026-08-07 立，0808 擴充成三站，2026-08-16 收斂回只保活 NS）：
 * 三站的憑證機制完全不同，但**都是滑動效期**——載入頁面就重新計時：
 *
 *   NS  localStorage 的 JWT     1 小時   ← 最短，沒有任何 cookie 後備，唯一還在保活的站
 *   RT  mexlogin cookie        23 小時   ← 2026-08-16 使用者指示移出保活（原因見下方 RT 區塊註解）
 *   AP  session_user cookie     7 天    ← 已於 2026-08-09 移出保活（見下方保留的實錯記錄）
 *
 * ⚠️ 2026-08-16 起，本支與 `s2_alerts.js`／`s2_mcp.json` 改用專屬的
 *    `.playwright-s2-profile`（從當時的 `.playwright-daily-profile` 複製 cookie／localStorage
 *    種子出來），不再與互動用的 DAILY profile 共用，也不再沿用舊的 `.playwright-mcp-profile`
 *    這個名字——三者職責分開：DAILY 給人互動用、S2 profile 給保活/掃帶/警報用。
 *
 * ⚠️ 2026-08-16 當天二度更名為 `.playwright-s2-profile-v2`（全新空白 profile，三站人工重登）：
 *    上面那個 `.playwright-s2-profile` 被 Reuters Connect 的 datadome 標記成受限環境，
 *    清 cookie／localStorage／IndexedDB 都救不回來（只回硬封鎖頁、連機器人驗證都不給），
 *    而全新 profile 用一般 Chrome 開就能拿到可手動通過的驗證、登入後三站都正常。
 *    舊 profile 保留未刪，需要退路時可改回來。
 *
 * 原本規則是「掃帶 agent 在兩輪之間自己顧」，但**改用工作排程器之後 agent 跑完
 * 就退出，根本沒有在等待的 agent**——這支就是補這個破口。
 *
 * ⚡ 刻意不叫 Claude：這件事只是「開幾個頁面」，用 Playwright 直接做**零 token**、
 *    約 20 秒。一天 48 次，走 `claude -p` 的成本會很可觀。
 *
 * ⚠️ **一定要用 MCP 同一個 user-data-dir 與同一個瀏覽器版本**：
 *    - profile 不同 → 讀不到登入態（0807 實錯：加了 `channel:'chrome'` 變成用
 *      Google Chrome 開同一個資料夾，症狀長得像「沒載入 cookie」，一度誤判要重登）
 *    - chromium 版本不符 → launch 後 context 立刻關閉（協定對不上）
 *
 * 離開碼：0＝全部續期成功；3＝**有站登出**（需人工重登）；1＝其他錯誤。
 * ⚠️ 一站登出不影響其餘兩站——照樣跑完再回報，不要一掛就整支中斷。
 */
'use strict';

const PROFILE = 'C:/Users/User/.playwright-s2-profile-v4';

const SITES = [
  // wait：SPA 要時間 boot 完才會換發憑證，讀太早會誤判成登出
  { name: 'NS', url: 'https://newsource.ns.cnn.com/landing', wait: 6000,
    check: () => {
      const s = localStorage.getItem('newsourceSession');
      if (!s) return { ok: false };
      const p = JSON.parse(atob(JSON.parse(s).token.split('.')[1]));
      return { ok: true, note: Math.round((p.exp - Date.now() / 1000)) + 's' };
    } },
  // ABC Extreme Reach：ASP.NET Session 滑動過期（預設約 20-60 分鐘），每次造訪 cmspage 即自動刷新
  { name: 'ABC', url: 'https://abcnews.extremereach.com/adbridge/news/cmspage/50162/abcnewsone', wait: 6000,
    check: () => {
      const isLogin = location.href.toLowerCase().includes('login');
      const hasLogout = Array.from(document.querySelectorAll('a')).some(a => a.innerText.trim() === 'Logout');
      return { ok: hasLogout && !isLogin };
    } },
  // ⛔ AP 已於 2026-08-09 05:00 **暫時移出保活**——強烈懷疑保活本身就是元凶。
  //
  // 【證據】AP 在被納入保活之前，**一次都沒有掉過線**：
  //   08-08 01:00  保活擴充成三站（commit 834644d），AP 首次被納入
  //   08-08 01:20  保活第一次碰 AP → OK
  //   08-08 01:50  OK
  //   08-08 02:20  **LOGGED_OUT** ← 才第 3 次
  //   接下來 28 小時內掉了 10 次；使用者手動重登後最短只撐 2 小時。
  //   而在此之前 AP 靠掃帶輪次（一天 12 次開關）活了好幾天，符合「7 天 cookie」的說法。
  //
  // 【推論】保活一天開關這個 profile **48 次**，是原本的 4 倍。chromium 的 cookie
  //   是在關閉時寫回磁碟的，關得不乾淨就可能丟失——0809 04:20 那次保活正是
  //   異常結束（`Execution context was destroyed`、跑了 60 秒、RT 也逾時），
  //   緊接著 04:30 掃帶就發現 `session_user` cookie 整個不見了。
  //
  // 【這是一個實驗，不是定論】判準：拿掉之後 **AP 若能連續撐過 24 小時不掉線**，
  //   就證實保活是元凶；**若照樣掉**，代表另有原因，把這段還原回去即可。
  //   ⚠️ 拿掉期間 AP 不會有 30 分鐘一次的掉線推播，但**掃帶輪次一天仍碰 AP 12 次**、
  //   進不去時會寫 needs-review，所以不會失去監看，只是延遲變成最多 2 小時。
  //
  // { name: 'AP', url: 'https://newsroom.ap.org/home', wait: 8000,
  //   check: () => {
  //     const t = document.body.innerText || '';
  //     // 只看有沒有 Sign in 會誤判——SPA 載入中也長那樣，所以同時要求 Latest 出現
  //     return { ok: /Latest/i.test(t) && !/sign\s*in/i.test(t) };
  //   } },
  // ⛔ RT 已於 2026-08-16 移出保活（使用者指示：只保活 NS）。
  // { name: 'RT', url: 'https://www.reutersconnect.com/all?media-types=vid', wait: 8000,
  //   check: () => ({ ok: !/\/login/i.test(location.href) }) },
];

// @playwright/mcp 是用 npx 跑的，套件躺在 npm 的 _npx 快取裡（路徑含雜湊）。
// 寫死雜湊會在快取被清掉時壞掉，所以用搜尋的——找不到才明確報錯。
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
  // ⚠️ 2026-08-16 修：**一定要 channel:'chrome'**，跟 @playwright/mcp 用同一個瀏覽器。
  //    @playwright/mcp 開的是真正的 Google Chrome（當時 151.0.7922.76），而 playwright
  //    內建 chromium 是 152.0.7977.8。兩者輪流開同一個 user-data-dir 時，**Chrome 讀到
  //    `Last Version` 比自己新就判定為降級，直接重置整個 profile**（cookie／localStorage
  //    全清）——症狀就是「才剛人工登入三站，下一輪掃帶又全部 LOGGED_OUT」。
  //    ⛔ 不要把這行拿掉改回內建 chromium：0807 那次的教訓是「兩邊要一致」，不是
  //       「不能用 channel:'chrome'」——現在 MCP 端就是 chrome，這裡必須跟上。
  const ctx = await chromium.launchPersistentContext(PROFILE, { headless: true, channel: 'chrome' });
  const out = [];
  let loggedOut = false;

  try {
    const page = ctx.pages()[0] || await ctx.newPage();
    for (const s of SITES) {
      try {
        await page.goto(s.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await page.waitForTimeout(s.wait);
        const r = await page.evaluate(s.check);
        if (r.ok) {
          out.push(`${s.name}=OK${r.note ? '(' + r.note + ')' : ''}`);
        } else {
          out.push(`${s.name}=LOGGED_OUT`);
          loggedOut = true;
        }
      } catch (e) {
        // 單站失敗不中斷其餘——一站掛掉不該讓另外兩站也跟著沒續期
        out.push(`${s.name}=ERR(${String(e.message || e).split('\n')[0].slice(0, 60)})`);
      }
    }
  } finally {
    await ctx.close();
  }

  const secs = ((Date.now() - t0) / 1000).toFixed(1);
  console.log(`${out.join(' ')} secs=${secs}`);
  process.exit(loggedOut ? 3 : 0);
})().catch(e => {
  console.error('ERR ' + String(e.message || e).split('\n')[0]);
  process.exit(1);
});
