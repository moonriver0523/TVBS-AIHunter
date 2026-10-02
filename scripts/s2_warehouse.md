# Phase 0 外電資料庫工具

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

預設根目錄為 `D:\S2-外電資料庫\`；所有輸出均進入 `phase0\`。可設定 `S2_WAREHOUSE_ROOT`，或在子指令**之前**傳 `--warehouse-root D:\另一個外電庫`；CLI 優先於環境變數。輸出根不可位於 G:、本 repository 或輸入副本目錄及其祖先／子目錄。Windows 的 Python 需能取得 `Asia/Taipei` 與 `America/New_York` 的 IANA 時區資料；本機已驗證可用。

CLI 只接受計畫書指定 scratchpad 下的 `0930-s2-state.json` 與 `0930晚班交接.txt`，不探索其他來源。每次將各檔完整讀一次 bytes，按 SHA-256 匯入，原檔不寫入。資料庫保存原始快照 bytes、班次頂層欄位及每列完整 payload；未知欄位不丟棄。公開查詢只回傳白名單投影，不輸出完整平台 payload。

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
