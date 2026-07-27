#!/usr/bin/env python3
"""Step B round 9 prep — re-sample the three subtopics B7 mislabelled worst,
with action-word keywords, AND run a pre-registered test of B8's ranker claim.

Two jobs in one round
---------------------

**Job 1 — fix the three bad subtopics.** B7 mislabelled 太空科學 3/5, 教育校園
2/5 and 移民難民 2/5, all for the same reason: the keyword lists were built out
of *scene nouns* (發射／學生／邊境) that any story passing through that scene
will hit. 「發射RPG火箭」and「伊朗學生示威」are not space and education stories.
B8 rebuilt 勞資's list out of *subtopic-exclusive action words* and the mislabel
rate went 25% → 12%. Same surgery here.

**Job 2 — test B8 §1-2 properly.** B8 noticed that among its 25 drafts, all 7
with ≥10 keyword hits were on-topic while only 44% of the 18 below 10 were. That
is a post-hoc observation on a sample that was never designed to test it, so it
could easily be an artefact of which drafts happened to be in the pool.

    PRE-REGISTERED HYPOTHESIS (written before any B9 draft was read):
      H1  drafts with hits >= 10 are on-topic (強真+真) at >= 85%
      H2  drafts with hits <  10 are on-topic at <= 60%
      H3  the gap between the two strata is >= 25 points

To make that testable the sample is deliberately STRATIFIED rather than
top-ranked: 6 drafts from the high band and 2 from the low band per subtopic.
Taking only the top would guarantee a high hit rate and prove nothing.

If H1–H3 hold, B10 can safely switch to "pool at >=3, rank by hits, read the
top" and stop spending quota on the tail. If they fail, the ranker idea dies
here and the 12% mislabel rate is as good as keyword filtering gets.

Writes b9_coverage.json and sample_B9/batch_XX.md.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from sample_for_B7 import HEAD_CHARS, MIN_CHARS, MIN_HITS, ai_shape

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
STATUS = HERE / "reading_status.json"
OUT_JSON = HERE / "b9_coverage.json"
OUT_DIR = HERE / "sample_B9"

PER_BATCH = 8
HIGH_BAND = 10          # the threshold under test
N_HIGH, N_LOW = 6, 2    # per subtopic

# Every term below is something that only happens in that subtopic. Scene nouns
# that B7 used and B9 drops are named in the comments so the change is auditable.
SUBTOPICS: dict[str, list[str]] = {
    # dropped: 發射, 火箭, 衛星, 太空, 太陽能 — 「發射RPG火箭」「飛上青天」all hit those
    "太空科學": ["太空人", "太空站", "太空總署", "太空漫步", "登月", "火星", "星艦",
                 "NASA", "探測器", "返回艙", "對接", "運載火箭", "彗星", "隕石",
                 "太空衣", "軌道艙", "載人任務", "發射升空"],
    # dropped: 學生, 大學, 老師, 教育, 考試 — 「伊朗學生示威」「倫敦大學學者」hit those
    "教育校園": ["開學", "課綱", "補習", "校長", "畢業典禮", "教育部", "升學", "課堂",
                 "教室", "校方", "退學", "學費", "教科書", "家長會", "義務教育",
                 "教職員", "校車", "學區"],
    # dropped: 邊境, 邊界, 難民 — 「泰柬邊境」「哈爾科夫」hit those
    "移民難民": ["遣返", "偷渡", "庇護", "驅逐出境", "非法入境", "移民局", "ICE",
                 "綠卡", "居留權", "移民法", "收容所", "難民營", "移民署",
                 "無證移民", "尋求庇護", "簽證", "移民政策"],
}

HYPOTHESIS = {
    "H1": "hits >= 10 的稿件，嚴格命中率 >= 85%",
    "H2": "hits < 10 的稿件，嚴格命中率 <= 60%",
    "H3": "兩層的差距 >= 25 個百分點",
    "note": "抽樣刻意分層（高段6篇＋低段2篇）而非只取前段，只取前段無法證偽",
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
            rejected["已讀過（B1–B8）"] += 1
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
            rejected["不屬這三個子類"] += 1
            continue
        pools[topic].append({"rec": r, "hits": scored[topic]})

    print("== B9 候選池（關鍵詞已收緊為專屬動作詞）==")
    for t in SUBTOPICS:
        pool = pools.get(t, [])
        hi = sum(1 for x in pool if x["hits"] >= HIGH_BAND)
        print(f"  {t:6s} {len(pool):4d} 篇（高段 hits>={HIGH_BAND}: {hi}，低段: {len(pool)-hi}）")
    print("\n== 排除統計 ==")
    for k, n in rejected.most_common():
        print(f"  {k:22s} {n:5d}")
    print(f"\n== 疑似流程／AI 產出前置攔截：{len(ai_flagged)} 篇 ==")

    picked = []
    for t in SUBTOPICS:
        pool = sorted(pools.get(t, []), key=lambda x: -x["hits"])
        high = [x for x in pool if x["hits"] >= HIGH_BAND][:N_HIGH]
        low_pool = [x for x in pool if x["hits"] < HIGH_BAND]
        # evenly spaced across the low band rather than its top, so the low
        # stratum is not quietly just-below-threshold cases
        low = []
        if low_pool:
            step = len(low_pool) / min(N_LOW, len(low_pool))
            low = [low_pool[int(i * step)] for i in range(min(N_LOW, len(low_pool)))]
        for x in high + low:
            band = "高段" if x["hits"] >= HIGH_BAND else "低段"
            picked.append((t, x["rec"], x["hits"], band))

    print(f"\n== 抽出 {len(picked)} 篇（分層） ==")
    for t in SUBTOPICS:
        rows = [p for p in picked if p[0] == t]
        print(f"  {t:6s} 高段 {sum(1 for p in rows if p[3]=='高段')} ／ "
              f"低段 {sum(1 for p in rows if p[3]=='低段')}")

    OUT_JSON.write_text(json.dumps({
        "method": "B9 重抽太空／教育／移民（關鍵詞改為專屬動作詞）＋預先登記的排序器測試",
        "hypothesis": HYPOTHESIS,
        "high_band_threshold": HIGH_BAND,
        "pool_sizes": {t: len(pools.get(t, [])) for t in SUBTOPICS},
        "rejected": dict(rejected),
        "ai_flagged": ai_flagged,
        "picked": [{"subtopic": t, "file": r["file"], "chars": len(r["draft"]),
                    "hits": h, "band": b} for t, r, h, b in picked],
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    OUT_DIR.mkdir(exist_ok=True)
    for b in range(0, len(picked), PER_BATCH):
        batch = picked[b:b + PER_BATCH]
        lines = []
        for topic, r, hits, band in batch:
            lines.append(f"\n\n{'='*70}\n=== 稿件：{r['file']}\n"
                         f"=== 子類：{topic}（命中 {hits} 次，{band}）\n{'='*70}\n")
            lines.append(r["draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(len(r['draft']) for _, r, _, _ in batch)} chars")


if __name__ == "__main__":
    main()
