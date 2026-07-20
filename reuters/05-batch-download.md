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

## 開始下載前：存清單

清單與 SLUG 都確認無誤、也做完開始前檢查（無異常重複）之後，**先把這份完整編號清單存成一份 txt**（檔名 `{SLUG} 素材清單.txt`），上傳到 Google Drive「Claude共用」底下的 SLUG 子資料夾（子資料夾還沒建立就先建立），再開始逐筆下載。**不用把清單內容再貼回對話視窗給使用者看**——清單使用者前面已經看過確認過，直接存檔即可，不必重複輸出。

## 來源分派表

| 代碼前綴/類型 | 實際來源 | 細節流程 | 檔名來源縮寫 |
|---|---|---|---|
| `RT`／`RTV` | Reuters Connect | [`搜尋外電素材(RT)`](01-search-workflow.md) | `RT` |
| `AP` | AP Newsroom | [`搜尋外電素材(AP)`](../ap/01-search-workflow.md)／[`找AP照片`](../ap/02-photo-search.md) | `AP` |
| `IN-XX` 組合碼 | CNN Newsource | [`自動寫稿(CTV)`](../cnn/01-auto-script-writing.md) | `CNN`（NEWSOURCE＝CNN Newsource） |
| `ENEX` | 尚無教學說明 | 遇到先問使用者要去哪裡找 | `ENEX` |
| `ABC` | 尚無教學說明 | 遇到先問使用者要去哪裡找 | `ABC` |
| YouTube URL | YouTube | `yt-dlp` 下載到 `D:\Downloads` | `YT` |
| X 影片 URL（網址含 "Video"） | X | `yt-dlp` 下載到 `D:\Downloads` | `X` |
| X 照片 URL（網址含 "Photo"，用**圖片編號**） | X | 瀏覽器開原圖 URL，右鍵另存到 `D:\Downloads` | `X`（檔名用 `圖#XX`） |
| Facebook URL（社群轉發連結） | Facebook | `yt-dlp` 下載到 `D:\Downloads`，做法同 YouTube；清單摘要簡短時先抽樣看完整支片再下判斷 | `FB` |

## 各來源處理細節

**RT／RTV：**
1. reutersconnect.com，Video 分頁，搜尋 Edit No.（My Subscription 維持預設關或開都可以，只要找得到）。
2. Edit No. 可能撞號到不相關舊新聞——核對標題/主題是否符合這批清單脈絡，不要無腦點第一筆結果。
3. 開詳情頁，記錄右側 **Restrictions** 面板完整內容＋複製 **Video Transcript**／逐字稿全文，合併存成該筆的文稿 txt。
4. 點 **Download**（HD 60fps (MP4) 是預設選項，不用另外選）。

**AP：**
1. 用純數字 ID 搜尋，媒體類型選對 Video 或 Photo（不要照抄「AP」字首去搜，那只是站台判斷標記）。
2. 影片：進詳情頁的 **Shotlist** 分頁（限制摘要＋SOUNDBITE＋STORYLINE）存成文稿 txt；按 Download 選 Master＋任一 HD 格式送出——**非同步處理，不用在 AP 網站的 Downloads 頁面等 ready，完成後直接進 D:\Downloads**。
3. 照片：列表頁卡片上的 ⬇ 圖示可直接下載（同步即時）；詳情頁 **Photo Metadata** 含 **Special Instructions**（限制）存成文稿 txt。

**CNN Newsource（`IN-XX` 組合碼）：** 依 [`自動寫稿(CTV)`](../cnn/01-auto-script-writing.md)，用「≡Q」預覽圖示取得官方 script 全文存成文稿 txt，下載影片，比對 TC。

**ENEX／ABC：** 沒有教學對應網站/流程，遇到時停下來問使用者，不要自行猜測去哪裡下載。

**YouTube：** 用 `yt-dlp` 下載影片到 `D:\Downloads`（選合理可用的最高畫質 mp4）。沒有教「文稿」的抓取方式，若使用者要文稿，先問。

**X（Twitter）：**
- 影片（URL 含 "Video"）：`yt-dlp` 下載到 `D:\Downloads`。
- 照片（URL 含 "Photo"）：瀏覽器打開該貼文/原圖 URL，右鍵另存圖片到 `D:\Downloads`。

兩者都沒教「文稿」的抓取方式，遇到時先問使用者。

**Facebook（或其他社群轉發連結，清單摘要只有一句話時）：** 用 `yt-dlp` 下載到 `D:\Downloads`，做法比照 YouTube。**若清單裡的摘要只有短短一句話（例如「網友轉發＿＿影片」），下載完成後務必先對整支影片做全長度抽樣（`video_analyze`＋`video_detail` 稀疏抽樣，見 [`common/07-bite-assistant.md`](../common/07-bite-assistant.md) 的 B-roll TC 補充情境），確認實際內容與敏感程度後才決定寫稿時怎麼呈現，不能只憑清單那句摘要判斷。**尤其當這篇新聞的標題本身已經偏敏感/聳動時（例如涉及特定人物人身安全、路線曝光等），更要先看完整支片再下判斷；2026-07-20「追殺川普1730」案例中，清單摘要只寫「網友下載伊朗媒體的影片轉發」，實際整支2分50秒是詳細標出座車型號、行館位置與抵達時間的動畫地圖，若不先抽樣看完整支片，容易低估內容尺度。

## 下載確認與卡住處理

用 PowerShell 輪詢 `D:\Downloads`（`Get-ChildItem -File | Where-Object {LastWriteTime -gt (Get-Date).AddMinutes(-2)}`），確認檔案（.crdownload 或臨時檔）已完成、大小穩定。

**單一素材卡住（重試 2-3 次仍 503／無回應／進度不動）時，先跳過這一筆，繼續處理清單中下一筆，不要讓整批流程卡在這一筆上。** 全部其他素材跑完後，回頭把卡住的項目再補試一次；仍然失敗才在最終彙整表中列為 ⚠️ 未完成，並回報使用者是否要再手動排除障礙或換個時間重試。

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

全部下載改名完成後，去 Google Drive「Claude共用」底下**新建一個以 SLUG 命名的子資料夾**（例如「梅西再勝1200」，不是直接放 Claude共用根目錄），把這批全部檔案（影片/圖片本體＋文稿 txt）都放進去。走本機同步資料夾操作：先建立該子資料夾，再複製進 `G:\我的雲端硬碟\Claude共用\{SLUG}\`，優先用本機同步資料夾而非 MCP 上傳大檔。

## 全部完成後

輸出彙整表（編號｜來源｜檔名｜限制重點），對不尋常的限制（整個地區禁用、特定媒體黑名單等）加註 ⚠️ 提醒。

## 後續銜接

下載＋上傳完成後，若使用者明確下令，可接續 [`自動寫稿(SOT)`](../common/06-auto-script-sot.md) 寫成台灣播出格式完成文稿；此步驟不會自動觸發。
