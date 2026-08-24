# -*- coding: utf-8 -*-
"""把 build_v1 判不出來（T 或 C 落在「未分類」）的則數倒成 JSONL，供 AI 補判。

⚠️ 這支只是 DEMO 用的取樣工具，不在產線上。正式 v2 的作法是掃帶 agent
   在 set-category 同一批順手判 T/C（見 TC矩陣評估 §9.2／§12.2），
   不是事後撿兜底再丟 LLM——那條「按信心切」的混合路線已被否決。
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
import build_v1 as V1           # noqa: E402

UNKNOWN = V1.UNKNOWN


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--base-date", default="")
    p.add_argument("--out", required=True)
    p.add_argument("--chars", type=int, default=200, help="每則附多少字內文供判斷")
    a = p.parse_args()

    base = a.base_date
    if not base:
        m = re.search(r"(\d{4})-s2-state", os.path.basename(a.file))
        base = m.group(1) if m else ""

    st = json.load(open(a.file, encoding="utf-8-sig"))
    raw = [r for r in H.collect(st, base) if r.get("kind") != "empty"]
    rows = V1.fold_side(raw)

    n = 0
    with open(a.out, "w", encoding="utf-8") as f:
        for r in rows:
            T, C, _ = V1.tag_tc(r)
            if UNKNOWN not in T and UNKNOWN not in C:
                continue
            n += 1
            txt = re.sub(r"\s+", " ", (r.get("text") or "")).strip()
            f.write(json.dumps({
                "id": r.get("id") or "",
                "need": ("T" if UNKNOWN in T else "") + ("C" if UNKNOWN in C else ""),
                "T": T, "C": C,
                "big": r.get("big") or "", "mid": r.get("mid") or "",
                "sub": r.get("sub") or "", "src": r.get("src") or "",
                "kind": r.get("kind") or "",
                "txt": txt[:a.chars],
            }, ensure_ascii=False) + "\n")
    print(f"OK {a.out}：{n} 則需補判（共 {len(rows)} 則）")


if __name__ == "__main__":
    main()
