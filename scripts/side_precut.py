# -*- coding: utf-8 -*-
"""側錄初處理：靜音切段＋字卡 OCR＋剪檔。規格見
`common/plans/2026-08-28-側錄初處理工作台-design.md`。"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass

import sb_format as SBF

KINDS = {
    "ad": "廣告",
    "anchor": "主播",
    "reporter": "記者",
    "interview": "訪問",
    "other": "其他",
}

ILLEGAL_FS = re.compile(r'[\\/:*?"<>|]+')


@dataclass
class PrecutSeg:
    id: str
    t0: float
    t1: float
    kind: str = "other"
    topic: str = ""
    ocr: str = ""
    selected: bool = True


def master_tc(t: float, offset_sec: int) -> str:
    return SBF.fmt_tc(t + offset_sec, 6)


def seg_to_dict(seg: PrecutSeg, offset_sec: int) -> dict:
    d = asdict(seg)
    d["tc0"] = master_tc(seg.t0, offset_sec)
    d["tc1"] = master_tc(seg.t1, offset_sec)
    d["duration"] = round(seg.t1 - seg.t0, 2)
    return d


def sanitize_filename_part(s: str) -> str:
    s = ILLEGAL_FS.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def export_filename(source: str, seg: PrecutSeg, offset_sec: int) -> str:
    src = sanitize_filename_part(source or "SIDE")
    kind_zh = KINDS.get(seg.kind, seg.kind)
    topic = sanitize_filename_part(seg.topic)
    tc = f"{master_tc(seg.t0, offset_sec)}-{master_tc(seg.t1, offset_sec)}"
    parts = [src, tc, kind_zh]
    if topic:
        parts.append(topic)
    return " ".join(parts) + ".mp4"


def export_dir(video_path: str) -> str:
    parent, name = os.path.split(video_path)
    stem, _ = os.path.splitext(name)
    return os.path.join(parent, stem + " 初處理")


BREATH_MAX = 1.5
SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


def parse_silencedetect(stderr: str) -> list[tuple[float, float]]:
    starts, ends = [], []
    for line in stderr.splitlines():
        m = SILENCE_START_RE.search(line)
        if m:
            starts.append(float(m.group(1)))
            continue
        m = SILENCE_END_RE.search(line)
        if m:
            ends.append(float(m.group(1)))
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else s
        out.append((s, e))
    return out


def speech_blocks(
    duration: float,
    silences: list[tuple[float, float]],
    breath_max: float = BREATH_MAX,
) -> list[tuple[float, float]]:
    if duration <= 0:
        return []
    long_sil = [(s, e) for s, e in silences if (e - s) >= breath_max]
    if not long_sil:
        return [(0.0, duration)]
    blocks = []
    t = 0.0
    for s, e in long_sil:
        if s > t:
            blocks.append((t, s))
        t = max(t, e)
    if t < duration:
        blocks.append((t, duration))
    return [(a, b) for a, b in blocks if b - a >= 0.2]
