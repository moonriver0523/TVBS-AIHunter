#!/usr/bin/env python3
"""Step B round 4 prep — anomaly screening over the ENTIRE unread pool.

B3 caught techniques that recur; B4 hunts one-off experiments ("特別的寫稿
變化") that random sampling would miss. Strategy: score all unread drafts on
style-anomaly signals, then have Fable close-read only the top-ranked ones.

Signals per draft (z-scored against the unread population, |z| summed):
  - exclam / question / quote / ellipsis rates (per 1000 CJK chars)
  - 拆字 lines (isolated single CJK chars separated by spaces — 頓挫排版)
  - reduplication rate (疊字 AA patterns — 擬聲/節奏訊號)
  - onomatopoeia lexicon hits (砰轟碰咻唰嘟嗡叩噠鏘)
  - line-length dispersion (std of cleaned line widths — 版面實驗訊號)
  - rare-trigram ratio (trigrams appearing in ≤3 drafts corpus-wide —
    罕見用語；會偏向特殊題材，但特殊題材本就常伴隨特殊寫法，交給精讀判斷)

Drafts flagged non-`ok` in reading_status.json's `quality` map (practice /
test drafts, AI-template-contaminated drafts, near-empty stubs) are excluded
up front — see tag_unread.py. Any future sampling round must do the same.

Writes:
  - b4_screening.json  : full ranking with per-draft signal breakdown
  - sample_B4/batch_XX.md : top N drafts (10/batch), each prefixed with its
    filename AND the signals that flagged it (so the reader knows why)
"""

from __future__ import annotations

import json
import math
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
STATUS = HERE / "reading_status.json"
OUT_JSON = HERE / "b4_screening.json"
OUT_DIR = HERE / "sample_B4"

TOP_N = 40
PER_BATCH = 10
MIN_CHARS = 700          # too-short stubs carry no style

CJK_RE = re.compile(r"[一-鿿]")
ONOMATOPOEIA = "砰轟碰咻唰嘟嗡叩噠鏘鏗咚喀嘎唏". replace(" ", "")
SPLIT_LINE_RE = re.compile(r"[一-鿿]\s+[一-鿿](?:\s+[一-鿿])*")  # 拆 字 頓挫


def width(line: str) -> float:
    return sum(1.0 if unicodedata.east_asian_width(ch) in ("F", "W") else 0.5 for ch in line)


def features(draft: str, rare_ratio: float) -> dict[str, float]:
    cjk_n = max(1, len(CJK_RE.findall(draft)))
    per_k = 1000.0 / cjk_n
    lines = [l.strip() for l in draft.splitlines() if l.strip()]
    widths = [width(l) for l in lines if CJK_RE.search(l)]
    return {
        "exclam": (draft.count("！") + draft.count("!")) * per_k,
        "question": (draft.count("？") + draft.count("?")) * per_k,
        "quote": sum(draft.count(c) for c in "「」『』“”") * per_k,
        "ellipsis": (draft.count("…") + draft.count("...")) * per_k,
        "split_lines": sum(1 for l in lines if SPLIT_LINE_RE.search(l)) * per_k * 10,
        "redup": len(re.findall(r"([一-鿿])\1", draft)) * per_k,
        "onoma": sum(draft.count(ch) for ch in ONOMATOPOEIA) * per_k,
        "line_std": statistics.pstdev(widths) if len(widths) > 5 else 0.0,
        "rare3": rare_ratio * 100,
    }


def main() -> None:
    _status_doc = json.loads(STATUS.read_text(encoding="utf-8"))
    status = _status_doc["status"]
    quality = _status_doc["quality"]   # regenerate via tag_unread.py if missing
    records = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]

    # document frequency of trigrams across the WHOLE corpus (read + unread)
    df: Counter = Counter()
    grams_per_file: dict[str, set[str]] = {}
    for r in records:
        cjk = "".join(CJK_RE.findall(r["draft"]))
        grams = {cjk[i:i + 3] for i in range(len(cjk) - 2)}
        grams_per_file[r["file"]] = grams
        df.update(grams)

    pool = []
    n_excluded = 0
    for r in records:
        if status.get(r["file"]) != "unread" or len(r["draft"]) < MIN_CHARS:
            continue
        if quality.get(r["file"]) != "ok":   # practice / ai_assisted / stub
            n_excluded += 1
            continue
        grams = grams_per_file[r["file"]]
        rare_ratio = (sum(1 for g in grams if df[g] <= 3) / len(grams)) if grams else 0.0
        pool.append((r, features(r["draft"], rare_ratio)))
    print(f"unread pool screened: {len(pool)} (excluded {n_excluded} non-ok-quality drafts)")

    # z-score each feature over the pool
    keys = list(pool[0][1].keys())
    stats_ = {}
    for k in keys:
        vals = [f[k] for _, f in pool]
        mu = statistics.mean(vals)
        sd = statistics.pstdev(vals) or 1.0
        stats_[k] = (mu, sd)

    scored = []
    for r, f in pool:
        zs = {k: (f[k] - stats_[k][0]) / stats_[k][1] for k in keys}
        # positive-side anomalies only (we hunt "more of something unusual")
        score = sum(max(0.0, z) for z in zs.values())
        top_signals = sorted(((k, z) for k, z in zs.items() if z > 1.0),
                             key=lambda kv: -kv[1])
        scored.append({
            "file": r["file"], "chars": len(r["draft"]), "score": round(score, 2),
            "signals": {k: round(z, 1) for k, z in top_signals},
            "_draft": r["draft"],
        })
    scored.sort(key=lambda d: -d["score"])

    OUT_JSON.write_text(json.dumps(
        [{k: v for k, v in d.items() if k != "_draft"} for d in scored[:200]],
        ensure_ascii=False, indent=1), encoding="utf-8")

    OUT_DIR.mkdir(exist_ok=True)
    picked = scored[:TOP_N]
    for b in range(0, len(picked), PER_BATCH):
        batch = picked[b:b + PER_BATCH]
        lines = []
        for d in batch:
            sig = "、".join(f"{k}(z={z})" for k, z in d["signals"].items()) or "綜合"
            lines.append(f"\n\n{'='*70}\n=== 稿件：{d['file']}\n=== 異常訊號：{sig}｜總分 {d['score']}\n{'='*70}\n")
            lines.append(d["_draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(d['chars'] for d in batch)} chars")

    print("\nTop 10 preview:")
    for d in picked[:10]:
        print(f"  {d['score']:6.2f}  {d['file'][:50]}  {list(d['signals'])[:3]}")


if __name__ == "__main__":
    main()
