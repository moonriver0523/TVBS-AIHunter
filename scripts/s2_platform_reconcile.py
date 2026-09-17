#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ENEX／ABC 候選檔清單對帳（MASTER A9 子項④）。

## 要解決什麼

三站的漏收是靠 `s2_audit.py` 的清單快照跟狀態檔機械比對抓出來的（0805 抓到 47 則）；
ENEX／ABC 候選 JSON 裡的 `counts.掃描` 目前完全是 agent 自己宣稱的數字，
沒有任何第二層驗證——agent 少算了也不會有人發現。

## 這支腳本只做離線比對，不會自己連線

`counts.掃描` 是否可信，要跟站方「這個時間窗實際有幾則」的真實數字比對，但那個數字
只能由掃帶 agent 在 `browser_evaluate` 裡打一次輕量查詢才拿得到（見
`common/18-交換平台素材整併.md` §10 的 ENEX／ABC 健康檢查查詢範本）。這支腳本吃
agent 查回來的那個數字（`--true-count`），跟候選檔裡的 `counts.掃描` 比對，
不符就報告差異；`--apply` 才把落差寫進候選檔的 `needs_review`（候選檔本來就是
未合併的暫存檔，改它不受「不准改狀態檔」那條限制——那條管的是正式狀態檔）。

## 用法

    python scripts/s2_platform_reconcile.py --file "…\\{MMDD}-{站}-state.json" --true-count 82
    python scripts/s2_platform_reconcile.py --file "…" --true-count 82 --apply

離開碼：0＝一致或已標記；1＝不一致但未 --apply（提醒還沒留痕）；2＝讀檔失敗。
"""
import argparse
import json
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="ENEX／ABC 候選檔清單對帳")
    ap.add_argument("--file", required=True, help="候選檔路徑（…-state.json）")
    ap.add_argument("--true-count", type=int, required=True,
                     help="agent 用 18 檔 §10 健康檢查查詢實測到的窗內真實則數")
    ap.add_argument("--apply", action="store_true",
                     help="不一致時把落差寫進候選檔的 needs_review（省略＝只報告）")
    args = ap.parse_args()

    try:
        with open(args.file, encoding="utf-8-sig") as f:
            doc = json.load(f)
    except Exception as e:
        print(f"ERROR 讀不到候選檔：{e}", file=sys.stderr)
        return 2

    counts = doc.get("counts", {})
    claimed = counts.get("掃描")
    if claimed is None:
        print("ERROR candidate 缺 counts.掃描，無從對帳", file=sys.stderr)
        return 2

    diff = args.true_count - claimed
    if diff == 0:
        print(f"✅ 對帳一致：counts.掃描={claimed}，真實={args.true_count}")
        return 0

    direction = "少算" if diff > 0 else "多算"
    note = (f"清單對帳不符：candidate counts.掃描={claimed}，"
            f"健康檢查真實={args.true_count}，agent {direction} {abs(diff)} 則")
    print(f"⚠️ {note}")

    if not args.apply:
        print("（未加 --apply，候選檔未寫入——記得處理，不要放著）")
        return 1

    doc.setdefault("needs_review", [])
    if note not in doc["needs_review"]:
        doc["needs_review"].append(note)
    with open(args.file, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"OK 已寫入候選檔 needs_review：{args.file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
