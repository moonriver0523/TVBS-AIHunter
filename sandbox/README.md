> # ⚠️ 沙盒版，尚未生效
>
> 這是規則庫去重／重整後的**測試版本**，還沒有取代線上流程。
>
> - **正式規則仍在 repo 根目錄**（`../common/`、`../reuters/`、`../cnn/`、`../ap/`）——日常任務一律照根目錄那套執行。
> - 本資料夾只在**明確要求「用沙盒規則跑」時**才使用，目的是實測去重後的規則會不會漏掉東西。
> - 測試通過後才會整批取代根目錄；在那之前兩套並存是正常狀態。
> - 學習案例（`auto-script-learning/`）**刻意不複製**，兩套共用根目錄那一份，避免案例分裂成兩份。

# TVBS-AIHunter（沙盒版）

外電（Reuters Connect / AP Newsroom / CNN Newsource）自動化流程規則庫，供 Claude 或其他 AI 助手處理外電素材時遵循。

## 核心檔（幾乎每個任務都會用到）

先讀這幾份，再讀你要執行的那條流程；**流程文件不重述核心檔的內容**：

| 檔案 | 管什麼 |
|---|---|
| [`common/00-寫稿通則.md`](common/00-寫稿通則.md) | 版權原則、單位換算 |
| [`common/01-shared-folders.md`](common/01-shared-folders.md) | Claude共用／掃帶歐印萬的位置、上傳判定、根目錄 vs SLUG 子資料夾 |
| [`common/02-tc-offset-filename.md`](common/02-tc-offset-filename.md) | 數字檔名＝母帶起始 TC offset 的換算 |
| [`common/07-bite-assistant.md`](common/07-bite-assistant.md) | **找 TC 與 SB 五行格式的唯一權威**，兼掐BITE助手流程本身 |
| [`common/08-execution-efficiency.md`](common/08-execution-efficiency.md) | 瀏覽器操作、下載重試階梯、省 Token 預設行為 |

[`common/09-known-issues.md`](common/09-known-issues.md) 是**例外**：邊角症狀與規則由來案例，**執行前不必讀**，撞到問題才查（索引在 `08` 底部）。

## 流程文件

### 跨來源
- [`common/05-material-numbering.md`](common/05-material-numbering.md) — **素材編號**：清單裡的 AP/RT/RTV/ENEX/ABC/IN-XX/YouTube/X/Facebook 依序編號
- [`common/10-batch-download.md`](common/10-batch-download.md) — **外電批次下載**：接編號清單，依代碼跨來源分派下載、存文稿、改名、上傳（**來源分派表在這裡**）
- [`common/06-auto-script-sot.md`](common/06-auto-script-sot.md) — **自動寫稿(SOT)**：接續批次下載結果寫成台灣電視新聞稿
- [`common/03-preliminary-analysis.md`](common/03-preliminary-analysis.md) — 長片「初步分析」標準流程
- [`common/04-bilingual-subtitle-qa.md`](common/04-bilingual-subtitle-qa.md) — 混語言影片的雙語字幕品質檢查

### Reuters Connect
- [`reuters/01-search-workflow.md`](reuters/01-search-workflow.md) — **搜尋外電素材(RT)**（RT 站台操作的唯一權威）
- [`reuters/02-wire-intake-summary.md`](reuters/02-wire-intake-summary.md) — **外電掃帶入庫(文稿摘要)**：不下載影片，建 Notion 頁
- [`reuters/03-auto-clip-so.md`](reuters/03-auto-clip-so.md) — **自動掐SO(RT)**：找 TC、下載、剪片、上傳

### AP Newsroom
- [`ap/01-search-workflow.md`](ap/01-search-workflow.md) — **搜尋外電素材(AP)**（AP 站台操作的唯一權威）
- [`ap/02-photo-search.md`](ap/02-photo-search.md) — **找AP照片**

### CNN Newsource
- [`cnn/01-auto-script-writing.md`](cnn/01-auto-script-writing.md) — **自動寫稿(CTV)**（CNN 站台操作的唯一權威；**只要下載素材就讀步驟 1、2、4**）
- [`cnn/02-clip-bite.md`](cnn/02-clip-bite.md) — **CNN掐Bite**：為無 TC 的官方文稿補句子級 TC

### 入口與工具
- [`AGENTS.md`](AGENTS.md) — AI 代理入口
- [`common/auto-script-learning/INDEX.md`](../common/auto-script-learning/INDEX.md) — 自動寫稿持續校稿索引（**與正式版共用同一份**）
- [`scripts/validate_sot.py`](../scripts/validate_sot.py) — SOT 完成文稿驗證
- [`scripts/slim_whisper_transcript.py`](../scripts/slim_whisper_transcript.py) — 精簡 Whisper 轉錄結果
- [`scripts/make_contact_sheet.ps1`](../scripts/make_contact_sheet.ps1) — 影片接觸表（非預設分析方式）

## 這一版跟正式版的差異

1. **新增** `common/00-寫稿通則.md`（版權原則收斂自 7 處；單位換算從掃帶入庫升為通用，SOT／CTV 也適用）。
2. **`common/07` 升格為找 TC 與 SB 格式的唯一權威**，其他 5 份文件的重複敘述改為連結。
3. **SB 五行格式統一適用所有流程，包含 CTV**（原本 CTV 用 `SB <TC>` 三段、沒有英文原文行）。TC 欄位依來源不同：`#03 0033-0044`／`CNN 060900-060923`／CTV `0006-0013` 不加前綴。**BAR 規則完全未動。**
4. **新增規則**：原始素材 BITE 不足、或有關鍵要點需向觀眾強調時，可插入記者／主播 BITE（適用所有寫稿流程，含原本沒有此規則的 CTV）。
5. **歷史敘事全部移到 `09-known-issues.md` 的「規則由來案例」**，準則檔只留結論。
6. **`reuters/05` 搬成 `common/10-batch-download.md`**（它已是跨來源公版，來源分派表跟著進 `common/`）。
7. 各站台文件的「省 Token 節」只留站台特有條款，與 `08` 重複的部分刪除。
8. **維持不動**：譯名規則、譯名標注格式、TC 三種寫法、四種檔名規則、三套字數上限、三套輸出結構、段落標題標記、各流程交付動作。

## 共用慣例
- 上傳目的地為 Google Drive `Claude共用`（`G:\我的雲端硬碟\Claude共用\`，雙向）。批次類流程建 SLUG 子資料夾，單支交付放根目錄，詳見 [`common/01-shared-folders.md`](common/01-shared-folders.md)
- 大檔案（幾十MB以上）上傳優先用本機同步資料夾複製，不要用 inline base64 上傳
- 影片下載預設路徑 `D:\Downloads`（預設值，未出現時以工具回報路徑為準）
- 素材查找除 `Claude共用` 外也要檢查「掃帶歐印萬」，且優先沿用既有逐字稿，不重新轉錄
- 數字開頭的檔名一律套用 TC offset 換算
- 台灣慣用譯名與標注格式見各流程文件內文（**格式各流程不同，不可互套**）
