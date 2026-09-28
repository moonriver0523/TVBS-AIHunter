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
- 01:00／20:00 不掃 CNA／YNA，其餘 04:30／07:30／11:00／17:00／22:00 共五輪掃描。
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
| 07:30 | ✅ | ✅ | NS→AP→RT→ENEX→ABC→CNA→YNA |
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
    "entry": "YNA-AbCd_ef-123 (韓聯社 記者報導) (BITE) ▎摘要句，150字內，不得省略號代摘要。▎畫面：具體鏡頭描述、具體鏡頭描述、具體鏡頭描述。▎BITE：主播 OS 全程可用▎01:35\n▎URL：https://www.youtube.com/watch?v=AbCd_ef-123",
    "category": {"大分類": "政治", "中主題": "...", "小分題": "新聞標題式短句，不得超譯原文"},
    "tc": {"T": ["政治"], "C": ["南韓"]}
  },
  "YNA-XyZ987_ab-c": {"skip": "具體排除理由（不得只寫片長；要講跨議題無單一主軸、與既有稿重複等實質理由）"}
}
```

**2026-09-21 使用者裁決訂正（第一輪沙箱候選實測 + Codex(gpt-5.6-sol) 稽核 + 使用者現場糾正後回填，取代舊版含糊範例）：**

- **entry 標頭**：`{id} ({媒體中文名，YNA=韓聯社／CNA=CNA} 主播讀稿／記者報導／專題) (BITE)`；「專題」用於長篇單一主題節目（見下方「長篇不因片長排除」）。
- **摘要句**：完整句子、句號結尾，**不得用省略號帶過**；**150 字硬上限**（13c2 既有規則對 D23 同樣適用），超過要分句或把細節移到畫面段，不因為是長專題就破例。
- **畫面段**：至少 2-3 項具體鏡頭描述（如「國會質詢畫面、朝野立委發言、記者會畫面」）；**禁止寫「無」**這種空泛占位——YouTube 來源沒有自己補拍的畫面，也要依內容合理推想可用鏡頭，不能空著。
- **BITE 段**：
  - 稿內有明確可掐引言（`src_text` 標出講者與引號內容）時，**BITE 欄只寫中文翻譯，不得夾帶韓文／英文原文**；格式為「講者（身分）：『中文譯文』」。
  - 沒有明確可掐引言、通篇是主播／記者旁白時，寫「主播 OS 全程可用」或「記者 OS 全程可用」。
  - 不得無中生有／超譯來源沒有明講的細節（如把「有貢獻」寫成「助攻」、把「香港政要」寫成「多國政要」）——內容必須可回查 `src_text`。
- **結尾**：`▎{時長 MM:SS}\n▎URL：{platform.url 原樣}` 必加，時長與 URL 一律取自 manifest 的 `platform`／`duration`，不得人工重算或省略。
- **category**：三層 `{"大分類","中主題","小分題"}`；**大分類用實際編輯分類**（政治／社會／財經／科技醫藥／娛樂藝文／體育／話題等，比照 `common/plans/a10-p0-data/TC-字典.md` 的 T 軸 12 類精神），**不得用「國際」當萬用分類**；小分題是新聞標題式短句，內容不得超出摘要與 `src_text`。
- **tc.T／tc.C**：**唯一依據 `common/plans/a10-p0-data/TC-字典.md`**，不得自造名稱（例：影劇類新聞要標 `娛樂藝文` 不是 `影劇`；「話題」不准收硬新聞；地緣 C 依字典專項規則，例如港澳併入「中國大陸」、賽事實際發生地是歐洲時南韓球員新聞要加掛「歐洲」）。字典若有更新，這條規則自動跟著字典走，不在本文件重複列舉。
- **長篇不因片長排除，但棚訪／座談節目不收（雙判準，2026-09-21 Codex(gpt-5.6-sol) 稽核＋使用者裁決細化）**：
  1. **內容門檻**：必須是單一事件／單一主題，有可查證的完整來源文字。
  2. **形式門檻**：以採訪、旁白、素材畫面編排構成的**敘事型**新聞專題可收（例如地方發展、產業現象等單一主題專題），收錄為「(媒體 專題)」，摘要／畫面／BITE 規則同上（含 150 字摘要上限，細節移畫面段）；以**棚內主持人與來賓來回對話為主體**構成的節目（如「여의도1번지」政論節目、「이슈ZIP」深度追蹤特輯這類節目式長片）**一律 skip**，不論是否單一主題——判準是形式（棚內對話 vs 敘事編排），不是主題數量；專題裡嵌入受訪 BITE 不算棚訪節目，只有整支片以棚內對話推進才算。`skip` 理由要寫實質原因（如「政論棚訪節目，橫跨N個議題無單一主軸」），不能只寫片長；skip 前先看是否已有其他更短則覆蓋了同一事件的核心事實，若有就在理由中註記「核心事實已由 {id} 收錄」。
- **同主題重複只收一則（本規則限 YNA 站；CNA 更新頻率低、重複情況少見，暫不套用，之後若觀察到 CNA 也有同題重複再另行裁決是否比照）**：同一時間窗內、同一新聞事件若被切成多支 YNA 影片（跟播、後續反應、[속보]先行快報、[앵커리포트]短評等），**先做「實質新增資訊」測試**——若某一則比其他則多了新事實、新官方回應、新當事人說法、新可用 BITE 或不同關鍵畫面，視為**互補內容**，兩則都收，不算重複；只有核心事實與可用素材**實質相同**的才算真重複。判定為重複時，保留規則依序：①先排除字幕不完整或不具收錄資格的候選；②在剩餘候選裡選**核心事實最完整、可用畫面／BITE 最充分**的一則；③完整度相當才比 `published_at_utc` 較晚者；④**不得只用片長本身推定完整度**。其餘標 `skip`，理由寫「重複主題，已收於 {保留的id}」。**保留稿必須確定會形成可套用的 entry（或已存在 state）才能 skip 其餘**；若保留稿本身因字幕失敗等原因進了 `deferred`，其餘同事件候選**不得**因此被 skip 掉——改收次佳、但確定可用的一則，避免整個事件當輪零收錄。不同事件即使關鍵字重疊（如同人物、同機構的不同新聞）不算重複，仍要各自收錄。
- **TC 字典缺值時**：不得自造新名稱，也不得為了通過驗證硬塞明顯不合的類別；先在現有 `TC-字典.md` 條目中選**最接近的既有值**填入完成 decisions，並在交接／回報時明確標註「此則暫用最接近值 X，需人工校正」，待使用者裁決後再回頭修正該筆與（必要時）更新字典本身。
- **category／tc 必填、且 final batch 只接受物件形式**：只要 decisions 該筆是 `entry`（非 `skip`），`category`／`tc` 都是必填欄位；`finalize` 產出的 final batch 一律把兩者正規化為本節開頭範例的三層物件／`{"T":[...],"C":[...]}` 物件，3.6 表格所稱「可用路徑字串／字串」只能是人工輸入時的簡寫，`finalize` 必須解析、驗證後轉成物件寫入 final batch，不得原樣輸出字串。
- **entry 與 skip 互斥（XOR）**：同一 ready item 的 decisions 必須恰有 `entry` 或 `skip` 其中之一，兩者同時出現或都缺，`finalize` 一律 blocking exit 2。重複 skip 理由裡引用的保留 id，`finalize` preflight 必須驗證其存在於同一批的 ready entries、或已存在於正式 state，否則同樣 blocking——不得引用被排除、deferred 或不存在的 id。

**entry 唯一 canonical 模板（逐字標明分隔符位置，避免各自理解換行／空格）**：

```
{id} ({媒體標籤}) (BITE) ▎{摘要句，句號結尾}。▎畫面：{鏡頭1}、{鏡頭2}、{鏡頭3}。▎BITE：{BITE內容}▎{MM:SS}
▎URL：{watch URL}
```

- `{id}` 後恰一個半形空白接 `({媒體標籤})`，媒體標籤與 `(BITE)` 之間恰一個半形空白。
- `▎摘要`／`▎畫面：`／`▎BITE：` 三段依序出現，`▎` 前後不加空白；`▎畫面：` 段以「、」分隔各鏡頭、句號收尾。
- `▎{BITE內容}` 後直接接 `▎{MM:SS}`，同一行不換行；`{MM:SS}` 後才換行（`\n`）接 `▎URL：`。
- 全形標點只用在中文敘述本身（，。「」）；`▎`、URL、`MM:SS` 一律半形字元。

`finalize` 必做全量對帳：manifest 內每個 ready item 都必須在 decisions 中有 `entry` 或非空 `skip`；缺判斷列為 `dropped` 並 exit 2，不產可 apply 的 batch。`skip` 不進 batch，但要留在 receipt／counts，證明不是漏判。

### 3.6 final batch 逐欄契約

| add-batch 欄位 | 來源 | 規則 |
|---|---|---|
| `id` | `source + "-" + videoId` | YNA／CNA 前綴固定；videoId 保留大小寫；同批不得重複 |
| `source` | CLI `--site` 設定 | 只可 `YNA` 或 `CNA`；不可寫 `YT` |
| `checkpoint` | 本輪 run context | 嚴格 `MMDD-HHMM`；不把 `-YNA`／`-補掃` 接在此欄 |
| `status` | 字幕可用性 | ready 固定 `has_script`；字幕暫時失敗不入此批，改列 deferred |
| `entry` | 人工 decisions | 非空字串；首碼必須與 `id` 完全一致；不得自帶時段標記；撰寫細則見上方 3.5「2026-09-21 使用者裁決訂正」（畫面/BITE不得空泛、BITE不得夾原文、150字摘要上限、URL 必加、category/tc 依字典） |
| `src_text` | 正規化字幕 | CNA 英文 ASR；YNA `zh-Hant` 初判字幕；不可缺、不可用 description 代替 |
| `category` | 人工 decisions | entry 存在時必填；人工可簡寫字串，`finalize` 必須解析驗證後正規化為三層物件寫入，不得原樣輸出字串 |
| `tc` | 人工 decisions | entry 存在時必填；人工可簡寫字串，`finalize` 必須解析驗證後正規化為 `{"T":[...],"C":[...]}` 物件寫入；YNA／CNA 來源預設仍由現行 pretag 輔助，不代替人工確認 |
| `sb_count` | 字幕機械分析（若可靠）或省略 | 不可把未知硬填 0；若字幕格式不足以可靠計數就省略 |
| `platform` | collect manifest | 保存影片 provenance、發布時間、時長與字幕精度 |
| `suggest` | bridge 呼叫既有 pretag（可選） | 純提示，`add-batch` 不保存；失敗不得影響入庫 |

輸出一律是 `{"entries": [...], "new_topics": {...}}`。`finalize` 在任何副作用前，先用 `s2_material_schema` 的 pure validation、素材行 lint 與全量對帳完成 preflight；不得等 `add-batch` 逐筆 skip 後才發現整批 schema 不相容。

### 3.7 獨立於五站之外的手動觸發機制（使用者 2026-09-20 提出，2026-09-20 二次訂正）

> **⛔ 2026-09-21 使用者裁決（訂正）：只拿掉「五站自動排程去觸發 CNA／YNA 收錄」這一段，「排定輪次順手整併 `_待整併/` 候選入庫」這段維持原設計、照舊要接。** 兩件事分開講：
> 1. **不接**：Phase 5／3.1 講的「排定輪次自動呼叫 `s2_youtube_bridge.py collect`／`finalize --apply --in-round` 去主動掃 CNA／YNA」——這部分維持 `scripts/s2_scan_prompt.md` 既有的 Phase 5 dry-run 限制（只列印命令計畫，不呼叫 bridge、不碰 state／cursor、不連外、不改 `s2_scan.ps1`），**不放寬**。D23 目前仍只能靠人工／agent 手動呼叫 `collect`／`finalize` 產生候選檔（見下方命令），排定輪次不會自己主動去抓新的 YNA／CNA 資料。
> 2. **照舊要接**：下面「排定輪次多一個檢查點」段落講的「排定輪次在自己收工／整併步驟裡，檢查 `_待整併/` 底下有沒有 `*.apply-batch.json` 候選，有就在同一鎖窗口內套用入庫、成功後歸檔」——這個**維持原設計，不拿掉**，就跟現行排定輪次整併人工 URL 素材候選（`_待整併/` 已有的機制）用同一套邏輯，YNA／CNA 候選檔只是內容換成 bridge 產出的結構化 batch，入庫路徑不變。

**設計目標**：CNA／YNA 除了掛在既有五站輪次尾端（3.1／Phase 5）之外，要能**不必等下一個排定輪次、也不必等整個五站輪跑完**，隨時單獨補開一次 CNA／YNA 掃描。

**⚠️ 本節初版設計錯誤，已訂正**：初版讓手動觸發直接對正式 `{MMDD}-s2-state.json` 呼叫 `finalize --apply`（只是省略 `--in-round`），使用者指出這違反 repo 既有慣例、有資料靜默遺失風險，已採用者建議的做法改寫。

**根因（跟現行 `_待整併/` 機制是同一個坑）**：`common/17-網址素材整併.md` §1 講得很明白——**「不要改狀態檔，那個檔沒有檔案鎖，寫入的當下若掃帶輪正在寫回，那幾則會靜靜消失且不會報錯」**。手動觸發跟排定輪次是兩個獨立行程，沒有共用鎖（bridge 本來就刻意不搶 `.s2-scan.lock`），若手動觸發直接 `add-batch` 進正式 state，跟排定輪次同時寫入時就是這個坑本身，光靠一把新的按站別鎖檔只能防「兩次手動觸發互撞」，防不了「手動觸發撞上正在跑的排定輪次」——排定輪次執行期間完全不會去讀／尊重這把新鎖檔。

**修正設計：手動觸發只做到 `collect`＋`finalize`（不帶 `--apply`），輸出一份候選 batch 檔放進既有 `_待整併/` 目錄，實際寫入 state 的動作交給下一個排定輪次在它自己持有 `.s2-scan.lock` 的單一寫入窗口內代勞**——跟韓聯社／CNA 網址素材（人工整理）用同一套現行整併機制，只是候選檔內容從「人工手打的素材行文字」換成「bridge 產出的結構化 batch JSON」：

```powershell
# 手動補掃 CNA：只到 collect + finalize（不 --apply），輸出候選檔
python scripts/s2_youtube_bridge.py collect --site cna `
  --checkpoint 0920-1234 `   # 嚴格 MMDD-HHMM，手動觸發用實際觸發時刻，不得用「-manual」等後綴（2026-09-21 訂正：程式已強制此格式，舊範例的 0920-manual 會被拒絕）
  --state "...\0920-s2-state.json" `
  --cursor "...\s2-youtube-cursors.json" `
  --out "...\_待整併\0920-1234-YNA_CNA候選-cna.manifest.json"      # 原始 manifest／raw

python scripts/s2_youtube_bridge.py finalize `
  --manifest "...\_待整併\0920-1234-YNA_CNA候選-cna.manifest.json" `
  --entries "...\cna_youtube_entries_manual.json" `
  --out "...\_待整併\0920-1234-YNA_CNA候選-cna.apply-batch.json"   # ready-to-apply batch，不 --apply
  # 不帶 --apply、不帶 --in-round：finalize 在手動模式下只產檔，
  # 完成 3.6 講的全量對帳／preflight，確保候選檔本身就是「乾淨、可直接套用」的狀態，
  # 但實際套用動作留給下一個排定輪次
```

**2026-09-21 補（Codex(gpt-5.6-sol) 稽核＋使用者裁決「B 類全做」）：**

- **手動 `collect` 必帶 `--checkpoint`**：值封存進 manifest 後不得被套用階段改寫；跨日候選套用到新一天的 state 時，`checkpoint` 仍沿用產出當下的值（代表實際收錄的時間點），不得改成套用當下的輪次 checkpoint——套用輪次自己的 `collect`／`finalize --apply --in-round` 才用套用當下的 checkpoint。
- **manifest 與 apply-ready batch 用不同副檔名區分，杜絕誤讀**：manifest／raw 一律 `*.manifest.json`，經 `finalize` 產出、preflight 通過、可直接套用的候選一律 `*.apply-batch.json`；排定輪次的「檢查 `_待整併/`」步驟只掃 `*.apply-batch.json`，不得誤把裸 manifest 當成候選套用。
- **候選檔命名：原子建立新編號檔，不覆寫既有候選（統一取代前版「append／開新檔」兩種矛盾說法）**：檔名固定帶 `{MMDD}-{HHMM或流水號}-YNA_CNA候選-{site}.apply-batch.json`；若同名已存在，一律改用下一個可用編號另存新檔，**不 append、不覆寫**既有候選內容——JSON 結構化檔案沒有安全的「append」語意，追加只能靠開新檔案達成。
- **候選 envelope 必須帶完整可重播資訊，不能只有 `{"entries":[...], "new_topics":{...}}`**：`finalize`（無論是否 `--apply`）產出的 apply-batch 檔，除了現有 `entries`／`new_topics`／`receipt` 之外，還須額外保存：
  - `site`
  - 產出當下讀到的 cursor `revision` 與 `last_complete_end_utc`（產出時的游標前值）
  - `window`（`lower_exclusive`／`upper_inclusive`，即這份候選實際涵蓋的窗口）
  - manifest 的 checksum（或直接保留 manifest 路徑供事後核對）
  - `deferred_video_ids`（這份候選裡確認 deferred 的影片，供排定輪次合併進 cursor 的 deferred 佇列）
  排定輪次套用前要能靠這些欄位判斷：這份候選對應的窗口跟目前 cursor 是否銜接、有沒有過期或跟其他候選重疊。
- **游標推進規則：只能取「已完整覆蓋之連續窗口的最大終點」，不得倒退、不得跳過中間缺口**：排定輪次若同時撿到多份候選（例如兩次手動觸發前後腳各出一份），依 envelope 裡的 `window`／cursor revision 排序後，只有當候選窗口與目前 cursor 的 `last_complete_end_utc` **相接或重疊**時，套用後才把 cursor 推進到該候選的 `window.upper_inclusive`；若候選窗口比目前 cursor 還舊（revision 過期）或跟目前 cursor 之間有未覆蓋的缺口，**仍可套用其 `entries`（靠永久 ID 去重，不會重複入庫）**，但**不得**用它去覆寫／推進 cursor，缺口要留給下一輪的正常 `collect` 從目前 cursor 續抓補齊。
- **套用候選的 CLI 入口要明確、不能跟「讀 manifest+decisions」的一般路徑混用**：`finalize --apply` 現行介面吃的是 `--manifest`＋`--entries`（decisions），`--file` 一律只代表 state 路徑；套用「已經是完成品的 apply-batch 候選檔」是不同語意，**必須另開一個子命令**（例如 `s2_youtube_bridge.py apply-batch --batch <候選檔> --file <state> --cursor <cursor檔> --in-round`），內部直接呼叫既有 `s2_state.py add-batch`，並用候選 envelope 裡的 window／revision 資訊做上一條的游標推進判斷；不得讓排定輪次誤用 `finalize --apply --file <state>` 卻把候選檔塞進 `--file`。

**排定輪次多一個檢查點**：CNA／YNA 站在收工步驟（Phase 5）除了做自己那份正常 `collect`／`finalize --apply --in-round` 之外，**開工時先檢查 `_待整併/` 底下有沒有待套用的 `*.apply-batch.json`**，有的話依上述游標推進規則排序、在同一個鎖 session 內用 `apply-batch` 子命令逐一套用，套用成功後把候選檔（及其對應 manifest）原地改名加 `已入庫_` 前綴（跟 `common/13`「_待整併/」節、`s2_mark_ingested.py` 認的慣例一致，2026-09-25 訂正：初版寫成搬進 `已整併/` 子目錄，跟 0816 那次「已整併 {原檔名}」誤改名是同一個錯，已改回原地改名），失敗則保留候選檔、留到下一輪重試——這一步邏輯上等同 `13c3` §4b「整併 `_待整併/` 的批次」，只是候選內容從人工文字改成本 bridge 產的結構化 batch。

**這樣設計後**：
- 手動觸發**不需要**額外的按站別鎖檔（3.6 初版提的 `s2-youtube-<site>.lock` 可以拿掉）——候選檔用上面的「原子開新編號檔」規則寫入，不會有跟排定輪次搶寫同一份正式 state 的風險，因為手動觸發**從不直接碰 state**。
- 游標（`s2-youtube-cursors.json`）**只在候選檔被排定輪次真的套用成功、且窗口與現有 cursor 銜接時才前進**，不在手動觸發的 `collect`／`finalize` 階段前進、也不會被過期或跳空的候選覆寫——避免手動觸發抓了窗口、候選檔卻遲遲沒被排定輪次撿起來套用（例如人工忘記觸發下一輪、或候選檔一直沒通過 preflight）時，游標卻已經往前跳、造成該段窗口實質上永久漏收又查不出來。
- 兩次手動觸發前後腳跑，可能各自產生一份候選檔、內容有重疊——**內容層面不需要特別防呆**，因為套用階段仍然是靠永久 ID（`YNA-<videoId>`／`CNA-<videoId>`）去重，重疊項目套用第二次會被 `add-batch` 正常跳過，不會造成重複入庫，只是白跑一次 API／字幕成本；但**游標層面**仍要照上面的規則判斷銜接與缺口，不能兩份候選都無條件推進游標。

**不在本次計畫書實作範圍內，留待未來排程整合階段裁決**：是否要額外幫「獨立手動觸發」建一支排程（例如另一個 Windows 工作排程器項目，讓 CNA／YNA 可以用跟五站不同的頻率獨立跑 `collect`／`finalize`），或純粹作為人工/agent 臨時補跑用的 CLI 介面即可、不建排程。這是使用範圍的決定，不影響上面的技術設計。

## 四、分階段實作步驟

### Phase 0：裁示與基線凍結

- [ ] 使用者明確把 D23 從「待評估」改為「核准實作」；未裁示不得進 production 實作。
- [ ] 版權／引用原則取得權責窗口結論，至少確認：可否保存自動字幕、可否把影片內容作交接與後續寫稿依據、成品需要何種來源標示。
- [ ] 決定 API key 的環境變數名稱與部署位置；確認不進 repo、不進 prompt、不進 log。
- [x] **裁定 live／upcoming 影片處理規則並列為上線 hard gate（2026-09-21 補，Codex(gpt-5.6-sol) 稽核指出 3.4 只講「規則先定案再上線」卻沒被列進任何 gate；2026-09-21 使用者裁決、Codex(gpt-5.6-terra) 已實作並補測試）**：`liveBroadcastContent` 非 `none` 時，`upcoming`（預告片）一律 `deferred`；`live`（直播中）**維持現行既有行為：永久 `skip`，不重試**（不做「直播結束後重試」的額外邏輯，避免直播內容不穩定或延續數小時造成重複處理複雜度）。
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

- [x] 先寫逐欄 fixture：一筆 YNA、一筆 CNA、一筆 skip、一筆 decisions 遺漏、一筆錯 checkpoint、一筆 ID/source mismatch。
- [x] decisions keyed object → final wrapper；`entry/category/tc` 來自人工，`src_text/platform/checkpoint/source` 只能來自可信 manifest，人工檔不得覆蓋。
- [x] 所有 ready item 必須 accounted；任何 dropped／重複／錯 ID 都 exit 2 且不產 apply-ready 檔。
- [x] wrapper 固定帶 `new_topics`；驗證既有 add-batch 新題 gate 可運作。
- [x] 用臨時 state file 執行真 `s2_state.py add-batch` subprocess e2e：欄位完整落入 state、同 ID 重送只跳過、不產第二筆、YNA／CNA source preserved。
- [ ] `--apply` 預設關閉；沒帶 `--file` 拒絕；`--in-round` 只略過「自己持有鎖」的檢查。**2026-09-21 訂正（Codex(gpt-5.6-sol) 稽核）**：鎖規則限縮為「任何直接寫正式 state 的非輪內 `--apply` 遇 `.s2-scan.lock` 必須拒絕」；純 `collect`／`finalize`（不帶 `--apply`，只產候選檔到 `_待整併/`）**不受** `.s2-scan.lock` 影響、鎖存在也照跑——3.7 已訂正為手動觸發從不直接寫 state，若這裡仍寫「人工模式遇鎖檔拒絕」會跟 3.7 的整個修正方向矛盾。

### Phase 4：游標交易順序與故障恢復（TDD）

- [x] 模擬 add-batch 失敗：游標完全不動。
- [x] 模擬 add-batch 成功、游標寫入失敗：重跑會因永久 ID 去重，不會重複入庫，也不漏收。
- [ ] 模擬 01:00／20:00 跳過、22:00 成功、04:30 執行：窗口涵蓋 22:00 後全部內容。
- [ ] 模擬 22:00 失敗：04:30 從 17:00 的最後成功終點續抓，不得從名義 22:00 截斷。
- [ ] 模擬 17:00 新日狀態檔：固定游標仍延續，10 分鐘重疊不造成跨班重複素材。
- [ ] 模擬字幕 deferred：時間游標可在完整清單抓取後前進，但 deferred ID 留在重試佇列，下一輪先重試；未成功／未明確排除前不可消失。
- [ ] 模擬手動觸發候選檔（3.7）：`finalize`（不帶 `--apply`）產出的候選 batch 放進 `_待整併/`，下一個排定輪次的 `--in-round` 呼叫要能讀到並正確套用、套用後游標才前進；套用失敗時候選檔原樣保留供下一輪重試。

### Phase 5：規則與 launcher 接線（只在規則空窗）

**預計修改：**13c 對應 V9 規則、S2 prompt／launcher 必要指路、測試；實際檔名以動工當下 active V9 為準。

- [ ] 把本文輪次表寫進 active 規則，措辭沿用「本輪不掃…」「窗順延，不漏收只延後」。
- [ ] 13c 的 URL ID 說明拆成 legacy 人工網址 ID 與 scheduled YouTube ID；不得覆寫 legacy 規則。
- [ ] 在五站瀏覽器收工硬步驟之後、render／通知統計之前插入 CNA→YNA；兩站失敗各自留警告，不能中止既有五站收工。
- [ ] 01:00／20:00 只回報「本輪不掃 CNA／YNA（D23）」；不呼叫 bridge。
- [ ] 應掃輪在自己 `collect`／`finalize --apply --in-round` 之前，先檢查 `_待整併/` 有沒有待套用的 YNA/CNA 候選 batch（3.7），有就在同一鎖窗口內先套用、成功後歸檔或刪除候選檔，失敗則保留供下一輪重試。
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
| 新增候選檔慣例 | `_待整併/{MMDD}-YNA_CNA候選*.json`（bridge `finalize` 不帶 `--apply` 時的輸出位置） | 手動觸發（3.7）的結構化候選 batch，沿用現行 `17-網址素材整併.md` 的 `_待整併/` 慣例，由下一個排定輪次的 `--in-round` 呼叫代為套用；不新增鎖檔 |

明確不改：`s2_batch_prep.py` 的 `SITE_SPEC`、`s2_platform_extract.py`、`s2_platform_lint.py`、`s2_platform_merge.py`。除非實作時出現本文未涵蓋且有測試證明的硬相依，否則不得為「共用看起來比較整齊」而擴大改動面。

## 六、風險與前提條件

| 風險 | 後果 | 防護／前提 |
|---|---|---|
| 版權／引用未裁定 | 技術可行但不可正式使用 | production 排程前 hard gate；由使用者／權責窗口裁示 |
| API key 洩漏 | 憑證風險 | env only；錯誤與 manifest 遮罩；測試檢查輸出不含 key |
| YNA 高頻超過預估 | 單輪頁數、字幕時間、人工作業量暴增 | 分頁到邊界、不截尾；記錄量與耗時；必要時調整「收錄判準」須另案裁決，不能暗中丟資料 |
| API quota／429／暫時失敗 | 當輪不完整 | exponential backoff 有上限；失敗不前進游標；下一輪 catch-up |
| 字幕 track 改名／缺失 | 無法形成可靠 `src_text` | deferred queue；description 不冒充字幕；YNA 可另取 ko 作精判 |
| `yt-dlp` 被 YouTube bot 偵測擋下（`Sign in to confirm you're not a bot`，`common/17-網址素材整併.md` 記過的既有坑，抓文稿說明欄時曾發生；本次 D23 查證階段抓字幕當下未觸發，但正式環境高頻率／不同 IP 下風險未知） | 字幕階段整批失敗，`collect` 卡住或大量 deferred | 短期：字幕抓取失敗率超過閾值時整站降級為只出清單（無 `src_text`）、留 needs-review，不得整輪 abort；中期備援：改走已登入瀏覽器同源存取（比照 17 的 `fetch('/watch?v=…')` 手法），可用 claude-in-chrome 或既有 Playwright profile 執行，但**這是 bridge 從無瀏覽器依賴退化成有瀏覽器依賴的架構變動，需另案評估與使用者裁決，不在本次 Phase 0-5 範圍內先做**|
| auto-translate 誤譯 | TC／摘要誤判 | 明標 triage-only；重大／語意可疑項回 ko 精翻；保留 video URL/provenance |
| 發布時間欄位混用 | 窗口漏收或舊片混入 | 固定 precedence；timezone-aware；fixture 覆蓋 DST 無關但跨日／跨班必測 |
| 只用全域 checkpoint | 跳過輪或失敗輪被截斷 | 每站成功游標；成功後才前進 |
| ID 大寫化／流水號耗盡 | 去重失效、影片錯配、YNA 超過 99 | 新永久 ID 保留 suffix 大小寫；legacy 並存 |
| add-batch 部分 skip 仍 rc=0 | 以為成功而錯推游標 | finalize 在呼叫前完成 blocking preflight；apply 後解析 receipt／核對 added+already-existing 等於預期數，再准推游標 |
| 跨兩檔非原子交易 | state 已寫、cursor 未寫或反之 | 嚴禁 cursor-first；state-first 後 cursor 原子寫；失敗重跑靠 ID 去重 |
| 與掃帶鎖競爭 | 狀態檔互蓋或輪內自擋 | 同一輪、同一 lock owner；人工 apply 不帶 `--in-round`；只看鎖存在不 open |
| 手動觸發直接寫正式 state（初版設計錯誤，已訂正見 3.7） | 跟排定輪次同時寫、state 無檔案鎖，資料靜默消失，同 `17-網址素材整併.md §1` 的坑 | 手動觸發只到 `finalize`（不 `--apply`），輸出候選檔到 `_待整併/`；實際套用交給排定輪次在自己的鎖窗口內代勞 |
| 候選 batch 一直沒被排定輪次撿起來套用 | 游標卡在舊點、窗口實質漏收但查不出來 | 游標只在候選檔真的套用成功後才前進，不在 `collect`／`finalize` 產檔階段前進 |
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

## 十、正式上線開關（2026-09-20 使用者裁定）

> ⛔ **D23 排定輪次（CNA／YNA 隨五站排程自動掃）預設關閉，使用者下令才啟動。**

- 這不是新的技術限制，是既有現況的明文化：Phase 5 本來就只做 `s2_youtube_launcher.py --dry-run`，未接 `s2_scan.ps1`、未接 Windows 排程，本節只是把「之後要接的時候，預設值是 OFF」寫死，避免日後有人以為 Phase 6 測試完就等於可以自動接上。
- 開關生效範圍：**只管「排定五站輪次尾端自動觸發 D23」這件事**。人工手動觸發（`collect`＋`finalize`，不帶 `--apply`，輸出候選檔到 `_待整併/`）不受此開關限制，本來就是獨立於排程之外的路徑（見 3.7）；但候選檔要真的套進正式 state，仍要等一個排定輪次的 `--in-round --apply` 撿起來，而只要 D23 排定輪次本身是 OFF，就沒有任何排定輪次會執行那個撿取動作。
- 換句話說：在使用者明確下令開啟之前，**即使 `_待整併/` 裡放著候選 JSON，也不會被任何自動流程套用**——這是本開關與 3.7 候選檔機制疊加後的實際效果，不需要另外加鎖或旗標。
- 日後要開啟，需要使用者明確下令，且仍受本文件既有前提條件（`八、回滾與停手條件` 最後一段：版權裁示、API key 安全配置、新 ID 全套 parser/render 測試）約束，缺一不可。

## 十一、2026-09-20 Phase 6 實測記錄（腳手架階段，未授權正式上線）

以下是 Phase 6 腳手架完成後的三輪真實測試記錄，供之後接續工作參考；**全部發生在 worktree `feat/d23-youtube-bridge`，未 merge、未 push、未接排程**：

1. **`playlistItems.list` 修正**：Codex 腳手架誤用 `channelId` 參數（該端點無此參數），改用官方慣例推導 `playlistId`（`UC`→`UU`）。
2. **regionRestriction 排除**：`allowed` 不含 `TW` 或 `blocked` 含 `TW` 一律歸 `skipped`（reason=`region-restricted`），不進 `deferred` 重試佇列。真實測試中 CNA 頻道抓到多筆僅開放 `SG` 的影片，已正確排除。
3. **直播／Shorts 排除**（使用者 2026-09-20 裁定：只收一般影片）：
   - 直播（含已結束、`liveBroadcastContent` 已變回 `none` 的往日直播錄影，用 `liveStreamingDetails.actualStartTime` 判斷）一律 `skipped`（reason=`livestream-excluded`）。
   - Shorts 用 `youtube.com/shorts/<id>` 可達性判斷，一律 `skipped`（reason=`short-excluded`）；查不到時 fail-open（留 warning，當作不是 Shorts），不中斷整批。
4. **yt-dlp 字幕真實接通**：本機已裝 yt-dlp（`2026.08.18.122307`），CNA 用 `en/auto`、YNA 用 `zh-Hant/auto-translated`，VTT 解析與去重驗證正常，暫存字幕檔用畢即刪。
5. **端到端真實測試**（2026-09-20 18:30–20:30 台北時間窗，`--max-pages 3`）：CNA 0 筆 ready（3 筆全被地區限制／Shorts 排除）；YNA 3 筆 ready，字幕正常取得，人工依 `13e` 規則寫分類（大分類／中主題／T-C）後產生候選 JSON，存入 `_待整併/0920-YNA_CNA候選-{CNA,YNA}.json`（因本節開關 OFF，不會被任何排程套用）。
6. **已知缺口**：ready 項目的「畫面：」段目前只能寫「未看影片，僅依字幕文字稿判讀」佔位——D23 YouTube 素材沒有 AP／RT 那種 shotlist 可抄，要真的看畫面才能補齊，尚未決定要不要在 finalize 前一律插入 video_analyze 步驟。
