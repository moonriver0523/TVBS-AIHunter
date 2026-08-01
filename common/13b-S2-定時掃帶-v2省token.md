# S2 定時掃帶 V2（省 Token 執行版）——測試中

> **狀態：測試版（2026-08-01 建立）。**
> 本檔是 [`13-S2-定時掃帶.md`](13-S2-定時掃帶.md)（V1）的**執行層覆蓋規格**：內容格式、分類規則、素材行寫法、時區換算、RT 連掃鐵律等**全部沿用 V1**，本檔只改「怎麼執行」——目標是省 token 並讓低階 agent 也能不卡住地跑完。
>
> **啟用方式（測試期）**：使用者指令明確說「用 V2」「省token版掃帶」時才走本檔；沒說就走 V1。
> **Rollback**：刪除本檔＋`scripts/s2_state.py`＋`scripts/s2_validate.py`，並撤掉 V1 檔頭的 V2 指標行即可，V1 未被修改過。
> **轉正**：測試穩定後，把本檔內容併回 V1、廢除雙軌。

## 與 V1 的差異總表

| # | 項目 | V1 做法 | V2 做法 | 預估省 |
|---|---|---|---|---|
| 1 | 詳情頁讀取 | 整頁 text／截圖 | **fallback 階梯＋硬字元上限** | ~60–80k/晚 |
| 2 | 狀態 JSON | agent 直接讀寫整份 | **`s2_state.py` 代管，agent 禁直讀寫** | ~70k/晚 |
| 3 | 品質掃／檔頭統計／三方比對 | agent 逐行掃 | **`s2_validate.py` 機器掃，只處理命中** | ~15–20k/晚 |
| 4 | SNTV 體育 | 開詳情寫完整三段式 | **`AP5` 白名單列表級收錄** | ~10–15k/晚 |
| 5 | 防卡設計 | — | resume／RT 斷點跳站／半夜禁問 | （穩定性） |

---

## 1. 詳情頁擷取：fallback 階梯＋硬上限

**階梯（固定順序，不准跳步、不准重試同一步）：**

1. 先用 `find`／選擇器抓 script 正文區塊與 Details 欄位（Edit No.／Duration／Restrictions／SOURCE）。
2. **失敗一次 → 立刻改整頁 `get_page_text`**。禁止重試選擇器第二次。
3. RT 詳情頁若必須截圖：只截 Details 欄＋script 區，不截整頁。

**讀多少（硬規則，不留判斷）：**

- script 正文：**取前 4,000 字元**，超過截斷（暫定值，實測後調）。
- shotlist：全文。
- S2 只需要寫出三段式（摘要一句＋畫面逐項＋BITE 濃縮＋講者），**不需要逐字讀完每段 SOUNDBITE**——逐字與精確 TC 是下游 S7 的事。

## 2. 狀態檔：`s2_state.py` 代管（agent 禁止直接開 JSON）

狀態檔仍是單一 JSON（`自動掃帶系統/s2-state.json`，欄位同 V1），但**一切讀寫都透過腳本**：

```
python scripts/s2_state.py resume                          # 開工必跑：現在幾點段、已收幾則、pending幾則、待整併幾則
python scripts/s2_state.py diff --checkpoint 16:00 --ids RT2333,AP4675135,IN-02TU
                                                           # 回傳哪些是新的；已在庫的自動更新 last_checked
python scripts/s2_state.py add --id RT2333 --source RT --checkpoint 16:00 --status pending --entry-file tmp.txt
python scripts/s2_state.py update-entry --id RT2333 --status has_script --entry-file tmp.txt
                                                           # pending→has_script 覆寫 raw_entry
python scripts/s2_state.py pending                         # 稿未到清單（最終整併清查用）
python scripts/s2_state.py to-compile                      # 增量整併輸入：新增＋變動，含 raw_entry 全文
python scripts/s2_state.py mark-compiled --checkpoint 18:00 --ids RT2333,RT2360
python scripts/s2_state.py set-category --id RT2333 --cat "社會/休達移民"
python scripts/s2_state.py get --id RT2333                 # 單則全文
python scripts/s2_state.py needs-review add --id RT2333 --note "疑似UGC，待人工"
python scripts/s2_state.py needs-review list
```

- 批次擷取流程 ＝ 收集本輪列表 ID → `diff` → 只對「新的」開詳情 → 每則 `add`。**全程不載入 70 則 raw_entry。**
- 整併流程 ＝ `to-compile` 拿增量 → 判斷分類（`set-category`）→ 改寫 txt → `mark-compiled`。
- **腳本連續失敗 2 次**：把錯誤訊息原文記進回報，**當輪改用 V1 直讀 JSON 的做法繼續**（degraded mode），不得卡住不動。

## 3. 品質掃／統計／比對：`s2_validate.py`

```
python scripts/s2_validate.py check "G:\...\0801晚班交接.txt"   # 格式異常掃描，輸出命中清單（行號＋原因）
python scripts/s2_validate.py stats "G:\...\0801晚班交接.txt"   # 輸出檔頭兩行（掃帶時段＋來源則數統計）
python scripts/s2_validate.py diff3 current.txt snapshot.txt    # 三方比對：列出人工編輯過的行
```

- `check` 涵蓋 V1「格式異常」表全部可 regex 的項目：BITE 矛盾、缺 `▎畫面：`、缺講者、備註重標、GMT 洩漏、`FILE`／`檔案`、操作備註全形括號、重複代碼、第二括號非 `(BITE)` 等。
- **LLM 只處理命中清單**（回站核對、修 raw_entry＋txt），不再整份逐行讀。`明顯可疑`（數字矛盾等語意類）維持 LLM 抽查，但只在機器掃結果之外補充，不重複掃格式。
- `stats` 產出的兩行直接貼進檔頭（[V1 檔頭備註規則](13-S2-定時掃帶.md#晚班交接檔頭備註2026-08-01-定案)）。
- `diff3` 只把「與機器版快照不同的行」列出來，LLM 只裁決這些行保不保留。
- **腳本失敗行為**：連續失敗 2 次 → 品質掃記為「未執行（腳本錯誤）」寫進回報，**禁止 agent 自行逐行手掃替代**。

## 4. SNTV 列表級收錄（機械白名單）

- **僅限代碼 `AP5` 開頭**（SNTV 體育，判定規則同 V1）：直接以列表可見資訊（標題＋時長＋Source）寫簡版三段式，**不開詳情頁**。備註照標 `(SNTV)`，摘要一句話，`畫面：` 依標題可推者寫、不確定就精簡，結尾 `無BITE。`（列表看不到 BITE 就不標）。
- 其餘**一律照常開詳情**——不做任何語意判斷的「低價值分類」，防低階 agent 誤殺大新聞。
- 使用者點名要開稿的 SNTV 素材，回站補完整三段式。

## 5. 防卡設計（低階 agent 必讀）

1. **每輪開工第一步跑 `resume`**——context 斷掉重進時，以腳本回報的狀態為準接續，不憑記憶。
2. **RT 卡住跳站**：連續 2 次 Next 沒反應／頁面沒變 → 記下目前 Edit No.（`needs-review add`），跳去掃 AP／CNN，回報 RT 中斷點。不准死磕（V1 已知 SPA 卡快取雷）。
3. **半夜禁問**：無人值守時段遇到需使用者確認的事項（可疑素材、分類拿不準、腳本壞掉）→ `needs-review add` 記錄＋寫進交接檔備註，**繼續往下跑**。不得 `AskUserQuestion` 等回應、不得停住。
4. **fallback 全部單向**：階梯只往下走（選擇器→整頁→截圖），不回頭重試上一步。

## 未定／實測後要回填

- [ ] script 4,000 字元上限是否夠（RT 長稿實測）
- [ ] `s2_state.py` degraded mode 實際觸發率
- [ ] SNTV 列表級的資訊量晚班夠不夠用
- [ ] 實測一晚總 token，對照 V1 估算 30.8 萬
