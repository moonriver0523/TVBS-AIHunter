# TVBS-AIHunter

外電（路透社 Reuters Connect / CNN Newsource）相關的自動化流程規則庫，供 Claude 或其他 AI 助手在處理外電素材時遵循。

## 目錄

### Reuters Connect
- [`reuters/01-search-workflow.md`](reuters/01-search-workflow.md) — **搜尋外電素材(RT)**：依 Edit No. 或關鍵字在 Reuters Connect 找到對應素材頁面
- [`reuters/02-wire-intake-summary.md`](reuters/02-wire-intake-summary.md) — **外電掃帶入庫(文稿摘要)**：文字摘要入庫並建立 Notion 頁面（不下載影片）
- [`reuters/03-auto-clip-so.md`](reuters/03-auto-clip-so.md) — **自動掐SO(RT)**：依引言找 TC、下載影片、剪片、上傳
- [`reuters/04-designated-clip-bite.md`](reuters/04-designated-clip-bite.md) — **指定掐Bite**：從既有素材或使用者貼上的原始文稿找 Bite TC，直接輸出雙語逐字
- [`reuters/05-batch-download.md`](reuters/05-batch-download.md) — **外電批次下載(RT)**：依清單批次搜尋 Reuters 素材、核對限制、整支下載、改名並上傳共用

### CNN Newsource
- [`cnn/01-auto-script-writing.md`](cnn/01-auto-script-writing.md) — **自動寫稿(CTV)**：依 Story ID 找官方完整稿、下載影片、比對TC、寫出台灣播出格式完成文稿
- [`cnn/02-clip-bite.md`](cnn/02-clip-bite.md) — **CNN掐Bite**：用 `video_analyze` 為無 TC 的 CNN／AP 官方文稿補上句子級 Bite TC

## 共用慣例
- 上傳目的地固定為 Google Drive `Claude共用` 資料夾（`G:\我的雲端硬碟\Claude共用\`）
- 影片下載預設路徑：`D:\Downloads`
- 版權注意：文字摘要/完成文稿一律為原創改寫，僅逐字引用簡短、明確標示來源的 BITE/SB 引言；不逐字複製整篇外電稿件
- 台灣慣用譯名與單位換算規則見各流程文件內文
