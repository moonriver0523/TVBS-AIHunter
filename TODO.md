# TODO

跨 session 待辦清單。規則本身的變更歷史見 `common/auto-script-learning/CHANGELOG.md`／`RULES.md`；這裡只放「還沒做、下次要接著做」的項目。

## 寫稿「人味」風格研究（2026-07-24 啟動）

- [ ] 對 [`style-corpus/draft_corpus.jsonl`](style-corpus/draft_corpus.jsonl)（1701 篇許岱軒過去 TVBS 完成稿的 `Draft` 區塊）做風格分析：用詞頻率、句長分布、常見句式，跟現行 CTV/SOT 規則（字數上限、斷句規則）對照，找出「人味」跟現行機械規則之間的落差。
- [ ] 決定怎麼把語料庫實際餵進寫稿流程——例如：寫稿前抽幾篇當範例、或先做語感摘要成一份精簡風格指南，供 CTV/SOT 寫稿時參考。
- [ ] `Note`（CG 文字稿）欄位目前只原樣保留在 `draft_corpus.jsonl` 裡，尚未使用；未來若要做 CG 文字風格研究可另外處理。

以上不影響現有字數/格式規則（`P-001`~`P-019`），純粹是額外的風格參照層，見 [`style-corpus/README.md`](style-corpus/README.md)。

## DVIDS 也要抓文稿（2026-07-24 啟動）

- [ ] 在 [`reuters/05-batch-download.md`](reuters/05-batch-download.md) 的來源分派表與各來源處理細節補上 **DVIDS**：目前 DVIDS 比照 YouTube 只用 `yt-dlp` 下載影片本體、沒抓文稿；但 DVIDS 影片詳情頁（`dvidshub.net/video/{id}/...`）有可用的**文字資訊**要一併存成 `{SLUG} #XX DVIDS (外電文稿).txt`。
- [ ] 文稿內容欄位（實測 2026-07-24「加倍轟伊2200」#08/#09）：**標題、DESCRIPTION 段（英文說明）、拍攝者/單位、Date Taken / Date Posted、Category（多為 B-Roll）、Length、Location、Video ID / VIRIN / Filename、版權（多為 PUBLIC DOMAIN，須遵守 dvidshub.net/about/copyright）**。抓法：詳情頁直接 `get_page_text` 即可一次拿到（不像 AP 要另開分頁）。
- [ ] 注意 **Date Taken 常常不是新聞當日**（B-Roll 資料帶），寫稿時要判斷是否僅能當背景/資料畫面，文稿裡要註明拍攝日與「非當日新畫面」。
- [ ] 順帶檢查 [`common/05-material-numbering.md`](common/05-material-numbering.md)：目前 URL 類只列 YouTube/X/Facebook，DVIDS 是直接給 `dvidshub.net` 網址，編號時比照一般素材（已於 2200 案例這樣做），規則文件可補一句明確化。
