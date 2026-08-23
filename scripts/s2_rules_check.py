# -*- coding: utf-8 -*-
"""完整性對照測試（照省Token計畫 Task 4 Step 3 的要求）：
高風險規則必須存在於分檔後的某一份必讀檔裡。規則掉了不會有錯誤訊息。"""
import os
C = r"E:\GitHub\TVBS-AIHunter\common"
S = r"E:\GitHub\TVBS-AIHunter\scripts"
REQUIRED = ["13-S2-定時掃帶.md", "13e-S2-素材行與分類規則.md",
            "13c-S2-定時掃帶-v3省token.md", "13d-S2-定時掃帶-v4.md"]
blob = ""
for f in REQUIRED:
    blob += open(os.path.join(C, f), encoding="utf-8").read()
prompt = open(os.path.join(S, "s2_scan_prompt.md"), encoding="utf-8").read()

CHECKS = [
    ("摘要 150 字硬上限",      "硬上限150字"),
    ("大分類清單權威樣板",      "======話題======"),
    ("大分類歸位通則",          "清單越前面＝優先層級越高"),
    ("主體歸屬制",              "主體歸屬制"),
    ("開新中主題必跑 list-topics", "開新中主題前必跑"),
    ("小分題不要一則一個",      "不要一則一個"),
    ("NS 沒稿也要收",           "沒稿也要收"),
    ("CNN GMT 換算口訣",        "CNN 換算口訣"),
    ("RT ‹ › 連讀鐵律",        "列表最新 → 點進去 → Next 往早"),
    ("RT 禁則 LOAD MORE",       "LOAD MORE"),
    ("BITE 必寫講者",           "必寫講者"),
    ("分隔符 ▎不加空格",        "分隔符用全形直線"),
    ("per-source 數量回報",     "per-source 數量回報"),
    ("時段標記",                "素材編號前的時段標記"),
    ("_待整併 交件夾",          "_待整併"),
    ("烏俄固定兩中主題",        "【烏打俄】"),
    ("畫面亮點 🔖",             "畫面亮點標記"),
]
bad = []
print("=== 高風險規則存在性 ===")
for name, needle in CHECKS:
    ok = needle in blob
    print(f"  {'✅' if ok else '❌'} {name}")
    if not ok:
        bad.append(name)

print("\n=== 必讀清單與 canary ===")
for f in REQUIRED:
    listed = f in prompt
    tag = f.split("-S2")[0] if "-S2" in f else f
    txt = open(os.path.join(C, f), encoding="utf-8").read()
    has_canary = "RULES-EOF" in txt.split("\n")[-3] or "RULES-EOF" in txt[-260:]
    print(f"  {'✅' if listed else '❌'} prompt 有列 {f}    "
          f"{'✅' if has_canary else '❌'} 檔尾有 RULES-EOF")
    if not listed: bad.append(f"prompt 未列 {f}")
    if not has_canary: bad.append(f"{f} 缺 canary")

print("\n=== 尺寸（Read 約 30,000 字元上限）===")
for f in REQUIRED:
    p = os.path.join(C, f)
    n = len(open(p, encoding="utf-8").read())
    lines = open(p, encoding="utf-8").read().count("\n") + 1
    est = n + lines * 5          # 行號前綴
    flag = "⚠️ 會截斷、需補讀" if est > 30000 else "✅ 可完整載入"
    print(f"  {f:<38}{n:>7} 字元  預估結果 {est:>7}  {flag}")

print("\n" + ("❌ 有 %d 項未通過：%s" % (len(bad), "／".join(bad)) if bad else "✅ 全數通過"))
