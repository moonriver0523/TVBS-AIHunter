# 搜尋外電素材(AP)

當使用者給出帶 **`AP`** 字首的編號（例如「AP4672591」）或關鍵字，要求尋找對應的外電素材時，使用瀏覽器工具在 **AP Newsroom**（newsroom.ap.org，需已登入）上操作。這是 [`搜尋外電素材(RT)`](../reuters/01-search-workflow.md) 的 AP 版本，兩站並行使用。

## 如何判斷該去 RT 還是 AP

編號帶 **`AP`** 字首時，代表要去 AP Newsroom 找——**`AP` 本身只是站台判斷標記，不是搜尋字串的一部分**。實際搜尋只打純數字部分（例如 `4672591`）。沒有字首、或明確指名 RT/Reuters 的，走 Reuters 流程。

## 可靠流程

1. 頂部搜尋框輸入純數字編號或關鍵字。
2. **務必選對媒體類型分頁**（Photo／Video／Text／Graphics／Audio）——選錯類型會直接搜不到（例如同一編號在 Photo 下 0 結果，切到 Video 才精準命中）。沒有特別說明類型時預設先試 Video。
3. 選「Search with keywords」（不是「with AI」）。
4. 點結果卡片會先觸發卡片內縮圖預覽播放；要開該素材的完整詳情頁，需點卡片右上角的展開圖示（↗），會開一個新分頁 `/detail/{slug}/{id}/video`。

## 詳情頁結構

- 標題 + **Download** 按鈕 + pin/copy/print/share 圖示
- 三個分頁：
  - **Thumbnails** — 縮圖
  - **Metadata** — Slug／Arrival Date／Creation Date／Duration／**ID**（下載檔名會用這個編號）／Provided By／Source／Dateline／Location／Usage Type／People Shown／People Mentioned／Subjects
  - **Shotlist** — 對應 RT 的逐字稿頁，內容依序是：**Restriction Summary**（使用限制摘要）→ 逐條 **SOUNDBITE** 引言（帶 `++...++` 製作註記，是翻譯後的引言文字，**沒有精確 TC**）→ **STORYLINE**（完整新聞稿全文）。有「Find in Shotlist」可在頁內搜關鍵字。
- 沒有 TC 時，比照 [`CNN掐Bite`](../cnn/02-clip-bite.md) 的做法：下載後用 `video_analyze`（transcription）補時間點，引言文字仍以官方 Shotlist/Storyline 文字為準，不可用 ASR 文字取代官方文字。

## 下載流程

1. 點 Download 按鈕 → 彈出對話框：選 **Master**（乾淨高解析度，供最終成品用）或 **Screener**，再選 **Format**（如 HD: 1080i50／1080i50 (Archive)／1080i60，1920x1080 16:9 MP4）。
2. 送出後跳「Your download request is in progress.」——這是**非同步背景處理**，**不需要**一直盯著網站右上角的 Downloads 頁面等它顯示「ready」，那個列表更新可能很慢或看不到；下載完成後檔案會直接落地到本機瀏覽器預設下載資料夾（`D:\Downloads`），檔名格式是 `{素材ID}_HD_{格式}.mp4`（例如 `4672591_HD_1080i50.mp4`）。要確認下載結果直接去 `D:\Downloads` 看檔案，不要在 AP 網站裡空轉等待。

## 版權注意

不要在對話中逐字貼出完整 Shotlist/Storyline 全文；如使用者要求特定內容，摘要/描述結構，僅在需要時引用簡短片段。
