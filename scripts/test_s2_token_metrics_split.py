import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import s2_token_metrics as metrics


class SplitMetricsTests(unittest.TestCase):
    def test_manifest_aggregates_both_transcripts_and_costs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for sid, output, tool in (("core-id", 11, "Read"),
                                      ("platform-id", 7, "Bash")):
                row = {
                    "timestamp": "2026-09-23T10:00:00+00:00",
                    "message": {
                        "id": sid,
                        "usage": {"input_tokens": 3, "output_tokens": output,
                                  "cache_read_input_tokens": 5,
                                  "cache_creation_input_tokens": 2},
                        "content": [{"type": "tool_use", "name": tool, "input": {}}],
                    },
                }
                (root / f"{sid}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
            manifest = {
                "sessions": [
                    {"id": "core", "sites": ["NS", "AP", "RT"], "attempts": [{
                        "status": "completed", "transcript_session_id": "core-id",
                        "total_cost_usd": 1.25,
                    }]},
                    {"id": "platform", "sites": ["ENEX", "ABC"], "attempts": [{
                        "status": "completed", "transcript_session_id": "platform-id",
                        "total_cost_usd": 2.5,
                    }]},
                ],
            }
            manifest_path = root / "round.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = metrics.measure_manifest(manifest_path, root)

            self.assertEqual(2, result["requests"])
            self.assertEqual(2, result["tool_calls"])
            self.assertEqual(18, result["output_tokens"])
            self.assertEqual(3.75, result["total_cost_usd"])
            self.assertEqual(["core", "platform"],
                             [row["segment"] for row in result["segments"]])
            self.assertEqual(1, result["tool_calls_by_name"]["Read"])
            self.assertEqual(1, result["tool_calls_by_name"]["Bash（其他）"])

    def test_manifest_fails_instead_of_silently_omitting_a_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "round.json"
            path.write_text(json.dumps({"sessions": [{
                "id": "core", "attempts": [{"status": "completed"}],
            }]}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                metrics.measure_manifest(path, root)


if __name__ == "__main__":
    unittest.main()
