# AIHUNTER S2 V3 省 Token 優化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`（建議）或 `superpowers:executing-plans` 逐項執行。本計畫所有工作均以 checkbox 追蹤；未通過前一階段品質閘門，不得進入下一階段。

**Goal:** 在「漏收、BITE、分類、重大標記、狀態檔與 render 品質零退步」前提下，降低 S2 每輪 Claude Code 冷啟動輸入、模型往返、工具結果回灌與不必要的高階模型消耗。

**Architecture:** 採「先量測、再瘦外殼、再分片規則、再合併機械操作、最後程式化採集與模型分流」的漸進架構。現行 V3 始終保留為回退路徑；每一刀先用既有歷史資料 replay 或 shadow mode 驗證，再逐輪放量。

**Tech Stack:** PowerShell 7、Claude Code CLI、Claude Sonnet 5、Playwright MCP、Python 3、`s2_state.py`、`s2_render.py`、`s2_audit.py`、JSON／JSONL、Windows 工作排程器。

## Global Constraints

- **品質零退步**：任何高嚴重度漏收、false BITE、missed BITE、對帳缺站或 state/render divergence，均立即停止 rollout。
- 固定掃描順序維持 **NS → AP → RT**。
- 保留 API-first、DOM fallback、UI 最終 fallback 的單向階梯。
- 不把整輪掃帶交給子代理；不以多 agent 換取表面平行化。
- 不允許 token、Bearer、JWT、cookie 或 Authorization header 離開頁面 JavaScript。
- `src_text` 必須保存瘦身後的站方原文，不得混入 agent 判斷文字。
- 狀態檔仍是唯一真相源；txt／HTML 只由 render 產生。
- 外部 agent 仍只能交件到 `_待整併/`，不得直接寫正式狀態檔。
- 每階段必須可獨立回退，不得依賴人工刪鎖、刪 state、手改 txt 才能復原。
- 實作前先檢查 working tree；不得覆蓋其他工作中的未提交修改。
- 2026-08-12 寫計畫時，`scripts/s2_scan.ps1` 已存在**非本計畫造成**的未提交修改：新增 `-Effort`、預設 `medium` 並傳入 `claude --effort`。後續執行者必須先確認其來源與實際排程狀態，不能重做或覆蓋。

---

# 一、評估摘要

## 1. 已完成且應保留的優化

V3 已經完成下列高價值工作，後續不應倒退：

1. 三站以 API／DOM 白名單抽取，避免完整頁面與原始回應進 context。
2. 列表先 diff，只有新素材才取得全文。
3. NS 清單與全文分兩段查詢，避免一次帶回約 198k 字元。
4. AP／RT 在單一 `browser_evaluate` 裡用 `Promise.all` 批量取得詳情。
5. `add-batch`、`update-entry --batch`、`set-category --pairs` 降低逐則寫入。
6. `show` 只輸出指定欄位，取代整包 state dump。
7. `s2_render.py` 取代 LLM 全量重寫晚班交接檔。
8. `s2_audit.py`、清單快照與 `reconcile_log` 保留零漏收證據。
9. pending 走批次重查，不逐則重開頁面。
10. BITE、preliminary、footage type 等可機械判斷欄位已移到上游。

上述機制是現行品質與成本底座，所有新方案均應在其上疊加。

## 2. 現行主要成本熱點

### 2.1 Claude Code 冷啟動前綴過大

在抽查的最近一輪 JSONL 中，第一個業務動作前已出現：

```text
model: claude-sonnet-5
cache_creation_input_tokens: 64,460
cache TTL: 1h
```

這是單輪樣本，不足以代表每日平均，但已證明每輪啟動時存在約 6.4 萬 token 等級的固定上下文。來源可能包含 Claude Code 預設 system prompt、全域 CLAUDE.md、memory、hooks、skills 描述、工具 schema、MCP schema 與 S2 規則。

目前啟動器使用：

```text
claude -p <prompt>
  --permission-mode bypassPermissions
  --model <model>
  --mcp-config <browser config>
  --add-dir <repo> --add-dir <state dir>
  --output-format stream-json --verbose
```

但尚未明確採用：

```text
--strict-mcp-config
--setting-sources
--disable-slash-commands
--tools / --disallowedTools
--no-session-persistence
```

因此每輪可能載入與掃帶無關的 user settings、hooks、skills、其他 MCP 或內建工具能力。

### 2.2 每輪強制重讀大量規則

目前開工 prompt 要求完整讀取：

| 檔案 | 字元數（抽查時） | 用途 |
|---|---:|---|
| `scripts/s2_scan_prompt.md` | 5,226 | 本輪入口與收工流程 |
| `common/13-S2-定時掃帶.md` | 52,747 | 內容格式與完整歷史規則 |
| `common/13c-S2-定時掃帶-v3省token.md` | 33,288 | V3 執行規則 |
| **合計** | **約 91,261** | 每輪要求完整讀取 |

`13` 同時包含規格演進、舊版敘事及大量目前由腳本承擔的流程；`13c` 已聲明只保留訂正後最終態。兩者同時全讀，會讓模型每輪重新消化歷史與衝突。

### 2.3 成本主因已從「規則長度」轉為「模型往返數」

`13c` 已記錄真實案例：0811-2000 一輪 67 次 Bash，其中 22 次臨時查詢、12 次臨時批改。規則精簡只降低約 16%，卻被工具呼叫增加抵銷。

每次工具呼叫後都會再產生一次模型請求；即使命中 prompt cache，cache read 仍有費用，也會增加 latency 與 output thinking。

### 2.4 Prompt 存在過時衝突

`s2_scan_prompt.md` 仍有建檔輪自行從 Archive 前一檔 checkpoint 推算 `window_start` 的敘述；現行 `13c` 與 `s2_scan.ps1` 已改由建檔腳本固定處理。此類衝突會同時造成：

- 額外 Token。
- 模型每輪重新判斷誰優先。
- 低 effort 時更高的字面誤執行風險。

### 2.5 Prompt caching 不是目前第一優先

Anthropic prompt caching 是精確 prefix match，渲染順序為：

```text
tools → system → messages
```

因此 checkpoint 位於 user prompt 開頭，**不必然**破壞 tools／system 層快取；真正要從 JSONL 的 `cache_creation_input_tokens` 與 `cache_read_input_tokens` 判斷。不能只靠「每輪文字不同」推論整個 cache 失效。

現況應先縮小固定前綴與模型 request 數，再研究 cache TTL／預熱。若固定前綴本身過大，持續付 cache read 仍然昂貴。

---

# 二、方案比較

## 方案 A：精簡 Agent 外殼與按需規則（推薦）

**內容：**

- 建立 S2 專用最小 Claude Code 啟動設定。
- 限定唯一 browser MCP、必要內建工具與設定來源。
- 停用 skills／slash commands／Agent／AskUserQuestion 等固定輪不會用的能力。
- 把規則分成 core、NS、AP、RT、fallback、建檔輪、YouTube、側錄等 shards。
- 合併機械型 state 查詢與收工步驟，降低模型往返。

**優點：** 不改三站內容判斷與 Sonnet 能力，品質風險最低。

**缺點：** 需要先做 cache／工具基線，避免誤關必要能力。

**建議：** 立即排第一順位。

## 方案 B：Deterministic Collector

**內容：**

- 三站 fetch、retry、schema 驗證、diff、去重、瘦身、原文落檔改由固定程式完成。
- Collector 產生統一 `source_batch.json`。
- LLM 一次只處理本輪新增素材的中文三段式、語意分類、重大性與少數例外。

**優點：** 中長期 Token 節省最大，也最容易觀測每站是否完整。

**缺點：** 涉及三站易變 API 與登入態，需要 shadow mode，工程量最高。

**建議：** 方案 A 穩定後進行。

## 方案 C：模型／effort 分流

**內容：**

- 例行、完整、低歧義批次使用較低 effort 或 Haiku。
- 規則衝突、BITE 歧義、重大性、分類收斂與 recovery 升級 Sonnet。

**優點：** 可再降低 output 與 thinking 成本。

**缺點：** 模型切換會切斷 prompt cache；另開 invocation 也有冷啟動成本。若前綴尚未瘦身，可能省小錢、付更大的啟動費。

**建議：** 最後才做。現行 working copy 已出現 `medium` effort 修改，應先量測，不再同時引入 Haiku。

---

# 三、分階段執行計畫

## Task 1：建立 Token 與品質基線

**Files:**

- Modify: `E:\GitHub\TVBS-AIHunter\scripts\s2_scan.ps1`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_log_metrics.py`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\test_s2_log_metrics.py`
- Output: `D:\Downloads\S2掃帶log\_token_metrics.jsonl`

**Interfaces:**

- Consumes: Claude Code `--output-format stream-json --verbose` JSONL log。
- Produces: 每輪一列、不含新聞內容的量測紀錄。

### Metrics schema

```json
{
  "checkpoint": "0812-0030",
  "model": "claude-sonnet-5",
  "effort": "medium",
  "requests": 0,
  "tool_calls": 0,
  "tool_calls_by_name": {},
  "input_tokens": 0,
  "cache_creation_input_tokens": 0,
  "cache_read_input_tokens": 0,
  "output_tokens": 0,
  "elapsed_minutes": 0.0,
  "new_items": 0,
  "reconcile_missing": 0,
  "audit_red": 0,
  "audit_yellow": 0,
  "exit_code": 0
}
```

- [ ] **Step 1：先固定目前 working tree 狀態**

執行：

```powershell
git -C "E:\GitHub\TVBS-AIHunter" status --short --branch
git -C "E:\GitHub\TVBS-AIHunter" diff -- scripts/s2_scan.ps1
```

預期：明確辨認既有 `Effort=medium` 修改的來源與是否正在被排程直接使用；不得用本計畫內容覆蓋。

- [ ] **Step 2：寫 JSONL parser 測試**

測試 fixture 必須覆蓋：

1. 同一 message ID 在 stream 中出現多次，只計最後一筆 usage。
2. `assistant` message 無 usage 時不報錯。
3. tool use 依 `name` 統計。
4. log 含 hook event 時忽略新聞文字，只輸出數字。
5. 破損 JSON 行跳過並記 `invalid_lines`。

- [ ] **Step 3：執行 parser 測試**

```powershell
python -m pytest "E:\GitHub\TVBS-AIHunter\scripts\test_s2_log_metrics.py" -v
```

預期：全部 PASS。

- [ ] **Step 4：從既有 log 建基線**

只在使用者授權讀取 S2 session log 後執行；輸出只留聚合數字，不複製 prompt、稿件或憑證。

```powershell
python "E:\GitHub\TVBS-AIHunter\scripts\s2_log_metrics.py" `
  --log-dir "D:\Downloads\S2掃帶log" `
  --out "D:\Downloads\S2掃帶log\_token_metrics.jsonl"
```

- [ ] **Step 5：至少收集代表性輪次**

必須包含：一般輪、安靜輪、大量新增輪、單站失敗輪、16:00 建檔輪。每一類至少一輪，不以單次 cache write 推估每日平均。

- [ ] **Step 6：基線驗收**

確認每輪均能回答：

- 固定前綴寫入／讀取多少？
- 共幾次模型 request？
- 哪些工具呼叫最多？
- 每新增一則素材平均多少 input／output Token？
- 0 則輪是否真的三站無素材，還是來源失守？

- [ ] **Step 7：獨立提交**

提交只包含量測器與測試，不改掃帶語意。

---

## Task 2：建立 S2 最小 Claude Code 啟動設定

**Files:**

- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_claude_settings.json`
- Modify: `E:\GitHub\TVBS-AIHunter\scripts\s2_scan.ps1`
- Test: `E:\GitHub\TVBS-AIHunter\scripts\test_s2_launcher.ps1`

**Interfaces:**

- Consumes: `s2_scan_prompt.md`、`s2_mcp.json`、現有 auth。
- Produces: 與現行流程等價，但只載入 S2 必要能力的 `claude -p` invocation。

- [ ] **Step 1：建立四組 DryRun／TestMode 對照**

```text
A0 現行旗標
A1 + --strict-mcp-config
A2 + --disable-slash-commands
A3 + 最小 settings／tools／setting-sources
```

每次只增加一個變因，不能一次全開，否則無法定位工具消失或 cache 變化原因。

- [ ] **Step 2：先測 `--strict-mcp-config`**

目標：只載入 `scripts/s2_mcp.json` 的 browser MCP，不載入其他 scope 的 MCP。

驗收：browser `navigate`、`evaluate`、`snapshot/find`、`close` 均可呼叫。

- [ ] **Step 3：測試停用 slash commands／skills**

加入：

```text
--disable-slash-commands
```

驗收：固定掃帶無需任何 skill；三站與 state 指令照常完成。

- [ ] **Step 4：限制內建工具面**

候選保留：

```text
Bash, Read
```

候選停用：

```text
Agent, AskUserQuestion, Edit, Write, NotebookEdit, WebSearch, WebFetch
```

檔案落地若現行流程依賴 Write，先保留；待 Collector／batch helper 可承接後再移除。MCP browser 不與 `--tools` 混為一談，必須實測。

- [ ] **Step 5：測試 `--setting-sources`**

依序測：

```text
project
project,local
```

比較 SessionStart hook、全域 memory、skills 描述與權限行為。若 user source 是 auth 或必要 hook 的唯一來源，不採用此刀；不要為省 Token 破壞登入或防護。

- [ ] **Step 6：評估 `--no-session-persistence`**

S2 每輪本來就是拋棄式 `-p` session，若不依賴 `/resume` 或 session 歷史，測試停用 persistence 是否能減少 session 管理成本。此旗標不應改變模型 prompt；只在結果等價時保留。

- [ ] **Step 7：排除 `--bare`**

現階段不採用，因為 `--bare` 會停止 OAuth／keychain 讀取，與目前 Claude CLI 登入方式可能衝突。只有未來改成專用 API key helper 且另做安全審查時才重評。

- [ ] **Step 8：比較每組冷啟動數字**

至少比較：

- 首次 `cache_creation_input_tokens`
- 後續 `cache_read_input_tokens`
- 第一個業務 tool call 前的 request 數
- 啟動秒數
- 工具可用性

- [ ] **Step 9：上線門檻**

只有在三站皆能走完 TestMode、audit／render 完整、Token 指標下降時才更新正式啟動器。

---

## Task 3：清理現行 prompt 衝突，不先大砍規則

**Files:**

- Modify: `E:\GitHub\TVBS-AIHunter\scripts\s2_scan_prompt.md`
- Modify: `E:\GitHub\TVBS-AIHunter\common\13-S2-定時掃帶.md`
- Modify: `E:\GitHub\TVBS-AIHunter\common\13c-S2-定時掃帶-v3省token.md`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\test_s2_prompt_contract.py`

**Interfaces:**

- Produces: 單一現行規則來源、無互相矛盾的啟動 prompt。

- [ ] **Step 1：建立衝突清單**

至少檢查：

- `window_start` 由誰設定。
- 建檔輪由 agent 還是 `s2_scan.ps1` 建 state。
- 現行規則讀 `13c` 還是 `13b`。
- pending 中繼輪是否每輪全查。
- txt 是增量人工整併還是 state 全量 render。
- NS 保活由 agent 還是獨立排程負責。
- 23:00 是否為終止點。

- [ ] **Step 2：讓 `s2_scan_prompt.md` 只保留本輪參數與不可省略 gate**

保留：

- checkpoint
- fixed scan order
- 無人值守禁止停問
- 收工驗收
- 當輪特例

移除已由腳本保證、且規則檔已有唯一真相源的歷史敘述。

- [ ] **Step 3：將 `13` 的執行層舊敘述標成非現行**

不可刪除格式、分類、三段式、重大性等內容規則；只處理已由 `13c` 或腳本取代的執行說明，避免排程 agent 誤讀。

- [ ] **Step 4：建立 prompt contract test**

測試必須確認：

```text
現行 prompt 不再指示讀 13b
現行 prompt 不再要求 agent 自建 state
window_start 只有一個權威定義
規則中仍存在 NS→AP→RT
規則中仍存在 no taskkill／no AskUserQuestion
規則中仍存在 audit＋三站 reconciliation
```

- [ ] **Step 5：先跑 replay，不直接上排程**

用歷史 state／snapshot 模擬開工與收工，確認模型不會因移除歷史敘述而漏掉 gate。

---

## Task 4：規則分片與按需載入

**Files:**

- Create: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\00-core.md`
- Create: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\10-ns.md`
- Create: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\20-ap.md`
- Create: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\30-rt.md`
- Create: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\40-state-batch.md`
- Create: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\50-render-audit.md`
- Create: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\60-recovery.md`
- Create: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\70-optional-inputs.md`
- Create: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\manifest.json`
- Modify: `E:\GitHub\TVBS-AIHunter\scripts\s2_scan_prompt.md`
- Test: `E:\GitHub\TVBS-AIHunter\scripts\test_s2_rule_shards.py`

**Interfaces:**

- `00-core.md` 每輪必讀。
- 各站開始前只讀本站 shard。
- `60-recovery.md` 只有 API／DOM 路徑失敗或工具輸出卸載時讀。
- `70-optional-inputs.md` 只有 YouTube、側錄、ENEX／ABC 人工特例時讀。

- [ ] **Step 1：建立 manifest**

每個 shard 記錄：

```json
{
  "id": "s2-ns-runtime",
  "path": "common/s2-runtime/10-ns.md",
  "version": "2026-08-12",
  "applies_when": ["source:NS"],
  "supersedes": [],
  "sha256": "由驗證腳本產生"
}
```

`sha256` 必須由測試／建置步驟實算，不能手填假值。

- [ ] **Step 2：只搬訂正後最終態**

每條規則必須可追溯回 `13` 或 `13c`；不搬事故敘事、過時版本與已被程式保證的重複說明。

- [ ] **Step 3：建立完整性對照測試**

建立高風險規則清單並 assert 存在於某個 shard：

- 三站入口與順序
- NS token 不離開頁面
- AP PageSize 16
- RT 虛擬捲動與 Load More 判準
- BITE 機械欄位
- pending
- src_text
- state batch
- audit reconciliation
- no kill／no ask

- [ ] **Step 4：進行 A/B replay**

A 組讀完整 `13 + 13c`；B 組只讀 core＋必要 shards。比較 normalized state mutation，而不是只比較文字回覆。

- [ ] **Step 5：上線門檻**

B 組必須同時達成：

- 清單 ID 集合一致。
- state delta 一致。
- BITE 標記一致。
- pending 一致。
- audit 結果不比 A 組差。
- 規則輸入 Token 下降至少 40%。

---

## Task 5：合併機械型 prepare／finalize 操作

**Files:**

- Modify: `E:\GitHub\TVBS-AIHunter\scripts\s2_state.py`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_round.py`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\test_s2_round.py`
- Modify: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\40-state-batch.md`
- Modify: `E:\GitHub\TVBS-AIHunter\common\s2-runtime\50-render-audit.md`

**Interfaces:**

### `prepare` output

```json
{
  "state_file": ".../0812-s2-state.json",
  "checkpoint": "0812-0030",
  "window_start": "0811-2200",
  "scratch_dir": ".../20260811",
  "pending_ids": [],
  "needs_review": [],
  "existing_ids_by_source": {"NS": [], "AP": [], "RT": []},
  "optional_inputs": []
}
```

### `finalize` output

```json
{
  "reclass": {"status": "skipped|applied|failed"},
  "ingest_check": {"status": "passed|failed", "missing": []},
  "topic_review": {"status": "passed|needs_changes"},
  "render": {"status": "passed|failed"},
  "audit": {"status": "passed|failed", "red": 0, "yellow": 0},
  "reconcile": {"NS": {}, "AP": {}, "RT": {}},
  "ns_keepalive": {"status": "passed|logged_out|blocked"}
}
```

- [ ] **Step 1：先寫冪等測試**

同一 checkpoint 連跑兩次 `prepare`，不得改 state；同一組 reconciliation 重跑，不得產生重複紀錄或破壞其他站資料。

- [ ] **Step 2：實作 `prepare` 的單次聚合輸出**

它只呼叫既有 `s2_state` 函式／介面，不自行發明第二套 state parser。

- [ ] **Step 3：將 finalize 分成明確子步**

`finalize` 可以是一個 CLI invocation，但每個子步要有獨立 status、原始錯誤摘要與是否已改 state，不能只回一個 boolean。

- [ ] **Step 4：處理 audit 是寫入操作**

`s2_audit.py` 會更新 `_top.reconcile_log`；測試必須涵蓋：

- 重跑同站。
- 前一次只有 RT，後一次補 AP／NS。
- audit 中斷後重新執行。
- state 在 audit 前被其他程序改動。

- [ ] **Step 5：加入 optimistic concurrency**

`prepare` 回傳 `state_hash`；任何 finalize 寫入前核對 hash 或 state revision。若不同，重新讀取並合併，不准用舊 snapshot 整份覆蓋。

- [ ] **Step 6：量測模型 request 降幅**

以 Phase 0 基線比較：

- unique model requests
- Bash／Read calls
- cache read tokens
- wall-clock time

目標先設定為模型 request 降低 30%；若品質等價且仍有大量零散呼叫，再進一步調整。

---

## Task 6：三站 Collector 統一資料契約與 shadow mode

**Files:**

- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_collectors\contract.py`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_collectors\ns.py`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_collectors\ap.py`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_collectors\rt.py`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_collectors\validate.py`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_collectors\shadow_compare.py`
- Test: `E:\GitHub\TVBS-AIHunter\scripts\tests\test_s2_collectors.py`

**Interfaces:**

Collector 不直接寫正式 state，只產生：

```json
{
  "source": "NS",
  "checkpoint": "0812-0030",
  "parser_version": "1",
  "list_snapshot": "path",
  "items": [
    {
      "id": "IN-02TU",
      "title": "...",
      "script": "...",
      "description": "...",
      "duration": "...",
      "script_status": "has_script",
      "footage_type": "SOT",
      "sb_count": null,
      "has_sot": null,
      "prelim": false,
      "source_meta": {},
      "src_text": "站方瘦身原文",
      "warnings": []
    }
  ]
}
```

- [ ] **Step 1：先凍結歷史 fixtures**

使用既有 scratch／archive 中已落地的瘦身資料；fixture 必須去除所有憑證。涵蓋正常、空清單、schema drift、preliminary、長整理包、無 BITE、pending 與重複 ID。

- [ ] **Step 2：實作 contract validator**

必填欄位缺失時整批不得直接進 LLM；應標示 source、item id、缺失欄位與原始 snapshot path。

- [ ] **Step 3：逐站實作，不同站分開切換**

順序建議：

1. NS：現有 API 最完整、收益最大。
2. AP：detail 雖需逐 item request，但可單一 evaluate 批量執行。
3. RT：清單虛擬捲動與格式漂移較多，最後處理。

- [ ] **Step 4：bounded retry**

同一階段最多依現行規則重試兩次；validation error 不用原輸入重試，直接進 fallback 或 `needs-review`。

- [ ] **Step 5：shadow compare 四層結果**

比較：

1. list ID 集合
2. normalized fields
3. 預期 state delta
4. render output

不能只比 txt。

- [ ] **Step 6：逐站 rollout**

每站依序：shadow → 1 輪 TestMode → 3 個正常完整輪 → 正式啟用。任一站可獨立回退現行 V3，不拖累其他站。

---

## Task 7：讓 LLM 只處理 normalized delta

**Files:**

- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_enrich_prompt.md`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_enrich_schema.json`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_enrich.py`
- Test: `E:\GitHub\TVBS-AIHunter\scripts\tests\test_s2_enrich.py`

**Interfaces:**

- Consumes: Collector 已驗證的 `source_batch.json`。
- Produces: 可直接交給 `add-batch` 的 entries，以及需升級／人工處理的 exceptions。

### Output schema

```json
{
  "entries": [
    {
      "id": "RT2333",
      "source": "RT",
      "checkpoint": "0812-0030",
      "status": "has_script",
      "entry": "三段式成品",
      "category": {"大分類": "...", "中主題": "...", "小分題": "..."},
      "importance": "normal|yellow|red",
      "sb_count": 1,
      "footage_type": null,
      "src_text_ref": "來源檔中的 item key"
    }
  ],
  "exceptions": []
}
```

- [ ] **Step 1：採 structured output**

不要再讓 agent 自行寫臨時 `batch.json` 格式；使用 JSON Schema 驗證。Schema failure 不直接寫 state。

- [ ] **Step 2：一批一次生成**

同站或同輪多則素材一次送入，避免每則一個模型回合。若批次過大，以字元／token 計數分塊，但保留每一 item id。

- [ ] **Step 3：保留語意任務**

LLM 只負責：

- 中文摘要
- 畫面描述
- BITE 濃縮與講者
- 中／小分題
- 重大性
- 有歧義的素材形態

下列保持程式處理：ID、duration、去重、`sb_count`、`footage_type`、pending、對帳、render、audit。

- [ ] **Step 4：建立 non-inferiority eval**

從歷史已人工修正案例建立標準答案，至少評估：

- 收錄／排除
- BITE 有無
- BITE 講者
- pending
- 大分類
- 臺灣至少 🟡
- 🔴 前三名

- [ ] **Step 5：先維持 Sonnet 5**

Collector 與 normalized delta 上線後，先量測 Sonnet 5 的新成本；不要同時切模型，避免無法歸因。

---

## Task 8：effort 與模型分流實驗

**Files:**

- Modify: `E:\GitHub\TVBS-AIHunter\scripts\s2_scan.ps1`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\s2_route.py`
- Create: `E:\GitHub\TVBS-AIHunter\scripts\tests\test_s2_route.py`
- Output: `D:\Downloads\S2掃帶log\_model_route_metrics.jsonl`

**Interfaces:**

- Consumes: validated normalized batch 與 ambiguity flags。
- Produces: `sonnet-medium`、`sonnet-high` 或未來 `haiku` 的可解釋路由決策。

- [ ] **Step 1：先評估現有 `medium` effort 修改**

因 working copy 已有此修改，先比較修改前後可取得的完整輪次，不再疊加其他模型變因。

觀測：

- output tokens
- tool call 數
- 漏收
- BITE 修正
- 分類修正
- audit 紅項
- 每則成本

- [ ] **Step 2：定義升級條件**

以下直接使用 Sonnet high，或在未來 Haiku 路徑中升級 Sonnet：

```text
schema 缺欄
規則衝突
source schema drift
BITE 不確定
重大性不確定
臺灣關聯
大型 timeline／wrap
單站 partial failure
retry recovery
分類收斂
state／collector 不一致
```

- [ ] **Step 3：Sonnet medium non-inferiority**

至少連續多個完整輪次無高嚴重度退化，才把 medium 視為正式預設；不能只看 output token 下降。

- [ ] **Step 4：最後才做 Haiku shadow**

Haiku 只處理低歧義 normalized batch，不直接操作 browser、不做 recovery、不做最終重大性拍板。

- [ ] **Step 5：計入冷啟動與 cache 斷裂成本**

成本比較必須包含：

```text
Haiku invocation 冷啟動
Haiku input/output
升級 Sonnet 的第二次冷啟動
兩模型無法共享 prompt cache
```

若升級率過高，維持單一 Sonnet session 反而更省。

---

## Task 9：評估 Message Batches 的有限適用範圍

**Files:**

- Create only if adopted: `E:\GitHub\TVBS-AIHunter\scripts\s2_offline_batch.py`
- Test only if adopted: `E:\GitHub\TVBS-AIHunter\scripts\tests\test_s2_offline_batch.py`

**Interfaces:**

- 僅處理非即時、彼此獨立的離線工作。

- [ ] **Step 1：排除正常固定輪掃帶**

正常掃帶需要 browser state、順序、fallback、即時 state mutation 與 audit，不適合 Message Batches。

- [ ] **Step 2：候選工作**

只有下列工作值得評估：

- 隔日分類收斂建議
- 歷史 corpus 離線重評
- 多個獨立 prompt 的成本 eval
- 不影響當輪交接的品質研究

- [ ] **Step 3：正確理解收益**

Batches 可降低 API 計價，但**不會降低 Token 數**，也不會自動解決規則過長或重複上下文。若流程仍透過 Claude Code subscription CLI，而非直接 Anthropic API，則不應為了 Batches 額外改架構。

---

# 四、Prompt caching 專項計畫

## 1. 先觀測四種時間間隔

比較相同 prompt／tools 前綴在：

```text
5 分鐘內
1 小時內
超過 1 小時
隔日
```

的：

- `cache_creation_input_tokens`
- `cache_read_input_tokens`
- `input_tokens`

## 2. 檢查 silent invalidators

檢查工具與 system 前綴是否包含：

- timestamp
- UUID
- 不固定排序的工具／JSON key
- 每輪變動的 user path
- 條件式 tools
- 模型切換

## 3. 不優先做 cache pre-warm

只有同時符合下列條件才評估預熱：

1. 第一個真實請求 latency 明顯影響排程。
2. 固定前綴仍然很大。
3. 能在真正輪次前可靠執行。
4. 預熱不會與 Playwright profile／掃帶鎖衝突。

S2 是背景排程，第一個 token latency 對使用者不敏感；預熱會多付一次 cache write，因此優先度低於縮前綴與減 request。

---

# 五、品質驗收矩陣

| 指標 | 上線門檻 | 自動回退條件 |
|---|---|---|
| 窗內漏收 | 不高於現行 V3 | 新增任何高嚴重度漏收 |
| 三站 reconciliation | 三站都有本輪證據，或明確 needs-review | 無聲缺站 |
| false BITE | 不增加 | 稽核或人工發現增加 |
| missed BITE | 不增加 | `sb_count/footage_type` 與成品不一致增加 |
| pending | 正確轉 has_script；天生無稿者不堆 pending | pending 無限堆積或正式稿未覆寫 |
| `src_text` | 每筆保留瘦身站方原文，零污染 | 缺失、混入 agent 說明、殘留憑證 |
| state/render | 一致 | render 遺失 state item 或 txt 出現 state 無資料 |
| audit | 紅項不得增加 | audit 未跑、無留痕或重跑破壞 state |
| retry | 有上限、可冪等恢復 | 重複寫入、同一步無限重試 |
| Token | 每階段達到其預期降幅 | 成本不降且 complexity 增加 |
| latency | p95 不惡化 | 大幅變慢或撞下一輪鎖 |

---

# 六、Rollout 與回退

## Rollout 順序

```text
歷史 replay
→ shadow mode
→ TestMode
→ 1 個正式輪次
→ 3 個連續正式輪次
→ 一個完整班次
→ 全量
```

不採固定 1% 流量，因 S2 每輪量少且有明確 checkpoint；以「輪次」作 rollout 單位更可觀測。

## 每階段 feature flag

建議旗標：

```text
S2_MINIMAL_BOOTSTRAP
S2_RULE_SHARDS
S2_ROUND_HELPER
S2_COLLECTOR_NS
S2_COLLECTOR_AP
S2_COLLECTOR_RT
S2_STRUCTURED_ENRICH
S2_MODEL_ROUTING
```

每個旗標預設 false；新路徑失敗時立即回現行 V3，而不是再由 agent 現場發明補救流程。

## 回退原則

- Collector 可逐站回退。
- 規則 shards 可回讀完整 `13 + 13c`。
- 最小啟動設定可移除新增 CLI flags。
- medium effort 可明確指定回 high。
- Haiku 路由可整體關閉，回單一 Sonnet。
- 不刪除現行 V3 規則與腳本，直到新路徑通過完整班次且有人工確認。

---

# 七、建議優先順序與預期價值

| 優先 | 工作 | 風險 | 預期 Token 效果 |
|---:|---|---|---|
| 1 | 基線量測器 | 極低 | 讓後續每刀可歸因 |
| 2 | 最小 Claude Code 啟動設定 | 低 | 冷啟動固定前綴明顯下降 |
| 3 | 清理 prompt 衝突 | 低 | 減少無效輸入與誤執行 |
| 4 | 規則 shards | 低至中 | 規則輸入預期下降 40–75% |
| 5 | prepare／finalize helper | 中 | 模型 request 預期下降約 30% 起 |
| 6 | NS Collector | 中 | 避免採集過程與大結果進 context |
| 7 | AP Collector | 中 | 降低 detail 往返與 retry |
| 8 | RT Collector | 中至高 | 長期收益高，但站點變化風險最大 |
| 9 | structured batch enrichment | 中 | 多則一次生成，減少逐則模型回合 |
| 10 | effort／模型分流 | 中至高 | 視升級率而定，最後評估 |
| 11 | Message Batches | 低但用途有限 | 只降離線 API 計價，不降 Token 數 |

---

# 八、明確不建議事項

1. **不要再單純刪短 `13c`**：實測已顯示 request 次數比規則長度更主導成本。
2. **不要立即整輪改 Haiku**：品質風險與第二次冷啟動可能抵銷節省。
3. **不要為快取頻繁預熱**：S2 是背景工作，預熱主要省 latency，未必省成本。
4. **不要把三站並行交給多 agent**：會重複載入前綴、增加 context，且 Playwright profile 互鎖。
5. **不要把全部 finalize 包成無細節黑盒**：部分失敗時無法知道哪些 state mutation 已生效。
6. **不要只用 exit code 0 判完成**：必須同看清單對帳、state、render、audit。
7. **不要只比較最後 txt**：Collector 驗收必須比較清單、normalized fields、state delta 與 render 四層。
8. **不要在同一階段同時改 prompt、collector、effort、model**：否則無法判斷品質或成本變化來源。

---

# 九、最終建議

品質零退步前提下，S2 V3 下一輪主線應是：

```text
先建立可信基線
→ 瘦 Claude Code 冷啟動外殼
→ 清除 prompt 衝突
→ 按站／例外載入規則
→ 合併機械工具往返
→ Collector shadow mode
→ LLM 只讀 normalized delta
→ 最後才調 effort 與模型分流
```

前五項不需要降低新聞判斷模型能力，是最安全的首波；Collector 是中長期最大收益；模型降級則只有在 normalized input、完整 quality gate 與低升級率都成立後才值得採用。

本文件是評估與執行計畫，未授權也未包含對 AIHunter 程式、設定或排程的實際修改。
