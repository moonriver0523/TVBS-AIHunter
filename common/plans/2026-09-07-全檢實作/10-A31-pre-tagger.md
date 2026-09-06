# A31 pre-tagger：機械預標 T/C、(BITE)、涉臺🟡、150 字、🔖負面 lint — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development。前置：09-A24（掛在 `from-raw` 提示表與 `build`）。

**Goal:** 新模組 `scripts/s2_pretag.py`，純函式、無網路、無 LLM。四個出口：①`from-raw` 提示表多三欄 `T?｜C?｜🇹🇼`；②`build` 把建議放進 batch row 的 `suggest`（不進狀態檔）；③`add-batch` 缺 `tc` 時印該則建議；④`lint(entry, fields)` 對 agent 寫好的素材行做四項檢查（摘要 >150 字／`(BITE)` 與 BITE 段不一致／🔖 但畫面欄只有受訪、連線／機動 T 名稱出現卻沒掛）。

**Architecture:**
- T/C 候選：重用 `scripts/prototype/build_tc_matrix_0821.py::tag_tc()` 的關鍵詞表（透過 `s2_render_matrix._make_tagger()` 取得 patched 版，`UNKNOWN` 就不建議）；補 D15 的軍事國防／英國關鍵詞；來源預設 C 表（13f：YNA→南韓、CNA→新加坡,東南亞、NHK→日本）。
- 涉臺詞表：`臺灣|臺海|國軍|漢光|兩岸|我國|臺北|高雄|台積電|海峽中線|陸委會|國台辦`（可擴充，放模組頂部常數）。
- `(BITE)` 建議：`sb_count>0` 或 `has_sot` 或 entry 有 `▎BITE：`。
- 🔖 負面：`fields.footage` 只含「受訪畫面／記者連線／站立播報／專訪／證詞」類詞而無實拍詞 → 警告（R19 判準）。
- ⛔ **不是 collector**、不寫狀態檔、建議永遠是建議。
- 若 09-A24 尚未上線（沒有 `from-raw` 提示表），Task 3 **跳過 Step 1**，只做 Step 2–4；09 上線後再補 Step 1。

**Tech Stack:** Python；`s2_parse.parse_entry()` 取 fields。

---

### Task 1: 失敗測試

**Files:**
- Create: `scripts/test_s2_pretag.py`

- [ ] 案例：(a) 文本含「漢光演習」→ `taiwan=True`、T 建議含 `軍事國防`、C 含 `臺灣`；(b) YNA 來源、文本講川普關稅→ C 建議 `南韓,美國`；(c) `sb_count=2` 而 entry 寫「無BITE」→ lint 報不一致；(d) 摘要 160 字→ lint 報長度；(e) footage「受訪畫面、記者連線」＋ entry 有 🔖 → lint 報 R19；(f) 機動 T「颱風」active、文本有「颱風」、tc.T 沒有 → lint 報漏掛（可 mock `load_special_t`）。
- [ ] 跑 → FAIL（模組不存在）。

### Task 2: `s2_pretag.py`

**Files:**
- Create: `scripts/s2_pretag.py`

- [ ] `suggest_tc(text, source=None) -> {"T":[…],"C":[…]}`；`taiwan_hit(text) -> list[str]`；`bite_suggest(sb_count, has_sot, entry) -> bool|None`；`lint(entry, sb_count=None, has_sot=None, footage_type=None, tc=None) -> list[str]`（訊息前綴 `📏`／`🎙`／`🔖`／`🌀`）。
- [ ] 關鍵詞表放模組頂部常數，每表附一行註解「只加不改；改字典見 D15」。
- [ ] 測試 PASS。

### Task 3: 掛接四個出口

**Files:**
- Modify: `scripts/s2_batch_prep.py`（`cmd_from_raw` 提示表、`cmd_build`）
- Modify: `scripts/s2_state.py`（`cmd_add_batch`：無 `tc` 時印建議；`fmt_issues` 之後呼叫 `lint`，訊息併入既有「⚠️ 格式待修」段）

- [ ] **Step 1**: 提示表尾加 `T?=政治,財經｜C?=美國｜🇹🇼`（🇹🇼 只在命中時印）。
- [ ] **Step 2**: `build` 每則 `row["suggest"] = {"T":…,"C":…,"taiwan":…,"bite":…}`；`add-batch` 讀到 `suggest` 只用來印，**不存**。
- [ ] **Step 3**: `add-batch` 無 `tc` 的則印一行 `💡 {id} 建議 tc="{T}/{C}"`；有 🇹🇼 且 entry 無 🔴🟡 → 印 `🇹🇼 {id} 涉臺，規則要求至少 🟡（13e）`。
- [ ] **Step 4**: `lint` 訊息走 `report_fmt()` 同一段輸出（只警告不修，13c2 §2「寫入當下就會跑」的既有原則）。
- [ ] **Step 5**: 全套測試 PASS。

### Task 4: 規則（空窗，只加一句）

- [ ] `13f`「怎麼下」段加：「`from-raw` 提示表與 `add-batch` 會印機械建議 `T?/C?`——**它只是起點**，照內容判；建議與你判斷不同時以你為準，不必回報。」
- [ ] `13e` 涉臺段加：「`add-batch` 會用詞表點名涉臺素材（🇹🇼），點到就標 🟡；沒點到不代表不涉臺。」
- [ ] `s2_rules_check.py` exit=0。

### Task 5: 上線與驗收

- [ ] commit：`全檢/A31：pre-tagger（T/C 建議、涉臺、BITE、150 字、🔖 lint）`；push；MASTER `A31` 現況更新，`A20`／`A21`／`A25`／`R19` 各加「牙齒見 A31」。
- [ ] 3 連續正式輪：未標率（render 閘門「N 則沒標」）→ 0；`patch-entry --bite` 事後補標次數 → 0；transcript 無「事後整批重寫 (BITE)」；🔖 誤標 0（人工抽 5 則）。通過 → `A31` ✅。
