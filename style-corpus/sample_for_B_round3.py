#!/usr/bin/env python3
"""Step B round 3 — rare-technique hunting sample.

B1/B2 saturated the COMMON patterns. B3's mission is different: hunt for
rare, one-off, high-signature techniques. Sampling therefore maximises
coverage of unseen material:

  - reads reading_status.json and picks ONLY from the `unread` pool
  - 50 drafts from the 1200-9000 band, evenly interleaved
  - the 2 mega drafts (>20000 chars) — never sampled in any round
  - 8 from the top of the short band (700-1200 chars) — a register never
    sampled (quick items often carry the sharpest one-liners)

Writes style-corpus/sample_B3/batch_01.md ... (10 drafts per batch).
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
STATUS = HERE / "reading_status.json"
OUT_DIR = HERE / "sample_B3"

N_NORMAL = 50
N_SHORT = 8
PER_BATCH = 10


def main() -> None:
    status = json.loads(STATUS.read_text(encoding="utf-8"))["status"]
    records = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]
    unread = [r for r in records if status.get(r["file"]) == "unread"]
    print(f"unread pool: {len(unread)}")

    normal = [r for r in unread if 1200 <= len(r["draft"]) <= 9000]
    mega = [r for r in unread if len(r["draft"]) > 20000]
    short = [r for r in unread if 700 <= len(r["draft"]) < 1200]
    print(f"normal {len(normal)}, mega {len(mega)}, short(700-1200) {len(short)}")

    step = len(normal) / N_NORMAL
    picked = [normal[int(i * step)] for i in range(N_NORMAL)]

    sstep = max(1, len(short) / N_SHORT)
    picked_short = [short[int(i * sstep)] for i in range(min(N_SHORT, len(short)))]

    allpicked = picked + mega + picked_short
    OUT_DIR.mkdir(exist_ok=True)
    for b in range(0, len(allpicked), PER_BATCH):
        batch = allpicked[b:b + PER_BATCH]
        lines = []
        for rec in batch:
            n = len(rec["draft"])
            tag = "（超長稿）" if n > 20000 else "（短稿）" if n < 1200 else ""
            lines.append(f"\n\n{'='*70}\n=== 稿件：{rec['file']} {tag}\n{'='*70}\n")
            lines.append(rec["draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(len(r['draft']) for r in batch)} chars")


if __name__ == "__main__":
    main()
