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

> 📌 **使用者丟一句話要改今天的庫存（標已播／改分類／撤素材…）→ 直接看 [§2a 使用者臨時口令](#2a-使用者臨時口令改庫存2026-08-04-訂案)**，那裡有口令對照表與「改完必 render」的固定四步。不必讀完整份文件。

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

> 📄 **完整配方（可直接抄的 JS、body 範例、欄位表）**：[`common/investigation-logs/2026-08-03-三站API破解總表.txt`](investigation-logs/2026-08-03-三站API破解總表.txt) ＋ NS 專篇 [`2026-08-03-NS掃帶卡點報告-回覆.txt`](investigation-logs/2026-08-03-NS掃帶卡點報告-回覆.txt)。本節只寫規則與地雷，不重複貼程式碼。

### 0-1) ⭐ 抽取白名單：`page.evaluate()` 裡先瘦身，只回傳需要的欄位（2026-08-03 上線）

**原始 API 回應有 6–9 成是雜訊**（媒體檔案變體、產品發布清單、授權計價規則、向量嵌入…），對「這則收不收、怎麼寫三段式」完全沒用，卻會整包進 agent 的 context。**在同一個 `browser_evaluate` 裡抽完再回傳**，實測省下：

| 端點 | 原始 | 抽取後 | 省 |
|---|---|---|---|
| AP 清單（5 則） | 53,461 | 2,190 | **95.9%** |
| AP 詳情（5 則） | 262,274 | 23,255 | **91.1%** |
| RT 單則（一般） | 7,207／23,049 | 1,486／1,820 | **79–92%** |
| RT 單則（超長整理包） | 74,145 | 55,530 | 25%（**內容本身就長，不是沒抽好**） |

⛔ **不准砍的東西**（砍了就寫不出三段式）：稿件全文（AP `script.nitf`／RT `story`）、**SHOTLIST 段**、**SOUNDBITE 段與講者**、限制語、來源、形式、時長、素材代碼。瘦身砍的只有 metadata／檔案 URL／計價規則，**內容本體一個字都不能動**（同側錄逐字規則）。

✅ **保真驗證做法（改抽取邏輯後都要重跑一次，兩項都要驗）**：
1. **逐字比對**：把「原始欄位只去 HTML tag」與「抽取結果」都正規化成純文字（`replace(/[^\p{L}\p{N}]/gu,'')`）後逐字元比對。⚠️ 比對基準要**先扣掉實體名**（`nbsp`／`amp` 等），否則會誤判成失敗——`&amp;`→`&` 後被正規化移除，看起來像少了 3 個字元，其實是正確解碼。
2. **殘留掃描**：抽取結果裡 `/&[a-zA-Z#0-9]{2,8};/`（未解碼實體）與 `/<[^>]+>/`（未去乾淨的 tag）都必須是 **0 命中**。第 1 項單獨看不出實體殘留，一定要配第 2 項。

**實測記錄**：2026-08-03 共跑 **8 輪**（第 7–8 輪加驗**全欄位殘留掃描**——前 6 輪只掃稿件欄位，`head`／`slug`／`restr`／`title`／`cap` 這輪才補掃，全乾淨；與**冪等性**——同一則抓兩次、抽取結果位元組級相同，RT／AP 皆過；AP 滿頁 16 則 706KB→82KB 省 88.4%，時長／限制語 16/16 無缺漏）。前 6 輪：2026-08-03 共跑 6 輪——AP 6/6＋8/8＋10/10＋12/12、RT 6/6＋4/4＋5/5；最終版全部 **殘留實體 0、殘留 tag 0**。第 5–6 輪另做**交叉核對**：AP 的 API 前 8 則與頁面 DOM 前 8 則**編號與順序逐位完全相同**；RT 的 guid 推導 Edit No 與 DOM 清單吻合（DOM 是虛擬化清單只渲染視窗內 ~8 則，API 抓到而 DOM 沒渲染的屬正常，**不是抽取錯誤**）；early-access 項目（稿未到）`story` 為空、`early:true` 正確標記。

⚠️ **驗證時別用「原始 raw 裡有沒有 SHOTLIST 字樣」當基準**——會假陽性：RT 回應裡的 `video-shotlist-url`／`stream:shotlist:json`／檔名 `..._STREAM-SHOTLIST-JSON_....JSON` 都含該字樣，但**不是**畫面清單內容（RT 的 shotlist 是獨立資源，item API 不含它；有些則的畫面描述寫在 `story` 開頭的 `VIDEO SHOWS:` 段）。要比就比**欄位內容本身**。

**共用的去 tag ＋ 實體解碼函式**（AP `script.nitf` 與 RT `story` 都是 HTML）：

```js
const ENT = {nbsp:' ',amp:'&',quot:'"',apos:"'",lt:'<',gt:'>',
  rsquo:'’',lsquo:'‘',ldquo:'“',rdquo:'”',ndash:'–',mdash:'—',hellip:'…',bull:'•',
  eacute:'é',egrave:'è',agrave:'à',ccedil:'ç',uuml:'ü',ouml:'ö',auml:'ä',szlig:'ß',
  ntilde:'ñ',deg:'°',euro:'€',pound:'£',copy:'©',reg:'®'};
const decodeEnt = (s) => String(s||'')
  .replace(/&#x([0-9a-fA-F]+);/g,(_,h)=>String.fromCodePoint(parseInt(h,16)))   // 十六進位
  .replace(/&#(\d+);/g,(_,d)=>String.fromCodePoint(+d))                          // 十進位
  .replace(/&([a-zA-Z]+);/g,(m,n)=>(n.toLowerCase() in ENT)?ENT[n.toLowerCase()]:m);
const clean = (h) => decodeEnt(
    String(h||'').replace(/<\/p>\s*<p>/gi,'\n').replace(/<br\s*\/?>/gi,'\n').replace(/<[^>]+>/g,'')
  ).replace(/\n{3,}/g,'\n\n').trim();
```

🔴 **實體一定要解碼，只列 `&nbsp;&amp;&quot;` 是不夠的（2026-08-03 多測兩輪才抓到）**：只處理那三個時，`&rsquo;`／`&ldquo;`／`&rdquo;`／`&ndash;` 會**原樣殘留在稿件裡**——`Iran&rsquo;s Foreign Minister` 就這樣進了素材行。上面的 `decodeEnt` 連**數字實體**（`&#8217;`／`&#x2019;`）一起處理，實測 RT 4/4、AP 10/10 **殘留實體 0、殘留 tag 0**。

⚠️ **不要改用 `DOMParser`／`textarea.innerHTML` 解碼**：看似更通用，但 Reuters 頁面的 CSP／Trusted Types 會讓 `DOMParser.parseFromString` **回傳空字串**（實測 v3 長度 0），而且失敗時**不報錯**，會靜默吐出空稿。純字串處理才跨站穩定。

⚠️ **RT 還要多一層 unescape**（transit 字串裡的 `\"` 會殘留）：`.replace(/\\"/g,'"').replace(/\\n/g,'\n')`，否則標題會變成 `Gladiatoren - \"Römische Tage\"`。

⚠️ **超長整理包**（RT TIMELINE／WRAP，實測單則 `story` 可達 **5.5 萬字元**）：抽取幫不上忙，因為那是內容本體。晚班交接只需要一句話摘要＋畫面段，**這類可只取前 3,000 字元＋標記 `(整理包 內容過長已截斷)`**，需要全文再回頭單獨取。

### 0) 開工前：Playwright 環境衛生（**每次都要做，不是可選**）

- **一律用 Playwright 工具組**（`mcp__browser__*`），**不是 claude-in-chrome**——NS 的 localStorage 在 claude-in-chrome 會被 extension 隱私防護擋死（回 `[BLOCKED: Cookie/query string data]`），AP／RT 的跨網域 fetch 也會被頁面 AdBlock 纏住。
- **檢查並清掉殘留 Chrome**：
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ? { $_.CommandLine -like "*playwright-mcp-profile*" } |
    Select ProcessId, CreationDate, @{n='Age';e={[int]((Get-Date)-$_.CreationDate).TotalMinutes}}
  ```
  用 `Get-Process` 的 `MainWindowTitle`／CPU／存活時間判斷是否閒置；閒置就 `Stop-Process -Force` 再開工。
- **自己收工也要關瀏覽器**，不要留給下一個 agent。⚠️ **`browser_close` 偶爾因暫時性服務錯誤失敗（2026-08-04 實錯回報）**：失敗不代表瀏覽器沒關掉，改用精準的 Playwright Chrome PID（前面殘留檢查那段查到的 ProcessId）`Stop-Process` 收尾，再確認真的關了，不要因為工具回錯就當沒收工、留著殘留鎖下一輪。
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
- `hash` **照抄當下頁面實際請求**（實測 `klwn20`，跨 session 穩定但那像前端 build hash、改版會變，不可硬編）。
- ⭐ **抽取白名單（實測定版，欄位名與型別都已逐一 dump 確認）**：

  ```js
  const pick = (t,k) => { const m = t.match(new RegExp('"~:'+k+'","((?:[^"\\\\]|\\\\.)*)"')); return m?m[1]:''; };
  const slimRT = (t, guid) => {
    const story = clean(pick(t,'story'));
    return {
      edit:  (guid.match(/RW(\d{4})/)||[])[1] || '',   // Edit No 由 guid 推，不從內文抓
      head:  unesc(pick(t,'headline')),
      slug:  unesc(pick(t,'slug')),
      dur:   pick(t,'duration'),        // ⚠️ 字串 "00:02:34" 不是數字，別用 \d+ 抓
      src:   unesc(pick(t,'source')),   // CCTV／SKAI TV／第三方判定用
      restr: unesc(pick(t,'restrictions')),  // ⚠️ 純字串不是陣列
      early: t.includes('early-access-script'),  // true＝稿未到（pending 判定）
      story,  // ⚠️ 稿件全文在 `~:story`，不是 body／script
      sb_count: (story.match(/SOUNDBITE/gi) || []).length  // 🎯 BITE 機械計數（見下方「BITE 判定」）
    };
  };
  ```

- ⚠️ **欄位名容易猜錯的三個**：稿全文是 **`~:story`**（不是 `body`／`script`）；`duration` 是**字串**；`restrictions` 是**純字串**（`"Broadcast: None. Digital: None.."`／`"Broadcast: No Use Greece…"`），不是陣列。
- `early-access-script` 出現＝該則只有早期版、**稿未到**，對應 `script_status: pending`（判準仍以 `13`「有稿判準」為準）。
- 🎯 **BITE 判定＝看 `sb_count`，不是 agent 自己讀稿判斷（2026-08-04 訂案，實錯修正）**：`sb_count > 0` 的素材**禁止標「無BITE」**——機器已經數出稿裡有 N 個 `SOUNDBITE)` 段，agent 的工作只剩「把那些段落翻成 `▎BITE：{講者}「{內容}」`」，不再自行判斷有無。0803–0804 實錯：0803 晚班交接的 ▲ 素材裡，**RT 誤判率高達 60%**（15 則抽查、9 則有 SOUNDBITE 卻標「無BITE」，最嚴重的 `RT2896` 有 7 個、`RT2915` 有 5 個）。抽取與資料都沒問題（驗證過 `pick()` 完整保留全部 SOUNDBITE、逐 37 個欄位確認引言只在 `story`、版次假說也排除），所以判定必須機械化。

  ⚠️ **誤判的真正形狀：不是「沒看到」，是「看到了但當成素材說明用掉」（2026-08-04 回頭比對 9 則誤判後歸納）**——誤判集中在「**引言講的事＝摘要已經寫過的事**」這種形態：

  | 素材 | 摘要寫了 | 實際 BITE 內容 |
  |---|---|---|
  | `RT2925` | 聯合國歡迎紅十字會與翁山蘇姬會面 | 聯合國副發言人說「我們注意到紅十字會宣布代表已探視翁山蘇姬」「我們歡迎這項進展」 |
  | `RT2907` | 川普成立委員會協助美軍配偶 | 川普說「我正簽署行政命令成立史上首個總統軍眷委員會」 |
  | `RT2955` | 華爾街上漲、道瓊收在紀錄高位 | 基金經理談雲端巨頭財報與 AI 資本支出動能 |

  agent 讀完稿件後把 SOUNDBITE 內容**消化進摘要**，然後認定「這些話我已經寫過了」，就沒再另開 `▎BITE：` 段。對照組支持這個歸納：標對的 6 則原始稿件確實 0 個 SOUNDBITE，而誤判的 9 則**全部**有 SOUNDBITE——沒有一則是「有 SOUNDBITE 但完全沒被寫進摘要」。AP 那邊形狀相同、只是更明顯（`AP5466752` 摘要已寫出「稱『絕佳機會』」，結尾仍標無BITE）。

  ⛔ **所以要記住：引言被消化進摘要 ≠ 可以不寫 BITE 段。** 兩段的用途完全不同——摘要回答「這件事是什麼」，BITE 段回答「**這支帶子有哪一段話可以直接剪出來上鏡、講者是誰**」。編輯挑素材時看的是後者，摘要寫得再完整都不能取代。

- ⛔ **CCTV／CNS 素材不做 BITE 事後查證（2026-08-04 訂案，成本效益考量）**：這類第三方供稿**不在 `my-feed` 清單範圍**，要另換查詢路徑才找得到，是所有查證裡成本最高的；但它們本質是官媒畫面包，**有可用引言的機率本來就低**。花最貴的成本查最不可能出錯的類別，CP 值最差——**掃到就照當下判斷寫，事後一律不回頭查證**。（0804 實例：`RT2652`／`2607`／`2606`／`2605` 四則 CCTV／CNS 卡在這裡查不到，不必再嘗試。）
- ⚠️ **要查證時必須比對 headline，光靠 Edit No 會抓錯素材（2026-08-04 實錯）**：**Edit No 會跨日重複使用**——0804 查 `RT2607` 時，regex `newsml_RW2607\d{8}RP1` 抓到的是 `01082026`（8/1）那則「多瑙河水位創新低」，但 state 裡的 `RT2607` 是 CCTV「美股週一收高」，**完全是兩則不同的新聞**，一度誤判成「5 個 SOUNDBITE 卻標無BITE」。**拿到 guid 後一定要比對 headline 與 state 摘要是否吻合，確認是同一則才採信查證結果。**

### 2) AP

- **清單**：`POST https://api.newsroom.ap.org/v1/nrsearch/search/topic`（cookie 驗證）。**照抄頁面實際發出的 request body**——自己拼的 body 排序會偏 relevance 抓到舊素材；照抄則順序與畫面完全一致（實測 16 則逐一比對相符）。
- ⚠️ **`PageNumber` 不可靠**：實測 `PageNumber=2`＋`PageSize=16` 回了 100 筆、與第 1 頁零重疊，回應卻自稱 Page=2。
- 🔴🔴 **`PageSize` 一個字都不准改，只能照抄頁面的 `16`（2026-08-04 實測再訂正，推翻先前「往上加沒問題／50、100、200 已驗過」的說法）**：`PageSize` **不論調大或調小都會靜默換掉排序**，回傳完全不同的一批舊素材，且**毫無錯誤訊息**：
  - **調小**（0803 18:50 實測）：`16 → 5`，回傳從「當下最新」變成 **2024–2025 年舊素材**（`Afghanistan Earthquake Bereaved` 2025-09、`HZ US CES BOSCH` 2024-01）。
  - **調大**（0804 11:4x 實測，這次才發現）：同一個 body、同一個 TopicId，`PageSize=16` 回傳最新的 `4676491`（當下最新素材）；改成 **`PageSize=50` 回傳最新的變成 `4472065`**（更舊的一批）、`PageSize=100` 最新是 `4634593`——**要找的今日素材一則都不在裡面**。先前「50／100／200 已驗過」是誤判，實際上只有 16 是對的。
  - ⛔ **所以「要多筆就加大 PageSize」這條舊做法作廢**。需要更多則時，正確做法是**照抄 `PageSize=16` 分批取**（`PageNumber` 也不可靠，見上），或改用其他能穩定定位的路徑（§1b 清單 DOM 直撈）。**永遠不要為了「多抓幾則」或「只想看幾則」去動這個值**——動了就會拿到兩年前的素材，diff 之後全部被當成「新素材」收進庫存。
  - 這也是為什麼規則一直寫「**照抄頁面實際發出的 request body**」：照抄就不會踩到。
- 欄位：`_source.itemid`＝32 碼 GUID、`_source.editorialid`＝**AP 編號**、`friendlykey`／`title`／`headline`／`dateline`。
- **文稿**：`POST /v1/nrsearch/search/item/details`，body `{"ItemIds":"{itemid}","mediaType":"video","IsNonSalable":false}`。**逗號串多則不支援**（回空），一則一次；但可在同一個 `browser_evaluate` 裡 `Promise.all` 打 N 則，**工具呼叫仍只算 1 次**。
- `TopicId` 實測跨 session 穩定（`116e9ab7…`），仍建議每輪從頁面請求照抄。
- ⭐ **抽取白名單（實測定版，欄位名與型別都已逐一 dump 確認）**：

  ```js
  // 清單：diff 與初判用（不必開詳情就能判斷收不收、是不是 SNTV）
  const slimList = (s) => ({
    id: 'AP' + s.editorialid, itemid: s.itemid,   // ⚠️ 一定要加 AP 前綴，見下方「id 前綴」踩雷
    title: s.title, head: s.headline,
    cap:  clean(s.caption && s.caption.nitf),  // ⭐ 清單就有一句話摘要
    role: s.editorialrole,                        // ⭐ 形式：VO／VOSOT／SOT／Package
    src:  (s.sources||[]).map(x=>x.name).join('/'),  // ⭐ SNTV 判定（本則的 sources，不是列表黏標）
    sig:  (s.signals||[]).filter(x=>/Ready|SNTV/i.test(x)).join(','),  // NewsroomReady＝稿齊
    line: s.dateline, ts: s.firstcreated, comp: s.compositiontype
  });
  // 詳情：寫三段式用
  const slimDetail = (s) => {
    const script = clean(s.script && s.script.nitf);  // ⚠️ 稿全文在 `script.nitf`（HTML）
    return {
      id: 'AP' + s.editorialid, title: s.title, head: s.headline,
      cap:    clean(s.caption && s.caption.nitf),
      script,
      role: s.editorialrole, src: (s.sources||[]).map(x=>x.name).join('/'),
      rights: s.rightsline, line: s.dateline || s.locationline,
      dur:  (s.shots && s.shots[0] && s.shots[0].end) || '',  // ⚠️ 沒有 duration 欄位，時長由 shots[0].end 推
      comp: s.compositiontype,
      sb_count: (script.match(/SOUNDBITE/gi) || []).length,   // 🎯 BITE 機械計數
      has_sot: /SOT/i.test(s.editorialrole || ''),            // 🎯 VOSOT／SOT 形式＝必有訪問聲音
      prelim: /^\s*\+\+\s*PRELIMINARY SCRIPT/i.test(script)   // 🎯 初稿：只認開頭，內文提到不算
    };
  };
  ```

- 🎯 **`prelim` 為 true ＝ 素材照收、標 `pending`、備註加 `(初稿)`，下一輪補正式稿（2026-08-04 使用者訂案）**：
  - **不是排除**——這跟 NS 的 `footageType==="GRAPHIC"` 佔位公告完全不同。AP 這種是**真素材**（實例 `AP4676355` 伊朗外交部簡報，有畫面有 SOUNDBITE），只是稿子還是初稿版，正式稿之後會出。NS 那種本身不是新聞帶，要整則排除。
  - **AP 沒有機械欄位可判初稿**（不像 NS 有 `footageType`），只能掃 `script` 字樣——所以正則**錨定開頭**（`^\s*\+\+`），不對全文 `find`，避免內文順帶提到就誤判。
  - 內容照初稿版正常寫三段式，**有 BITE 就寫 BITE**，不要因為是初稿就留白（`sb_count`／`has_sot` 兜底照常適用）。
  - 下一輪 pending 清查回頭重查：正式稿到了就覆寫 `raw_entry`、拿掉 `(初稿)`、轉 `has_script`。

- 🎯 **BITE 判定＝看 `has_sot` 與 `sb_count`，不是 agent 自己讀稿判斷（2026-08-04 訂案，實錯修正）**：
  - **`has_sot`（`editorialrole` 含 `SOT`）為 true → 必定標 `(BITE)`**，這是 AP 自己標的素材形式（`VOSOT`＝VO＋SOT、`SOT`＝純訪問），有這個標記就代表帶子裡有訪問聲音——0804 實測當下清單 **16/16 全是 `VOSOT`／`SOT`**，但 state 裡 AP 卻有 55% 標「無BITE」，明顯大量誤判。
  - **引言逐字稿在 `SHOTLIST` 段，不在 `STORYLINE` 段**（0804 實測 6 則：SOUNDBITE 全部在 SHOTLIST、STORYLINE 段 0 個）——寫 `▎BITE：` 段時要去 **SHOTLIST 段**抓 `SOUNDBITE (語言) 講者職銜姓名, SAYING:` 後面的引言，**只讀 STORYLINE（敘事摘要段）會誤以為整篇沒有引言**，這正是大量「無BITE」誤判的成因。
  - `sb_count > 0` 同樣**禁止標「無BITE」**；`has_sot` 為 true 但 `sb_count` 為 0（shotlist 沒逐字）時，標 `(BITE)` 並在 BITE 段寫講者與內容概述（例：`▎BITE：市長受訪談疏散進度（逐字稿未附）`），不可寫「無BITE」。
  - ⚠️ **AP 也會出現「引言被消化進摘要就不寫 BITE 段」這個形狀**——`AP5466752` 摘要已寫出「稱『絕佳機會』」、畫面段寫「受訪」，結尾仍標「無BITE」，自相矛盾。成因與判準見上方 **§1 RT 的「誤判的真正形狀」** 那段，兩站完全一樣：**摘要回答「這件事是什麼」，BITE 段回答「哪一段話可以直接剪出來上鏡、講者是誰」，前者不能取代後者。**

- ⚠️ **`id` 前綴踩雷（2026-08-04 工作 agent 實錯回報，已修）**：`s.editorialid` 是**裸數字**（如 `4676366`），但狀態檔／既有素材代碼一律是 `AP` 前綴＋數字（`AP4676366`）。**上面兩個函式都已補上 `'AP' +` 前綴**——早期版本沒補，若 diff 步驟拿裸數字直接跟狀態檔比對，永遠比不出「已收過」，每輪都會把舊素材當新素材重新判斷一次。**任何依這份文件早期版本抄過程式碼的地方，都要回頭檢查有沒有補這個前綴。**
- ⚠️ **欄位名容易猜錯的三個**：稿全文是 **`script.nitf`**（HTML 字串，不是 `storyline`／`shotlist`——照那兩個名字抓會拿到空字串，還會算出「省 98%」的假數字）；**沒有 `duration` 欄位**，時長要用 `shots[0].end`（格式 `00:02:16.720`）換算成 `MM:SS`；`caption`／`script` 都是**物件**，內容在 `.nitf`。
- **雜訊大戶**：`renditions`（7,920）＋`filings`（7,373）＝ 單則詳情的 63%；另有 `embeddings`／`pooled_embedding`／`searchembedding`（向量嵌入）、`subjects`／`audiences`／`services`（分類代碼）。這些**一律不取**。
- **`signals` 含 `NewsroomReady`** 可當「稿齊」訊號。
- ⭐ **SNTV 判定改用 `signals` 最可靠（2026-08-03 實測）**：`signals` 陣列裡會直接出現 `sntv`／`sntvGlobalCleared`／`sntvMENAcleared`。實例 `AP5466730` 的 `sources[].name` 是 **`World Surf League`**（供片方），光看 source 判不出是 SNTV，但 `signals` 有 `sntv`。
  - **判準優先序**：`signals` 含 `sntv` ＞ `sources[].name` 為 `SNTV` ＞ 代碼 `AP5` 開頭。三者都是**本則自己的欄位**，**不會踩到列表扁平文字把下一則徽章黏上來的坑**（見 `13`「列表文字黏標」）。
- **一輪實測（2026-08-03 18:5x，PageSize=16 清單＋前 3 則詳情）**：清單 146,732 → 7,390、詳情 100,073 → 14,696，**總省 91.1%**；寫三段式的每個元素（代碼／限制語／來源／形式／時長／SHOTLIST／SOUNDBITE／摘要）**全數保留**。

### 3) NS（CNN Newsource）——**收益最大的一站**

- **清單即文稿**：`POST https://newsource-content-api-530.ns.cnn.com/api/v3/stories`，一次回傳 **`alternateIds.bitcentralId`（＝NS 編號）＋`footageType`（PKG/SOT/VO 等形式）＋`duration`＋`description`（現成一句摘要）＋`content.bitcentral.script`（稿件全文，含 `--LEAD IN--`／`--VO SCRIPT--` 標記）＋`embargo`**。**完全不必開詳情頁或 Preview modal。**
- Bearer token 在 `localStorage.newsourceSession.token`（**1 小時效期**）。

> 🔴 **NS 登入態是「滑動時效」，過期就必須人工重登——這是 NS 天生設計，不是設定問題（2026-08-04 實測定案）**
>
> **實測證據**：三站認證機制根本不同——**AP** 有 `session_user`（httpOnly，**7 天**）、**RT** 有 `mexlogin`（**23 小時**）＋`rcp-sid`；**NS 一個認證 cookie 都沒有**（`newsource.ns.cnn.com`／`.cnnnewsource.com`／`.cnn.com` 底下全是 `_ga`／`_cb`／`_chartbeat2`／`SigniantAppInstalled` 這類 analytics 與廣告）。**NS 的登入態 100% 只存在 localStorage 那顆 1 小時 JWT 裡。**
>
> **機制**：`exp - iat` 恰為 3600 秒。只要 token **還沒過期**，每次載入 NS 頁面就會拿舊 token 換一顆新的、時效**重新算 1 小時**（sliding session）。一旦**過期**，沒有任何後備憑證可用——實測把 localStorage 的 session 刪掉後 reload，直接被踢回 `/`、出現密碼欄位，**無法自動恢復**。
>
> ⚠️ **這會誤導診斷**：如果剛好在 1 小時內測試，會看到「重開瀏覽器也能自動登入」的假象（0804 第一輪測試就被誤導過）。要驗證必須模擬「token 不存在」的狀態，不是只重開瀏覽器。

- 🎫 **NS 保活（keep-alive）：每 58 分鐘續一次門票（2026-08-04 使用者訂案）**
  - **為什麼需要**：固定排程的間隔（23:00→01:00 隔 2hr、01:00→04:30 隔 3.5hr、13:00→隔天 16:00 隔 3hr）**每一段都超過 1 小時**，等於每輪開工 NS 幾乎必定已經過期。插一個極輕量的保活動作就能無限續期。
  - **做什麼**：只要 `browser_navigate` 開一次 `https://newsource.ns.cnn.com/landing`、等 token 寫入、確認 `isAuthenticated` 為真，就完成續期——**不查清單、不打 API、不寫狀態檔**，成本約 1–2 次工具呼叫。
  - ⚠️ **一律由掃帶 agent 自己執行，不可另開獨立 agent／排程去做**（使用者明確要求）：Playwright 只有**一個** persistent profile，另一個行程去開瀏覽器就會跟正在掃帶的 agent 互鎖——那正是 0803 害 RT 空窗八小時的坑（見 §0）。**保活必須排進掃帶 agent 自己的工作序列裡，跟其他 Playwright 動作共用同一個瀏覽器 session。**
  - **時機**：掃帶 agent 在**兩輪之間的等待期**，若距離上次接觸 NS 已接近 58 分鐘，就順手做一次保活再繼續等；若下一輪馬上就要開工，直接開工即可（開工本身就會續期），不必多跑一次。
  - **過期了怎麼辦**：保活失敗或發現已經卡登入頁 → **停下來請使用者手動登入**，agent **不得自行輸入帳密**。無人值守時段（`▲`）遇到就照 §5「半夜禁問」原則記進 `needs-review` 並跳過 NS，不要卡住整輪。
- ⚠️ **回應是多行 JSON（NDJSON）**，不能 `r.json()`——取含 `"stories"` 的那一行再 parse。
- `scriptOnly: true` **就是 UI 上點不動的 Has Script 篩選**；`from`／`size` 分頁，`size` 上限 100。
- ⚠️ **`size` 開大配全稿一次回傳會爆量（2026-08-04 工作 agent 實錯回報）**：`size:100` 一次要完整稿件全文，實測輸出約 **198k 字元**，整包塞進 agent context 太浪費。**正確做法：先用小欄位（不含 `script`）篩出時間窗內真的要收的則數，再只對這些則另外打一次要全文的查詢**——不要為了少一次呼叫就一次要 100 則的完整稿。
- ⛔ **兩類直接排除，用 `footageType` 機械判斷（2026-08-03 晚實測定版，不要用關鍵字猜）**：判準與理由見 `13`「NS 兩類素材不採納」。抽取階段就濾掉，不進 `batch.json`：

  ```js
  const SKIP = (it) => {
    const ft = it.footageType || '';
    const sc = (it.content && it.content.bitcentral && it.content.bitcentral.script) || '';
    if (ft === 'AUDIO TRACK') return 'audio';              // 純音軌，無畫面
    if (ft === 'GRAPHIC' && /THIS IS NOT THE FINAL SCRIPT/i.test(sc)) return 'prelim';  // 初稿佔位公告
    return '';
  };
  // 初稿公告會點名最終版 ID，撈出來寫進回報（那則才是要收的）
  const finalId = (sc) => (sc.match(/WILL BE IN ITEM\s*<?[^>]*>?\s*([A-Z]{2}-\d{2,3}[A-Z]{2})/i)||[])[1] || '';
  ```

- **`footageType` 實測全集**（0803 晚 100 則樣本）：`PKG`／`NAT PKG`／`DONUT`／`LOOK LIVE`／`VO/NAT`／`VO/STILL`／`VO/SIL`／`VO/RAW`／`SOT`／`BUTTED SOTS`／`ISO`／`CLIP`／`BEEPER`／`GRAPHIC`／`AUDIO TRACK`／`""`（空字串多為 `VERTICAL:` 直式素材）。前面那些是正常內容型態；要排除的只有 `AUDIO TRACK` 與「`GRAPHIC` ＋初稿字樣」兩種。
- 🎯 **BITE 判定＝看 `footageType`（機械判準，2026-08-04 明文化）**：`footageType` 為 `SOT`／`BUTTED SOTS`／`SOT RAW` → **必定標 `(BITE)`**，禁止標「無BITE」。0804 抽驗 10 則 `SOT` 類素材，state 裡全部正確標了 `(BITE)`——NS 是三站裡唯一沒出誤判的，正因為它一直在用這個機械欄位；這條把既有正確做法明文化，與 RT（`sb_count`）／AP（`has_sot`）統一成同一套「有無 BITE 由機器判、BITE 內容才是 LLM 的事」原則。⚠️ NS 稿件**不用 `SOUNDBITE` 這個詞**（0804 實測 60 則全部 0 個），引言段標記是 `--SOT--`——**不要拿 AP／RT 的關鍵字習慣來掃 NS 稿件**，會全部誤判成無BITE。
- ⚠️ **`hideScript` 與初稿無關**（實測排除的誤判線索）：`hideScript: true` 的那幾則稿件一樣完整（含 `--LEAD IN--`／`--VO SCRIPT--`），只是站方的顯示設定，**不可拿來判斷稿件狀態**。
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
python scripts/s2_state.py set-aired --ids RT2995,AP4676455
                                                           # 🟤 本台已做過（仍留庫存、仍可做後續）；--clear 取消
                                                           # ⛔ 只有使用者下令才標，agent 不得自行判斷
python scripts/s2_state.py set-mark --ids RT2754,RT2753 --mark ▲
                                                           # 補掃輪等 checkpoint 判不準時寫死時段標記（--clear 改回自動）
python scripts/s2_state.py get --id RT2333                 # 單則全文
python scripts/s2_state.py needs-review add --id RT2333 --note "疑似UGC，待人工"
python scripts/s2_state.py needs-review list
python scripts/s2_state.py needs-review done --ids RT2333    # 處理完就結案，別讓清單只進不出
```

- 📌 **`needs-review` 是「待辦」不是「日誌」，處理完一定要 `done`（2026-08-04 補齊）**：
  - **`add` 對不存在的 id** 會建一個 `script_status="note"` 的備註殼（例：`--id RT-r9-空白` 記某輪掃到 0 筆的原因）。**殼不算素材**——不計入 `pending`、不進 render、不出現在晚班交接，只出現在 `resume` 的「待人工」與 `needs-review list`。⚠️ 0803 實錯：這種殼原本建成 `pending`，害 60 則 pending 裡有 7 則是假的。
  - **`done --ids` 是唯一的結案出口**，兩種項目處理方式不同（腳本自動分辨，不用你判斷）：**備註殼**→整筆刪掉；**真素材**→只脫掉 `needs_review` 旗標，素材與內文原封不動留在庫存。
  - **全有全無**：一批裡有任何一個 id 不存在、或本來就沒有標記，整批都不處理並報錯——避免「以為清掉了、其實只清一半」。
  - 不結案的話，`resume` 每輪都會重印同一批早就處理完的項目，清單失去警示作用，真正該注意的新項目會被淹沒。

- 批次擷取流程 ＝ 收集本輪列表 ID → `diff` → 只對「新的」取文稿（**§1a API 直查，不開詳情頁**；失敗才退 §1b） → **邊看邊把每則累積進一份 `batch.json`，全部看完後一次 `add-batch`**。不要一則一次 `add`（2026-08-02 起：呼叫次數是 V2 變慢主因，一輪 25 則從約 52 次呼叫降到約 4 次）。**全程不載入 70 則 raw_entry。**
- **批次規則**：`batch.json` 是 JSON 陣列，每筆 `{"id","source","checkpoint","status","entry"}`（`entry` 直接放字串，含換行）。撞已存在 id 或格式錯的單筆會**自動跳過並回報原因、不中斷**——回報裡有跳過清單時，逐筆判斷：已存在→改用 `update-entry`，格式錯→修正後單筆補。`--pairs` 的分隔符**優先用分號 `;`**（中主題含逗號時逗號會切錯）。
- 🎯 **RT／AP 每筆必帶 `sb_count`（2026-08-04 起，BITE 機械兜底）**：抽取白名單已回傳 `sb_count`（RT）／`sb_count`＋`has_sot`（AP），寫 batch.json 時**原樣帶上**（`{"id":…,"sb_count":4,…}`）。`add-batch` 會擋「`sb_count > 0` 卻寫『無BITE』」的單筆（跳過並要求把引言寫進 `▎BITE：` 段重送）；`update-entry` 用 `--sb-count N` 帶入，同樣會擋。NS 走 `footageType` 判準、SNTV 列表級沒有全文，這兩類**不帶** `sb_count`（不帶＝不檢查，向下相容）。
- 💾 **每筆必帶 `src_text`＝瘦身後的原文，落檔留存（2026-08-04 訂案）**：`batch.json` 每筆再加一個 `src_text`，放**抽取白名單瘦身後的稿件全文**（RT 的 `story`／AP 的 `script`／NS 的 `script`，已經去過 tag 與 metadata 的那份），`add-batch` 會忽略這個未知欄位、不影響入庫，但檔案本身留在 `{YYYYMMDD}/` 暫存資料夾裡可事後查。
  - **為什麼要存（0804 實錯代價）**：原本 `batch.json` 只存 `entry`（agent 消化完的中文三段式成品），**瘦身後的原文用完就沒了**。0804 回頭查 BITE 誤判時，只能重開瀏覽器打 API 撈原稿，而且**RT 有 4 則（`RT2875`／`2845`／`2902`／`2847`）、AP 有 9 則已經捲出 API 翻頁範圍，永遠查不回來**——素材一旦被新素材推出清單就無法回溯，等於當天的判斷再也無法查證。存了原文就能離線比對，不必開瀏覽器、也不受站方清單長度限制。
  - **用途**：①誤判查證（BITE、限制語、時長、講者都能回頭核）②`sb_count` 兜底擋下時直接看原文改，不必重打 API ③日後要做規則研究或抽樣分析有現成語料。
  - **成本可忽略**：瘦身後 AP 詳情單則約 5KB、RT 約 1.5KB、NS 約 1KB，一輪 25 則約 40–100KB，一晚十幾輪約 1–2MB。本來就歸檔在日期資料夾、隔天可清，不佔長期空間。
  - ⛔ **存的是「瘦身後」不是「原始 API 回應」**——原始回應 6–9 成是 `renditions`／計價規則／向量嵌入等雜訊（見 §1a-0-1），存那個等於把省下來的空間又浪費掉。也**不准存 token／cookie**（回傳值黑名單一樣適用）。
- **整併流程（2026-08-03 WP1 改版）＝ `pending` 全量重查（見下）→ `add-batch`／`update-entry` 更新狀態檔 → `set-category --pairs` 批次設分類（含小分題）→ 側錄 `add-side` → 重大素材 `set-alert` → `s2_render.py` 全量渲染 txt。agent 輸出趨近 0，不再手寫整份 txt。**
- ⚠️ **pending 每輪都要主動清查，不只 23:00（2026-08-03 訂正，見 `13` 決策 4）**：跑 `pending` 看目前清單，逐則走 §1a API 批次重查（NS 整批一次查；RT／AP guid／itemid 一次 `Promise.all` 打 N 則，同一個 `browser_evaluate` 裡做，工具呼叫仍算 1 次）。稿已到就 `update-entry` 覆寫；稿仍未到維持原樣。**查完照規則直接處理，不要停下來問使用者「要不要清」**——這不是需要裁決的事，是每輪固定要做的步驟。pending 為 0 的輪次跳過，不必空跑。
  - 🎟️ **搭便車：這次重查順手把 `sb_count` 記下來（2026-08-04 訂案，近乎零成本）**：pending 清查本來就要打 API 拿全文，**同一份回應順手數一次 `SOUNDBITE`**，`update-entry` 時用 `--sb-count N` 帶入即可——不另外開一趟、不多一次呼叫。轉正那一刻正是最容易漏標 BITE 的時機（見 §1「誤判的真正形狀」），搭這班順風車等於免費補上兜底。
- ⚠️ **`to-compile`／`mark-compiled`／`compiled` 欄位已廢除**：它們存在的唯一理由是「讓 agent 不用每輪重寫整份」，render 讓重寫免費，增量反而多一次呼叫又會漏（0803 標籤字串比較實錯漏 50 則）。`resume` 的「待整併」改成「上次 render 後有變動」，只是參考值，不影響產出。
- ⚠️ **狀態檔＝唯一真相源，render 是單向投影**：狀態檔裡沒有的東西，下一輪 render 就會從 txt 消失。所以**任何進 txt 的內容都必須先進狀態檔**（側錄、檔頭重大提醒行都在此列），也**不要手改 txt**——下一輪就被覆蓋。品質掃命中要修的是 `raw_entry`，不是 txt。
- **腳本連續失敗 2 次**：把錯誤訊息原文記進回報，**當輪改用 V1 直讀 JSON 的做法繼續**（degraded mode），不得卡住不動。

## 2a. 使用者臨時口令：改庫存（2026-08-04 訂案）

使用者常常會在兩輪之間丟一句話要求改今天的庫存。**這種口令一律是「一句話 → 你自己補完整個流程」，不要反過來要使用者背指令、也不要問路徑。**

**收到口令的固定四步（每一步都不准省）**：

1. **認日期**：沒特別講就是**今天的晚班交接**（晚班起始日的 `{MMDD}-s2-state.json`）。跨夜時段用晚班起始日，不是日曆日。路徑一律 `G:\我的雲端硬碟\Claude共用\自動掃帶系統\{MMDD}-s2-state.json`，**自己組出來，不要問使用者**。
2. **只做指名的那幾則**：⛔ 使用者點名 A、B、C，就只改 A、B、C。**不准自行擴充**（「這幾則看起來也是同一類，順便一起改」是明確禁止的）。判斷不了哪幾則就問，不要猜。
3. **跑對應指令**（下表）。
4. ⚠️ **一定要接著 `s2_render.py` 重新渲染**——狀態檔是唯一真相源、txt 是單向投影，**只改狀態檔不 render 等於沒改**，使用者打開 txt 會看不到。這步最常被漏，漏了就是白做。

| 使用者這樣說 | 你要跑的 |
|---|---|
| 「把 RT2612、RT2993 標**已播**／**灰圈**／**🟤**／**本台做過了**」 | `set-aired --ids RT2612,RT2993` |
| 「RT2612 **取消已播**／拿掉灰圈」 | `set-aired --ids RT2612 --clear` |
| 「把 XX 標**重大**／紅圈」 | `set-alert --add "…"`（檔頭行）＋正文該則加 `🔴`（見 `13`） |
| 「XX **分類錯了**，應該放 OO」 | `set-category --pairs`（分隔符用分號 `;`） |
| 「XX 這則**不要了**／誤收」 | `remove --ids XX`（真的不要才用；「待人工」用 `needs-review add`） |
| 「XX 的**時段標記**錯了」 | `set-mark --ids XX --mark ▲` |

**回報**：實際改了幾則、render 後有沒有反映出來（例如標 🟤 後檔頭圖例是否出現 `🟤=已做過`）。⚠️ **不要**把整份 txt 貼回來。

> ⚠️ **併發**：狀態檔沒有鎖檔機制。若當下正在跑掃帶輪次，**先做完該輪再處理口令**，不要兩邊同時寫（0803 實錯：另一個 session 同時動同一份檔）。若使用者是在開工 prompt 裡一併交代的，就掃完順手做、只 render 一次。

## 2b. 查證的成本原則：把判斷留在上游，不要靠事後清查（2026-08-04 訂案）

**背景**：0804 為了查 BITE 誤判，開了 20+ 次瀏覽器呼叫、撈了數百則清單，只為驗證幾十則素材的一個布林值——**這是反面教材**。同一件事若當初有 `src_text` 落檔，會變成一支本地 python 幾秒跑完、**零瀏覽器呼叫**。

- 🥇 **最省的是根本不需要查證**：`sb_count` 兜底在 `add-batch`／`update-entry` 就擋下，誤判**不會進到狀態檔**。這與 S2 一貫方向一致——判斷往上游搬（NS `footageType`、SNTV `signals`、初稿機械欄位），查證是下游補救，本質上就違背這個方向。
- 🥈 **要查也優先離線查**：`src_text` 落檔後，查證＝本地 grep（見 §2「批次規則」）。**不受「素材捲出清單就查不到」限制**——0804 就有 13 則因此永久失去查證機會。
- 🥉 **必須連線查時搭便車**：pending 清查那趟順手記 `sb_count`（見 §2），不另外開一趟。
- ⛔ **不做「全面回溯清查歷史誤判」**：這是最貴又最沒產出的做法。**歷史誤判只修「還在用的」**——當天交接檔編輯還在看，值得修；昨天以前的沒人回頭看，修了沒有實際效益，資料乾淨本身不是目的。使用者實際指出問題時再針對個案處理即可。
- ⛔ **CCTV／CNS 一律不查證**（理由見 §1 該條）。

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
- **時段標記由 render 依 `first_seen_checkpoint` 自動補**（2026-08-04 固定排程定案邊界）：23:00 前＝`△`、23:00–07:00＝`▲`、07:00–09:00＝`■`、09:00–14:00＝`◆`。16:00～23:00 五輪皆晚班（23:00 是下班前最後一輪）。固定排程表與理由見 `13`「隔夜續掃」節。**補掃輪**（例如 09:10 撈回稍早漏掉的素材）checkpoint 判不準，用 `s2_state.py set-mark` 逐則寫死。
- `raw_entry` **零加工輸出**；側錄照 `14-S2b` 兩行式原樣帶出（不壓縮、不加 `▎`、TC 冒號格式保留）。
- **YouTube 兩行式（§4c）的網址行照樣帶時段標記**，但標記與網址之間**一定要有半形空格**——`△https://…` 會黏成一串、網址點不開（2026-08-03 使用者訂正）。render 的 prefix 固定以一個半形空格收尾，並對首行 lstrip，不會出現雙空格或漏空格。⚠️ 存進狀態檔時**小分題不要塞進 `raw_entry` 第一行**——那是 `category.小分題` 的位子，`raw_entry` 只放「網址行＋備註行」兩行（0802 有 8 則存成三行，render 會把小分題當內容輸出）。
- 寫檔走 tmp+rename（原子），寫完在狀態檔記 `last_render_ts`／`last_render_sha`（`--no-touch-state` 可略）。分類不在 16 格樣板內的會附在檔尾並在 stderr 警告——看到就去修 `set-category`。
- 💾 **輕量備份（2026-08-03 加）**：覆蓋前把現行 txt 另存 `{MMDD}晚班交接.txt.prev.txt`（同資料夾，只留最近一版，不無限累積）。這不是 diff3 復活——不比對、不裁決，純粹「render 本身出 bug 吐出壞 txt 時有東西可以救」。要回復上一版就把 `.prev.txt` 內容複製回正式檔名，不必跑腳本。
- ⛔ **手改偵測（2026-08-03 加）**：覆蓋前比對現行 txt 的 sha 與 `last_render_sha`，對不上就**拒絕覆蓋並 exit 3**。這是防「手改 txt／側錄只貼 txt 沒 add-side」被無聲洗掉——看到這個錯誤，先把 txt 上那些內容寫回狀態檔，確認可丟棄才加 `--force`。
- 📊 **每輪必看的對帳三行**：render 完會印「素材 N 則（±X）／側錄 M 段（±X）／YouTube K 支（±X）」，並點名「現行 txt 有、本次 render 沒有」的代碼。**出現點名就是漏了 `add-side`／`update-entry`**，不要當成正常。回報時要把這三行貼上來。
- ✅ render 完會**自動跑一次 `check`**（`--no-check` 可略），不必另外呼叫。
- ✅ render 完也會**自動跑一次 `s2_topic_dedupe.py`**（`--no-topic-check` 可略）：偵測「同一個小分題名稱同時出現在不同大分類」——這是真實案例訂正出來的機制（見下方獨立段落），純提示不改 state。
- ⚠️ **重大提醒行（`🔴 重大：…`）**：本輪掃到重大素材時，用 **`s2_state.py set-alert`** 存進狀態檔（render 每輪從那裡取；`stats --alert` 只剩不走 render 的舊路徑用）（最多 3 則），判準與撤除時機見 V1 `13`「重大提醒行」。**不給 `--alert` 時 `stats` 會自動沿用檔內既有的重大行**，所以例行重算檔頭不會把它洗掉；要撤才傳 `--clear-alerts`。`check` 會抓「代碼正文找不到／沒寫代碼／超過 3 行／不在檔頭」。
- **腳本失敗行為**：連續失敗 2 次 → 品質掃記為「未執行（腳本錯誤）」寫進回報，**禁止 agent 自行逐行手掃替代**。

## 3a. 主題重複偵測：`s2_topic_dedupe.py`（render 前置檢查，2026-08-03 上線）

**緣起（真實案例）**：0803 晚班交接裡，同一起莫斯科餐廳爆炸被拆成兩則不同來源（`RT1615`／`IN-14MO`），一則歸在 `烏俄`、一則卻被歸進軟性花絮桶 `話題`，使用者人工發現才訂正。人工每天肉眼抓這種錯誤是持續性成本，需要機械輔助——但**不是靠手動維護關鍵字表**（新聞主題每天在變，維護者一停更就開始腐爛），也**不是每輪讓 AI 重新判斷全部分類**（成本高、且同一則今天判 A 明天判 B 會抖動）。

**做法＝拿「今天已經建出來的小分題名稱」自己當比對基準，零外部維護**：

```
python scripts/s2_topic_dedupe.py --file "G:\...\0803-s2-state.json"
# --yesterday-file 省略時自動用 MMDD-1 天推算同目錄檔名
# （優先找 {MMDD}-s2-state.json，找不到才退回解析 {MMDD}晚班交接.txt）
```

- **【今天內部】**：同一個小分題名稱，若同時出現在**不同大分類**底下 → 命中。只比大分類、不比中主題（中主題名稱本來就允許每天用詞微調，比了會誤報——0803 實測「歐洲野火」／「希臘野火」這種純改名就被誤觸過，已改掉）。
- **【跨天】**：昨天存在的小分題名稱，今天雖然還在用，但今天所有出現的位置跟昨天的大分類**完全不重疊** → 命中，抓的是「跨天延續故事被拆到新大分類」，解決「今天剛開始、state 還是空的，第一則進來時沒東西可比對」的冷啟動問題。**只回看前一天這一份，不做多天累積**，避免跟手動維護的關鍵字表一樣越滾越大。
- **只提示，不寫 state**：命中後印出建議，人工確認後用 `s2_state.py set-category` 手動改，改完重跑 `s2_render.py` 生效——跟現有品質掃 `check` 同一套「機器抓異常、人工拍板」的模式。
- ⚠️ **曾試過但放棄的做法**：「不同小分題名稱、但內文用 bigram 模糊比對」——0803 回溯測試對 93 則實際素材跑出 24 項命中，多數是「同主題不同子事件」的假警報（例如「希臘野火／滅火」跟「希臘野火／疏散」被誤判成該合併），雜訊蓋過訊號，人工排除假警報的成本比它省下來的還高。**不要重新加回模糊比對**，只做「同名精確比對」這一級。

## 4. SNTV 列表級收錄（機械白名單）

**為什麼體育可以不開詳情（2026-08-02 使用者確認的理由）**：體育新聞的畫面**必然是比賽或訪問**，開詳情看 shotlist 得到的資訊，跟從標題推出來的幾乎一樣——這是「跳過詳情不會漏掉判斷素材價值所需資訊」的少數類別。其他分類不成立（同樣是社會案件，畫面可能是空景、可能是關鍵監視器，差很多），所以白名單**只給體育、且只認機械可判的 `AP5`**。

- **僅限代碼 `AP5` 開頭**（SNTV 體育，判定規則同 V1）：直接以列表可見資訊（標題＋時長＋Source）寫簡版三段式，**不開詳情頁**。備註照標 `(SNTV)`，摘要一句話。
- 🎯 **結尾標記看 `editorialrole`，不再寫死「無BITE」（2026-08-04 訂正，推翻原本「結尾一律 `無BITE。`」）**：§1a API 清單的 `slimList` 本來就帶 `role` 欄位（免開詳情就有），照三站統一判準——**`role` 含 `SOT`（`VOSOT`／`SOT`）→ 標 `(BITE)`**，BITE 段從清單 `cap`（caption 一句話摘要）能寫多少寫多少，寫不出引言原文就寫講者＋內容概述；`role` 是 `VO` 等無聲形式才標 `無BITE。`。**舊規則寫死「一律無BITE」造成的實害（0803–0804）**：`AP5466752` 摘要都寫出「稱『絕佳機會』」了、畫面段寫「受訪」，結尾卻標無BITE——摘要裡有引言、結尾說沒有，自相矛盾，編輯無所適從。實務上 agent 也早就沒照舊規則做（0803 有 7 則 SNTV 標了 BITE），這次是把規則跟上實務並給出機械判準。
- ⚠️ **`畫面：` 要寫「依標題可推的實際畫面」，絕不可寫操作註記（2026-08-02 實錯訂正）**：
  - ❌ `▎畫面：(列表級,未開詳情)。`／`▎畫面：(未開詳情)資料畫面。`——這是**給 agent 自己看的註記**，違反 V1「操作備註禁止寫進素材行」，編輯看了完全無用。
  - ✅ 依項目寫**必然會有的畫面**：`▎畫面：比賽精華、遠射進球與重播。`／`▎畫面：決賽對打精華、賽末點與捧盃。`／`▎畫面：Skubal投球資料畫面。`
  - 真的推不出來就**只寫最低限度一句**（`▎畫面：比賽精華。`），不要用括號註記填空。
  - `s2_validate.py` 已加通式偵測：素材行任何括號內含「列表級／未開詳情／待補／待確認／待人工／TODO」一律命中。
- 其餘**一律照常開詳情**——不做任何語意判斷的「低價值分類」，防低階 agent 誤殺大新聞。
- 使用者點名要開稿的 SNTV 素材，回站補完整三段式。
- ⚠️ **SNTV 同主題重複只收一則**（2026-08-03，判準與例外見 `13`「SNTV 例外」節，含直橫式與內容完全相同兩種情形）：掃到清單裡同一事件重複收錄時，`add-batch` **只放留下的那一則**，其餘在列表判讀階段就跳過，不進 `batch.json`。

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
   ⚠️ **緊接著跑 `scratch-dir --mmdd {晚班起始日MMDD}`**（2026-08-03 深夜訂案），取得（並自動建立）本輪暫存檔資料夾路徑——本輪所有中間檔（`_ap_*`／`_rt_*`／`{MMDD}-batch-*.json` 等）都寫進這個路徑，**不要**直接寫在 `自動掃帶系統/` 這層。日期用晚班起始日，不是實際掃帶當下的日曆日（跟「檔名不換日」同邏輯）。正式庫存檔（`{MMDD}-s2-state.json`／`{MMDD}晚班交接.txt`）不受影響，維持原位不動。指令：`python scripts/s2_state.py scratch-dir --mmdd 0804`（印出路徑，資料夾不存在就自動建）。
2. 🎫 **兩輪之間顧好 NS 保活（58 分鐘門票）**：NS 登入態是 1 小時滑動時效、過期只能人工重登（機制與證據見 §1a-3「NS 登入態」框）。**掃帶 agent 自己在等待期做**——距上次接觸 NS 接近 58 分鐘就 `browser_navigate` 開一次 `newsource.ns.cnn.com/landing`、確認 `isAuthenticated`，然後照常收工關瀏覽器。⛔ **不可另開獨立 agent／排程做這件事**，Playwright 只有一個 persistent profile，會跟掃帶互鎖（0803 空窗八小時的坑）。下一輪馬上要開工就不必多跑（開工本身就會續期）。
3. **RT 卡住跳站**：連續 2 次 Next 沒反應／頁面沒變 → 記下目前 Edit No.（`needs-review add`），跳去掃 AP／CNN，回報 RT 中斷點。不准死磕（V1 已知 SPA 卡快取雷）。
4. **半夜禁問**：無人值守時段遇到需使用者確認的事項（可疑素材、分類拿不準、腳本壞掉）→ `needs-review add` 記錄＋寫進交接檔備註，**繼續往下跑**。不得 `AskUserQuestion` 等回應、不得停住。⚠️ **NS 登入過期是此原則的典型適用場景**：無人值守時段發現 NS 卡登入頁，記進 `needs-review` 並跳過 NS，不要停住等使用者。
5. **fallback 全部單向**：階梯只往下走（選擇器→整頁→截圖），不回頭重試上一步。
6. ⚠️ **RT 連掃＝單分頁 Next 鏈＋「換頁後必須刷新再讀」（2026-08-02 三輪實測定案，取代先前雙分頁法）**

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
