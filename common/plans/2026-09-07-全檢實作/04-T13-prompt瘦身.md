# T13 掃帶 prompt 瘦身 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans。文字搬移＋改寫，含一個可選的 launcher 小改。**Task 1 沒做完不准動 Task 2**——先搬家再拆屋。

**Goal:** `scripts/s2_scan_prompt.md` 從約 22,500 字元瘦到 ≤8,000，只留本輪參數與指路；prompt 裡**只有 prompt 才有**的規則先逐字搬進規則檔。

**Architecture:** 三步：①盤點 prompt 每一節在規則檔有沒有對應（0907 已初盤，見 Task 1 表）②沒有的搬進去③重寫 prompt。規則檔改動只在改規則空窗做；prompt 檔本身每輪開跑才讀，改完下一輪生效。

**Tech Stack:** Markdown、`s2_rules_check.py`、`s2_scan.ps1`（可選 `{SITES}` 代換）。

## Global Constraints

- 搬進規則的段落**逐字**，只加「（2026-09-07 自 prompt 搬入，T13）」。
- prompt 刪掉的每一段都要能在 Task 1 表裡指到一個規則檔 §；指不到就不能刪。
- 檔尾 `V5-FORK-BASE`／`V7-FORK-BASE` 兩段註解**保留**（switch 腳本靠它）。
- 不動 `{CHECKPOINT}` 佔位符（launcher 代換）。
- 做完 `cp` 一份到 `s2_scan_prompt_v7.md`（T8 Task 3 的快照制）。

---

### Task 1: 盤點並搬家（規則端）

**Files:**
- Read: `scripts/s2_scan_prompt.md`
- Modify: `common/13c2-S2-定時掃帶-v3省token-下.md`（§2a、§5、新增 §6）
- Modify: `common/13c-S2-定時掃帶-v3省token.md`（§0）

0907 盤點結果（`grep -lE` 對八份規則）：

| prompt 節 | 規則檔對應 | 處置 |
|---|---|---|
| 🔴 不准轉包子代理（Agent／Task 工具） | **無** | 搬 → `13c2` §5 防卡新增第 10 條（逐字） |
| 第一件事：重讀規則＋清單 | `13c2` §5 第 1 條只寫 resume；清單本來就是 prompt 的事 | prompt 保留**清單＋一行 rules_check** |
| 讀完驗證截斷／RULES-EOF | 八份檔尾都有標記；規則裡沒寫「怎麼驗」 | 搬 → `13c2` §5 新增第 11 條（三小步） |
| D9 提醒（查詢走子指令、Write 寫 json） | `13c2` §2 標題、`13d` §10／§11 | prompt 只留一行指路 |
| 上一輪整站失守先補掃 | `13d`／`13g`／`13h` 各有片段，無總則 | 搬 → `13c2` §5 新增第 12 條 |
| 本輪參數（checkpoint 寫法／窗／順序／ENEX、ABC 輪次） | 順序 `13c` §0、輪次 `13g` V5-1／`13h` V7-1、set-top 時序 `13f` | prompt 保留 checkpoint＋窗兩句；輪次表**刪**，改指路（或 Task 3 由 launcher 注入） |
| 建檔輪判定（17:00、兩個旁證、window_start、機動格） | `13c2` §5a 全有 | prompt 留一句指路 |
| 三站登入態表（憑證／效期） | 分散 `13c` §1a 各站、`13g` V5-2、`13h` V7-2 | 搬總表 → `13c` §0 白名單之後（逐字） |
| 登出處置（needs-review 跳站、不登入、NS 逾時 2 次） | `13c2` §5 第 6 條半夜禁問、`13c2:387` AP /home | 搬「NS 逾時 2 次」句 → `13c2` §5 第 9 條之後 |
| 收工前必做 0–7 步 | 分散：`13c2` §2a-2／§3b、`13f` T/C 時序、`13g` V5-5、`13h` V7-5、`13` 待整併 | **新增 `13c2` §6 收工清單總表**（一張表、每步指路，不重抄內文） |
| 逐則判斷重大（前三名 set-alert／🟡／patch-entry／只加不撤／涉臺保底） | 🔴🟡 判準、涉臺 `13e` L77–95；`patch-entry` `13c2` §2；「只加不撤」**無** | 搬「排程輪只加不撤、`--alert none` 與降級只有使用者口令才做」→ `13c2` §2a 口令表下方 |
| 卡住時（taskkill／AskUserQuestion／轉包） | `13c2` §5 第 4、6 條 | prompt 留三行指路 |
| 回報格式 | 無（本來就是 prompt 的事） | 保留 |

- [ ] **Step 1: 確認空窗**（README checklist）。

- [ ] **Step 2: `13c2` §5 加三條**（第 10 不准轉包／第 11 讀完驗 RULES-EOF／第 12 上一輪整站失守先補掃），文字**逐字**取自 prompt 對應段，各段末加「（2026-09-07 自 prompt 搬入，T13）」。

- [ ] **Step 3: `13c2` §2a 加「排程輪只加不撤」**，逐字取自 prompt「⛔ 排程輪只加不撤…所以規則要寫明」。

- [ ] **Step 4: `13c` §0 加登入態總表**（NS／RT／AP／ENEX／ABC 五列＋「發現登出 → needs-review 跳站、不登入」兩句），逐字取自 prompt。

- [ ] **Step 5: `13c2` 新增 §6 收工清單**（放在 §5c 之後、附錄之前）：

  | 步 | 動作 | 規則出處 |
  |---|---|---|
  | 0 | `s2_apply_reclass.py --dry-run`→套用；`s2_mark_ingested.py --apply` | `13` 待整併／`13c2` §2a |
  | 1 | 三站清單快照落 scratch | `13c2` §2a-2 |
  | 2 | `s2_audit.py --mmdd … --rt-list --ap-list --ns-list`；ENEX／ABC 走 `s2_platform_reconcile.py` | `13c2` §2a-2／`13g` V5-5／`13h` V7-5 |
  | 3 | 稽核嚴重級處理或 needs-review | `13c2` §2a-2 |
  | 4 | 逐則判重大：`set-alert`（前三）／`patch-entry --alert`；涉臺至少 🟡 | `13e` 重大提醒行 |
  | 4.5／4.6 | ENEX／ABC platform 三件套（`--in-round`）＋ `set-tc` | `13g` V5-3／`13h` V7-3 |
  | 5 | `s2_topic_review.py --compact` 看整張表、`set-category --pairs` 合併 | `13c2` §3b |
  | 5.5 | `set-top checkpoint {CHECKPOINT}` → `set-tc` → `render` 順序鐵律 | `13f` T/C 時序 |
  | 6 | `s2_render.py`，看收工閘門喊什麼 | `13c2` §3 |
  | 7 | 關瀏覽器前摸 NS landing ＋ ABC cmspage（硬性） | `13h` V7-5 |

  表下加一句：「本表只指路，各步細節看出處；prompt 不再重抄」。

- [ ] **Step 6: 驗證規則端**
  ```bash
  python scripts/s2_rules_check.py; echo exit=$?
  grep -nE "自 prompt 搬入" common/13c-S2-定時掃帶-v3省token.md common/13c2-S2-定時掃帶-v3省token-下.md | wc -l
  ```
  Expected: exit=0（`13c2` 若逼近 28,000 字元預算，把 §6 表改放 `13f` 尾——rules_check 會告訴你）；搬入標記 ≥5 處。

- [ ] **Step 7: commit 規則端（獨立 commit）**
  ```bash
  git add common/13c-S2-定時掃帶-v3省token.md common/13c2-S2-定時掃帶-v3省token-下.md
  git commit -m "全檢/T13①：prompt 獨有規則搬入 13c §0／13c2 §2a §5 §6"
  git push origin main
  ```
  跑**一個正式輪**確認無異常後再進 Task 2。

### Task 2: 重寫 prompt

**Files:**
- Modify: `scripts/s2_scan_prompt.md`
- Modify: `scripts/s2_scan_prompt_v7.md`（cp 快照）

- [ ] **Step 1: 備份**
  ```bash
  cp scripts/s2_scan_prompt.md scripts/_s2_scan_prompt_v7_pre-T13.bak.md
  ```

- [ ] **Step 2: 依下列骨架重寫**（每節字數上限是硬的）：

  1. **身分與 checkpoint**（≤300 字元）：「你是 S2 定時掃帶工作 agent，本輪 checkpoint＝`{CHECKPOINT}`（含日期，不要改）。」
  2. **必讀清單**（≤1,200）：八份路徑＋一句「先跑 `python scripts/s2_rules_check.py`，❌ 就回報不開工；每份讀到 `RULES-EOF` 才算讀完（`13c2` §5 第 11 條）；開工回報附『規則載入：13 ✅／…／13h ✅』」。⛔ 不讀 `13b`。
  3. **本輪參數**（≤1,500）：掃描窗＝狀態檔 `checkpoint` 到現在（`resume` 看）；順序 `13c` §0；「本輪是否掃 ENEX／ABC 看 `13g` V5-1／`13h` V7-1 那張表對照 `{CHECKPOINT}`」（若做了 Task 3 則改成 `{SITES}`）；建檔輪只有 17:00、判定看 `13c2` §5a；`set-top checkpoint` 時機看 `13c2` §6 第 5.5 步。
  4. **開工先看**（≤400）：`resume` 後看 `needs-review` 有無「整站失守」→ `13c2` §5 第 12 條。
  5. **收工**（≤300）：「照 `13c2` §6 收工清單逐步做完，不跳步。」
  6. **卡住時**（≤500）：三條指路（不殺程序／半夜禁問／不轉包 → `13c2` §5 第 4、6、10 條；登出處置 → `13c` §0 登入態表）。
  7. **回報格式**（≤1,000）：照現行「回報（簡短）」節逐字保留。
  8. 檔尾兩段 `FORK-BASE` 註解逐字保留。

  ⛔ 不要在 prompt 裡再寫任何「理由」「實錯案例」——那些都在規則檔。

- [ ] **Step 3: 量尺寸**
  ```bash
  python -X utf8 -c "print(len(open('scripts/s2_scan_prompt.md',encoding='utf-8').read()))"
  ```
  Expected: ≤ 8,000。超過就回頭砍第 3、7 節的重複句，不砍第 2 節。

- [ ] **Step 4: 對照表自檢**
  對 Task 1 表逐列確認：被刪的段在規則檔 `grep` 得到（用該段一句獨特文字）。任何一列 grep 不到 → 停下，回 Task 1 補搬。

- [ ] **Step 5: 快照同步＋launcher dry-run**
  ```bash
  cp scripts/s2_scan_prompt.md scripts/s2_scan_prompt_v7.md
  MSYS_NO_PATHCONV=1 pwsh -NoProfile -File scripts/s2_v7_switch.ps1
  MSYS_NO_PATHCONV=1 pwsh -NoProfile -File scripts/s2_scan.ps1 -WhatIf 2>&1 | head -30   # 若 launcher 沒有 -WhatIf，改看 L421「以下是會送出的 prompt 前 400 字」那段的 dry-run 參數
  ```
  Expected: switch 全 OK；launcher 印出的 prompt 開頭是新版第 1 節。

- [ ] **Step 6: commit**
  ```bash
  git add scripts/s2_scan_prompt.md scripts/s2_scan_prompt_v7.md common/plans/S2-MASTER-追蹤清單.md
  git diff --cached --stat
  git commit -m "全檢/T13②：掃帶 prompt 瘦身 22.5K→≤8K，只留本輪參數與指路"
  git push origin main
  ```
  MASTER `T13` 現況改「🔶2026-09-07 `<hash>` 上線，待 3 連續正式輪驗收」。

### Task 3（可選）: launcher 注入 `{SITES}`

**Files:**
- Modify: `scripts/s2_scan.ps1`（L336 附近 `-replace '\{CHECKPOINT\}'` 旁）

- [ ] **Step 1**: 在 launcher 依 `$Checkpoint` 的 HHMM 算「本輪掃站清單」（01:00／04:30／07:00／17:00／22:00 → `NS → AP → RT → ENEX → ABC`；11:00／20:00 → `NS → AP → RT`），`-replace '\{SITES\}'` 注入；prompt 第 3 節改用 `{SITES}`。
- [ ] **Step 2**: `scripts/test_s2_launcher.ps1` 加兩個案例（17:00 含五站、20:00 只三站）。
- [ ] **Step 3**: 這樣輪次表只剩 `13g`／`13h`＋launcher 一處；未來改輪次不必再碰 prompt。⚠️ 與 `13h` V7-1 表不一致時以**使用者最新裁示**為準並同步兩處。

### Task 4: 驗收（3 連續正式輪）

- [ ] 每輪 transcript：「規則載入」八個 ✅；D9 hook 攔截次數 ≤ 改前（0904 基線每輪 2–3 次）；無新增 `needs-review`。
- [ ] `_token_metrics.jsonl`：`tool_calls` 不高於全檢 §1a 區間；`cache_creation_input_tokens` 較 0905–0906 基線（377k–520k）下降（prompt 少 14K 字元的直接效果）。
- [ ] 通過 → MASTER `T13` 改 ✅；失敗 → `git revert` 兩個 commit（規則端搬入的內容可留，無害）。
