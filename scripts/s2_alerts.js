'use strict';
/**
 * AP／RT 快訊守護：零 Claude token。
 *
 * 預設關閉——沒有 %USERPROFILE%\.s2-alerts-enabled 就立刻離開。
 * 用 s2_alerts_ctl.ps1 -On／-Off 開關。
 *
 *   node s2_alerts.js              常駐迴圈（旗標消失就退出）
 *   node s2_alerts.js --once       只跑一輪
 *   node s2_alerts.js --dry-run    不呼叫推播出口
 *   node s2_alerts.js --force      忽略旗標（只給人工測試）
 *
 * 首次有資料只建基準、不推，避免啟動洗幾十則。
 * 推播走 scripts/s2_alerts_push.ps1（既有 Send-Ntfy）。
 */
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawnSync } = require('child_process');
const lib = require('./s2_alerts_lib');

const PROFILE = 'C:/Users/User/.playwright-s2-profile';
const FLAG = path.join(os.homedir(), '.s2-alerts-enabled');
const SEEN_FILE = path.join(os.homedir(), '.s2-alerts-seen.json');
const LOCK = path.join(os.homedir(), '.s2-scan.lock');
const INTERVAL_MS = 90 * 1000;
const PUSH_PS1 = path.join(__dirname, 's2_alerts_push.ps1');

function resolveLog() {
  const cloud = 'G:/我的雲端硬碟/Claude共用/自動掃帶系統/S2掃帶log/_alerts.log';
  try {
    fs.mkdirSync(path.dirname(cloud), { recursive: true });
    return cloud;
  } catch (_) {
    const local = 'D:/Downloads/S2掃帶log/_alerts.log';
    try { fs.mkdirSync(path.dirname(local), { recursive: true }); } catch (e) { /* ignore */ }
    return local;
  }
}
const LOG = resolveLog();

function log(line) {
  const stamp = new Date().toISOString().replace('T', ' ').slice(0, 19);
  const s = stamp + '\t' + line;
  try { fs.appendFileSync(LOG, s + '\n', 'utf8'); } catch (_) { /* 雲端鎖檔不炸 */ }
  console.log(line);
}

function argsHas(flag) {
  return process.argv.slice(2).indexOf(flag) !== -1;
}

function resolvePlaywright() {
  const base = path.join(process.env.LOCALAPPDATA || '', 'npm-cache', '_npx');
  if (fs.existsSync(base)) {
    for (const dir of fs.readdirSync(base)) {
      const p = path.join(base, dir, 'node_modules', 'playwright');
      if (fs.existsSync(p)) return require(p);
    }
  }
  try { return require('playwright'); } catch (_) { /* fallthrough */ }
  throw new Error('找不到 playwright——跑一次 npx @playwright/mcp 重建快取');
}

function readSeen() {
  try {
    if (!fs.existsSync(SEEN_FILE)) return {};
    const j = JSON.parse(fs.readFileSync(SEEN_FILE, 'utf8'));
    return j && typeof j === 'object' ? j : {};
  } catch (e) {
    log('WARN seen 讀檔失敗，當成首次：' + e.message);
    return {};
  }
}

function writeSeen(seen) {
  try {
    fs.writeFileSync(SEEN_FILE, JSON.stringify(seen), 'utf8');
  } catch (e) {
    log('WARN seen 寫檔失敗：' + e.message);
  }
}

function lockHeld() {
  try {
    if (!fs.existsSync(LOCK)) return false;
    const st = fs.statSync(LOCK);
    if (Date.now() - st.mtimeMs > 90 * 60 * 1000) return false;
    return true;
  } catch (_) {
    return false;
  }
}

function profileBusy() {
  try {
    const r = spawnSync('powershell.exe', [
      '-NoProfile', '-Command',
      "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('.playwright-s2-profile') } | Measure-Object | Select-Object -ExpandProperty Count",
    ], { encoding: 'utf8', timeout: 15000 });
    const n = parseInt(String(r.stdout || '').trim(), 10);
    return Number.isFinite(n) && n > 0;
  } catch (_) {
    return false;
  }
}

function pushAlert(push) {
  const r = spawnSync('pwsh.exe', [
    '-NoProfile', '-File', PUSH_PS1,
    '-Body', push.body,
    '-Title', push.title,
    '-Tags', push.tags || 'warning',
    '-Priority', push.priority || 'high',
  ], { encoding: 'utf8', timeout: 30000 });
  if (r.status !== 0) {
    return String(r.stdout || r.stderr || 'push-failed').trim().slice(0, 120);
  }
  return null;
}

async function grabJson(page, urlPart, gotoUrl) {
  const pending = page.waitForResponse(
    (r) => r.url().indexOf(urlPart) !== -1 && r.ok(),
    { timeout: 28000 },
  );
  await page.goto(gotoUrl, { waitUntil: 'domcontentloaded', timeout: 45000 });
  const resp = await pending;
  return resp.json();
}

async function oneCycle(page, dryRun) {
  const items = [];
  try {
    const rt = await grabJson(
      page,
      'messages/user',
      'https://www.reutersconnect.com/all?media-types=vid',
    );
    items.push.apply(items, lib.parseRtMessages(rt));
  } catch (e) {
    log('WARN RT ' + String(e.message || e).split('\n')[0].slice(0, 80));
  }
  try {
    const ap = await grabJson(
      page,
      'nr_breaking_news',
      'https://newsroom.ap.org/home',
    );
    items.push.apply(items, lib.parseApBreaking(ap));
  } catch (e) {
    log('WARN AP ' + String(e.message || e).split('\n')[0].slice(0, 80));
  }

  const r = lib.applyCycle(readSeen(), items);
  writeSeen(r.seen);
  if (r.seeded) {
    log('SEED 基準 ' + items.length + ' 則（不推） RT=' +
      items.filter((x) => x.site === 'RT').length +
      ' AP=' + items.filter((x) => x.site === 'AP').length);
    return { seeded: true, n: 0 };
  }
  for (const it of r.notify) {
    const p = lib.formatPush(it);
    if (dryRun) {
      log('DRY ' + it.id + ' ' + (it.text || '').slice(0, 80));
    } else {
      const err = pushAlert(p);
      if (err) log('WARN push ' + err + ' ' + it.id);
      else log('PUSH ' + it.id + ' ' + (it.text || '').slice(0, 80));
    }
  }
  if (!r.notify.length) log('OK 無新快訊（監看 ' + Object.keys(r.seen).length + '）');
  return { seeded: false, n: r.notify.length };
}

async function main() {
  process.title = 's2-alerts';
  const once = argsHas('--once');
  const dryRun = argsHas('--dry-run');
  const force = argsHas('--force');

  if (!force && !lib.isEnabled(FLAG)) {
    console.log('DISABLED（沒有 .s2-alerts-enabled，預設關）');
    process.exit(0);
  }

  if (lockHeld()) {
    log('SKIP 掃帶鎖占用，這輪不開瀏覽器');
    process.exit(0);
  }
  if (profileBusy()) {
    log('BUSY profile 已被其他 chromium 占用，這輪不搶（掃帶／保活優先）');
    process.exit(0);
  }

  const { chromium } = resolvePlaywright();
  const ctx = await chromium.launchPersistentContext(PROFILE, { headless: true });
  const page = ctx.pages()[0] || await ctx.newPage();

  try {
    do {
      if (!force && !lib.isEnabled(FLAG)) {
        log('旗標已撤，退出');
        break;
      }
      if (lockHeld()) {
        log('SKIP 掃帶鎖占用');
      } else {
        await oneCycle(page, dryRun);
      }
      if (once) break;
      await new Promise((res) => setTimeout(res, INTERVAL_MS));
    } while (true);
  } finally {
    await ctx.close();
  }
}

main().catch((e) => {
  console.error('ERR ' + String(e.message || e).split('\n')[0]);
  process.exit(1);
});
