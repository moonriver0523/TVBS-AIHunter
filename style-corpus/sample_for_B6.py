#!/usr/bin/env python3
"""Step B round 6 prep — topic-coverage sampling (replaces signal screening).

Why the method changed
----------------------
B5 audited the signal screener honestly: headline precision looked like it
improved (50%→64% strict), but only 4/44 picks had the signal actually
pointing at the technique found — real signal→technique precision ≈9%, no
better than v1. So more screener tuning is not the highest-value move.

What B4-vs-B5 *did* prove is stronger: **topic mix determines which techniques
surface**. B4's sample skewed entertainment/oddity → it found 吐槽 OS and
ellipsis-based gags. B5's skewed hard news → it found 外交辭令解碼句 and
慘況相對化句. Same corpus, same method, different topics, different findings.

So B6 samples by topic coverage: classify every draft, measure what the 244
already-read drafts covered, and deliberately draw from the under-covered
topics — targeting unexplored technique space directly instead of hoping a
style signal correlates with novelty.

Also runs the precise 5th-register scan B5 prescribed: `(變色強調)` / `SUPER`
appearing in a natural-language line that has NO `[tag]` markup (which is what
separates B4-N1's register from the AICG spec sheets B5 identified).

Writes b6_coverage.json (topic stats) and sample_B6/batch_XX.md.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
STATUS = HERE / "reading_status.json"
OUT_JSON = HERE / "b6_coverage.json"
OUT_DIR = HERE / "sample_B6"

TOTAL_PICKS = 44
PER_BATCH = 10
MIN_CHARS = 1200

# Topic buckets. Keyword lists are deliberately broad — this is for coverage
# balancing, not precise classification; a draft counts toward every topic it
# matches, and the dominant one (most hits) decides its primary bucket.
TOPICS: dict[str, list[str]] = {
    "戰爭衝突": ["烏克蘭", "俄羅斯", "俄軍", "烏軍", "加薩", "以色列", "哈瑪斯", "飛彈", "無人機", "停火", "空襲"],
    "政治外交": ["川普", "總統", "選舉", "國會", "外交", "峰會", "制裁", "內閣", "首相", "白宮", "投票"],
    "天災氣候": ["地震", "颱風", "野火", "洪水", "熱浪", "暴雪", "火山", "海嘯", "氣候", "乾旱", "暴雨"],
    "意外事故": ["車禍", "空難", "墜機", "爆炸", "坍塌", "翻覆", "起火", "事故", "脫軌", "沉沒"],
    "犯罪治安": ["槍擊", "槍手", "搶案", "詐騙", "毒品", "逮捕", "嫌犯", "起訴", "綁架", "殺害", "竊盜"],
    "經濟財經": ["關稅", "股市", "通膨", "物價", "經濟", "央行", "升息", "降息", "匯率", "失業", "財報", "消費"],
    "科技產業": ["AI", "人工智慧", "晶片", "半導體", "太空", "火箭", "衛星", "馬斯克", "機器人", "電動車", "手機"],
    "體育": ["大谷", "世足", "奧運", "NBA", "棒球", "足球", "球員", "冠軍", "比賽", "教練", "賽事"],
    "娛樂名人": ["明星", "電影", "演唱會", "歌手", "影集", "演員", "頒獎", "紅毯", "藝人", "導演"],
    "生活奇聞": ["旅遊", "美食", "寵物", "動物園", "網紅", "爆紅", "婚禮", "節日", "觀光", "餐廳", "民眾拍下"],
    "醫療健康": ["疫情", "病毒", "疫苗", "醫院", "醫師", "病患", "健康", "藥物", "確診", "手術"],
    "環境生態": ["環保", "污染", "生態", "物種", "海洋", "森林", "碳排", "永續", "瀕危", "垃圾"],
}

# B5-prescribed 5th-register detector: the marker must sit in a natural-language
# line, NOT inside the `[tag] content` DSL that marks an AICG spec sheet.
REG5_MARKER = re.compile(r"變色強調|請把\s*SUPER|SUPER\s*上在|放大變色")
DSL_LINE = re.compile(r"^\s*\[[^\]]+\]")


def classify(draft: str) -> tuple[str, dict[str, int]]:
    hits = {t: sum(draft.count(k) for k in kws) for t, kws in TOPICS.items()}
    hits = {t: n for t, n in hits.items() if n}
    if not hits:
        return "其他", {}
    return max(hits, key=lambda t: hits[t]), hits


def scan_register5(draft: str) -> bool:
    for line in draft.splitlines():
        if REG5_MARKER.search(line) and not DSL_LINE.match(line):
            return True
    return False


def main() -> None:
    doc = json.loads(STATUS.read_text(encoding="utf-8"))
    status, quality = doc["status"], doc["quality"]
    records = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]

    read_topics: Counter = Counter()
    unread_by_topic: dict[str, list] = defaultdict(list)
    reg5_hits: list[str] = []

    for r in records:
        f = r["file"]
        st = status.get(f)
        topic, _ = classify(r["draft"])
        if st in ("B1", "B2", "B3", "B4"):
            read_topics[topic] += 1
        elif st == "unread" and quality.get(f) == "ok" and len(r["draft"]) >= MIN_CHARS:
            unread_by_topic[topic].append(r)
        if quality.get(f) == "ok" and scan_register5(r["draft"]):
            reg5_hits.append(f)

    total_read = sum(read_topics.values())
    print(f"已讀 {total_read} 篇的題材分布：")
    all_topics = sorted(set(read_topics) | set(unread_by_topic),
                        key=lambda t: -len(unread_by_topic.get(t, [])))
    for t in all_topics:
        rd, un = read_topics.get(t, 0), len(unread_by_topic.get(t, []))
        share = rd / total_read * 100 if total_read else 0
        print(f"  {t:6s} 已讀 {rd:3d} ({share:4.1f}%)   未讀可用 {un:4d}")

    print(f"\n[第五語體] B5 精準判準全語料命中：{len(reg5_hits)} 篇")
    for f in reg5_hits:
        print(f"   {f[:60]}")

    # Allocation: inverse to how much each topic was already read. Topics with
    # more unread material and less prior coverage get more slots.
    weights = {}
    for t in all_topics:
        un = len(unread_by_topic.get(t, []))
        if not un:
            continue
        # +1 smoothing so a never-read topic doesn't divide by zero
        weights[t] = un / (read_topics.get(t, 0) + 1)
    wsum = sum(weights.values()) or 1.0
    alloc = {t: max(1, round(TOTAL_PICKS * w / wsum)) for t, w in weights.items()}

    picked = []
    for t, n in sorted(alloc.items(), key=lambda kv: -kv[1]):
        pool = unread_by_topic[t]
        step = len(pool) / n if n else 1
        for i in range(min(n, len(pool))):
            r = pool[int(i * step)]
            picked.append((t, r))
    picked = picked[:TOTAL_PICKS]

    print(f"\n配額（依「未讀量 ÷ 已讀量」反向加權）：")
    for t, n in sorted(Counter(t for t, _ in picked).items(), key=lambda kv: -kv[1]):
        print(f"  {t:6s} {n} 篇")

    OUT_JSON.write_text(json.dumps({
        "read_topic_distribution": dict(read_topics),
        "unread_usable_by_topic": {t: len(v) for t, v in unread_by_topic.items()},
        "allocation": dict(Counter(t for t, _ in picked)),
        "register5_candidates": reg5_hits,
        "picked": [{"topic": t, "file": r["file"], "chars": len(r["draft"])} for t, r in picked],
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    OUT_DIR.mkdir(exist_ok=True)
    for b in range(0, len(picked), PER_BATCH):
        batch = picked[b:b + PER_BATCH]
        lines = []
        for topic, r in batch:
            lines.append(f"\n\n{'='*70}\n=== 稿件：{r['file']}\n=== 題材分類：{topic}\n{'='*70}\n")
            lines.append(r["draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(len(r['draft']) for _, r in batch)} chars")


if __name__ == "__main__":
    main()
