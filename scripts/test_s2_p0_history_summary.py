# -*- coding: utf-8 -*-
"""S2 P0 歷史語料聚合工具的迴歸測試。

用法：python scripts/test_s2_p0_history_summary.py
"""
import copy
import csv
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "s2_p0_history_summary.py"
sys.path.insert(0, os.fspath(HERE))


class ModuleAvailabilityTests(unittest.TestCase):
    def test_聚合工具模組存在(self):
        self.assertTrue(MODULE_PATH.is_file(), "尚未建立 s2_p0_history_summary.py")
        self.assertIsNotNone(importlib.util.spec_from_file_location("s2_p0_history_summary", MODULE_PATH))


import s2_p0_history_summary as summary  # noqa: E402


def _topic(name, item_count, *, subtopic_counts=()):
    direct_count = item_count - sum(subtopic_counts)
    return {
        "name": name,
        "line_number": 10,
        "format": "括號中主題",
        "items": [
            {"text": f"素材全文 {index}", "line_number": 11 + index}
            for index in range(direct_count)
        ],
        "subtopics": [
            {
                "name": f"{name}小分題{index}",
                "line_number": 20 + index,
                "items": [
                    {"text": f"小分題素材全文 {item_index}", "line_number": 30 + item_index}
                    for item_index in range(count)
                ],
            }
            for index, count in enumerate(subtopic_counts, start=1)
        ],
    }


def _document(date, group, phase, categories, diagnostics=None):
    parsed_categories = []
    for category_index, (category_name, topics) in enumerate(categories, start=1):
        parsed_categories.append(
            {
                "name": category_name,
                "line_number": category_index,
                "topics": topics,
            }
        )
    return {
        "date": date,
        "group": group,
        "phase": phase,
        "category_order": [name for name, _ in categories],
        "categories": parsed_categories,
        "unrecognized_lines": [{"text": "檔頭全文", "line_number": 1}],
        "diagnostics": diagnostics or [],
        "source_path": f"G:/private/{date}.txt",
    }


def _input_statistics(documents):
    periods = {}
    selections = {
        "人工 0501–0521": [d for d in documents if d["group"] == "人工交接" and d["phase"] == "0501–0521"],
        "人工 0527–0626": [d for d in documents if d["group"] == "人工交接" and d["phase"] == "0527–0626"],
        "人工 合併總表": [d for d in documents if d["group"] == "人工交接"],
        "AI 對照組 0802–0811": [d for d in documents if d["group"] == "AI 對照組"],
    }
    for label, selected in selections.items():
        middle_topic_counts = []
        topic_name_records = []
        item_distribution = {}
        for document in selected:
            for category in document["categories"]:
                middle_topic_counts.append(
                    {"date": document["date"], "category": category["name"], "count": len(category["topics"])}
                )
                for topic in category["topics"]:
                    count = len(topic["items"]) + sum(len(subtopic["items"]) for subtopic in topic["subtopics"])
                    topic_name_records.append(
                        {
                            "date": document["date"],
                            "category": category["name"],
                            "topic": topic["name"],
                            "item_count": count,
                        }
                    )
                    item_distribution[str(count)] = item_distribution.get(str(count), 0) + 1
        periods[label] = {
            "document_count": len(selected),
            "category_orders": [
                {"date": document["date"], "order": document["category_order"]}
                for document in selected
            ],
            "middle_topic_counts": middle_topic_counts,
            "topic_item_count_distribution": item_distribution,
            "topic_names": [record["topic"] for record in topic_name_records],
            "topic_name_records": topic_name_records,
        }
    return {"periods": periods, "keyword_crosstab": {}}


def _valid_payload():
    documents = [
        _document(
            "0501",
            "人工交接",
            "0501–0521",
            [
                ("財經", [_topic("美股收黑", 1), _topic("匯市", 3, subtopic_counts=(2,))]),
                ("體育", [_topic("NBA季後賽", 2)]),
            ],
            diagnostics=[{"kind": "未辨識行", "text": "檔頭全文", "line_number": 1}],
        ),
        _document(
            "0527",
            "人工交接",
            "0527–0626",
            [("國際", [_topic("颱風傷亡", 4)])],
            diagnostics=[{"kind": "空分類", "text": "空格", "line_number": 8}],
        ),
        _document(
            "0802",
            "AI 對照組",
            "0802–0811",
            [("話題", [_topic("軟性趣味", 5)]), ("財經", [_topic("華爾街焦點", 6)])],
            diagnostics=[{"kind": "RTF 編碼修正", "text": "修正 1 行", "line_number": None}],
        ),
    ]
    return {
        "source_correction": "測試",
        "sources": [{"path": "G:/private/source.txt", "date": "0501"}],
        "documents": documents,
        "statistics": _input_statistics(documents),
    }


class DistributionTests(unittest.TestCase):
    def test_七數摘要採_Hyndman_Fan_type_7_線性插值(self):
        result = summary.describe_distribution([1, 2, 3, 4])

        self.assertEqual(
            result,
            {
                "count": 4,
                "min": 1,
                "q1": 1.75,
                "median": 2.5,
                "q3": 3.25,
                "max": 4,
                "mean": 2.5,
            },
        )
        self.assertIn("Hyndman–Fan type 7", summary.QUARTILE_METHOD)


class AggregationTests(unittest.TestCase):
    def test_人工兩期合併表與_AI_分開且保留順序與來源日期(self):
        result = summary.summarize_payload(_valid_payload())

        self.assertEqual(
            list(result["periods"]),
            ["人工 0501–0521", "人工 0527–0626", "人工 合併總表", "AI 對照組 0802–0811"],
        )
        self.assertEqual(result["periods"]["人工 0501–0521"]["document_count"], 1)
        self.assertEqual(result["periods"]["人工 合併總表"]["document_count"], 2)
        self.assertEqual(result["periods"]["AI 對照組 0802–0811"]["document_count"], 1)
        self.assertEqual(
            result["periods"]["人工 0501–0521"]["category_orders"],
            [{"date": "0501", "category_count": 2, "order": ["財經", "體育"]}],
        )
        self.assertEqual(
            result["periods"]["人工 0501–0521"]["category_presence"]["財經"]["positions"],
            {"1": 1},
        )
        self.assertEqual(
            result["periods"]["人工 0501–0521"]["middle_topics_per_cell"]["summary"]["count"],
            2,
        )
        self.assertEqual(
            result["periods"]["人工 0501–0521"]["items_per_middle_topic"]["frequency"],
            {"1": 1, "2": 1, "3": 1},
        )

    def test_中主題全表保留分類位置中主題位置與素材則數(self):
        result = summary.summarize_payload(_valid_payload())

        self.assertEqual(
            result["middle_topic_records"][0],
            {
                "date": "0501",
                "group": "人工交接",
                "phase": "0501–0521",
                "category": "財經",
                "category_position": 1,
                "middle_topic": "美股收黑",
                "middle_topic_position": 1,
                "item_count": 1,
            },
        )
        self.assertEqual(len(result["middle_topic_records"]), 6)

    def test_關鍵主題跨格表保留命中詞日期並明示不是真值(self):
        result = summary.summarize_payload(_valid_payload())
        stock = result["keyword_crosstab"]["美股"]

        self.assertFalse(stock["is_ground_truth"])
        self.assertEqual(stock["occurrences"][0]["date"], "0501")
        self.assertEqual(stock["occurrences"][0]["matched_terms"], ["美股"])
        self.assertEqual(stock["occurrences"][0]["review_status"], "unreviewed")
        self.assertEqual(stock["counts_by_category"], {"財經": 2})

    def test_守恆可回算文件分類中主題與素材總數(self):
        result = summary.summarize_payload(_valid_payload())

        self.assertEqual(
            result["conservation"],
            {
                "input": {"documents": 3, "categories": 5, "middle_topics": 6, "materials": 21},
                "aggregated": {"documents": 3, "categories": 5, "middle_topics": 6, "materials": 21},
                "checks": {"documents": "PASS", "categories": "PASS", "middle_topics": "PASS", "materials": "PASS"},
                "overall": "PASS",
            },
        )

    def test_正式聚合完全移除原文路徑與原始容器欄位(self):
        result = summary.summarize_payload(_valid_payload())
        rendered = json.dumps(result, ensure_ascii=False)

        for forbidden in ("素材全文", "檔頭全文", "G:/private", '"text"', '"raw"', '"items"', '"source_path"', '"path"', '"unrecognized_lines"'):
            self.assertNotIn(forbidden, rendered)


class ValidationTests(unittest.TestCase):
    def assert_invalid(self, mutate, message_fragment):
        payload = _valid_payload()
        mutate(payload)
        with self.assertRaises(summary.SummaryValidationError) as raised:
            summary.summarize_payload(payload)
        self.assertIn(message_fragment, str(raised.exception))

    def test_零分類文件必須失敗(self):
        self.assert_invalid(lambda payload: payload["documents"][0].update(categories=[], category_order=[]), "零分類")

    def test_未知組別必須失敗(self):
        self.assert_invalid(lambda payload: payload["documents"][0].update(group="未知"), "未知組別")

    def test_缺日期或分期必須失敗(self):
        self.assert_invalid(lambda payload: payload["documents"][0].update(date=""), "日期")
        self.assert_invalid(lambda payload: payload["documents"][0].update(phase=""), "分期")

    def test_非數字素材則數必須失敗(self):
        def mutate(payload):
            payload["statistics"]["periods"]["人工 0501–0521"]["topic_name_records"][0]["item_count"] = "1"

        self.assert_invalid(mutate, "非數字")

    def test_input_aggregate_不守恆必須失敗(self):
        def mutate(payload):
            payload["statistics"]["periods"]["人工 0501–0521"]["document_count"] = 99

        self.assert_invalid(mutate, "aggregate 不守恆")


class OutputTests(unittest.TestCase):
    def test_寫出固定檔名_JSON_Markdown_CSV_與診斷覆核(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = summary.write_outputs(_valid_payload(), Path(temp_dir))

            self.assertEqual(
                set(outputs),
                {"json", "markdown", "csv", "diagnostic_review"},
            )
            self.assertTrue(all(path.is_file() for path in outputs.values()))
            self.assertEqual(outputs["json"].name, "2026-08-20-S2-P0歷史語料聚合.json")
            self.assertEqual(outputs["markdown"].name, "2026-08-20-S2-P0歷史語料統計摘要.md")
            self.assertEqual(outputs["csv"].name, "2026-08-20-S2-P0中主題名稱全表.csv")
            self.assertEqual(outputs["diagnostic_review"].name, "2026-08-20-S2-P0解析診斷覆核.md")

            markdown = outputs["markdown"].read_text(encoding="utf-8")
            self.assertIn("Hyndman–Fan type 7", markdown)
            self.assertIn("守恆檢查：PASS", markdown)
            self.assertNotIn("素材全文", markdown)

            with outputs["csv"].open(encoding="utf-8-sig", newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 6)
            self.assertEqual(rows[0]["日期"], "0501")
            self.assertEqual(rows[0]["素材則數"], "1")

            diagnostic_review = outputs["diagnostic_review"].read_text(encoding="utf-8")
            self.assertIn("未辨識行", diagnostic_review)
            self.assertIn("來源日期與行號", diagnostic_review)
            self.assertNotIn("檔頭全文", diagnostic_review)


if __name__ == "__main__":
    unittest.main(verbosity=2)
