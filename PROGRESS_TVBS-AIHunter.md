# TVBS-AIHunter 進度存檔

存檔時間：2026-09-23（新增段落，見下方「S2 掃帶轉Codex CLI可行性調查」；2026-09-20 D23 段落原樣保留）

## S2 掃帶轉Codex CLI可行性調查（2026-09-23，進行中，未動 repo 任何檔案）

**背景**：評估能否把S2掃帶launcher（現用`claude -p`）換成Codex CLI執行，前提是Codex CLI要有等效於`s2_gate_guard.py`（PreToolUse/PostToolUse hook）的攔截機制。

**已查證（文件層面，非本機實測）**：Codex CLI（v0.154.0）確實有等效hook系統——事件涵蓋`PreToolUse`/`PostToolUse`等，設定檔`~/.codex/hooks.json`（可疊repo層級`.codex/hooks.json`），matcher/command結構跟`.claude/settings.json`幾乎同款；deny協定是回傳`hookSpecificOutput.permissionDecision:"deny"`或exit code 2；覆蓋範圍含`apply_patch`/Edit/Write/Bash/MCP tools，只有hosted tools（如WebSearch）沒有。來源：`learn.chatgpt.com/codex/hooks`、第三方整理文（未經本機PoC驗證）。

**已派工但卡住**：派了一個headless PoC任務給Codex sol（在`C:\Users\User\AppData\Local\Temp\claude\...\scratchpad\codex-hook-poc\task.md`，隔離scratch目錄，不碰本repo）去實測驗證hook機制＋規劃轉接方案，但兩次派工都失敗：
1. 第一次：scratch目錄不是git repo被擋（已補`--skip-git-repo-check`修正）
2. 第二次：模型名稱錯誤——`~/.codex/config.toml`裡`model = "gpt-6-sol"`，但Codex CLI本機`models_cache.json`實際清單只有`gpt-5.5`/`gpt-5.6-luna`/`gpt-5.6-sol`/`gpt-5.6-terra`/`gpt-6-astra`/`gpt-reserve`，**沒有`gpt-6-sol`**，呼叫時400錯誤。使用者研判可能是這個Claude Code session太久沒重開、沒讀到最新模型清單，正在重開session中。

**下一步（待使用者重開session後）**：確認sol目前正確代號（`gpt-5.6-sol`還是真的有更新但本機快取未同步），再重新派工跑上述PoC任務。`task.md`內容已就緒可直接重跑，不用重寫。

**尚未做**：PoC本身尚未成功執行過一次，所以「Codex CLI hook機制」目前仍只是查文件查到的、沒有本機實測驗證；轉接方案設計文件（`findings.md`）也還沒產出。

## D23：韓聯社(YNA)/CNA YouTube 接線

- **worktree**：`E:\GitHub\TVBS-AIHunter-d23-youtube`，branch `feat/d23-youtube-bridge`
- **main 未動**：只有一個 plan-doc commit（`b8049f7`），main 上的自動掃帶排程完全沒接 D23
- **最新 commit**（worktree 上）：
  - `e8b180d` D23：description 優先於字幕，字幕只當備援（使用者裁定）
  - `b5f2a67` D23 Phase 6：yt-dlp 字幕節流間隔 2秒→8秒（使用者裁定）
  - `fc0927f` D23 Phase 6：yt-dlp 字幕 HTTP 429 限流誤判成「沒字幕」+ 加請求節流
- **狀態**：Phase 6 已完成，剛做完一輪真實端到端測試（CNA+YNA、description-first 邏輯）。該次測試依使用者指示「這次不要產出候選檔」，只產生 repo 外的暫存 manifest，未落任何 commit、未寫候選檔，working tree 乾淨。

### 安全設計（雙重防呆，已跟使用者確認過）
1. **手動模式**：只能跑 `finalize`（不加 `--apply`）→ 只寫 `_待整併/` 候選 JSON，絕不碰正式狀態。
2. **排定輪次**：只有 scheduled round 的 `finalize --apply --in-round`（跑在自己的 `.s2-scan.lock` 視窗內）才會真的寫正式狀態，且該呼叫才會去撿 `_待整併/` 裡的候選檔一併整併、成功後歸檔到 `已整併/`。
3. **D23 排定輪次目前預設 OFF**（2026-09-20 使用者裁定，main 上有文件記載）。因此就算候選檔留在 `_待整併/`，也不會被自動撿走套用——要嘛使用者手動 `--apply`，要嘛先開啟排定輪次。

### merge 回 main 的影響評估（已查證，尚未執行）
跑過 `git diff main...feat/d23-youtube-bridge --stat`：
- **總計**：25 files changed, 3452 insertions(+), 5 deletions(-)
- **非純新增，會動到既有正式檔案**：
  - `scripts/s2_material_schema.py`（22 行變動）
  - `scripts/s2_scan_prompt.md`（6 行變動，是既有 5 站自動掃帶用的 agent prompt）
  - `scripts/s2_validate.py`（1 行變動）
  - `scripts/test_s2_material_schema.py`（+13，測試檔）
  - 兩份 `common/` 規則文件各改個位數行（`common/17-網址素材整併.md`、`common/13...站擷取.md`）
- **純新增（~19 個檔案、無風險）**：`s2_youtube_bridge.py`、`s2_youtube_launcher.py`、各 `test_s2_youtube_*.py`、`scripts/fixtures/d23_youtube/*`、兩份 D23 plan/驗收文件
- **結論（已回覆使用者）**：merge 進 main 不是純加法，但改動幅度小；且即使 merge，D23 排定輪次仍需額外去接 `s2_watchdog`/排程設定才會真的跑，目前完全沒做這步——**merge 本身不會讓既有五站掃帶行為改變，也不會讓 D23 自動開始跑**。

### 尚未做/待辦
- 三個既有正式檔案的實際 diff 內容尚未逐行檢視過（只看過 stat 行數），若要真的評估「merge 安全性」的技術細節，下一步是跑：
  ```
  git diff main...feat/d23-youtube-bridge -- scripts/s2_material_schema.py scripts/s2_scan_prompt.md scripts/s2_validate.py
  ```
- 兩份 `common/` 文件的確切檔名因終端機編碼顯示成 octal escape，尚未解析出可讀檔名（可用 `git -c core.quotepath=false diff --stat` 重查）。
- **未授權事項**：merge 回 main、啟用 D23 排定輪次、接 `s2_watchdog`/排程 — 這三件事都尚未經使用者明確下令執行，不可自行動工。

## S2 掃帶轉 Codex CLI Phase 1：adapter／patch parser／golden tests（2026-09-23，完成）

- **獨立 worktree**：`C:\Users\User\Documents\Codex\2026-09-23\session-prompt-s2-codex-cli-phase\work\TVBS-AIHunter-s2-codex-gate`
- **分支**：`feat/s2-codex-gate-adapter-phase1`；**commit**：`c398d289816558e803842adfd634e75cf560ada8`（基於 main 當時 HEAD `255ec6e`）。worktree 乾淨；未 merge 回 main。main 工作目錄的既有未提交內容沒有搬入或修改（本進度段落是使用者指定的例外）。D23 worktree 未動。
- **完成**：新增 `scripts/s2_codex_gate_adapter.py` 與 `scripts/test_s2_codex_gate_adapter.py`。純函式 parser 處理單檔／多檔／多 hunk／rename／delete／add；相對路徑依 hook `cwd` 正規化，拒絕越界、絕對路徑歧義、重複 path 與既存目標的 Add/Move。Update、Delete、rename 的來源與目的映成 `edits` 後呼叫原有 `decide_edit()`；Delete 讀取完整舊內容。任一檔拒絕就回 Codex `permissionDecision: deny` JSON；放行時 stdout 空白。Add 沿用原本 Write 類語意，不套 Edit 鎖；本階段不做 PostToolUse 清鎖。目標 `apply_patch` 的 payload/patch 無法安全解析時 fail-closed；非目標工具或爛 JSON 依現有 hook 慣例 fail-open。
- **測試**：`python -m unittest -q test_s2_codex_gate_adapter` → 10 tests，OK（含 table-driven golden patches、路徑、category/tc 改值與其他欄位、gate lock、session tally、stdin/stdout subprocess contract）；`python test_s2_gate_guard.py` → PASS=221 FAIL=0；`git diff --cached --check` → 0 問題。只提交上述兩個新檔，沒有改 `scripts/s2_scan.ps1`、production launcher、排程或 `s2_gate_guard.py` 判斷／簽名。
- **這階段仍未驗證**：調查文件第 8 節的 exit code 2／legacy `decision:block` 相容格式、正式 OpenAI provider + gpt-6-sol live run、Codex PostToolUse 成功 apply_patch 的完整 `tool_response`、S2 browser MCP 在 Codex profile 的可用性、完整五站掃帶與 split-session manifest 端到端、所有 browser/MCP/file-change JSONL item schema。這次也**沒有**用真實 `codex exec` 呼叫新 adapter 做 CLI integration；目前只有 Python parser／hook subprocess contract。調查文件已有的 localhost fixture 驗證的是 PoC hook，並非這支 adapter。
- **下一步**：接調查文件第 7 節落地順序 **第 2 步**，建立預設仍為 Claude 的 canary launcher／`-Runtime claude|codex`，並先檢查 `-C` 與受允許 repo 路徑如何對應：本階段 adapter 有意只接受 `cwd` 內的相對 patch 路徑，若 canary 繼續用 scratch 當 cwd，repo 外 patch 需要明確、安全的路徑契約，再補測試。之後按第 3–6 步做 canary、live fixture、真實輪次對帳，未授權前不切正式排程。
- **卡住**：無；Git metadata 與指定 main 進度檔位於沙箱寫入範圍外，已透過受控授權完成 worktree／commit／本段追加。

## S2 掃帶轉 Codex CLI Phase 2：平行 guard canary launcher（2026-09-23，完成）

- **承接 worktree**：`C:\Users\User\Documents\Codex\2026-09-23\session-prompt-s2-codex-cli-phase\work\TVBS-AIHunter-s2-codex-gate`；本階段分支 `feat/s2-codex-canary-phase2`，commit `1b87b3a6a52faee1a75a8adb4d35994ee3cfbefe`（前一筆 Phase 1 commit `c398d289816558e803842adfd634e75cf560ada8` 仍在歷史中）。worktree 乾淨，沒有 merge main。
- **完成（調查文件第 7 節第 2 步）**：新增獨立 `scripts/s2_codex_canary.ps1`，`-Runtime claude|codex` 預設 `claude`。預設只輸出 JSON 預覽，不建檔、不呼叫模型；只有明傳 `-Live` 才在系統暫存目錄建立全新 run directory，產生受保護的 `ns_entries_1100.json` fixture，嘗試單次 Edit/apply_patch，檢查檔案未改且 log 有 guard deny。Codex 路徑產生該 run 專屬 `.codex/hooks.json`，hook 指向 Phase 1 adapter；使用 `codex.cmd exec --json -C <fixture>`、workspace-write、獨立 stdout JSONL／stderr log。launcher 在使用 hook trust bypass 前先檢查 adapter 與原 guard 都是乾淨的 tracked HEAD 內容。Claude 路徑使用原 guard 的獨立 settings fixture。沒有修改 `s2_scan.ps1`、watchdog、production launcher、排程、S2 state 或原 guard 邏輯。
- **範圍界線**：這是**隔離的 guard fixture canary launcher**，不是五站真實掃帶 launcher；沒有導入 browser MCP、真實 prompt/state contract、split manifest、Codex JSONL 下游 parser，也沒有在這階段跑真實 Claude/Codex provider 的 `-Live`。`gpt-6-sol` 是 Codex 預覽預設模型，但調查文件指出目標帳號／本機 catalog 未完成 live 驗證，不把可用性視為已證明。正式 OpenAI provider、目標模型、主機信任／hook deny 仍列未驗證。
- **測試**：`python -m unittest -q test_s2_codex_canary test_s2_codex_gate_adapter` → 13 tests，OK；其中 canary 兩種 runtime 的 dry-run 參數／無副作用、拒絕非暫存根目錄，以及 fake `codex.cmd` 的 `-Live` wrapper 測試（確認 fixture、hook JSON、stdout/stderr 分流）。fake CLI **沒有**測真實 hook dispatch。`git diff --cached --check` → 0 問題。Phase 1 的原 guard 221/221 通過結果仍有效，本階段未改 guard，也未重跑該 221 測試。
- **仍未驗證**：Phase 1 交接列出的 exit code 2／legacy deny 格式、正式 provider + gpt-6-sol、PostToolUse shape、Codex browser MCP、五站及 split manifest、完整 Codex JSONL schema 均尚未完成；此外新 launcher 的真實 `-Live` provider／hook pipeline 尚未跑。
- **下一步**：接調查文件第 7 節 **第 3 步**，在隔離 canary 上補齊 S2 同一 prompt/state contract、Codex browser MCP profile、獨立 raw logs 與關閉自動 PostToolUse 清鎖；先決定真實掃帶 `cwd`／repo／state 路徑如何在 adapter 的安全路徑規則下對應。第 4 步再用目標主機／帳號跑 live protected fixture。沒有到第 5–6 步對帳前，不接正式排程或切預設 runtime。
- **卡住**：無；本階段按範圍沒有進行真實模型執行。OpenAI Docs／官方 Hooks 文件確認目前 Codex hook 設定與 `--dangerously-bypass-hook-trust` 的用途，但這不替代目標環境 live 驗證。

## S2 掃帶轉 Codex CLI Phase 3：隔離輪次 canary（2026-09-23，完成程式與假 CLI 驗證）

- **獨立 worktree**：`C:\Users\User\Documents\Codex\2026-09-23\session-prompt-s2-codex-cli-phase\work\TVBS-AIHunter-s2-codex-gate`；branch `feat/s2-codex-round-canary-phase3`；本階段 commits `389628da50acd130b7805776d77be3f44cc9143b`、`e51e78d39fafe5a5e59c28271b80209444ed601a`（最新 HEAD）。worktree 乾淨；沒有 merge main、改 D23 worktree、啟用排程或修改 production launcher／`scripts/s2_scan.ps1`／`s2_gate_guard.py` 判斷邏輯。
- **完成（調查文件第 7 節第 3 步）**：新增 `scripts/s2_codex_round_plan.py` 與測試；同一份 `s2_scan_prompt.md` 的 checkpoint／run_id 契約、既有 state 檔名與 daily scratch cwd 經獨立 canary plan 對應。依原 `s2_mcp.json` 產生 run 專屬 browser profile/output 和 Codex MCP 設定；產生 repo 專屬 PreToolUse apply_patch adapter／Bash guard hook，明確不設 PostToolUse 自動清 lock。adapter 新增明列 repo／state 允許根路徑的解析，保留未設定時原本嚴格路徑規則。preview 預設唯讀、`--prepare` 只在系統暫存目錄產生設定與 prompt、`--run` 只接受暫存 state/run root 且要求非 main 分支和已提交的 hook 原始碼。runner 分開保存原始 stdout JSONL、stderr log、last message 路徑及 result.json；process exit 0 仍記為 `scan_success_verified=false`。prompt 附加 canary 路徑覆蓋並禁止讀寫正式 E:/G: 路徑。此次沒有呼叫真實模型。
- **測試**：`python -m unittest -q test_s2_codex_round_plan test_s2_codex_gate_adapter test_s2_codex_canary` → 20 tests，OK（含 prompt/state/context、MCP/profile、hook 無 PostToolUse、暫存路徑、修改已準備 hook 時拒跑、fake CLI `--run` stdout/stderr 分流與未驗證狀態）。`git diff --cached --check` → 0 問題。第一筆 Phase 3 commit 後另跑過原 guard `python test_s2_gate_guard.py` → PASS=221 FAIL=0；第二筆只改 round runner／其測試，未改 guard。fake CLI 不代表真實 Codex hook dispatch、browser 或五站掃帶已通過。
- **調查文件第 8 節仍尚未驗證**：exit code 2／legacy `decision:block` deny 相容格式；正式 OpenAI provider + gpt-6-sol live run；Codex PostToolUse 成功 apply_patch 的 `tool_response` 完整 shape（本 canary 關閉該 hook）；S2 browser MCP 在 Codex profile 的實際可用性；完整五站掃帶與 split-session manifest 的 Codex 端到端結果；所有 browser/MCP/file-change JSONL item type 的完整 schema／真實 log golden fixture。另外，新 round runner 尚未用真實 `codex exec`、目標主機 project trust、真實帳號或 browser 登入態驗證；硬編碼在原規則中的正式 E:/G: 路徑目前靠 sandbox 加 prompt 覆蓋隔離，需在 live canary 再查證。
- **下一步**：接調查文件第 7 節 **第 4 步**，在目標帳號／模型／主機用 live protected fixture 確認 project trust、hook deny、path/sandbox 與 browser MCP；再接第 5 步 2–3 輪五站掃帶、state/render/receipt/metrics 對帳與 JSONL golden fixtures。第 6 步才考慮切排程預設。
- **卡住**：無程式開發阻礙；真實 provider／browser／五站驗證尚未執行，不能據此宣稱掃帶成功。

## S2 T14：一次多筆 Bash／平行 tool call canary（2026-09-23，實作完成、未啟用）

- **隔離 worktree**：`E:\GitHub\TVBS-AIHunter\.tmp-s2-parallel-worktree`；branch `feat/s2-parallel-canary`；commit `4dacbd9f35964165e44e8c888fb7d48ed2088558`。未 merge main、未切正式排程 canary、未動 `E:\GitHub\TVBS-AIHunter-d23-youtube`。本 session 的主 repo `.git` 為唯讀，無法直接建立主 repo 的 branch ref，因此採 `E:\GitHub\TVBS-AIHunter\.tmp-s2-parallel-seed` 所屬的 clone-backed linked worktree；後續若要帶回主 repo，可由該 seed／worktree fetch 或 cherry-pick 此 commit。
- **完成內容**：新增 `common\parallel\s2_scan_prompt.md` canary、`common\parallel\_orig_bak\s2_scan_prompt.md` V8 原版備份、`common\parallel\FORK-BASE.txt`，以及 `scripts\s2_parallel_switch.ps1`。canary 指示放在 prompt 前段，明訂「同一則 assistant message 送多個 tool call」，固定用開工 8 份規則 Read 量測，並列出同站多個獨立唯讀 inspect、dry-run／audit、T/C 查詢等安全案例；NS／AP／RT／ENEX／ABC 跨站因共用 Playwright profile 與單一 state writer，明訂不可平行。
- **切換與安全性**：`pwsh -File scripts\s2_parallel_switch.ps1` 唯讀查狀態；`-On` 切 canary；`-Off` 退 V8；`-Force` 只略過忙碌／漂移保護。具備 LF 正規化 sha256 fork-base 漂移偵測、`.s2-scan.lock`／`s2_scan.ps1` 忙碌偵測、切換後自動跑 `s2_rules_check.py`，且 `-On`／`-Off` 任一方向驗證失敗都恢復切換前內容。
- **驗證與目前狀態**：`python -X utf8 scripts\s2_rules_check.py` 全過；PowerShell UTF-8 parser 通過；隔離 worktree 內的正常 `-On`／`-Off` 與刻意移除 Python PATH 的雙向失敗回滾測試均通過。測完已退回 **V8**，live prompt 與 V8 backup sha256 相同。此環境找不到 `pwsh` 7，所以沒有以原始 `#Requires -Version 7` 入口直接執行；執行測試是 UTF-8 讀入後僅在記憶體移除 Requires 行，其他腳本內容不變。
- **量測取捨**：未改 `s2_render.py` 或其他生產程式；低風險做法是事後讀真實 round log，固定核對開工 8 次 Read 是否出現在同一 assistant message／是否有重疊執行，並沿用 T14 查證報告列出的同站 inspect、dry-run＋audit、T/C 查詢與最大實際併發量測點。
- **下一步**：經使用者決定後，先把 `4dacbd9f` 帶入主 repo，再用 `s2_parallel_switch.ps1 -On` 切 canary，連續觀察至少 2 輪真實排程；逐輪比對 T14 查證報告的量測點。兩輪後若最大併發仍為 1，判定 prompt 引導未生效／runtime 仍序列化，再評估 deterministic fan-out wrapper；觀察完成前不可宣告 T14 已優化完成。
- **卡點**：主 repo Git metadata 的沙箱寫入權限與本機缺少 `pwsh` 7；均已在上述交接中保留可追溯資訊，沒有擴大修改生產程式。
- **2026-09-23 路徑更正**：上面「隔離 worktree」段落所述的權限問題根因已查出——不是主 repo `.git` 本身唯讀，是**另一支同時在跑的 Codex task**（`feat/s2-codex-round-canary-phase3`，跑在 `C:\Users\User\Documents\Codex\2026-09-23\...\TVBS-AIHunter-s2-codex-gate`，正常註冊、繼續在跑、未受影響）跟這支 T14 task 同時搶 main repo `.git` 寫入權，Codex sandbox 因而把 T14 這支隔離成不同 OS 帳號（`DENIS/CodexSandboxOffline`）、只能開自己的 clone-backed worktree。已處理：`git fetch` commit `4dacbd9f` 進 main repo，改開正常 worktree **`E:\GitHub\TVBS-AIHunter-s2-parallel`**（`git worktree list` 可見，與 `-d23-youtube` 等既有 worktree 同構），刪除 `.tmp-s2-parallel-worktree`／`.tmp-s2-parallel-seed` 殘留（原本就已被 `.gitignore` 排除，未汙染 main 追蹤狀態）。commit 內容不變，下一步仍是「使用者決定後 `-On` 切 canary、觀察 2 輪」。


## S2 掃帶轉 Codex CLI Phase 4：protected fixture 本機驗證與 live 阻礙（2026-09-23，部分完成）

- **獨立 worktree**：`C:\Users\User\Documents\Codex\2026-09-23\session-prompt-s2-codex-cli-phase\work\TVBS-AIHunter-s2-codex-gate`；branch `feat/s2-codex-protected-fixture-phase4`；commit `1bf79266dcdd1b584993538c53e1e09b4860ec27`（承接 Phase 3 最新 `e51e78d39fafe5a5e59c28271b80209444ed601a`）。worktree 乾淨；main 工作目錄僅按使用者要求追加本進度段落；沒有修改 D23 worktree、production launcher／`scripts/s2_scan.ps1`／`s2_gate_guard.py`、排程或 merge。
- **查出的真實問題與修正**：Codex CLI 0.154.0 的 `--ignore-user-config` 在本機實測會連專案 `.codex/hooks.json` 一起略過；原 Phase 2/3 plan 因此無法真的攔 Edit。另若 canary fixture 放在本 worktree 的子目錄，Codex 會以外層 Git root 找 project hooks，也會略過 fixture 自己的 hook。已從兩個隔離 launcher/plan 移除該旗標；Phase 2 canary 若放在 worktree 下，會在單次 fixture run directory 建獨立巢狀 Git root，再放 hook。補測試禁止該旗標並檢查巢狀 root。
- **本機實際 CLI integration**：使用調查文件的 localhost Responses fixture（無外部模型呼叫），由真實 `codex-cli 0.154.0`／`gpt-5.5` 產生一個更新 `ns_entries_1100.json` 的 `apply_patch`。隔離 project hook 實際呼叫本分支 adapter，stdout 顯示 `Command blocked by PreToolUse hook` 與 `NS/AP/RT`；fixture 最終仍是 `{"entry":"ORIGINAL"}`；下一個 mock Responses request 的 `custom_tool_call_output` 帶有相同拒絕理由。若加回 `--ignore-user-config` 或省略巢狀 Git root，測試 patch 實際會成功改檔，故這不是只有 Python unit test 的推論。測試使用決定論 localhost provider；因目前外層 Windows sandbox 的 `CreateRestrictedToken failed: 87`，該**隔離 mock CLI 測試**需用 CLI 的 sandbox bypass 才能讓 patch 走到 hook，並非正式 provider canary 的安全設定。暫存原始 log 與 fixture 在本任務 `work/phase4-local`，沒有提交到 repo。
- **測試結果**：`python -m unittest -q test_s2_codex_canary test_s2_codex_gate_adapter test_s2_codex_round_plan` → 20 tests，OK；`git diff --cached --check` → 0 問題。原 guard 221/221 的 Phase 3 結果仍有效，本 commit 沒改 guard／adapter 判斷邏輯。
- **外部 live 嘗試與阻礙**：第一次 `-Runtime codex -Live` 使用 `gpt-6-sol`，在受限沙箱中約 241.6 秒；stdout 有 thread.started 與重連事件，stderr 明確記 `wss://api.openai.com/v1/responses` 存取遭拒 `os error 10013`，HTTPS 也重試失敗。因尚未進模型 apply_patch，結果 FAIL、無 hook deny；fixture 未變不能當通過證據。原始 stdout/stderr 已保留在本任務 `work/phase4-live-attempts/phase4-protected-20260923`，已從 worktree 移出。要求允許網路的相同 protected fixture 重試時，**自動核准審核拒絕**：理由是會把 fixture/prompt 傳到外部 OpenAI API，使用者尚未對這次明確外傳／live retry 給予批准；沒有繞過拒絕，已向使用者提出授權問題，答覆仍待確認。
- **其他尚未驗證／需先處理**：`codex login status` 顯示 Not logged in（環境僅確認有 `OPENAI_API_KEY`，沒有讀取或揭露值）；本機 `codex debug models` catalog 無 `gpt-6-sol`，第一次 live log 有 fallback metadata 警告，目標模型能否使用仍未知。移除 `--ignore-user-config` 才能啟用 project hook，但會載入使用者 config；目前使用者 config 含 SessionStart hook 與 browser、codebase-memory-mcp、filesystem、github、node_repl MCP servers，尚未隔離／審核其在 live canary 的影響。調查文件第 8 節的 exit code 2／legacy deny、正式 provider + gpt-6-sol、PostToolUse shape、Codex browser MCP、五站與 split manifest、完整 JSONL item schemas 仍未完成；localhost 實測只補了 adapter 的 CLI hook/deny/feedback 路徑。
- **下一步**：仍是調查文件第 7 節 **第 4 步**：取得本次外部 live retry 的明確授權，先處理目標帳號／模型與 user config hooks/MCP 隔離，再用 protected fixture 驗 project trust、hook deny 與 sandbox；成功後才進第 5 步 2–3 輪真實掃帶對帳。第 6 步排程切換尚未開始。

## S2 T14 第 2 階段：平行 tool call canary 根因查證（2026-09-23，完成）

- **產出**：完整報告在 Codex scratch `C:\Users\User\AppData\Local\Temp\claude\C--Users-User\eb4b2d77-4a48-422c-b0db-25ce3810af6b\scratchpad\codex-bash-batch\findings2.md`；另有可重放的 `analyze_round_log.ps1`。只讀 canary prompt、真實 round JSONL、Claude session transcript、launcher 與相關規則；沒有切 canary、沒有修改 S2 程式或 prompt。
- **量測更正**：0923-2026 真實 round 仍是 157 個 tool_use／157 個 result，但不是「最大併發 1、0 次平行」。按第一個 tool_result 前的連續 tool_use 重算，實際有 **2 個雙呼叫批次、最大同批在途數 2**：`13c2`＋`13c3` 兩個 Read，以及 `needs-review list`＋`scratch-dir` 兩個 Bash。固定 8 Read canary 的分段是 **`1,1,1,1,1,1,2`**，所以驗收仍 FAIL、但不能稱完全無效。舊判讀漏算的原因是 `stream-json` 把同一 logical assistant turn 的每個 tool_use 拆成各自一筆 top-level assistant event。
- **prompt 到達與注意證據**：canary 在 `common\parallel\s2_scan_prompt.md` 第 9–29 行，是 V8 說明後的第一個操作性規則段；共 903 個 Unicode 文字元素（去空白 763），明寫「同一則 assistant message 多個 tool call」與「8 個 Read 一次送出」。`s2_scan.ps1` 直接把整份 prompt 當 `claude -p` 的初始 user prompt；session transcript 的第 3 筆 user message 含 marker／標題，round log 也有 agent 自述「現在同時讀取 8 份」。111 個 thinking block 都是空字串，沒有其他可檢查思考；也沒有 runtime 拒絕多呼叫的錯誤。
- **根因**：排除「prompt 沒讀到／位置太後／只寫抽象建議」，也排除 headless `-p` 硬性一次只准一個（同 session 已成功執行 Read/Bash 多呼叫批次）。主因是模型對 prompt 的**部分、非決定性遵守**；prompt 可以提高平行 tool use 機率，不能保證恰好 8 個才 yield。`13c3:164-170` 的「機械步驟串成單一 Bash」與 canary 多 tool_use 有次要介面形狀競合，但不能解釋讀到 `13c3` 前的前六份 Read 已逐一 yield。
- **推薦**：正式方向轉 deterministic、allowlist 唯讀的 batch/fan-out module，把有界併發、timeout、部分失敗、順序、輸出預算與遙測藏進小 interface；不要做任意 shell 字串併發器。若仍要測 prompt，只先用 `--append-system-prompt` 加 Anthropic 官方強版 `<use_parallel_tool_calls>`，跑 3 次 8-file fixture micro-canary，3/3 達 8-way 才再跑真實 round；不再把 prompt 當結構保證。另 8 份規則總輸出超過單一 Bash result 安全預算，不能用八檔 `cat` 成一個結果當 wrapper。
- **粗估工程量**：同站、小輸出的 `inspect-many`／唯讀 jobs＋測試與遙測約 1–2 工程日；通用但安全的 manifest fan-out 約 2–4 日；若連 8 份大規則載入也要 deterministic，需另改 launcher/input transport 或專用 MCP/harness，再加約 1–2 日。

## S2 T14 第 3 階段：方案 B deterministic read fan-out 規劃（2026-09-23，規劃完成、尚未實作）

- **產出與範圍**：完整可審查規劃位於 Codex scratch [plan_optionB.md](C:/Users/User/AppData/Local/Temp/claude/C--Users-User/eb4b2d77-4a48-422c-b0db-25ce3810af6b/scratchpad/codex-bash-batch/plan_optionB.md)。本階段只寫規劃與交接，沒有修改程式、prompt、排程或 production state，也未因文件工作重跑測試。
- **介面決策**：建議新增獨立 `scripts/s2_read_fanout.py`，以 JSON manifest 接收有 label 的結構化唯讀 jobs；禁止任意 command／argv／browser／寫入旗標。第一版僅 allowlist `inspect`，底層以 `shell=False` 固定 argv 呼叫既有 `s2_batch_prep.py`，重用 T9 已驗證的 id／field／28k 預算邏輯；不在大檔內直接用執行緒包 `cmd_*`，也不重寫查詢邏輯。
- **執行與安全契約**：預設 4、硬上限 8 workers；job 上限 64；預設 timeout 15 秒、硬上限 60 秒；單 job error／timeout 不取消其他 jobs；全部完成後依 manifest 輸入順序回傳。summary 與所有 job envelope 優先保留，正文按序列化後字元數 deterministic 裝箱，整個 Bash 可見結果不超過 `INSPECT_TEXT_BUDGET`，超量必須明記 truncated／original／rendered，不能靜默截斷。
- **遙測**：外層 tool call 進固定 `s2_read_fanout:run`／`:validate` 桶；logical jobs 另記 `jobs.planned/completed/succeeded/failed/timed_out`、`max_concurrency`、`jobs_by_op`，不灌進 `tool_calls_by_name`，維持 `classified_total == tool_calls`。parser 只收 schema 合法的 summary 與固定 op 白名單；同一 Bash 內若有多個 invocation 必須逐筆收齊，避免 T9(F/H) 的幽靈桶與漏算。
- **8 份規則界線**：本工具 Phase 1／2 不處理。八檔總輸出超過單一 Bash result 安全預算；另立 launcher file-backed input injection 或專用 MCP/harness spike，驗收要求第一個 assistant sampling 前 8 檔 SHA／bytes／EOF 皆可對帳，10/10 fixture 完整注入。預估另加 1～2 工程日；做不到就維持現行 8 Read，不以 fan-out wrapper 冒充解法。
- **下一步建議**：進入 Phase 1 最小實作（含 schema、`inspect` adapter、有界併發、timeout、28k 裝箱、metrics 與 table-driven tests，總計 1～2 工程日），之後只在同站、低輸出、互不依賴的 2～4 jobs 上觀察 2～3 輪。只有正確性不退化、無 orphan／guard 衝突／截斷，且 wall time 有可重現改善，才擴至 `search/compare/dedup-check`（累計 2～4 日）；否則直接退回既有逐次 `s2_batch_prep.py inspect` 路徑。

## S2 A42：A41 新鎖成本歸因與調鬆評估（2026-09-23，查證完成、待裁決）

- **產出與範圍**：完整報告在 Codex scratch `C:\Users\User\AppData\Local\Temp\claude\C--Users-User\eb4b2d77-4a48-422c-b0db-25ce3810af6b\scratchpad\codex-bash-batch\findings_a41.md`。逐一讀完指定 12 個 commit 的 `git show`，並解析 `D:\Downloads\S2掃帶log` 中 0922-1907、0922-2100、0923-1700、0923-2200 四輪完整 tool call/result；沒有修改 production 程式、規則、prompt、排程或 state。
- **錯誤事件更正**：四輪共有 **62** 筆 `is_error:true`，不是先前粗算的 61。逐筆分類為：22 筆真的被 gate/鎖迫使改方法、18 筆正常驗證/對帳、22 筆 agent 指令或參數失誤。先前 39 筆 exit code 1/2 中只有 4 筆是真 gate，另 18 筆是正常驗證、17 筆是操作失誤；exit code 不能直接當成本分類。
- **A41 歸因**：嚴格可指認新 A41/A12 的有 10 筆；把 0923-2200 兩筆新 gate 與 lock lifecycle 的強交互也算入是 12 筆，占全部 error 16.1%～19.4%。四輪 819 calls，相對舊三輪平均的四輪預期值 406.7，多 412.3 calls；以每次拒絕至少再做一個替代 call 計，新鎖占超額 calls 下界約 4.9%～5.8%，加上重建/重驗與較大輸出後，證據支持的成本帶約 **5%～10%**，不能解釋大部分漲幅。
- **時間線結論**：9/22 17:00 已達 257 calls／35 分／$27.2，但 `8fc8248` 18:40 才上線，主要 A41 commits 更在 9/23；因此 A41 不是初始轉折原因。該輪 53 次 Edit，相對 9/21 17:00 多出的 149 calls 中占 35.6%。主因仍是大量逐筆修補塞進單一長 session、零散 turns/cache read；A41 是後續少數但真實的放大/轉移成本。
- **autofix／驗證判讀**：`b4a9ba4` 的 9 組控制實驗只驗 build 函式 runtime，沒有覆蓋 agent turn、cache read、hook deny、rewrite/build/lint 繞路、browser/CLI 失誤或 lock 生命週期；所以「build 未退化」與「整輪變貴」可以同時成立。沒有證據把主要漲幅歸給 autofix 計算；實際看到的是操作備註修完後，低於門檻且不相干的 `FMT_PKG_DONUT_NEED_SOT(1)` 接管並延長 lock。
- **建議**：維持操作備註、ENEX/ABC derived files、batch `category/tc`、第三次 Edit 兜底、ID/site/欄位/原子寫入/lint 等核心防線。下一實作若獲裁決，優先讓 active lock 只追蹤原觸發 reason set，其他低於門檻 reason 只警告、不接管 lock。另由使用者裁決是否把 NS/AP/RT 無 active lock、既有 ID、非機械欄位的前 1～2 次 Edit 改警告，第三次仍硬擋；報告建議預設安全優先，先只修黏鎖並觀察 3 個同時段近似素材量輪次。
- **狀態**：A42 已追加到 MASTER；本輪只做查證與文件交接。未獲使用者明確裁決前，不實作任何調鬆。

## 2026-09-24 — A42 操作失誤修復與 A41 成本優先放寬完成（已 merge main）

- 在隔離 worktree `E:\GitHub\TVBS-AIHunter-a42-fix`、branch `feat/a42-ops-and-cost-priority` 完成實作；核心 commit `994e3deed7c11f0f35153342f921431b5a1dc9c7`。
- 22 筆操作失誤已逐筆映射到工具修法與測試：補 `check-entries` 相容入口、flat-map inspect/search、`inspect --offset`、AP browser `itemids`／JS 語法 guard、NS token 空值範本、`uuidgen`／未閉合引號提示、topic-alias 相容參數、reclass 預設建議檔、needs-review 可結案 ID、rewrite-entry 餵錯 batch 的精確指路。完整表在 `common/plans/A42-操作失誤與成本優先修復.md`。
- A41 成本優先已落地：無 active lock 時只放寬「既有 ID、只改 entry、JSON 可解析、共用 lint 不退步」的前 2 次 Edit；每次 PreToolUse 警告，PostToolUse 自動跑共用 lint 並要求完整 `build --dry-run`；第 3 次硬擋並要求一次 Write／批次路徑。category/tc、ID 增刪、其他欄位、ENEX/ABC derived files 與 active lock 都維持硬擋。
- 黏鎖 bug 已修：active lock 只追蹤原始跨過門檻的 reason set；原始 reason 歸零後，`FMT_PKG_DONUT_NEED_SOT(1)` 這類其他低量 reason 回到 warning，不再接管或延長鎖。
- 驗證：A42 14/14、gate guard 221/221、batch prep 266/266、bash guard 51/51；相關 raw loader／needs-review／topic／platform／settings 測試全過；`s2_rules_check.py` 全過；`py_compile`、`git diff --check` 全過。全 73 支 S2 測試為 70 支通過，3 支受既有外部環境限制（G: corpus 權限、缺 `pwsh`）失敗，未修改 base 同樣失敗。

## 2026-09-24 — 0100／0430／0700 exit code 1/2 精確分類（只查證，待裁決）

- 完整報告：Codex scratch `codex-bash-batch\findings_exit12.md`。逐行解析三份 stream-json 並讀完每筆未截斷訊息，符合 `is_error:true`＋`Exit code 1/2` 的母體為 18 筆：0100=0、0430=9、0700=9。
- 分類：真正被交件 lint 擋下 **3（16.7%）**；正常驗證／對帳非零回報 **6（33.3%）**；agent 操作失誤 **9（50.0%）**。正常桶是 5 次 `compare` 與 1 次 needs-review／schedule 狀態檢查，不應算成額外錯誤成本。3 次真擋路均為應保留的 `s2_platform_lint.py` 品質防線。
- A42 覆蓋：9 次操作失誤中直接修到 4 次、因上游 flat-map inspect 修好而間接消除 1 次，共 **5/9（55.6%）**。未覆蓋 4 次：多行未閉合引號、`inspect --ids` 多 argv、NS `rewrite-entry` 誤傳 `skip`、bulk `topic-register --entries`。

## 2026-09-24 — A42補件：多行未閉合引號防呆＋inspect --ids空白分隔相容（已merge main）

- 使用者裁決「照sol建議做」，補了merge main前的兩個低風險缺口：`s2_bash_guard.py`多行指令保守未閉合引號偵測（合法跨行引號/註解/heredoc不誤擋）、`s2_batch_prep.py` `inspect --ids`同時接受逗號分隔與空白分隔兩種格式並存。commit `1948c77`。
- 測試：A42 unittest 16/16、bash guard 51/51、batch prep 266/266，`s2_rules_check`全過。
- 已merge回main（合併commit見git log）。`rewrite-entry skip`誤改與bulk`topic-register --entries`原子性問題**未修**，留待另案。
- 下一步：未啟用canary觀察，若要驗證真實成本與安全性，需另外決定是否切canary觀察排程。

## 2026-09-24 — A43 逐筆 Edit／長 session 根本解法評估（規劃完成、未實作）

- **產出與範圍**：完整規劃在 Codex scratch [plan_root_fix.md](C:/Users/User/AppData/Local/Temp/claude/C--Users-User/eb4b2d77-4a48-422c-b0db-25ce3810af6b/scratchpad/codex-bash-batch/plan_root_fix.md)；MASTER 已新增 A43。本階段只查證與規劃，沒有修改 production 程式、prompt、排程或 state。
- **split-session 現況更正**：A41 早期「manifest 已寫、尚未接線」已過期。main 的 `3714ea7`／`8c04952` 已完成 `{RUN_ID}`、`-SplitSession`、core→platform 循序兩段、fail-closed receipt、resume/finalize，以及兩段 transcript/token/cost 聚合；基本接線工程量為 0。剩餘是至少一次 17:00 真實 canary、ENEX/ABC 正式 reconcile receipt、啟用政策。split 不會直接減 Edit／turns，只會讓 platform turns 不再重讀 core conversation；A41 的 10%～20% cache-read 降幅仍是未驗證推估。
- **批次修補結論**：優先在 `s2_platform_bridge.py rewrite-entry` 與 `s2_batch_prep.py rewrite-entry` 加同一份 file-backed `--patch-file` 契約（target SHA、局部 set、全批驗證、原子寫入、dry-run、patch scaffold），不把 `s2_state.py add-batch` 改成 upsert；正式 state 既有稿更新沿用已有的 `update-entry --batch`。另查到 platform bridge 接受 `tc`，但 build/merge 沒有把它帶往下游，須在新介面前修正或從契約移除。
- **重算量化**：直接解析 0922-1700／2359 stream-json，ENEX 39＋ABC 9 是 48 個獨立 Edit turns，對應 25,002,406 cache-read tokens；全輪分別為 257／217 tool-use turns、114.1M／90.6M cache read。batch patch 的驗收目標是 targeted Edit＝0、repair turns 48→約4～6；split 的增量效益要在 batch canary 後另量，兩者不能直接相加。
- **建議交付順序**：Phase 0 fixture/規格 0.5 日；Phase 1 兩條 patch-file 路徑 2～3 日；採用提示 0.5 日；單 session canary 工程 0.5 日＋2～3 輪；split safety replay＋一輪 17:00 canary 工程 1 日；若要正式排程，再補 platform 強 receipt 1～2 日。未經使用者裁決不動工。

## 2026-09-24 — A43 file-backed batch patch Phase 0＋1＋1b 完成（已 merge main）

- **交接位置**：隔離 worktree `E:\GitHub\TVBS-AIHunter-a43-batchpatch`；branch `feat/a43-batch-patch`；實作 commit `58e5683f93951f1ad51601d8e1e1b3e867e9530b`。
- **Phase 0**：新增 sanitized 0922-1700 ENEX 39 則＋0922-2359 ABC 9 則 fixture 與 replay，只保留合成 ID／欄位／數值遺測，不含真實 ID、路徑或素材。腳本可重算 48 次 targeted Edit、25,002,406 cache-read tokens、474 全輪 tool turns、65 全輪 Edit calls、7,393,439 source-log bytes 與 lint 結果；規格固化於 `common/plans/A43-file-backed-batch-patch.md`。
- **Phase 1**：`s2_platform_bridge.py rewrite-entry` 與 `s2_batch_prep.py rewrite-entry` 均支援 schema v1 `--patch-file [--dry-run]` 與 `--init-patch`。契約含 `entry/category/tc/skip` 全域白名單（core seam 依既有契約只收 `entry/category/tc`）、前綴 ID canonicalization、SHA stale-write 防線、lock/lint 全批驗證、局部 set 與原子替換，失敗不留半套。platform `tc` 已從 skeleton 帶到 entries、candidate 與 merge。
- **Phase 1b**：build/lint/gate 錯誤改為輸出可直接執行的 scaffold／apply 路徑；13c 只加窄幅一句，沒有新增懲罰規則。`s2_token_metrics.py` 新增 targeted Edit、platform/core patch apply 及 legacy rewrite 獨立桶與採用率。
- **驗證**：A43 unittest 15/15、batch prep 266/266、gate guard 221/221、platform 77/77、token metrics 靜態分桶全過；`py_compile`、`git diff --check`、`s2_rules_check.py` 全過。含多則 apply、錯站、裸／前綴 ID、canonical duplicate、未知／機械欄位、stale SHA、lock 權限、lint regression、單檔與 platform pair 寫入中斷／rollback。
- **邊界**：merge main前未啟用排程、未碰 `s2_round_manifest.py`／`-SplitSession`，`add-batch` 仍是 add-only，正式 state 更新仍走 `update-entry --batch`。D23 與 `TVBS-AIHunter-s2-parallel` worktree 未動。
- **A44發現的驗收指標**：0924-1100真實輪已量到RT/ENEX的零散inspect/search/rewrite/整份Write問題（RT 38 calls、ENEX 35 calls，對量體相近正常基準各為2.78×/3.00×）——這正是A43要解決的問題形狀。canary驗收要看RT/ENEX calls是否從38/35降回約14/12、整份Write次數是否下降。

## 2026-09-24 — A44 0924-1100 逐站成本／耗時歸因（查證完成）

- **產出與範圍**：完整報告在 Codex scratch [findings_1100_persite.md](C:/Users/User/AppData/Local/Temp/claude/C--Users-User/eb4b2d77-4a48-422c-b0db-25ce3810af6b/scratchpad/codex-bash-batch/findings_1100_persite.md)；可重跑工具為同目錄 `analyze_persite_logs.py`，逐 call TSV／JSON summary 在 `persite_output/`。完整解析 0924-1100 的 1,411 行 JSONL、237 tool_use／237 result，另用同一分類器解析 0919／0920／0921 的正常 11:00 與 17:00 輪。只寫分析與追蹤文件，沒有修改 production 程式、prompt、排程或 state。
- **精確歸站**：NS 49／AP 80／RT 38／ENEX 35／ABC 2／通用 33，合計237、UNKNOWN=0；本輪一次assistant message只有一個tool call，所以是237個tool-use turns，result的238 turns另含最後回覆。cache read歸因：NS15.77M／AP41.12M／RT27.02M／ENEX27.10M／ABC1.61M／通用13.55M，最後回覆0.819M，與總126.984M守恆。時間口徑校正：`duration_api_ms`＝56.65分，`duration_ms`總wall＝61.50分；逐call互斥分攤的tool loop＝61.04分。
- **核心判斷**：不是只有AP。帳面排除AP backlog與ABC登入失守後，NS＋RT＋ENEX＋通用仍有155 calls／33.56分／83.43M，對A41/A42前三個正常11:00平均61.67 calls／7.37分／13.99M，為2.51×／4.55×／5.96×。NS本輪78則、正常11:00平均26.3則，49 calls也幾乎同比到2.94×，主要是另一個高量體站；RT 17則卻38 calls、ENEX 17則卻35 calls，對量體相近正常17:00基準分別為2.78×與3.00× calls，確認兩站存在量體以外的流程膨脹。
- **根因與 confound**：RT雖0 error，仍有大量零散inspect/search與3次rewrite＋build鏈；ENEX有5 errors、3次整份Write、`entry/raw_entry`改名後反覆extract、補26筆dropped再重建。AP仍是最大單站且先於RT/ENEX，把後兩站每-turn cache推到歷史約2.5×，所以AP是直接主因兼context放大器，但非唯一工作量。A42新防呆只明確對到4次壞指令早拒（3 quote＋1 JS syntax），RT 0 error仍膨脹，沒有主要A42 computational regression證據。背景Codex可能對75.2秒目錄`ls`有小幅影響，但排除AP/ABC後相對基準多出的26.19分僅2.54分是tool-wait增量，約23.65分是model/agent gap；不支持本機資源競爭為主因。A43 commits在獨立branch/worktree，main於本輪全程仍是A42 merge `804a55a`，沒有跑到一半換production code。
- **後續量測建議**：A43 batch-patch canary要以RT/ENEX calls是否從38/35降回約14/12及整份Write次數為驗收；split-session另看platform每-turn cache是否回落，兩者效益不可混算。若要再判背景任務，下一輪需同步採CPU／disk queue遙測，不能只靠時間重疊推因果。

## 2026-09-24 — 存進度快照（截至本次session結束）

- **main目前狀態**：HEAD `8b7f037`（ahead origin/main 27，未push）。A42、A43均已merge進main並驗證乾淨：`test_s2_patch_file.py` 15/15、`test_s2_batch_prep.py` 266/266、`test_s2_gate_guard.py` 221/221、`test_s2_token_metrics.py` 78/78、`test_s2_a42_regressions.py` 16/16、`test_s2_bash_guard.py` 51/51、`s2_rules_check.py`全過。
- **A43-fix worktree已清理**（merge完刪除）。仍存在的既有worktree：`TVBS-AIHunter-d23-youtube`、`TVBS-AIHunter-s2-parallel`（T14 canary，目前切回V8，未merge main）、`TVBS-AIHunter-bite`、`TVBS-AIHunter-d21-anchor`、`TVBS-AIHunter-s2-scoped-1259`、`TVBS-AIHunter-side-precut`，以及另一個Claude session在跑的`.../TVBS-AIHunter-s2-codex-gate`（S2轉Codex CLI adapter，Phase 4進行中，跟本次S2效能修復無關）。
- **T14（一次多筆Bash平行呼叫）結論**：已測1輪canary，確認prompt引導對此問題無效（部分遵守但遠不足），已切回V8。根因是模型層機率性遵守，非runtime硬限制。**未再繼續**，判定放棄prompt路線。
- **A41/A42/A43/A44這條主線的最終判斷**：9/22起變慢變貴主因是逐筆Edit塞單一長session（非A41鎖本身，A41只佔5-10%）。A42（成本優先放寬＋操作失誤修復）已merge但0924-1100真實輪測出RT/ENEX仍有零散inspect/rebuild/重複整份Write問題，且被AP backlog的context放大效應加乘。A43（file-backed batch patch）已merge main，是目前對這個根因最直接的解法，**尚未經過任何真實排程輪驗證**——下一步待觀察輪次比對RT/ENEX calls是否真的降到約14/12。
- **AP資料缺口**：0924凌晨0100/0430/0700三輪AP整站因登入/fetch問題失守約9小時，1100輪已一次性補齊backlog（163則），但22:00-07:00那段窗口本身的原始缺口手動補掃任務已被使用者裁決放棄，四筆needs-review記錄（AP0924-0100/0430/0700/0700-audit）保留原樣未清除。
- **看門狗狀態**：已關閉（旗標與排程任務都停用）。S2掃帶主排程7個trigger（04:30/07:00/11:00/17:00/20:00/22:00/01:00）已全部確認為啟用狀態。
- **下一步待辦**：①觀察下一個正常量體輪次的A43效果（RT/ENEX calls數）②視結果決定是否需要接續做split-session canary（A43報告Phase 3）③AP登入穩定性未深入排查根因，只是這次手動介入後暫時恢復④main目前27個commit未push，尚未詢問使用者是否要push。

