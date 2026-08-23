# -*- coding: utf-8 -*-
"""逐字節守恆證明：從切出來的四份檔案還原原檔，與備份做 SHA-256 比對。

還原方式刻意與切檔腳本無關——只認檔案裡的 <!--BODY--> / <!--ENDBODY--> 標記，
逐字節取回正文，不做任何 strip。
"""
import hashlib
import os

BK = r"E:\GitHub\TVBS-AIHunter\common\_rules_backup_20260824\13-S2-定時掃帶.md"
C = r"E:\GitHub\TVBS-AIHunter\common"
FILES = {"P1": "13-S2-定時掃帶.md", "P2": "13e-S2-素材行與分類規則.md",
         "P3": "13f-S2-大分類與各站規則.md", "R": "13-rationale.md"}
PLAN = [(1, 8, "P1"), (9, 206, "P1"), (207, 228, "R"), (229, 345, "P1"),
        (346, 792, "P2"), (793, 926, "P3"), (927, 936, "R"), (937, 949, "R"),
        (950, 1053, "P3")]
OLD_HEAD_MARK = "## 附：分檔前的原始檔頭（2026-08-24 存查，逐字保留）"


def body(key):
    lines = open(os.path.join(C, FILES[key]), encoding="utf-8").read().split("\n")
    a = lines.index("<!--BODY-->") + 1
    b = lines.index("<!--ENDBODY-->")
    return lines[a:b]


bodies = {k: body(k) for k in FILES}

# rationale 末尾附了「原始檔頭」存查區，要先切掉、並取出原檔頭
r = bodies["R"]
m = r.index(OLD_HEAD_MARK)
tail = r[m:]
fence = [i for i, x in enumerate(tail) if x.strip() == "```"]
old_head = tail[fence[0] + 1:fence[1]]
# 切檔腳本在原文之後**固定**接了 ["", "---", "", MARK, ...]，所以原文結束於 m-3。
# ⛔ 不可用「往回吃空行」的啟發式——原文段落本身就可能以空行結尾（L949 即是），
#    那樣會多吃一行，守恆證明就會假性失敗（或更糟，掩蓋真的少一行）。
assert r[m - 3:m] == ["", "---", ""], f"存查區前綴不如預期：{r[m-3:m]}"
bodies["R"] = r[:m - 3]

cur = {k: 0 for k in FILES}
rebuilt = []
for a, b, where in PLAN:
    n = b - a + 1
    if (a, b) == (1, 8):
        rebuilt.extend(old_head)
        cur["P1"] = 0          # P1 正文不含原前 8 行
        continue
    rebuilt.extend(bodies[where][cur[where]:cur[where] + n])
    cur[where] += n

orig = open(BK, encoding="utf-8").read().split("\n")
print(f"原檔 {len(orig)} 行 / 重組 {len(rebuilt)} 行")
diff = [(i + 1, o, x) for i, (o, x) in enumerate(zip(orig, rebuilt)) if o != x]
if diff:
    print(f"❌ {len(diff)} 行不一致，前 3 筆：")
    for ln, o, x in diff[:3]:
        print(f"   L{ln}\n     原: {o[:100]}\n     組: {x[:100]}")
else:
    print("✅ 逐行完全一致（含空行、含順序）")

h1 = hashlib.sha256("\n".join(orig).encode()).hexdigest()
h2 = hashlib.sha256("\n".join(rebuilt).encode()).hexdigest()
print(f"  原檔 SHA-256 {h1}")
print(f"  重組 SHA-256 {h2}")
print("\n✅ 逐字節守恆：零刪減、零遺漏" if h1 == h2 else "\n❌ 雜湊不同")

# 各段是否落在正確檔案（抽查段落起始行）
print("\n=== 段落歸屬抽查 ===")
for a, b, where in PLAN:
    if (a, b) == (1, 8):
        continue
    first = orig[a - 1]
    where_txt = FILES[where]
    ok = first in bodies[where]
    print(f"  {'✅' if ok else '❌'} L{a}-{b} → {where_txt:<34}{first[:44]}")
