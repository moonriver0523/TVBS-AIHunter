#!/usr/bin/env python3
"""Step B round 5 prep — screener v2, revised per the B4 hit-rate audit.

B4's screener reached 50% strict precision. `analysis_B4_fable.md` §4 audited
每個訊號 and prescribed fixes; this file implements them:

  ellipsis      最佳訊號（吐槽氣口/尷尬停頓全命中）      → highest weight
  redup         最大誤報源：專名疊字（珊珊/泡泡/狗狗）    → REPLACED, see below
  onoma         「轟-20」「35轟」武器/棒球量詞灌分         → strip N轟 / 轟-N first
  question      網路標問號堆疊灌分                        → OS 內文行才計
  exclam        SB 引語內驚嘆灌水                         → OS 行與 SB 行分開計
  quote         低命中，但意外抓到影音變色體              → 改為專用字串旗標
  split/line_std 幾乎純結構誤報                           → 降權，僅助語體切換偵測
  rare3         無獨立命中                                → 移除

The redup replacement matters most. B4's `([一-鿿])\\1` matched single-char
reduplication — which is overwhelmingly proper nouns (珊珊颱風, 泡泡瑪特) —
while its only true hits (心痛 心痛 心痛 心痛／停車！停車！停車！) were
repeated *phrases*. So v2 scores consecutive phrase repetition instead, which
targets N8「SB 原話劇場」directly and drops the name false positives by
construction.

Sampling obeys the corpus-hygiene rule: status == unread AND quality == ok.

Writes b5_screening.json (full ranking) and sample_B5/batch_XX.md (top N,
each draft prefixed with the signals that flagged it).
"""

from __future__ import annotations

import json
import re
import statistics
import unicodedata
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
STATUS = HERE / "reading_status.json"
OUT_JSON = HERE / "b5_screening.json"
OUT_DIR = HERE / "sample_B5"

TOP_N = 40
PER_BATCH = 10
MIN_CHARS = 700

CJK = r"[一-鿿]"
CJK_RE = re.compile(CJK)

# --- signal patterns --------------------------------------------------------
# 連續重複的詞組（2–4 字），允許中間夾空白或驚嘆/頓號分隔。
PHRASE_REPEAT_RE = re.compile(rf"({CJK}{{2,4}})(?:[\s　！!，,、。]*\1){{1,}}")
# 同字連放 3 次以上（刷刷刷／哈哈哈）＝擬聲或情緒爆發；兩字疊詞（珊珊）
# 刻意不算，那是專名的主要形態，正是 B4 的最大誤報源。
CHAR_RUN_RE = re.compile(rf"({CJK})\1{{2,}}")
# 擬聲字；先移除「轟-20」「35轟」「開轟」這類武器/棒球用法再計。
ONOMATOPOEIA = "砰轟碰咻唰嘟嗡叩噠鏘鏗咚喀嘎唏"
# 「轟炸/轟擊/開轟/N轟」是軍事與棒球的實詞用法，不是擬聲；「轟隆」才是。
WEAPON_BASEBALL_RE = re.compile(
    r"[0-9０-９]+\s*轟|轟\s*[-－]?\s*[0-9０-９]+|開轟|轟出|轟炸|轟擊|轟入|狂轟"
)
ELLIPSIS_RE = re.compile(r"…|\.\.\.")
SPLIT_LINE_RE = re.compile(rf"{CJK}\s+{CJK}(?:\s+{CJK})*")
# 影音變色強調體（B4 N1）：專用字串旗標，不進 z-score。
VIDEO_STYLE_RE = re.compile(r"變色強調|ICON|請放.{0,4}ICON|SUPER\s*與|上在講話人")

WEIGHTS = {
    "ellipsis": 2.0,        # 最佳訊號
    "phrase_repeat": 1.5,   # 取代 redup，直指 SB 原話劇場
    "onoma": 1.0,
    "question_os": 1.0,
    "exclam_os": 1.0,
    "split_lines": 0.3,     # 降權
    "line_std": 0.3,        # 降權
}


def width(line: str) -> float:
    return sum(1.0 if unicodedata.east_asian_width(ch) in ("F", "W") else 0.5 for ch in line)


def is_title_like(s: str) -> bool:
    """網路標／BAR 字卡：內部有空格分隔前後半句且夠長。問號驚嘆號不計這些行。"""
    if width(s) < 12:
        return False
    for m in re.finditer(r"\s+", s):
        i, j = m.start(), m.end()
        if 0 < i and j < len(s) and CJK_RE.match(s[i - 1]) and CJK_RE.match(s[j]):
            return True
    return False


def classify_lines(draft: str):
    """Split into (os_lines, sb_lines) — SB 區塊自 `SB` 標記起至空行止。"""
    os_lines, sb_lines = [], []
    in_sb = False
    in_title_block = False
    for raw in draft.splitlines():
        s = raw.strip()
        if not s:
            in_sb = False
            in_title_block = False
            continue
        if re.match(r"^(SB|SOT)\b", s):
            in_sb = True
            continue
        if re.match(r"^(NS|BAR|OS)\b", s) or s.startswith(("##", "==", ">")):
            in_sb = False
            continue
        if "網路標" in s:
            in_title_block = True
            continue
        if in_sb:
            sb_lines.append(s)
        elif in_title_block or is_title_like(s):
            continue          # 標題區不計問號/驚嘆號
        else:
            os_lines.append(s)
    return os_lines, sb_lines


def features(draft: str) -> dict[str, float]:
    cjk_n = max(1, len(CJK_RE.findall(draft)))
    per_k = 1000.0 / cjk_n
    os_lines, sb_lines = classify_lines(draft)
    os_text = "\n".join(os_lines)

    onoma_src = WEAPON_BASEBALL_RE.sub("", draft)
    all_lines = [l.strip() for l in draft.splitlines() if l.strip()]
    widths = [width(l) for l in all_lines if CJK_RE.search(l)]

    return {
        "ellipsis": len(ELLIPSIS_RE.findall(draft)) * per_k,
        "phrase_repeat": sum(len(PHRASE_REPEAT_RE.findall(l)) + len(CHAR_RUN_RE.findall(l))
                             for l in all_lines) * per_k * 5,
        "onoma": sum(onoma_src.count(ch) for ch in ONOMATOPOEIA) * per_k,
        "question_os": (os_text.count("？") + os_text.count("?")) * per_k,
        "exclam_os": (os_text.count("！") + os_text.count("!")) * per_k,
        "split_lines": sum(1 for l in all_lines if SPLIT_LINE_RE.search(l)) * per_k * 10,
        "line_std": statistics.pstdev(widths) if len(widths) > 5 else 0.0,
    }


def main() -> None:
    doc = json.loads(STATUS.read_text(encoding="utf-8"))
    status, quality = doc["status"], doc["quality"]
    records = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]

    pool, video_flagged = [], []
    skipped = 0
    for r in records:
        f = r["file"]
        if status.get(f) != "unread" or len(r["draft"]) < MIN_CHARS:
            continue
        if quality.get(f) != "ok":
            skipped += 1
            continue
        if VIDEO_STYLE_RE.search(r["draft"]):
            video_flagged.append(f)
        pool.append((r, features(r["draft"])))
    print(f"pool: {len(pool)} (skipped {skipped} non-ok quality)")
    print(f"影音變色強調體旗標命中: {len(video_flagged)} 篇")

    keys = list(WEIGHTS)
    stats_ = {}
    for k in keys:
        vals = [f[k] for _, f in pool]
        stats_[k] = (statistics.mean(vals), statistics.pstdev(vals) or 1.0)

    scored = []
    for r, f in pool:
        zs = {k: (f[k] - stats_[k][0]) / stats_[k][1] for k in keys}
        score = sum(max(0.0, zs[k]) * WEIGHTS[k] for k in keys)
        top = sorted(((k, z) for k, z in zs.items() if z > 1.0), key=lambda kv: -kv[1])
        scored.append({
            "file": r["file"], "chars": len(r["draft"]), "score": round(score, 2),
            "signals": {k: round(z, 1) for k, z in top},
            "video_style": r["file"] in set(video_flagged),
            "_draft": r["draft"],
        })
    scored.sort(key=lambda d: -d["score"])

    OUT_JSON.write_text(json.dumps(
        {"video_style_candidates": video_flagged,
         "ranking": [{k: v for k, v in d.items() if k != "_draft"} for d in scored[:200]]},
        ensure_ascii=False, indent=1), encoding="utf-8")

    # top N, plus any 影音體 candidate that didn't make the cut (rare register,
    # only 2 known specimens — worth reading every one we can find)
    picked = scored[:TOP_N]
    picked_files = {d["file"] for d in picked}
    extras = [d for d in scored if d["video_style"] and d["file"] not in picked_files]
    picked += extras
    if extras:
        print(f"另補入 {len(extras)} 篇影音體候選（未進前 {TOP_N} 名）")

    OUT_DIR.mkdir(exist_ok=True)
    for b in range(0, len(picked), PER_BATCH):
        batch = picked[b:b + PER_BATCH]
        lines = []
        for d in batch:
            sig = "、".join(f"{k}(z={z})" for k, z in d["signals"].items()) or "綜合"
            vs = "｜⚑影音變色強調體候選" if d["video_style"] else ""
            lines.append(f"\n\n{'='*70}\n=== 稿件：{d['file']}\n"
                         f"=== 異常訊號：{sig}｜總分 {d['score']}{vs}\n{'='*70}\n")
            lines.append(d["_draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(d['chars'] for d in batch)} chars")

    print("\nTop 10:")
    for d in picked[:10]:
        print(f"  {d['score']:6.2f}  {d['file'][:46]}  {list(d['signals'])[:3]}")


if __name__ == "__main__":
    main()
