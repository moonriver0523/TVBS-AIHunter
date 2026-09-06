# -*- coding: utf-8 -*-
"""A34 CTV 候選清單機械篩 — 回歸測試（全檢 §11／12-A34-CTV候選清單.md Task 1）。

判準：`source=="NS"` ∧ `script_status=="has_script"` ∧ `len(src_text)>=500` ∧
`fields.no_bite==False` ∧ `60s<=duration<=210s` ∧ notes 無限制字
（`限用|限非|僅授權|不得|禁止|embargo`）。
排序：🔴>🟡>🔖>其餘，涉臺（tc.C 含「臺灣」）前置，🟤 沉底。

用法：python -X utf8 test_s2_ctv_candidates.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_ctv_candidates as cc  # noqa: E402

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


LONG = "X" * 520


def make_item(id_, source="NS", script_status="has_script", src_text=LONG,
              duration="01:32", no_bite=False, bite=None, notes=None,
              T=None, C=None, mark=""):
    notes = notes if notes is not None else [f"{id_}題目", "BITE"]
    bite = bite if bite is not None else ["某人「一句話」"]
    prefix = (mark + " ") if mark else ""
    raw = (f"{prefix}{id_} ({notes[0]}) (BITE) ▎摘要內容。"
           f"▎畫面：畫面描述。▎BITE：{'▎'.join(bite)}▎{duration or ''}")
    return {
        "id": id_,
        "source": source,
        "script_status": script_status,
        "raw_entry": raw,
        "src_text": src_text,
        "fields": {
            "notes": notes,
            "summary": "摘要內容。",
            "footage": "畫面描述。",
            "bite": bite,
            "no_bite": no_bite,
            "duration": duration,
        },
        "tc": {"T": T or [], "C": C or []},
    }


# ① 合格：🟡、2 BITE、01:32
it1 = make_item("SE-101SU", bite=["A「第一句」", "B「第二句」"], mark="🟡")
# ② AP 來源 → 排除（非 NS，不進 NS 分母）
it2 = make_item("AP-202SU", source="AP")
# ③ NS 無 BITE → 排除
it3 = make_item("WE-303SU", no_bite=True, bite=[])
# ④ NS 04:10 → 排除（時長超出 01:00–03:30）
it4 = make_item("PO-404SU", duration="04:10")
# ⑤ NS notes「限用社群」→ 排除
it5 = make_item("MW-505SU", notes=["某題目 限用社群畫面", "BITE"])
# ⑥ NS 合格＋🔴＋C 臺灣 → 應排第一
it6 = make_item("IN-606SU", mark="🔴", C=["臺灣"])

ITEMS = [it1, it2, it3, it4, it5, it6]

# ── is_candidate ─────────────────────────────────────────────────────
report("①合格", cc.is_candidate(it1) == (True, None))
report("②非NS排除", cc.is_candidate(it2) == (False, "非NS"))
report("③無BITE排除", cc.is_candidate(it3) == (False, "無BITE"))
report("④時長排除", cc.is_candidate(it4) == (False, "時長"))
report("⑤限制排除", cc.is_candidate(it5) == (False, "限制"))
report("⑥合格", cc.is_candidate(it6) == (True, None))

# 邊界：稿未全（script_status 非 has_script／src_text 太短／fields 缺）
report("script_status=pending → 稿未全",
       cc.is_candidate(make_item("X1", script_status="pending")) == (False, "稿未全"))
report("src_text 太短 → 稿未全",
       cc.is_candidate(make_item("X2", src_text="短")) == (False, "稿未全"))
it_nofields = make_item("X3")
del it_nofields["fields"]
report("fields 缺 → 稿未全", cc.is_candidate(it_nofields) == (False, "稿未全"))
report("時長剛好邊界 01:00 合格", cc.is_candidate(make_item("X4", duration="01:00"))[0] is True)
report("時長剛好邊界 03:30 合格", cc.is_candidate(make_item("X5", duration="03:30"))[0] is True)
report("時長 00:59 排除", cc.is_candidate(make_item("X6", duration="00:59")) == (False, "時長"))
report("時長 03:31 排除", cc.is_candidate(make_item("X7", duration="03:31")) == (False, "時長"))
report("時長解析失敗（非 MM:SS）→ 時長排除",
       cc.is_candidate(make_item("X8", duration="亂碼")) == (False, "時長"))

# ── rank_key：⑥（🔴＋臺灣）排在 ①（🟡）之前 ──────────────────────────
ordered = sorted([it1, it6], key=cc.rank_key)
report("排序 ⑥ 在 ① 之前", [it["id"] for it in ordered] == ["IN-606SU", "SE-101SU"])

# ── main() 端到端：只用 ITEMS 六則組一份假狀態檔 ──────────────────────
with tempfile.TemporaryDirectory() as td:
    state_path = os.path.join(td, "0910-s2-state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"checkpoint": "0910-2200", "items": ITEMS}, f, ensure_ascii=False)
    out_dir = os.path.join(td, "_out")
    result = cc.run(state_path, out_dir)

    report("候選數為 2", result["candidate_count"] == 2, result["candidate_count"])
    report("排除計數：無BITE 1", result["excluded"]["無BITE"] == 1, result["excluded"])
    report("排除計數：時長 1", result["excluded"]["時長"] == 1, result["excluded"])
    report("排除計數：限制 1", result["excluded"]["限制"] == 1, result["excluded"])
    report("NS 分母不含 AP", result["ns_total"] == 5, result["ns_total"])

    txt_path = os.path.join(out_dir, "0910-CTV候選.txt")
    json_path = os.path.join(out_dir, "0910-CTV候選.json")
    report("txt 檔已寫出", os.path.exists(txt_path))
    report("json 檔已寫出", os.path.exists(json_path))

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    report("json 兩則", len(data) == 2, len(data))
    report("json 順序 ⑥①", [x["id"] for x in data] == ["IN-606SU", "SE-101SU"], data)

    with open(txt_path, encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]
    report("txt 兩行", len(lines) == 2, lines)
    for i, line in enumerate(lines, start=1):
        cols = line.split("｜")
        report(f"txt 第{i}行 8 欄", len(cols) == 8, line)
        report(f"txt 第{i}行序號正確", cols[0] == str(i), line)
    report("txt 第一行 id＝IN-606SU", lines[0].split("｜")[1] == "IN-606SU", lines[0])
    report("txt 第一行標記含🔴", "🔴" in lines[0].split("｜")[2], lines[0])
    report("txt 第二行標記含🟡", "🟡" in lines[1].split("｜")[2], lines[1])

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
