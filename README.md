# TVBS-AIHunter

外電（路透社 Reuters Connect / AP Newsroom / CNN Newsource）相關的自動化流程規則庫，供 Claude 或其他 AI 助手在處理外電素材時遵循。

## 目錄

### Reuters Connect
- [`reuters/01-search-workflow.md`](reuters/01-search-workflow.md) — **搜尋外電素材(RT)**：依 Edit No. 或關鍵字在 Reuters Connect 找到對應素材頁面（省 Token：預設只回標題/Edit No./Restrictions，全文留給下游落檔）
- [`reuters/02-wire-intake-summary.md`](reuters/02-wire-intake-summary.md) — **外電掃帶入庫(文稿摘要)**：文字摘要入庫並建立 Notion 頁面（不下載影片；省 Token：交付以 Notion 為主，對話不雙貼全文）
- [`reuters/03-auto-clip-so.md`](reuters/03-auto-clip-so.md) — **自動掐SO(RT)**：依引言找 TC、下載影片、剪片、上傳（省 Token：transcript-first、只輸出剪輯區間雙語）
- [`reuters/05-batch-download.md`](reuters/05-batch-download.md) — **外電批次下載**：接[`素材編號`](common/05-material-numbering.md)清單，依代碼跨來源分派（RT/AP/CNN Newsource/YouTube/X）批次下載、核對限制、存文稿、改名並上傳共用

### AP Newsroom
- [`ap/01-search-workflow.md`](ap/01-search-workflow.md) — **搜尋外電素材(AP)**：依純數字編號或關鍵字在 AP Newsroom 找到對應影片素材頁面（省 Token：精簡回報、下載只查 `D:\Downloads`）
- [`ap/02-photo-search.md`](ap/02-photo-search.md) — **找AP照片**：依自然語言描述自生關鍵字，搜尋並下載最新最相關的照片（省 Token：列表 ⬇ 直下，無 ⚠️ 不開詳情）

### CNN Newsource
- [`cnn/01-auto-script-writing.md`](cnn/01-auto-script-writing.md) — **自動寫稿(CTV)**：依 Story ID 找官方完整稿、下載影片、只為 SB 定位 TC、寫出台灣播出格式完成文稿（省 Token：官方稿／ASR 落地不重貼、單次 transcription、先抽 SB 再關鍵字定位）
- [`cnn/02-clip-bite.md`](cnn/02-clip-bite.md) — **CNN掐Bite**：用 `video_analyze` 為無 TC 的 CNN／AP 官方文稿補上句子級 Bite TC（省 Token：先選句、單次 ASR、關鍵字 ±5 秒）

### 跨來源共用流程
- [`common/05-material-numbering.md`](common/05-material-numbering.md) — **素材編號**：在素材清單裡找出 AP/RT/RTV/ENEX/ABC/IN-XX/YouTube/X 等素材代碼並依序編號（完整輸出一次；下游禁止重貼）
- [`common/06-auto-script-sot.md`](common/06-auto-script-sot.md) — **自動寫稿(SOT)**：接續外電批次下載結果，寫成台灣電視新聞稿（省 Token：瘦盤點、每片一次 ASR、完成稿落檔、照片列表直下）
- [`common/07-bite-assistant.md`](common/07-bite-assistant.md) — **掐BITE助手**：從編號素材、CNN側錄6碼素材，或本機/雲端既有素材找 Bite TC，直接輸出SB五行雙語逐字，不剪片不上傳
- [`common/auto-script-learning/INDEX.md`](common/auto-script-learning/INDEX.md) — **自動寫稿持續校稿索引**：保存使用者修改稿帶來的規則、成熟度、案例與 Prompt 變更；所有代理執行自動寫稿前必讀
- [`style-corpus/README.md`](style-corpus/README.md) — **風格語料庫**：使用者過去實際寫的 TVBS 國際新聞完成稿（1701 篇 `Draft`），作為未來提升寫稿「人味」的風格參照基礎；不是規則來源，字數/格式仍以上方規則文件為準

### 共用規則（跨 Reuters／CNN 流程）
- [`common/00-寫稿通則.md`](common/00-寫稿通則.md) — **寫稿共用規格**：版權原則、單位換算、寫稿前事實分層、**SB 五行格式與 TC 欄位寫法**（所有輸出 SB 的流程一律以此為準）
- [`common/01-shared-folders.md`](common/01-shared-folders.md) — Claude共用（雙向）／掃帶歐印萬資料夾的位置、優先讀既有雙語逐字稿、大檔案上傳方式、暫定性質
- [`common/02-tc-offset-filename.md`](common/02-tc-offset-filename.md) — 數字檔名＝母帶起始TC offset 的換算規則
- [`common/03-preliminary-analysis.md`](common/03-preliminary-analysis.md) — 長片「初步分析」標準流程（silence掃描＋稀疏取樣畫面，不做完整轉錄；本流程本身即省 Token 設計）
- [`common/04-bilingual-subtitle-qa.md`](common/04-bilingual-subtitle-qa.md) — 混語言影片的雙語字幕品質檢查（抓語音辨識誤判外語的漏洞）
- [`common/08-execution-efficiency.md`](common/08-execution-efficiency.md) — 瀏覽器自動化執行效率（省Token）準則：多用批次工具、少截圖、下載改用檔案系統檢查、統一重試階梯、不重複貼原文/長清單
- [`common/09-known-issues.md`](common/09-known-issues.md) — 特定站台／工具的邊角症狀與解法（**不必每次預讀**，執行中撞到才查；索引在 `08` 底部）

### 工具與入口
- [`AGENTS.md`](AGENTS.md) — AI 代理入口：自動寫稿前的必讀順序與持續校稿機制的責任要求
- [`scripts/validate_sot.py`](scripts/validate_sot.py) — SOT 完成文稿驗證（主標/次標字數、SB 的 TC 有效性、總長度加總）
- [`scripts/slim_whisper_transcript.py`](scripts/slim_whisper_transcript.py) — 精簡 Whisper 轉錄結果
- [`scripts/make_contact_sheet.ps1`](scripts/make_contact_sheet.ps1) — 影片接觸表（非預設分析方式，見 `09-known-issues.md`）

## 共用慣例
- 上傳目的地固定為 Google Drive `Claude共用` 資料夾（`G:\我的雲端硬碟\Claude共用\`，雙向：使用者放入待處理檔案、AI產出也放這裡；舊「Claude上傳」資料夾已停用）。跨來源批次下載會在其下建立以 SLUG 命名的子資料夾，詳見 [`common/01-shared-folders.md`](common/01-shared-folders.md)
- 大檔案（幾十MB以上）上傳優先用本機同步資料夾複製，不要用 Google Drive MCP 的 inline base64 上傳工具
- 影片下載預設路徑：`D:\Downloads`
- 素材查找除 `Claude共用` 外，也要檢查「掃帶歐印萬」資料夾，且優先沿用該資料夾裡既有的逐字稿/雙語對照文件，不重新轉錄
- 數字開頭的檔名一律套用 TC offset 換算，見 [`common/02-tc-offset-filename.md`](common/02-tc-offset-filename.md)
- 版權注意：文字摘要/完成文稿一律為原創改寫，僅逐字引用簡短、明確標示來源的 BITE/SB 引言；不逐字複製整篇外電稿件
- 台灣慣用譯名與單位換算規則見各流程文件內文

## 更新 AI HUNTER

當使用者說「更新 AI HUNTER」（包含全形字母、全形空格或大小寫差異）時，視為明確要求同步本機規則庫：

1. 檢查目前 Git 分支、工作目錄狀態及遠端設定。
2. 從 GitHub 遠端取得最新 repository 狀態。
3. 將本機同步到遠端最新版；不得用強制重設或其他方式覆蓋未提交的本機變更。
4. 若存在未提交變更、分支分歧或合併衝突，保留本機內容並回報阻礙，不自行丟棄或覆寫。
5. 同步成功後重新讀取 `README.md`，以及 `common/`、`reuters/`、`cnn/` 內的最新規則文件，後續工作一律依更新後規則執行。
