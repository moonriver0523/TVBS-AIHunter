/**
 * 晚班交接 HTML 的 Google Apps Script 代管（2026-08-09；歷史瀏覽 2026-08-11）。
 *
 * 為什麼需要這支：**Google Drive 從 2016 年就停掉網頁代管**，直接把 .html 丟 Drive、
 * 用分享連結開，只會看到原始碼或下載提示——**JS 不會執行**，搜尋與篩選全部失效。
 * 這支把檔案內容當網頁吐出來，編輯用手機開一個固定網址就是完整互動版。
 *
 * ⛔ **絕對不要把存取權開成「網際網路上的任何人」**：內容含路透／AP 的限制條款
 *    （For Reuters customers only、限播地區等），公開等於違約。
 *    部署時存取權限選 **TVBS 網域內的使用者**（或指定人員）。
 *
 * 📌 **檔案是自己找的，不寫死 ID**：晚班交接檔名每天帶日期（0808→0809），
 *    寫死 ID 會在換日那天壞掉。這裡改成搜尋檔名含「晚班交接.html」的檔案、
 *    取**最後修改時間最新**的那份——所以掃帶每輪重新產出後，網址內容自動跟著更新，
 *    網址本身永遠不用換。
 *
 * 📌 **歷史瀏覽（2026-08-11）**：`s2_render_html.py` 現在會在檔頭下方印一條「歷史」
 *    列，連結是 `?date=MMDD`（例：`?date=0810`）。這支加了 `findByDate_()` 接住這個
 *    參數——不帶參數（或帶了但找不到）一律退回原本的「抓最新」，行為不變、
 *    網址本身仍然不用換，只是同一個網址現在能多接一個可選參數。
 */

/** 檔名的搜尋關鍵字。改檔名規則時這裡要一起改。 */
var NAME_HINT = '晚班交接.html';

function doGet(e) {
  var date = e && e.parameter && e.parameter.date;
  var file = date ? findByDate_(date) : findLatest_();
  if (!file) {
    var msg = date
      ? ('找不到 ' + date + ' 的晚班交接檔案（可能還沒掃到那天，或已經搬出 Archive 保留範圍）。' +
         '<br><a href="?">回到今天</a>')
      : ('找不到檔名含「' + NAME_HINT + '」的檔案。<br>' +
         '請確認：①檔案已同步到這個 Google 帳號的雲端硬碟 ②檔案沒有被丟到垃圾桶。');
    return HtmlService.createHtmlOutput(
      '<meta charset="utf-8"><p style="font:16px sans-serif;padding:20px">' + msg + '</p>');
  }
  var html = file.getBlob().getDataAsString('UTF-8');
  return HtmlService.createHtmlOutput(html)
    .setTitle(file.getName().replace(/\.html$/i, ''))
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/** 取檔名含 NAME_HINT、最後修改時間最新的那一份。 */
function findLatest_() {
  var q = 'title contains "' + NAME_HINT + '" and trashed = false';
  var it = DriveApp.searchFiles(q);
  var best = null;
  while (it.hasNext()) {
    var f = it.next();
    if (!best || f.getLastUpdated() > best.getLastUpdated()) best = f;
  }
  return best;
}

/**
 * 精準比對檔名＝`{MMDD}晚班交接.html`（例：`0810晚班交接.html`），用在 `?date=` 查詢。
 * ⚠️ **先驗證格式再拼進 Drive 查詢字串**——不然任何人把 `date` 參數帶成帶引號的
 *    字串，就能改變查詢語意去搜尋不該搜到的檔案。四位數字以外的一律直接回 null，
 *    不觸發任何 Drive API 呼叫。
 */
function findByDate_(mmdd) {
  if (!/^\d{4}$/.test(mmdd)) return null;
  var name = mmdd + NAME_HINT;
  var q = 'title = "' + name + '" and trashed = false';
  var it = DriveApp.searchFiles(q);
  return it.hasNext() ? it.next() : null;
}

/**
 * 部署前先在編輯器裡跑這支，確認找得到檔、也能讀得到內容。
 * 執行紀錄會印出檔名、修改時間與大小——都對了再去部署，
 * 免得部署完才發現是權限或檔名問題。
 */
function 測試找檔() {
  var f = findLatest_();
  if (!f) { console.log('❌ 找不到檔名含「%s」的檔案', NAME_HINT); return; }
  var s = f.getBlob().getDataAsString('UTF-8');
  console.log('✅ 檔名：%s', f.getName());
  console.log('   最後修改：%s', f.getLastUpdated());
  console.log('   大小：%s 字元', s.length);
  console.log('   看起來是完整網頁：%s', s.indexOf('<!doctype html') === 0 ? '是' : '否（請檢查）');
}

/**
 * 部署前測 `?date=` 那條路——**改這裡的 MMDD 成一個 Archive 裡實際存在的日期**再跑。
 */
function 測試找日期() {
  var mmdd = '0810';   // ← 改成你要測的日期
  var f = findByDate_(mmdd);
  if (!f) { console.log('❌ 找不到 %s晚班交接.html（檢查 Archive 裡有沒有這份檔案）', mmdd); return; }
  console.log('✅ 檔名：%s', f.getName());
  console.log('   最後修改：%s', f.getLastUpdated());
}
