# 找AP照片

當使用者給一段自然語言描述（例如「找AP照片 川普伊朗相關」），而非精確關鍵字或編號，要求下載「最新、最符合新聞」的若干張照片時，使用本規則。這是 [`搜尋外電素材(AP)`](01-search-workflow.md) 的照片版，同樣在 AP Newsroom 操作。

**2026-08-10 起改走 API 流程**（可行性調查與實測見 [`../common/plans/2026-08-10-AP照片-API抓圖可行性計畫.md`](../common/plans/2026-08-10-AP照片-API抓圖可行性計畫.md) 附錄 A–C）。核心改變：**不再靠讀 caption 文字挑片，改成免費裸抓 preview 圖親眼看過再挑**，下載前用免費的 `check` 端點預先確認授權，只有真的選中的張數才計量。

**Rollback：** 改走 API 前的點擊流舊版見 [`../_archive/ap/02-photo-search.pre-api-2026-08-10.md`](../_archive/ap/02-photo-search.pre-api-2026-08-10.md)。

瀏覽器操作（`navigate` 續期、下載卡住重試階梯等）套用 [`../common/08-execution-efficiency.md`](../common/08-execution-efficiency.md)，包含**「⛔ 不得用會消耗額度的操作做測試」鐵則**——`check` 免費可以隨便用來探路，但 `tick` 是真的計量，不得用來測試流程。

## 觸發格式

使用者給的是一段描述，不是精確關鍵字。需要自己判斷／生成適合的英文搜尋關鍵字（例如「川普伊朗」→「Trump Iran」），然後挑「最新、最符合新聞」的前 N 張下載（N 由使用者指定；沒指定就抓 3 張當預設，或詢問使用者）。**關鍵字要簡短，不要一次疊多個限定詞**：多字精確片語常直接回 0 結果，換成 1–2 個字的寬鬆關鍵字才查得到；預設先試短關鍵字，0 結果才逐步拆解/簡化。

## 流程

### ⓪ Token 續期（每輪開工前）

`browser_navigate` 開一次任一 AP 頁面（例如 `https://newsroom.ap.org/home`）。**這不是可省的步驟**——AP 有短命 API access token，閒置約 17 分鐘會 403 `"token expired"`（不是登出，`session_user` cookie 仍有效）。中途若收到 403，`navigate` 重載一次後重試一輪；**連續兩輪重載後仍 403，才是真的登出**，這時停下來請使用者手動登入，不要自己輸入帳密。

### ① 搜尋（`browser_evaluate`，同源 fetch，`credentials:'include'`）

```js
POST https://api.newsroom.ap.org/v1/nrsearch/search
```

body **照抄頁面實際發出的**，只改 `Query`／`PageSize`：

```json
{"SearchType":"keyword","Date":"Anytime","IsSavedSearch":false,"IsSharedSearch":false,
 "PageNumber":1,"PageSize":10,"persons":[],"Sort":["arrivaldatetime:desc"],"ShareToken":"",
 "digitizationType":null,"language":"","Query":"{關鍵字}","MediaTypes":["photo"],
 "SemanticSearch":false,"isTopicSearch":false,"TopicId":null,"FootageType":[],"GraphicsType":[],
 "IgnoreSpellCheck":false,"ProductGroup":"","query_from_date":null,"itemId":null,
 "isSemanticItemIdSearch":false,"Semantic":null,"MyPlanSearch":false}
```

- **與影片端點（`/search/topic`）不同支，規則也不同**：`PageSize` 這裡可以自由調（本端點 `Sort` 明寫在 body 裡，排序不受影響），但 `PageNumber` 一樣不可靠——**只用第 1 頁**，不要翻頁。
- 回應 `{Query, TotalRows, TotalPages, Page, PageSize, Items:[{_source,…}]}`。抽取白名單：

```js
const clean = s => (s||'').replace(/<[^>]+>/g,'').trim();
const slimPhoto = (s) => ({
  id:    'AP' + s.friendlykey,     // ⭐ 照片的編號是 friendlykey，不是 editorialid（那是影片欄位）
  itemid: s.itemid,                //   32 碼 hex，preview／check／tick 都要用
  title:  s.title,
  cap:    clean(s.caption && s.caption.nitf),
  photog: s.photographer && s.photographer.name,
  ts:     s.arrivaldatetime,
  type:   s.compositiontype,       // 白名單只認 'StandardPrintPhoto'，見下方 PHOTO GALLERY 一節
  preview:'https://mapi.associatedpress.com/v2/items/' + s.itemid + '/preview/AP' + s.friendlykey + '.jpg?s=540x360'
});
```

`renditions`（含 Full／Preview／Thumbnail 尺寸資訊）**要保留**，不是雜訊——這點跟影片白名單相反，是判斷畫質與組 URL 的依據；`binarypath` 是 `"None"`，沒有現成下載 URL，一定要自組。

### ② Preview 判讀（免認證、免計量，這是新流程的核心價值）

```
https://mapi.associatedpress.com/v2/items/{itemid}/preview/AP{friendlykey}.jpg?s=540x360
```

裸抓即可（不需要 cookie／Referer／簽章參數），本機 `curl`／`Invoke-WebRequest` 批次抓下候選張數，再逐張 `Read` 目視。**這一步不准跳過，也不准只讀 caption 就挑片**——caption 文字可能跟畫面對不上（實例：caption 寫某人「在機上」，畫面裡實際沒有那個人），純文字也無法辨識「同一事件的不同幀是否構圖相同」（實測：同一場火災的 5 筆結果 caption 逐字相同，只有秒差，不看圖完全無法判斷是否視覺重複）。**「三張要挑不同人物或不同場景」這條，就是靠這一步判斷。**

preview 有「Distributed by The Associated Press」浮水印，只能拿來判讀，不是成品。需要看細節（例如分不清是不是同一個人）才把 `s=` 調到 `1024x1024`。

### ③ `check`（免費，可批次，下載前置查詢）

```js
POST https://api.newsroom.ap.org/v1/downloadnr/check
body: {"ItemIds":["{itemid}", ...], "IsClip":false, "IsNonSalable":false}
```

對選中的候選（不必侷限 3 張，多留幾個備援一起問）一次查詢，回傳每張的 `Term`：

```json
{"Term":{"DownloadActionTypeText":"WithinAge_Download","IsSuccess":true,"ErrorMessage":null, ...}}
```

**這支就是「先測試帳號能否下載」的正解**——不必真的下載一張試探，`check` 免費、`IsSuccess`／`DownloadActionTypeText` 直接給答案。已知值：`WithinAge_Download`＝可下載；`Duplicate_Download`＝本帳號已下載過。**白名單寫法**：`IsSuccess !== true` 或 `DownloadActionTypeText` 不在已知可下載清單，一律當不可下載，不要去猜其他字串。

**⚠️ `MeterExpired_Shutdown` 有兩種不同情境，判準要分清楚（2026-08-10 Phase 1 pilot 實測發現）**：
- **同批 `check` 只有部分 `ItemId` 回這個值，其他正常** → 通常是**該張的供稿來源不在本帳號訂閱範圍**（實測案例：某 brigade press service 供稿的照片全部中招，同批其他來源正常），**換候選即可，不必停**。
- **同批（或近乎全部）都回這個值** → 才是真的帳號額度／授權到期，**立即停止，不要換關鍵字或重試，直接回報使用者是帳號授權問題**。

「content older than what you are allowed to download under your subscription」這類措辭對應的正是 `WithinAge_Download` 的反面，換一張較新日期的候選即可，不算授權問題。

### ④ `tick`（🔴 唯一計量點）

```js
POST https://api.newsroom.ap.org/v1/downloadnr/tick
body: {"Ticks":[{"ItemId":"{itemid}","MediaType":"photo","Role":"Main",
                 "Title":"{title}","ContentId":"{check回應中Renditions[Rel=Main].ContentId}",
                 "StoryNumber":null,"ContentRenditionId":"{同上.ContentRenditionId}"}, ...],
      "StoryItemID":null}
```

`ContentId`／`ContentRenditionId` **一律取自 `check` 回應**，不要硬編（全解析度通常是 `ContentRenditionId:2`，但以 `check` 實際回傳為準）。`Ticks` 是陣列，選中的張數可以一次送。回傳 `DownloadRecorded:true`／`ClientMediaUrl`（CloudFront 簽章 URL，有效期約 30 分鐘）／`DownloadFileName`／`IsDuplicate`／`OverageAlert`（true 要當警訊回報）。

### ⑤ 落地（同一個 `evaluate` 裡完成，簽章 URL 不離開瀏覽器）

```js
const resp = await fetch(ClientMediaUrl);
const blob = await resp.blob();
const a = document.createElement('a');
a.href = URL.createObjectURL(blob);
a.download = "{檔名}";
document.body.appendChild(a); a.click(); a.remove();
```

- **`tick` 與取檔必須寫在同一個 `page.evaluate()` 裡**，`ClientMediaUrl` 全程不離開頁面 JS、**也不准為了除錯把它 `return` 到 agent 層**（一次性付費資產取用權，比照 token 不外流的精神；Phase 1 pilot 曾為除錯短暫回傳過，事後確認無實質風險，但這是不該重犯的偏差）。
- **不可用 `<a href={簽章URL} download=…>` 直接指過去**——`download` 屬性對跨網域 URL 會被忽略，中文檔名會失效，一定要先轉成同源 blob URL。
- 中文全形檔名（含 `（）`／`／`）皆可正確落地，成品**無浮水印**。
- 下載後用 PowerShell（不是 Bash `mv`，中文檔名在 Git Bash 常編碼錯誤）把檔案從瀏覽器落地資料夾搬到目的地。

### 驗證計量消耗（多張一次 `tick` 時建議做，非每次必要）

`POST /v1/downloadnr/orderhistorymerged`（AP Newsroom「Downloads」頁用的端點，body 抄自實際請求，`fromDate`/`toDate` 抓當天即可）回傳 `TotalRows`，`tick` 前後各查一次，差值應等於本輪張數。這是帳號端獨立紀錄，比 `tick` 自己回報的 `DownloadRecorded:true` 更可信，額外呼叫成本很低，批次下載或需要跟使用者交代計量時可以做。

## Fallback 階梯（固定順序，不准跳步、不准重試同一步）

1. API 搜尋 → preview 判讀 → `check` → `tick`
2. preview 取不到 → 退回「用 caption 文字判讀」＋照樣走 `check`／`tick`（挑片品質下降，要在回報裡講）
3. 搜尋或 `check` 整支失敗 → 完全退回本文件 rollback 連結的舊版點擊流
4. `check` 回不可下載 → **換候選，不重試同一張**
5. 疑似額度／授權到期（見上方 `MeterExpired_Shutdown` 判準）→ **立刻停，不進下一階，回報使用者**

## 下載結果

預設落地檔名為 `AP{素材ID}.jpg`（取自 `tick` 回應的 `DownloadFileName`）。若呼叫來源要求自訂檔名（例如 [`自動寫稿(SOT)`](../common/06-auto-script-sot.md) §10 的圖說檔名），落地時直接用該檔名，不必先存 `AP{ID}.jpg` 再改名。

## 搜到 PHOTO GALLERY 標題卡時

`compositiontype` 白名單只認 `'StandardPrintPhoto'`；其他值（研判包含圖輯封面卡，尚未取得實際樣本）一律當可疑、記進 needs_review，不要當成可用照片。若確實搜到圖輯封面卡，改用該圖輯標題全文重搜。

## 限制訊息（Special Instructions／⚠️）

目前尚未在 API 欄位裡定位到對應限制訊息的欄位（150 筆樣本掃描皆為 `newscontent`，無帶 ⚠️ 樣本可驗）。**沿用舊版判斷**：需要限制內容時才呼叫 `POST /v1/nrsearch/search/item/details`（body 加 `mediaType:"photo"`）查 `copyrightnotice` 等欄位，或退回瀏覽器詳情頁 `/detail/{slug}/{id}/photo` 看橘色 Special Instructions 提示框；只摘要限制文字，不貼整頁 metadata。

## 挑片原則

同一則新聞事件常有多張不同角度/構圖的照片，只要主題、時效都符合使用者要求，可以視為不同的候選照片分別下載，不必侷限只選視覺完全不同的題材——但**視覺是否真的不同，靠②的 preview 判讀確認，不要只憑 caption 文字或素材 ID 相近就假設不同**。

對話回報：最終檔名 + 一句圖說 + 有無限制；不貼完整 Photo Metadata 全文。
