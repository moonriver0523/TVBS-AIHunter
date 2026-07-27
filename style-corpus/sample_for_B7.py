#!/usr/bin/env python3
"""Step B round 7 prep — unexplored *subtopic* sampling with pre-filters.

Why this method
---------------
B6 proved topic-coverage sampling is what surfaces **rule boundary conditions**
(it produced 10 C-level rule corrections from 32 usable drafts), while signal
screening (B4/B5) surfaces one-off tricks at ~9% real precision. B6 §8 therefore
prescribed three concrete changes for B7, all implemented here:

1. Sample the *subclasses never read yet*, not the 12 broad topics. B6 named
   eight: obituary, courtroom, election night, space/science, religious rites,
   education, immigration, labour disputes. Obituary and courtroom are the most
   likely to carry their own red lines (the way medical drafts carry anonymity).

2. Validate the topic label **before** spending a read slot. B6 wasted 43.8% of
   its low-coverage quota on mislabelled drafts. Here a draft only qualifies if
   the subtopic's keywords appear in the opening HEAD_CHARS *and* the draft hits
   the keyword set at least MIN_HITS times overall.

3. Detect the three known "process / AI output" shapes up front instead of
   discovering them mid-read. Signatures come straight from B6 §8-3.

Writes b7_coverage.json and sample_B7/batch_XX.md.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
STATUS = HERE / "reading_status.json"
OUT_JSON = HERE / "b7_coverage.json"
OUT_DIR = HERE / "sample_B7"

PER_TOPIC = 5
PER_BATCH = 10
MIN_CHARS = 1200
HEAD_CHARS = 300   # B6 said 200; widened because drafts open with `>` quote noise
MIN_HITS = 3       # total keyword hits required across the whole draft

# The eight subclasses B6 §8-1 flagged as completely unread. Keywords are tuned
# tighter than B6's broad buckets — here they double as the label validator, so
# a loose keyword would defeat recommendation #2.
SUBTOPICS: dict[str, list[str]] = {
    "訃聞追悼": ["逝世", "過世", "病逝", "享年", "追悼", "悼念", "告別式", "喪禮", "遺孀",
                 "生前", "辭世", "哀悼", "追思", "遺體", "葬禮", "安息"],
    "法庭審判": ["法官", "開庭", "判決", "判刑", "陪審", "出庭", "檢方", "辯護", "法庭",
                 "上訴", "有罪", "無罪", "認罪", "求刑", "審判", "起訴書", "宣判"],
    "選舉開票": ["開票", "得票", "票數", "勝選", "敗選", "投票所", "計票", "當選",
                 "支持率", "大選", "選情", "選民", "民調", "選舉人票"],
    "太空科學": ["火箭", "太空", "太空人", "衛星", "發射", "探測", "NASA", "星艦",
                 "登月", "火星", "太空站", "軌道", "望遠鏡", "彗星", "太陽能"],
    "宗教儀典": ["教宗", "主教", "教堂", "清真寺", "朝聖", "禮拜", "佛教", "齋戒",
                 "梵蒂岡", "加冕", "儀典", "神父", "僧侶", "祈禱", "聖地"],
    "教育校園": ["學校", "學生", "校園", "老師", "大學", "教育", "考試", "課程",
                 "校長", "開學", "畢業", "教師", "課綱", "補習"],
    "移民難民": ["移民", "難民", "邊境", "遣返", "庇護", "偷渡", "非法入境", "簽證",
                 "收容", "ICE", "驅逐出境", "邊界", "尋求庇護"],
    "勞資爭議": ["罷工", "工會", "勞工", "加薪", "資遣", "裁員", "勞資", "工時",
                 "抗議薪資", "停工", "勞動條件", "集體談判"],
}

# --- B6 §8-3: three known process/AI output shapes -------------------------
FORM1 = re.compile(r"記者\s*OS\s*字數約|預估朗讀長度|預估朗讀|OS字數約")
FORM2_BULLET = re.compile(r"^\s*-\s+\S", re.M)
FORM3_BAR = re.compile(r"BAR\s*\d")
# Material numbering only — `#01`, `#02`. Deliberately does NOT match `#CNN`,
# which is an SB source tag; treating it as numbering is what made the first
# cut of this detector miss both known 形態三 positives (0618-2, 0626-2).
MATERIAL_NO = re.compile(r"#\s*\d{2}\b")
CJK = re.compile(r"[一-鿿]")


def ai_shape(draft: str) -> str | None:
    """Return the name of the process/AI output shape detected, else None."""
    if FORM1.search(draft):
        return "形態一：產稿模板欄位"

    # 形態二 — half-width commas inside CJK prose + bullet-style headlines.
    # Judged per line, not corpus-wide: in the known positive (0707-1) the
    # half-width prose is confined to the lead, so the whole-draft ratio dilutes
    # to 0.08 and a >30% global threshold never fires.
    hw_prose = sum(1 for l in draft.splitlines()
                   if len(CJK.findall(l)) >= 20 and l.count(",") >= 2 and l.count(",") > l.count("，"))
    if hw_prose >= 1 and len(FORM2_BULLET.findall(draft)) >= 3:
        return "形態二：半形逗號段落＋項目符號標題"

    # 形態三 — CNN auto-script BAR output: BAR markers but no material numbering
    if len(FORM3_BAR.findall(draft)) >= 3 and not MATERIAL_NO.search(draft):
        return "形態三：BAR分段成品、無素材編號"
    return None


def classify(draft: str) -> tuple[str | None, dict[str, int]]:
    """Assign a subtopic only if the label survives the head-of-draft check."""
    head = draft[:HEAD_CHARS]
    scored = {}
    for name, kws in SUBTOPICS.items():
        hits = sum(draft.count(k) for k in kws)
        in_head = any(k in head for k in kws)
        if hits >= MIN_HITS and in_head:
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
            rejected["已讀過（B1–B6）"] += 1
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
            rejected["不屬八個未讀子類（或標籤未過驗）"] += 1
            continue
        pools[topic].append({"rec": r, "hits": scored[topic]})

    print("== B7 候選池（已過三道前置過濾）==")
    for t in SUBTOPICS:
        print(f"  {t:6s} {len(pools.get(t, [])):4d} 篇")
    print("\n== 排除統計 ==")
    for k, n in rejected.most_common():
        print(f"  {k:28s} {n:5d}")
    print(f"\n== 疑似流程／AI 產出（前置攔截，B6 是讀完才發現）：{len(ai_flagged)} 篇 ==")
    for item in Counter(x["shape"] for x in ai_flagged).most_common():
        print(f"  {item[0]:28s} {item[1]:4d}")

    # Even spread per subtopic; sort each pool by keyword density (most clearly
    # on-topic first) then take an evenly spaced slice so we do not only read
    # the most keyword-saturated drafts.
    picked = []
    for t in SUBTOPICS:
        pool = sorted(pools.get(t, []), key=lambda x: -x["hits"])
        n = min(PER_TOPIC, len(pool))
        if not n:
            continue
        step = len(pool) / n
        for i in range(n):
            picked.append((t, pool[int(i * step)]["rec"], pool[int(i * step)]["hits"]))

    print(f"\n== 實際抽出 {len(picked)} 篇 ==")
    for t, n in Counter(t for t, _, _ in picked).most_common():
        print(f"  {t:6s} {n} 篇")

    OUT_JSON.write_text(json.dumps({
        "method": "B7 未讀子類抽樣（B6 §8 三項建議：子類抽樣＋標籤前驗＋AI產出前置偵測）",
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
                         f"=== 子類：{topic}（關鍵詞命中 {hits} 次，已過標籤前驗）\n{'='*70}\n")
            lines.append(r["draft"])
        out = OUT_DIR / f"batch_{b//PER_BATCH + 1:02d}.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        print(f"{out.name}: {len(batch)} drafts, {sum(len(r['draft']) for _, r, _ in batch)} chars")


if __name__ == "__main__":
    main()
