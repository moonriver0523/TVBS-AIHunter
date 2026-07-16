# TVBS-AIHunter

外電（路透社 Reuters Connect / AP Newsroom / CNN Newsource）相關的自動化流程規則庫，供 Claude 或其他 AI 助手在處理外電素材時遵循。

## 目錄

### Reuters Connect
- [`reuters/01-search-workflow.md`](reuters/01-search-workflow.md) — **搜尋外電素材(RT)**：依 Edit No. 或關鍵字在 Reuters Connect 找到對應素材頁面
- [`reuters/02-wire-intake-summary.md`](reuters/02-wire-intake-summary.md) — **外電掃帶入庫(文稿摘要)**：文字摘要入庫並建立 Notion 頁面（不下載影片）
- [`reuters/03-auto-clip-so.md`](reuters/03-auto-clip-so.md) — **自動掐SO(RT)**：依引言找 TC、下載影片、剪片、上傳
- [`reuters/04-designated-clip-bite.md`](reuters/04-designated-clip-bite.md) — **指定掐Bite**：從既有素材或使用者貼上的原始文稿找 Bite TC，直接輸出雙語逐字
- [`reuters/05-batch-download.md`](reuters/05-batch-download.md) — **外電批次下載**：接[`素材編號`](common/05-material-numbering.md)清單，依代碼跨來源分派（RT/AP/CNN Newsource/YouTube/X）批次下載、核對限制、存文稿、改名並上傳共用

### AP Newsroom
- [`ap/01-search-workflow.md`](ap/01-search-workflow.md) — **搜尋外電素材(AP)**：依純數字編號或關鍵字在 AP Newsroom 找到對應影片素材頁面
- [`ap/02-photo-search.md`](ap/02-photo-search.md) — **找AP照片**：依自然語言描述自生關鍵字，搜尋並下載最新最相關的照片

### CNN Newsource
- [`cnn/01-auto-script-writing.md`](cnn/01-auto-script-writing.md) — **自動寫稿(CTV)**：依 Story ID 找官方完整稿、下載影片、比對TC、寫出台灣播出格式完成文稿
- [`cnn/02-clip-bite.md`](cnn/02-clip-bite.md) — **CNN掐Bite**：用 `video_analyze` 為無 TC 的 CNN／AP 官方文稿補上句子級 Bite TC

### 跨來源共用流程
- [`common/05-material-numbering.md`](common/05-material-numbering.md) — **素材編號**：在素材清單裡找出 AP/RT/RTV/ENEX/ABC/IN-XX/YouTube/X 等素材代碼並依序編號
- [`common/06-auto-script-sot.md`](common/06-auto-script-sot.md) — **自動寫稿(SOT)**：接續外電批次下載結果，寫成台灣電視新聞稿（稿頭/標題/次標題/OS+畫面/BITE/總長度/譯名），需使用者明確下令才啟動

## 共用慣例
- 上傳目的地固定為 Google Drive `Claude共用` 資料夾（`G:\我的雲端硬碟\Claude共用\`）；跨來源批次下載會在其下建立以 SLUG 命名的子資料夾
- 影片下載預設路徑：`D:\Downloads`
- 版權注意：文字摘要/完成文稿一律為原創改寫，僅逐字引用簡短、明確標示來源的 BITE/SB 引言；不逐字複製整篇外電稿件
- 台灣慣用譯名與單位換算規則見各流程文件內文
