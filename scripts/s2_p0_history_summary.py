# -*- coding: utf-8 -*-
"""將 S2 P0 完整解析 JSON 轉成不含素材全文的歷史聚合資料。"""
import argparse
from collections import Counter, OrderedDict
import csv
import json
import math
from pathlib import Path
import re
import statistics
import sys


OUTPUT_DATE = "2026-08-20"
JSON_FILENAME = f"{OUTPUT_DATE}-S2-P0歷史語料聚合.json"
MARKDOWN_FILENAME = f"{OUTPUT_DATE}-S2-P0歷史語料統計摘要.md"
CSV_FILENAME = f"{OUTPUT_DATE}-S2-P0中主題名稱全表.csv"
DIAGNOSTIC_FILENAME = f"{OUTPUT_DATE}-S2-P0解析診斷覆核.md"
QUARTILE_METHOD = (
    "Hyndman–Fan type 7 線性插值：對 p∈{0.25, 0.5, 0.75}，"
    "h=(n−1)p，以排序後第 floor(h) 與 ceil(h) 個零起算值線性插值。"
)
DEFAULT_KEYWORD_TOPICS = OrderedDict(
    [
        ("美股", ["美股", "華爾街", "道瓊", "那斯達克", "標普"]),
        ("美國體育", ["美國體育", "NBA", "MLB", "NFL", "美式足球", "美職"]),
        ("颱風傷亡", ["颱風", "颱風傷亡", "風災"]),
        ("軟性趣味", ["軟性趣味", "趣聞", "趣味", "暖聞"]),
    ]
)
EXPECTED_GROUP_PHASES = {
    "人工交接": {"0501–0521", "0527–0626"},
    "AI 對照組": {"0802–0811"},
}
PERIOD_ORDER = (
    "人工 0501–0521",
    "人工 0527–0626",
    "人工 合併總表",
    "AI 對照組 0802–0811",
)
# 人工覆核後以 occurrence_id 為鍵填入；未列者保持 unreviewed，不能當真值。
KEYWORD_REVIEW_OVERRIDES = {}
LIKELY_MISSES = {label: [] for label in DEFAULT_KEYWORD_TOPICS}


class SummaryValidationError(RuntimeError):
    """完整 JSON 不符合可供統計的結構或守恆條件。"""


def _type7_quantile(sorted_values, probability):
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def _clean_number(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return round(value, 6) if isinstance(value, float) else value


def describe_distribution(values):
    """回傳 count、min、Q1、median、Q3、max、mean 的 type-7 摘要。"""
    if not values:
        return {key: None for key in ("count", "min", "q1", "median", "q3", "max", "mean")} | {"count": 0}
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
        raise SummaryValidationError("分布包含非數字值")
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": _clean_number(ordered[0]),
        "q1": _clean_number(_type7_quantile(ordered, 0.25)),
        "median": _clean_number(_type7_quantile(ordered, 0.5)),
        "q3": _clean_number(_type7_quantile(ordered, 0.75)),
        "max": _clean_number(ordered[-1]),
        "mean": _clean_number(statistics.fmean(ordered)),
    }


def _distribution(values):
    return {
        "summary": describe_distribution(values),
        "frequency": {str(value): count for value, count in sorted(Counter(values).items())},
    }


def _require_nonempty_string(value, label, date_hint=""):
    if not isinstance(value, str) or not value.strip():
        suffix = f"（{date_hint}）" if date_hint else ""
        raise SummaryValidationError(f"缺少{label}{suffix}")
    return value


def _require_list(value, label):
    if not isinstance(value, list):
        raise SummaryValidationError(f"{label}必須是陣列")
    return value


def _count_topic_materials(topic, *, context):
    direct = _require_list(topic.get("items"), f"{context}的素材")
    subtopics = _require_list(topic.get("subtopics"), f"{context}的小分題")
    count = len(direct)
    for subtopic_index, subtopic in enumerate(subtopics, start=1):
        if not isinstance(subtopic, dict):
            raise SummaryValidationError(f"{context}的小分題 {subtopic_index} 不是物件")
        _require_nonempty_string(subtopic.get("name"), "小分題名稱", context)
        count += len(_require_list(subtopic.get("items"), f"{context}小分題的素材"))
    return count


def _validate_documents(payload):
    if not isinstance(payload, dict):
        raise SummaryValidationError("input 最外層必須是物件")
    documents = _require_list(payload.get("documents"), "documents")
    if not documents:
        raise SummaryValidationError("documents 不得為空")

    dates = set()
    for document_index, document in enumerate(documents, start=1):
        if not isinstance(document, dict):
            raise SummaryValidationError(f"第 {document_index} 份文件不是物件")
        date = _require_nonempty_string(document.get("date"), "日期")
        if not re.fullmatch(r"\d{4}", date):
            raise SummaryValidationError(f"日期格式錯誤：{date}")
        if date in dates:
            raise SummaryValidationError(f"日期重複：{date}")
        dates.add(date)
        group = _require_nonempty_string(document.get("group"), "組別", date)
        if group not in EXPECTED_GROUP_PHASES:
            raise SummaryValidationError(f"未知組別：{group}（{date}）")
        phase = _require_nonempty_string(document.get("phase"), "分期", date)
        if phase not in EXPECTED_GROUP_PHASES[group]:
            raise SummaryValidationError(f"未知分期：{phase}（{date}／{group}）")
        categories = _require_list(document.get("categories"), f"{date} categories")
        if not categories:
            raise SummaryValidationError(f"零分類文件：{date}")
        category_order = _require_list(document.get("category_order"), f"{date} category_order")
        category_names = []
        for category_index, category in enumerate(categories, start=1):
            if not isinstance(category, dict):
                raise SummaryValidationError(f"{date} 第 {category_index} 個大分類不是物件")
            category_name = _require_nonempty_string(category.get("name"), "大分類名稱", date)
            category_names.append(category_name)
            topics = _require_list(category.get("topics"), f"{date}／{category_name} topics")
            for topic_index, topic in enumerate(topics, start=1):
                if not isinstance(topic, dict):
                    raise SummaryValidationError(
                        f"{date}／{category_name} 第 {topic_index} 個中主題不是物件"
                    )
                topic_name = _require_nonempty_string(topic.get("name"), "中主題名稱", date)
                _count_topic_materials(
                    topic,
                    context=f"{date}／{category_name}／{topic_name}",
                )
        if category_order != category_names:
            raise SummaryValidationError(f"大分類清單與 category_order 不一致：{date}")
    return documents


def _select_period_documents(documents):
    manual = [document for document in documents if document["group"] == "人工交接"]
    return OrderedDict(
        [
            (
                "人工 0501–0521",
                [document for document in manual if document["phase"] == "0501–0521"],
            ),
            (
                "人工 0527–0626",
                [document for document in manual if document["phase"] == "0527–0626"],
            ),
            ("人工 合併總表", manual),
            (
                "AI 對照組 0802–0811",
                [document for document in documents if document["group"] == "AI 對照組"],
            ),
        ]
    )


def _source_period_snapshot(documents):
    category_orders = []
    middle_topic_counts = []
    topic_name_records = []
    item_count_distribution = Counter()
    for document in documents:
        category_orders.append({"date": document["date"], "order": document["category_order"]})
        for category in document["categories"]:
            middle_topic_counts.append(
                {
                    "date": document["date"],
                    "category": category["name"],
                    "count": len(category["topics"]),
                }
            )
            for topic in category["topics"]:
                count = _count_topic_materials(
                    topic,
                    context=f"{document['date']}／{category['name']}／{topic['name']}",
                )
                topic_name_records.append(
                    {
                        "date": document["date"],
                        "category": category["name"],
                        "topic": topic["name"],
                        "item_count": count,
                    }
                )
                item_count_distribution[count] += 1
    return {
        "document_count": len(documents),
        "category_orders": category_orders,
        "middle_topic_counts": middle_topic_counts,
        "topic_name_records": topic_name_records,
        "topic_item_count_distribution": dict(sorted(item_count_distribution.items())),
    }


def _normalize_frequency(value, *, period):
    if not isinstance(value, dict):
        raise SummaryValidationError(f"aggregate 不守恆：{period} 素材則數分布不是物件")
    normalized = {}
    for raw_key, raw_count in value.items():
        try:
            key = int(raw_key)
        except (TypeError, ValueError) as error:
            raise SummaryValidationError(
                f"aggregate 不守恆：{period} 含非數字素材則數 {raw_key!r}"
            ) from error
        if not isinstance(raw_count, int) or isinstance(raw_count, bool):
            raise SummaryValidationError(
                f"aggregate 不守恆：{period} 含非數字分布次數 {raw_count!r}"
            )
        normalized[key] = raw_count
    return normalized


def _validate_input_aggregate(payload, period_documents):
    statistics_payload = payload.get("statistics")
    if not isinstance(statistics_payload, dict) or not isinstance(statistics_payload.get("periods"), dict):
        raise SummaryValidationError("缺少 input statistics.periods，無法驗證 aggregate 守恆")
    input_periods = statistics_payload["periods"]
    for period, documents in period_documents.items():
        actual = _source_period_snapshot(documents)
        reported = input_periods.get(period)
        if not isinstance(reported, dict):
            raise SummaryValidationError(f"aggregate 不守恆：缺少 {period}")
        if reported.get("document_count") != actual["document_count"]:
            raise SummaryValidationError(f"aggregate 不守恆：{period} 文件數不一致")
        if reported.get("category_orders") != actual["category_orders"]:
            raise SummaryValidationError(f"aggregate 不守恆：{period} 大分類順序不一致")
        if reported.get("middle_topic_counts") != actual["middle_topic_counts"]:
            raise SummaryValidationError(f"aggregate 不守恆：{period} 中主題數不一致")
        reported_records = reported.get("topic_name_records")
        if not isinstance(reported_records, list):
            raise SummaryValidationError(f"aggregate 不守恆：{period} 中主題名稱表不存在")
        for record in reported_records:
            if not isinstance(record, dict) or not isinstance(record.get("item_count"), int) or isinstance(record.get("item_count"), bool):
                raise SummaryValidationError(f"aggregate 不守恆：{period} 含非數字素材則數")
        if reported_records != actual["topic_name_records"]:
            raise SummaryValidationError(f"aggregate 不守恆：{period} 中主題名稱表不一致")
        normalized_distribution = _normalize_frequency(
            reported.get("topic_item_count_distribution"), period=period
        )
        if normalized_distribution != actual["topic_item_count_distribution"]:
            raise SummaryValidationError(f"aggregate 不守恆：{period} 素材則數分布不一致")


def _middle_topic_records(documents):
    records = []
    for document in documents:
        for category_position, category in enumerate(document["categories"], start=1):
            for topic_position, topic in enumerate(category["topics"], start=1):
                records.append(
                    {
                        "date": document["date"],
                        "group": document["group"],
                        "phase": document["phase"],
                        "category": category["name"],
                        "category_position": category_position,
                        "middle_topic": topic["name"],
                        "middle_topic_position": topic_position,
                        "item_count": _count_topic_materials(
                            topic,
                            context=f"{document['date']}／{category['name']}／{topic['name']}",
                        ),
                    }
                )
    return records


def _summarize_period(documents):
    category_orders = []
    category_occurrences = OrderedDict()
    topics_per_cell = []
    materials_per_topic = []
    category_count = 0
    middle_topic_count = 0
    material_count = 0

    for document in documents:
        category_orders.append(
            {
                "date": document["date"],
                "category_count": len(document["categories"]),
                "order": list(document["category_order"]),
            }
        )
        category_count += len(document["categories"])
        for category_position, category in enumerate(document["categories"], start=1):
            entry = category_occurrences.setdefault(
                category["name"], {"dates": [], "positions": Counter()}
            )
            entry["dates"].append(document["date"])
            entry["positions"][category_position] += 1
            topic_count = len(category["topics"])
            topics_per_cell.append(topic_count)
            middle_topic_count += topic_count
            for topic in category["topics"]:
                count = _count_topic_materials(
                    topic,
                    context=f"{document['date']}／{category['name']}／{topic['name']}",
                )
                materials_per_topic.append(count)
                material_count += count

    document_count = len(documents)
    category_presence = OrderedDict()
    for category_name, entry in category_occurrences.items():
        appearance_count = len(entry["dates"])
        category_presence[category_name] = {
            "document_count": document_count,
            "appearance_count": appearance_count,
            "appearance_rate": round(appearance_count / document_count, 6) if document_count else None,
            "source_dates": entry["dates"],
            "positions": {str(position): count for position, count in sorted(entry["positions"].items())},
        }

    return {
        "document_count": document_count,
        "category_count": category_count,
        "middle_topic_count": middle_topic_count,
        "material_count": material_count,
        "category_orders": category_orders,
        "category_presence": category_presence,
        "middle_topics_per_cell": _distribution(topics_per_cell),
        "items_per_middle_topic": _distribution(materials_per_topic),
    }


def _keyword_crosstab(documents, keyword_topics, review_overrides, likely_misses):
    output = OrderedDict()
    for label, keywords in keyword_topics.items():
        if not isinstance(keywords, list) or not keywords or not all(
            isinstance(keyword, str) and keyword for keyword in keywords
        ):
            raise SummaryValidationError(f"關鍵主題「{label}」的關鍵詞必須是非空字串陣列")
        occurrences = []
        category_counts = Counter()
        for document in documents:
            for category_position, category in enumerate(document["categories"], start=1):
                for topic_position, topic in enumerate(category["topics"], start=1):
                    names = [topic["name"]] + [subtopic["name"] for subtopic in topic["subtopics"]]
                    matched_terms = [
                        keyword for keyword in keywords if any(keyword in name for name in names)
                    ]
                    if not matched_terms:
                        continue
                    occurrence_id = (
                        f"{label}|{document['date']}|{category_position}|{topic_position}"
                    )
                    category_counts[category["name"]] += 1
                    occurrences.append(
                        {
                            "occurrence_id": occurrence_id,
                            "date": document["date"],
                            "group": document["group"],
                            "phase": document["phase"],
                            "category": category["name"],
                            "middle_topic": topic["name"],
                            "matched_terms": matched_terms,
                            "review_status": review_overrides.get(occurrence_id, "unreviewed"),
                        }
                    )
        output[label] = {
            "keywords": list(keywords),
            "is_ground_truth": False,
            "counts_by_category": dict(sorted(category_counts.items())),
            "occurrences": occurrences,
            "likely_misses": list(likely_misses.get(label, [])),
        }
    return output


def _diagnostic_summary(documents):
    kinds = OrderedDict()
    for document in documents:
        diagnostics = document.get("diagnostics", [])
        if not isinstance(diagnostics, list):
            raise SummaryValidationError(f"diagnostics 必須是陣列（{document['date']}）")
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, dict):
                raise SummaryValidationError(f"diagnostic 不是物件（{document['date']}）")
            kind = _require_nonempty_string(diagnostic.get("kind"), "diagnostic kind", document["date"])
            line_number = diagnostic.get("line_number")
            if line_number is not None and (not isinstance(line_number, int) or isinstance(line_number, bool)):
                raise SummaryValidationError(f"diagnostic 行號不是整數（{document['date']}／{kind}）")
            entry = kinds.setdefault(kind, {"count": 0, "locations": []})
            entry["count"] += 1
            entry["locations"].append({"date": document["date"], "line_number": line_number})
    return kinds


def _conservation(documents, period_summaries, records):
    input_counts = {
        "documents": len(documents),
        "categories": sum(len(document["categories"]) for document in documents),
        "middle_topics": len(records),
        "materials": sum(record["item_count"] for record in records),
    }
    manual_phases = period_summaries["人工 0501–0521"], period_summaries["人工 0527–0626"]
    ai = period_summaries["AI 對照組 0802–0811"]
    aggregated_counts = {
        "documents": sum(period["document_count"] for period in manual_phases) + ai["document_count"],
        "categories": sum(period["category_count"] for period in manual_phases) + ai["category_count"],
        "middle_topics": sum(period["middle_topic_count"] for period in manual_phases) + ai["middle_topic_count"],
        "materials": sum(period["material_count"] for period in manual_phases) + ai["material_count"],
    }
    checks = {
        key: "PASS" if input_counts[key] == aggregated_counts[key] else "FAIL"
        for key in input_counts
    }
    overall = "PASS" if all(value == "PASS" for value in checks.values()) else "FAIL"
    if overall != "PASS":
        raise SummaryValidationError("聚合守恆檢查失敗")
    return {
        "input": input_counts,
        "aggregated": aggregated_counts,
        "checks": checks,
        "overall": overall,
    }


def summarize_payload(
    payload,
    *,
    keyword_topics=None,
    review_overrides=None,
    likely_misses=None,
):
    """驗證完整解析 JSON 並回傳不含全文的統計聚合。"""
    documents = _validate_documents(payload)
    period_documents = _select_period_documents(documents)
    _validate_input_aggregate(payload, period_documents)
    records = _middle_topic_records(documents)
    period_summaries = OrderedDict(
        (period, _summarize_period(selected))
        for period, selected in period_documents.items()
    )
    keyword_topics = keyword_topics or DEFAULT_KEYWORD_TOPICS
    review_overrides = KEYWORD_REVIEW_OVERRIDES if review_overrides is None else review_overrides
    likely_misses = LIKELY_MISSES if likely_misses is None else likely_misses
    result = {
        "schema_version": 1,
        "source_scope": "23 份人工交接與 10 份 AI 對照稿的去全文聚合",
        "quartile_method": QUARTILE_METHOD,
        "periods": period_summaries,
        "middle_topic_records": records,
        "keyword_crosstab": _keyword_crosstab(
            documents, keyword_topics, review_overrides, likely_misses
        ),
        "diagnostics": _diagnostic_summary(documents),
    }
    result["conservation"] = _conservation(documents, period_summaries, records)
    return result


def _format_stat(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _render_markdown(result):
    lines = [
        "# S2 P0 歷史語料統計摘要",
        "",
        "## 統計口徑",
        "",
        f"- 四分位數：{result['quartile_method']}",
        "- 人工兩期分列，另列人工合併總表；AI 對照組單列，不混合平均。",
        "- 關鍵詞命中僅供人工覆核，不宣稱為分類真值。",
        "",
        "## 守恆",
        "",
        f"- 守恆檢查：{result['conservation']['overall']}",
    ]
    for key, value in result["conservation"]["input"].items():
        lines.append(
            f"- {key}：input {value}／aggregated {result['conservation']['aggregated'][key]}／"
            f"{result['conservation']['checks'][key]}"
        )

    lines.extend(["", "## 分期摘要", ""])
    headers = "| 分期 | 文件 | 大分類 | 中主題 | 素材則數 | 每格中主題 median | 每中主題素材 median |"
    lines.extend([headers, "|---|---:|---:|---:|---:|---:|---:|"])
    for period, data in result["periods"].items():
        lines.append(
            f"| {period} | {data['document_count']} | {data['category_count']} | "
            f"{data['middle_topic_count']} | {data['material_count']} | "
            f"{_format_stat(data['middle_topics_per_cell']['summary']['median'])} | "
            f"{_format_stat(data['items_per_middle_topic']['summary']['median'])} |"
        )

    lines.extend(["", "## 大分類出現率與位置", ""])
    for period, data in result["periods"].items():
        lines.extend([f"### {period}", "", "| 大分類 | 出現份數 | 出現率 | 位置分布 | 來源日期 |", "|---|---:|---:|---|---|"])
        for category, presence in data["category_presence"].items():
            positions = "、".join(
                f"第{position}格×{count}" for position, count in presence["positions"].items()
            )
            lines.append(
                f"| {category} | {presence['appearance_count']} | "
                f"{presence['appearance_rate']:.1%} | {positions} | "
                f"{', '.join(presence['source_dates'])} |"
            )
        lines.append("")

    lines.extend(["## 關鍵主題機械命中", ""])
    for label, data in result["keyword_crosstab"].items():
        statuses = Counter(occurrence["review_status"] for occurrence in data["occurrences"])
        status_text = "、".join(f"{status} {count}" for status, count in sorted(statuses.items())) or "無命中"
        lines.append(
            f"- {label}：{len(data['occurrences'])} 筆；覆核狀態 {status_text}；"
            f"likely miss {len(data['likely_misses'])} 筆。"
        )
    lines.append("")
    return "\n".join(lines)


def _render_diagnostic_review(result):
    lines = [
        "# S2 P0 解析診斷覆核",
        "",
        "本檔不收錄診斷原文，只保留聚合數量、來源日期與行號，以免把素材全文帶入 repo。",
        "",
        "## 診斷總表",
        "",
        "| 類型 | 數量 | 來源日期與行號（抽樣） | 初步判定 |",
        "|---|---:|---|---|",
    ]
    default_dispositions = {
        "空分類": "待人工覆核是否為樣板空格",
        "未辨識行": "待人工覆核是否為檔頭、圖例或漏解析內容",
        "RTF 編碼修正": "讀取層修復；需抽樣核對中文名稱",
        "RTF 轉換容錯": "讀取層容錯；需抽樣核對結構",
    }
    for kind, data in result["diagnostics"].items():
        samples = "、".join(
            f"{location['date']}:{location['line_number'] if location['line_number'] is not None else 'N/A'}"
            for location in data["locations"][:8]
        )
        lines.append(
            f"| {kind} | {data['count']} | {samples} | "
            f"{default_dispositions.get(kind, '待人工覆核')} |"
        )
    lines.extend(
        [
            "",
            "## 統計影響",
            "",
            "- 本檔由工具提供去全文的診斷索引；人工抽樣結論須在正式驗收前補齊。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_csv(records, path):
    fieldnames = [
        "日期",
        "組別",
        "分期",
        "大分類",
        "大分類位置",
        "中主題",
        "中主題位置",
        "素材則數",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "日期": record["date"],
                    "組別": record["group"],
                    "分期": record["phase"],
                    "大分類": record["category"],
                    "大分類位置": record["category_position"],
                    "中主題": record["middle_topic"],
                    "中主題位置": record["middle_topic_position"],
                    "素材則數": record["item_count"],
                }
            )


def write_outputs(payload, output_dir):
    """產生固定命名的 JSON、Markdown、CSV 與去全文診斷覆核索引。"""
    result = summarize_payload(payload)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "json": output_dir / JSON_FILENAME,
        "markdown": output_dir / MARKDOWN_FILENAME,
        "csv": output_dir / CSV_FILENAME,
        "diagnostic_review": output_dir / DIAGNOSTIC_FILENAME,
    }
    outputs["json"].write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    outputs["markdown"].write_text(_render_markdown(result), encoding="utf-8")
    _write_csv(result["middle_topic_records"], outputs["csv"])
    outputs["diagnostic_review"].write_text(
        _render_diagnostic_review(result), encoding="utf-8"
    )
    return outputs


def _load_payload(path):
    try:
        with Path(path).open(encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as error:
        raise SummaryValidationError(f"無法讀取 input JSON：{error}") from error


def _validate_full_corpus_counts(payload):
    documents = payload.get("documents", [])
    counts = Counter(document.get("group") for document in documents if isinstance(document, dict))
    if counts != {"人工交接": 23, "AI 對照組": 10}:
        raise SummaryValidationError(
            "正式 corpus 必須是 23 份人工交接與 10 份 AI 對照稿；"
            f"目前為人工 {counts.get('人工交接', 0)}／AI {counts.get('AI 對照組', 0)}"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="將 s2_p0_history.py 完整 JSON 轉成不含素材全文的 P0 歷史聚合。"
    )
    parser.add_argument("--input", type=Path, required=True, help="完整解析 JSON")
    parser.add_argument("--output-dir", type=Path, required=True, help="正式輸出目錄")
    args = parser.parse_args(argv)
    try:
        payload = _load_payload(args.input)
        _validate_full_corpus_counts(payload)
        outputs = write_outputs(payload, args.output_dir)
    except SummaryValidationError as error:
        parser.error(str(error))
    print(
        "已輸出：" + "、".join(str(path) for path in outputs.values()),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
