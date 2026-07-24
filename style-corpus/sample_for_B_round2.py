#!/usr/bin/env python3
"""Step B round 2 — 50 more drafts for qualitative reading.

Differences from round 1 (sample_for_B.py):
  - excludes every draft already read in round 1 (parsed from sample_B/batch_*.md)
  - 40 drafts from the same 1200-9000 char band, evenly interleaved across
    the remaining corpus
  - 10 long-form drafts (9000-20000 chars) — 專題/特別報導 were entirely
    excluded from round 1, and their narrative pacing is a distinct register

Writes style-corpus/sample_B2/batch_01.md ... batch_05.md (10 drafts each).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
ROUND1_DIR = HERE / "sample_B"
OUT_DIR = HERE / "sample_B2"

N_NORMAL = 40
N_LONG = 10
PER_BATCH = 10
MIN_CHARS, MAX_CHARS = 1200, 9000
LONG_MIN, LONG_MAX = 9000, 20000


def round1_files() -> set[str]:
    seen: set[str] = set()
    for f in ROUND1_DIR.glob("batch_*.md"):
        for m in re.finditer(r"^=== 稿件：(.+)$", f.read_text(encoding="utf-8"), re.M):
            seen.add(m.group(1).strip())
    return seen


def main() -> None:
    exclude = round1_files()
    print(f"round-1 files excluded: {len(exclude)}")

    records = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    fresh = [r for r in records if r["file"] not in exclude]

    normal = [r for r in fresh if MIN_CHARS <= len(r["draft"]) <= MAX_CHARS]
    longform = [r for r in fresh if LONG_MIN < len(r["draft"]) <= LONG_MAX]
    print(f"eligible normal {len(normal)}, longform {len(longform)}")

    step = len(normal) / N_NORMAL
    picked = [normal[int(i * step)] for i in range(N_NORMAL)]

    lstep = max(1, len(longform) / N_LONG)
    picked_long = [longform[int(i * lstep)] for i in range(min(N_LONG, len(longform)))]

    allpicked = picked + picked_long
    OUT_DIR.mkdir(exist_ok=True)
    for b in range(0, len(allpicked), PER_BATCH):
        batch = allpicked[b:b + PER_BATCH]
        lines = []
        for rec in batch:
            tag = "（長篇專題）" if len(rec["draft"]) > LONG_MIN else ""
            lines.append(f"\n\n{'='*70}\n=== 稿件：{rec['file']} {tag}\n{'='*70}\n")
            lines.append(rec["draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(len(r['draft']) for r in batch)} chars")


if __name__ == "__main__":
    main()
