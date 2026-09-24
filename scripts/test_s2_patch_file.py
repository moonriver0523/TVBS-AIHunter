#!/usr/bin/env python3
"""A43 patch schema v1 contract tests.

These tests exercise the file-backed public contract, not either caller's private
implementation.  CLI integration tests for the two rewrite-entry commands live in
their existing test modules.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

try:
    import s2_patch_file as patch_file
except ImportError:
    patch_file = None


def _write(path: Path, value) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PatchFileSchemaTests(unittest.TestCase):
    def setUp(self):
        if patch_file is None:
            self.fail("scripts.s2_patch_file is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_schema_v1_accepts_partial_fields_and_canonicalizes_ids(self):
        target = _write(self.tmp_path / "target.json", {"items": []})
        patch = _write(
            self.tmp_path / "patch.json",
            {
                "schema_version": 1,
                "site": "enex",
                "target_sha256": _sha(target),
                "changes": [
                    {"id": "ENEX1001", "set": {"entry": "new", "tc": "T1/C1"}},
                    {"id": "1002", "set": {"skip": "duplicate"}},
                ],
            },
        )

        doc = patch_file.load_patch(
            patch,
            expected_site="enex",
            canonicalize=lambda value: str(value).removeprefix("ENEX"),
            allowed_fields={"entry", "category", "tc", "skip"},
        )

        self.assertEqual([change.canonical_id for change in doc.changes], ["1001", "1002"])
        self.assertEqual(doc.changes[0].fields, ("entry", "tc"))
        self.assertEqual(doc.target_sha256, _sha(target))

    def test_schema_v1_rejects_wrong_site_unknown_fields_and_duplicate_ids(self):
        cases = [
            (lambda doc: doc.update(site="abc"), "站別"),
            (lambda doc: doc["changes"][0]["set"].update(src_text="forbidden"), "不可修改欄位"),
            (
                lambda doc: doc["changes"].append(
                    {"id": "1001", "set": {"entry": "duplicate canonical id"}}
                ),
                "重複",
            ),
            (lambda doc: doc.update(extra="unknown"), "未知欄位"),
        ]
        for index, (mutate, message) in enumerate(cases):
            with self.subTest(message=message):
                payload = {
                    "schema_version": 1,
                    "site": "enex",
                    "target_sha256": "a" * 64,
                    "changes": [{"id": "ENEX1001", "set": {"entry": "new"}}],
                }
                mutate(payload)
                patch = _write(self.tmp_path / f"patch-{index}.json", payload)
                with self.assertRaisesRegex(patch_file.PatchFileError, message):
                    patch_file.load_patch(
                        patch,
                        expected_site="enex",
                        canonicalize=lambda value: str(value).removeprefix("ENEX"),
                        allowed_fields={"entry", "category", "tc", "skip"},
                    )

    def test_target_sha_is_a_required_compare_before_write_precondition(self):
        target = _write(self.tmp_path / "target.json", {"value": "current"})
        original = target.read_bytes()

        with self.assertRaisesRegex(patch_file.PatchFileError, "stale"):
            patch_file.require_target_sha(target, "0" * 64)

        self.assertEqual(target.read_bytes(), original)

    def test_scaffold_is_empty_and_bound_to_exact_target_bytes(self):
        target = _write(self.tmp_path / "target.json", {"value": "current"})
        out = self.tmp_path / "repair.patch.json"

        patch_file.write_scaffold(out, site="rt", target=target)

        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {
            "schema_version": 1,
            "site": "rt",
            "target_sha256": _sha(target),
            "changes": [],
        })
        with self.assertRaisesRegex(patch_file.PatchFileError, "已存在"):
            patch_file.write_scaffold(out, site="rt", target=target)

    def test_atomic_write_interruption_preserves_original_and_cleans_temp(self):
        target = _write(self.tmp_path / "target.json", {"before": True})
        original = target.read_bytes()
        with mock.patch.object(patch_file.os, "replace", side_effect=OSError("injected")):
            with self.assertRaisesRegex(OSError, "injected"):
                patch_file.atomic_write_json(target, {"after": True})

        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(list(self.tmp_path.glob(".s2patch_*.json")), [])


class PlatformPatchCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp.name)
        self.script = Path(__file__).with_name("s2_platform_bridge.py")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(self.script), *map(str, args)],
            cwd=self.script.parents[1],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )

    def make_enex_target(self, stem="case"):
        skeleton = _write(
            self.tmp_path / f"{stem}_skeleton.json",
            [
                {"id": "ENEX1001", "source": "ENEX", "entry": "old one",
                 "category": "國際/舊題", "tc": "", "skip": "", "sb_count": 0},
                {"id": "ENEX1002", "source": "ENEX", "entry": "old two",
                 "category": "國際/舊題", "tc": "", "skip": "", "sb_count": 0},
            ],
        )
        entries = self.tmp_path / f"{stem}_entries.json"
        built = self.run_cli("build", "--skeleton", skeleton, "--out", entries)
        self.assertEqual(built.returncode, 0, built.stderr)
        return skeleton, entries

    def test_platform_scaffold_dry_run_and_multi_apply_preserve_unlisted_fields(self):
        skeleton = _write(
            self.tmp_path / "enex_skeleton.json",
            [
                {
                    "id": "ENEX1001",
                    "source": "ENEX",
                    "entry": "old one",
                    "category": "國際/舊題",
                    "tc": "T0/C0",
                    "skip": "",
                    "sb_count": 1,
                    "mechanical": "keep-me",
                },
                {
                    "id": "ENEX1002",
                    "source": "ENEX",
                    "entry": "old two",
                    "category": "國際/舊題",
                    "tc": "",
                    "skip": "",
                    "sb_count": 0,
                },
            ],
        )
        entries = self.tmp_path / "enex_entries.json"
        built = self.run_cli("build", "--skeleton", skeleton, "--out", entries)
        self.assertEqual(built.returncode, 0, built.stderr)
        patch = self.tmp_path / "enex.patch.json"

        initialized = self.run_cli(
            "rewrite-entry",
            "--site", "enex",
            "--skeleton", skeleton,
            "--entries", entries,
            "--init-patch", patch,
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        patch_payload = json.loads(patch.read_text(encoding="utf-8"))
        patch_payload["changes"] = [
            {"id": "1001", "set": {"entry": "new one", "tc": "T1/C1"}},
            {"id": "ENEX1002", "set": {"category": "國際/新題"}},
        ]
        _write(patch, patch_payload)
        before_skeleton = skeleton.read_bytes()
        before_entries = entries.read_bytes()

        preview = self.run_cli(
            "rewrite-entry",
            "--site", "enex",
            "--skeleton", skeleton,
            "--entries", entries,
            "--patch-file", patch,
            "--dry-run",
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("ENEX1001", preview.stderr)
        self.assertEqual(skeleton.read_bytes(), before_skeleton)
        self.assertEqual(entries.read_bytes(), before_entries)

        applied = self.run_cli(
            "rewrite-entry",
            "--site", "enex",
            "--skeleton", skeleton,
            "--entries", entries,
            "--patch-file", patch,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        rows = json.loads(skeleton.read_text(encoding="utf-8"))
        output = json.loads(entries.read_text(encoding="utf-8"))
        self.assertEqual(rows[0]["entry"], "new one")
        self.assertEqual(rows[0]["category"], "國際/舊題")
        self.assertEqual(rows[0]["mechanical"], "keep-me")
        self.assertEqual(output["ENEX1001"]["tc"], "T1/C1")
        self.assertEqual(output["ENEX1002"]["category"], "國際/新題")

    def test_platform_tc_survives_build_extract_and_merge(self):
        from s2_platform_extract import extract_enex
        from s2_platform_merge import build as merge_build

        entries = {
            "ENEX1001": {
                "raw_entry": "ENEX1001 (VO) ▎摘要。▎畫面：資料畫面。無BITE。",
                "category": "國際/測試題",
                "tc": "T1,T2/C1",
                "sb_count": 0,
            }
        }
        raw = [{
            "id": "ENEX1001",
            "desc": "sanitized source text",
            "url": "https://example.invalid/clip.mp4",
            "nlid": 1001,
            "partner": "fixture",
        }]

        items, skipped, dropped, gaps = extract_enex(
            raw, entries, duration_fn=lambda _url: 60
        )
        batch, _pairs, _misc = merge_build({
            "source": "ENEX",
            "checkpoint": "0924-1700",
            "items": [dict(items[0], first_seen_checkpoint="0924-1700")],
        })

        self.assertFalse(skipped)
        self.assertFalse(dropped)
        self.assertEqual(items[0]["tc"], "T1,T2/C1")
        self.assertEqual(batch[0]["tc"], "T1,T2/C1")

    def test_platform_rejects_invalid_patch_table_without_touching_either_output(self):
        cases = [
            ("wrong-site", lambda p: p.update(site="abc"), "站別"),
            (
                "duplicate-canonical",
                lambda p: p["changes"].append(
                    {"id": "1001", "set": {"entry": "duplicate"}}
                ),
                "重複",
            ),
            (
                "mechanical-field",
                lambda p: p["changes"][0]["set"].update(src_text="forbidden"),
                "不可修改欄位",
            ),
            ("stale-sha", lambda p: p.update(target_sha256="0" * 64), "stale"),
        ]
        for stem, mutate, expected in cases:
            with self.subTest(stem=stem):
                skeleton, entries = self.make_enex_target(stem)
                payload = {
                    "schema_version": 1,
                    "site": "enex",
                    "target_sha256": _sha(skeleton),
                    "changes": [{"id": "ENEX1001", "set": {"entry": "new"}}],
                }
                mutate(payload)
                patch = _write(self.tmp_path / f"{stem}.patch.json", payload)
                before = (skeleton.read_bytes(), entries.read_bytes())

                result = self.run_cli(
                    "rewrite-entry", "--site", "enex", "--skeleton", skeleton,
                    "--entries", entries, "--patch-file", patch,
                )

                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertEqual((skeleton.read_bytes(), entries.read_bytes()), before)

    def test_platform_second_replace_failure_rolls_back_first_output(self):
        import s2_platform_bridge as bridge

        skeleton, entries = self.make_enex_target("interrupt")
        patch = _write(
            self.tmp_path / "interrupt.patch.json",
            {
                "schema_version": 1,
                "site": "enex",
                "target_sha256": _sha(skeleton),
                "changes": [{"id": "1001", "set": {"entry": "new"}}],
            },
        )
        before = (skeleton.read_bytes(), entries.read_bytes())
        original_replace = bridge.os.replace
        calls = 0

        def fail_second_replace(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated second replace interruption")
            return original_replace(source, target)

        stderr = StringIO()
        with mock.patch.object(bridge.os, "replace", side_effect=fail_second_replace):
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                bridge.main([
                    "rewrite-entry", "--site", "enex", "--skeleton", str(skeleton),
                    "--entries", str(entries), "--patch-file", str(patch),
                ])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("未保留半套結果", stderr.getvalue())
        self.assertEqual((skeleton.read_bytes(), entries.read_bytes()), before)
        self.assertFalse(list(self.tmp_path.glob(".s2pb_*")))


class CorePatchCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp.name)
        self.script = Path(__file__).with_name("s2_batch_prep.py")

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(self.script), *map(str, args)],
            cwd=self.script.parents[1],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )

    def test_core_scaffold_dry_run_and_multi_apply_use_partial_set(self):
        entries = _write(
            self.tmp_path / "rt_entries_1700.json",
            {
                "RT1001": {
                    "entry": "RT1001 (VO) ▎舊摘要。▎畫面：資料畫面。無BITE。",
                    "category": "國際/舊題",
                    "tc": "T0/C0",
                    "fixture_note": "keep-me",
                },
                "RT1002": {
                    "entry": "RT1002 (VO) ▎第二則。▎畫面：資料畫面。無BITE。",
                    "category": "國際/舊題",
                    "tc": "",
                },
            },
        )
        patch = self.tmp_path / "rt.patch.json"
        initialized = self.run_cli(
            "rewrite-entry", "--site", "rt", "--entries", entries,
            "--init-patch", patch,
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        payload = json.loads(patch.read_text(encoding="utf-8"))
        payload["changes"] = [
            {"id": "RT1001", "set": {"category": "國際/新題"}},
            {"id": "RT1002", "set": {"tc": "T1/C1"}},
        ]
        _write(patch, payload)
        before = entries.read_bytes()

        preview = self.run_cli(
            "rewrite-entry", "--site", "rt", "--entries", entries,
            "--patch-file", patch, "--dry-run",
        )
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(entries.read_bytes(), before)
        self.assertIn("RT1001", preview.stderr)

        applied = self.run_cli(
            "rewrite-entry", "--site", "rt", "--entries", entries,
            "--patch-file", patch,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        output = json.loads(entries.read_text(encoding="utf-8"))
        self.assertEqual(output["RT1001"]["category"], "國際/新題")
        self.assertIn("舊摘要", output["RT1001"]["entry"])
        self.assertEqual(output["RT1001"]["fixture_note"], "keep-me")
        self.assertEqual(output["RT1002"]["tc"], "T1/C1")

    def test_core_patch_respects_active_lock_id_permissions(self):
        entries = _write(
            self.tmp_path / "rt_entries_1700.json",
            {
                "RT1001": "RT1001 (VO) ▎摘要一。▎畫面：資料畫面。無BITE。",
                "RT1002": "RT1002 (VO) ▎摘要二。▎畫面：資料畫面。無BITE。",
            },
        )
        _write(
            self.tmp_path / "rt_gate_lock.json",
            {
                "site": "RT",
                "entries_path": str(entries.resolve()),
                "reasons": [{"code": "FMT_OPERATIONAL_NOTE", "count": 1,
                             "items": ["RT1001"]}],
                "lint_contexts": {},
            },
        )
        patch = _write(
            self.tmp_path / "rt.patch.json",
            {
                "schema_version": 1,
                "site": "rt",
                "target_sha256": _sha(entries),
                "changes": [{"id": "RT1002", "set": {"entry": "not allowed"}}],
            },
        )
        before = entries.read_bytes()

        result = self.run_cli(
            "rewrite-entry", "--site", "rt", "--entries", entries,
            "--patch-file", patch,
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("不在 gate lock", result.stderr)
        self.assertEqual(entries.read_bytes(), before)

    def test_core_patch_rejects_lint_regression_and_stale_sha(self):
        cases = ("lint", "stale")
        for stem in cases:
            with self.subTest(stem=stem):
                entries = _write(
                    self.tmp_path / f"rt_{stem}_entries.json",
                    {"RT1001": "RT1001 (VO) ▎乾淨摘要。▎畫面：資料畫面。無BITE。"},
                )
                payload = {
                    "schema_version": 1,
                    "site": "rt",
                    "target_sha256": _sha(entries),
                    "changes": [{
                        "id": "RT1001",
                        "set": {"entry": "RT1001 (VO) ▎摘要（完整引言待補）。▎畫面：資料畫面。無BITE。"},
                    }],
                }
                if stem == "stale":
                    payload["target_sha256"] = "0" * 64
                patch = _write(self.tmp_path / f"rt_{stem}.patch.json", payload)
                before = entries.read_bytes()

                result = self.run_cli(
                    "rewrite-entry", "--site", "rt", "--entries", entries,
                    "--patch-file", patch,
                )

                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("stale" if stem == "stale" else "FMT_OPERATIONAL_NOTE",
                              result.stderr)
                self.assertEqual(entries.read_bytes(), before)


class SanitizedBaselineFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp.name)
        self.bridge = Path(__file__).with_name("s2_platform_bridge.py")

    def tearDown(self):
        self.temp.cleanup()

    def run_bridge(self, *args):
        return subprocess.run(
            [sys.executable, str(self.bridge), *map(str, args)],
            cwd=self.bridge.parents[1],
            text=True,
            encoding="utf-8",
            capture_output=True,
        )

    def test_fixture_recomputes_historical_totals_and_replays_39_plus_9(self):
        import s2_batch_patch_baseline as baseline

        fixture = baseline.load_fixture()
        summary = baseline.summarize(fixture)
        self.assertEqual(summary["targeted_edit_turns"], 48)
        self.assertEqual(summary["targeted_cache_read_input_tokens"], 25_002_406)
        self.assertEqual(summary["round_tool_turns"], 474)
        self.assertEqual(summary["source_log_bytes"], 7_393_439)
        self.assertEqual(
            [len(session["modified"]) for session in summary["sessions"]], [39, 9]
        )
        written = baseline.materialize(fixture, self.tmp_path / "replay")

        for case in written:
            with self.subTest(site=case["site"]):
                skeleton = Path(case["skeleton"])
                patch = Path(case["patch"])
                entries = skeleton.with_name(f"{case['site']}_entries.json")
                built = self.run_bridge("build", "--skeleton", skeleton, "--out", entries)
                self.assertEqual(built.returncode, 0, built.stderr)
                applied = self.run_bridge(
                    "rewrite-entry", "--site", case["site"],
                    "--skeleton", skeleton, "--entries", entries,
                    "--patch-file", patch,
                )
                self.assertEqual(applied.returncode, 0, applied.stderr)
                rows = json.loads(skeleton.read_text(encoding="utf-8"))
                self.assertEqual(len(rows), case["changes"])
                self.assertEqual(
                    sum("after" in row["entry"] for row in rows),
                    8 if case["site"] == "abc" else case["changes"],
                )


class BatchPatchMetricsTests(unittest.TestCase):
    def test_metrics_separate_targeted_edits_patch_applies_and_legacy_rewrite(self):
        import s2_token_metrics as metrics

        with tempfile.TemporaryDirectory() as temp:
            transcript = Path(temp) / "fixture.jsonl"
            blocks = [
                ("Edit", {"file_path": "C:/scratch/enex_entries_1700.json"}),
                ("Edit", {"file_path": "C:/scratch/notes.md"}),
                ("Bash", {"command": "python scripts/s2_platform_bridge.py rewrite-entry "
                                     "--site enex --patch-file enex.patch.json"}),
                ("Bash", {"command": "python scripts/s2_batch_prep.py rewrite-entry "
                                     "--site rt --patch-file rt.patch.json"}),
                ("Bash", {"command": "python scripts/s2_batch_prep.py rewrite-entry "
                                     "--site rt --id RT1 --set RT1=x"}),
            ]
            lines = []
            for index, (name, tool_input) in enumerate(blocks, 1):
                lines.append(json.dumps({
                    "timestamp": f"2026-09-24T00:00:0{index}+00:00",
                    "message": {
                        "id": f"m{index}",
                        "usage": {"cache_read_input_tokens": 10, "output_tokens": 1},
                        "content": [{"type": "tool_use", "name": name,
                                     "input": tool_input}],
                    },
                }))
            transcript.write_text("\n".join(lines), encoding="utf-8")

            measured = metrics.measure(str(transcript))

        self.assertEqual(measured["batch_patch"]["targeted_edit_calls"], 1)
        self.assertEqual(measured["batch_patch"]["patch_apply_calls"], 2)
        self.assertEqual(measured["batch_patch"]["adoption_rate"], 2 / 3)
        self.assertEqual(
            measured["tool_calls_by_name"]["platform_bridge:rewrite-entry:patch-file"], 1
        )
        self.assertEqual(
            measured["tool_calls_by_name"]["s2_batch_prep:rewrite-entry:patch-file"], 1
        )
        self.assertEqual(measured["tool_calls_by_name"]["s2_batch_prep:rewrite-entry"], 1)


class PatchAdoptionHintTests(unittest.TestCase):
    def test_platform_lint_failure_prints_executable_scaffold_command(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = _write(
                Path(temp) / "0924-ENEX-state.json",
                {"source": "ENEX", "checkpoint": "0924-1700"},
            )
            result = subprocess.run(
                [sys.executable, "scripts/s2_platform_lint.py", str(candidate)],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("s2_platform_bridge.py rewrite-entry", result.stdout)
        self.assertIn("--init-patch", result.stdout)
        self.assertIn("enex_skeleton_1700.json", result.stdout)
        self.assertNotIn("--id", result.stdout)


if __name__ == "__main__":
    unittest.main()
