# -*- coding: utf-8 -*-
"""側錄初處理：靜音切段＋字卡 OCR＋剪檔。規格見
`common/plans/2026-08-28-側錄初處理工作台-design.md`。"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
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


RMS_AD = 0.25
REPORTER_RE = re.compile(r"\bCNN'?s\b|\breport(er|ing)\b|特派|記者", re.I)
INTERVIEW_RE = re.compile(r"\b(analyst|professor|minister|official)\b|訪問|專家", re.I)


def norm_topic(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def classify_kind(*, rms: float, ocr: str, duration: float, near_black: bool) -> str:
    text = (ocr or "").strip()
    if not text and duration >= 8 and (rms >= RMS_AD or near_black):
        return "ad"
    if INTERVIEW_RE.search(text):
        return "interview"
    if REPORTER_RE.search(text):
        return "reporter"
    if text:
        return "anchor"
    return "other"


def merge_topic_runs(segs: list[PrecutSeg]) -> list[PrecutSeg]:
    if not segs:
        return []
    out = [PrecutSeg(**{**asdict(segs[0])})]
    for s in segs[1:]:
        prev = out[-1]
        same = (
            prev.kind != "ad"
            and s.kind != "ad"
            and prev.kind == s.kind
            and norm_topic(prev.topic) != ""
            and norm_topic(prev.topic) == norm_topic(s.topic)
        )
        if same:
            prev.t1 = s.t1
            continue
        out.append(PrecutSeg(**{**asdict(s)}))
    for i, s in enumerate(out, 1):
        s.id = f"s{i}"
        s.selected = s.kind != "ad"
    return out


def cache_path(video_path: str) -> str:
    stem, _ = os.path.splitext(video_path)
    return stem + " PRECUT.json"


def save_cache(video_path: str, offset_sec: int, segs: list[PrecutSeg], mtime: float | None = None) -> str:
    path = cache_path(video_path)
    if mtime is None:
        mtime = os.path.getmtime(video_path)
    payload = {
        "source": os.path.basename(video_path),
        "offset_sec": offset_sec,
        "mtime": mtime,
        "segments": [seg_to_dict(s, offset_sec) for s in segs],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def load_cache(video_path: str) -> dict | None:
    path = cache_path(video_path)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cache_stale(video_path: str, cache: dict) -> bool:
    try:
        return float(cache.get("mtime") or 0) < os.path.getmtime(video_path) - 0.01
    except OSError:
        return True


def dicts_to_segs(rows: list[dict]) -> list[PrecutSeg]:
    out = []
    for i, r in enumerate(rows, 1):
        out.append(PrecutSeg(
            id=r.get("id") or f"s{i}",
            t0=float(r["t0"]), t1=float(r["t1"]),
            kind=r.get("kind") or "other",
            topic=r.get("topic") or "",
            ocr=r.get("ocr") or "",
            selected=bool(r["selected"]) if "selected" in r else (r.get("kind") != "ad"),
        ))
    return out


def waveform_points(rms_series: list[float], buckets: int = 800) -> list[float]:
    if not rms_series:
        return [0.0] * buckets
    n = len(rms_series)
    out = []
    for i in range(buckets):
        a = int(i * n / buckets)
        b = max(a + 1, int((i + 1) * n / buckets))
        out.append(max(rms_series[a:b]))
    return out


def analyze(video_path: str, *, offset_sec: int, duration: float,
            run_silence, rms_of, ocr_of, black_of, on_phase=None) -> dict:
    def phase(msg: str):
        if on_phase:
            on_phase(msg)
    phase("靜音偵測")
    sil = parse_silencedetect(run_silence(video_path))
    blocks = speech_blocks(duration, sil)
    segs: list[PrecutSeg] = []
    for i, (a, b) in enumerate(blocks, 1):
        phase(f"標段 {i}/{len(blocks)}")
        ocr = ocr_of((a + b) / 2) or ""
        kind = classify_kind(
            rms=float(rms_of(a, b)), ocr=ocr, duration=b - a,
            near_black=bool(black_of(a, b)),
        )
        segs.append(PrecutSeg(
            id=f"s{i}", t0=a, t1=b, kind=kind,
            topic=ocr.replace("\n", " ").strip(), ocr=ocr,
            selected=kind != "ad",
        ))
    segs = merge_topic_runs(segs)
    mtime = os.path.getmtime(video_path) if os.path.isfile(video_path) else 0
    save_cache(video_path, offset_sec, segs, mtime=mtime)
    return {
        "source": os.path.basename(video_path),
        "offset_sec": offset_sec,
        "mtime": mtime,
        "stale": False,
        "segments": [seg_to_dict(s, offset_sec) for s in segs],
    }


def cut_cmd(video_path: str, seg: PrecutSeg, dest: str, *, accurate: bool) -> list[str]:
    ss = f"{seg.t0:.3f}"
    to = f"{seg.t1:.3f}"
    if accurate:
        return [
            "ffmpeg", "-y", "-ss", ss, "-to", to, "-i", video_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", dest,
        ]
    return [
        "ffmpeg", "-y", "-i", video_path, "-ss", ss, "-to", to,
        "-c", "copy", "-avoid_negative_ts", "make_zero", dest,
    ]


_ocr_mod = "unset"
OCR_IMPORT_HINT = "pip install rapidocr-onnxruntime"
CROP_BOTTOM = 0.28  # CNN 720x480 下方約 28%


def require_ocr() -> None:
    global _ocr_mod
    if _ocr_mod is None:
        raise FileNotFoundError(
            f"沒有 RapidOCR，無法分析字卡。安裝：{OCR_IMPORT_HINT}"
        )
    if _ocr_mod == "unset":
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
            _ocr_mod = RapidOCR
        except ImportError:
            _ocr_mod = None
            raise FileNotFoundError(
                f"沒有 RapidOCR，無法分析字卡。安裝：{OCR_IMPORT_HINT}"
            )


def _run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )


def ffprobe_duration(path: str) -> float:
    r = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nk=1:nw=1", path,
    ])
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "ffprobe 失敗")
    return float(r.stdout.strip())


def run_silence_ffmpeg(path: str) -> str:
    # 閾值可實調；規格允許不寫進規則文件
    r = _run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", path,
        "-af", "silencedetect=noise=-30dB:d=0.6", "-f", "null", "-",
    ])
    return (r.stderr or "") + (r.stdout or "")


def rms_ffmpeg(path: str, t0: float, t1: float) -> float:
    dur = max(0.05, t1 - t0)
    r = _run([
        "ffmpeg", "-hide_banner", "-nostats",
        "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", path,
        "-af", "volumedetect", "-f", "null", "-",
    ])
    m = re.search(r"max_volume:\s*([-\d.]+)\s*dB", r.stderr or "")
    if not m:
        return 0.0
    db = float(m.group(1))
    # 0 dB → 1.0；-20 dB → ~0.1。廣告啟發式用相對值。
    return max(0.0, min(1.0, 10 ** (db / 20)))


def black_ffmpeg(path: str, t0: float, t1: float) -> bool:
    dur = max(0.05, min(2.0, t1 - t0))
    r = _run([
        "ffmpeg", "-hide_banner", "-nostats",
        "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", path,
        "-vf", "blackdetect=d=0.2:pix_th=0.10", "-f", "null", "-",
    ])
    return "black_start" in (r.stderr or "")


def _maybe_opencc(text: str) -> str:
    try:
        import opencc  # type: ignore
        return opencc.OpenCC("s2twp").convert(text)
    except Exception:
        return text


def ocr_at(path: str, t_mid: float) -> str:
    require_ocr()
    tmp = tempfile.mkdtemp(prefix="precut_")
    try:
        png = os.path.join(tmp, "f.png")
        r = _run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{t_mid:.3f}", "-i", path, "-frames:v", "1",
            "-vf", f"crop=iw:ih*{CROP_BOTTOM}:0:ih*(1-{CROP_BOTTOM})",
            png,
        ])
        if r.returncode or not os.path.isfile(png):
            return ""
        engine = _ocr_mod()
        result, _ = engine(png)
        if not result:
            return ""
        lines = [row[1] for row in result if len(row) > 1 and row[1]]
        return _maybe_opencc(" ".join(lines).strip())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def analyze_file(path: str, offset_sec: int, on_phase=None) -> dict:
    require_ocr()
    duration = ffprobe_duration(path)
    return analyze(
        path, offset_sec=offset_sec, duration=duration,
        run_silence=run_silence_ffmpeg,
        rms_of=lambda a, b: rms_ffmpeg(path, a, b),
        ocr_of=lambda t: ocr_at(path, t),
        black_of=lambda a, b: black_ffmpeg(path, a, b),
        on_phase=on_phase,
    )


def segs_overlap(segs: list[PrecutSeg]) -> bool:
    ordered = sorted(segs, key=lambda s: s.t0)
    for a, b in zip(ordered, ordered[1:]):
        if b.t0 < a.t1 - 0.05:
            return True
    return False


def export_segs(video_path, segs, *, mode, accurate, source, offset_sec, run=subprocess.run) -> list[str]:
    chosen = []
    for s in segs:
        if mode == "non_ad" and s.kind == "ad":
            continue
        if mode == "selected" and not s.selected:
            continue
        chosen.append(s)
    dest_dir = export_dir(video_path)
    os.makedirs(dest_dir, exist_ok=True)
    paths = []
    for s in chosen:
        dest = os.path.join(dest_dir, export_filename(source, s, offset_sec))
        cmd = cut_cmd(video_path, s, dest, accurate=accurate)
        r = run(cmd, capture_output=True, text=True)
        if getattr(r, "returncode", 0):
            err = (getattr(r, "stderr", None) or "")[-400:]
            raise RuntimeError(f"ffmpeg 剪檔失敗：{err}")
        paths.append(dest)
    return paths
