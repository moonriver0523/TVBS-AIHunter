# -*- coding: utf-8 -*-
"""D23 Phase 4：cursor transaction、故障恢復與按站鎖。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s2_youtube_bridge as bridge  # noqa: E402
from test_s2_youtube_bridge_finalize import READY, decisions, manifest  # noqa: E402


def report(name, passed, detail=""):
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return passed


def cursor(revision=4):
    return {"schema_version": 1, "revision": revision, "sites": {
        "CNA": {"last_success_checkpoint": "0920-0100",
                 "last_complete_end_utc": "2026-09-20T01:00:00Z",
                 "deferred_video_ids": [], "recent_video_ids": []},
        "YNA": {"last_success_checkpoint": "0920-0100",
                 "last_complete_end_utc": "2026-09-20T01:00:00Z",
                 "deferred_video_ids": [], "recent_video_ids": []},
    }}


def test_advance_cursor_keeps_deferred_and_moves_only_after_complete_manifest():
    current = cursor()
    current["sites"]["CNA"]["deferred_video_ids"] = ["old-deferred"]
    m = manifest(
        site="CNA",
        items=[dict(READY, id="CNA-AbCd_ef-123", site="CNA",
                    video_id="AbCd_ef-123", platform={"site": "CNA"})],
        deferred=[{"video_id": "CnaVid_00-1", "reason": "caption", "id": "CNA-CnaVid_00-1"}],
        counts={"window_total": 2, "ready": 1, "skipped": 0,
                "dropped": 0, "deferred": 1, "accounted": 2},
        collect_started_at_utc="2026-09-20T15:00:00Z",
    )
    next_cursor = bridge.advance_cursor(current, m)
    assert next_cursor["revision"] == 4
    assert next_cursor["sites"]["CNA"]["last_success_checkpoint"] == "0920-0430"
    assert next_cursor["sites"]["CNA"]["last_complete_end_utc"] == "2026-09-20T15:00:00Z"
    assert set(next_cursor["sites"]["CNA"]["deferred_video_ids"]) == {"old-deferred", "CnaVid_00-1"}
    assert "AbCd_ef-123" in next_cursor["sites"]["CNA"]["recent_video_ids"]


def test_cursor_save_is_atomic_and_rejects_stale_revision():
    with tempfile.TemporaryDirectory(prefix="d23-cursor-") as td:
        path = os.path.join(td, "s2-youtube-cursors.json")
        bridge.save_cursor_atomic(path, cursor(revision=0), expected_revision=0)
        saved = bridge.load_cursor(path)
        assert saved["revision"] == 1
        try:
            bridge.save_cursor_atomic(path, cursor(revision=0), expected_revision=0)
        except bridge.CursorConflict:
            pass
        else:
            raise AssertionError("stale cursor revision must be rejected")
        assert bridge.load_cursor(path)["revision"] == 1


def test_site_locks_are_exclusive_per_site_and_release_on_exit():
    with tempfile.TemporaryDirectory(prefix="d23-lock-") as td:
        cna_lock = os.path.join(td, "s2-youtube-CNA.lock")
        yna_lock = os.path.join(td, "s2-youtube-YNA.lock")
        with bridge.site_lock(cna_lock, "CNA"):
            assert os.path.exists(cna_lock)
            try:
                with bridge.site_lock(cna_lock, "CNA"):
                    raise AssertionError("unreachable")
            except bridge.LockBusy:
                pass
            with bridge.site_lock(yna_lock, "YNA"):
                assert os.path.exists(yna_lock)
        assert not os.path.exists(cna_lock)
        assert not os.path.exists(yna_lock)


def test_add_batch_failure_does_not_advance_cursor():
    with tempfile.TemporaryDirectory(prefix="d23-cursor-failure-") as td:
        manifest_path = os.path.join(td, "manifest.json")
        decision_path = os.path.join(td, "decisions.json")
        out_path = os.path.join(td, "batch.json")
        cursor_path = os.path.join(td, "s2-youtube-cursors.json")
        bad_state_path = os.path.join(td, "state-directory")
        os.mkdir(bad_state_path)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest(cursor_revision=1), f, ensure_ascii=False)
        with open(decision_path, "w", encoding="utf-8") as f:
            json.dump(decisions(), f, ensure_ascii=False)
        bridge.save_cursor_atomic(cursor_path, cursor(revision=0), expected_revision=0)
        before = bridge.load_cursor(cursor_path)
        result = subprocess.run([
            sys.executable, os.path.join(HERE, "s2_youtube_bridge.py"), "finalize",
            "--manifest", manifest_path, "--entries", decision_path, "--out", out_path,
            "--apply", "--file", bad_state_path, "--cursor", cursor_path,
            "--in-round", "--youtube-lock", os.path.join(td, "s2-youtube-YNA.lock"),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert result.returncode != 0
        assert bridge.load_cursor(cursor_path) == before
        assert not os.path.exists(os.path.join(td, "s2-youtube-YNA.lock"))


def test_cursor_write_failure_is_recoverable_by_idempotent_retry():
    with tempfile.TemporaryDirectory(prefix="d23-cursor-retry-") as td:
        manifest_path = os.path.join(td, "manifest.json")
        decision_path = os.path.join(td, "decisions.json")
        first_out = os.path.join(td, "batch-first.json")
        retry_out = os.path.join(td, "batch-retry.json")
        state_path = os.path.join(td, "0920-s2-state.json")
        registry_path = os.path.join(td, "registry.json")
        cursor_path = os.path.join(td, "s2-youtube-cursors.json")
        lock_path = os.path.join(td, "s2-youtube-YNA.lock")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest(), f, ensure_ascii=False)
        with open(decision_path, "w", encoding="utf-8") as f:
            json.dump(decisions(), f, ensure_ascii=False)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"date": "0920", "checkpoint": "0920-0430", "items": []}, f)
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump({"topics": [{"name": "韓聯測試", "big": "國際", "charter": "既有"}]}, f,
                      ensure_ascii=False)
        bridge.save_cursor_atomic(cursor_path, cursor(revision=0), expected_revision=0)
        before = bridge.load_cursor(cursor_path)

        args = bridge.build_parser().parse_args([
            "finalize", "--manifest", manifest_path, "--entries", decision_path,
            "--out", first_out, "--apply", "--file", state_path,
            "--registry", registry_path, "--cursor", cursor_path,
            "--in-round", "--youtube-lock", lock_path,
        ])
        original_save = bridge.save_cursor_atomic
        bridge.save_cursor_atomic = lambda *a, **k: (_ for _ in ()).throw(
            bridge.CursorConflict("simulated cursor write failure")
        )
        try:
            try:
                bridge._finalize_command(args)
            except bridge.CursorConflict:
                pass
            else:
                raise AssertionError("simulated cursor write failure must surface")
        finally:
            bridge.save_cursor_atomic = original_save
        assert bridge.load_cursor(cursor_path) == before
        assert not os.path.exists(lock_path)
        with open(state_path, encoding="utf-8-sig") as f:
            state = json.load(f)
        assert sum(row.get("id") == READY["id"] for row in state["items"]) == 1

        retried = subprocess.run([
            sys.executable, os.path.join(HERE, "s2_youtube_bridge.py"), "finalize",
            "--manifest", manifest_path, "--entries", decision_path, "--out", retry_out,
            "--apply", "--file", state_path, "--registry", registry_path,
            "--cursor", cursor_path, "--in-round", "--youtube-lock", lock_path,
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert retried.returncode == 0, (retried.stdout, retried.stderr)
        assert bridge.load_cursor(cursor_path)["revision"] == before["revision"] + 1
        with open(state_path, encoding="utf-8-sig") as f:
            state = json.load(f)
        assert sum(row.get("id") == READY["id"] for row in state["items"]) == 1


def test_cli_apply_rejects_existing_site_lock_immediately():
    with tempfile.TemporaryDirectory(prefix="d23-lock-cli-") as td:
        manifest_path = os.path.join(td, "manifest.json")
        decision_path = os.path.join(td, "decisions.json")
        out_path = os.path.join(td, "batch.json")
        state_path = os.path.join(td, "0920-s2-state.json")
        registry_path = os.path.join(td, "registry.json")
        cursor_path = os.path.join(td, "s2-youtube-cursors.json")
        lock_path = os.path.join(td, "s2-youtube-YNA.lock")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest(), f, ensure_ascii=False)
        with open(decision_path, "w", encoding="utf-8") as f:
            json.dump(decisions(), f, ensure_ascii=False)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"date": "0920", "checkpoint": "0920-0430", "items": []}, f)
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump({"topics": [{"name": "韓聯測試", "big": "國際", "charter": "既有"}]}, f,
                      ensure_ascii=False)
        bridge.save_cursor_atomic(cursor_path, cursor(revision=0), expected_revision=0)
        before = bridge.load_cursor(cursor_path)
        with open(lock_path, "w", encoding="ascii") as f:
            f.write("owner=first\n")
        result = subprocess.run([
            sys.executable, os.path.join(HERE, "s2_youtube_bridge.py"), "finalize",
            "--manifest", manifest_path, "--entries", decision_path, "--out", out_path,
            "--apply", "--file", state_path, "--registry", registry_path,
            "--cursor", cursor_path, "--in-round", "--youtube-lock", lock_path,
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert result.returncode != 0
        assert not os.path.exists(out_path)
        assert os.path.exists(lock_path)
        assert bridge.load_cursor(cursor_path) == before


def main():
    tests = [test_advance_cursor_keeps_deferred_and_moves_only_after_complete_manifest,
             test_cursor_save_is_atomic_and_rejects_stale_revision,
             test_site_locks_are_exclusive_per_site_and_release_on_exit,
             test_add_batch_failure_does_not_advance_cursor,
             test_cursor_write_failure_is_recoverable_by_idempotent_retry,
             test_cli_apply_rejects_existing_site_lock_immediately]
    ok = True
    for test in tests:
        try:
            test()
            ok &= report(test.__name__, True)
        except Exception as exc:
            ok &= report(test.__name__, False, repr(exc))
    print("ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
