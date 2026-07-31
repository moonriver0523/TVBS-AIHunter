# 搜尋外電素材(AP)

當使用者給出帶 **`AP`** 字首的編號（例如「AP4672591」）或關鍵字，要求尋找對應的外電素材時，使用瀏覽器工具在 **AP Newsroom**（newsroom.ap.org，需已登入）上操作。這是 [`搜尋外電素材(RT)`](../reuters/01-search-workflow.md) 的 AP 版本，兩站並行使用。

瀏覽器操作套用 [`../common/08-execution-efficiency.md`](../common/08-execution-efficiency.md)。

**Rollback：** 省 Token 改寫前舊版見 [`../_archive/ap/01-search-workflow.pre-token-saving-2026-07-20.md`](../_archive/ap/01-search-workflow.pre-token-saving-2026-07-20.md)。

## 省 Token 執行備註

- 搜尋 → 選對媒體分頁 → 開詳情：能 batch 就 batch；不要每步截圖。
- **預設回報欄位**：標題、純數字 ID、媒體類型、Restriction Summary 一句、是否有 SOUNDBITE。使用者沒要求時不要貼完整 Shotlist/Storyline。
- 下載完成與否**只查** `D:\Downloads`（檔名＋大小），不要在 AP 網站 Downloads 列表空等或截圖確認。
- 無 TC 時的 `video_analyze` 規則見下方；同一支片只分析一次，對齊 [`../common/07-bite-assistant.md`](../common/07-bite-assistant.md)／[`../cnn/02-clip-bite.md`](../cnn/02-clip-bite.md)。**本文件的找 TC 敘述若與 `07` 不一致，一律以 `07` 為準。**

## 如何判斷該去 RT 還是 AP

編號帶 **`AP`** 字首時，代表要去 AP Newsroom 找——**`AP` 本身只是站台判斷標記，不是搜尋字串的一部分**。實際搜尋只打純數字部分（例如 `4672591`）。沒有字首、或明確指名 RT/Reuters 的，走 Reuters 流程。

## 可靠流程

1. **優先用網址直接查詢（2026-07-21 實證）**：`navigate` 到
   `https://newsroom.ap.org/home/search?query={關鍵字或純數字ID}&mediaType=video`
   （照片為 `&mediaType=photo`）。本次 16 筆素材與 3 張照片全部一次到位。
   - ⚠️ **不要用** `https://newsroom.ap.org/search?query={ID}`——會掉到 **Planning 頁**，顯示「There is no coverage plan for your selection / 0 plans」，看起來像查無資料。
   - 頂部搜尋框仍可作備援。
2. **務必選對媒體類型分頁**（Photo／Video／Text／Graphics／Audio）——選錯類型會直接搜不到（例如同一編號在 Photo 下 0 結果，切到 Video 才精準命中）。沒有特別說明類型時預設先試 Video。
3. 選「Search with keywords」（不是「with AI」）。
4. 點結果卡片會先觸發卡片內縮圖預覽播放；要開該素材的完整詳情頁，需點卡片右上角的展開圖示（↗），會開一個新分頁 `/detail/{slug}/{id}/video`。

## 詳情頁結構

- 標題 + **Download** 按鈕 + pin/copy/print/share 圖示
- 三個分頁：
  - **Thumbnails** — 縮圖
  - **Metadata** — Slug／Arrival Date／Creation Date／Duration／**ID**（下載檔名會用這個編號）／**Provided By**／Source／Dateline／Location／Usage Type／People Shown／People Mentioned／Subjects
  - **Shotlist** — 對應 RT 的逐字稿頁，內容依序是：**Restriction Summary**（使用限制摘要）→ 逐條 **SOUNDBITE** 引言（帶 `++...++` 製作註記，是翻譯後的引言文字，**沒有精確 TC**）→ **STORYLINE**（完整新聞稿全文）。有「Find in Shotlist」可在頁內搜關鍵字。
- **`Provided by: SNTV`（2026-07-31）**：**可以收、不要略過**。仍用 `AP`＋7 碼編號；寫進庫存／稿單／回報時備註**必標 `(SNTV)`**。頁尾常有「This content is not produced or verified by the Associated Press」——與 `vrb`／`stltd`／`un` 等**要扣點的 stringer 前綴**不同，不要混判排除。詳見 [`../common/13-S2-定時掃帶.md`](../common/13-S2-定時掃帶.md)。
- 沒有 TC 時，比照 [`CNN掐Bite`](../cnn/02-clip-bite.md) 的做法：下載後用 `video_analyze`（transcription）補時間點，引言文字仍以官方 Shotlist/Storyline 文字為準，不可用 ASR 文字取代官方文字。

### 取 Shotlist 的標準做法：開新分頁（2026-07-21 實證，取代截圖逐段讀）

點卡片標題後 Shotlist 開在 **modal** 裡，此時 `get_page_text` 抓到的是**彈窗背後的搜尋清單**，不是 Shotlist——只能靠截圖逐段捲讀，很花 token 且會被裁切。

**正解**：彈窗右上點 **「Open in a new tab」**，開出真正的詳情分頁 `newsroom.ap.org/detail/{標題去空白}/{hash}/video?...`，對該分頁 `get_page_text` 可一次抓到**完整純文字**，比截圖版多拿到：

- 完整 **STORYLINE**（截圖版只讀得到第一段就被裁掉）
- **Video Metadata** 全欄位（Slug／Arrival & Creation Date／Duration／ID／Dateline／Location／Usage Type／People Shown／People Mentioned／Subjects）
- **Restrictions** 與 **Use information** 原文
- 攝影記者署名、「More like this」相關素材清單（可當同題材補素材線索）

注意事項：
- 詳情頁網址含 hash，**無法自己組出來**，一定要先點卡片標題開 modal 再點 Open in a new tab。
- 點卡片標題有時第一下只叫出 hover 圖示列而沒開 modal，需再點一次。
- 會多開一個分頁，後續操作用 `tabs_context_mcp` 確認 tabId，不要對舊分頁下指令。
- **彈窗的 Close 需要點兩次**（第一次會變成放大的播放器）。**不要關彈窗**，直接 `navigate` 到下一個搜尋網址最穩。

## 下載流程

1. 點 Download 按鈕 → 彈出對話框：選 **Master**（乾淨高解析度，供最終成品用）或 **Screener**，再選 **Format**（如 HD: 1080i50／1080i50 (Archive)／1080i60，1920x1080 16:9 MP4）。
2. 送出後跳「Your download request is in progress.」——這是**非同步背景處理**，**不需要**一直盯著網站右上角的 Downloads 頁面等它顯示「ready」，那個列表更新可能很慢或看不到；下載完成後檔案會直接落地到本機瀏覽器預設下載資料夾（`D:\Downloads`），檔名格式是 `{素材ID}_HD_{格式}.mp4`（例如 `4672591_HD_1080i50.mp4`）。要確認下載結果直接去 `D:\Downloads` 看檔案，不要在 AP 網站裡空轉等待。

## 版權注意
依 [`common/00-寫稿通則.md`](../common/00-寫稿通則.md)。
