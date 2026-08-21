# -*- coding: utf-8 -*-
"""P0 歷史交接語料解析與統計工具的迴歸測試。

用法：python scripts/test_s2_p0_history.py
"""
import io
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import s2_p0_history as history  # noqa: E402


class ParseDocumentTextTests(unittest.TestCase):
    def test_保留大分類中主題小分題與素材的文件順序(self):
        text = """======財經======
【市場】
美股收黑
AP001 美股下跌。<無BITE>
+
美股反彈
RT002 美股回升。<無BITE>
======體育======
【美國體育】
NBA季後賽
AP003 球隊晉級。<無BITE>
"""

        document = history.parse_document_text(
            text, date="0802", group="AI 對照組", phase="0802–0811"
        )

        self.assertEqual(document["date"], "0802")
        self.assertEqual(document["category_order"], ["財經", "體育"])
        self.assertEqual(
            [category["name"] for category in document["categories"]], ["財經", "體育"]
        )
        market = document["categories"][0]["topics"][0]
        self.assertEqual(market["name"], "市場")
        self.assertEqual(
            [subtopic["name"] for subtopic in market["subtopics"]], ["美股收黑", "美股反彈"]
        )
        self.assertEqual(market["subtopics"][0]["items"][0]["text"], "AP001 美股下跌。<無BITE>")
        self.assertEqual(market["subtopics"][0]["items"][0]["line_number"], 4)
        self.assertEqual(document["diagnostics"], [])

    def test_舊式純文字中主題保留素材與行號(self):
        text = """======財經======
美股
AP001 指數下跌。<無BITE>
第二行素材內容。

外匯
RT002 日圓走升。<無BITE>
"""

        document = history.parse_document_text(
            text, date="0501", group="人工交接", phase="0501–0521"
        )

        topics = document["categories"][0]["topics"]
        self.assertEqual([topic["name"] for topic in topics], ["美股", "外匯"])
        self.assertEqual(topics[0]["items"], [
            {"text": "AP001 指數下跌。<無BITE>", "line_number": 3},
            {"text": "第二行素材內容。", "line_number": 4},
        ])

    def test_空分類與未辨識行產出診斷(self):
        text = """交接前言
======空格======
======國際======
【外交】
伊朗局勢
AP001 外交消息。<無BITE>
"""

        document = history.parse_document_text(
            text, date="0802", group="AI 對照組", phase="0802–0811"
        )

        self.assertEqual(document["unrecognized_lines"], [{"text": "交接前言", "line_number": 1}])
        self.assertEqual(
            [(diagnostic["kind"], diagnostic["line_number"]) for diagnostic in document["diagnostics"]],
            [("未辨識行", 1), ("空分類", 2)],
        )
        self.assertTrue(document["categories"][0]["is_empty"])
        self.assertFalse(document["categories"][1]["is_empty"])

    def test_首個大分類前的人工主題與素材另存未指定大分類內容(self):
        text = """范斯美中臺
RT2262 第一筆素材
+講關稅
RT2234 第二筆素材
+講烏俄
RT2236 第三筆素材
======大陸======
人民幣
RT3000 正文素材
"""

        document = history.parse_document_text(
            text, date="0507", group="人工交接", phase="0501–0521"
        )

        section = document["unscoped_sections"]
        self.assertEqual(section["kind"], "未指定大分類內容")
        self.assertEqual([topic["name"] for topic in section["topics"]], ["范斯美中臺"])
        topic = section["topics"][0]
        self.assertEqual(topic["items"], [{"text": "RT2262 第一筆素材", "line_number": 2}])
        self.assertEqual(
            [(subtopic["name"], subtopic["line_number"]) for subtopic in topic["subtopics"]],
            [("講關稅", 3), ("講烏俄", 5)],
        )
        self.assertEqual(topic["subtopics"][0]["items"], [
            {"text": "RT2234 第二筆素材", "line_number": 4}
        ])
        self.assertEqual(document["category_order"], ["大陸"])
        self.assertNotIn("范斯美中臺", [topic["name"] for topic in document["categories"][0]["topics"]])
        statistics = history.build_statistics([document], keyword_topics={})
        self.assertEqual(statistics["periods"]["人工 合併總表"]["topic_names"], ["人民幣"])
        self.assertEqual(document["unrecognized_lines"], [])

    def test_未指定大分類內容支援獨立加號後的小分題(self):
        text = """地震主題
+
災情更新
IN-21SU 第一筆素材
======國際======
外交
AP001 正文素材
"""

        document = history.parse_document_text(
            text, date="0608", group="人工交接", phase="0527–0626"
        )

        topic = document["unscoped_sections"]["topics"][0]
        self.assertEqual(topic["items"], [])
        self.assertEqual(topic["subtopics"], [{
            "name": "災情更新",
            "line_number": 3,
            "items": [{"text": "IN-21SU 第一筆素材", "line_number": 4}],
        }])

    def test_未指定大分類內容支援一行敘述素材後接代碼素材(self):
        text = """哥國強震 (等畫面)
南美洲國家發生規模6.3強震，震央位於首都東方約60公里，屬於淺層地震。
IN-21SU 地震後民眾就地避難
======國際======
外交
AP001 正文素材
"""

        document = history.parse_document_text(
            text, date="0608", group="人工交接", phase="0527–0626"
        )

        topic = document["unscoped_sections"]["topics"][0]
        self.assertEqual(topic["name"], "哥國強震 (等畫面)")
        self.assertEqual([item["line_number"] for item in topic["items"]], [2, 3])
        self.assertEqual(document["unrecognized_lines"], [])

    def test_未知前言與備忘不得因後方素材被整包升格(self):
        text = """未知前言
未知備忘
RT123 素材
======國際======
外交
AP001 正文素材
"""

        document = history.parse_document_text(
            text, date="0501", group="人工交接", phase="0501–0521"
        )

        self.assertEqual(document["unscoped_sections"]["topics"], [])
        self.assertEqual(document["unrecognized_lines"], [
            {"text": "未知前言", "line_number": 1},
            {"text": "未知備忘", "line_number": 2},
            {"text": "RT123 素材", "line_number": 3},
        ])

    def test_AI_檔頭_metadata_與重大索引不灌入正文素材計數(self):
        text = """0802 晚班交接
時間窗：2026-08-02 14:00–2026-08-03 09:00（約19hrs）
收錄外電共1則（AP 1則）
標記：▲=新增
🔴 重大：▲ AP4676262 重大摘要
======國際======
【安全】
炸彈攻擊
AP4676262 正文素材
"""

        document = history.parse_document_text(
            text, date="0802", group="AI 對照組", phase="0802–0811"
        )

        self.assertEqual([entry["kind"] for entry in document["header_metadata"]], [
            "文件名", "時間窗", "總數", "標記圖例"
        ])
        self.assertEqual(document["header_highlights"], [{
            "text": "🔴 重大：▲ AP4676262 重大摘要",
            "line_number": 5,
            "marker": "▲",
            "material_code": "AP4676262",
            "summary": "重大摘要",
        }])
        topic = document["categories"][0]["topics"][0]
        self.assertEqual(history._topic_item_count(topic), 1)
        statistics = history.build_statistics([document], keyword_topics={})
        self.assertEqual(
            statistics["periods"]["AI 對照組 0802–0811"]["topic_item_count_distribution"],
            {1: 1},
        )
        self.assertEqual(document["unrecognized_lines"], [])

    def test_檔頭白名單註記保留原因而未知行仍阻塞(self):
        text = """Microsoft Sans Serif;
;;;;
AP叫錄【北約川普】 川普記者會
無法分類的未知前言
======國際======
外交
AP001 正文素材
"""

        document = history.parse_document_text(
            text, date="0625", group="人工交接", phase="0527–0626"
        )

        self.assertEqual(
            [(entry["line_number"], entry["reason"]) for entry in document["ignored_lines"]],
            [(1, "RTF 字型表殘屑"), (2, "純分隔殘屑"), (3, "錄帶／傳送註記")],
        )
        self.assertEqual(document["unrecognized_lines"], [
            {"text": "無法分類的未知前言", "line_number": 4}
        ])

    def test_單一未知前言加一則素材不得升格為未指定大分類(self):
        text = """單一未知前言
RT123 素材
======國際======
外交
AP001 正文素材
"""

        document = history.parse_document_text(
            text, date="0501", group="人工交接", phase="0501–0521"
        )

        self.assertEqual(document["unscoped_sections"]["topics"], [])
        self.assertEqual(document["unrecognized_lines"], [
            {"text": "單一未知前言", "line_number": 1},
            {"text": "RT123 素材", "line_number": 2},
        ])

    def test_找不到正文的重大索引要列orphan_highlight(self):
        text = """0802 晚班交接
時間窗：2026-08-02 14:00–2026-08-03 09:00（約19hrs）
收錄外電共1則（AP 1則）
標記：▲=新增
🔴 重大：▲ AP999 找不到正文
======國際======
【安全】
炸彈攻擊
AP001 正文素材
"""

        document = history.parse_document_text(
            text, date="0802", group="AI 對照組", phase="0802–0811"
        )

        self.assertEqual(document["header_highlights"][0]["material_code"], "AP999")
        self.assertTrue(
            any(
                diagnostic["kind"] == "orphan highlight" and diagnostic["line_number"] == 5
                for diagnostic in document["diagnostics"]
            )
        )


def _rtf_hex(data):
    return "".join("\\'%02x" % byte for byte in data)


class SourceReadingTests(unittest.TestCase):
    def test_讀取帶_BOM_的_UTF8_文字檔(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "0501國際晚班交接.txt"
            path.write_text("======財經======\n", encoding="utf-8-sig")

            self.assertEqual(history.read_source_text(path), "======財經======\n")

    def test_RTF_交由_pandoc_轉成純文字(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "0527國際晚班交接.rtf"
            path.write_text("{\\rtf1 測試}", encoding="utf-8")
            received = []

            def fake_pandoc(received_path):
                received.append(Path(received_path))
                return "======財經======\n"

            self.assertEqual(history.read_source_text(path, pandoc_runner=fake_pandoc), "======財經======\n")
            self.assertEqual(received, [path])

    def test_損壞RTF不經pandoc也能解出純文字(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "0606國際晚班交接.rtf"
            path.write_text(
                r"{\rtf1\ansi\deff0{\fonttbl{\f0\fnil\fcharset0 Arial;}}\f0 ======OK======\par stock}",
                encoding="ascii",
            )

            self.assertEqual(history.read_source_text(path), "======OK======\nstock")
            document = history.analyze_corpus(
                [{"path": path, "date": "0606", "group": "人工交接", "phase": "0527–0626"}],
            )[0]
            self.assertFalse(
                any(diagnostic["kind"] in {"RTF 轉換容錯", "RTF 編碼修正"} for diagnostic in document["diagnostics"])
            )

    def test_font_aware解碼Big5分類與中主題(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "0613國際晚班交接.rtf"
            rtf = (
                r"{\rtf1\ansi\deff0{\fonttbl{\f0\fnil\fcharset136 Ming;}}\f0 "
                + _rtf_hex("======大陸======".encode("cp950"))
                + r"\par " + _rtf_hex("【蝴蝶】".encode("cp950"))
                + r"\par RT1612 " + _rtf_hex("報導".encode("cp950"))
                + "}"
            )
            path.write_bytes(rtf.encode("latin1"))

            document = history.analyze_corpus(
                [{"path": path, "date": "0613", "group": "人工交接", "phase": "0527–0626"}],
            )[0]

        self.assertEqual(document["category_order"], ["大陸"])
        self.assertEqual(document["categories"][0]["topics"][0]["name"], "蝴蝶")
        self.assertIn("報導", document["categories"][0]["topics"][0]["items"][0]["text"])
        self.assertFalse(
            any(diagnostic["kind"] == "RTF 編碼修正" for diagnostic in document["diagnostics"])
        )

    def test_合法重音外文與西文標點不會被誤轉為中文(self):
        path = Path("accented.rtf")
        converted = (
            "======國際======\n外文姓名\n"
            "RT001 éclair José Álvarez Müller Schüchler\n"
            "RT002 ¡Hola! ¿Cómo está? ¡Buenos días!\n"
            "RT003 中文……現在\n"
            "RT004 中文….."
        )

        self.assertEqual(
            history.read_source_text(path, pandoc_runner=lambda _: converted),
            converted,
        )
        self.assertEqual(history.find_mojibake_issues(converted), [])

    def test_高密度合法重音外文不得被靜默改寫(self):
        path = Path("accent-dense.rtf")
        converted = "======國際======\n外文\nRT001 Crème brûlée déjà\n"

        self.assertEqual(
            history.read_source_text(path, pandoc_runner=lambda _: converted),
            converted,
        )
        self.assertEqual(history.find_mojibake_issues(converted), [])

    def test_連續合法重音外文不得被兩字元gate拒讀(self):
        path = Path("accent-run.rtf")
        converted = "======國際======\n外文\nRT001 ÀÉÎ\nRT002 ééé\n"

        self.assertEqual(
            history.read_source_text(path, pandoc_runner=lambda _: converted),
            converted,
        )
        self.assertEqual(history.find_mojibake_issues(converted), [])

    def test_兩字元_Big5_mojibake_必須拒絕輸出(self):
        path = Path("two-byte.rtf")

        with self.assertRaises(history.SourceReadError) as raised:
            history.read_source_text(
                path,
                pandoc_runner=lambda _: "======°ê======\n主題\nRT001 素材",
            )

        self.assertIn("mojibake", str(raised.exception))
        self.assertTrue(
            history.find_mojibake_issues("======°ê======", residual_two_byte=True)
        )

    def test_分類列上的殘餘mojibake必須拒絕而非猜測修復(self):
        path = Path("category-delimiter.rtf")

        with self.assertRaises(history.SourceReadError) as raised:
            history.read_source_text(
                path,
                pandoc_runner=lambda _: "======°ê======\n市場\nRT001 素材",
            )

        self.assertIn("mojibake", str(raised.exception))

    def test_RTF_殘留_mojibake_無法安全修復時拒絕讀取(self):
        path = Path("bad.rtf")

        def replacement_character_pandoc(_):
            return "======財經======\n美股\nRT001 無法修復�素材"

        with self.assertRaises(history.SourceReadError) as raised:
            history.read_source_text(path, pandoc_runner=replacement_character_pandoc)

        self.assertIn("mojibake", str(raised.exception))
        self.assertTrue(history.find_mojibake_issues("RT001 單一¤殘留"))
        self.assertTrue(history.find_mojibake_issues("阿巴´絲"))
        self.assertEqual(history.find_mojibake_issues("José Álvarez Müller"), [])

    def test_真實已知亂碼片段可由font_aware解碼(self):
        sources = history.discover_corpus(history.DEFAULT_MANUAL_DIR, history.DEFAULT_ARCHIVE_DIR)
        selected = [
            next(source for source in sources if source["date"] == date)
            for date in ("0608", "0620", "0626")
        ]

        texts = {
            source["date"]: history.read_source_text(source["path"])
            for source in selected
        }

        expected = {
            "0608": ("俄羅斯", "換俘行動"),
            "0620": ("伊朗外長阿巴斯·阿拉克奇",),
            "0626": ("印度喜馬偕爾邦", "喜馬偕爾邦首席部長", "山區發現了三具遺體"),
        }
        for date, snippets in expected.items():
            self.assertEqual(history.find_mojibake_issues(texts[date]), [], date)
            for snippet in snippets:
                self.assertIn(snippet, texts[date], f"{date} {snippet}")

    def test_真實曾需fallback的RTF可直接解析且無字型殘屑(self):
        sources = history.discover_corpus(history.DEFAULT_MANUAL_DIR, history.DEFAULT_ARCHIVE_DIR)
        selected = [
            next(source for source in sources if source["date"] == date)
            for date in ("0606", "0613")
        ]

        documents = history.analyze_corpus(selected)

        for document in documents:
            self.assertTrue(document["categories"], document["date"])
            self.assertTrue(any(category["topics"] for category in document["categories"]), document["date"])
            self.assertTrue(any(
                history._topic_item_count(topic) > 0
                for category in document["categories"]
                for topic in category["topics"]
            ), document["date"])
            self.assertEqual(document["unrecognized_lines"], [], document["date"])
            self.assertFalse(
                any(entry["reason"] == "RTF 字型表殘屑" for entry in document["ignored_lines"]),
                document["date"],
            )
            self.assertFalse(any(
                diagnostic["kind"] in {"RTF 轉換容錯", "RTF 編碼修正"}
                for diagnostic in document["diagnostics"]
            ), document["date"])


class CorpusDiscoveryTests(unittest.TestCase):
    def _create_complete_corpus(self, root):
        manual_dir = root / "manual"
        manual_dir.mkdir()
        for date in history.MANUAL_TXT_DATES:
            (manual_dir / f"{date}國際晚班交接.txt").write_text("範例", encoding="utf-8")
        for date in history.MANUAL_RTF_DATES:
            (manual_dir / f"{date}國際晚班交接.rtf").write_text("{\\rtf1 範例}", encoding="utf-8")

        ai_root = root / "ai"
        for date in history.AI_DATES:
            folder = ai_root / f"2026{date}"
            folder.mkdir(parents=True)
            (folder / f"{date}晚班交接.txt").write_text("範例", encoding="utf-8")
        (ai_root / "20260802" / "0802晚班交接.snapshot.txt").write_text("排除", encoding="utf-8")
        (ai_root / "20260803" / "0803晚班交接.txt.prev.txt").write_text("排除", encoding="utf-8")
        return manual_dir, ai_root

    def test_只接受指定的_23_份人工與_10_份_AI_canonical_語料(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manual_dir, ai_root = self._create_complete_corpus(Path(temp_dir))

            sources = history.discover_corpus(manual_dir, ai_root)

        manual_sources = [source for source in sources if source["group"] == "人工交接"]
        ai_sources = [source for source in sources if source["group"] == "AI 對照組"]
        self.assertEqual(len(manual_sources), 23)
        self.assertEqual(len([source for source in manual_sources if source["path"].suffix == ".txt"]), 10)
        self.assertEqual(len([source for source in manual_sources if source["path"].suffix == ".rtf"]), 13)
        self.assertEqual([source["date"] for source in ai_sources], history.AI_DATES)
        self.assertEqual(
            {source["phase"] for source in manual_sources}, {"0501–0521", "0527–0626"}
        )

    def test_人工語料數量不符時失敗而非靜默忽略(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manual_dir, ai_root = self._create_complete_corpus(Path(temp_dir))
            (manual_dir / "0501國際晚班交接.txt").unlink()

            with self.assertRaises(history.CorpusDiscoveryError) as raised:
                history.discover_corpus(manual_dir, ai_root)

        self.assertIn("人工", str(raised.exception))


class StatisticsTests(unittest.TestCase):
    def test_依分期輸出量測與可配置關鍵主題跨格表(self):
        old_manual = history.parse_document_text(
            """======財經======
美股
AP001 舊期美股。<無BITE>
======體育======
美國體育
AP002 舊期體育。<無BITE>
""",
            date="0501", group="人工交接", phase="0501–0521",
        )
        new_manual = history.parse_document_text(
            """======國際======
【災害】
颱風傷亡
AP003 新期颱風。<無BITE>
======話題======
【趣聞】
軟性趣味
AP004 新期趣聞。<無BITE>
""",
            date="0527", group="人工交接", phase="0527–0626",
        )

        statistics = history.build_statistics(
            [old_manual, new_manual],
            keyword_topics={
                "美股": ["美股", "華爾街"],
                "美國體育": ["美國體育", "NBA"],
                "颱風傷亡": ["颱風", "傷亡"],
                "軟性趣味": ["趣味", "趣聞"],
            },
        )

        self.assertEqual(statistics["periods"]["人工 0501–0521"]["document_count"], 1)
        self.assertEqual(statistics["periods"]["人工 0527–0626"]["document_count"], 1)
        self.assertEqual(statistics["periods"]["人工 合併總表"]["document_count"], 2)
        self.assertEqual(statistics["periods"]["人工 0501–0521"]["category_orders"][0]["order"], ["財經", "體育"])
        self.assertEqual(statistics["periods"]["人工 0501–0521"]["topic_names"], ["美股", "美國體育"])
        self.assertEqual(statistics["keyword_crosstab"]["美股"]["counts_by_category"], {"財經": 1})
        self.assertEqual(statistics["keyword_crosstab"]["美國體育"]["counts_by_category"], {"體育": 1})
        self.assertEqual(statistics["keyword_crosstab"]["颱風傷亡"]["counts_by_category"], {"國際": 1})
        self.assertEqual(statistics["keyword_crosstab"]["軟性趣味"]["counts_by_category"], {"話題": 1})


class RealCorpusSmokeTests(unittest.TestCase):
    def test_數份真實語料可讀取並解析出大分類(self):
        sources = history.discover_corpus(history.DEFAULT_MANUAL_DIR, history.DEFAULT_ARCHIVE_DIR)
        selected = [
            next(source for source in sources if source["date"] == "0501"),
            next(source for source in sources if source["date"] == "0527"),
            next(source for source in sources if source["date"] == "0606"),
            next(source for source in sources if source["date"] == "0802"),
        ]

        documents = history.analyze_corpus(selected)

        self.assertEqual([document["date"] for document in documents], ["0501", "0527", "0606", "0802"])
        self.assertTrue(all(document["categories"] for document in documents))
        self.assertFalse(
            any(
                diagnostic["kind"] in {"RTF 轉換容錯", "RTF 編碼修正"}
                for document in documents
                for diagnostic in document["diagnostics"]
            )
        )


class FullCorpusAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources = history.discover_corpus(history.DEFAULT_MANUAL_DIR, history.DEFAULT_ARCHIVE_DIR)
        cls.documents = history.analyze_corpus(sources)

    def test_33份文件與已知90筆未辨識行全部達到結構化門檻(self):
        self.assertEqual(len(self.documents), 33)
        self.assertTrue(all(document["categories"] for document in self.documents))
        self.assertEqual(sum(len(document["header_metadata"]) for document in self.documents), 40)
        self.assertEqual(sum(len(document["header_highlights"]) for document in self.documents), 23)
        self.assertEqual(sum(len(document["ignored_lines"]) for document in self.documents), 8)
        self.assertEqual(sum(len(document["unrecognized_lines"]) for document in self.documents), 0)
        self.assertLessEqual(
            {
                diagnostic["kind"]
                for document in self.documents
                for diagnostic in document["diagnostics"]
            },
            {"空分類", "orphan highlight"},
        )

    def test_人工未指定大分類內容有3主題9素材且不進分類(self):
        manual_documents = [
            document for document in self.documents if document["group"] == "人工交接"
        ]
        unscoped_topics = [
            topic
            for document in manual_documents
            for topic in document["unscoped_sections"]["topics"]
        ]
        self.assertEqual(len(unscoped_topics), 3)
        self.assertEqual(sum(history._topic_item_count(topic) for topic in unscoped_topics), 9)
        unscoped_ids = {id(topic) for topic in unscoped_topics}
        category_ids = {
            id(topic)
            for document in manual_documents
            for category in document["categories"]
            for topic in category["topics"]
        }
        self.assertTrue(unscoped_ids.isdisjoint(category_ids))

    def test_13份RTF所有結構化文字均無_mojibake(self):
        for document in self.documents:
            if document["date"] not in history.MANUAL_RTF_DATES:
                continue
            values = []
            for category in document["categories"]:
                values.append(category["name"])
                for topic in category["topics"]:
                    values.append(topic["name"])
                    values.extend(item["text"] for item in topic["items"])
                    for subtopic in topic["subtopics"]:
                        values.append(subtopic["name"])
                        values.extend(item["text"] for item in subtopic["items"])
            for topic in document["unscoped_sections"]["topics"]:
                values.append(topic["name"])
                values.extend(item["text"] for item in topic["items"])
                for subtopic in topic["subtopics"]:
                    values.append(subtopic["name"])
                    values.extend(item["text"] for item in subtopic["items"])
            self.assertEqual(
                history.find_mojibake_issues("\n".join(values)),
                [],
                document["date"],
            )

    def test_13份RTF無殘留且fallback與85空分類可追溯(self):
        rtf_documents = [
            document for document in self.documents if document["date"] in history.MANUAL_RTF_DATES
        ]
        self.assertEqual(len(rtf_documents), 13)
        self.assertEqual(
            {
                document["date"]
                for document in rtf_documents
                if any(
                    diagnostic["kind"] in {"RTF 轉換容錯", "RTF 編碼修正"}
                    for diagnostic in document["diagnostics"]
                )
            },
            set(),
        )
        empty_categories = [
            category
            for document in self.documents
            for category in document["categories"]
            if category["is_empty"]
        ]
        self.assertEqual(len(empty_categories), 84)
        self.assertEqual(
            sum(
                diagnostic["kind"] == "空分類"
                for document in self.documents
                for diagnostic in document["diagnostics"]
            ),
            84,
        )


class ReviewRegressionTests(unittest.TestCase):
    def test_前四個等號的真實分類格式可解析(self):
        document = history.parse_document_text(
            """====大陸======
【兩岸】
AP001 測試素材。<無BITE>
""",
            date="0613", group="人工交接", phase="0527–0626",
        )

        self.assertEqual(document["category_order"], ["大陸"])
        self.assertEqual(document["categories"][0]["topics"][0]["items"], [
            {"text": "AP001 測試素材。<無BITE>", "line_number": 3}
        ])

    def test_括號中主題後的直接素材計入中主題則數(self):
        document = history.parse_document_text(
            """======財經======
【市場】
AP001 美股下跌。<無BITE>
RT002 美股回升。<無BITE>
""",
            date="0802", group="AI 對照組", phase="0802–0811",
        )

        topic = document["categories"][0]["topics"][0]
        statistics = history.build_statistics([document], keyword_topics={})
        self.assertEqual(topic["subtopics"], [])
        self.assertEqual([item["text"] for item in topic["items"]], [
            "AP001 美股下跌。<無BITE>", "RT002 美股回升。<無BITE>"
        ])
        self.assertEqual(
            statistics["periods"]["AI 對照組 0802–0811"]["topic_item_count_distribution"],
            {2: 1},
        )

    def test_discovery_拒絕日期開頭但副檔名不符的候選檔(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manual_dir, ai_root = CorpusDiscoveryTests()._create_complete_corpus(Path(temp_dir))
            (manual_dir / "0527國際晚班交接.docx").write_text("不應忽略", encoding="utf-8")

            with self.assertRaises(history.CorpusDiscoveryError) as raised:
                history.discover_corpus(manual_dir, ai_root)

        self.assertIn("0527國際晚班交接.docx", str(raised.exception))

    def test_明確傳入空關鍵詞設定時不產生預設交叉表(self):
        document = history.parse_document_text(
            """======財經======
美股
AP001 測試素材。<無BITE>
""",
            date="0501", group="人工交接", phase="0501–0521",
        )

        self.assertEqual(history.build_statistics([document], keyword_topics={})["keyword_crosstab"], {})

    def test_真實_0613_0614_0620_RTF_使用正確中文分類名稱(self):
        sources = history.discover_corpus(history.DEFAULT_MANUAL_DIR, history.DEFAULT_ARCHIVE_DIR)
        selected = [
            next(source for source in sources if source["date"] == date)
            for date in ("0613", "0614", "0620")
        ]

        documents = history.analyze_corpus(selected)

        self.assertEqual([document["date"] for document in documents], ["0613", "0614", "0620"])
        for document in documents:
            self.assertIn("大陸", document["category_order"], document["date"])
            self.assertFalse(any("¤" in name for name in document["category_order"]), document["date"])
            self.assertFalse(
                any(diagnostic["kind"] in {"RTF 編碼修正", "RTF 轉換容錯"} for diagnostic in document["diagnostics"]),
                document["date"],
            )

    def test_CLI_遇到零分類文件時非零失敗(self):
        zero_category_document = history.parse_document_text(
            "沒有分類標題", date="0501", group="人工交接", phase="0501–0521"
        )
        source = {
            "path": Path("假檔"),
            "date": "0501",
            "group": "人工交接",
            "phase": "0501–0521",
        }
        with mock.patch.object(history, "discover_corpus", return_value=[source]), \
             mock.patch.object(history, "analyze_corpus", return_value=[zero_category_document]):
            with self.assertRaises(SystemExit) as raised:
                history.main([])

        self.assertNotEqual(raised.exception.code, 0)

    def test_CLI_遇到未知未辨識行時不建立輸出檔(self):
        document = history.parse_document_text(
            "未知檔頭\n======國際======\n外交\nAP001 素材",
            date="0501", group="人工交接", phase="0501–0521",
        )
        source = {
            "path": Path("假檔"),
            "date": "0501",
            "group": "人工交接",
            "phase": "0501–0521",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "blocked.json"
            with mock.patch.object(history, "discover_corpus", return_value=[source]), \
                 mock.patch.object(history, "analyze_corpus", return_value=[document]):
                with self.assertRaises(SystemExit) as raised:
                    history.main(["--output", str(output)])

            self.assertNotEqual(raised.exception.code, 0)
            self.assertFalse(output.exists())

    def test_CLI_遇到orphan_highlight時非零失敗(self):
        document = history.parse_document_text(
            "0802 晚班交接\n時間窗：x\n收錄外電共1則（AP 1則）\n標記：▲=新增\n"
            "🔴 重大：▲ AP999 找不到正文\n======國際======\n外交\nAP001 正文素材\n",
            date="0802",
            group="AI 對照組",
            phase="0802–0811",
        )
        source = {
            "path": Path("假檔"),
            "date": "0802",
            "group": "AI 對照組",
            "phase": "0802–0811",
        }
        stderr = io.StringIO()
        with mock.patch.object(history, "discover_corpus", return_value=[source]), \
             mock.patch.object(history, "analyze_corpus", return_value=[document]), \
             mock.patch.object(sys, "stderr", stderr):
            with self.assertRaises(SystemExit) as raised:
                history.main([])

        self.assertNotEqual(raised.exception.code, 0)
        self.assertIn("orphan highlight", stderr.getvalue())


class FontAwareRtfDecoderTests(unittest.TestCase):
    def test_依字型charset解碼中文外文與GB字(self):
        rtf = (
            r"{\rtf1\ansi\ansicpg1252\deff0"
            r"{\fonttbl{\f0\fnil\fcharset136 Microsoft Sans Serif;}"
            r"{\f1\fnil\fcharset0 Arial;}"
            r"{\f2\fnil\fcharset134 SimSun;}}"
            r"\f1 " + _rtf_hex("Crème brûlée déjà".encode("cp1252"))
            + r"\par \f0 " + _rtf_hex("中文……現在".encode("cp950"))
            + r"\par \f2 " + _rtf_hex("国".encode("gb18030"))
            + "}"
        )

        text, metadata = history.decode_font_aware_rtf(rtf.encode("latin1"))

        self.assertIn("Crème brûlée déjà", text)
        self.assertIn("中文……現在", text)
        self.assertIn("国", text)
        self.assertEqual(metadata["replacement_characters"], 0)

    def test_未知fcharset必須明確失敗並帶font與charset(self):
        rtf = r"{\rtf1\ansi\deff0{\fonttbl{\f0\fnil\fcharset222 Mystery;}}\f0 \'aa}"

        with self.assertRaises(history.SourceReadError) as raised:
            history.decode_font_aware_rtf(rtf.encode("latin1"))

        message = str(raised.exception)
        self.assertIn("222", message)
        self.assertRegex(message, r"f(?:ont)?\s*0")

    def test_fonttbl沒有的font_id必須明確失敗(self):
        rtf = r"{\rtf1\ansi\deff0{\fonttbl{\f0\fnil\fcharset0 Arial;}}\f99 \'aa}"

        with self.assertRaises(history.SourceReadError) as raised:
            history.decode_font_aware_rtf(rtf.encode("latin1"))

        message = str(raised.exception)
        self.assertIn("99", message)
        self.assertRegex(message, r"f(?:ont)?\s*99")

    def test_group結束後字型狀態要還原(self):
        rtf = (
            r"{\rtf1\ansi\deff0"
            r"{\fonttbl{\f0\fnil\fcharset0 Arial;}"
            r"{\f1\fnil\fcharset136 Ming;}}"
            r"\f0 A{\f1 " + _rtf_hex("中".encode("cp950")) + r"}B}"
        )

        text, _ = history.decode_font_aware_rtf(rtf.encode("latin1"))

        self.assertEqual(text.replace("\n", ""), "A中B")

    def test_unicode控制字會跳過fallback位元組(self):
        rtf = "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0\\fnil\\fcharset0 Arial;}}\\f0 \\uc1\\u20013\\'3fX}"

        text, _ = history.decode_font_aware_rtf(rtf.encode("latin1"))

        self.assertIn("中", text)
        self.assertIn("X", text)
        self.assertNotIn("?", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
