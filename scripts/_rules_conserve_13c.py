# -*- coding: utf-8 -*-
"""13c 逐字節守恆證明。"""
import hashlib, os
BK=r"E:\GitHub\TVBS-AIHunter\common\_rules_backup_20260824\13c-S2-定時掃帶-v3省token.md"
C=r"E:\GitHub\TVBS-AIHunter\common"
MARK="## 附：分檔前 13c 的原始檔頭（2026-08-24 存查，逐字保留）"
def body(f):
    l=open(os.path.join(C,f),encoding="utf-8").read().split("\n")
    return l[l.index("<!--BODY-->")+1:l.index("<!--ENDBODY-->")]
up=body("13c-S2-定時掃帶-v3省token.md")
dn_all=open(os.path.join(C,"13c2-S2-定時掃帶-v3省token-下.md"),encoding="utf-8").read().split("\n")
dn=body("13c2-S2-定時掃帶-v3省token-下.md")
m=dn_all.index(MARK)
fence=[i for i,x in enumerate(dn_all[m:]) if x.strip()=="```"]
old_head=dn_all[m+fence[0]+1:m+fence[1]]
orig=open(BK,encoding="utf-8").read().split("\n")
rebuilt=old_head+up+dn
print(f"原檔 {len(orig)} 行 / 重組 {len(rebuilt)} 行")
d=[(i+1,o,r) for i,(o,r) in enumerate(zip(orig,rebuilt)) if o!=r]
print("✅ 逐行完全一致" if not d else f"❌ {len(d)} 行不一致 首筆 L{d[0][0]}: 原[{d[0][1][:60]}] 組[{d[0][2][:60]}]")
h1=hashlib.sha256("\n".join(orig).encode()).hexdigest()
h2=hashlib.sha256("\n".join(rebuilt).encode()).hexdigest()
print(f"  原檔 {h1}\n  重組 {h2}")
print("✅ 逐字節守恆：零刪減、零遺漏" if h1==h2 else "❌ 雜湊不同")
