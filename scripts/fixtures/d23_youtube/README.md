# D23 YouTube fixtures

這些檔案是 D23 Phase 0 的去憑證、不可連外測試資料。內容是合成的
`playlistItems.list`／`videos.list`／字幕 runner 回應，刻意覆蓋：

- CNA playlist 三頁與 `nextPageToken`，包含窗口下界前一筆與重複 video ID。
- YNA 的自動翻譯 `zh-Hant` 字幕與 CNA 的英文自動字幕。
- 缺字幕、private、live、頻道不符、join 缺列與跨時區 UTC timestamp 的測試形狀。

測試只從這個目錄載入 JSON，不含 API key、cookie、真實抓取內容或完整 yt-dlp 命令。

