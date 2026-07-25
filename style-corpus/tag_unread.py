#!/usr/bin/env python3
"""Tag every corpus draft with its B-step reading status AND a quality flag,
so future targeted rounds sample only from the clean unread pool.

Reads:
  - draft_corpus.jsonl
  - sample_B/batch_*.md   (round 1 picks)
  - sample_B2/batch_*.md  (round 2 picks)
  - sample_B3/batch_*.md  (round 3 picks)
Writes:
  - reading_status.json : per record {read: B1|B2|B3|unread, quality: ...},
    plus a summary block (counts, unread breakdown by length band)

Quality flags (B4 語料衛生發現，2026-07-25)：
  - `practice`    練習/測試稿（檔名含 TEST／練習／practice）——非正式產出
  - `ai_assisted` 含 AI 產稿模板痕跡（【主播稿頭】【總長度】等），2026 年語料
                  已混入 AI 輔助產出，萃取人味時須排除
  - `stub`        近乎空白的樣板（中文字 < 60），只有標題或佔位符
  - `ok`          可用於風格萃取

抽樣腳本應只從 `read == "unread" and quality == "ok"` 取樣。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
OUT = HERE / "reading_status.json"

CJK_RE = re.compile(r"[一-鿿]")
AI_MARKERS = ("【主播稿頭】", "【記者OS內文", "【總長度】", "預估朗讀長度")
PRACTICE_PAT = re.compile(r"practice|test|練習", re.I)
STUB_MIN_CJK = 60


def quality_of(file: str, draft: str) -> str:
    if PRACTICE_PAT.search(file):
        return "practice"
    if any(m in draft for m in AI_MARKERS):
        return "ai_assisted"
    if len(CJK_RE.findall(draft)) < STUB_MIN_CJK:
        return "stub"
    return "ok"


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

    # `status` stays a flat {file: read-state} map — sample_for_B_round3.py and
    # screen_for_B4.py already consume it in that shape; `quality` is additive.
    status: dict[str, str] = {}
    quality: dict[str, str] = {}
    bands = {"<1200": 0, "1200-9000": 0, "9000-20000": 0, ">20000": 0}
    qcount: dict[str, int] = {}

    for r in records:
        f = r["file"]
        q = quality_of(f, r["draft"])
        quality[f] = q
        qcount[q] = qcount.get(q, 0) + 1

        if f in b1:
            status[f] = "B1"
        elif f in b2:
            status[f] = "B2"
        elif f in b3:
            status[f] = "B3"
        else:
            status[f] = "unread"
            if q == "ok":  # bands describe the *usable* unread pool
                n = len(r["draft"])
                band = "<1200" if n < 1200 else "1200-9000" if n <= 9000 else "9000-20000" if n <= 20000 else ">20000"
                bands[band] += 1

    clean_unread = sum(1 for f, v in status.items() if v == "unread" and quality[f] == "ok")
    summary = {
        "total": len(records),
        "read_B1": sum(1 for v in status.values() if v == "B1"),
        "read_B2": sum(1 for v in status.values() if v == "B2"),
        "read_B3": sum(1 for v in status.values() if v == "B3"),
        "unread_total": sum(1 for v in status.values() if v == "unread"),
        "unread_usable": clean_unread,
        "unread_usable_by_length": bands,
        "quality_counts": qcount,
        "note": "抽樣請只取 status=unread 且 quality=ok 的稿件（B4 語料衛生，2026-07-25）",
    }
    OUT.write_text(
        json.dumps({"summary": summary, "status": status, "quality": quality},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
