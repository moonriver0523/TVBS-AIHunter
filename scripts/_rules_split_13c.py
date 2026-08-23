# -*- coding: utf-8 -*-
"""13c 切成上／下兩部（同一套機械切法，逐字保留）。
13c 42,998 字元 > Read 約 30,000 字元上限，必會截斷。
切點取 §1a 結束處（1-419 擷取 / 420-833 狀態與收工），兩邊都約 21k、餘裕充足。"""
import os
SRC = r"E:\GitHub\TVBS-AIHunter\common\_rules_backup_20260824\13c-S2-定時掃帶-v3省token.md"
C   = r"E:\GitHub\TVBS-AIHunter\common"
STAMP = "2026-08-24"
CUT = 417                     # 切在 "## 1b." 之前；餘裕優先（兩邊各約 21k）

UP_HEAD = """# 13c　S2 定時掃帶 V3（省 token 執行版）— 上：三站入口與擷取

> 🔴 **2026-08-24 切成上下兩部（R15）**：原檔 42,998 字元，而 Read 工具結果約
> 30,000 字元就**靜默截斷**，本檔尾端的 §2～§5a（狀態檔、稽核、品質掃、防卡、
> 建檔輪）**從沒被完整載入過**。**內容逐字保留、未改寫**（附逐字節守恆證明）。
>
> - **本檔（上）**：§0 三站入口／§1 詳情頁擷取階梯／**§1a 三站 API 直查（掃帶首選路徑）**
> - **[`13c2`](13c2-S2-定時掃帶-v3省token-下.md)（下，同樣必讀）**：§2 狀態檔代管／
>   §2a-2 每輪稽核／§3 品質掃與渲染／§3b 中小分題檢視／§4 SNTV／§4c YT／§5 防卡／§5a 建檔輪
>
> ⛔ **只讀上半不算讀完 13c。**
"""

DN_HEAD = """# 13c2　S2 定時掃帶 V3（省 token 執行版）— 下：狀態檔、稽核與收工

> 🔴 **2026-08-24 由 [`13c`](13c-S2-定時掃帶-v3省token.md) 切出（R15）**，
> 內容逐字保留、未改寫。**本檔與上半同為必讀。**
>
> 本檔涵蓋：§1b AP＋RT 清單直開流程（§1a 失敗時的退路）、
> **§2 狀態檔 `s2_state.py` 代管（agent 禁止直接開 JSON）**、
> §2a 臨時口令、**§2a-2 每輪快速稽核 `s2_audit.py`（交班前必跑）**、
> §2b 查證成本原則、§2d 檔頭時間窗、**§3 品質掃／統計／渲染**、
> **§3b 中／小分題檢視 `s2_topic_review.py`（render 前必做，每輪）**、
> §3a 主題重複偵測、§4 SNTV 列表級收錄、§4c YouTube 網址素材、
> §4b 整併分類修正、**§5 防卡設計**、§5c 排程啟動器、**§5a 建檔輪額外動作**、
> §2c 結構化欄位。
"""

def canary(tag):
    return (f"<!-- RULES-EOF {tag} {STAMP} — 讀到這一行才算讀完本檔；"
            f"沒讀到＝被截斷，必須用 offset 補讀。 -->\n")

lines = open(SRC, encoding="utf-8").read().split("\n")
# 原檔前 15 行是舊檔頭，用新檔頭取代；原文存進「下」的存查區，一個字不丟
old_head, up_body, dn_body = lines[:12], lines[12:CUT-1], lines[CUT-1:]

for fname, head, body, tag, extra in [
    ("13c-S2-定時掃帶-v3省token.md", UP_HEAD, up_body, "13c", ""),
    ("13c2-S2-定時掃帶-v3省token-下.md", DN_HEAD, dn_body, "13c2",
     "\n".join(["", "## 附：分檔前 13c 的原始檔頭（2026-08-24 存查，逐字保留）", "",
                "```"] + old_head + ["```", ""])),
]:
    text = (head + "\n---\n<!--BODY-->\n" + "\n".join(body)
            + "\n<!--ENDBODY-->\n" + extra + "\n" + canary(tag))
    open(os.path.join(C, fname), "w", encoding="utf-8").write(text)
    nl = text.count("\n") + 1
    est = len(text) + nl * 5
    print(f"{'✅' if est < 26000 else '⚠️'} {fname:<36}{len(text):>7} 字元 {nl:>4} 行 預估載入 {est:>7}")
