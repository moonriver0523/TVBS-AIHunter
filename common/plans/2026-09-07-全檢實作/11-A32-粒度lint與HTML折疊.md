# A32 中主題粒度 lint（只印）＋ HTML 巨格折疊 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development。D17 裁決：**txt 一字不動**，只改 `s2_topic_review.py` 輸出與 `s2_render_html.py` 前端。獨立於 T12／A24，可平行。

**Goal:** ①`s2_topic_review.py` 新增「📐 粒度」區：巨格拆分候選、類別詞命名警告、孤兒合併候選；②網頁版中主題 ≥8 則預設折疊（🔴🟡🔖 與前 3 則展開，其餘「＋N 則」），中主題內 🔴→🟡→🔖→其餘排序（**只在 HTML**）。

**Architecture:** lint 全在 `collect()` 產出的 tree 上算，沿用 `R._lcs_len`；門檻常數放檔頭，D-d 裁決值：`BIG_N=8`、`SPREAD=0.6`、`CATEGORY_WORDS=[體壇,治安,趣聞,軟性,政情,司法案件,民生,生活服務]`（⚠️ 上線前用 0905／0906 狀態檔的全部中主題名跑一次，誤殺者刪；「動態」「議題」「新聞」「外交」等過寬詞**不收**——【川普動態】【俄羅斯外交】【國際外交】是事件型或已在巨格規則裡另抓）。HTML 只動 `draw()`／`midText()` 附近的 JS 與一段 CSS。

## Global Constraints

- lint 只印不改（A10 P0 禁令雖已解除，本項仍維持「工具提示、agent 判斷」）。
- `--compact` 模式只印計數＋前 5 筆，控制輸出 < 60 行。
- HTML 折疊狀態不寫 localStorage 以外的地方；「複製整段」功能要複製**全部**素材（含折疊的）。

---

### Task 1: lint 失敗測試

**Files:**
- Create: `scripts/test_s2_topic_review_granularity.py`

- [ ] 合成狀態檔：【國際體壇】12 則／10 個小分題（→巨格＋類別詞）；【尼泊爾洪災】12 則／3 小分題（→不是巨格）；【美網】1 則與【美網戰報】5 則（→孤兒合併候選，共享「美網」）；【川普改湖名】1 則（→孤兒但無候選）。
  斷言 stdout：`📐 巨格候選 1`＋列出國際體壇並附小分題分群；`命名警告 1`；`孤兒合併候選 1：【美網】→【美網戰報】`。
- [ ] 跑 → FAIL。

### Task 2: lint 實作

**Files:**
- Modify: `scripts/s2_topic_review.py`（`main()` 末段新增 `granularity(tree)`）

- [ ] `granularity(tree)`：對每個 `(big, mid)`：`n`、`k=len(subs)`；`n>=BIG_N and k/n>=SPREAD` → 巨格；`any(w in mid for w in CATEGORY_WORDS)` → 命名警告；`n==1` → 對同大分類其他 mid 算 `_lcs_len>=2` 的最佳對象 → 合併候選。
- [ ] 巨格附「拆法建議」：把小分題名兩兩以 `_lcs_len>=2` 連通分群，印 `群1{a,b,c}／群2{…}`（純字面，agent 自己判）。
- [ ] 輸出段標 `📐 粒度（D-d 門檻：孤兒 <30%、巨格 <5）`，末行印今日孤兒率與巨格數對門檻的 ✅／⚠️。
- [ ] 測試 PASS；`python -X utf8 scripts/s2_topic_review.py --file "<0906 狀態檔>" --compact` 跑得動、輸出 < 60 行。

### Task 3: HTML 折疊與排序

**Files:**
- Modify: `scripts/s2_render_html.py`（JS `draw()` L577–700 附近、`midText()`、CSS）

- [ ] **Step 1**: `draw()` 內每個中主題：`its` 依 `alert`（🔴>🟡）→`hilite`（🔖）→原序排序（**只在 DOM**，`rows` 順序不變，複製功能仍用原序）。
- [ ] **Step 2**: `n>=8` 時，超過「alert/hilite 或前 3 則」的項目加 class `fold` 隱藏，中主題標題旁加按鈕 `＋N 則`／`收合`（沿用 `toggle()`）。側欄篩選啟動時（有任何 chip／搜尋）**不折疊**。
- [ ] **Step 3**: `midText()`／`blockText()` 複製時取全部（不受 fold 影響）——寫一個 JS 斷言註解並手動驗證。
- [ ] **Step 4**: `python -X utf8 scripts/s2_render.py --file "<0906 狀態檔>"` 重 render；瀏覽器開 `0906晚班交接.html`：【國際外交】（19 則）預設折疊、按鈕可展開；複製整段含 19 則；txt 檔 `diff` 與改前**零差異**。

### Task 4: 上線與驗收

- [ ] commit：`全檢/A32：topic_review 粒度 lint；HTML 巨格折疊＋重大置頂（txt 不動）`；push；MASTER `A32` 現況更新。
- [ ] 3 個正式輪：transcript 中 agent 對 📐 候選有處置（合併／拆分／明寫不動）；孤兒率、巨格數逐日記進 MASTER `A32` 現況（目標 <30%／<5，不強求一週內達標）。
