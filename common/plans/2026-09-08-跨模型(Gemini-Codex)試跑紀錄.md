# S2 跨模型（Gemini／Codex）試跑紀錄

- **背景**：使用者本機已有三組獨立 CLIProxyAPI 代理（`claudeg`=Gemini／Antigravity OAuth，
  `claudex`=Codex／OpenAI OAuth，`claudek`=Grok／xAI OAuth），詢問 S2 定時掃帶能否改接
  Gemini 或 Codex。本次為第一次實測試跑，非正式換線決策。
- **做法**：直接把 `s2_scan.ps1` 最終呼叫的 `claude @claudeArgs` 包一層對應代理的
  `ANTHROPIC_BASE_URL`／`ANTHROPIC_API_KEY`／`ANTHROPIC_AUTH_TOKEN` 環境變數（比照
  `claudeg.ps1`／`claudex.ps1` 的做法），`--model` 換成對應代理的模型名稱，其餘完全比照
  正式排程參數（`--mcp-config s2_mcp.json`、`--add-dir`、guard settings、V8 prompt 全套不動）。
  每次試跑前都先備份當時的 `0907-s2-state.json` 到
  `D:\Downloads\S2掃帶log\claudeg試跑備份\`。

## 嘗試 1：claudeg（Gemini `gemini-pro`）— 失敗，配額冷卻

`checkpoint=0907-1200-claudeg試跑`，全站 V8 流程（NS/AP/RT/ENEX/ABC）。69 秒即終止，
離開碼=1。實際錯誤：

```
API Error: Request rejected (429) · All credentials for model gemini-pro are cooling down
(last error: {"error":{"code":429,"message":"Resource has been exhausted (e.g. check quota).","status":"RESOURCE_EXHAUSTED"}})
```

未進入任何 S2 流程步驟，狀態檔完全未被觸碰。

**後續**：使用者指定改用模型 `gemini-3.8-flash-high[1m]`。`cliproxyapi-gemini\config.yaml`
原本 `oauth-model-alias.antigravity` 只有兩條（`gemini-pro-agent`→`gemini-pro`、
`gemini-3-flash-agent`→`gemini-flash`），新增第三條 `name`/`alias` 皆為
`gemini-3.8-flash-high[1m]`（直接透傳，未知真實 upstream 內部代號是否需要轉換），
同步把 `claudeg.ps1` 的 `$Model` 預設值一併改掉，重啟 `CLIProxyAPI-claudeg` 排程任務。

連通測試（非 S2 全流程，僅 `claude -p "..." --model "gemini-3.8-flash-high[1m]"`）仍持續
429 quota。查 `cliproxyapi-gemini\server.log` 證實請求確實送達 upstream（
`auth=provider=antigravity auth_file=antigravity-moonriver0523@gmail.com.json`），proxy 端
會把 `[1m]` 後綴自動剝除、實際送給 upstream 的模型名是 `gemini-3.8-flash-high`（不含
`[1m]`），upstream 連續多次回 `429 RESOURCE_EXHAUSTED reason=quota`。使用者確認整體
Antigravity 訂閱配額是滿的（非帳號用量爆表），代表問題大概率出在
**`gemini-3.8-flash-high` 這個模型 ID 本身**——可能拼寫需要核對，或這個 preview／高階
變體在 Antigravity 端本身是獨立且很小的限流池，跟 `gemini-pro`／`gemini-flash` 不共用配額。
**尚未解決，待使用者核對正確模型 ID 或等配額狀態改變後重試。**

## 嘗試 2：claudex（Codex `gpt-5.6-sol[1m]`）— 跑完但 0 則寫入，checkpoint 格式不合法

`checkpoint=0907-1200-claudex試跑`（沿用嘗試 1 的中文後綴命名習慣）。連線／瀏覽／分類
判斷全部正常（依序處理 NS→AP→RT，正確判斷 12:00 這個 checkpoint 不屬於 ENEX/ABC 既定
掃描點而略過），跑滿 22.2 分鐘、離開碼=0，但最終「本輪新增=-1 則、txt=False」。

**根因**：`scripts/s2_state.py` 的 `CHECKPOINT_RE = re.compile(r"^\d{4}-\d{4}$")` 要求
checkpoint 必須是**嚴格 8 位純數字**（`MMDD-HHMM`），**不接受任何文字後綴**。agent 嘗試
`add-batch` 時因 checkpoint 格式不合法被拒絕，最終只留一筆 `needs-review`：
「add-batch 在 v版 checkpoint 驗證前已有重複主題（烏俄戰爭／托爾巴欣），本輪新增 0
則；請修正 checkpoint 驗證相容性」。**這是本次操作者（人類）checkpoint 命名方式的錯，
與 claudex／Codex 模型能力無關**——狀態檔沒有被寫壞，只多了一筆 needs-review。

**附帶查證**：順手用 `Get-ScheduledTask -TaskName 'S2掃帶'` 即時查了目前真實生效的排程
觸發點（repo 文件已知會過期，見 `common/plans/S2-MASTER-追蹤清單.md` 引用的
`feedback_s2_schedule_query_live` 教訓）：`04:30／07:00／11:00／17:00／20:00／22:00／
01:00`，**11:00–17:00 之間本來就是空窗，沒有 12:00/13:00 這個排程點**。本次兩次試跑
（嘗試 1、2）皆未搶占或拖累任何正式輪次；`0907-s2-state.json` 在今天（0908）17:00
建檔輪之前都是目前唯一的 live state，不論 checkpoint 標記的 MMDD 是幾號，只要在 17:00
前跑都會寫進這份、render 出 `0907晚班交接.txt`。

## 嘗試 3：claudex（Codex `gpt-5.6-sol[1m]`）— 成功

改用合規的純數字 checkpoint `0908-1200`（順著當時頂層 checkpoint `0908-1100` 自然推
進，同時填補上述查明的 11:00–17:00 排程空窗）。離開碼=0，耗時 27.3 分，**本輪新增
39 則**，`txt=True`，殼層檢查無任何異常標記（無漏站、無 checkpoint 問題、無對帳缺口
警告）。`0907晚班交接.txt` 已於 15:10 重新 render（284KB，較試跑前的 269KB 增大，
與新增 39 則量級相符）。

## 結論與待辦

1. **claudex（Codex `gpt-5.6-sol[1m]`）技術上可行**：完整跑通一輪 V8 全站流程，
   連線、瀏覽器操作、分類判斷、checkpoint/set-top、render 全部正常，無需修改 S2 prompt
   或流程本身，只要把 `claude` CLI 包一層代理環境變數即可。**尚未做的**：把這 39 則
   跟同時段 sonnet 產出的品質做人工比對（用字、分類準確度、TC 標註、BITE 判斷等），
   在有這份比對之前不建議視為「可換線」的結論，僅證明「流程通」。
2. **claudeg（Gemini）目前卡住**：`gemini-pro` 遇配額冷卻、使用者指定的
   `gemini-3.8-flash-high[1m]` 疑似模型 ID 或該變體本身限流，尚未跑通任何一輪。
3. **checkpoint 命名教訓**：往後任何非正式（人工手動）試跑，checkpoint 一律用純數字
   `MMDD-HHMM` 格式，不要加文字後綴（`s2_state.py` 的 `CHECKPOINT_RE` 不接受）；要標記
   「這是試跑」可以選一個明顯不落在正式排程整點上的 HHMM，或事後在 needs-review／
   `_輪次紀錄.txt` 額外補一行文字說明，不要塞進 checkpoint 本身。
4. 本次操作全程走 `s2_scan.ps1` 既有互斥鎖／備份／log 機制，未新增任何腳本層修改；
   `cliproxyapi-gemini\config.yaml`／`claudeg.ps1` 的模型別名調整見上文，兩檔已各自
   留有 `.bak-*` 備份。
