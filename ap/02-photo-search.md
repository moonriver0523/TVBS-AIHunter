# 找AP照片

當使用者給一段自然語言描述（例如「找AP照片 川普伊朗相關」），而非精確關鍵字或編號，要求下載「最新、最符合新聞」的若干張照片時，使用本規則。這是 [`搜尋外電素材(AP)`](01-search-workflow.md) 的照片版，同樣在 AP Newsroom 操作。

瀏覽器操作套用 [`../common/08-execution-efficiency.md`](../common/08-execution-efficiency.md)。

**Rollback：** 省 Token 改寫前舊版見 [`../_archive/ap/02-photo-search.pre-token-saving-2026-07-20.md`](../_archive/ap/02-photo-search.pre-token-saving-2026-07-20.md)。

## 省 Token 執行備註

- **預設只點列表 ⬇** 下載；**沒有 ⚠️ 就不要開詳情頁**。
- 一次抓 N 張時，連續下載動作能 batch 就 batch；不要每張截圖確認。
- 下載確認用 `D:\Downloads` 檔案系統檢查，只查詢跟本次搜尋相關的檔名/時間，不要列出整個資料夾。
- 對話回報：最終檔名 + 一句圖說/標題 + 有無 Special Instructions；不貼完整 Photo Metadata。
- **先測試帳號能否下載，再展開大量搜尋**：任選一張結果嘗試下載確認流程正常。若下載回傳明確的授權/計量錯誤（例如 `MeterExpired_Shutdown`），代表帳號下載額度或授權已到期，**立即停止，不要再換關鍵字或重試**，回報使用者是帳號授權問題。
- **搜尋後要再次確認目前分頁**：AP 頁面切換分頁後，媒體類型（Photo／Video）狀態有時不會穩定保留，同一個站台曾出現過搜尋後自動跳回 Video、也出現過跳回 Photo 的情況，兩種方向都遇過，下載前先看清楚目前是不是 Photo 分頁。
- **找不到跟事件本身相關的照片時，回報「無事件照片」，不要為了湊滿張數改塞不相關的舊照/背景照片**——相關性比湊滿數量重要。

## 觸發格式

使用者給的是一段描述，不是精確關鍵字。需要自己判斷／生成適合的英文搜尋關鍵字（例如「川普伊朗」→「Trump Iran」），媒體類型選 **Photo**，然後挑「最新、最符合新聞」的前 N 張下載（N 由使用者指定；沒指定就抓 3 張當預設，或詢問使用者）。

## 流程

1. 搜尋框輸入自己生成的關鍵字，媒體類型切到 **Photo**，選「Search with keywords」。
2. 排序預設是「**Newest filed**」（右上角排序圖示可切 Newest filed／Best match／Newest created／Oldest），不用額外設定，結果本來就是新到舊。
3. 結果列表卡片上直接顯示：來源（通常 AP）、幾小時前、日期、標題、caption 摘要、素材 ID，以及一排操作圖示：⚠️（有的話代表有 Special Instructions／使用限制）、**⬇下載圖示**、▾（格式選單）、⋮（更多）。
4. **重點技巧**：Photo 不需要像 Video 那樣點進詳情頁才能下載——**直接點列表卡片上的 ⬇ 圖示就會立即下載**，比 Video 流程快很多。若要看完整 caption／攝影記者／Special Instructions（限制），或卡片上有 ⚠️，才需要點進詳情頁（`/detail/{slug}/{id}/photo`）。
5. 詳情頁的 **Photo Metadata** 有：ID／Submission Date／Creation Date／Photographer／Source／Copyright／Credit／Transmission Reference／Byline Title／People Shown／People Mentioned／Subjects，限制訊息會另外用橘色 **Special Instructions** 提示框顯示（對應列表卡片上的 ⚠️ 圖示）。需要限制內容時只摘 Special Instructions，不要把整頁 metadata 貼進對話。

## 下載結果

Photo 下載是**同步立即**完成（不像 Video 是非同步排隊），直接落地到本機瀏覽器預設下載資料夾 `D:\Downloads`，檔名格式是 `AP{素材ID}.jpg`（例如 `AP26196329903421.jpg`）。

## 挑片原則

同一則新聞事件常有多張不同角度/構圖的照片（例如同一塊看板的不同拍攝角度），只要主題、時效都符合使用者要求，可以視為不同的候選照片分別下載，不必侷限只選視覺完全不同的題材。
