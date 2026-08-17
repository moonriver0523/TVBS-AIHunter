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
| E1 | RT Load More 迴圈判定：頁面行為改變 vs 策略漂移 | 交接§6-1 | ⏸半結 | **0812-2200 實測：迴圈消失**（捲動探測 145→11、RT 階段 7.2分/28次，回到正常水位）。傾向策略漂移或短暫頁面狀態，非持續性頁面改版；⚠️ 與 effort medium 同輪上線，歸因不純。再觀察 0030 輪無迴圈即結案；R1 是否仍要把配方寫死當預防，交使用者裁決 → **0813-0100 續驗：RT 僅 13 次/4.7分、scroll 關鍵字 13 次（2000 輪=145），連兩輪無迴圈，✅結案＝策略漂移偶發**。R1 預防性寫死留使用者裁決 |
| E2 | effort=medium 實效驗證 | 093c713 | ✅ | **0812-2200(medium) vs 0811-2200(high) 同時段對照：111次/27.0分/29.4M/106.5k vs 117次/29.5分/29.5M/106.5k（收 65 vs 70 則）——各口徑幾乎相同**。與 TODO「量不出差別」結論一致。數據已備，交 D1 裁決 |
| E3 | 鎖檔收工自動清理實戰驗證 | c9614ac | ✅ | 2200 輪 DONE 後鎖檔已不存在，收工推播同輪首次實戰成功（curl 版），移歸檔 |
| E4 | ①b 稽核前置驗收：update-entry 次數 7→1~3 | TODO | 🔶 | 2200 輪 update-entry=**4**（目標 1~3，接近未達）；set-category=8（①目標 1，未達，65 則大輪情有可原）。再看一兩輪趨勢；`s2_state:?`=6 待 A1 認齊後才能斷言。**0813-0100：update-entry=5（仍超標）、set-category=5（收 71 則，較 2200 的 8 略改善）**，①/①b 規則實質未被遵守，繼續觀察。0100 分類健檢發現規則與「邊掃邊分類」流程打架，驗收口徑擬改（見 T7）。**0813-0430/0730 續觀：set-category=3（收158則，佳）/6；update-entry=8/3。0730 收尾又出現 5 次 show 試探＋needs-review 3 次＋ls _待整併 2 次的固定尾巴（T5/T6 同款）** |

## R — 修復（品質與可靠性）

| ID | 項目 | 來源 | 優先 | 狀態 | 說明／驗收 |
|----|------|------|-----:|------|------------|
| R1 | RT Load More 迴圈修法：0811「一次抓完」evaluate 配方寫死進 13c §1b＋⛔禁迴圈 | 交接§6-1 | 1 | ⏸等E1 | 每輪省 ~38 次呼叫/6 分。⚠️ 禁令下不准附範本（交接§11-3 教訓） |
| R2 | RT 對帳只用 Edit No 判歷史已收，跨日撞號→靜默漏收（P0-1） | 複核 | 2 | ✅281d380（0813-1600 首次真實命中 RT4607） | 唯一真資料風險（RT3609 實例）。改 Edit No＋日期複合判斷。0812 未踩中但每天在骰 |
| R3 | audit finding fingerprint 去重／紅燈冪等（P0-4） | 複核＋交接§6-4 | 3 | ✅281d380 | PO-11~14WE 已登記 needs-review 仍每輪紅燈重查，1600 輪燒 7.7分/51次。修好順帶消掉目前唯一殘留紅燈 |
| R4 | truncate() 加標記後總長 4014 > 4000（P0-2） | 複核 | 4 | ✅281d380 | 17:05 只改了標記字元，長度溢出沒修→已修：標記算進 limit |
| R5 | audit △ 判準尊重合法 set-mark override（P0-3） | 複核 | 5 | ✅2026-08-13 | 17:05 只修了假警報那一半。修法：`mark` 欄位存在＝set-mark 留痕（s2_state 唯一寫入點已核），有 override 者不再報「判日失敗」；副本合成雙情境測試 PASS（無 override 照抓、有 override 不誤報） |
| R6 | AP 對帳清單抓到 page 2（≥32 則） | 接手查證 | 6 | ✅2026-08-13（13d §7）；**2026-08-14 訂正** | 現況 list=16 恰為 page 1 容量，被擠出 page 1 的素材對帳網接不到（AP5467302 實例）。掃描本身有翻頁（三輪 log 均有 PageNumber=2），弱的是對帳快照。修法走規則層：13d §7 原要求對帳快照 page1+page2 合併（≥32 則，當窗不足 17 則才允許單頁）。屬規則文字，待下輪實戰驗收快照筆數。**0814-1200 體檢訂正：PageNumber=2 回 100+（與 0100 的 117 同形），合併 page2 會把 116 寫進對帳分母。13d §7 已改為「只信 Page1＝16；禁止打 Page2；被擠出的用 term／DOM 定向補，不准 116 假綠燈」**。**0814-0100 實戰：agent 改走 API 一次撈 117 則（超額達標），但落地格式變 tab＋ISO UTC，audit parser 只認 `\|` 分隔→整行當 code、時間空白→117 則全進「窗外」假綠燈（已收 0 竟無紅燈）。main 當場修 parse_list_file（tab 分隔／total 表頭跳過／ISO UTC→本地時區），重跑：AP 已收 58＋前幾天 33＋**窗內未收 23**——全窗對帳首戰就抓到被 page1 快照時代遮住的累積漏收。**後續（0814 上午）：23 之中 1 則是稽核不看日期的誤報（已修 73e172e，窗判斷帶日期）；真漏收 22 則，使用者裁定回補 9 則硬新聞（含哥倫比亞強震搜救）、13 則運動/軟性放掉。sonnet 子代理已回補完成並經 main 獨立驗收：9 則全入庫帶 src_text、分類歸位（哥倫比亞強震那則進機動格）、render 444 則（+9）品質掃 0 命中。⚠️ 流程教訓：main 把「待 0430 回補」寫 MASTER 但排程 agent 不讀 MASTER→訊息斷鏈兩輪，跨輪交辦要走狀態檔（needs-review/alert），不是帳本** |
| R7 | src_text 混入中文說明 9 筆清洗（RT1395/RT3501/RT3613/RT3657/RT4161/RT4631/RT4641/RT4820＋截斷標記） | audit③ | 7 | ⬜ | 要回站方抓原文，成本較高；影響事後離線查證依據 |
| R8 | audit 其餘輸出補完：各清單 shown/total/more（P0-5）＋ --json-report（P0-6) | 複核 | 8 | ✅P0-5（2026-08-13） | §4 已做一處（384d9de）。P0-5 已補齊：more_note() helper 套到 Ⓐ/②/③/④/⑥/⑦ 全部截斷點（生產稽核實測「還有 14 則未列出」8+14=22 對得上）。--json-report（P0-6）仍 ⬜ 留案不動 |
| R9 | update-entry 同步 src_text／footage_type（P1） | 複核 | 9 | ✅6ecfc17 | src_text 已補（--src-text/--src-text-file/批次每筆可帶；{id,src_text} 純回補不動稿）；footage_type 原本就會傳入 apply_update |
| R10 | BITE 三態 CONFIRMED／NO_BITE／REVIEW_REQUIRED（P1） | 複核 | 10 | ⬜ | |
| R11 | 0812-2200 輪 65 則新增**全數缺 src_text** | 2200健檢 | 3.5 | ⬜ | dd0e95f 修過 new_item()，1600~2000 的 batch 都有帶，2200 突然全缺→事後查證得重開瀏覽器（audit 🟡152筆沒帶）。查 2200 的 batch json 是否漏欄位、還是走了別條入庫路徑；可用 update-entry 回補。**0813-0100 續驗：該輪 71 則 src_text 全有→只有 2200 一輪異常；65 則待回補未動**。**0813-1200 再犯 80 則→破案：batch 檔本身就沒 src_text 欄位（agent 組批漏欄位，非工具 bug）。防呆已上線（6ecfc17：add-batch 當場警告＋稽核整批漏帶升🔴＋update-entry 回補路徑）。待辦只剩：2200 的 65 則＋1200 的 80 則要不要人工回補（素材會老化），交使用者裁決** |
| R12 | truncate 3000 字截斷 SOUNDBITE 段→BITE 無法驗證 | RT9878 實例 | 4.5 | ✅281d380 | RT9878 sb_count 機械數到 9，但 truncate 只取前 3000 字未含逐字引言，agent 只能標無BITE 待人工。修法與 R4 同區：truncate 應保證 SOUNDBITE/SUPERS 段落優先保留，不是傻取前 N 字 |
| R14 | browser_evaluate 大回應落檔＝資料遺失：MCP 回 `[Evaluation result](./檔)` 連結但檔案從未寫出，agent 全機找檔 | 0813-2200健檢 | 2.5 | ✅2026-08-13（13d §6）；**0814-1000 首戰驗收過**：agent 遇到同款連結自述「per V4 §6 資料沒落地」直接分段重抓，前天 13 分鐘的坑這次 ~20 秒繞過 | 0813-2200 NS 站兩踩（ns_probe/ns_full_2200.json）：一次抓 60 則回應過大→MCP 聲稱落檔→實際連自家 output-dir（D:\Downloads\PlaywrightMCP）都沒有→agent 燒約 9＋4 分鐘搜檔（含 `find /` 全磁碟 120s timeout）。該輪 NS 15.8分/46次（正常約3分），整輪 33.7 分。agent 最後自己用分段回傳解掉＝正解。修法：13d 新章節硬規則（見連結視同資料遺失、禁找檔、禁 `find /`、立即分段重抓） |
| R13 | batch 檔寫錯位置→雙重搬運（浪費 ~3 分/輪） | 2200健檢 | 6.5 | ✅281d380 | 2200 輪把 rt/ap batch 先寫 repo 根目錄，再 Read 回來重 Write 到 scratch 目錄（卡點 91s+102s 就在這）。repo 根目錄已累積 9 個各輪殘留 json（0700/0100/1500/2000…）。修法：規則明示 batch 一律直接寫 `scratch-dir` 路徑＋清一次現存殘留。**0813-0100 再犯：ns/ap/rt_new_0813.json 又先落 repo 根（該輪三個 >60s 停頓 345s/136s/148s 全在這組檔的 Read 之後），事後有自清但雙重搬運照舊——已連兩輪，建議優先度上調**。1000 輪第三種變體：ns/ap/rt_list_1000.json 先落 repo 根、就地 python -c 檢查、再 `mv` 進 scratch（比 Read+Write 便宜但同病）。**0813-1200（13d §1 硬規則生效首輪）仍再犯**（detail 檔先落 repo 根再 mv）——規則文字管不住，剩下的硬解是 launcher 把工作目錄設成 scratch-dir（候補案，需裁決，見 D7） |

## T — 省 Token（既有計畫未完成項）

| ID | 項目 | 來源 | 優先 | 狀態 | 說明／前置 |
|----|------|------|-----:|------|------------|
| T1 | Task 2 最小啟動設定（A0→A3 逐旗標實驗） | 省T | 1 | ⬜ | 預估 ~4.7M/16%，最大單筆在 `--setting-sources`。⚠️ 唯一有實質風險的一刀：先確認 auth 不來自 user scope；`--tools` 先不砍 Write。骨架 `test_s2_launcher.ps1` 從未執行過。前置：④已修（DryRun 不再污染紀錄） |
| T2 | A4 實驗：排除 Agent／TaskCreate／TaskUpdate 工具 | 全流§4.4 | 2 | ✅281d380 | **0813-1200 首戰：Task 類工具歸零**（前一輪 0430 還有 12 次），硬排除生效 | 1600/1800 輪 Task 類 26/17 次呼叫零產出。併入 T1 流程但**單獨一輪測**，一次一個變因。**0813-0430 復發：TaskCreate 4＋TaskUpdate 8＝12 次純開銷（2200/0100 兩輪原本歸零）——行為靠 agent 自律會漂移，硬排除的必要性再添一證** |
| T3 | Task 3 清理 prompt 衝突 | 省T | 3 | ✅2026-08-13 | 三項查核完：①window_start 改為「launcher 寫死＝本班建檔日當天 13:00，agent 只確認不改寫」（⚠️子代理初版誤寫「前一天 13:00」，main 對 s2_scan.ps1:182 複核後更正——`mmdd`＝本班日期）；②「其餘 11 輪」→「8 輪」（9 輪制同步）；③taskkill 鐵律確認仍在未動。順手：步驟 5 topic_review 補 `--compact`（13d §3 連動）。衍生新案見 T8 |
| T8 | 13/13c 過期描述清理＋prompt「第一輪」整節重寫 | T3查核 | 7 | ⬜ | T3 查出但超範圍未動：①13/13c 內文多處仍寫 23:00 為晚班最後一輪（現行 2200 收尾）；②prompt「如果這是當天第一輪（狀態檔還不存在）」整節框架與 13c §5a「腳本已建檔、agent 只確認」現況矛盾（本次只修了節內 window_start 段）。低風險純文字，待批 |
| T4 | Task 4 規則分片（八片＋manifest） | 省T | 延後 | ⬜ | ~16% 但中風險 3–5 天，單獨排期。完整性對照測試與 A/B replay 比 state mutation 兩條不准省 |
| T5 | topic_review 誤報時直接印出 id | 0100分類健檢 | 4 | ✅281d380 | 0100 輪 topic_review 報「1 則(無中主題)」但沒印 id，agent 燒 6 次呼叫/40s 翻 state 檔追兇，最後查無收場（needs-review 已留痕）。一行工具修改可消滅整段白追查。**先多收幾輪資料再動工（使用者 0813 裁定）**。**1000 輪健檢破案：鬼＝AP4678031（2200 輪入庫、category 空 dict），空分類項用 `show --cat \"?\"` 查不到→懸置 4 輪；已於 0813 人工補分類（哥倫比亞強震/佩雷拉生還者救援）＋重 render。修 T5 時順帶讓 show 支援查空分類** |
| T6 | list-topics／topic_review 長輸出精簡模式 | 0100分類健檢 | 5 | ✅281d380 | 兩工具輸出過長，agent 拆 head/tail 各讀兩次（0100 輪合計 ~88s、4 次呼叫）；主題樹隨當日累積成長，晚輪更肥（2200 輪 list-topics 後接 270s 長思考）。加 --compact 或保證單次可讀。**先多收幾輪資料再動工**。0730 續證：list-topics --sub 後接 244s 長思考（隔夜主題樹 300+ 則最肥時段）、topic_review 又拆 head/tail 兩讀 |
| T7 | 「set-category 一輪一次」規則改「一站一批」 | 0100分類健檢 | 6 | ✅281d380（13d §2） | 實際流程是邊掃邊分類（NS/AP/RT 各一批＋零星補刀），規則與流程天生打架，E4 每輪都「未達標」是量錯了尺。改規則同時更新 E4 驗收口徑（目標：一站一批＋補刀 ≤1）。**先多收幾輪資料再動工** |

## A — 腳本自動化（全流程分析 Phase 0–4）

| ID | 項目 | 來源 | 優先 | 狀態 | 說明／驗收 |
|----|------|------|-----:|------|------------|
| A1 | Phase 0 剩餘：metrics 細分＋報表 | 全流§4.5 | 1 | 🔶部分 | 驗收：報表能解釋任一輪多出的呼叫去了哪裡。子項見下 |
| A2 | Phase 1：`s2_batch_prep.py` 擴充成 raw 工具層 | 全流§4.1-4.2 | 2 | 🔶核心已上線 | 最高投報（保守省 10~22% 呼叫）。只讀或寫 scratch 不動 state；先拿 1600/1800 已保存 raw replay。驗收：tool-result 一次 unwrap、`python -c` 30/54→≤10/≤15。子項見下。**0813 三輪鐵證：同一個「檢查 scratch raw」需求，0430 用 Read×16、0730 用 PowerShell×29、1000 用 python -c×45——每輪換工具即興發揮，正是缺 `inspect` 標準工具的症狀**。inspect 上線後續觀：0813-2000 輪仍有 `python -c`×14（13d §4 未被完全遵守），1800/2200 輪已收斂——再觀察。**0817 續驗：0430/0730 兩輪 `python -c:json` 又回到 26/33 次（1000 輪只 2 次、有叫 s2_batch_prep×4）——查證內容確認是「檢查 raw json 印筆數/欄位/比對」，屬 13d §4 應用 inspect/search 的場景，判定真違規非誤判。根因查到：13c §1a「`s2_batch_prep.py` 保留為選用工具」沒點名是哪個子指令，agent 讀到容易連 inspect/unwrap 一起跳過。已在 13c §1a 補澄清「選用只涵蓋 dump/build，inspect/unwrap/search 一律必用」，待下輪觀察是否收斂** |
| A3 | Phase 2：state 查詢擴充＋輪次閘門 | 全流§4.3/4.6 | 3 | ⬜ | 唯讀優先、不做第二套 parser、初版只報告不阻斷。驗收：postflight 對 0811-1800/2200 類異常能命中。子項見下 |
| A4 | Phase 4a：`s2_schedule_check.py` 排程一致性唯讀比對 | 全流§4.8 | 4 | ⬜ | XML 與 watchdog $Slots/model/TestMode 多真相源，曾險發生取消輪被看門狗補跑。只報不改 |
| A5 | Phase 4b：watchdog「START 無 DONE」中途死亡偵測 | 全流§4.7 | 5 | ⬜ | 第一版只推播不代打（自動代打見 D5）。不可只看 0-byte log、鎖被占時絕不重跑。**真實樣本＋1：0814-1000 輪收工前被 API Connection lost 打死（terminal_reason=api_error）——render 已完成但 checkpoint 未推進、DONE 推播未發，無任何機制發現，靠使用者「這輪異常久」人工起疑才查到；main 手修 checkpoint=0814-1000。D5 樣本數 2/3** |

**A1 子項**（各自可勾）：
- [x] 站別/階段分類（`phases` 欄位，093c713）
- [x] （281d380）階段分類器修誤標：TaskCreate/TaskUpdate 的待辦文字含「set-category」等關鍵詞會被誤判成分類階段＋黏性繼承放大（0813-0430 實例：分類顯示 7.2 分，攤開 NS 寫摘要的長思考被誤記，真值約 2.5 分）。修法：Task 類工具一律不參與階段判定、直接走繼承
- [x] （2026-08-13）`s2_state:?` 子指令認齊——對照 s2_state.py subparser 抓齊 20 個（含漏網的 `add`；`update-batch` 不存在未加；`done` 是 needs-review 次動詞不另開桶），token 邊界比對防 `add` 誤配 `add-batch`。三輪 replay：?=9/4/5 → 2/0/0（殘留 2 筆經查為 --help 與 find 檔名，正確落 ?）
- [x] （2026-08-13）`python -c` 依用途分桶（read-state/json/length-check/time-convert/other）——2000 輪 14 筆全數歸桶（json:11、read-state:3），other 佔比後續觀察 <10%
- [ ] 每輪記 `prompt_sha`／`13_sha`／`13c_sha`／launcher flags（規則改了不誤判為腳本效益）
- [ ] `s2_metrics_report.py` 趨勢報表（每輪/每站/每類工具）
- [ ] 用 0030~1800 歷史 transcript replay 驗證：分類總數＝原工具呼叫數

**A2 子項**（各自可勾；動工前先過 D2 裁決）：
- [x] （281d380）`unwrap` — 自動偵測 AP Items 殼/RT items 殼/裸陣列/NS 純文字清單，卸成裸陣列；失敗回報實際頂層格式不靜默
- [x] （281d380）`inspect --ids/--fields/--limit/--index` — 讀取時自動卸殼、摘要模式印 id＋標題行，取代「印整批→agent 再寫 python -c 篩」
- [x] （281d380）`search --contains --field script|story|head|all`
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
| D2 | `s2_batch_prep.py` 路線：擴充成 raw 工具層（=A2）or 就地封存 | 省T② vs 全流§8 | ✅已裁決 | 使用者 0813 裁定走工具層；unwrap/inspect/search 已上線（281d380），13d §4 立為標準用法 | 強制版已回滾（25133eb），腳本現為選用。全流分析主張「已完成第一版、應擴到 raw 工具層」；1600/1800 實測 dump/build 只補到一部分 |
| D3 | audit §4「還有 N 組未列出」提示去留 | 交接§8 | 🗳 | 抓真問題（今日抓到 RT4881 錯分類）但每輪多花時間。接手 agent 建議保留 |
| D4 | 無變動快速路徑（diff=0 輪跳過語意分類與全量 topic review） | 全流§Phase5 | 🗳 | 中高風險，改變執行行為 |
| D5 | watchdog 自動代打（A5 第二階段） | 全流§4.7 | 🗳 | 累積 3 次真實「中途死亡」樣本後再議 |
| D6 | S2b C 通道排程化 | 全流§Phase5 | 🗳 | 使用者已明示先人工跑幾天，觀察期未結束不接進 22:00 |
| D7 | launcher 把 agent 工作目錄設成 scratch-dir（R13 硬解） | 1200驗收 | ✅255313d | 使用者 0813 裁定做。launcher 解析班次日→Set-Location scratch 夾；transcript 目錄跟 cwd 走，metrics 加 --transcript-dir（退回保護）。**0813-1600 實戰：暫存檔 20 個全落 scratch、repo 根零新增＝R13 根治**。⚠️ 連動踩雷：transcript 目錄淨化規則猜錯（非英數一律換 `-`，非只換 `:\`），量測器退回舊目錄把 1200 數字記成 1600；已修（3f83554）＋誤記已刪並重記真值 |
| D8 | 2200 的 65 則＋1200 的 80 則 src_text 人工回補 | R11 | ❌裁定不補 | 使用者 0813 裁定不補（高 token、素材老化）。防呆已上線（6ecfc17）之後不會再發生；這 145 則缺原文為已接受的既成事實，後人不要再立案 |

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

### 2026-08-13（V4 批修日：13d 生效，七個 sonnet 子代理執行、main 逐項複驗）
| 項目 | commit / 證據 |
|------|---------------|
| 13d V4 增量規則文件（scratch-dir 硬規則/一站一批/--compact 預設/inspect 標準工具），prompt 加讀 V4（附回退法） | 281d380 |
| T5：topic_review 異常逐條印 id＋show --uncat（AP4678031 隱形四輪的直接解） | 281d380；生產檔 --uncat=0 則、備註殼正確排除 |
| T6：list-topics/topic_review --compact（單次讀完不再 head/tail；預設輸出逐位元組不變） | 281d380；145/61 行實測 |
| T7：set-category 一站一批＋≤1 補刀（13d §2），E4 驗收口徑連動 | 281d380 |
| T2：launcher --disallowedTools 硬排除 Task 類/Agent（-NoToolBan 回退），DryRun 驗證、BOM 完好 | 281d380；16:00 輪實戰驗收 |
| R2：RT 跨日撞號偵測（audit reconcile 清單日期 vs first_seen，僅 RT，帶⚠️標記；合成副本測試 3 情境 PASS） | 281d380 |
| R3：audit 紅燈冪等（needs_review 留痕→黃燈一行、done 後復紅；副本實測不是無腦壓燈） | 281d380；順帶照出 JL-143WE/NE-028WE 真待處理 |
| R4＋R12：truncate 含標記 ≤ 上限＋SOUNDBITE 段保留（標記純 ASCII 避 strip_agent_note 誤殺；5 情境單元測試 PASS） | 281d380 |
| R13：13d §1 硬規則＋repo 根 8 個殘留 json 搬 _repo根清理20260813/（NE-022SA 不明舊檔未動） | 281d380 |
| A1 子項：遙測 Task 工具不參與階段判定（0430 分類 7.2→2.4 分，1000 輪無回歸） | 281d380 |
| D2 裁決落地：unwrap/inspect/search 三子指令（三站真實檔實測，自動卸殼含 NS 純文字型） | 281d380 |
| 順手修：AP4678031 空分類（懸置四輪的「無中主題」之鬼）補分類＋重 render | state 紀錄（commit f1cb0fe 記載） |

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
