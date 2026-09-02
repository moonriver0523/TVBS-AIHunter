# 側錄 TC 修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 `TC要修` 資料夾的 7 支 CNN／NHK 側錄，使用檔內既有正確 TC，直接以兩行式 SIDE 項目新增至 `0901-s2-state.json`。

**Architecture:** 不重新計算 TC、不用 `patch-entry`／`update-entry`。先把 7 支全文轉為 S2b C 軌可解析的候選文字，通過 `add-side --dry-run` 後，備份正式狀態檔並以 `add-side` 寫入，最後全量 render 並逐筆驗證。

**Tech Stack:** Python 3、`scripts/s2_state.py`、`scripts/s2_render.py`、JSON 狀態檔。

## Global Constraints

- TC 一律沿用 7 支 `_TC中文大段翻譯.txt` 正文中的現有起始 TC，不得由檔名重新推算。
- 新增項目來源限定 `SIDE_CNN`／`SIDE_NHK`；不得覆寫既有 313 則項目。
- `raw_entry` 必須是來源內容的逐字複製；只允許把既有角色標示移到 TC 行，或依 S2b C-4 三種明確依據補強 SUPER。
- 先 dry-run；寫入前備份 `0901-s2-state.json`；寫入後執行全量 render。
- `CNN 170522` 與 `CNN 161835` 的 Tupac Shakur 重播不得重複完整收錄。

---

### Task 1: 製作並獨立審核側錄候選

**Files:**
- Read: `G:\我的雲端硬碟\Autopilot\(掃帶歐印萬) 檔名取TC起頭 6位數\TC要修\*.txt`
- Create: `G:\我的雲端硬碟\Claude共用\自動掃帶系統\20260901-side-tc-correction-candidate.txt`

**Interfaces:**
- Consumes: 7 支完整 TC 中文大段翻譯。
- Produces: S2b C 軌格式的「擬歸位」區塊，每個內容段都是 `來源 MM-DD 6碼 （SUPER）` 加內容行。

- [ ] **Step 1: 擷取現有 TC 與內容行**

  只讀以下 7 支來源：`CNN 161835`、`CNN 163318`、`CNN 170522`、`CNN 175557`、`NHK 180012`、`NHK 181116`、`NHK 182203`；TC 取各正文段落現有起點。

- [ ] **Step 2: 建立候選文字**

  依主題建立擬歸位區塊，內容行從來源段落原封複製。`CNN 170522` 的 `17:06:00` Tupac 段不收，以避免和 `CNN 161835` 的完整判決段重複。

- [ ] **Step 3: 執行獨立審核**

  核對每一段的 `來源／日期／6 碼 TC／SUPER／內容` 對來源逐字一致；確認每區塊附有效 T/C；確認沒有收錄 `CNN 170522` 的重播 Tupac 段。

- [ ] **Step 4: 以 add-side dry-run 驗證可解析性**

  Run:
  ```bash
  python "E:/GitHub/TVBS-AIHunter/scripts/s2_state.py" --file "G:/我的雲端硬碟/Claude共用/自動掃帶系統/0901-s2-state.json" add-side --txt "G:/我的雲端硬碟/Claude共用/自動掃帶系統/20260901-side-tc-correction-candidate.txt" --checkpoint "0901-2000" --normalize --dry-run
  ```
  Expected: 所有候選段落均被解析；無日期、TC、來源或內容格式錯誤。

### Task 2: 安全寫入狀態檔並渲染

**Files:**
- Backup: `G:\我的雲端硬碟\Claude共用\自動掃帶系統\0901-s2-state.json.bak-20260901-side-tc-correction`
- Modify: `G:\我的雲端硬碟\Claude共用\自動掃帶系統\0901-s2-state.json`
- Modify: `G:\我的雲端硬碟\Claude共用\自動掃帶系統\0901晚班交接.txt`

**Interfaces:**
- Consumes: 已通過 dry-run 的候選檔。
- Produces: 新增的 `SIDE_CNN`／`SIDE_NHK` 項目與從狀態檔全量投影的新交接檔。

- [ ] **Step 1: 建立狀態檔備份**

  完整複製原始 `0901-s2-state.json` 至指定備份檔，並比較檔案 SHA-256 相同。

- [ ] **Step 2: 寫入側錄項目**

  Run:
  ```bash
  python "E:/GitHub/TVBS-AIHunter/scripts/s2_state.py" --file "G:/我的雲端硬碟/Claude共用/自動掃帶系統/0901-s2-state.json" add-side --txt "G:/我的雲端硬碟/Claude共用/自動掃帶系統/20260901-side-tc-correction-candidate.txt" --checkpoint "0901-2000" --normalize
  ```
  Expected: 僅新增候選中的 SIDE 項目；不得出現 overwrite。

- [ ] **Step 3: 寫入後檢查新增項目**

  Run:
  ```bash
  python "E:/GitHub/TVBS-AIHunter/scripts/s2_state.py" --file "G:/我的雲端硬碟/Claude共用/自動掃帶系統/0901-s2-state.json" show --checkpoint "0901-2000" --fields "id,source,raw_entry,category,tc"
  ```
  Expected: 新項目的 TC、內容、三層分類、T/C 與候選檔一致。

- [ ] **Step 4: 全量 render**

  Run:
  ```bash
  python "E:/GitHub/TVBS-AIHunter/scripts/s2_render.py" --file "G:/我的雲端硬碟/Claude共用/自動掃帶系統/0901-s2-state.json" --out "G:/我的雲端硬碟/Claude共用/自動掃帶系統/0901晚班交接.txt"
  ```
  Expected: render 成功，側錄項目出現在交接檔，既有通訊社與側錄內容仍存在。

### Task 3: 最終獨立驗證與回報

**Files:**
- Read: 備份、狀態檔、候選檔、`0901晚班交接.txt`。

**Interfaces:**
- Consumes: 寫入後的完整狀態檔與原始備份。
- Produces: 可稽核的新增數、TC 範圍、去重決策與異常清單。

- [ ] **Step 1: 比較非新增項目**

  以 id 與完整 item JSON 對照備份，確認僅本批新增 SIDE 項目有所不同。

- [ ] **Step 2: 比較逐字內容**

  對每個新增項目將 `raw_entry` 的內容行與候選檔逐行比較，確認無人工改字。

- [ ] **Step 3: 回報**

  回報新增支數／素材數／段數、每支 TC 範圍、捨棄的重複或交接語、T/C 未標項目（若有）及 render 結果。
