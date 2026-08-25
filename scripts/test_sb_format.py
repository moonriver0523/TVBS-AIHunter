# -*- coding: utf-8 -*-
"""sb_format 的機械行為測試。

範例值全部取自 `common/00-寫稿通則.md` §4 與 `common/02-tc-offset-filename.md`
裡實際寫下的範例——測的是「有沒有照規則文件做」，不是「程式有沒有照自己做」。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sb_format import SB, fmt_tc, lint_sb, offset_from_filename, render_sb, tc_field  # noqa: E402


class TestOffset(unittest.TestCase):
    def test_六碼檔名解析成秒(self):
        # 02-tc-offset-filename.md 的範例：041628 → 04:16:28
        self.assertEqual(offset_from_filename("041628 某節目.mp4"), 4 * 3600 + 16 * 60 + 28)

    def test_八碼只取前六碼(self):
        self.assertEqual(offset_from_filename("06070812.mp4"), 6 * 3600 + 7 * 60 + 8)

    def test_全零與非數字都不偏移(self):
        self.assertEqual(offset_from_filename("000000 test.mp4"), 0)
        self.assertEqual(offset_from_filename("西國不敗1200 #01 RT.mp4"), 0)

    def test_不像時間碼的數字不當offset(self):
        # AP 素材編號那種純數字檔名不可誤判成 TC
        self.assertEqual(offset_from_filename("4671347.mp4"), 0)


class TestFmtTc(unittest.TestCase):
    def test_四碼六碼(self):
        self.assertEqual(fmt_tc(33, 4), "0033")
        self.assertEqual(fmt_tc(44, 4), "0044")
        self.assertEqual(fmt_tc(3600 + 4 * 60 + 52, 6), "010452")

    def test_秒到MMSS要過算式而不是照抄數字(self):
        # 00-寫稿通則 §4 記載的踩雷：第 225 秒不是 TC0225（＝2分25秒）
        self.assertEqual(fmt_tc(225, 4), "0345")

    def test_超出四碼範圍要報錯而不是靜默截斷(self):
        with self.assertRaises(ValueError):
            fmt_tc(100 * 60, 4)


class TestTcField(unittest.TestCase):
    def test_有編號素材(self):
        # 00-寫稿通則 §4 範例：#03 0033-0044
        self.assertEqual(tc_field("numbered", 33, 44, material_no="03"), "#03 0033-0044")

    def test_側錄素材要套offset且為六碼(self):
        # 範例 CNN 7/28 060900-060923，檔名 060656 → offset 06:06:56
        off = offset_from_filename("060656 CNN.mp4")
        self.assertEqual(
            tc_field("side", 124, 147, source="CNN", md="7/28", offset=off),
            "CNN 7/28 060900-060923",
        )

    def test_ctv純四碼無前綴(self):
        self.assertEqual(tc_field("ctv", 6, 13), "0006-0013")

    def test_plain有offset用六碼沒有用四碼(self):
        self.assertEqual(tc_field("plain", 33, 44), "0033-0044")
        self.assertEqual(
            tc_field("plain", 124, 147, offset=offset_from_filename("060656.mp4")),
            "060900-060923",
        )

    def test_訖點早於起點要報錯(self):
        with self.assertRaises(ValueError):
            tc_field("numbered", 44, 33, material_no="03")

    def test_側錄缺日期不可矇混輸出(self):
        with self.assertRaises(ValueError):
            tc_field("side", 1, 5, source="CNN", offset=100)


class TestRender(unittest.TestCase):
    def test_五行順序與內容(self):
        sb = SB(
            speaker="智利總統 卡斯特",
            zh="那些透過非法、不正規且秘密手段越境的人，遲早必須離開我們的國家。",
            tc="#03 0033-0044",
            original="Those who came in through the window in an illegal manner.",
        )
        lines = render_sb(sb).split("\n")
        self.assertEqual(lines[0], "SB")
        self.assertEqual(lines[1], "智利總統 卡斯特")
        self.assertEqual(lines[3], "#03 0033-0044")
        self.assertEqual(len(lines), 5)

    def test_中文多行合法且不被壓成一行(self):
        sb = SB(speaker="X Y", zh="第一行\n第二行", tc="0006-0013", original="Hello.")
        self.assertIn("第一行\n第二行", render_sb(sb))


class TestLint(unittest.TestCase):
    def _sb(self, **kw):
        base = dict(speaker="白宮記者 Kevin Liptak", zh="他們不必造成巨大破壞。",
                    tc="CNN 7/28 060900-060923", original="They do not have to cause damage.")
        base.update(kw)
        return SB(**base)

    def test_中文帶引號要FAIL(self):
        out = lint_sb(self._sb(zh="「他們不必造成巨大破壞」"))
        self.assertTrue(any("引號" in m and m.startswith("[FAIL]") for m in out))

    def test_原文帶引號要FAIL(self):
        out = lint_sb(self._sb(original='"They do not have to cause damage."'))
        self.assertTrue(any(m.startswith("[FAIL]") for m in out))

    def test_代名詞未補主詞要WARN(self):
        out = lint_sb(self._sb(zh="他知道防空資產短缺。", original="He knows there are shortages."))
        self.assertTrue(any("P-037" in m for m in out))

    def test_補了主詞就不再WARN(self):
        out = lint_sb(self._sb(zh="(普欽)知道防空資產短缺。", original="He knows there are shortages."))
        self.assertFalse(any("P-037" in m for m in out))

    def test_秒數門檻依P015(self):
        self.assertTrue(any(m.startswith("[FAIL]") for m in lint_sb(self._sb(), duration=1.5)))
        self.assertTrue(any(m.startswith("[WARN]") for m in lint_sb(self._sb(), duration=3.0)))
        self.assertEqual([m for m in lint_sb(self._sb(), duration=11.0) if "P-015" in m], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
