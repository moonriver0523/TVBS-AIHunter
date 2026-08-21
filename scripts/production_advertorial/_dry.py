# -*- coding: utf-8 -*-
from sot_common import load_script, group_os_lines
p = r"G:\我的雲端硬碟\Claude共用\業配自動寫稿測試\花蓮暑假2400\花蓮暑假2400 完成文稿.txt"
doc, blocks, events = load_script(p)
print("title", doc.title)
print("events", [(e["kind"], e["id"]) for e in events])
for b in blocks:
    print("os"+str(b["bar"]), b["os"])
    print(" groups", group_os_lines(b["os"]))
