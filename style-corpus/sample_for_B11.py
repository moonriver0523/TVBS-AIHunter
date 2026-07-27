#!/usr/bin/env python3
"""Step B round 11 prep — switch axis from topic to LENGTH.

Why the axis changes
--------------------
B6–B10 sampled by subtopic keywords. B10 proved that seam is mined out: six
brand-new subtopics yielded two usable drafts, and the 984 remaining drafts are
59.5% war+politics — the two topics already read 184 times. More keyword
sampling would just resample B1–B5.

Length is a better axis for three reasons:
  1. It is an **objective field**. No keyword list, so none of the mislabelling
     that dominated B6–B10 can happen — there is nothing to mislabel.
  2. Long drafts carry the **structural** techniques. B2's six long-form rules
     and B8's 四字對仗標題群 all came out of 9000+ char drafts.
  3. B2 read only 10 long drafts. 43 remain unread — a real, untouched seam.

Selection: longest first. Unlike the keyword ranker (B9), this is not a
relevance proxy — a long draft is definitionally long. Longest-first simply
maximises structural material per draft read.

Second job: finally test B8's untested split signal
---------------------------------------------------
B8 §1-3 observed that composite files (one file, several unrelated stories)
had reached 28% and guessed the split signal was **a count of `TVBS 許岱軒`
sign-offs** — one per story. B9 and B10 both repeated "still untested". It has
been carried as a to-do for three rounds without anyone checking it.

    PRE-REGISTERED HYPOTHESIS (fixed before reading any B11 draft):
      H1  a draft with >=2 `TVBS <name>` sign-offs is a composite file
          (precision >= 80%)
      H2  a draft with exactly 1 sign-off is a single story
          (precision >= 80%)

Long-form 專題 are the least likely place for composites, which makes this a
conservative test: if the signal survives here it is worth building on; if the
sign-off count is noisy even in clean long drafts, drop the idea for good.

Writes b11_coverage.json and sample_B11/batch_XX.md.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from sample_for_B7 import ai_shape

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
STATUS = HERE / "reading_status.json"
OUT_JSON = HERE / "b11_coverage.json"
OUT_DIR = HERE / "sample_B11"

MIN_CHARS = 9000     # B2's long-form threshold
N_PICK = 6
PER_BATCH = 3

SIGNOFF = re.compile(r"TVBS[ 　]+[一-鿿]{2,4}")

HYPOTHESIS = {
    "H1": "署名 >=2 次的稿件是一檔多稿，精準度 >=80%",
    "H2": "署名恰好 1 次的稿件是單一則稿，精準度 >=80%",
    "note": "長專題是複合檔最不可能出現的地方，故本測試偏保守——"
            "訊號若在乾淨長稿都不穩，這個構想就該永久放棄",
}


def signoff_count(draft: str) -> int:
    """Distinct sign-off lines, not raw matches: the same sign-off often gets
    pasted twice in a draft's tail notes."""
    return len({m.strip() for m in SIGNOFF.findall(draft)})


def main() -> None:
    doc = json.loads(STATUS.read_text(encoding="utf-8"))
    status, quality = doc["status"], doc["quality"]
    records = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]

    pool, rejected, ai_flagged = [], Counter(), []
    for r in records:
        f, draft = r["file"], r["draft"]
        if status.get(f) != "unread":
            rejected["已讀過（B1–B10）"] += 1
            continue
        if quality.get(f) != "ok":
            rejected["quality 非 ok"] += 1
            continue
        if len(draft) < MIN_CHARS:
            rejected[f"未達 {MIN_CHARS} 字"] += 1
            continue
        shape = ai_shape(draft)
        if shape:
            ai_flagged.append({"file": f, "shape": shape})
            rejected["疑似流程／AI 產出"] += 1
            continue
        pool.append(r)

    pool.sort(key=lambda r: -len(r["draft"]))
    picked = pool[:N_PICK]

    print(f"== B11 候選池（篇幅 >= {MIN_CHARS} 字，無關鍵詞過濾）==")
    print(f"  可用長稿 {len(pool)} 篇；抽最長的 {len(picked)} 篇")
    print("\n== 排除統計 ==")
    for k, n in rejected.most_common():
        print(f"  {k:22s} {n:5d}")

    print(f"\n== 抽出（長度／署名次數）==")
    for r in picked:
        print(f"  {r['file'][:40]:40s} {len(r['draft']):6d} 字   署名 {signoff_count(r['draft'])} 次")

    print(f"\n== 署名訊號在整個長稿池的分布（H1／H2 的母體）==")
    dist = Counter(signoff_count(r["draft"]) for r in pool)
    for k in sorted(dist):
        print(f"  署名 {k} 次： {dist[k]:3d} 篇")

    OUT_JSON.write_text(json.dumps({
        "method": "B11 改用篇幅軸（客觀欄位，無關鍵詞）；並預先登記測試 B8 提出但從未實測的一檔多稿切分訊號",
        "min_chars": MIN_CHARS,
        "hypothesis": HYPOTHESIS,
        "pool_size": len(pool),
        "signoff_distribution": {str(k): v for k, v in sorted(dist.items())},
        "rejected": dict(rejected),
        "ai_flagged": ai_flagged,
        "picked": [{"file": r["file"], "chars": len(r["draft"]),
                    "signoffs": signoff_count(r["draft"])} for r in picked],
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    OUT_DIR.mkdir(exist_ok=True)
    for b in range(0, len(picked), PER_BATCH):
        batch = picked[b:b + PER_BATCH]
        lines = []
        for r in batch:
            lines.append(f"\n\n{'='*70}\n=== 稿件：{r['file']}\n"
                         f"=== {len(r['draft'])} 字／署名 {signoff_count(r['draft'])} 次\n{'='*70}\n")
            lines.append(r["draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(len(r['draft']) for r in batch)} chars")


if __name__ == "__main__":
    main()
