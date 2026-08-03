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
| `ENEX` | 尚無教學說明 | 遇到先問使用者要去哪裡找 | `ENEX` |
| `ABC` | 尚無教學說明 | 遇到先問使用者要去哪裡找 | `ABC` |
| DVIDS URL（`dvidshub.net`） | DVIDS（美國國防部影像庫） | 見下方「DVIDS」細節 | `DVIDS` |
| YouTube URL | YouTube | `yt-dlp` 下載到 `D:\Downloads` | `YT` |
| X 影片貼文（一般 `#XX`） | X | `yt-dlp` 下載到 `D:\Downloads` | `X` |
| X 照片貼文（**圖片編號** `圖#XX`） | X | 取 `pbs.twimg.com` 原圖網址下載 | `X`（檔名用 `圖#XX`） |
| Facebook URL（社群轉發連結） | Facebook | `yt-dlp` 下載到 `D:\Downloads`，做法同 YouTube；清單摘要簡短時先抽樣看完整支片再下判斷 | `FB` |

## API 直取（2026-08-03 訂案，AP／RT／NS 首選路徑）

**核心**：定位、文稿、（AP／RT 的）影片下載**全部走 API，不點 UI**。三站端到端實測完成。**API 失敗兩次就退回下一節的 UI 舊做法**，不要死磕。

**共同前提**
- **一律用 Playwright 工具組**（`mcp__browser__*`），不是 claude-in-chrome（NS 的 localStorage 在 claude-in-chrome 會被 extension 隱私防護擋死）。
- **開工前檢查 profile 殘留**（多 agent 並行會互鎖；0803 曾害 RT 三輪誤判「全站 0 素材」）：
  `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ? { $_.CommandLine -like "*playwright-mcp-profile*" }`，閒置就 `Stop-Process -Force`；**自己收工也要關**。
- ⚠️ **下載落點是 `D:\Downloads\PlaywrightMCP\`，不是 `D:\Downloads\`**（2026-08-03 實測）。改名時從這裡取檔；Playwright 會把檔名裡的 `_`／空格換成 `-`，**別假設檔名原樣保留**。
- **費用：不必事前把關、不必為此停下來**（2026-08-03 使用者訂正）——**使用者提交清單時已人工確認過都是免費素材**，本流程照單全收即可，不要因為費用欄位而卡住或反覆確認。
  - 但**看到就順手回報**：費用欄位本來就在你已經取回的回應裡（RT 的 `points`／`free` 就在文稿那份 item 回應；AP 的 `Term` 在 `downloadnr/check`，而 check 本來就是拿 `ContentId` 的必要步驟），**零額外呼叫**。若發現某筆不是免費（RT `points` 非 0，或 AP `AppliedPrice` 非 0／`IsAlaCarte: true`），**照樣下載**，但在回報裡列出該筆與數值，當人工核對的備援。

### RT（文稿＋影片都可 API）

1. **定位**：照 `13b` §1b DOM 直撈 `a[href*="detail?id="]` 拿 guid。Edit No 可從 guid 的 `newsml_RW{4碼}` 推出、與清單值互相校驗。
2. **文稿**：`GET /api/item/{guid}?hash={hash}&live=false`（同源 fetch＋`credentials:'include'`）→ SCRIPT＋SHOTLIST＋Restrictions 一次到手。`hash` **照抄當下頁面請求**（實測 `klwn20`，但那是前端 build hash、改版會變，不要硬編）。
3. **費用（只記錄不擋）**：同一份 item 回應裡的 `~:points`／`~:free` 順手看一眼；非 0 照樣下載，但列進回報。
4. **影片**：從 renditions 取 **`...-STREAM:{n}:16X9:HD1080I60:MP4`**（＝UI 預設 HD 60fps；沒有就退 `HD1080I50`），組
   `https://www.reutersconnect.com/api/download/video/{guid}/{binaryId}?filename={檔名}&hash={hash}&purchase-type=ayce`
   在頁面內 `a.href=url; a.download=檔名; a.click()` 觸發（`purchase-type=ayce`＝訂閱吃到飽）。
   ✅ **`filename` 可直接指定成目標檔名**（如 `西國不敗1200 #01 RT.mp4`），省掉事後改名。

### AP（文稿＋影片都可 API）

1. **定位**：`POST https://api.newsroom.ap.org/v1/nrsearch/search/topic`（cookie 驗證）。**照抄頁面實際發出的 request body**（順序才與畫面一致）；⚠️ **`PageNumber` 不可靠**（實測 Page 2 回 100 筆、與 Page 1 零重疊），要多筆就**固定 `PageNumber=1` 加大 `PageSize`**（16／50／100／200 實測精準）。`_source.itemid`＝32 碼 GUID，`_source.editorialid`＝AP 編號。
2. **文稿**：`POST /v1/nrsearch/search/item/details`，body `{"ItemIds":"{itemid}","mediaType":"video","IsNonSalable":false}`。**逗號串多則不支援**，一則一次；但可在同一個 `browser_evaluate` 裡 `Promise.all` 打 N 則（工具呼叫仍只算 1 次）。
3. **`check`（拿 rendition 用，順帶看費用）**：`POST /v1/downloadnr/check`，body `{"ItemIds":["{itemid}"],"IsClip":false,"IsNonSalable":false}`。**這步不能省**——第 4 步要用它回傳的 `ContentId`／`ContentRenditionId`。回應的 `Term`（`AppliedPrice`／`MeteredType`／`IsAlaCarte`）順手看一眼，非免費照樣下載但列進回報。
4. **影片**：同一份 check 回應的 `Renditions` 挑 `Duid: "vid-1080i-main-60-slate"`（HD 1080i60 MP4），取其 `ContentId` 與 `ContentRenditionId`，再打
   `POST /v1/downloadnr/tick`，body
   `{"Ticks":[{"ItemId":"{itemid}","MediaType":"video","Role":"Main","Title":"{slug}","ContentId":"{ContentId}","StoryNumber":"{editorialid}","ContentRenditionId":{ContentRenditionId},"RecordSequenceNumber":1}],"StoryItemID":null}`
   → 回應的 **`ClientMediaUrl`** 就是簽章直連（CloudFront，**約 15 分鐘到期**），`a.click()` 下載即可，`FileName` 也一併給。
   ⚠️ `tick` 是 AP 的下載計數／授權登錄，**不可為了省一步跳過**——沒有它也拿不到 `ClientMediaUrl`。

### CNN Newsource（NS）：文稿走 API，**影片只能走 UI**

- **文稿（大幅省成本）**：`POST https://newsource-content-api-530.ns.cnn.com/api/v3/stories`（Bearer token 在 `localStorage.newsourceSession.token`）——**清單回應直接含 `content.bitcentral.script` 全文**，不必開任何詳情頁或 Preview modal。完整配方見 `G:\...\自動掃帶系統\0803-NS掃帶卡點報告-回覆.txt`。
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

**ENEX／ABC：** 沒有教學對應網站/流程，遇到時停下來問使用者，不要自行猜測去哪裡下載。

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
⚠️ **兩個落點不一樣**：`yt-dlp` 系（YouTube／X／FB／DVIDS）落在 **`D:\Downloads`**；**瀏覽器下載（AP／RT／NS，含 API 直取）落在 `D:\Downloads\PlaywrightMCP`**（2026-08-03 實測）。找不到檔案時先確認自己在看哪一個資料夾。

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

全部下載改名完成後，去 Google Drive「Claude共用」底下 **`SOT自動寫稿測試\` 底下新建一個以 SLUG 命名的子資料夾**（例如「梅西再勝1200」，不是直接放 Claude共用根目錄，也不是放 `SOT自動寫稿測試` 外面），把這批全部檔案（影片/圖片本體＋文稿 txt）都放進去。走本機同步資料夾操作：先建立該子資料夾，再複製進 `G:\我的雲端硬碟\Claude共用\SOT自動寫稿測試\{SLUG}\`，優先用本機同步資料夾而非 MCP 上傳大檔。

⚠️ **2026-07-24 訂正**：此路徑原本是 `Claude共用\{SLUG}\`（母端根目錄下），與 [`自動寫稿(SOT)`](../common/06-auto-script-sot.md) 2026-07-22 訂定的「完成稿放 `SOT自動寫稿測試\{SLUG}\`、不放母端根目錄」規則沒有同步，導致同一個 SLUG 產生兩個路徑不同的資料夾（「外送抓匪1700」案例踩過）。現改為與 SOT 完成稿共用同一個 `SOT自動寫稿測試\{SLUG}\` 路徑，素材與完成文稿統一放在一起。

## 全部完成後

輸出彙整表（編號｜來源｜檔名｜限制重點），對不尋常的限制（整個地區禁用、特定媒體黑名單等）加註 ⚠️ 提醒。

## 後續銜接

下載＋上傳完成後，若使用者明確下令，可接續 [`自動寫稿(SOT)`](../common/06-auto-script-sot.md) 寫成台灣播出格式完成文稿；此步驟不會自動觸發。
