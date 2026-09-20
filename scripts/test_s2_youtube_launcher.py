# -*- coding: utf-8 -*-
"""D23 Phase 5：規則接線 launcher 的離線 dry-run contract。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s2_youtube_launcher as launcher  # noqa: E402


def test_round_sites_and_skip_policy():
    assert launcher.scheduled_sites("0920-0100") == []
    assert launcher.scheduled_sites("0920-2000") == []
    assert launcher.scheduled_sites("0920-0430") == ["CNA", "YNA"]
    assert launcher.scheduled_sites("0920-2200") == ["CNA", "YNA"]


def test_plan_is_cna_then_yna_and_only_describes_commands():
    plan = launcher.build_dry_run_plan(
        checkpoint="0920-0430",
        state_path=r"E:\sandbox\0920-s2-state.json",
        cursor_path=r"E:\sandbox\s2-youtube-cursors.json",
        out_dir=r"E:\sandbox\d23-out",
    )
    assert plan["status"] == "ready"
    assert [row["site"] for row in plan["sites"]] == ["CNA", "YNA"]
    assert all(row["collect"][0:3] == [sys.executable, "scripts/s2_youtube_bridge.py", "collect"]
               for row in plan["sites"])
    assert all("--apply" in row["finalize"] and "--in-round" in row["finalize"]
               for row in plan["sites"])
    assert all("--fixture-dir" not in row["collect"] for row in plan["sites"])


def test_cli_dry_run_does_not_touch_paths_or_call_external_bridge():
    with tempfile.TemporaryDirectory(prefix="d23-launcher-") as td:
        state = os.path.join(td, "missing-state.json")
        cursor = os.path.join(td, "missing-cursor.json")
        out_dir = os.path.join(td, "must-not-be-created")
        result = subprocess.run([
            sys.executable, os.path.join(HERE, "s2_youtube_launcher.py"),
            "--checkpoint", "0920-0100", "--state", state,
            "--cursor", cursor, "--out-dir", out_dir, "--dry-run",
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert not os.path.exists(out_dir)
        output = json.loads(result.stdout)
        assert output["status"] == "skipped"
        assert output["sites"] == []
        assert "api_key" not in result.stdout.lower()
        assert "yt-dlp" not in result.stdout.lower()


def main():
    tests = [test_round_sites_and_skip_policy,
             test_plan_is_cna_then_yna_and_only_describes_commands,
             test_cli_dry_run_does_not_touch_paths_or_call_external_bridge]
    ok = True
    for test in tests:
        try:
            test()
            print(f"[PASS] {test.__name__}")
        except Exception as exc:
            ok = False
            print(f"[FAIL] {test.__name__} — {exc!r}")
    print("ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
