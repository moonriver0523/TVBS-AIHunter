# S2 MASTER 追蹤清單（唯一列管帳本）

- **建立**：2026-08-12（接手 agent，彙整交接文件＋複核報告＋省Token計畫＋全流程分析）
- **定位**：S2 所有改進項目的**唯一狀態帳本**，不同 agent 之間以本表交接。
  規格與理由不重抄——看「來源」欄指向的文件；本表只管**狀態、優先序、驗收與依賴**。
- **衝突時**：使用者裁決 > 本表狀態 > 來源文件。

## 使用規則（每個 agent 都要遵守）

1. **開工先讀本表**，認領項目把狀態改 🔶 並寫日期；收工更新狀態＋一行進度（含 commit hash）。
2. **不刪列、不重用 ID**。完成的移到最下方「已完成歸檔」；新項目往後編號。
3. 進度紀錄**只加不改**——寫錯就再加一行更正，保留判斷軌跡（0812 教訓：先自證清白、
   沒查完就叫「完整」都是因為軌跡被美化）。
4. 動手前檢查「依賴/前置」欄；裁決類（D-）**沒有使用者明示不得自行動工**。
5. 本表隨 main 走，改完就 commit＋push（TODO 類文件不留在功能分支）。

**狀態代號**：⬜待做｜🔶進行中｜⏸等證據｜🗳待使用者裁決｜✅完成（移歸檔）｜❌不做

**來源文件**：
- 交接 = `G:\我的雲端硬碟\Claude共用\20260812-S2-交接文件.txt`
- 複核 = `G:\我的雲端硬碟\Claude共用\20260812-S2-1600輪異常分析-複核意見與改善計畫.md`
- 省T = `common/plans/2026-08-02-S2省Token優化計畫-修訂版.md`
- 全流 = `common/plans/2026-08-12-S2全流程與腳本自動化分析.md`
- 診斷 = `G:\我的雲端硬碟\Claude共用\自動掃帶系統\0812-2000掃帶診斷.txt`

---

## E — 等證據（0812-2200 輪與後續輪次）

| ID | 項目 | 來源 | 狀態 | 要看什麼／驗收 |
|----|------|------|------|----------------|
| E1 | RT Load More 迴圈判定：頁面行為改變 vs 策略漂移 | 交接§6-1 | ⏸半結 | **0812-2200 實測：迴圈消失**（捲動探測 145→11、RT 階段 7.2分/28次，回到正常水位）。傾向策略漂移或短暫頁面狀態，非持續性頁面改版；⚠️ 與 effort medium 同輪上線，歸因不純。再觀察 0030 輪無迴圈即結案；R1 是否仍要把配方寫死當預防，交使用者裁決 |
| E2 | effort=medium 實效驗證 | 093c713 | ✅ | **0812-2200(medium) vs 0811-2200(high) 同時段對照：111次/27.0分/29.4M/106.5k vs 117次/29.5分/29.5M/106.5k（收 65 vs 70 則）——各口徑幾乎相同**。與 TODO「量不出差別」結論一致。數據已備，交 D1 裁決 |
| E3 | 鎖檔收工自動清理實戰驗證 | c9614ac | ✅ | 2200 輪 DONE 後鎖檔已不存在，收工推播同輪首次實戰成功（curl 版），移歸檔 |
| E4 | ①b 稽核前置驗收：update-entry 次數 7→1~3 | TODO | 🔶 | 2200 輪 update-entry=**4**（目標 1~3，接近未達）；set-category=8（①目標 1，未達，65 則大輪情有可原）。再看一兩輪趨勢；`s2_state:?`=6 待 A1 認齊後才能斷言 |

## R — 修復（品質與可靠性）

| ID | 項目 | 來源 | 優先 | 狀態 | 說明／驗收 |
|----|------|------|-----:|------|------------|
| R1 | RT Load More 迴圈修法：0811「一次抓完」evaluate 配方寫死進 13c §1b＋⛔禁迴圈 | 交接§6-1 | 1 | ⏸等E1 | 每輪省 ~38 次呼叫/6 分。⚠️ 禁令下不准附範本（交接§11-3 教訓） |
| R2 | RT 對帳只用 Edit No 判歷史已收，跨日撞號→靜默漏收（P0-1） | 複核 | 2 | ⬜ | 唯一真資料風險（RT3609 實例）。改 Edit No＋日期複合判斷。0812 未踩中但每天在骰 |
| R3 | audit finding fingerprint 去重／紅燈冪等（P0-4） | 複核＋交接§6-4 | 3 | ⬜ | PO-11~14WE 已登記 needs-review 仍每輪紅燈重查，1600 輪燒 7.7分/51次。修好順帶消掉目前唯一殘留紅燈 |
| R4 | truncate() 加標記後總長 4014 > 4000（P0-2） | 複核 | 4 | ⬜ | 17:05 只改了標記字元，長度溢出沒修 |
| R5 | audit △ 判準尊重合法 set-mark override（P0-3） | 複核 | 5 | ⬜ | 17:05 只修了假警報那一半 |
| R6 | AP 對帳清單抓到 page 2（≥32 則） | 接手查證 | 6 | ⬜ | 現況 list=16 恰為 page 1 容量，被擠出 page 1 的素材對帳網接不到（AP5467302 實例）。掃描本身有翻頁（三輪 log 均有 PageNumber=2），弱的是對帳快照 |
| R7 | src_text 混入中文說明 9 筆清洗（RT1395/RT3501/RT3613/RT3657/RT4161/RT4631/RT4641/RT4820＋截斷標記） | audit③ | 7 | ⬜ | 要回站方抓原文，成本較高；影響事後離線查證依據 |
| R8 | audit 其餘輸出補完：各清單 shown/total/more（P0-5）＋ --json-report（P0-6） | 複核 | 8 | ⬜ | §4 已做一處（384d9de），其餘清單未補 |
| R9 | update-entry 同步 src_text／footage_type（P1） | 複核 | 9 | ⬜ | 配合 dd0e95f（new_item 已修）補齊另一半 |
| R10 | BITE 三態 CONFIRMED／NO_BITE／REVIEW_REQUIRED（P1） | 複核 | 10 | ⬜ | |

## T — 省 Token（既有計畫未完成項）

| ID | 項目 | 來源 | 優先 | 狀態 | 說明／前置 |
|----|------|------|-----:|------|------------|
| T1 | Task 2 最小啟動設定（A0→A3 逐旗標實驗） | 省T | 1 | ⬜ | 預估 ~4.7M/16%，最大單筆在 `--setting-sources`。⚠️ 唯一有實質風險的一刀：先確認 auth 不來自 user scope；`--tools` 先不砍 Write。骨架 `test_s2_launcher.ps1` 從未執行過。前置：④已修（DryRun 不再污染紀錄） |
| T2 | A4 實驗：排除 Agent／TaskCreate／TaskUpdate 工具 | 全流§4.4 | 2 | ⬜ | 1600/1800 輪 Task 類 26/17 次呼叫零產出。併入 T1 流程但**單獨一輪測**，一次一個變因 |
| T3 | Task 3 清理 prompt 衝突 | 省T | 3 | ⬜ | 檢查表含：window_start 誰設（全流已確認 prompt 與 launcher 說法不一致）、23:00 輪已取消要同步、assert「不准 taskkill」鐵律仍在 |
| T4 | Task 4 規則分片（八片＋manifest） | 省T | 延後 | ⬜ | ~16% 但中風險 3–5 天，單獨排期。完整性對照測試與 A/B replay 比 state mutation 兩條不准省 |

## A — 腳本自動化（全流程分析 Phase 0–4）

| ID | 項目 | 來源 | 優先 | 狀態 | 說明／驗收 |
|----|------|------|-----:|------|------------|
| A1 | Phase 0 剩餘：metrics 細分＋報表 | 全流§4.5 | 1 | 🔶部分 | 驗收：報表能解釋任一輪多出的呼叫去了哪裡。子項見下 |
| A2 | Phase 1：`s2_batch_prep.py` 擴充成 raw 工具層 | 全流§4.1-4.2 | 2 | 🗳見D2 | 最高投報（保守省 10~22% 呼叫）。只讀或寫 scratch 不動 state；先拿 1600/1800 已保存 raw replay。驗收：tool-result 一次 unwrap、`python -c` 30/54→≤10/≤15。子項見下 |
| A3 | Phase 2：state 查詢擴充＋輪次閘門 | 全流§4.3/4.6 | 3 | ⬜ | 唯讀優先、不做第二套 parser、初版只報告不阻斷。驗收：postflight 對 0811-1800/2200 類異常能命中。子項見下 |
| A4 | Phase 4a：`s2_schedule_check.py` 排程一致性唯讀比對 | 全流§4.8 | 4 | ⬜ | XML 與 watchdog $Slots/model/TestMode 多真相源，曾險發生取消輪被看門狗補跑。只報不改 |
| A5 | Phase 4b：watchdog「START 無 DONE」中途死亡偵測 | 全流§4.7 | 5 | ⬜ | 第一版只推播不代打（自動代打見 D5）。不可只看 0-byte log、鎖被占時絕不重跑 |

**A1 子項**（各自可勾）：
- [x] 站別/階段分類（`phases` 欄位，093c713）
- [ ] `s2_state:?` 子指令認齊（resume/pending/scratch-dir/set-top/needs-review/remove/set-mark/set-aired），驗收：`s2_state:?` 歸零
- [ ] `python -c` 依用途分桶（read-state/inspect-raw/unwrap-tool-result/write-json/length-check/time-convert/other），驗收：other <10%
- [ ] 每輪記 `prompt_sha`／`13_sha`／`13c_sha`／launcher flags（規則改了不誤判為腳本效益）
- [ ] `s2_metrics_report.py` 趨勢報表（每輪/每站/每類工具）
- [ ] 用 0030~1800 歷史 transcript replay 驗證：分類總數＝原工具呼叫數

**A2 子項**（各自可勾；動工前先過 D2 裁決）：
- [ ] `unwrap` — tool-result 卸載檔一次解包成規範化 raw（失敗回報外層格式與原始錯誤，不靜默）
- [ ] `inspect --ids/--fields/--limit` — 精準查 raw，取代「印整批→agent 再寫 python -c 篩」
- [ ] `search --contains --field script|story|head`
- [ ] `snapshot --out _audit_{site}_{HHMM}.txt` — 稽核快照
- [ ] `compare --raw --batch` — 只印缺 ID/欄位差
- 護欄：per-site adapter（RT 用 `code` 不是 `id`）；冪等；不覆寫舊 snapshot；子步獨立 status

**A3 子項**（各自可勾）：
- [ ] `s2_state show` 補 `--source/--status/--id-prefix/--unclassified/--missing-field/--contains`
- [ ] `resume --json`（供其他工具組合，開工查詢至少取代 3 個）
- [ ] `s2_round_gate.py` preflight（state 路徑/班次日/掃描窗/pending/needs-review/scratch/待整併/既有中主題）
- [ ] `s2_round_gate.py` postflight（頂層 checkpoint/三站 reconcile/本輪 snapshot/未結案嚴重項/last render/txt+html hash）
- [ ] （後步）launcher 記 gate 結果→依結果決定通知級別；**不以 gate 阻斷正式輪**

## D — 待使用者裁決（未裁定前不得動工）

| ID | 議題 | 來源 | 狀態 | 給裁決者的脈絡 |
|----|------|------|------|----------------|
| D1 | effort 定案：high or medium | 省T§三 vs 0812 裁定 | 🗳等E2 | 三方說法：省T計畫書寫「medium 無效不要再試」；TODO 更正為「量不出差別，先做 Task 1」；使用者 0812 21時裁定改 medium（已上線 093c713）。E2 的 P2 遙測數據出來後定案，**定案後要回寫省T計畫書§三**，免得下個 agent 被「不要再試」誤導 |
| D2 | `s2_batch_prep.py` 路線：擴充成 raw 工具層（=A2）or 就地封存 | 省T② vs 全流§8 | 🗳 | 強制版已回滾（25133eb），腳本現為選用。全流分析主張「已完成第一版、應擴到 raw 工具層」；1600/1800 實測 dump/build 只補到一部分 |
| D3 | audit §4「還有 N 組未列出」提示去留 | 交接§8 | 🗳 | 抓真問題（今日抓到 RT4881 錯分類）但每輪多花時間。接手 agent 建議保留 |
| D4 | 無變動快速路徑（diff=0 輪跳過語意分類與全量 topic review） | 全流§Phase5 | 🗳 | 中高風險，改變執行行為 |
| D5 | watchdog 自動代打（A5 第二階段） | 全流§4.7 | 🗳 | 累積 3 次真實「中途死亡」樣本後再議 |
| D6 | S2b C 通道排程化 | 全流§Phase5 | 🗳 | 使用者已明示先人工跑幾天，觀察期未結束不接進 22:00 |

## ❌ 明文不做（防止後人重提）

| 項目 | 出處與理由 |
|------|-----------|
| Task 6 三站固定 collector | 省T§六：API 漂移會從「agent 當場繞過」變「無聲失敗」，投報率九項最差 |
| Task 7 LLM 只讀 normalized delta | 依賴 Task 6，一併延後 |
| Task 9 Message Batches | 降 API 計價不降 token，本流程走 subscription CLI 不適用 |
| Haiku 模型分流 | 前綴 64.7k 未砍前，雙模型雙冷啟動不可能划算 |
| Prompt caching 專項 | 降為觀察項，Task 1 已順手記 cache 欄位 |

## 實作共同護欄（摘自全流§九，全項目適用）

一次只上一項；歷史 replay→shadow→TestMode→1 正式輪→3 連續正式輪；比 normalized
state mutation 不比文字回覆；不覆寫舊 snapshot；錯誤帶原始訊息不回單一 boolean；
欄位全空必須明確失敗；新路徑跑完一個完整班次＋人工確認前，不刪現行規則與腳本。

---

## 附錄：來源文件 → MASTER 對照（防漏收查核表）

| 全流程分析 | MASTER | | 省T計畫 | MASTER |
|---|---|---|---|---|
| §4.1 unwrap | A2 | | Task 2 A0-A3 | T1 |
| §4.2 inspect/search/snapshot/compare | A2 | | Task 3 prompt 衝突 | T3 |
| §4.3 show 篩選＋resume --json | A3 | | Task 4 規則分片 | T4 |
| §4.4 排除 Task 工具（A4 實驗） | T2 | | ② batch_prep 路線 | D2→A2 |
| §4.5 遙測細分＋版本 hash | A1 | | Task 5 | 併A2 |
| §4.6 round gate | A3 | | Task 6/7/9、Haiku、caching | ❌不做 |
| §4.7 watchdog 中途死亡 | A5＋D5 | | Task 8 effort | D1 |
| §4.8 schedule check | A4 | | 複核 P0-1~P0-6/P1 | R2~R5/R8~R10 |
| Phase 5 快速路徑/S2b/collector | D4/D6/❌ | | 交接§6-1 RT/§6-2 推播/§6-3 漏收 | R1/歸檔/歸檔 |
| §九 護欄 | 護欄段 | | 交接§6-4 稽核/§6-5 P0 | R3/R2~R10 |

## ✅ 已完成歸檔

### 2026-08-12（接手 agent 清理日）
| 項目 | commit / 證據 |
|------|---------------|
| ntfy 推播修復（curl.exe 取代 .NET，根因：本機 .NET 走主機名稱連 ntfy.sh 必逾時） | 313d930；實測手機收到，13 項測試全過 |
| 殘留鎖誤判源修除（收工 Dispose 後 best-effort 刪鎖檔；互斥本靠獨佔握把從未失效） | c9614ac；DryRun 兩情境驗證 |
| P2 分段耗時遙測（phases 欄位：稽核/render/分類/NS/AP/RT 每輪自動記 calls/minutes） | 093c713；0812-2000 對照手工拆帳同量級 |
| effort high→medium（使用者裁定，待 E2 驗證、D1 定案） | 093c713 |
| RT4881 北京昌平淹路 天氣→大陸＋needs-review 留痕＋txt 重渲染 | state＋render 紀錄 |
| §7 查證：NS 2000 輪低量=真清閒（對帳 40/38 僅漏已留痕的 PY-04WE）；AP 三輪 13 則=巧合（三輪均有翻頁），漏收皆已留痕個案 | 接手進度檔 |
| 0812-2000 診斷覆核：耗時正常區間、AP Failed to fetch 為一次性偶發、「殘留鎖」為誤判 | 本表 c9614ac 項 |

### 2026-08-12（前任 agent，摘自交接文件）
| 項目 | commit |
|------|--------|
| ②強制流程＋cp950 樣板回滾（自改自修，2000 輪驗證有效） | 25133eb |
| ①強制批次寫入（一半有效：set-category 9→4）＋①b 稽核前置 | f71c623／c3d188e |
| ④DryRun 污染修復、遙測雲端化、watchdog BOM、Task1 量測器、⑤AP PageSize=16 | 2cc03dc／852a743／a74cfc7／1b9d986 |
| 烏俄中主題固定＋機動格（使用者要求，不要動）、audit §2 誤報修正、§4 more 提示 | 163320d／08d64a7／384d9de |
| new_item() 存 src_text/footage_type（1600 輪掃帶 agent 自修） | dd0e95f |
| 排程 12→9 輪（實省 ~15%） | 2026-08-12 01:39 |
