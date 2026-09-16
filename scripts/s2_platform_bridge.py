#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ENEX／ABC 骨架橋接工具（D19）：先出骨架、agent 填完再轉成 platform entries。

這支是獨立工具，**不改** `s2_batch_prep.py` 的 SITE_SPEC／cmd_build／cmd_from_raw，
也**不改** `s2_platform_extract.py`。NS／AP／RT 三站的正式骨架流程維持原樣；
ENEX／ABC 走這裡，產出 `extract_enex`／`extract_abc` 吃得下的 `{id: {…}}`。

完整流程（以 ABC 為例）：

    python scripts/s2_platform_bridge.py from-raw --site abc --raw abc_raw_0430.json --detail abc_detail_0430.json --checkpoint 0916-0430 --out abc_skeleton_0430.json
    # agent 編輯 abc_skeleton_0430.json，填 entry/category/tc/skip
    python scripts/s2_platform_bridge.py build --skeleton abc_skeleton_0430.json --out abc_entries_0430.json
    python scripts/s2_platform_extract.py abc --raw abc_raw_0430.json --entries abc_entries_0430.json --checkpoint 0916-0430 --out abc_candidate_0430.txt

ENEX 同款，不帶 `--detail`（全文在 raw 的 `desc`，機械帶進骨架給 agent 看；
`build` 輸出**不帶** `src_text`／`detailId`，因為 `extract_enex` 是從 raw.desc 讀正文）。

機械 vs 編輯判斷
================
- **機械**（這支填）：id、src_text（ENEX＝raw.desc；ABC＝detail.script_html）、
  detailId（僅 ABC）、hint、sb_count 缺省 0。
- **agent 填**：`entry`／`category`／`tc`／`skip`（排除理由；語意等同
  platform entries 的 `skip`，跟 raw 端若有機械排除欄位是兩回事，不要混用）。
- ABC 的 Detail 頁回應天生帶 `script_html` 與 `detailId`，from-raw 階段就合併進來，
  agent 不必再去 Detail 頁抄全文。找不到對應 detail 的 story 記 known_gaps、
  該筆骨架列仍照出（`src_text`／`detailId` 留空並標 `detail_missing`）。
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s2_batch_prep import INSPECT_TEXT_BUDGET, _load_raw_any  # noqa: E402  卸殼／分頁預算；不要重寫
from s2_platform_extract import (  # noqa: E402
    abc_length_mmss,
    bare_enex_id,
    truncate,
)
import s2_state  # noqa: E402  from-raw 讀狀態檔（唯讀，D12 已在庫標記）

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

_NONE_MARKERS = ("", "<NONE>", "none", "null")


def load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _html_to_text(s):
    """Detail 頁 `#script_smry` 的 innerHTML → 純文。本來就是純文時幾乎是 no-op。"""
    s = s or ""
    s = s.replace("\r", "")
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _first150(text):
    return re.sub(r"\s+", " ", text or "").strip()[:150]


def _abc_id(story):
    s = str(story or "").strip()
    if not s:
        return ""
    return s if s.upper().startswith("ABC") else "ABC" + s


def _abc_story_of_id(item_id):
    s = str(item_id or "")
    return s[3:] if s.upper().startswith("ABC") else s


def _script_html_to_src_text(script_html):
    raw = "" if script_html is None else str(script_html).strip()
    if raw.lower() in _NONE_MARKERS:
        return ""
    # 骨架必須帶全文；truncate 留給 extract_abc。
    return _html_to_text(raw)


def _lookup_status(have, item_id):
    """狀態檔的 id 可能帶／不帶站別前綴，兩邊都認（同 extract 的 lookup_entry 精神）。"""
    if not have or not item_id:
        return None
    candidates = [item_id]
    s = str(item_id)
    if s.upper().startswith("ENEX"):
        candidates.append(s[4:])
    elif s.upper().startswith("ABC"):
        candidates.append(s[3:])
    else:
        candidates.append("ENEX" + s)
        candidates.append("ABC" + s)
    for c in candidates:
        if c in have:
            return have[c]
    return None


def _load_items(path):
    try:
        items, _shell = _load_raw_any(path)
    except ValueError as e:
        print(f"✗ 卸殼失敗：{e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(items, list) or not all(isinstance(x, dict) for x in items):
        print(f"✗ {path} 卸殼後不是 dict 陣列（實得 {type(items).__name__}）",
              file=sys.stderr)
        sys.exit(2)
    return items


def _load_abc_detail(path):
    """`--detail` → {story: detail物件}。path 為空就當沒有對應資料，不擋流程。"""
    if not path:
        print("⚠️ ABC from-raw 沒給 --detail，每一則都會標 detail_missing",
              file=sys.stderr)
        return {}
    items = _load_items(path)
    by_story = {}
    dups = []
    for it in items:
        story = str(it.get("story") or it.get("News Story") or "").strip()
        if not story:
            continue
        if story.upper().startswith("ABC") and story[3:]:
            story = story[3:]
        if story in by_story:
            dups.append(story)
            continue
        by_story[story] = it
    if dups:
        print(f"⚠️ detail 裡有重複 story／News Story，只保留第一次出現的那筆："
              f"{', '.join(dups)}", file=sys.stderr)
    return by_story


def _enex_row(it, checkpoint):
    rid = bare_enex_id(it.get("id") or it.get("_id"))
    if not rid:
        return None
    src_text = truncate(it.get("desc") or "")
    dur = it.get("dur")
    if dur is None:
        dur = it.get("duration")
    if dur is None:
        dur = it.get("dur_ms", "")
    sb_count = it.get("sb_count", 0)
    try:
        sb_count = int(sb_count or 0)
    except (TypeError, ValueError):
        sb_count = 0
    head = it.get("title") or it.get("head") or ""
    return {
        "id": rid,
        "source": "ENEX",
        "checkpoint": checkpoint,
        "src_text": src_text,
        "sb_count": sb_count,
        "entry": "",
        "category": "",
        "tc": "",
        "skip": "",
        "hint": {
            "head": head,
            "first150": _first150(src_text),
            "dur": dur if dur is not None else "",
            "sb_count": sb_count,
        },
    }


def _abc_row(it, checkpoint, detail_map):
    story = str(it.get("News Story") or "").strip()
    if not story:
        return None
    item_id = _abc_id(story)
    bare = _abc_story_of_id(item_id)
    detail = detail_map.get(bare) or detail_map.get(item_id)
    src_text = ""
    detail_id = ""
    missing = False
    if detail:
        src_text = _script_html_to_src_text(detail.get("script_html"))
        detail_id = detail.get("detailId")
        if detail_id is None:
            detail_id = ""
        else:
            detail_id = str(detail_id)
        # detail 對到了但 script_html 空字串／null／缺欄 → 一樣標 detail_missing
        if not src_text:
            missing = True
    else:
        missing = True
    length = it.get("Length")
    dur = abc_length_mmss(length)
    if dur is None:
        dur = str(length or "")
    sb_count = it.get("sb_count", 0)
    try:
        sb_count = int(sb_count or 0)
    except (TypeError, ValueError):
        sb_count = 0
    head = it.get("Slug") or it.get("slug") or ""
    if not head:
        head = _first150(src_text)
    row = {
        "id": item_id,
        "source": "ABC",
        "checkpoint": checkpoint,
        "src_text": src_text,
        "detailId": detail_id,
        "sb_count": sb_count,
        "entry": "",
        "category": "",
        "tc": "",
        "skip": "",
        "hint": {
            "head": head,
            "first150": _first150(src_text),
            "dur": dur,
            "sb_count": sb_count,
        },
    }
    if missing:
        row["detail_missing"] = True
    return row


def cmd_from_raw(args):
    """站方 raw（＋ABC detail）＋ 可選狀態檔 → 提示表＋骨架 JSON。

    D12：`--state` 給了才排除——只排除已經是 `has_script` 的 id，
    `pending`／其他狀態一律保留並標 `prev_status`。
    """
    site = args.site
    items = _load_items(args.raw)
    detail_map = _load_abc_detail(args.detail) if site == "abc" else {}

    have = {}
    if args.state:
        state = s2_state.load(args.state)
        have = {i: (v.get("script_status") or "") for i, v in state["items"].items()}

    skeleton = []
    already_have = []
    pending_kept = []
    known_gaps = []
    seen = set()
    dup_ids = []
    for it in items:
        row = _enex_row(it, args.checkpoint) if site == "enex" else _abc_row(
            it, args.checkpoint, detail_map)
        if row is None:
            continue
        item_id = row["id"]
        if not item_id:
            continue
        if item_id in seen:
            dup_ids.append(item_id)
            continue
        seen.add(item_id)

        prev_status = _lookup_status(have, item_id)
        if prev_status == "has_script":
            already_have.append(item_id)
            continue
        if prev_status is not None:
            row["prev_status"] = prev_status
            if prev_status == "pending":
                pending_kept.append(item_id)

        if row.get("detail_missing"):
            bare = _abc_story_of_id(item_id)
            if detail_map.get(bare) or detail_map.get(item_id):
                known_gaps.append(
                    f"{item_id}: detail 有對到但全文欄位是空的，src_text 留空")
            else:
                known_gaps.append(
                    f"{item_id}: --detail 找不到對應 story，src_text／detailId 留空")
        skeleton.append(row)

    out = args.out
    if not out:
        hhmm = str(args.checkpoint).split("-")[-1]
        base = os.path.dirname(os.path.abspath(args.raw))
        out = os.path.join(base, f"{site}_skeleton_{hhmm}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)

    all_lines = []
    for idx, row in enumerate(skeleton, 1):
        hint = row.get("hint") or {}
        all_lines.append(
            f"#{idx}｜{row['id']}｜{hint.get('dur', '')}｜{hint.get('sb_count', 0)}｜"
            f"{hint.get('head', '')}｜{hint.get('first150', '')}"
        )
    pages, cur, cur_len = [], [], 0
    for ln in all_lines:
        ln_len = len(ln) + 1
        if cur and cur_len + ln_len > INSPECT_TEXT_BUDGET:
            pages.append(cur)
            cur, cur_len = [], 0
        cur.append(ln)
        cur_len += ln_len
    pages.append(cur)  # 0 則時也留一頁空的，--page 1 才有東西可選

    page_no = args.page or 1
    if page_no < 1 or page_no > len(pages):
        print(f"✗ --page {page_no} 超出範圍（共 {len(pages)} 頁）", file=sys.stderr)
        sys.exit(1)

    page_lines = pages[page_no - 1]
    if page_lines:
        print("\n".join(page_lines))
    else:
        print("（骨架 0 則）")
    if len(pages) > 1:
        if page_no < len(pages):
            print(f"— 第 {page_no}/{len(pages)} 頁，--page {page_no + 1} 看下一頁 —")
        else:
            print(f"— 第 {page_no}/{len(pages)} 頁（最後一頁）—")

    if dup_ids:
        print(f"⚠️ raw 裡有重複 id，只保留第一次出現的那筆：{', '.join(dup_ids)}",
              file=sys.stderr)
    if already_have:
        print(f"已在庫略過 {len(already_have)} 則：{', '.join(already_have)}",
              file=sys.stderr)
    if pending_kept:
        print(f"pending 保留 {len(pending_kept)} 則：{', '.join(pending_kept)}",
              file=sys.stderr)
    if known_gaps:
        print(f"⚠️ known_gaps {len(known_gaps)} 項（不擋流程，骨架列仍照出）："
              + "；".join(known_gaps), file=sys.stderr)
    print(f"骨架已寫 {out}（{len(skeleton)} 則）", file=sys.stderr)


def _as_int_sb(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def cmd_build(args):
    """骨架陣列 → platform `--entries` 要的 `{id: {raw_entry, category, …}}`。

    `entry` 空字串的列印警告但仍輸出（讓下游 extract 自己記 known_gaps），
    除非該筆 `skip` 有填（排除列不要求 raw_entry）。
    """
    rows = load_json(args.skeleton)
    if not isinstance(rows, list):
        print(f"✗ 骨架應為陣列，實得 {type(rows).__name__}", file=sys.stderr)
        sys.exit(2)

    entries = {}
    missing = []
    dup_ids = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_id = row.get("id")
        if not item_id:
            continue
        skip = row.get("skip") or ""
        entry_text = row.get("entry") or ""
        if not entry_text and not skip:
            missing.append(str(item_id))

        value = {
            "raw_entry": entry_text,
            "category": row.get("category") if row.get("category") is not None else "",
            "sb_count": _as_int_sb(row.get("sb_count")),
        }
        if skip:
            value["skip"] = skip
        # ABC：骨架階段已機械算好的全文／detailId 直接照抄。
        # ENEX：extract_enex 從 raw.desc 讀正文，帶 src_text／detailId 只會污染輸出。
        source = (row.get("source") or "").upper()
        if source == "ABC" or "detailId" in row:
            value["src_text"] = row.get("src_text") or ""
            value["detailId"] = row.get("detailId") if row.get("detailId") is not None else ""
        sid = str(item_id)
        if sid in entries:
            dup_ids.append(sid)
        entries[sid] = value

    out = json.dumps(entries, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"已寫入 {args.out}（{len(entries)} 則）", file=sys.stderr)
    else:
        print(out)
    if dup_ids:
        print(f"⚠️ 骨架裡有重複 id，後筆覆蓋前筆：{', '.join(dup_ids)}",
              file=sys.stderr)
    if missing:
        print("⚠️ 骨架裡有、沒填 entry 的 id（未填，不算錯，該筆仍輸出給下游 extract 記 "
              f"known_gaps）：{', '.join(missing)}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_fr = sub.add_parser(
        "from-raw",
        help="raw（＋ABC detail）一次產出提示表＋骨架 JSON",
    )
    p_fr.add_argument("--site", required=True, choices=["enex", "abc"])
    p_fr.add_argument("--raw", required=True)
    p_fr.add_argument("--detail", help="ABC Detail 頁回應陣列（key＝story）；僅 ABC 需要")
    p_fr.add_argument("--state", help="狀態檔路徑；給了才排除已 has_script 的 id")
    p_fr.add_argument("--checkpoint", required=True)
    p_fr.add_argument("--out", help="骨架 json 路徑；不給就用 raw 所在目錄組 {site}_skeleton_{HHMM}.json")
    p_fr.add_argument("--page", type=int, help="提示表分頁（每頁 ≤28,000 字元），預設第 1 頁")
    p_fr.set_defaults(func=cmd_from_raw)

    p_bd = sub.add_parser(
        "build",
        help="骨架 json → platform entries `{id: {raw_entry, category, …}}`",
    )
    p_bd.add_argument("--skeleton", required=True)
    p_bd.add_argument("--out")
    p_bd.set_defaults(func=cmd_build)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
