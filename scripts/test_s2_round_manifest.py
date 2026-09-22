import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import s2_round_manifest as rm


class RoundManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "round.json"
        self.run_id = str(uuid.uuid4())
        manifest = rm.new_manifest(
            "0923-1200",
            self.run_id,
            [
                {"id": "core", "sites": ["NS", "AP", "RT"]},
                {"id": "platform", "sites": ["ENEX", "ABC"]},
            ],
        )
        rm.write_manifest(self.path, manifest)

    def tearDown(self):
        self.temp.cleanup()

    def _finish(self, session_id):
        log = self.root / f"{session_id}.jsonl"
        log.write_text('{"type":"result"}\n', encoding="utf-8")
        _, attempt = rm.start_session(self.path, session_id, pid=123)
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
