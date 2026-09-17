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


def reconcile_candidate(doc, true_count, site):
    """回傳統一 reconcile record，不直接寫檔。

    輸入：
    - doc: candidate JSON 物件
    - true_count: agent 用健康檢查取得的真實則數
    - site: 必須是 ENEX 或 ABC
    """
    site_clean = (site or "").strip().upper()
    if site_clean not in ("ENEX", "ABC"):
        raise ValueError(f"site 必須是 ENEX 或 ABC，得到: {site}")

    if not isinstance(doc, dict):
        return {
            "status": "missing-evidence",
            "source": site_clean,
            "evidence_path": None,
            "list": None,
            "got": None,
            "missing": None,
            "missing_ids": [],
            "reason_code": "MISSING_CANDIDATE",
            "reason": "缺少候選檔資料",
        }

    counts = doc.get("counts") or {}
    claimed = counts.get("掃描")
    got = counts.get("收錄")

    if claimed is None or true_count is None:
        return {
            "status": "missing-evidence",
            "source": site_clean,
            "evidence_path": None,
            "list": claimed,
            "got": got,
            "missing": None,
            "missing_ids": [],
            "reason_code": "MISSING_EVIDENCE",
            "reason": "缺少 counts.掃描 或 true_count",
        }

    delta = true_count - claimed
    missing_count = abs(delta)
    if delta == 0:
        status = "ok"
        reason_code = None
        reason = None
    else:
        status = "needs-review"
        reason_code = "COUNT_MISMATCH"
        direction = "少算" if delta > 0 else "多算"
        reason = f"清單對帳不符：candidate counts.掃描={claimed}，健康檢查真實={true_count}，agent {direction} {missing_count} 則"

    rec = {
        "status": status,
        "source": site_clean,
        "evidence_path": None,
        "list": claimed,
        "got": got,
        "missing": missing_count,
        "missing_ids": [],
        "true_count": true_count,
        "reported_count": claimed,
        "delta": delta,
    }
    if reason_code:
        rec["reason_code"] = reason_code
    if reason:
        rec["reason"] = reason
    return rec


def main():
    ap = argparse.ArgumentParser(description="ENEX／ABC 候選檔清單對帳")
    ap.add_argument("--file", required=True, help="候選檔路徑（…-state.json）")
    ap.add_argument("--true-count", type=int, required=True,
                     help="agent 用 18 檔 §10 健康檢查查詢實測到的窗內真實則數")
    ap.add_argument("--apply", action="store_true",
                     help="不一致時把落差寫進候選檔的 needs_review（省略＝只報告）")
    ap.add_argument("--state-file", help="正式狀態檔路徑（可選：將對帳紀錄寫入正式狀態檔）")
    ap.add_argument("--checkpoint", help="對應之 checkpoint（搭配 --state-file 使用）")
    ap.add_argument("--site", choices=["ENEX", "ABC", "enex", "abc"],
                    help="站別（搭配 --state-file 使用，預設從檔名推導）")
    args = ap.parse_args()

    try:
        with open(args.file, encoding="utf-8-sig") as f:
            doc = json.load(f)
    except Exception as e:
        print(f"ERROR 讀不到候選檔：{e}", file=sys.stderr)
        return 2

    site = args.site
    if not site:
        fname = args.file.upper()
        if "ENEX" in fname:
            site = "ENEX"
        elif "ABC" in fname:
            site = "ABC"
        else:
            site = "ENEX"
    site = site.upper()

    rec = reconcile_candidate(doc, args.true_count, site)
    rec["evidence_path"] = args.file

    if rec["status"] == "missing-evidence":
        print(f"ERROR: {rec.get('reason')}", file=sys.stderr)
        return 2

    diff = rec["delta"]
    claimed = rec["list"]
    if diff == 0:
        print(f"✅ 對帳一致：counts.掃描={claimed}，真實={args.true_count}")
    else:
        print(f"⚠️ {rec['reason']}")

    # 寫入候選檔 needs_review
    if diff != 0 and args.apply:
        doc.setdefault("needs_review", [])
        if rec["reason"] not in doc["needs_review"]:
            doc["needs_review"].append(rec["reason"])
        with open(args.file, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print(f"OK 已寫入候選檔 needs_review：{args.file}")

    # 若指定了 state-file 與 checkpoint，寫入正式 state
    if args.state_file and args.checkpoint:
        try:
            import s2_state
            st = s2_state.load(args.state_file)
            log = st["_top"].setdefault("reconcile_log", {})
            entry_log = log.setdefault(args.checkpoint, {})
            entry_log[site] = rec
            s2_state.save(st, args.state_file)
            print(f"OK 已將 {site} 對帳紀錄寫入狀態檔 {args.state_file}（{args.checkpoint}）")
        except Exception as e:
            print(f"⚠️ 寫入狀態檔 reconcile_log 失敗：{e}", file=sys.stderr)

    if diff != 0 and not args.apply:
        print("（未加 --apply，候選檔未寫入——記得處理，不要放著）")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
