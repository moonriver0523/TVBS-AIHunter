# 外電批次下載

當使用者接續 [`素材編號`](../common/05-material-numbering.md) 產出的已編號清單、並提供 **SLUG**，要求批次下載這些素材、改名並上傳共用資料夾時，使用本規則。此流程原本只處理 Reuters（曾稱「外電批次下載(RT)」），現已擴充為跨來源公版：依代碼前綴分派到 Reuters／AP／CNN Newsource／YouTube／X。

本流程與 [`自動掐SO(RT)`](03-auto-clip-so.md) 不同：不剪片、不找 TC、不找引言，只把素材整支/整張下載、存文稿、改名並上傳。

## 觸發與輸入

使用者會提供：

1. 一份已用 [`素材編號`](../common/05-material-numbering.md) 編號的素材清單（每行帶簡短摘要，摘要留著當索引，不要更動）。
2. 一個 **SLUG**——這則新聞在 TVBS 內部系統的編號（例如「西國不敗1200」），貫穿檔名／文稿 txt 命名／上傳資料夾名稱。

**防呆（重要）：清單裡若沒給 SLUG，先停下來問使用者要用什麼 SLUG，不要自己編或拿標題代替。**

## 開始前檢查

- 若清單裡看到同一素材代碼在不同編號下重複出現（沒有被標成「同#XX」），先跟使用者確認是否為 Edit No./ID 打錯，不要自行假設丟棄或保留哪一筆（正常情況下 [`素材編號`](../common/05-material-numbering.md) 應該已經把真正重複的都標成同#XX 了）。
- **標「同#XX」的項目不需要重新搜尋或下載**——直接沿用 #XX 那筆已經下載好的檔案即可，不產生新檔案、不用重新分派來源。
- **清單裡素材代碼後方若標註「(不存)」，不代表該素材在來源網站查無資料、也不代表要跳過下載。** 2026-07-24 使用者說明：這通常是 TVBS 公司內部片庫整理時「不入庫」的標記，跟該素材是否存在於 Reuters／AP、是否要下載無關，與執行本流程的 AI 代理無關。看到「(不存)」時仍應正常搜尋、下載；不確定時向使用者確認，不要自行判斷跳過（「破一百1200」案例：#02 RT0258 一開始因標「不存」被誤判跳過，實際 Reuters Connect 上找得到）。

## 開始下載前：存清單

清單與 SLUG 都確認無誤、也做完開始前檢查（無異常重複）之後，**先把這份完整編號清單存成一份 txt**（檔名 `{SLUG} 素材清單.txt`），上傳到 Google Drive「Claude共用」底下 `SOT自動寫稿測試\{SLUG}\` 子資料夾（子資料夾還沒建立就先建立，見下方「上傳」章節），再開始逐筆下載。**不用把清單內容再貼回對話視窗給使用者看**——清單使用者前面已經看過確認過，直接存檔即可，不必重複輸出。

## 來源分派表

| 代碼前綴/類型 | 實際來源 | 細節流程 | 檔名來源縮寫 |
|---|---|---|---|
| `RT`（`RTV` 正規化為 `RT`） | Reuters Connect | [`搜尋外電素材(RT)`](01-search-workflow.md) | `RT` |
| `AP` | AP Newsroom | [`搜尋外電素材(AP)`](../ap/01-search-workflow.md)／[`找AP照片`](../ap/02-photo-search.md) | `AP` |
| `{2 字母}-{數字}{星期兩碼}` 組合碼<br>（`IN-07SU`／`PO-35TU`／`WE-018FR`…前綴不固定） | CNN Newsource | [`自動寫稿(CTV)`](../cnn/01-auto-script-writing.md) | `CNN`（NEWSOURCE＝CNN Newsource） |
| `ENEX`（`ENEX{6 碼}`） | ENEX 會員站 `members.enex.news` | 見下方「ENEX」細節（2026-09-07 訂定：文稿走 ES API、影片走 `/download/{id}` 簽章直鏈） | `ENEX` |
| `ABC`（`ABC{9 碼 Story Number}`） | ABC NewsOne（Extreme Reach AdBridge）`abcnews.extremereach.com` | 見下方「ABC」細節（2026-09-07 訂定：文稿走 Detail 頁、影片要先 Approve 再 Download） | `ABC` |
| DVIDS URL（`dvidshub.net`） | DVIDS（美國國防部影像庫） | 見下方「DVIDS」細節 | `DVIDS` |
| YouTube URL | YouTube | `yt-dlp` 下載到 `D:\Downloads` | `YT` |
| X 影片貼文（一般 `#XX`） | X | `yt-dlp` 下載到 `D:\Downloads` | `X` |
| X 照片貼文（**圖片編號** `圖#XX`） | X | 取 `pbs.twimg.com` 原圖網址下載 | `X`（檔名用 `圖#XX`） |
| Facebook URL（社群轉發連結） | Facebook | `yt-dlp` 下載到 `D:\Downloads`，做法同 YouTube；清單摘要簡短時先抽樣看完整支片再下判斷 | `FB` |

## API 直取（2026-08-03 訂案，AP／RT／NS 首選路徑）

**核心**：定位、文稿全走 API；**影片下載＝AP 可 API 直連、RT 只能真點按鈕、NS 走 UI**（見各站）。**API 失敗兩次就退回下一節的 UI 舊做法**，不要死磕。**每筆下載後必查檔案大小**（見「下載驗證」）——「Downloaded」事件會騙人。

**共同前提**
- **一律用 Playwright 工具組**（`mcp__browser__*`），不是 claude-in-chrome（NS 的 localStorage 在 claude-in-chrome 會被 extension 隱私防護擋死）。
- **開工前檢查 profile 殘留**（多 agent 並行會互鎖；0803 曾害 RT 三輪誤判「全站 0 素材」）：
  `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ? { $_.CommandLine -like "*playwright*profile*" }`，閒置就 `Stop-Process -Force`；**自己收工也要關**。（2026-09-07 訂正：本流程用的是 `~/.claude.json` 裡 `browser` MCP 的 `.playwright-daily-profile`，舊字串 `*playwright-mcp-profile*` 比對不到任何實際 profile；S2 掃帶用的 `.playwright-s2-profile-v4` 不共用登入態，⛔ 不要拿它來做批次下載。）
- ⚠️ **下載落點是 `D:\Downloads\PlaywrightMCP\`，不是 `D:\Downloads\`**（2026-08-03 實測）。改名時從這裡取檔；Playwright 會把檔名裡的 `_`／空格換成 `-`，**別假設檔名原樣保留**。
- **費用：不必事前把關、不必為此停下來**（2026-08-03 使用者訂正）——**使用者提交清單時已人工確認過都是免費素材**，本流程照單全收即可，不要因為費用欄位而卡住或反覆確認。
  - 但**看到就順手回報**：費用欄位本來就在你已經取回的回應裡（RT 的 `points`／`free` 就在文稿那份 item 回應；AP 的 `Term` 在 `downloadnr/check`，而 check 本來就是拿 `ContentId` 的必要步驟），**零額外呼叫**。若發現某筆不是免費（RT `points` 非 0，或 AP `AppliedPrice` 非 0／`IsAlaCarte: true`），**照樣下載**，但在回報裡列出該筆與數值，當人工核對的備援。

### RT（文稿走 API，**影片只能真點按鈕下載**）

1. **定位**：照 `13b` §1b DOM 直撈 `a[href*="detail?id="]` 拿 guid。Edit No 可從 guid 的 `newsml_RW{4碼}` 推出、與清單值互相校驗。
2. **文稿**：`GET /api/item/{guid}?hash={hash}&live=false`（同源 fetch＋`credentials:'include'`）→ SCRIPT＋SHOTLIST＋Restrictions 一次到手。`hash` **照抄當下頁面請求**（實測 `klwn20`，但那是前端 build hash、改版會變，不要硬編）。
3. **費用（只記錄不擋）**：同一份 item 回應裡的 `~:points`／`~:free` 順手看一眼；非 0 照樣下載，但列進回報。
4. **影片下載**：⚠️ **不能用 `a.click()` 合成觸發下載**（2026-08-03 工作 agent 端到端實測抓到、經根因驗證）——
   - **現象**：在 `browser_evaluate` 內 `a.href={download-url}; a.click()`，Playwright 照樣回報「Downloaded file X」**沒有任何錯誤**，但落地的其實是 **~8KB 的帳號 JSON**（`application/transit+json`），不是影片。**22 筆全中招**。
   - **根因**：合成點擊是 untrusted click、缺 `Sec-Fetch-User: ?1`，RT 的 `/api/download/video` 端點對「真人手勢觸發」與「腳本觸發」做內容協商——URL 完全相同（同 guid／binaryId／hash／`purchase-type=ayce`），真點按鈕回真影片、腳本點回帳號資料。這是瀏覽器規格層行為，不是 Reuters 的 bug，**這個端點就是不吃合成點擊**。
   - **正確做法**：定位／文稿／費用全走 API 不變（guid 已確定，省掉開新分頁看 Restrictions／捲動找 Transcript），**只有下載這步**回到 detail 頁 → `browser_find` 找 label 恰為 `Download` 的按鈕 → **`browser_click` 真點**（不是 JS click）。
   - ⚠️ **`filename` 自訂優化失效**：按鈕觸發的下載套不上自訂 query-string 檔名，會用 Reuters 原始檔名，**下載完仍要照原 UI 流程手動改名**。
   - 為什麼不再嘗試純 API：download 端點回的 transit JSON 裡 `download-url`／`status-url` 兩欄都是 `null`，看不出兩段式流程的下一步；深挖 CP 值低，先用真點按鈕。
   - ✅ **下載後必查檔案大小**（見本節末「下載驗證」硬規則）——這正是這次踩雷的教訓。

### AP（文稿＋影片都可 API）

1. **定位**：`POST https://api.newsroom.ap.org/v1/nrsearch/search/topic`（cookie 驗證）。**照抄頁面實際發出的 request body**（順序才與畫面一致）；⚠️ **`PageNumber` 不可靠**（實測 Page 2 回 100 筆、與 Page 1 零重疊），要多筆就**固定 `PageNumber=1` 加大 `PageSize`**（16／50／100／200 實測精準）。`_source.itemid`＝32 碼 GUID，`_source.editorialid`＝AP 編號。
2. **文稿**：`POST /v1/nrsearch/search/item/details`，body `{"ItemIds":"{itemid}","mediaType":"video","IsNonSalable":false}`。**逗號串多則不支援**，一則一次；但可在同一個 `browser_evaluate` 裡 `Promise.all` 打 N 則（工具呼叫仍只算 1 次）。
3. **`check`（拿 rendition 用，順帶看費用）**：`POST /v1/downloadnr/check`，body `{"ItemIds":["{itemid}"],"IsClip":false,"IsNonSalable":false}`。**這步不能省**——第 4 步要用它回傳的 `ContentId`／`ContentRenditionId`。回應的 `Term`（`AppliedPrice`／`MeteredType`／`IsAlaCarte`）順手看一眼，非免費照樣下載但列進回報。
4. **影片**：同一份 check 回應的 `Renditions` 挑 `Duid: "vid-1080i-main-60-slate"`（HD 1080i60 MP4），取其 `ContentId` 與 `ContentRenditionId`，再打
   `POST /v1/downloadnr/tick`，body
   `{"Ticks":[{"ItemId":"{itemid}","MediaType":"video","Role":"Main","Title":"{slug}","ContentId":"{ContentId}","StoryNumber":"{editorialid}","ContentRenditionId":{ContentRenditionId},"RecordSequenceNumber":1}],"StoryItemID":null}`
   → 回應的 **`ClientMediaUrl`** 就是簽章直連（CloudFront，**約 15 分鐘到期**），`a.click()` 下載即可，`FileName` 也一併給。
   ⚠️ `tick` 是 AP 的下載計數／授權登錄，**不可為了省一步跳過**——沒有它也拿不到 `ClientMediaUrl`。
   ✅ **AP 的 `a.click()` 可以用**（與 RT 不同）：`ClientMediaUrl` 是 CloudFront 純簽章直連，沒有登入態／信任觸發的內容協商，合成點擊正常。2026-08-03 實測 3 筆全對（96–188MB）。**但仍要照下方驗檔案大小**。

### ⚠️ 下載驗證（三站共同硬規則，2026-08-03 訂）

**「Downloaded file」事件文字不代表下載成功**——RT 的假檔就是靜默失敗、事件照樣回報成功。每筆下載後**必查落地檔案的大小與型別**：

```powershell
Get-ChildItem "D:\Downloads\PlaywrightMCP" -File | Sort LastWriteTime -Desc |
  Select -First 5 Name, @{n='MB';e={[math]::Round($_.Length/1MB,1)}}, LastWriteTime
```

- **影片正常範圍**：數十 MB 到數百 MB（實測 RT 54–713MB、AP 96–188MB）。
- **⚠️ 8KB 級（<1MB）＝假檔**（帳號 JSON／錯誤頁），該筆判定失敗、重下（RT 改真點按鈕）。
- 不能只憑事件文字或檔名存在就打勾；大小不合理就是沒下到。

### CNN Newsource（NS）：文稿走 API，**影片只能走 UI**

- **文稿（大幅省成本）**：`POST https://newsource-content-api-530.ns.cnn.com/api/v3/stories`（Bearer token 在 `localStorage.newsourceSession.token`）——**清單回應直接含 `content.bitcentral.script` 全文**，不必開任何詳情頁或 Preview modal。完整配方見 [`common/investigation-logs/2026-08-03-NS掃帶卡點報告-回覆.txt`](../common/investigation-logs/2026-08-03-NS掃帶卡點報告-回覆.txt)。
- ⚠️ **影片下載不能 API 直取**（2026-08-03 實測結論）：NS 走 **Signiant 傳輸服務**（`POST /api/v2/download` → `downloadIds` → `/api/v2/download/config/{id}` 回的是 `sig://` 路徑＋Signiant 伺服器與憑證，前端載入 `transferapi.min.js` 由 Signiant 客戶端搬檔），**沒有 HTTP 直鏈可取**。NS 影片一律照下一節 UI 做法點 Download。
- ⚠️ NS token 會過期，第一次呼叫拿到 `null` 是常態——重新整理頁面等登入完成再打；**連兩次拿不到就是真的登出，停下來請使用者登入**（agent 不得自行輸入帳密）。

## 各來源處理細節（UI 舊做法：API 失敗兩次時的退路，NS 影片則一律用這套）

**RT（含來源端寫成 `RTV` 者，一律當 `RT` 處理）：**
1. reutersconnect.com，Video 分頁，搜尋 Edit No.——搜尋方式（優先直接帶網址、My Subscription 維持預設 **ON**）一律依 [`搜尋外電素材(RT)`](01-search-workflow.md)，本文件不另訂。
2. Edit No. 可能撞號到不相關舊新聞——核對標題/主題是否符合這批清單脈絡，不要無腦點第一筆結果。
3. 開詳情頁，記錄右側 **Restrictions** 面板完整內容＋複製 **Video Transcript**／逐字稿全文，合併存成該筆的文稿 txt。
4. 點 **Download**（HD 60fps (MP4) 是預設選項，不用另外選）。

**AP：**
1. 用純數字 ID 搜尋，媒體類型選對 Video 或 Photo（不要照抄「AP」字首去搜，那只是站台判斷標記）。
2. 影片：進詳情頁的 **Shotlist** 分頁（限制摘要＋SOUNDBITE＋STORYLINE）存成文稿 txt——**取全文時依 [`搜尋外電素材(AP)`](../ap/01-search-workflow.md) 的「取 Shotlist 的標準做法：開新分頁」，點彈出 modal 右上角「Open in a new tab」再對該分頁 `get_page_text`；不要對 modal 直接 `get_page_text`**（會抓到背後列表頁摘要而不是 Shotlist 內容，只能改靠截圖逐段捲讀，浪費 token 又會被裁切，2026-07-24「破一百1200」案例踩過）。按 Download 選 Master＋任一 HD 格式送出——**非同步處理，不用在 AP 網站的 Downloads 頁面等 ready，完成後直接進 D:\Downloads**。
3. 照片：列表頁卡片上的 ⬇ 圖示可直接下載（同步即時）；詳情頁 **Photo Metadata** 含 **Special Instructions**（限制）存成文稿 txt。

**CNN Newsource（`{2 字母}-{數字}{星期兩碼}` 組合碼）：** 依 [`自動寫稿(CTV)`](../cnn/01-auto-script-writing.md)，用「≡Q」預覽圖示取得官方 script 全文存成文稿 txt，下載影片，比對 TC。

**ENEX（`ENEX{6 碼}`，2026-09-07 訂定，daily profile 實測）：** 文稿與影片都不必開任何頁面點按鈕。兩步都寫在 `members.enex.news` 頁面的同一個 `browser_evaluate` 裡（同源 cookie，不需 token）。

1. **登入態＋文稿**：`POST https://members.enex.news/elasticsearch/news/_search`，body `{"size":1,"query":{"ids":{"values":["{6 碼}"]}},"_source":[…白名單]}`（0907 實測 `ids` 與 `term:{_id}` 兩種寫法都回 `total: 1`）；`hits.hits[0]._source` 的 `description` 就是完整 dopesheet（STORYLINE／SHOTLIST／SOUNDBITE／限制語），加 `title`／`partner`／`location`／`sortDate`／`filename` 一起存成 `{SLUG} #XX ENEX (外電文稿).txt`。⛔ `description` 逐字保留。欄位白名單與 CCTV 授權樣板剝除照 [`common/13c1`](../common/13c1-S2-執行版-中-ENEX.md) V5-2 的 `slimEnex()`，不要自己發明。回 `hits.total` 為 0 或 fetch 被導到登入頁＝未登入，停下來請使用者登入。
2. **影片直鏈**：`https://members.enex.news/download/{6 碼}` 會 **302 到 `enexfeed.s3.eu-west-1.amazonaws.com` 的 SigV4 簽章直鏈**（`X-Amz-Expires=600`，**10 分鐘**到期），就是全解析度 mp4（實測 929921 → 522MB `video/mp4`）。
   - 🔴 **不能用頁內 `fetch('/download/…')` 取**：轉址跨到 S3、S3 沒開 CORS，會直接拋 `Failed to fetch`（0907 實測）。要用 **`browser_navigate` 開這個網址**——導航不受 CORS 限制，分頁會停在 S3 網址上（畫面是 403 XML，這是正常的，見下一點），然後 `browser_evaluate` 回 `location.href` 就是簽章直鏈；或用 `browser_network_requests`（filter `amazonaws`）抄。
   - 🔴 **落地前一定要把尾巴的 `&check_logged_in=1` 拿掉**（Drupal 轉址時附加的，不在簽章範圍內，帶著打就是那個 `403 SignatureDoesNotMatch`）：`url.replace(/[?&]check_logged_in=1$/, '')`。拿掉後同一條網址 0907 實測 `206 bytes 0-0/522565697`。
   - 直鏈是純簽章 S3，**不需 cookie、不吃真人手勢**，用 `curl -L -o "D:\Downloads\{SLUG} #XX ENEX.mp4" "{url}"` 從本機下載即可，不要在頁面裡 `a.click()`。**10 分鐘內要開始下載**，過期就重開一次 `/download/{id}` 換新鏈。⚠️ 簽章只綁 `GET`，`HEAD` 會 403，探測用 `Range: bytes=0-0` 的 GET。
   - ⛔ ES 回應裡的 `videoLowResCdn` 是低解析度預覽（量時長用），**不是**要交件的檔案。
3. **落點在 `D:\Downloads`**（curl 系，同 yt-dlp），不是 `PlaywrightMCP`。照下方「下載驗證」查大小（ENEX 全解析度多為數百 MB）。
4. **費用**：會員交換平台，站上沒有計價欄位；`/download/` 是站方正規下載入口。首批仍照「看到就回報」原則在彙整表註明「ENEX 無計價資訊」。

**ABC（`ABC{9 碼}`＝ABC NewsOne 的 Story Number，2026-09-07 訂定，daily profile 實測）：** 站台是 Extreme Reach AdBridge，模型是「**交付**」不是「下載」——每則素材對 TVBS 都是一筆 delivery，狀態從 `Awaiting Approval` → `Ready For Download`，**沒核准之前沒有任何下載鏈**。全部寫在 `abcnews.extremereach.com/cmspage/50162/abcnewsone` 頁面的 `browser_evaluate` 裡，每個 fetch 都帶 `credentials:'include'` 與 header `__RequestVerificationToken`（值取自頁面 `input[name=__RequestVerificationToken]`；[`common/18`](../common/18-交換平台素材整併.md) §1 安全條款：讀 token→fetch→parse 不出同一個 evaluate）。

1. **登入態**：頁面沒有 `input[name=__RequestVerificationToken]`、或有 `input[type=password]`、或 fetch 直接拋 `Failed to fetch`＝未登入（`ss-tok` 約 1 小時到期，見 [`common/13c1b`](../common/13c1b-S2-執行版-中-ABC.md) V7-2）。停下來請使用者登入，⛔ 不准輸入帳密。
2. **Story Number → detailId**：`GET /Delivery/NewsSearch?deliveryDateStart={M/D/YYYY}&deliveryDateEnd={M/D/YYYY}&pageSize=1000&page=1`（**不加** `getCSV`）回 HTML，每列 `tr` 裡 `a[href*="/Delivery/Detail/"]` 的 `Detail/(\d+)` 是 detailId、`span.smallText` 是 Story Number；日期窗給素材上架日前後各一天。對映寫法照 `13c1b` V7-2 那段，⛔ 不要用「附近第一串 9 位數」近似抓。
3. **文稿**：`GET /adbridge/news/Delivery/Detail/{detailId}?includeCategories=True`（HTML 約 35KB），取 `Script` 欄（🔴 換行是 `&#10;`，要解 HTML 實體全套），連同 Slug／Story Number／Length／Synopsis／`ADVISORIES/RESTRICTIONS/EMBARGOES` 段存成 `{SLUG} #XX ABC (外電文稿).txt`。同一份 HTML 裡有 `a[href^="/Delivery/ApproveNews/"]`（`title="Approve this news story for download"`），把 href 記下來給第 4 步。
4. **核准（真實副作用，只對清單上的素材做）**：`GET /Delivery/ApproveNews/{MediaGuid}?g=…&d=…&returnUrl=…`（href 照抄，`&amp;` 要還原成 `&`）。這一步會把該筆 delivery 狀態改成核准、ABC 端看得到，**是不可逆動作**：⛔ 只對使用者清單上明列的 `ABC` 編號做，⛔ 不准為了「先看看」核准清單外的素材；依 [`common/08`](../common/08-execution-efficiency.md) 額度鐵則，也不准拿它做測試。做之前先確認該筆狀態確實是 `Awaiting Approval`（已經 `Ready For Download` 的就跳過這步）。
5. **等 `Ready For Download`**：`GET /Delivery/NewsDeliveries?pageSize=200` 回 HTML 表格（欄位 Date／News Story／Slug／Length／Destination／Status／Delivery Date／Actions）；找 Story Number 那列，Status 變成 `Ready For Download` 時，Actions 裡會多出 `a[title="Download local delivery"]`，href 形如 `/Delivery/Download/{GUID}?c=…&mpid=…&did={detailId}&d=…`。核准後多久會轉態尚未計時（0907 觀察：上午 10:29 上架、人工核准的一則在下午已是 Ready）；輪詢間隔 1–2 分鐘、上限依重試階梯，超時先跳過做下一筆。
6. **下載**：`/Delivery/Download/…` 會 **302 到 `s3.amazonaws.com/fs2.extremereach.com/media/…/{StoryNumber}.mp4` 的簽章直鏈**（SigV2 `Expires`，實測效期約 **2 天**；`response-content-disposition=attachment;fileName={StoryNumber}.mp4`）。**跨網域，頁內 `fetch` 會被 CORS 擋（`Failed to fetch`），不要在 evaluate 裡抓它。** 做法二選一：
   - **A（首選）**：`browser_navigate` 直接開 `https://abcnews.extremereach.com{Download href}`，瀏覽器跟著 302 落地成下載，檔案進 **`D:\Downloads\PlaywrightMCP\`**，檔名 `{StoryNumber}.mp4`。
   - **B**：開完 A 之後用 `browser_network_requests`（filter `s3.amazonaws.com`）把最終 S3 網址抄下來，之後同一筆要重下就 `curl -L -o … "{url}"`，不必再過站台。
   - ⛔ 頁面上的 `View Low-Res Proxy`（`app.extremereach.com/Media/Stream/…`）是串流預覽，不是交件檔。
7. **`Acknowledge media delivery`**（`/Delivery/Acknowledge/{GUID}`）是回報「已收到」的登錄動作，**本流程不點**；要不要按由使用者決定（0907 尚未裁定）。
8. 照下方「下載驗證」查大小（ABC PKG 多為百 MB 級）。

> 兩站共同：**本流程只做「已編號清單上的素材」**。掃帶輪（S2）擷取 ENEX／ABC 只讀清單與文稿、從不核准也不下載，那套規則在 `13c1`／`13c1b`；這裡是 S6 下載，兩邊不要互抄。

**ENEX／ABC 尚未實測的部分（2026-09-07 記錄，首次真跑時補）**：ENEX 直鏈的 curl 全檔落地（只驗到 `206 bytes 0-0/522565697`）、ABC 核准→Ready 的等待時間、ABC 導航下載在 Playwright 的落地檔名。首次跑到時把結果回寫本節並刪掉這一段。

**YouTube：** 用 `yt-dlp` 下載影片到 `D:\Downloads`（選合理可用的最高畫質 mp4）。沒有教「文稿」的抓取方式，若使用者要文稿，先問。**清單裡有多支彼此獨立的 YouTube 影片時，可以平行/背景執行多個 `yt-dlp` 下載，不用一支一支排隊等**，這是效率最好的一種下載方式。若同時下載官方/自動字幕，通常只需保留 `-orig`（原始語言）那一份即可，不必把翻譯版字幕也一起留著。

**DVIDS（`dvidshub.net`，2026-07-24 訂定）：** 美國國防部公開影像庫（DVIDS＝Defense Visual Information Distribution Service），素材在清單裡是直接給 `https://www.dvidshub.net/video/{id}/{slug}` 這種網址（使用者通常已登入該站）。

1. **影片本體**：用 `yt-dlp` 下載到 `D:\Downloads`，做法比照 YouTube（可平行/背景多支同時跑）。格式挑合理最高畫質 mp4，例如 `-f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b"`。
2. **文稿一定要抓（不要比照 YouTube 略過）**：DVIDS 詳情頁本身就有可用的文字資訊，抓法很簡單——**直接對詳情頁 `get_page_text` 就能一次拿到全部欄位**，不像 AP 要另開分頁。存成 `{SLUG} #XX DVIDS (外電文稿).txt`。要保留的欄位：
   - **標題**、**DESCRIPTION**（英文說明段，通常 1~3 句）
   - **拍攝者 / 單位**（Video by …／所屬中隊、AFCENT、CENTCOM 等）
   - **Date Taken**、**Date Posted**、**Category**（多半是 `B-Roll`）、**Length**、**Location**（常是 `(UNDISCLOSED LOCATION)`）
   - **Video ID / VIRIN / Filename**（DVIDS 內部編號，存查用）
   - **版權**：多為 `PUBLIC DOMAIN`（公有領域），但仍須遵守 `https://www.dvidshub.net/about/copyright` 所列限制，文稿裡照抄那句聲明。
3. ⚠️ **Date Taken 常常不是新聞當日**：DVIDS 多是 B-Roll 資料帶，拍攝日可能是幾週、幾個月甚至前一年。文稿裡務必註明拍攝日，並提醒寫稿時判斷這支是否只能當**背景/資料畫面**，不可當成事件當日的新畫面。（2026-07-24「加倍轟伊2200」案例：#08 拍攝日 2025-10-23、#09 拍攝日 2026-04-23，都比新聞當日早很多。）

**X（Twitter，2026-07-31 訂正）：**

⚠️ 判斷是影片還是照片、以及有幾件媒體，依 [`素材編號`](../common/05-material-numbering.md) 的「X 連結不能只看網址字串」規則——一般 `.../status/{id}` 連結先打開貼文確認內容，不要假設沒有影片/照片就跳過不下載（「俄炸朝彈2200」案例 5 則 X 連結全部因此誤判漏編漏下載，事後補救）。

- **影片**：`yt-dlp` 直接對 `https://x.com/{user}/status/{id}` 下載，**不需要登入/cookies**（2026-07-31 實測，公開貼文可直接抓）。格式建議 `-f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b"`。
  - 同一則貼文含多支影片時，`yt-dlp` 會當成 playlist 依序下載出多個檔案（對應多個 `#XX`），下載順序即貼文內影片顯示順序。
- **照片**：`yt-dlp` 不處理純圖片貼文。改用 `read_network_requests` 篩 `pbs.twimg.com` 找出該貼文自己的圖片（媒體 ID 通常同一批貼文共用相近前綴，注意排除頁面上其他人頭像/回覆串裡的圖），把網址參數改成 `?format=jpg&name=orig` 取原始解析度，用 `curl -sL "{url}" -o "{檔名}"` 直接落地，比瀏覽器右鍵另存更穩定也更快（一次可批量抓多張）。同一貼文多張照片，每張各自存成一個 `圖#XX`。
- **文稿/備註**：X 沒有 Restrictions 面板，改存一份簡短 txt 記錄：貼文帳號、URL、發文時間、原文 caption 全文、以及跟稿單哪一段對應；不確定的背景資訊（例如是否為同一事件的不同鏡頭）用備註標註，不要略過。

**Facebook（或其他社群轉發連結，清單摘要只有一句話時）：** 用 `yt-dlp` 下載到 `D:\Downloads`，做法比照 YouTube。**若清單裡的摘要只有短短一句話（例如「網友轉發＿＿影片」），下載完成後務必先對整支影片做全長度抽樣（`video_analyze`＋`video_detail` 稀疏抽樣，見 [`common/07-bite-assistant.md`](../common/07-bite-assistant.md) 的 B-roll TC 補充情境），確認實際內容與敏感程度後才決定寫稿時怎麼呈現，不能只憑清單那句摘要判斷。**尤其當這篇新聞的標題本身已經偏敏感/聳動時（例如涉及特定人物人身安全、路線曝光等），更要先看完整支片再下判斷（案例見 [`../common/09-known-issues.md`](../common/09-known-issues.md#規則由來案例歷史紀錄)）。

## 下載確認與卡住處理

用 PowerShell 輪詢下載夾（`Get-ChildItem -File | Where-Object {LastWriteTime -gt (Get-Date).AddMinutes(-2)}`），確認檔案（.crdownload 或臨時檔）已完成、大小穩定。
⚠️ **兩個落點不一樣**：`yt-dlp`／`curl` 系（YouTube／X／FB／DVIDS／**ENEX 直鏈**）落在 **`D:\Downloads`**；**瀏覽器下載（AP／RT／NS，含 API 直取；**ABC** 導航下載）落在 `D:\Downloads\PlaywrightMCP`**（2026-08-03 實測，ENEX／ABC 2026-09-07 補）。找不到檔案時先確認自己在看哪一個資料夾。

RT 詳情頁點連結後畫面還停在列表摘要、或 Download 點了 `D:\Downloads` 沒有新檔案等症狀，先查 [`common/09-known-issues.md`](../common/09-known-issues.md#瀏覽器自動化) 有沒有對應解法（通常是「再點一次」或「頁面要維持在最上方再點 Download」），再進入下方重試階梯。

卡住時依 [`common/08-execution-efficiency.md`](../common/08-execution-efficiency.md) 的**統一重試階梯**（重點1次 → 仍無檔案就查 network log → 確認失敗後收尾）。本流程屬**批次類**，收尾方式為：**先跳過這一筆，繼續處理清單中下一筆，不要讓整批流程卡在這一筆上**；全部其他素材跑完後，回頭把卡住的項目再補試一次；仍然失敗才在最終彙整表中列為 ⚠️ 未完成，並回報使用者是否要再手動排除障礙或換個時間重試。

## 檔名規則

一律：

```text
{SLUG} #{編號} {來源縮寫}
{SLUG} 圖#{編號} {來源縮寫}          ← X的Photo URL用「圖片編號」
{SLUG} #{編號} {來源縮寫} (外電文稿).txt   ← 對應的原始文稿
```

例：

```text
西國不敗1200 #01 RT
西國不敗1200 #01 RT (外電文稿).txt
西國不敗1200 圖#01 X
```

編號沿用 [`素材編號`](../common/05-material-numbering.md) 產出的 `#XX`；「同#XX」標記的項目**不產生新檔案**。副檔名依實際下載檔案類型（.mp4／.jpg 等）。

## 上傳

去 Google Drive「Claude共用」底下 **`SOT自動寫稿測試\` 底下新建一個以 SLUG 命名的子資料夾**（例如「梅西再勝1200」，不是直接放 Claude共用根目錄，也不是放 `SOT自動寫稿測試` 外面）。走本機同步資料夾操作：`G:\我的雲端硬碟\Claude共用\SOT自動寫稿測試\{SLUG}\`，優先用本機同步資料夾而非 MCP 上傳大檔。

⚠️ **2026-08-17 訂正：分批更名、分批上傳，不要全部下載完才一次大量搬移**——本機同步資料夾一次丟進大量大檔（尤其影片）容易在同步過程中網路斷線、造成半上傳的殘缺檔案或同步卡住。做法：素材**每下載完成幾筆**（例如同一個「+」分隔的小主題、或湊到 3–5 筆）就先把那幾筆改名、複製進 `{SLUG}\` 子資料夾，確認同步資料夾裡的檔案大小與本機一致後，再繼續下一批下載，不要等清單全部跑完才一次搬。卡住／斷線時容易定位是哪一批出問題，也比較好重試。

⚠️ **2026-07-24 訂正**：此路徑原本是 `Claude共用\{SLUG}\`（母端根目錄下），與 [`自動寫稿(SOT)`](../common/06-auto-script-sot.md) 2026-07-22 訂定的「完成稿放 `SOT自動寫稿測試\{SLUG}\`、不放母端根目錄」規則沒有同步，導致同一個 SLUG 產生兩個路徑不同的資料夾（「外送抓匪1700」案例踩過）。現改為與 SOT 完成稿共用同一個 `SOT自動寫稿測試\{SLUG}\` 路徑，素材與完成文稿統一放在一起。

## 全部完成後

輸出彙整表（編號｜來源｜檔名｜限制重點），對不尋常的限制（整個地區禁用、特定媒體黑名單等）加註 ⚠️ 提醒。

## 後續銜接

下載＋上傳完成後，若使用者明確下令，可接續 [`自動寫稿(SOT)`](../common/06-auto-script-sot.md) 寫成台灣播出格式完成文稿；此步驟不會自動觸發。
