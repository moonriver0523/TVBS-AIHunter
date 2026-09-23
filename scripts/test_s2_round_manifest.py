import sys
import tempfile
import unittest
import uuid
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import s2_round_manifest as rm


class RoundManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "round.json"
        self.state = self.root / "state.json"
        self.state.write_text('{"items": [], "reconcile_log": {}}', encoding="utf-8")
        self.run_id = str(uuid.uuid4())
        manifest = rm.new_manifest(
            "0923-1200",
            self.run_id,
            [
                {"id": "core", "sites": ["NS", "AP", "RT"]},
                {"id": "platform", "sites": ["ENEX", "ABC"]},
            ],
            state_file=str(self.state),
        )
        rm.write_manifest(self.path, manifest)

    def tearDown(self):
        self.temp.cleanup()

    def _finish(self, session_id):
        log = self.root / f"{session_id}.jsonl"
        _, attempt = rm.start_session(self.path, session_id, pid=123)
        if session_id == "core":
            state = {
                "items": [],
                "reconcile_log": {"0923-1200": {
                    site: {"list": 0, "got": 0, "ts": "2026-09-23T12:01:00+08:00"}
                    for site in ("NS", "AP", "RT")
                }},
            }
            self.state.write_text(__import__('json').dumps(state), encoding="utf-8")
            tool_rows = []
        else:
            tool_rows = [
                {"type": "assistant", "message": {"content": [{
                    "type": "tool_use", "input": {"command":
                    "python s2_platform_extract.py enex --file x"}}]}},
                {"type": "assistant", "message": {"content": [{
                    "type": "tool_use", "input": {"command":
                    "python s2_platform_extract.py abc --file y"}}]}},
            ]
        rows = tool_rows + [{"type": "result", "session_id": f"sid-{session_id}",
                             "total_cost_usd": 1.25, "usage": {"output_tokens": 5}}]
        log.write_text("\n".join(__import__('json').dumps(row) for row in rows) + "\n",
                       encoding="utf-8")
        return rm.finish_session(
            self.path, session_id, attempt, exit_code=0, log_path=log
        )

    def test_second_session_cannot_start_early(self):
        with self.assertRaises(rm.ManifestIncompleteError):
            rm.start_session(self.path, "platform")

    def test_nonzero_exit_never_counts_as_complete(self):
        log = self.root / "core.jsonl"
        log.write_text("failed\n", encoding="utf-8")
        _, attempt = rm.start_session(self.path, "core")
        manifest = rm.finish_session(
            self.path, "core", attempt, exit_code=1, log_path=log
        )
        self.assertEqual("failed", manifest["sessions"][0]["status"])
        with self.assertRaises(rm.ManifestIncompleteError):
            rm.assert_complete(manifest)

    def test_empty_or_missing_log_never_counts_as_complete(self):
        _, attempt = rm.start_session(self.path, "core")
        manifest = rm.finish_session(
            self.path, "core", attempt, exit_code=0,
            log_path=self.root / "missing.jsonl",
        )
        self.assertEqual("failed", manifest["status"])

    def test_retry_after_failure_is_recorded(self):
        missing = self.root / "missing.jsonl"
        _, first = rm.start_session(self.path, "core")
        rm.finish_session(self.path, "core", first, exit_code=1, log_path=missing)
        self._finish("core")
        manifest = rm.load_manifest(self.path)
        self.assertEqual(2, len(manifest["sessions"][0]["attempts"]))
        self.assertEqual("completed", manifest["sessions"][0]["status"])

    def test_exit_zero_without_site_receipt_fails_closed(self):
        log = self.root / "core-no-evidence.jsonl"
        log.write_text('{"type":"result","session_id":"sid"}\n', encoding="utf-8")
        _, attempt = rm.start_session(self.path, "core")
        manifest = rm.finish_session(
            self.path, "core", attempt, exit_code=0, log_path=log
        )
        row = manifest["sessions"][0]["attempts"][-1]
        self.assertEqual("failed", row["receipt"]["status"])
        self.assertEqual(["NS", "AP", "RT"], row["receipt"]["missing_sites"])

    def test_zero_item_core_round_passes_when_all_reconcile_receipts_advance(self):
        manifest = self._finish("core")
        attempt = manifest["sessions"][0]["attempts"][-1]
        self.assertEqual("completed", attempt["status"])
        self.assertTrue(all(
            "reconcile_updated" in attempt["receipt"]["sites"][site]["evidence"]
            for site in ("NS", "AP", "RT")
        ))

    def test_platform_receipt_accepts_operational_trace_when_no_new_items(self):
        self._finish("core")
        manifest = self._finish("platform")
        attempt = manifest["sessions"][1]["attempts"][-1]
        self.assertEqual("verified", attempt["receipt"]["status"])
        self.assertEqual("sid-platform", attempt["transcript_session_id"])
        self.assertEqual(1.25, attempt["total_cost_usd"])

    def test_prepare_resume_skips_completed_and_resets_dead_running_attempt(self):
        self._finish("core")
        rm.start_session(self.path, "platform", pid=999999)
        with mock.patch.object(rm, "_pid_alive", return_value=False):
            manifest = rm.prepare_resume(self.path)
        self.assertEqual("completed", manifest["sessions"][0]["status"])
        self.assertEqual("failed", manifest["sessions"][1]["status"])
        self.assertIn("stale", manifest["sessions"][1]["attempts"][-1]["error"])

    def test_prepare_resume_refuses_live_pid_without_force(self):
        rm.start_session(self.path, "core", pid=123)
        with mock.patch.object(rm, "_pid_alive", return_value=True):
            with self.assertRaises(rm.ManifestError):
                rm.prepare_resume(self.path)
            manifest = rm.prepare_resume(self.path, force=True)
        self.assertEqual("failed", manifest["sessions"][0]["status"])

    def test_prepare_resume_recovers_stale_finalization_without_rerunning_sessions(self):
        self._finish("core")
        self._finish("platform")
        rm.start_finalization(self.path, pid=999999)
        with mock.patch.object(rm, "_pid_alive", return_value=False):
            manifest = rm.prepare_resume(self.path)
        self.assertEqual("ready_to_finalize", manifest["status"])
        self.assertEqual("failed", manifest["finalization"]["status"])
        self.assertEqual(["completed", "completed"],
                         [row["status"] for row in manifest["sessions"]])

    def test_finalization_is_blocked_until_every_session_completes(self):
        self._finish("core")
        with self.assertRaises(rm.ManifestIncompleteError):
            rm.start_finalization(self.path)

    def test_happy_path_requires_render_artifact(self):
        self._finish("core")
        manifest = self._finish("platform")
        self.assertEqual("ready_to_finalize", manifest["status"])
        rm.assert_complete(manifest)
        rm.start_finalization(self.path)
        output = self.root / "handover.txt"
        output.write_text("rendered\n", encoding="utf-8")
        manifest = rm.finish_finalization(
            self.path, exit_code=0, artifacts=[output]
        )
        self.assertEqual("finalized", manifest["status"])
        self.assertTrue(manifest["finalization"]["artifacts"][0]["exists"])

    def test_render_failure_keeps_round_failed(self):
        self._finish("core")
        self._finish("platform")
        rm.start_finalization(self.path)
        manifest = rm.finish_finalization(
            self.path, exit_code=1, artifacts=[self.root / "missing.txt"]
        )
        self.assertEqual("failed", manifest["status"])
        self.assertEqual("failed", manifest["finalization"]["status"])

    def test_atomic_writer_leaves_no_temp_files(self):
        manifest = rm.load_manifest(self.path)
        rm.write_manifest(self.path, manifest)
        self.assertEqual([], list(self.root.glob(".round.json.*.tmp")))

    def test_rejects_non_uuid4_run_id(self):
        with self.assertRaises(rm.ManifestError):
            rm.new_manifest(
                "0923-1200", "not-a-uuid",
                [{"id": "core", "sites": ["NS"]}],
            )


if __name__ == "__main__":
    unittest.main()
