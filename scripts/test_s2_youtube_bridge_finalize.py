# -*- coding: utf-8 -*-
"""D23 Phase 3：finalize → add-batch wrapper contract and offline e2e."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s2_youtube_bridge as bridge  # noqa: E402


READY = {
    "id": "YNA-AbCd_ef-123",
    "site": "YNA",
    "video_id": "AbCd_ef-123",
    "published_at_utc": "2026-09-20T14:55:00Z",
    "title": "fixture",
    "description": "fixture",
    "duration_seconds": 95,
    "duration": "01:35",
    "src_text": "南韓政府今天表示",
    "platform": {
        "site": "YNA", "provider": "YouTube", "video_id": "AbCd_ef-123",
        "channel_id": "UCTHCOPwqNfZ0uiKOvFyhGwg",
        "url": "https://www.youtube.com/watch?v=AbCd_ef-123",
        "published_at_utc": "2026-09-20T14:55:00Z",
        "duration_seconds": 95,
        "caption": {"language": "zh-Hant", "kind": "auto-translated", "precision": "triage-only"},
    },
    "status": "ready",
}


def manifest(**extra):
    value = {
        "schema_version": 1, "status": "complete", "site": "YNA",
        "checkpoint": "0920-0430", "items": [dict(READY)],
        "collect_started_at_utc": "2026-09-20T15:00:00Z",
        "skipped": [], "dropped": [], "deferred": [],
        "counts": {"window_total": 1, "ready": 1, "skipped": 0,
                   "dropped": 0, "deferred": 0, "accounted": 1},
    }
    value.update(extra)
    return value


def decisions(entry=None, **extra):
    value = {"_new_topics": {}, READY["id"]: {
        "entry": entry or f"{READY['id']} (南韓) ▎摘要。▎畫面：無。▎無BITE。▎01:35",
        "category": {"大分類": "國際", "中主題": "韓聯測試"},
        "tc": {"T": ["社會"], "C": ["美國"]},
        "src_text": "人工不可信來源，不可覆寫 manifest",
        "platform": {"tampered": True},
    }}
    value.update(extra)
    return value


def report(name, passed, detail=""):
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return passed


def expect_error(callback, phrase):
    try:
        callback()
    except bridge.BridgeError as exc:
        assert phrase in str(exc), str(exc)
    else:
        raise AssertionError(f"expected BridgeError containing {phrase!r}")


def test_final_wrapper_uses_trusted_manifest_fields():
    wrapper = bridge.finalize_manifest(manifest(), decisions())
    assert wrapper["new_topics"] == {}
    assert len(wrapper["entries"]) == 1
    row = wrapper["entries"][0]
    assert row["id"] == READY["id"]
    assert row["source"] == "YNA"
    assert row["checkpoint"] == "0920-0430"
    assert row["status"] == "has_script"
    assert row["src_text"] == READY["src_text"]
    assert row["platform"] == READY["platform"]
    assert row["category"] == {"大分類": "國際", "中主題": "韓聯測試"}
    assert row["tc"] == {"T": ["社會"], "C": ["美國"]}
    assert "suggest" not in row
    assert wrapper["receipt"]["accounted"] == 1


def test_skip_and_new_topics_are_accounted():
    decision = {"_new_topics": {"韓聯測試": {"charter": "測試 charter", "big": "國際"}},
                READY["id"]: {"skip": "明確排除：非新聞"}}
    wrapper = bridge.finalize_manifest(manifest(), decision)
    assert wrapper["entries"] == []
    assert wrapper["new_topics"]["韓聯測試"]["charter"] == "測試 charter"
    assert wrapper["receipt"]["skipped"] == [{"id": READY["id"], "reason": "明確排除：非新聞"}]
    assert wrapper["receipt"]["accounted"] == 1


def test_missing_or_unknown_decision_is_blocking():
    expect_error(lambda: bridge.finalize_manifest(manifest(), {"_new_topics": {}}), READY["id"])
    expect_error(lambda: bridge.finalize_manifest(
        manifest(), decisions(**{"CNA-XyZ987_ab-c": {"skip": "錯 ID"}})
    ), "不在 manifest")


def test_manifest_preflight_blocks_dropped_bad_checkpoint_and_source_mismatch():
    expect_error(lambda: bridge.finalize_manifest(
        manifest(dropped=[{"video_id": "bad", "reason": "join"}]), decisions()
    ), "dropped")
    expect_error(lambda: bridge.finalize_manifest(
        manifest(checkpoint="0920-04:30"), decisions()
    ), "checkpoint")
    bad = dict(READY)
    bad["id"] = "CNA-AbCd_ef-123"
    expect_error(lambda: bridge.finalize_manifest(
        manifest(items=[bad]), decisions(**{"CNA-AbCd_ef-123": decisions()[READY["id"]]})
    ), "source")


def test_cli_apply_e2e_and_manual_scan_lock():
    with tempfile.TemporaryDirectory(prefix="d23-finalize-") as td:
        manifest_path = os.path.join(td, "manifest.json")
        decision_path = os.path.join(td, "decisions.json")
        out_path = os.path.join(td, "batch.json")
        state_path = os.path.join(td, "0920-s2-state.json")
        registry_path = os.path.join(td, "registry.json")
        scan_lock = os.path.join(td, ".s2-scan.lock")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest(), f, ensure_ascii=False)
        with open(decision_path, "w", encoding="utf-8") as f:
            json.dump(decisions(), f, ensure_ascii=False)
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"date": "0920", "checkpoint": "0920-0430", "items": []}, f)
        with open(registry_path, "w", encoding="utf-8") as f:
            json.dump({"topics": [{"name": "韓聯測試", "big": "國際", "charter": "既有"}]}, f,
                      ensure_ascii=False)
        with open(scan_lock, "w", encoding="utf-8") as f:
            f.write("busy")

        locked = subprocess.run([
            sys.executable, os.path.join(HERE, "s2_youtube_bridge.py"), "finalize",
            "--manifest", manifest_path, "--entries", decision_path, "--out", out_path,
            "--apply", "--file", state_path, "--registry", registry_path,
            "--scan-lock", scan_lock,
        ], capture_output=True, text=True, encoding="utf-8")
        assert locked.returncode != 0
        assert not os.path.exists(out_path)

        dry = subprocess.run([
            sys.executable, os.path.join(HERE, "s2_youtube_bridge.py"), "finalize",
            "--manifest", manifest_path, "--entries", decision_path, "--out", out_path,
        ], capture_output=True, text=True, encoding="utf-8")
        assert dry.returncode == 0
        assert os.path.exists(out_path)
        os.remove(out_path)

        applied = subprocess.run([
            sys.executable, os.path.join(HERE, "s2_youtube_bridge.py"), "finalize",
            "--manifest", manifest_path, "--entries", decision_path, "--out", out_path,
            "--apply", "--file", state_path, "--in-round", "--registry", registry_path,
            "--scan-lock", scan_lock,
        ], capture_output=True, text=True, encoding="utf-8")
        assert applied.returncode == 0, (applied.stdout, applied.stderr)
        with open(state_path, encoding="utf-8-sig") as f:
            state = json.load(f)
        stored = next(item for item in state["items"] if item["id"] == READY["id"])
        assert stored["source"] == "YNA"
        assert stored["src_text"] == READY["src_text"]
        assert stored["platform"] == READY["platform"]
        assert stored["category"] == {"大分類": "國際", "中主題": "韓聯測試"}


def main():
    tests = [test_final_wrapper_uses_trusted_manifest_fields,
             test_skip_and_new_topics_are_accounted,
             test_missing_or_unknown_decision_is_blocking,
             test_manifest_preflight_blocks_dropped_bad_checkpoint_and_source_mismatch,
             test_cli_apply_e2e_and_manual_scan_lock]
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
