# T12 `add-batch` 一次帶 `category`＋`tc` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development。砍呼叫主線第一刀。

**Goal:** batch.json 每則可帶 `category`（`大分類/中主題[/小分題]`）與 `tc`（`T1,T2/C1,C2`），`add-batch` 一次入庫＋分類＋標 T/C；`set-category`／`set-tc` 退為事後修補。順帶消掉 13f 的兩個 T/C 時序陷阱。

**Architecture:**
- `cmd_add_batch()`：每筆 `new_item()` 之後，若有 `category` → `_set_one_category(strict=False, quiet=True)`；若有 `tc` → `_set_one_tc()`（字典與機動 T **每批只載入一次**）。錯誤不擋入庫：素材照收，錯誤彙整印出並寫 `tc_rejected[cp]`。
- `add-batch` 內建的 T/C **不計入 `tc_calls`**（上限是擋逐則呼叫，不是擋批次）。
- `s2_batch_prep build`：entries.json 的值若是物件，`category`／`tc` 兩鍵**原樣帶進** batch row。
- 收尾印同一段「🔴 本檔還有 N 則沒有 T/C」提醒（現在只在 `set-category` 印）。

**Tech Stack:** Python、subprocess 測試（比照 `test_s2_listtopics.py`）。

## Global Constraints

- 舊 batch.json（無這兩鍵）行為完全不變。
- `_set_one_category` 現在會 `print("OK …")`——加 `quiet` 參數，批次時不逐則印。
- 規則檔（`13c2` §2 `add-batch` 說明、`13f`「跟 set-category 同一批下」）只在空窗改，且只加不改寫既有句子。

---

### Task 1: 失敗測試

**Files:**
- Create: `scripts/test_s2_add_batch_tc.py`

- [ ] **Step 1**: 臨時狀態檔（`_top.checkpoint="0999-1700"`，空 items），batch 三則：
  ① 帶 `category:"社會/測試案/子題"`、`tc:"社會/美國"` → 期望 `get --id` 看到兩者；
  ② `tc:"不存在的T/美國"` → 素材入庫、`tc` 缺、stdout 含「不在 TC-字典」、`_top.tc_rejected["0999-1700"]` 有一筆；
  ③ `tc:"政治,社會,財經,體育/美國"` → 入庫、T 超上限退回。
  再斷言 `_top.tc_calls` **沒有** `0999-1700` 鍵（不計次）。
- [ ] **Step 2**: 跑 → Expected: FAIL（現況忽略這兩鍵）。

### Task 2: `s2_state.py`

**Files:**
- Modify: `scripts/s2_state.py`（`cmd_add_batch` L505–593、`_set_one_category` L1519）

- [ ] **Step 1**: `_set_one_category(state, raw_id, cat, strict, quiet=False)`：`quiet` 時不 print。
- [ ] **Step 2**: `cmd_add_batch` 迴圈前：
  ```python
  ok_t, ok_c = _load_tc_dict(); _sp_active, _sp_all = load_special_t()
  ok_t = list(ok_t) + _sp_active; _sp_names = {x.get("name") for x in _sp_all if x.get("name")}
  cat_done, tc_done, tc_bad, rewrites = [], [], [], []
  ```
  迴圈內 `new_item` 之後：
  ```python
  if e.get("category"):
      err = _set_one_category(state, i, str(e["category"]), strict=False, quiet=True)
      (tc_bad if err else cat_done).append(err or i)
  if e.get("tc"):
      err = _set_one_tc(state, i, str(e["tc"]), ok_t, ok_c, rewrites, _sp_names)
      (tc_bad if err else tc_done).append(err or i)
  ```
  結尾：`tc_bad` 非空 → 寫 `top["tc_rejected"][cp]`（沿用 `cmd_set_tc` 的寫法，`top = state.setdefault("_top", {})`）；印「分類 N／T/C M／退回 K」與退回明細；最後複製 `cmd_set_category` 末段「🔴 本檔還有 N 則沒有 T/C」提醒（抽成 `_remind_missing_tc(state)` 兩處共用）。
- [ ] **Step 3**: 跑測試 → PASS；`test_s2_listtopics.py` 等全套無新增失敗。

### Task 3: `s2_batch_prep build` 透傳

**Files:**
- Modify: `scripts/s2_batch_prep.py`（`cmd_build` L289–346）
- Modify: `scripts/test_s2_batch_prep.py`（加一案）

- [ ] **Step 1**: entries 值為 dict 時，`row["category"] = raw_entry.get("category")`、`row["tc"] = raw_entry.get("tc")`（None 就不放鍵）。docstring 的 entries.json 格式說明加這兩鍵。
- [ ] **Step 2**: 測試：entries `{"AP1": {"entry": "…", "category": "社會/x", "tc": "社會/美國"}}` → batch row 含兩鍵；純字串 entries → 不含。
- [ ] **Step 3**: 全套測試 PASS。

### Task 4: 規則文字（空窗）

**Files:**
- Modify: `common/13c2-S2-定時掃帶-v3省token-下.md`（§2 `add-batch` 條目）
- Modify: `common/13f-S2-大分類與各站規則.md`（T／C 標籤「怎麼下」段）

- [ ] **Step 1**: `13c2` §2 `add-batch` 條目後加一行：「（2026-09-07 T12）batch 每則可帶 `category`／`tc`，一次入庫＋分類＋T/C；`set-category`／`set-tc` 只用於事後修補。」
- [ ] **Step 2**: `13f`「怎麼下：跟 set-category 同一批下」段開頭加：「**首選：直接寫在 batch.json 的 `tc` 欄一起 `add-batch`**（T12）；下面的 `set-tc` 是修補用。」兩個時序陷阱段落開頭加一句「用 batch 內建 T/C 時不會發生；仍用 set-tc 才要注意」。
- [ ] **Step 3**: `python scripts/s2_rules_check.py` exit=0。

### Task 5: 上線與驗收

- [ ] commit（`s2_state.py`、`s2_batch_prep.py`、兩個測試、兩份規則、MASTER）：`全檢/T12：add-batch 帶 category+tc，一次入庫`；push。
- [ ] 第 1 個正式輪：transcript 中 batch.json 含 `category`／`tc`；`set-category`＋`set-tc` 合計 ≤2 次；render 覆蓋率閘門不再喊「N 則沒標」。
- [ ] 3 連續正式輪：`_token_metrics.jsonl` 的 `s2_state:set-category`＋`s2_state:set-tc` 合計 ≤2／輪（基線 3–16）。通過 → MASTER `T12` ✅。
- [ ] 失敗回滾：`git revert`；舊 batch 格式仍相容，無資料風險。
