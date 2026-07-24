# 風格語料庫（Style Corpus）

來源：`Denis-News-Knowledge-Base` repo 的 `00_Inbox/documents/【Daily Draft】/`（使用者「許岱軒」過去在 TVBS 國際新聞寫的每日稿件，Notion 匯出）。目的：作為未來提升 CTV／SOT 自動寫稿「人味」（語感、節奏、用詞）的風格參照基礎，**不是**規則來源——字數／格式規則仍以 repo 根目錄的 `common/`、`cnn/`、`scripts/validate_sot.py` 為準。

## 目錄結構

- `raw/【Daily Draft】/` — 原始檔案，逐字複製自來源 repo，**未經任何修改**（1728 個 `.md`，44MB，含 3 篇巢狀子頁面）。保留作為稽核與重新萃取的依據。
- `extract_corpus.py` — 清理腳本：去除每篇檔案裡混入的 `¤WA<n> <len> <hex>` 雜訊行（Notion 貼上時夾帶的 MOS/VizRT 素材中繼資料，對風格研究無意義），並依 H3 標題（`### *Materials*`／`### *Draft*`／`### ***Note***` 等）切分區塊。用 `rglob` 遞迴掃描，含子資料夾裡的頁面（例如 `0411專題/`、`專題 美中壓力2100/` 底下的 BITE 子頁）。
- `cleaned/` — 去雜訊後的完整檔案（結構、其餘內容不變，只是拿掉雜訊行），1728 個檔案、24MB，維持與 `raw/` 相同的子資料夾結構。
- `draft_corpus.jsonl` — 主要語料檔：每行一個 JSON 物件 `{file, date_prefix, draft, note}`，只留有實際內容的 `Draft` 區塊（+ 若存在則附上 `Note`／CG 文字稿）。1701 筆（27 篇因 `Draft` 區塊完全空白，屬未填寫的範本檔或空白子頁，已略過）。

## 三種內容的定位（使用者 2026-07-24 訂定）

- **`Materials`** = 素材清單（記者整理的原始外電/畫面/引言筆記），是「讀了什麼」，不是風格語料。
- **`Draft`** = **使用者自己寫的完成稿**（含稿頭、標題選項、正文 NS/SB/CG 交錯的完整播出稿），這是風格研究的核心目標——`draft_corpus.jsonl` 只萃取這個區塊。
- **`Note`**（多數寫作 `***Note***`）= 通常是 CG（跑馬燈/字卡）文字底稿，屬於另一種較短的字卡語域，跟 `Draft` 的敘事語感不同，先原樣保留在 `note` 欄位，暫不併入主語料。

## 分析進度與閱讀狀態

- **A 步（統計）**：`analyze_style_A.py` → `analysis_A_report.md`。
- **B 步（質性，Fable）**：第一輪 `sample_for_B.py` → `sample_B/` 50 篇 → `analysis_B_fable.md`；第二輪 `sample_for_B_round2.py` → `sample_B2/` 50 篇（含 10 篇長篇專題）→ `analysis_B2_fable.md`。第二輪驗證顯示結論已飽和（7 成立/2 修正/0 推翻），B 步收工。
- **閱讀狀態標籤**：`tag_unread.py` → `reading_status.json`——全部 1701 篇的 `B1`/`B2`/`unread` 標記。未讀 1601 篇（<1200 字 367、1200–9000 字 1183、9000–20000 字 49、>20000 字 2）。**日後若需針對性補抽（特定題材/語域），從 `unread` 池取樣即可，不會重讀。**
