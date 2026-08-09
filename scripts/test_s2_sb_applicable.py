# -*- coding: utf-8 -*-
"""`sb_count=0` 何時算數的迴歸（2026-08-09）。

**要防的誤報**：路透 captioned／rough-cut 社群短片沒有 SHOTLIST 段、也不寫
SOUNDBITE，引言直接以「姓名，職銜」＋引號段落呈現。抽取白名單數不到
SOUNDBITE 字樣 → `sb_count=0` → 觸發假 BITE 兜底。0808–0809 一夜誤報三次
（RT4107／RT4131／RT4125），每則都要人工查證結案。
⚠️ **重複誤報會把警告訓練成雜訊，那比不報還糟。**

**同時要防「修過頭」**：0805 那批 AP Live Choice 是**真的**假 BITE
（有 SHOTLIST、role 標 SOT，但整份沒有可引用的引言），那個擋必須留著。
判準因此刻意保守——稿內出現 SHOTLIST 或 SOUNDBITE 任一字樣就照舊擋。

用法：python test_s2_sb_applicable.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "s2_state.py")
sys.path.insert(0, HERE)
import s2_state as S  # noqa: E402

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


# ── 真實形狀的原文樣本 ───────────────────────────────────────────────
# 路透字幕版（RT4107 那一類）：STORY 開頭、無 SHOTLIST、引言靠姓名職銜＋引號
RT_CAPTIONED = """STORY: :: Khim, 14, student
"There were more gunshots, the teacher told everyone to get into the classroom."
:: Kwan, mother
"I told her not to cry."
[headline] Thai school shooting survivor recounts
[slug] THAILAND-SHOOTING/SURVIVOR (CAPTIONED)"""

# 路透正常格式：有 SHOTLIST，數得出 SOUNDBITE
RT_NORMAL = """VIDEO SHOWS: DEMONSTRATION
SHOTLIST:
1. PEOPLE DANCING
2. (SOUNDBITE) CONGRESSMAN SAYING:
"There is an incompatibility."
STORY: Colombian Congressman criticized..."""

# AP Live Choice（0805 那批真假 BITE）：有 SHOTLIST，但整份沒有 SOUNDBITE
AP_LIVE = """SHOTLIST:
1. WIDE OF PODIUM
2. VARIOUS OF CROWD
This video is a recording of an event transmitted live on AP Live Choice
that has not gone through a full editorial review by the AP."""

BITE_ENTRY = "RT0001 (測試) (BITE) ▎摘要。▎畫面：測試。▎BITE：受訪者「內容」。▎01:30"

# ── 1. sb_applicable 本身 ────────────────────────────────────────────
report("路透字幕版 → sb_count 不適用（數不出來≠沒有）",
       S.sb_applicable(RT_CAPTIONED) is False)
report("路透正常格式（有 SHOTLIST）→ sb_count 照樣算數",
       S.sb_applicable(RT_NORMAL) is True)
report("AP Live Choice（有 SHOTLIST 無 SOUNDBITE）→ 照樣算數，擋不可放行",
       S.sb_applicable(AP_LIVE) is True)
report("沒有原文可判時維持原行為（不放寬）",
       S.sb_applicable("") is True and S.sb_applicable(None) is True)

# ⚠️ 二次修正（2026-08-09）：第一版用裸字比對，被 agent 寫進 src_text 的中文說明
# 騙倒——RT4131 的 src_text 尾巴附了判斷備註，裡面有「無 SHOTLIST 段」
# 「數不到 SOUNDBITE 字樣」，裸字就命中、照樣誤報（連四輪）。只認結構標記。
POLLUTED = RT_CAPTIONED + "\n[agent備註] 這則 STORY 以「STORY: ::」開頭、無 SHOTLIST 段，" \
                          "故數不到 SOUNDBITE 字樣；稿內兩位受訪者姓名職銜齊備，屬可掐的談話。"
report("src_text 被 agent 的中文說明污染時，仍判定為不適用（RT4131 實例）",
       S.sb_applicable(POLLUTED) is False)
report("結構標記帶冒號才算（SHOTLIST: ✓）", S.sb_applicable("SHOTLIST:\n1. WIDE") is True)
report("結構標記帶括號才算（(SOUNDBITE) ✓）", S.sb_applicable("2. (SOUNDBITE) MAN SAYING") is True)

# ── 2. 接上 bite_doubt 的實際效果 ────────────────────────────────────
report("字幕版 + sb_count=0 → 不再誤報假 BITE",
       S.bite_doubt(BITE_ENTRY, None, None) is None)
report("AP Live Choice + sb_count=0 → 仍然要報（0805 那批不可放行）",
       S.bite_doubt(BITE_ENTRY, 0, None) is not None)


# ── 3. 端到端：add-batch 走完整流程 ──────────────────────────────────
def run_batch(entries):
    d = tempfile.mkdtemp()
    sp, bp = os.path.join(d, "s.json"), os.path.join(d, "b.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump({"date": "0101", "items": []}, f)
    with open(bp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    subprocess.run([sys.executable, SCRIPT, "--file", sp, "add-batch", "--entries", bp],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
    with open(sp, encoding="utf-8-sig") as f:
        return {i["id"]: i for i in json.load(f)["items"]}


items = run_batch([{"id": "RT4107", "source": "RT", "checkpoint": "0809-0100",
                    "status": "has_script", "entry": BITE_ENTRY,
                    "sb_count": 0, "src_text": RT_CAPTIONED}])
it = items["RT4107"]
report("端到端：字幕版素材入庫後沒有 needs_review",
       "needs_review" not in it, f"殘留：{it.get('needs_review')!r}")
report("端到端：字幕版不把 sb_count=0 寫進狀態檔（否則稽核③ 換個地方再報一次）",
       "sb_count" not in it, f"實得 {it.get('sb_count')!r}")

items = run_batch([{"id": "AP123", "source": "AP", "checkpoint": "0809-0100",
                    "status": "has_script", "entry": BITE_ENTRY,
                    "sb_count": 0, "src_text": AP_LIVE}])
it = items["AP123"]
report("端到端：AP Live Choice 仍然被標 needs_review（防修過頭）",
       "needs_review" in it)
report("端到端：AP Live Choice 的 sb_count=0 有存進狀態檔",
       it.get("sb_count") == 0, f"實得 {it.get('sb_count')!r}")

items = run_batch([{"id": "RT9999", "source": "RT", "checkpoint": "0809-0100",
                    "status": "has_script", "entry": BITE_ENTRY,
                    "sb_count": 2, "src_text": RT_NORMAL}])
report("端到端：正常格式且真的有 SOUNDBITE → 乾淨入庫並存下數字",
       items["RT9999"].get("sb_count") == 2 and "needs_review" not in items["RT9999"])

print("\n" + ("全部通過" if ok else "有失敗"))
sys.exit(0 if ok else 1)
