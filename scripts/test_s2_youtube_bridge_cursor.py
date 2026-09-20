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


def test_manual_apply_without_in_round_is_rejected():
    """3.7（訂正版）：手動觸發一律不得 --apply，不論掃帶鎖是否存在。"""
    with tempfile.TemporaryDirectory(prefix="d23-manual-apply-") as td:
        manifest_path = os.path.join(td, "manifest.json")
        decision_path = os.path.join(td, "decisions.json")
        out_path = os.path.join(td, "batch.json")
        state_path = os.path.join(td, "0920-s2-state.json")
        cursor_path = os.path.join(td, "s2-youtube-cursors.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest(), f, ensure_ascii=False)
        with open(decision_path, "w", encoding="utf-8") as f:
            json.dump(decisions(), f, ensure_ascii=False)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"date": "0920", "checkpoint": "0920-0430", "items": []}, f)
        bridge.save_cursor_atomic(cursor_path, cursor(revision=0), expected_revision=0)
        result = subprocess.run([
            sys.executable, os.path.join(HERE, "s2_youtube_bridge.py"), "finalize",
            "--manifest", manifest_path, "--entries", decision_path, "--out", out_path,
            "--apply", "--file", state_path, "--cursor", cursor_path,
            # 刻意不帶 --in-round
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert result.returncode != 0
        assert not os.path.exists(out_path)
        with open(state_path, encoding="utf-8-sig") as f:
            state = json.load(f)
        assert state["items"] == []


def test_manual_mode_without_apply_only_produces_candidate_file():
    """手動觸發省略 --apply：只產候選 batch，不碰 state、不前進游標。"""
    with tempfile.TemporaryDirectory(prefix="d23-manual-candidate-") as td:
        manifest_path = os.path.join(td, "manifest.json")
        decision_path = os.path.join(td, "decisions.json")
        pending_dir = os.path.join(td, "_待整併")
        os.makedirs(pending_dir, exist_ok=True)
        out_path = os.path.join(pending_dir, "0920-YNA_CNA候選-CNA.json")
        cursor_path = os.path.join(td, "s2-youtube-cursors.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest(), f, ensure_ascii=False)
        with open(decision_path, "w", encoding="utf-8") as f:
            json.dump(decisions(), f, ensure_ascii=False)
        bridge.save_cursor_atomic(cursor_path, cursor(revision=0), expected_revision=0)
        before = bridge.load_cursor(cursor_path)
        result = subprocess.run([
            sys.executable, os.path.join(HERE, "s2_youtube_bridge.py"), "finalize",
            "--manifest", manifest_path, "--entries", decision_path, "--out", out_path,
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert os.path.exists(out_path)
        assert bridge.load_cursor(cursor_path) == before


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
            "--in-round",
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
            "--in-round",
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
            "--cursor", cursor_path, "--in-round",
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert retried.returncode == 0, (retried.stdout, retried.stderr)
        assert bridge.load_cursor(cursor_path)["revision"] == before["revision"] + 1
        with open(state_path, encoding="utf-8-sig") as f:
            state = json.load(f)
        assert sum(row.get("id") == READY["id"] for row in state["items"]) == 1


def test_in_round_apply_picks_up_pending_candidate_and_archives_it():
    """3.7：排定輪次 --in-round --apply 時，先掃 --pending-dir 把候選 batch 一併套用、
    成功後搬進 已整併/ 子目錄；候選檔內容單獨也要能通過去重（同 ID 不重複入庫）。
    """
    with tempfile.TemporaryDirectory(prefix="d23-pending-") as td:
        manifest_path = os.path.join(td, "manifest.json")
        decision_path = os.path.join(td, "decisions.json")
        out_path = os.path.join(td, "batch.json")
        state_path = os.path.join(td, "0920-s2-state.json")
        registry_path = os.path.join(td, "registry.json")
        cursor_path = os.path.join(td, "s2-youtube-cursors.json")
        pending_dir = os.path.join(td, "_待整併")
        os.makedirs(pending_dir, exist_ok=True)
        pending_path = os.path.join(pending_dir, "0920-YNA_CNA候選-CNA.json")

        pending_item = dict(READY, id="CNA-PendingVid1", site="CNA", video_id="PendingVid1",
                             platform=dict(READY["platform"], site="CNA", video_id="PendingVid1"))
        pending_manifest = manifest(site="CNA", items=[pending_item],
                                     counts={"window_total": 1, "ready": 1, "skipped": 0,
                                             "dropped": 0, "deferred": 0, "accounted": 1})
        pending_decisions = decisions(entry="CNA-PendingVid1 (韓聯社) ▎摘要。▎畫面：無。▎無BITE。▎01:35")
        pending_decisions["CNA-PendingVid1"] = pending_decisions.pop(READY["id"])
        pending_wrapper = bridge.finalize_manifest(pending_manifest, pending_decisions)
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(pending_wrapper, f, ensure_ascii=False)

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

        result = subprocess.run([
            sys.executable, os.path.join(HERE, "s2_youtube_bridge.py"), "finalize",
            "--manifest", manifest_path, "--entries", decision_path, "--out", out_path,
            "--apply", "--file", state_path, "--registry", registry_path,
            "--cursor", cursor_path, "--in-round", "--pending-dir", pending_dir,
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert result.returncode == 0, (result.stdout, result.stderr)

        with open(state_path, encoding="utf-8-sig") as f:
            state = json.load(f)
        ids = {row.get("id") for row in state["items"]}
        assert READY["id"] in ids
        assert "CNA-PendingVid1" in ids

        assert not os.path.exists(pending_path)
        archived = os.path.join(pending_dir, "已整併", "0920-YNA_CNA候選-CNA.json")
        assert os.path.exists(archived)


def test_in_round_apply_failure_keeps_pending_candidate_for_retry():
    """套用失敗時候選檔原樣保留，不歸檔、不清空，供下一輪重試。"""
    with tempfile.TemporaryDirectory(prefix="d23-pending-fail-") as td:
        manifest_path = os.path.join(td, "manifest.json")
        decision_path = os.path.join(td, "decisions.json")
        out_path = os.path.join(td, "batch.json")
        bad_state_path = os.path.join(td, "state-directory")
        os.mkdir(bad_state_path)
        cursor_path = os.path.join(td, "s2-youtube-cursors.json")
        pending_dir = os.path.join(td, "_待整併")
        os.makedirs(pending_dir, exist_ok=True)
        pending_path = os.path.join(pending_dir, "0920-YNA_CNA候選-CNA.json")
        pending_item = dict(READY, id="CNA-PendingVid2", site="CNA", video_id="PendingVid2",
                             platform=dict(READY["platform"], site="CNA", video_id="PendingVid2"))
        pending_manifest = manifest(site="CNA", items=[pending_item],
                                     counts={"window_total": 1, "ready": 1, "skipped": 0,
                                             "dropped": 0, "deferred": 0, "accounted": 1})
        pending_decisions = decisions(entry="CNA-PendingVid2 (韓聯社) ▎摘要。▎畫面：無。▎無BITE。▎01:35")
        pending_decisions["CNA-PendingVid2"] = pending_decisions.pop(READY["id"])
        pending_wrapper = bridge.finalize_manifest(pending_manifest, pending_decisions)
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(pending_wrapper, f, ensure_ascii=False)
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
            "--in-round", "--pending-dir", pending_dir,
        ], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert result.returncode != 0
        assert bridge.load_cursor(cursor_path) == before
        assert os.path.exists(pending_path)


def main():
    tests = [test_advance_cursor_keeps_deferred_and_moves_only_after_complete_manifest,
             test_cursor_save_is_atomic_and_rejects_stale_revision,
             test_manual_apply_without_in_round_is_rejected,
             test_manual_mode_without_apply_only_produces_candidate_file,
             test_add_batch_failure_does_not_advance_cursor,
             test_cursor_write_failure_is_recoverable_by_idempotent_retry,
             test_in_round_apply_picks_up_pending_candidate_and_archives_it,
             test_in_round_apply_failure_keeps_pending_candidate_for_retry]
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
