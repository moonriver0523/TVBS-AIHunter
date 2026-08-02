# TVBS-AIHunter

外電（路透社 Reuters Connect / AP Newsroom / CNN Newsource）相關的自動化流程規則庫，供 Claude 或其他 AI 助手在處理外電素材時遵循。

> 🗺️ **先看全貌**：[`common/12-子系統地圖.md`](common/12-子系統地圖.md) — 這 26 份規則實際上組成 9 個子系統＋一層共用地基＋一層參考知識。下方目錄仍按「來源」排列（歷史結構），跟子系統邊界是垂直交叉的。

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
- [`common/11-wire-rundown-organizer.md`](common/11-wire-rundown-organizer.md) — **外電稿單整理**：把雜亂的外電候選素材（或只給主題）整理成稿頭+素材代碼+一句話短摘要的稿單，存 txt 供編輯瀏覽決定（新流程，`+`分隔符與「參考」行語意待使用中驗證）
- [`common/05-material-numbering.md`](common/05-material-numbering.md) — **素材編號**：在素材清單裡找出 AP/RT/APcctv/ENEX/ABC/CNN Newsource 組合碼/YouTube/X 等素材代碼並依序編號（`RTV` 正規化為 `RT`）（完整輸出一次；下游禁止重貼）
- [`common/06-auto-script-sot.md`](common/06-auto-script-sot.md) — **自動寫稿(SOT)**：接續外電批次下載結果，寫成台灣電視新聞稿（省 Token：瘦盤點、每片一次 ASR、完成稿落檔、照片列表直下）
- [`common/16-auto-script-junlian.md`](common/16-auto-script-junlian.md) — **自動寫稿(準連)**：`{SLUG}XX準` 短版口播帶（預設 OS+BITE+OS、40~60 秒）；稿頭收交場句、網路標上限 24 字、SB 只有 2 行帶「」不列英文、段落用 `====` 分隔、OS 不逐段標 TC。結構與 SOT／CTV 皆不同，**不可互套**，也不能用 `validate_sot.py` 驗
- [`common/07-bite-assistant.md`](common/07-bite-assistant.md) — **掐BITE助手**：從編號素材、CNN側錄6碼素材，或本機/雲端既有素材找 Bite TC，直接輸出SB五行雙語逐字，不剪片不上傳
- [`common/auto-script-learning/INDEX.md`](common/auto-script-learning/INDEX.md) — **自動寫稿持續校稿索引**：保存使用者修改稿帶來的規則、成熟度、案例與 Prompt 變更；所有代理執行自動寫稿前必讀
- [`common/15-歐印萬掃帶.md`](common/15-歐印萬掃帶.md) — **歐印萬掃帶**：監控「掃帶歐印萬」資料夾、指定/自動翻譯側錄音檔成 TC中文大段翻譯 或 雙語逐字稿全文，存於來源音檔旁（與 S2b 濃縮摘要不同，見文件內說明）
- [`style-corpus/README.md`](style-corpus/README.md) — **風格語料庫**：使用者過去實際寫的 TVBS 國際新聞完成稿（1701 篇 `Draft`），作為未來提升寫稿「人味」的風格參照基礎；不是規則來源，字數/格式仍以上方規則文件為準

### 共用規則（跨 Reuters／CNN 流程）
- [`common/00-寫稿通則.md`](common/00-寫稿通則.md) — **寫稿共用規格**：版權原則、單位換算、寫稿前事實分層、**SB 五行格式與 TC 欄位寫法**（所有輸出 SB 的流程一律以此為準）
- [`common/01-shared-folders.md`](common/01-shared-folders.md) — Claude共用（雙向）／掃帶歐印萬資料夾的位置、優先讀既有雙語逐字稿、大檔案上傳方式、暫定性質
- [`common/02-tc-offset-filename.md`](common/02-tc-offset-filename.md) — 數字檔名＝母帶起始TC offset 的換算規則
- [`common/03-preliminary-analysis.md`](common/03-preliminary-analysis.md) — 長片「初步分析」標準流程（silence掃描＋稀疏取樣畫面，不做完整轉錄；本流程本身即省 Token 設計）
- [`common/04-bilingual-subtitle-qa.md`](common/04-bilingual-subtitle-qa.md) — 混語言影片的雙語字幕品質檢查（抓語音辨識誤判外語的漏洞）
- [`common/08-execution-efficiency.md`](common/08-execution-efficiency.md) — 瀏覽器自動化執行效率（省Token）準則：多用批次工具、少截圖、下載改用檔案系統檢查、統一重試階梯、不重複貼原文/長清單
- [`common/09-known-issues.md`](common/09-known-issues.md) — 特定站台／工具的邊角症狀與解法（**不必每次預讀**，執行中撞到才查；索引在 `08` 底部）
- [`common/10-寫稿風格指南.md`](common/10-寫稿風格指南.md) — **寫稿風格指南（人味層）**：合成自 style-corpus 100 篇人稿分析；稿頭四型、敘事節奏、比喻開關、情緒紀律、簽名層額度、收尾句型、長篇專題結構、生成檢核表。屬風格參照層，與格式規則衝突時以格式規則為準

### 製片產出（Production）— 自動剪片配音上字
> 端到端的最後一段：完成文稿 + 素材影片 → 配音上字成品。**建置中，逐步回填**（首個實測案例：CTV 魚群暴斃1600）。
- [`production/00-overview.md`](production/00-overview.md) — **製片總覽**：在系統中的位置（下載→寫稿→**製片**→成品）、輸入輸出、子流程、前置依賴（os_voice3 待重訓）
- [`production/01-voiceover-os.md`](production/01-voiceover-os.md) — **OS 配音**：GPT-SoVITS 本人聲音配過音（跳過 LEAD/SB）；分組合成、int16 峰值正規化、ASR 覆蓋驗收、弱句換 seed
- [`production/02-video-assembly.md`](production/02-video-assembly.md) — **剪接組裝**：時間軸（OS/SB 交錯）、SB 接點 VAD 精裁、B-roll 不重複、影片配合音訊（不 -shortest）
- [`production/03-subtitle-burn.md`](production/03-subtitle-burn.md) — **上字**：硬字幕 + BAR 下標 + SUPER 名條；ASR 詞級同步、零長度防呆、ASS 燒錄
- [`production/09-known-issues.md`](production/09-known-issues.md) — **製片踩雷與定版流程**（已驗證，做製片前必讀）：int16 爆音、逐句更慘、字幕零長度塌陷、污染判定文字>聲學

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
