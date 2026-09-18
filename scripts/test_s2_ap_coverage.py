#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s2_ap_coverage.py 的離線合成 fixture 測試。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    print("SKIP: pytest-only（從 repo 根目錄跑 pytest scripts/test_s2_ap_coverage.py）")
    sys.exit(0)

import pytest

from scripts import s2_ap_coverage as coverage


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "s2_ap_coverage.py"


def _write_json(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _items(*ids: str) -> list[dict[str, str]]:
    return [
        {
            "id": item_id,
            "comp": "Editorial",
            "func": "BroadcastVideo",
            "title": f"Synthetic {item_id}",
        }
        for item_id in ids
    ]


def test_anchor_set_keeps_original_index_and_skips_online_video():
    items = [
        {
            "id": "AP-online",
            "comp": "StandardLibraryVideo",
            "func": "OnlineVideo",
            "title": "online",
        },
        {"id": "AP-1", "comp": "Editorial", "func": "BroadcastVideo", "title": "one"},
        {"id": "AP-2", "comp": "Editorial", "func": "BroadcastVideo", "title": "two"},
        {"id": "AP-3", "comp": "Editorial", "func": "BroadcastVideo", "title": "three"},
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
        {
            "id": "AP-online",
            "comp": "StandardLibraryVideo",
            "func": "OnlineVideo",
            "title": "online",
        },
        {"id": "AP-1", "comp": "Editorial", "func": "BroadcastVideo", "title": "one"},
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
    assert result["lis_length"] == 1
    assert "LIS 長度" in result["reason"]


def test_check_overlap_allows_minor_reordering_when_lis_reaches_threshold():
    # 舊版要求所有命中 index 嚴格遞增，這個案例會是 False；LIS 修法應放行。
    result = coverage.check_anchor_overlap(
        _items("AP-1", "AP-3", "AP-2", "AP-4"),
        _anchor_set(),
    )

    assert result["coverage_ok"] is True
    assert result["order_consistent"] is True
    assert result["lis_length"] == 3
    assert "LIS 長度 3" in result["reason"]


def test_check_overlap_fails_when_hits_are_online_video_in_new_list():
    """OnlineVideo 不適合證明清單銜接，即使 comp 是 StandardLibraryVideo。"""
    new_items = [
        {
            "id": "AP-1",
            "comp": "StandardLibraryVideo",
            "func": "OnlineVideo",
            "title": "one",
        },
        {
            "id": "AP-2",
            "comp": "StandardLibraryVideo",
            "func": "OnlineVideo",
            "title": "two",
        },
        {
            "id": "AP-3",
            "comp": "StandardLibraryVideo",
            "func": "OnlineVideo",
            "title": "three",
        },
        {"id": "AP-tail", "comp": "Editorial", "func": "BroadcastVideo", "title": "tail"},
    ]

    result = coverage.check_anchor_overlap(new_items, _anchor_set())

    assert result["coverage_ok"] is False
    assert result["hits"]["count"] == 0
    assert "沒有命中任何 anchor" in result["reason"]


def test_online_video_is_excluded_from_anchor_set_and_hits():
    baseline = [
        {"id": "AP-online", "comp": "Editorial", "func": "OnlineVideo"},
        {"id": "AP-broadcast", "comp": "Editorial", "func": "BroadcastVideo"},
    ]
    anchors = coverage.build_anchor_set(baseline, 1)["anchors"]

    result = coverage.check_anchor_overlap(
        [
            {"id": "AP-online", "comp": "Editorial", "func": "OnlineVideo"},
            {"id": "AP-broadcast", "comp": "Editorial", "func": "BroadcastVideo"},
        ],
        [{"id": "AP-online", "index": 0}],
        min_hits=1,
    )

    assert anchors == [{"id": "AP-broadcast", "index": 1}]
    assert result["hits"]["count"] == 0
    assert result["coverage_ok"] is False


def test_broadcast_video_is_valid_even_when_comp_is_standard_library_video():
    items = [
        {
            "id": "AP-broadcast",
            "comp": "StandardLibraryVideo",
            "func": "BroadcastVideo",
        },
    ]

    anchors = coverage.build_anchor_set(items, 1)["anchors"]
    result = coverage.check_anchor_overlap(items, anchors, min_hits=1)

    assert anchors == [{"id": "AP-broadcast", "index": 0}]
    assert result["coverage_ok"] is True
    assert result["hits"]["count"] == 1


def test_missing_func_falls_back_to_consumer_ready_sig():
    items = [
        {"id": "AP-online-missing", "comp": "Editorial", "sig": "ConsumerReady|SNTV"},
        {
            "id": "AP-online-empty",
            "comp": "Editorial",
            "func": "",
            "sig": "consumerready|SNTV",
        },
        {"id": "AP-broadcast", "comp": "Editorial", "sig": "NewsroomReady"},
    ]

    anchors = coverage.build_anchor_set(items, 1)["anchors"]
    result = coverage.check_anchor_overlap(
        items,
        [
            {"id": "AP-online-missing", "index": 0},
            {"id": "AP-online-empty", "index": 1},
        ],
        min_hits=1,
    )

    assert anchors == [{"id": "AP-broadcast", "index": 2}]
    assert result["hits"]["count"] == 0
    assert result["coverage_ok"] is False


def test_missing_func_and_sig_is_conservatively_kept():
    items = [{"id": "AP-old", "comp": "StandardLibraryVideo"}]

    anchors = coverage.build_anchor_set(items, 1)["anchors"]
    result = coverage.check_anchor_overlap(items, anchors, min_hits=1)

    assert anchors == [{"id": "AP-old", "index": 0}]
    assert result["coverage_ok"] is True
    assert result["hits"]["count"] == 1


def test_check_overlap_fails_clearly_when_there_is_no_overlap():
    result = coverage.check_anchor_overlap(
        _items("AP-new-1", "AP-new-2", "AP-new-3"),
        _anchor_set(),
    )

    assert result["coverage_ok"] is False
    assert result["hits"]["count"] == 0
    assert "沒有命中任何 anchor" in result["reason"]
    assert "未達門檻 3" in result["reason"]


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
            {
                "id": "AP-online",
                "comp": "StandardLibraryVideo",
                "func": "OnlineVideo",
                "title": "online",
            },
            {"id": "AP-1", "comp": "Editorial", "func": "BroadcastVideo", "title": "one"},
            {"id": "AP-2", "comp": "Editorial", "func": "BroadcastVideo", "title": "two"},
            {"id": "AP-3", "comp": "Editorial", "func": "BroadcastVideo", "title": "three"},
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
    assert anchor_payload["list_path"] == str(baseline)
    assert result_payload["coverage_ok"] is True
    assert result_payload["list_path"] == str(new_list)
    assert result_payload["anchor_path"] == str(anchor_path)


def test_check_overlap_cli_exits_1_when_coverage_fails(tmp_path):
    """coverage_ok=False 時 CLI 必須 exit 1，且 stdout 完整保留 JSON 結果。"""
    baseline = _write_json(tmp_path / "baseline.json", _items("AP-1", "AP-2", "AP-3"))
    disjoint_list = _write_json(tmp_path / "disjoint.json", _items("AP-x", "AP-y", "AP-z"))
    anchor_path = tmp_path / "anchor.json"
    result_path = tmp_path / "result.json"

    # 先產出 anchor
    subprocess.run(
        [sys.executable, str(SCRIPT), "anchor-set", "--list", str(baseline), "--n", "3", "--out", str(anchor_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    # 執行 check-overlap，預期回傳 1
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "check-overlap",
            "--list",
            str(disjoint_list),
            "--anchor",
            str(anchor_path),
            "--out",
            str(result_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1, f"預期 exit 1，實際為 {proc.returncode}"
    # stdout 必須能被 json.loads 解析出完整 payload，證明未被 exit 吃掉
    stdout_payload = json.loads(proc.stdout)
    assert stdout_payload["coverage_ok"] is False
    assert stdout_payload["hits"]["count"] == 0
    assert stdout_payload["list_path"] == str(disjoint_list)
    assert stdout_payload["anchor_path"] == str(anchor_path)
    assert "未達門檻" in stdout_payload["reason"]

    # 磁碟輸出檔也完整寫入
    file_payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert file_payload == stdout_payload


def test_check_overlap_cli_exits_1_when_order_is_reversed(tmp_path):
    """命中數量夠但順序顛倒（order_consistent=False）時，CLI 必須 exit 1。"""
    baseline = _write_json(tmp_path / "baseline.json", _items("AP-1", "AP-2", "AP-3"))
    reversed_list = _write_json(tmp_path / "reversed.json", _items("AP-3", "AP-2", "AP-1"))
    anchor_path = tmp_path / "anchor.json"
    result_path = tmp_path / "result.json"

    subprocess.run(
        [sys.executable, str(SCRIPT), "anchor-set", "--list", str(baseline), "--n", "3", "--out", str(anchor_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "check-overlap",
            "--list",
            str(reversed_list),
            "--anchor",
            str(anchor_path),
            "--out",
            str(result_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 1
    stdout_payload = json.loads(proc.stdout)
    assert stdout_payload["coverage_ok"] is False
    assert stdout_payload["order_consistent"] is False
    assert stdout_payload["lis_length"] == 1


def test_check_overlap_cli_exits_0_when_coverage_succeeds(tmp_path):
    """coverage_ok=True 時 CLI 維持 exit 0，且 stdout 輸出完整 JSON。"""
    baseline = _write_json(tmp_path / "baseline.json", _items("AP-1", "AP-2", "AP-3"))
    overlap_list = _write_json(tmp_path / "overlap.json", _items("AP-new", "AP-1", "AP-2", "AP-3"))
    anchor_path = tmp_path / "anchor.json"
    result_path = tmp_path / "result.json"

    subprocess.run(
        [sys.executable, str(SCRIPT), "anchor-set", "--list", str(baseline), "--n", "3", "--out", str(anchor_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "check-overlap",
            "--list",
            str(overlap_list),
            "--anchor",
            str(anchor_path),
            "--out",
            str(result_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    stdout_payload = json.loads(proc.stdout)
    assert stdout_payload["coverage_ok"] is True
    assert stdout_payload["list_path"] == str(overlap_list)
    assert stdout_payload["anchor_path"] == str(anchor_path)


def test_check_overlap_cli_exits_2_on_error(tmp_path):
    """缺少必要參數或輸入檔案格式損毀時，CLI exit 2。"""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not a json", encoding="utf-8")
    result_path = tmp_path / "result.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "check-overlap",
            "--list",
            str(bad_file),
            "--anchor",
            str(bad_file),
            "--out",
            str(result_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 2
