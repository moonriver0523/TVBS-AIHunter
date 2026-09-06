# A24 `from-raw` batch 骨架＋提示表（含 D12 跨批已查標記） — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development。砍呼叫主線第二刀：把 `inspect` 中位 36 次／輪壓到 ≤10，並讓 agent 不再 Write 重打整包 batch（A15）。前置：08-T12 已上線。

**Goal:** 新子指令 `s2_batch_prep.py from-raw`：讀站方 detail raw ＋ 狀態檔，一次產出 ①**提示表**（每則一行：id｜時長｜sb｜標題｜正文前 150 字，分頁不超 28K）②**骨架 JSON**（機械欄位全填好、`entry`／`category`／`tc` 留空）③**已在庫標記**（D12：狀態檔已有且非 pending／prelim 的 id 直接排除並列出，pending／prelim 一律保留）。agent 只 Write 一份**極小的** `{id: {entry, category, tc}}`，`build --skeleton` 合併成 batch。

**Architecture:** 純機械；不碰站方 API（不是 ❌ 的固定 collector）；讀狀態檔用 `s2_state.load()`（唯讀）。

**Tech Stack:** Python；測試比照 `test_s2_batch_prep.py`。

## Global Constraints

- `SITE_SPEC` 三站 adapter 沿用（ns／ap／rt），欄位名以 13c 為準。
- 提示表每頁 ≤ `INSPECT_TEXT_BUDGET`（28,000）；超過自動分頁 `--page N`。
- pending／prelim／early 狀態**永遠不排除**（D12 風險條款）。
- 骨架檔寫到 scratch dir（D7 規則），檔名 `{site}_skeleton_{HHMM}.json`。

---

### Task 1: 失敗測試

**Files:**
- Create: `scripts/test_s2_from_raw.py`

- [ ] **Step 1**: 造 AP raw 4 則（其中 1 則 `prelim:true`）、狀態檔已有其中 2 則（一則 `has_script`、一則就是那個 prelim 的 `pending`）。
  斷言：骨架含 3 則（排除已在庫 has_script 那則；pending 的保留並標 `prev_status:"pending"`）；stdout 提示表 3 行、含「已在庫略過 1 則：AP…」；每則骨架含 `id/source/checkpoint/status/src_text/sb_count/has_sot` 與空 `entry/category/tc`。
- [ ] **Step 2**: `build --site ap --raw … --skeleton skel.json --entries mini.json --checkpoint …`：mini 只有 `{id:{entry,category,tc}}` → batch 三鍵齊。
- [ ] **Step 3**: 跑 → FAIL（子指令不存在）。

### Task 2: `from-raw`

**Files:**
- Modify: `scripts/s2_batch_prep.py`（新增 `cmd_from_raw`、`main()` 加 parser；`cmd_build` 加 `--skeleton`）

- [ ] **Step 1**: `cmd_from_raw(args)`：
  - `items = dedup_by_id(spec, _load_raw_any(args.raw)[0])`。
  - `--state` 有給就 `s2_state.load()`，`have = {id: script_status}`；排除 `have.get(id) == "has_script"`，其餘保留並帶 `prev_status`。
  - 骨架每則：`id/source/checkpoint/status/src_text` ＋ `spec['extra_of']`，加 `entry:""`、`category:""`、`tc:""`、`hint:{head, dur, sb_count, first150}`（`first150` 取 `src_text` 正文前 150 字，去換行）。
  - 提示表 stdout：`#序｜id｜dur｜sb｜head｜first150`，累計字元逼近 28,000 就停並印「— 第 1/N 頁，`--page 2` 看下一頁 —」。
  - 尾行：`已在庫略過 K 則：…`／`pending 保留 M 則：…`／`骨架已寫 <path>（N 則）`。
- [ ] **Step 2**: `cmd_build` 加 `--skeleton <path>`：有給就以骨架為底，`--entries` 的 `{id: {entry, category, tc, status?}}` 合併覆蓋；缺 entry 的 id 列入「未填」警告、不進 batch。
- [ ] **Step 3**: `main()`：`from-raw --site --raw --checkpoint [--state] [--out] [--page]`。
- [ ] **Step 4**: 測試 PASS；全套無新增失敗。

### Task 3: 規則與 prompt（空窗）

- [ ] `13d` §4（或 V8 後的對應節）加：「掃完一站先 `from-raw`，看提示表寫 entries，**不要逐則 `inspect`**；`inspect` 只查提示表看不清的疑點（T9 預算制照舊）。」
- [ ] `13c2` §2 `add-batch` 前加一句：「batch 由 `build --skeleton` 產，agent 只寫 `{id:{entry,category,tc}}`。」
- [ ] `python scripts/s2_rules_check.py` exit=0。

### Task 4: 上線與驗收

- [ ] commit：`全檢/A24：from-raw 骨架＋提示表（含 D12 已在庫標記）；build --skeleton`；push；MASTER `A24`／`D12` 現況更新。
- [ ] 第 1 個正式輪：三站各出現 1 次 `from-raw`；`s2_batch_prep:inspect` ≤10；`Write` 次數 ≤6；無「未填」警告殘留。
- [ ] 3 連續正式輪：`inspect` 中位 ≤10（基線 36）、`output_tokens`／輪較基線（71k–140k）下降。通過 → MASTER `A24` ✅（3a／3b 一起結）、`A15` ✅、`T9` 結案。
