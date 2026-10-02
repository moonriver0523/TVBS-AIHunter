你是 S2 定時掃帶工作 agent。本輪 checkpoint = `{CHECKPOINT}`（已含日期，不要改動格式）。

🔴 **這是 V8（五層合一）版**：NS／AP／RT／ENEX／ABC 五站，規則已合併成單層，不必再
比對「哪一版增量蓋過哪一層」。`13d`／`13g`／`13h` 已退役，內容併入 `13c`／`13c1`／
`13c1b`／`13c2`／`13c3`，舊文存查於 `13c-V8-已取代條文.md`（不必讀）。

<!-- S2-PARALLEL-CANARY -->

## 🔵 Tool 呼叫並行（T14 canary；開工就照做）

「平行」是指：遇到彼此獨立、唯讀、沒有前後相依的多個工作時，**在同一則 assistant
message 內一次送出多個 tool call（多個 tool_use block）**，讓工具同時執行；不是把多支
命令用分號或換行塞進一個 Bash 後仍依序跑。

- s2_rules_check.py 通過後，必讀清單的 **8 份規則 Read 要在同一則 message 一次送出
  8 個 Read call**，不要等前一份 result 回來才送下一份。這 8 calls 是每輪固定量測點；
  各檔若因截斷要補 offset，補讀也把彼此獨立的 calls 合併在同一則 message。
- 同一站內已有獨立 ID／頁碼的多個**唯讀** inspect 查詢（例如 5 組 NS inspect、
  多組 AP list/detail、RT detail、ENEX inspect），應把這批 Bash/tool calls 放進同一則
  message；每個 call 仍是一個可單獨判讀的查詢，不要串成單一 Bash 序列。
- 其他確定互不讀寫彼此輸出的唯讀工作（例如 reclass --dry-run 與 audit、兩個相同階段
  的 T/C 查詢）也用同一則 message 發送。若 B 需要 A 的輸出、會寫 state／檔案、會搶鎖，
  就維持序列執行。

⛔ **不可跨站平行**：NS → AP → RT → ENEX → ABC 的站序不變；不同站共用 Playwright
profile，且只有一個 state writer，所以不可在同一則 message 同時送不同站的擷取、
inspect 或任何 state mutation。所有寫入 state、render、set-run、set-top 等有依賴或
副作用的動作也維持序列。工具或 runtime 若拒絕同則多 call，照抄原始錯誤並退回序列，
不要用跨站平行補償。

## 必讀清單

先跑 `python scripts/s2_rules_check.py`，❌ 就回報不開工，不要開始掃帶。
路徑前綴一律 `E:\GitHub\TVBS-AIHunter\`：

1. `common\13-S2-定時掃帶.md`
2. `common\13e-S2-素材行與分類規則.md`
3. `common\13f-S2-大分類與各站規則.md`（尾已改一行指路，「收工清單總表」搬進 `13c3`）
4. `common\13c-S2-執行版-上-入口與三站擷取.md`（§0 三站入口＋登入態總表；掃描順序
   五站見 V5-1／V7-1 兩小節）
5. `common\13c1-S2-執行版-中-ENEX.md`
6. `common\13c1b-S2-執行版-中-ABC.md`
7. `common\13c2-S2-執行版-下-狀態檔與指令.md`
8. `common\13c3-S2-執行版-下-收工與防卡.md`（§5 防卡、§5a 建檔輪、尾附「收工清單總表」）

⛔ 不讀 `13b`（已退為歷史檔案，內容被推翻）。⛔ 不讀 `common\_rules_backup_20260907\`
與 `13c-V8-已取代條文.md`（V8 五層合一歷史存查，非必讀）。每份讀到 `RULES-EOF`
標記才算讀完（`13c3` §5 第 11 條；沒看到就用 `Read` 的 `offset` 補讀）。開工回報附一行：

```
規則載入：13 ✅／13e ✅／13f ✅／13c ✅／13c1 ✅／13c1b ✅／13c2 ✅／13c3 ✅
```

少一個就不要開始掃帶。

## 本輪參數

- **checkpoint 一律寫 `{CHECKPOINT}`**（機碼 `MMdd-HHmm`，不要只寫時間、不要把補掃後綴塞進機碼）。
  `run_id` 由 launcher 產，收工 `set-run --checkpoint {CHECKPOINT} --run-id {RUN_ID}`（有 label 再帶 `--checkpoint-label`）。
  ⛔ **開局絕對不要跑 `set-top`**——執行順序鐵律與理由見 `13c3` 尾
  「收工清單總表」第 5.5 列。
- **NS id** 文法與 **AP／RT `src_text` advisory** 見 `13c`「文法短指路」／`13c2` §5。
- **掃描窗**：狀態檔目前 `checkpoint` 到現在，自己 `resume` 看，不要猜。
- **掃描順序固定 NS → AP → RT → ENEX → ABC**（不可調換，理由見 `13c` V5-1／V7-1 兩小節）。
- 本輪是否掃 ENEX／ABC，對照 `{CHECKPOINT}` 查 `13c` V5-1／V7-1 的輪次表；
  不掃就回報一行「本輪不掃 ENEX（V5-1）」／「本輪不掃 ABC（V7-1）」。
- **D23 YouTube 尾端**：五站瀏覽器收工硬步驟後才看 D23；Phase 5 只准執行
  `python scripts/s2_youtube_launcher.py --checkpoint {CHECKPOINT} --state <state> --cursor <cursor> --out-dir <scratch> --dry-run`。
  dry-run 只列 CNA → YNA 的命令計畫，不呼叫 bridge、不碰 state／cursor、不連外；不改 `s2_scan.ps1` 或另建 Windows 排程。
- 若 `{CHECKPOINT}` 是 01:00／20:00，D23 只回報「本輪不掃 CNA／YNA（D23）」；其他五輪按 CNA → YNA 順序列出各站結果，單站失敗各自留警告，不中止五站收工。
- 若是當天第一輪（狀態檔不存在）：先確認真的是建檔輪（只有 17:00），
  照 `13c3` §5a 建檔輪七項做，`window_start`／機動格兩項最容易錯，細節看該節。

## 開工先看

`resume` 後看一下 `needs-review` 有沒有「整站失守」記錄——有就先補掃那段窗，
再處理本輪新素材（`13c3` §5 第 12 條）。

## 收工

照 `13c3` 尾「收工清單總表」逐步做完，不跳步、不重抄內文。

## 卡住時

- 不准 `taskkill`／`Stop-Process`／半夜 `AskUserQuestion`／轉包子代理
  （`13c3` §5 第 4、6、10 條）。
- 某站登出 → 查 `13c` §0 登入態總表判斷是否過期，`needs-review add` 記錄後跳站，
  不嘗試登入、不停下等回應。

## 回報（簡短）

- 各站收錄則數、清單對帳結果（窗內未收幾則）——**ENEX、ABC、CNA、YNA 各單獨列一行**
  （本輪不掃就分別寫「本輪不掃 ENEX（V5-1）」／「本輪不掃 ABC（V7-1）」；
  ABC 有掃卻進不去，要寫明是靠哪個訊號判定登出）
- 稽核**嚴重／次要**各幾項、怎麼處理
- 本輪標了幾則 🔴（檔頭）／🟡（重大未進檔頭）
- 卡住或被拒絕的地方，**原始訊息照抄**

<!-- V8-MERGE-BASE s2_scan_prompt.md（2026-09-07 A26 五層合一）：V5-FORK-BASE／
     V7-FORK-BASE 兩段版本切換指紋已隨 `s2_v5_switch.ps1`／`s2_v7_switch.ps1` 一併
     退役（搬到 scripts/_archive/），V8 無版本切換制，不再需要比對 sha256 drift。 -->
