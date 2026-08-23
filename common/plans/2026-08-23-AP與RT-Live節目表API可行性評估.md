# AP／RT Live 節目表（Channel Guide）API 可行性評估

- 日期：2026-08-23
- 性質：**測試性評估報告，不是規則、不是授權實作**
- 提問：AP Newsroom（`newsroom.ap.org/live`）與 Reuters Connect（`reutersconnect.com/app/live/rlo`）頁面底下的 Live 節目表，能否用 API 直接抓取，不必模擬點擊 UI？
- 方法：以 Playwright MCP 開兩站，用 `browser_network_requests` / `browser_network_request` 攔截並比對兩站的實際 XHR/Fetch，再用 `browser_evaluate` 在頁面 context 內對候選端點發 `fetch` 驗證回應內容。
- 裁決紀錄：本檔為測試存證，**未授權任何後續實作**。若要接進 S2 排程或獨立工具，須另外開案評估（含穩定性、登入態、稽核欄位對照）。
- 補充（2026-08-23，使用者提出）：構想「加掛」進 S2 定時掃帶，見末尾「六、後續補充構想」。**同樣未授權動工，僅記錄構想與待決事項。**

---

## 一句話結論

**AP 可以，RT 不行（目前只能靠瀏覽器模擬）。** AP 節目表背後是一支乾淨的 REST GET，一次打完就能拿到含頻道／內容／時間／限制的完整結構化資料；RT 的節目表是透過 WebSocket 即時推播、且頁面資料流走的是版本綁定的 Next.js Server Action，沒有可重複呼叫的公開 REST 端點。

---

## 一、AP Newsroom（`newsroom.ap.org/live`）

### 1.1 核心端點

```
GET https://api.newsroom.ap.org/v1/nrlive/events?includeCurrent=true&cacheBuster=<timestamp>
```

- 帶登入 session cookie（同源 `fetch(..., {credentials:'include'})`）即可呼叫，未測試未登入情形。
- 一次回傳所有「即將播出＋當前播出中」節目的 JSON 陣列，等同整張 Channel Guide，不需要逐項點開 UI。
- 輔助端點：
  - `GET /v1/nrlive/channels?cacheBuster=...` — 頻道清單（AP Direct、AP Live Choice 1–6…）
  - `GET /v1/nrlive/endpoints` — 串流端點資訊
  - `GET /v1/nrlive/events/apdirect?includeCurrent=true` — 只抓 AP Direct 頻道

### 1.2 單筆事件欄位（已用 2026-08-24 節目表實測驗證）

| 欄位 | 說明 | 範例 |
|---|---|---|
| `channelName` / `channelId` | 頻道 | `"AP Live Choice 5"` / `"5"` |
| `title` / `slug` | 節目標題 | `"MIDEAST: IRAN STRAIT OF HORMUZ SHIP TRACKER"` |
| `description` | 內容說明（含 AUDIO 註記） | `"Live ship tracking map... AUDIO: MUTE"` |
| `startDateTimeUtc` / `isStartTimeTBA` | 預定時間（UTC）、是否時間未定 | `"2026-08-22T19:25:00Z"` |
| `durationInMs` | 預估時長 | `3600000`（1 小時） |
| `restrictions` | 限制／版權要求 | `"Must credit \"MarineTraffic/OpenStreetMap\""` |
| `location` / `source` | 地點、供稿來源 | `"Virtual"` / `"MarineTraffic"` |
| `eventCategory` | 分類 | `"War & Conflict"` |
| `storyNumber` | AP 稿號 | `"L167644"` |
| `isCancelled` / `isPublished` / `isBooked` | 狀態旗標 | bool |

### 1.3 注意事項

- `startDateTimeUtc` 是 UTC；AP UI 顯示的日期是**瀏覽器本地時區**換算後的日期，兩者可能相差一整天（例：UTC 2026-08-23T18:00 在 UI 上顯示為台北時間 2026-08-24 02:00）。**用日期篩選節目表時，必須先把 UTC 換算成台北時間（+8）再比對日期，不能直接比對 `startDateTimeUtc` 的日期字串**，否則會漏抓／抓錯跨日節目（本次測試曾實際踩到這個坑，已用台北時間換算修正並與 UI 比對確認一致）。

---

## 二、Reuters Connect（`reutersconnect.com/app/live/rlo`）

### 2.1 為什麼不能直接打 API

- 頁面是 Next.js。同一頁面 URL 會收到多支 **POST Server Action**（帶 `next-action` header，一組隨前端 build 版本變動的雜湊值），回應是 RSC 序列化格式，不是穩定可重放的 JSON REST 契約。實測抓到的 Server Action 內容多半是使用者偏好、點數、單一事件的串流位址（`hlsUrl`/`vodUrl`），**不是節目表本身**。
- 真正的節目表（Broadcast schedule）資料流是：
  1. `POST https://ap-northeast-1.rcp-api.reutersconnect.com/ws-active/auth-ticket/issue` 取得一次性 WebSocket 授權票證
  2. 用該票證建立 **WebSocket** 連線，接收即時推播的節目清單／狀態更新
- 這種架構無法用單純重複 `fetch` 拿到完整列表：沒有票證就連不上 WS，票證本身有時效，且尚未逆向出 WS 訊息協定（本次評估未做這一步，投入產出比低，見「五、未做事項」）。

### 2.2 目前唯一可行方式：DOM 擷取（瀏覽器自動化）

RT 頁面 hydrate 完成後，節目表會渲染成標準 HTML `<table>`，可直接用 accessibility snapshot／`read_page` 讀出結構化列，不需要逆向 WS：

| 欄位 | 內容（實測範例：IRAN-CRISIS/HORMUZ-TRACKER） |
|---|---|
| Status | Live／Cancelled／Completed |
| Slug（標題） | `IRAN-CRISIS/HORMUZ-TRACKER --INTERRUPTIBLE--` |
| Date / Start / End | `08/23/2026`, `08:40`（`-1` 上標＝跨日）, `TBD` |
| Restrictions | 限制全文（如 must credit／no resale） |
| Copyright | 版權聲明全文 |
| Aspect Ratio / Audio | `16:9` / `MUTE` |
| Location | `Iran` |
| ID | newsml tag（如 `tag:reuters.com,2026:newsml_ADOMI1ZH4:3`） |
| Topics | `Politics / International Affairs` |
| Source / USN | `MARINE TRAFFIC` / `ADOMI1ZH4` |
| Editorial Support | 電話＋email |

表格列本身（Status/Slug/Start/End）點開列表即可見；Restrictions／Copyright／Details 需要點進單筆事件才會展開，等同現行 AP UI 點擊流程，只是 RT 沒有 API 捷徑可省略這一步。

---

## 三、兩站對照

| 項目 | AP Newsroom | Reuters Connect |
|---|---|---|
| 節目表資料來源 | REST GET（`/v1/nrlive/events`） | WebSocket push（RSC Server Action 不含節目表本身） |
| 是否可重複 `fetch` 拿到完整表 | 可以 | 不行 |
| 需要登入態 | 需要（session cookie） | 需要（session cookie＋WS 票證） |
| 端點穩定性 | 一般 REST，語意穩定 | `next-action` 雜湊隨前端版本變動，不可硬編 |
| 抓詳情是否要點開 UI | 不用，API 一次回全部欄位 | 表格列可 DOM 抓，但 Restrictions/Copyright 等仍需點開 |
| 目前建議做法 | 直接呼叫 API | 沿用瀏覽器自動化（DOM snapshot） |

---

## 四、後續若要接進正式流程的最低門檻（本檔不授權，僅列供評估）

1. AP：確認 API 呼叫頻率／穩定性是否受限（本次僅少量測試呼叫，未壓測），並固定「UTC→台北時間换算再比對日期」這條規則寫進抓取腳本，避免重蹈本次踩過的跨日誤篩。
2. RT：若要脫離逐次點擊，下一步是嘗試逆向 WebSocket 訊息格式（進廠須有 devtools 網路面板長時間側錄，非本次 Playwright MCP 攔截範圍能簡單做到），或維持現行 DOM snapshot 擷取但排程化。
3. 兩者皆用真實登入帳號測試，未評估帳號權限（roles/features）差異是否影響資料回傳範圍。

---

## 五、未做事項（明列，避免誤以為已查證）

- 未逆向 RT WebSocket 的訊息協定／訂閱格式。
- 未測試 AP API 在未登入或 session 過期狀態下的行為（401/403 或降級）。
- 未壓測 AP API 的呼叫頻率上限。
- 未評估兩站 API／DOM 結構未來改版的偵測與容錯機制。

---

## 六、後續補充構想（2026-08-23 使用者提出，未授權動工）

### 6.1 併入方式：加掛，不動掃帶流程本身

- 目標：把「AP／RT Live 節目表」的擷取／更新，掛進 S2 定時掃帶的既有排程外殼，而不是新開一條獨立排程。
- 硬性前提：**不動掃帶流程本身**——即不改 `s2_scan.ps1` 的既有步驟、不動 NS→AP→RT 收錄順序、不動狀態檔 `s2_state.py` 寫入邏輯。節目表擷取要視為「額外附掛的一步」，掃帶流程本體失敗與否不受它牽連，它失敗也不該讓掃帶流程本體跟著壞。
- 頻率：**不是每輪都跑**。9 輪中暫定只在 **22:00／04:30／12:00** 這三輪加掛，其餘輪次略過。三個時間點的選定理由（每日節目表變化頻率、與晚班/早班交接時間對齊等）本次未討論，留待正式開案時確認。

### 6.2 輸出檔案與更新規則

- 位置：雲端硬碟 `Claude共用/自動掃帶系統/`（現況已在用這個資料夾放 `s2-state.json`、晚班交接 txt 等產出，見查證依據）。
- 檔名：指定單一固定檔名 `AP_RT_LIVE節目表.txt`（每次直接覆蓋更新，不用日期戳記入檔名）。
- 備份規則：**只留「更新前的最新一份」**，即覆蓋前先把舊檔搬成 `.prev.txt`，不做多版本歷史。此規則與現有 `0823晚班交接.txt` / `0823晚班交接.txt.prev.txt` 的既有慣例一致，沿用同一套 `.prev.txt` 命名即可，不必另創新格式。

### 6.3 待決事項（正式開案前必須先定案，本檔不代為決定）

1. 三輪加掛的觸發點要嵌在 `s2_scan.ps1` 排程外殼的哪個位置（收工後／收工前／獨立平行呼叫），才能真正做到「不動掃帶流程本身」而非只是口頭不動。
2. AP／RT 擷取失敗時的容錯：允許該輪不更新 `AP_RT_LIVE節目表.txt`（保留舊檔），或寫入部分結果並標記「本輪未完整更新」？本次評估未定案。
3. RT 目前只能靠 DOM snapshot（見二、2.2），排程化後長期跑是否穩定（改版偵測、hydrate 等待時間）未經壓測，見「五、未做事項」。
4. 這個「加掛」構想與 `2026-08-21-S2三站子代理並行掃帶可行性評估.md` 中「單例資源不可拆」的四個硬擋（瀏覽器單例／狀態檔單寫者／排程外殼留不住背景任務／工具層禁止派出）是否互相影響，尚未交叉檢查——若加掛步驟本身要開瀏覽器分頁，需先確認不會撞到掃帶流程本體正在用的同一個 Playwright profile。
5. 是否需要、以及如何寫入 S2 MASTER 追蹤清單列管（依現行規則屬 D-裁決項，不得自行動工），本檔僅供正式提案時附帶引用。

---

## 查證依據（2026-08-23）

| 聲明 | 來源 |
|---|---|
| AP `GET /v1/nrlive/events?includeCurrent=true` 回傳完整節目表 JSON | `browser_evaluate` 對該端點實測 fetch，回應含 channelName/title/startDateTimeUtc 等欄位 |
| AP UI 本地時區顯示與 UTC 相差一天（跨日節目） | 以「FRANCE: MACRON ESPORTS」為例，UI 顯示台北時間 08/24 02:00，`startDateTimeUtc` 為 `2026-08-23T18:00:00Z` |
| RT 節目表非可重放 REST | `browser_network_requests` 攔截 `/app/live/rlo` 頁面，主要資料請求為同 URL 的 POST（`next-action` header），回應內容為使用者偏好／單一事件串流位址，非節目表清單 |
| RT 節目表走 WebSocket | 攔截到 `POST /ws-active/auth-ticket/issue`（`ap-northeast-1.rcp-api.reutersconnect.com`），且頁面初始 HTML 中節目表區塊為 `Loading events...` 佔位、非伺服端直出 |
| RT 表格可 DOM 擷取 | `browser_snapshot` 在頁面 hydrate 完成後讀出結構化 `<table>`（Status/Slug/Start/End 欄），並點開單筆事件確認 Restrictions/Copyright/Details 完整可讀 |
| `Claude共用/自動掃帶系統/` 現況已用 `.prev.txt` 做單版備份 | 實際列出該資料夾內容：`0823晚班交接.txt` 與 `0823晚班交接.txt.prev.txt` 並存 |
