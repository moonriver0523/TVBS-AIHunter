#!/usr/bin/env python3
"""Tag every corpus draft with its B-step reading status, so future targeted
rounds can sample only from the unread pool.

Reads:
  - draft_corpus.jsonl
  - sample_B/batch_*.md   (round 1 picks)
  - sample_B2/batch_*.md  (round 2 picks)
Writes:
  - reading_status.json : {file: "B1" | "B2" | "unread"} for every record,
    plus a summary block (counts, unread breakdown by length band)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
OUT = HERE / "reading_status.json"


def picks(d: Path) -> set[str]:
    s: set[str] = set()
    for f in d.glob("batch_*.md"):
        for m in re.finditer(r"^=== 稿件：(.+?)\s*(?:（長篇專題）|（超長稿）|（短稿）)?\s*$", f.read_text(encoding="utf-8"), re.M):
            s.add(m.group(1).strip())
    return s


def main() -> None:
    b1 = picks(HERE / "sample_B")
    b2 = picks(HERE / "sample_B2")
    b3 = picks(HERE / "sample_B3")
    records = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]

    status: dict[str, str] = {}
    bands = {"<1200": 0, "1200-9000": 0, "9000-20000": 0, ">20000": 0}
    for r in records:
        f = r["file"]
        if f in b1:
            status[f] = "B1"
        elif f in b2:
            status[f] = "B2"
        elif f in b3:
            status[f] = "B3"
        else:
            status[f] = "unread"
            n = len(r["draft"])
            band = "<1200" if n < 1200 else "1200-9000" if n <= 9000 else "9000-20000" if n <= 20000 else ">20000"
            bands[band] += 1

    summary = {
        "total": len(records),
        "read_B1": sum(1 for v in status.values() if v == "B1"),
        "read_B2": sum(1 for v in status.values() if v == "B2"),
        "read_B3": sum(1 for v in status.values() if v == "B3"),
        "unread": sum(1 for v in status.values() if v == "unread"),
        "unread_by_length": bands,
    }
    OUT.write_text(
        json.dumps({"summary": summary, "status": status}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
