# -*- coding: utf-8 -*-
"""Static publish contracts, using isolated synthetic archive databases."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import s2_warehouse as W
import s2_warehouse_publish as P
from test_s2_warehouse import item


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "archive"
        self.output = self.archive / "publish"

    def put(self, day, rows, hour="18"):
        raw = P.packed({"window_start": day + " 13:00", "updated_at": day + f"T{hour}:00:00+08:00",
                        "checkpoint": day[5:7] + day[8:] + "-1700", "items": rows})
        return W.import_bytes(raw, self.archive, archive_mode=True, folder_date=day)

    def seed(self):
        self.put("2026-09-30", [item(raw_entry="中文摘要", src_text="NeedleOnlyInOriginal " + "x" * 900,
                                    platform={"secret": "DO_NOT_EXPORT"}, compiled="DO_NOT_EXPORT", fields={"secret": "DO_NOT_EXPORT"}),
                                item("AP4684893", raw_entry="備註", script_status="note"),
                                item("AP4684894", first_seen_checkpoint=None)])
        self.put("2026-10-01", [item("RT1234", "RT", raw_entry="第二班", first_seen_checkpoint="1001-1700")])

    def manifest(self):
        return json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))

    def rows(self, entry):
        return [row for part in entry["parts"] for row in json.loads((self.output / part["path"]).read_text(encoding="utf-8"))["items"]]

    def files(self):
        return {p.relative_to(self.output).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.output.rglob("*.json")}

    def test_query_projection_whitelist_counts_and_hashes(self):
        self.seed()
        db = self.archive / "warehouse.sqlite"
        original = (db.read_bytes(), db.stat().st_mtime_ns)
        result = P.export_archive(self.root)
        manifest = self.manifest()
        self.assertEqual(result["oversized_shards"], 0)
        self.assertEqual(manifest["material_count"], 4)
        self.assertEqual(manifest["observation_count"], 4)
        self.assertIn("unknown", [d["date"] for d in manifest["days"]])
        conn = W.connect_db(db)
        try:
            cli = {r["material_id"]: r for r in W.query(conn, include_notes=True)["素材"]}
        finally:
            conn.close()
        exported = [r for e in manifest["days"] for r in self.rows(e)]
        for row in exported:
            self.assertEqual({k: row[k] for k in cli[row["material_id"]]}, cli[row["material_id"]])
            self.assertEqual(set(row) - set(cli[row["material_id"]]), {"id", "raw_entry", "tc", "search_text"})
        self.assertIn("NeedleOnlyInOriginal", next(r for r in exported if r["id"] == "AP4684892")["search_text"])
        for e in manifest["days"] + manifest["shifts"]:
            self.assertEqual(e["count"], len(self.rows(e)))
            for part in e["parts"]:
                data = (self.output / part["path"]).read_bytes()
                self.assertEqual(P.digest(data), part["sha256"])
                self.assertEqual(len(data), part["bytes"])
                for secret in (b'DO_NOT_EXPORT', b'payload_json', b'"platform"', b'"compiled"', b'"fields"'):
                    self.assertNotIn(secret, data)
        self.assertEqual(original, (db.read_bytes(), db.stat().st_mtime_ns))

    def test_repeat_preserves_generation_timestamp_and_every_mtime(self):
        self.seed()
        first = P.export_archive(self.root)
        before = self.files()
        second = P.export_archive(self.root)
        self.assertEqual(first["generation"], second["generation"])
        self.assertEqual(second["changed_files"], 0)
        self.assertEqual(before, self.files())

    def test_only_affected_shards_change(self):
        self.seed()
        first = P.export_archive(self.root)
        before = self.files()
        self.put("2026-10-02", [item("RT5678", "RT", first_seen_checkpoint="1002-1700")])
        second = P.export_archive(self.root)
        self.assertNotEqual(first["generation"], second["generation"])
        # Material/shift, editorial owner, reference bucket, empty bundle and
        # optional-rundown shards for the new shift, plus the manifest.
        self.assertEqual(second["changed_files"], 7)
        after = self.files()
        for path, value in before.items():
            if path != "manifest.json":
                self.assertEqual(value, after[path])

    def test_utf8_split_boundary_and_exceptional_single_row(self):
        rows = [{"text": "中" * 50} for _ in range(8)]
        chunks = P.split_rows(rows, 350)
        self.assertEqual(sum(chunks, []), rows)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(P.packed({"items": c})) <= 350 for c in chunks))
        self.seed()
        P.export_archive(self.root, max_bytes=1800)
        parts = [p for e in self.manifest()["days"] for p in e["parts"]]
        self.assertTrue(any(p["oversized"] for p in parts))
        self.assertTrue(all(p["count"] == 1 for p in parts if p["oversized"]))

    def test_large_day_and_shift_split_and_match_all_rows(self):
        self.put("2026-09-30", [item(f"AP{4684000+i}", raw_entry="測試中文" * 50) for i in range(7)])
        P.export_archive(self.root, max_bytes=4200)
        for group in ("days", "shifts"):
            entry = self.manifest()[group][0]
            self.assertGreater(len(entry["parts"]), 1)
            self.assertEqual(len(self.rows(entry)), 7)
            self.assertTrue(all(p["bytes"] <= 4200 for p in entry["parts"]))

    def test_observed_revision_and_tags_survive_current_update(self):
        old = item("YNA-buGW2sCr_do", "YNA", raw_entry="舊摘要", tc={"T": ["政治"], "C": ["南韓"]})
        self.put("2026-09-30", [old])
        new = dict(old, raw_entry="新摘要", first_seen_checkpoint="1001-1700", tc={"T": ["科技"], "C": ["美國"]})
        self.put("2026-10-01", [new])
        P.export_archive(self.root)
        m = self.manifest()
        self.assertEqual(m["material_count"], 1)
        self.assertEqual(m["observation_count"], 2)
        old_row = self.rows(m["shifts"][0])[0]
        self.assertEqual(old_row["raw_entry"], "舊摘要")
        self.assertEqual(old_row["tc"], old["tc"])
        current = self.rows(m["days"][0])[0]
        self.assertEqual(current["raw_entry"], "新摘要")
        self.assertEqual(set(current["tc"]["T"]), {"政治", "科技"})

    def test_same_day_multiple_snapshots_keep_all_observations(self):
        self.put("2026-09-30", [item()])
        self.put("2026-09-30", [item(raw_entry="新摘要")], hour="19")
        P.export_archive(self.root)
        entry = self.manifest()["shifts"][0]
        self.assertEqual(entry["snapshot_count"], 2)
        self.assertEqual(entry["count"], 2)

    def test_atomic_failure_does_not_change_target_or_leave_temp(self):
        path = self.root / "atomic.json"
        path.write_bytes(b"old")
        with mock.patch.object(P.os, "replace", side_effect=OSError("simulated interruption")):
            with self.assertRaises(OSError):
                P.write_changed(path, b"new")
        self.assertEqual(path.read_bytes(), b"old")
        self.assertEqual(list(self.root.glob(".publish-*")), [])

    def test_failed_export_does_not_publish_manifest(self):
        self.seed()
        P.export_archive(self.root)
        before = (self.output / "manifest.json").read_bytes()
        self.put("2026-10-02", [item("RT5678", "RT")])
        with mock.patch.object(P, "write_changed", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                P.export_archive(self.root)
        self.assertEqual((self.output / "manifest.json").read_bytes(), before)

    def test_corrupt_shard_repaired_on_same_generation(self):
        self.seed()
        first = P.export_archive(self.root)
        manifest_bytes = (self.output / "manifest.json").read_bytes()
        part = self.manifest()["days"][0]["parts"][0]
        (self.output / part["path"]).write_bytes(b"broken")
        again = P.export_archive(self.root)
        self.assertEqual(first["generation"], again["generation"])
        self.assertEqual(again["changed_files"], 1)
        self.assertEqual((self.output / "manifest.json").read_bytes(), manifest_bytes)

    def test_demo_copies_only_manifest_shards_and_static_assets(self):
        self.seed()
        P.export_archive(self.root)
        (self.output / "days/stale.json").write_bytes(b"not reachable")
        demo = self.root / "demo"
        P.build_demo(self.output, demo)
        self.assertFalse((demo / "data/days/stale.json").exists())
        self.assertTrue((demo / "index.html").exists())
        self.assertIn('fetch(', (demo / "app.js").read_text(encoding="utf-8"))
        self.assertEqual((demo / "data/manifest.json").read_bytes(), (self.output / "manifest.json").read_bytes())
        before = {p: p.stat().st_mtime_ns for p in demo.rglob("*") if p.is_file()}
        P.build_demo(self.output, demo)
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in before})

    def test_missing_db_does_not_create_database_or_empty_manifest(self):
        with self.assertRaises(W.sqlite3.OperationalError):
            P.export_archive(self.root)
        self.assertFalse(self.archive.exists())
        with self.assertRaises(ValueError):
            P.allowed_path(Path(r"G:\forbidden"))


if __name__ == "__main__":
    unittest.main()
