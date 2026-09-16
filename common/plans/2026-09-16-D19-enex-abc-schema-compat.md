# D19：ENEX／ABC 與骨架收斂格式相容性前置評估

## 1. 欄位對照表

### ENEX

| platform raw 欄位 | `extract_enex` 用途／產出 | 骨架端對應（`SITE_SPEC`／`cmd_from_raw`／`cmd_build --skeleton`） | 相容性判斷 |
|---|---|---|---|
| `id` 或 `_id` | 經 `bare_enex_id()` 去除既有 `ENEX` 前綴，組成輸出 `id: "ENEX" + rid`；查詢 `entries` 時裸 id、帶 `ENEX` 前綴的 key 都接受 | `id_of` 必須由 `id`／`_id` 取值，且應統一輸出裸 id 或 `ENEX` 前綴 id；兩者 platform lookup 都能吃。骨架列的 `id` 同時是 `cmd_build --skeleton` 查 entries map 的 key | 欄位可對應；但同一輪必須固定 key 形式，否則 `cmd_build --skeleton` 先於 platform lookup 就可能配不到 |
| `url` 或 `videoLowResCdn` | 找媒體網址、批次量時長，最後把時長補到 `raw_entry` 行尾，並寫入 `enex.duration` | 不適合放進 `src_text_of`；若要保留供其他批次工具使用，可列入 `dump_fields`。骨架 `hint.dur` 只讀 raw 的 `dur`／`dur_ms`，不會讀這兩欄，也不會量測 | platform 可用，現有骨架提示不會自動得到 ENEX 時長 |
| `estat` | 無媒體網址時，辨識 `PUBLISHING NOW` 為尚未上架並記入 `known_gaps` | 可列入 `dump_fields`；`status_of` 不應拿它模擬 platform 的上架判斷，因 platform 仍需原 raw 自行判定 | 無直接 entries 對應；不可用骨架 `status` 取代 |
| `desc` | 輸出 item 的 `src_text = truncate(desc)` | 最自然的 `src_text_of` 是 `truncate(desc)`，骨架也會由此製作 `hint.first150` | 可直接對應 |
| `nlid` | 輸出 `enex.newslinkId` | 可列入 `dump_fields`，不必進 platform entries | 不衝突，但不是 entries 必填欄位 |
| `partner` | 輸出 `enex.partner` | 可列入 `dump_fields`，不必進 platform entries | 不衝突，但不是 entries 必填欄位 |
| entries 的 `skip` | 非空即輸出到 `skipped`，此筆不進 items；被 skip 的 entry 只需這個理由 | `SITE_SPEC.skip_of` 是「從 raw 機械排除」，為真時 `from-raw` 根本不產骨架列，和 platform entries 的「agent 判斷後排除」不是同一語意。現行 `cmd_build --skeleton` 也不從判斷 map 複製 `skip` | **對不起來**；ENEX spec 的 `skip_of` 應預設不排除，另由轉換層保存 agent 填的 `skip` |
| entries 的 `raw_entry`（字串，可空） | 三段式中文摘要；行首裸代碼會機械補 `ENEX`；時長會自動補在行尾。空值先記 `known_gaps`，後續 lint 才擋 | 骨架讓 agent 填的是 `entry`；`cmd_build --skeleton` 也只讀／輸出 `entry` | **欄名不同**；需 `entry` → `raw_entry`。不可同時保留兩份互相矛盾的內容 |
| entries 的 `category`（物件或 `大分類/中主題/小分題` 字串） | `check_entries` 要求至少有大分類、中主題；extract 後經 `norm_category()` 正規化 | 骨架預留 `category: ""`，build 會帶入 agent 提交的 category | 形狀相容，但空字串不能直接通過 platform 預檢，必須先完成分類 |
| entries 的 `sb_count`（整數） | 輸出 item 的 `sb_count`，預設 `0`；預檢拒絕非整數 | `extra_of` 應產出 `{"sb_count": 0}` 或 raw 中確實存在的整數；骨架 `hint.sb_count` 也由此取得 | 可直接對應，須維持整數型別 |
| entries 未使用的骨架欄位 | platform 不讀 `source`、`checkpoint`、`status`、`tc`、`prev_status`、`hint`、`suggest` | `status_of` 可為骨架流程提供既有狀態字串，`source` 應為 `ENEX`；但 adapter 應捨棄這些 platform 不需要的欄位 | 不衝突，但不能誤認為 platform entries schema 的一部分 |
| `dump_fields` | `extract_enex` 不讀這個設定 | 依本次可見 raw 欄位，至少需考慮 `id`／`_id`、`desc`、`url`／`videoLowResCdn`、`estat`、`nlid`、`partner`；指定的 `cmd_from_raw`／`cmd_build` 範圍本身沒有使用 `dump_fields` | 只能確認欄位候選；它對其他子指令的影響不在本次授權讀取範圍內 |

### ABC

| platform raw 欄位 | `extract_abc` 用途／產出 | 骨架端對應（`SITE_SPEC`／`cmd_from_raw`／`cmd_build --skeleton`） | 相容性判斷 |
|---|---|---|---|
| `News Story` | 必填 Story Number；組成輸出 `id: "ABC" + story`，並寫入 `abc.storyNumber`。查詢 `entries` 時裸 Story Number、帶 `ABC` 前綴的 key 都接受 | `id_of` 應取 `News Story`，可統一成裸碼或 `ABC` 前綴碼；骨架 `id` 同時是 build 查詢判斷 map 的 key | 欄位可對應；但同 ENEX，骨架與判斷 map 必須採同一 key 形式 |
| `Length` | 解析 `MM:SS`、`:SS` 或 `HH:MM:SS`，正規化後補到 `raw_entry` 行尾；原值另寫入 `abc.duration` | `cmd_from_raw` 的 `hint.dur` 只讀 `dur`／`dur_ms`，因此 ABC `Length` 不會自動顯示；可由 `extra_of` 另帶欄位，但現有 hint 不會使用 | 原始資料可保留，現有骨架提示欄位名不相容；需 `Length` → 骨架提示所用時長值的轉換，或明確接受 hint 無時長 |
| `Slug` | 輸出 `abc.slug` | 可列入 `dump_fields`；platform entries 不要求它 | 不衝突，但不是 entries 必填欄位 |
| entries 的 `skip` | 非空即輸出到 `skipped`，此筆不進 items | 與 ENEX 相同：`skip_of` 是 raw 機械排除，現行 build 不保存 agent 判斷的 `skip` | **對不起來**；ABC spec 的 `skip_of` 應預設不排除，轉換層另存 `skip` |
| entries 的 `src_text`（字串） | ABC 全文；缺值記 `known_gaps`，輸出前 `truncate()` | 骨架本身有 `src_text`，由 `src_text_of(raw)` 產生；但可見的 ABC raw 清單欄位只有 Story Number、Length、Slug 被 extractor 使用，全文目前是 entries 端提供。現行 `cmd_build --skeleton` 不會從判斷 map覆蓋 `src_text` | **來源與保存方式不相容**；必須在骨架建立前把 Detail 全文併入 raw，或讓 build／adapter接受並保存 agent 填入的 `src_text` |
| entries 的 `raw_entry`（字串，可空） | 三段式中文摘要；裸碼行首可補成 `ABC…`，並自動附加 Length 時長。空值記 `known_gaps` | 骨架使用 `entry` | **欄名不同**；需 `entry` → `raw_entry` |
| entries 的 `category`（物件或分類路徑字串） | 預檢與正規化規則同 ENEX | 骨架預留 `category: ""`，build 可帶入 | 形狀相容，但必須先填到至少含大分類、中主題 |
| entries 的 `sb_count`（整數） | 輸出 item 的 `sb_count`，預設 `0` | `extra_of` 應提供整數 `sb_count`，通常可先為 `0` | 可直接對應 |
| entries 的 `detailId` | 寫入 `abc.detailId` | `SITE_SPEC` 沒有專用欄位；可由 `extra_of` 放入骨架，但現行 `cmd_build --skeleton` 若它只存在判斷 map 中不會複製 | 需要明確保存規則；否則串接後 metadata 會遺失 |
| entries 未使用的骨架欄位 | platform 不讀 `source`、`checkpoint`、`status`、`tc`、`prev_status`、`hint`、`suggest` | `source` 應為 `ABC`；`status_of` 對 platform 最終固定輸出的 `script_status: has_script` 沒有控制作用 | 不衝突，但 adapter 應捨棄無關欄位 |
| `dump_fields` | `extract_abc` 不讀這個設定 | 依本次可見 raw 欄位，至少需考慮 `News Story`、`Length`、`Slug`；若上游 raw 已併入全文或 Detail 識別值，也必須列入，否則骨架無法承接 `src_text`／`detailId` | 核心三欄可列；全文與 Detail 欄位名需先跟實際上游快照定案 |

骨架的容器形狀也有一個決定性差異：`cmd_from_raw` 寫出的是「列陣列」；`cmd_build --skeleton` 寫出的是 `{"entries": [列…], "new_topics": {...}}`。platform 的 `check_entries` 則只接受最外層為 `{"id": {判斷欄位…}}` 的物件；因此兩種骨架產物都不能原樣當作 `s2_platform_extract.py --entries`。

## 2. 相容性結論

結論選 **(b) 大致相容，但需要欄位改名／轉換層**。

語意核心可以共用：兩邊都有素材 id、分類、摘要文字、S/B 數，ABC 另有全文與 Detail 識別值；platform 也同時接受裸 id 與站別前綴 id。因此不需要另造完全不同的人工判斷模型，但不能把目前任何一種骨架 JSON 直接餵給 `--entries`。

必要轉換如下：

1. 把骨架列陣列（若來自 build，先取外層 `entries`）轉置成 `{id: value_object}`；不要把 `new_topics` 一起送進 platform 預檢。
2. 把每列的 `entry` 政名為 `raw_entry`。
3. 原樣保留已填妥的 `category`；空字串必須在轉換前完成分類，否則 `check_entries` 會報缺大分類／中主題。
4. `sb_count` 必須保留為整數，未提供時用 `0`，不能轉成字串。
5. agent 判斷的 `skip` 必須成為 value object 的 `skip`；不可拿 `SITE_SPEC.skip_of` 代替。若 `skip` 非空，其餘 platform 欄位可不要求。
6. ABC 必須保留 `src_text` 與 `detailId`。若全文是在 Detail 階段才取得，轉換層或 build 必須允許它從 agent 判斷資料覆蓋骨架值；不能沿用目前 build 只取 `entry/category/tc/status` 的白名單。
7. ENEX 的 `src_text` 仍由原 raw `desc` 產生；媒體網址、上架狀態、newslinkId、partner 與時長量測仍交給 extractor 使用原 raw，不要塞進 platform entries 取代原邏輯。
8. ABC `Length` 仍由 extractor 正規化並附加到 `raw_entry`；若只為骨架提示顯示時長，需另做 `Length` 到 hint 時長的映射，不能改變 platform 的時長規則。
9. `source/checkpoint/status/tc/prev_status/hint/suggest` 不屬於 platform entries 契約；轉換時可捨棄。尤其骨架 `status` 不能取代 platform 最終的 `script_status`。

若完全不加轉換而硬接，`cmd_from_raw` 的陣列會被 `check_entries` 直接拒絕；build 的外層物件則會把 `entries` 陣列與 `new_topics` 當成兩筆 value，因「值不是物件」被拒絕。即使人工只抽出 build 的 `entries` 陣列，仍不是 platform 要的 keyed object，且 `entry`、`skip`、ABC `src_text/detailId` 的語意尚未補齊。

## 3. 若要擴充 SITE_SPEC 的風險清單

| D19 原列風險 | 判斷 | 依據 |
|---|---|---|
| ① 既有 NS/AP/RT 行為可能受影響 | **單純新增兩個隔離的 spec key，這項偏保守；若同時改共用 build 輸出契約，風險是真的。** | 可見程式都是先以 `SITE_SPEC[args.site]` 取單站 spec，再呼叫該 spec 的函式；新增 `abc`／`enex` key 本身不會改三站 lambda。真正的交叉風險在於為 platform 保存 `skip/raw_entry/src_text/detailId` 而修改 `cmd_build --skeleton` 的共用欄位白名單或輸出容器。D19 提到的 `dump/inspect/compare/snapshot` 實作不在本次允許讀取範圍，不能據此宣稱已排除其風險。 |
| ② schema 相容性尚未驗證 | **是真的，而且本次已確認為「可轉換、不可直連」。** | 骨架是列陣列或帶 `entries` 陣列的 wrapper；platform 要 keyed object。另有 `entry`／`raw_entry`、兩種 `skip` 語意、ABC `src_text/detailId` 保存方式等差異。 |
| ③ 既有測試涵蓋面不足、擴充需新增測試 | **是真的；但「現有測試只假設三站」這個細節本次未直接查證。** | 本次禁止讀測試與執行測試，因此不能宣稱具體覆蓋率；不過新增兩站 id 正規化、容器轉置、skip 分流、ABC 全文／Detail 保存、時長提示等新分支，客觀上都需要對應測試，尤其要證明 NS/AP/RT 輸出不變。 |

## 4. 給使用者的一句話建議

D19 **還不能直接授權動工**：schema 已確認可用轉換層銜接，但需先確認 ABC 上游 raw 快照中 Detail 全文與 `detailId` 的實際欄位名，並決定轉換層放在 `cmd_build --skeleton` 還是 platform 前置 adapter，才能裁決不影響三站的實作邊界。
