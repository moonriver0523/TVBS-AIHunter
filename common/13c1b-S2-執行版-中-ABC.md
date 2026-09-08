# 13c1b　S2 定時掃帶 V8（執行版）— 中：ABC

> **V8 五層合一（2026-09-07）**：來源＝13h V7-2～V7-5（ABC 清單直查／整併路徑／素材行分類檔頭／對帳與收工）。單層無疊合。
> 掃描順序與輪次表已併入 `13c`（上）；V7-0（取代宣告）、V7-6（上線前檢查表）已存查於 `13c-V8-已取代條文.md`，非必讀。
> 2026-09-07 裁決①：ENEX／ABC 直接拆成 `13c1`／`13c1b` 兩檔（不等超字元才拆）。

---
<!--BODY-->
## V7-2. ABC 清單直查（沿用 `18 §10`／`§5`，本節已抄關鍵部分，不必整份讀 `18`）

### 端點與取值

| 項目 | 內容 |
|---|---|
| 清單 | `GET /Delivery/NewsSearch?{query}`（同源 cookie ＋ **CSRF token**），加 `getCSV=true` 回 `text/csv` |
| CSV 欄位 | `DeliveryAvailableDateTime, News Story, Slug, Length, DestinationName, DeliveryStatus, DeliveryCompleteDateTime` |
| 文稿 | `GET /adbridge/news/Delivery/Detail/{detailId}?includeCategories=True`（HTML，約 39KB／則） |
| 時間窗 | `deliveryDateStart`／`deliveryDateEnd` 只吃 **`M/D/YYYY`**，**沒有時分** → 撈整天再前端過濾 |
| 認證 | 同源 cookie `ss-tok`（HttpOnly）。⛔ 全站沒有 JSON API，別去找 |
| 呼叫方式 | **讀 token → fetch → parse → 過濾 全部寫在同一個 `page.evaluate()` 內**（`18 §1` 安全條款） |

### 🔴 跨日窗要給兩個日期

`22:00`→`01:00`／`04:30` 這種窗**跨兩天**。`dateStart` ＝窗起點那天、`dateEnd` ＝現在那天。
⛔ 只給一天＝**整段跨夜素材直接漏收**，而且回傳筆數看起來很正常，不會有任何一處會叫。

### 主查詢（照抄，出自 `18 §10`）

```js
// 整段寫在同一個 page.evaluate() 內。sinceMs／untilMs 是台北時間的 epoch ms。
async function fetchAbcWindowRows(dateStart, dateEnd, sinceMs, untilMs) {
  const tok = document.querySelector('input[name=__RequestVerificationToken]').value;
  const qs = new URLSearchParams({
    deliveryDateStart: dateStart, deliveryDateEnd: dateEnd,   // 'M/D/YYYY'，跨夜要給兩天
    pageSize: '1000', page: '1', getCSV: 'true',
  });
  const res = await fetch('/Delivery/NewsSearch?' + qs.toString(), {
    credentials: 'include', headers: { '__RequestVerificationToken': tok },
  });
  const text = await res.text();
  const lines = text.trim().split(/\r?\n/);
  const header = lines.shift().split(',');
  const rows = lines.map((line) => {
    const cols = line.split(',');
    const o = {}; header.forEach((h, i) => (o[h] = cols[i])); return o;
  });
  const parseDt = (s) => {
    const m = String(s || '').match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)$/);
    if (!m) return null;
    let [, mo, d, y, h, mi, se, ap] = m;
    h = parseInt(h, 10);
    if (ap === 'PM' && h !== 12) h += 12;
    if (ap === 'AM' && h === 12) h = 0;
    return new Date(+y, mo - 1, +d, h, +mi, +se).getTime();
  };
  return rows.filter((r) => {
    const t = parseDt(r['DeliveryAvailableDateTime']);
    return t !== null && t >= sinceMs && t <= untilMs;
  });
}
```

- **`DeliveryAvailableDateTime` 直接就是台北時間**（`9/5/2026 12:02:45 AM` 這種寫法），
  ⛔ 不要再換算一次。📌 2026-09-05 實測：daily profile **沒有 `tzOffset` cookie**，
  時間一樣是台北——所以⛔ **不要拿「有沒有那個 cookie」當時區正確與否的判準**。
- 回傳的**陣列長度＝窗內真實則數**，直接餵 V7-5 的清單對帳。
- **`Length` 與 `Categories` 都是現成欄位**——ABC 這兩格比 ENEX 好，不必再量。

### 🔴 CSV 的實際值域（2026-09-05 daily profile 實測，9/4～9/5 共 140 列）

| 欄位 | 實測 | 要注意的 |
|---|---|---|
| 整體 | 每列**固定 7 欄、全檔無任何 `"` 引號** | 所以 `split(',')` 是安全的；哪天出現引號欄位就會整列錯位，⚠️ 覺得欄位對不上時先看這件事 |
| `Length` | **只有兩種形狀**：`MM:SS`（94 列）與 **`:SS`（46 列，33%）** | 🔴 `:33` ＝只有秒。`s2_platform_extract.py` 已認得兩種並一律正規化成 `MM:SS`（2026-09-05 修）；⛔ 自己寫時長時不要照抄 `:33` 進素材行 |
| `News Story` | **9 碼**（ABC 自家，`090426088`）與 **14 碼**（加盟台轉供，`09042606422425`，當日 14 列） | 代碼一律 `ABC` ＋原值（`s2_validate.py` 收 `ABC\d{6,16}`）。⛔ 不要以為只有 9 碼 |
| `DeliveryStatus` | 例：`Awaiting_Approval` | 與收不收無關，本規則不用它篩 |

⚠️ **這是一天份的樣本**，值域仍可能有沒看過的形狀；`extract` 認不得的 `Length`
會記進 `known_gaps` 而不是亂補，看到就回報。

### `src_text`（站方原文）：CSV 沒有，要自己去 Detail 頁抓

`s2_platform_extract.py` **不代抓 ABC 全文**（`18 §9` 明寫），沒填會記 `known_gaps`、
lint 會擋。而 `src_text` 是 `18 §2` 訂的「事後查證唯一依據」與 `sb_count` 判準，**不能省**。

1. **拿 `detailId`**：CSV 模式**沒有**這個欄位。把同一支 `NewsSearch` **不加 `getCSV`**
   再打一次取 HTML（實測約 426KB），用下面這段把 `Story Number → detailId／slug` 建成對映。
   ✅ **2026-09-05 實測驗證**：140 列 → 137 列同時有兩個欄位、對映出 132 個
   unique Story Number（差額就是「同一支素材投兩次」，正是 V7-3 要去重的那種）。

```js
// 同樣寫在 page.evaluate() 內。html ＝上面那支不加 getCSV 的回應。
const doc = new DOMParser().parseFromString(html, 'text/html');
const map = {};
doc.querySelectorAll('tr').forEach((tr) => {
  const a = tr.querySelector('a[href*="/Delivery/Detail/"]');   // 標題欄的 slug 連結
  const sp = tr.querySelector('span.smallText');                // 縮圖下方的 Story Number
  if (!a || !sp) return;
  const id = (a.getAttribute('href').match(/Detail\/(\d+)/) || [])[1];
  const story = sp.textContent.trim();
  if (id && /^\d{6,16}$/.test(story)) map[story] = { detailId: id, slug: a.textContent.trim() };
});
```

   ⛔ **不要用「Detail 連結附近第一串 9 位數字」這種近似寫法**——實測會抓到
   `detailId` 自己（它也是 9 位數），對映出來全是垃圾而且看起來很正常。
   撈不到就**記 `needs-review` 寫明、該則照收但 `src_text` 留空**，
   ⛔ 不要卡住整輪、⛔ 不要在同一輪重複換寫法硬試。
2. **抓 `Script`**：Detail 頁的 `Script` 欄。🔴 **換行是 `&#10;`，一定要解 HTML 實體**，
   不解會整篇擠成一行（用 `13c §0-1` 的 `decodeEnt` 全套，⛔ 不要只解 5 個常見的，
   ENEX 那邊踩過 `&rsquo;` 殘留）。
3. `Script` **逐字保留**，⛔ 不順稿、不改字（同 `18 §2`）。

### ⛔ 整則排除：三層分類器（`18 §5`，**外電層優先於任何 ABC 正向訊號**）

> **不對稱原則**：把外電誤收成 ABC，**比漏收一則 ABC 更糟**（版權）。有疑慮就排除。

| 層 | 排除／收錄什麼 | 機械判準 |
|---|---|---|
| 0 | ⛔ **體育**（版權，TVBS 不能用） | `Categories` 含 `Sports` |
| 0 | ⛔ **例行娛樂／節目宣傳** | `Categories` 含 `Promos/Tie-Ins`，或 slug 以 `OTRC` 開頭，或 `GMAAhead*`／`GMATomorrow*`／`WKNDWorldNewsPromo*` |
| 1 | ⛔ **外電**（AP／APTN／REUTERS／AFP／CCTV／CGTN／POOL／GETTY／STORYFUL／NIPPON TV／JAPAN POOL…） | 只比對 `LOCATION/STORY` 末括號、`SOURCE:` 值、`VIDEO PROVIDED BY:` 值三處，正則 `^` 錨在**括號值開頭** |
| 2 | ✅ ABC 自製 | slug 含 `PKG`／`PACKAGE`（335 則實測零反例）、末括號是記者名（`… reports`）、`VIDEO PROVIDED BY: ABC*`／`NEWSONE*` |
| 3 | ✅ 附屬台 | 括號值是呼號 `^[WK][A-Z]{2,3}$`（`KABC`／`WGNO`／`WLS`…） |

### 🔴 `Categories` 只有 Detail 頁有，**清單 CSV 沒有這一欄**

第 0 層（體育／例行娛樂）判的是 `Categories`，但**那一欄不在清單 CSV 的七個欄位裡**——
要靠 Detail 頁（`?includeCategories=True`）抓回來。

🔴 **2026-09-05 首輪實錯**：那一輪 15 則 Detail 全部抓回**空的 `cats`**，
第 0 層等於整層沒生效，體育／娛樂全靠 agent 讀 `Script` 自己判——
結果 `ABC090426074`（WNBA 主席退休資料畫面，`COURTESY: WNBA`）被收錄，
而且大分類還標成「體育」。**標了體育卻沒排除，本身就是自相矛盾。**

🔴 **2026-09-05 又錯一次（`0905-0700`）**：那輪 agent 自己發明了
`className`／`id` 含 `categor` 的 selector，11 則全抓回空 `cats`，**而且沒察覺、沒重抓**，
第 0 層再次整層失效（該輪剛好沒體育才沒出事）。同一天的 `0430b`／`0900` 用下面這段就
28/28、13/13 全中——**⛔ 不要自己想 selector，照抄這段**：

```js
// 已實測：0905-0430b 28/28、0905-0900 13/13 都拿到 Categories
const one = async (story, detailId) => {
  const r = await fetch('/Delivery/Detail/' + detailId + '?includeCategories=True',
                        { credentials: 'include' });
  const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
  const scriptEl = doc.querySelector('#script_smry');     // ← 文稿在這，⛔ 不要抓 body.innerText
  const synEl = doc.querySelector('#synopsis_smry');
  let cats = '';
  doc.querySelectorAll('td, th, label, span, div').forEach((el) => {
    if (cats) return;
    const t = (el.textContent || '').trim();
    if (t === 'Categories' || t === 'Categories:') {
      const sib = el.nextElementSibling;
      if (sib) cats = sib.textContent.trim();
    }
  });
  return {
    story, detailId,
    script_html: scriptEl ? scriptEl.innerHTML.slice(0, 6000) : '<NONE>',
    synopsis_html: synEl ? synEl.innerHTML.slice(0, 3000) : '<NONE>',
    // 兩種分隔都出現過：`Politics, Travel, U.S. News,`（逗號）與 `BIG STORIES\nBig Trials`（換行）
    cats: cats.split(/[,\n]/).map((x) => x.trim()).filter(Boolean),
  };
};
```

- 🚨 **自檢：`cats` 全部是空的＝你的 selector 壞了，不是站方沒分類**。
  Detail 頁一定有 Categories 區塊（`?includeCategories=True` 就是為了它）。
  這時**先照上面那段重抓一次**，⛔ 不可直接往下走。
- **重抓後仍全空**，才退而求其次：①改用 `Script` 裡的訊號補判（見下），
  ②並在回報裡寫明「本輪 Categories 抓不到（已重抓 1 次）」，讓人看得見這輪的第 0 層是瞎的。
- **只有個別幾則空**才是真的沒分類，照常往下判即可。
- **`Script` 可用的體育訊號**（任一命中就當體育處理）：
  `STORY:` 開頭或末括號是**聯盟／球隊名**（`WNBA`／`NBA`／`NFL`／`MLB`／`NHL`／
  `ESPN`／`College GameDay`…）、`COURTESY:` 是聯盟名（那同時代表**畫面版權在聯盟**，
  比一般體育更不能用）、slug 含 `GameDay`／`TopPlays`／隊名。
- 📌 **大分類寫「體育」＝這則本來就該排除**。⛔ 不要一邊標體育一邊收錄；
  真的認為該破例，就寫進排除清單註明「人工判斷收錄」並在回報裡點名，讓人看得到。

**三個一定會踩的地雷**（`18 §5`，每一個都實錯過）：

1. `SOURCE` **不可行首錨定**——ABC 是內嵌標注，錨定會漏掉真的寫著 `SOURCE: Reuters` 的。
2. `SOURCE` **也不可完全不錨定**——會抓到 `SOURCE OF POWER IRAN CONTROLS…` 這種普通句子。
   只取 `SOURCE` 後 **60 字元內**、且比對已知供應商清單。
3. 呼號 `\bW[A-Z]{3}\b` **不可對全文比對**——稿件全大寫，會命中 `WITH`／`WHEN`／`KNOW`。

**機械判準管不到的，由你判斷後列進排除清單並註明「人工判斷」**，⛔ 不要靜默放行、也不要靜默排除：

- **該擋沒擋**：`Categories` 沒標 `Sports` **不等於**不是體育（0810 兩筆使用者裁示：
  NFL 名人堂 GMA 包裝、愛國者運動會，都排除）。📌 **看的是「畫面本身是不是體育活動」**，
  不是它被歸在哪一類、不是報導角度。
- **不該擋卻擋了**：`Promos/Tie-Ins` 誤殺 `ABC080926014`（失智症研究），人工翻案收錄。
  ⛔ 不可直接拿 `Entertainment` 整類砍（裡面混著醫療線內容）。
- 🔴 **ABC 自製 PKG 內嵌外電畫面**（如 `IranWarSunPKG`）**不該被排除**——它確實是 ABC 的素材，
  但稿內的 `CONTAINS REUTERS`／`CONTAINS APTN` 授權期限與時間碼
  **必須完整寫進素材行第一個括號**，否則編輯會用到過期或無授權的片段。

### 🔴 登入態怎麼判（⛔ 不要看 `document.cookie`）

`ss-tok` 是 **HttpOnly，頁面 JS 讀不到**；`cmod` 開任何 ABC 頁都會滑動，
**只看它會誤判成「已經續到了」**。判準用這三個訊號（2026-09-05 在 daily profile 的
登出態實測，見下）：

| 訊號 | 登出時實測到的樣子 |
|---|---|
| 網址 | cmspage 會 **302 到 `/cmspage/50162/abclogin?returnUrl=…`**，頁面標題 `abclogin` |
| token input | `document.querySelector('input[name=__RequestVerificationToken]')` **不見了**（實測 `count = 0`），而頁面上**有** `input[type=password]` |
| `NewsSearch` | 🔴 **不是回登入頁 HTML，而是整個 `fetch` 直接 throw `TypeError: Failed to fetch`** |

🔴 **第三條要特別記**：登出時 `/Delivery/NewsSearch` 會 **302 轉去
`identity.adstream.com/auth/realms/AdBridge/…`（Keycloak）**，那是**跨網域**，
瀏覽器以 CORS 擋下（`No 'Access-Control-Allow-Origin' header`），所以你拿不到
`res.status`／`res.headers`，`await fetch(...)` 那一行就直接拋例外。

- ⛔ **不要把這個例外當成「網路壞了」而重試**——它就是「沒登入」。
- ⛔ **也不要**寫成「檢查 `content-type` 是不是 `text/csv`」就以為夠了：
  那段程式碼在登出時**根本走不到**，要用 `try/catch` 包住才看得見這個訊號。

→ 記 `needs-review`（寫明是哪個訊號）＋跳過 ABC，⛔ 不准輸入帳密（§5 半夜禁問）。

📌 **2026-09-05 沙箱實測（daily profile）**：
- **未登入態**：cmspage 直接被導去 `abclogin`；token input 0 個、有密碼欄；
  `NewsSearch?getCSV=true` 的 fetch 拋 `Failed to fetch`（CORS）。
- **登入後同一支查詢**：HTTP 200、`content-type: text/csv; charset=utf-8`、140 列，
  欄位與 `18 §10` 記的七欄完全一致。
⚠️ 這兩次都是在 **daily profile** 做的；掃帶輪用的是 **v4 profile**，
兩者**不共用登入態**，V7-6 的「v4 profile 已登入 ABC」那一項**仍未驗**。

### 回傳被卸載成檔案：照 `13g` 同一套三步，不要重試

ABC 一輪可能上百則，**幾乎一定會被卸載**。⛔ 這不是錯誤、不用重試、不要換寫法：
① 路徑就在訊息裡（⛔ 不要 `find`）；② ⛔ 不要整包 `Read` 進 context——
卸載檔就是 `s2_platform_extract.py --raw` 吃的形狀；③ 把它搬進本輪 scratch dir。
要看內容用 `python scripts/s2_batch_prep.py inspect <檔> --lengths`
（⛔ 不要 `python -c`，D9 會擋；`--site` 不用給）。

### Fallback 階梯（固定順序，不准跳步、不准重試同一步）

1. CSV 清單（上面的主路徑）。
2. 失敗兩次 → 同一支端點**不加 `getCSV`** 取 HTML 清單，從 DOM 撈 `Story Number` 與 Detail 連結。
3. 再失敗 → `needs-review add` 記明「ABC N 則不是站方無素材，是進不去」，
   **跳過 ABC 繼續收工**。⛔ 不要卡住整輪。

---

## V7-3. 整併路徑：走 platform 三件套（同 ENEX，⛔ 不走 `add-batch` 直入）

```
fetchAbcWindowRows() 陣列 → s2_platform_extract.py abc → 候選 JSON
                          → s2_platform_lint.py        → ❌ 就修，不修不准往下
                          → s2_platform_merge.py --apply --in-round → 狀態檔
                          → s2_state.py set-tc
```

🔴 **每一行都自帶 `cd`，⛔ 不要只在第一行 cd**：掃帶輪每個 Bash 呼叫都是新的 shell，
**cwd 是本輪 scratch dir**（`…\自動掃帶系統\{YYYYMMDD}\`），
`cd` 不會延續到下一個指令。0905-0900 實錯：lint 被解析成
`…\20260904\scripts\s2_platform_lint.py` → `[Errno 2] No such file or directory`。

🔴 **`abc_entries_{HHMM}.json` 判完全部則後一次 `Write` 整包，⛔ 不要逐則 `Edit`**：
同 `13c2` 對三站 batch.json 的規定。0908-1700 實錯：28 則逐一 `Edit` append，
單這個檔就吃掉 28 次工具呼叫（同輪 NS 只用 3 次 `Write`、RT 1 次、ENEX 5 次
`Edit` 就寫完）——先在腦內／scratch 把整包 `{id:entry}` 組好，**判完再寫一次**。

```
# ⓪ entries 寫完先驗形狀（<1 秒，不碰網路）——⛔ 不要跳過
cd E:/GitHub/TVBS-AIHunter && python scripts/s2_platform_extract.py check-entries --entries "<scratch>/abc_entries_{HHMM}.json"

# ① 機械封裝成候選檔（順手產成對的 {MMDD}-ABC.txt，18 §2 要的兩份一次到位）
cd E:/GitHub/TVBS-AIHunter && python scripts/s2_platform_extract.py abc \
    --raw   "<scratch>/abc_raw_{HHMM}.json" \
    --entries "<scratch>/abc_entries_{HHMM}.json" \
    --checkpoint {CHECKPOINT} \
    --window-start "YYYY-MM-DD HH:MM" --window-end "YYYY-MM-DD HH:MM" \
    --out "<scratch>/{MMDD}-ABC-state.json"

# ② 交件前 lint（有 ❌ 就停下來修）
cd E:/GitHub/TVBS-AIHunter && python scripts/s2_platform_lint.py "<scratch>/{MMDD}-ABC-state.json"

# ③ 整併進狀態檔（⛔ 一定要 --in-round，否則護欄 100% 誤擋，理由見 13g V5-3）
cd E:/GitHub/TVBS-AIHunter && python scripts/s2_platform_merge.py "<scratch>/{MMDD}-ABC-state.json" \
    --apply --in-round --file "…/{MMDD}-s2-state.json"

# ④ 🔴 set-tc —— merge 不做這步，漏了整批就沒有 T／C
cd E:/GitHub/TVBS-AIHunter && python scripts/s2_state.py --file "…/{MMDD}-s2-state.json" \
    set-tc --pairs "ABC090426021=T1,T2/C1;ABC090426022=T3/C2"

# 清單分頁要合併時（0905-0430 撞過 `invalid choice: 'abc'`，2026-09-05 已修）
cd E:/GitHub/TVBS-AIHunter && python scripts/s2_batch_prep.py concat \
    "<scratch>/abc_raw_{HHMM}a.json" "<scratch>/abc_raw_{HHMM}b.json" \
    --site abc --out "<scratch>/abc_raw_{HHMM}.json"
```

📌 **2026-09-05 三件已修，⛔ 不要再照舊做法繞路**：
① 素材行**行首可以裸寫** `090426151`，extract 會機械補成 `ABC090426151`
（以前會被判「行首代碼與 id 不符」整批退回重寫，那是工具的錯不是你的）；
② 成對的 `{MMDD}-ABC.txt` **由 extract 自動產**，⛔ 不要再手抄一份——
lint 擋下來改完 entries 重跑 extract 時，txt 也會跟著重出（不會留舊的）；
③ `concat --site abc`／`--site enex` 已支援。

### `--entries` 的形狀（同 ENEX，`13g` V5-3；這裡只記 ABC 的差別）

- **鍵**：裸 `Story Number`（`090426021`）或帶前綴（`ABC090426021`）**都認得**
  （2026-09-04 起；在那之前只認裸鍵，寫成帶前綴會**整批無聲進 `dropped`**——
  候選檔空的，而 `extract` 與 `lint` 的離開碼都是 0，沒有任何一處會叫）。
- **`src_text` 必填**（見 V7-2），沒填記 `known_gaps`、lint 擋。
- **時長不必自己寫**：`extract` 會拿 CSV 的 `Length`（`05:00`／`00:05:00` 都認，一律正規化成
  `MM:SS`）自動補成行尾 `▎MM:SS`（2026-09-04 起）；
  你自己已經寫了就以你的為準、這支不覆蓋。
- `category` 物件或 `"大分類/中主題/小分題"` 字串都收；`sb_count` **整數**、⛔ 不要寫 `"1"`；
  `raw_entry` 行首直接是代碼，🔴🟡⭐🔖 可帶在代碼前面，
  ⛔ 時段標記 `△▲◇◆`（舊符號 `■●`）不准帶——render 依收錄時間自己補。
- 排除的只要 `{"skip": "理由"}`，其餘免填。
- ⛔ `--checkpoint` 與每筆的 `first_seen_checkpoint` 一律 `{MMDD}-{HHMM}` 完整格式（A14 實錯）。

### 去重：鍵是 `Story Number`，不是 `detailId`

同一支素材投兩次會有兩個 `detailId`、**同一個 `Story Number`** → **去重**；
同 slug 但不同 `Story Number`（跨日重上）→ **各自收錄**。
⛔ 素材代碼一律 `ABC` ＋ `Story Number`（`MMDDYY` ＋3 碼序號，自帶日期），
**不要用 `/Delivery/Detail/{id}` 網址裡那串投遞紀錄 id**。

---

## V7-4. 素材行、分類、檔頭

沿用既有規則，本檔只指路：

| 項目 | 依據 | 要點 |
|---|---|---|
| 素材代碼 | `18 §3`／`05` | `ABC{Story Number}`，例 `ABC080926021` |
| 素材行寫法 | `13e` 素材行節 ＋ `18 §2`／`§4` | 第一個 `()` ＝來源媒體＋備註（附屬台寫呼號）、第二個 `()` ＝ `(BITE)`、⛔ 不寫 `▎URL：`、行尾 `▎MM:SS` |
| 計不計則數 | `18 §0` | **一則算一則**，計進檔頭「收錄外電共 X 則」（跟三站一樣） |
| 大分類／T/C | `13f:275`／`13f:301` | 走 `add-batch → set-category → set-tc`。⚠️ T（議題）沒有預設、一律照內容判、⛔ 不要自創；ABC **沒有預設 C**（`13f` 明訂 ABC／ENEX 不得自創預設） |
| BITE 判定 | `18 §6`／0810 §五 | ABC 稿**不用 `SOUNDBITE` 這個詞**、也沒有 `footageType`。線索：`SUPERS:`（講者字卡）、`FORMAT:` 含 `SOT`、逐字稿的 `講者名: [00:00:00] …` 形狀。⭐ `ThisWeek` 系列自帶逐字時間碼，可直接寫進 BITE 段 |
| 🔴🟡 重大標記 | prompt 收工第 4 步 | ABC 素材**一樣要逐則過一次**，臺灣相關一律至少 🟡 |

✅ `s2_validate.py` 已認得 `ABC\d{6,16}`，品質掃與檔頭統計不必額外處理。

---

## V7-5. 對帳與收工

### 對帳（ABC 版）

`s2_audit.py` 的三站對帳**不涵蓋 ABC**。用自己那支：

```
python scripts/s2_platform_reconcile.py --file "<候選檔>" --true-count <N> [--apply]
```

`<N>` ＝ `fetchAbcWindowRows(...).length`（V7-2 那支現場查回來的窗內真實則數）。
一致就結束；不一致才 `--apply` 把落差寫進候選檔的 `needs_review`。

### 收工順序

ABC 的 ①②③④ 要排在 **prompt 收工第 5 步（檢視中／小分題）之前**——
ABC 的素材也要一起參與同義分題合併，晚一步就漏掉了。ENEX 與 ABC 誰先都可以。

### 🔴 關瀏覽器前：NS landing **之外再摸一次 ABC cmspage**

V5 只摸 NS；**V7 起兩站都要摸**（ABC 的 `ss-tok` 跟 NS 的 JWT 同量級，都是約 1 小時）：

1. navigate `https://newsource.ns.cnn.com/landing`，確認 `localStorage.newsourceSession` 還在。
2. navigate `https://abcnews.extremereach.com/adbridge/news/cmspage/50162/abcnewsone`，
   **等到頁面自己打出 `/Cms/SearchMedia`**（`/Cms/SearchMedia(?:LoadFirst)?/` 皆可）再關。
   ⚠️ 只開頁面、沒等到那支 XHR ＝**沒有續到期**（`cmod` 一定會滑動，看它會誤判成功）。

⛔ **掃帶輪禁止 spawn `scripts/s2_keepalive.js`**（或 `s2_keepalive.ps1`）：
它會自己開一個 Playwright context 去搶**同一份 v4 profile**，而掃帶輪正握著
`.s2-scan.lock`——保活腳本本來就是撞鎖就放棄的設計，輪次內硬叫它等於自己跟自己搶 profile。
**在同一個 MCP v4 session 裡 navigate 一次就好**（`channel:'chrome'`，profile
`C:\Users\User\.playwright-s2-profile-v4`）。

- 兩站都摸完才算收工。哪一站發現已經登出，照常 `needs-review add` 記錄，不必額外處理。
- **唯一豁免**：本輪已確認該站 401／登出且已記 `needs-review`（token 已失效，摸了無意義）。

### 🔶 已知限制（V7 第一版接受，不要當成 bug 回報）

- 殼層 ntfy 的「窗內未收」摘要**不含 ENEX／ABC**（那段讀的是 `s2_audit.py` 的三站對帳留痕）。
- `_token_metrics.jsonl` 的分桶**不認 `enex`／`abc`**，會落進「其他」桶。遙測歸因會糊掉，
  不影響掃帶本身。
- ABC 的 checkpoint 表（V7-1）是**使用者裁示、不是量測結果**——上線後要累積各輪實際量再回頭校正。

---
<!--ENDBODY-->

<!-- RULES-EOF 13c1b 2026-09-07 — V8 五層合一，讀到這一行才算讀完本檔；沒讀到＝被截斷，必須用 offset 補讀。 -->
