#!/usr/bin/env python3
"""Step B prep — pick ~50 representative drafts for qualitative reading.

Stratified sampling from draft_corpus.jsonl:
  - only drafts with substantial content (1200–9000 chars) so the reader
    sees full narrative arcs, not stubs or mega-specials
  - spread evenly across the corpus in file order (which is roughly
    chronological by MMDD prefix) so early/late periods are both covered

Writes style-corpus/sample_B/batch_01.md … batch_05.md (10 drafts each),
each draft prefixed with its filename for traceability.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
OUT_DIR = HERE / "sample_B"

N_SAMPLES = 50
PER_BATCH = 10
MIN_CHARS = 1200
MAX_CHARS = 9000


def main() -> None:
    records = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    eligible = [r for r in records if MIN_CHARS <= len(r["draft"]) <= MAX_CHARS]
    print(f"eligible {len(eligible)} / {len(records)}")

    # even spread across the (roughly chronological) ordering
    step = len(eligible) / N_SAMPLES
    picked = [eligible[int(i * step)] for i in range(N_SAMPLES)]

    OUT_DIR.mkdir(exist_ok=True)
    for b in range(0, N_SAMPLES, PER_BATCH):
        batch = picked[b:b + PER_BATCH]
        lines = []
        for rec in batch:
            lines.append(f"\n\n{'='*70}\n=== 稿件：{rec['file']}\n{'='*70}\n")
            lines.append(rec["draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(len(r['draft']) for r in batch)} chars")


if __name__ == "__main__":
    main()
