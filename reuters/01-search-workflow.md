# 搜尋外電素材(RT)

當使用者給出 Reuters 的 **Edit No.**（例如「7300」）或關鍵字，要求尋找對應的外電素材時，使用瀏覽器工具在 **Reuters Connect**（reutersconnect.com，需已登入）上操作。

瀏覽器操作套用 [`../common/08-execution-efficiency.md`](../common/08-execution-efficiency.md)。

**Rollback：** 省 Token 改寫前舊版見 [`../_archive/reuters/01-search-workflow.pre-token-saving-2026-07-20.md`](../_archive/reuters/01-search-workflow.pre-token-saving-2026-07-20.md)。

## 省 Token 執行備註

- 搜尋 → 切 Video 分頁 → 點標題：能 batch 就 batch；不要每步截圖。
- **預設回報欄位**：標題、Edit No.、Restrictions 摘要、是否有 Video Transcript（可否直接取 TC）。使用者沒要求全文時，不要貼 shotlist／script 全文。
- 下游流程（入庫、掐SO、批次下載）若需要完整文稿，在該流程內抓一次並**直接落檔**，不要在「搜尋」階段就先貼一整份進對話。

## 開始整批之前（只做一次）

1. 確認 `reutersconnect.com` 已在 Chrome 自動下載允許清單裡，且**設定後有重新載入頁面**——見 [`../common/08-execution-efficiency.md`](../common/08-execution-efficiency.md) 的前置檢查。這是自動化下載能不能運作的前提。
2. **確認「My Subscription」toggle 是 ON**（2026-07-21 修訂）。

   ⚠️ **舊規則說「用網址查詢時 toggle 會維持預設 ON」，這是錯的。** 實測 toggle 狀態會**跨頁 persist、由帳號／session 決定，不由網址參數決定**，整批搜尋期間可能全程是 OFF（灰色）。

   OFF 的後果：每個 Edit No. 回 **13~21 筆**，混進完全無關的舊新聞（烏克蘭獨立日、郵輪漢他病毒、Shein…），逼你每筆都截圖用肉眼比對標題才能確認點對。ON 的時候同樣的查詢是 **1 筆精準命中**。

   **判斷線索：Edit No. 搜尋若回超過個位數筆數，通常就是 toggle 是 OFF。** 第一次搜尋時在截圖上確認，OFF 就先點開；整批只需確認一次。

## 單筆素材標準流程（2026-07-21 實證版）

1. **`navigate`** 到 `https://www.reutersconnect.com/all?media-types=vid&search=all%3A{query}`
   （`{query}` 做 URL encode，空白轉 `%20`；關鍵字 `iran nuclear` → `all%3Airan%20nuclear`，Edit No. `7438` → `all%3A7438`）。這個網址已固定在 **Video** 分頁，等同「搜尋框輸入＋切 Video」一次到位。
   - ⚠️ 主搜尋框用點擊＋打字不穩定（曾發生 `find` 的 ref 點下去沒真的輸入文字），**直接改網址可完全跳過**。只有完整句子／複雜片語查詢才退回搜尋框。
   - ⚠️「Text」分頁不穩定（同一組關鍵字前一刻查得到、重打回 0 items）；「All」分頁已被使用者明確更正，**一律以 Video 為準**。
2. 等待約 **9 秒**。
3. **`screenshot`**（第 1 張）。

   ⚠️ **這張截圖不只是給人看的——`find` 依賴它。** accessibility tree 不會隨頁面自行更新，`navigate` 後直接 `find` 會回「results region shows 0 items」，即使畫面早就渲染完成（實測：連續等 18 秒完全不截圖仍回 0 items；先 screenshot 一次後 `find` 立刻成功）。
4. **`find("search result headline link")`** → **用回傳的標題文字挑對素材** → `click(ref)`。
   toggle ON 時通常只有 1~2 筆（最新的 WRAP 稿可能一併出現），靠標題文字辨識即可，**不要用座標點擊**清單項目。
5. 等待約 **8 秒**。
6. **`screenshot`**（第 2 張，同樣兼作 a11y tree 刷新）。
7. **`get_page_text`** → 一次取得 shotlist 全條、STORY 全文、**Restrictions**、Details（Duration／Edit No.／Audio／Locations／Source／USN／Slug），**直接落檔**。

   ⚠️ 點進詳情頁**直接** `get_page_text` 會抓到**清單卡片摘要**（Slug／標題／日期／Edit No. 幾行就結束），不是詳情內文。先 screenshot 一次就正常，**不需要捲動**。
8. **`find("Download button in the right side panel")`** → 取 **label 恰為 `"Download"`** 的 ref → `click(ref)`。
   - 會回傳三個候選，務必區分：`button "Download"` ← **要點這個**／`button "Download Keyframe"`／`button "Download XML"`。
   - **完全不要用座標。** 有「Download Audio (WAV split)」選項的素材按鈕在 y≈320、沒有的在 y≈272，沿用座標必定點歪。改用 ref 之後這個問題從根本消失。
9. 下載結果用 PowerShell **精確 filter** 檢查 `D:\Downloads`（不要用寬鬆 regex）。
10. **只有需要 BITE 的 TC 時**，才往下捲約 3 格再 `get_page_text` 取 **Video Transcript**——該面板是 lazy render，不捲不會出現。沒有 BITE 需求的素材不要白抓這段長文。

**這個流程的效果**：座標點擊全部消除、截圖固定 2 張／筆且每張都有雙重用途（看畫面＋刷新 a11y tree）、素材選對與否從「肉眼比對」變成「標題文字比對」可稽核。

詳情頁內含：影片、Video Transcript 面板（帶時間碼，原始語言，附「Automated Translation」切換）、完整文字稿（shotlist ＋「RESENDING WITH COMPLETE SCRIPT」正文）、右側 **Restrictions** 面板（例如「No use BBC Persian」「No use VOA Persian」）——限制對新聞編輯室很重要，找到後務必回報。

## 版權注意
不要在對話中逐字貼出完整外電稿件內文；如使用者要求特定內容，摘要/描述結構，僅在需要時引用簡短片段。
