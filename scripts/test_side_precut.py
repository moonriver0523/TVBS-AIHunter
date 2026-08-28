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


if __name__ == "__main__":
    unittest.main(verbosity=2)
