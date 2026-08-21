# -*- coding: utf-8 -*-
from sot_common import load_script, group_os_lines, line_width
p = r"D:\Downloads\花蓮暑假2400\花蓮暑假2400 完成文稿.txt"
doc, blocks, events = load_script(p)
print("cards", {k: (v, line_width(v)) for k, v in doc.cards.items()})
print("events", [(e["kind"], e["id"], e.get("bar"), round(e["end"]-e["start"],1) if e["kind"]=="ns" else "") for e in events])
print("NS durs", [round(e["end"]-e["start"], 2) for e in events if e["kind"]=="ns"])
for b in blocks:
    print(b["id"], "bar", b["bar"], "lines", len(b["os"]))
    for ln in b["os"]:
        w = line_width(ln)
        flag = " OVER" if w > 14.01 else ""
        print(f"  {w:4.1f}{flag}  {ln}")
    print("  groups", [len(g) for g in group_os_lines(b["os"])])
