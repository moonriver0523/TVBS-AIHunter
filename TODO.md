# TODO

跨 session 待辦清單。規則本身的變更歷史見 `common/auto-script-learning/CHANGELOG.md`／`RULES.md`；這裡只放「還沒做、下次要接著做」的項目。

## 寫稿「人味」風格研究（2026-07-24 啟動，**待使用者說「開始」再動手**）

語料庫已就緒：[`style-corpus/draft_corpus.jsonl`](style-corpus/draft_corpus.jsonl)，1701 篇許岱軒過去 TVBS 完成稿的 `Draft` 區塊，共約 481 萬字、平均每篇 2829 字、中位數 1916 字。

### 已選定的做法：A+B 搭配（2026-07-24 評估後裁定）

評估過三種規模（純統計 A／抽樣質性 B／全量窮舉 C）。全量 C 換算約 800 萬–1200 萬 token、2–5 小時以上，CP 值低，**不採用**。採 **A+B**：用統計數據當骨架、用抽樣質性讀當血肉。

- [x] **A 步：純統計分析（2026-07-24 完成）**——[`style-corpus/analyze_style_A.py`](style-corpus/analyze_style_A.py) → [`style-corpus/analysis_A_report.md`](style-corpus/analysis_A_report.md)。已量出：乾淨斷行中位數 10.5 全形字、p90 19.5、僅 26.9% 超過 14 字上限；標題中位數 19.5（比現行 BAR 16.5–17.5 明顯長）；高頻連接詞 而/更/不過/這是/卻/甚至；語料屬「草稿散文語體」（44.7% 行帶句讀、成句），非最終字幕格式。
- [x] **B 步第二輪（2026-07-24 完成，Fable）**——再讀 50 篇（40 一般＋10 長篇專題，排除第一輪）→ [`style-corpus/analysis_B2_fable.md`](style-corpus/analysis_B2_fable.md)。B1 九組結論 7 成立 2 修正（比喻開關判準改為「有無死亡悲劇」而非題材類別；「不用疑問句」限縮於稿頭層級）。新發現：設問引擎（正文每篇 1–3 個自問自答）、長篇專題六條模板（問題清單骨架/四層推軌/專家SB三連發等）、雙關隱藏簽名（諧音改字+物件雙關回扣收尾）。新增 2 點規則張力待裁定（專家 SB 連發 vs SOT 模板、問號不可被 14 字斷行切開）。
- [x] **B 步：抽樣質性分析（2026-07-24 完成，由 Fable 模型執行）**——[`style-corpus/sample_for_B.py`](style-corpus/sample_for_B.py) 抽 50 篇（`sample_B/` 5 批）→ Fable 產出 [`style-corpus/analysis_B_fable.md`](style-corpus/analysis_B_fable.md)。三大核心發現：①情緒外包紀律（情緒由 SB 承載，OS 只做動作白描＋一句 15–25 字人性註腳）；②比喻有題材開關（戲謔比喻只開在武器/體育/政治攻防稿，人道災難稿比喻歸零）；③收尾即簽名（末句固定為不含新事實的 12–30 字判斷/展望句）。含 8 層面模式+原句證據+可操作指引、「不要學的東西」、「與現行規則的張力」（4 點，待使用者裁定）、一頁式生成檢核表。
- [x] **產出（2026-07-24 完成）**：[`common/10-寫稿風格指南.md`](common/10-寫稿風格指南.md)——合成 A+B1+B2 為 13 節可操作指南（語體判定/稿頭四型/敘事節奏/比喻死亡開關/情緒外包/簽名層額度/標題/收尾/長篇專題/內幕改寫/用字/檢核表/待裁定張力）。已接進寫稿流程：`cnn/01` 與 `common/06` 的「開始前必讀」各加「寫稿階段另讀 10」指引，定位為風格參照層、格式規則優先。
- [ ] **待使用者裁定：6 點規則張力**（見指南第 13 節）：①14字斷行 vs 成句節奏 ②BAR字數 vs 標題三段結構 ③稿頭150字 vs 故事鉤子 ④驚嘆號低密度約束 ⑤專家SB三連發 vs SOT模板 ⑥問號不可被斷行切開。
- [ ] **待使用者裁定：語料個資清理**——B2 發現 `0725-1`（泰柬軍力專題）稿內留有台南大學教授的電話分機；另 B1/B2 均見帳密區塊。語料已 commit 進私人 repo，是否清除後重寫歷史/重新 commit 由使用者決定。
- [ ] **實戰驗證迴圈**：用指南實際寫 1–2 篇 CTV/SOT，走既有 auto-script-learning 校稿機制比對使用者修改，驗證指南可執行性。
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
