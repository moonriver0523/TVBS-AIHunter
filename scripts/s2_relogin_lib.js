/**
 * NS／AP／ENEX／ABC 四站自動重登入的共用邏輯，被 `s2_relogin_daily.js`（平常用，
 * 預設 daily profile）與 `s2_relogin_s2.js`（S2 掃帶用，預設 v4 profile）共用。
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
 * ⚠️ 這支是「主動重登」，跟 `s2_keepalive.js`（單純載頁面續期，不填帳密）是兩支不同
 *    職責的腳本，刻意不合併——keepalive 的 AP 目前處於「移出保活」實驗觀察期
 *    （見該檔內註解），本支不動那個實驗，只在被明確呼叫時才對 AP 動作。
 */
'use strict';

const fs = require('fs');
const path = require('path');

const CRED_FILE = 'C:/Users/User/.s2_five_sites_credentials';

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

// AP 登入態判定（2026-09-25 修正誤判）：
//   - 登出時不是伺服器端立即轉址，而是前端 JS 載入後才導到 login.newsroom.ap.org；
//     只看 goto 當下的網址會把「已登出」誤判成 already-logged-in。
//   - headless 下 AP 前端常常根本不跑（頁面只剩「Skip to main content」、不打任何 API；
//     全新 profile 甚至直接吃 Cloudflare 封鎖頁），轉址永遠不會發生。
//   所以改成等「正面證據」：出現 Sign out 連結＝已登入；被導到登入網域、或停在
//   公開首頁出現 Sign in 按鈕＝未登入；逾時都沒有＝無法判定，丟錯誤讓呼叫端回報，
//   不再默認已登入。
async function apLoginState(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (/login\.newsroom\.ap\.org/i.test(page.url())) return 'logged-out';
    const title = await page.title().catch(() => '');
    if (/Attention Required|Cloudflare/i.test(title)) throw new Error('cloudflare-blocked');
    // Sign out 連結收在帳號選單裡、平常是隱藏的，getByRole 會略過隱藏元素，所以直接查 DOM。
    const signOut = await page.evaluate(() => [...document.querySelectorAll('a,button')]
      .some((e) => /^\s*sign\s*out\s*$/i.test(e.textContent || ''))).catch(() => false);
    if (signOut) return 'logged-in';
    // 從沒登入過的 profile 不會轉址，而是停在公開首頁（「Do you have an AP Newsroom
    // account?」＋ Sign in 按鈕），這也算未登入。
    const signIn = await page.getByRole('button', { name: 'Sign in' }).count().catch(() => 0);
    if (signIn > 0) return 'logged-out';
    await page.waitForTimeout(500);
  }
  throw new Error('state-unknown(page-not-rendered)');
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
    // 判定邏輯見上方 apLoginState() 註解；有跑 AP 時 run() 預設開有視窗模式。
    alreadyOk: async (page) => (await apLoginState(page, 25000)) === 'logged-in',
    login: async (page, cred) => {
      // 被 JS 導到 login.newsroom.ap.org/u/login/identifier 時已經是帳號輸入頁，
      // 沒有首頁那顆「Sign in」可按；只有停在首頁時才先按。
      const userBox = page.getByRole('textbox', { name: 'Username or Email address' });
      if (!(await userBox.isVisible().catch(() => false))) {
        await page.getByRole('button', { name: 'Sign in' }).click();
        await page.waitForTimeout(1500);
      }
      await userBox.fill(cred.user);
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.waitForTimeout(1500);
      await page.getByRole('textbox', { name: 'Enter your password' }).fill(cred.pass);
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.waitForTimeout(3000);
    },
    verify: async (page) => (await apLoginState(page, 25000)) === 'logged-in',
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
  const base = path.join(process.env.LOCALAPPDATA || '', 'npm-cache', '_npx');
  for (const dir of (fs.existsSync(base) ? fs.readdirSync(base) : [])) {
    const p = path.join(base, dir, 'node_modules', 'playwright');
    if (fs.existsSync(p)) return require(p);
  }
  try { return require('playwright'); } catch (_) { /* fallthrough */ }
  throw new Error('找不到 playwright——npx 快取被清掉了？跑一次 npx @playwright/mcp 重建');
}

function parseArgs(argv, defaultProfile, apHeadedDefault) {
  const opts = { sites: Object.keys(SITES), profile: defaultProfile, headless: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--site' && argv[i + 1]) {
      opts.sites = argv[++i].split(',').map((s) => s.trim().toUpperCase()).filter(Boolean);
    } else if (argv[i] === '--profile' && argv[i + 1]) {
      opts.profile = argv[++i];
    } else if (argv[i] === '--headed') {
      opts.headless = false;
    } else if (argv[i] === '--headless') {
      opts.headless = true;
    }
  }
  // 沒明講時：daily 版有跑 AP 就開視窗（headless 下 AP 前端不跑、無法判定登入態）；
  // S2 版（s2_keepalive.ps1 無人值守呼叫、v4 profile 開視窗在本機有已知問題）維持 headless，
  // AP 判定不了會回 ERR(state-unknown…) 交給人工，不再誤報已登入。
  if (opts.headless === null) opts.headless = !(apHeadedDefault && opts.sites.includes('AP'));
  return opts;
}

// 離開碼：0＝全部成功（或該站已在登入態、不需重登）；3＝有站重登失敗（需人工介入）；
//         1＝其他錯誤（例如讀不到帳密檔）。
async function run(argv, defaultProfile, { apHeadedDefault = false } = {}) {
  const opts = parseArgs(argv, defaultProfile, apHeadedDefault);
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

  console.log(`[profile=${opts.profile}] ` + out.join(' '));
  process.exit(failed ? 3 : 0);
}

module.exports = { run, SITES };
