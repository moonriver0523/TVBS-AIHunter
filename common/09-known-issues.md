# 已知問題與疑難排解

這份文件收錄「特定站台/工具在特定情況下才會出現」的症狀與解法，跟 [`08-execution-efficiency.md`](08-execution-efficiency.md) 的預設行為準則不同——**不需要在每次執行流程前主動整份讀過**，只要在執行中真的撞到對應症狀時才查閱對應章節即可，避免每個任務都要讀一堆用不到的邊角案例。

`08-execution-efficiency.md` 底部有一份症狀關鍵字索引，對照到這裡的章節。

**Rollback：** 2026-07-20 從 `08-execution-efficiency.md` 拆分出來，原文見該檔案的 git 歷史。

## CNN Newsource

**症狀：** 搜尋框按 Enter 沒有觸發搜尋，或關鍵字被清空、結果沒有更新。
**解法：** 改用點擊搜尋/放大鏡圖示送出，不要依賴 Enter。

**症狀：** 下載回來的檔案 `LastWriteTime`（修改時間）顯示成很早之前的日期，跟實際下載時間對不上。
**解法：** 不要用時間戳記判斷下載是否剛完成，改用「檔名是否已出現＋檔案大小是否穩定不再變動」判斷。

**症狀：** 在搜尋欄輸入 ID 送出後，分頁 renderer 凍結——`Page.captureScreenshot` 連續 CDP timeout（30 秒），工具可能回報「無法判斷此動作要操作哪個分頁」。
**解法：** CTV 屬「單支任務」，依 [`08-execution-efficiency.md`](08-execution-efficiency.md) 的重試階梯**直接回報使用者，不無限重試**。此症狀與下方「搜尋框按 Enter 沒反應」不同——那是沒觸發搜尋，這是送出後整頁無回應（2026-07-21 PY-03MO 實例）。

**症狀：** 展開單則搜尋結果的詳情框（點右側 chevron 展開 Story Number/Title/Script 等欄位）後，找不到能看完整稿件的「≡Q」（Preview w/Script）圖示。
**解法：** 這個圖示只在卡片「收合」狀態的 `Media :` 列才看得到（緊鄰下載圖示左側），展開詳情框後圖示會消失／不在同一列。要點 Preview 前先確認卡片是收合狀態；螢幕截圖找一次沒看到就直接用 `find` 工具搜尋「Preview w/Script」按鈕，不要重複 zoom 猜座標位置。

## 瀏覽器自動化

**症狀：** 點擊先前記下的座標，結果點到不相關的元素，或操作沒有反應——常發生在返回列表、關閉彈窗、頁面捲動之後，版面已經跟記下座標時不一樣了。
**解法：** 導覽類操作（返回列表、換頁）優先直接帶網址重新導航；真的需要用座標時，先重新截圖確認目前版面，不要沿用前一次畫面的座標假設當前畫面沒變。

**症狀：** 大檔（數百 MB）下載進行中，對同一分頁 `screenshot` 連續回「Script injection timed out after 5000ms — the page is busy or mid-navigation」，`get_page_text` 也回「No text content found」。
**解法：** **重新 `navigate` 到目標網址即恢復**，不需要重開分頁或重啟瀏覽器，也不要據此判定工具或站台故障（2026-07-21 RT9434／406MB 實例，3 次逾時後 navigate 即恢復）。過程中詳情頁可能自行開出新分頁，後續操作先用 `tabs_context_mcp` 確認在對的分頁上。

**症狀：** `find` 回報找不到元素／「0 items」，但畫面明明已經渲染出來。
**解法：** 先 `screenshot` 一次，緊接著同一批呼叫內再 `find`。accessibility tree 不會隨頁面自行更新，需要一次 screenshot 觸發快照刷新——**等待更久沒有用**（實測連續等 18 秒不截圖仍回 0 items）。此現象在 Reuters 已實證並寫進 [`../reuters/01-search-workflow.md`](../reuters/01-search-workflow.md) 的標準流程；**是否為跨站台通則尚未驗證**，其他站台遇到時可比照試一次。

**症狀：** `find`（語意定位）工具回傳伺服器過載（overloaded）錯誤。
**解法：** 失敗一次就直接退回座標點擊完成當前操作，不要重複呼叫同一個 `find` 硬等。

**症狀：** 下載的檔案沒有出現在預期的資料夾（例如某些瀏覽器自動化工具會落在專屬暫存資料夾，不是系統預設的 `D:\Downloads`）。
**解法：** 下載完成的判定以工具實際回報或找到檔案的路徑為準，不要在流程文件裡寫死單一路徑後就不加驗證。

## video_analyze

**症狀：** 同時對多支影片送出 `video_analyze`，全部被安全分類器暫時拒絕，等於多次無效呼叫。
**解法：** 先對其中1支跑，確認沒有被分類器拒絕、服務正常回應後，才平行展開處理其餘影片。

## 接觸表（Contact Sheet）

**不是預設分析方式，只在真的需要一次性瀏覽整支片的縮圖時才用**——正常流程仍先用 `video_analyze` 找候選區段，再用 `video_detail` 低解析抽幀，不要一開始就想做接觸表。

**需要接觸表時：** 統一用 [`scripts/make_contact_sheet.ps1`](../scripts/make_contact_sheet.ps1)，用法：`powershell -File scripts/make_contact_sheet.ps1 -InputPath "素材.mp4" -IntervalSeconds 10`。這支腳本直接指定 `C:\Windows\Fonts\msjh.ttc` 當字型來源，避開 Windows 環境常缺設定的 Fontconfig 字型查找；`drawtext` 加時間戳失敗時會自動退回不帶文字的接觸表，不會整個失敗。腳本預設拒絕覆蓋既有輸出（不用 `ffmpeg -y`），需要重新產生時先手動處理舊檔或指定新的 `-OutputPath`。

**Reuters 點數在測試下載期間減少（未釐清）**
2026-07-21：素材頁顯示 `HD 60fps (MP4) = Included`、只有 `Download Audio (WAV split)` 標 2pts，依此下載 MP4 不應扣點；但同期間帳號點數由 452 降至 446（少 6 點），無法從畫面確認是否由 AI 的下載造成。在查明前，[`08-execution-efficiency.md`](08-execution-efficiency.md) 的「不得用會消耗額度的操作做測試」禁令維持有效，**不得以「Included 就不扣點」為由自行放寬**。另已確認「FREE TO ME」標示**不是**可靠的免扣點指標。

**Chrome 自動下載封鎖導致批次下載全滅（已破案）**
2026-07-21 封冠遊行1200：整批 RT 素材只有第一支成功，之後全部檔案不落地。真因是 Chrome 對同一網站連續自動下載的內建封鎖，**不是** 503、不是帳號問題、也不是「CDP 合成點擊不帶 user activation」（這兩個結論都曾被提出並已作廢）。誤判的根源是把 `reutersconnect.com` 加進允許清單後**沒有重新載入頁面**就繼續測試。重新 navigate 後 4/4 成功。規則見 [`08-execution-efficiency.md`](08-execution-efficiency.md) 的前置檢查。
