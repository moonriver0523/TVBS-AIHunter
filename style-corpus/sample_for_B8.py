#!/usr/bin/env python3
"""Step B round 8 prep — exhaust the two highest-yield subtopics.

Why these two
-------------
B7 read 5 drafts from each of eight never-read subtopics. Two stood out:
  - 法庭審判: 5/5 on-topic, and every one of the five yielded a distinct
    templatable technique (U4–U8). Highest technique density of any subtopic
    across all seven rounds.
  - 勞資爭議: 4/5 on-topic, and its two long drafts shared one reusable
    long-form skeleton (the case–policy–case sandwich, U23).
Both pools are small enough to read to the bottom, so B8 exhausts them
instead of sampling. No quota, no spacing — every remaining draft.

Keyword tightening (B7 §1-3)
----------------------------
B7's cleanest methodological finding: **subtopic-exclusive action words beat
scene nouns.**
法庭/選舉/宗教 (開庭, 判決, 開票, 教宗) mislabelled 0%; 太空/教育/移民
(發射, 學生, 邊境) mislabelled 40–60%, because a scene noun is hit by any
story that happens to pass through that scene.

So the 勞資 list drops the scene nouns that let a general economics story in
(勞工／工時／勞動條件 — the one B7 mislabel, 0711-1, was an inflation story
that merely used them). 法庭's list was already all action words and is kept
as-is, minus nothing.

Writes b8_coverage.json and sample_B8/batch_XX.md.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from sample_for_B7 import HEAD_CHARS, MIN_CHARS, MIN_HITS, ai_shape

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
STATUS = HERE / "reading_status.json"
OUT_JSON = HERE / "b8_coverage.json"
OUT_DIR = HERE / "sample_B8"
PER_BATCH = 8

SUBTOPICS: dict[str, list[str]] = {
    # Unchanged from B7 — 0% mislabel, every term is a courtroom action.
    "法庭審判": ["法官", "開庭", "判決", "判刑", "陪審", "出庭", "檢方", "辯護", "法庭",
                 "上訴", "有罪", "無罪", "認罪", "求刑", "審判", "起訴書", "宣判"],
    # Tightened: 勞工／工時／勞動條件／抗議薪資 removed as scene nouns.
    "勞資爭議": ["罷工", "工會", "裁員", "資遣", "加薪", "勞資", "停工", "集體談判",
                 "關廠", "遣散", "無薪假", "勞資協商"],
}


def classify(draft: str) -> tuple[str | None, dict[str, int]]:
    head = draft[:HEAD_CHARS]
    scored = {}
    for name, kws in SUBTOPICS.items():
        hits = sum(draft.count(k) for k in kws)
        if hits >= MIN_HITS and any(k in head for k in kws):
            scored[name] = hits
    if not scored:
        return None, {}
    return max(scored, key=lambda t: scored[t]), scored


def main() -> None:
    doc = json.loads(STATUS.read_text(encoding="utf-8"))
    status, quality = doc["status"], doc["quality"]
    records = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]

    pools: dict[str, list] = defaultdict(list)
    rejected = Counter()
    ai_flagged: list[dict] = []

    for r in records:
        f, draft = r["file"], r["draft"]
        if status.get(f) != "unread":
            rejected["已讀過（B1–B7）"] += 1
            continue
        if quality.get(f) != "ok":
            rejected["quality 非 ok"] += 1
            continue
        if len(draft) < MIN_CHARS:
            rejected["過短 <1200 字"] += 1
            continue
        shape = ai_shape(draft)
        if shape:
            ai_flagged.append({"file": f, "shape": shape})
            rejected["疑似流程／AI 產出"] += 1
            continue
        topic, scored = classify(draft)
        if topic is None:
            rejected["不屬這兩個子類"] += 1
            continue
        pools[topic].append({"rec": r, "hits": scored[topic]})

    print("== B8 候選池（抽乾，不設配額）==")
    for t in SUBTOPICS:
        print(f"  {t:6s} {len(pools.get(t, [])):4d} 篇")
    print("\n== 排除統計 ==")
    for k, n in rejected.most_common():
        print(f"  {k:24s} {n:5d}")
    print(f"\n== 疑似流程／AI 產出前置攔截：{len(ai_flagged)} 篇 ==")
    for shape, n in Counter(x["shape"] for x in ai_flagged).most_common():
        print(f"  {shape:28s} {n:4d}")

    picked = []
    for t in SUBTOPICS:
        for item in sorted(pools.get(t, []), key=lambda x: -x["hits"]):
            picked.append((t, item["rec"], item["hits"]))

    print(f"\n== 全數抽出 {len(picked)} 篇 ==")
    for t, n in Counter(t for t, _, _ in picked).most_common():
        print(f"  {t:6s} {n} 篇")

    OUT_JSON.write_text(json.dumps({
        "method": "B8 抽乾法庭＋勞資（B7 最高產出的兩個子類；關鍵詞改為只用專屬動作詞）",
        "pool_sizes": {t: len(pools.get(t, [])) for t in SUBTOPICS},
        "rejected": dict(rejected),
        "ai_flagged": ai_flagged,
        "picked": [{"subtopic": t, "file": r["file"], "chars": len(r["draft"]), "hits": h}
                   for t, r, h in picked],
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    OUT_DIR.mkdir(exist_ok=True)
    for b in range(0, len(picked), PER_BATCH):
        batch = picked[b:b + PER_BATCH]
        lines = []
        for topic, r, hits in batch:
            lines.append(f"\n\n{'='*70}\n=== 稿件：{r['file']}\n"
                         f"=== 子類：{topic}（關鍵詞命中 {hits} 次）\n{'='*70}\n")
            lines.append(r["draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(len(r['draft']) for _, r, _ in batch)} chars")


if __name__ == "__main__":
    main()
