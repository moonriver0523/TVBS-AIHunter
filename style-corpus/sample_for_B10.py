#!/usr/bin/env python3
"""Step B round 10 prep — open new subtopics under the locked sampling spec.

The spec (B9 §1-4, validated by a pre-registered test: high band 10/10 vs
low band 0/6)
------------------------------------------------------------------------
    pool   : hits >= 3 AND a keyword inside the opening 300 chars
    rank   : by hit count, descending
    read   : ONLY hits >= HIGH_BAND
    short  : if a subtopic cannot fill its slots, read fewer — never top up
             from below the band

That last rule is the one that is easy to break and the whole point of the
round. B9's 教育校園 had six drafts in pool and none in the high band; the
correct call was to declare the subtopic unmineable, and the two below-band
drafts read to check that call both turned out to be half-hits, exactly as
predicted.

Subtopic choice
---------------
太空科學 and 移民難民 have had their high bands nearly exhausted (移民 has 3
left, 太空 none); 教育校園 is unmineable. So B10 opens six subtopics that no
round has touched. Keyword lists are built action-word-first per B8 §1-3, and
each list was checked against the question that matters: *would this word show
up in a different subject's story that merely passes through this scene?*

Deliberately NOT included: 軍事裝備. Its natural vocabulary (部署／攔截／
射程／服役) is exactly the vocabulary of the war coverage that already
dominates rounds B1–B5, so it cannot be separated by keyword at all — it would
reproduce the 太空科學 failure. If military hardware is ever wanted it needs a
different selector than keywords.

Writes b10_coverage.json and sample_B10/batch_XX.md.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from sample_for_B7 import HEAD_CHARS, MIN_CHARS, MIN_HITS, ai_shape

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
STATUS = HERE / "reading_status.json"
OUT_JSON = HERE / "b10_coverage.json"
OUT_DIR = HERE / "sample_B10"

PER_BATCH = 8
HIGH_BAND = 10        # locked by B9
MAX_PER_TOPIC = 5     # cap so one big subtopic cannot eat the whole round

SUBTOPICS: dict[str, list[str]] = {
    # 收成／歉收／採收 are things only agriculture does. 農民 kept (it is an
    # actor, not a scene); 糧食 dropped — famine stories in war coverage use it.
    "農業糧食": ["收成", "歉收", "採收", "耕作", "農民", "種植", "灌溉", "畜牧",
                 "漁獲", "農藥", "產季", "農地", "牧場", "農作物", "休耕", "農損"],
    # 時裝周／伸展台／高訂 are unambiguous. 品牌／設計 dropped as too general.
    "時尚服飾": ["時裝周", "伸展台", "秀場", "高訂", "時尚圈", "服裝設計師",
                 "穿搭", "紅毯造型", "精品業", "訂製服", "時裝秀", "潮牌"],
    # 出土／遺址／年代測定 only happen in archaeology.
    "考古文史": ["考古", "出土", "遺址", "文物", "化石", "古墓", "年代測定",
                 "史前", "遺骸", "碑文", "壁畫", "文化遺產", "挖掘出", "古文明"],
    # 米其林／訂房／導遊 are travel-trade actions; 旅遊／景點 dropped as scenes.
    "美食旅遊": ["米其林", "訂房", "導遊", "觀光客", "住房率", "餐酒", "名廚",
                 "主廚", "旅行社", "郵輪", "背包客", "觀光局", "旅遊業", "訂位"],
    # 領養／收容所／獸醫 are actions on animals; 動物 alone dropped.
    "寵物動物": ["領養", "飼主", "獸醫", "動物園", "收容所", "繁殖", "棲地",
                 "保育類", "圈養", "野放", "認養", "寵物店", "毛小孩", "馴養"],
    # 選美／奪冠／參賽者 — pageant and contest coverage, never war vocabulary.
    "競賽選拔": ["選美", "參賽者", "評審", "冠軍賽", "決選", "奪冠", "初賽",
                 "報名參賽", "得獎者", "頒獎典禮", "入圍", "選拔賽"],
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
            rejected["已讀過（B1–B9）"] += 1
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
            rejected["不屬這六個子類"] += 1
            continue
        pools[topic].append({"rec": r, "hits": scored[topic]})

    print("== B10 候選池 ==")
    for t in SUBTOPICS:
        pool = pools.get(t, [])
        hi = sum(1 for x in pool if x["hits"] >= HIGH_BAND)
        flag = "" if hi else "   ← 高段掛零，判定為挖不動"
        print(f"  {t:6s} 入池 {len(pool):3d}　高段 {hi:2d}{flag}")
    print("\n== 排除統計 ==")
    for k, n in rejected.most_common():
        print(f"  {k:22s} {n:5d}")

    picked, skipped = [], []
    for t in SUBTOPICS:
        pool = sorted(pools.get(t, []), key=lambda x: -x["hits"])
        high = [x for x in pool if x["hits"] >= HIGH_BAND]
        if not high:
            skipped.append(t)
            continue
        for x in high[:MAX_PER_TOPIC]:
            picked.append((t, x["rec"], x["hits"]))

    print(f"\n== 只讀高段（hits >= {HIGH_BAND}），共 {len(picked)} 篇 ==")
    for t, n in Counter(t for t, _, _ in picked).most_common():
        print(f"  {t:6s} {n} 篇")
    if skipped:
        print(f"\n== 依規格放棄（高段掛零，不往下補）：{'、'.join(skipped)} ==")

    OUT_JSON.write_text(json.dumps({
        "method": "B10 開新子類，套用 B9 定案規格（入池>=3、依命中數排序、只讀 hits>=10、不足額不往下補）",
        "high_band_threshold": HIGH_BAND,
        "pool_sizes": {t: len(pools.get(t, [])) for t in SUBTOPICS},
        "high_band_sizes": {t: sum(1 for x in pools.get(t, []) if x["hits"] >= HIGH_BAND)
                            for t in SUBTOPICS},
        "skipped_subtopics": skipped,
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
                         f"=== 子類：{topic}（命中 {hits} 次）\n{'='*70}\n")
            lines.append(r["draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(len(r['draft']) for _, r, _ in batch)} chars")


if __name__ == "__main__":
    main()
