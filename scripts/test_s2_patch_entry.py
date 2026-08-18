# -*- coding: utf-8 -*-
"""`patch-entry` 機械標記修補迴歸（A12 桶①，2026-08-18）。

要防的是「加一個標記卻重打整條 entry」——0818-1600 那輪四支臨時腳本
（`_fix_ns_bite` / `_fix_ap` / `_fix_markers` / `_fix_combined2`）的全部內容
就是這件事。所以最重要的一組測試是**真實 replay**：拿 0818-1600 那輪
`_fix_markers.py` 與 `_fix_ns_bite.py` 的輸入輸出，驗 `patch-entry` 產出
一字不差的同一條 entry——若對不上，這支工具就沒有取代臨時腳本的資格。

其餘負向測試守兩件事：
  ① 標記順序／互斥（`{時段} {🔴|🟡} {🟤} {🔖} {代碼}`）不可被打亂——
     順序錯或沒剝乾淨會讓整行 LINE_RE 不 match，從品質掃與檔頭統計裡
     **靜默消失**（△／🔴／🟡／🔖 上線時各踩過一次，見 s2_validate 註解）。
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

# 併用：換標記＋補 (BITE) 一次做完
new, why = patch("△ 🟡 " + NOBITE_TAG, alert="red", bite=True)
report("--alert 與 --bite 併用", new == "△ 🔴 " + NOBITE_TAG.replace(
    "(CCTV) ▎", "(CCTV) (BITE) ▎"), f"得到 {new!r}")

# ── ③ 守門：側錄與非素材行不套這套格式 ─────────────────────────────
SIDE = "CNN 08-18 160000\n（主播 某某） 內容。"
new, why = patch(SIDE, alert="red")
report("守門：側錄兩行式不動", new is None and "非素材行" in why, why)
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

print("\n全部通過" if ok else "\n有失敗項")
sys.exit(0 if ok else 1)
