/**
 * 偵測到登出時，用存好的帳密自動重新登入。
 *
 * 涵蓋：NS／AP／ENEX／ABC 四站（2026-09-14 逐一用 `browser` MCP daily profile 手動驗證
 * 過，流程穩定、無 CAPTCHA／2FA）。
 *
 * ⛔ 刻意不含 RT（Reuters Connect）：使用者 2026-09-14 裁示——RT 的登入行為較可能被
 *    datadome 判定為機器人（[[project_s2_profile_v4_chrome_channel]] 記錄過 datadome
 *    連續把好幾代 profile 判定成受限環境的教訓），怕自動化重登觸發帳號鎖定，先保持
 *    讓使用者手動登入。若要加回 RT，見 S2-MASTER-追蹤清單.md A37「TODO 觀察」，未經
 *    使用者明示不得啟用。
 *
 * 帳密來源：`C:\Users\User\.s2_five_sites_credentials`（不進版控），格式每行
 *   `站名|登入網址|帳號|密碼`，見 memory `project_s2_five_sites_credentials.local.md`。
 *
 * 用法：
 *   node s2_relogin.js                 # 依序嘗試 NS/AP/ENEX/ABC，預設 DAILY profile
 *   node s2_relogin.js --site NS,AP    # 只重登指定站（逗號分隔）
 *   node s2_relogin.js --s2            # 改用 S2 掃帶生產 profile（v4）
 *   node s2_relogin.js --profile <dir> # 自訂 profile 路徑（優先權最高）
 *
 * ⚠️ 2026-09-15 修正：預設值原本誤設成 S2 v4 掃帶 profile，導致「平常開這五站」
 *    這種非掃帶用途的重登會誤登進 v4 profile（使用者手動瀏覽根本看不到效果，
 *    還可能跟同時在跑的 S2 排程搶同一個 profile 鎖）。**預設改回 DAILY profile**
 *    （`.playwright-daily-profile`，跟 `mcp__browser__*` 工具用的是同一個），
 *    S2 掃帶場景要明確帶 `--s2` 或 `--profile .playwright-s2-profile-v4`。
 *
 * 離開碼：0＝全部成功（或該站已在登入態、不需重登）；3＝有站重登失敗（需人工介入）；
 *         1＝其他錯誤（例如讀不到帳密檔）。
 *
 * ⚠️ 這支是「主動重登」，跟 `s2_keepalive.js`（單純載頁面續期，不填帳密）是兩支不同
 *    職責的腳本，刻意不合併——keepalive 的 AP 目前處於「移出保活」實驗觀察期
 *    （見該檔內註解），本支不動那個實驗，只在被明確呼叫時才對 AP 動作。
 */
'use strict';

const fs = require('fs');

const CRED_FILE = 'C:/Users/User/.s2_five_sites_credentials';
const DAILY_PROFILE = 'C:/Users/User/.playwright-daily-profile';
const S2_PROFILE = 'C:/Users/User/.playwright-s2-profile-v4';

// 帳密檔裡的站名跟本檔 SITES 的 key 不完全一樣（例如帳密檔寫 CNN-NS／ABC-NEWSONE），
// 這裡做別名對應，不改帳密檔格式。
const SITE_ALIASES = { 'CNN-NS': 'NS', 'ABC-NEWSONE': 'ABC' };

function loadCredentials() {
  const text = fs.readFileSync(CRED_FILE, 'utf8');
  const creds = {};
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const [site, url, user, pass] = line.split('|');
    if (!site || !user || !pass) continue;
    const key = SITE_ALIASES[site.trim()] || site.trim();
    creds[key] = { url: (url || '').trim(), user: user.trim(), pass: pass.trim() };
  }
  return creds;
}

// 每站：alreadyOk 判斷是否已登入（免重登）；login 執行實際填表；verify 登入後複查。
const SITES = {
  NS: {
    startUrl: 'https://newsource.ns.cnn.com/landing',
    alreadyOk: async (page) => {
      const s = await page.evaluate(() => localStorage.getItem('newsourceSession'));
      return !!s;
    },
    login: async (page, cred) => {
      await page.getByRole('textbox', { name: 'Username' }).fill(cred.user);
      await page.getByRole('textbox', { name: 'Password' }).fill(cred.pass);
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.waitForTimeout(3000);
    },
    verify: async (page) => {
      const s = await page.evaluate(() => localStorage.getItem('newsourceSession'));
      return !!s;
    },
  },
  AP: {
    startUrl: 'https://newsroom.ap.org/',
    alreadyOk: async (page) => !/login\.newsroom\.ap\.org/i.test(page.url()),
    login: async (page, cred) => {
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.waitForTimeout(1500);
      await page.getByRole('textbox', { name: 'Username or Email address' }).fill(cred.user);
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.waitForTimeout(1500);
      await page.getByRole('textbox', { name: 'Enter your password' }).fill(cred.pass);
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.waitForTimeout(3000);
    },
    verify: async (page) => !/login\.newsroom\.ap\.org/i.test(page.url()),
  },
  ENEX: {
    startUrl: 'https://members.enex.news/user/login?destination=/',
    alreadyOk: async (page) => !/\/user\/login/i.test(page.url()),
    login: async (page, cred) => {
      await page.getByRole('textbox', { name: 'Username' }).fill(cred.user);
      await page.getByRole('textbox', { name: 'Password' }).fill(cred.pass);
      await page.getByRole('button', { name: 'Login to Account' }).click();
      await page.waitForTimeout(2500);
    },
    verify: async (page) => !/\/user\/login/i.test(page.url()),
  },
  ABC: {
    startUrl: 'https://abcnews.extremereach.com/cmspage/50162/abclogin?returnUrl=/cmspage/50162/abcnewsone',
    alreadyOk: async (page) => !/abclogin/i.test(page.url()),
    login: async (page, cred) => {
      await page.locator('#userName').fill(cred.user);
      await page.locator('#password').fill(cred.pass);
      await page.getByRole('button', { name: 'Sign In' }).click();
      await page.waitForTimeout(3000);
    },
    verify: async (page) => !/abclogin/i.test(page.url()),
  },
  // ⛔ RT 刻意不列——見檔頭說明，未經使用者明示不得加回。
};

function resolvePlaywright() {
  const path = require('path');
  const base = path.join(process.env.LOCALAPPDATA || '', 'npm-cache', '_npx');
  for (const dir of (fs.existsSync(base) ? fs.readdirSync(base) : [])) {
    const p = path.join(base, dir, 'node_modules', 'playwright');
    if (fs.existsSync(p)) return require(p);
  }
  try { return require('playwright'); } catch (_) { /* fallthrough */ }
  throw new Error('找不到 playwright——npx 快取被清掉了？跑一次 npx @playwright/mcp 重建');
}

function parseArgs(argv) {
  const opts = { sites: Object.keys(SITES), profile: DAILY_PROFILE, headless: true };
  let explicitProfile = null;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--site' && argv[i + 1]) {
      opts.sites = argv[++i].split(',').map((s) => s.trim().toUpperCase()).filter(Boolean);
    } else if (argv[i] === '--profile' && argv[i + 1]) {
      explicitProfile = argv[++i];
    } else if (argv[i] === '--s2') {
      opts.profile = S2_PROFILE;
    } else if (argv[i] === '--headed') {
      opts.headless = false;
    }
  }
  // --profile 明確指定路徑優先權最高，不管跟 --s2 誰先誰後
  if (explicitProfile) opts.profile = explicitProfile;
  return opts;
}

(async () => {
  const opts = parseArgs(process.argv.slice(2));
  const unknown = opts.sites.filter((s) => !SITES[s]);
  if (unknown.length) {
    console.error(`未知站別（RT 刻意不支援自動重登）：${unknown.join(',')}`);
    process.exit(1);
  }

  const creds = loadCredentials();
  const { chromium } = resolvePlaywright();
  const ctx = await chromium.launchPersistentContext(opts.profile, { headless: opts.headless, channel: 'chrome' });
  const out = [];
  let failed = false;

  try {
    const page = ctx.pages()[0] || await ctx.newPage();
    for (const name of opts.sites) {
      const site = SITES[name];
      const cred = creds[name];
      if (!cred) {
        out.push(`${name}=ERR(no-credential)`);
        failed = true;
        continue;
      }
      try {
        await page.goto(site.startUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await page.waitForTimeout(2000);
        if (await site.alreadyOk(page)) {
          out.push(`${name}=OK(already-logged-in)`);
          continue;
        }
        await site.login(page, cred);
        const ok = await site.verify(page);
        if (ok) {
          out.push(`${name}=OK(relogin)`);
        } else {
          out.push(`${name}=FAIL(verify-failed)`);
          failed = true;
        }
      } catch (e) {
        out.push(`${name}=ERR(${String(e.message || e).split('\n')[0].slice(0, 60)})`);
        failed = true;
      }
    }
  } finally {
    await ctx.close();
  }

  console.log(out.join(' '));
  process.exit(failed ? 3 : 0);
})().catch((e) => {
  console.error('ERR ' + String(e.message || e).split('\n')[0]);
  process.exit(1);
});
