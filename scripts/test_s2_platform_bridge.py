#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s2_platform_bridge.py 測試——只用自造假資料，不讀 production 檔。

覆蓋：
  1. ENEX from-raw：骨架、src_text＝desc、agent 欄位留空
  2. ABC from-raw：detail 合併 script_html／detailId；缺對應仍照出、標 detail_missing
  3. build：entry→raw_entry；skip 帶到輸出；ABC 照抄 src_text／detailId；ENEX 不含這兩鍵
  4. 端到端：from-raw → 模擬 agent 填 entry/category → build → extract_enex／extract_abc
"""
from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import s2_platform_bridge as bridge  # noqa: E402
from scripts.s2_platform_extract import extract_abc, extract_enex  # noqa: E402


def _write(path: Path, obj) -> Path:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _from_raw(**kw):
    defaults = dict(detail=None, state=None, out=None, page=None)
    defaults.update(kw)
    bridge.cmd_from_raw(Namespace(**defaults))


def _build(**kw):
    defaults = dict(out=None)
    defaults.update(kw)
    bridge.cmd_build(Namespace(**defaults))


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# ── 假資料（3～5 筆，不依賴真實掃帶檔）────────────────────────────────

ENEX_ITEMS = [
    {
        "id": "ENEX100001",
        "title": "Paris fire",
        "desc": "STORYLINE: A fire broke out in Paris downtown. SHOTLIST: flames",
        "partner": "FR BFM",
        "url": "https://cdn.example/100001.mp4",
        "estat": "PUBLISHED",
        "nlid": 11,
    },
    {
        "id": "100002",  # 已是裸 id，bare_enex_id 應原樣收下
        "title": "Berlin vote",
        "desc": "STORYLINE: Berlin votes today. SHOTLIST: ballot boxes",
        "partner": "DE ARD",
        "url": "https://cdn.example/100002.mp4",
        "estat": "PUBLISHED",
        "nlid": 12,
    },
    {
        "id": "ENEX100003",
        "title": "TVBS clip",
        "desc": "TVBS own footage, should be skippable by agent",
        "partner": "TVBS",
        "url": None,
        "estat": "PUBLISHED",
        "nlid": 13,
    },
]

ABC_RAW = [
    {"News Story": "091601001", "Slug": "StormHits", "Length": "02:15"},
    {"News Story": "091601002", "Slug": "CourtCase", "Length": "01:00"},
    {"News Story": "091601003", "Slug": "NoDetailYet", "Length": ":45"},
    {"News Story": "091601004", "Slug": "SkipMe", "Length": "00:30"},
]

ABC_DETAIL = [
    {
        "story": "091601001",
        "detailId": "9000001",
        "script_html": "STORY: Storm hits the coast. SOUNDBITE: mayor says evacuate.",
    },
    {
        "story": "091601002",
        "detailId": "9000002",
        "script_html": "<p>STORY: Court case continues in federal court.</p>",
    },
    # 091601003／091601004 故意不放，測 detail_missing
]


# ── 1. ENEX from-raw ─────────────────────────────────────────────────

def test_enex_from_raw_skeleton(tmp_path, capsys):
    raw = _write(tmp_path / "enex_raw.json", {"items": ENEX_ITEMS})  # dict 殼，證明走 _load_raw_any
    out = tmp_path / "enex_skeleton.json"
    _from_raw(site="enex", raw=str(raw), checkpoint="0916-0430", out=str(out))
    captured = capsys.readouterr()
    rows = _load(out)
    by_id = {r["id"]: r for r in rows}

    assert len(rows) == 3, rows
    assert set(by_id) == {"100001", "100002", "100003"}
    assert by_id["100001"]["src_text"] == ENEX_ITEMS[0]["desc"]
    assert by_id["100002"]["src_text"] == ENEX_ITEMS[1]["desc"]
    for rid, row in by_id.items():
        assert row["entry"] == ""
        assert row["category"] == ""
        assert row["tc"] == ""
        assert row["skip"] == ""
        assert row["source"] == "ENEX"
        assert row["checkpoint"] == "0916-0430"
        assert "head" in row["hint"] and "first150" in row["hint"]
        assert "sb_count" in row["hint"]
        assert row["sb_count"] == 0
    assert "Paris fire" in captured.out
    assert "骨架已寫" in captured.err


# ── 2. ABC from-raw ──────────────────────────────────────────────────

def test_abc_from_raw_merges_detail_and_keeps_missing(tmp_path, capsys):
    raw = _write(tmp_path / "abc_raw.json", ABC_RAW)
    detail = _write(tmp_path / "abc_detail.json", ABC_DETAIL)
    out = tmp_path / "abc_skeleton.json"
    _from_raw(
        site="abc", raw=str(raw), detail=str(detail),
        checkpoint="0916-0430", out=str(out),
    )
    captured = capsys.readouterr()
    rows = _load(out)
    by_id = {r["id"]: r for r in rows}

    assert len(rows) == 4, rows
    hit = by_id["ABC091601001"]
    assert hit["detailId"] == "9000001"
    assert "Storm hits the coast" in hit["src_text"]
    assert hit.get("detail_missing") is not True
    assert hit["entry"] == "" and hit["skip"] == ""

    html_hit = by_id["ABC091601002"]
    assert html_hit["detailId"] == "9000002"
    assert "Court case continues" in html_hit["src_text"]
    assert "<p>" not in html_hit["src_text"]

    missing = by_id["ABC091601003"]
    assert missing.get("detail_missing") is True
    assert missing["src_text"] == ""
    assert missing["detailId"] == ""
    assert "detail_missing" not in by_id["ABC091601001"]
    assert "ABC091601003" in captured.err
    assert "known_gaps" in captured.err


# ── 3. build ─────────────────────────────────────────────────────────

def test_build_enex_renames_omits_src_and_carries_skip(tmp_path, capsys):
    skel = [
        {
            "id": "100001", "source": "ENEX", "checkpoint": "0916-0430",
            "src_text": "STORYLINE: A fire", "sb_count": 0,
            "entry": "ENEX100001 (BFM) ▎巴黎大火▎畫面：火場",
            "category": "歐洲/測試/火災", "tc": "T1/C1", "skip": "",
            "hint": {"head": "Paris fire", "first150": "STORYLINE", "dur": "", "sb_count": 0},
        },
        {
            "id": "100003", "source": "ENEX", "checkpoint": "0916-0430",
            "src_text": "TVBS own footage", "sb_count": 0,
            "entry": "", "category": "", "tc": "", "skip": "own",
            "hint": {"head": "TVBS clip", "first150": "TVBS", "dur": "", "sb_count": 0},
        },
        {
            "id": "100002", "source": "ENEX", "checkpoint": "0916-0430",
            "src_text": "STORYLINE: Berlin", "sb_count": 0,
            "entry": "", "category": "", "tc": "", "skip": "",
            "hint": {"head": "Berlin vote", "first150": "STORYLINE", "dur": "", "sb_count": 0},
        },
    ]
    skel_path = _write(tmp_path / "enex_skel.json", skel)
    out = tmp_path / "enex_entries.json"
    _build(skeleton=str(skel_path), out=str(out))
    captured = capsys.readouterr()
    entries = _load(out)

    assert entries["100001"]["raw_entry"].startswith("ENEX100001")
    assert "entry" not in entries["100001"]
    assert "src_text" not in entries["100001"]
    assert "detailId" not in entries["100001"]
    assert entries["100001"]["category"] == "歐洲/測試/火災"
    assert entries["100001"]["sb_count"] == 0

    assert entries["100003"]["skip"] == "own"
    assert "skip" not in entries["100001"]
    assert "skip" not in entries["100002"]

    assert "100002" in entries  # 空 entry 仍輸出
    assert "100002" in captured.err  # missing 警告
    assert "100003" not in captured.err  # skip 有填，不列進 missing


def test_build_abc_copies_src_text_and_detail_id(tmp_path):
    skel = [
        {
            "id": "ABC091601001", "source": "ABC", "checkpoint": "0916-0430",
            "src_text": "STORY: Storm hits the coast.", "detailId": "9000001",
            "sb_count": 2, "entry": "ABC091601001 (ABC) ▎颶風登陸▎畫面：海浪",
            "category": {"大分類": "美國", "中主題": "天災"}, "tc": "", "skip": "",
        },
        {
            "id": "ABC091601003", "source": "ABC", "checkpoint": "0916-0430",
            "src_text": "", "detailId": "", "detail_missing": True,
            "sb_count": 0, "entry": "ABC091601003 (ABC) ▎尚無全文▎畫面：待補",
            "category": "美國/測試", "tc": "", "skip": "",
        },
    ]
    skel_path = _write(tmp_path / "abc_skel.json", skel)
    out = tmp_path / "abc_entries.json"
    _build(skeleton=str(skel_path), out=str(out))
    entries = _load(out)

    assert entries["ABC091601001"]["src_text"] == "STORY: Storm hits the coast."
    assert entries["ABC091601001"]["detailId"] == "9000001"
    assert entries["ABC091601001"]["raw_entry"].startswith("ABC091601001")
    assert entries["ABC091601001"]["sb_count"] == 2
    assert entries["ABC091601003"]["src_text"] == ""
    assert entries["ABC091601003"]["detailId"] == ""
    assert "skip" not in entries["ABC091601001"]


# ── 4. 端到端：build 輸出真的能被 extract_enex／extract_abc 吃 ─────────

def test_e2e_enex_from_raw_build_extract(tmp_path):
    raw = _write(tmp_path / "enex_raw.json", ENEX_ITEMS)
    skel_path = tmp_path / "enex_skeleton.json"
    _from_raw(site="enex", raw=str(raw), checkpoint="0916-0430", out=str(skel_path))
    rows = _load(skel_path)
    by_id = {r["id"]: r for r in rows}
    by_id["100001"]["entry"] = "ENEX100001 (BFM) ▎巴黎大火▎畫面：火場"
    by_id["100001"]["category"] = "歐洲/測試/火災"
    by_id["100002"]["entry"] = "ENEX100002 (ARD) ▎柏林投票▎畫面：票箱"
    by_id["100002"]["category"] = "歐洲/測試/選舉"
    by_id["100003"]["skip"] = "own"
    _write(skel_path, rows)

    entries_path = tmp_path / "enex_entries.json"
    _build(skeleton=str(skel_path), out=str(entries_path))
    entries = _load(entries_path)

    items, skipped, dropped, gaps = extract_enex(
        ENEX_ITEMS, entries, duration_fn=lambda url: 69.36,
    )
    assert not dropped, dropped
    assert len(items) == 2, items
    assert {it["id"] for it in items} == {"ENEX100001", "ENEX100002"}
    assert len(skipped) == 1 and skipped[0]["id"] == "ENEX100003"
    paris = next(it for it in items if it["id"] == "ENEX100001")
    assert paris["src_text"] == ENEX_ITEMS[0]["desc"]
    assert paris["raw_entry"].startswith("ENEX100001")


def test_e2e_abc_from_raw_build_extract(tmp_path):
    raw = _write(tmp_path / "abc_raw.json", ABC_RAW)
    detail = _write(tmp_path / "abc_detail.json", ABC_DETAIL)
    skel_path = tmp_path / "abc_skeleton.json"
    _from_raw(
        site="abc", raw=str(raw), detail=str(detail),
        checkpoint="0916-0430", out=str(skel_path),
    )
    rows = _load(skel_path)
    by_id = {r["id"]: r for r in rows}
    by_id["ABC091601001"]["entry"] = "ABC091601001 (ABC) ▎颶風登陸▎畫面：海浪"
    by_id["ABC091601001"]["category"] = "美國/天災"
    by_id["ABC091601002"]["entry"] = "ABC091601002 (ABC) ▎聯邦法庭續審▎畫面：法院"
    by_id["ABC091601002"]["category"] = "美國/司法"
    by_id["ABC091601003"]["entry"] = "ABC091601003 (ABC) ▎尚無全文▎畫面：待補"
    by_id["ABC091601003"]["category"] = "美國/測試"
    by_id["ABC091601004"]["skip"] = "體育／不收"
    _write(skel_path, rows)

    entries_path = tmp_path / "abc_entries.json"
    _build(skeleton=str(skel_path), out=str(entries_path))
    entries = _load(entries_path)

    items, skipped, dropped, gaps = extract_abc(ABC_RAW, entries)
    assert not dropped, dropped
    assert len(skipped) == 1 and skipped[0]["id"] == "ABC091601004"
    assert len(items) == 3, [it["id"] for it in items]
    storm = next(it for it in items if it["id"] == "ABC091601001")
    assert "Storm hits the coast" in storm["src_text"]
    assert storm["abc"]["detailId"] == "9000001"
    missing = next(it for it in items if it["id"] == "ABC091601003")
    assert any("src_text" in g for g in gaps)
    assert missing["src_text"] == ""


def test_from_raw_d12_skips_has_script_keeps_pending(tmp_path, capsys):
    raw = _write(tmp_path / "enex_raw.json", ENEX_ITEMS)
    state = _write(tmp_path / "state.json", {
        "date": "2026-09-16",
        "items": [
            {"id": "ENEX100001", "script_status": "has_script", "entry": "既有稿"},
            {"id": "100002", "script_status": "pending", "entry": ""},
        ],
    })
    out = tmp_path / "enex_skeleton.json"
    _from_raw(
        site="enex", raw=str(raw), checkpoint="0916-0430",
        state=str(state), out=str(out),
    )
    captured = capsys.readouterr()
    rows = _load(out)
    ids = [r["id"] for r in rows]
    assert "100001" not in ids
    assert "100002" in ids
    assert "100003" in ids
    pending = next(r for r in rows if r["id"] == "100002")
    assert pending["prev_status"] == "pending"
    assert "已在庫略過" in captured.err
    assert "pending 保留" in captured.err


# ── 5. Codex 驗收：全文不截斷／空 script_html／重複警告／--page ──

def test_abc_from_raw_keeps_full_script_html_untruncated(tmp_path):
    """骨架 src_text 必須是全文，不能套 truncate() 的 8,000 字上限。"""
    long_body = "STORY: " + ("x" * 9000)
    raw = _write(tmp_path / "abc_raw.json", [
        {"News Story": "091601099", "Slug": "LongOne", "Length": "02:00"},
    ])
    detail = _write(tmp_path / "abc_detail.json", [
        {"story": "091601099", "detailId": "9000099", "script_html": long_body},
    ])
    out = tmp_path / "abc_skeleton.json"
    _from_raw(
        site="abc", raw=str(raw), detail=str(detail),
        checkpoint="0916-0430", out=str(out),
    )
    hit = _load(out)[0]
    assert hit["src_text"] == long_body
    assert len(hit["src_text"]) == len(long_body)
    assert "截斷" not in hit["src_text"]
    assert hit.get("detail_missing") is not True


def test_abc_empty_script_html_marks_detail_missing(tmp_path, capsys):
    """detail 對到但 script_html 空字串／null／缺欄，一樣標 detail_missing。"""
    raw = _write(tmp_path / "abc_raw.json", [
        {"News Story": "091601010", "Slug": "EmptyHtml", "Length": "01:00"},
        {"News Story": "091601011", "Slug": "NullHtml", "Length": "01:00"},
        {"News Story": "091601012", "Slug": "NoField", "Length": "01:00"},
        {"News Story": "091601013", "Slug": "NoDetail", "Length": "01:00"},
    ])
    detail = _write(tmp_path / "abc_detail.json", [
        {"story": "091601010", "detailId": "10", "script_html": ""},
        {"story": "091601011", "detailId": "11", "script_html": None},
        {"story": "091601012", "detailId": "12"},
    ])
    out = tmp_path / "abc_skeleton.json"
    _from_raw(
        site="abc", raw=str(raw), detail=str(detail),
        checkpoint="0916-0430", out=str(out),
    )
    captured = capsys.readouterr()
    by_id = {r["id"]: r for r in _load(out)}

    for rid, did in (
        ("ABC091601010", "10"),
        ("ABC091601011", "11"),
        ("ABC091601012", "12"),
    ):
        assert by_id[rid].get("detail_missing") is True, rid
        assert by_id[rid]["src_text"] == ""
        assert by_id[rid]["detailId"] == did
        assert "全文欄位是空" in captured.err
        assert rid in captured.err

    missing = by_id["ABC091601013"]
    assert missing.get("detail_missing") is True
    assert missing["src_text"] == ""
    assert missing["detailId"] == ""
    assert "找不到對應" in captured.err
    assert "ABC091601013" in captured.err


def test_duplicate_ids_warn_on_stderr(tmp_path, capsys):
    """detail／raw 重複保留第一筆並警告；build 重複則後筆覆蓋前筆並警告。"""
    raw = _write(tmp_path / "abc_raw.json", [
        {"News Story": "091601001", "Slug": "First", "Length": "01:00"},
        {"News Story": "091601001", "Slug": "Second", "Length": "02:00"},
    ])
    detail = _write(tmp_path / "abc_detail.json", [
        {"story": "091601001", "detailId": "111", "script_html": "FIRST BODY"},
        {"story": "091601001", "detailId": "222", "script_html": "SECOND BODY"},
    ])
    skel_path = tmp_path / "abc_skeleton.json"
    _from_raw(
        site="abc", raw=str(raw), detail=str(detail),
        checkpoint="0916-0430", out=str(skel_path),
    )
    captured = capsys.readouterr()
    rows = _load(skel_path)
    assert len(rows) == 1
    assert rows[0]["hint"]["head"] == "First"
    assert rows[0]["src_text"] == "FIRST BODY"
    assert rows[0]["detailId"] == "111"
    assert "detail 裡有重複" in captured.err
    assert "raw 裡有重複 id" in captured.err
    assert "只保留第一次出現的那筆" in captured.err

    skel = [
        {
            "id": "ABC091601001", "source": "ABC",
            "src_text": "A", "detailId": "1", "sb_count": 0,
            "entry": "first entry", "category": "x", "skip": "",
        },
        {
            "id": "ABC091601001", "source": "ABC",
            "src_text": "B", "detailId": "2", "sb_count": 0,
            "entry": "second entry", "category": "y", "skip": "",
        },
    ]
    build_in = _write(tmp_path / "dup_skel.json", skel)
    build_out = tmp_path / "dup_entries.json"
    _build(skeleton=str(build_in), out=str(build_out))
    build_cap = capsys.readouterr()
    entries = _load(build_out)
    assert list(entries) == ["ABC091601001"]
    assert entries["ABC091601001"]["raw_entry"] == "second entry"
    assert entries["ABC091601001"]["src_text"] == "B"
    assert "後筆覆蓋前筆" in build_cap.err


def test_from_raw_page_splits_hint_table(tmp_path, capsys, monkeypatch):
    """--page 比照 s2_batch_prep：提示表超長就分頁，N 選第幾頁。"""
    monkeypatch.setattr(bridge, "INSPECT_TEXT_BUDGET", 1)
    items = [
        {
            "id": "ENEX100001", "title": "PAGEONE_HEAD", "desc": "d1",
            "partner": "FR BFM", "url": "https://cdn.example/1.mp4",
            "estat": "PUBLISHED", "nlid": 1,
        },
        {
            "id": "ENEX100002", "title": "PAGETWO_HEAD", "desc": "d2",
            "partner": "DE ARD", "url": "https://cdn.example/2.mp4",
            "estat": "PUBLISHED", "nlid": 2,
        },
    ]
    raw = _write(tmp_path / "enex_raw.json", items)
    out = tmp_path / "enex_skeleton.json"

    _from_raw(site="enex", raw=str(raw), checkpoint="0916-0430",
              out=str(out), page=1)
    cap1 = capsys.readouterr()
    assert "PAGEONE_HEAD" in cap1.out
    assert "PAGETWO_HEAD" not in cap1.out
    assert "第 1/2 頁" in cap1.out
    assert "骨架已寫" in cap1.err
    assert len(_load(out)) == 2  # 分頁只切提示表，骨架仍是全份

    _from_raw(site="enex", raw=str(raw), checkpoint="0916-0430",
              out=str(out), page=2)
    cap2 = capsys.readouterr()
    assert "PAGETWO_HEAD" in cap2.out
    assert "PAGEONE_HEAD" not in cap2.out
    assert "最後一頁" in cap2.out

    try:
        _from_raw(site="enex", raw=str(raw), checkpoint="0916-0430",
                  out=str(out), page=9)
        raise AssertionError("expected SystemExit for out-of-range --page")
    except SystemExit as e:
        assert e.code == 1
    cap3 = capsys.readouterr()
    assert "超出範圍" in cap3.err
