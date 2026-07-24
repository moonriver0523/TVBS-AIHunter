# TODO

跨 session 待辦清單。規則本身的變更歷史見 `common/auto-script-learning/CHANGELOG.md`／`RULES.md`；這裡只放「還沒做、下次要接著做」的項目。

## 寫稿「人味」風格研究（2026-07-24 啟動）

- [ ] 對 [`style-corpus/draft_corpus.jsonl`](style-corpus/draft_corpus.jsonl)（1701 篇許岱軒過去 TVBS 完成稿的 `Draft` 區塊）做風格分析：用詞頻率、句長分布、常見句式，跟現行 CTV/SOT 規則（字數上限、斷句規則）對照，找出「人味」跟現行機械規則之間的落差。
- [ ] 決定怎麼把語料庫實際餵進寫稿流程——例如：寫稿前抽幾篇當範例、或先做語感摘要成一份精簡風格指南，供 CTV/SOT 寫稿時參考。
- [ ] `Note`（CG 文字稿）欄位目前只原樣保留在 `draft_corpus.jsonl` 裡，尚未使用；未來若要做 CG 文字風格研究可另外處理。

以上不影響現有字數/格式規則（`P-001`~`P-019`），純粹是額外的風格參照層，見 [`style-corpus/README.md`](style-corpus/README.md)。

## 已完成

- [x] **DVIDS 也要抓文稿**（2026-07-24 完成）：已在 [`reuters/05-batch-download.md`](reuters/05-batch-download.md) 補 DVIDS 來源分派與處理細節（影片本體 `yt-dlp`＋詳情頁 `get_page_text` 抓文稿、欄位清單、B-Roll 拍攝日非當日的提醒），並在 [`common/05-material-numbering.md`](common/05-material-numbering.md) 補 DVIDS URL 的編號歸屬。
