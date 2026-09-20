# D23：YNA／CNA YouTube 納入 S2 定時掃帶接線實作計畫

> **文件性質**：實作計畫，尚未授權動工。本文不代表已修改 production 腳本、排程、規則或狀態檔。
>
> **唯一業務事實來源**：`common/plans/S2-MASTER-追蹤清單.md` 的 D23 完整列（2026-09-20 累積七輪查證）。本文只以該列已確認的頻道、抓取途徑、配額、字幕策略、輪次裁示與版權待決事項為前提；未另外重做網路查證。
>
> **實作方式**：後續若獲准，採 TDD、小步提交；先用 fixtures／假 client 驗證，未到實跑階段不得呼叫真 YouTube API、不得下載字幕、不得碰正式狀態檔或 `.s2-scan.lock`。

## 一、背景與目標

現行 S2 固定掃描 NS／AP／RT／ENEX／ABC。D23 已確認 YNA（`@yonhapnewstv23`）與 CNA（`@channelnewsasia`）可透過 YouTube uploads playlist 納入清單掃描：

- YNA channel ID：`UCTHCOPwqNfZ0uiKOvFyhGwg`
- CNA channel ID：`UC83jt4dlz1Gjl58fzQrrKZg`
- 清單主路徑：YouTube Data API `playlistItems.list`，每頁最多 50 則並可分頁；`videos.list` 補時長與影片狀態等 metadata。
- 字幕：CNA 取英文自動字幕；YNA 先取 YouTube 自動翻譯 `zh-Hant` 作初判，需要精確判斷時再回取 `ko` 原文精翻。
- 固定站序：`NS → AP → RT → ENEX → ABC → CNA → YNA`。
- 01:00／20:00 不掃 CNA／YNA，其餘 04:30／07:00／11:00／17:00／22:00 共五輪掃描。
- 跳過輪不查、不寫候選；下次掃描把窗口往前順延，以穩定 ID 去重，素材只延後、不漏收。
- 不把 YouTube 塞進 `s2_batch_prep.py` 的 `SITE_SPEC`；另建 `scripts/s2_youtube_bridge.py`，沿用 D19「獨立 platform 前置 adapter」的隔離原則。

本計畫的目標不是只把 API 回應存成 JSON，而是把「分頁抓齊、窗口判定、字幕取得、人工編輯判斷、格式驗證、入庫、成功後推進游標」收成一條可重播、可測試、失敗不漏收的接線，最後只透過既有 `s2_state.py add-batch` seam 寫入狀態檔。

## 二、現況複核與結論

### 2.1 13c 輪次邏輯

`common/v9/13c-S2-執行版-上-入口與三站擷取.md` V5-1／V7-1 的既有原則是：跳過輪不查、不寫候選；窗口順延；查發布時間；窗口有 10 分鐘重疊並由 ID 去重。D23 的五輪設計與此原則一致。

YNA／CNA 的正式輪次表應沿用同一張表的四欄格式，而不是另造簡化格式：

| 檢查點 | CNA | YNA | 實際站序 |
|---|---|---|---|
| 01:00 | ⬜ 跳過 | ⬜ 跳過 | NS→AP→RT；沿用 V7-5 的 ABC 收工觸碰，但不算掃 ABC／YouTube |
| 04:30 | ✅ 窗回 22:00–04:30 | ✅ 窗回 22:00–04:30 | NS→AP→RT→ENEX→ABC→CNA→YNA |
| 07:00 | ✅ | ✅ | NS→AP→RT→ENEX→ABC→CNA→YNA |
| 11:00 | ✅ | ✅ | NS→AP→RT→ENEX→ABC→CNA→YNA |
| 17:00 | ✅ | ✅ | NS→AP→RT→ENEX→ABC→CNA→YNA |
| 20:00 | ⬜ 跳過 | ⬜ 跳過 | NS→AP→RT |
| 22:00 | ✅ 窗回 17:00–22:00 | ✅ 窗回 17:00–22:00 | NS→AP→RT→ENEX→ABC→CNA→YNA |

補充執行順序：ABC 完成後，仍須先履行 13c 的「關瀏覽器前最後再碰一次 NS」並關閉瀏覽器，再做不依賴瀏覽器的 CNA／YNA adapter。這樣既維持 D23 的站序，也不讓 YouTube API／字幕耗時延長 NS JWT、ABC `ss-tok` 的瀏覽器持有時間。YouTube 失敗只能把本輪標成警告並保留待補窗口，不得回滾或拖垮已完成的五站。

### 2.2 `s2_platform_extract.py`／lint／merge 三件套的適用性

現行 platform 三件套的實際 interface 是：

1. `s2_platform_extract.py`：吃站方 `--raw` 與 keyed object `--entries`，產出 ENEX／ABC 專用候選檔；候選列使用 `first_seen_checkpoint`／`script_status`／`raw_entry`。
2. `s2_platform_lint.py`：只接受頂層 `source=ENEX|ABC`，ID 正則也只認 ENEX／ABC，並檢查候選 JSON 與成對 txt。
3. `s2_platform_merge.py`：把候選欄位映成 `add-batch` 的 `checkpoint`／`status`／`entry`，再另產 category pairs；`--apply` 時才呼叫 `add-batch` 與 `set-category`。

判斷：**YNA／CNA 不直接接這套候選 schema，也不擴充其 hard-coded site 分支。**原因如下：

- YouTube 的主要複雜度是 API 分頁、影片 metadata join、字幕與每站游標；ENEX／ABC extractor 的核心則是 CSV／站方 JSON 正規化與候選檔交件，兩者不是同一個 seam。
- platform lint 的 `source`、ID、候選檔與成對 txt 規則都寫死 ENEX／ABC；為 YouTube 擴充會同時改三支 production 腳本，卻只是讓資料繞一圈再回到 `add-batch`。
- 現行 `add-batch` 已能在同一 batch row 接受 `category`／`tc`，使用 wrapper 時也能走新題閘門；YouTube 無須退回 platform merge 的「先 add-batch、再 set-category」舊分段。
- 應仿 D19 的是**獨立 adapter 與兩階段骨架精神**，不是照抄 ENEX／ABC 的最終候選格式。

因此 `s2_youtube_bridge.py` 應直接輸出 `add-batch` wrapper；但要重用 D19 已證實有效的護欄：raw 快照可重播、ID 去重、所有漏判／排除明列、人工只填小型決策檔、預設不覆寫既有輸出、正式 apply 前 lint、鎖檔語意區分人工與輪內執行。

### 2.3 `s2_batch_prep.py` 與 `add-batch` 的實際契約

`s2_batch_prep.py build` 目前只允許 `--site ns|ap|rt`，`SITE_SPEC` 也只含三站；這正是 D23 不應硬塞進去的原因。其可借鏡的輸出契約如下：

```json
{
  "entries": [
    {
      "id": "...",
      "source": "...",
      "checkpoint": "0920-0430",
      "status": "has_script",
      "entry": "...",
      "src_text": "...",
      "category": {"大分類": "...", "中主題": "...", "小分題": "..."},
      "tc": {"T": ["..."], "C": ["..."]},
      "platform": {}
    }
  ],
  "new_topics": {}
}
```

`s2_state.py add-batch` 的結構必填欄位是 `id/source/checkpoint/status/entry`；`status` 只接受 `has_script|pending`；`entry` 必須是字串；`checkpoint` 必須符合 `^\d{4}-\d{4}$`。`src_text`、`category`、`tc`、`sb_count`、`footage_type`、`platform` 是選填，但 YouTube 正式入庫時 `src_text` 與 `platform` 應列為 bridge 的必備欄位，避免字幕依據與影片 provenance 消失。

最終一律輸出 wrapper，不輸出裸陣列。雖然 YNA／CNA 目前不在 `GATED_SOURCES`，wrapper 可啟用 `new_topics` gate，避免 YouTube 批次繞過現行中主題登記機制。

### 2.4 前一版接線提案的漏洞與修正

| 項目 | 前案判斷 | 本次複核 | 計畫修正 |
|---|---|---|---|
| 排在五站後 | 可行 | 可行，但不可延後瀏覽器收工硬步驟 | 先做 NS 最後觸碰並關瀏覽器，再跑 CNA→YNA；仍在同一輪、同一鎖內 |
| 01:00／20:00 跳過 | 可行 | 與 13c 一致 | 跳過時零 API、零字幕、零候選、零游標更新；明文回報 |
| 用全域 state checkpoint 算窗口 | 未細化 | **不可直接用**。01:00／20:00 是 YouTube 特有跳過輪；17:00 又會新建狀態檔，單一頂層 checkpoint 無法代表每站上次成功掃描點 | 建立 CNA／YNA 各自的持久化成功游標；只在完整抓取且入庫成功後前進 |
| 以 ID 重疊去重 | 方向正確 | 現有 `YNA01–99`／`CNA01–99` 不足：YNA 日量可能超過 99，流水號也不能穩定映射 `videoId` | 新增保留大小寫的 `YNA-<videoId>`／`CNA-<videoId>` writer ID；舊 `YNA01`／`CNA01` 繼續相容 |
| bridge 直接轉 batch | 可行 | 必須先補決策骨架、全量對帳與輸出 preflight，否則 API 有 N 則、batch 少 K 則會靜默漏判 | 採 `collect`＋`finalize` 兩個 entry point；每筆必為入庫、明確 skip 或 deferred 三者之一 |
| 降輪次即可化解 YNA 高頻 | 部分可行 | 降輪次降低啟動次數，不降低單輪總則數；不能把「不用篩選」解讀成可任意截斷 | 分頁一定抓到窗口邊界；可做編輯排除，但不可用固定頁數／固定筆數截尾；高量另列正式輪觀察指標 |
| 同一把鎖 | 可行 | 同輪呼叫時鎖必然存在，照人工流程檢查會誤擋 | 比照 `s2_platform_merge.py`：輪內明帶 `--in-round`；人工 apply 不得帶，且只看鎖存在、不 open 鎖檔 |
| 版權 | 未決 | 仍是 production 上線阻斷條件 | 可先做 fixture 與沙箱技術驗證；未有使用者／權責窗口裁示，不得接正式排程或供正式引用 |

## 三、目標設計

### 3.1 模組與 seam

`s2_youtube_bridge.py` 是「YouTube 外部來源 → S2 add-batch」的深 module。外部 seam 只有兩個 CLI entry point：

1. `collect`：讀每站成功游標與正式狀態檔，抓完整窗口，取得 metadata／字幕，輸出可重播 manifest 與人工提示表；**不寫 S2 state、不前進游標**。
2. `finalize`：把 manifest 與人工 decisions 合併成 add-batch wrapper；預設只產檔與 preflight。正式輪明帶 `--apply --file ... --in-round` 時才呼叫既有 `add-batch`，成功後原子更新游標。

建議介面草案：

```powershell
python scripts/s2_youtube_bridge.py collect `
  --site cna `
  --checkpoint 0920-0430 `
  --state "...\0920-s2-state.json" `
  --cursor "...\s2-youtube-cursors.json" `
  --out "...\cna_youtube_manifest_0430.json"

python scripts/s2_youtube_bridge.py finalize `
  --manifest "...\cna_youtube_manifest_0430.json" `
  --entries "...\cna_youtube_entries_0430.json" `
  --out "...\cna_youtube_batch_0430.json" `
  --apply --file "...\0920-s2-state.json" --in-round
```

測試不應透過真網路。module 內部把 Data API client、字幕 runner、時鐘當成可替換依賴；單元測試使用 fixture adapter。production adapter 才讀 API key 並執行 `yt-dlp`。API key 只從環境變數讀取，不得寫進命令列、manifest、log 或錯誤訊息。

### 3.2 素材 ID 相容方案

正式 YouTube 素材碼定為：

```text
YNA-<11字元、保留大小寫的 YouTube videoId>
CNA-<11字元、保留大小寫的 YouTube videoId>
```

不可把整個 ID `.upper()`：YouTube `videoId` 大小寫有意義。只正規化站別前綴，suffix 原樣保存。

後續實作需同步調整並測試：

- `scripts/s2_material_schema.py`
  - 新增 scheduled YouTube ID regex；舊 `YNA01–99`／`CNA01–99` URL 素材仍合法。
  - `detect_id_family()`、`canonicalize_id_for_lookup()`、`validate_material_id_for_write()` 支援新格式並保留 suffix 大小寫。
  - `validate_source_for_write()` 仍強制 `YNA-* → source=YNA`、`CNA-* → source=CNA`。
- `scripts/s2_validate.py`
  - 素材行 `CODE` 同時接受 legacy 流水號與新 `YNA-/CNA-<videoId>`，避免正文有資料但檔頭計數／品質掃靜默漏掉。
- 受 ID parser 影響的測試與 reader／render 路徑
  - 至少覆蓋 `s2_mark_ingested.py`、source reader、render 計數與查找；確認 generic regex 已可接受連字號與 `_`，否則補最小調整。
- 規則文字
  - 後續獲准實作時，13c 的「URL id＝YNA／CNA＋01–99」要明確保留為人工網址素材，另加 scheduled YouTube ID 規格；不可把兩種來源混成同一流水號規則。

不採用 `YT:<videoId>`：現行 reader 會把它分類成 `OTH/YouTube`，且 writer 要求 `source=YT`，會失去 YNA／CNA 的來源預設、站別統計與排序語意。

### 3.3 每站游標與窗口

建立獨立持久檔（建議位於正式 S2 狀態目錄、固定檔名 `s2-youtube-cursors.json`，不隨日狀態檔歸檔）：

```json
{
  "schema_version": 1,
  "sites": {
    "CNA": {
      "last_success_checkpoint": "0920-2200",
      "last_complete_end_utc": "2026-09-20T14:03:12Z",
      "deferred_video_ids": [],
      "recent_video_ids": []
    },
    "YNA": {
      "last_success_checkpoint": "0920-2200",
      "last_complete_end_utc": "2026-09-20T14:05:41Z",
      "deferred_video_ids": [],
      "recent_video_ids": []
    }
  }
}
```

窗口規則：

- `checkpoint` 只是本輪機碼，永遠用 `MMDD-HHMM`，CNA／YNA 不另加 suffix；補跑說明走既有 `checkpoint_label`／run context，不污染 `CHECKPOINT_RE`。
- 選取發布時間區間為 `(last_complete_end_utc - 10 分鐘, collect_started_at_utc]`。10 分鐘只作重疊，不拿未來時間當上限；重疊項由永久 video ID 去重。
- 比對欄位使用影片實際發布時間：優先 `playlistItems.contentDetails.videoPublishedAt`，再用 `videos.snippet.publishedAt` 交叉檢查／補缺；不得拿 playlist item 加入清單時間或本地抓取時間代替。
- 01:00／20:00 完全不執行 `collect`，游標不動；04:30 自然從 22:00 成功終點續抓，22:00 自然從 17:00 成功終點續抓。
- 前一個應掃輪若失敗，游標仍停在更早的成功點；下一成功輪會多抓，不會依固定時刻硬切掉失敗窗口。
- 首次上線沒有游標時，必須由操作者明帶 bootstrap 起點或經核准建立初始游標；禁止默認「現在往回 N 小時」後就當完整。
- 游標只在 `add-batch` 回傳成功、manifest 全量對帳通過後更新。若 add-batch 成功但游標寫入失敗，下輪會重抓，state 的永久 ID 會擋重複；這是可接受的重複，不是漏收。反向順序（先推游標再入庫）禁止。
- `deferred_video_ids` 保存字幕／metadata 暫時失敗的影片。即使時間游標已向前，下一輪仍先重試 deferred；成功或明確永久排除後才移除。

游標用 temp file＋`os.replace` 原子寫入，並帶 revision／前值比對，拒絕以過期 manifest 覆蓋新游標。

### 3.4 Data API 分頁與欄位映射

`playlistItems.list` 不得寫死「每輪 1–2 頁」。每頁 `maxResults=50`，持續跟 `nextPageToken`，直到已看見早於窗口下界的項目；若觸及安全頁數上限仍未越過窗口下界，整站 collect 失敗、游標不前進並明確報警。

`videos.list` 以最多 50 個 video ID 一批 join metadata。逐欄映射如下：

| 上游欄位 | 正規化欄位／用途 | 必要護欄 |
|---|---|---|
| `playlistItems.items[].contentDetails.videoId` | `video_id`；組永久素材 ID 與 watch URL | 缺值進 `dropped`，不可靜默跳過 |
| `playlistItems.items[].snippet.resourceId.videoId` | `video_id` fallback／交叉檢查 | 與 contentDetails 不同時 hard fail 該筆並列明 |
| `contentDetails.videoPublishedAt` | `published_at_utc` 主值、窗口判斷 | 必須是 timezone-aware UTC；解析失敗 deferred |
| `playlistItems.snippet.channelId` | 頻道身分檢查 | 必須等於設定的 YNA／CNA channel ID |
| `videos.items[].id` | join key | API 回來少一筆時該 video deferred，不得當不存在 |
| `videos.snippet.channelId` | 第二次頻道身分檢查 | 不符即 blocking，避免 uploads playlist／設定接錯 |
| `videos.snippet.publishedAt` | 發布時間交叉檢查／fallback | 與主值差異超過容許值時列 needs_review，不自動改窗 |
| `videos.snippet.title` | `title`／hint；優先於 playlist snapshot | 保留原文；YNA 不以機器翻譯標題取代 provenance |
| `videos.snippet.description` | `description`／fallback context | 不是字幕，不得冒充 `src_text` 正文 |
| `videos.snippet.liveBroadcastContent` | live／upcoming 篩選 | 非 `none` 明列 skipped 或 deferred；規則先定案再上線 |
| `videos.contentDetails.duration` | ISO-8601 duration；轉 `duration_seconds` 與素材行 `MM:SS` | 無法解析記 known gap；不得填 `00:00` 佔位 |
| `videos.status.privacyStatus`／`uploadStatus` | 可用性判斷 | 非公開／未處理完成列 deferred 或明確排除，不可靜默少一則 |
| 字幕 runner 正規化文字 | `src_text` | CNA=`en` auto；YNA=`zh-Hant` auto-translate；空字串不得標 `has_script` |
| 字幕 track／來源 | `platform.caption` | 記 `language`、`kind`、取得時間；YNA 必標「初判用自動翻譯」 |

建議 `platform` metadata：

```json
{
  "site": "YNA",
  "provider": "YouTube",
  "video_id": "AbCd_ef-123",
  "channel_id": "UCTHCOPwqNfZ0uiKOvFyhGwg",
  "url": "https://www.youtube.com/watch?v=AbCd_ef-123",
  "published_at_utc": "2026-09-20T12:34:56Z",
  "duration_seconds": 95,
  "caption": {
    "language": "zh-Hant",
    "kind": "auto-translated",
    "precision": "triage-only"
  }
}
```

`new_item()` 已會把 `platform` 物件保存進狀態檔，因此不需為每個 YouTube metadata 增加一個頂層 state 欄位。

### 3.5 字幕與人工判斷

`collect` 對窗口內且尚未在庫的影片才跑字幕，避免對重疊／已收錄 ID 重複下載。

- CNA：首選 `en` automatic captions，正規化 rolling captions 的重複片段、時間碼與斷句後存 `src_text`。
- YNA：首選 `zh-Hant` auto-translated captions，`platform.caption.precision=triage-only`；不得在 metadata 或提示表把它稱為人工／官方翻譯。
- 需要精判時，操作者可依 manifest 的 video ID 回取 `ko` 原文，另做精翻；這是例外路徑，不強迫每則都跑。
- 字幕抓取失敗、空白或只有無意義片段時，列入 `deferred_video_ids`；不得用 description 偽裝成字幕後標 `has_script`。
- raw manifest 可保存字幕正規化前後的檔案路徑與 checksum，避免在 batch／state 塞兩份長文；API key、cookie、完整 yt-dlp 命令列不得落檔。

人工 decisions 檔沿用小型 keyed object：

```json
{
  "_new_topics": {},
  "YNA-AbCd_ef-123": {
    "entry": "YNA-AbCd_ef-123 (南韓／主題) ▎摘要…▎畫面：…▎無BITE▎01:35",
    "category": {"大分類": "國際", "中主題": "...", "小分題": "..."},
    "tc": {"T": ["..."], "C": ["南韓"]}
  },
  "YNA-XyZ987_ab-c": {"skip": "明確排除理由"}
}
```

`finalize` 必做全量對帳：manifest 內每個 ready item 都必須在 decisions 中有 `entry` 或非空 `skip`；缺判斷列為 `dropped` 並 exit 2，不產可 apply 的 batch。`skip` 不進 batch，但要留在 receipt／counts，證明不是漏判。

### 3.6 final batch 逐欄契約

| add-batch 欄位 | 來源 | 規則 |
|---|---|---|
| `id` | `source + "-" + videoId` | YNA／CNA 前綴固定；videoId 保留大小寫；同批不得重複 |
| `source` | CLI `--site` 設定 | 只可 `YNA` 或 `CNA`；不可寫 `YT` |
| `checkpoint` | 本輪 run context | 嚴格 `MMDD-HHMM`；不把 `-YNA`／`-補掃` 接在此欄 |
| `status` | 字幕可用性 | ready 固定 `has_script`；字幕暫時失敗不入此批，改列 deferred |
| `entry` | 人工 decisions | 非空字串；首碼必須與 `id` 完全一致；不得自帶時段標記 |
| `src_text` | 正規化字幕 | CNA 英文 ASR；YNA `zh-Hant` 初判字幕；不可缺、不可用 description 代替 |
| `category` | 人工 decisions | 接受既有物件或路徑字串；建議物件型式 |
| `tc` | 人工 decisions | 接受既有物件或字串；YNA／CNA 來源預設仍由現行 pretag 輔助，不代替人工確認 |
| `sb_count` | 字幕機械分析（若可靠）或省略 | 不可把未知硬填 0；若字幕格式不足以可靠計數就省略 |
| `platform` | collect manifest | 保存影片 provenance、發布時間、時長與字幕精度 |
| `suggest` | bridge 呼叫既有 pretag（可選） | 純提示，`add-batch` 不保存；失敗不得影響入庫 |

輸出一律是 `{"entries": [...], "new_topics": {...}}`。`finalize` 在任何副作用前，先用 `s2_material_schema` 的 pure validation、素材行 lint 與全量對帳完成 preflight；不得等 `add-batch` 逐筆 skip 後才發現整批 schema 不相容。

### 3.7 獨立於五站之外的手動觸發機制（使用者 2026-09-20 新增需求）

**設計目標**：CNA／YNA 除了掛在既有五站輪次尾端（3.1／Phase 5）之外，要能**不必等下一個排定輪次、也不必等整個五站輪跑完**，隨時單獨補開一次 CNA／YNA 掃描。

**核心結論：這個需求不必另開一支新腳本，`collect`／`finalize` 這兩個 CLI entry point 本來就已經是獨立可手動呼叫的介面**（見 3.1）——差別只在於帶不帶 `--in-round`：

```powershell
# 手動補掃 CNA，從上次成功游標抓到現在，不帶 --in-round
python scripts/s2_youtube_bridge.py collect --site cna `
  --state "...\0920-s2-state.json" `
  --cursor "...\s2-youtube-cursors.json" `
  --out "...\cna_youtube_manifest_manual.json"

python scripts/s2_youtube_bridge.py finalize `
  --manifest "...\cna_youtube_manifest_manual.json" `
  --entries "...\cna_youtube_entries_manual.json" `
  --out "...\cna_youtube_batch_manual.json" `
  --apply --file "...\0920-s2-state.json"
  # 不帶 --in-round：finalize 只看 .s2-scan.lock 是否存在（見 2.4／3.1），
  # 若五站正在跑會直接拒絕而非等待或搶鎖，避免手動流程誤撞正在進行的瀏覽器輪次
```

**不需要 `.s2-scan.lock`**：bridge 完全不碰 Playwright／瀏覽器，設計上就不需要跟五站共用那把鎖；`--in-round` 只是「確認呼叫方是排定輪次本身、可跳過額外保護檢查」的旗標，手動呼叫時本來就該省略。

**窗口與去重天然對齊、不必特別處理**：手動觸發用的仍是同一份 `s2-youtube-cursors.json`，窗口一樣是「上次成功終點 → 觸發當下」，跟排定輪次共用同一套永久 ID（`YNA-<videoId>`／`CNA-<videoId>`）去重機制。手動觸發等於幫該站多一次「提早把游標往前推」的機會，不會因為多跑一次而重複入庫或漏收下一個排定輪次的窗口。

**唯一需要新增的保護**：兩份呼叫（人工手動 vs. 排定輪次的 `--in-round` 呼叫）理論上可能同時對同一站呼叫 `finalize --apply`，游標檔的 `os.replace` 原子寫入＋revision 比對（3.3）可以防止檔案寫壞，但無法防止兩邊各自根據同一個舊游標起點各抓一次窗口、各自呼叫 `add-batch`（結果不會產生重複素材，但游標會被其中較晚完成的一方覆蓋，較早完成那次抓到的窗口尾端可能被誤判成還沒收）。**修正**：比照 `.s2-scan.lock` 的排他鎖模式，但另開一把**輕量、獨立、按站別區分**的鎖檔（例如 `s2-youtube-<site>.lock`），只在同一站的 `collect`→`finalize --apply` 期間握住，跟五站的 `.s2-scan.lock` 互不阻擋；第二個呼叫撞到鎖時直接報錯退出（不等待、不重試），比照保活腳本「寧可拒絕一次、不要卡死」的既有設計原則。

**不在本次計畫書實作範圍內，留待未來排程整合階段裁決**：是否要額外幫「獨立手動觸發」建一支排程（例如另一個 Windows 工作排程器項目，讓 CNA／YNA 可以用跟五站不同的頻率獨立跑），或純粹作為人工/agent 臨時補跑用的 CLI 介面即可、不建排程。這是使用範圍的決定，不影響上面的技術設計。

## 四、分階段實作步驟

### Phase 0：裁示與基線凍結

- [ ] 使用者明確把 D23 從「待評估」改為「核准實作」；未裁示不得進 production 實作。
- [ ] 版權／引用原則取得權責窗口結論，至少確認：可否保存自動字幕、可否把影片內容作交接與後續寫稿依據、成品需要何種來源標示。
- [ ] 決定 API key 的環境變數名稱與部署位置；確認不進 repo、不進 prompt、不進 log。
- [ ] 錄製 fixture：playlist 第一頁／多頁、videos join、YNA zh-Hant 字幕、CNA en 字幕、無字幕、private／live、重複 ID、時區邊界；fixture 必須去除憑證。
- [ ] 記錄未接線前五站測試與排程基線，後續驗收要證明 NS／AP／RT／ENEX／ABC 無回歸。

### Phase 1：先修 ID seam（TDD）

**預計修改：**`scripts/s2_material_schema.py`、`scripts/s2_validate.py`、對應測試；必要時才最小調整 reader／render parser。

- [ ] 先寫失敗測試：新 ID 可寫入、可 lookup、source 不符被拒、videoId 大小寫不被改、legacy `YNA01/CNA02` 行為不變。
- [ ] 加入 `YNA-/CNA-<videoId>` 規格；避免共用 legacy 分支對整串 `.upper()`。
- [ ] 素材行 lint、render 計數、mark-ingested、source reader 各補一例，防止「正文看得到、計數與品質掃漏掉」的靜默錯誤。
- [ ] 跑 schema／state／render 相關既有測試；不通過不得進 bridge。

### Phase 2：`collect` 純讀路徑（TDD，先 fixture）

**預計新增：**`scripts/s2_youtube_bridge.py`、`scripts/test_s2_youtube_bridge.py`。

- [ ] 以假 Data API client 驗證 `nextPageToken` 分頁直到越過窗口下界；固定一頁／兩頁的實作應被測試抓出。
- [ ] 驗證 playlistItems→videos join、50 IDs 分批、頻道 ID 雙重檢查、發布時間 precedence、ISO-8601 duration。
- [ ] 驗證 state 已有 `has_script` ID 不再抓字幕；重疊項與同批重複只保留一筆並警告。
- [ ] 驗證字幕 runner：CNA `en`、YNA `zh-Hant`；rolling caption 去重；空字幕進 deferred。
- [ ] 產 manifest、提示表、counts、skipped／dropped／deferred；輸出已存在時預設拒絕覆寫。
- [ ] API 分頁／videos join 等「窗口完整性」失敗時，collect 非 0 結束且不碰游標；單筆字幕暫時失敗則 collect 可成功，但該 ID 必須進 deferred，不能混入 ready。

### Phase 3：`finalize` 與 add-batch 契約（TDD）

- [ ] 先寫逐欄 fixture：一筆 YNA、一筆 CNA、一筆 skip、一筆 decisions 遺漏、一筆錯 checkpoint、一筆 ID/source mismatch。
- [ ] decisions keyed object → final wrapper；`entry/category/tc` 來自人工，`src_text/platform/checkpoint/source` 只能來自可信 manifest，人工檔不得覆蓋。
- [ ] 所有 ready item 必須 accounted；任何 dropped／重複／錯 ID 都 exit 2 且不產 apply-ready 檔。
- [ ] wrapper 固定帶 `new_topics`；驗證既有 add-batch 新題 gate 可運作。
- [ ] 用臨時 state file 執行真 `s2_state.py add-batch` subprocess e2e：欄位完整落入 state、同 ID 重送只跳過、不產第二筆、YNA／CNA source preserved。
- [ ] `--apply` 預設關閉；沒帶 `--file` 拒絕；人工模式遇鎖檔拒絕；`--in-round` 只略過「自己持有鎖」的檢查。

### Phase 4：游標交易順序與故障恢復（TDD）

- [ ] 模擬 add-batch 失敗：游標完全不動。
- [ ] 模擬 add-batch 成功、游標寫入失敗：重跑會因永久 ID 去重，不會重複入庫，也不漏收。
- [ ] 模擬 01:00／20:00 跳過、22:00 成功、04:30 執行：窗口涵蓋 22:00 後全部內容。
- [ ] 模擬 22:00 失敗：04:30 從 17:00 的最後成功終點續抓，不得從名義 22:00 截斷。
- [ ] 模擬 17:00 新日狀態檔：固定游標仍延續，10 分鐘重疊不造成跨班重複素材。
- [ ] 模擬字幕 deferred：時間游標可在完整清單抓取後前進，但 deferred ID 留在重試佇列，下一輪先重試；未成功／未明確排除前不可消失。
- [ ] 模擬手動觸發與排定輪次同站撞鎖（3.7）：第二個 `finalize --apply` 呼叫在 `s2-youtube-<site>.lock` 存在時應立即報錯退出，不等待、不覆寫先到者的游標；另一站不受影響。

### Phase 5：規則與 launcher 接線（只在規則空窗）

**預計修改：**13c 對應 V9 規則、S2 prompt／launcher 必要指路、測試；實際檔名以動工當下 active V9 為準。

- [ ] 把本文輪次表寫進 active 規則，措辭沿用「本輪不掃…」「窗順延，不漏收只延後」。
- [ ] 13c 的 URL ID 說明拆成 legacy 人工網址 ID 與 scheduled YouTube ID；不得覆寫 legacy 規則。
- [ ] 在五站瀏覽器收工硬步驟之後、render／通知統計之前插入 CNA→YNA；兩站失敗各自留警告，不能中止既有五站收工。
- [ ] 01:00／20:00 只回報「本輪不掃 CNA／YNA（D23）」；不呼叫 bridge。
- [ ] 更新通知／本輪則數統計，從只列 NS/AP/RT 擴成能顯示 YNA/CNA；若 ENEX/ABC 統計另有既有規格，依現行格式統一處理，不另造第二套數字。
- [ ] `python scripts/s2_rules_check.py` 與 launcher dry-run 全過；dry-run 不准呼叫外網、不准建游標、不准動 state。

### Phase 6：沙箱、限量觀察、正式上線

- [ ] fixture 全綠後，才用專用測試 API key 在非正式狀態檔跑一次 list/meta；字幕下載只取已核准的小樣本。
- [ ] 以 `--out` 產 manifest／batch，人工逐筆比對影片頁面、發布時間、字幕語言、時長、ID 與 source；不加 `--apply`。
- [ ] 用臨時 state e2e，確認 render、source 排序、T/C 預設、檔頭計數、mark-ingested。
- [ ] 第一個正式輪只開 CNA 或設明確限量觀察模式；限量只可限制「供人檢視／apply」且未處理項要進 deferred，**不可截斷分頁或推進游標後丟掉窗口尾端**。
- [ ] CNA 穩定後再開 YNA；連續至少三個應掃輪確認 catch-up、配額、耗時、字幕失敗率與人力負荷。
- [ ] 通過後才把 D23 狀態與實測數據回寫 MASTER；這個回寫屬未來實作工作，不在本計畫文件產出任務內。

## 五、預計檔案異動範圍（未授權前不得改）

| 類型 | 檔案 | 用途 |
|---|---|---|
| 新增 production | `scripts/s2_youtube_bridge.py` | collect／finalize adapter |
| 新增測試 | `scripts/test_s2_youtube_bridge.py` | API fixture、字幕、窗口、游標、batch e2e |
| 修改 schema | `scripts/s2_material_schema.py` | 新永久 ID；legacy 相容 |
| 修改 validator | `scripts/s2_validate.py` | 素材行辨識新 ID |
| 修改測試 | schema／ID／reader／render 既有測試 | 防大小寫、source、計數回歸 |
| 可能最小修改 | `scripts/s2_scan.ps1`、通知統計相關程式 | 同輪串接、跳過、統計；須以測試證明五站不變 |
| 修改 active 規則 | `common/v9/13c-...` 與必要 prompt 指路 | 輪次、站序、ID、失敗處理 |
| 新增 runtime state | `s2-youtube-cursors.json`（repo 外正式狀態目錄） | 每站成功游標與 deferred queue |
| 新增 runtime lock | `s2-youtube-<site>.lock`（repo 外正式狀態目錄，按站別各一把） | 保護手動觸發（3.7）與排定輪次同站同時 `finalize --apply` 的游標競態；與 `.s2-scan.lock` 互不阻擋 |

明確不改：`s2_batch_prep.py` 的 `SITE_SPEC`、`s2_platform_extract.py`、`s2_platform_lint.py`、`s2_platform_merge.py`。除非實作時出現本文未涵蓋且有測試證明的硬相依，否則不得為「共用看起來比較整齊」而擴大改動面。

## 六、風險與前提條件

| 風險 | 後果 | 防護／前提 |
|---|---|---|
| 版權／引用未裁定 | 技術可行但不可正式使用 | production 排程前 hard gate；由使用者／權責窗口裁示 |
| API key 洩漏 | 憑證風險 | env only；錯誤與 manifest 遮罩；測試檢查輸出不含 key |
| YNA 高頻超過預估 | 單輪頁數、字幕時間、人工作業量暴增 | 分頁到邊界、不截尾；記錄量與耗時；必要時調整「收錄判準」須另案裁決，不能暗中丟資料 |
| API quota／429／暫時失敗 | 當輪不完整 | exponential backoff 有上限；失敗不前進游標；下一輪 catch-up |
| 字幕 track 改名／缺失 | 無法形成可靠 `src_text` | deferred queue；description 不冒充字幕；YNA 可另取 ko 作精判 |
| auto-translate 誤譯 | TC／摘要誤判 | 明標 triage-only；重大／語意可疑項回 ko 精翻；保留 video URL/provenance |
| 發布時間欄位混用 | 窗口漏收或舊片混入 | 固定 precedence；timezone-aware；fixture 覆蓋 DST 無關但跨日／跨班必測 |
| 只用全域 checkpoint | 跳過輪或失敗輪被截斷 | 每站成功游標；成功後才前進 |
| ID 大寫化／流水號耗盡 | 去重失效、影片錯配、YNA 超過 99 | 新永久 ID 保留 suffix 大小寫；legacy 並存 |
| add-batch 部分 skip 仍 rc=0 | 以為成功而錯推游標 | finalize 在呼叫前完成 blocking preflight；apply 後解析 receipt／核對 added+already-existing 等於預期數，再准推游標 |
| 跨兩檔非原子交易 | state 已寫、cursor 未寫或反之 | 嚴禁 cursor-first；state-first 後 cursor 原子寫；失敗重跑靠 ID 去重 |
| 與掃帶鎖競爭 | 狀態檔互蓋或輪內自擋 | 同一輪、同一 lock owner；人工 apply 不帶 `--in-round`；只看鎖存在不 open |
| 手動觸發與排定輪次同站同時 `finalize --apply`（3.7） | 游標被較晚完成者覆蓋，較早完成那次的窗口尾端可能被誤判成未收 | 按站別各一把獨立輕量鎖 `s2-youtube-<site>.lock`（與 `.s2-scan.lock` 互不阻擋）；撞鎖直接報錯退出，不等待不重試 |
| YouTube 失敗拖累五站 | 既有交接延誤 | 排最後且瀏覽器先收工；站別失敗隔離、留警告、五站成果照常 render |
| 新來源未進統計／品質掃 | 看似入庫但報表漏算 | ID／render／通知／mark-ingested e2e 為上線必驗，不只測 add-batch |

## 七、驗收標準

### 7.1 單元與契約測試

- [ ] 新／舊 YNA、CNA ID 全部通過；videoId 大小寫 round-trip 不變；錯 source blocking。
- [ ] `CHECKPOINT_RE` 維持原樣，所有 item checkpoint 仍是 `MMDD-HHMM`；補跑文字不混入 checkpoint。
- [ ] playlist 跨至少三頁仍能抓到窗口下界；任何固定頁數截尾都會使測試失敗。
- [ ] playlistItems 與 videos 每個列出的欄位完成 mapping 測試，缺 join／錯 channel／壞 timestamp 不靜默消失。
- [ ] CNA en、YNA zh-Hant、無字幕、rolling 重複、空字幕全有 fixture。
- [ ] manifest 每筆最後必為 batch、skip 或 deferred；`counts` 等式成立，dropped 非零時禁止 apply。
- [ ] final wrapper 可被現行 `s2_state.py add-batch` 接受，`platform`、`src_text`、category、tc 落檔；同 ID 重送不新增。
- [ ] legacy NS／AP／RT／ENEX／ABC／人工 YNA/CNA URL 測試無回歸。

### 7.2 窗口與故障測試

- [ ] 01:00／20:00 觀察到零 API call、零字幕 call、零候選、游標不變。
- [ ] 正常 22:00→04:30、17:00→22:00 窗口全收；10 分鐘重疊不重複入庫。
- [ ] 任一應掃輪失敗後，下輪從最後成功游標 catch up；測試資料中不漏任何 video ID。
- [ ] add-batch 失敗游標不動；cursor 寫失敗只造成可安全重試，不造成漏收。
- [ ] 新日 17:00 換 state file 後，游標延續且跨班重疊無重複。

### 7.3 沙箱與正式輪驗收

- [ ] API raw 筆數＝窗口內＋窗口外緩衝＋明列異常；不得有無法解釋的數量差。
- [ ] batch ready＋skip＋deferred＝窗口內去重後總數。
- [ ] 抽查每站至少 10 則：影片 ID、頻道、發布時間、標題、時長、字幕語言、watch URL 全對。
- [ ] YNA `src_text` 清楚標示自動翻譯初判性質；需要精判的抽樣可由同 video ID 回取 ko。
- [ ] render 後 YNA／CNA 素材行、檔頭則數、來源排序、HTML source 標籤一致；品質掃沒有因新 ID 靜默跳過。
- [ ] 連續三個應掃輪：零漏收、零重複入庫、零錯 checkpoint、零未解釋 dropped；deferred 每輪有可追蹤去向。
- [ ] YouTube 任一站故障時，NS／AP／RT／ENEX／ABC 仍正常收工、render 與通知，且 YouTube 游標未越過故障窗口。
- [ ] 每日 Data API 使用量有記錄；以 D23 估算為基準觀察，但實際上線門檻以「分頁完整、不漏收」優先，不為壓配額暗中少抓頁。

## 八、回滾與停手條件

- 規則與 launcher 用獨立 commit；bridge／schema／測試分小提交。任一階段不通過只回滾該階段，不動既有五站。
- 關閉接線的最小回滾是：移除 launcher 對 CNA／YNA 的呼叫並保留游標／raw 供查核；不得刪游標後假裝沒掃過。
- 出現下列任一情況立即停手、不前進游標：分頁未越過窗口下界、API 回應缺頁／缺 video join、channel ID 不符、checkpoint 非法、ready item 未全量 accounted、add-batch preflight blocking、正式 state 路徑不明、人工模式偵測到掃帶鎖。
- 版權裁示未完成、API key 未以安全方式配置、YNA/CNA 新 ID 尚未通過全套 parser/render 測試，任一項未滿足都不得正式上線。

## 九、最終建議

D23 的站序與五輪安排可以採用；`playlistItems.list`＋`videos.list`＋字幕也能明確映射到 `add-batch`。但前案「另開 bridge、直接接 batch、其餘不動」少算了兩個 production 級相容問題：現有兩位數 URL ID 不適合高頻且無法穩定去重，以及全域 checkpoint 無法表示 YouTube 特有跳過輪與前輪失敗。

建議核准的版本是：**獨立 `s2_youtube_bridge.py`，不進 `SITE_SPEC`、不擴充 ENEX／ABC 三件套；先補永久 video ID seam，再以每站成功游標實作 at-least-once 窗口，最後輸出現行 add-batch wrapper。**這個方案讓 YouTube 特有複雜度集中在單一 adapter，既有五站只需在收工尾端多一個隔離呼叫點，回滾面最小。
