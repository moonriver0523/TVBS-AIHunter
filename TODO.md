# TODO

跨 session 待辦清單。規則本身的變更歷史見 `common/auto-script-learning/CHANGELOG.md`／`RULES.md`；這裡只放「還沒做、下次要接著做」的項目。

## 寫稿「人味」風格研究（2026-07-24 啟動，**待使用者說「開始」再動手**）

語料庫已就緒：[`style-corpus/draft_corpus.jsonl`](style-corpus/draft_corpus.jsonl)，1701 篇許岱軒過去 TVBS 完成稿的 `Draft` 區塊，共約 481 萬字、平均每篇 2829 字、中位數 1916 字。

### 已選定的做法：A+B 搭配（2026-07-24 評估後裁定）

評估過三種規模（純統計 A／抽樣質性 B／全量窮舉 C）。全量 C 換算約 800 萬–1200 萬 token、2–5 小時以上，CP 值低，**不採用**。採 **A+B**：用統計數據當骨架、用抽樣質性讀當血肉。

- [x] **A 步：純統計分析（2026-07-24 完成）**——[`style-corpus/analyze_style_A.py`](style-corpus/analyze_style_A.py) → [`style-corpus/analysis_A_report.md`](style-corpus/analysis_A_report.md)。已量出：乾淨斷行中位數 10.5 全形字、p90 19.5、僅 26.9% 超過 14 字上限；標題中位數 19.5（比現行 BAR 16.5–17.5 明顯長）；高頻連接詞 而/更/不過/這是/卻/甚至；語料屬「草稿散文語體」（44.7% 行帶句讀、成句），非最終字幕格式。
- [ ] **B 步：抽樣質性分析（約 25–40 萬 token）**——跨時間/主題抽 40–60 篇代表性稿件，讀完整文本感受語感、句式、轉場手法、稿頭與收尾的節奏，補 A 抓不到的質性層面。預估 30–60 分鐘。
- [ ] **產出**：把 A+B 的發現整理成一份精簡的「風格指南」，並決定怎麼實際餵進寫稿流程（寫稿前抽幾篇當範例／或用風格指南當 CTV/SOT 寫稿的參考層）。
- [ ] `Note`（CG 文字稿）欄位目前只原樣保留在 `draft_corpus.jsonl` 裡，尚未使用；未來若要做 CG 文字風格研究可另外處理。

以上不影響現有字數/格式規則（`P-001`~`P-021`），純粹是額外的風格參照層，見 [`style-corpus/README.md`](style-corpus/README.md)。**使用者明確要求：等他說「開始」再動手，現在只記錄不執行。**

## `.git` 肥大清理（2026-07-24 規劃，暫緩執行）

- [ ] 用 `git filter-repo` 從全部歷史（所有分支含 `agent/rules-v2-sandbox`）剔除三個已棄用的舊路徑：`.tmp-sot/`（141MB whisper 模型 `ggml-base.en.bin`）、`.tmp-yt-dlp/`（83MB `ffmpeg-win-x86_64-v7.1.exe` 及整包 vendored yt-dlp）、`downloads/`（幾支測試下載的 mp4）。三者皆已被 `.gitignore` 排除、現在的 tracked 樹裡完全不存在，純粹是歷史包袱。
- [ ] 指令：`git filter-repo --path .tmp-sot/ --path .tmp-yt-dlp/ --path downloads/ --invert-paths --force`（`git-filter-repo` 已裝好，2026-07-24 用 `pip install git-filter-repo`）。
- [ ] 執行前已做好完整 mirror 備份：`E:\GitHub\TVBS-AIHunter-backup-20260724.git`（198MB，含所有 refs，改壞可從這裡復原）。
- [ ] **會改寫全部 commit hash**，之後必須 force-push 才能同步回 GitHub；GitHub 上已合併完的舊分支（`agent/add-bite-and-batch-rules` 等）建議一併刪除，否則會繼續留著舊肥大 blob 抵銷清理效果。
- [ ] force-push 後，Mac 那台 clone 的 `git pull --ff-only` 自動化 hook 會失效，需要在 Mac 上重新 clone 或手動 reset 到新歷史。
- [ ] 使用者 2026-07-24 裁決：先不動手，列入 TODO 待之後再決定執行時機。

## 已完成

- [x] **DVIDS 也要抓文稿**（2026-07-24 完成）：已在 [`reuters/05-batch-download.md`](reuters/05-batch-download.md) 補 DVIDS 來源分派與處理細節（影片本體 `yt-dlp`＋詳情頁 `get_page_text` 抓文稿、欄位清單、B-Roll 拍攝日非當日的提醒），並在 [`common/05-material-numbering.md`](common/05-material-numbering.md) 補 DVIDS URL 的編號歸屬。
