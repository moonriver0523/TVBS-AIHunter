# -*- coding: utf-8 -*-
"""`patch-entry` 機械標記修補迴歸（A12 桶①，2026-08-18）。

要防的是「加一個標記卻重打整條 entry」——0818-1600 那輪四支臨時腳本
（`_fix_ns_bite` / `_fix_ap` / `_fix_markers` / `_fix_combined2`）的全部內容
就是這件事。所以最重要的一組測試是**真實 replay**：拿 0818-1600 那輪
`_fix_markers.py` 與 `_fix_ns_bite.py` 的輸入輸出，驗 `patch-entry` 產出
一字不差的同一條 entry——若對不上，這支工具就沒有取代臨時腳本的資格。

其餘負向測試守兩件事：
  ① 標記順序／互斥（`{時段} {🔴|🟡|⭐} {🟤} {🔖} {代碼}`）不可被打亂——
     順序錯或沒剝乾淨會讓整行 LINE_RE 不 match，從品質掃與檔頭統計裡
     **靜默消失**（△／🔴／🟡／🔖 上線時各踩過一次，見 s2_validate 註解；
     ⭐ 是 2026-08-19 加入的第三個互斥值，同一套剝除機制）。
  ② `--bite` 只補 s2_validate 已經在報的那一種，其餘一律拒絕——
     補錯方向會製造出「有 (BITE) 但缺 ▎BITE： 段」這個相反的錯誤。

用法：python test_s2_patch_entry.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_validate as sv    # noqa: E402
import s2_state as st       # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def patch(entry, alert=None, bite=False):
    return st.patch_marks(sv, entry, alert, bite)


BODY = ("RT2612 (CCTV) (BITE) ▎哥倫比亞馬尼薩雷斯強震重創主教座堂。"
        "▎畫面：教堂損毀現況。▎BITE：佩德羅(居民)「地面劇烈搖晃。」▎2:20")

# ── ① 插入／切換／撤除，位置與互斥 ─────────────────────────────────
for pre, alert, want, label in (
    ("△ ",            "red",    "△ 🔴 ", "無 → 🔴"),
    ("△ ",            "yellow", "△ 🟡 ", "無 → 🟡"),
    ("△ 🟡 ",         "red",    "△ 🔴 ", "🟡 → 🔴（升級，不並存）"),
    ("△ 🔴 ",         "yellow", "△ 🟡 ", "🔴 → 🟡（降級，不並存）"),
    ("△ 🔴 ",         "none",   "△ ",     "🔴 → 撤除"),
    ("△ 🔴 🟤 ",      "yellow", "△ 🟡 🟤 ", "換標記保住 🟤"),
    ("△ 🔴 🟤 🔖 ",   "none",   "△ 🟤 🔖 ", "撤除保住 🟤🔖"),
    ("△ 🟡 🔖 ",      "red",    "△ 🔴 🔖 ", "換標記保住 🔖"),
    ("",              "red",    "🔴 ",    "沒有時段標記也能插"),
):
    new, why = patch(pre + BODY, alert=alert)
    report(f"標記：{label}", new == want + BODY,
           f"得到 {new!r}" if new != want + BODY else "")

# 冪等：已經是該標記就回 None（不寫檔、不動 entry_updated）
new, why = patch("△ 🔴 " + BODY, alert="red")
report("標記：已是 🔴 再標 🔴 → 不變更", new is None, f"why={why}")
new, why = patch("△ " + BODY, alert="none")
report("標記：本來就沒有再撤 → 不變更", new is None, f"why={why}")

# 🔴 一定要剝乾淨——沒剝乾淨整行會從品質掃靜默消失
for pre, alert in (("△ 🔴 ", "yellow"), ("△ 🟡 🟤 🔖 ", "red"), ("△ 🔴 🟤 ", "none")):
    new, _ = patch(pre + BODY, alert=alert)
    _, bare = sv.strip_mark(new)
    report(f"剝乾淨：{pre.strip()} 換標記後 LINE_RE 仍認得",
           bool(sv.LINE_RE.match(bare)), f"剩 {bare[:24]!r}")

# ── ①b ⭐ 推薦：與 🔴／🟡 三者互斥（2026-08-19）──────────────────────
for pre, alert, want, label in (
    ("△ ",            "star",   "△ ⭐ ", "無 → ⭐"),
    ("△ 🔴 ",         "star",   "△ ⭐ ", "🔴 → ⭐（不並存）"),
    ("△ 🟡 ",         "star",   "△ ⭐ ", "🟡 → ⭐（不並存）"),
    ("△ ⭐ ",         "red",    "△ 🔴 ", "⭐ → 🔴（不並存）"),
    ("△ ⭐ ",         "none",   "△ ",     "⭐ → 撤除"),
    ("△ ⭐ 🟤 ",      "none",   "△ 🟤 ",  "撤除保住 🟤"),
):
    new, why = patch(pre + BODY, alert=alert)
    report(f"標記：{label}", new == want + BODY,
           f"得到 {new!r}" if new != want + BODY else "")

new, why = patch("△ ⭐ " + BODY, alert="star")
report("標記：已是 ⭐ 再標 ⭐ → 不變更", new is None, f"why={why}")

for pre, alert in (("△ ⭐ ", "red"), ("△ 🔴 ", "star"), ("△ ⭐ 🟤 🔖 ", "none")):
    new, _ = patch(pre + BODY, alert=alert)
    _, bare = sv.strip_mark(new)
    report(f"剝乾淨：{pre.strip()} 換標記後 LINE_RE 仍認得",
           bool(sv.LINE_RE.match(bare)), f"剩 {bare[:24]!r}")

# ── ② --bite：只補「有 ▎BITE： 段但缺 (BITE)」那一種 ──────────────
NOBITE_TAG = ("RT2612 (CCTV) ▎哥倫比亞強震重創主教座堂。▎畫面：教堂損毀。"
              "▎BITE：佩德羅(居民)「地面劇烈搖晃。」▎2:20")
new, why = patch("△ " + NOBITE_TAG, bite=True)
report("--bite：缺 (BITE) → 補上", new is not None and "(CCTV) (BITE) ▎" in (new or ""),
       f"得到 {new!r}")
report("--bite：補完 s2_validate 零問題",
       new is not None and sv.check_entry(new) == [],
       f"殘留 {sv.check_entry(new or '')}")

new, why = patch("△ " + BODY, bite=True)
report("--bite：已有 (BITE) → 拒絕不動", new is None and "已有" in why, why)

NOBITE = ("RT2612 (CCTV) ▎哥倫比亞強震重創主教座堂。▎畫面：教堂損毀。"
          "▎無BITE。")
new, why = patch("△ " + NOBITE, bite=True)
report("--bite：寫著無BITE → 拒絕（不製造矛盾）", new is None and "無BITE" in why, why)

# ⚠️ 這條要跟上一條真的走不同分支：不可寫「無BITE」，否則會被上一個判準先攔下，
#    測試就變成重複測同一件事（首版就寫錯過，長得像通過其實沒測到）。
NOSEG = "RT2612 (CCTV) ▎哥倫比亞強震重創主教座堂。▎畫面：教堂損毀。▎2:20"
new, why = patch("△ " + NOSEG, bite=True)
report("--bite：沒有 ▎BITE： 段 → 拒絕（不製造相反的錯）",
       new is None and "沒有 ▎BITE：" in why, why)

NOPAREN = "RT2612 ▎摘要。▎畫面：畫面。▎BITE：某人(某某)「話。」▎1:00"
new, why = patch("△ " + NOPAREN, bite=True)
report("--bite：沒有備註括號可接 → 拒絕不猜位置", new is None and "不猜" in why, why)

# 畸形行：括號裡夾了 ▎。判準若掃整行、插入卻只切 head，就會放行卻找不到 `)`，
# 產出開頭多一個空格的壞行——而 check_entry 對 LINE_RE 不 match 的行回空清單，
# 等於壞掉還不報、整行從品質掃靜默消失（本 repo 記過三次的坑）。
WEIRD = "RT2612 (備註▎怪) ▎摘要。▎畫面：畫面。▎BITE：某人(某某)「話。」▎1:00"
new, why = patch("△ " + WEIRD, bite=True)
report("--bite：括號裡夾 ▎ 的畸形行 → 拒絕（不產出壞行）", new is None, f"得到 {new!r} / {why}")

# 併用：換標記＋補 (BITE) 一次做完
new, why = patch("△ 🟡 " + NOBITE_TAG, alert="red", bite=True)
report("--alert 與 --bite 併用", new == "△ 🔴 " + NOBITE_TAG.replace(
    "(CCTV) ▎", "(CCTV) (BITE) ▎"), f"得到 {new!r}")

# ── ③ 守門：非素材行不套這套格式；側錄兩行式改吃這套（A28，2026-09-02）──
SIDE = "CNN 08-18 160000\n（主播 某某） 內容。"
new, why = patch(SIDE, alert="red")
report("側錄兩行式現在可套標記（patch_marks 這層不含首段檢查，見 cmd_patch_entry）",
       new == "🔴 " + SIDE, f"得到 {new!r} / {why}")
new, why = patch(SIDE, bite=True)
report("守門：側錄沒有 (BITE) 機制，--bite 拒絕", new is None and "BITE" in why, why)
new, why = patch("這不是素材行", alert="red")
report("守門：非素材行不動", new is None, why)

# ── ④ 真實 replay：0818-1600 那四支臨時腳本的輸入 → 輸出 ─────────────
# `_fix_markers.py`：把 🔴／🟡 插到既有 entry 的時段標記之後、代碼之前。
REAL_MARKER = [
    ("△ RT6172 (菲律賓校園槍擊) (BITE) ▎三寶顏聖依納爵大學附中校長安達爾在記者會證實"
     "校園槍擊案造成2人死亡。▎畫面：記者會畫面。▎BITE：安達爾(校長)「這是非常悲傷的"
     "一天。」▎1:07", "red",
     "△ 🔴 RT6172 (菲律賓校園槍擊) (BITE) ▎三寶顏聖依納爵大學附中校長安達爾在記者會證實"
     "校園槍擊案造成2人死亡。▎畫面：記者會畫面。▎BITE：安達爾(校長)「這是非常悲傷的"
     "一天。」▎1:07"),
    ("△ AP4679058 (尚比亞總統連任) (BITE) ▎尚比亞選委會宣布希奇萊馬連任。"
     "▎畫面：選委會宣布結果。▎BITE：扎洛米斯(選委會主席)「我依法確認結果。」▎1:37",
     "yellow",
     "△ 🟡 AP4679058 (尚比亞總統連任) (BITE) ▎尚比亞選委會宣布希奇萊馬連任。"
     "▎畫面：選委會宣布結果。▎BITE：扎洛米斯(選委會主席)「我依法確認結果。」▎1:37"),
]
for src, alert, want in REAL_MARKER:
    new, _ = patch(src, alert=alert)
    report(f"replay _fix_markers：{src[2:11]}", new == want, f"得到 {new!r}")

# `_fix_ns_bite.py`／`_fix_ap.py`：整條重打只為了補 (BITE)。
REAL_BITE = [
    ("△ MW-003TU (愛荷華州博覽會) ▎愛荷華州博覽會退伍軍人遊行創下110隊紀錄。"
     "▎畫面：遊行隊伍畫面。▎BITE：陶德(廳長)「服役經歷是為人生增添價值的事。」▎1:39",
     "△ MW-003TU (愛荷華州博覽會) (BITE) ▎愛荷華州博覽會退伍軍人遊行創下110隊紀錄。"
     "▎畫面：遊行隊伍畫面。▎BITE：陶德(廳長)「服役經歷是為人生增添價值的事。」▎1:39"),
    ("△ AP4679064 (南韓對美軍援表態) ▎南韓外交部表示正與美國密切磋商。"
     "▎畫面：記者會畫面。▎BITE：朴斗淳(發言人)「我們正與美方密切磋商。」▎1:29",
     "△ AP4679064 (南韓對美軍援表態) (BITE) ▎南韓外交部表示正與美國密切磋商。"
     "▎畫面：記者會畫面。▎BITE：朴斗淳(發言人)「我們正與美方密切磋商。」▎1:29"),
]
for src, want in REAL_BITE:
    new, _ = patch(src, bite=True)
    report(f"replay _fix_ns_bite/_fix_ap：{src[2:11]}", new == want, f"得到 {new!r}")

# 兩支腳本合起來做的事（先補 (BITE) 再插 🟡），一次呼叫要等價
src = REAL_BITE[1][0]
new, _ = patch(src, alert="yellow", bite=True)
report("replay：一次做完 _fix_ap＋_fix_markers 兩步",
       new == "△ 🟡 " + REAL_BITE[1][1][2:], f"得到 {new!r}")

# ── ⑤ needs_review 必須原樣保住（2026-08-18 上線當天實測抓到的靜默資料遺失）──
# apply_update 的「重算 doubt → 算不出來就 pop needs_review」前提是呼叫端帶了新的
# sb_count；patch-entry 沒有那個資訊，光標一個 🟡 就把跨輪交辦的留痕清掉。
# 踩的正好是 R6 的教訓（跨輪交辦要走狀態檔的 needs-review，不是帳本）。
import json                                                        # noqa: E402
import tempfile                                                    # noqa: E402


class _Args:
    def __init__(self, **kw):
        self.ids = kw.get("ids", "")
        self.alert = kw.get("alert")
        self.bite = kw.get("bite", False)
        self.checkpoint = kw.get("checkpoint")
        self.file = kw.get("file")


def _fresh_state(path, needs_review=None):
    it = {"id": "RT2612", "source": "RT", "script_status": "has_script",
          "sb_count": 5, "raw_entry": "△ " + BODY}
    if needs_review:
        it["needs_review"] = needs_review
    json.dump({"items": [it]}, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return st.load(path)


with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "s.json")

    s = _fresh_state(p, "稿未到，跨輪交辦")
    st.cmd_patch_entry(s, _Args(ids="RT2612", alert="yellow", file=p))
    after = {x["id"]: x for x in json.load(open(p, encoding="utf-8"))["items"]}
    report("needs_review：標 🟡 之後留痕還在",
           after["RT2612"].get("needs_review") == "稿未到，跨輪交辦",
           f"得到 {after['RT2612'].get('needs_review')!r}")

    s = _fresh_state(p)          # 本來就沒有留痕 → 不可憑空生出來
    st.cmd_patch_entry(s, _Args(ids="RT2612", alert="red", file=p))
    after = {x["id"]: x for x in json.load(open(p, encoding="utf-8"))["items"]}
    report("needs_review：本來沒有就維持沒有",
           "needs_review" not in after["RT2612"], f"得到 {after['RT2612'].get('needs_review')!r}")

# ── ⑥ A28（2026-09-02）：側錄「首段代表整組」──────────────────────────
# 真實 0902-s2-state.json 抽測發現：items 陣列順序不保證同單元彼此相鄰
# （見 side_unit_head_id() docstring）。這裡用最小案例覆蓋：同單元非首段
# 被擋、首段可標、跨單元／缺日期不誤判。

CAT_A = {"大分類": "社會", "中主題": "測試單元", "小分題": "小題"}
CAT_B = {"大分類": "社會", "中主題": "另一單元", "小分題": ""}


def _side_state(path, extra_items=()):
    items = [
        {"id": "CNN 09-01 100000", "source": "SIDE_CNN", "category": dict(CAT_A),
         "raw_entry": "CNN 09-01 100000 （主播）\n第一段內容。"},
        {"id": "CNN 09-01 100200", "source": "SIDE_CNN", "category": dict(CAT_A),
         "raw_entry": "CNN 09-01 100200 （記者 某某）\n第二段內容。"},
        {"id": "CNN 09-01 090000", "source": "SIDE_CNN", "category": dict(CAT_B),
         "raw_entry": "CNN 09-01 090000 （主播）\n不同單元，TC 更早也不該被算進 CAT_A。"},
        *extra_items,
    ]
    json.dump({"items": items}, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return st.load(path)


with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "side.json")
    s = _side_state(p)

    report("side_unit_head_id：同單元找出 TC 最早的首段",
           st.side_unit_head_id(s, "CNN 09-01 100200") == "CNN 09-01 100000",
           f"得到 {st.side_unit_head_id(s, 'CNN 09-01 100200')!r}")
    report("side_unit_head_id：首段自己查也回自己",
           st.side_unit_head_id(s, "CNN 09-01 100000") == "CNN 09-01 100000")
    report("side_unit_head_id：不同單元（CAT_B）不被混進來，即使 TC 更早",
           st.side_unit_head_id(s, "CNN 09-01 090000") == "CNN 09-01 090000")

    # 標非首段 → 拒絕，state 不變
    st.cmd_patch_entry(s, _Args(ids="CNN 09-01 100200", alert="red", file=p))
    after = {x["id"]: x for x in json.load(open(p, encoding="utf-8"))["items"]}
    report("cmd_patch_entry：非首段被擋，raw_entry 不變",
           after["CNN 09-01 100200"]["raw_entry"] == "CNN 09-01 100200 （記者 某某）\n第二段內容。",
           after["CNN 09-01 100200"]["raw_entry"])

    # 標首段 → 成功
    s = st.load(p)   # 重讀，避免沿用上一步已改動的記憶體物件
    st.cmd_patch_entry(s, _Args(ids="CNN 09-01 100000", alert="red", file=p))
    after = {x["id"]: x for x in json.load(open(p, encoding="utf-8"))["items"]}
    report("cmd_patch_entry：首段可標，🔴 進了 raw_entry",
           after["CNN 09-01 100000"]["raw_entry"].startswith("🔴 CNN 09-01 100000"),
           after["CNN 09-01 100000"]["raw_entry"])
    report("cmd_patch_entry：標首段不影響同單元其他段",
           after["CNN 09-01 100200"]["raw_entry"] == "CNN 09-01 100200 （記者 某某）\n第二段內容。")

    # 缺日期（舊格式）混進同單元 → side_unit_head_id 回 None，不准猜
    legacy = {"id": "CNN 100050", "source": "SIDE_CNN", "category": dict(CAT_A),
              "raw_entry": "CNN 100050 （主播）\n舊格式沒有日期。"}
    p2 = os.path.join(td, "side_legacy.json")
    s2 = _side_state(p2, extra_items=[legacy])
    report("side_unit_head_id：同單元混了缺日期舊格式 → 回 None，不猜",
           st.side_unit_head_id(s2, "CNN 09-01 100000") is None)
    st.cmd_patch_entry(s2, _Args(ids="CNN 09-01 100000", alert="red", file=p2))
    after2 = {x["id"]: x for x in json.load(open(p2, encoding="utf-8"))["items"]}
    report("cmd_patch_entry：判定失敗時整批不動（含本來該過關的首段）",
           after2["CNN 09-01 100000"]["raw_entry"] == "CNN 09-01 100000 （主播）\n第一段內容。",
           after2["CNN 09-01 100000"]["raw_entry"])

print("\n全部通過" if ok else "\n有失敗項")
sys.exit(0 if ok else 1)
