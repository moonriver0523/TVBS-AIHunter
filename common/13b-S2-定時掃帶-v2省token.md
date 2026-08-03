# S2 定時掃帶 V2（省 Token 執行版）——測試中

> **狀態：測試版（2026-08-01 建立）。**
> 本檔是 [`13-S2-定時掃帶.md`](13-S2-定時掃帶.md)（V1）的**執行層覆蓋規格**：內容格式、分類規則、素材行寫法、時區換算、RT 連掃鐵律等**全部沿用 V1**，本檔只改「怎麼執行」——目標是省 token 並讓低階 agent 也能不卡住地跑完。
>
> **啟用方式（測試期）**：使用者指令明確說「用 V2」「省token版掃帶」時才走本檔；沒說就走 V1。
> **Rollback**：刪除本檔＋`scripts/s2_state.py`＋`scripts/s2_validate.py`，並撤掉 V1 檔頭的 V2 指標行即可，V1 未被修改過。
> **轉正**：測試穩定後，把本檔內容併回 V1、廢除雙軌。

## 0. 三站入口網址（2026-08-02 補，開工前先核對）

⚠️ **靠記憶打網址容易打錯**（2026-08-02 實例：CNN Newsource 被誤記成 `newsource.cnn.com`，缺了 `.ns.`，導向「隱私權設定發生錯誤」頁面，`get_page_text`／截圖都讀不到東西）。開工前照這份表核對，不要憑印象打：

| 站 | 入口網址 | 備註 |
|---|---|---|
| AP Newsroom | `https://newsroom.ap.org/home` | Latest 分頁；空白關鍵字查詢會回空白頁 |
| Reuters Connect | `https://www.reutersconnect.com/all?media-types=vid` | 大列表，My Subscription／Newest First |
| CNN Newsource | `https://newsource.ns.cnn.com` | **注意中間有 `.ns.`**，少了會導向錯誤頁；不支援網址直接搜尋，見 [`cnn/01-auto-script-writing.md`](../cnn/01-auto-script-writing.md) |

## 與 V1 的差異總表

| # | 項目 | V1 做法 | V2 做法 | 預估省 |
|---|---|---|---|---|
| 1 | 詳情頁讀取 | 整頁 text／截圖 | **fallback 階梯＋硬字元上限** | ~60–80k/晚 |
| 2 | 狀態 JSON | agent 直接讀寫整份 | **`s2_state.py` 代管，agent 禁直讀寫** | ~70k/晚 |
| 3 | 品質掃／檔頭統計／三方比對 | agent 逐行掃 | **`s2_validate.py` 機器掃，只處理命中** | ~15–20k/晚 |
| 4 | SNTV 體育 | 開詳情寫完整三段式 | **`AP5` 白名單列表級收錄** | ~10–15k/晚 |
| 5 | 防卡設計 | — | resume／RT 斷點跳站／半夜禁問 | （穩定性） |
| 6 | RT 連掃讀取 | 每則回列表重點 | **單分頁 Next 鏈＋換頁後 scroll 再讀**（見防卡設計 5） | 省一次頁載入/則 |
| 7 | **三站清單／文稿取得**（2026-08-03 新增，**首選路徑**） | 逐則開詳情頁讀 | **API 直查（§1a）**：AP／RT／NS 都不開詳情頁 | 呼叫數：AP/RT 各 20–30 次、NS 40+ 次 → **每站 2–3 次** |

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

## 1a. 三站 API 直查（2026-08-03 上線，**掃帶首選路徑**）

**核心**：清單與文稿**全部走 API，完全不開詳情頁**。實測一輪每站 **2–3 次工具呼叫**（舊 UI 做法 AP／RT 各 20–30 次、NS 40+ 次）。**任一步失敗兩次 → 該站當輪退回 §1b DOM 直撈；§1b 再失敗才退 §5 舊流程。**

> 📄 **完整配方（可直接抄的 JS、body 範例、欄位表）**：`G:\我的雲端硬碟\Claude共用\自動掃帶系統\0803-三站API破解總表.txt` ＋ NS 專篇 `0803-NS掃帶卡點報告-回覆.txt`。本節只寫規則與地雷，不重複貼程式碼。

### 0) 開工前：Playwright 環境衛生（**每次都要做，不是可選**）

- **一律用 Playwright 工具組**（`mcp__browser__*`），**不是 claude-in-chrome**——NS 的 localStorage 在 claude-in-chrome 會被 extension 隱私防護擋死（回 `[BLOCKED: Cookie/query string data]`），AP／RT 的跨網域 fetch 也會被頁面 AdBlock 纏住。
- **檢查並清掉殘留 Chrome**：
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ? { $_.CommandLine -like "*playwright-mcp-profile*" } |
    Select ProcessId, CreationDate, @{n='Age';e={[int]((Get-Date)-$_.CreationDate).TotalMinutes}}
  ```
  用 `Get-Process` 的 `MainWindowTitle`／CPU／存活時間判斷是否閒置；閒置就 `Stop-Process -Force` 再開工。
- **自己收工也要關瀏覽器**，不要留給下一個 agent。
- ⚠️ **`navigate` 失敗、或清單回 0 筆時，第一個懷疑對象是 profile 被鎖，不是「站方無素材」或「帳號失效」**——0803 實錯：RT 連續三輪（04:40／06:40／08:40）回報「全站 0 items」，實測帳號完全正常、當下窗內明明有新素材，根因是 01:28 的殘留鎖掉前兩輪、另一個 agent 08:22 開的 Chrome 鎖掉第三輪，**RT 素材因此空窗 01:00–09:00**。誤判成帳號問題會叫醒錯的人、還埋掉真因。
- ⚠️ **`navigate` 第一次失敗訊息是「Target page, context or browser has been closed」時，通常是它自己剛啟動了一個孤兒 process**（底層瀏覽器已起、連線沒接上），第二次才會看到真正的 `Browser is already in use`。**先精準確認再清**，不要用 `taskkill /IM chrome.exe` 之類的廣域指令（機器上通常同時有幾十個不相干的 chrome.exe）：
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
    Where-Object { $_.CommandLine -match 'playwright-mcp-profile' } | Select-Object ProcessId,CommandLine
  ```
  只對比對出來的主 process（`--user-data-dir=…playwright-mcp-profile --remote-debugging-pipe`，通常還停在 `about:blank`）下 `taskkill /PID {id} /T /F`（`/T` 連子 process 一起收）。**清別人（其他 agent）留下的鎖之前，先確認對方工作已結束**（問使用者，或看有沒有 session 還活著）——本節開頭「不要擅自 Kill」的原則不變，這裡只是把「怎麼精準找到該清哪個 process」寫清楚。

### 1) RT

- **清單**：`POST https://www.reutersconnect.com/api/search-api?hash={hash}`（同源 cookie，`browser_evaluate` 內 fetch）。`cursorMark=*` 起手、用回應的 `nextCursorMark` 翻頁；`limit=60`。
- ⚠️ **回應是 transit 壓縮格式**（欄位名只出現一次、後續用 `^N` 參照）——**不要用 regex 解清單**，只會抓到第一則。清單改用 §1b 的 DOM 直撈拿 Edit No／href（順序有保證），API 清單當備援。
- **文稿**：`GET /api/item/{guid}?hash={hash}&live=false`，**單則回應每個欄位只出現一次、必為字面值，regex 可靠**。新素材的 guid 一次 `Promise.all` 打 N 則——**免開分頁、免等 8–9 秒**。
- Edit No 可從 guid 的 `newsml_RW{4碼}` 機械推出，與清單值互相校驗。⚠️ **不要從 item 回應抓 `editnumber`**（結構深、regex 不穩，實測回 undefined）。
- `hash` **照抄當下頁面實際請求**（實測 `klwn20`，但那像前端 build hash、改版會變，不可硬編）。

### 2) AP

- **清單**：`POST https://api.newsroom.ap.org/v1/nrsearch/search/topic`（cookie 驗證）。**照抄頁面實際發出的 request body**——自己拼的 body 排序會偏 relevance 抓到舊素材；照抄則順序與畫面完全一致（實測 16 則逐一比對相符）。
- ⚠️ **`PageNumber` 不可靠**：實測 `PageNumber=2`＋`PageSize=16` 回了 100 筆、與第 1 頁零重疊，回應卻自稱 Page=2。**要多筆一律固定 `PageNumber=1` 加大 `PageSize`**（16／50／100／200 實測都精準）。
- 欄位：`_source.itemid`＝32 碼 GUID、`_source.editorialid`＝**AP 編號**、`friendlykey`／`title`／`headline`／`dateline`。
- **文稿**：`POST /v1/nrsearch/search/item/details`，body `{"ItemIds":"{itemid}","mediaType":"video","IsNonSalable":false}`。**逗號串多則不支援**（回空），一則一次；但可在同一個 `browser_evaluate` 裡 `Promise.all` 打 N 則，**工具呼叫仍只算 1 次**。
- `TopicId` 實測跨 session 穩定（`116e9ab7…`），仍建議每輪從頁面請求照抄。

### 3) NS（CNN Newsource）——**收益最大的一站**

- **清單即文稿**：`POST https://newsource-content-api-530.ns.cnn.com/api/v3/stories`，一次回傳 **`alternateIds.bitcentralId`（＝NS 編號）＋`footageType`（PKG/SOT/VO 等形式）＋`duration`＋`description`（現成一句摘要）＋`content.bitcentral.script`（稿件全文，含 `--LEAD IN--`／`--VO SCRIPT--` 標記）＋`embargo`**。**完全不必開詳情頁或 Preview modal。**
- Bearer token 在 `localStorage.newsourceSession.token`（1 小時效期，頁面開著會自動續）。
- ⚠️ **回應是多行 JSON（NDJSON）**，不能 `r.json()`——取含 `"stories"` 的那一行再 parse。
- `scriptOnly: true` **就是 UI 上點不動的 Has Script 篩選**；`from`／`size` 分頁，`size` 上限 100。
- ⚠️ **token 過期時第一次呼叫會拿到 `null`**，重新整理頁面等登入完成再打；**連兩次拿不到就是真的登出，停下來請使用者登入**（agent 不得自行輸入帳密）。
- 這條路一次解掉 NS 的五個老卡點（清單無連結／虛擬化列表/捲不動／逐則點 modal／Has Script 篩不動），詳見回覆檔。

#### ⛔ 讀 token＋跨網域打 API 的**寫法**會被 auto mode 攔下，必須用「token 不離開頁面 JS」的形態（2026-08-03 訂正）

**實錯**：`page.evaluate()` 讀出 token → 回傳給 agent 層 → 再用 `page.context().request.post(url, {headers:{authorization:'Bearer '+tok}})` 送出去。這個「讀秘密→agent 自己組請求送到別的 origin」的形狀，跟真正的憑證竊取程式碼結構一樣，被 classifier 判定為 `[Browser JS Exfil]` 直接拒絕——**這不是誤判，這段寫法本來就危險，不要想辦法繞過偵測**。

**正確寫法：整個「讀 token → fetch → parse」都寫在同一個 `page.evaluate()` 裡，token 從頭到尾只活在瀏覽器的 JS engine 內，不當作回傳值的一部分**——這跟「使用者自己在瀏覽器裡操作這個網站」是同一件事，網站本來就是用頁面內 JS 打自己的 API。已實測通過，不再被攔：

```js
() => {
  const tok = JSON.parse(localStorage.getItem('newsourceSession')).token;
  const body = { /* 同上方 request body */ };
  return fetch('https://newsource-content-api-530.ns.cnn.com/api/v3/stories',
    { method:'POST', headers:{'Content-Type':'application/json', authorization:'Bearer '+tok}, body:JSON.stringify(body) })
    .then(r => r.text())
    .then(t => {
      const d = JSON.parse(t.split('\n').find(l => l.includes('"stories"')));
      // ⚠️ 回傳值只准白名單欄位，不准把整段 API 回應原樣丟出來
      return d.stories.content.map(it => ({
        id: it.alternateIds && it.alternateIds.bitcentralId,
        ft: it.footageType, dur_ms: it.duration, created: it.createdDate,
        has_script: !!(it.content && it.content.bitcentral && it.content.bitcentral.script),
        desc: (it.description || '').slice(0, 200),
        script: (it.content && it.content.bitcentral && it.content.bitcentral.script) || ''
        // script 全文是後續寫三段式要用的正常資料，不是秘密——禁止的只有 token/Authorization/JWT
      }));
    });
}
```

- **回傳值黑名單**：`token`／`Bearer`／`Authorization` header／完整 JWT／cookie 字串——這幾樣**永遠不准出現在 `evaluate` 的回傳值裡**，也不准寫進 transcript、log、`add-batch` 的 entries 檔、狀態檔。`script` 全文、`description`、編號這些是正常業務資料，照樣回傳沒問題，不要因為「安全」就連這些也砍掉。
- **`page.context().request.*`（Playwright 的請求層 API）不要用來打帶 token 的跨網域請求**——它的呼叫結果會經過 agent 工具層，形狀就是會被攔的那種。同源／不帶敏感 header 的請求不受此限。
- 若仍被攔（例如 classifier 版本更新），**不要嘗試混淆程式碼、拆呼叫、換名字去繞過**——回報使用者，退回 §5 UI 舊流程，或請使用者當次明確授權後再試一次同樣的安全寫法。

### 4) 守門（任一觸發＝該站當輪退回 §1b，並 `needs-review add` 記錄）

- API 回 401／403／空清單，重試一次仍失敗。
- 回應欄位對不上（缺 `script`／`itemid`／`editnumber`），連 2 則皆然。
- **同站累計失敗 2 次**即退，不要死磕。退回後照 §1b 的守門條款走，§1b 再失敗才退 §5。

## 1b. AP＋RT 清單直開流程（2026-08-02 上線，**§1a 失敗時的第一層退路**）

**核心**：不再「開一則→讀→回清單→再開下一則」，改成**清單一次 JS 撈完 → diff → 新素材直接用網址開分頁逐頁收錄**。modal／Next ‹ › 鏈全程不用。⚠️ **本節只涵蓋 AP／RT；NS 沒有 §1b 這一層**——NS 的 §1a API 失敗兩次直接退 §5 的 UI 舊做法（點 ≡🔍 modal）。

> ⚠️ 2026-08-03 起這是**第二順位**：先試 §1a API 直查，失敗兩次才用本節。RT 的清單 DOM 直撈仍是 §1a 的一部分（transit 格式不適合 regex 解清單），不受此降級影響。

**AP**（實測 2026-08-02）：
1. `/home` Latest 清單，一次 JS 撈每張卡的 **GUID＋標題**（GUID 在縮圖網址裡：`mapi.associatedpress.com/v2/items/{32碼hex}...`；卡片本身沒有 href）。
2. `diff` 後，新素材直開 `https://newsroom.ap.org/detail/x/{GUID}/video`（slug 隨便填、免參數）。
3. **直開後等 8–9 秒再讀**（⚠️ 2026-08-03 00:00 實驗輪實測：等 4 秒 `get_page_text` 仍回「No text content」，8–9 秒才穩；原寫 3 秒是驗證時用 JS 直查 DOM 的值，`get_page_text` 要等更久）。更穩的做法：先讀一次，沒抓到 SHOTLIST／STORYLINE 關鍵字就再等 5 秒重讀一次，兩次都空才算失敗。讀取前核對頁面 GUID／標題與預期一致。

**RT**（實測 2026-08-02）：
1. `all?media-types=vid` 大列表，一次 JS 撈 `a[href*="detail?id="]` 的 **href＋Edit No＋版次＋slug＋標題＋時長＋RAW/SCRIPT 狀態**——「EARLY ACCESS SCRIPT / Video will be available shortly」（稿到片未到）清單層直接可判。
2. 新素材**照抄清單撈到的 href 直開**（內部碼勿自行拼湊，版次尾碼會變）；開後等 8–9 秒（同 AP 第 3 條，含重讀規則），核對 Edit No 與預期一致才讀。
3. **Load More 三條行為規則**（實測）：⑴ 是**換頁替換**不是累加——按下後最新那批從 DOM 消失，所以**必須先撈完目前這頁才准按**，按完再撈一次做聯集去重；⑵ 只認**真實點擊**，合成 JS click 無效；⑶ 深夜窗通常首屏 10 則就夠，不需要按。舊的 LOAD MORE 禁則是為 Next 鏈設的，本流程不走 Next 鏈故不適用；退回舊流程時禁則照舊。

**分波**：一次最多開 5–8 個分頁，讀完關掉再開下一波。

**守門（任一觸發＝該站當輪退回 §5 舊流程，並 `needs-review add` 記錄）**：
- 清單 JS 撈到 0 筆或明顯少於畫面可見數。
- 直開頁面依上方等待規則（8–9 秒＋重讀一次）後仍空白，或 GUID／Edit No 與預期**不符**（絕不寫入不符頁面的內容）。
- 同站連續 2 頁觸發上述任一條。

## 2. 狀態檔：`s2_state.py` 代管（agent 禁止直接開 JSON）

狀態檔仍是單一 JSON，但**一切讀寫都透過腳本**。

⚠️ **檔名與 schema（2026-08-02 實跑訂正，務必照做）**：
- **檔名＝`{MMDD}-s2-state.json`**（例 `0802-s2-state.json`），與 `{MMDD}晚班交接.txt` 同資料夾、**一天一檔**。不是固定的 `s2-state.json`。
- **正式 schema**：頂層有 `checkpoint`／`updated_at`／`window_local`／`rt_status`／`ap_status`／`cnn_status`／`notes`／`items`，2026-08-03（WP1）另加 **`alerts`**（檔頭 🔴 重大提醒行，陣列 ≤3）／**`special_category`**（第一格機動大分類顯示名，如「熊本地震」）／**`last_render_ts`**；**`items` 是陣列**（每筆含 `id`）；**`category` 是 `{"大分類": …, "中主題": …[, "小分題": …]}` 物件**，不是字串。`s2_state.py` 已對齊此格式，`set-category --cat "大分類/中主題[/小分題]"` 會自動轉成物件。
- 頂層欄位用 `set-top {欄位} {值}` 設定（開工先設 `window_local` 與 `checkpoint`）；`alerts` 用專用的 `set-alert`。
- ⚠️ **`.snapshot.txt` 機器版快照與 `diff3` 已廢除（2026-08-03，WP1）**：txt 改由 `s2_render.py` 從狀態檔全量渲染、人工不改，沒有「人工編輯過的行」要裁決了。

指令：

```
python scripts/s2_state.py --file "…/{MMDD}-s2-state.json" resume   # 開工必跑：現在幾點段、已收幾則、pending幾則、待整併幾則
python scripts/s2_state.py diff --checkpoint 16:00 --ids RT2333,AP4675135,IN-02TU
                                                           # 回傳哪些是新的；已在庫的自動更新 last_checked
python scripts/s2_state.py add-batch --entries batch.json  # ⭐ 批次新增（預設路徑，見下方批次規則）
python scripts/s2_state.py add --id RT2333 --source RT --checkpoint 16:00 --status pending --entry "RT2333 ▎一句話摘要▎畫面：…"
python scripts/s2_state.py update-entry --id RT2333 --status has_script --entry "改寫後內容"
                                                           # pending→has_script 覆寫 raw_entry
                                                           # ⚠️ 標 pending 前先讀 13「有稿判準」：沒標記但有完整敘事＝有稿；
                                                           #    ISO長帶/裸SOT/音軌等天生無旁白稿的＝has_script＋備註形態，不是 pending
                                                           # add／update-entry 短內容用 --entry 行內；長內容（如CNN連線全文）才用 --entry-file
python scripts/s2_state.py pending                         # 稿未到清單（最終整併清查用）
python scripts/s2_state.py set-category --pairs "RT2333=社會/休達移民/岸際動態;RT2360=天氣/野火"
                                                           # ⭐ 批次設分類（預設路徑）；單筆仍可 --id RT2333 --cat "社會/休達移民"
                                                           # 第三段＝小分題（選填）：render 會產出裸行標題＋`+` 分隔
python scripts/s2_state.py add-side --txt "…/0803 CNN側錄.txt" --source CNN --checkpoint 22:00 \
       --homes "天氣/華州野火/州長宣布緊急=160106,160151"
                                                           # 側錄入庫（SIDE_CNN／SIDE_NHK），見 14-S2b「暫定辦法」
                                                           # --normalize：機械正規化（上傳者不懂格式時一律加）
                                                           #   範圍TC取起點去冒號成6碼／拆黏行／角色搬到TC行／清雜訊，不改字
                                                           # --source：裸 TC 檔補來源前綴（不補會解析出 0 段）
                                                           # --homes：用 TC 指定歸位，不必重打逐字內容
                                                           # --dry-run 先驗解析段數
python scripts/s2_state.py set-alert --set "▲ AP4676262 巴基斯坦自殺炸彈14死…"
                                                           # 檔頭 🔴 重大提醒行（≤3則，整組取代；--add 追加／--clear 撤掉）
python scripts/s2_state.py set-mark --ids RT2754,RT2753 --mark ▲
                                                           # 補掃輪等 checkpoint 判不準時寫死時段標記（--clear 改回自動）
python scripts/s2_state.py get --id RT2333                 # 單則全文
python scripts/s2_state.py needs-review add --id RT2333 --note "疑似UGC，待人工"
python scripts/s2_state.py needs-review list
```

- 批次擷取流程 ＝ 收集本輪列表 ID → `diff` → 只對「新的」取文稿（**§1a API 直查，不開詳情頁**；失敗才退 §1b） → **邊看邊把每則累積進一份 `batch.json`，全部看完後一次 `add-batch`**。不要一則一次 `add`（2026-08-02 起：呼叫次數是 V2 變慢主因，一輪 25 則從約 52 次呼叫降到約 4 次）。**全程不載入 70 則 raw_entry。**
- **批次規則**：`batch.json` 是 JSON 陣列，每筆 `{"id","source","checkpoint","status","entry"}`（`entry` 直接放字串，含換行）。撞已存在 id 或格式錯的單筆會**自動跳過並回報原因、不中斷**——回報裡有跳過清單時，逐筆判斷：已存在→改用 `update-entry`，格式錯→修正後單筆補。`--pairs` 的分隔符**優先用分號 `;`**（中主題含逗號時逗號會切錯）。
- **整併流程（2026-08-03 WP1 改版）＝ `add-batch`／`update-entry` 更新狀態檔 → `set-category --pairs` 批次設分類（含小分題）→ 側錄 `add-side` → 重大素材 `set-alert` → `s2_render.py` 全量渲染 txt。agent 輸出趨近 0，不再手寫整份 txt。**
- ⚠️ **`to-compile`／`mark-compiled`／`compiled` 欄位已廢除**：它們存在的唯一理由是「讓 agent 不用每輪重寫整份」，render 讓重寫免費，增量反而多一次呼叫又會漏（0803 標籤字串比較實錯漏 50 則）。`resume` 的「待整併」改成「上次 render 後有變動」，只是參考值，不影響產出。
- ⚠️ **狀態檔＝唯一真相源，render 是單向投影**：狀態檔裡沒有的東西，下一輪 render 就會從 txt 消失。所以**任何進 txt 的內容都必須先進狀態檔**（側錄、檔頭重大提醒行都在此列），也**不要手改 txt**——下一輪就被覆蓋。品質掃命中要修的是 `raw_entry`，不是 txt。
- **腳本連續失敗 2 次**：把錯誤訊息原文記進回報，**當輪改用 V1 直讀 JSON 的做法繼續**（degraded mode），不得卡住不動。

## 3. 品質掃／統計／比對：`s2_validate.py`

```
python scripts/s2_validate.py check "G:\...\0802晚班交接.txt"   # 格式異常掃描，輸出命中清單（行號＋原因）
python scripts/s2_validate.py stats "G:\...\0802晚班交接.txt" --window "14:00 - 15:00"   # 輸出檔頭各行（日期由檔名推得）
```

**渲染：`s2_render.py`（2026-08-03 上線，WP1，整併主力）**

```
python scripts/s2_render.py --file "G:\...\0802-s2-state.json" --out "G:\...\0802晚班交接.txt" --window "2026-08-02 14:00 - 2026-08-03 09:00"
python scripts/s2_render.py --file "G:\...\0802-s2-state.json" --base-date 0802   # 不給 --out ＝ 印出預覽，不寫檔
```

- `check` 涵蓋 V1「格式異常」表全部可 regex 的項目：BITE 矛盾、缺 `▎畫面：`、缺講者、備註重標、GMT 洩漏、`FILE`／`檔案`、操作備註全形括號、重複代碼、第二括號非 `(BITE)` 等。
- **LLM 只處理命中清單**（回站核對、修 raw_entry＋txt），不再整份逐行讀。`明顯可疑`（數字矛盾等語意類）維持 LLM 抽查，但只在機器掃結果之外補充，不重複掃格式。
- `stats` 產出的**檔頭各行**（基本三行＋標記圖例＋沿用的重大提醒行）直接貼進檔頭（見 V1 `13`「晚班交接檔頭」）。走 render 時**不必再跑 `stats`**——檔頭由 render 自己生（同一個函式 `header_from_lines`）。
- **render 產出順序**：檔頭（🔴 重大行取自狀態檔 `alerts`）→ 樣板 16 格大分類（空格保留）→ `【中主題】` → 小分題（裸行＋`+` 分隔）→ 素材行。
- **時段標記由 render 依 `first_seen_checkpoint` 自動補**：23:00 前＝`△`、23:00–07:00＝`▲`、07:00–09:00＝`●`（23:00 那輪算 `▲`）。**補掃輪**（例如 09:10 撈回稍早漏掉的素材）checkpoint 判不準，用 `s2_state.py set-mark` 逐則寫死。
- `raw_entry` **零加工輸出**；側錄照 `14-S2b` 兩行式原樣帶出（不壓縮、不加 `▎`、TC 冒號格式保留）。
- **YouTube 兩行式（§4c）的網址行照樣帶時段標記**，但標記與網址之間**一定要有半形空格**——`△https://…` 會黏成一串、網址點不開（2026-08-03 使用者訂正）。render 的 prefix 固定以一個半形空格收尾，並對首行 lstrip，不會出現雙空格或漏空格。⚠️ 存進狀態檔時**小分題不要塞進 `raw_entry` 第一行**——那是 `category.小分題` 的位子，`raw_entry` 只放「網址行＋備註行」兩行（0802 有 8 則存成三行，render 會把小分題當內容輸出）。
- 寫檔走 tmp+rename（原子），寫完在狀態檔記 `last_render_ts`／`last_render_sha`（`--no-touch-state` 可略）。分類不在 16 格樣板內的會附在檔尾並在 stderr 警告——看到就去修 `set-category`。
- 💾 **輕量備份（2026-08-03 加）**：覆蓋前把現行 txt 另存 `{MMDD}晚班交接.txt.prev.txt`（同資料夾，只留最近一版，不無限累積）。這不是 diff3 復活——不比對、不裁決，純粹「render 本身出 bug 吐出壞 txt 時有東西可以救」。要回復上一版就把 `.prev.txt` 內容複製回正式檔名，不必跑腳本。
- ⛔ **手改偵測（2026-08-03 加）**：覆蓋前比對現行 txt 的 sha 與 `last_render_sha`，對不上就**拒絕覆蓋並 exit 3**。這是防「手改 txt／側錄只貼 txt 沒 add-side」被無聲洗掉——看到這個錯誤，先把 txt 上那些內容寫回狀態檔，確認可丟棄才加 `--force`。
- 📊 **每輪必看的對帳三行**：render 完會印「素材 N 則（±X）／側錄 M 段（±X）／YouTube K 支（±X）」，並點名「現行 txt 有、本次 render 沒有」的代碼。**出現點名就是漏了 `add-side`／`update-entry`**，不要當成正常。回報時要把這三行貼上來。
- ✅ render 完會**自動跑一次 `check`**（`--no-check` 可略），不必另外呼叫。
- ⚠️ **重大提醒行（`🔴 重大：…`）**：本輪掃到重大素材時，用 **`s2_state.py set-alert`** 存進狀態檔（render 每輪從那裡取；`stats --alert` 只剩不走 render 的舊路徑用）（最多 3 則），判準與撤除時機見 V1 `13`「重大提醒行」。**不給 `--alert` 時 `stats` 會自動沿用檔內既有的重大行**，所以例行重算檔頭不會把它洗掉；要撤才傳 `--clear-alerts`。`check` 會抓「代碼正文找不到／沒寫代碼／超過 3 行／不在檔頭」。
- **腳本失敗行為**：連續失敗 2 次 → 品質掃記為「未執行（腳本錯誤）」寫進回報，**禁止 agent 自行逐行手掃替代**。

## 4. SNTV 列表級收錄（機械白名單）

**為什麼體育可以不開詳情（2026-08-02 使用者確認的理由）**：體育新聞的畫面**必然是比賽或訪問**，開詳情看 shotlist 得到的資訊，跟從標題推出來的幾乎一樣——這是「跳過詳情不會漏掉判斷素材價值所需資訊」的少數類別。其他分類不成立（同樣是社會案件，畫面可能是空景、可能是關鍵監視器，差很多），所以白名單**只給體育、且只認機械可判的 `AP5`**。

- **僅限代碼 `AP5` 開頭**（SNTV 體育，判定規則同 V1）：直接以列表可見資訊（標題＋時長＋Source）寫簡版三段式，**不開詳情頁**。備註照標 `(SNTV)`，摘要一句話，結尾 `無BITE。`（列表看不到 BITE 就不標）。
- ⚠️ **`畫面：` 要寫「依標題可推的實際畫面」，絕不可寫操作註記（2026-08-02 實錯訂正）**：
  - ❌ `▎畫面：(列表級,未開詳情)。`／`▎畫面：(未開詳情)資料畫面。`——這是**給 agent 自己看的註記**，違反 V1「操作備註禁止寫進素材行」，編輯看了完全無用。
  - ✅ 依項目寫**必然會有的畫面**：`▎畫面：比賽精華、遠射進球與重播。`／`▎畫面：決賽對打精華、賽末點與捧盃。`／`▎畫面：Skubal投球資料畫面。`
  - 真的推不出來就**只寫最低限度一句**（`▎畫面：比賽精華。`），不要用括號註記填空。
  - `s2_validate.py` 已加通式偵測：素材行任何括號內含「列表級／未開詳情／待補／待確認／待人工／TODO」一律命中。
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

- **檔頭統計**用 `s2_validate.py stats --window "14:00 - 15:00"` 產生檔頭各行（見 V1 `13` 檔頭章節）。
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

> ⚠️ **路徑順序（2026-08-03 更新）：§1a API 直查（首選）→ §1b 清單直開（第一層退路）→ 本節 UI 舊做法（最後退路）。** 本節的 RT Next 鏈（5b）與 AP modal 相關條目**只在 §1b 也失敗時才使用**。其餘防卡條目（resume、跳站、半夜禁問等）不分路徑一律適用。
> ⚠️ **開工前的 Playwright profile 檢查是每輪必做**（見 §1a-0）——多 agent 並行會互鎖，0803 曾害 RT 三輪誤判「全站 0 素材」、素材空窗八小時。

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
6. **AP `/home` 偶發跳轉到其他頁（2026-08-02 實測，已見兩種變體）**：navigate 到 AP Newsroom `/home` 或點側欄 Latest 後，偶爾會被 SPA 路由帶去別的頁面——已見過 `/live`（Live Feeds）與 `/home/foryou`（訂閱推薦頁），根因同樣是路由不穩，**不是特定跳去哪一頁的問題**，之後遇到別的變體（例如 `/archive`）也比照處理。**每次讀列表前先確認 URL 是 `/home`**；不是就重新點側欄 Latest（點文字正中央），最多重試 2 次，仍失敗照第 2 條跳下一站並記錄。

## 未定／實測後要回填

- [ ] script 4,000 字元上限是否夠（RT 長稿實測）
- [ ] `s2_state.py` degraded mode 實際觸發率
- [ ] SNTV 列表級的資訊量晚班夠不夠用
- [ ] 實測一晚總 token，對照 V1 估算 30.8 萬
- [ ] **時間／呼叫次數**（2026-08-02 補，batch 熱修後量）：批次擷取段與整併段各自耗時、工具呼叫總數。原差異總表只估 token 沒估呼叫次數，這正是 V2 變慢沒被預見的原因；此數據也是 txt 渲染案（`common/plans/2026-08-02-S2提速計劃.md` WP1）的 go/no-go 依據
  - 第一筆基準（2026-08-03 00:00 實驗輪，§1b＋batch 全開）：**7 則全流程（含整併）12 分 18 秒、52 次呼叫**，守門零觸發，add-batch／--pairs 零跳過，check 0 命中。狀態檔操作僅佔個位數次呼叫，大宗已移到瀏覽器擷取——WP1 評估時要看的是整併段在這 52 次／12 分裡的佔比
