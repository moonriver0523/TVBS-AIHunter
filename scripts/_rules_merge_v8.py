# -*- coding: utf-8 -*-
"""V8 五層合一——剪貼組稿（Task 2 Step 1-3）。

從 common/_rules_backup_20260907/ 的五份原檔，用**精確行號切塊**（不手打、逐字複製）
組成四份新執行版＋一份歸檔附錄。切塊粒度已在對照表（05-A26-取代對照表.md）與
Task 2 執行紀錄中逐節核對過；此腳本只負責機械組裝，不做任何文字改寫。

同時處理 `common/13f-S2-大分類與各站規則.md` 的「收工清單總表」搬遷（該檔不在
五份守恆集合內，搬遷時順手把表格內指向 `13g`/`13h` 的儲存格文字改成 `13c1`/`13c1b`
——這是 Task 6 要做的引用更新，順手在搬移當下一併做掉，避免表格一移過去就是錯的）。

執行後務必接著跑：
  python -X utf8 scripts/_rules_conserve_v8.py   → 必須「缺 0 行」
  python -X utf8 -c "..."                         → 逐檔字元數 < 28000
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMON = os.path.join(ROOT, "common")
BACKUP_DIR = os.path.join(COMMON, "_rules_backup_20260907")

FC = "13c-S2-定時掃帶-v3省token.md"
FC2 = "13c2-S2-定時掃帶-v3省token-下.md"
FD = "13d-S2-定時掃帶-v4.md"
FG = "13g-S2-定時掃帶-v5-四站.md"
FH = "13h-S2-定時掃帶-v7-五站.md"

_cache = {}


def lines(fname):
    if fname not in _cache:
        with open(os.path.join(BACKUP_DIR, fname), encoding="utf-8") as f:
            _cache[fname] = f.read().split("\n")
    return _cache[fname]


def sl(fname, a, b):
    """1-indexed 含頭含尾的行範圍，回傳 join 好的字串（不含結尾換行）。"""
    L = lines(fname)
    chunk = L[a - 1:b]
    return "\n".join(chunk)


def block(*parts):
    return "\n\n".join(p.strip("\n") for p in parts if p is not None)


def write(relpath, h1, desc_lines, body, tag):
    header = "# " + h1 + "\n\n"
    header += "\n".join("> " + d for d in desc_lines) + "\n\n---\n<!--BODY-->\n"
    footer = ("\n<!--ENDBODY-->\n\n"
              f"<!-- RULES-EOF {tag} 2026-09-07 — V8 五層合一，讀到這一行才算讀完本檔；"
              "沒讀到＝被截斷，必須用 offset 補讀。 -->\n")
    text = header + body.strip("\n") + footer
    path = os.path.join(COMMON, relpath)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"寫入 {relpath}：{len(text)} 字元")
    return path


# ------------------------------------------------------------------
# A) 13c-S2-執行版-上-入口與三站擷取.md
# ------------------------------------------------------------------
body_a = block(
    sl(FC, 15, 52),      # §0（三站入口/登入態表，扣掉三站順序小節）
    sl(FG, 39, 83),      # V5-1 掃描順序與輪次（ENEX，含 --- 收尾）
    sl(FH, 37, 94),      # V7-1 掃描順序與輪次（ABC，五站終版，含 --- 收尾）
    sl(FC, 63, 433),     # §1 詳情頁擷取 ... §1a ... §4 守門（13c 原本body其餘全部）
)

# ── team-lead 2026-09-07 15:15 前補丁 ①：把 13d §8 的具體 NS body 填回
#    13c(上) 原本的佔位註解，消除已知殘留缺口（0814 實錯：agent 自拼 body 打出
#    400，白燒 6-8 分）。取代對照表表二 B 項一併更新為「已補完」。
_NS_BODY_PLACEHOLDER = "  const body = { /* request body */ };"
_NS_BODY_CONCRETE = (
    "  // 2026-09-07 V8 自 13d §8 合入；配方以此為準，⛔ 禁翻 investigation-logs\n"
    "  const body = {\n"
    "    bundlesOnly: false, date: new Date().toISOString(),\n"
    "    facets: {contentType:[], videoTypes:[], categories:[], digitalCategories:[], videoFormats:[]},\n"
    "    filters: {contentType:{}, videoTypes:{}, categories:{}, digitalCategories:{}, videoFormats:{}},\n"
    "    from: 0, language: ['en','es'], scriptOnly: false, size: 30,\n"
    "    sort: {order: 'ascending', type: 'relevancyDate'}, term: null\n"
    "  };"
)
assert _NS_BODY_PLACEHOLDER in body_a, "NS body 佔位註解找不到，13c 原文結構可能變了"
body_a = body_a.replace(_NS_BODY_PLACEHOLDER, _NS_BODY_CONCRETE)

# ── 補丁 ②：等量把 AP 範本前的純說明／歷史脈絡段落搬去歸檔，抵消補丁①加的
#    字元，讓估計載入量回到 < 28,000。這兩段只解釋「為什麼要改範本」，不影響
#    「照抄即用範本」本身的可執行性——搬走不影響執行正確性。
#    （第一次只搬清單範本那段，估計載入量 27,906，離 28,000 只剩 94、margin
#    太薄，追加搬第二段「AP 詳情查詢」前的同性質說明，拉開安全margin。）
_AP_HISTORY_PARA = sl(FC, 208, 213)
_AP_HISTORY_PARA2 = sl(FC, 262, 266)
assert _AP_HISTORY_PARA in body_a, "AP 歷史說明段落找不到，13c 原文結構可能變了"
assert _AP_HISTORY_PARA2 in body_a, "AP 詳情歷史說明段落找不到，13c 原文結構可能變了"
body_a = body_a.replace(_AP_HISTORY_PARA + "\n", "")
body_a = body_a.replace(_AP_HISTORY_PARA2 + "\n", "")

write(
    "13c-S2-執行版-上-入口與三站擷取.md",
    "13c　S2 定時掃帶 V8（執行版）— 上：入口與三站擷取",
    [
        "**V8 五層合一（2026-09-07）**：來源＝13c（本檔原身）＋13g V5-1／13h V7-1"
        "（掃描順序併為五站）。單層無疊合，不必再讀 13d/13g/13h。13d §6（大回應落檔）"
        "因字元預算改放 `13c2`。",
        "已取代／已搬離的舊條文（13c 原三站順序句、13g V5-0、13h V7-0 等）逐字存查於"
        "`13c-V8-已取代條文.md`，非必讀。",
        "同為必讀：`13c1`（ENEX）、`13c1b`（ABC）、`13c2`（狀態檔與指令）、`13c3`（收工與防卡）。",
    ],
    body_a,
    "13c",
)

# ------------------------------------------------------------------
# B) 13c1-S2-執行版-中-ENEX.md
# ------------------------------------------------------------------
body_b = sl(FG, 85, 429)  # V5-2..V5-5
write(
    "13c1-S2-執行版-中-ENEX.md",
    "13c1　S2 定時掃帶 V8（執行版）— 中：ENEX",
    [
        "**V8 五層合一（2026-09-07）**：來源＝13g V5-2～V5-5（ENEX API 直查／整併路徑／"
        "素材行分類檔頭／對帳與收工）。單層無疊合。",
        "掃描順序與輪次表已併入 `13c`（上）；V5-0（取代宣告）、V5-6（上線前檢查表）"
        "已存查於 `13c-V8-已取代條文.md`，非必讀。",
        "2026-09-07 裁決①：ENEX／ABC 直接拆成 `13c1`／`13c1b` 兩檔（不等超字元才拆）。",
    ],
    body_b,
    "13c1",
)

# ------------------------------------------------------------------
# C) 13c1b-S2-執行版-中-ABC.md
# ------------------------------------------------------------------
body_c = sl(FH, 96, 468)  # V7-2..V7-5
write(
    "13c1b-S2-執行版-中-ABC.md",
    "13c1b　S2 定時掃帶 V8（執行版）— 中：ABC",
    [
        "**V8 五層合一（2026-09-07）**：來源＝13h V7-2～V7-5（ABC 清單直查／整併路徑／"
        "素材行分類檔頭／對帳與收工）。單層無疊合。",
        "掃描順序與輪次表已併入 `13c`（上）；V7-0（取代宣告）、V7-6（上線前檢查表）"
        "已存查於 `13c-V8-已取代條文.md`，非必讀。",
        "2026-09-07 裁決①：ENEX／ABC 直接拆成 `13c1`／`13c1b` 兩檔（不等超字元才拆）。",
    ],
    body_c,
    "13c1b",
)

# ------------------------------------------------------------------
# D) 13c2-S2-執行版-下-狀態檔與指令.md
# ------------------------------------------------------------------
body_d = block(
    sl(FC2, 17, 198),    # §1b + §2 狀態檔代管
    sl(FD, 57, 74),      # 13d §2 set-category 改一站一批（緊接 §2 之後，就地訂正）
    sl(FC2, 199, 276),   # §2a／§2a-2／§2b／§2d
    sl(FC2, 460, 468),   # §2c 結構化欄位（原檔尾端，歸隊到 2.x 家族）
    sl(FD, 34, 56),      # 13d §1 scratch 路徑
    sl(FD, 75, 97),      # 13d §3 --compact
    sl(FD, 98, 166),     # 13d §4 inspect/unwrap
    sl(FD, 167, 200),    # 13d §5 src_text 必帶
    sl(FD, 201, 232),    # 13d §6 大回應落檔（因 13c 上檔字元預算改放本檔）
    sl(FD, 316, 330),    # 13d §9 素材行不加摘要/不自創分隔
)
write(
    "13c2-S2-執行版-下-狀態檔與指令.md",
    "13c2　S2 定時掃帶 V8（執行版）— 下：狀態檔與指令",
    [
        "**V8 五層合一（2026-09-07）**：來源＝13c2（本檔原身，§1b/§2/§2a/§2a-2/§2b/§2d/§2c）"
        "＋13d §1/§2/§3/§4/§5/§6/§9。單層無疊合。§6（大回應落檔）因 `13c`（上）字元預算"
        "改放本檔；§10/§11（hook 相關防護）因本檔字元預算改放 `13c3`（與 §5 防卡設計同"
        "主題相鄰）。",
        "13d §2「`set-category` 改一站一批」緊接在原 §2「一輪一次」規則之後——"
        "**讀到 §2 沒看完就往下讀一段，那段就是最終版**，不必再回 13d。",
        "同為必讀：`13c`（上）、`13c1`（ENEX）、`13c1b`（ABC）、`13c3`（收工與防卡）。",
    ],
    body_d,
    "13c2",
)

# ------------------------------------------------------------------
# E) 13c3-S2-執行版-下-收工與防卡.md
# ------------------------------------------------------------------
# 13f 收工清單總表：搬遷同時把儲存格內指向 13g/13h 的引用改成 13c1/13c1b
f13f_table = sl("13f-S2-大分類與各站規則.md", 418, 434) if False else None
F13F_PATH = os.path.join(COMMON, "13f-S2-大分類與各站規則.md")
with open(F13F_PATH, encoding="utf-8") as f:
    f13f_lines = f.read().split("\n")
f13f_table = "\n".join(f13f_lines[417:434])  # 0-indexed slice for lines 418-434
f13f_table_v8 = (
    f13f_table
    .replace("`13g` V5-5／`13h` V7-5", "`13c1` V5-5／`13c1b` V7-5")
    .replace("`13g` V5-3／`13h` V7-3", "`13c1` V5-3／`13c1b` V7-3")
    .replace("`13h` V7-5", "`13c1b` V7-5")
)
f13f_table_v8 = f13f_table_v8.replace(
    "（跨檔案索引，2026-09-07 自 prompt 瘦身新增，T13）",
    "（跨檔案索引，2026-09-07 自 13f 尾遷入 `13c3`，V8）",
)
f13f_table_v8 = f13f_table_v8.replace(
    "> 原規劃放 `13c2` §6，因 `13c2` 已逼近 28,000 字元估計載入預算改放本檔尾。",
    "> 原規劃放 `13c2` §6，2026-09-07 自 `13f` 尾遷入本檔（V8 五層合一）。",
)

body_e_raw = sl(FC2, 277, 459)   # §3/§3b/§3a/§4/§4c/§4b/§5/§5c/§5a

# ── team-lead 2026-09-07 補丁 ③：§5 第 11 條內嵌的「規則載入」示例仍寫舊 8
#    個代號（13d/13g/13h），這只是說明性例句，加一句訂正即可，不動原例句本身。
_STALE_EXAMPLE_ANCHOR = "**少任何一個就不要開始掃帶**，先補讀完。"
_STALE_EXAMPLE_NOTE = (
    "**少任何一個就不要開始掃帶**，先補讀完。\n"
    "    （2026-09-07 訂正：上面例句仍是 V8 之前的 8 個舊代號，現為 13／13e／13f／"
    "13c／13c1／13c1b／13c2／13c3——例句本身不改，示範格式不變，代號依上表為準）"
)
assert _STALE_EXAMPLE_ANCHOR in body_e_raw, "§5 第 11 條示例錨點找不到，13c2 原文結構可能變了"
body_e_raw = body_e_raw.replace(_STALE_EXAMPLE_ANCHOR, _STALE_EXAMPLE_NOTE)

body_e = block(
    body_e_raw,
    sl(FD, 331, 344),    # 13d §10 工具層防護（與 §5 防卡設計同主題，字元預算從 13c2 移來）
    sl(FD, 345, 483),    # 13d §11 hook 補洞（同上）
    f13f_table_v8,
)
write(
    "13c3-S2-執行版-下-收工與防卡.md",
    "13c3　S2 定時掃帶 V8（執行版）— 下：收工與防卡",
    [
        "**V8 五層合一（2026-09-07）**：來源＝13c2（本檔原身，§3/§3b/§3a/§4/§4c/§4b/"
        "§5/§5c/§5a）＋13d §10/§11（hook 相關防護，因 `13c2` 字元預算改放本檔，與 §5 "
        "防卡設計同主題相鄰）＋13f 尾「收工清單總表」（原放 13c2 §6，因預算改放 13f 尾，"
        "V8 再搬回本檔）。單層無疊合。",
        "13f 該處已改一行指路，不再重抄全表。",
        "同為必讀：`13c`（上）、`13c1`（ENEX）、`13c1b`（ABC）、`13c2`（狀態檔與指令）。",
    ],
    body_e,
    "13c3",
)

# 改 13f 尾：整段換成一行指路
new_13f_pointer = (
    "## 收工清單總表（已搬遷）\n\n"
    "> 2026-09-07（V8 五層合一）：本表已搬進 [`13c3`](13c3-S2-執行版-下-收工與防卡.md)"
    "「收工清單總表」小節，本檔不再重複列出，請直接讀 `13c3`。"
)
f13f_new = f13f_lines[:417] + new_13f_pointer.split("\n") + f13f_lines[435:]
with open(F13F_PATH, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(f13f_new))
print("已改寫 13f 尾為一行指路")

# ------------------------------------------------------------------
# F) 13c-V8-已取代條文.md（歸檔附錄，非必讀）
# ------------------------------------------------------------------
def divider(src, sect, reason):
    return f"### 原 {src} §{sect}（{reason}）"


archive_parts = []

archive_parts.append(divider("13c", "檔頭前言", "R15 分檔說明，V8 已改新 5 行檔頭，本段存查"))
archive_parts.append(sl(FC, 1, 11))

archive_parts.append(divider("13c2", "檔頭前言", "R15 分檔說明，V8 已改新 5 行檔頭，本段存查"))
archive_parts.append(sl(FC2, 1, 13))

archive_parts.append(divider("13d", "檔頭前言", "V4 增補沿革記錄，V8 單層化後不再需要，本段存查"))
archive_parts.append(sl(FD, 1, 32))

archive_parts.append(divider("13g", "檔頭前言", "V5 增量說明，V8 單層化後不再需要，本段存查"))
archive_parts.append(sl(FG, 1, 9))

archive_parts.append(divider("13h", "檔頭前言", "V7 增量說明，V8 單層化後不再需要，本段存查"))
archive_parts.append(sl(FH, 1, 12))

archive_parts.append(divider("13c", "0（三站掃描順序小節）", "被 13g V5-1／13h V7-1 取代，V8 併入 13c（上）"))
archive_parts.append(sl(FC, 53, 61))

archive_parts.append(divider(
    "13c", "1a-2（AP 清單範本前的 2026-08-21 訂正歷史說明段落）",
    "team-lead 2026-09-07 15:15 前補丁②：純解釋「為什麼要改範本」的歷史脈絡，"
    "不影響下方「照抄即用範本」的可執行性，等量搬離抵消補丁①（NS body 填空）"
    "加的字元，讓 13c（上）估計載入量回到 28,000 以下",
))
archive_parts.append(_AP_HISTORY_PARA)

archive_parts.append(divider(
    "13c", "1a-2（AP 詳情範本前的 2026-08-21 訂正歷史說明段落）",
    "同上，第一段搬完 margin 仍太薄（27,906／28,000），追加搬這段拉開安全margin",
))
archive_parts.append(_AP_HISTORY_PARA2)

archive_parts.append(divider("13g", "V5-0", "取代宣告本身已執行完畢（13c §0 三站句已於 2026-09-07 訂正刪除線），本段存查"))
archive_parts.append(sl(FG, 14, 37))

archive_parts.append(divider("13h", "V7-0", "取代宣告本身已執行完畢（13c §0 三站句已於 2026-09-07 訂正刪除線），本段存查"))
archive_parts.append(sl(FH, 17, 35))

archive_parts.append(divider(
    "13d", "7（AP 清單改打完整 topic 頁）",
    "內容已於更早的編輯直接寫回現行 13c 正文「### 2) AP」小節（含 0820/0821 訂正、"
    "PageSize:50 範本、對帳快照說明），不重複複製；13c 正文已是最終版，本段存查",
))
archive_parts.append(sl(FD, 233, 270))

archive_parts.append(divider(
    "13d", "8（開工只精讀13c＋本檔；NS body配方）",
    "上半「開工只精讀13c＋本檔」已隨 T13／V8 的必讀清單改版而失效（現行 prompt 讀 8→9 份，"
    "非「只讀13c」），整段存查。下半 NS body 具體範例：team-lead 2026-09-07 15:15 前"
    "補丁①已把這段具體 body（`bundlesOnly`…`term: null` 那 7 行）逐字填回 13c（上）"
    "原本的佔位處，缺口已補；本段仍整段存查供對照，13c（上）正文為現行準版",
))
archive_parts.append(sl(FD, 271, 315))

archive_parts.append(divider(
    "13c", "3（NS）（原始佔位註解，補丁①填空前的舊文）",
    "team-lead 2026-09-07 15:15 前補丁①：`{ /* request body */ }` 這行佔位註解已被"
    "上面 13d §8 的具體 body 取代，原句逐字存查於此，滿足守恆缺 0",
))
archive_parts.append(_NS_BODY_PLACEHOLDER)

archive_parts.append(divider("13g", "V5-6（上線前檢查表）", "給執行切換的人看，非掃帶 agent 必讀，本段存查"))
archive_parts.append(sl(FG, 431, 451))

archive_parts.append(divider("13h", "V7-6（上線前檢查表）", "給執行切換的人看，非掃帶 agent 必讀，本段存查"))
archive_parts.append(sl(FH, 470, 493))

archive_parts.append(divider("13c2", "附：分檔前13c的原始檔頭", "2026-08-24 存查用途已由本歸檔檔取代，原樣搬入"))
archive_parts.append(sl(FC2, 473, 486))

body_f = block(*archive_parts)
write(
    "13c-V8-已取代條文.md",
    "13c-V8　已取代條文（歸檔附錄，非必讀）",
    [
        "**V8 五層合一（2026-09-07）存查用**：本檔收錄五份原檔（13c/13c2/13d/13g/13h）"
        "被 V8 取代、搬移、或判定不再需要必讀的段落，逐字保留，供日後追查「為什麼有這條」。",
        "**掃帶 agent 不讀本檔**——必讀清單是 `13`／`13e`／`13f`／`13c`／`13c1`／`13c1b`／"
        "`13c2`／`13c3` 共 8 份。",
        "每段前的「### 原 X §Y（原因）」是本次歸檔新加的分隔標題，不是原文的一部分。",
    ],
    body_f,
    "13c-V8archive",
)

print("\n全部寫入完成。")
