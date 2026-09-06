# A35 `s2_token_metrics.py` rule_shas 補 13g／13h — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans。單檔常數修改。

**Goal:** `rule_shas` 記錄的規則指紋補上 `13g`／`13h`，拿掉已退役的 `13b`，讓後續 T13／A26 的每輪驗收看得到規則版本。

**Architecture:** 只改 `RULE_FILES` 字典與其註解；`rule_shas()` 邏輯不動。

**Tech Stack:** Python 3。

## Global Constraints

- 不改輸出 schema（仍是 `{代號: sha12}`），舊 jsonl 相容。
- 不在輪次進行中改（量測器在輪次收工時被 launcher 呼叫）。

---

### Task 1: 修改常數

**Files:**
- Modify: `scripts/s2_token_metrics.py`（L55–66 `RULE_FILES`）

- [ ] **Step 1: 看現況**
  ```bash
  sed -n 50,70p scripts/s2_token_metrics.py
  ```
  Expected: 看到 `'13b': …13b-S2-定時掃帶-v2省token.md` 與 `13`/`13e`/`13f`/`13c`/`13c2`/`13d`，無 `13g`/`13h`。

- [ ] **Step 2: 改字典**
  - 刪 `'13b'` 那行，補註解「13b 2026-08-24 退役，prompt 明文禁讀，不再量測」。
  - 加：
    ```python
    '13g': os.path.join('common', '13g-S2-定時掃帶-v5-四站.md'),
    '13h': os.path.join('common', '13h-S2-定時掃帶-v7-五站.md'),
    ```
  - 註解加一句：「A26 五層合一上線後改成新檔名（見 05-A26 計畫 Task 6）」。

- [ ] **Step 3: dry-run 驗證**
  ```bash
  python -X utf8 scripts/s2_token_metrics.py --checkpoint 0906-2200 --dry-run 2>&1 | grep -A12 rule_shas
  ```
  Expected: 印出的 `rule_shas` 有 `prompt/13/13e/13f/13c/13c2/13d/13g/13h` 九個鍵、無 `13b`；沒有 `FileNotFoundError`。
  ⚠️ `--dry-run` 不寫 `_token_metrics.jsonl`；若它抓錯 session 只是數字不同，不影響本項驗證。

- [ ] **Step 4: 既有測試**
  ```bash
  ls scripts/test_s2_*.py | xargs -I{} python -X utf8 {} 2>&1 | tail -3
  ```
  Expected: 無新增失敗（本檔沒有專屬測試；跑全套只是確認沒把 import 弄壞）。

### Task 2: commit

- [ ] **Step 1**
  ```bash
  git add scripts/s2_token_metrics.py common/plans/S2-MASTER-追蹤清單.md
  git diff --cached --stat
  git commit -m "全檢/A35：token_metrics rule_shas 補 13g/13h、去 13b"
  git push origin main
  ```
  MASTER `A35` 現況改「✅2026-09-07 `<hash>`；下一輪 jsonl 見九鍵即驗收」。

- [ ] **Step 2: 下一輪驗收**
  ```bash
  tail -1 "/g/我的雲端硬碟/Claude共用/自動掃帶系統/S2掃帶log/_token_metrics.jsonl" | python -X utf8 -c "import json,sys;print(sorted(json.loads(sys.stdin.read())['rule_shas']))"
  ```
  Expected: 含 `13g`、`13h`，不含 `13b`。
