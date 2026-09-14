/**
 * S2 掃帶用：NS／AP／ENEX／ABC 四站自動重登入，預設 S2 v4 掃帶生產 profile
 * （`.playwright-s2-profile-v4`，跟 `s2_mcp.json`／`s2_keepalive.js` 同一個）。
 *
 * ⛔ 不含 RT，⚠️ 不要跟 `s2_relogin_daily.js`（平常瀏覽用，預設 daily profile）
 * 搞混——兩支預設 profile 不同，邏輯見共用的 `s2_relogin_lib.js`。
 *
 * 用法：
 *   node s2_relogin_s2.js                 # 依序嘗試 NS/AP/ENEX/ABC
 *   node s2_relogin_s2.js --site NS,AP    # 只重登指定站（逗號分隔）
 *   node s2_relogin_s2.js --headed        # 顯示視窗（預設 headless）
 *   node s2_relogin_s2.js --profile <dir> # 覆寫成別的 profile 路徑
 */
'use strict';

const { run } = require('./s2_relogin_lib');

const S2_PROFILE = 'C:/Users/User/.playwright-s2-profile-v4';

run(process.argv.slice(2), S2_PROFILE).catch((e) => {
  console.error('ERR ' + String(e.message || e).split('\n')[0]);
  process.exit(1);
});
