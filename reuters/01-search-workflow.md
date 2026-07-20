# 搜尋外電素材(RT)

當使用者給出 Reuters 的 **Edit No.**（例如「7300」）或關鍵字，要求尋找對應的外電素材時，使用瀏覽器工具在 **Reuters Connect**（reutersconnect.com，需已登入）上操作。

瀏覽器操作套用 [`../common/08-execution-efficiency.md`](../common/08-execution-efficiency.md)。

**Rollback：** 省 Token 改寫前舊版見 [`../_archive/reuters/01-search-workflow.pre-token-saving-2026-07-20.md`](../_archive/reuters/01-search-workflow.pre-token-saving-2026-07-20.md)。

## 省 Token 執行備註

- 搜尋 → 切 Video 分頁 → 點標題：能 batch 就 batch；不要每步截圖。
- **預設回報欄位**：標題、Edit No.、Restrictions 摘要、是否有 Video Transcript（可否直接取 TC）。使用者沒要求全文時，不要貼 shotlist／script 全文。
- 下游流程（入庫、掐SO、批次下載）若需要完整文稿，在該流程內抓一次並**直接落檔**，不要在「搜尋」階段就先貼一整份進對話。

## 可靠流程

1. **優先用網址直接查詢，不要用搜尋框打字**：直接 `navigate` 到
   `https://www.reutersconnect.com/all?media-types=vid&search=all%3A{query}`
   （`{query}` 做 URL encode，空白轉 `%20`，例如關鍵字 `iran nuclear` → `all%3Airan%20nuclear`；Edit No. `7438` → `all%3A7438`）。
   這個網址已經固定在 **Video** 分頁、`media-types=vid`，等同「搜尋框輸入+切Video」一次到位，2026-07-20「通膨升息1730」案例驗證過純數字 Edit No. 與多字關鍵字都可行。
   - ⚠️ 主搜尋框用點擊+打字的方式不穩定——曾發生 `find` 抓到的 ref 點下去沒有真的把文字輸入進搜尋框（畫面還停在未過濾的全部結果），要retry用座標點擊才成功；直接改網址可以完全跳過這個點擊步驟。
   - 若使用者是用完整句子/複雜片語查詢，仍可退回主搜尋框手動輸入這個備援做法。
2. 分頁固定用 **「Video」**（已內含在上面的網址參數 `media-types=vid`）。
   - ⚠️「Text」分頁不穩定，曾出現同一組關鍵字前一刻查得到、重打卻顯示「0 items」的情況。
   - 「All」分頁在早期測試中可行，但後來使用者明確更正為固定用「Video」分頁，故 **一律以 Video 為準**。
3. 「My Subscription」toggle 保持預設 **ON**（用上面的網址直接查詢時，toggle 仍維持頁面預設的 ON，不用另外操作）——關閉會切換成不相關的第三方內容（例如「The Conversation」文章），不是 Reuters outwire 內容。
4. 若改用主搜尋框手動查詢：用連結文字（ref-based）定位並點擊正確的標題連結，**不要用座標點擊**清單項目——曾發生座標點擊點到錯誤元素、導致搜尋結果被重置為 0 筆的情況。
5. 點擊該則的標題連結（以「Edit No: XXXX」標籤辨識）進入該素材的詳細頁面，內含：
   - 影片
   - 「Video Transcript」面板（帶時間碼，原始語言，附「Automated Translation」切換）
   - 完整文字稿（shotlist 描述 + 「RESENDING WITH COMPLETE SCRIPT」正文）
   - 右側 **Restrictions** 面板，列出播出/數位使用限制（例如「No use BBC Persian」「No use VOA Persian」「No use Iran International」等）——這對新聞編輯室的使用者很重要，找到後務必回報。

## 版權注意
不要在對話中逐字貼出完整外電稿件內文；如使用者要求特定內容，摘要/描述結構，僅在需要時引用簡短片段。
