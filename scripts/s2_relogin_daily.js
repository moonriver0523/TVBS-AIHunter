/**
 * 平常瀏覽用：NS／AP／ENEX／ABC 四站自動重登入，預設 DAILY profile
 * （`.playwright-daily-profile`，跟 `mcp__browser__*` 工具用的是同一個）。
 *
 * ⛔ 不含 RT，⚠️ 不要跟 `s2_relogin_s2.js`（掃帶用，預設 v4 profile）搞混——
 * 兩支預設 profile 不同，邏輯見共用的 `s2_relogin_lib.js`。
 *
 * 用法：
 *   node s2_relogin_daily.js                 # 依序嘗試 NS/AP/ENEX/ABC
 *   node s2_relogin_daily.js --site NS,AP    # 只重登指定站（逗號分隔）
 *   node s2_relogin_daily.js --headed        # 顯示視窗（預設 headless）
 *   node s2_relogin_daily.js --profile <dir> # 覆寫成別的 profile 路徑
 */
'use strict';

const { run } = require('./s2_relogin_lib');

const DAILY_PROFILE = 'C:/Users/User/.playwright-daily-profile';

run(process.argv.slice(2), DAILY_PROFILE).catch((e) => {
  console.error('ERR ' + String(e.message || e).split('\n')[0]);
  process.exit(1);
});
