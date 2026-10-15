# 外電資料庫工具（Phase 0 單班／Phase 1 Archive 多班）

固定入口為 `s2_warehouse.py`，schema v1、extractor `s2-warehouse-1.0.0`、連結模板 v1。只使用 Python 標準函式庫，並引用零 I/O 的 `s2_material_schema` 純函式；不 import `s2_state`，也沒有掃帶／render 接線、排程、網路或 Drive 發布。

## 執行

在 repository 根目錄執行：

```powershell
python -X utf8 scripts/test_s2_warehouse.py
python -X utf8 scripts/s2_warehouse.py import
python -X utf8 scripts/s2_warehouse.py report
python -X utf8 scripts/s2_warehouse.py query --date 2026-09-30 --limit 5
python -X utf8 scripts/s2_warehouse.py query --date 2026-10-01 --source YNA --keyword buGW2sCr_do
python -X utf8 scripts/s2_warehouse.py query --from 2026-09-30 --to 2026-10-01 --t 科技醫藥 --c 南韓
python -X utf8 scripts/s2_warehouse.py query --date 2026-09-30 --overlap
```

預設根目錄為 `D:\S2-外電資料庫\`；單班輸出進入 `phase0\`，多班輸出進入 `archive\`。可設定 `S2_WAREHOUSE_ROOT`，或在子指令**之前**傳 `--warehouse-root D:\另一個外電庫`；CLI 優先於環境變數。輸出根不可位於 G:、本 repository 或輸入副本目錄及其祖先／子目錄。Windows 的 Python 需能取得 `Asia/Taipei` 與 `America/New_York` 的 IANA 時區資料；本機已驗證可用。

單班 `import` 只接受計畫書指定 scratchpad 下的 `0930-s2-state.json` 與 `0930晚班交接.txt`，不探索其他來源。每次將各檔完整讀一次 bytes，按 SHA-256 匯入，原檔不寫入。資料庫保存原始快照 bytes、班次頂層欄位及每列完整 payload；未知欄位不丟棄。公開查詢只回傳白名單投影，不輸出完整平台 payload。

## Archive 多班匯入（2026-10-15 授權範圍）

```powershell
python -X utf8 scripts/s2_warehouse.py import-archive
python -X utf8 scripts/s2_warehouse.py --dataset archive query --from 2026-07-31 --to 2026-10-14 --source RT --limit 20
python -X utf8 scripts/s2_warehouse.py --dataset archive query --keyword YNA01 --include-notes
# 可讀的唯讀副本亦可作來源；輸出仍固定為指定根下的 archive 子庫
python -X utf8 scripts/s2_warehouse.py --warehouse-root D:\另一個外電庫 import-archive --archive-root D:\Archive唯讀副本
```

來源預設 `G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive`，只收日期資料夾直屬且月日相符的 `<YYYYMMDD>/<MMDD>-s2-state.json`，同層 `<MMDD>晚班交接.txt` 若存在則核對 hash／標頭；txt 不獨立復原、不讀 Archive 外的當日進行中檔。G: 僅列清冊、讀 bytes 與算 SHA-256，絕不建立、寫入、搬移、改名或刪除來源。符號連結與越出來源根的連結不追蹤；輸出與來源不可相互包含。

排除 `_誤開新檔-*`、`*.bak*`、`*.prev.txt`、`_暫存`、`_s2_raw_*`、`_repo根清理*`、`晚班交接歷史範例` 與其他非標準路徑／檔名。排除目錄在清冊記一列「整棵略過」，不展開內容。日期資料夾缺標準 state 會列出，不把 txt-only 當零素材完整班次。

`YYYYMMDD(1)`／`YYYYMMDD (1)` 內若有標準 state，先讀 bytes 比對同日標準資料夾 hash：相同者略過；不同、缺標準對照或無法讀完比對者，雙方均暫緩並列待人工判斷，回 `partial`，不自動選用其中一份。如果前次已匯入同日快照，保留既有資料，本次不新增爭議快照。非標準檔名不讀內容。

班次日以 `window_start` 交叉核對資料夾；舊 schema 缺值時由資料夾推定，收據 `shift_date_quality=inferred_folder` 並註明原因，不把班次日當素材日。窗口與資料夾日期不同時暫緩該快照。無法解析的列保存原值與序號至快照收據 quarantine，其他列照常匯入，回 `partial`。同碼矛盾列另有衝突鍵保留，不靜默吞列。無 offset／無法解析的快照 `updated_at` 留原值並註記，不因此丟棄整班。

每份不同快照有獨立 shift（`s2:<班次日>:<snapshot_sha256>`）、receipt 與 observation，同一班次日可保存多份快照。新制 YNA／CNA 強身份跨班只一筆 material、多筆 observation；其他沿用 `legacy:<班次日>:<SRC>:<local_id>`，跨班次日不合併。同來源同原 ID 跨班另列疑似素材報表，僅供人工裁決。完整 payload 不同則保留 revision；current 按帶 offset 的原始快照 `updated_at` 排序，舊快照不覆蓋新快照；無法判斷先後時保留既有 current 並在收據明示，兩版仍可追溯。全庫 first_seen 取最早可靠正式 checkpoint；T/C 索引保留各次觀測曾有的標籤，revision／observation 留每次原值。

同 SHA-256 重匯，資料庫所有表均零新增；每班一個 `BEGIN IMMEDIATE` 交易，中斷後重跑續接已提交收據。snapshot 收據可從 DB 重建；每次執行另留 `receipts/archive-run-<run_hash>.json`，不增加 DB observation。exit 0＝本次完成，2＝隔離／待判斷／缺標準 state 等部分完成，1＝清冊不可讀或操作失敗；不表示全站候選覆蓋完整。讀清冊失敗仍輸出失敗報告，不建立空資料庫假稱匯入成功。

所有新輸出在 `<warehouse-root>\archive\`，不碰 `phase0\`：

- `warehouse.sqlite`：原始 bytes、素材、revision、observation 與班次。
- `receipts/<snapshot_sha256>.json`：逐快照來源路徑／hash、班次日品質、txt 核對、逐班筆數與隔離原值。
- `reports/archive-import.md`／`.json`：累計班次日／快照數、每班輸入／處理／隔離／內容／note、資料表總量、素材日期品質、班次日期品質、本次略過清單與原因／錯誤。
- `reports/archive-possible-duplicates.json`：同來源同原 ID 的跨班疑似素材與全部暫定鍵；Markdown 報告也列出對照。

報表將未匯入壞列與已保留衝突分開：`輸入＝已處理 observation＋未匯入壞列`；quarantine 包含兩類，不能再與 observation 直接相加。匯入不呼叫 API／模型、不連網、不接正式掃帶／排程／render／Drive 發布。

## 日期與身份契約

- 班次日取 `window_start` 的完整年月日；正式 `first_seen_checkpoint` 以班次錨定年份，precision=`checkpoint_anchor`。候選輪、編輯時間與本機匯入時間各有原始欄位，不替代首次正式入庫。相鄰三日以外／缺失 checkpoint 保持未知。
- AP 只辨認 `SHOTLIST:` 至 `STORYLINE:` 之間「地點 - 英文全日期 [可選畫面標記] 編號.」標頭；RT 只辨認 `SHOWS:` 區段的大寫地點＋括號英文全日期。標頭中的 ARCHIVE／FILE／歷史 B-roll、歷年日期及截斷稿僅保存證據；正文引用日期不作主日。SNTV 等未支援標頭保留完整原文、退路標記，後續需以版本更新擴充。
- 無明確主次的已辨認主日期，依 D-候選1 採最早日、quality=`ambiguous`；完整區間與逐項證據保留。`--overlap` 查候選區間相交；預設查索引日。只有日期不製造 UTC 午夜。`AP4687838` 原文有截斷與多組日期，主素材未確認，因此暫列入庫日。
- NS 明示 `Shot Date`（含現有 HTML 包裝）作拍攝日；`createdDate` 另記建立時間，不冒稱發布時間。ABC `DeliveryAvailableDateTime` 已為臺灣時區，另存完成時間；ENEX `sortDate`／`publishedDate` 為 epoch 毫秒，衝突保留雙份證據並退路。實際 0930 副本缺這些 ABC／ENEX 結構化時間，未以 ID 或內文日期代替。
- YNA／CNA 採同一 video ID 的 `published_at_utc`，換算臺灣素材日。發布時間證據不同 ID 或缺 video ID 時不採用。ET 用 `America/New_York`，無 offset 的夏令時間切換模糊／不存在時刻拒絕推算；本副本沒有經確認的 ET 發布時間欄位，不從節目播出時間推導。
- 側錄 ID 的 MM-DD、HHMMSS 與班次年份推定起點，quality=`inferred_recording`。副本沒有母帶收據，明示待交叉驗證；不以六碼合併，也不把 373 段當成 txt 的 224 個顯示群組。
- 新制 `YNA-{videoId}`／`CNA-{videoId}` 直接作強身份，保留大小寫；其餘未驗證永久鍵使用 `legacy:<完整班次日>:<SRC>:<百分比編碼local_id>`。AP Edit No、ENEX newslinkId、ABC detailId 的生命週期尚未確認，原值存 payload，未在 Phase 0 升格為永久身份。
- 每筆 `source_link` 由固定模板產生，包含版本、依據與缺值原因。AP 數字 Edit No 生成搜尋頁；Reuters 僅以驗證 GUID 生成 permalink；YouTube 11 字元 ID 生成 watch URL；NS 僅接受白名單原生頁面，不採有簽章 query 的預覽媒體。異型 AP、未知 ENEX／ABC 路由、無母帶引用的側錄保持缺值。

## 收據、查詢與限制

`warehouse.sqlite` 的關聯表包含素材、初始 revision、observation、班次、receipt、alias、原有 T/C 與歷史 note 處置。索引覆蓋日期、來源＋日期、T/C、班次。初始 revision 保存來源／編輯／中繼資料獨立 hash，標 `history_completeness=final_snapshot_only`；Phase 0 不宣稱可重建已覆蓋的中間稿，也不實作多班更新，第二份不同快照會拒收。

單一 writer 使用 SQLite `BEGIN IMMEDIATE` 與外鍵。同快照重匯不增加任何資料表列，收據可從 DB 重建；schema／extractor 版本不符拒收。壞列或同碼多筆保留原始序號、隔離清單，回傳 `partial` 與 exit code 2；操作失敗為 exit code 1。`complete` 只指匯入完整，不等於來源全站覆蓋完整。note 保存 `legacy_unresolved`，沒有結構化保留對象證據時，不補造去重或排除關係。

txt 收據核對 hash、一般內容總數與標頭來源數；`last_render_sha` 命中也不冒稱重新執行 renderer／完成 envelope 驗證，品質維持 provisional。R51 的 txt NS=301／其他=200 與本庫 NS=296／其他=205 差異列入收據；沒有修改原 txt 或 validator。

`query` 支援素材日、區間、來源、正文／中文摘要／ID 關鍵字、當時保存的 T/C，全部為參數化 SQL。預設排除 note，未知日期只能不加日期條件查出；`--include-notes` 可納入備註。結果有總數、分頁 offset 與下一頁位置。未知日期的正式介面預設仍待後續裁決；這只是離線 CLI 契約。

`receipts/<snapshot_sha256>.json` 是匯入收據；`reports/date-quality.md`、`.json` 是來源 × 日期品質／依據、ambiguous 與完整退路清單；`reports/phase0-measurements.md`、`.json` 保存實測筆數、日期分布、範例與五個數字開頭 video ID。

CLI 路徑護欄與 `generated_by` 不是 OS 權限隔離。相同作業系統帳號仍有任意 SQL／檔案寫入能力，Phase 0 沒有發布端；正式服務帳號、未授權寫入監測、備份責任人與 Drive 發布需後續階段另行處理。

## Archive 靜態分片與本機線上 demo（A47／D-候選23 A 案）

```powershell
python -X utf8 scripts/test_s2_warehouse_publish.py
python -X utf8 scripts/test_s2_warehouse.py
# 只匯出；不連網、不部署、不啟動正式掃帶
python -X utf8 scripts/s2_warehouse_publish.py
# 匯出並複製靜態網站與當前發布分片
python -X utf8 scripts/s2_warehouse_publish.py --demo-dir D:\Downloads\外電資料庫_線上demo
# 自訂母本根／分片大小（bytes，預設 2,000,000）
python -X utf8 scripts/s2_warehouse_publish.py --warehouse-root D:\另一個外電庫 --max-shard-bytes 1000000
```

入口 `s2_warehouse_publish.py` 只以 SQLite `mode=ro`、`query_only` 和單一讀取交易讀取 `<warehouse-root>/archive/warehouse.sqlite`，schema／extractor 檢查沿用原工具。預設根與 `S2_WAREHOUSE_ROOT` 的優先序同原工具。輸出固定在 `archive/publish/`，不讀取 G: Archive，不碰 phase0／舊 demo 庫，不改掃帶、排程或原資料庫。

- `manifest.json`：格式版本、generation、UTC 產生時間、完整年月日班次／素材日目錄、各組總筆數、來源／T／C 詞彙，以及各片 `path/count/bytes/sha256/oversized`。
- `shifts/YYYY-MM-DD.json`：當日全部 observation（含 note），保留當時摘要、T/C、來源連結與日期推導；同日多快照全部保留，`snapshot_count` 註明數量，不能當成去重後新素材數。
- `days/YYYY-MM-DD.json`：每筆 material 的目前版本，沿用 query 的素材日、日期品質及 note 語意；T/C 取原庫累積索引，對齊 CLI。日期未知獨立放在 `days/unknown.json`，不補假日期。
- 超過上限拆成 `YYYY-MM-DD.json`、`YYYY-MM-DD.part002.json` 等，manifest `parts` 列出全部。每片是 `{"items":[...]}`。依實際 UTF-8 bytes 計算；單筆本身已超標時保持完整，明示 `oversized=true`。不截斷正文或偷偷丟列。

公開欄位採明確白名單：基礎 metadata 完整沿用 `query` 投影，另為清單與篩選加 `id`、完整中文 `raw_entry`、`tc.T/C`；日期片另加 `search_text`（原 CLI 已存的 ID／完整中文摘要／來源原文／category／needs_review 文字串），班次片另加 `observation.shift_id/ordinal/revision_id`。**不發布** `platform`、`fields`、`compiled`、快照 bytes、完整 payload、原始路徑或收據。原文以搜尋文字串發布，並非完整平台 payload；搜尋採 SQLite 原 CLI 的 ASCII 英文字母忽略大小寫、中文字面子字串，不截成預覽。這個 demo 的跨日關鍵字範圍直接對齊 CLI，晚班關鍵字只查代碼／完整中文摘要。

`generation` 是 manifest 內容（含全部分片 SHA-256、大小、筆數與設定，排除產生時間）的 SHA-256。相同內容重跑沿用時間與 generation；逐檔比較 bytes，完全相同不寫入、不改 mtime，只修復／改寫內容異動的片。每檔同目錄暫存、flush/fsync 後 `os.replace`，manifest 最後換名。不是跨檔案交易；前端逐片驗證 SHA-256，遇到中斷更新／混版／缺片時顯示搜尋未完成，禁止顯示假完整總數。舊的多餘片不自動刪除，manifest 不再引用即可；日後正式雲端發布仍需另外實作整代切換、權限及備份。

網站原始碼位於 `scripts/s2_warehouse_web/`（純 HTML/CSS/JS，無框架、套件、外部字型或模型／圖片 API）。`--demo-dir` 只複製 manifest 引用的片到 `data/`，並複製靜態資產；同內容不覆寫。輸出後雙擊 `serve.cmd`，或執行：

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory D:\Downloads\外電資料庫_線上demo
# 網址：http://127.0.0.1:8765/
```

晚班預設最新班次、包含備註、T/C 矩陣收合；跨日預設「最新班次日往前七日」（不是異常未來素材日）、排除備註，可另勾日期未知。同一維度多選 OR，不同維度 AND。只 fetch 選定班次或指定區間的分片，逐片讀取、最多快取 16 片，50 則分頁；搜尋中不提供精確總數，全部成功才顯示。縮小日期區間能控制手機的流量與記憶體；本機 demo 尚未實作計畫書的伺服端 8 MiB／5 秒 cursor，也沒有權限登入或 Drive／Apps Script 接線。議題包與稿單助手已補入，分片、可選人工候選輸入及驗證方式見 [s2_warehouse_editorial.md](s2_warehouse_editorial.md)。

日期品質直接保留母本推導結果；「入庫日代替」「多日期待確認」「側錄日期推定」「日期未知」均會顯示，未知日勾選時才讀 unknown 片。異常歷年／未來日期不擅自修正；標籤亦保留母本原值。這是發布方式驗證，不代表歷史日期已全面清洗。
