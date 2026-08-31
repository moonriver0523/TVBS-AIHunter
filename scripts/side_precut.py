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
    selected: bool = False


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


LONG_BLOCK_MAX = 90.0
LONG_BLOCK_STEP = 30.0
LONG_BLOCK_MAX_SAMPLES = 8  # 每個超長段落最多補幾次OCR，避免極端長段落把成本炸開


def _long_block_samples(a: float, b: float, step: float, max_samples: int) -> list[float]:
    span = b - a
    n = max(2, min(max_samples, int(span // step) + 1))
    eff_step = span / n
    return [a + i * eff_step for i in range(n)]


def split_long_blocks(
    blocks: list[tuple[float, float]],
    ocr_of,
    max_span: float = LONG_BLOCK_MAX,
    step: float = LONG_BLOCK_STEP,
    max_samples: int = LONG_BLOCK_MAX_SAMPLES,
    on_phase=None,
) -> list[tuple[float, float]]:
    """靜音偵測對長時間沒有明顯停頓的段落沒用（廣告/轉場常靠音樂銜接、不留靜音），
    對超過 max_span 的段落改用字卡主題變化找斷點，避免不同內容黏在同一段。
    每次取樣都是一次 ffmpeg 截圖＋OCR，成本不小，只對確實過長的段落做，且每段最多取 max_samples 次。"""
    out: list[tuple[float, float]] = []
    long_spans = [(a, b) for a, b in blocks if b - a > max_span]
    total_samples = sum(
        len(_long_block_samples(a, b, step, max_samples)) for a, b in long_spans
    )
    done = 0
    for a, b in blocks:
        if b - a <= max_span:
            out.append((a, b))
            continue
        samples = _long_block_samples(a, b, step, max_samples)
        topics = []
        for s in samples:
            topics.append(norm_topic(topic_from_ocr(ocr_of(min(s, b - 0.1)) or "")))
            done += 1
            if on_phase:
                on_phase(f"長段落補切 {done}/{total_samples}")
        cuts = {a, b}
        for i in range(1, len(samples)):
            if topics[i] != topics[i - 1]:
                cuts.add(samples[i])
        prev = None
        for c in sorted(cuts):
            if prev is None:
                prev = c
                continue
            if c - prev >= 0.5:
                out.append((prev, c))
            prev = c
    return out


RMS_AD = 0.25
REPORTER_RE = re.compile(r"\bCNN'?s\b|\breport(er|ing)\b|特派|記者", re.I)
INTERVIEW_RE = re.compile(r"\b(analyst|professor|minister|official)\b|訪問|專家", re.I)


def norm_topic(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


_LATIN_RE = re.compile(r"[A-Za-z]")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
NLLB_PY = os.environ.get(
    "NLLB_PY",
    r"C:\Users\User\AppData\Local\Programs\Python\Python310\python.exe",
)
NLLB_SCRIPTS = r"C:\Users\User\AppData\Local\nllb200-ct2\scripts"


def looks_english(s: str) -> bool:
    """夠長的拉丁字才送翻譯；MD/CNN/已是中文的字卡略過。"""
    s = (s or "").strip()
    if not s:
        return False
    latin = len(_LATIN_RE.findall(s))
    cjk = len(_CJK_RE.findall(s))
    if cjk >= 2 and latin < 8:
        return False
    return latin >= 8


def _topic_mixed_fail(s: str) -> bool:
    """NLLB 殘譯：中英夾雜且英文字還很多。"""
    s = (s or "").strip()
    return len(_CJK_RE.findall(s)) >= 1 and len(_LATIN_RE.findall(s)) >= 8


_SPLIT_KEYS = sorted([
    ("INTERNATIONALCORRESPONDENT", "INTERNATIONAL CORRESPONDENT"),
    ("USCANADATRADEWAR", "US CANADA TRADE WAR"),
    ("CANADATRADEWAR", "CANADA TRADE WAR"),
    ("IMMIGRATIONCRACKDOWN", "IMMIGRATION CRACKDOWN"),
    ("DEVELOPINGSTORY", "DEVELOPING STORY"),
    ("AMERICASCHOICE", "AMERICA S CHOICE"),
    ("ENHANCEMENTCRAZE", "ENHANCEMENT CRAZE"),
    ("THEWHOLESTORY", "THE WHOLE STORY"),
    ("PREMIERESTONIGHT", "PREMIERES TONIGHT"),
    ("SECONDSOFCALM", "SECONDS OF CALM"),
    ("DARLINEGRAHAM", "DARLINE GRAHAM"),
    ("DOLLYPARTON", "DOLLY PARTON"),
    ("CALLTOEARTH", "CALL TO EARTH"),
    ("AFRICANVOICES", "AFRICAN VOICES"),
    ("WORLDSPORT", "WORLD SPORT"),
    ("WARWITHIRAN", "WAR WITH IRAN"),
    ("ISOBELYEUNG", "ISOBEL YEUNG"),
    ("CORRESPONDENT", "CORRESPONDENT"),
    ("TRADEWAR", "TRADE WAR"),
    ("COMINGUP", "COMING UP"),
    ("HIGHLIGHT", "HIGHLIGHT"),
    ("NEWSROOM", "NEWSROOM"),
    ("HEADLINES", "HEADLINES"),
    ("BREAKING", "BREAKING"),
    ("STACKED", "STACKED"),
    ("INSIDE", "INSIDE"),
    ("PREMIERES", "PREMIERES"),
    ("TONIGHT", "TONIGHT"),
    ("WHOLE", "WHOLE"),
    ("STORY", "STORY"),
    ("LIVE", "LIVE"),
    ("CNN", "CNN"),
], key=lambda x: len(x[0]), reverse=True)

_GLOSSARY = [
    (re.compile(r"INTERNATIONAL\s*CORRESPONDENT", re.I), "國際特派"),
    (re.compile(r"(?:U\.?\s*S\.?|US)\s*[-–]?\s*CANADA\s*TRADE\s*WAR|CANADA\s*TRADE\s*WAR", re.I), "美加貿易戰"),
    (re.compile(r"U\.?S\.?\s*IMMIGRATION\s*CRACKDOWN", re.I), "美國移民掃蕩"),
    (re.compile(r"(?:THE\s*)?(?:CNN\s*)?WHOLE\s*STORY", re.I), "《全記錄》"),
    (re.compile(r"PREMIERES?\s*TONIGHT(?:\s*AT\s*\d+\s*P\.?M\.?)?", re.I), "今晚首播"),
    (re.compile(r"STACKED|INSIDE\s*THE\s*ENHANCEMENT\s*CRAZE|ENHANCEMENT\s*CRAZE", re.I), "整形熱潮"),
    (re.compile(r"HIGHLIGHT(?:\s*\d+)?(?:\s*CNN)?(?:\s*SECONDS\s*OF\s*CALM)?", re.I), "精華"),
    (re.compile(r"SECONDS\s*OF\s*CALM", re.I), "片刻平靜"),
    (re.compile(r"DEVELOPING\s*STORYS?", re.I), "最新消息"),
    (re.compile(r"AMERICA\s*'?S?\s*CHOICE", re.I), "美國大選"),
    (re.compile(r"CALL\s*TO\s*EARTH", re.I), "地球呼叫"),
    (re.compile(r"AFRICAN\s*VOICES", re.I), "非洲之聲"),
    (re.compile(r"WORLD\s*SPORT", re.I), "全球體育"),
    (re.compile(r"CNN\s*NEWSROOM|\bNEWSROOM\b", re.I), "新聞室"),
    (re.compile(r"COMING\s*UP", re.I), "即將播出"),
    (re.compile(r"DOLLY\s*PARTON", re.I), "多莉·巴頓"),
    (re.compile(r"DARLINE\s*GRAHAM", re.I), "達琳·葛拉漢"),
    (re.compile(r"WAR\s*(?:WITH\s*)?IRAN", re.I), "伊朗戰事"),
    (re.compile(r"ISOBEL\s*YEUNG|ISOBELYEUNG", re.I), "伊莎貝·楊"),
    (re.compile(r"\bCORRESPONDENT\b", re.I), "特派"),
    (re.compile(r"\bHEADLINES?\b", re.I), "頭條"),
    (re.compile(r"\bBREAKING\b", re.I), "突發"),
    (re.compile(r"\bLIVE\b", re.I), "現場"),
    (re.compile(r"\bUS\s*OPEN\b", re.I), "美網"),
]

_JUNK = re.compile(
    r"Cable\s*News\s*Network|WARNER\s*BROS\.?\s*DISCOVERY|All\s*rights\s*reserved|"
    r"\b(?:KOSPI|FTSE|DAX|HSI|SMI|NIKKEI|NASDAQ)\s*[▼▼\-–]?\s*[\d.]*|"
    r"\d{1,2}:\d{2}\s*[AP]M\s*(?:GMT|CET|ET|PT)?|"
    r"\b(?:GMT|CET)\b|"
    r"(?:CNN\.)COM(?:/\w+)?|\bCOM\b|"
    r"\bC[MW]\.com\b|"
    r"1946\s*-?\s*2026|"
    r"SINCE\s*I?8T8|"
    r"B\.?\s*GRIMM|DANGOTE",
    re.I,
)
_DROP_TOK = {
    "MD", "ND", "CN", "CM", "CW", "CTT", "NND", "NIKKEI", "KOSPI", "FTSE", "DAX",
    "HSI", "SMI", "COM", "GMT", "CET", "ET", "PT", "AM", "PM", "AT", "THE", "OF",
    "FOR", "AND", "YET", "ANOTHER", "ROUND", "MARKING", "AS", "STIS", "BRACING",
    "DRENCHING", "STORMS", "ARI", "ONA", "GPBANGKOK", "WORLD", "SPORT", "WARI",
    "NE", "A", "AN", "TO", "ON", "IN", "OR", "BY", "WITH",
}


def split_glued_ocr(s: str) -> str:
    s = (s or "").replace('"', " ").replace("'", " ")
    s = re.sub(r"\d{1,2}:\d{2}\s*[AP]M\s*(CET|ET|PT)?", " ", s, flags=re.I)
    s = re.sub(r"[\d:.\-]+", " ", s)

    def split_run(run: str) -> str:
        u, i, out = run.upper(), 0, []
        while i < len(u):
            hit = next((w for w in _SPLIT_KEYS if u.startswith(w[0], i)), None)
            if hit:
                out.append(hit[1])
                i += len(hit[0])
            else:
                j = i + 1
                while j < len(u) and not any(u.startswith(w[0], j) for w in _SPLIT_KEYS):
                    j += 1
                out.append(u[i:j])
                i = j
        return " ".join(out)

    return re.sub(r"[A-Za-z]+", lambda m: split_run(m.group()), s)


def topic_parts(ocr: str) -> tuple[str, str]:
    """回傳 (繁中主題, 待翻英文字卡)。"""
    text = split_glued_ocr(ocr)
    text = _JUNK.sub(" ", text)
    for pat, zh in _GLOSSARY:
        text = pat.sub(zh, text)
    text = re.sub(
        r"\b(MD|ND|CN|CM|CW|CET|AM|PM|AT|THE|OF|FOR|YET|ANOTHER|ROUND|MARKING|AS|STIS|BRACING|DRENCHING|STORMS)\b",
        " ", text, flags=re.I,
    )
    zh_parts: list[str] = []
    lat_parts: list[str] = []
    for p in re.split(r"[\s／/]+", text):
        p = p.strip(" ·,;:\"'")
        if not p:
            continue
        if p.upper() in _DROP_TOK:
            continue
        if len(p) == 1 and p.isascii() and p.isalpha():
            continue
        if p.upper() == "CNN" and (zh_parts or lat_parts):
            continue
        if _CJK_RE.search(p):
            if p not in zh_parts:
                zh_parts.append(p)
        elif p.isascii() and len(p) >= 3:
            lat_parts.append(p)
    return "／".join(zh_parts), " ".join(lat_parts)


def topic_from_ocr(ocr: str) -> str:
    zh, lat = topic_parts(ocr)
    return "／".join(p for p in (zh, lat) if p)


def nllb_map(texts: list[str], run=subprocess.run) -> dict[str, str]:
    uniq: list[str] = []
    seen: set[str] = set()
    for t in texts:
        t = (t or "").strip()
        if not looks_english(t) or t in seen:
            continue
        seen.add(t)
        uniq.append(t)
    if not uniq or not os.path.isfile(NLLB_PY):
        return {}
    code = (
        "import json,sys;"
        f"sys.path.insert(0,{NLLB_SCRIPTS!r});"
        "from translate import translate;"
        "xs=json.loads(sys.stdin.read());"
        "print(json.dumps([translate(x,'eng_Latn','zho_Hant') for x in xs],"
        "ensure_ascii=False))"
    )
    # 實測約 4.4 秒/條（含首條的模型載入），段落切得越細、待翻字卡越多，
    # 固定 300 秒在段落數多時會不夠，改成依待翻字數量估算並留餘裕。
    timeout = max(300, 8 * len(uniq))
    r = run(
        [NLLB_PY, "-c", code],
        input=json.dumps(uniq, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    if r.returncode:
        return {}
    lines = (r.stdout or "").strip().splitlines()
    if not lines:
        return {}
    out = json.loads(lines[-1])
    return {u: _maybe_opencc(str(v).strip()) for u, v in zip(uniq, out) if str(v).strip()}


_STRONG_ZH = re.compile(
    r"全記錄|精華|特派|現場|整形|今晚首播|伊莎貝|新聞室|美加|伊朗|美國大選|"
    r"多莉|地球呼叫|非洲|全球體育|最新消息|即將播出|頭條|美網|達琳|移民"
)


def apply_topic_zh(segs: list[PrecutSeg], mapping: dict[str, str] | None = None, nllb: bool = True) -> list[PrecutSeg]:
    if mapping is not None:
        for s in segs:
            t = (s.topic or "").strip()
            if t in mapping:
                s.topic = mapping[t]
        return segs
    pending: list[tuple[PrecutSeg, str, str]] = []
    leftover_txt: list[str] = []
    for s in segs:
        cur = (s.topic or "").strip()
        src = (s.ocr or s.topic or "").strip()
        zh, lat = topic_parts(src)
        human = len(_CJK_RE.findall(cur)) >= 2 and not _topic_mixed_fail(cur)
        if human and not _STRONG_ZH.search(zh or ""):
            continue
        if lat and looks_english(lat):
            pending.append((s, lat, zh))
            leftover_txt.append(lat)
            s.topic = "／".join(p for p in (zh, lat) if p)
        elif zh:
            s.topic = zh
        elif looks_english(src) or looks_english(lat):
            pending.append((s, lat or src, zh))
            leftover_txt.append(lat or src)
            s.topic = "／".join(p for p in (zh, lat or src) if p)
        elif not human:
            s.topic = zh
    if leftover_txt and nllb:
        m = nllb_map(leftover_txt)
        for s, lat, zh in pending:
            extra = (m.get(lat) or "").strip()
            if extra and _topic_mixed_fail(extra):
                extra = lat
            s.topic = "／".join(p for p in (zh, extra or lat) if p)
    return segs


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
        s.selected = False
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
        data = json.load(f)
    segs = dicts_to_segs(data.get("segments") or [])
    apply_topic_zh(segs, nllb=False)
    off = int(data.get("offset_sec") or 0)
    data["segments"] = [seg_to_dict(s, off) for s in segs]
    return data


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
            selected=bool(r["selected"]) if "selected" in r else False,
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
            run_silence, rms_of, ocr_of, black_of, on_phase=None, zh_of=None) -> dict:
    def phase(msg: str):
        if on_phase:
            on_phase(msg)
    phase("靜音偵測")
    sil = parse_silencedetect(run_silence(video_path))
    blocks = speech_blocks(duration, sil)
    # split_long_blocks() 曾試過用字卡變化補切過長段落，實測顆粒太碎，先停用回到純靜音切段。
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
            selected=False,
        ))
    segs = merge_topic_runs(segs)
    if zh_of:
        zh_of(segs)
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
_ocr_engine = None
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


def _get_ocr_engine():
    """RapidOCR() 建構會重新載入 ONNX 模型，很吃 CPU；同一個 process 內只建一次重複用。"""
    global _ocr_engine
    require_ocr()
    if _ocr_engine is None:
        _ocr_engine = _ocr_mod()
    return _ocr_engine


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
        engine = _get_ocr_engine()
        result, _ = engine(png)
        if not result:
            return ""
        lines = [row[1] for row in result if len(row) > 1 and row[1]]
        return _maybe_opencc(" ".join(lines).strip())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def analyze_file(path: str, offset_sec: int, on_phase=None, translate: bool = True) -> dict:
    require_ocr()
    duration = ffprobe_duration(path)
    def zh_of(segs):
        if on_phase:
            on_phase("翻譯主題")
        apply_topic_zh(segs)
    return analyze(
        path, offset_sec=offset_sec, duration=duration,
        run_silence=run_silence_ffmpeg,
        rms_of=lambda a, b: rms_ffmpeg(path, a, b),
        ocr_of=lambda t: ocr_at(path, t),
        black_of=lambda a, b: black_ffmpeg(path, a, b),
        on_phase=on_phase,
        zh_of=zh_of if translate else None,
    )


def translate_cache(video_path: str, offset_sec: int, on_phase=None) -> dict:
    """對已存在的快取跑一次 NLLB 翻譯（手動觸發，不在分析時自動跑）。"""
    cached = load_cache(video_path)
    if not cached:
        raise FileNotFoundError("還沒有分析結果，無法翻譯")
    segs = dicts_to_segs(cached.get("segments") or [])
    if on_phase:
        on_phase("翻譯主題")
    apply_topic_zh(segs, nllb=True)
    mtime = os.path.getmtime(video_path) if os.path.isfile(video_path) else 0
    save_cache(video_path, offset_sec, segs, mtime=mtime)
    return {
        "source": os.path.basename(video_path),
        "offset_sec": offset_sec,
        "mtime": mtime,
        "stale": False,
        "segments": [seg_to_dict(s, offset_sec) for s in segs],
    }


def segs_overlap(segs: list[PrecutSeg]) -> bool:
    ordered = sorted(segs, key=lambda s: s.t0)
    for a, b in zip(ordered, ordered[1:]):
        if b.t0 < a.t1 - 0.05:
            return True
    return False


def export_filename_merged(source: str, segs: list[PrecutSeg], offset_sec: int, label: str = "合併") -> str:
    """勾選出的多段合併成一支——檔名帶「來源＋起始 TC」（不是每段的區間），
    後面接 label；自訂檔名也要保留這個字首，不能整段被蓋掉。"""
    src = sanitize_filename_part(source or "SIDE")
    first = min(segs, key=lambda s: s.t0)
    return f"{src} {master_tc(first.t0, offset_sec)} {label}.mp4"


def export_segs(video_path, segs, *, mode, accurate, source, offset_sec, filename=None,
                 run=subprocess.run) -> list[str]:
    chosen = []
    for s in segs:
        if mode == "non_ad" and s.kind == "ad":
            continue
        if mode == "selected" and not s.selected:
            continue
        chosen.append(s)
    dest_dir = export_dir(video_path)
    os.makedirs(dest_dir, exist_ok=True)

    def cut_one(s: PrecutSeg, dest: str, *, accurate: bool) -> None:
        cmd = cut_cmd(video_path, s, dest, accurate=accurate)
        r = run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if getattr(r, "returncode", 0):
            err = (getattr(r, "stderr", None) or "")[-400:]
            raise RuntimeError(f"ffmpeg 剪檔失敗：{err}")

    if mode == "selected":
        # 勾選常常是同一支帶不連續的多段——合併成一支，不要一段一檔。
        # 一律精準重編：不精準（stream copy）若段落沒跨到 keyframe，
        # 剪出來的片段可能整段沒有影像（只剩聲音），合併起來就是壞檔——
        # 不能交給「精準重編」勾選框，這裡自己蓋掉。
        if not chosen:
            return []
        ordered = sorted(chosen, key=lambda s: s.t0)
        custom = filename.strip() if filename and filename.strip() else None
        if custom and custom.lower().endswith(".mp4"):
            custom = custom[:-4]
        label = sanitize_filename_part(custom) if custom else ""
        name = export_filename_merged(source, ordered, offset_sec, label=label or "合併")
        dest = os.path.join(dest_dir, name)
        if len(ordered) == 1:
            cut_one(ordered[0], dest, accurate=True)
            return [dest]
        tmp_dir = tempfile.mkdtemp(prefix="precut_merge_", dir=dest_dir)
        try:
            clip_paths = []
            for i, s in enumerate(ordered, 1):
                clip = os.path.join(tmp_dir, f"clip{i:03d}.mp4")
                cut_one(s, clip, accurate=True)
                clip_paths.append(clip)
            list_path = os.path.join(tmp_dir, "concat.txt")
            with open(list_path, "w", encoding="utf-8") as f:
                for p in clip_paths:
                    f.write("file '%s'\n" % p.replace("'", "'\\''"))
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", dest]
            r = run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if getattr(r, "returncode", 0):
                err = (getattr(r, "stderr", None) or "")[-400:]
                raise RuntimeError(f"ffmpeg 合併失敗：{err}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return [dest]

    paths = []
    for s in chosen:
        dest = os.path.join(dest_dir, export_filename(source, s, offset_sec))
        cut_one(s, dest, accurate=accurate)
        paths.append(dest)
    return paths
