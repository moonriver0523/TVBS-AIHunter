# 自動掐SO(RT)

當使用者以此名稱呼叫（或給出 Edit No. + 引言 + 目標檔名，明確要求剪出對應片段），依下列五步驟執行，不需逐步再次確認：

## 1. 搜尋 Reuters Connect 並開啟該則
依 [`01-search-workflow.md`](01-search-workflow.md)：以 Edit No. 用「**Video**」分頁搜尋，開啟詳細頁面，點擊 script 的「VIEW MORE」查看完整 shotlist。檢查並回報 Restrictions 面板內容（若有限制）。下載影片到預設下載位置 `D:\Downloads`，預設格式 **HD 60fps MP4**，不需詢問格式。

## 2. 找出引言的精確 TC
將引言與頁面的「Video Transcript」面板比對，該面板提供逐行時間碼（例如 `00:00:10`、`00:00:16`、`00:00:23`...）。片段區間為：該句引言自身的時間碼 → 下一行逐字稿開始的時間碼。

⚠️ 此面板的時間戳記**不可點擊/不可跳轉**，其標示的逐行起始時間即是最精細的可用精度，不要宣稱比這更精確。

## 3. 提供該 TC 區間的雙語逐字稿
英文逐字引用 script/transcript 面板原文，搭配原創的繁體中文翻譯。這是針對已指定引言的局部查找，不是整則的完整逐字稿。

## 4. 用 ffmpeg 在本機剪出片段
依步驟 2 找出的 TC 區間，對步驟 1 下載的檔案執行：

```
ffmpeg -y -i "<downloaded file>" -ss <start> -to <end> -c:v libx264 -c:a aac -avoid_negative_ts make_zero "<output filename>.mp4"
```

輸出檔名由使用者當次指定（例如「歐限兒網1800SO.mp4」），沒有固定命名規則。

## 5. 上傳剪好的片段到 Google Drive
將輸出檔案複製到 `G:\我的雲端硬碟\Claude共用\`（目前唯一的共用上傳/輸入資料夾），檔名維持使用者指定的原樣。

## 版權注意
逐字引用僅限使用者指定的短引言片段，不做整則逐字稿。
