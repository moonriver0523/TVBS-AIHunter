# -*- coding: utf-8 -*-
"""用 0810 的真實判斷當 ground truth 驗證廢話偵測器的精準度／召回率。

ground truth＝當天另一個 agent 實際捨棄的 7 段（擷取器 79 段、入庫 72 段的差集）。
"""
import sys, os, io
sys.path.insert(0, r"E:\GitHub\TVBS-AIHunter\scripts")
sys.stdout.reconfigure(encoding="utf-8")
import s2_side_from_oyw as m

D = r"G:\我的雲端硬碟\Autopilot\(掃帶歐印萬) 檔名取TC起頭 6位數\0810"
TRUTH = {"153446", "161625", "162545", "163620", "164112", "164945", "170933"}

# ⚠️ **基準集要釘死在校準當時那 10 支**。來源資料夾是活的，晚上還會有新檔進來——
#    0810 20:30 就從 79 段長到 175 段，而新檔裡的 `194451`
#    （主播 John「我們來談談——」）是**真廢話**，卻因為不在 TRUTH 裡被算成假陽性，
#    害測試假性失敗。回歸測試比對的是**固定樣本**，不是「資料夾現在有什麼」。
BASELINE = ("152933", "153905", "160108", "161224", "162445",
            "163336", "164433", "173628", "174751", "170012")

flagged, all_tc = set(), set()
for p in sorted(os.listdir(D)):
    if not p.endswith(".wav.txt") or not any(k in p for k in BASELINE):
        continue
    raw = io.open(os.path.join(D, p), encoding="utf-8-sig", errors="replace").read()
    body, err = m.extract_zh(raw)
    if err:
        continue
    segs = m.segments(body)
    all_tc |= {s[0] for s in segs}
    flagged |= {c[0] for c in m.fluff_candidates(segs)}

tp = flagged & TRUTH
fp = flagged - TRUTH
fn = TRUTH - flagged
print("總段數        :", len(all_tc))
print("標記為疑似廢話:", len(flagged))
print("真陽性 TP     :", len(tp), sorted(tp))
print("假陽性 FP     :", len(fp), sorted(fp), "  ← 必須是 0（誤刪真內容的代價最大）")
print("漏抓   FN     :", len(fn), sorted(fn))
print()
print("精準度 precision = %d/%d" % (len(tp), len(flagged)))
print("召回率 recall    = %d/%d" % (len(tp), len(TRUTH)))
print()
print("結果:", "PASS（零假陽性）" if not fp else "FAIL（有假陽性，必須收緊）")
