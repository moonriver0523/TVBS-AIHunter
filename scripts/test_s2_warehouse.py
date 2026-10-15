# -*- coding: utf-8 -*-
"""Phase 0 契約與反例測試：python -X utf8 scripts/test_s2_warehouse.py。"""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

import s2_warehouse as W


def item(mid="AP4684892", source="AP", **extra):
    row = {"id": mid, "source": source, "script_status": "has_script",
           "first_seen_checkpoint": "0930-1700", "first_seen_run_id": "正式輪",
           "last_checked_checkpoint": "1001-0900", "last_checked_run_id": "末輪",
           "raw_entry": "可查中文摘要", "src_text": "", "tc": {"T": ["政治"], "C": ["美國"]}}
    row.update(extra)
    return row


def snapshot(rows):
    return json.dumps({"window_start": "2026-09-30 13:00", "checkpoint": "1001-1100",
                       "updated_at": "2026-10-01T11:14:17+08:00", "items": rows}, ensure_ascii=False).encode("utf-8")


class DatesTest(unittest.TestCase):
    def dates(self, row):
        return W.extract_dates(row, "2026-09-30")

    def test_r45_style_ap_shotlist_not_shift_or_editorial_time(self):
        # R45 型態 fixture；未冒稱讀過 0916 原始 state。
        for mid, d, expected in (("APcns007383", "12 September 2026", "2026-09-12"),
                                 ("AP4684892", "10 September 2026", "2026-09-10")):
            with self.subTest(mid=mid):
                row = item(mid, src_text=f"HEAD: 日期不在標題\nSCRIPT: SHOTLIST: ASSOCIATED PRESS Kyiv - {d} 1. Wide city STORYLINE: 1 January 2021",
                           entry_updated_ts="2026-10-01T08:00:00")
                dates = self.dates(row)
                self.assertEqual(dates["material_date"], expected)
                self.assertEqual(dates["first_seen_at_utc"], "2026-09-30T09:00:00Z")
                self.assertEqual(dates["first_seen_precision"], "checkpoint_anchor")
                self.assertIsNone(dates["material_at_utc"])
                self.assertIsNone(dates["source_published_at_utc"])
                self.assertEqual(dates["content_dates"][0]["precision"], "date")
                self.assertEqual(len(dates["content_dates"]), 1)

    def test_archive_and_historical_broll_do_not_override_main(self):
        for label in ("ARCHIVE", "FILE", "HISTORICAL B-ROLL"):
            with self.subTest(label=label):
                row = item(src_text="SCRIPT: SHOTLIST: ASSOCIATED PRESS - ARCHIVE Kyiv - 1 January 2021 1. Old\n"
                           f"ASSOCIATED PRESS - {label} Kyiv - 10 September 2026 2. Old\n"
                           "ASSOCIATED PRESS Kyiv - 30 September 2026 3. Main STORYLINE: 12 September 2026")
                dates = self.dates(row)
                self.assertEqual(dates["material_date"], "2026-09-30")
                self.assertEqual(dates["date_quality"], "embedded_verified")
                self.assertFalse(dates["content_dates"][0]["main_candidate"])
                self.assertFalse(dates["content_dates"][1]["main_candidate"])
                self.assertTrue(dates["content_dates"][2]["main_candidate"])

    def test_historical_only_is_evidence_not_main(self):
        dates = self.dates(item("AP4684982", src_text="SCRIPT: SHOTLIST: ASSOCIATED PRESS London - 10 September 2021 1. Old"))
        self.assertEqual(dates["material_date_basis"], "ingestion_fallback")
        self.assertEqual(dates["content_dates"][0]["date_start"], "2021-09-10")

    def test_cctv_body_date_not_shotlist(self):
        dates = self.dates(item("APcctv079619", src_text="HEAD: 10 September 2026\nSCRIPT: SHOTLIST: 1. Various STORYLINE: On 12 September 2026 he said..."))
        self.assertEqual(dates["material_date_basis"], "ingestion_fallback")
        self.assertEqual(dates["content_dates"], [])

    def test_truncated_0930_style_keeps_evidence(self):
        dates = self.dates(item("AP4687838", src_text="SCRIPT: SHOTLIST: ASSOCIATED PRESS Louisville - 30 July 2026 1. Housing\n"
                               "ASSOCIATED PRESS Louisville - 31 July 2026 2. Housing ...[TRUNCATED]"))
        self.assertEqual(dates["material_date"], "2026-09-30")
        self.assertEqual(dates["date_quality"], "ingestion_fallback")
        self.assertEqual(len(dates["content_dates"]), 2)
        self.assertTrue(all(not e["main_candidate"] for e in dates["content_dates"]))

    def test_multi_equal_rank_earliest_ambiguous_full_range(self):
        dates = self.dates(item(src_text="SCRIPT: SHOTLIST: ASSOCIATED PRESS Paris - 1 October 2026 1. Main\n"
                               "ASSOCIATED PRESS London - 30 September 2026 2. Main"))
        self.assertEqual(dates["material_date"], "2026-09-30")
        self.assertEqual(dates["date_quality"], "ambiguous")
        self.assertEqual(dates["material_date_range"], ["2026-09-30", "2026-10-01"])
        self.assertEqual({e["date_start"] for e in dates["content_dates"]}, {"2026-09-30", "2026-10-01"})

    def test_repeat_same_date_is_not_ambiguous(self):
        dates = self.dates(item(src_text="SCRIPT: SHOTLIST: ASSOCIATED PRESS Paris - 30 September 2026 1. Main\n"
                               "ASSOCIATED PRESS London - 30 September 2026 2. Main"))
        self.assertEqual(dates["date_quality"], "embedded_verified")
        self.assertIsNone(dates["material_date_range"])
        self.assertEqual(len(dates["content_dates"]), 2)

    def test_unknown_format_retained_not_guessed(self):
        dates = self.dates(item(src_text="SCRIPT: SHOTLIST: narrator quotes 30 September 2026 in a sentence. 1. Main"))
        self.assertEqual(dates["date_quality"], "ingestion_fallback")
        self.assertFalse(dates["content_dates"][0]["main_candidate"])

    def test_reuters_dateline_and_archive(self):
        dates = self.dates(item("RT6431", "RT", src_text="HEAD: title\nSTORY: VIDEO SHOWS: City\n"
                               "SHOWS: KYIV, UKRAINE (SEPTEMBER 30, 2026) (REUTERS - Access all)\n1. City\n"
                               "LONDON, UK (SEPTEMBER 12, 2026) (FILE)\n2. Old\nSTORY: In SEPTEMBER 10, 2026..."))
        self.assertEqual(dates["material_date"], "2026-09-30")
        self.assertEqual(dates["date_quality"], "embedded_verified")
        self.assertEqual(len(dates["content_dates"]), 2)

    def test_youtube_three_dates_and_candidate_is_not_first_seen(self):
        dates = self.dates(item("YNA-buGW2sCr_do", "YNA", first_seen_checkpoint="1001-0900",
                               src_text="September 29 was the event",
                               platform={"video_id": "buGW2sCr_do", "published_at_utc": "2026-09-30T22:51:23Z", "candidate_checkpoint": "1001-0700"}))
        self.assertEqual(dates["material_date"], "2026-10-01")
        self.assertEqual(dates["source_published_at_utc"], "2026-09-30T22:51:23Z")
        self.assertEqual(dates["first_seen_at_utc"], "2026-10-01T01:00:00Z")
        self.assertEqual(dates["content_dates"][0]["kind"], "published")
        self.assertEqual(dates["content_dates"][0]["date_start"], "2026-10-01")

    def test_youtube_id_mismatch_falls_back(self):
        dates = self.dates(item("YNA-buGW2sCr_do", "YNA", platform={"video_id": "7blpZHaLwik", "published_at_utc": "2026-09-29T22:51:23Z"}))
        self.assertIsNone(dates["source_published_at_utc"])
        self.assertEqual(dates["date_quality"], "ingestion_fallback")

    def test_abc_already_taipei_and_completion_separate(self):
        dates = self.dates(item("ABC093026020", "ABC", platform={"DeliveryAvailableDateTime": "2026-10-01T00:30:00",
                               "DeliveryCompleteDateTime": "2026-10-01T01:00:00"}))
        self.assertEqual(dates["material_date"], "2026-10-01")
        self.assertEqual(dates["source_transmitted_at_utc"], "2026-09-30T16:30:00Z")
        self.assertEqual(dates["source_arrived_at_utc"], "2026-09-30T17:00:00Z")
        self.assertIsNone(dates["source_published_at_utc"])

    def test_et_summer_winter_and_dst_uncertainty(self):
        self.assertEqual(W.utc_text(W.parse_timestamp("2026-09-30T20:30:00", "America/New_York")), "2026-10-01T00:30:00Z")
        self.assertEqual(W.utc_text(W.parse_timestamp("2026-01-01T20:30:00", "America/New_York")), "2026-01-02T01:30:00Z")
        for raw in ("2026-11-01T01:30:00", "2026-03-08T02:30:00"):
            with self.assertRaises(ValueError):
                W.parse_timestamp(raw, "America/New_York")

    def test_rt_guid_date_fallback_never_makes_a_time(self):
        guid = "tag:reuters.com,2026:newsml_RW643129092026RP1:0004"
        dates = self.dates(item("RT6431", "RT", platform={"guid": guid, "guid_created_date": "1999-01-01"}))
        self.assertEqual(dates["material_date"], "2026-09-29")
        self.assertEqual(dates["material_date_basis"], "source_created_fallback")
        self.assertIsNone(dates["material_at_utc"])
        self.assertIsNone(dates["source_created_at_utc"])
        ev = next(e for e in dates["time_evidence"] if e.get("field") == "guid")
        self.assertEqual(ev["precision"], "date")
        self.assertIsNone(ev["at_utc"])
        self.assertEqual(W.source_link(item("RT6431", "RT", platform={"guid": guid}), "RT")["url"],
                         "https://www.reutersconnect.com/all?id=" + W.url_encode(guid) + "&media-types=vid")

    def test_rt_guid_does_not_override_main_or_published(self):
        platform = {"guid": "tag:reuters.com,2026:newsml_RW643129092026RP1:4",
                    "published_at_utc": "2026-09-30T01:00:00Z"}
        dates = self.dates(item("RT6431", "RT", platform=platform))
        self.assertEqual(dates["material_date_basis"], "source_published")
        dates = self.dates(item("RT6431", "RT", platform=platform,
                               src_text="STORY: SHOWS: KYIV, UKRAINE (SEPTEMBER 28, 2026) (REUTERS - Access all)\n1. City"))
        self.assertEqual(dates["material_date"], "2026-09-28")
        self.assertEqual(dates["material_date_basis"], "source_content_date")

    def test_rt_missing_or_malformed_guid_uses_ingestion(self):
        for guid in (None, "", "tag:reuters.com,2026:newsml_RW643131022026RP1:4", 7):
            with self.subTest(guid=guid):
                dates = self.dates(item("RT6431", "RT", platform={"guid": guid}))
                self.assertEqual(dates["material_date_basis"], "ingestion_fallback")
                link = W.source_link(item("RT6431", "RT", platform={"guid": guid}), "RT")
                self.assertEqual(link["kind"], "permalink" if isinstance(guid, str) and guid else "unavailable")

    def test_rt_opaque_guid_can_link_without_a_created_date(self):
        guid = "tag:reuters.com,2026:newsml_RWOS2QB1L:2"
        row = item("RT3603", "RT", platform={"guid": guid})
        self.assertEqual(W.source_link(row, "RT")["kind"], "permalink")
        self.assertEqual(self.dates(row)["material_date_basis"], "ingestion_fallback")
        for wrong in ('https://example.com/item', 'tag:evil.com,2026:newsml_RW615029092026RP1:4',
                      'tag:reuters.com,2026:newsml_RW615029092026RP1:4?key=x'):
            self.assertEqual(W.source_link(item("RT6431", "RT", platform={"guid": wrong}), "RT")["kind"], "unavailable")

    def test_abc_correct_complete_spelling_is_the_only_field_read(self):
        dates = self.dates(item("ABC093026020", "ABC", platform={
            "DeliveryCompleteDateTime": "2026-10-01T01:00:00",
            "DeliveryCompletedDateTime": "2026-10-02T01:00:00"}))
        self.assertEqual(dates["source_arrived_at_utc"], "2026-09-30T17:00:00Z")
        dates = self.dates(item("ABC093026020", "ABC", platform={"DeliveryCompletedDateTime": "2026-10-02T01:00:00"}))
        self.assertIsNone(dates["source_arrived_at_utc"])

    def test_enex_epoch_and_conflict(self):
        ms = int(W.parse_timestamp("2026-09-30T22:30:00Z").timestamp()*1000)
        row = item("ENEX932915", "ENEX", platform={"sortDate": ms, "publishedDate": ms})
        self.assertEqual(self.dates(row)["material_date"], "2026-10-01")
        row["platform"]["publishedDate"] += 86400000
        dates = self.dates(row)
        self.assertEqual(dates["date_quality"], "ingestion_fallback")
        self.assertEqual(len([e for e in dates["time_evidence"] if "at_utc" in e]), 2)

    def test_ns_shotdate_and_created_are_different_semantics(self):
        row = item("SE-004WE", "NS", src_text="SCRIPT: <p><b>Shot Date: </b> 09/29/2026</p>",
                   platform={"createdDate": "2026-09-30T22:00:00Z"})
        dates = self.dates(row)
        self.assertEqual(dates["material_date"], "2026-09-29")
        self.assertEqual(dates["source_created_at_utc"], "2026-09-30T22:00:00Z")
        row["src_text"] = ""
        dates = self.dates(row)
        self.assertEqual(dates["material_date_basis"], "source_created_fallback")
        self.assertIsNone(dates["source_published_at_utc"])

    def test_ap_arrival_timezone_unknown_and_aware_fallback(self):
        row = item(platform={"arrivaldatetime": "2026-10-01T02:00:00"})
        dates = self.dates(row)
        self.assertIsNone(dates["source_arrived_at_utc"])
        self.assertEqual(dates["date_quality"], "ingestion_fallback")
        row["platform"]["arrivaldatetime"] += "+00:00"
        self.assertEqual(self.dates(row)["material_date_basis"], "source_arrival_fallback")

    def test_recording_cross_midnight_and_missing_year(self):
        dates = self.dates(item("CNN 10-01 010158", "SIDE_CNN", first_seen_checkpoint="1001-0430"))
        self.assertEqual(dates["material_date"], "2026-10-01")
        self.assertEqual(dates["recorded_at_utc"], "2026-09-30T17:01:58Z")
        self.assertEqual(dates["date_quality"], "inferred_recording")
        dates = self.dates(item("CNN 010158", "SIDE_CNN"))
        self.assertEqual(dates["date_quality"], "ingestion_fallback")

    def test_checkpoint_crossyear_and_unknown_no_candidate_substitution(self):
        self.assertEqual(W.utc_text(W.checkpoint_time("0101-0100", "2026-12-31")), "2026-12-31T17:00:00Z")
        self.assertIsNone(W.checkpoint_time("0920-1700", "2026-09-30"))
        dates = self.dates(item(first_seen_checkpoint=None, entry_updated_ts="2026-09-30T18:00:00",
                               platform={"candidate_checkpoint": "0930-1700"}))
        self.assertIsNone(dates["material_date"])
        self.assertIsNone(dates["first_seen_at_utc"])


class IdentityLinksTest(unittest.TestCase):
    def test_digit_leading_video_ids_are_not_ns(self):
        for mid, expected in (("YNA-7blpZHaLwik", "YNA"), ("YNA-5vlRwHvWwkQ", "YNA"),
                              ("CNA-3SIb5qK0cqk", "CNA"), ("YNA-8GnWofrZ_uQ", "YNA"),
                              ("YNA-5EFB8BHM0EE", "YNA")):
            with self.subTest(mid=mid):
                row = item(mid, expected)
                self.assertEqual(W.source_class(row)[0], expected)
                self.assertEqual(W.canonical_identity(row, "2026-09-30")[:2], (mid, "strong"))
        self.assertEqual(W.source_class(item("PO-16WE", "NS"))[0], "NS")

    def test_prefix_only_normalization_and_legacy_namespacing(self):
        self.assertEqual(W.canonical_identity(item("yna-AbCd_ef-123", "YT"), "2026-09-30")[0], "YNA-AbCd_ef-123")
        for mid, src in (("YNA01", "YNA"), ("CNA01", "CNA"), ("OTH01", "X"), ("RT6431", "RT")):
            one = W.canonical_identity(item(mid, src), "2026-09-30")
            two = W.canonical_identity(item(mid, src), "2026-10-01")
            self.assertEqual(one[1], "provisional")
            self.assertNotEqual(one[0], two[0])
        self.assertEqual(W.canonical_identity(item("RT6431", "RT"), "2026-09-30")[0], "legacy:2026-09-30:RT:RT6431")
        self.assertEqual(W.canonical_identity(item("CNN 10-01 010158", "SIDE_CNN"), "2026-09-30")[0],
                         "legacy:2026-09-30:SIDE_CNN:CNN%2010-01%20010158")

    def test_deterministic_links_and_missing_reasons(self):
        link = W.source_link(item("YNA-AbCd_ef-123", "YNA"), "YNA")
        self.assertEqual(link["url"], "https://www.youtube.com/watch?v=AbCd_ef-123")
        self.assertIsNone(link["missing_reason"])
        link = W.source_link(item(), "AP")
        self.assertEqual(link["url"], "https://newsroom.ap.org/home/search?query=4684892&mediaType=video")
        self.assertEqual(link["kind"], "search")
        guid = "urn:newsml:reuters.com:20260930:RT6431:1"
        link = W.source_link(item("RT6431", "RT", platform={"guid": guid}), "RT")
        self.assertEqual(link["url"], "https://www.reutersconnect.com/all?id=urn%3Anewsml%3Areuters.com%3A20260930%3ART6431%3A1&media-types=vid")
        for mid, src in (("RT6431", "RT"), ("APcns007383", "AP"), ("YNA01", "YNA"), ("PO-16WE", "NS"), ("ABC093026020", "ABC")):
            link = W.source_link(item(mid, src), src)
            self.assertIsNone(link["url"])
            self.assertTrue(link["missing_reason"])

    def test_ns_link_whitelist_rejects_preview_and_untrusted(self):
        for url in ("https://newsource.cnn.com.evil.example/asset", "https://cdn.example/preview.mp4", "https://newsource.cnn.com/asset?token=secret"):
            self.assertIsNone(W.source_link(item("PO-16WE", "NS", platform={"url": url}), "NS")["url"])
        url = "https://newsource.cnn.com/asset/123"
        self.assertEqual(W.source_link(item("PO-16WE", "NS", platform={"url": url}), "NS")["url"], url)


class ArchiveImportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Archive"
        self.source.mkdir()
        self.out = self.root / "warehouse" / "archive"

    def put(self, day, rows, *, legacy=False, suffix="", **extra):
        folder = self.source / (day.replace("-", "")+suffix)
        folder.mkdir(exist_ok=True)
        state = {"checkpoint": day[5:7]+day[8:]+"-1700", "items": rows,
                 "updated_at": day+"T18:00:00+08:00", "notes": [], "rt_status": {}}
        if not legacy:
            state["window_start"] = day+" 13:00"
        state.update(extra)
        path = folder / (day[5:7]+day[8:]+"-s2-state.json")
        path.write_bytes(json.dumps(state, ensure_ascii=False).encode())
        return path

    def connect(self):
        conn = W.connect_db(self.out / "warehouse.sqlite")
        self.addCleanup(conn.close)
        return conn

    def test_multishift_strong_identity_legacy_separate_and_idempotency(self):
        for day, cp in (("2026-09-30", "0930-1700"), ("2026-10-01", "1001-1700")):
            self.put(day, [item("YNA-buGW2sCr_do", "YNA", first_seen_checkpoint=cp),
                           item("CNA-3SIb5qK0cqk", "CNA", first_seen_checkpoint=cp),
                           item("YNA01", "YNA", first_seen_checkpoint=cp), item("RT6431", "RT", first_seen_checkpoint=cp)])
        result = W.import_archive(self.source, self.out)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["shift_count"], 2)
        self.assertEqual(result["totals"]["materials"], 6)
        self.assertEqual(result["totals"]["material_observations"], 8)
        self.assertEqual(result["possible_duplicate_count"], 2)
        conn = self.connect()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM shifts").fetchone()[0], 2)
        self.assertEqual(conn.execute("SELECT first_seen_at_utc FROM materials WHERE material_id='YNA-buGW2sCr_do'").fetchone()[0], "2026-09-30T09:00:00Z")
        self.assertEqual(W.query(conn, "2026-09-30", "2026-10-01")["總筆數"], 6)
        receipts = {p.name: p.read_bytes() for p in (self.out / "receipts").glob("*.json") if not p.name.startswith("archive-run-")}
        repeated = W.import_archive(self.source, self.out)
        self.assertEqual(result["totals"], repeated["totals"])
        self.assertTrue(all(all(n == 0 for n in p["added"].values()) for p in repeated["processed"]))
        self.assertEqual(receipts, {p.name: p.read_bytes() for p in (self.out / "receipts").glob("*.json") if not p.name.startswith("archive-run-")})

    def test_old_schema_folder_inference_bad_rows_partial_and_txt(self):
        path = self.put("2026-07-31", [item(first_seen_checkpoint="0731-1700"), {"source": "AP"},
                                     item("RT1234", "RT", platform="bad"), item("RT2222", "RT", tc={"T": "bad"})], legacy=True,
                        updated_at="2026-08-01T07:00:00")
        txt = path.with_name("0731晚班交接.txt")
        txt.write_bytes(b"\xffnon-utf8")
        result = W.import_archive(self.source, self.out)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["shift_date_quality"], {"inferred_folder": 1})
        self.assertEqual((result["shifts"][0]["input"], result["shifts"][0]["accepted"], result["shifts"][0]["quarantine"]), (4, 1, 3))
        receipt = json.loads(self.connect().execute("SELECT receipt_json FROM ingest_receipts").fetchone()[0])
        self.assertEqual(receipt["shift_date"], "2026-07-31")
        self.assertTrue(any("資料夾推定" in issue for issue in receipt["issues"]))
        self.assertEqual(receipt["txt_crosscheck"]["sha256"], W.sha(txt.read_bytes()))
        self.assertEqual(W.import_archive(self.source, self.out)["status"], "partial")

    def test_duplicate_folder_hash_and_filtering(self):
        path = self.put("2026-09-30", [item()])
        duplicate = self.put("2026-09-30", [item()], suffix=" (1)")
        self.assertEqual(path.read_bytes(), duplicate.read_bytes())
        self.put("2026-10-01", [item()])
        self.put("2026-10-01", [item(raw_entry="另一份")], suffix="(1)")
        for relative in ("0930-s2-state.json.bak", "_誤開新檔-0930-s2-state.json", "0930晚班交接.prev.txt"):
            (path.parent / relative).write_bytes(b"bad")
        scratch = path.parent / "_暫存"
        scratch.mkdir()
        (scratch / "0930-s2-state.json").write_bytes(b"bad")
        (duplicate.parent / "0930-s2-state (1).json").write_bytes(b"bad")
        (self.source.parent / "1015-s2-state.json").write_bytes(b"live")
        result = W.import_archive(self.source, self.out)
        self.assertEqual(result["totals"]["ingest_receipts"], 1)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(any(s["reason"] == "(1) 快照 hash 重複" for s in result["skipped"]))
        self.assertTrue(any("hash 不同" in e["reason"] for e in result["errors"]))
        self.assertEqual(len(result["skipped"]), 8)

    def test_multiple_snapshots_same_shift_new_revisions_and_out_of_order(self):
        path = self.put("2026-09-30", [item("YNA-buGW2sCr_do", "YNA", raw_entry="新版")], updated_at="2026-10-01T12:00:00+08:00")
        W.import_archive(self.source, self.out)
        self.put("2026-09-30", [item("YNA-buGW2sCr_do", "YNA", raw_entry="舊版")], updated_at="2026-09-30T18:00:00+08:00")
        result = W.import_archive(self.source, self.out)
        conn = self.connect()
        self.assertEqual(result["totals"]["materials"], 1)
        self.assertEqual(result["totals"]["material_revisions"], 2)
        self.assertEqual(result["totals"]["material_observations"], 2)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM shifts").fetchone()[0], 2)
        payload = conn.execute("SELECT r.payload_json FROM materials m JOIN material_revisions r ON r.revision_id=m.current_revision_id").fetchone()[0]
        self.assertEqual(json.loads(payload)["raw_entry"], "新版")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM ingest_receipts WHERE snapshot_bytes=?", (path.read_bytes(),)).fetchone()[0], 1)

    def test_same_payload_reuses_revision_and_newer_snapshot_updates_current(self):
        rows = [item("YNA-buGW2sCr_do", "YNA", first_seen_checkpoint="0930-1700")]
        self.put("2026-09-30", rows)
        W.import_archive(self.source, self.out)
        self.put("2026-10-01", rows)
        result = W.import_archive(self.source, self.out)
        self.assertEqual(result["totals"]["material_revisions"], 1)
        self.assertEqual(result["totals"]["material_observations"], 2)
        self.put("2026-10-01", [dict(rows[0], raw_entry="較新摘要")], updated_at="2026-10-02T18:00:00+08:00")
        result = W.import_archive(self.source, self.out)
        self.assertEqual(result["totals"]["material_revisions"], 2)
        conn = self.connect()
        self.assertEqual(W.query(conn, keyword="較新摘要")["總筆數"], 1)
        self.assertEqual(conn.execute("SELECT material_date FROM materials").fetchone()[0], "2026-09-30")

    def test_unknown_snapshot_order_keeps_both_revisions_and_flags_conflict(self):
        self.put("2026-09-30", [item("YNA-buGW2sCr_do", "YNA", raw_entry="先觀測")], updated_at=None)
        W.import_archive(self.source, self.out)
        self.put("2026-09-30", [item("YNA-buGW2sCr_do", "YNA", raw_entry="時間不明")], updated_at=None)
        result = W.import_archive(self.source, self.out)
        self.assertEqual(result["totals"]["material_revisions"], 2)
        conn = self.connect()
        self.assertEqual(W.query(conn, keyword="先觀測")["總筆數"], 1)
        receipts = [json.loads(r[0]) for r in conn.execute("SELECT receipt_json FROM ingest_receipts")]
        self.assertTrue(any("先後未知" in issue for r in receipts for issue in r["issues"]))

    def test_archive_only_promotes_scheduled_yna_cna_ids(self):
        row = item("YT:buGW2sCr_do", "YT")
        self.assertEqual(W.canonical_identity(row, "2026-09-30")[1], "strong")
        for day in ("2026-09-30", "2026-10-01"):
            self.put(day, [row])
        result = W.import_archive(self.source, self.out)
        self.assertEqual(result["totals"]["materials"], 2)
        self.assertEqual(result["possible_duplicate_count"], 1)
        self.assertTrue(all(r[0].startswith("legacy:") for r in self.connect().execute("SELECT material_id FROM materials")))

    def test_txt_only_missing_state_and_orphan_duplicate_are_visible(self):
        folder = self.source / "20260730"
        folder.mkdir()
        (folder / "0730晚班交接.txt").write_bytes(b"txt only")
        self.put("2026-07-31", [item()], suffix="(1)")
        result = W.import_archive(self.source, self.out)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["totals"], {})
        self.assertTrue(any("缺標準 state" in s["reason"] for s in result["skipped"]))
        self.assertTrue(any("缺標準對照" in e["reason"] for e in result["errors"]))

    def test_cli_uses_archive_subdirectory_and_leaves_phase0_untouched(self):
        from contextlib import redirect_stdout
        from io import StringIO
        self.put("2026-09-30", [item()])
        root = self.out.parent
        phase0 = root / "phase0"
        phase0.mkdir(parents=True)
        sentinel = phase0 / "warehouse.sqlite"
        sentinel.write_bytes(b"phase0 must stay byte-identical")
        with redirect_stdout(StringIO()):
            code = W.main(["--warehouse-root", str(root), "import-archive", "--archive-root", str(self.source)])
        self.assertEqual(code, 0)
        self.assertEqual(sentinel.read_bytes(), b"phase0 must stay byte-identical")
        with redirect_stdout(StringIO()) as stdout:
            code = W.main(["--warehouse-root", str(root), "--dataset", "archive", "query", "--source", "AP"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["總筆數"], 1)

    def test_interrupt_then_resume_and_row_conflicts_preserved(self):
        self.put("2026-09-30", [item(), item(raw_entry="同班同碼")])
        self.put("2026-10-01", [item()])
        original = W.import_bytes
        calls = []
        def interrupt(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return original(*args, **kwargs)
        with mock.patch.object(W, "import_bytes", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                W.import_archive(self.source, self.out)
        resumed = W.import_archive(self.source, self.out)
        self.assertTrue(resumed["processed"][0]["repeated"])
        self.assertEqual(resumed["totals"]["material_observations"], 3)
        self.assertEqual(resumed["shifts"][0]["conflict_preserved"], 1)

    def test_source_is_read_only_and_g_output_rejected(self):
        self.put("2026-09-30", [item()])
        before = {p.relative_to(self.source).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.source.rglob("*") if p.is_file()}
        original_open, original_mkdir = Path.open, Path.mkdir
        def guarded_open(path, mode="r", *args, **kwargs):
            if path.is_relative_to(self.source):
                self.assertEqual(mode, "rb", "來源只能 read_bytes")
            return original_open(path, mode, *args, **kwargs)
        def guarded_mkdir(path, *args, **kwargs):
            self.assertFalse(path.is_relative_to(self.source), "不可建立來源目錄")
            return original_mkdir(path, *args, **kwargs)
        with mock.patch.object(Path, "open", guarded_open), mock.patch.object(Path, "mkdir", guarded_mkdir):
            W.import_archive(self.source, self.out)
        after = {p.relative_to(self.source).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.source.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        for output in (self.source / "archive", Path(r"G:\輸出\archive"), self.root / "phase0"):
            with self.assertRaises(ValueError):
                W.import_archive(self.source, output)
        self.assertEqual(W.output_path(W.DEFAULT_ROOT, "archive").name, "archive")

    def test_bad_snapshot_and_window_mismatch_do_not_stop_other_shifts(self):
        bad = self.put("2026-09-30", [])
        bad.write_bytes(b"{broken")
        self.put("2026-10-01", [item()], window_start="2026-09-30 13:00")
        self.put("2026-10-02", [item(first_seen_checkpoint="1002-1700")])
        result = W.import_archive(self.source, self.out)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["errors"]), 2)
        self.assertEqual(result["totals"]["ingest_receipts"], 1)

    def test_unreadable_archive_creates_failure_report_not_empty_success(self):
        with mock.patch.object(W, "archive_inventory", side_effect=PermissionError("Access is denied")):
            result = W.import_archive(self.source, self.out)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["shift_count"], 0)
        self.assertFalse((self.out / "warehouse.sqlite").exists())
        self.assertIn("Access is denied", (self.out / "reports/archive-import.md").read_text(encoding="utf-8"))


class ImportQueryReportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)

    def conn(self):
        conn = W.connect_db(self.out / "warehouse.sqlite")
        self.addCleanup(conn.close)
        return conn

    def test_idempotency_raw_payload_notes_and_hash(self):
        rows = [item(), item("RT3656", "?", script_status="note", first_seen_checkpoint=None,
                             needs_review="重複，但無保留對象證據", arbitrary_field={"未知": 1})]
        raw = snapshot(rows)
        input_file = self.out / "input.json"
        input_file.write_bytes(raw)
        before_hash = W.sha(input_file.read_bytes())
        result = W.import_bytes(input_file.read_bytes(), self.out)
        self.assertEqual(result["內容筆數"], 1)
        self.assertEqual(result["備註筆數"], 1)
        receipt_bytes = next((self.out / "receipts").glob("*.json")).read_bytes()
        result = W.import_bytes(input_file.read_bytes(), self.out)
        self.assertTrue(result["重複匯入"])
        self.assertTrue(all(v == 0 for v in result["新增"].values()))
        self.assertEqual(before_hash, W.sha(input_file.read_bytes()))
        self.assertEqual(receipt_bytes, next((self.out / "receipts").glob("*.json")).read_bytes())
        conn = self.conn()
        self.assertEqual(conn.execute("SELECT snapshot_bytes FROM ingest_receipts").fetchone()[0], raw)
        disposition = conn.execute("SELECT * FROM candidate_dispositions").fetchone()
        self.assertEqual(disposition["quality"], "legacy_unresolved")
        self.assertEqual(disposition["disposition"], "unresolved")
        self.assertIsNone(disposition["retained_material_id"])
        payloads = [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM material_revisions")]
        self.assertIn(rows[1], payloads)
        self.assertEqual(W.query(conn)["總筆數"], 1)
        self.assertEqual(W.query(conn, include_notes=True)["總筆數"], 2)

    def test_query_date_range_source_keyword_tags_and_overlap(self):
        rows = [item(src_text="SCRIPT: SHOTLIST: ASSOCIATED PRESS Paris - 1 October 2026 1. Main\n"
                     "ASSOCIATED PRESS London - 30 September 2026 2. Main"),
                item("YNA-buGW2sCr_do", "YNA", platform={"video_id": "buGW2sCr_do", "published_at_utc": "2026-09-30T22:51:23Z"})]
        W.import_bytes(snapshot(rows), self.out)
        conn = self.conn()
        self.assertEqual(W.query(conn, "2026-09-30", "2026-09-30")["總筆數"], 1)
        self.assertEqual(W.query(conn, "2026-10-01", "2026-10-01")["總筆數"], 1)
        self.assertEqual(W.query(conn, "2026-10-01", "2026-10-01", overlap=True)["總筆數"], 2)
        self.assertEqual(W.query(conn, "2026-09-30", "2026-10-01", source="YNA", keyword="中文", t="政治", c="美國")["總筆數"], 1)
        self.assertEqual(W.query(conn, keyword="%' OR 1=1")["總筆數"], 0)
        page = W.query(conn, limit=1)
        self.assertEqual(page["下一頁"], 1)
        self.assertEqual(W.query(conn, limit=1, offset=1)["下一頁"], None)

    def test_quality_reports_markdown_and_json(self):
        W.import_bytes(snapshot([item(src_text="SCRIPT: SHOTLIST: ASSOCIATED PRESS Paris - 1 October 2026 1. Main\n"
                       "ASSOCIATED PRESS London - 30 September 2026 2. Main"), item("RT6431", "RT")]), self.out)
        report = W.report(self.out)
        self.assertEqual(report["ambiguous筆數"], 1)
        self.assertEqual(report["退路與未知筆數"], 1)
        value = json.loads((self.out / "reports/date-quality.json").read_text(encoding="utf-8"))
        self.assertEqual(len(value["同等主日期待重判"][0]["content_dates"]), 2)
        self.assertIn("最早日只是索引", (self.out / "reports/date-quality.md").read_text(encoding="utf-8"))

    def test_duplicate_local_id_and_bad_row_are_not_silently_dropped(self):
        raw = snapshot([item(), item(raw_entry="同碼不同稿"), {"source": "AP"}])
        result = W.import_bytes(raw, self.out)
        self.assertEqual(result["狀態"], "partial")
        conn = self.conn()
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0], 2)
        receipt = json.loads(conn.execute("SELECT receipt_json FROM ingest_receipts").fetchone()[0])
        self.assertEqual(len(receipt["quarantine"]), 2)
        self.assertIn(":ordinal:1", conn.execute("SELECT material_id FROM materials WHERE identity_status='provisional_conflict'").fetchone()[0])

    def test_schema_version_rejection_and_rollback(self):
        W.import_bytes(snapshot([item()]), self.out)
        conn = sqlite3.connect(self.out / "warehouse.sqlite")
        conn.execute("UPDATE warehouse_meta SET schema_version=99")
        conn.commit()
        conn.close()
        with self.assertRaisesRegex(ValueError, "版本不符"):
            W.import_bytes(snapshot([item()]), self.out)

    def test_unsupported_input_schema_and_invalid_json_create_no_db(self):
        value = json.loads(snapshot([item()]))
        value["schema_version"] = 99
        with self.assertRaisesRegex(ValueError, "輸入宣告"):
            W.import_bytes(json.dumps(value).encode(), self.out)
        with self.assertRaises(ValueError):
            W.import_bytes(b"{bad-json", self.out)
        self.assertFalse((self.out / "warehouse.sqlite").exists())

    def test_cli_rejects_other_input_before_io(self):
        from contextlib import redirect_stderr
        from io import StringIO
        with redirect_stderr(StringIO()) as errors:
            result = W.main(["--warehouse-root", str(self.out), "import", "--snapshot", r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\live.json"])
        self.assertEqual(result, 1)
        self.assertIn("只能讀指定", errors.getvalue())
        self.assertFalse((self.out / "phase0").exists())

    def test_second_different_snapshot_rejected(self):
        W.import_bytes(snapshot([item()]), self.out)
        with self.assertRaisesRegex(ValueError, "多班匯入"):
            W.import_bytes(snapshot([item(raw_entry="不同快照")]), self.out)
        self.assertEqual(self.conn().execute("SELECT COUNT(*) FROM ingest_receipts").fetchone()[0], 1)

    def test_txt_counts_provisional_and_render_sha_separate(self):
        raw = "0930 晚班交接\n時間窗\n收錄外電共1則（AP 1則／RT 0則／NS 0則／其他 0則） 側錄 0則".encode("utf-8")
        state = {"items": [item()], "last_render_sha": "不是txt雜湊"}
        result = W.txt_crosscheck(raw, state)
        self.assertTrue(result["general_count_matches"])
        self.assertFalse(result["last_render_sha_matches"])
        self.assertEqual(result["quality"], "provisional")

    def test_output_guard_rejects_live_drive_repo_and_inputs(self):
        for path in (r"G:\我的雲端硬碟\輸出", W.INPUT_ROOT, Path(W.__file__).parent):
            with self.assertRaises(ValueError):
                W.output_path(path)
        self.assertEqual(W.output_path(W.DEFAULT_ROOT).name, "phase0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
