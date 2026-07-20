#!/usr/bin/env python3
"""Validate a TVBS-AIHunter SOT 完成文稿.txt before it is filed.

Checks (see common/06-auto-script-sot.md "交稿前必須用腳本精算"):
  - 主標題／次標題 full-width character counts (target 18-19)
  - SB block structure (SB / 職稱姓名 / 中文翻譯 / TC / 英文原文) and TC validity
  - Total estimated length (OS reading time + all SB seconds + any NS seconds)
    against a target (default 120s, or --target-seconds)
  - Optional: cross-check each #XX SB's TC end against the actual video
    duration via ffprobe, if --videos-dir is given

This does not rewrite the script; it only reports problems so a human/agent
can fix the source file. Exit code is non-zero if any check fails.

Usage:
    python scripts/validate_sot.py "追殺川普1730 完成文稿.txt"
    python scripts/validate_sot.py foo.txt --target-seconds 150
    python scripts/validate_sot.py foo.txt --videos-dir "G:/我的雲端硬碟/Claude共用/追殺川普1730"
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys

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

SECTION_MARKERS = ("【", "##", "＃＃")


def full_width_len(line: str) -> int:
    """Character count for headline sizing (每個字元算1個字，含標點)."""
    return len(line.strip())


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
    problems: list[str] = []
    notes: list[str] = []

    # --- headline / subheadline character counts ---
    headline_block = extract_section(text, "主標題")
    if headline_block:
        headline = headline_block.splitlines()[0].strip()
        n = full_width_len(headline)
        if not (HEADLINE_MIN <= n <= HEADLINE_MAX):
            problems.append(f"主標題「{headline}」共{n}字，不在{HEADLINE_MIN}~{HEADLINE_MAX}字範圍")
        else:
            notes.append(f"主標題「{headline}」共{n}字 OK")
    else:
        problems.append("找不到「主標題」區塊")

    subhead_block = extract_section(text, "次標題")
    if subhead_block:
        for line in subhead_block.splitlines():
            stripped = re.sub(r"^\s*\d+[.\、]\s*", "", line.strip())
            if not stripped:
                continue
            n = full_width_len(stripped)
            if not (HEADLINE_MIN <= n <= HEADLINE_MAX):
                problems.append(f"次標題「{stripped}」共{n}字，不在{HEADLINE_MIN}~{HEADLINE_MAX}字範圍")
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

    total_seconds = os_seconds + sb_seconds_total
    notes.append(f"OS約{os_chars}字 → 約{os_seconds:.1f}秒；SB共{sb_seconds_total:.1f}秒；總長度約{total_seconds:.1f}秒（目標{target_seconds:.0f}秒）")
    if total_seconds > target_seconds * 1.1:
        problems.append(f"總長度約{total_seconds:.1f}秒，超過目標{target_seconds:.0f}秒的10%以上")

    return problems, notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("script_path", help="{SLUG} 完成文稿.txt 的路徑")
    parser.add_argument("--target-seconds", type=float, default=120.0, help="目標總長度秒數，預設120")
    parser.add_argument("--videos-dir", default=None, help="下載素材所在資料夾，提供時會用ffprobe核對TC是否超出片長")
    args = parser.parse_args()

    with open(args.script_path, "r", encoding="utf-8") as f:
        text = f.read()

    problems, notes = validate(text, args.target_seconds, args.videos_dir)

    print("=== 檢查結果 ===")
    for n in notes:
        print(f"  - {n}")

    if problems:
        print("\n=== 發現問題 ===")
        for p in problems:
            print(f"  [FAIL] {p}")
        return 1

    print("\n全部檢查通過。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
