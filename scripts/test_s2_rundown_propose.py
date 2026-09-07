# -*- coding: utf-8 -*-
"""S4 稿單提案生成器：評分器回歸測試（全檢 §10／14-A33-稿單提案生成器.md Task 1）。

判準（全部用狀態檔既有欄位，機械算，不判讀內容）：
  score：🔴+5／🟡+3（同題取最高）；distinct sources +1 each（上限+3）；
         有 BITE +1；🔖+1；tc.C 含「臺灣」+3；🟤-2；則數≥8 +1。
  入榜門檻：題目底下至少一則帶 🔴／🟡／🔖／🟤 其中之一，否則不入榜
           （純機械訊號掃視，不判讀內容重要性）。
  聚合：登記簿 canonical（沒有就用中主題名本身）為 key，跨大分類合併。
  missing：無 BITE→「缺SOT」；畫面欄全是受訪／連線類詞（或全空）→「缺現場畫面」；
           僅一個來源→「單一來源」。

全程唯讀：本檔只用 tempfile 合成狀態檔／登記簿，不碰任何正式檔案。

用法：python -X utf8 test_s2_rundown_propose.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_rundown_propose as rp  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


LONG = "X" * 520  # 給 CTV 候選判準用的完整官方稿長度


def make_item(id_, big, mid, sub="", source="NS", mark="", hilite=False, aired=False,
              bite=None, duration="01:30", footage="現場畫面、群眾集會", C=None,
              src_text="", script_status="has_script", notes=None):
    """合成一則素材：raw_entry 標記順序照 s2_validate 規定
    `{時段} {🔴|🟡} {🟤} {🔖} {代碼}…`（時段這裡略過不標）。
    """
    bite = bite if bite is not None else []
    notes = notes if notes is not None else [f"{id_}題目"]
    prefix = ""
    if mark == "red":
        prefix += "🔴 "
    elif mark == "orange":
        prefix += "🟡 "
    if aired:
        prefix += "🟤 "
    if hilite:
        prefix += "🔖 "
    bite_seg = ("▎BITE：" + "、".join(bite)) if bite else "▎無BITE。"
    raw = f"{prefix}{id_} ({notes[0]}) ▎摘要內容。▎畫面：{footage}{bite_seg}▎{duration}"
    return {
        "id": id_,
        "source": source,
        "script_status": script_status,
        "raw_entry": raw,
        "src_text": src_text,
        "category": {"大分類": big, "中主題": mid, "小分題": sub},
        "fields": {
            "notes": notes,
            "summary": "摘要內容。",
            "footage": footage,
            "bite": bite,
            "no_bite": not bool(bite),
            "duration": duration,
        },
        "tc": {"T": [], "C": C or []},
    }


# ── 五個中主題（見檔頭判準）────────────────────────────────────────────
# A：🔴、3 來源、有 BITE → 第一
a1 = make_item("A1", "話題", "A", source="NS", mark="red",
                bite=["某人「第一句」"], duration="01:30", src_text=LONG)
a2 = make_item("A2", "話題", "A", source="AP")
a3 = make_item("A3", "話題", "A", source="RT")

# E：與 A 同 canonical（跨大分類：E 掛在「社會」，A 掛在「話題」）→ 併成一題
e1 = make_item("E1", "社會", "E", source="CNA")

# B：🟡、涉臺 → 進前三，但分數低於 A
b1 = make_item("B1", "政治", "B", source="YNA", mark="orange", C=["臺灣"])

# C：🟤 已播、5 則、單一來源、無 BITE、畫面欄只有受訪/連線類詞 → 沉底（仍入榜）
c_items = [
    make_item(f"C{i}", "體育", "C", source="NS", aired=True,
              footage="受訪畫面" if i % 2 == 0 else "記者連線")
    for i in range(1, 6)
]

# D：1 則、無任何標記 → 不入榜
d1 = make_item("D1", "話題", "D", source="NS")

ITEMS = [a1, a2, a3, e1, b1] + c_items + [d1]

REGISTRY = {"topics": [
    {"name": "A", "charter": "", "aliases": ["E"], "big": "話題",
     "tc": {"T": [], "C": []}, "first_seen": "2026-09-01", "last_seen": "2026-09-07",
     "resident": False},
]}

# ── score()／missing_of() 單元測試 ──────────────────────────────────────
s_a, reasons_a = rp.score([a1, a2, a3])
report("A 分數＝5(紅)+3(3來源)+1(BITE)=9", s_a == 9, s_a)
report("A reasons 含🔴", any("🔴" in r for r in reasons_a), reasons_a)
report("A reasons 含來源", any("來源" in r for r in reasons_a), reasons_a)
report("A reasons 含BITE", any("BITE" in r for r in reasons_a), reasons_a)

s_b, reasons_b = rp.score([b1])
report("B 分數＝3(橘)+3(涉臺)+1(1來源)=7", s_b == 7, s_b)
report("B reasons 含涉臺", any("臺" in r for r in reasons_b), reasons_b)

s_c, reasons_c = rp.score(c_items)
report("C 分數為負（1來源+1、🟤-2、5則未達8則加分）＝-1", s_c == -1, s_c)
report("C reasons 含🟤", any("🟤" in r for r in reasons_c), reasons_c)

s_d, _ = rp.score([d1])
report("D 分數僅來源+1", s_d == 1, s_d)

report("A 入榜", rp.qualifies([a1, a2, a3]) is True)
report("B 入榜", rp.qualifies([b1]) is True)
report("C 入榜（🟤 也算訊號）", rp.qualifies(c_items) is True)
report("D 不入榜（無任何🔴🟡🔖🟤）", rp.qualifies([d1]) is False)

missing_a = rp.missing_of([a1, a2, a3])
report("A 3 來源不算單一來源", "單一來源" not in missing_a, missing_a)
report("A 有 BITE 不缺SOT", "缺SOT" not in missing_a, missing_a)

missing_c = rp.missing_of(c_items)
report("C 單一來源", "單一來源" in missing_c, missing_c)
report("C 缺SOT（無BITE）", "缺SOT" in missing_c, missing_c)
report("C 畫面欄全受訪/連線 → 缺現場畫面", "缺現場畫面" in missing_c, missing_c)

missing_b = rp.missing_of([b1])
report("B 單一來源", "單一來源" in missing_b, missing_b)
report("B 無BITE → 缺SOT", "缺SOT" in missing_b, missing_b)

# ── run() 端到端：合成一份狀態檔＋一份 tempfile 登記簿 ─────────────────
with tempfile.TemporaryDirectory() as td:
    state_path = os.path.join(td, "0910-s2-state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"checkpoint": "0910-2200", "items": ITEMS}, f, ensure_ascii=False)
    registry_path = os.path.join(td, "registry.json")
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(REGISTRY, f, ensure_ascii=False)
    out_dir = os.path.join(td, "_稿單提案")

    result = rp.run(state_path, out_dir=out_dir, top=12, registry_path=registry_path)
    cands = result["candidates"]
    topics = [c["topic"] for c in cands]

    report("候選數＝3（D 不入榜）", len(cands) == 3, topics)
    report("candidates[0].topic == A", cands[0]["topic"] == "A", topics)
    report("A 分數最高", cands[0]["score"] == max(c["score"] for c in cands), cands)
    report("D 不存在", "D" not in topics, topics)
    report("C 排最後", cands[-1]["topic"] == "C", topics)

    a_cand = next(c for c in cands if c["topic"] == "A")
    a_ids = {it["id"] for it in a_cand["items"]}
    report("E 的素材(E1)併入 A 底下", "E1" in a_ids, a_ids)
    report("A canonical == A", a_cand["canonical"] == "A", a_cand["canonical"])
    report("A 素材含 4 則（3+E1）", len(a_cand["items"]) == 4, a_ids)

    for c in cands:
        for key in ("topic", "canonical", "score", "reasons", "items", "ctv_ids", "missing",
                     "items_omitted"):
            report(f"{c['topic']} 含欄位 {key}", key in c, c.keys())
        for it in c["items"]:
            for key in ("id", "alert", "hilite", "bite", "dur", "src", "summary", "notes"):
                report(f"{c['topic']}/{it.get('id')} item 含欄位 {key}", key in it, it.keys())

    # A33 v2：items[] 加 summary／notes／bite文字／items_omitted——agent 不需 get --id
    a1_row = next(it for it in a_cand["items"] if it["id"] == "A1")
    report("A1 summary 沿用 fields.summary 全文", a1_row["summary"] == "摘要內容。", a1_row)
    report("A1 notes 沿用 fields.notes（括號內備註）", a1_row["notes"] == "A1題目", a1_row)
    report("A1 bite 給文字（非純 bool）", a1_row["bite"] == "某人「第一句」", a1_row)
    a2_row = next(it for it in a_cand["items"] if it["id"] == "A2")
    report("A2 無 BITE → bite 給 False", a2_row["bite"] is False, a2_row)
    report("A 未超過 ITEM_CAP → items_omitted == 0", a_cand["items_omitted"] == 0,
           a_cand["items_omitted"])

    # ctv_ids：沒有既存 CTV候選.json → 退回跑 A34 的函式（記憶體內，不寫檔）
    # a1 本身符合 A34 判準（NS／has_script／src_text≥500／有BITE／01:30／無限制字）
    report("A 的 ctv_ids 含 A1（回退跑 A34 函式）", "A1" in a_cand["ctv_ids"], a_cand["ctv_ids"])
    report("回退計算不落地任何 CTV候選 檔案",
           not os.path.exists(os.path.join(out_dir, "0910-CTV候選.json")))

    report("json 已寫出", os.path.exists(os.path.join(out_dir, "0910-稿單候選.json")))
    report("txt 已寫出", os.path.exists(os.path.join(out_dir, "0910-稿單候選.txt")))

    with open(os.path.join(out_dir, "0910-稿單候選.txt"), encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]
    report("txt 3 行", len(lines) == 3, lines)
    for line in lines:
        cols = line.split("｜")
        report(f"txt 行 5 欄：{line}", len(cols) == 5, line)
    report("txt 第一行是 A", lines[0].split("｜")[1] == "A", lines[0])

# ── 既有 CTV候選.json 時優先讀檔，不重算 ──────────────────────────────
with tempfile.TemporaryDirectory() as td:
    state_path = os.path.join(td, "0911-s2-state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"checkpoint": "0911-2200", "items": [a1, a2, a3]}, f, ensure_ascii=False)
    out_dir = os.path.join(td, "_稿單提案")
    os.makedirs(out_dir, exist_ok=True)
    # 手植一份跟機械判準對不上的 CTV候選.json（只收 A2），驗證優先讀檔而非重算
    with open(os.path.join(out_dir, "0911-CTV候選.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": "A2"}], f, ensure_ascii=False)

    result2 = rp.run(state_path, out_dir=out_dir, top=12,
                      registry_path=os.path.join(td, "no_such_registry.json"))
    a_cand2 = result2["candidates"][0]
    report("優先讀既有 CTV候選.json（只收 A2，不是重算出的 A1）",
           a_cand2["ctv_ids"] == ["A2"], a_cand2["ctv_ids"])

# ── --top 截斷 ───────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as td:
    many_topics = []
    for i in range(15):
        many_topics.append(make_item(f"T{i}-1", "話題", f"題{i}", source="NS", mark="red"))
    state_path = os.path.join(td, "0912-s2-state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"checkpoint": "0912-2200", "items": many_topics}, f, ensure_ascii=False)
    result3 = rp.run(state_path, out_dir=None, top=12,
                      registry_path=os.path.join(td, "no_such_registry.json"))
    report("--top 12 截斷（15 題只留 12）", len(result3["candidates"]) == 12,
           len(result3["candidates"]))

# ── ITEM_CAP：🔴🟡🔖 全列，其餘依原序取前 12，多的計入 items_omitted ─────
report("ITEM_CAP 常數為 12", rp.ITEM_CAP == 12, rp.ITEM_CAP)

cap_marked = [make_item(f"CAPR{i}", "話題", "CAP", source="NS", mark="red")
              for i in range(3)]
cap_unmarked = [make_item(f"CAPU{i}", "話題", "CAP", source="AP")
                for i in range(20)]
CAP_ITEMS = cap_marked + cap_unmarked

with tempfile.TemporaryDirectory() as td:
    state_path = os.path.join(td, "0913-s2-state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"checkpoint": "0913-2200", "items": CAP_ITEMS}, f, ensure_ascii=False)
    out_dir = os.path.join(td, "_稿單提案")

    result4 = rp.run(state_path, out_dir=out_dir, top=12,
                      registry_path=os.path.join(td, "no_such_registry.json"))
    cap_cand = result4["candidates"][0]
    kept_ids = [it["id"] for it in cap_cand["items"]]

    report("🔴 標記則全列（3 則）",
           all(f"CAPR{i}" in kept_ids for i in range(3)), kept_ids)
    report("未標記則依原序取前 12（CAPU0..CAPU11）",
           all(f"CAPU{i}" in kept_ids for i in range(12)), kept_ids)
    report("未標記超過 12 的部分不列（CAPU12 不在內）",
           "CAPU12" not in kept_ids, kept_ids)
    report("items 總數＝15（3 標記＋12 未標記）", len(kept_ids) == 15, kept_ids)
    report("items_omitted＝8（20 則未標記 - 12）", cap_cand["items_omitted"] == 8,
           cap_cand["items_omitted"])
    # score()／missing_of() 用完整 its（未截斷）算，不受 ITEM_CAP 影響
    report("分數仍以完整 23 則計算（不受截斷影響）",
           cap_cand["score"] == rp.score(CAP_ITEMS)[0], cap_cand["score"])

    with open(os.path.join(out_dir, "0913-稿單候選.txt"), encoding="utf-8") as f:
        cap_lines = [l.rstrip("\n") for l in f if l.strip()]
    report("txt 該題尾加「另 8 則未列」",
           any("另 8 則未列" in l for l in cap_lines), cap_lines)

# 未截斷的題目：txt 不應出現「另 N 則未列」字樣（沿用最上面 0910 那組，皆 <12 則）
with tempfile.TemporaryDirectory() as td:
    state_path = os.path.join(td, "0914-s2-state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"checkpoint": "0914-2200", "items": ITEMS}, f, ensure_ascii=False)
    registry_path = os.path.join(td, "registry.json")
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(REGISTRY, f, ensure_ascii=False)
    out_dir = os.path.join(td, "_稿單提案")
    rp.run(state_path, out_dir=out_dir, top=12, registry_path=registry_path)
    with open(os.path.join(out_dir, "0914-稿單候選.txt"), encoding="utf-8") as f:
        no_cap_lines = [l.rstrip("\n") for l in f if l.strip()]
    report("未截斷題目 txt 不出現「另…則未列」",
           not any("另" in l and "則未列" in l for l in no_cap_lines), no_cap_lines)

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
