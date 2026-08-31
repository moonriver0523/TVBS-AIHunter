# 13c2　S2 定時掃帶 V3（省 token 執行版）— 下：狀態檔、稽核與收工

> 🔴 **2026-08-24 由 [`13c`](13c-S2-定時掃帶-v3省token.md) 切出（R15）**，
> 內容逐字保留、未改寫。**本檔與上半同為必讀。**
>
> 本檔涵蓋：§1b AP＋RT 清單直開流程（§1a 失敗時的退路）、
> **§2 狀態檔 `s2_state.py` 代管（agent 禁止直接開 JSON）**、
> §2a 臨時口令、**§2a-2 每輪快速稽核 `s2_audit.py`（交班前必跑）**、
> §2b 查證成本原則、§2d 檔頭時間窗、**§3 品質掃／統計／渲染**、
> **§3b 中／小分題檢視 `s2_topic_review.py`（render 前必做，每輪）**、
> §3a 主題重複偵測、§4 SNTV 列表級收錄、§4c YouTube 網址素材、
> §4b 整併分類修正、**§5 防卡設計**、§5c 排程啟動器、**§5a 建檔輪額外動作**、
> §2c 結構化欄位。

---
<!--BODY-->
## 1b. AP＋RT 清單直開流程（§1a 失敗時的第一層退路）

清單一次 JS 撈完 → diff → 新素材直接用網址開分頁逐頁收錄；modal／Next 鏈全程不用。
⚠️ 只涵蓋 AP／RT；**NS 沒有 §1b**——NS 的 §1a 失敗兩次直接退 §5 UI 舊做法。

**AP**：
1. `/home` Latest 清單一次 JS 撈每張卡的 GUID＋標題（GUID 在縮圖網址 `mapi.associatedpress.com/v2/items/{32碼hex}` 裡；卡片沒有 href）。
2. diff 後直開 `https://newsroom.ap.org/detail/x/{GUID}/video`（slug 隨便填）。
3. **開頁後等 8–9 秒再讀**；沒抓到 SHOTLIST／STORYLINE 關鍵字就再等 5 秒重讀一次，兩次都空才算失敗。讀取前核對頁面 GUID／標題與預期一致。

**RT**：
1. `all?media-types=vid` 大列表一次 JS 撈 `a[href*="detail?id="]` 的 href＋Edit No＋版次＋slug＋標題＋時長＋RAW/SCRIPT 狀態（「EARLY ACCESS SCRIPT」清單層直接可判）。
2. 新素材**照抄撈到的 href 直開**（內部碼勿自行拼湊，版次尾碼會變）；開後等 8–9 秒＋重讀規則同 AP，核對 Edit No 才讀。
3. 🔴 **清單是內層容器的虛擬捲動，首屏只渲染約 10 則**——不捲只看得到 1/6（0805 實錯：agent 只「找到」2 則、實際窗內 36 則未收）。`window.scrollBy` 無效，要捲 `.homepage` 那個 `overflow-y:auto` 的內層 div，**邊捲邊累積**（捲過去的會從 DOM 消失）：

   ```js
   const box = [...document.querySelectorAll('div')].find(el =>
     (el.className||'').toString().includes('homepage') &&
     el.scrollHeight > el.clientHeight + 200);
   const seen = new Map();
   const grab = () => document.querySelectorAll('a[href*="/detail?id="]').forEach(a => {
     const t = (a.innerText||'').replace(/\s+/g,' ').trim();
     const m = t.match(/Edit No:\s*(\d{4})/);
     if (!m || seen.has(m[1])) return;
     const dm = t.match(/^(\d{2}\/\d{2}\/\d{4} \d{2}:\d{2})/);   // 上站時間，判窗內外用
     let g=''; try { g = decodeURIComponent((a.href.match(/id=([^&]+)/)||[])[1]||''); } catch(e){}
     seen.set(m[1], { code:'RT'+m[1], at: dm?dm[1]:'', guid:g, text:t.slice(0,110) });
   });
   grab();
   let stall = 0;                       // 連續數次沒有新增就停，不要死捲
   for (let i = 0; i < 60 && stall < 6; i++) {
     box.scrollTop += 900;
     await new Promise(r => setTimeout(r, 350));
     const n = seen.size; grab();
     stall = (seen.size === n) ? stall + 1 : 0;
   }
   ```

   一次約 60 則、涵蓋前 5 個多小時，正常輪次夠用。
   🔴 **兩種情況必須按 Load More 補撈**：①窗較長的輪次（建檔輪、04:30／07:00）②補掃失守窗。
   **判準機械**：撈到的清單裡**最舊一則的上站時間仍晚於本輪窗起點** → 按 Load More 繼續，直到最舊一則早於窗起點。（與 `13` 的 LOAD MORE 禁則不衝突：那條禁的是拿它當主掃法。）
4. **Load More 三規則**：⑴換頁替換不是累加——**先撈完目前這頁才准按**，按完再撈一次做聯集去重⑵只認真實點擊，合成 JS click 無效⑶「深夜首屏 10 則就夠」是錯的（虛擬捲動只渲染這麼多，不代表窗內只有 10 則）。
   🔴 **⑵是死鎖警告不是提醒**（0827-1000：`browser_evaluate` 裡 `element.click()`＋遞迴重試「按到 8 次才 resolve」，合成 click 點了等於沒點、DOM 不變，卡近 30 分鐘、整輪拖到 65 分）。**點 Load More 一律用 `mcp__browser__browser_click`**（真實 CDP 事件），⛔ 不准在 `browser_evaluate` 裡用 `element.click()`／`dispatchEvent(new MouseEvent(…))` 代替——沒有例外。**任何「按了再撈、撈不到就重按」的迴圈都要有 stall 出場條件**（連續 N 次點擊則數沒增加就放棄、記 `needs-review`），⛔ 不准寫成「達到 N 次成功點擊才 resolve」——點擊失敗時永遠數不到 N，Promise 永不 resolve。
5. ✅ **收工前自我檢查**：清單撈到、上站時間在窗內的 Edit No 全列出來跟狀態檔 diff——**窗內有一則沒進庫就不算掃完**，不論原因都要 `needs-review add` 記代碼與原因。⛔ 不可只回報「已找到的都收了」（視野被縮小時那句永遠為真）。
   💾 **diff 用的清單必存當晚暫存資料夾**（`{YYYYMMDD}/_rt_list_{HHMM}.json`，含 code／上站時間／guid）——沒存＝這輪視野沒留證據，站方清單滾動後永遠查不回來；存了就能離線對帳、零瀏覽器呼叫。

**分波**：一次最多開 5–8 個分頁，讀完關掉再開下一波。

**守門（任一觸發＝該站退 §5 舊流程＋`needs-review add`）**：清單撈到 0 筆或明顯少於畫面可見數；直開頁面依等待規則後仍空白或 GUID／Edit No 不符（絕不寫入不符頁面的內容）；同站連續 2 頁觸發。

## 2. 狀態檔：`s2_state.py` 代管（agent 禁止直接開 JSON）

- **檔名＝`{MMDD}-s2-state.json`**（一天一檔），與 `{MMDD}晚班交接.txt` 同資料夾（`G:\我的雲端硬碟\Claude共用\自動掃帶系統\`）。
- schema：頂層 `checkpoint`／`updated_at`／`window_local`／`rt_status`／`ap_status`／`cnn_status`／`notes`／`items`／`alerts`／`special_category`／`last_render_ts`；`items` 是陣列；`category` 是 `{"大分類":…,"中主題":…[,"小分題":…]}` 物件（`set-category --cat "大/中/小"` 自動轉）。頂層欄位用 `set-top`；`alerts` 用 `set-alert`。

```
python scripts/s2_state.py --file "…/{MMDD}-s2-state.json" resume   # 開工必跑：時段、已收、pending、待整併
python scripts/s2_state.py diff --checkpoint 16:00 --ids RT2333,AP4675135,IN-02TU
python scripts/s2_state.py add-batch --entries batch.json  # ⭐ 批次新增（預設路徑）
python scripts/s2_state.py add --id RT2333 --source RT --checkpoint 16:00 --status pending --entry "…"
python scripts/s2_state.py update-entry --id RT2333 --status has_script --entry "改寫後內容"
                                # ⚠️ 標 pending 前先讀 13「有稿判準」；ISO長帶/裸SOT/音軌等
                                #    天生無旁白稿的＝has_script＋備註形態，不是 pending
python scripts/s2_state.py update-entry --batch fix.json    # ⭐ 批次覆寫（改 N 則就用這個）
                                # fix.json＝陣列，每筆 {"id","entry"[,"sb_count","status"]}
                                # ⛔ 不要自己寫 subprocess 迴圈跑 N 次 update-entry
python scripts/s2_state.py pending
python scripts/s2_state.py set-category --pairs "RT2333=社會/休達移民/岸際動態;RT2360=天氣/野火動態/加州"
                                # 🔴 第三段小分題**必填**（13 的三層骨架：素材行掛在小分題下；
                                #    0810 實錯 97 則漏開）。相似素材共用同一小分題，不要一則一個
python scripts/s2_audit.py --mmdd 0805                     # ⭐ 交班前必跑，見 §2a-2
python scripts/s2_state.py list-topics                     # ⭐ 開新中主題前必跑（--subs 連小分題）
python scripts/s2_state.py add-side --txt "…/0803 CNN側錄.txt" --source CNN --checkpoint 22:00 \
       --homes "天氣/華州野火/州長宣布緊急=160106,160151"
                                # 側錄入庫見 14-S2b；--normalize 機械正規化；--dry-run 先驗段數
python scripts/s2_state.py set-alert --set "▲ AP4676262 …"  # 檔頭 🔴 ≤3則；--add 追加/--clear 撤
python scripts/s2_state.py set-aired --ids RT2995           # 🟤 已播；⛔ 只有使用者下令才標
python scripts/s2_state.py set-mark --ids RT2754 --mark ▲   # 補掃輪寫死時段標記
python scripts/s2_state.py get --id RT2333                  # 單則、整包 JSON（查一則的全貌才用）
python scripts/s2_state.py show --ids RT2333,AP4675135 --fields id,cat,entry
                                # ⭐ 批次查、只取要用的欄位（TSV；--json 出 JSON）
                                # 篩選：--cat 烏俄／--mid 某中主題／--checkpoint 0811-2000／--needs-review
                                # 欄位：id,cat,大分類,中主題,小分題,entry,source,status,cp,sb,review,summary,bite,dur
python scripts/s2_state.py needs-review add --id RT2333 --note "疑似UGC，待人工"
python scripts/s2_state.py needs-review list
python scripts/s2_state.py needs-review done --ids RT2333   # 處理完就結案，別讓清單只進不出
```

- 🔴 **⛔ 不准自己寫 python 去讀／改狀態檔**（2026-08-11 立規，實測最大宗的浪費）：
  `python -c "import json; d=json.load(...)"` 這種臨時查詢、以及 `python - << PYEOF`
  跑 subprocess 迴圈批次改，**一律改用 `show`／`update-entry --batch`**。
  - **實測**：0811-2000 那輪 67 次 Bash 裡，**22 次是臨時查詢腳本、12 次是臨時批改腳本**，
    合計佔六成。而每一次工具呼叫都要把整個 context 重讀一遍——**呼叫次數才是成本主因**，
    不是規則檔多長（同輪精簡規則只降 16%，還被呼叫次數上升吃掉）。
  - **為什麼以前會這樣**：不是紀律問題，是**工具箱缺口**——`get` 只吃單一 id 又整包 dump，
    要查 20 則的分類就得叫 20 次，自己寫 python 反而便宜。`show`／`--batch` 補掉這個缺口後，
    正規指令永遠比臨時腳本省，**沒有理由再自己寫**。
  - ⚠️ **臨時腳本還特別容易自傷**：0811-2000 第 14–18 次連續 5 次卡在 `/tmp` 路徑
    （Windows 沒有 `/tmp`，寫失敗→sed 想補救→又失敗→最後才改 heredoc）。
    五次呼叫全部白費，什麼事都沒做成。
  - ⚠️ **這台機器的主控台是 cp950，臨時 python 印中文／emoji 會直接崩潰**
    （`UnicodeEncodeError: 'cp950' codec can't encode`，整段白跑）。
    這裡**不給防護樣板**——2026-08-12 的教訓是：給了樣板等於發許可證。
    當天 17:13 在這裡放了一段 UTF-8 防護樣板，18:00 那輪臨時 python 立刻從
    30 次衝到 **54 次**（樣板本身被抄了 58 次），呼叫總數 177→203、
    成本 54.3M→56.9M。**這條規則是「不要寫」，不是「怎麼寫得安全」。**
    正規腳本（`s2_batch_prep.py`／`s2_token_metrics.py`）開頭已有這段防護，
    走正規指令就不會遇到這個問題。
  - 📌 真的遇到 `show` 查不到的欄位：**回報說缺什麼**，不要繞路自己寫——
    補一個欄位進 `SHOW_FIELDS` 是一次性的，每輪重寫臨時腳本是永久成本。
- 🔴 **⛔ 改狀態檔的子指令，一輪只准呼叫一次**（2026-08-12 立規）：
  `set-category`、`update-entry`、`add-batch` 這三個**寫入**指令，一輪各只跑一次，
  把整輪要改的全部塞進同一次呼叫——`set-category --pairs "a=…;b=…;c=…"`、
  `update-entry --batch fix.json`。⛔ **不准一則一次、不准跑迴圈**。
  - **實測（0812-0730 輪）**：`set-category` 叫了 **9 次**、`update-entry` 叫了 **6 次**，
    全都是單筆。這兩個指令**本來就支援批次**（`--pairs`／`--batch`），工具沒缺口，
    純粹是沒有一條「只准叫一次」的硬規則。15 次應該是 3 次。
  - **立規後複驗（0812-1000 輪）**：`set-category` **9→4** ✅、`add-batch` 3 次（三站各一，
    正常）——但 `update-entry` **6→7** ❌。七次全是**送出之後**才發現標題要改、
    `status` 要改而回頭補的單筆呼叫。上面那句「中途發現分錯就改清單裡那一行」
    只管到「還沒送出」，**送出後才發現**這個情境沒堵到，於是補了 ①b 👇
  - **成本**：實測 **每次工具呼叫 ≈ 0.25M cache_read**，五輪一致
    （106 次/23.1M、117 次/29.5M、94 次/24.6M、119 次/33.0M、117 次/29.9M）。
    多叫 12 次 = 白燒 3M，約單輪的 10%。
    ⚠️ **算 token 一定要先依 `message.id` 去重**：JSONL 每個 content block 一行、
    同一則 message 的 usage 會重複出現，不去重會灌水約 1.8 倍（2026-08-12 實錯）。
  - **做法**：邊分類邊把 `id=大/中/小` 累積成一份清單，**全部看完才送出**。
    中途發現前面分錯了就改清單裡那一行，不要另外再叫一次補正。
  - 📌 讀取類（`show`／`diff`／`get`／`list-topics`）不受這條限制，但一樣優先
    用一次 `show --ids a,b,c` 取代多次 `get`。
- 🔴 **①b 稽核前置：自我檢查做在 `add-batch` 之前，不是之後**（2026-08-12 立規）：
  一站的 `batch.json` 湊齊之後、**送出之前**，把「標題順不順、`status` 對不對、
  分類合不合理、有沒有跟前面重複」一次檢查完，確認了才 `add-batch`。
  - ⚠️ **這條不是叫你別修正**。發現錯**一定要改**——只是改在**還沒送出的草稿**裡，
    那不用多花任何一次工具呼叫。品質永遠優先於省 token，這兩者在這裡不衝突。
  - 真的送出後才發現的錯（例如後面某站的素材讓你回頭發現前面標題不精確），
    **照樣改，但累積起來到本站收尾時一次 `update-entry --batch`**。
    ⛔ 不准發現一則就補一次。
  - **成本**：0812-1000 那七次單筆補正 ≈ 1.75M ≈ 單輪的 5%。
- 📌 **`needs-review` 是「待辦」不是「日誌」**：`add` 對不存在的 id 會建 `script_status="note"` 備註殼（不算素材、不進 render）；**`done --ids` 是唯一結案出口**（備註殼→刪掉；真素材→只脫旗標）；批次全有全無（任一 id 不對就整批報錯）。不結案的話 `resume` 每輪重印舊項目，清單失去警示作用。
- **批次擷取流程**＝收本輪列表 ID → `diff` → 只對新的取文稿（§1a）→ **邊看邊累積 `batch.json`，看完一次 `add-batch`**。⛔ 不要一則一次 `add`（呼叫次數是變慢主因：25 則從 52 次降到 4 次）。
- **批次規則**：`batch.json` 是 JSON 陣列，每筆 `{"id","source","checkpoint","status","entry"}`。撞 id 或格式錯的單筆自動跳過並回報（已存在→改 `update-entry`；格式錯→修後單筆補）。`--pairs` 分隔符用分號 `;`。
- 🎯 **RT／AP 每筆必帶 `sb_count`（AP 另帶 `has_sot`），NS 必帶 `footage_type`**——兜底機制靠它。SNTV 列表級沒全文可不帶，**但開了詳情的那格必帶**（既然開了就有這個數字）。pending 重查時 `update-entry --sb-count N` 帶入。
- 💾 **每筆必帶 `src_text`＝瘦身後的站方原文**（落檔留存，`add-batch` 忽略此欄位）：
  - 用途：離線查證誤判、兜底擋下時直接看原文改、日後規則研究。素材捲出站方清單後**只有這份能回溯**。
  - ⛔ **裡面只准站方原文，不准寫任何自己的判斷或說明**（0808 實錯 RT4131：agent 加的中文說明含 `SOUNDBITE` 字樣，害假 BITE 判準連錯四輪）。要記判斷用 `needs-review add`。
  - ⛔ 存「瘦身後」不是「原始回應」；不准存 token／cookie。
- 🔴 **NS 站 `add-batch` 前必跑 `compare --require src_text` 硬性檢查**（2026-08-21 立規，MASTER R9）：
  NS 整批漏帶 `src_text` 已連續復發四次（0812-2200／65 則、0813-1200／80 則、
  0818-1000／39 則、0821-0730／35 則），每次都要整批回補（Write 一份 `_fix.json`
  重補 src_text＋`update-entry`），單次成本約 4–5 分鐘。事後警告（`add-batch` 印
  ⚠️）驗證過**擋不住**——四次都是警告照印、agent 照樣先送出再回頭補，因為警告
  在送出**之後**才出現。改成送出**之前**擋：
  ```
  python scripts/s2_batch_prep.py compare --raw <NS原始清單/raw檔> --batch ns_batch_{HHMM}.json --site ns --require src_text
  ```
  看到「batch 缺欄位」就地把 `batch.json` 補齊 `src_text` 再送 `add-batch`，
  **不准先送出再回補**。只回「無差異」才准 `add-batch`。⚠️ AP／RT 目前四次都沒
  中招，暫不強制（但 `compare` 本身也適用三站，順手查不吃虧）。
- **整併流程**＝pending 全量重查 → `add-batch`／`update-entry` → `set-category --pairs` → 側錄 `add-side` → `set-alert` → `s2_render.py` 全量渲染。agent 輸出趨近 0，不手寫 txt。
- 🔴 **分類收斂：獨立 agent 出建議，掃帶輪只套用**（跨輪一致性沒有輪內 agent 能看見；23:00 已是最重的一輪不再加擔）：
  - 建議檔：`_待整併/{MMDD}-分類收斂建議.txt`，只認 `MOVE {id}={大}/{中}/{小}` 與 `ORDER {大}={中1};{中2};…` 兩種指令行。交辦範本：[`scripts/s2_reclass_prompt.md`](../scripts/s2_reclass_prompt.md)。
  - 掃帶輪收工前、render 之前套用：`python scripts/s2_apply_reclass.py --file … --suggest … --dry-run`，看過再拿掉 `--dry-run`。建議檔不存在就跳過，⛔ 不要自己生一份；套用階段不再做判斷。id 不存在整份拒絕，不會套一半。
  - ⛔ 不要逐則重讀內文重分類（那是這一步的 8–10 倍成本）。
- ⚠️ **pending 每輪都要主動清查**（不只 23:00）：§1a API 批次重查，稿到就 `update-entry` 覆寫並順手帶 `--sb-count`（同一份回應數一次 SOUNDBITE，零額外成本）。照規則直接處理，不問使用者。pending 為 0 就跳過。
- ⚠️ **狀態檔＝唯一真相源，render 是單向投影**：任何要進 txt 的內容（含側錄、檔頭重大行）必先進狀態檔；⛔ 不手改 txt——下一輪就被覆蓋。品質掃命中修的是 `raw_entry`。
- 🔴 **品質檢查在「寫入當下」就會跑**：`add`／`add-batch`／`update-entry` 寫完立刻印「⚠️ 格式待修 N 項（已入庫，請直接 `update-entry` 改掉）」——**看到當場修，不要留到收工**（那時已忘脈絡）。只警告不擋、不會替你修。（為什麼：品質掃原本只綁 render，輪次外寫入等於側門繞過關卡——0811 實錯 35 則帶著 52 項格式問題上了交接單。側錄／YouTube 兩行式不套此判準。）
  - ⚠️ **「有 ▎BITE： 但缺 (BITE) 第二括號」這一項不要重打整條**（2026-08-18）：
    跑 `python scripts/s2_state.py patch-entry --ids A,B,C --bite` 就好，
    它只插第二括號、其餘一字不動。**只補這一種**——已經有 `(BITE)`、寫著
    「無BITE」、或根本沒有 `▎BITE：` 段，一律拒絕不動（那些是編輯判斷，
    要改請用 `update-entry`）。其餘格式問題仍照舊自己改。
    ⛔ 這條**刻意不做成寫入時自動補**：本節訂的就是「只警告不修」，
    靜默改稿會牴觸它——要改成自動導出屬裁決題（MASTER A12）。
    背景：0818-1600 那輪為了補 `(BITE)`，`_fix_ns_bite.py`＋`_fix_ap.py`
    把 18 條完整 entry 重打了一遍；實測同樣 28 則用 `--bite` 一次還原、
    與原文一字不差。
- **腳本連續失敗 2 次**：錯誤原文記進回報，當輪改 V1 直讀 JSON 繼續（degraded mode），不卡住。

## 2a. 使用者臨時口令：改庫存

一句話口令 → 你自己補完整流程，不要反問路徑、不要要使用者背指令。**固定四步（不准省）**：

1. **認日期**：沒講就是今天的晚班交接（跨夜用晚班起始日）。路徑自己組：`G:\我的雲端硬碟\Claude共用\自動掃帶系統\{MMDD}-s2-state.json`。
2. **只做指名的那幾則**：⛔ 不准自行擴充「順便一起改」。判斷不了哪幾則就問。
3. **跑對應指令**（下表）。
4. ⚠️ **一定接著 `s2_render.py` 重渲染**——只改狀態檔不 render 等於沒改。這步最常被漏。

| 使用者這樣說 | 你要跑的 |
|---|---|
| 「把 XX 標**已播**／灰圈／🟤」 | `set-aired --ids …`（`--clear` 取消） |
| 「XX 標**重大**／紅圈」 | `set-alert --add "…"` ＋ `patch-entry --ids XX --alert red` |
| 「XX 標**次重大**／橘圈」 | `patch-entry --ids XX --alert yellow`（不動 set-alert） |
| 「XX **撤掉**紅圈／橘圈」 | `patch-entry --ids XX --alert none` |
| 「XX **分類錯了**」 | `set-category --pairs`（分號分隔） |
| 「XX **不要了**／誤收」 | `remove --ids XX`（「待人工」用 `needs-review add`） |
| 「XX 的**時段標記**錯了」 | `set-mark --ids XX --mark ▲` |

回報：實際改了幾則、render 有沒有反映。⚠️ 不要貼整份 txt。
⚠️ **併發**：狀態檔沒有鎖。掃帶輪在跑就先做完該輪再處理口令，不要兩邊同時寫。

## 2a-2. 每輪快速稽核：`s2_audit.py`（交班前必跑）

```
python scripts/s2_audit.py --mmdd 0805
```

七項離線檢查（數秒、零瀏覽器）＋第八項清單對帳：

| # | 檢查 | 抓什麼 |
|---|---|---|
| ① | `checkpoint` 格式 | 沒有 4 位數字群 → 時段標記塌成 `△` |
| ② | 時段標記分佈 | 跨夜輪次全是 `△` ＝ 幾乎確定有問題 |
| ③ | BITE 一致性 | 假 BITE、漏標、`src_text`／`sb_count`／`footage_type` 沒帶 |
| ④ | 中主題 | 同格互相包含、跨格同名、放錯大分類 |
| ⑤ | 暫存檔落地 | `_rt_list_{HHMM}.json` 有沒有留 |
| ⑥ | 結構化欄位 | `fields`／`parse_ok`／`pending`／`needs-review` 未結案 |
| ⑦ | 品質掃 | 呼叫 `s2_validate check` |

離開碼 0＝全過；1＝有 🔴（🟡 只提醒）。**當輪 agent**：整併完、render 後、交班前跑一次，🔴 直接處理掉再交班（或 `needs-review add` 記錄）——⛔ **不要只在回報裡講一句**，排程情境沒人看終端機，等於沒發生。本模組的主要設計目的是**換一雙眼睛**：當輪 agent 看不見自己的盲區（0805–0806 一夜漏收 47＋則、每項都是事後才發現，當輪全數回報「正常完成」）。

**Ⓐ 清單對帳（價值最高，別跳過；0805 靠它抓回 47 則漏收）**：

```
python scripts/s2_audit.py --mmdd 0806 --rt-list 20260806/_audit_rt_0700.txt
```

1. agent 撈清單（RT 用內層容器捲動，§1b）
2. **存成檔**：每行 `CODE|MM/DD/YYYY HH:MM` 或 JSON 陣列。⚠️ **一律用 PowerShell／python 寫檔，不要走 browser MCP 的輸出檔功能**——MCP 檔案存取限 workspace roots，寫 `G:\…\自動掃帶系統\` 必回 `File access denied`。📌 不要用 `--allow-unrestricted-file-access` 繞（會連帶解除 `file://` 封鎖）。
3. 重跑本模組帶 `--rt-list`（`--ap-list`／`--ns-list` 同理）。腳本自動分四類：已收／前幾天收過／**窗內未收（🔴 漏收）**／窗外。

- ⚠️ 開瀏覽器前先確認下一輪掃帶還沒開始（profile 互鎖）。搶不到就 `needs-review` 記「沒做、下次補」，不硬等也不無聲跳過。
- 🔴 **對帳結果自動寫進 `_top.reconcile_log[{checkpoint}]`，render 收工時查、缺哪站指名喊**（只警告不擋——無人值守硬擋會卡死整輪）。真做不了就 `needs-review add` 寫明原因。
- 📌 已裁定不收的不重複報：代碼出現在任何 `needs-review` 備註且含「不收／重複／排除／未收／跳過」字樣，之後列「已裁定不收」。

## 2b. 查證的成本原則：判斷留在上游，不靠事後清查

- 🥇 最省是根本不用查：兜底在寫入時就攔（`sb_count`／`footageType`／`signals`／初稿機械欄位）。
- 🥈 要查優先離線查：`src_text` 落檔後查證＝本地 grep，不受「捲出清單就查不到」限制。
- 🥉 必須連線時搭便車：pending 清查那趟順手記 `sb_count`，不另開一趟。
- ⛔ 不做「全面回溯清查歷史誤判」：只修「還在用的」（當天交接檔）；使用者指出時再個案處理。
- ⛔ CCTV／CNS 一律不查證（§1a-1）。

## 2d. 檔頭時間窗：`window_start`

檔頭時間窗＝「這份交接檔開檔至今累計」，不是最後一輪的區間。

- 建檔輪設一次：`set-top window_start "{YYYY-MM-DD} 13:00"`（值見 §5a 第 4 項），**之後每輪不要再動**。
- 終點由 render 自己取頂層 `checkpoint`。
- ⚠️ 不要靠 `--window` 傳（漏傳或格式不合檔頭默默壞掉）；它只當特例覆寫。
- ⚠️ `window_local` 是**單輪**區間、每輪覆蓋，不是檔頭時間窗。

## 3. 品質掃／統計／渲染：`s2_validate.py`＋`s2_render.py`

```
python scripts/s2_validate.py check "G:\...\0802晚班交接.txt"    # 格式異常掃描（行號＋原因）
python scripts/s2_render.py --file "G:\...\{MMDD}-s2-state.json" --out "G:\...\{MMDD}晚班交接.txt"
python scripts/s2_render.py --file "…" --base-date 0802          # 不給 --out ＝ 印預覽
```

- `check` 涵蓋 V1 格式異常表全部可 regex 項目；**LLM 只處理命中清單**，不整份逐行讀。
- render 產出順序：檔頭（🔴 取自 `alerts`）→ 16 格大分類（空格保留）→ `【中主題】` → 小分題（裸行＋`+` 分隔）→ 素材行。走 render 不必再跑 `stats`（檔頭由 render 自生）。
- 時段標記由 render 依 `first_seen_checkpoint` 自動補：23:00 前＝`△`、23:00–07:00＝`▲`、07:00–09:00＝`■`、09:00–14:00＝`◆`。補掃輪判不準就 `set-mark` 寫死。
- `raw_entry` 零加工輸出；側錄照 `14-S2b` 兩行式原樣帶出。
- YouTube 兩行式的網址行照樣帶時段標記（render 已保證標記後有半形空格）；⚠️ 小分題不要塞進 `raw_entry` 第一行——那是 `category.小分題` 的位子，`raw_entry` 只放「網址行＋備註行」。
- 寫檔 tmp+rename 原子；覆蓋前另存 `.prev.txt`（只留最近一版，救 render 壞檔用）。
- ⛔ **手改偵測**：現行 txt sha 對不上 `last_render_sha` → 拒絕覆蓋 exit 3。看到先把 txt 上的內容寫回狀態檔，確認可丟才 `--force`。
- 📊 **每輪必看對帳三行**：「素材 N 則（±X）／側錄 M 段（±X）／YouTube K 支（±X)」＋點名「現行 txt 有、本次 render 沒有」的代碼——**出現點名就是漏了 `add-side`／`update-entry`**。回報要貼這三行。
- render 完自動跑 `check` 與 `s2_topic_dedupe`（`--no-check`／`--no-topic-check` 可略）。
- 重大提醒行用 `set-alert` 存狀態檔（≤3 則），判準與撤除見 `13`。
- 腳本連續失敗 2 次 → 記「未執行（腳本錯誤）」，⛔ 禁止 agent 手掃替代。

## 3b. 中／小分題檢視：`s2_topic_review.py`（**render 前必做，每輪**）

```
python scripts/s2_topic_review.py --file "<狀態檔>"
```

**看過整張表**（約 60 行），同義／同事件的合併掉再 render（`set-category --pairs`）。
⚠️ **不要只看它列的候選**——機械只認字面：港譯「美斯」對台譯「梅西」零共同字永遠挑不出來，只有你看得出來；候選也會誤報（「足球 vs 美式足球」），自己判斷。實例形態：【高爾夫】＋【高球】；【泰國校園槍擊】＋【校園槍案】；足球下「悼念老梅西／梅西家族／梅西父喪／美斯家事」四個同一件事。
⛔ 只印不改；本支只碰中／小分題同義合併，不碰大分類歸屬。

## 3a. 主題重複偵測：`s2_topic_dedupe.py`（render 自動叫）

- 【今天內部】同一小分題名稱出現在不同大分類 → 命中（只比大分類；中主題名稱允許每天微調，比了誤報）。
- 【跨天】昨天的小分題今天全搬到不重疊的大分類 → 命中（只回看前一天一份，不多天累積）。
- 只提示不寫 state，人工 `set-category` 確認後改。
- ⛔ 不要加回「內文 bigram 模糊比對」——實測假警報蓋過訊號。

## 4. SNTV 列表級收錄（機械白名單）

體育畫面必然是比賽或訪問，是「跳過詳情不漏判斷資訊」的少數類別；白名單**只給機械可判的 `AP5`**，其餘一律照常開詳情。

- 僅限代碼 `AP5` 開頭：以列表可見資訊（標題＋時長＋Source）寫簡版三段式，不開詳情。備註標 `(SNTV)`。
- 🎯 **結尾標記兩層判準**（`role` 含 SOT 是必要條件不是充分條件，不可直接標 `(BITE)`）：

  | 列表級看到的 | 怎麼標 | 開詳情？ |
  |---|---|---|
  | `cap` 裡有引號引言（`"…"`） | 標 `(BITE)`，引言**照抄** `cap` 原文 | ❌ |
  | `role` 含 SOT 但 `cap` 沒引言 | **開一次詳情**取 `sb_count`：>0 標 `(BITE)`、=0 標 `無BITE。` | ✅ 只有這格 |
  | `role` 是 `VO` 等無聲形式 | 標 `無BITE。` | ❌ |

  ⛔ **禁止「寫不出引言原文就寫講者＋內容概述」**——那是假 BITE 產生器（概述是從標題猜的）。寧可標無BITE 讓編輯自己看帶。開詳情那格記得帶 `sb_count`（§2 批次規則），否則稽核③變盲區。
- ⚠️ **`畫面：` 寫依標題可推的實際畫面**（`▎畫面：比賽精華、遠射進球與重播。`），⛔ 不可寫操作註記（`(列表級,未開詳情)` 之類，`s2_validate` 會抓）。推不出就只寫最低限度一句。
- 使用者點名要開稿的 SNTV，回站補完整三段式。
- ⚠️ SNTV 同主題重複只收一則（判準與例外見 `13`「SNTV 例外」）；列表判讀階段就跳過，不進 `batch.json`。

## 4c. YouTube 網址素材（人工投餵）

**觸發**：使用者貼 YouTube 網址要求加入晚班交接。S2 不主動掃 YouTube。

**兩行式**（與通訊社單行三段式不同）：

```
{YouTube 網址}
({來源} {形式} {MM:SS}) {摘要}
```

- 第一行＝網址原樣（不縮短、不加括號），就是代碼。
- 第二行括號＝`({來源} {形式} {MM:SS})` 固定順序；來源用中文慣稱；時長寫括號內。
- 摘要約 200 字，直接寫內容。❌ 不寫 `▎畫面：`／`▎BITE：`／`無BITE。`；❌ 不加 `(BITE)`；❌ 不寫佔位字樣（`（200字摘要）`／`（AI摘要）` 等）。

**形式三選一（必填）**：

| 形式 | 判準 | 給編輯的意義 |
|---|---|---|
| **記者連線** | 記者出鏡對鏡頭報導，主體是記者講話 | 可整段當連線帶播 |
| **SOT** | 有可直接使用的成音（受訪／官員談話或配好旁白的包裝） | 有料可掐 |
| **主播BS** | 只有畫面、無可用成音 | 只能當背板／背景畫面 |

判斷順序：先看有無可用成音→記者出鏡＝連線；受訪／旁白＝SOT；沒有＝主播BS。**拿不準標 `主播BS`＋`needs-review add`**（高估成音會害編輯排帶落空）。

**判讀流程（字幕優先省 token）**：
1. `yt-dlp --write-auto-sub --write-sub --sub-lang "ko,en,zh-TW,zh,ja" --skip-download` 先抽字幕，有就直接寫。
2. `yt-dlp --print "%(title)s|%(duration_string)s|%(uploader)s" --skip-download` 拿 metadata（時長由此取，不下載）。
3. 無字幕才 `yt-dlp -f "best[height<=480]"` 下載跑 `video_analyze`（frame_resolution 256）。
4. 形式判不準只抽數張低解析影格確認，不跑全片。

**狀態檔**：`--source YT`；`--id` 正規化成 `YT:{video id}`（原始網址寫法多變，用它當 id 會重複收錄）；檔頭統計歸「其他」。

## 4b. 整併時的分類修正（歸錯位要歸位）

「沿用既有 `category`」是省 token 預設不是鐵律，與「同組必須相鄰」衝突時**歸位優先**。三個修正時機：
1. `raw_entry` 被覆寫時（pending→has_script）順便重檢分類——稿到後全貌常與初判不同。
2. 同事件素材已在其他大分類 → 併過去同組相鄰，不要兩邊各留一半。
3. 23:00 最終整併順掃「同事件跨大分類分裂」。

機械判準：slug 前綴相同、備註含相同專名（地名＋事件詞）＝同事件。拿不準→維持沿用＋`needs-review add`，不亂搬。

🔴 **整併 `_待整併/` 的批次時，T／C 跟 `set-category` 同一批下完**（2026-08-25 補）。
韓聯社／CNA／YouTube（[`17`](17-網址素材整併.md)）的交件檔**檔尾附了一行
`id=T/C;…`**，直接貼進 `set-tc --pairs` 即可，不必自己重判。
⚠️ ENEX／ABC（[`18`](18-交換平台素材整併.md)）與側錄（[`14`](14-S2b-側錄轉譯摘要.md)）
不走這條——那兩條是各自的 agent 直接寫進狀態檔，你不用管。
⚠️ 交件檔沒附那一行時才自己判，名單見 [`13f`](13f-S2-大分類與各站規則.md)。
⛔ **不要留到 render 之後**——那樣網頁與 txt 會停在補標前的覆蓋率（T10）。

## 5. 防卡設計（低階 agent 必讀）

> 路徑順序：§1a（首選）→ §1b（第一層退路）→ 本節 UI 舊做法（最後退路）。8／8b 兩條只在 §1b 也失敗時用；其餘條目不分路徑一律適用。

1. **每輪開工第一步 `resume`**，緊接著 `scratch-dir --mmdd {晚班起始日MMDD}`——本輪所有中間檔（`_ap_*`／`_rt_*`／batch 等）寫進它印出的路徑，不要寫在 `自動掃帶系統/` 這層。日期用晚班起始日。
2. ⚠️ **`checkpoint` 一律 `{MMDD}-{HHMM}` 格式**：時段標記靠 checkpoint 裡的 4 位數字群判斷，只寫 `01:30` 會**無聲**退回 `△`（0806 實錯 85 則）。補掃後綴可加（`0806-0430-RT補漏`），日期不能省。
3. 🎫 NS 保活已由獨立排程負責（見 §1a-3）；收工前照 `s2_scan_prompt.md` 第 7 步最後摸一次 NS。
4. ⛔ **不准 `taskkill`／`Stop-Process` 殺 Playwright 或 node**（0806 實錯：agent 自救把整個 browser MCP server 殺掉，之後每輪都跑不動；排程情境沒人能重連）。profile 被佔 → `needs-review` 記下、跳過該站、往下跑。同理不准刪 profile 的 `Singleton*` 鎖檔。真正的互斥在呼叫端 `s2_scan.ps1`。
5. **RT 卡住跳站**：連續 2 次 Next 沒反應 → `needs-review add` 記 Edit No、跳去掃下一站。不死磕。
6. **半夜禁問**：無人值守遇到需確認的事 → `needs-review add`＋寫進交接檔備註，**繼續往下跑**。⛔ 不得 `AskUserQuestion` 等回應、不得停住。NS 登入過期是典型場景：記錄、跳過 NS。
7. **fallback 全部單向**：只往下走，不回頭重試上一步。
8. ⚠️ **RT UI 連掃＝單分頁 Next 鏈＋換頁後必 `scroll` 再讀**：`get_page_text` 讀的是擷取快照，SPA 換頁不刷新——換頁後立刻讀會**無聲拿到上一則內容**；純 wait／連讀兩次都無效，只有 `screenshot` 或 `scroll` 能強制刷新。每則四步：①從大列表頂端點最新那則進詳情②按 Next③**scroll 3–5 格**④讀取並**核對文中 Edit No 與 URL 一致**才寫入。不符→再 scroll 重讀；仍不符→照第 5 條跳站。
8b. ⚠️ **Next 灰掉＝進入路徑不對**：必須從 `all?media-types=vid` 大列表、頁面在最頂、點最新那則進去，‹ › 才綁得住。灰掉→回大列表重進；仍失效→逐張點卡進詳情（每則同樣 scroll→讀→核對）；窗內素材已捲出首屏且 Next 仍失效→記中斷點跳站。
9. **AP `/home` 偶發跳轉**（`/live`／`/home/foryou` 等）：每次讀列表前先確認 URL 是 `/home`，不是就重點側欄 Latest，最多重試 2 次，仍失敗跳站記錄。

## 5c. 排程啟動器：`scripts/s2_scan.ps1`

排程不走 `CronCreate`，由 Windows 工作排程器叫：

```
pwsh -NoProfile -File "E:\GitHub\TVBS-AIHunter\scripts\s2_scan.ps1" -Model opus
```

| # | 做什麼 | 為什麼 |
|---|---|---|
| ① | 互斥鎖（OS 層獨佔檔案握把） | 程序當機握把由 OS 回收，不留死鎖 |
| ② | 撞鎖就跳過不排隊（記 `_跳過紀錄.txt`，離開碼 0） | 漏的事後補掃，比兩輪打架好 |
| ③ | checkpoint 由它算（`{MMDD}-{HHMM}`） | prompt 寫死的值幾小時就過期 |

- prompt 範本 `scripts/s2_scan_prompt.md`（`{CHECKPOINT}` 代換）——範本只放本輪參數，⚠️ 不複製規則內容（會過期並與本檔衝突）。
- 跑完會驗 `{MMDD}-s2-state.json` 與 txt 在不在——**離開碼 0 不等於掃帶做完了**。
- 排程設定完先 `-DryRun` 跑一次。⛔ 這支腳本自己也不殺任何進程。

## 5a. 每天第一輪（建檔輪，17:00）的額外動作

> 🔴 **歸檔與建檔已由腳本做掉**：`s2_scan.ps1` 的 `New-ShiftState` 在 `{MMDD}-1700` 開頭的輪次
> ①建好 `{MMDD}-s2-state.json`（`window_start` 直接寫好＝當天 13:00）②把上一班的檔（含 `.html`）
> 全部搬進 `Archive/{YYYYMMDD}/`。冪等，重跑不會重建也不重複歸檔。
> `default_file()` 遇到「已過 17:00 卻沒有今天的檔」會直接報錯，不再靜靜用昨天那份。
>
> **你要做的只剩**：開工確認 `{MMDD}-s2-state.json` 是今天日期、且 `items` 是空的。
> 不是就**停下來回報**，⛔ 不要自己建、不要退回用昨天那份。

其餘只在建檔輪做一次的事：

| # | 動作 | 說明 |
|---|---|---|
| 1 | **確認自己真的是建檔輪** | ⛔ 「共 0 則」不是證明，它同時是最常見的失敗形狀（`resume` 沒帶對 `--file` 就會 0 則）。**兩個旁證缺一不可**：①現在是 16:00 那一輪嗎（建檔輪只有 16:00，其餘 11 輪一律續掃）②資料夾裡還有沒有 `{MMDD}-s2-state.json`——有就是它還在服役（晚班交接檔**跨夜**，`checkpoint` 是今天日期就不准歸檔）。0809 實錯：還在用的 0808 檔被歸檔、資料斷成兩份 |
| 2 | `resume` | `--file` 一定明寫（自動挑最新是防呆，不是授權不寫） |
| 3 | `scratch-dir --mmdd {MMDD}` | 建當晚暫存資料夾 |
| 4 | `window_start` | 腳本已寫好＝**前一天 13:00**（排程設計上的交界點）。⚠️ 不要照「前一檔實際跑到哪」算——漏跑時會把失守窗算進涵蓋範圍；失守窗用 `needs-review` 記，不是靠 window_start 表達 |
| 5 | **機動格（第一格大分類）** | ⛔ 使用者沒指定就**空著**，不自行開、不沿用昨天 |
| 6 | pending 清查 | 跳過（新檔沒有 pending） |
| 7 | 跨日主題檢查 | 不用手動——render 完 `s2_topic_dedupe` 自己讀前一天的檔 |

## 2c. 結構化欄位：`fields`／`parse_ok`（dashboard 前置）

寫入時由 `s2_parse.derive()` 自動從 `raw_entry` 推導（codes／notes／summary／footage／bite／no_bite／duration），**agent 完全不用管**。

- ⛔ `fields` 不取代 `raw_entry`：render 仍吃 `raw_entry`。
- ⛔ 解析失敗不擋入庫：只標 `parse_ok: false`＋`parse_note`，素材照收。
- ⛔ 三類不解析：側錄（`SIDE_*`）、YouTube 兩行式、備註殼——它們本來就不是三段式。
- `parse_ok: false` 冒出來：格式真壞→修 `raw_entry`；合法變體→改 `s2_parse.py` 並補測試，不放著累積。

<!--ENDBODY-->

## 附：分檔前 13c 的原始檔頭（2026-08-24 存查，逐字保留）

```
# S2 定時掃帶 V3（精簡版）——**現行版本**

> **狀態：2026-08-11 16:00 那輪起正式上線**（由 13b V2 精簡而成）。
> 排程 agent 讀的就是本檔，`13b` 已退為歷史檔案。
> 本檔與 [`13b`](13b-S2-定時掃帶-v2省token.md) 的**規則內容完全等價**：只保留每條規則的
> **訂正後最終態**，刪去歷史敘事與已被推翻的舊版本。§ 編號沿用 V2，跨檔引用不必改。
> 內容格式、分類規則、素材行寫法、時區換算等**全部沿用 V1 [`13`](13-S2-定時掃帶.md)**，本檔只管「怎麼執行」。
>
> **Rollback**：把 `scripts/s2_scan_prompt.md` 規則清單第 2 項改回 `13b` 即可，
> `13b` 原檔未動、永久保留（含全部實錯脈絡與驗證紀錄）。
> **日後改規則一律改本檔**；要查「為什麼有這條」才回 `13b` 或 git 歷史。

```

<!-- RULES-EOF 13c2 2026-08-24 — 讀到這一行才算讀完本檔；沒讀到＝被截斷，必須用 offset 補讀。 -->
