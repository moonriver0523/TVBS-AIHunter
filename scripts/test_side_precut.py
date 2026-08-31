# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import side_precut as P  # noqa: E402
import bite_workbench as W  # noqa: E402


class TestKinds(unittest.TestCase):
    def test_五類中英對照齊(self):
        self.assertEqual(P.KINDS, {
            "ad": "廣告", "anchor": "主播", "reporter": "記者",
            "interview": "訪問", "other": "其他",
        })


class TestTopicZh(unittest.TestCase):
    def test_短代碼與中文不送翻(self):
        self.assertFalse(P.looks_english("MD"))
        self.assertFalse(P.looks_english("CNN"))
        self.assertFalse(P.looks_english("驗收仍在-重選"))
        self.assertFalse(P.looks_english(""))
        self.assertTrue(P.looks_english("HIGHLIGHT CNN"))
        self.assertTrue(P.looks_english("THE CNN- WHOLE STORY"))

    def test_套用對照表只改英文主題(self):
        segs = [
            P.PrecutSeg("s1", 0, 1, "anchor", topic="HIGHLIGHT CNN"),
            P.PrecutSeg("s2", 1, 2, "anchor", topic="MD"),
        ]
        P.apply_topic_zh(segs, {"HIGHLIGHT CNN": "CNN精華"})
        self.assertEqual(segs[0].topic, "CNN精華")
        self.assertEqual(segs[1].topic, "MD")

    def test_字卡對照成繁中(self):
        self.assertIn("全記錄", P.topic_from_ocr("THE CNN- WHOLE STORY"))
        self.assertEqual(P.topic_from_ocr("HIGHLIGHT CNN"), "精華")
        self.assertEqual(P.topic_from_ocr("HIGHLIGHT 30 CNN SECONDS OF CALM"), "精華")
        zh = P.topic_from_ocr("ISOBELYEUNG MD CNNINTERNATIONALCORRESPONDENT")
        self.assertIn("伊莎貝·楊", zh)
        self.assertIn("國際特派", zh)
        blob = P.topic_from_ocr(
            'THEWHOLESTORY LIVE "STACKED:INSIDETHEENHANCEMENTCRAZE"'
            "PREMIERESTONIGHTAT8PM"
        )
        self.assertIn("全記錄", blob)
        self.assertIn("整形熱潮", blob)
        self.assertIn("今晚首播", blob)
        news = P.topic_from_ocr(
            "U.S.-CANADATRADEWAR LIVE CANADA DETAILS RETALIATORY TARIFFS CNNNEWSROOM"
        )
        self.assertIn("美加貿易戰", news)
        self.assertIn("新聞室", news)
        self.assertIn("現場", news)
        self.assertNotIn("KOSPI", P.topic_from_ocr("LIVE KOSPI 65.47 CNN NEWSROOM"))
        self.assertIn("美國大選", P.topic_from_ocr("AMERICA'SCHOICE LIVE DARLINE GRAHAM CNN NEWSROOM"))
        self.assertEqual(P.topic_from_ocr("Call to Earth NND"), "地球呼叫")
        news2 = P.topic_from_ocr(
            "LIVE CN DIRECTOROFCOMMUNICATIONS HAVE BEEN PLACED ON LEAVE CNNNEWSROOM"
        )
        self.assertIn("現場", news2)
        self.assertIn("新聞室", news2)
        self.assertIn("DIRECTOROFCOMMUNICATIONS", news2)
        self.assertIn("LEAVE", news2)

    def test_已是中文的主題不覆蓋(self):
        segs = [P.PrecutSeg("s1", 0, 1, "reporter", topic="驗收仍在-重選", ocr="CNN KOSPIA 164.60")]
        P.apply_topic_zh(segs)
        self.assertEqual(segs[0].topic, "驗收仍在-重選")

    def test_手改短主題不被洗成空字串(self):
        # 使用者手改的主題若推導不出東西（zh 為空），要保留原值，不能清空
        segs = [P.PrecutSeg("s1", 0, 1, "anchor", topic="X", ocr="")]
        P.apply_topic_zh(segs, nllb=False)
        self.assertEqual(segs[0].topic, "X")

    def test_NLLB殘譯被字卡對照蓋掉(self):
        segs = [P.PrecutSeg("s1", 0, 1, "anchor", topic="美國CNN", ocr="HIGHLIGHT CNN")]
        P.apply_topic_zh(segs)
        self.assertEqual(segs[0].topic, "精華")


class TestMasterTc(unittest.TestCase):
    def test_檔內秒加offset成六碼(self):
        off = 7 * 3600 + 56 * 60 + 58  # 075658
        self.assertEqual(P.master_tc(0, off), "075658")
        self.assertEqual(P.master_tc(66, off), "075804")  # +1:06


class TestScanDirOffsetNotNaive(unittest.TestCase):
    """規格硬規定：不可對完整『CNN 075658 …』檔名只呼叫 offset_from_filename。"""
    def test_scan_dir給正確offset(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        open(os.path.join(d, "CNN 075658 0817 增強藥專題.mp4"), "wb").close()
        m = W.scan_dir(d)[0]
        self.assertEqual(m.offset, 7 * 3600 + 56 * 60 + 58)
        self.assertEqual(m.source, "CNN")


class TestExportName(unittest.TestCase):
    def test_檔名含來源母帶TC類型主題(self):
        seg = P.PrecutSeg(id="s1", t0=66.0, t1=120.0, kind="anchor", topic="增強藥")
        off = 7 * 3600 + 56 * 60 + 58
        self.assertEqual(
            P.export_filename("CNN", seg, off),
            "CNN 075804-075858 主播 增強藥.mp4",
        )

    def test_主題空白不留多餘空白(self):
        seg = P.PrecutSeg(id="s1", t0=0, t1=10, kind="ad", topic="")
        name = P.export_filename("CNN", seg, 0)
        self.assertEqual(name, "CNN 000000-000010 廣告.mp4")
        self.assertNotIn("  .", name)

    def test_檔名非法字元清掉(self):
        # Controller: delete illegal chars (not replace with space) → "ABCx"
        self.assertEqual(P.sanitize_filename_part('A/B:C*?"<>|x'), "ABCx")

    def test_輸出資料夾是檔名加初處理(self):
        p = r"D:\TVBS\CNN\CNN 075658 0817 增強藥專題.mp4"
        self.assertEqual(
            P.export_dir(p),
            r"D:\TVBS\CNN\CNN 075658 0817 增強藥專題 初處理",
        )


FFMPEG_SILENCE = """
[silencedetect @ 000] silence_start: 10.0
[silencedetect @ 000] silence_end: 10.8 | silence_duration: 0.8
[silencedetect @ 000] silence_start: 40.0
[silencedetect @ 000] silence_end: 45.0 | silence_duration: 5.0
[silencedetect @ 000] silence_start: 90.0
[silencedetect @ 000] silence_end: 91.2 | silence_duration: 1.2
"""


class TestSilence(unittest.TestCase):
    def test_parse兩端時間(self):
        sil = P.parse_silencedetect(FFMPEG_SILENCE)
        self.assertEqual(sil, [(10.0, 10.8), (40.0, 45.0), (90.0, 91.2)])

    def test_短氣口合併長靜音切開(self):
        # duration=100；0.8s 與 1.2s 氣口併掉，5s 切開
        blocks = P.speech_blocks(100.0, [(10.0, 10.8), (40.0, 45.0), (90.0, 91.2)])
        self.assertEqual(len(blocks), 2)
        self.assertAlmostEqual(blocks[0][0], 0.0)
        self.assertAlmostEqual(blocks[0][1], 40.0)
        self.assertAlmostEqual(blocks[1][0], 45.0)
        self.assertAlmostEqual(blocks[1][1], 100.0)

    def test_沒有靜音就是整段(self):
        self.assertEqual(P.speech_blocks(50.0, []), [(0.0, 50.0)])


class TestSplitLongBlocks(unittest.TestCase):
    def test_短段落不動也不叫OCR(self):
        calls = []

        def ocr_of(t):
            calls.append(t)
            return "不該被呼叫"

        out = P.split_long_blocks([(0.0, 15.0)], ocr_of)
        self.assertEqual(out, [(0.0, 15.0)])
        self.assertEqual(calls, [])

    def test_長段落依字卡變化切開(self):
        # 60 秒的段落，broadcast 內容其實換了兩次主題但中間都沒有靜音
        topics_by_time = {
            5.0: "INSIDE AFRICA",
            20.0: "INSIDE AFRICA",
            35.0: "HIGHLIGHT",
            50.0: "HIGHLIGHT",
            59.5: "MORNING ROUNDUP",
        }

        def ocr_of(t):
            # 取最接近的取樣點對應主題（模擬固定字卡文字）
            key = min(topics_by_time, key=lambda k: abs(k - t))
            return topics_by_time[key]

        out = P.split_long_blocks(
            [(0.0, 60.0)], ocr_of, max_span=20.0, step=15.0,
        )
        self.assertGreater(len(out), 1)
        self.assertAlmostEqual(out[0][0], 0.0)
        self.assertAlmostEqual(out[-1][1], 60.0)
        # 涵蓋整段、無重疊無縫隙
        for (a1, b1), (a2, b2) in zip(out, out[1:]):
            self.assertAlmostEqual(b1, a2)

    def test_長段落但字卡沒變不切(self):
        def ocr_of(t):
            return "同一張字卡"

        out = P.split_long_blocks([(0.0, 60.0)], ocr_of, max_span=20.0, step=15.0)
        self.assertEqual(out, [(0.0, 60.0)])


class TestClassify(unittest.TestCase):
    def test_無字高音量偏廣告(self):
        self.assertEqual(
            P.classify_kind(rms=0.4, ocr="", duration=20, near_black=False),
            "ad",
        )

    def test_無字但兩頭黑也偏廣告(self):
        self.assertEqual(
            P.classify_kind(rms=0.05, ocr="", duration=25, near_black=True),
            "ad",
        )

    def test_有字卡預設主播(self):
        self.assertEqual(
            P.classify_kind(rms=0.1, ocr="BREAKING NEWS", duration=40, near_black=False),
            "anchor",
        )

    def test_記者關鍵字(self):
        self.assertEqual(
            P.classify_kind(rms=0.1, ocr="CNN's Jane Doe", duration=30, near_black=False),
            "reporter",
        )

    def test_其餘無字是other(self):
        self.assertEqual(
            P.classify_kind(rms=0.05, ocr="", duration=8, near_black=False),
            "other",
        )


class TestMergeTopics(unittest.TestCase):
    def test_相鄰同主題非廣告合併(self):
        segs = [
            P.PrecutSeg("s1", 0, 10, "anchor", topic="增強藥", ocr="增強藥"),
            P.PrecutSeg("s2", 10, 20, "anchor", topic="增強藥", ocr="增強藥"),
            P.PrecutSeg("s3", 20, 30, "ad", topic=""),
        ]
        out = P.merge_topic_runs(segs)
        self.assertEqual(len(out), 2)
        self.assertEqual((out[0].t0, out[0].t1, out[0].kind), (0, 20, "anchor"))
        self.assertEqual(out[1].kind, "ad")

    def test_廣告不與兩邊合併(self):
        segs = [
            P.PrecutSeg("a", 0, 10, "anchor", topic="A"),
            P.PrecutSeg("b", 10, 20, "ad", topic="A"),
            P.PrecutSeg("c", 20, 30, "anchor", topic="A"),
        ]
        self.assertEqual(len(P.merge_topic_runs(segs)), 3)


class TestCacheAndAnalyze(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.d, ignore_errors=True))
        self.vid = os.path.join(self.d, "CNN 075658 0817 增強藥專題.mp4")
        open(self.vid, "wb").close()

    def test_旁路檔名(self):
        self.assertTrue(P.cache_path(self.vid).endswith("CNN 075658 0817 增強藥專題 PRECUT.json"))

    def test_存讀往返(self):
        segs = [P.PrecutSeg("s1", 0, 10, "anchor", topic="X")]
        P.save_cache(self.vid, 28618, segs, mtime=1)
        data = P.load_cache(self.vid)
        self.assertEqual(data["offset_sec"], 28618)
        self.assertEqual(data["segments"][0]["topic"], "X")
        self.assertEqual(data["segments"][0]["tc0"], "075658")

    def test_mtime更新算stale(self):
        P.save_cache(self.vid, 0, [], mtime=1)
        self.assertTrue(P.cache_stale(self.vid, {"mtime": 1, "segments": []}))
        # 檔案 mtime 一定 ≥1；明確用比較：cache mtime 小於真實 mtime → stale
        cache = P.load_cache(self.vid)
        cache["mtime"] = 0
        self.assertTrue(P.cache_stale(self.vid, cache))

    def test_分析預設不翻譯只有OCR英文原字(self):
        stderr = (
            "[silencedetect] silence_start: 20.0\n"
            "[silencedetect] silence_end: 28.0 | silence_duration: 8.0\n"
        )
        called = []
        orig_nllb = P.nllb_map
        P.nllb_map = lambda texts, run=None: (called.append(texts) or {})
        try:
            data = P.analyze(
                self.vid, offset_sec=0, duration=60.0,
                run_silence=lambda p: stderr,
                rms_of=lambda a, b: 0.05,
                ocr_of=lambda t: "BREAKING NEWS TONIGHT",
                black_of=lambda a, b: False,
                zh_of=None,
            )
        finally:
            P.nllb_map = orig_nllb
        self.assertEqual(called, [])
        self.assertIn("BREAKING", data["segments"][0]["topic"])

    def test_translate_cache手動翻譯已存在的快取(self):
        segs = [P.PrecutSeg("s1", 0, 10, "anchor", topic="HIGHLIGHT CNN", ocr="HIGHLIGHT CNN")]
        P.save_cache(self.vid, 0, segs, mtime=1)
        orig_nllb = P.nllb_map
        P.nllb_map = lambda texts, run=None: {t: "精華" for t in texts}
        try:
            data = P.translate_cache(self.vid, 0)
        finally:
            P.nllb_map = orig_nllb
        self.assertIn("精華", data["segments"][0]["topic"])

    def test_translate_cache沒快取就報錯(self):
        with self.assertRaises(FileNotFoundError):
            P.translate_cache(self.vid, 0)

    def test_分析用注入假靜音與OCR(self):
        stderr = (
            "[silencedetect] silence_start: 20.0\n"
            "[silencedetect] silence_end: 28.0 | silence_duration: 8.0\n"
        )
        def ocr_of(t):
            return "" if t >= 24 else "BREAKING"
        out = P.analyze(
            self.vid, offset_sec=28618, duration=60.0,
            run_silence=lambda p: stderr,
            rms_of=lambda a, b: 0.4 if a >= 20 else 0.05,
            ocr_of=ocr_of,
            black_of=lambda a, b: False,
        )
        kinds = [s["kind"] for s in out["segments"]]
        self.assertIn("anchor", kinds)
        self.assertIn("ad", kinds)
        self.assertEqual(out["offset_sec"], 28618)

    def test_copy與精準命令(self):
        seg = P.PrecutSeg("s1", 10.0, 20.0, "anchor")
        copy = P.cut_cmd("in.mp4", seg, "out.mp4", accurate=False)
        self.assertIn("-c", copy)
        self.assertIn("copy", copy)
        acc = P.cut_cmd("in.mp4", seg, "out.mp4", accurate=True)
        self.assertTrue(any(x in acc for x in ("libx264", "crf")))
        self.assertNotIn("copy", acc)

    def test_waveform分桶取max(self):
        pts = P.waveform_points([0.1, 0.9, 0.2, 0.3], buckets=2)
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[0], 0.9)
        self.assertAlmostEqual(pts[1], 0.3)


class TestAdapters(unittest.TestCase):
    def test_沒裝OCR時require會說明怎麼裝(self):
        # 用注入：把 _ocr_mod 設成 None
        old = getattr(P, "_ocr_mod", "missing")
        P._ocr_mod = None
        self.addCleanup(lambda: setattr(P, "_ocr_mod", old) if old != "missing" else None)
        with self.assertRaises(FileNotFoundError) as ctx:
            P.require_ocr()
        self.assertIn("rapidocr-onnxruntime", str(ctx.exception))

    def test_export非廣告略過ad(self):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            class R:
                returncode = 0
                stderr = ""
            return R()
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        vid = os.path.join(d, "CNN 075658 x.mp4")
        open(vid, "wb").close()
        segs = [
            P.PrecutSeg("s1", 0, 10, "ad", selected=False),
            P.PrecutSeg("s2", 10, 20, "anchor", topic="主題", selected=True),
        ]
        paths = P.export_segs(
            vid, segs, mode="non_ad", accurate=False,
            source="CNN", offset_sec=0, run=fake_run,
        )
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].endswith("CNN 000010-000020 主播 主題.mp4"))
        self.assertEqual(len(calls), 1)

    def test_export只出勾選_單段直接剪不用合併(self):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            class R:
                returncode = 0
            return R()
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        vid = os.path.join(d, "a.mp4")
        open(vid, "wb").close()
        segs = [
            P.PrecutSeg("s1", 0, 5, "anchor", selected=False),
            P.PrecutSeg("s2", 5, 9, "ad", selected=True),
        ]
        paths = P.export_segs(
            vid, segs, mode="selected", accurate=True,
            source="CNN", offset_sec=0, run=fake_run,
        )
        self.assertEqual(len(paths), 1)
        self.assertTrue(os.path.basename(paths[0]).startswith("CNN 000005 合併"))
        self.assertEqual(len(calls), 1)

    def test_export只出勾選_自訂檔名(self):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            class R:
                returncode = 0
            return R()
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        vid = os.path.join(d, "a.mp4")
        open(vid, "wb").close()
        segs = [P.PrecutSeg("s1", 0, 5, "anchor", selected=True)]
        paths = P.export_segs(
            vid, segs, mode="selected", accurate=True,
            source="CNN", offset_sec=0, filename="我的片段", run=fake_run,
        )
        # 自訂檔名要保留「來源＋起始TC」字首，不能整段被自訂名蓋掉
        self.assertEqual(os.path.basename(paths[0]), "CNN 000000 我的片段.mp4")

    def test_export只出勾選_自訂檔名已帶副檔名不重複加(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        vid = os.path.join(d, "a.mp4")
        open(vid, "wb").close()
        segs = [P.PrecutSeg("s1", 0, 5, "anchor", selected=True)]
        paths = P.export_segs(
            vid, segs, mode="selected", accurate=True,
            source="CNN", offset_sec=0, filename="片段.mp4",
            run=lambda *a, **k: type("R", (), {"returncode": 0})(),
        )
        self.assertEqual(os.path.basename(paths[0]), "CNN 000000 片段.mp4")

    def test_export只出勾選_檔名空白等同自動命名(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        vid = os.path.join(d, "a.mp4")
        open(vid, "wb").close()
        segs = [P.PrecutSeg("s1", 0, 5, "anchor", selected=True)]
        paths = P.export_segs(
            vid, segs, mode="selected", accurate=True,
            source="CNN", offset_sec=0, filename="   ",
            run=lambda *a, **k: type("R", (), {"returncode": 0})(),
        )
        self.assertTrue(os.path.basename(paths[0]).startswith("CNN 000000 合併"))

    def test_export只出勾選_多段合併成一支(self):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            class R:
                returncode = 0
            return R()
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        vid = os.path.join(d, "a.mp4")
        open(vid, "wb").close()
        segs = [
            P.PrecutSeg("s1", 0, 5, "anchor", selected=True),
            P.PrecutSeg("s2", 5, 9, "ad", selected=False),
            P.PrecutSeg("s3", 9, 15, "anchor", selected=True),
        ]
        paths = P.export_segs(
            vid, segs, mode="selected", accurate=False,
            source="CNN", offset_sec=0, run=fake_run,
        )
        self.assertEqual(len(paths), 1)
        # 檔名只帶起始 TC（第一個勾選段 s1 的 t0=0），不是每段的區間
        self.assertTrue(os.path.basename(paths[0]).startswith("CNN 000000 合併"))
        # 兩段各剪一次 + 最後 concat 一次
        self.assertEqual(len(calls), 3)
        self.assertIn("-f", calls[-1])
        self.assertIn("concat", calls[-1])
        # accurate=False 也要被合併模式蓋成精準重編——不精準剪法遇到片段沒跨到
        # keyframe 會整段沒有影像，合併起來就是壞檔（實測重現過）。
        self.assertIn("libx264", calls[0])
        self.assertIn("libx264", calls[1])

    def test_export只出勾選_沒勾就不輸出(self):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        vid = os.path.join(d, "a.mp4")
        open(vid, "wb").close()
        segs = [P.PrecutSeg("s1", 0, 5, "anchor", selected=False)]
        paths = P.export_segs(
            vid, segs, mode="selected", accurate=False,
            source="CNN", offset_sec=0, run=lambda *a, **k: None,
        )
        self.assertEqual(paths, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
