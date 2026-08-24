# -*- coding: utf-8 -*-
"""DEMO：v1 啟發式先判 T/C，判不出來的吃 AI 補判檔（唯讀、不寫回狀態檔）。

跟 build_v1.py 的差別只有一件事：**多吃一份 `--ai` 覆蓋檔**，
把 `tag_tc()` 落「未分類」的那一軸換成 AI 判的結果，並在該則標記 `ai="T"/"C"/"TC"`，
讓模板把那些標籤畫成虛線＋🤖——**判準來源不同，畫面上就不該長得一樣**
（這是 D3「未分類要可見、不准靜默兜底」的同一條原則）。

⛔ 這支是**展示用**，不是 v2 的實作路線。
   TC矩陣評估 §9.2 已否決「Python 先判、兜底才丟 LLM」的混合路線：
   錯最兇的是「有信心地答錯」（RT7263 賴清德 823 沒掛臺灣、SE-001SU 哥倫比亞高中掛中南美），
   那些在 tag_tc() 眼中都是**已分類**，永遠不會落進本檔補判的集合。
   v2 的正解是掃帶 agent 在 set-category 同一批順手判 T/C（§12.2）。

牙齒放在讀取端：AI 覆蓋檔用到不在 TC-字典 裡的名字就**直接失敗**，
不靜默略過——比照 build_v1.py 對兜底改寫的處理。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import s2_render_html as H      # noqa: E402
import s2_render as R           # noqa: E402
import build_tc_matrix_0821 as BASE  # noqa: E402
import build_v1 as V1           # noqa: E402

TPL = os.path.join(HERE, "_template_demo_ai.html")
UNKNOWN = V1.UNKNOWN


def load_ai(path):
    """讀 AI 補判檔並對照 TC-字典驗名。名字不在字典裡＝直接失敗。"""
    if not path:
        return {}
    doc = json.load(open(path, encoding="utf-8-sig"))
    items = doc.get("items", doc)
    ok_t = {t for t, _ in BASE.T_FIXED}
    ok_c = {c for c, _ in BASE.C_FIXED}
    bad = []
    for k, v in items.items():
        for t in v.get("T", []):
            if t not in ok_t:
                bad.append(f"{k}: T={t!r}")
        for c in v.get("C", []):
            if c not in ok_c:
                bad.append(f"{k}: C={c!r}")
    if bad:
        raise SystemExit("ERROR: AI 補判檔用了不在 TC-字典.md 裡的名字：\n  "
                         + "\n  ".join(bad))
    return items


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--ai", default="", help="AI 補判覆蓋檔（JSON）")
    p.add_argument("--base-date", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--local-links", action="store_true")
    a = p.parse_args()

    base = a.base_date
    if not base:
        m = re.search(r"(\d{4})-s2-state", os.path.basename(a.file))
        base = m.group(1) if m else ""

    st = json.load(open(a.file, encoding="utf-8-sig"))
    win = R.window_from_state(st, base) or st.get("window_local", "")
    head = H.build_header(st, base, win)
    title = head[0] if head else f"{base} 晚班交接"
    window_line = head[1] if len(head) > 1 else win

    raw = [r for r in H.collect(st, base) if r.get("kind") != "empty"]
    rows = V1.fold_side(raw)
    ai = load_ai(a.ai)

    out = []
    need_t = need_c = 0          # 啟發式判不出來的則數
    fix_t = fix_c = 0            # AI 實際補上的則數
    miss = []                    # 判不出來、AI 也沒給的
    for r in rows:
        T, C, flags = V1.tag_tc(r)
        rid = r.get("id") or ""
        o = ai.get(rid, {})
        tag = ""
        if UNKNOWN in T:
            need_t += 1
            if o.get("T"):
                T, tag, fix_t = list(o["T"]), tag + "T", fix_t + 1
            else:
                miss.append((rid, "T"))
        if UNKNOWN in C:
            need_c += 1
            if o.get("C"):
                C, tag, fix_c = list(o["C"]), tag + "C", fix_c + 1
            else:
                miss.append((rid, "C"))
        out.append({
            "id": rid, "big": r.get("big") or "",
            "mid": r.get("mid") or "", "sub": r.get("sub") or "",
            "src": r.get("src") or "", "kind": r.get("kind") or "",
            "mark": r.get("mark") or "", "alert": r.get("alert") or "",
            "hilite": r.get("hilite") or "", "text": r.get("text") or "",
            "preview": BASE.slim_text(r.get("text") or ""),
            "segs": r.get("segs") or 1,
            "q": (r.get("q") or "")[:400],
            "T": T, "C": C, "flags": flags, "ai": tag,
        })

    n_ai = sum(1 for r in out if r["ai"])
    n = len(out) or 1

    live_dir = os.path.dirname(os.path.abspath(a.file))
    pills, dates = V1.build_histpills(base, live_dir)

    # 「未分類」只在補判之後**還真的有**時才進顯示清單（跟 build_v1 同一條原則）。
    t_list = list(BASE.T_FIXED)
    c_list = list(BASE.C_FIXED)
    c_fb = dict(BASE.C_FALLBACK)
    if any(UNKNOWN in r["T"] for r in out):
        t_list.append((UNKNOWN, "❓"))
    if any(UNKNOWN in r["C"] for r in out):
        c_list.append((UNKNOWN, ""))
        c_fb[UNKNOWN] = "❓"

    ainote = (f"啟發式判不出來 {n_ai} 則（{n_ai*100//n}%）"
              f"：T {need_t}／C {need_c}，AI 已補 T {fix_t}／C {fix_c}"
              + (f"，仍缺 {len(miss)} 軸" if miss else "，全數補齊"))

    tpl = open(TPL, encoding="utf-8").read()
    html = (tpl
            .replace("__DATA__", json.dumps(out, ensure_ascii=False))
            .replace("__T__", json.dumps(t_list, ensure_ascii=False))
            .replace("__C__", json.dumps(c_list, ensure_ascii=False))
            .replace("__C_FALLBACK__", json.dumps(c_fb, ensure_ascii=False))
            .replace("__FLAGS__", json.dumps(BASE.FLAGS, ensure_ascii=False))
            .replace("__TITLE__", title + "（T/C 矩陣 DEMO：AI 補分類）")
            .replace("__WINDOW__", window_line)
            .replace("__STATS__", V1.stats_line(rows, base))
            .replace("__AICOUNT__", str(n_ai))
            .replace("__AINOTE__", ainote)
            .replace("__HISTPILLS__", pills))
    if a.local_links:
        html = html.replace("%%EXEC_URL%%", "#")

    with open(a.out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"OK {a.out}（{os.path.getsize(a.out)} bytes）")
    print(f"   原始列 {len(raw)} → 摺疊後 {len(rows)} 則")
    print(f"   啟發式判不出來：T {need_t}／C {need_c}／至少一軸 {n_ai}（{n_ai*100//n}%）")
    print(f"   AI 補判：T {fix_t}／C {fix_c}")
    if miss:
        print(f"   ⚠️ 仍缺 {len(miss)} 軸未補：{miss[:10]}")
    else:
        print("   ✅ 全數補齊，頁面上不會再出現「未分類」")
    print(f"   歷史列日期：{dates}")


if __name__ == "__main__":
    main()
