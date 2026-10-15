# 線上 demo：議題包與稿單助手（2026-10-15）

## 重建與驗證

```powershell
python -B -X utf8 scripts/s2_warehouse_publish.py --rundown-dir scripts/s2_warehouse_inputs/rundowns --demo-dir D:\Downloads\外電資料庫_線上demo
python -B -X utf8 -m unittest discover -s scripts -p "test_s2_warehouse*.py"
node scripts/verify_s2_warehouse_web.cjs D:\Downloads\外電資料庫_線上demo
```

Python 僅使用標準函式庫。瀏覽器驗證使用既有本機 Playwright；其他環境可用 `PLAYWRIGHT_MODULE` 指定模組路徑。驗證器啟動短期本機 HTTP server 與 headless Chromium，輸出 JSON、1440／390 截圖到 demo 的 `_截圖/`。頁面不需 Playwright 或 Node，雙擊 `serve.cmd` 即可開啟。

## 資料流

`s2_warehouse_editorial.py` 將舊 `demo_build_v5_bundles.py` 的 `derive` 移入 repo，直接沿用現有 A33 `group_by_canonical`、`score`、`qualifies` 與 A34 `is_candidate`，不改正式掃帶程式。資料取 archive 的 current revisions 與 observation 關係，不讀舊 demo、舊庫或 G 槽。分組精確比對 canonical 登記簿，不跑模型、語意比對或候選稿單生成。

全庫同題至少 2 個不同 material 才建立自動包；包 ID 仍為 `b-` 加 canonical 名稱 SHA-256 前 12 碼。各班 TAG 僅包含該班觀測的成員。A33 的本班 score／qualifies 取此子集；重複 observation 不重複算包成員。

原 `days/`、`shifts/` 白名單與搜尋規則不變。新增的每種分片均列入 manifest 的 hash、大小、generation 與 demo 複製流程：

| 分片 | 內容／讀取時機 |
| --- | --- |
| `bundles/YYYY-MM-DD.json` | 本班 TAG 成員及 A33 訊號；交接讀當班，跨日／議題包與跨班組稿按需讀全體 TAG metadata |
| `editorial/YYYY-MM-DD.json` | 明確白名單的 v8 相容投影：素材代碼、完整中文摘要、分類、日期、T/C、連結、觀測班次及 notes／bite／codes／A34 等衍生 metadata；每個 material 只放最早觀測班次那一片 |
| `references/00…ff.json` | 素材鍵／legacy 別名 → 真實 material ID、editorial 所屬片；依鍵 SHA-256 前 2 碼分桶，恢復已保存稿單時只載相關桶／素材片 |
| `rundowns/YYYY-MM-DD.json` | 可選的人工候選稿單；缺輸入仍匯出空陣列，頁面顯示「本班尚無候選稿單」 |
| `config/supplement.json` | 沿用 v7 的離線增補任務、來源名單、英文候選與別名表 |

預設只讀當班素材、TAG 與設定。進入議題包／稿單助手時載所需 editorial 片；指定議題選「全部班次」或按「增補素材」時才讀全庫 editorial。後者會保留讀過的文字在本頁記憶體，70 班全庫檢索的流量與記憶體用量高於單班；可用指定班次縮小檢索。HTTP 分片快取仍驗證 manifest SHA-256，載入失敗不宣稱完成搜尋。

## 人工候選輸入與 ID 對映

不傳 `--rundown-dir` 時讀 `<warehouse-root>/archive/rundowns/YYYY-MM-DD.json`。本次為避免改 archive 來源內容，將舊 `候選稿單_1003.json` 原樣複製到 repo 的 `s2_warehouse_inputs/rundowns/2026-10-03.json`，用上方明確參數匯出。其他班沒有補寫候選。

每班 manifest `rundowns[].mapping` 保存輸入存在與否、不同引用 ID 數、改鍵數、無法對映數／清單及失效 BITE 清單。先接受原 material ID，再接受由觀測的班次／來源／代碼建立的唯一 legacy 別名；一個別名對到多個素材時不擅選。缺素材會保留在稿單缺口，移出可操作清單；BITE 必須存在對應原文才保留。

1003：11 份、35 個不同素材引用，全部直接命中新庫既有 legacy 鍵（因此改鍵 0、對不上 0），失效 BITE 0。輸入正文、段落用途與人工角度原樣保留。

## 前端與本機儲存

`bundles.js`／`rundown.js`／`supplement.js` 保留 v5／v6／v7 的建議形式、素材編號、稿單編輯、BITE／缺口、精修／寫稿指令、增補任務與回填邏輯；`editorial.js` 接上新分片、四分頁及 TAG。頁面沒有外站請求；搜尋任務只產生文字與可手動開啟的連結。

- `s2.demo.bundles.v1`：沿用 version 1、自訂包、全域包改名／成員調整、開稿包鎖定快照。自訂包帶完整班次日；既有 MMDD 會按 manifest 轉為完整日期，無 day 的早期自訂包歸到當前班。
- `s2.demo.rundown.v1`：沿用 version 1、採用／略過、草稿、編輯器與外部增補素材。可解析的 legacy ID 在記憶體正規化，下一次成功保存才寫入；鎖定文字原封保留。
- `s2.demo.view.v8`：沿用 version 1，保存 view、完整班次日，兼讀 v8 MMDD day。篩選條件只留記憶體。

讀寫都有 try/catch。未知版本、損壞資料不覆寫；稿單寫入失敗仍可在當頁編輯與複製備份，議題包則沿舊版規則不套用保存失敗的變更。儲存限同一瀏覽器／origin；舊 `file://` demo 的 localStorage 不會自動跨到 `http://127.0.0.1`，沒有跨裝置同步或已保存資料的跨 origin 搬運介面。

## 與舊 v8 對照

| 班次 | 舊三班 v8 TAG | 新 70 班 TAG | 候選稿單 |
| --- | ---: | ---: | ---: |
| 1003 | 98 | 114 | 11 → 11 |
| 0930 | 190 | 210 | 0 → 0 |
| 0929 | 191 | 224 | 0 → 0 |

1003 原有 98 包的名稱與本班成員集合逐一完全相同。新增 16 包在舊三班各僅 1 則，擴到 70 班後全庫同題達 2 則，符合原 v5 演算法的全庫門檻。分別為 BTS巡演、LPGA巡迴賽、WTT中國大滿貫、中歐貿易、加薩人道處境、南加州熱浪、奧莉維亞迪恩抄襲訴訟、巴爾的摩青少年球賽槍擊、巴黎同志驕傲遊行、柏林反戰示威、沖繩美軍涉殺人案、白宮媒體採訪禁令、科州氣候訴訟、美國國家紀念日、美巡賽、阿根廷足球聯賽。

「杜拜航空劫機案」同為 27 成員；新交接篩選為 27 筆 observation。舊 v8 為 25 列，是兩個側錄分段已合併到其他交接列。新架構原本就保留逐 observation 顯示，本次保留這個行為。

## 驗收範圍與限制

Python 單元測試涵蓋 canonical 合併、全庫門檻、本班評分、重複觀測、歧義別名、改鍵／缺件／失效 BITE、hash 及重匯出穩定性；並跑既有 warehouse／publish 測試。瀏覽器驗證包含四分頁、兩個其他班、TAG OR／跨組 AND、推薦跳轉、自訂與自動包操作、素材入稿、稿單保存／增補／鎖定、原兩分頁與矩陣、初次載入範圍、390px、儲存異常與文字注入。

保留舊版已知語意：同 canonical 不保證同一事件；日期／BITE／連結／版權仍待人工核對；「增補任務」沒有實際執行外站取材。沒有新增其他班的人工候選稿單、登入、雲端同步或正式部署。

本機最終驗證：Python 66／66、headless Chromium 16／16，零 JS 錯誤、零外站請求；兩次重匯出 changed_files 均為 0，generation 同為 `c9970a601c70acda5b9038bf98949be599d1585bc71b960b2e904577fb871bf9`。完整證據在 demo `_截圖/線上demo驗證.json` 與 `_截圖/議題包對照與重匯出驗證.json`；後者亦核對 archive DB 與舊 v8 成品未變。
