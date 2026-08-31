# -*- coding: utf-8 -*-
"""掐BITE 工作台的機械行為測試（不碰真實影片，用合成 ASR）。

真實素材的端到端驗證紀錄在
`common/plans/2026-08-24-S5至S8產線UI前台可行性評估.md` §十；
這裡測的是「規則有沒有被寫進程式」，尤其三條容易被寫壞的：

  1. 官方文稿優先於 ASR——輸出用字必須是官方稿，ASR 只供定位。
  2. 定位不可靠時**不自行猜測 TC**（`cnn/02`），要如實標記。
  3. 沒有官方引言標記 ≠ 沒有 BITE（`P-046`），仍要列出 ASR 段落並警告用字須核對。
  4. **全段落列出**（2026-08-25 需求修正）：秒數門檻、官方引言優先、25 秒
     上限一律降級為標籤——不丟行、不截斷、有官方稿時 ASR 段落照樣全列。
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bite_workbench as W  # noqa: E402


def fake_asr(pairs):
    segs = [{"start": a, "end": b, "text": t} for a, b, t in pairs]
    words = []
    for a, b, t in pairs:
        toks = t.split()
        step = (b - a) / max(len(toks), 1)
        for i, tok in enumerate(toks):
            words.append({"start": a + i * step, "end": a + (i + 1) * step, "text": tok})
    return {"segments": segs, "words": words}


SPEECH = [
    (0.0, 6.0, "every year hikers vanish in taiwan's mountains"),
    (10.0, 19.0, "the weather and combined with the terrain would be dangerous "
                 "but the most danger is actually the people themselves"),
    (30.0, 42.0, "huge relief like the adrenaline is still there and then in half a minute "
                 "my brain switched to survival mode how to actually get out"),
    (50.0, 55.0, "i'm mike valerio in beijing and this is cnn"),
]


class TestQuoteParsing(unittest.TestCase):
    def _write(self, text):
        fd, path = tempfile.mkstemp(suffix=".txt", text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_抽出SOUNDBITE並剝掉引號(self):
        p = self._write('SOUNDBITE (English) Jane Doe, analyst:\n"The market is broken."\n\nSTORY:\nbackground\n')
        q = W.parse_official_quotes(p)
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["text"], "The market is broken.")   # 00-寫稿通則 §4：原文不加引號
        self.assertEqual(q[0]["speaker_hint"], "Jane Doe, analyst")

    def test_STORY背景段不可被當成引言(self):
        # `06` 鐵則：STORY 是平面背景，裡面的話即使像 BITE 也不可當影音引言
        p = self._write('SOUNDBITE (English) A B:\n"Real quote."\n\nSTORY:\nHe said something quotable here.\n')
        q = W.parse_official_quotes(p)
        self.assertEqual([x["text"] for x in q], ["Real quote."])

    def test_沒有標記就回空清單(self):
        p = self._write("Man filming queue at petrol station in Sochi.\n")
        self.assertEqual(W.parse_official_quotes(p), [])


class TestLocate(unittest.TestCase):
    def test_官方引言定位到正確時間軸(self):
        asr = fake_asr(SPEECH)
        loc = W.locate_quote(
            "The weather combined with the terrain would be dangerous, "
            "but the most danger is actually the people themselves.",
            asr["words"], asr["segments"])
        self.assertIsNotNone(loc)
        self.assertAlmostEqual(loc["start"], 10.0, delta=2.0)
        self.assertGreater(loc["confidence"], 0.5)

    def test_粗顆粒來源不可跨段框出假TC(self):
        """字幕／分段來源（無詞級時間）時的回歸測試。

        2026-08-24 實測踩到：滑窗為了湊滿引言詞數，硬吃下鄰近另一段
        （該段剛好有個常用詞命中關鍵字），框出橫跨 172 秒的假 TC。
        真實情況是引言只在後面那一段裡。
        """
        coarse = {"segments": [
            {"start": 222.7, "end": 232.5,
             "text": "the weather combined with the terrain would be dangerous "
                     "but the most danger is actually the people themselves"},
            {"start": 384.5, "end": 395.0,
             "text": "huge relief the adrenaline is still there and then my brain "
                     "switched to survival mode"},
        ], "words": []}
        loc = W.locate_quote(
            "Huge relief, like the adrenaline is still there, and then in half a minute "
            "more my brain switched to survival mode, how to actually get out.",
            coarse["words"], coarse["segments"])
        self.assertIsNotNone(loc)
        self.assertAlmostEqual(loc["start"], 384.5, delta=1.0)
        self.assertLess(loc["end"] - loc["start"], 30)
        self.assertFalse(loc["granular"])   # 段落顆粒度要如實標示

    def test_對不上的引言不猜TC(self):
        asr = fake_asr(SPEECH)
        loc = W.locate_quote(
            "Inflation in Argentina accelerated beyond ninety percent last quarter.",
            asr["words"], asr["segments"])
        self.assertIsNone(loc)


class TestSegments(unittest.TestCase):
    QUOTE = {"speaker_hint": "Peter Navadny, volunteer", "marker": "SOUNDBITE",
             "text": "The weather combined with the terrain would be dangerous, "
                     "but the most danger is actually the people themselves."}

    def test_官方稿優先_輸出用官方字ASR只定位(self):
        segs = W.build_segments(fake_asr(SPEECH), [self.QUOTE])
        c = [s for s in segs if s.origin == "official"][0]
        self.assertIn("combined with the terrain", c.text)
        self.assertNotIn("and combined", c.text)          # 官方稿用字，不是 ASR 的
        self.assertIn("and combined", c.asr_text)         # ASR 原文保留在定位欄位
        self.assertGreater(c.end, c.start)
        self.assertIn("官方引言", c.tags)

    def test_有官方稿時ASR段落照樣全列(self):
        """2026-08-25 需求修正核心：官方引言只是標籤，不是過濾器。
        舊版 `if not quotes:` 會讓有官方稿的素材完全看不到其他段落。"""
        segs = W.build_segments(fake_asr(SPEECH), [self.QUOTE])
        asr_segs = [s for s in segs if s.origin == "asr"]
        self.assertEqual(len(asr_segs), len(SPEECH))       # 一段都不能少
        overlapped = [s for s in asr_segs if "與官方引言重疊" in s.tags]
        self.assertEqual(len(overlapped), 1)               # 對應段要標重疊

    def test_定位失敗要標記而不是給假TC(self):
        quotes = [{"speaker_hint": "X", "marker": "SOT",
                   "text": "Inflation in Argentina accelerated beyond ninety percent."}]
        segs = W.build_segments(fake_asr(SPEECH), quotes)
        c = [s for s in segs if s.origin == "official"][0]
        self.assertEqual((c.start, c.end), (0.0, 0.0))
        self.assertTrue(any("定位失敗" in f for f in c.flags))
        self.assertEqual(segs[0], c)                       # 排最前，一眼看到

    def test_無官方標記仍列ASR段落並警告用字(self):
        # P-046：社群 UGC 只有一行 caption，不代表沒有 BITE
        segs = W.build_segments(fake_asr(SPEECH), [])
        self.assertEqual(len(segs), len(SPEECH))
        self.assertTrue(all(s.origin == "asr" for s in segs))
        self.assertTrue(all(any("用字須自行核對" in f for f in s.flags) for s in segs))

    def test_短段落仍列出並帶標籤(self):
        """需求修正：8 秒以下不再丟掉，改標籤供 UI 篩選。"""
        segs = W.build_segments(fake_asr([(0.0, 3.0, "short line here")]), [])
        self.assertEqual(len(segs), 1)
        self.assertIn("<8秒", segs[0].tags)
        self.assertTrue(any("P-015" in f for f in segs[0].flags))  # 2–5 秒 WARN

    def test_超過25秒不截斷改標籤(self):
        """需求修正：25 秒上限不再替人截斷，改標籤＋警告。"""
        long = [(0.0, 40.0, " ".join(["word"] * 60))]
        s = W.build_segments(fake_asr(long), [])[0]
        self.assertAlmostEqual(s.duration, 40.0, delta=0.01)   # 起訖保持原樣
        self.assertIn(">25秒", s.tags)
        self.assertTrue(any("不替你截斷" in f for f in s.flags))

    def test_純交接語要標記但不靜默丟掉(self):
        segs = W.build_segments(fake_asr([(0.0, 12.0, "i'm mike valerio in beijing and this is cnn "
                                                      "reporting from the forbidden city today")]), [])
        self.assertEqual(len(segs), 1)                     # 仍然列出
        self.assertIn("疑似交接語", segs[0].tags)
        self.assertTrue(any("交接語" in f for f in segs[0].flags))


class TestTranslatePrompt(unittest.TestCase):
    def test_prompt含P037與禁引號規則(self):
        p = W.TRANSLATE_PROMPT
        for needle in ("P-037", "半形括號", "不加任何引號", "殘譯", "繁體中文"):
            self.assertIn(needle, p)

    def test_空原文直接報錯不打API(self):
        with self.assertRaises(ValueError):
            W.translate_zh("   ")

    def test_NLLB後處理_全形標點與固定譯名(self):
        self.assertEqual(
            W._zh_postprocess("特朗普總統說, 普京和澤連斯基應該儘快見面."),
            "川普總統說，普欽和澤倫斯基應該儘快見面。")

    def test_批次翻譯快取以段落文字為key掛回段落(self):
        segs = W.build_segments(fake_asr(SPEECH), [])
        W.attach_zh(segs, {segs[0].text: "測試譯文"})
        self.assertEqual(segs[0].zh, "測試譯文")
        self.assertIsNone(segs[1].zh)   # 沒翻過的維持 None，前端才知道要補

    def test_NLLB輸出必附殘譯警語(self):
        # 使用者裁定用 NLLB 的前提就是「加警語」——警語不見等於規格破功
        self.assertIn("殘譯", W.NLLB_WARNING)


class TestScanDir(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.d, ignore_errors=True))

    def _touch(self, name):
        open(os.path.join(self.d, name), "wb").close()

    def test_編號素材與文稿配對(self):
        self._touch("西國不敗1200 #03 RT.mp4")
        self._touch("西國不敗1200 #03 RT (外電文稿).txt")
        m = W.scan_dir(self.d)[0]
        self.assertEqual((m.kind, m.material_no), ("numbered", "03"))
        self.assertTrue(m.script_path.endswith("(外電文稿).txt"))

    def test_側錄檔名取offset與來源(self):
        self._touch("060656 CNN 整節.mp4")
        m = W.scan_dir(self.d)[0]
        self.assertEqual(m.kind, "side")
        self.assertEqual(m.source, "CNN")
        self.assertEqual(m.offset, 6 * 3600 + 6 * 60 + 56)

    def test_來源前綴側錄檔名取offset與日期(self):
        """實際命名 `{來源} {HHMMSS} {MMDD} {標題}`——6 碼不在開頭也要認得。
        交接文件 §四 明訂此檔 offset＝07:56:58。"""
        self._touch("CNN 075658 0817 增強藥專題.mp4")
        m = W.scan_dir(self.d)[0]
        self.assertEqual(m.kind, "side")
        self.assertEqual(m.source, "CNN")
        self.assertEqual(m.offset, 7 * 3600 + 56 * 60 + 58)
        self.assertEqual(m.md, "8/17")

    def test_ASR旁路檔不會被誤認成文稿(self):
        self._touch("某片 #01 AP.mp4")
        self._touch("某片 #01 AP ASR.json")
        m = W.scan_dir(self.d)[0]
        self.assertIsNone(m.script_path)


class TestPrecutStatusPayload(unittest.TestCase):
    CACHED = {
        "source": "SIDE",
        "offset_sec": 28618,
        "mtime": 2000.0,
        "segments": [{"id": "cached", "topic": "存回後"}],
    }

    def test_error加快取仍回error(self):
        job = {"state": "error", "error": "ffmpeg failed"}
        out = W.precut_status_payload(job, self.CACHED, False)
        self.assertEqual(out["state"], "error")
        self.assertEqual(out["error"], "ffmpeg failed")
        self.assertNotEqual(out.get("segments"), self.CACHED["segments"])

    def test_running忽略快取(self):
        job = {"state": "running", "phase": "OCR", "started": 1000.0}
        out = W.precut_status_payload(job, self.CACHED, False, now=1005.0)
        self.assertEqual(out["state"], "running")
        self.assertEqual(out["phase"], "OCR")
        self.assertEqual(out["elapsed"], 5.0)
        self.assertNotIn("started", out)
        self.assertNotIn("segments", out)

    def test_done記憶體舊段改讀快取(self):
        job = {
            "state": "done",
            "phase": "完成",
            "segments": [{"id": "stale-mem", "topic": "分析當下"}],
        }
        out = W.precut_status_payload(job, self.CACHED, False)
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["segments"], self.CACHED["segments"])
        self.assertEqual(out["stale"], False)

    def test_無job有快取回done(self):
        out = W.precut_status_payload(None, self.CACHED, True)
        self.assertEqual(out["state"], "done")
        self.assertEqual(out["phase"], "快取")
        self.assertEqual(out["stale"], True)
        self.assertEqual(out["segments"], self.CACHED["segments"])

    def test_無job無快取回none(self):
        self.assertEqual(W.precut_status_payload(None, None, False), {"state": "none"})


class TestResolveDroppedDir(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.root = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.d = os.path.join(self.root, "0830素材")
        os.makedirs(self.d)
        open(os.path.join(self.d, "CNN 170025.mp4"), "wb").close()

    def test_資料夾名反查(self):
        got = W.resolve_dropped_dir("0830素材", [], [self.root])
        self.assertEqual(got, self.d)

    def test_檔名驗證擋同名撞衫(self):
        other = os.path.join(self.root, "另一區", "0830素材")
        os.makedirs(other)
        # 兩個候選根都有同名資料夾，只有含指定檔案的那個算數
        roots = [os.path.join(self.root, "另一區"), self.root]
        got = W.resolve_dropped_dir("0830素材", ["CNN 170025.mp4"], roots)
        self.assertEqual(got, self.d)

    def test_拖單檔用檔名找資料夾(self):
        got = W.resolve_dropped_dir(None, ["CNN 170025.mp4"], [self.root, self.d])
        self.assertEqual(got, self.d)

    def test_找不到回None(self):
        self.assertIsNone(W.resolve_dropped_dir("不存在", [], [self.root]))
        self.assertIsNone(W.resolve_dropped_dir(None, [], [self.root]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
