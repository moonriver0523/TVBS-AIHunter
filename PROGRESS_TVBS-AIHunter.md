# TVBS-AIHunter 進度

## 2026-09-24 — A42 操作失誤修復與 A41 成本優先放寬完成（未啟用）

- 在隔離 worktree `C:\Users\User\AppData\Local\Temp\TVBS-AIHunter-a42-fix`、branch `feat/a42-ops-and-cost-priority` 完成實作；核心 commit `994e3deed7c11f0f35153342f921431b5a1dc9c7`。沒有 merge main，也沒有改正式排程或正式 main 的 `scripts/s2_gate_guard.py`。
- 22 筆操作失誤已逐筆映射到工具修法與測試：補 `check-entries` 相容入口、flat-map inspect/search、`inspect --offset`、AP browser `itemids`／JS 語法 guard、NS token 空值範本、`uuidgen`／未閉合引號提示、topic-alias 相容參數、reclass 預設建議檔、needs-review 可結案 ID、rewrite-entry 餵錯 batch 的精確指路。完整表在 `common/plans/A42-操作失誤與成本優先修復.md`。
- A41 成本優先已落地：無 active lock 時只放寬「既有 ID、只改 entry、JSON 可解析、共用 lint 不退步」的前 2 次 Edit；每次 PreToolUse 警告，PostToolUse 自動跑共用 lint 並要求完整 `build --dry-run`；第 3 次硬擋並要求一次 Write／批次路徑。category/tc、ID 增刪、其他欄位、ENEX/ABC derived files 與 active lock 都維持硬擋。
- 黏鎖 bug 已修：active lock 只追蹤原始跨過門檻的 reason set；原始 reason 歸零後，`FMT_PKG_DONUT_NEED_SOT(1)` 這類其他低量 reason 回到 warning，不再接管或延長鎖。
- 驗證：A42 14/14、gate guard 221/221、batch prep 266/266、bash guard 51/51；相關 raw loader／needs-review／topic／platform／settings 測試全過；`s2_rules_check.py` 全過；`py_compile`、`git diff --check` 全過。全 73 支 S2 測試為 70 支通過，3 支受既有外部環境限制（G: corpus 權限、缺 `pwsh`）失敗，未修改 base 同樣失敗。
- 下一步：若要驗證真實成本與安全性，才切獨立 canary 觀察排程，至少核對前兩次 Edit 的 lint 回饋、第三次硬擋、lock 解鎖 reason set，以及 calls／turns／cache read；本次沒有啟用 canary。
- 卡點：無程式阻礙。唯一環境限制是主 repo `.git` 在本 session 不可寫，因此 worktree 是 clone-backed 且位於系統暫存目錄；交接時不要清除該 temp worktree，直到 commit 已帶回主 repo。

## 2026-09-24 — 0100／0430／0700 exit code 1/2 精確分類（只查證，待裁決）

- 完整報告：Codex scratch `C:\Users\User\AppData\Local\Temp\claude\C--Users-User\eb4b2d77-4a48-422c-b0db-25ce3810af6b\scratchpad\codex-bash-batch\findings_exit12.md`。逐行解析三份 stream-json 並讀完每筆未截斷訊息，符合 `is_error:true`＋`Exit code 1/2` 的母體為 18 筆：0100=0、0430=9、0700=9。
- 分類：真正被交件 lint 擋下 **3（16.7%）**；正常驗證／對帳非零回報 **6（33.3%）**；agent 操作失誤 **9（50.0%）**。正常桶是 5 次 `compare` 與 1 次 needs-review／schedule 狀態檢查，不應算成額外錯誤成本。3 次真擋路均為應保留的 `s2_platform_lint.py` 品質防線。
- A42 覆蓋：9 次操作失誤中直接修到 4 次、因上游 flat-map inspect 修好而間接消除 1 次，共 **5/9（55.6%）**。未覆蓋 4 次：多行未閉合引號、`inspect --ids` 多 argv、NS `rewrite-entry` 誤傳 `skip`、bulk `topic-register --entries`。A42 回歸 14/14 PASS；精確 probe 證實現行 quote guard 單行會擋、多行會放過。
- 建議裁決：merge main 前補「保守多行 quote 檢查」與「`inspect --ids A B C` 相容」兩項低風險 CLI/guard 缺口，預期本輪 (c) 可避免率由 5/9 升至 7/9；不要放寬 `rewrite-entry` 的 `skip` 安全邊界，bulk topic-register 涉及批次驗證與原子性，兩項另案處理。
- 範圍：本階段只有 log 查證、scratch 報告與文件追加；沒有修改 production 程式碼、prompt、排程或 state，也未替使用者做是否補修／merge 的裁決。
