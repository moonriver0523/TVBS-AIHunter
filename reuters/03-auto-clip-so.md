# 自動掐SO(RT)

當使用者以此名稱呼叫（或給出 Edit No. + 引言 + 目標檔名，明確要求剪出對應片段），依下列五步驟執行，不需逐步再次確認。

瀏覽器操作套用 [`../common/08-execution-efficiency.md`](../common/08-execution-efficiency.md)。找 TC 的文字優先序與「先選句再定位」對齊 [`../common/07-bite-assistant.md`](../common/07-bite-assistant.md)。

**Rollback：** 省 Token 改寫前舊版見 [`../_archive/reuters/03-auto-clip-so.pre-token-saving-2026-07-20.md`](../_archive/reuters/03-auto-clip-so.pre-token-saving-2026-07-20.md)。

## 省 Token 核心流程（優先遵守）

1. **TC 來源優先 Video Transcript 面板**（有逐行時間碼就停）。使用者已給定引言時，**不要**為了剪一句把完整 shotlist／VIEW MORE 全文貼進對話。
2. **Restrictions 一句話回報**即可；無限制就說無。
3. **下載確認用檔案系統**（`D:\Downloads` 檔名＋大小），不截圖確認進度。
4. **步驟 3 只輸出該 TC 區間**的雙語逐字，不附前後大段 transcript。
5. 能 batch 的搜尋→開頁→點 Download 就 batch；少截圖。

## 1. 搜尋 Reuters Connect 並開啟該則
依 [`01-search-workflow.md`](01-search-workflow.md)：以 Edit No. 用「**Video**」分頁搜尋，開啟詳細頁面。優先打開「Video Transcript」面板找引言 TC；只有 transcript 對不到、需要 shotlist 上下文時，才點 script 的「VIEW MORE」。檢查並回報 Restrictions 面板內容（若有限制）。下載影片到預設下載位置 `D:\Downloads`，預設格式 **HD 60fps MP4**，不需詢問格式；完成與否以資料夾檔案為準。

## 2. 找出引言的精確 TC
將使用者指定的引言與頁面的「Video Transcript」面板比對，該面板提供逐行時間碼（例如 `00:00:10`、`00:00:16`、`00:00:23`...）。可先取引言 5–10 個關鍵字在面板文字中定位，再讀命中列的時間碼。片段區間為：該句引言自身的時間碼 → 下一行逐字稿開始的時間碼。

⚠️ 此面板的時間戳記**不可點擊/不可跳轉**，其標示的逐行起始時間即是最精細的可用精度，不要宣稱比這更精確。

## 3. 提供該 TC 區間的雙語逐字稿
英文逐字引用 script/transcript 面板原文，搭配原創的繁體中文翻譯。這是針對已指定引言的局部查找，不是整則的完整逐字稿——**只輸出剪輯區間內的句子**。

## 4. 用 ffmpeg 在本機剪出片段
依步驟 2 找出的 TC 區間，對步驟 1 下載的檔案執行：

```
ffmpeg -y -i "<downloaded file>" -ss <start> -to <end> -c:v libx264 -c:a aac -avoid_negative_ts make_zero "<output filename>.mp4"
```

輸出檔名由使用者當次指定（例如「歐限兒網1800SO.mp4」），沒有固定命名規則。

## 5. 上傳剪好的片段到 Google Drive
將輸出檔案複製到 `G:\我的雲端硬碟\Claude共用\` **根目錄**（單支剪輯不建 SLUG 子資料夾；批次類流程才建，見 [`common/01-shared-folders.md`](../common/01-shared-folders.md)），檔名維持使用者指定的原樣。大檔用本機同步資料夾複製。

## 版權注意
依 [`common/00-寫稿通則.md`](../common/00-寫稿通則.md)；逐字引用僅限使用者指定的短引言片段，不做整則逐字稿。
