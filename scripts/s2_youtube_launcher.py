# -*- coding: utf-8 -*-
"""D23 scheduled-round command planner (Phase 5 dry-run only).

This module describes the future CNA → YNA tail of an S2 round.  It never creates
directories, invokes the bridge, opens state, or performs network access.  Until
the Phase 6 hard gates are explicitly cleared, the CLI requires ``--dry-run``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import s2_material_schema as schema
import s2_youtube_bridge as bridge


BRIDGE_SCRIPT = "scripts/s2_youtube_bridge.py"


def scheduled_sites(checkpoint: str) -> list[str]:
    """Return the fixed D23 tail order, or no sites for a skipped checkpoint."""
    if schema.CHECKPOINT_RE.fullmatch(str(checkpoint).strip()) is None:
        raise ValueError(f"checkpoint 須為 MMDD-HHMM：{checkpoint!r}")
    return [] if bridge.checkpoint_is_skipped(checkpoint) else ["CNA", "YNA"]


def _artifact(out_dir: str, site: str, kind: str, checkpoint: str) -> str:
    return os.path.join(out_dir, f"{site.lower()}_youtube_{kind}_{checkpoint[-4:]}.json")


def build_dry_run_plan(*, checkpoint: str, state_path: str, cursor_path: str,
                       out_dir: str) -> dict[str, Any]:
    """Build command descriptions without touching any of the supplied paths."""
    sites = scheduled_sites(checkpoint)
    if not sites:
        return {
            "status": "skipped",
            "checkpoint": checkpoint,
            "reason": "本輪不掃 CNA／YNA（D23）",
            "sites": [],
        }

    planned: list[dict[str, Any]] = []
    for site in sites:
        manifest = _artifact(out_dir, site, "manifest", checkpoint)
        entries = _artifact(out_dir, site, "entries", checkpoint)
        batch = _artifact(out_dir, site, "batch", checkpoint)
        collect = [
            sys.executable, BRIDGE_SCRIPT, "collect",
            "--site", site.lower(), "--checkpoint", checkpoint,
            "--state", state_path, "--cursor", cursor_path, "--out", manifest,
        ]
        finalize = [
            sys.executable, BRIDGE_SCRIPT, "finalize",
            "--manifest", manifest, "--entries", entries, "--out", batch,
            "--apply", "--file", state_path, "--cursor", cursor_path,
            "--in-round",
        ]
        planned.append({"site": site, "collect": collect, "finalize": finalize})
    return {"status": "ready", "checkpoint": checkpoint, "sites": planned}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="D23 launcher planner（Phase 5 dry-run only）")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--cursor", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--dry-run", action="store_true",
                        help="只印 CNA→YNA 命令計畫；Phase 6 前必須帶此旗標")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.dry_run:
        print("ERROR: D23 Phase 5 launcher 只允許 --dry-run；尚未開放真實執行。",
              file=sys.stderr)
        return 2
    try:
        plan = build_dry_run_plan(
            checkpoint=args.checkpoint, state_path=args.state,
            cursor_path=args.cursor, out_dir=args.out_dir,
        )
    except (ValueError, bridge.BridgeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
