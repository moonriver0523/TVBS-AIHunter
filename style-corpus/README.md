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
- **閱讀狀態標籤**：`tag_unread.py` → `reading_status.json`——全部 1701 篇的 `B1`～`B6`／`unread` 標記＋`quality` 品質標記。**已讀 286 篇**（B1 50＋B2 50＋B3 60＋B4 40＋B5 44＋B6 42），可用未讀池 **1347 篇**。**日後補抽一律從 `status=unread` 且 `quality=ok` 取樣，不會重讀。**
- **B5（2026-07-26，Opus，篩選器 v2）**：`screen_for_B5.py` → `sample_B5/` 44 篇 → `analysis_B5.md`。12 新招＋24 變體；**推翻 B4 三項結論**（第五語體判定、ellipsis 最佳訊號、命中率指標本身）。
- **B6（2026-07-27，Opus，題材覆蓋抽樣）**：`sample_for_B6.py` → `sample_B6/` 43 篇 → `analysis_B6.md`。23 題材專屬招＋4 項硬修正。**方法改變原因**：B5 證實訊號→招式精準度僅 9%，而 B4/B5 分歧證明**題材組成才是決定找到什麼招的主因**；前五輪 53% 集中在戰爭＋政治。
  - ⚠️ **方法檢討**：關鍵字題材分類錯誤率偏高（醫療健康 6 篇僅 1 篇正確），有效樣本 43→38 篇。下輪若沿用需改進分類法。
- **B3（獵稀有招式，2026-07-25）**：`sample_for_B_round3.py` → `sample_B3/` 60 篇（50 一般＋2 超長＋8 短稿，全部來自未讀池）→ `analysis_B3_fable.md`（16 主招＋5 題材小招）。使用者親自勾選後，10 條建議項＋6 條「其實是常用招」已增補進 [`../common/10-寫稿風格指南.md`](../common/10-寫稿風格指南.md) 第 14 節；反向成全反諷留「遇到不要錯過」提醒、自鑄詞維持存檔。
- **B4（異常側寫精讀，2026-07-25）**：`screen_for_B4.py` 全量掃描未讀池的風格異常訊號（刪節號/擬聲/疊字/拆字排版/行長離散度等）→ 排名存 `b4_screening.json`（前 200 名）→ 前 40 名進 `sample_B4/` → `analysis_B4_fable.md`。真陽性 28/40，12 條新招，並發現**第五種語體「影音變色強調體」**。篩選器修訂建議（ellipsis 加權、redup/onoma 加專名白名單）留在報告第四節，日後要再挖時可用。

## ⚠️ 語料衛生（B3/B4 發現，2026-07-25 已制度化）

`reading_status.json` 除 `status`（`B1`/`B2`/`B3`/`unread`）外，另有 **`quality`** 對照表，由 `tag_unread.py` 產生：

| 標記 | 意義 | 篇數 |
|---|---|---|
| `ok` | 可用於風格萃取 | 1632 |
| `stub` | 近乎空白樣板（中文字 < 60），只有標題或佔位符 | 63 |
| `practice` | 練習／測試稿（檔名含 TEST／練習／practice） | 3 |
| `ai_assisted` | 含 AI 產稿模板痕跡（【主播稿頭】【總長度】等），2026 語料已混入 AI 輔助產出 | 3 |

**抽樣鐵則：一律只取 `status == "unread"` 且 `quality == "ok"` 的稿件**（可用未讀池 1473 篇）。`screen_for_B4.py` 已內建此過濾；日後新增抽樣腳本必須沿用，否則會把練習稿與 AI 產出當成人味樣本學。
