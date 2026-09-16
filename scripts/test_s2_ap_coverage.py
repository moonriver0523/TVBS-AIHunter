#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s2_ap_coverage.py 的離線合成 fixture 測試。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import s2_ap_coverage as coverage


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "s2_ap_coverage.py"


def _write_json(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _items(*ids: str) -> list[dict[str, str]]:
    return [
        {"id": item_id, "comp": "Editorial", "title": f"Synthetic {item_id}"}
        for item_id in ids
    ]


def test_anchor_set_keeps_original_index_and_skips_standard_library_video():
    items = [
        {"id": "AP-std", "comp": "StandardLibraryVideo", "title": "library"},
        {"id": "AP-1", "comp": "Editorial", "title": "one"},
        {"id": "AP-2", "comp": "Editorial", "title": "two"},
        {"id": "AP-3", "comp": "Editorial", "title": "three"},
    ]

    result = coverage.build_anchor_set(items, 3)

    assert result == {
        "anchors": [
            {"id": "AP-1", "index": 1},
            {"id": "AP-2", "index": 2},
            {"id": "AP-3", "index": 3},
        ],
        "n": 3,
        "partial": False,
    }


def test_anchor_set_marks_partial_when_fewer_usable_items_exist():
    items = [
        {"id": "AP-std", "comp": "StandardLibraryVideo", "title": "library"},
        {"id": "AP-1", "comp": "Editorial", "title": "one"},
    ]

    result = coverage.build_anchor_set(items, 3)

    assert result["partial"] is True
    assert result["anchors"] == [{"id": "AP-1", "index": 1}]


def test_anchor_set_deduplicates_ids_without_losing_original_position():
    items = _items("AP-1", "AP-1", "AP-2", "AP-3")

    result = coverage.build_anchor_set(items, 3)

    assert result["anchors"] == [
        {"id": "AP-1", "index": 0},
        {"id": "AP-2", "index": 2},
        {"id": "AP-3", "index": 3},
    ]


def _anchor_set() -> list[dict[str, int | str]]:
    return [
        {"id": "AP-1", "index": 0},
        {"id": "AP-2", "index": 1},
        {"id": "AP-3", "index": 2},
        {"id": "AP-4", "index": 3},
    ]


def test_check_overlap_succeeds_with_enough_hits_and_consistent_order():
    result = coverage.check_anchor_overlap(
        _items("AP-new", "AP-1", "AP-2", "AP-3", "AP-tail"),
        _anchor_set(),
    )

    assert result["coverage_ok"] is True
    assert result["order_consistent"] is True
    assert result["hits"]["count"] == 3
    assert [hit["id"] for hit in result["hits"]["items"]] == ["AP-1", "AP-2", "AP-3"]


def test_check_overlap_fails_when_hit_count_is_below_threshold():
    result = coverage.check_anchor_overlap(
        _items("AP-new", "AP-1", "AP-tail"),
        _anchor_set(),
        min_hits=3,
    )

    assert result["coverage_ok"] is False
    assert result["order_consistent"] is False
    assert result["hits"]["count"] == 1
    assert "少於門檻 3" in result["reason"]


def test_check_overlap_fails_when_anchor_order_is_reversed():
    result = coverage.check_anchor_overlap(
        _items("AP-3", "AP-2", "AP-1", "AP-tail"),
        _anchor_set(),
    )

    assert result["coverage_ok"] is False
    assert result["order_consistent"] is False
    assert "相對順序" in result["reason"]


def test_check_overlap_fails_when_anchor_order_is_interleaved():
    result = coverage.check_anchor_overlap(
        _items("AP-1", "AP-3", "AP-2", "AP-4"),
        _anchor_set(),
    )

    assert result["coverage_ok"] is False
    assert result["order_consistent"] is False


def test_check_overlap_fails_when_hits_are_standard_library_video_in_new_list():
    """圖庫批次不能證明清單銜接：即使新清單裡有 3 個 id 對得上 anchor、
    順序也遞增，只要那幾列在新清單裡的 comp 是 StandardLibraryVideo，
    就不算真正命中（回歸測試，見 D21 review 抓到的偽陽性）。"""
    new_items = [
        {"id": "AP-1", "comp": "StandardLibraryVideo", "title": "one"},
        {"id": "AP-2", "comp": "StandardLibraryVideo", "title": "two"},
        {"id": "AP-3", "comp": "StandardLibraryVideo", "title": "three"},
        {"id": "AP-tail", "comp": "Editorial", "title": "tail"},
    ]

    result = coverage.check_anchor_overlap(new_items, _anchor_set())

    assert result["coverage_ok"] is False
    assert result["hits"]["count"] == 0
    assert "沒有命中任何 anchor" in result["reason"]


def test_check_overlap_fails_clearly_when_there_is_no_overlap():
    result = coverage.check_anchor_overlap(
        _items("AP-new-1", "AP-new-2", "AP-new-3"),
        _anchor_set(),
    )

    assert result["coverage_ok"] is False
    assert result["hits"]["count"] == 0
    assert "沒有命中任何 anchor" in result["reason"]
    assert "需要至少 3 個" in result["reason"]


@pytest.mark.parametrize(
    ("current", "expected"),
    [(100, 400), (400, 600), (600, None)],
)
def test_pagesize_ladder(current, expected):
    assert coverage.next_page_size(current) == expected


@pytest.mark.parametrize(
    ("argv", "expected_stdout"),
    [
        (["pagesize-ladder", "--current", "100"], "400\n"),
        (["pagesize-ladder", "--current", "400"], "600\n"),
        (["pagesize-ladder", "--current", "600"], "exhausted\n"),
    ],
)
def test_pagesize_ladder_cli(argv, expected_stdout):
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout == expected_stdout


def test_cli_writes_anchor_and_overlap_json(tmp_path):
    baseline = _write_json(
        tmp_path / "baseline.json",
        [
            {"id": "AP-std", "comp": "StandardLibraryVideo", "title": "library"},
            {"id": "AP-1", "comp": "Editorial", "title": "one"},
            {"id": "AP-2", "comp": "Editorial", "title": "two"},
            {"id": "AP-3", "comp": "Editorial", "title": "three"},
        ],
    )
    new_list = _write_json(tmp_path / "new.json", _items("AP-x", "AP-1", "AP-2", "AP-3"))
    anchor_path = tmp_path / "anchor.json"
    result_path = tmp_path / "result.json"

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "anchor-set",
            "--list",
            str(baseline),
            "--n",
            "3",
            "--out",
            str(anchor_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "check-overlap",
            "--list",
            str(new_list),
            "--anchor",
            str(anchor_path),
            "--out",
            str(result_path),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    anchor_payload = json.loads(anchor_path.read_text(encoding="utf-8"))
    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert anchor_payload["partial"] is False
    assert result_payload["coverage_ok"] is True
