# 全檢實作計畫（第一波：純文字低風險組；第二波：砍呼叫與分類治本）

> **For agentic workers:** 每份計畫用 superpowers:executing-plans 逐 Task 執行；步驟是 `- [ ]` 勾選格式。**一次只執行一份**，做完 commit＋push、跑過一個正式輪再開下一份。

- **上位規格**：[`../2026-09-07-S2全面檢視與改進計畫.md`](../2026-09-07-S2全面檢視與改進計畫.md)（全檢）；狀態帳本：[`../S2-MASTER-追蹤清單.md`](../S2-MASTER-追蹤清單.md)。
- **本波範圍**：只改文字檔與兩支腳本的常數，不動狀態檔、不動掃帶邏輯。

## 執行順序（不可調換）

| 序 | 計畫 | MASTER | 難度 | 為什麼在這個位置 |
|---|---|---|---|---|
| 1 | [`01-T8-過期清理.md`](01-T8-過期清理.md) | T8 | 低階可獨立 | 先把三處已知過期敘述清掉，後面兩份才不會搬到錯的內容 |
| 2 | [`02-A35-metrics補13g13h.md`](02-A35-metrics補13g13h.md) | A35 | 低階可獨立 | 一行修；先補齊量測，後面 T13／A26 的驗收才看得到規則指紋 |
| 3 | [`03-R21-收斂prompt改指路.md`](03-R21-收斂prompt改指路.md) | R21 | 低階可獨立 | 獨立、小；順手 |
| 4 | [`04-T13-prompt瘦身.md`](04-T13-prompt瘦身.md) | T13 | 低階可做，**必須在空窗**，Task 1→2 順序不可倒 | 先把 prompt 獨有的規則**搬進規則檔**，再瘦身 prompt |
| 5 | [`05-A26-五層合一.md`](05-A26-五層合一.md) | A26 刀4 擴充 | **中階**：Task 0 取代對照表做完要使用者看一眼放行，才准進 Task 2 | 最大的一刀；T13 搬進去的內容要一起合併，所以排最後 |

## 第二波（使用者 2026-09-07 裁決後寫；前置：第一波 01–04 至少完成到 T13）

| 序 | 計畫 | MASTER | 難度 | 依賴 |
|---|---|---|---|---|
| 6 | [`06-D15-TC字典拆分.md`](06-D15-TC字典拆分.md) | D15 | 低階（空窗改 13f） | 無 |
| 7 | [`07-R20-audit-RT前綴.md`](07-R20-audit-RT前綴.md) | R20 | 低階（TDD） | 無 |
| 8 | [`08-T12-add-batch帶分類與TC.md`](08-T12-add-batch帶分類與TC.md) | T12 | 中（改 s2_state 寫入路徑） | 無 |
| 9 | [`09-A24-from-raw骨架(含D12).md`](09-A24-from-raw骨架(含D12).md) | A24／D12／A15／T9 | 中 | 08 |
| 10 | [`10-A31-pre-tagger.md`](10-A31-pre-tagger.md) | A31 | 中 | 09 |
| 11 | [`11-A32-粒度lint與HTML折疊.md`](11-A32-粒度lint與HTML折疊.md) | A32 | 低階（獨立） | 無 |
| 12 | [`12-A34-CTV候選清單.md`](12-A34-CTV候選清單.md) | A34 | 低階（獨立、唯讀） | 無 |
| 13 | [`13-A10P1-登記簿與find-similar與判例庫.md`](13-A10P1-登記簿與find-similar與判例庫.md) | A10 P1 | **中高**（P1a 初始資料要使用者看過） | 08、09 |
| 14 | [`14-A33-稿單提案生成器.md`](14-A33-稿單提案生成器.md) | A33／D16 | 中 | 12、13-P1a |

第二波一律 TDD（先寫失敗測試）；每份自帶 3 連續正式輪驗收指標，對照全檢 §1 基線。

## 開工前 checklist（每份都要）

- [ ] `cd E:/GitHub/TVBS-AIHunter && git status --short --branch`：確認在 `main`。⚠️ 工作樹可能有**別的 session 未提交的檔**（0907 當時：`common/17`、`scripts/s2_render_html.py`、`scripts/s2_validate.py`）——**只 `git add` 本計畫列出的檔案**，`git diff --cached --stat` 確認後才 commit。
- [ ] 現在是**改規則空窗**嗎？現查排程七輪：17:00／20:00／22:00／01:00／04:30／07:00／11:00。**只在 11:00 輪收工後～17:00 前改必讀規則**（`python scripts/s2_schedule_check.py` 可查；或 `MSYS_NO_PATHCONV=1 pwsh -NoProfile -Command "Get-ScheduledTask S2掃帶 | % Triggers | % StartBoundary"`）。不在空窗就只做不碰 `common/13*` 的計畫（02、03）。
- [ ] 沒有輪次在跑：`%USERPROFILE%\.s2-scan.lock` 存在**不代表**在跑（R16）；用 `s2_watchdog.ps1` 的 `Test-ScanRunning` 或看 `S2掃帶log/` 最新 log 是否已 DONE。
- [ ] 讀完該計畫**整份**再動手；每個 Step 的 Expected 沒達到就停下來寫 `needs-review`／回報，不要自己繞。

## 共通護欄

- 規則檔改完**一定**跑 `python scripts/s2_rules_check.py`，離開碼非 0 不得讓下一輪跑。
- 規則檔內容**只搬不改寫**（逐字），除非計畫明寫「改寫成…」。
- 每份計畫一個 commit（可多個但同一份不跨計畫），訊息前綴 `全檢/T8：`、`全檢/A35：`…；push 到 `origin main`。
- 做完把 MASTER 該列「一句話現況」改成一句最新現況＋commit hash（只改索引那一句；detail 檔只加不改）。
- 任何一步發現「規則裡沒有這條、只有 prompt 有」→ **先搬進規則再刪 prompt**，反過來會把規則弄丟。

## 全部做完的驗收（第一波結案條件）

- [ ] 五份計畫各自的 Expected 全過、各一個正式輪無新增 `needs-review`。
- [ ] `s2_rules_check.py` 列出的必讀檔 ≤7 份，全部 < 28,000 字元。
- [ ] `scripts/s2_scan_prompt.md` ≤ 8,000 字元。
- [ ] `_token_metrics.jsonl` 最新一輪 `rule_shas` 含新檔名、無 `13b`。
- [ ] 全檢 §1a 基線對照：呼叫數／輪**沒有上升**（本波不承諾下降）。
