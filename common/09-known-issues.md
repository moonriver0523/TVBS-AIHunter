# 已知問題與疑難排解

這份文件收錄「特定站台/工具在特定情況下才會出現」的症狀與解法，跟 [`08-execution-efficiency.md`](08-execution-efficiency.md) 的預設行為準則不同——**不需要在每次執行流程前主動整份讀過**，只要在執行中真的撞到對應症狀時才查閱對應章節即可，避免每個任務都要讀一堆用不到的邊角案例。

`08-execution-efficiency.md` 底部有一份症狀關鍵字索引，對照到這裡的章節。

**Rollback：** 2026-07-20 從 `08-execution-efficiency.md` 拆分出來，原文見該檔案的 git 歷史。

## CNN Newsource

**症狀：** 搜尋框按 Enter 沒有觸發搜尋，或關鍵字被清空、結果沒有更新。
**解法：** 改用點擊搜尋/放大鏡圖示送出，不要依賴 Enter。

**症狀：** 點下載後 Chrome 完全沒有跳出下載提示或進度條，看起來像沒觸發。
**解法：** CNN Newsource 是交給**背景下載程式**處理，不經過 Chrome 的下載管理員，完成後檔案直接出現在 `D:\Downloads`。**這是正常行為，不是失敗**。直接用 PowerShell 精確 filter 查目標資料夾即可，**不要枯等、更不要再點一次 Download**（會消耗額度，違反 [`08-execution-efficiency.md`](08-execution-efficiency.md) 的鐵則）。

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

**症狀：** 點擊清單裡的標題連結（Reuters Connect／AP 等 SPA 站台）後，網址列已經帶上該素材的 id／detail 參數，但 `get_page_text` 或畫面顯示的仍是**列表頁摘要**（只有標題、日期、Edit No. 幾行），不是完整詳情內容。
**解法：** 這是路由已更新但畫面未同步渲染，同一個 ref／座標**再點一次**通常就會正確切換到詳情頁。判斷依據：`get_page_text` 回傳內容明顯過短、只有摘要格式，就代表還沒真的進入詳情頁，不要誤判成該素材沒有更多內容（2026-07-24「破一百1200」案例，RT #02／#03／#04 皆踩到）。

**症狀：** 點擊 Download 按鈕後，`D:\Downloads` 沒有出現新檔案或 `.crdownload`，看起來完全沒有觸發下載，按鈕本身也沒有任何錯誤訊息。
**解法：** 2026-07-24 實測（Reuters Connect）：**頁面若沒有維持在最上方（已被捲動、或版面因故收合）**，點擊 Download 可能不會真的觸發下載。點擊前先確認頁面在初始（最上方、未收合）狀態再點；已經點過一次沒反應時，回到頁面頂端再點一次即可，不必先懷疑站台或帳號問題。

## video_analyze

**症狀：** 同時對多支影片送出 `video_analyze`，全部被安全分類器暫時拒絕，等於多次無效呼叫。
**解法：** 先對其中1支跑，確認沒有被分類器拒絕、服務正常回應後，才平行展開處理其餘影片。

## 掃帶歐印萬資料夾／大型雲端同步資料夾

**症狀：** 對「掃帶歐印萬」資料夾（或其他大型雲端同步資料夾）直接下 `ls -la`／`grep -r` 整個目錄，出現大量 `No such file or directory` 錯誤（舊檔案檔名含 emoji／特殊符號，讓 Bash 引號解析失敗），或 `Grep`／`rg` 20 秒逾時。
**解法：** 不要對整個資料夾做 `ls -la` 或 `grep -r`。**先用 `find -newermt` 按時間窄縮範圍**（例如只抓最近 1~2 天修改的檔案），再對縮小後的結果 `grep` 關鍵字；需要確認特定檔名是否存在時，優先用 `Glob` 工具而非 Bash `ls`（`Glob` 不受檔名特殊字元影響 shell 解析）（2026-07-24「破一百1200」案例，找 210219/210329 對應側錄檔時踩到）。**搜尋範圍一律排除 `Archive` 子資料夾**（2026-07-24 訂定，見 [`01-shared-folders.md`](01-shared-folders.md)）——裡面是舊資料，不但會跟新素材搞混，也會拖慢掃描。

## validate_sot.py

**症狀：** SOT 稿件裡 CNN 六碼側錄的 SB TC 欄位依 [`common/00-寫稿通則.md`](00-寫稿通則.md) 寫成 `CNN HHMMSS-HHMMSS`（例如 `CNN 210215-210234`），跑 `validate_sot.py` 卻回報「TC 欄位格式無法辨識」。
**解法：** 這是腳本本身的 bug，不是文稿寫法錯誤——`TC_RE` 原本只認得 `#XX ` 前綴或純數字，沒有涵蓋文件裡明訂的 `CNN` 前綴。2026-07-24 已修好正則式（`TC_RE` 加入 `CNN\s+` 選項）並補上反例測試（[`scripts/test_validate_sot.py`](../scripts/test_validate_sot.py) 的「SOT/CNN 六碼側錄 TC 格式應通過」案例）。**此問題只會出現在 SOT 模式**——CTV 流程的 SB TC 一律是純 `MMSS-MMSS` 不帶來源前綴（見 `00-寫稿通則.md` 的 TC 欄位寫法表），不會遇到這個格式。若未來又遇到「TC 格式無法辨識」但文稿寫法確認符合文件規格，先懷疑腳本沒跟上文件更新，不要反過來改文稿遷就腳本（呼應 [`08-execution-efficiency.md`](08-execution-efficiency.md) 的「驗證器不得逼寫稿改壞內容」）。

## 接觸表（Contact Sheet）

**不是預設分析方式，只在真的需要一次性瀏覽整支片的縮圖時才用**——正常流程仍先用 `video_analyze` 找候選區段，再用 `video_detail` 低解析抽幀，不要一開始就想做接觸表。

**需要接觸表時：** 統一用 [`scripts/make_contact_sheet.ps1`](../scripts/make_contact_sheet.ps1)，用法：`powershell -File scripts/make_contact_sheet.ps1 -InputPath "素材.mp4" -IntervalSeconds 10`。這支腳本直接指定 `C:\Windows\Fonts\msjh.ttc` 當字型來源，避開 Windows 環境常缺設定的 Fontconfig 字型查找；`drawtext` 加時間戳失敗時會自動退回不帶文字的接觸表，不會整個失敗。腳本預設拒絕覆蓋既有輸出（不用 `ffmpeg -y`），需要重新產生時先手動處理舊檔或指定新的 `-OutputPath`。

**Reuters 點數在測試下載期間減少（未釐清）**
2026-07-21：素材頁顯示 `HD 60fps (MP4) = Included`、只有 `Download Audio (WAV split)` 標 2pts，依此下載 MP4 不應扣點；但同期間帳號點數由 452 降至 446（少 6 點），無法從畫面確認是否由 AI 的下載造成。在查明前，[`08-execution-efficiency.md`](08-execution-efficiency.md) 的「不得用會消耗額度的操作做測試」禁令維持有效，**不得以「Included 就不扣點」為由自行放寬**。另已確認「FREE TO ME」標示**不是**可靠的免扣點指標。

**Chrome 自動下載封鎖導致批次下載全滅（已破案）**
2026-07-21 封冠遊行1200：整批 RT 素材只有第一支成功，之後全部檔案不落地。真因是 Chrome 對同一網站連續自動下載的內建封鎖，**不是** 503、不是帳號問題、也不是「CDP 合成點擊不帶 user activation」（這兩個結論都曾被提出並已作廢）。誤判的根源是把 `reutersconnect.com` 加進允許清單後**沒有重新載入頁面**就繼續測試。重新 navigate 後 4/4 成功。規則見 [`08-execution-efficiency.md`](08-execution-efficiency.md) 的前置檢查。

## 規則由來案例（歷史紀錄）

以下是各條規則的實際觸發案例。**執行流程時完全不需要讀本節**——規則本身已寫在對應的準則檔裡，這裡只保存「為什麼會有這條規則」，供日後檢討或判斷規則是否該調整時查閱。

**batch 盲猜座標（對應 `08` 的 batch 準則）**
2026-07-21 實測 RT9432（非 batch）vs RT9435（batch）：非 batch 為 12 次個別呼叫、116.5 秒；batch 為 1 次呼叫、30.9 秒。但 batch 那次沿用「上一支素材量到的下載鈕座標」，因 RT9435 頁面多一個「Download Audio (WAV split)」選項把按鈕往下推而點歪，下載請求根本沒送出，是靠額外一次 `read_network_requests` 才發現。

**省 Token 準則的建立（對應 `08` 全文）**
2026-07-20 使用者審視一次 RT/AP 批次下載＋掐BITE 任務的實際 token 消耗，發現主因是每步截圖、每筆素材整段原文貼進對話、清單重複輸出，以及 503 失敗時的重截圖＋查 log 迴圈。同日稍晚多次任務陸續補了多條卡點修正，準則清單一度膨脹到 18 條，其中約 7 條屬特定站台/工具的邊角案例，2026-07-20 拆分到本文件。

**下載卡住提早查 network log（對應 `08` 的重試階梯）**
2026-07-20「油輪觸雷1200」RT 下載案例：盲點 4 次才查 network log，其實一查就看到請求已送出、只是還在處理。

**換頁後沿用舊座標會點歪（對應 `08` 的 navigate 後重新截圖）**
2026-07-20 SE-003SA 搜尋時因橫幅重新出現把版面下推，連續兩次點歪、誤跳轉到 Planner 頁。

**CNN 官方稿必須點 ≡Q 取得（對應 `cnn/01` 步驟 1）**
2026-07-13 WE-018FR 曾漏掉點 ≡Q Preview 這一步，完全依賴 AI 語音轉錄寫完成文稿，導致受訪者姓名／職稱錯誤或籠統：寫成「Cupertino Electric公司代表」而非正確的「Nick McComb, Director of Field Operations, Cupertino Electric」；「Soraya Ortega」應為「Sariah Ortega, Welding Apprentice」；並完全漏掉「Hannah Pettinichio, Silicon Valley Mechanical」與「Paul Gigliotti, General Superintendent, Cupertino Electric」。

**SUPERS 自帶 TC 可與 ASR 互相驗證（對應 `cnn/01` 步驟 5）**
2026-07-20 實測 WE-001FR：SUPERS 附的兩組 TC 與 ASR 結果幾乎完全吻合。

**CTV SUPER 一行超長（對應 `cnn/01` 的 SUPER 字數上限）**
2026-07-20 校準：WE-001FR 使用純中文職稱「泛舟公司營運總監」沒問題，但 SE-003SA 誤把「Louisiana Central」整段英文機構名留在職稱裡，超出 18 全形字上限。

**SOT 段落標題必須用【】（對應 `06` 的格式鐵則）**
2026-07-20「通膨升息1730」草稿只寫「主標題」「次標題」沒加【】，`validate_sot.py` 的 `extract_section()` 抓不到段落邊界，後面所有內容被誤判成同一區塊，直接噴出 30 幾條字數 FAIL，重寫加上【】才正常。

**總長度必須用腳本精算（對應 `06` 的總長度）**
曾發生手算 114 秒、實際精算後是 123.4 秒的落差。

**讀過逐字稿不等於已使用（對應 `06` 的交稿檢查）**
2026-07-20「油輪觸雷1200」案例中，兩則 CNN 側錄逐字稿讀過卻忘了寫進 SB，是使用者事後才發現才補上。

**記者／主播口白要主動盤點（對應 `07` 的 BITE 講者範圍）**
2026-07-20「通膨升息1730」案例中，前面幾次盤點都只顧著找受訪者引言，直到使用者明確提醒才回頭從兩段記者現場連線裡挑出 BITE。

**掐BITE 先確認方向再跑全片轉錄（對應 `07` 方式2）**
2026-07-20「追殺川普1730」案例曾先跑完 10 分鐘側錄檔的全片轉錄，結果使用者對候選方向答「放棄」，該次轉錄等於白工。

**社群轉發連結要先看完整支片（對應批次下載的 Facebook 處理）**
2026-07-20「追殺川普1730」清單摘要只寫「網友下載伊朗媒體的影片轉發」，實際整支 2 分 50 秒是詳細標出座車型號、行館位置與抵達時間的動畫地圖。若不先抽樣看完整支片，容易低估內容尺度。

**AP 搜尋關鍵字要短（對應 `ap/02`）**
2026-07-20 實測：多字精確片語（「Strait of Hormuz oil tanker」「Trump Iran nuclear」）常直接回 0 結果；換成 1-2 字的寬鬆關鍵字才查得到。
