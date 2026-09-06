# R21 收斂 agent prompt 改指路 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans。單檔文字修改。

**Goal:** `scripts/s2_reclass_prompt.md` 不再叫收斂 agent 讀已退役的 `13b`；改指現行分檔，並確認「分類收斂」規則在現行檔裡完整。

**Architecture:** 先比對 `13b` 的收斂段與 `13c2` §2a 現行段，缺的先搬（逐字）到 `13c2`，再改 prompt 指路。

**Tech Stack:** Markdown。

## Global Constraints

- 收斂 agent 的「不寫狀態檔、只產建議檔」鐵律一字不動。
- 若需搬內容進 `13c2`，只在改規則空窗做。

---

### Task 1: 比對兩處收斂規則

**Files:**
- Read: `common/13b-S2-定時掃帶-v2省token.md`（L605–635 「分類收斂」段）
- Read: `common/13c2-S2-定時掃帶-v3省token-下.md`（L177–181）

- [ ] **Step 1: 並排看**
  ```bash
  sed -n 605,635p common/13b-S2-定時掃帶-v2省token.md
  sed -n 175,182p common/13c2-S2-定時掃帶-v3省token-下.md
  ```
  Expected: `13c2` 已有「獨立 agent 出建議、掃帶輪只套用／建議檔路徑／`MOVE`／`ORDER` 兩種指令／`s2_apply_reclass.py --dry-run`／不逐則重讀內文」。

- [ ] **Step 2: 判斷缺口**
  `13b` 段裡若有 `13c2` 沒有的**規則句**（不是敘事），逐字搬到 `13c2` L181 之後，加「（2026-09-07 自 13b 搬入，R21）」。0907 初看兩者等價，預期**不需要搬**；若真要搬，只在空窗做並跑 `s2_rules_check.py`。

### Task 2: 改 prompt

**Files:**
- Modify: `scripts/s2_reclass_prompt.md`（L4–9 規則指路段）

- [ ] **Step 1: 替換指路**
  把
  ```
  …\common\13b-S2-定時掃帶-v2省token.md   ← 找「分類收斂」那節
  …\common\13-S2-定時掃帶.md              ← 三層骨架與小分題寫法
  ```
  改成
  ```
  …\common\13c2-S2-定時掃帶-v3省token-下.md  ← §2a「分類收斂」規則（你的職責邊界）
  …\common\13e-S2-素材行與分類規則.md        ← 三層骨架、庫存檔格式、小分題寫法
  …\common\13f-S2-大分類與各站規則.md        ← 大分類清單、歸位通則、中主題命名候選判準、T/C
  ```
  並加一行：「⛔ 不要讀 `13b`——已退役，含被推翻的規則。」
  「⚠️ 本檔不重複規則內容——規則天天在改，`13`／`13b` 才是最新的」那句改成「`13c2`／`13e`／`13f` 才是最新的」。

- [ ] **Step 2: 順手補工具**
  「怎麼看」的三個指令加 `--compact`：`s2_topic_review.py --file … --compact`（T6 已上線的精簡模式）。

- [ ] **Step 3: 驗證**
  ```bash
  grep -n "13b" scripts/s2_reclass_prompt.md
  ```
  Expected: 只剩「不要讀 13b」那一行。

### Task 3: commit

- [ ] **Step 1**
  ```bash
  git add scripts/s2_reclass_prompt.md common/plans/S2-MASTER-追蹤清單.md   # 若 Task 1 有搬內容再加 common/13c2-…
  git diff --cached --stat
  git commit -m "全檢/R21：收斂 agent prompt 改指 13c2/13e/13f，禁讀 13b"
  git push origin main
  ```
  MASTER `R21` 現況改「✅2026-09-07 `<hash>`」。

- [ ] **Step 2: 驗收**
  下次使用者下令跑收斂 agent 時，它的開工回報應列出讀了 `13c2`／`13e`／`13f`，建議檔仍只含 `MOVE`／`ORDER` 行。
