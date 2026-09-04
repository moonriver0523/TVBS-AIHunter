# -*- coding: utf-8 -*-
"""離線解析 S2 歷史交接語料，供 P0 分類實證分析使用。

此工具只讀取指定的歷史交接檔；不讀寫當日 state、不觸發 render，也不碰排程。
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys


MANUAL_TXT_DATES = ["0501", "0503", "0504", "0505", "0506", "0507", "0512", "0517", "0518", "0521"]
MANUAL_RTF_DATES = ["0527", "0531", "0601", "0603", "0606", "0607", "0608", "0613", "0614", "0620", "0621", "0625", "0626"]
AI_DATES = ["0802", "0803", "0804", "0805", "0806", "0807", "0808", "0809", "0810", "0811"]

DEFAULT_MANUAL_DIR = Path(r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive\晚班交接歷史範例")
DEFAULT_ARCHIVE_DIR = Path(r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive")
DEFAULT_KEYWORD_TOPICS = {
    "美股": ["美股", "華爾街", "道瓊", "那斯達克", "標普"],
    "美國體育": ["美國體育", "NBA", "MLB", "NFL", "美式足球", "美職"],
    "颱風傷亡": ["颱風", "颱風傷亡", "風災"],
    "軟性趣味": ["軟性趣味", "趣聞", "趣味", "暖聞"],
}

_CATEGORY = re.compile(r"^={4,}\s*(.*?)\s*={6,}\s*$")
_TOPIC = re.compile(r"^【\s*(.*?)\s*】$")
_SOURCE_DATE = re.compile(r"^(\d{4})")
_MATERIAL = re.compile(
    r"^[△▲●■◇◆🔴🟡🟤]?\s*(?:\d{1,2}:\d{2}(?::\d{2})?|"
    r"(?:APCCTV|AP|RT|CNN|NHK|ABC|IN|NS|YT|SIDE|PO|WE|JL|NE|PY)"
    r"[A-Za-z0-9_.-]*)\b",
    re.IGNORECASE,
)
_HEADER_METADATA = (
    ("文件名", re.compile(r"^\d{4}\s+晚班交接$")),
    ("時間窗", re.compile(r"^時間窗：")),
    ("總數", re.compile(r"^收錄外電共")),
    ("標記圖例", re.compile(r"^標記：")),
)
_HEADER_HIGHLIGHT = re.compile(r"^🔴\s*重大：\s*(.*)$")
_HEADER_MARKER = re.compile(r"^([△▲●■◇◆🔴🟡🟤])\s*")
_CNN_MATERIAL_CODE = re.compile(r"^(CNN\s+\d{2}-\d{2}\s+\d{6})\b", re.IGNORECASE)
_GENERIC_MATERIAL_CODE = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*)\b")
_IGNORED_LINE_PATTERNS = (
    ("RTF 字型表殘屑", re.compile(r"^Microsoft\s+Sans\s+Serif;$", re.IGNORECASE)),
    ("純分隔殘屑", re.compile(r"^[;:|/\\\-_.#~*]+$")),
    ("錄帶／傳送註記", re.compile(r"^CNN目前只傳了.+[：:]$")),
    ("交班／錄帶註記", re.compile(r"^.+(?:小夜值班已出|小夜出了|求諒解)$")),
    ("錄帶／傳送註記", re.compile(r"^(?:AP繼續錄|叫錄|AP叫錄)")),
    ("待補畫面註記", re.compile(r"^等.+畫面$")),
)
_CP1252_REVERSE = {
    character: byte
    for byte in range(0x80, 0x100)
    for character in [bytes([byte]).decode("cp1252", errors="ignore")]
    if character
}
_OBVIOUS_MOJIBAKE_MARKERS = frozenset("¤")
_RTF_CHARSET_ENCODINGS = {
    0: "cp1252",
    134: "gb18030",
    136: "cp950",
}
_RTF_DESTINATIONS = frozenset({
    "annotation", "author", "colortbl", "comment", "creatim", "datafield",
    "doccomm", "docvar", "filetbl", "fontemb", "fontfile", "fonttbl", "footer",
    "footerf", "footerl", "footerr", "footnote", "generator", "header",
    "headerf", "headerl", "headerr", "info", "latentstyles", "list", "listlevel",
    "listname", "listoverridetable", "listtable", "nonshppict", "object",
    "objdata", "pict", "private", "revtbl", "rsidtbl", "shp", "shpinst",
    "shppict", "stylesheet", "themedata", "xmlnstbl",
})
_RTF_SPECIAL_WORDS = {
    "bullet": "•",
    "emdash": "—",
    "emspace": " ",
    "endash": "–",
    "enspace": " ",
    "ldblquote": "“",
    "lquote": "‘",
    "qmspace": " ",
    "rdblquote": "”",
    "rquote": "’",
}


class CorpusDiscoveryError(RuntimeError):
    """指定的 P0 語料集不完整或包含不應納入的來源。"""


class SourceReadError(RuntimeError):
    """來源文字無法安全讀取或轉換。"""


class CorpusAnalysisError(RuntimeError):
    """語料解析結果不完整，不能產出可供決策使用的統計。"""


def _manual_phase(date):
    if date in MANUAL_TXT_DATES:
        return "0501–0521"
    if date in MANUAL_RTF_DATES:
        return "0527–0626"
    raise CorpusDiscoveryError(f"人工語料日期不在 P0 範圍：{date}")


def _source_record(path, *, date, group, phase):
    return {"path": path, "date": date, "group": group, "phase": phase}


def discover_corpus(manual_dir, archive_dir):
    """發現並嚴格驗證 P0 的 23 份人工與 10 份 AI canonical 語料。"""
    manual_dir = Path(manual_dir)
    archive_dir = Path(archive_dir)
    if not manual_dir.is_dir():
        raise CorpusDiscoveryError(f"人工語料目錄不存在：{manual_dir}")
    if not archive_dir.is_dir():
        raise CorpusDiscoveryError(f"AI Archive 目錄不存在：{archive_dir}")

    manual_files = []
    for path in manual_dir.iterdir():
        if not path.is_file():
            continue
        match = _SOURCE_DATE.match(path.name)
        if match:
            manual_files.append((match.group(1), path))

    txt_by_date = {date: [] for date in MANUAL_TXT_DATES}
    rtf_by_date = {date: [] for date in MANUAL_RTF_DATES}
    unexpected_manual = []
    for date, path in manual_files:
        if date in txt_by_date and path.suffix.lower() == ".txt":
            txt_by_date[date].append(path)
        elif date in rtf_by_date and path.suffix.lower() == ".rtf":
            rtf_by_date[date].append(path)
        else:
            unexpected_manual.append(path.name)

    missing_txt = [date for date, paths in txt_by_date.items() if len(paths) != 1]
    missing_rtf = [date for date, paths in rtf_by_date.items() if len(paths) != 1]
    duplicate_dates = [
        date for date, paths in {**txt_by_date, **rtf_by_date}.items() if len(paths) > 1
    ]
    if missing_txt or missing_rtf or duplicate_dates or unexpected_manual:
        details = []
        if missing_txt:
            details.append(f"TXT 日期數量不符：{','.join(missing_txt)}")
        if missing_rtf:
            details.append(f"RTF 日期數量不符：{','.join(missing_rtf)}")
        if duplicate_dates:
            details.append(f"日期重複：{','.join(duplicate_dates)}")
        if unexpected_manual:
            details.append(f"不預期檔案：{','.join(unexpected_manual)}")
        raise CorpusDiscoveryError("人工語料必須剛好 10 TXT＋13 RTF＝23 份；" + "；".join(details))

    manual_sources = []
    for date in MANUAL_TXT_DATES + MANUAL_RTF_DATES:
        paths = txt_by_date.get(date) or rtf_by_date.get(date)
        manual_sources.append(
            _source_record(paths[0], date=date, group="人工交接", phase=_manual_phase(date))
        )

    ai_sources = []
    missing_ai = []
    for date in AI_DATES:
        path = archive_dir / f"2026{date}" / f"{date}晚班交接.txt"
        if not path.is_file():
            missing_ai.append(str(path))
            continue
        ai_sources.append(
            _source_record(path, date=date, group="AI 對照組", phase="0802–0811")
        )
    if missing_ai or len(ai_sources) != 10:
        raise CorpusDiscoveryError(
            "AI 對照組必須剛好 10 份 canonical MMDD晚班交接.txt；缺少：" + "；".join(missing_ai)
        )

    return manual_sources + ai_sources


class _RtfDecodeState:
    def __init__(self, font, uc_skip=1, skip_destination=False, pending_ignorable=False, unicode_fallback=0):
        self.font = font
        self.uc_skip = uc_skip
        self.skip_destination = skip_destination
        self.pending_ignorable = pending_ignorable
        self.unicode_fallback = unicode_fallback

    def copy(self):
        return _RtfDecodeState(
            self.font,
            self.uc_skip,
            self.skip_destination,
            self.pending_ignorable,
            self.unicode_fallback,
        )


def _rtf_font_table(raw):
    default_match = re.search(r"\\deff(\d+)", raw[:4096])
    default_font = int(default_match.group(1)) if default_match else 0
    fonts = {}
    for match in re.finditer(
        r"\{\\f(\d+)\b(?:(?![{}]).)*?\\fcharset(\d+)\b(?:(?![{}]).)*?;",
        raw,
        flags=re.DOTALL,
    ):
        fonts[int(match.group(1))] = int(match.group(2))
    return default_font, fonts


def decode_font_aware_rtf(data):
    """依 fonttbl／目前 \\fN 的 fcharset 解碼 RTF hex，不猜測輸出文字編碼。"""
    raw = data.decode("latin1")
    default_font, fonts = _rtf_font_table(raw)
    state = _RtfDecodeState(font=default_font)
    stack = []
    output = []
    encoded = bytearray()
    encoded_charset = None
    encoded_font = None
    replacement_count = 0

    def require_font(font_id):
        if font_id not in fonts:
            raise SourceReadError(
                f"未知 RTF font f{font_id}，不在 fonttbl，拒絕猜測編碼"
            )
        return fonts[font_id]

    def current_charset():
        return require_font(state.font)

    def flush():
        nonlocal encoded_charset, encoded_font, replacement_count
        if not encoded:
            return
        charset = encoded_charset if encoded_charset is not None else 0
        encoding = _RTF_CHARSET_ENCODINGS.get(charset)
        if encoding is None:
            raise SourceReadError(
                f"不支援的 RTF fcharset {charset}（font f{encoded_font if encoded_font is not None else state.font}），拒絕猜測編碼"
            )
        decoded = bytes(encoded).decode(encoding, errors="replace")
        replacement_count += decoded.count("�")
        if not state.skip_destination:
            output.append(decoded)
        encoded.clear()
        encoded_charset = None
        encoded_font = None

    def add_hex(value):
        nonlocal encoded_charset, encoded_font
        if state.unicode_fallback:
            state.unicode_fallback -= 1
            return
        charset = current_charset()
        if encoded and encoded_charset != charset:
            flush()
        encoded_charset = charset
        encoded_font = state.font
        encoded.append(value)

    index = 0
    while index < len(raw):
        character = raw[index]
        if character == "{":
            flush()
            stack.append(state.copy())
            index += 1
            continue
        if character == "}":
            flush()
            if stack:
                state = stack.pop()
            index += 1
            continue
        if character != "\\":
            flush()
            if state.unicode_fallback:
                state.unicode_fallback -= 1
            elif not state.skip_destination and character not in "\r\n":
                output.append(character)
            index += 1
            continue

        if index + 1 >= len(raw):
            break
        symbol = raw[index + 1]
        if symbol == "'" and index + 3 < len(raw):
            hexadecimal = raw[index + 2:index + 4]
            if re.fullmatch(r"[0-9A-Fa-f]{2}", hexadecimal):
                add_hex(int(hexadecimal, 16))
                index += 4
                continue
        flush()
        index += 2
        if symbol in "\\{}":
            if state.unicode_fallback:
                state.unicode_fallback -= 1
            elif not state.skip_destination:
                output.append(symbol)
            continue
        if symbol == "*":
            state.pending_ignorable = True
            continue
        if symbol == "~":
            if not state.skip_destination:
                output.append("\u00a0")
            continue
        if symbol == "-":
            if not state.skip_destination:
                output.append("\u00ad")
            continue
        if symbol == "_":
            if not state.skip_destination:
                output.append("‑")
            continue
        if not symbol.isalpha():
            continue

        start = index - 1
        while index < len(raw) and raw[index].isalpha():
            index += 1
        word = raw[start:index]
        sign = 1
        if index < len(raw) and raw[index] in "+-":
            sign = -1 if raw[index] == "-" else 1
            index += 1
        number_start = index
        while index < len(raw) and raw[index].isdigit():
            index += 1
        number = sign * int(raw[number_start:index]) if index > number_start else None
        if index < len(raw) and raw[index] == " ":
            index += 1

        if state.pending_ignorable:
            state.skip_destination = True
            state.pending_ignorable = False
        if word in _RTF_DESTINATIONS:
            state.skip_destination = True
        if word == "bin" and number is not None:
            index += max(number, 0)
            continue
        if word == "f" and number is not None:
            if not state.skip_destination:
                require_font(number)
            state.font = number
            continue

        if word == "plain":
            state.font = default_font
            continue
        if word == "uc" and number is not None:
            state.uc_skip = max(number, 0)
            continue
        if word == "u" and number is not None:
            if not state.skip_destination:
                codepoint = number if number >= 0 else number + 65536
                output.append(chr(codepoint))
            state.unicode_fallback = state.uc_skip
            continue
        if state.skip_destination:
            continue
        if word in {"par", "line", "page", "row"}:
            output.append("\n")
        elif word in {"tab", "cell"}:
            output.append("\t")
        elif word in _RTF_SPECIAL_WORDS:
            output.append(_RTF_SPECIAL_WORDS[word])

    flush()
    text = "\n".join(line.rstrip() for line in "".join(output).splitlines()).strip()
    return text, {
        "default_font": default_font,
        "font_charsets": fonts,
        "replacement_characters": replacement_count,
        "unclosed_groups": len(stack),
    }


def _cjk_count(text):
    return sum("㐀" <= character <= "鿿" for character in text)


def _mojibake_metrics(text):
    replacement = text.count("�")
    controls = sum("\x80" <= character <= "\x9f" for character in text)
    private_or_bopomofo = sum(
        "" <= character <= "" or "ㄅ" <= character <= "ㆺ"
        for character in text
    )
    byteish = sum(
        character != "·"
        and (" " <= character <= "ÿ" or character in _CP1252_REVERSE)
        for character in text
    )
    return replacement, controls, private_or_bopomofo, byteish


def _cjk_adjacent_byteish_count(text):
    count = 0
    for index, character in enumerate(text):
        if character.isalpha() or character in "·…°±×÷©®¥£€":
            continue
        if not (" " <= character <= "ÿ" or character in _CP1252_REVERSE):
            continue
        left_is_cjk = index > 0 and _cjk_count(text[index - 1]) == 1
        right_is_cjk = index + 1 < len(text) and _cjk_count(text[index + 1]) == 1
        count += left_is_cjk or right_is_cjk
    return count


def _two_byte_cjk_mojibake_count(text):
    """殘餘 °ê 類非字母兩字元錯解。連續合法重音（ÀÉÎ／ééé）不得當 mojibake。"""
    count = 0
    for index in range(len(text) - 1):
        pair = text[index:index + 2]
        if any(not (128 <= ord(character) <= 255) for character in pair):
            continue
        if all(character.isalpha() for character in pair):
            continue
        raw = bytes(ord(character) for character in pair)
        for encoding in ("cp950", "gb18030"):
            try:
                decoded = raw.decode(encoding)
            except UnicodeDecodeError:
                continue
            if len(decoded) == 1 and _cjk_count(decoded) == 1:
                count += 1
                break
    return count


def find_mojibake_issues(text, *, residual_two_byte=False):
    """列出 replacement、控制字元、私用字／注音及（可選）殘餘兩字元錯解。"""
    issues = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        replacement, controls, private_or_bopomofo, _byteish = _mojibake_metrics(line)
        reasons = []
        if replacement:
            reasons.append("Unicode replacement character")
        if controls:
            reasons.append("C1 控制字元")
        if private_or_bopomofo:
            reasons.append("私用字或注音錯解序列")
        if any(character in _OBVIOUS_MOJIBAKE_MARKERS for character in line):
            reasons.append("常見 mojibake 標記")
        if _cjk_adjacent_byteish_count(line):
            reasons.append("中西文錯解夾雜序列")
        if residual_two_byte and _two_byte_cjk_mojibake_count(line):
            reasons.append("兩字元 Big5／GB mojibake")
        if reasons:
            issues.append({"line_number": line_number, "reasons": reasons, "text": line})
    return issues


def _read_source_text(path, *, pandoc_runner=None):
    path = Path(path)
    if path.suffix.lower() == ".txt":
        return path.read_text(encoding="utf-8-sig"), []
    if path.suffix.lower() != ".rtf":
        raise SourceReadError(f"不支援的來源副檔名：{path.suffix}（{path}）")

    diagnostics = []
    if pandoc_runner is not None:
        text = pandoc_runner(path)
    else:
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise SourceReadError(f"無法讀取 RTF 原始檔：{path}") from error
        text, metadata = decode_font_aware_rtf(payload)
        if metadata["replacement_characters"]:
            raise SourceReadError(
                f"RTF 解碼產生 Unicode replacement character，拒絕納入結構化輸出：{path}"
            )
        if metadata["unclosed_groups"]:
            raise SourceReadError(
                f"RTF 群組未閉合（{metadata['unclosed_groups']}），拒絕納入結構化輸出：{path}"
            )
    mojibake_issues = find_mojibake_issues(
        text,
        residual_two_byte=pandoc_runner is not None,
    )
    if mojibake_issues:
        locations = ", ".join(
            f"L{issue['line_number']}（{'、'.join(issue['reasons'])}）"
            for issue in mojibake_issues[:10]
        )
        if len(mojibake_issues) > 10:
            locations += f"，另 {len(mojibake_issues) - 10} 行"
        raise SourceReadError(f"RTF 仍含 mojibake，拒絕納入結構化輸出：{path}：{locations}")
    return text, diagnostics


def read_source_text(path, *, pandoc_runner=None):
    """讀取 UTF-8（含 BOM）TXT，或用 font-aware decoder 取得 RTF 純文字。"""
    text, _ = _read_source_text(path, pandoc_runner=pandoc_runner)
    return text


def _looks_like_material(line):
    return bool(_MATERIAL.match(line.strip()))


def _document_structured_text(document):
    values = []

    def collect(topics):
        for topic in topics:
            values.append(topic["name"])
            values.extend(item["text"] for item in topic["items"])
            for subtopic in topic["subtopics"]:
                values.append(subtopic["name"])
                values.extend(item["text"] for item in subtopic["items"])

    for category in document["categories"]:
        values.append(category["name"])
        collect(category["topics"])
    collect(document["unscoped_sections"]["topics"])
    return "\n".join(values)


def _new_topic(name, line_number, *, bracketed):
    return {
        "name": name,
        "line_number": line_number,
        "items": [],
        "subtopics": [],
        "format": "括號中主題" if bracketed else "純文字中主題",
    }


def _add_diagnostic(document, kind, text, line_number):
    document["diagnostics"].append(
        {"kind": kind, "text": text, "line_number": line_number}
    )


def _header_metadata_kind(line):
    for kind, pattern in _HEADER_METADATA:
        if pattern.match(line):
            return kind
    return None


def _ignored_line_reason(line):
    for reason, pattern in _IGNORED_LINE_PATTERNS:
        if pattern.match(line):
            return reason
    return None


def _parse_header_highlight(raw_line, line_number):
    match = _HEADER_HIGHLIGHT.match(raw_line.strip())
    if not match:
        return None
    remainder = match.group(1).strip()
    marker = None
    marker_match = _HEADER_MARKER.match(remainder)
    if marker_match:
        marker = marker_match.group(1)
        remainder = remainder[marker_match.end():].strip()
    code_match = _CNN_MATERIAL_CODE.match(remainder) or _GENERIC_MATERIAL_CODE.match(remainder)
    material_code = code_match.group(1) if code_match else None
    summary = remainder[code_match.end():].strip() if code_match else remainder
    return {
        "text": raw_line,
        "line_number": line_number,
        "marker": marker,
        "material_code": material_code,
        "summary": summary,
    }


def _looks_like_unscoped_prose_item(line):
    return len(line) >= 24 and any(mark in line for mark in "，。；：")


def _valid_unscoped_sequence(candidates):
    """驗證完整局部序列，避免未知前言因後方恰有素材而被整包升格。"""
    if len(candidates) < 2:
        return False
    first_line = candidates[0][1]
    if _looks_like_material(first_line) or first_line.startswith("+"):
        return False

    has_item = False
    index = 1
    while index < len(candidates):
        line = candidates[index][1]
        if _looks_like_material(line):
            has_item = True
            index += 1
            continue
        if line == "+":
            if index + 2 >= len(candidates):
                return False
            subtopic = candidates[index + 1][1]
            if not subtopic or subtopic.startswith("+") or _looks_like_material(subtopic):
                return False
            if not _looks_like_material(candidates[index + 2][1]):
                return False
            index += 2
            continue
        if line.startswith("+"):
            if not line[1:].strip() or index + 1 >= len(candidates):
                return False
            if not _looks_like_material(candidates[index + 1][1]):
                return False
            index += 1
            continue
        if (
            not has_item
            and index == 1
            and _looks_like_unscoped_prose_item(line)
            and index + 1 < len(candidates)
            and _looks_like_material(candidates[index + 1][1])
        ):
            has_item = True
            index += 1
            continue
        return False
    if not has_item:
        return False
    body = candidates[1:]
    if len(body) == 1 and _looks_like_material(body[0][1]):
        return False
    return True


def _unscoped_content_lines(lines, *, group):
    """只在人工檔頭符合完整「主題→素材／小分題」序列時啟用。"""
    if group != "人工交接":
        return set()
    candidates = []
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if _CATEGORY.match(line):
            break
        if not line or _header_metadata_kind(line) or _parse_header_highlight(raw_line, line_number):
            continue
        if _ignored_line_reason(line):
            continue
        candidates.append((line_number, line))
    if not _valid_unscoped_sequence(candidates):
        return set()
    return {line_number for line_number, _ in candidates}


def parse_document_text(text, *, date, group, phase):
    """解析一份交接文字，保留分類、主題、素材與來源行號的原始順序。

    格式差異會記進 diagnostics；本工具不以猜測補造分類，也不靜默丟棄文字。
    """
    lines = text.splitlines()
    unscoped_line_numbers = _unscoped_content_lines(lines, group=group)
    document = {
        "date": date,
        "group": group,
        "phase": phase,
        "category_order": [],
        "categories": [],
        "unscoped_sections": {"kind": "未指定大分類內容", "topics": []},
        "header_metadata": [],
        "header_highlights": [],
        "ignored_lines": [],
        "unrecognized_lines": [],
        "diagnostics": [],
    }
    category = None
    topic = None
    subtopic = None
    unscoped_topic = None
    unscoped_subtopic = None
    unscoped_expects_subtopic = False
    expects_subtopic = False
    previous_was_blank = True

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            previous_was_blank = True
            continue

        category_match = _CATEGORY.match(line)
        if category_match:
            category = {
                "name": category_match.group(1),
                "line_number": line_number,
                "topics": [],
                "is_empty": False,
            }
            document["categories"].append(category)
            document["category_order"].append(category["name"])
            topic = None
            subtopic = None
            expects_subtopic = False
            previous_was_blank = False
            continue

        if category is None:
            metadata_kind = _header_metadata_kind(line)
            if metadata_kind:
                document["header_metadata"].append(
                    {"kind": metadata_kind, "text": raw_line, "line_number": line_number}
                )
                previous_was_blank = False
                continue
            highlight = _parse_header_highlight(raw_line, line_number)
            if highlight:
                document["header_highlights"].append(highlight)
                previous_was_blank = False
                continue
            ignored_reason = _ignored_line_reason(line)
            if ignored_reason:
                document["ignored_lines"].append(
                    {"text": raw_line, "line_number": line_number, "reason": ignored_reason}
                )
                previous_was_blank = False
                continue
            if line_number in unscoped_line_numbers:
                if unscoped_topic is None:
                    topic_match = _TOPIC.match(line)
                    unscoped_topic = _new_topic(
                        topic_match.group(1) if topic_match else line,
                        line_number,
                        bracketed=bool(topic_match),
                    )
                    document["unscoped_sections"]["topics"].append(unscoped_topic)
                elif line == "+":
                    unscoped_subtopic = None
                    unscoped_expects_subtopic = True
                elif line.startswith("+"):
                    name = line[1:].strip()
                    unscoped_subtopic = {"name": name, "line_number": line_number, "items": []}
                    unscoped_topic["subtopics"].append(unscoped_subtopic)
                    unscoped_expects_subtopic = False
                elif unscoped_expects_subtopic:
                    unscoped_subtopic = {"name": line, "line_number": line_number, "items": []}
                    unscoped_topic["subtopics"].append(unscoped_subtopic)
                    unscoped_expects_subtopic = False
                else:
                    item = {"text": raw_line, "line_number": line_number}
                    if unscoped_subtopic is not None:
                        unscoped_subtopic["items"].append(item)
                    else:
                        unscoped_topic["items"].append(item)
                previous_was_blank = False
                continue

            entry = {"text": raw_line, "line_number": line_number}
            document["unrecognized_lines"].append(entry)
            _add_diagnostic(document, "未辨識行", raw_line, line_number)
            previous_was_blank = False
            continue

        topic_match = _TOPIC.match(line)
        if topic_match:
            topic = _new_topic(topic_match.group(1), line_number, bracketed=True)
            category["topics"].append(topic)
            subtopic = None
            expects_subtopic = True
            previous_was_blank = False
            continue

        if line == "+" and topic is not None and topic["format"] == "括號中主題":
            subtopic = None
            expects_subtopic = True
            previous_was_blank = False
            continue

        if topic is None:
            if _looks_like_material(line):
                entry = {"text": raw_line, "line_number": line_number}
                document["unrecognized_lines"].append(entry)
                _add_diagnostic(document, "未辨識行", raw_line, line_number)
            else:
                topic = _new_topic(line, line_number, bracketed=False)
                category["topics"].append(topic)
            previous_was_blank = False
            continue

        if expects_subtopic:
            expects_subtopic = False
            if _looks_like_material(line):
                topic["items"].append({"text": raw_line, "line_number": line_number})
            else:
                subtopic = {"name": line, "line_number": line_number, "items": []}
                topic["subtopics"].append(subtopic)
            previous_was_blank = False
            continue

        if topic["format"] == "純文字中主題" and previous_was_blank and not _looks_like_material(line):
            topic = _new_topic(line, line_number, bracketed=False)
            category["topics"].append(topic)
            subtopic = None
        elif subtopic is not None:
            subtopic["items"].append({"text": raw_line, "line_number": line_number})
        else:
            topic["items"].append({"text": raw_line, "line_number": line_number})
        previous_was_blank = False

    if not document["categories"]:
        _add_diagnostic(document, "解析失敗", "找不到任何大分類", None)
    for parsed_category in document["categories"]:
        parsed_category["is_empty"] = not parsed_category["topics"]
        if parsed_category["is_empty"]:
            _add_diagnostic(
                document,
                "空分類",
                parsed_category["name"],
                parsed_category["line_number"],
            )
    structured_text = _document_structured_text(document)
    for highlight in document["header_highlights"]:
        code = highlight.get("material_code")
        if code and code not in structured_text:
            _add_diagnostic(
                document,
                "orphan highlight",
                highlight["text"],
                highlight["line_number"],
            )
    return document


def _topic_item_count(topic):
    return len(topic["items"]) + sum(len(subtopic["items"]) for subtopic in topic["subtopics"])


def _topic_names(topic):
    return [topic["name"]] + [subtopic["name"] for subtopic in topic["subtopics"]]


def _summarize_period(documents):
    category_orders = []
    middle_topic_counts = []
    topic_name_records = []
    item_counts = []
    topic_names = []
    seen_topic_names = set()

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
                count = _topic_item_count(topic)
                item_counts.append(count)
                topic_name_records.append(
                    {
                        "date": document["date"],
                        "category": category["name"],
                        "topic": topic["name"],
                        "item_count": count,
                    }
                )
                if topic["name"] not in seen_topic_names:
                    seen_topic_names.add(topic["name"])
                    topic_names.append(topic["name"])

    return {
        "document_count": len(documents),
        "category_orders": category_orders,
        "middle_topic_counts": middle_topic_counts,
        "topic_item_count_distribution": dict(sorted(Counter(item_counts).items())),
        "topic_names": topic_names,
        "topic_name_records": topic_name_records,
    }


def _keyword_crosstab(documents, keyword_topics):
    output = {}
    for label, keywords in keyword_topics.items():
        if not isinstance(keywords, list) or not all(isinstance(word, str) for word in keywords):
            raise ValueError(f"關鍵主題「{label}」的關鍵詞必須是字串陣列")
        counts = Counter()
        occurrences = []
        for document in documents:
            for category in document["categories"]:
                for topic in category["topics"]:
                    names = _topic_names(topic)
                    matched_names = [
                        name for name in names if any(keyword in name for keyword in keywords)
                    ]
                    if not matched_names:
                        continue
                    counts[category["name"]] += 1
                    occurrences.append(
                        {
                            "date": document["date"],
                            "group": document["group"],
                            "phase": document["phase"],
                            "category": category["name"],
                            "middle_topic": topic["name"],
                            "matched_names": matched_names,
                        }
                    )
        output[label] = {
            "keywords": keywords,
            "counts_by_category": dict(sorted(counts.items())),
            "occurrences": occurrences,
        }
    return output


def build_statistics(documents, *, keyword_topics=None):
    """彙整規劃 §3a 所需的分類順序、量粒度、名稱表與跨格表。"""
    if keyword_topics is None:
        keyword_topics = DEFAULT_KEYWORD_TOPICS
    periods = {}
    manual_documents = [document for document in documents if document["group"] == "人工交接"]
    for phase in ("0501–0521", "0527–0626"):
        periods[f"人工 {phase}"] = _summarize_period(
            [document for document in manual_documents if document["phase"] == phase]
        )
    periods["人工 合併總表"] = _summarize_period(manual_documents)

    for group in sorted({document["group"] for document in documents if document["group"] != "人工交接"}):
        group_documents = [document for document in documents if document["group"] == group]
        for phase in sorted({document["phase"] for document in group_documents}):
            periods[f"{group} {phase}"] = _summarize_period(
                [document for document in group_documents if document["phase"] == phase]
            )

    return {
        "periods": periods,
        "keyword_crosstab": _keyword_crosstab(documents, keyword_topics),
    }


def analyze_corpus(sources, *, pandoc_runner=None):
    """讀取並解析已驗證來源；讀取失敗會中止，解析異常則留在各文件診斷。"""
    documents = []
    for source in sources:
        text, conversion_diagnostics = _read_source_text(
            source["path"], pandoc_runner=pandoc_runner
        )
        document = parse_document_text(
            text,
            date=source["date"],
            group=source["group"],
            phase=source["phase"],
        )
        document["diagnostics"] = [
            {"kind": kind, "text": detail, "line_number": None}
            for kind, detail in conversion_diagnostics
        ] + document["diagnostics"]
        document["source_path"] = str(source["path"])
        documents.append(document)
    return documents


def _load_keyword_topics(path):
    with Path(path).open(encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("關鍵主題設定 JSON 的最外層必須是物件")
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="離線分析 S2 P0 歷史交接語料；嚴格驗證 23 份人工與 10 份 AI canonical 來源。"
    )
    parser.add_argument(
        "--manual-dir",
        type=Path,
        default=DEFAULT_MANUAL_DIR,
        help="人工交接語料目錄（預設：指定 Archive 歷史範例目錄）",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=DEFAULT_ARCHIVE_DIR,
        help="包含 20260802 至 20260811 子目錄的 Archive 目錄",
    )
    parser.add_argument(
        "--keywords-json",
        type=Path,
        help="可選的關鍵主題 JSON 設定；格式為 {主題名稱: [關鍵詞, ...]}。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="輸出 machine-readable JSON 的路徑；未指定時輸出至標準輸出。",
    )
    args = parser.parse_args(argv)

    try:
        sources = discover_corpus(args.manual_dir, args.archive_dir)
        documents = analyze_corpus(sources)
        zero_category_dates = [document["date"] for document in documents if not document["categories"]]
        if zero_category_dates:
            raise CorpusAnalysisError(
                "下列文件未解析出任何大分類，拒絕輸出統計：" + ",".join(zero_category_dates)
            )
        unknown_lines = [
            (document["date"], entry["line_number"])
            for document in documents
            for entry in document["unrecognized_lines"]
        ]
        if unknown_lines:
            locations = ",".join(f"{date}:L{line_number}" for date, line_number in unknown_lines)
            raise CorpusAnalysisError("仍有未知未辨識行，拒絕輸出統計：" + locations)
        orphan_highlights = [
            (document["date"], diagnostic["line_number"])
            for document in documents
            for diagnostic in document["diagnostics"]
            if diagnostic["kind"] == "orphan highlight"
        ]
        if orphan_highlights:
            locations = ",".join(f"{date}:L{line_number}" for date, line_number in orphan_highlights)
            raise CorpusAnalysisError("仍有 orphan highlight，拒絕輸出統計：" + locations)
        keyword_topics = _load_keyword_topics(args.keywords_json) if args.keywords_json else None
        payload = {
            "source_correction": "規劃原列 0501–0620／23 份；實際語料為 0501–0626／23 份，已依實際檔案驗證。",
            "sources": [
                {
                    "path": str(source["path"]),
                    "date": source["date"],
                    "group": source["group"],
                    "phase": source["phase"],
                }
                for source in sources
            ],
            "documents": documents,
            "statistics": build_statistics(documents, keyword_topics=keyword_topics),
        }
    except (CorpusDiscoveryError, CorpusAnalysisError, SourceReadError, ValueError, OSError) as error:
        parser.error(str(error))

    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        diagnostics = sum(len(document["diagnostics"]) for document in documents)
        print(f"已輸出 {len(documents)} 份文件的 JSON：{args.output}；diagnostics {diagnostics} 筆", file=sys.stderr)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
