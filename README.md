# TVBS-AIHunter

外電（路透社 Reuters Connect / CNN Newsource）相關的自動化流程規則庫，供 Claude 或其他 AI 助手在處理外電素材時遵循。

## 目錄

### Reuters Connect
- [`reuters/01-search-workflow.md`](reuters/01-search-workflow.md) — **搜尋外電素材(RT)**：依 Edit No. 或關鍵字在 Reuters Connect 找到對應素材頁面
- [`reuters/02-wire-intake-summary.md`](reuters/02-wire-intake-summary.md) — **外電掃帶入庫(文稿摘要)**：文字摘要入庫並建立 Notion 頁面（不下載影片）
- [`reuters/03-auto-clip-so.md`](reuters/03-auto-clip-so.md) — **自動掐SO(RT)**：依引言找 TC、下載影片、剪片、上傳

### CNN Newsource
- [`cnn/01-auto-script-writing.md`](cnn/01-auto-script-writing.md) — **自動寫稿(CTV)**：依 Story ID 找官方完整稿、下載影片、比對TC、寫出台灣播出格式完成文稿

### 共用規則（跨 Reuters／CNN 流程）
- [`common/01-shared-folders.md`](common/01-shared-folders.md) — Claude共用（雙向）／掃帶歐印萬資料夾的位置、優先讀既有雙語逐字稿、大檔案上傳方式、暫定性質
- [`common/02-tc-offset-filename.md`](common/02-tc-offset-filename.md) — 數字檔名＝母帶起始TC offset 的換算規則
- [`common/03-preliminary-analysis.md`](common/03-preliminary-analysis.md) — 長片「初步分析」標準流程（silence掃描＋稀疏取樣畫面，不做完整轉錄）
- [`common/04-bilingual-subtitle-qa.md`](common/04-bilingual-subtitle-qa.md) — 混語言影片的雙語字幕品質檢查（抓語音辨識誤判外語的漏洞）

> 註：`指定掐Bite`／`外電批次下載(RT)`／`CNN掐Bite` 三條規則目前在另一個尚未merge的draft PR（`agent/add-bite-and-batch-rules`）分支上，本分支（`agent/sync-gap-rules`）是從main另外切出來補共用規則缺口，兩者尚未合併前，索引暫時不完整。

## 共用慣例
- 上傳目的地固定為 Google Drive `Claude共用` 資料夾（`G:\我的雲端硬碟\Claude共用\`，雙向：使用者丟檔＋Claude產出都放這裡；舊「Claude上傳」資料夾已停用，詳見 [`common/01-shared-folders.md`](common/01-shared-folders.md)）
- 大檔案（幾十MB以上）上傳優先用本機同步資料夾複製，不要用 Google Drive MCP 的 inline base64 上傳工具
- 影片下載預設路徑：`D:\Downloads`
- 素材查找除 `Claude共用` 外，也要檢查「掃帶歐印萬」資料夾，且優先沿用該資料夾裡既有的逐字稿/雙語對照文件，不重新轉錄
- 數字開頭的檔名一律套用 TC offset 換算，見 [`common/02-tc-offset-filename.md`](common/02-tc-offset-filename.md)
- 版權注意：文字摘要/完成文稿一律為原創改寫，僅逐字引用簡短、明確標示來源的 BITE/SB 引言；不逐字複製整篇外電稿件
- 台灣慣用譯名與單位換算規則見各流程文件內文
