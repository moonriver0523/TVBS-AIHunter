# S2 定時掃帶 V2（省 Token 執行版）——測試中

> **狀態：測試版（2026-08-01 建立）。**
> 本檔是 [`13-S2-定時掃帶.md`](13-S2-定時掃帶.md)（V1）的**執行層覆蓋規格**：內容格式、分類規則、素材行寫法、時區換算、RT 連掃鐵律等**全部沿用 V1**，本檔只改「怎麼執行」——目標是省 token 並讓低階 agent 也能不卡住地跑完。
>
> **啟用方式（測試期）**：使用者指令明確說「用 V2」「省token版掃帶」時才走本檔；沒說就走 V1。
> **Rollback**：刪除本檔＋`scripts/s2_state.py`＋`scripts/s2_validate.py`，並撤掉 V1 檔頭的 V2 指標行即可，V1 未被修改過。
> **轉正**：測試穩定後，把本檔內容併回 V1、廢除雙軌。

## 與 V1 的差異總表

| # | 項目 | V1 做法 | V2 做法 | 預估省 |
|---|---|---|---|---|
| 1 | 詳情頁讀取 | 整頁 text／截圖 | **fallback 階梯＋硬字元上限** | ~60–80k/晚 |
| 2 | 狀態 JSON | agent 直接讀寫整份 | **`s2_state.py` 代管，agent 禁直讀寫** | ~70k/晚 |
| 3 | 品質掃／檔頭統計／三方比對 | agent 逐行掃 | **`s2_validate.py` 機器掃，只處理命中** | ~15–20k/晚 |
| 4 | SNTV 體育 | 開詳情寫完整三段式 | **`AP5` 白名單列表級收錄** | ~10–15k/晚 |
| 5 | 防卡設計 | — | resume／RT 斷點跳站／半夜禁問 | （穩定性） |
| 6 | RT 連掃讀取 | 每則回列表重點 | **單分頁 Next 鏈＋換頁後 scroll 再讀**（見防卡設計 5） | 省一次頁載入/則 |

---

## 1. 詳情頁擷取：fallback 階梯＋硬上限

**階梯（固定順序，不准跳步、不准重試同一步）：**

1. 先用 `find`／選擇器抓 script 正文區塊與 Details 欄位（Edit No.／Duration／Restrictions／SOURCE）。
2. **失敗一次 → 立刻改整頁 `get_page_text`**。禁止重試選擇器第二次。
3. RT 詳情頁若必須截圖：只截 Details 欄＋script 區，不截整頁。

**讀多少（硬規則，不留判斷）：**

- script 正文：**取前 4,000 字元**，超過截斷（暫定值，實測後調）。
- shotlist：全文。
- S2 只需要寫出三段式（摘要一句＋畫面逐項＋BITE 濃縮＋講者），**不需要逐字讀完每段 SOUNDBITE**——逐字與精確 TC 是下游 S7 的事。

## 2. 狀態檔：`s2_state.py` 代管（agent 禁止直接開 JSON）

狀態檔仍是單一 JSON，但**一切讀寫都透過腳本**。

⚠️ **檔名與 schema（2026-08-02 實跑訂正，務必照做）**：
- **檔名＝`{MMDD}-s2-state.json`**（例 `0802-s2-state.json`），與 `{MMDD}晚班交接.txt` 同資料夾、**一天一檔**。不是固定的 `s2-state.json`。
- **正式 schema**：頂層有 `checkpoint`／`updated_at`／`window_local`／`rt_status`／`ap_status`／`cnn_status`／`notes`／`items`；**`items` 是陣列**（每筆含 `id`）；**`category` 是 `{"大分類": …, "中主題": …}` 物件**，不是字串。`s2_state.py` 已對齊此格式，`set-category --cat "大分類/中主題"` 會自動轉成物件。
- 頂層欄位用 `set-top {欄位} {值}` 設定（開工先設 `window_local` 與 `checkpoint`）。
- **整併後另存機器版快照** `{MMDD}晚班交接.snapshot.txt`（同資料夾），供下一輪 `diff3` 三方比對用。

指令：

```
python scripts/s2_state.py --file "…/{MMDD}-s2-state.json" resume   # 開工必跑：現在幾點段、已收幾則、pending幾則、待整併幾則
python scripts/s2_state.py diff --checkpoint 16:00 --ids RT2333,AP4675135,IN-02TU
                                                           # 回傳哪些是新的；已在庫的自動更新 last_checked
python scripts/s2_state.py add --id RT2333 --source RT --checkpoint 16:00 --status pending --entry-file tmp.txt
python scripts/s2_state.py update-entry --id RT2333 --status has_script --entry-file tmp.txt
                                                           # pending→has_script 覆寫 raw_entry
python scripts/s2_state.py pending                         # 稿未到清單（最終整併清查用）
python scripts/s2_state.py to-compile                      # 增量整併輸入：新增＋變動，含 raw_entry 全文
python scripts/s2_state.py mark-compiled --checkpoint 18:00 --ids RT2333,RT2360
python scripts/s2_state.py set-category --id RT2333 --cat "社會/休達移民"
python scripts/s2_state.py get --id RT2333                 # 單則全文
python scripts/s2_state.py needs-review add --id RT2333 --note "疑似UGC，待人工"
python scripts/s2_state.py needs-review list
```

- 批次擷取流程 ＝ 收集本輪列表 ID → `diff` → 只對「新的」開詳情 → 每則 `add`。**全程不載入 70 則 raw_entry。**
- 整併流程 ＝ `to-compile` 拿增量 → 判斷分類（`set-category`）→ 改寫 txt → `mark-compiled`。
- **腳本連續失敗 2 次**：把錯誤訊息原文記進回報，**當輪改用 V1 直讀 JSON 的做法繼續**（degraded mode），不得卡住不動。

## 3. 品質掃／統計／比對：`s2_validate.py`

```
python scripts/s2_validate.py check "G:\...\0801晚班交接.txt"   # 格式異常掃描，輸出命中清單（行號＋原因）
python scripts/s2_validate.py stats "G:\...\0801晚班交接.txt"   # 輸出檔頭兩行（掃帶時段＋來源則數統計）
python scripts/s2_validate.py diff3 current.txt snapshot.txt    # 三方比對：列出人工編輯過的行
```

- `check` 涵蓋 V1「格式異常」表全部可 regex 的項目：BITE 矛盾、缺 `▎畫面：`、缺講者、備註重標、GMT 洩漏、`FILE`／`檔案`、操作備註全形括號、重複代碼、第二括號非 `(BITE)` 等。
- **LLM 只處理命中清單**（回站核對、修 raw_entry＋txt），不再整份逐行讀。`明顯可疑`（數字矛盾等語意類）維持 LLM 抽查，但只在機器掃結果之外補充，不重複掃格式。
- `stats` 產出的**三行**直接貼進檔頭（見 V1 `13`「晚班交接檔頭」）。
- `diff3` 只把「與機器版快照不同的行」列出來，LLM 只裁決這些行保不保留。
- **腳本失敗行為**：連續失敗 2 次 → 品質掃記為「未執行（腳本錯誤）」寫進回報，**禁止 agent 自行逐行手掃替代**。

## 4. SNTV 列表級收錄（機械白名單）

- **僅限代碼 `AP5` 開頭**（SNTV 體育，判定規則同 V1）：直接以列表可見資訊（標題＋時長＋Source）寫簡版三段式，**不開詳情頁**。備註照標 `(SNTV)`，摘要一句話，`畫面：` 依標題可推者寫、不確定就精簡，結尾 `無BITE。`（列表看不到 BITE 就不標）。
- 其餘**一律照常開詳情**——不做任何語意判斷的「低價值分類」，防低階 agent 誤殺大新聞。
- 使用者點名要開稿的 SNTV 素材，回站補完整三段式。

## 4c. YouTube 網址素材（人工投餵，2026-08-02 新增）

**觸發**：使用者直接貼 YouTube 網址（可一次多條），要求「摘要後加入晚班交接」。**不是**自動輪詢——S2 不主動掃 YouTube 頻道（第 3 類仍未開，見 V1 `13` 素材種類表）。

### 素材行格式（**兩行式**，與通訊社單行三段式不同）

```
{YouTube 網址}
({來源} {形式} {MM:SS}) {摘要}
```

實例（摘要直接寫內容，**不要**寫「200字摘要」這種字樣）：

```
【韓國情勢】
韓聯社連線
youtube.com/watch?v=AA6tRh8n-_w
(韓聯社 記者連線 03:24) 韓聯社記者於首爾市區連線報導，南韓政府就近期情勢召開跨部會緊急會議，會後宣布三項因應措施，包含邊境查驗加嚴、相關產業補貼延長半年，以及成立跨部會應變小組。記者現場說明，首爾市中心秩序平穩，未見大規模集會；受訪民眾多數支持政府作法，但對補貼發放時程仍有疑慮。官方表示本週內將對外公布具體時程與申請方式。
```

| 欄位 | 規則 |
|---|---|
| **第一行＝網址** | 原樣貼上，**不縮網址、不加括號**。這行就是代碼，供編輯直接複製點開 |
| **第二行第一段＝`({來源} {形式} {MM:SS})`** | 半形括號，三個元素固定此順序。**時長寫在括號內**（與通訊社素材的行尾 `▎MM:SS` 不同，此為兩行式專屬） |
| **來源** | 頻道名（`韓聯社`／`CNA`／`CNN`／`NHK`…），用中文慣稱 |
| **形式** | **三選一**，判斷準則見下 |
| **摘要** | **約 200 字**（比通訊社素材長，因為沒有 `畫面：`／`BITE：` 分段）。事件、關鍵數字、誰說了什麼一次講完。**直接寫內容**——「200字」只是長度目標，**不是要寫出來的字樣** |
| **不要的東西** | ❌ 不寫 `▎畫面：`／`▎BITE：`／`▎無BITE。`（那是通訊社單行式的欄位）；❌ 不加 `(BITE)` 第二括號；❌ **不寫佔位／字數字樣**：`（200字摘要）`／`（AI摘要）`／`（摘要待補）`／`（約200字）` 等一律禁止出現在成品，同 V1「操作備註禁止寫進素材行」精神 |

### 形式判斷（三選一，必填）

| 形式 | 判準 | 給編輯的意義 |
|---|---|---|
| **記者連線** | 記者出鏡對鏡頭報導（現場站播、視訊連線框），主體是記者本人講話 | 可整段當連線帶播，或抽現場畫面 |
| **SOT** | 有可直接使用的成音——受訪者／官員／當事人談話，或已配好旁白的完整包裝 | 有料可掐，下游可走 [`07-bite-assistant.md`](07-bite-assistant.md) |
| **主播BS** | 只有畫面、無可用成音（純畫面、無聲、外語無字幕、或僅棚內主播讀稿配圖） | 只能當主播背板／背景畫面用 |

**判斷順序**：先看有無可用成音 → 有且是記者出鏡＝`記者連線`；有但是受訪／官員／旁白包裝＝`SOT`；沒有可用成音＝`主播BS`。**拿不準時標 `主播BS` 並 `needs-review add`**，不要猜——高估成音會害編輯排了帶才發現不能用。

### 判讀流程（省 token，字幕優先）

1. **先抽字幕**：`yt-dlp --write-auto-sub --write-sub --sub-lang "ko,en,zh-TW,zh,ja" --skip-download --output "<scratch>/%(id)s" <URL>`。有字幕 → 直接讀字幕寫摘要與判形式。
2. **順手拿 metadata**：`yt-dlp --print "%(title)s|%(duration_string)s|%(uploader)s" --skip-download <URL>` 取標題／時長／頻道，`MM:SS` 直接用這裡的 duration，**不要**為了看時長去下載。
3. **無字幕才下載**：`yt-dlp -f "best[height<=480]" <URL>` 後跑 `video_analyze`（依 [[feedback_video_watching_token_saving]]：先 `video_analyze`、frame_resolution 256，需要才 `video_detail`）。
4. **形式判斷若字幕不足以判定**（例如有字幕但看不出是不是記者出鏡）→ 只抽數張低解析度影格確認畫面，不跑全片。
5. 寫入狀態 JSON：`--source YT`，`--id` 用網址（見下）。

### 狀態 JSON 與統計

- **檔頭統計**用 `s2_validate.py stats --window "14:00 - 15:00"` 產生三行（見 V1 `13` 檔頭章節）。
- `--id` 一律**正規化成 `YT:{video id}`**（`YT:AA6tRh8n-_w`）——同一支影片可能被貼成 `youtube.com/watch?v=…`／`youtu.be/…`／帶 `&t=`／帶 `?si=` 追蹤參數等多種寫法，用原始網址當 id 會**重複收錄同一支片**。`video id` 全域唯一，天然不會與通訊社代碼撞號。txt 裡的第一行仍寫使用者給的完整網址（方便點開），去重靠 id。
- `--source YT`。
- **檔頭統計歸「其他」**（依 V1 `13` 檔頭備註規則：非 AP／RT／NS 一律併入其他）。

## 4b. 整併時的分類修正（歸錯位要歸位，2026-08-02 補）

「增量整併沿用既有 `category`」是**省 token 的預設**，不是鐵律。V1 本來就有「同組必須相鄰、歸錯位要歸位」，兩者衝突時**歸位優先**。沿用預設之外的三個修正時機：

1. **`raw_entry` 被覆寫時**（pending→has_script、品質修正）：該則本來就要重新排版，**順便重新檢視分類**——稿到後事件全貌常與列表級初判不同（實例：RT2650 愛達荷槍擊初判時資訊少被丟進話題，稿到後應歸美國與同事件素材相鄰）。
2. **同事件素材已存在於其他大分類**：整併新素材時，發現同一事件（同 slug 家族／同主題）已有素材在別的大分類 → **併過去同組相鄰**，不要在兩個大分類各留一半。搬動的那則用 `set-category` 更新，舊位置的行移除。
3. **最終整併（23:00）**：定版品質掃時順掃「同事件跨大分類分裂」，有則歸位。中繼整併只處理當次撞見的，不全量掃。

**低階 agent 判斷依據（機械優先）**：slug 前綴相同（`USA-SHOOTING/IDAHO` 家族）、代碼備註含相同專名（地名＋事件詞）→ 視為同事件。拿不準 → 維持沿用＋`needs-review add`，不要亂搬。

## 5. 防卡設計（低階 agent 必讀）

1. **每輪開工第一步跑 `resume`**——context 斷掉重進時，以腳本回報的狀態為準接續，不憑記憶。
2. **RT 卡住跳站**：連續 2 次 Next 沒反應／頁面沒變 → 記下目前 Edit No.（`needs-review add`），跳去掃 AP／CNN，回報 RT 中斷點。不准死磕（V1 已知 SPA 卡快取雷）。
3. **半夜禁問**：無人值守時段遇到需使用者確認的事項（可疑素材、分類拿不準、腳本壞掉）→ `needs-review add` 記錄＋寫進交接檔備註，**繼續往下跑**。不得 `AskUserQuestion` 等回應、不得停住。
4. **fallback 全部單向**：階梯只往下走（選擇器→整頁→截圖），不回頭重試上一步。
5. ⚠️ **RT 連掃＝單分頁 Next 鏈＋「換頁後必須刷新再讀」（2026-08-02 三輪實測定案，取代先前雙分頁法）**

   **根因**：`get_page_text`／`find`／`read_page` 讀的是**擷取快照**，SPA 換頁（Next／Previous）**不會**刷新它——換頁後立刻讀，會**無聲拿到上一則的完整內容**（URL 與畫面都已是新的，只有文字是舊的）。**純 `wait` 無效、連讀兩次也無效**；只有**會回傳畫面的互動動作**（`screenshot` 或 `scroll`）能強制刷新。

   **標準流程（每則固定四步，不可省第 2 步）**：
   1. 從 **`https://www.reutersconnect.com/all?media-types=vid` 大列表**、頁面**在最頂**、點**最新那則**卡片進詳情（首次進入）。
   2. 按 **Next（›）** 往時間更早。
   3. **做一次 `scroll`（往下 3–5 格）**——強制刷新擷取快照，順帶把 shotlist／script 捲進視野。
   4. `get_page_text` 讀取 → **核對文中 Edit No 與 URL 編號一致**才寫入。

   - 用 `scroll` 不用 `screenshot`：兩者都能刷新，但 `scroll` 同時達成「捲到正文」的目的，一個動作兩用。
   - **保險絲**：Edit No 與 URL 不符 → 再 `scroll` 一次重讀；仍不符 → 照第 2 條記錄跳站。
   - 📌 **雙分頁法（A 目錄／B 冷開）降級為備援**：只在 Next 鏈整段失效時使用（B 分頁冷開後同樣要**先 scroll 再讀**，原因相同）。單分頁 Next 鏈**省一次完整頁面載入／則**，是預設路徑。

5b. ⚠️ **Next（›）灰掉按不動時（2026-08-02 實測，使用者指出主因）**：
   - **主因＝進入路徑不對**：必須從 **`all?media-types=vid` 大列表**、**頁面在最頂**、點**最新那則**進去，結果集才會綁好、‹ › 才會生效。從搜尋結果、篩選後清單、深連結、或捲動過的列表點進去，都可能讓 ‹ › 失效。
   - **處置**：Next 灰掉 → **回大列表重新照上述路徑進入**（不是改用別的方法硬幹）。
   - **備援**：仍失效才回列表**逐張點卡**進詳情（首屏可見的素材不需要 Next 鏈，也不會踩 LOAD MORE 禁則）；每則同樣「進去→scroll→讀→核對 Edit No」。
   - 只有窗內素材已捲出首屏時才非用 Next 鏈不可；此時 Next 仍失效 → 照第 2 條記錄中斷點並跳站。
   - 只有在「窗內素材已捲出首屏」時才需要 Next 鏈；此時若 Next 仍失效，照第 2 條記錄中斷點並跳站。
6. **AP `/home` 偶發跳轉 `/live`（2026-08-02 實測）**：navigate 到 AP Newsroom `/home` 或點側欄 Latest 後，偶爾會被 SPA 路由帶去 `/live`。**每次讀列表前先確認 URL 是 `/home`**；發現在 `/live` → 重新點側欄 Latest（點文字正中央），最多重試 2 次，仍失敗照第 2 條跳下一站並記錄。

## 未定／實測後要回填

- [ ] script 4,000 字元上限是否夠（RT 長稿實測）
- [ ] `s2_state.py` degraded mode 實際觸發率
- [ ] SNTV 列表級的資訊量晚班夠不夠用
- [ ] 實測一晚總 token，對照 V1 估算 30.8 萬
