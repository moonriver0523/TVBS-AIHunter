#!/usr/bin/env python3
"""Validate a TVBS-AIHunter 完成文稿.txt before it is filed.

Two modes, one implementation, because the two 流程 share the SB five-line
format, the TC grammar and the full-width counting rules — keeping them in one
file stops the two copies from drifting apart.

--mode sot (default) — 自動寫稿(SOT), see common/06-auto-script-sot.md:
  - 主標題／次標題 full-width character counts (target 18-19)
  - SB block structure (SB / 職稱姓名 / 中文翻譯 / TC / 英文原文) and TC validity
  - Total estimated length (OS reading time + all SB seconds + any NS seconds)
    against a target (default 120s, or --target-seconds)
  - Optional: cross-check each #XX SB's TC end against the actual video
    duration via ffprobe, if --videos-dir is given

--mode ctv — 自動寫稿(CTV), see cnn/01-auto-script-writing.md:
  - 稿頭存在且為單一整段
  - SUPER: 每行 <= 18 全形字
  - BAR 1-4 字卡文字各 17-18 全形字（空格不計，18 為絕對上限），最多一個半形空格，
    半形標點只准 ! " + : .
  - 內文 BAR1-BAR4 定位標記齊全、順序正確、不重複字卡文字
  - SB 五行格式；TC 為純 MMSS-MMSS（不帶來源前綴）且 MM/SS 合法
  - OS 與 SB 中文口白每行 <= 14 全形字
  - SUPER 名單與內文 SB 標籤互相對應且逐字一致
  - 全篇以 OS 收尾（BAR4 之後不再接 SB）
  - 至少一段 SB；搭配 --source-script 時，比對官方稿的 BITE 有沒有被漏掉，
    並確認每句英文原句真的出自官方稿

The 區塊 are parsed from the actual markers (`##`, `SUPER:`, `BAR n`, `SB`);
never from fixed line numbers — a fixed-offset check silently skips whatever
moved (see common/auto-script-learning/cases/2026-07-21-罕見四胞1600.md).

This does not rewrite the script; it only reports problems so a human/agent
can fix the source file. Exit code is non-zero if any check fails.

Usage:
    python scripts/validate_sot.py "追殺川普1730 完成文稿.txt"
    python scripts/validate_sot.py foo.txt --target-seconds 150
    python scripts/validate_sot.py foo.txt --videos-dir "G:/我的雲端硬碟/Claude共用/追殺川普1730"
    python scripts/validate_sot.py "罕見四胞1600 完成文稿.txt" --mode ctv
    python scripts/validate_sot.py "罕見四胞1600 完成文稿.txt" --mode ctv \
        --source-script "罕見四胞1600 原始文稿.txt"
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import unicodedata

# Windows terminals (Git Bash / cmd) often default stdout to a non-UTF-8
# codepage, which mangles the Chinese text this script prints. Force UTF-8
# where possible instead of requiring PYTHONIOENCODING to be set manually.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

CHARS_PER_MINUTE = 250.0
HEADLINE_MIN = 18
HEADLINE_MAX = 19

SB_BLOCK_RE = re.compile(
    r"^SB\s*$\n(?P<speaker>.+)\n(?P<translation>.+)\n(?P<tc>.+)\n(?P<original>.+)$",
    re.MULTILINE,
)

# TC field: either "#XX MMSS-MMSS" (numbered material) or plain "MMSS-MMSS" /
# "HHMMSS-HHMMSS" (side-recorded / no-number material).
TC_RE = re.compile(r"^(?:#(?P<num>\d+)\s+)?(?P<start>\d{4,6})-(?P<end>\d{4,6})\s*$")

# NS line: "NS #01 0050-0053 球員登巴士歡呼" or "NS 0050-0053 現場歡聲".
# Trailing free-text description is allowed and ignored.
NS_RE = re.compile(r"^NS\b\s*(?P<tc>(?:#\d+\s+)?\d{4,6}-\d{4,6})\b")

SECTION_MARKERS = ("【", "##", "＃＃")

# --- CTV (cnn/01-auto-script-writing.md) ---
CTV_BAR_MIN = 17.0          # BAR 字卡下限
# 上限 18 是硬上限——使用者明令「絕對不可超過 18 字」，不得放寬。
# 沿革：固定18 → 17-18 → 15-17 → 17-18（現行，2026-07-21）
CTV_BAR_MAX = 18.0
CARD_MAX_SPACES = 1         # 字卡／標題最多一個半形空格（空格本身不計入字數）
# 字卡允許的半形標點白名單。此外的半形標點（, ? - / % ( ) 等）一律不得使用；
# 半形英文字母與數字不受此限（照樣算 0.5 個全形字）。
# `.` 於 2026-07-21 補入：數值簡寫 `5.7萬`／`950.3萬` 需要小數點。
CARD_ALLOWED_PUNCT = set('!"+:.')
CTV_SUPER_MAX = 18.0        # SUPER 每行上限 18 全形字
CTV_SPOKEN_MAX = 14.0       # OS／SB 中文口白每行上限 14 全形字
CTV_LEAD_MIN = 100          # 稿頭約 100-150 字（超出只提醒，不判 FAIL）
CTV_LEAD_MAX = 150

CTV_CARD_RE = re.compile(r"^BAR\s+([1-4])$")     # 字卡列表：`BAR 1`
CTV_MARK_RE = re.compile(r"^BAR([1-4])$")        # 內文定位標記：`BAR1`
CTV_TC_RE = re.compile(r"^(?P<start>\d{4})-(?P<end>\d{4})$")

# 官方稿的講者引言行，例如
#   `Alexa Bendall, Obstetrician, Royal Brisbane and Women’s Hospital: They have...`
#   `SOT: We are still waiting...`
CTV_SOURCE_QUOTE_RE = re.compile(r"^(?P<label>[A-Za-z][^:]{1,80}):\s+(?P<quote>\S.*)$")

# 引號式引言：整行就是一句被引號包住的話，沒有講者標籤。CNN 的 TALAT／PKG 稿
# 常用這種寫法（記者旁白全大寫、受訪者引言用引號），2026-07-21 `爆紅浣熊1600`
# 案發現只認 `Label: quote` 會漏抓整篇。
CTV_SOURCE_BARE_QUOTE_RE = re.compile(r'^["“](?P<quote>.+?)["”][.,]?$')

# CTV 單段 SB 的長度門檻（2026-07-21 訂定，見 cnn/01-auto-script-writing.md）
CTV_SB_MIN_SECONDS = 3       # 低於此秒數直接 FAIL：語意不可能完整
CTV_SB_SHORT_SECONDS = 4     # 3~4 秒之間給 WARN，要能說明為何這樣取捨

OPENING_QUOTES = "「『“\"'《〈"


def full_width_len(line: str) -> int:
    """Character count for headline sizing (每個字元算1個字，含標點)."""
    return len(line.strip())


def script_width(line: str) -> float:
    """字數換算：中文全形字算 1，英文/數字等半形字算 0.5，空白不計。

    這是本 repo 全部字數規格共用的唯一尺標：CTV 的 SUPER／BAR／口白
    （cnn/01-auto-script-writing.md），以及 SOT 的主標題／次標題
    （common/06-auto-script-sot.md，2026-07-21 起改用本尺標）。
    """
    total = 0.0
    for ch in line:
        if ch.isspace():
            continue
        total += 1.0 if unicodedata.east_asian_width(ch) in ("F", "W") else 0.5
    return total


def fmt_width(w: float) -> str:
    return f"{w:g}"


def check_card_chars(label: str, text: str) -> list[str]:
    """字卡／標題共用的半形字元規則：空格最多一個且須為半形，半形標點只准白名單。

    CTV 的 BAR 與 SOT 的主標題／次標題套用同一組規則（2026-07-21 訂定）。
    半形英文字母與數字不受限。
    """
    found: list[str] = []

    spaces = [ch for ch in text if ch.isspace()]
    if len(spaces) > CARD_MAX_SPACES:
        found.append(
            f"{label}「{text}」有{len(spaces)}個空格，最多只能有{CARD_MAX_SPACES}個半形空格"
        )
    for ch in spaces:
        if ch != " ":
            found.append(
                f"{label}「{text}」用了非半形空格（U+{ord(ch):04X}），空格必須是半形空格"
            )
            break

    bad_punct = sorted({
        ch for ch in text
        if not ch.isspace()
        and unicodedata.east_asian_width(ch) not in ("F", "W")
        and not ch.isalnum()
        and ch not in CARD_ALLOWED_PUNCT
    })
    if bad_punct:
        found.append(
            f"{label}「{text}」用了不允許的半形標點 {' '.join(bad_punct)}；"
            f"半形標點只准用 {' '.join(sorted(CARD_ALLOWED_PUNCT))}"
        )
    return found


def parse_tc_field(tc: str):
    """Return (start_seconds, end_seconds, material_num_or_None) or None if unparseable."""
    m = TC_RE.match(tc.strip())
    if not m:
        return None
    start_s, end_s = m.group("start"), m.group("end")

    def to_seconds(digits: str) -> int:
        if len(digits) == 4:  # MMSS
            mm, ss = int(digits[:2]), int(digits[2:])
            return mm * 60 + ss
        if len(digits) == 6:  # HHMMSS
            hh, mm, ss = int(digits[:2]), int(digits[2:4]), int(digits[4:])
            return hh * 3600 + mm * 60 + ss
        raise ValueError(f"unexpected TC digit length: {digits}")

    return to_seconds(start_s), to_seconds(end_s), m.group("num")


def extract_section(text: str, marker: str) -> str | None:
    """Grab the block of text following a line containing `marker`, up to the
    next section marker or blank-line-then-marker boundary."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if marker in line:
            start = i + 1
            break
    if start is None:
        return None
    collected = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped and any(stripped.startswith(m) for m in SECTION_MARKERS) and marker not in stripped:
            break
        collected.append(line)
    return "\n".join(collected).strip()


def find_ffprobe() -> str | None:
    return shutil.which("ffprobe")


def video_duration_seconds(path: str) -> float | None:
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


def find_video_for_material(videos_dir: str, num: str) -> str | None:
    padded = num.zfill(2)
    candidates = glob.glob(os.path.join(videos_dir, f"*#{padded}*.*"))
    candidates = [c for c in candidates if not c.lower().endswith(".txt")]
    return candidates[0] if candidates else None


def validate(text: str, target_seconds: float, videos_dir: str | None):
    """SOT 模式檢查。回傳 (problems, notes, warnings)。"""
    problems: list[str] = []
    notes: list[str] = []
    warnings: list[str] = []

    # --- headline / subheadline character counts ---
    headline_block = extract_section(text, "主標題")
    if headline_block:
        headline = headline_block.splitlines()[0].strip()
        n = script_width(headline)
        if not (HEADLINE_MIN <= n <= HEADLINE_MAX):
            problems.append(
                f"主標題「{headline}」換算{fmt_width(n)}個全形字，"
                f"不在{HEADLINE_MIN}~{HEADLINE_MAX}字範圍"
            )
        else:
            notes.append(f"主標題「{headline}」換算{fmt_width(n)}個全形字 OK")
        problems.extend(check_card_chars("主標題", headline))
    else:
        problems.append("找不到「主標題」區塊")

    subhead_block = extract_section(text, "次標題")
    if subhead_block:
        for line in subhead_block.splitlines():
            stripped = re.sub(r"^\s*\d+[.\、]\s*", "", line.strip())
            if not stripped:
                continue
            n = script_width(stripped)
            if not (HEADLINE_MIN <= n <= HEADLINE_MAX):
                problems.append(
                    f"次標題「{stripped}」換算{fmt_width(n)}個全形字，"
                    f"不在{HEADLINE_MIN}~{HEADLINE_MAX}字範圍"
                )
            else:
                notes.append(f"次標題「{stripped}」換算{fmt_width(n)}個全形字 OK")
            problems.extend(check_card_chars("次標題", stripped))
    else:
        problems.append("找不到「次標題」區塊")

    # --- SB blocks ---
    sb_seconds_total = 0.0
    sb_count = 0
    for m in SB_BLOCK_RE.finditer(text):
        sb_count += 1
        tc_field = m.group("tc")
        parsed = parse_tc_field(tc_field)
        if parsed is None:
            problems.append(f"第{sb_count}段 SB 的 TC 欄位「{tc_field.strip()}」格式無法辨識")
            continue
        start_sec, end_sec, num = parsed
        if end_sec <= start_sec:
            problems.append(f"第{sb_count}段 SB TC「{tc_field.strip()}」結束時間不晚於開始時間")
            continue
        dur = end_sec - start_sec
        sb_seconds_total += dur
        notes.append(f"第{sb_count}段 SB：{tc_field.strip()} = {dur:.0f}秒")

        if videos_dir and num:
            video_path = find_video_for_material(videos_dir, num)
            if video_path:
                vdur = video_duration_seconds(video_path)
                if vdur is not None and end_sec > vdur:
                    problems.append(
                        f"第{sb_count}段 SB #{num} 的TC結束秒數({end_sec})超過影片實際長度({vdur:.1f}秒) — {video_path}"
                    )

    # --- NS (natural sound) seconds ---
    # 06-auto-script-sot.md: 總長度＝OS＋全部SB＋全部NS。NS 寫成單行，例如
    #   NS #01 0050-0053 球員登巴士歡呼
    #   NS 0050-0053 現場歡聲
    # 帶不帶 #編號都接受；沒有 TC 的裸 "NS" 行無法計時，另外提醒。
    ns_seconds_total = 0.0
    ns_count = 0
    ns_untimed = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not re.match(r"^NS\b", stripped):
            continue
        ns_m = NS_RE.match(stripped)
        parsed = parse_tc_field(ns_m.group("tc")) if ns_m else None
        if parsed is None:
            ns_untimed += 1
            continue
        start_sec, end_sec, _num = parsed
        dur = end_sec - start_sec
        if dur <= 0:
            problems.append(f"NS「{stripped}」結束時間不晚於開始時間")
            continue
        ns_count += 1
        ns_seconds_total += dur
        notes.append(f"NS：{stripped} = {dur:.0f}秒")
    if ns_untimed:
        problems.append(
            f"有 {ns_untimed} 段 NS 沒有可解析的 TC，無法計入總長度"
            "（NS 也要納入計時，格式如 `NS #01 0050-0053 說明`）"
        )

    # --- OS reading time ---
    os_block = extract_section(text, "記者OS內文") or extract_section(text, "記者OS")
    os_chars = 0
    if os_block:
        for line in os_block.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped == "SB" or SB_BLOCK_RE.search(stripped):
                continue
            if TC_RE.match(stripped):
                continue
            if re.match(r"^NS\b", stripped):
                continue
            if re.match(r"^#\d+\s+TC", stripped) or stripped.startswith("圖#"):
                continue
            # skip lines that look like they belong to an SB block (speaker/
            # translation/english) — heuristic: lines immediately following
            # "SB" are already excluded via the SB regex sweep below.
            os_chars += full_width_len(stripped)
    # Subtract characters already counted as part of SB blocks (speaker name /
    # translation / english line), since extract_section can't perfectly
    # distinguish them from OS paragraphs.
    for m in SB_BLOCK_RE.finditer(os_block or ""):
        os_chars -= full_width_len(m.group("speaker"))
        os_chars -= full_width_len(m.group("translation"))
        os_chars -= full_width_len(m.group("original"))
        os_chars -= 2  # the literal "SB" line

    os_seconds = max(os_chars, 0) / CHARS_PER_MINUTE * 60.0

    total_seconds = os_seconds + sb_seconds_total + ns_seconds_total
    notes.append(
        f"OS約{os_chars}字 → 約{os_seconds:.1f}秒；SB共{sb_seconds_total:.1f}秒；"
        f"NS共{ns_seconds_total:.1f}秒（{ns_count}段）；"
        f"總長度約{total_seconds:.1f}秒（目標{target_seconds:.0f}秒）"
    )
    if total_seconds > target_seconds * 1.1:
        problems.append(f"總長度約{total_seconds:.1f}秒，超過目標{target_seconds:.0f}秒的10%以上")

    return problems, notes, warnings


# ---------------------------------------------------------------------------
# CTV 模式（cnn/01-auto-script-writing.md）
# ---------------------------------------------------------------------------


class CtvScript:
    """依實際標記解析出來的 CTV 完成文稿結構（不使用固定行號）。"""

    def __init__(self) -> None:
        self.lead: list[str] = []               # `##` 之前的稿頭
        self.has_separator = False
        self.super_lines: list[str] = []        # `SUPER:` 之後的名單
        self.cards: dict[int, str] = {}         # {1: "字卡文字", ...}
        self.card_order: list[int] = []
        self.marks: list[int] = []              # 內文出現的 BAR1-4 順序
        self.body_lines: list[str] = []         # 內文區（含 SB 區塊）原文行
        self.body_start: int | None = None


def parse_ctv(text: str) -> CtvScript:
    lines = text.splitlines()
    doc = CtvScript()

    # 1. `##` 分隔線之前是稿頭。
    sep_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "##":
            sep_idx = i
            break
    if sep_idx is None:
        doc.lead = [ln for ln in lines if ln.strip()]
        return doc
    doc.has_separator = True
    doc.lead = [ln.strip() for ln in lines[:sep_idx] if ln.strip()]

    # 2. `SUPER:` 之後、遇到空行或 `BAR n` 為止是 SUPER 名單。
    idx = sep_idx + 1
    super_idx = None
    for i in range(idx, len(lines)):
        if lines[i].strip().startswith("SUPER:"):
            super_idx = i
            break
    if super_idx is not None:
        for line in lines[super_idx + 1:]:
            stripped = line.strip()
            if not stripped or CTV_CARD_RE.match(stripped) or CTV_MARK_RE.match(stripped):
                break
            doc.super_lines.append(stripped)

    # 3. 字卡列表：`BAR n` 的下一個非空行就是該張字卡文字。
    scan_from = (super_idx if super_idx is not None else sep_idx) + 1
    i = scan_from
    while i < len(lines):
        stripped = lines[i].strip()
        m = CTV_CARD_RE.match(stripped)
        if m:
            num = int(m.group(1))
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            card_text = lines[j].strip() if j < len(lines) else ""
            if not CTV_CARD_RE.match(card_text) and not CTV_MARK_RE.match(card_text):
                doc.cards[num] = card_text
                doc.card_order.append(num)
                i = j + 1
                continue
            doc.cards[num] = ""
            doc.card_order.append(num)
        elif CTV_MARK_RE.match(stripped) and doc.card_order:
            doc.body_start = i
            break
        i += 1

    if doc.body_start is None:
        for k in range(scan_from, len(lines)):
            if CTV_MARK_RE.match(lines[k].strip()):
                doc.body_start = k
                break

    if doc.body_start is not None:
        doc.body_lines = lines[doc.body_start:]
        for line in doc.body_lines:
            m = CTV_MARK_RE.match(line.strip())
            if m:
                doc.marks.append(int(m.group(1)))

    return doc


def split_ctv_body(body_lines: list[str]):
    """把內文切成 (kind, payload) 序列。

    - ('mark', n)
    - ('sb', {speaker, zh_lines, tc, english})
      SB 中文口白可多行（每行仍受 14 全形字上限），結構為：
        SB
        {職稱姓名}
        {中文行1}
        {中文行2...}   ← 可 1 行以上，直到 TC 行
        {MMSS-MMSS}
        {英文原句}
    - ('os', line)
    """
    items = []
    i = 0
    while i < len(body_lines):
        stripped = body_lines[i].strip()
        if not stripped:
            i += 1
            continue
        m = CTV_MARK_RE.match(stripped)
        if m:
            items.append(("mark", int(m.group(1))))
            i += 1
            continue
        if stripped == "SB":
            i += 1
            while i < len(body_lines) and not body_lines[i].strip():
                i += 1
            speaker = body_lines[i].strip() if i < len(body_lines) else ""
            if speaker:
                i += 1
            zh_lines: list[str] = []
            while i < len(body_lines):
                s = body_lines[i].strip()
                if not s:
                    i += 1
                    continue
                if CTV_TC_RE.match(s) or s == "SB" or CTV_MARK_RE.match(s):
                    break
                zh_lines.append(s)
                i += 1
            tc = ""
            if i < len(body_lines) and CTV_TC_RE.match(body_lines[i].strip()):
                tc = body_lines[i].strip()
                i += 1
            while i < len(body_lines) and not body_lines[i].strip():
                i += 1
            english = ""
            if i < len(body_lines):
                s = body_lines[i].strip()
                # 英文原句；若下一段已是標記/下一 SB 則視為缺英文
                if s and s != "SB" and not CTV_MARK_RE.match(s) and not CTV_TC_RE.match(s):
                    english = s
                    i += 1
            items.append(("sb", {
                "speaker": speaker,
                "zh_lines": zh_lines,
                "tc": tc,
                "english": english,
            }))
            continue
        items.append(("os", stripped))
        i += 1
    return items


def parse_ctv_tc(tc: str):
    """回傳 (start_seconds, end_seconds) 或 None；MM/SS 必須合法（SS <= 59）。"""
    m = CTV_TC_RE.match(tc.strip())
    if not m:
        return None
    out = []
    for digits in (m.group("start"), m.group("end")):
        mm, ss = int(digits[:2]), int(digits[2:])
        if ss > 59:
            return None
        out.append(mm * 60 + ss)
    return out[0], out[1]


def normalize_quote(s: str) -> str:
    """比對官方稿用：去空白、統一引號與破折號、轉小寫。"""
    s = s.strip().lower()
    for ch in "“”‘’＂'\"「」":
        s = s.replace(ch, "")
    s = s.replace("’", "'").replace("—", "-").replace("–", "-")
    s = re.sub(r"\s+", "", s)
    return s


def collect_source_quotes(source_text: str) -> list[str]:
    """從 CNN 官方稿抽出講者引言行（SUPERS／LEAD IN／全大寫 OS 不算）。"""
    quotes = []
    for line in source_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--") or stripped.startswith("***"):
            continue
        # 形式二：整行是一句被引號包住的話（沒有講者標籤）。
        bare = CTV_SOURCE_BARE_QUOTE_RE.match(stripped)
        if bare:
            quote = bare.group("quote").strip()
            if quote and not quote.isupper():
                quotes.append(quote)
            continue

        # 形式一：`講者姓名／職稱: 引言`
        m = CTV_SOURCE_QUOTE_RE.match(stripped)
        if not m:
            continue
        label = m.group("label")
        quote = m.group("quote")
        # metadata 行（Title:／Source:／TRT: …）與全大寫記者旁白不是 BITE。
        if label.strip() in {
            "Story Number", "Title", "Description", "Source", "Embargo",
            "Embargo / Restrictions", "Footage Type", "TRT", "Reporter",
            "Official Script", "Script",
        }:
            continue
        if quote.isupper():
            continue
        quotes.append(quote)
    return quotes


def validate_ctv(text: str, source_text: str | None):
    """CTV 模式檢查。回傳 (problems, notes, warnings)。"""
    problems: list[str] = []
    notes: list[str] = []
    warnings: list[str] = []

    doc = parse_ctv(text)

    # --- 稿頭 ---
    if not doc.has_separator:
        problems.append("找不到 `##` 分隔線，無法區分稿頭與 SUPER／BAR 區塊")
    if not doc.lead:
        problems.append("找不到主播稿頭（`##` 之前沒有內容）")
    else:
        if len(doc.lead) > 1:
            problems.append(
                f"稿頭被斷成 {len(doc.lead)} 行；稿頭要以單一整段文字呈現，不分句、不套 14 字斷行上限"
            )
        lead_text = "".join(doc.lead)
        lead_n = len(re.sub(r"\s+", "", lead_text))
        notes.append(f"稿頭共{lead_n}字")
        if not (CTV_LEAD_MIN <= lead_n <= CTV_LEAD_MAX):
            warnings.append(f"稿頭共{lead_n}字，不在建議的{CTV_LEAD_MIN}~{CTV_LEAD_MAX}字之間")

    # --- SUPER ---
    if not doc.super_lines:
        problems.append("找不到 `SUPER:` 區塊或區塊內沒有任何人物")
    for line in doc.super_lines:
        w = script_width(line)
        if w > CTV_SUPER_MAX:
            problems.append(
                f"SUPER「{line}」換算{fmt_width(w)}個全形字，超過上限{fmt_width(CTV_SUPER_MAX)}"
            )
        else:
            notes.append(f"SUPER「{line}」換算{fmt_width(w)}個全形字 OK")

    # --- BAR 字卡：17-18 全形字（18 為硬上限），且半形字元受限 ---
    if doc.card_order != [1, 2, 3, 4]:
        problems.append(
            f"BAR 字卡列表應為 `BAR 1`~`BAR 4` 四張且順序正確，實際解析到：{doc.card_order or '無'}"
        )
    for num in doc.card_order:
        card = doc.cards.get(num, "")
        if not card:
            problems.append(f"BAR {num} 沒有字卡文字")
            continue

        w = script_width(card)
        if not (CTV_BAR_MIN <= w <= CTV_BAR_MAX):
            problems.append(
                f"BAR {num}「{card}」換算{fmt_width(w)}個全形字，"
                f"不在{fmt_width(CTV_BAR_MIN)}~{fmt_width(CTV_BAR_MAX)}全形字範圍"
            )
        else:
            notes.append(f"BAR {num}「{card}」換算{fmt_width(w)}個全形字 OK")

        # 空格與半形標點：與 SOT 主標題／次標題共用同一組規則。
        problems.extend(check_card_chars(f"BAR {num}", card))

    # --- 內文定位標記 ---
    if doc.marks != [1, 2, 3, 4]:
        problems.append(
            f"內文定位標記應依序為 BAR1→BAR2→BAR3→BAR4 各一次，實際為：{doc.marks or '無'}"
        )
    body_flat = re.sub(r"\s+", "", "".join(doc.body_lines))
    for num, card in doc.cards.items():
        if card and re.sub(r"\s+", "", card) in body_flat:
            problems.append(f"內文重複了 BAR {num} 的字卡文字「{card}」；內文只放 BAR{num} 定位標記")

    # --- 內文逐項：OS / SB ---
    items = split_ctv_body(doc.body_lines)
    sb_count = 0
    sb_speakers: list[str] = []
    sb_english: list[str] = []
    last_mark = 0
    for kind, payload in items:
        if kind == "mark":
            last_mark = payload
            continue
        if kind == "os":
            w = script_width(payload)
            if w > CTV_SPOKEN_MAX:
                problems.append(
                    f"OS 口白「{payload}」換算{fmt_width(w)}個全形字，超過上限{fmt_width(CTV_SPOKEN_MAX)}"
                )
            continue

        # kind == "sb" — payload 為 dict: speaker / zh_lines / tc / english
        sb_count += 1
        speaker = payload.get("speaker", "")
        zh_lines = payload.get("zh_lines") or []
        tc_field = payload.get("tc", "")
        english = payload.get("english", "")
        sb_speakers.append(speaker)
        sb_english.append(english)

        if last_mark == 4:
            problems.append(f"第{sb_count}段 SB 出現在 BAR4 之後；BAR4 之後不再接 SB，全篇須以 OS 收尾")

        if not speaker or CTV_TC_RE.match(speaker):
            problems.append(f"第{sb_count}段 SB 第2行缺少「中文職稱 英文姓名」")
        if not zh_lines:
            problems.append(f"第{sb_count}段 SB 缺少中文引言口白")
        for zh in zh_lines:
            if zh and zh[0] in OPENING_QUOTES:
                problems.append(f"第{sb_count}段 SB 引言「{zh}」以引號起始；SB 引言起始不加任何引號")
            tw = script_width(zh)
            if tw > CTV_SPOKEN_MAX:
                problems.append(
                    f"第{sb_count}段 SB 引言「{zh}」換算{fmt_width(tw)}個全形字，"
                    f"超過上限{fmt_width(CTV_SPOKEN_MAX)}"
                )

        parsed = parse_ctv_tc(tc_field)
        if parsed is None:
            problems.append(
                f"第{sb_count}段 SB 的 TC 欄位「{tc_field or '(空)'}」不是合法的純 4 碼 `MMSS-MMSS`"
                "（CTV 不加來源前綴，且 SS 不得大於 59）"
            )
        else:
            start_sec, end_sec = parsed
            if end_sec <= start_sec:
                problems.append(f"第{sb_count}段 SB TC「{tc_field}」結束時間不晚於開始時間")
            else:
                dur = end_sec - start_sec
                notes.append(f"第{sb_count}段 SB：{speaker}｜{tc_field} = {dur}秒")
                # 過短的 BITE 語意必然不完整（2026-07-21 爆紅浣熊1600 案）。
                if dur < CTV_SB_MIN_SECONDS:
                    problems.append(
                        f"第{sb_count}段 SB 只有 {dur} 秒，短於 {CTV_SB_MIN_SECONDS} 秒下限"
                        "——語意不可能完整，不要為了湊 SB 段數塞碎句；"
                        "這類短句改寫進 OS 敘事即可"
                    )
                elif dur < CTV_SB_SHORT_SECONDS:
                    warnings.append(
                        f"第{sb_count}段 SB 只有 {dur} 秒（偏短），確認它是完整句、"
                        "且比改寫成 OS 更有價值"
                    )

        if not english:
            problems.append(f"第{sb_count}段 SB 缺少英文原句")
        elif english[0] in OPENING_QUOTES:
            problems.append(f"第{sb_count}段 SB 英文原句以引號起始；英文原句不加任何引號")

    legacy_sb = [
        ln.strip() for ln in doc.body_lines
        if re.match(r"^SB\s+(?:#\d+\s+)?\d{4,6}-\d{4,6}\s*$", ln.strip())
    ]
    if legacy_sb:
        problems.append(
            f"偵測到 {len(legacy_sb)} 處舊版三段式 `SB <TC>` 寫法（例如「{legacy_sb[0]}」）；"
            "2026-07-21 起 CTV 一律改用 common/00-寫稿通則.md 的五行 SB 格式"
        )

    if sb_count == 0:
        problems.append("完成文稿沒有任何 SB；CTV 完成版必須保留官方稿可用的 BITE，0 段 SB 不得當成完成版交付")

    # --- SUPER 名單與內文 SB 標籤必須互相對應 ---
    super_set = {re.sub(r"\s+", " ", s) for s in doc.super_lines}
    speaker_set = {re.sub(r"\s+", " ", s) for s in sb_speakers}
    for s in sorted(speaker_set - super_set):
        problems.append(f"內文 SB 標籤「{s}」沒有逐字出現在 SUPER 區塊（兩處寫法必須完全一致）")
    for s in sorted(super_set - speaker_set):
        problems.append(f"SUPER「{s}」在內文沒有對應的 SB；SUPER 只列實際有引用 SB 的人物")

    # --- 全篇須以 OS 收尾 ---
    if items and items[-1][0] != "os":
        problems.append("全篇最後一項不是 OS；BAR4 之後須以記者 OS 收尾")

    # --- 與官方稿比對 ---
    if source_text is not None:
        source_quotes = collect_source_quotes(source_text)
        notes.append(f"官方稿解析到{len(source_quotes)}句可用引言；完成文稿用了{sb_count}段 SB")
        if source_quotes and sb_count == 0:
            problems.append(
                f"官方稿有{len(source_quotes)}句可用引言，完成文稿卻 0 段 SB —— 漏掉官方稿已有的 BITE"
            )
        flat_source = normalize_quote(source_text)
        for i, english in enumerate(sb_english, start=1):
            if english and normalize_quote(english) not in flat_source:
                problems.append(
                    f"第{i}段 SB 的英文原句在官方稿裡找不到：「{english}」"
                    "（英文用字一律以官方稿為準，不可照抄 ASR）"
                )
        used = {normalize_quote(e) for e in sb_english}
        unused = [q for q in source_quotes if normalize_quote(q) not in used]
        if unused:
            warnings.append(
                f"官方稿還有{len(unused)}句引言未使用，確認是刻意取捨而非漏盤："
                + "；".join(q[:30] + ("…" if len(q) > 30 else "") for q in unused)
            )

    return problems, notes, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("script_path", help="{SLUG} 完成文稿.txt 的路徑")
    parser.add_argument("--mode", choices=("sot", "ctv"), default="sot",
                        help="sot=自動寫稿(SOT)（預設）；ctv=自動寫稿(CTV)")
    parser.add_argument("--target-seconds", type=float, default=120.0, help="目標總長度秒數，預設120（僅 sot 模式）")
    parser.add_argument("--videos-dir", default=None, help="下載素材所在資料夾，提供時會用ffprobe核對TC是否超出片長（僅 sot 模式）")
    parser.add_argument("--source-script", default=None,
                        help="`{SLUG} 原始文稿.txt` 的路徑（僅 ctv 模式）：比對官方稿 BITE 有無漏掉、英文原句是否照官方稿")
    args = parser.parse_args()

    if args.mode == "sot" and args.source_script:
        parser.error("--source-script 只適用於 --mode ctv")
    if args.mode == "ctv" and args.videos_dir:
        parser.error("--videos-dir 只適用於 --mode sot")

    with open(args.script_path, "r", encoding="utf-8-sig") as f:
        text = f.read()

    if args.mode == "ctv":
        source_text = None
        if args.source_script:
            with open(args.source_script, "r", encoding="utf-8-sig") as f:
                source_text = f.read()
        problems, notes, warnings = validate_ctv(text, source_text)
    else:
        problems, notes, warnings = validate(text, args.target_seconds, args.videos_dir)

    print("=== 檢查結果 ===")
    for n in notes:
        print(f"  - {n}")

    if warnings:
        print("\n=== 提醒（不影響通過與否） ===")
        for w in warnings:
            print(f"  [WARN] {w}")

    if problems:
        print("\n=== 發現問題 ===")
        for p in problems:
            print(f"  [FAIL] {p}")
        return 1

    print("\n全部檢查通過。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
