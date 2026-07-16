# 找AP照片

當使用者給一段自然語言描述（例如「找AP照片 川普伊朗相關」），而非精確關鍵字或編號，要求下載「最新、最符合新聞」的若干張照片時，使用本規則。這是 [`搜尋外電素材(AP)`](01-search-workflow.md) 的照片版，同樣在 AP Newsroom 操作。

## 觸發格式

使用者給的是一段描述，不是精確關鍵字。需要自己判斷／生成適合的英文搜尋關鍵字（例如「川普伊朗」→「Trump Iran」），媒體類型選 **Photo**，然後挑「最新、最符合新聞」的前 N 張下載（N 由使用者指定；沒指定就抓 3 張當預設，或詢問使用者）。

## 流程

1. 搜尋框輸入自己生成的關鍵字，媒體類型切到 **Photo**，選「Search with keywords」。
2. 排序預設是「**Newest filed**」（右上角排序圖示可切 Newest filed／Best match／Newest created／Oldest），不用額外設定，結果本來就是新到舊。
3. 結果列表卡片上直接顯示：來源（通常 AP）、幾小時前、日期、標題、caption 摘要、素材 ID，以及一排操作圖示：⚠️（有的話代表有 Special Instructions／使用限制）、**⬇下載圖示**、▾（格式選單）、⋮（更多）。
4. **重點技巧**：Photo 不需要像 Video 那樣點進詳情頁才能下載——**直接點列表卡片上的 ⬇ 圖示就會立即下載**，比 Video 流程快很多。若要看完整 caption／攝影記者／Special Instructions（限制），才需要點進詳情頁（`/detail/{slug}/{id}/photo`）。
5. 詳情頁的 **Photo Metadata** 有：ID／Submission Date／Creation Date／Photographer／Source／Copyright／Credit／Transmission Reference／Byline Title／People Shown／People Mentioned／Subjects，限制訊息會另外用橘色 **Special Instructions** 提示框顯示（對應列表卡片上的 ⚠️ 圖示）。

## 下載結果

Photo 下載是**同步立即**完成（不像 Video 是非同步排隊），直接落地到本機瀏覽器預設下載資料夾 `D:\Downloads`，檔名格式是 `AP{素材ID}.jpg`（例如 `AP26196329903421.jpg`）。

## 挑片原則

同一則新聞事件常有多張不同角度/構圖的照片（例如同一塊看板的不同拍攝角度），只要主題、時效都符合使用者要求，可以視為不同的候選照片分別下載，不必侷限只選視覺完全不同的題材。
