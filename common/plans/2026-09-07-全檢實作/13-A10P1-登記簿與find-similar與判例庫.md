# A10 P1：中主題登記簿（charter／aliases）＋ add-batch 新題閘門 ＋ find-similar ＋ 判例庫 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development。**分四個子計畫 P1a→P1d，各自 commit、各跑一個正式輪**。前置：08-T12、09-A24 已上線。D14 已裁決（2026-09-07）：D-a～D-g 依《分類系統化規劃》§3b 建議欄定案。

**Goal:** 解決「同一條新聞不同輪各開中主題、跨天異名」：①跨天登記簿讓 agent 看得到「這格收什麼」與別名；②`add-batch` 遇到登記簿沒有的中主題必須附 charter（硬閘）；③入庫前 `find-similar` 粗篩候選；④人工糾正落判例庫，CONFIRMED 才晉升規則。

**Architecture:**
- `scripts/s2_topic_registry.json`（單一真相源、跨天）：`{"topics":[{"name","charter","aliases":[],"big","tc":{"T":[],"C":[]},"first_seen","last_seen","resident":false}]}`。`s2_resident_topics.json` 的內容併入（`resident:true`），舊檔保留一個週期後退役。
- 寫入端正規化（比照 `normalize_c`）：`category.中主題` 命中 alias → 改寫成 canonical，並印改寫說明。
- 讀取端：`list-topics --compact` 每行加 `｜charter`，登記簿有但今天 0 則的**不印**（除 resident）。
- 判例庫 `scripts/s2_case_log.jsonl`：一行一筆 `{ts, id, summary, from:{big,mid,sub}, to:{…}, by:"user|reclass|audit"}`。
- ⛔ 不做內文模糊比對（不變式）；`find-similar` 只做名稱／charter／aliases／今日中小分題名稱的 2–4 字 token 重疊。

**Tech Stack:** Python；subprocess 測試。

## Global Constraints

- 「只併不改名」鐵律：canonical 名寫下就不改；改名＝加 alias。
- 登記簿改動只走子指令（`topic-register`／`topic-alias`），⛔ agent 不直接編 JSON（D9 同一精神）。
- 規則檔改動（13f）只在空窗，且是「把 0805 三判準從候選升為規則」＋登記簿用法兩段。

---

## P1a 登記簿＋charter＋alias 正規化

### Task 1: 測試
- Create `scripts/test_s2_topic_registry.py`：①`topic-register --name 美網 --charter "…" --big 體育 --aliases "美網戰報,美網賽事,網球"` → JSON 有一筆；②`set-category --pairs "X=體育/美網戰報"` → 狀態檔存 `美網`、stdout 印「美網戰報→美網（alias）」；③`list-topics --compact` 行尾有 charter；④同名再 register 只更新 charter 不重複；⑤`topic-alias --name 美網 --alias 網球公開賽` 追加。
- 跑 → FAIL。

### Task 2: 實作
- `s2_state.py`：`REGISTRY_PATH`、`load_registry()`、`save_registry()`；`cmd_topic_register`、`cmd_topic_alias`；`_set_one_category` 內在寫入前 `mid = canonical_of(mid)`（alias 命中就改寫、印說明）；`cmd_list_topics --compact` 帶 charter；`main()` 註冊兩個子指令。
- `resident_topics`：`load_registry()` 若 `s2_topic_registry.json` 不存在，從 `s2_resident_topics.json` 生成初始檔（烏打俄／俄打烏 `resident:true`，charter 取 13f 文字）。
- 測試 PASS；全套 PASS。

### Task 3: 初始資料
- 用近 11 天 Archive 狀態檔跑一支一次性腳本 `scripts/_registry_seed_20260907.py`：取出現 ≥2 天或 ≥8 則的中主題，人工（agent）合併同事件異名成 canonical（例：尼泊爾洪災 5 名、美網 4 名、克蘭西 2 名），charter 一句；輸出 `s2_topic_registry.json` 草稿 → **給使用者看過**再 commit。
- commit：`全檢/A10-P1a：中主題登記簿、charter、alias 正規化`；1 正式輪：transcript 有 alias 改寫訊息或 `list-topics` 帶 charter；無 needs-review 新增。

## P1b `add-batch` 新題閘門＋建檔輪參考清單

### Task 1: 測試
- batch 一則 `category:"體育/全新主題"`（登記簿沒有）且 batch 無 `new_topics` → 素材入庫、category **不寫**、stdout 印「🆕 未登記中主題：全新主題——請在 batch 頂層 `new_topics` 附 charter 或改掛既有格」；同 batch 帶 `"new_topics":{"全新主題":{"charter":"…","big":"體育"}}` → 自動 register＋寫 category。
- 建檔輪：`list-topics --yesterday` 印前一天 ≥3 則的中主題＋charter（讀 Archive 前一日狀態檔）。

### Task 2: 實作
- `cmd_add_batch`：`data` 可為 `{"entries":[…],"new_topics":{…}}`；先處理 `new_topics` → register；再逐則；未登記者 category 留空並列入「🆕 未登記」清單（不擋入庫，擋的是**沒 charter 就開名**）。
- `cmd_list_topics --yesterday`：找 `Archive/{前一日}/{MMDD}-s2-state.json`，列 ≥3 則者。
- 🔴 **其他產線過閘（沒這段不能上線）**：ENEX／ABC（`s2_platform_merge.py` 內部呼叫 `add-batch`＋`set-category`）、韓聯社／CNA／YouTube（`common/17` 交件檔）、側錄（`add-side`）的交件端**都沒有 `new_topics`**。處理：這三條路徑遇到未登記中主題 → **自動 register**，charter 取該中主題第一則 `fields.summary` 前 40 字，標 `auto:true`；收工清單（`13c2` §6）印「本輪自動登記 N 個中主題待補 charter：…」，由掃帶 agent 或使用者事後 `topic-register` 覆寫。`add-batch` 加 `--auto-register` 旗標給 merge 用；`add-side` 與 17 整併走同旗標。測試加一案：merge 路徑未登記名 → 自動登記、category 有寫、stdout 有「待補 charter」。
- 空窗改 `13c2` §5a 建檔輪七項加第 8 項「跑 `list-topics --yesterday` 當今天命名參考」；`13f`「開新中主題前必跑 list-topics」段加「開新名必附 charter（batch `new_topics`）」；0805 三判準改寫為規則句（D-d 已裁）。
- 測試 PASS；commit；1 正式輪：無「未登記」殘留到收工（agent 都補了 charter）。

## P1c `find-similar`

### Task 1: 測試
- 登記簿有「尼泊爾洪災」（aliases 含「尼泊爾水電廠隧道搜救」）；今日狀態檔有【中尼邊境洪災】；輸入 `--text "尼泊爾努瓦科特洪災搜救 隧道工人獲救"` → 候選前兩名為 尼泊爾洪災、中尼邊境洪災，附命中 token；輸入 `--text "德國地方選舉"` 對上述 → 印「無相似項」（不是空輸出）。

### Task 2: 實作
- `s2_state.py find-similar --text … [--top 5]`：token＝文本中所有 2–4 字連續中文子串（去停用字：的、了、與、及、和、在、於、對、被、將、已、仍、等），對「登記簿 name+aliases+charter」與「今日 mid+sub 名稱」算重疊字數（`_lcs_len>=2` 計 1 分、完全包含計 2 分），列前 N。
- `from-raw` 提示表（09-A24）每則多印 `≈{候選1}/{候選2}`（呼叫同一函式，不另開子指令）——這才是「入庫前」的位置。
- 測試 PASS；commit；1 正式輪：孤兒率較 P1a 前下降（記數字）。

## P1d 判例庫

### Task 1: 測試
- `set-category` 覆寫既有 category（不同 mid）→ `s2_case_log.jsonl` 追加一筆 `by:"user"`（`--by` 可指定）；`s2_apply_reclass.py` 套用 MOVE → 追加 `by:"reclass"`；`case report` 對三筆同型（from mid→to mid 相同）印 `CONFIRMED`，兩筆 `REPEATED`，一筆 `NEW`。

### Task 2: 實作
- `s2_state.py`：`_log_case()`；`cmd_case`（`report`／`add`）；`set-category` 在覆寫時呼叫；`s2_apply_reclass.py` 套用時呼叫（import）。
- `case report --confirmed` 輸出可直接貼進 `13f` 例外表的列（`| 類型 | 錯放 | 正解 | 次數 |`），上限 20 列；**晉升規則由使用者決定**，工具只印。
- 測試 PASS；commit；一週後看 `case report`：REPEATED 是否遞減。

## 驗收（全 P1）
- 指標（全檢 §1c 基線）：孤兒中主題比率 44–62% → <30%；跨天同事件異名數（近 11 天實例 3 組）→ 0；`case report` REPEATED 遞減。
- 3 連續正式輪無新增 needs-review、無 alias 誤改寫（人工抽查 10 則）。通過 → MASTER `A10` 改「P1 ✅／P2 待」。
