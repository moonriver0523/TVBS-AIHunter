# TODO

跨 session 待辦清單。規則本身的變更歷史見 `common/auto-script-learning/CHANGELOG.md`／`RULES.md`；這裡只放「還沒做、下次要接著做」的項目。

## 寫稿「人味」風格研究（2026-07-24 啟動）

- [ ] 對 [`style-corpus/draft_corpus.jsonl`](style-corpus/draft_corpus.jsonl)（1701 篇許岱軒過去 TVBS 完成稿的 `Draft` 區塊）做風格分析：用詞頻率、句長分布、常見句式，跟現行 CTV/SOT 規則（字數上限、斷句規則）對照，找出「人味」跟現行機械規則之間的落差。
- [ ] 決定怎麼把語料庫實際餵進寫稿流程——例如：寫稿前抽幾篇當範例、或先做語感摘要成一份精簡風格指南，供 CTV/SOT 寫稿時參考。
- [ ] `Note`（CG 文字稿）欄位目前只原樣保留在 `draft_corpus.jsonl` 裡，尚未使用；未來若要做 CG 文字風格研究可另外處理。

以上不影響現有字數/格式規則（`P-001`~`P-019`），純粹是額外的風格參照層，見 [`style-corpus/README.md`](style-corpus/README.md)。

## `.git` 肥大清理（2026-07-24 規劃，暫緩執行）

- [ ] 用 `git filter-repo` 從全部歷史（所有分支含 `agent/rules-v2-sandbox`）剔除三個已棄用的舊路徑：`.tmp-sot/`（141MB whisper 模型 `ggml-base.en.bin`）、`.tmp-yt-dlp/`（83MB `ffmpeg-win-x86_64-v7.1.exe` 及整包 vendored yt-dlp）、`downloads/`（幾支測試下載的 mp4）。三者皆已被 `.gitignore` 排除、現在的 tracked 樹裡完全不存在，純粹是歷史包袱。
- [ ] 指令：`git filter-repo --path .tmp-sot/ --path .tmp-yt-dlp/ --path downloads/ --invert-paths --force`（`git-filter-repo` 已裝好，2026-07-24 用 `pip install git-filter-repo`）。
- [ ] 執行前已做好完整 mirror 備份：`E:\GitHub\TVBS-AIHunter-backup-20260724.git`（198MB，含所有 refs，改壞可從這裡復原）。
- [ ] **會改寫全部 commit hash**，之後必須 force-push 才能同步回 GitHub；GitHub 上已合併完的舊分支（`agent/add-bite-and-batch-rules` 等）建議一併刪除，否則會繼續留著舊肥大 blob 抵銷清理效果。
- [ ] force-push 後，Mac 那台 clone 的 `git pull --ff-only` 自動化 hook 會失效，需要在 Mac 上重新 clone 或手動 reset 到新歷史。
- [ ] 使用者 2026-07-24 裁決：先不動手，列入 TODO 待之後再決定執行時機。

## 已完成

- [x] **DVIDS 也要抓文稿**（2026-07-24 完成）：已在 [`reuters/05-batch-download.md`](reuters/05-batch-download.md) 補 DVIDS 來源分派與處理細節（影片本體 `yt-dlp`＋詳情頁 `get_page_text` 抓文稿、欄位清單、B-Roll 拍攝日非當日的提醒），並在 [`common/05-material-numbering.md`](common/05-material-numbering.md) 補 DVIDS URL 的編號歸屬。
