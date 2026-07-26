# TODO

跨 session 待辦清單。規則本身的變更歷史見 `common/auto-script-learning/CHANGELOG.md`／`RULES.md`；這裡只放「還沒做、下次要接著做」的項目。

## 🔴 資安：帳密外洩後續（2026-07-25，只有使用者能處理）

清除語料時發現**歐新社（EPA）與 TVBS 數位帳號的帳號＋密碼明文**被當頁尾樣板貼進 401 篇稿件，並隨語料進了版控（commit `b4b278d`）。工作區已清乾淨（`ffda02f`），但以下兩件只有使用者能決定／執行：

- [ ] **更換這些帳密（最優先）**——清除只是止血；憑證仍存在於 git 歷史，任何有 repo 讀取權者都拿得到。**改密碼是唯一有效的補救**，不做這件事其他都沒意義。
- [ ] **（可選）改寫 git 歷史徹底移除舊憑證**——需 `git filter-repo`，代價：全部 commit hash 改變、必須 force-push、Mac 那台的自動 pull hook 失效。**建議與下方「`.git` 肥大清理」合併成同一次歷史改寫**，只付一次代價。考量這是私人 repo，且帳密更換後舊憑證即失效，不改寫歷史亦可接受——但上一項不能省。
- [ ] **源頭防治**：這批帳密是 Notion 稿件範本的頁尾，日後再從 Notion 匯出語料仍會帶進來。要嘛請同事把範本裡的帳密拿掉，要嘛每次匯入後固定跑一次 `python style-corpus/redact_secrets.py`（需先備妥 gitignored 的 `.secret-tokens.txt`）。

## 寫稿「人味」風格研究（2026-07-24 啟動，**待使用者說「開始」再動手**）

語料庫已就緒：[`style-corpus/draft_corpus.jsonl`](style-corpus/draft_corpus.jsonl)，1701 篇許岱軒過去 TVBS 完成稿的 `Draft` 區塊，共約 481 萬字、平均每篇 2829 字、中位數 1916 字。

### 已選定的做法：A+B 搭配（2026-07-24 評估後裁定）

評估過三種規模（純統計 A／抽樣質性 B／全量窮舉 C）。全量 C 換算約 800 萬–1200 萬 token、2–5 小時以上，CP 值低，**不採用**。採 **A+B**：用統計數據當骨架、用抽樣質性讀當血肉。

- [x] **A 步：純統計分析（2026-07-24 完成）**——[`style-corpus/analyze_style_A.py`](style-corpus/analyze_style_A.py) → [`style-corpus/analysis_A_report.md`](style-corpus/analysis_A_report.md)。已量出：乾淨斷行中位數 10.5 全形字、p90 19.5、僅 26.9% 超過 14 字上限；標題中位數 19.5（比現行 BAR 16.5–17.5 明顯長）；高頻連接詞 而/更/不過/這是/卻/甚至；語料屬「草稿散文語體」（44.7% 行帶句讀、成句），非最終字幕格式。
- [x] **B 步第四輪（2026-07-25 完成，Fable，異常側寫篩選精讀）**——全量掃描 1375 篇未讀稿的風格異常訊號 → 前 40 名精讀 → [`style-corpus/analysis_B4_fable.md`](style-corpus/analysis_B4_fable.md)。真陽性 28/40（嚴格 20/40），12 條全新招式（N1–N12）＋8 項既有招補證。**重大發現：第五種語體「影音變色強調體」**（社群短影音改寫規格，僅 2 標本待補齊）。篩選器評價：值得再用但需修訂（ellipsis 最佳訊號；redup/onoma 要加專名白名單）。語料衛生：**已制度化（2026-07-25）**——`tag_unread.py` 產生 `quality` 標記（ok 1632／stub 63／practice 3／ai_assisted 3），抽樣鐵則改為「`unread` 且 `quality=ok`」（可用池 1473 篇），`screen_for_B4.py` 已內建過濾。**已決定（2026-07-25）**：10 條建議項全數入指南（`common/10` 新增 14d 節＋語體表加第五語體）；影音體全量掃描與篩選器修訂再跑**暫不做**（篩選器修訂建議保留在 B4 報告第四節，日後要再挖時可用）；5 條存檔項不再挑選、維持存檔。
- [x] **B 步第三輪（2026-07-25 完成，Fable，獵稀有招式）**——60 篇未讀池（50 一般＋2 超長＋8 短稿）→ [`style-corpus/analysis_B3_fable.md`](style-corpus/analysis_B3_fable.md)。16 組主招＋5 題材特化小招：全篇延伸隱喻（「別人賞煙火」本尊出土，可完整模板化）、場景接力雙關、超長稿「主題辭典＋群像輪唱」（與 B2 長專題是兩種動物）、短稿壓縮公式（金句從逐字稿挖不自己造）等。附兩級增補建議（10 條值得入指南／8 條太個案僅存檔）。⚠️ 抽樣警訊：2026 語料混入 AI 輔助產出稿（0622-2 留有產稿模板痕跡），萃取人味時應降權（已記入 style-corpus README 與指南維護註記）。**已決定（2026-07-25）**：10 條建議項全數入指南；8 條個案由使用者親選 6 條「其實是常用招」一併升級（諧音替字、辣個男人、迷因指標、判斷前置稿頭、文學典故盲盒、拆字頓挫排版），反向成全反諷留提醒、自鑄詞維持存檔——全部寫入 `common/10` 第 14 節「稀有招式庫」。
- [x] **B 步第二輪（2026-07-24 完成，Fable）**——再讀 50 篇（40 一般＋10 長篇專題，排除第一輪）→ [`style-corpus/analysis_B2_fable.md`](style-corpus/analysis_B2_fable.md)。B1 九組結論 7 成立 2 修正（比喻開關判準改為「有無死亡悲劇」而非題材類別；「不用疑問句」限縮於稿頭層級）。新發現：設問引擎（正文每篇 1–3 個自問自答）、長篇專題六條模板（問題清單骨架/四層推軌/專家SB三連發等）、雙關隱藏簽名（諧音改字+物件雙關回扣收尾）。新增 2 點規則張力待裁定（專家 SB 連發 vs SOT 模板、問號不可被 14 字斷行切開）。
- [x] **B 步：抽樣質性分析（2026-07-24 完成，由 Fable 模型執行）**——[`style-corpus/sample_for_B.py`](style-corpus/sample_for_B.py) 抽 50 篇（`sample_B/` 5 批）→ Fable 產出 [`style-corpus/analysis_B_fable.md`](style-corpus/analysis_B_fable.md)。三大核心發現：①情緒外包紀律（情緒由 SB 承載，OS 只做動作白描＋一句 15–25 字人性註腳）；②比喻有題材開關（戲謔比喻只開在武器/體育/政治攻防稿，人道災難稿比喻歸零）；③收尾即簽名（末句固定為不含新事實的 12–30 字判斷/展望句）。含 8 層面模式+原句證據+可操作指引、「不要學的東西」、「與現行規則的張力」（4 點，待使用者裁定）、一頁式生成檢核表。
- [x] **產出（2026-07-24 完成）**：[`common/10-寫稿風格指南.md`](common/10-寫稿風格指南.md)——合成 A+B1+B2 為 13 節可操作指南（語體判定/稿頭四型/敘事節奏/比喻死亡開關/情緒外包/簽名層額度/標題/收尾/長篇專題/內幕改寫/用字/檢核表/待裁定張力）。已接進寫稿流程：`cnn/01` 與 `common/06` 的「開始前必讀」各加「寫稿階段另讀 10」指引，定位為風格參照層、格式規則優先。
- [x] **6 點規則張力已裁定（2026-07-24，逐點問答）**：①先成句後切行（14字上限不變，只改產生方式）②BAR雙軌並行（長版18–22不進完成文稿本體，驗證器只驗壓縮版）③鉤子優先明文化（A型可到180字接受WARN，絕不砍鉤子）④驚嘆號留指南軟約束（不進驗證器）⑤長專題另立模板（明確下令才套用，豁免SB連發與120秒；common/06 新增專節）⑥設問句指南層斷行保護（≤14字整句一行，不動驗證器）。全部落實於 `common/10` 第13節裁定表＋`cnn/01`＋`common/06`。
- [x] **語料個資／憑證清除（2026-07-25 完成，commit `ffda02f`）**——實際規模比 B2 回報嚴重：不只教授分機，而是**歐新社（EPA）與 TVBS 數位帳號的帳密明文**被當頁尾樣板貼進 401 篇稿件。已用 [`style-corpus/redact_secrets.py`](style-corpus/redact_secrets.py) 兩階段清除（①錨定「標籤＋值」行 ②嵌在 markdown 連結內的帳號信箱／裸帳號 token），範圍涵蓋 `raw/` 401 檔、`cleaned/` 401 檔、`sample_B`～`B4` 14 檔、`draft_corpus.jsonl` 336 筆，共 819 檔，值改為 `[已移除]`、標籤保留可稽核。11 項單元測試確認新聞內文提到「帳號／密碼」者零誤刪，公開網址與外部信箱保留。機密字串清單移至 gitignored 的 `style-corpus/.secret-tokens.txt`，腳本本身不含真實憑證。
- [ ] **實戰驗證迴圈（進行中）**：首篇實驗已完成（2026-07-24）——`魚群暴斃1600` 依風格指南改寫另存 `完成文稿-風格改寫.txt`＋`網路標.txt`（BAR長版，裁定②雙軌）於雲端 `CTV自動寫稿測試\魚群暴斃1600\`，驗證 `--mode ctv` 全過；套用手法：先成句後切行、設問×2、對照句簽名、SB前後橋、比喻半開、21字判斷句收尾、鉤子優先稿頭。**待使用者改稿回饋**→走 auto-script-learning 校稿機制比對，才算完成第一輪驗證。原完成文稿未動（P-010）。
- [ ] `Note`（CG 文字稿）欄位目前只原樣保留在 `draft_corpus.jsonl` 裡，尚未使用；未來若要做 CG 文字風格研究可另外處理。

以上不影響現有字數/格式規則（`P-001`~`P-021`），純粹是額外的風格參照層，見 [`style-corpus/README.md`](style-corpus/README.md)。**使用者明確要求：等他說「開始」再動手，現在只記錄不執行。**

## `.git` 肥大清理（2026-07-24 規劃，暫緩執行）

> 💡 **2026-07-25 註**：上方資安項的「改寫歷史移除舊憑證」與本節都需要 `git filter-repo` 改寫全部歷史。真的要動手時**兩件事一起做**（同一次 filter-repo 同時 `--invert-paths` 剔除肥大路徑、並用 `--replace-text` 抹掉憑證字串），只承受一次 hash 變更與 force-push 的代價。

- [ ] 用 `git filter-repo` 從全部歷史（所有分支含 `agent/rules-v2-sandbox`）剔除三個已棄用的舊路徑：`.tmp-sot/`（141MB whisper 模型 `ggml-base.en.bin`）、`.tmp-yt-dlp/`（83MB `ffmpeg-win-x86_64-v7.1.exe` 及整包 vendored yt-dlp）、`downloads/`（幾支測試下載的 mp4）。三者皆已被 `.gitignore` 排除、現在的 tracked 樹裡完全不存在，純粹是歷史包袱。
- [ ] 指令：`git filter-repo --path .tmp-sot/ --path .tmp-yt-dlp/ --path downloads/ --invert-paths --force`（`git-filter-repo` 已裝好，2026-07-24 用 `pip install git-filter-repo`）。
- [ ] 執行前已做好完整 mirror 備份：`E:\GitHub\TVBS-AIHunter-backup-20260724.git`（198MB，含所有 refs，改壞可從這裡復原）。
- [ ] **會改寫全部 commit hash**，之後必須 force-push 才能同步回 GitHub；GitHub 上已合併完的舊分支（`agent/add-bite-and-batch-rules` 等）建議一併刪除，否則會繼續留著舊肥大 blob 抵銷清理效果。
- [ ] force-push 後，Mac 那台 clone 的 `git pull --ff-only` 自動化 hook 會失效，需要在 Mac 上重新 clone 或手動 reset 到新歷史。
- [ ] 使用者 2026-07-24 裁決：先不動手，列入 TODO 待之後再決定執行時機。

## 已完成

- [x] **DVIDS 也要抓文稿**（2026-07-24 完成）：已在 [`reuters/05-batch-download.md`](reuters/05-batch-download.md) 補 DVIDS 來源分派與處理細節（影片本體 `yt-dlp`＋詳情頁 `get_page_text` 抓文稿、欄位清單、B-Roll 拍攝日非當日的提醒），並在 [`common/05-material-numbering.md`](common/05-material-numbering.md) 補 DVIDS URL 的編號歸屬。
