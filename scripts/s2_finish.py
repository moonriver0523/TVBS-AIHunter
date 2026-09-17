#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2 五站收工留痕與對帳整合 (s2-reconcile/v1)。

收工時統一協調 RT/AP/NS/ENEX/ABC 五站對帳留痕，寫入 state["_top"]["reconcile_log"]。
支援明確站台不可用 (--unavailable) 與未排程 (--not-scheduled) 例外。
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import s2_audit
import s2_platform_reconcile
import s2_reconcile
import s2_state

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def find_checkpoint_snapshot(scratch_dir: str | None, station: str, checkpoint: str) -> str | None:
    """尋找檔名中明確帶有 checkpoint（如 HHMM）的快照檔。不可只取最新修改！"""
    if not scratch_dir or not os.path.isdir(scratch_dir):
        return None
    hhmm = checkpoint.split("-")[-1]
    st = station.lower()
    candidates = [
        os.path.join(scratch_dir, f"_audit_{st}_{hhmm}.txt"),
        os.path.join(scratch_dir, f"{st}_list_{hhmm}.json"),
        os.path.join(scratch_dir, f"_{st}_list_{hhmm}.json"),
        os.path.join(scratch_dir, f"{st}_timeline_{hhmm}.txt"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    for pat in (f"_audit_{st}_*{hhmm}*.txt", f"{st}_list_*{hhmm}*.json", f"_{st}_list_*{hhmm}*.json"):
        hits = [h for h in glob.glob(os.path.join(scratch_dir, pat)) if os.path.isfile(h)]
        if hits:
            return hits[0]
    return None


def run_finish(args: argparse.Namespace) -> int:
    cp = args.checkpoint
    mmdd = cp.split("-")[0]
    now_ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")

    state_file = args.state_file or s2_state.default_file()
    if not os.path.isfile(state_file):
        print(f"ERROR: 找不到狀態檔 {state_file}", file=sys.stderr)
        return 2

    st = s2_state.load(state_file)

    # 解析 unavailable 與 not-scheduled
    unavail = {}
    for item in args.unavailable or []:
        site, sep, reason = item.partition("=")
        unavail[site.strip().upper()] = reason.strip() if sep else "站台不可用"

    not_sched = {s.strip().upper() for s in (args.not_scheduled or [])}

    site_records = {}

    # 1. 處理三站：RT, AP, NS
    station_opt = {
        "RT": args.rt_list,
        "AP": args.ap_list,
        "NS": args.ns_list,
    }

    for site in ("RT", "AP", "NS"):
        if site in unavail:
            site_records[site] = s2_reconcile.make_record(
                site, s2_reconcile.STATUS_NEEDS_REVIEW,
                reason_code="STATION_UNAVAILABLE",
                reason=unavail[site],
                ts=now_ts,
            )
            continue
        if site in not_sched:
            site_records[site] = s2_reconcile.make_record(
                site, s2_reconcile.STATUS_NOT_SCHEDULED,
                reason_code="NOT_SCHEDULED",
                reason=f"本輪固定掃帶未啟用 {site}",
                ts=now_ts,
            )
            continue

        snap_path = station_opt[site] or find_checkpoint_snapshot(args.scratch, site, cp)
        if snap_path and os.path.isfile(snap_path):
            try:
                r = s2_audit.reconcile(st, mmdd, snap_path, site)
                if r:
                    status = s2_reconcile.STATUS_OK if r.get("missing", 0) == 0 else s2_reconcile.STATUS_NEEDS_REVIEW
                    r_code = None if status == s2_reconcile.STATUS_OK else "COUNT_MISMATCH"
                    r_reason = None if status == s2_reconcile.STATUS_OK else f"窗內漏收 {r.get('missing')} 則"
                    site_records[site] = s2_reconcile.make_record(
                        site, status,
                        evidence_path=snap_path,
                        list_count=r.get("list"),
                        got_count=r.get("got"),
                        missing=r.get("missing"),
                        missing_ids=r.get("missing_ids"),
                        reason_code=r_code,
                        reason=r_reason,
                        extra={"cross_day": r.get("cross_day", [])},
                        ts=now_ts,
                    )
                else:
                    site_records[site] = s2_reconcile.make_record(
                        site, s2_reconcile.STATUS_MISSING_EVIDENCE,
                        reason_code="RECONCILE_FAILED",
                        reason=f"{site} 清單對帳解析無結果",
                        evidence_path=snap_path,
                        ts=now_ts,
                    )
            except Exception as exc:
                site_records[site] = s2_reconcile.make_record(
                    site, s2_reconcile.STATUS_NEEDS_REVIEW,
                    reason_code="RECONCILE_ERROR",
                    reason=f"對帳計算異常：{exc}",
                    evidence_path=snap_path,
                    ts=now_ts,
                )
        else:
            site_records[site] = s2_reconcile.make_record(
                site, s2_reconcile.STATUS_MISSING_EVIDENCE,
                reason_code="MISSING_EVIDENCE",
                reason=f"找不到 {site} 本輪清單快照（未提供亦無符合 checkpoint 之檔案）",
                ts=now_ts,
            )

    # 2. 處理平台兩站：ENEX, ABC
    platform_info = {
        "ENEX": (args.enex_candidate, args.enex_true_count),
        "ABC": (args.abc_candidate, args.abc_true_count),
    }

    for site in ("ENEX", "ABC"):
        if site in unavail:
            site_records[site] = s2_reconcile.make_record(
                site, s2_reconcile.STATUS_NEEDS_REVIEW,
                reason_code="STATION_UNAVAILABLE",
                reason=unavail[site],
                ts=now_ts,
            )
            continue
        if site in not_sched:
            site_records[site] = s2_reconcile.make_record(
                site, s2_reconcile.STATUS_NOT_SCHEDULED,
                reason_code="NOT_SCHEDULED",
                reason=f"本輪固定掃帶未啟用 {site}",
                ts=now_ts,
            )
            continue

        cand_file, true_cnt = platform_info[site]
        if cand_file and os.path.isfile(cand_file) and true_cnt is not None:
            try:
                with open(cand_file, encoding="utf-8-sig") as f:
                    cand_doc = json.load(f)
                rec = s2_platform_reconcile.reconcile_candidate(cand_doc, true_cnt, site)
                rec["evidence_path"] = str(cand_file)
                rec["ts"] = now_ts
                site_records[site] = rec
            except Exception as exc:
                site_records[site] = s2_reconcile.make_record(
                    site, s2_reconcile.STATUS_NEEDS_REVIEW,
                    reason_code="RECONCILE_ERROR",
                    reason=f"平台對帳計算異常：{exc}",
                    evidence_path=cand_file,
                    ts=now_ts,
                )
        else:
            site_records[site] = s2_reconcile.make_record(
                site, s2_reconcile.STATUS_MISSING_EVIDENCE,
                reason_code="MISSING_EVIDENCE",
                reason=f"缺少 {site} 候選檔或真實筆數 true_count",
                ts=now_ts,
            )

    # 3. 寫回 state["_top"]["reconcile_log"][checkpoint]
    top = st.setdefault("_top", {})
    rlog = top.setdefault("reconcile_log", {})
    container = {
        "_schema": s2_reconcile.RECONCILE_SCHEMA,
        "finished_at": now_ts,
    }
    for site in s2_reconcile.SITE_ORDER:
        container[site] = site_records[site]

    rlog[cp] = container
    s2_state.save(st, state_file)

    # 4. 判斷離開碼
    has_missing = any(site_records[s]["status"] == s2_reconcile.STATUS_MISSING_EVIDENCE
                      for s in s2_reconcile.SITE_ORDER)

    for site in s2_reconcile.SITE_ORDER:
        rec = site_records[site]
        stt = rec["status"]
        if stt == s2_reconcile.STATUS_OK:
            print(f"  [OK] {site}: list={rec.get('list')}, got={rec.get('got')}, missing={rec.get('missing')}")
        elif stt == s2_reconcile.STATUS_NEEDS_REVIEW:
            print(f"  [NEEDS-REVIEW] {site}: {rec.get('reason')} ({rec.get('reason_code')})")
        elif stt == s2_reconcile.STATUS_NOT_SCHEDULED:
            print(f"  [NOT-SCHEDULED] {site}: 未排程")
        else:
            print(f"  [MISSING-EVIDENCE] {site}: {rec.get('reason')}")

    if has_missing:
        missing_sites = [s for s in s2_reconcile.SITE_ORDER
                         if site_records[s]["status"] == s2_reconcile.STATUS_MISSING_EVIDENCE]
        print(f"⚠️ 五站收工對帳未完成（缺證據站別：{'／'.join(missing_sites)}），請補充快照或標記 --unavailable / --not-scheduled 後重跑",
              file=sys.stderr)
        return 1

    print(f"✅ 五站收工對帳留痕完成（checkpoint={cp}，五站全數已留痕）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="S2 五站收工留痕與對帳整合 (s2-reconcile/v1)")
    ap.add_argument("--checkpoint", required=True, help="本輪 checkpoint，例如 0917-1200")
    ap.add_argument("--state-file", default=None, help="狀態檔路徑（省略則自動取最新狀態檔）")
    ap.add_argument("--scratch", default=None, help="本輪暫存資料夾路徑")
    ap.add_argument("--rt-list", help="RT 清單快照路徑")
    ap.add_argument("--ap-list", help="AP 清單快照路徑")
    ap.add_argument("--ns-list", help="NS 清單快照路徑")
    ap.add_argument("--enex-candidate", help="ENEX 候選檔路徑")
    ap.add_argument("--enex-true-count", type=int, help="ENEX 健康檢查真實筆數")
    ap.add_argument("--abc-candidate", help="ABC 候選檔路徑")
    ap.add_argument("--abc-true-count", type=int, help="ABC 健康檢查真實筆數")
    ap.add_argument("--not-scheduled", action="append", default=[],
                    help="明確未排程站台（可多次指定，如 --not-scheduled ENEX --not-scheduled ABC）")
    ap.add_argument("--unavailable", action="append", default=[],
                    help="明確站台不可用（如 --unavailable 'NS=登入逾時，無法取得清單'）")
    args = ap.parse_args()
    return run_finish(args)


if __name__ == "__main__":
    sys.exit(main())
