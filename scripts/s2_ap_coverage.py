#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AP 清單的錨點重疊 coverage 檢查工具。

這個工具只處理離線 JSON 快照，不連線抓取 AP，也不依賴掃帶系統的其他
模組。AP 清單的順序直接代表清單位置；``ts``／``firstcreated`` 等內容
日期欄位完全不參與判斷。

Examples::

    python scripts/s2_ap_coverage.py anchor-set \
        --list ap_list_100.json --n 20 --out anchor.json
    python scripts/s2_ap_coverage.py check-overlap \
        --list ap_list_100.json --anchor anchor.json --out coverage.json
    python scripts/s2_ap_coverage.py pagesize-ladder --current 100
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


STANDARD_LIBRARY_VIDEO = "StandardLibraryVideo"
PAGE_SIZE_LADDER = (100, 400, 600)


def _positive_int(value: str) -> int:
    """argparse type for counts and thresholds that must be greater than zero."""
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"不是有效的整數：{value}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必須是大於 0 的整數")
    return parsed


def _read_json(path: str | Path) -> Any:
    try:
        with Path(path).open(encoding="utf-8-sig") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 格式錯誤：{path}（第 {exc.lineno} 行）") from exc
    except OSError as exc:
        raise ValueError(f"無法讀取 JSON：{path}（{exc}）") from exc


def _write_json(path: str | Path, payload: Any) -> None:
    try:
        with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise ValueError(f"無法寫入 JSON：{path}（{exc}）") from exc


def _item_id(item: Any, index: int) -> str:
    if not isinstance(item, dict):
        raise ValueError(f"清單第 {index} 筆不是 JSON object")
    if "id" not in item or item["id"] is None:
        raise ValueError(f"清單第 {index} 筆缺少 id")
    item_id = str(item["id"]).strip()
    if not item_id:
        raise ValueError(f"清單第 {index} 筆的 id 不可為空")
    if "comp" not in item:
        raise ValueError(f"清單第 {index} 筆缺少 comp")
    return item_id


def load_ap_list(path: str | Path) -> list[dict[str, Any]]:
    """讀取並驗證 AP 清單快照；不改變列的原始順序。"""
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"AP 清單必須是 JSON array：{path}")
    for index, item in enumerate(payload):
        _item_id(item, index)
    return payload


def build_anchor_set(items: list[dict[str, Any]], n: int) -> dict[str, Any]:
    """從清單前方掃描可用項目，產生以原始 index 定位的 anchor set。

    同一個 id 若在快照中重複，只保留第一次出現的位置。這讓 anchor set
    真正代表「不同 ID」；重複列不會虛增後續的命中數。
    """
    if n <= 0:
        raise ValueError("n 必須是大於 0 的整數")

    anchors: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        item_id = _item_id(item, index)
        if item.get("comp") == STANDARD_LIBRARY_VIDEO or item_id in seen:
            continue
        seen.add(item_id)
        anchors.append({"id": item_id, "index": index})
        if len(anchors) == n:
            break

    return {
        "anchors": anchors,
        "n": n,
        "partial": len(anchors) < n,
    }


def _load_anchor_set(path: str | Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    # 接受純 anchors array 也方便人工準備小型離線 fixture；anchor-set
    # 子指令輸出的標準格式則是 object。
    raw_anchors = payload.get("anchors") if isinstance(payload, dict) else payload
    if not isinstance(raw_anchors, list):
        raise ValueError(f"anchor 檔必須包含 anchors array：{path}")

    anchors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_indices: set[int] = set()
    for position, anchor in enumerate(raw_anchors):
        if not isinstance(anchor, dict) or "id" not in anchor or "index" not in anchor:
            raise ValueError(f"anchor 第 {position} 筆必須包含 id 與 index")
        item_id = str(anchor["id"]).strip()
        if not item_id:
            raise ValueError(f"anchor 第 {position} 筆的 id 不可為空")
        try:
            index = int(anchor["index"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"anchor 第 {position} 筆的 index 必須是整數") from exc
        if index < 0:
            raise ValueError(f"anchor 第 {position} 筆的 index 不可為負數")
        if item_id in seen_ids:
            raise ValueError(f"anchor id 重複：{item_id}")
        if index in seen_indices:
            raise ValueError(f"anchor index 重複：{index}")
        seen_ids.add(item_id)
        seen_indices.add(index)
        anchors.append({"id": item_id, "index": index})
    return sorted(anchors, key=lambda anchor: anchor["index"])


def _strictly_increasing(values: list[int]) -> bool:
    return all(left < right for left, right in zip(values, values[1:]))


def check_anchor_overlap(
    items: list[dict[str, Any]],
    anchor_set: list[dict[str, Any]],
    min_hits: int = 3,
) -> dict[str, Any]:
    """比對 anchor 命中與相對順序，回傳可直接寫入 JSON 的結果。

    anchor set 依基準快照 index 排序；本輪命中的 index 必須嚴格遞增，
    也就是保留基準清單的相對順序。只使用 index，不使用 ts 或任何日期欄位。
    """
    if min_hits <= 0:
        raise ValueError("min_hits 必須是大於 0 的整數")

    # 同一 ID 若在新清單重複，第一次出現的位置才是它在清單中的位置；
    # 命中數仍然以不同 ID 計算。StandardLibraryVideo 批次項目不得被拿來
    # 當 anchor 命中（即使 id 剛好等於某個 anchor），但原始 index 位移
    # 仍要保留，所以照樣 enumerate 全部項目，只是跳過建立映射。
    new_indices: dict[str, int] = {}
    for index, item in enumerate(items):
        item_id = _item_id(item, index)
        if item.get("comp") == STANDARD_LIBRARY_VIDEO:
            continue
        new_indices.setdefault(item_id, index)

    hits = [
        {
            "id": anchor["id"],
            "anchor_index": anchor["index"],
            "new_index": new_indices[anchor["id"]],
        }
        for anchor in anchor_set
        if anchor["id"] in new_indices
    ]
    hit_count = len(hits)

    order_consistent = False
    if hit_count >= min_hits:
        order_consistent = _strictly_increasing(
            [hit["new_index"] for hit in hits]
        )

    if hit_count == 0:
        reason = f"沒有命中任何 anchor（需要至少 {min_hits} 個），無法確認清單銜接。"
    elif hit_count < min_hits:
        reason = (
            f"命中 {hit_count} 個不同 anchor，少於門檻 {min_hits} 個，"
            "無法確認清單銜接。"
        )
    elif not order_consistent:
        reason = (
            f"命中 {hit_count} 個不同 anchor，但相對順序與基準清單不一致，"
            "無法確認清單銜接。"
        )
    else:
        reason = (
            f"命中 {hit_count} 個不同 anchor，且相對順序與基準清單一致，"
            "清單銜接成功。"
        )

    return {
        "coverage_ok": hit_count >= min_hits and order_consistent,
        "hits": {"count": hit_count, "items": hits},
        "order_consistent": order_consistent,
        "reason": reason,
    }


def next_page_size(current: int) -> int | None:
    """回傳固定 PageSize 階梯的下一階；到頂端時回傳 None。"""
    try:
        position = PAGE_SIZE_LADDER.index(int(current))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"current 必須是 PageSize 階梯中的值：{PAGE_SIZE_LADDER}"
        ) from exc
    if position + 1 >= len(PAGE_SIZE_LADDER):
        return None
    return PAGE_SIZE_LADDER[position + 1]


def cmd_anchor_set(args: argparse.Namespace) -> dict[str, Any]:
    items = load_ap_list(args.list_path)
    payload = build_anchor_set(items, args.n)
    _write_json(args.out, payload)
    print(f"anchor-set: {len(payload['anchors'])} anchors -> {args.out}")
    return payload


def cmd_check_overlap(args: argparse.Namespace) -> dict[str, Any]:
    items = load_ap_list(args.list_path)
    anchors = _load_anchor_set(args.anchor)
    payload = check_anchor_overlap(items, anchors, args.min_hits)
    _write_json(args.out, payload)
    print(payload["reason"])
    print(f"check-overlap: result -> {args.out}")
    return payload


def cmd_pagesize_ladder(args: argparse.Namespace) -> int | None:
    next_size = next_page_size(args.current)
    print(next_size if next_size is not None else "exhausted")
    return next_size


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    anchor_parser = sub.add_parser(
        "anchor-set", help="從 AP 清單快照依原始順序抽出 anchor set"
    )
    anchor_parser.add_argument("--list", dest="list_path", required=True)
    anchor_parser.add_argument("--n", type=_positive_int, required=True)
    anchor_parser.add_argument("--out", required=True)
    anchor_parser.set_defaults(func=cmd_anchor_set)

    overlap_parser = sub.add_parser(
        "check-overlap", help="檢查新 AP 清單是否與 anchor set 銜接"
    )
    overlap_parser.add_argument("--list", dest="list_path", required=True)
    overlap_parser.add_argument("--anchor", required=True)
    overlap_parser.add_argument(
        "--min-hits", type=_positive_int, default=3, help="最低不同 anchor 命中數（預設 3）"
    )
    overlap_parser.add_argument("--out", required=True)
    overlap_parser.set_defaults(func=cmd_check_overlap)

    ladder_parser = sub.add_parser(
        "pagesize-ladder", help="取得 100→400→600 階梯的下一個 PageSize"
    )
    ladder_parser.add_argument("--current", type=int, required=True)
    ladder_parser.set_defaults(func=cmd_pagesize_ladder)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ValueError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    main()
