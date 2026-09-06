# R20 `s2_audit.py` RT 清單對帳前綴修正（只修不回溯） — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development（先寫失敗測試再修）。使用者 2026-09-07 裁決：**只修、不回溯歷史記錄**。

**Goal:** `reconcile()` 比對 RT 清單快照（站方 Edit No，無 `RT` 前綴）與狀態檔 key（`RT9614`）時正規化前綴，消除「RT 窗內漏收 N 則」假陽性；R2 跨日撞號判斷一併用同一正規化。

**Architecture:** 在 `reconcile()` 內建 `key_of(code)`：`label=="RT"` 且 code 不以 `RT` 開頭 → `"RT"+code`；所有對 `cur` 的成員檢查改用 `key_of`；**顯示仍用原 code**。

**Tech Stack:** Python、既有測試骨架（`scripts/test_s2_batch_prep.py` 的 `check()` 風格）。

## Global Constraints

- 只動 `scripts/s2_audit.py` 的 `reconcile()`；不動 AP／NS 路徑（它們的 code 本來就帶前綴）。
- 不重算 Archive 歷史；只在 `master-detail/R.md` R20 段加一行「過去 RT 漏收數字受此 bug 影響、未重算」。

---

### Task 1: 失敗測試

**Files:**
- Create: `scripts/test_s2_audit_rt_prefix.py`

- [ ] **Step 1: 寫測試**：臨時目錄造 `0999-s2-state.json`（`items` 含 `RT9614`、`RT9700`、`AP1`）與 `rt_list.txt`（每行 `CODE|MM/DD/YYYY HH:MM`：`9614|…`、`9700|…`、`9800|…` 三行、時間都在窗內）；呼叫 `s2_audit.reconcile(st, "0999", rt_list_path, "RT")`（看 L211 簽名，必要時改用 subprocess 跑 `s2_audit.py --mmdd 0999 --rt-list …` 抓 stdout）。
  斷言：漏收只有 `9800` 一則；`9614`／`9700` 不在漏收清單。
- [ ] **Step 2: 跑**：`python -X utf8 scripts/test_s2_audit_rt_prefix.py` → Expected: **FAIL**（現況會報 3 則漏收）。

### Task 2: 修

**Files:**
- Modify: `scripts/s2_audit.py`（L211–320 `reconcile()`）

- [ ] **Step 1**: `cur = set(st["items"])` 之後加
  ```python
  def key_of(code):
      # RT 清單快照是站方 Edit No（無前綴），狀態檔 key 帶 RT（R20，2026-09-07）
      return code if (label != "RT" or str(code).startswith("RT")) else f"RT{code}"
  ```
- [ ] **Step 2**: 逐一把 `code in cur`（L239 `cross_day_seen` 判斷、後段 `inw`／`missing` 計算、`_first_seen_index` 若有）改成 `key_of(code) in cur`。`grep -n "in cur" scripts/s2_audit.py` 確認沒有漏。
- [ ] **Step 3**: 跑測試 → Expected: PASS。
- [ ] **Step 4: 真實資料驗證**（唯讀）
  ```bash
  python -X utf8 scripts/s2_audit.py --mmdd 0906 --rt-list "<0906 scratch 的 rt_list_*.json 或 .txt>" 2>&1 | grep -E "RT"
  ```
  Expected: RT 漏收數由改前的大數字降到個位數；逐一 `s2_state.py get --id RT<code>` 確認剩下的真的不在庫。
- [ ] **Step 5**: 全套測試無新增失敗。

### Task 3: 記錄與 commit

- [ ] `master-detail/R.md` R20 段加一行：「2026-09-07 已修 `<hash>`；歷史『RT 漏收 N』數字未重算（使用者裁決只修不回溯）」。
- [ ] ```bash
  git add scripts/s2_audit.py scripts/test_s2_audit_rt_prefix.py common/plans/S2-MASTER-追蹤清單.md common/plans/master-detail/R.md
  git commit -m "全檢/R20：audit RT 清單對帳補前綴，消除假漏收；只修不回溯"
  git push origin main
  ```
  MASTER `R20` 改 ✅。
- [ ] 下一輪驗收：該輪 `s2_audit.py` 輸出的 RT 漏收數與 agent 逐一核對結果一致（transcript 裡不再出現「其實已入庫」的自證段落）。
