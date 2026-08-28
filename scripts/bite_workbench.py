# -*- coding: utf-8 -*-
"""掐BITE 工作台——本機後端。

立案與實測依據：`common/plans/2026-08-24-S5至S8產線UI前台可行性評估.md`
（§4 設計、§十 Phase 0 實測、§七 護欄）；需求修正見
`common/plans/2026-08-25-掐BITE工作台-交接.md` §一——**列出整支素材的
所有段落**（過濾降級為標籤），**中文翻譯自動產生**（Claude API／CLI）。

    素材資料夾 → TC 來源優先序 → 全段落列舉 → 瀏覽器點列跳 TC 人工核對
    → 選段落 → 中文翻譯草稿 → 五行 SB

**這支不做編輯判斷。** 選哪一句、講者職稱怎麼寫、是不是 STAND，
全部是人的工作；翻譯由 LLM 產草稿、仍需人核。這裡做機械的部分：
配對檔案、跑 ASR、列全部段落、算 TC、排版。

護欄（計畫書 §七）：
  1. SB 排版與 TC 欄位一律呼叫 `sb_format.py`，**不在這裡也不在 JS 裡重寫一份**。
  2. 官方文稿優先於 ASR：候選同時保存 `text`（輸出用，官方稿）與
     `asr_text`（定位用），**輸出永遠取前者**。
  3. 不覆寫來源檔；ASR 結果落地成旁路 `{檔名} ASR.json`（比照 `common/06` 慣例）。
  4. 一律開 VAD——whisper-cli 對靜音／純配樂段會捏造文字（見計畫書 §十）。

用法：
    python scripts/bite_workbench.py --dir "G:\\我的雲端硬碟\\Claude共用\\SOT自動寫稿測試\\某SLUG"
    python scripts/bite_workbench.py            # 不給 --dir 就在頁面上輸入
瀏覽器開 http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sb_format as SBF  # noqa: E402
import side_precut as SP  # noqa: E402

# fastapi 必須在模組層 import——理由見 build_app() 的 docstring。
# 沒裝 fastapi 時仍可 import 本檔用 scan_dir／transcribe／build_candidates（測試就是這樣跑）。
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
except ImportError:  # pragma: no cover - 只有沒裝 fastapi 的環境會走到
    FastAPI = None

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".wav", ".mp3", ".m4a"}
WHISPER_MODEL_DIR = os.path.expanduser("~/.claude-video-vision/models")
WHISPER_MODEL = os.path.join(WHISPER_MODEL_DIR, "ggml-large-v3-turbo.bin")
VAD_MODEL = os.path.join(WHISPER_MODEL_DIR, "ggml-silero-v5.1.2.bin")

# 候選段落長度：`07-bite-assistant.md`（側錄 2 句話或 10–20 秒、上限 25 秒）
CAND_MIN_SEC = 8.0
CAND_MAX_SEC = 25.0
UTTERANCE_GAP = 0.8          # 小於這個間隔的相鄰 ASR 段視為同一段話

# 純交接語不掐（`07` P-022 取捨順序最末）——只做初篩，命中仍列出並標記，不靜默丟掉
HANDOFF_RE = re.compile(
    r"(for cnn|back to you|reporting from|i'm \w+ \w+,? (cnn|in )|this is cnn"
    r"|以上是.{0,12}報導|為您報導|接下來由)", re.I)

# 官方文稿裡的引言標記（RT／AP／CNN Newsource 三種寫法）
QUOTE_MARK_RE = re.compile(
    r"^\s*(SOUNDBITE|SOT|SAYING|SUPERS?)\b(.*)$", re.I | re.M)


# ---------------------------------------------------------------- 素材探索

@dataclass
class Material:
    path: str
    name: str
    kind: str                      # numbered / side / plain
    material_no: str | None = None
    source: str | None = None      # 側錄來源（CNN／NHK…）
    offset: int = 0
    md: str | None = None          # 母帶日期 M/D（檔名帶 MMDD 時預填）
    script_path: str | None = None
    asr_path: str | None = None
    has_asr: bool = False
    has_subtitle: bool = False


NUMBERED_RE = re.compile(r"#(\d{2})\s+([A-Za-z]+)")
SIDE_SOURCE_RE = re.compile(r"\b(CNN|NHK|BBC|CNA|NBC|ABC|FOX)\b", re.I)
# 側錄另一種實際命名：`{來源} {HHMMSS} {MMDD} {標題}`（例 `CNN 075658 0817 增強藥專題`）。
# offset 解析仍委給 sb_format.offset_from_filename（規則唯一實作），這裡只負責
# 認出「6 碼不在檔名開頭、前面是來源字」這個變形。
SIDE_PREFIX_RE = re.compile(r"^([A-Za-z]{2,6})\s+(\d{6})(?:\s+(\d{4}))?\b")


def scan_dir(path: str) -> list[Material]:
    """把資料夾裡的影音檔配對成素材清單。

    檔名慣例依 `reuters/05-batch-download.md`：`{SLUG} #XX {來源}` 與其
    `{SLUG} #XX {來源} (外電文稿).txt`；6 碼開頭者為側錄，依
    `common/02-tc-offset-filename.md` 取 offset。
    """
    if not os.path.isdir(path):
        raise FileNotFoundError(path)
    out: list[Material] = []
    entries = sorted(os.listdir(path))
    for name in entries:
        full = os.path.join(path, name)
        stem, ext = os.path.splitext(name)
        if not os.path.isfile(full) or ext.lower() not in VIDEO_EXT:
            continue

        offset = SBF.offset_from_filename(name)
        md = None
        m = NUMBERED_RE.search(stem)
        pm = SIDE_PREFIX_RE.match(stem)
        if m:
            kind, no, src = "numbered", m.group(1), m.group(2)
        elif offset:
            kind, no, src = "side", None, None
            sm = SIDE_SOURCE_RE.search(stem)
            src = sm.group(1).upper() if sm else None
        elif pm and SBF.offset_from_filename(pm.group(2)):
            kind, no, src = "side", None, pm.group(1).upper()
            offset = SBF.offset_from_filename(pm.group(2))
            if pm.group(3):
                md = f"{int(pm.group(3)[:2])}/{int(pm.group(3)[2:])}"
        else:
            kind, no, src = "plain", None, None

        script = None
        for cand in entries:
            if cand.startswith(stem) and cand.lower().endswith(".txt") and "asr" not in cand.lower():
                script = os.path.join(path, cand)
                break
        asr = os.path.join(path, f"{stem} ASR.json")
        sub = any(c.lower().endswith(SUB_EXT) and os.path.splitext(c)[0].startswith(stem)
                  for c in entries)
        out.append(Material(
            path=full, name=name, kind=kind, material_no=no, source=src,
            offset=offset, md=md, script_path=script, asr_path=asr,
            has_asr=os.path.exists(asr), has_subtitle=sub,
        ))
    return out


# ---------------------------------------------------------------- ASR

def _run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


def transcribe(material: Material, language: str = "auto", on_phase=None) -> dict:
    """跑 whisper.cpp 取得**分段**與**詞級**時間戳，落地成旁路 JSON。

    ⚠️ 一律帶 `--vad`：沒有 VAD 時 whisper-cli 會對靜音／純配樂段捏造文字
    （plugin 原始碼 `local.ts` 明載，計畫書 §十 已列為 Phase 1 硬規則）。
    側錄動輒 60 分鐘、內含廣告與配樂墊檔，正是這個失效樣態的溫床。
    """
    for p, what in ((WHISPER_MODEL, "whisper 模型"), (VAD_MODEL, "VAD 模型")):
        if not os.path.exists(p):
            raise FileNotFoundError(f"找不到{what}：{p}")
    if not shutil.which("whisper-cli"):
        raise FileNotFoundError("PATH 裡找不到 whisper-cli")

    def phase(msg: str):
        if on_phase:
            on_phase(msg)

    tmp = tempfile.mkdtemp(prefix="bitewb_")
    try:
        wav = os.path.join(tmp, "audio.wav")
        phase("抽音軌（ffmpeg）")
        r = _run(["ffmpeg", "-y", "-v", "error", "-i", material.path,
                  "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav])
        if r.returncode != 0 or not os.path.exists(wav):
            raise RuntimeError(f"ffmpeg 抽音軌失敗：{r.stderr.strip()[:400]}")

        base = ["whisper-cli", "--model", WHISPER_MODEL, "--file", wav,
                "--language", language, "--vad", "--vad-model", VAD_MODEL,
                "--output-json"]
        seg_prefix = os.path.join(tmp, "seg")
        phase("轉錄分段（whisper.cpp + VAD）")
        r = _run(base + ["--output-file", seg_prefix])
        if r.returncode != 0:
            raise RuntimeError(f"whisper-cli 失敗：{(r.stderr or r.stdout).strip()[:400]}")
        segments = _load_whisper(seg_prefix + ".json")

        word_prefix = os.path.join(tmp, "word")
        phase("轉錄詞級時間戳（--max-len 1）")
        r = _run(base + ["--output-file", word_prefix, "--max-len", "1"])
        words = _load_whisper(word_prefix + ".json") if r.returncode == 0 else []

        data = {
            "source_file": material.name,
            "offset_seconds": material.offset,
            "engine": "whisper.cpp large-v3-turbo (+silero VAD)",
            "segments": segments,
            "words": words,
        }
        with open(material.asr_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _load_whisper(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    out = []
    for s in raw.get("transcription", []):
        off = s.get("offsets") or {}
        text = (s.get("text") or "").strip()
        if not text:
            continue
        out.append({"start": off.get("from", 0) / 1000.0,
                    "end": off.get("to", 0) / 1000.0, "text": text})
    return out


# ------------------------------------------------- TC 來源優先序（07 §省Token核心）

SUB_EXT = (".srt", ".vtt")
SCRIPT_TC_RE = re.compile(r"\b\d{2}:\d{2}:\d{2}[.,:]?\d{0,3}\b|\b\d{4}\s*-\s*\d{4}\b")
_SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{1,3})")


def find_subtitle(material: Material) -> str | None:
    """找同名字幕檔（YouTube 官方／自動字幕，`07` 優先序第 4 項）。

    `07`（2026-08-24 訂）明訂：素材是 YouTube URL 時，下載同一步就要抓字幕，
    **字幕自帶時間碼，不需要再跑 `video_analyze`**——那次 `CNN台獸` 漂移
    事故的教訓就是圖方便跳過這一步。
    """
    d = os.path.dirname(material.path)
    stem = os.path.splitext(material.name)[0]
    for f in sorted(os.listdir(d)):
        if f.lower().endswith(SUB_EXT) and os.path.splitext(f)[0].startswith(stem):
            return os.path.join(d, f)
    return None


def parse_subtitle(path: str) -> list[dict]:
    """SRT／VTT → 與 ASR 同形狀的分段（start／end／text，秒）。"""
    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    out: list[dict] = []
    blocks = re.split(r"\n\s*\n", raw)
    for b in blocks:
        m = _SRT_TIME_RE.search(b)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
        text = " ".join(
            line.strip() for line in b.splitlines()
            if line.strip() and not _SRT_TIME_RE.search(line) and not line.strip().isdigit()
            and not line.strip().upper().startswith("WEBVTT"))
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text:
            out.append({"start": start, "end": end, "text": text})
    return out


def tc_sources(material: Material) -> list[dict]:
    """回報這支素材有哪些 TC 來源可用，依 `07` 的優先序排列。

    **這支只回報、不替人決定**——但前台會照順序用第一個 available 的，
    因為規則寫的是「找到有 TC 的來源就停，不要繼續往下多做」。
    """
    out = []
    has_script_tc = False
    if material.script_path and os.path.exists(material.script_path):
        try:
            with open(material.script_path, encoding="utf-8", errors="replace") as f:
                has_script_tc = bool(SCRIPT_TC_RE.search(f.read()))
        except OSError:
            pass
    out.append({"rank": 1, "kind": "official_script_tc", "label": "官方文稿自帶 TC",
                "available": has_script_tc, "path": material.script_path if has_script_tc else None})
    sub = find_subtitle(material)
    out.append({"rank": 4, "kind": "subtitle", "label": "字幕檔（YouTube 官方／自動）",
                "available": bool(sub), "path": sub})
    out.append({"rank": 5, "kind": "asr", "label": "本機 whisper.cpp 轉錄（最後手段）",
                "available": material.has_asr or os.path.exists(material.asr_path or ""),
                "path": material.asr_path})
    return out


def timeline_for(material: Material) -> tuple[dict | None, str]:
    """取這支素材要用的時間軸，回傳 (資料, 來源說明)。字幕優先於 ASR。"""
    sub = find_subtitle(material)
    if sub:
        segs = parse_subtitle(sub)
        if segs:
            return ({"segments": segs, "words": []},
                    f"字幕檔 {os.path.basename(sub)}（自帶時間碼，依 07 優先序高於 ASR）")
    asr = load_asr(material)
    if asr:
        return asr, "本機 whisper.cpp 轉錄（+VAD）"
    return None, "尚無時間軸來源"


def load_asr(material: Material) -> dict | None:
    if not material.asr_path or not os.path.exists(material.asr_path):
        return None
    with open(material.asr_path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- 官方文稿

def parse_official_quotes(script_path: str | None) -> list[dict]:
    """從官方文稿抽出被標成引言的段落（RT `SAYING`／AP `SOUNDBITE`／NS `SOT`／`SUPERS`）。

    ⚠️ 抽不到標記**不等於沒有 BITE**（`P-046`）——社群 UGC 與側拍常常只有
    一行 caption，音軌裡照樣有人講話。抽不到時前台改走純 ASR 候選，
    並在畫面上明講「這批候選沒有官方引言標記，用字需自行核對」。
    """
    if not script_path or not os.path.exists(script_path):
        return []
    try:
        with open(script_path, encoding="utf-8") as f:
            text = f.read()
    except UnicodeDecodeError:
        with open(script_path, encoding="cp950", errors="replace") as f:
            text = f.read()

    quotes: list[dict] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = QUOTE_MARK_RE.match(line)
        if not m:
            continue
        # `SOUNDBITE (English) Peter Navadny, 職稱:` → 去掉語言括號，只留人名職稱
        speaker = re.sub(r"^\s*\([^)]*\)\s*", "", m.group(2)).strip(" :-–—")
        body: list[str] = []
        for nxt in lines[i + 1:]:
            if QUOTE_MARK_RE.match(nxt) or re.match(r"^\s*(SHOTLIST|STORY|STORYLINE|RESTRICTIONS)\b", nxt, re.I):
                break
            if not nxt.strip():
                if body:
                    break
                continue
            body.append(nxt.strip())
        # 官方稿常把引言包在 "..." 裡，但 SB 第 5 行**不加任何引號**
        # （`00-寫稿通則` §4），所以在這裡就剝掉，不要讓它流到輸出。
        quote = " ".join(body).strip().strip('"“”「」')
        if quote:
            quotes.append({"speaker_hint": speaker, "text": quote, "marker": m.group(1).upper()})
    return quotes


_STOP = set("""a an the and or but if of to in on at for with from by is are was were be been
this that these those it its he she they them his her their we you i as not no so than then
there here what which who whom when where how will would can could should may might must have
has had do does did about into over under after before more most very just also""".split())


def keywords(text: str, n: int = 10) -> list[str]:
    """取 5–10 個關鍵字定位用（優先專有名詞、數字、罕見詞），依 `07` 的做法。"""
    toks = re.findall(r"[A-Za-z0-9']+", text)
    scored = []
    for t in toks:
        low = t.lower()
        if low in _STOP or len(low) < 3:
            continue
        score = len(low) + (5 if any(c.isdigit() for c in t) else 0) + (3 if t[:1].isupper() else 0)
        scored.append((score, low))
    seen, out = set(), []
    for _, w in sorted(scored, reverse=True):
        if w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= n:
            break
    return out


def locate_quote(quote: str, words: list[dict], segments: list[dict]) -> dict | None:
    """用關鍵字把官方引言對到 ASR 時間軸；回傳起訖與命中率。

    命中率低就是「無法可靠判定」——`cnn/02` 明訂這時**不自行猜測 TC**，
    所以這裡照實回報 `confidence`，由前台顯示並讓人決定，不偷偷四捨五入。
    """
    kws = keywords(quote)
    if not kws:
        return None
    stream = words or segments
    if not stream:
        return None

    # 以「單位」為粒度滑窗：詞級來源時一個單位＝一個詞，字幕／分段來源時
    # 一個單位＝一段。窗的大小用**累積詞數**逼近引言詞數——不能用固定的單位
    # 個數，否則字幕來源（一段就好幾十個詞）會把兩三段整個框進來，
    # 產出橫跨數分鐘的假 TC（2026-08-24 實測踩到，見計畫書 §十）。
    units = []
    for u in stream:
        toks = re.findall(r"[A-Za-z0-9']+", u["text"].lower())
        if toks:
            units.append((toks, u["start"], u["end"]))
    if not units:
        return None

    want = max(len(re.findall(r"[A-Za-z0-9']+", quote)), 4)
    kwset = set(kws)
    best, best_hit, best_dur = None, 0, float("inf")
    for i in range(len(units)):
        count, hits, j = 0, set(), i
        while j < len(units) and count < want:
            toks, s, e = units[j]
            count += len(toks)
            hits |= set(toks) & kwset
            j += 1
            # 每擴一個單位就評分一次：命中一樣多時**取比較短的窗**，
            # 否則字幕來源會為了湊滿詞數硬吃下一整段，框出橫跨數分鐘的假 TC。
            dur = e - units[i][1]
            # 合理長度上限：一般語速約每秒 2.5 個詞，抓到 1.5 已經很慢了。
            # 多單位的窗若長到不可能是這句話的長度，就是誤吃了鄰段（鄰段剛好
            # 有個常用詞命中關鍵字），直接不計分——單一單位的窗不套這條，
            # 因為字幕一段本來就可能比引言長。
            if j - i > 1 and dur > want / 1.5 + 5:
                continue
            if len(hits) > best_hit or (len(hits) == best_hit and dur < best_dur):
                best_hit, best_dur, best = len(hits), dur, units[i:j]
        if count < want and i > 0:   # 已到結尾，再往後也湊不滿
            break
    if not best or best_hit < max(2, len(kws) // 3):
        return None

    granular = bool(words)    # 有詞級才算精確；字幕／分段只有段落顆粒度
    return {"start": best[0][1], "end": best[-1][2],
            "confidence": round(best_hit / len(kws), 2),
            "granular": granular,
            "asr_text": " ".join(t for toks, _, _ in best for t in toks)}


# ---------------------------------------------------------------- 段落列舉

@dataclass
class Segment:
    """一個可點選的段落。

    2026-08-25 需求修正：**列出整支素材的所有段落，由人自己挑**——
    秒數門檻、官方引言優先、25 秒上限這些一律降級為 `tags`（UI 篩選／
    排序提示），不做入選條件、不丟行、不截斷。工具不替人篩掉東西。
    """
    start: float
    end: float
    text: str                 # 輸出用（官方引言＝官方稿逐字；其餘＝ASR/字幕文字）
    asr_text: str             # 定位用（ASR，可能有同音錯字）
    origin: str               # official / asr
    speaker_hint: str = ""
    confidence: float | None = None
    tags: list[str] = field(default_factory=list)    # 中性標籤，供 UI 篩選排序
    flags: list[str] = field(default_factory=list)   # 警告文字
    zh: str | None = None     # NLLB 批次翻譯草稿（快取命中才有；殘譯警語適用）

    @property
    def duration(self) -> float:
        return self.end - self.start


def merge_utterances(segments: list[dict]) -> list[dict]:
    out: list[dict] = []
    for s in segments:
        if out and s["start"] - out[-1]["end"] <= UTTERANCE_GAP:
            out[-1]["end"] = s["end"]
            out[-1]["text"] += " " + s["text"]
        else:
            out.append(dict(s))
    return out


def _overlaps(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and b_start < a_end


def build_segments(asr: dict, quotes: list[dict]) -> list[Segment]:
    """列舉**全部**段落＋官方引言定位結果。排序只是時間順序，不是裁決——
    新聞價值與衝突性是編輯判斷，這裡不假裝算得出來（計畫書 §4.3）。"""
    segments, words = asr.get("segments", []), asr.get("words", [])
    out: list[Segment] = []
    located: list[tuple[float, float]] = []

    for q in quotes:
        loc = locate_quote(q["text"], words, segments)
        if not loc:
            out.append(Segment(
                start=0.0, end=0.0, text=q["text"], asr_text="", origin="official",
                speaker_hint=q.get("speaker_hint", ""), confidence=0.0,
                tags=["官方引言"],
                flags=["定位失敗：ASR 對不上這段官方引言，需人工找 TC（cnn/02：不自行猜測）"]))
            continue
        s = Segment(start=loc["start"], end=loc["end"], text=q["text"],
                    asr_text=loc["asr_text"], origin="official",
                    speaker_hint=q.get("speaker_hint", ""), confidence=loc["confidence"],
                    tags=["官方引言"])
        if loc["confidence"] < 0.5:
            s.flags.append(f"關鍵字命中率僅 {loc['confidence']:.0%}，TC 需特別核對")
        if not loc.get("granular"):
            # `07` 方式2 明訂：段落／句群顆粒度的時間標記精確度不足以直接當
            # BITE 起訖，不可只憑它切段落當成品。
            s.flags.append("TC 只有段落顆粒度（來源無詞級時間），起訖需在播放器上自行收窄")
        located.append((s.start, s.end))
        out.append(s)

    # 全部段落一律列出——有官方稿也一樣（官方引言標記只是標籤，不是過濾器）
    for u in merge_utterances(segments):
        s = Segment(start=u["start"], end=u["end"], text=u["text"].strip(),
                    asr_text=u["text"].strip(), origin="asr")
        if any(_overlaps(s.start, s.end, ls, le) for ls, le in located):
            s.tags.append("與官方引言重疊")
        if HANDOFF_RE.search(u["text"]):
            s.tags.append("疑似交接語")
            s.flags.append("疑似純交接語，`P-022` 取捨順序最末——仍列出供判斷")
        out.append(s)

    for s in out:
        d = s.duration
        if s.origin == "asr":
            s.flags.append("非官方引言逐字：**用字須自行核對**，ASR 可能有同音錯字（07／cnn-02）")
        if 0 < d < 2:
            s.tags.append("<8秒")
            s.flags.append("[FAIL] 不足 2 秒（P-015）")
        elif 2 <= d < 5:
            s.tags.append("<8秒")
            s.flags.append("[WARN] 2–5 秒，確認是完整一句（P-015）")
        elif 5 <= d < CAND_MIN_SEC:
            s.tags.append("<8秒")
        elif CAND_MIN_SEC <= d <= CAND_MAX_SEC:
            s.tags.append("10–25秒" if d >= 10 else "8–10秒")
        elif d > CAND_MAX_SEC:
            s.tags.append(">25秒")
            s.flags.append(f"段落 {d:.0f} 秒超過 25 秒上限（07）——不替你截斷，起訖請在播放器上自行收窄")

    # 時間順序；定位失敗的官方引言（start=0）自然排最前，一眼看到
    out.sort(key=lambda s: (s.start, s.end))
    return out


# ---------------------------------------------------------------- 中文翻譯（LLM）

TRANSLATE_PROMPT = """你是臺灣電視新聞的資深編譯。把以下新聞受訪原文翻成 SB 用的繁體中文口白。

規則（來源：TVBS common/00-寫稿通則.md §4）：
- 繁體中文、臺灣新聞用語與固定譯名（例：Trump→川普、Putin→普欽、Zelensky→澤倫斯基）；指涉臺灣這個地方時用「臺」。
- 不加任何引號（不用「」也不用 ""）。
- 完整翻譯整句，不可漏譯、不可殘譯。
- 原文代名詞（he／she／they／it）指涉不明時：若下方「講者」或「前後文」能確定主詞，用半形括號補在句首，例：(普欽)知道這件事；無法確定就保留代名詞翻譯，**不可自行推定主詞**（P-037）。
- 口語自然、可直接當電視口白，不要書面腔。
- 只輸出翻譯本文，不要任何說明、標點以外的符號或前綴。

講者：{speaker}
前後文（僅供理解指涉，不用翻譯）：{context}
原文：{text}"""

TRANSLATE_MODEL = "claude-opus-5"

# 2026-08-25 使用者裁定：翻譯引擎用本機 NLLB-200（CTranslate2）＋警語。
# 實測已知限制（同日紀錄於交接文件 §七）：NLLB 對長複句**會掉句尾（殘譯）**，
# 且 `zho_Hant` 目標語會早停——所以走 zho_Hans 再 OpenCC s2twp 轉臺灣正體，
# 輸出一律附警語要人逐句比對。模型不在時 fallback：Claude API → claude CLI。
NLLB_DIR = os.path.join(WHISPER_MODEL_DIR, "nllb-200-distilled-600M-ct2-int8")
_NLLB: dict = {}

# 臺灣固定譯名（feedback_tai_character_convention／00-寫稿通則）；
# OpenCC s2twp 沒轉到的補在這裡。key 為 s2twp 轉換後的形態。
NLLB_NAME_MAP = {
    "特朗普": "川普", "普京": "普欽", "普丁": "普欽",
    "澤連斯基": "澤倫斯基", "内塔尼亞胡": "納坦雅胡", "內塔尼亞胡": "納坦雅胡",
}


def _nllb_load():
    if not _NLLB:
        import ctranslate2
        import sentencepiece
        import opencc
        _NLLB["sp"] = sentencepiece.SentencePieceProcessor(
            os.path.join(NLLB_DIR, "sentencepiece.bpe.model"))
        _NLLB["tr"] = ctranslate2.Translator(NLLB_DIR, device="cpu")
        _NLLB["cc"] = opencc.OpenCC("s2twp")
    return _NLLB


def _zh_postprocess(zh: str) -> str:
    """NLLB 輸出的收尾：半形標點轉全形、去 CJK 間空白、套固定譯名。"""
    for k, v in NLLB_NAME_MAP.items():
        zh = zh.replace(k, v)
    zh = re.sub(r"\s*,\s*", "，", zh)
    zh = re.sub(r"\s*\.\s*", "。", zh)
    zh = re.sub(r"\s*\?\s*", "？", zh)
    zh = re.sub(r"\s*!\s*", "！", zh)
    zh = re.sub(r"([一-鿿，。？！：；])\s+(?=[一-鿿])", r"\1", zh)
    return zh.strip()


def _nllb_translate(text: str) -> str:
    n = _nllb_load()
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    outs = []
    for s in sents:
        toks = ["eng_Latn"] + n["sp"].encode(s, out_type=str) + ["</s>"]
        r = n["tr"].translate_batch([toks], target_prefix=[["zho_Hans"]], beam_size=4)
        outs.append(n["sp"].decode(
            [t for t in r[0].hypotheses[0] if t not in ("zho_Hans", "</s>")]))
    return _zh_postprocess(n["cc"].convert(" ".join(outs)))


NLLB_WARNING = ("NLLB 草稿：已知會掉句尾（殘譯）且用詞生硬——"
                "請逐句對照第 5 行原文核對，缺的自己補")


# ---------------------------------------------------- 批次翻譯快取（旁路檔）

def zh_cache_path(material: Material) -> str:
    return os.path.splitext(material.path)[0] + " ZH.json"


def load_zh_cache(material: Material) -> dict:
    p = zh_cache_path(material)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_zh_cache(material: Material, cache: dict) -> None:
    with open(zh_cache_path(material), "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)


def attach_zh(segs: list[Segment], cache: dict) -> None:
    """把快取裡的翻譯掛到段落上；key 用段落文字本身（段落是 merge 出來的，
    沒有穩定 id，文字相同＝同一句）。"""
    for s in segs:
        if s.text:
            s.zh = cache.get(s.text)


def translate_zh(text: str, speaker: str = "", context: str = "") -> dict:
    """產生 SB 第 3 行中文翻譯草稿。**是草稿**——殘譯與指涉判斷仍要人看過。

    引擎順序（2026-08-25 使用者裁定）：本機 NLLB-200（零 token、約 1 秒/句，
    附殘譯警語）→ Claude API（ANTHROPIC_API_KEY；Key 不進 repo、不進 HTML）
    → 本機 `claude` CLI（用既有 Claude Code 登入）。
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("沒有原文可翻")

    if os.path.isdir(NLLB_DIR):
        try:
            zh = _nllb_translate(text)
            if zh:
                return {"zh": zh, "engine": "NLLB-200-600M（本機）",
                        "warning": NLLB_WARNING}
        except Exception:
            pass  # NLLB 掛了就往下走 LLM 路徑，不擋人

    prompt = TRANSLATE_PROMPT.format(
        speaker=speaker.strip() or "（未知）",
        context=context.strip() or "（無）", text=text)

    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("有 ANTHROPIC_API_KEY 但沒裝 anthropic 套件：pip install anthropic")
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=TRANSLATE_MODEL, max_tokens=1024,
            messages=[{"role": "user", "content": prompt}])
        zh = "".join(b.text for b in resp.content if b.type == "text").strip()
        engine = f"Claude API ({TRANSLATE_MODEL})"
    else:
        exe = shutil.which("claude")
        if not exe:
            raise RuntimeError("沒有 ANTHROPIC_API_KEY，PATH 也找不到 claude CLI——兩者擇一設好才能自動翻譯")
        r = _run([exe, "-p", prompt, "--output-format", "text"], timeout=180)
        if r.returncode != 0:
            raise RuntimeError(f"claude CLI 失敗：{(r.stderr or r.stdout).strip()[:400]}")
        zh = r.stdout.strip()
        engine = "claude CLI（本機登入）"
    if not zh:
        raise RuntimeError("翻譯引擎回了空字串")
    return {"zh": zh, "engine": engine}


# ---------------------------------------------------------------- HTTP

def precut_status_payload(job, cached, stale, now=None):
    """組 /api/precut/status 回傳。running／error 先回 job，其餘才讀快取。"""
    if now is None:
        now = time.time()
    if job and job.get("state") in ("running", "error"):
        out = dict(job)
        if "started" in out:
            out["elapsed"] = round(now - out.pop("started"), 1)
        return out
    if cached:
        phase = (job or {}).get("phase") or "快取"
        return {"state": "done", "phase": phase, "stale": stale, **cached}
    if not job:
        return {"state": "none"}
    out = dict(job)
    if "started" in out:
        out["elapsed"] = round(now - out.pop("started"), 1)
    return out


def build_app(default_dir: str | None):
    """⚠️ FastAPI 的型別註解必須解析得到——本檔用了 `from __future__ import
    annotations`（註解變字串），若把 `Request` 這類型別 import 在函式區域，
    FastAPI 會在模組 globals 裡找不到它，把 `request` 當成缺少的 query 參數
    回 422。所以 fastapi 的名稱一律 import 在模組層（見檔案上方）。"""
    app = FastAPI(title="掐BITE 工作台")
    state: dict = {"dir": default_dir, "materials": []}

    def refresh(path: str) -> list[Material]:
        state["dir"] = path
        state["materials"] = scan_dir(path)
        return state["materials"]

    if default_dir:
        try:
            refresh(default_dir)   # 先掃一次，否則第一個 /media 請求會找不到素材
        except FileNotFoundError:
            print(f"⚠️ 找不到資料夾：{default_dir}（可在頁面上重新輸入）")

    def get_material(name: str) -> Material:
        for m in state["materials"]:
            if m.name == name:
                return m
        raise HTTPException(404, f"素材不在目前清單：{name}")

    @app.get("/", response_class=HTMLResponse)
    def index():
        with open(os.path.join(HERE, "assets", "bite_workbench.html"), encoding="utf-8") as f:
            return f.read()

    @app.get("/api/materials")
    def api_materials(dir: str | None = None):
        path = dir or state["dir"]
        if not path:
            return {"dir": None, "materials": []}
        try:
            mats = refresh(path)
        except FileNotFoundError:
            raise HTTPException(404, f"找不到資料夾：{path}")
        return {"dir": path, "materials": [asdict(m) for m in mats]}

    # 背景轉錄工作——同步跑 65 分鐘素材要 160 秒以上，fetch 會在那裡
    # 靜默乾等；改成「啟動就回、前端輪詢進度」。
    jobs: dict = {}

    def _precut_run(m: Material):
        job = jobs[f"precut:{m.name}"]
        try:
            data = SP.analyze_file(
                m.path, m.offset,
                on_phase=lambda p: job.update(phase=p),
            )
            job.update(state="done", phase="完成", **data)
        except Exception as e:
            job.update(state="error", error=str(e))

    @app.post("/api/precut")
    def api_precut(payload: dict):
        m = get_material(payload["name"])
        force = bool(payload.get("force"))
        key = f"precut:{m.name}"
        if jobs.get(key, {}).get("state") == "running":
            raise HTTPException(409, "這支素材的初處理分析已在跑，別重複啟動")
        cached = SP.load_cache(m.path)
        if cached and not force:
            stale = SP.cache_stale(m.path, cached)
            jobs[key] = {"state": "done", "phase": "快取", "stale": stale, **cached}
            return {"state": "done", "stale": stale}
        try:
            SP.require_ocr()
        except FileNotFoundError as e:
            raise HTTPException(400, str(e))
        jobs[key] = {"state": "running", "phase": "啟動中", "started": time.time()}
        threading.Thread(target=_precut_run, args=(m,), daemon=True).start()
        return {"state": "running"}

    @app.get("/api/precut/status")
    def api_precut_status(name: str):
        job = jobs.get(f"precut:{name}")
        if job and job.get("state") in ("running", "error"):
            cached = None
            stale = False
        else:
            m = get_material(name)
            cached = SP.load_cache(m.path)
            stale = SP.cache_stale(m.path, cached) if cached else False
        return precut_status_payload(job, cached, stale)

    @app.post("/api/precut/save")
    def api_precut_save(payload: dict):
        m = get_material(payload["name"])
        segs = SP.dicts_to_segs(payload.get("segments") or [])
        SP.save_cache(m.path, m.offset, segs)
        overlap = SP.segs_overlap(segs)
        rows = [SP.seg_to_dict(s, m.offset) for s in segs]
        key = f"precut:{m.name}"
        if jobs.get(key, {}).get("state") == "done":
            jobs[key]["segments"] = rows
        return {"ok": True, "overlap": overlap, "segments": rows}

    def _export_run(m: Material, segs, mode, accurate):
        job = jobs[f"export:{m.name}"]
        try:
            paths = SP.export_segs(
                m.path, segs, mode=mode, accurate=accurate,
                source=m.source or "SIDE", offset_sec=m.offset,
            )
            job.update(state="done", phase="完成", files=paths,
                       dir=SP.export_dir(m.path))
        except Exception as e:
            job.update(state="error", error=str(e))

    @app.post("/api/precut/export")
    def api_precut_export(payload: dict):
        m = get_material(payload["name"])
        mode = payload.get("mode") or "non_ad"
        if mode not in ("non_ad", "selected"):
            raise HTTPException(400, "mode 只能是 non_ad 或 selected")
        accurate = bool(payload.get("accurate"))
        rows = payload.get("segments")
        if rows is None:
            cached = SP.load_cache(m.path) or {}
            rows = cached.get("segments") or []
        segs = SP.dicts_to_segs(rows)
        SP.save_cache(m.path, m.offset, segs)  # 匯出前先落地人改的
        key = f"export:{m.name}"
        if jobs.get(key, {}).get("state") == "running":
            raise HTTPException(409, "這支素材正在剪檔")
        overlap = SP.segs_overlap(segs)
        jobs[key] = {"state": "running", "phase": "剪檔", "started": time.time(),
                     "overlap": overlap}
        threading.Thread(
            target=_export_run, args=(m, segs, mode, accurate), daemon=True
        ).start()
        return {"state": "running", "overlap": overlap}

    @app.get("/api/precut/export/status")
    def api_precut_export_status(name: str):
        job = jobs.get(f"export:{name}")
        if not job:
            return {"state": "none"}
        out = dict(job)
        if "started" in out:
            out["elapsed"] = round(time.time() - out.pop("started"), 1)
        return out

    def _job_run(m: Material, language: str):
        job = jobs[m.name]
        try:
            data = transcribe(m, language,
                              on_phase=lambda p: job.update(phase=p))
            m.has_asr = True
            job.update(state="done", phase="完成",
                       segments=len(data.get("segments", [])),
                       words=len(data.get("words", [])))
        except Exception as e:
            job.update(state="error", error=str(e))

    @app.post("/api/transcribe")
    def api_transcribe(payload: dict):
        m = get_material(payload["name"])
        force = bool(payload.get("force"))
        # `07` 找 TC 優先序：找到有 TC 的來源就停，不要繼續往下多做。
        if m.has_subtitle and not force:
            raise HTTPException(409, "這支素材已有字幕檔（自帶時間碼，優先序高於 ASR）——"
                                     "不需要跑轉錄。真的要重跑請帶 force。")
        job = jobs.get(m.name)
        if job and job.get("state") == "running":
            raise HTTPException(409, "這支素材的轉錄已在跑，別重複啟動")
        if not force and load_asr(m) is not None:
            m.has_asr = True
            return {"state": "done", "note": "已有 ASR 旁路檔，直接沿用"}
        jobs[m.name] = {"state": "running", "phase": "啟動中", "started": time.time()}
        threading.Thread(target=_job_run, args=(m, payload.get("language", "auto")),
                         daemon=True).start()
        return {"state": "running"}

    @app.get("/api/transcribe/status")
    def api_transcribe_status(name: str):
        job = jobs.get(name)
        if not job:
            return {"state": "none"}
        out = dict(job)
        if "started" in out:
            out["elapsed"] = round(time.time() - out.pop("started"), 1)
        return out

    @app.get("/api/segments")
    def api_segments(name: str):
        m = get_material(name)
        timeline, tl_note = timeline_for(m)
        if timeline is None:
            raise HTTPException(409, "這支素材沒有可用的時間軸來源（無字幕、無 ASR），先按「跑轉錄」")
        quotes = parse_official_quotes(m.script_path)
        segs = build_segments(timeline, quotes)
        attach_zh(segs, load_zh_cache(m))
        return {
            "material": asdict(m),
            "official_quotes": len(quotes),
            "tc_sources": tc_sources(m),
            "timeline_note": tl_note,
            "note": ("官方文稿有引言標記（已標「官方引言」），輸出用字以官方稿為準；"
                     "其餘段落仍全部列出供挑選"
                     if quotes else
                     "官方文稿沒有引言標記（或沒有文稿）——不代表沒有 BITE（P-046），"
                     "段落文字來自轉錄結果，用字須自行核對"),
            "segments": [{**asdict(s), "duration": round(s.duration, 2)} for s in segs],
        }

    def _zh_job_run(m: Material, texts: list[str]):
        job = jobs[f"zh:{m.name}"]
        cache = load_zh_cache(m)
        try:
            for i, t in enumerate(texts):
                if t not in cache:
                    cache[t] = _nllb_translate(t)
                    if i % 10 == 0:
                        save_zh_cache(m, cache)   # 邊跑邊落地，中斷不用重來
                job.update(done=i + 1)
            save_zh_cache(m, cache)
            job.update(state="done")
        except Exception as e:
            save_zh_cache(m, cache)
            job.update(state="error", error=str(e))

    @app.post("/api/translate_all")
    def api_translate_all(payload: dict):
        """整支素材所有段落的 NLLB 批次翻譯（背景），結果進旁路快取。
        只走本機 NLLB——批次量大，不 fallback 到 LLM（token／額度成本）。"""
        m = get_material(payload["name"])
        if not os.path.isdir(NLLB_DIR):
            raise HTTPException(409, "批次翻譯需要本機 NLLB 模型（不在就只能逐句用 AI 翻譯鈕）")
        key = f"zh:{m.name}"
        if jobs.get(key, {}).get("state") == "running":
            return {"state": "running"}
        timeline, _ = timeline_for(m)
        if timeline is None:
            raise HTTPException(409, "先跑轉錄才有段落可翻")
        segs = build_segments(timeline, parse_official_quotes(m.script_path))
        cache = load_zh_cache(m)
        texts = list(dict.fromkeys(s.text for s in segs if s.text and s.text not in cache))
        if not texts:
            return {"state": "done", "total": 0}
        jobs[key] = {"state": "running", "done": 0, "total": len(texts), "started": time.time()}
        threading.Thread(target=_zh_job_run, args=(m, texts), daemon=True).start()
        return {"state": "running", "total": len(texts)}

    @app.get("/api/translate_all/status")
    def api_translate_all_status(name: str):
        job = jobs.get(f"zh:{name}")
        if not job:
            return {"state": "none"}
        out = dict(job)
        out.pop("started", None)
        return out

    @app.post("/api/translate")
    def api_translate(payload: dict):
        try:
            return translate_zh(payload.get("text", ""),
                                speaker=payload.get("speaker", ""),
                                context=payload.get("context", ""))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(500, str(e))

    @app.post("/api/sb")
    def api_sb(payload: dict):
        m = get_material(payload["name"])
        start, end = float(payload["start"]), float(payload["end"])
        kind = payload.get("kind") or m.kind
        try:
            tc = SBF.tc_field(
                kind, start, end,
                material_no=payload.get("material_no") or m.material_no,
                source=payload.get("source") or m.source,
                md=payload.get("md") or m.md, offset=m.offset,
            )
        except ValueError as e:
            raise HTTPException(400, str(e))
        sb = SBF.SB(speaker=payload.get("speaker", ""), zh=payload.get("zh", ""),
                    tc=tc, original=payload.get("original", ""))
        return {"text": SBF.render_sb(sb),
                "lint": SBF.lint_sb(sb, duration=end - start)}

    @app.get("/media")
    def media(name: str):
        """影片串流——starlette 的 FileResponse 原生支援 Range（206），
        `<video>` 靠它秒級跳轉；不像先前手寫版把整檔 read() 進記憶體。"""
        m = get_material(name)
        ctype = "video/mp4" if m.path.lower().endswith((".mp4", ".m4v")) else "application/octet-stream"
        return FileResponse(m.path, media_type=ctype)

    @app.exception_handler(FileNotFoundError)
    def _fnf(_req, exc):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    return app


def main() -> int:
    ap = argparse.ArgumentParser(description="掐BITE 工作台（本機）")
    ap.add_argument("--dir", help="素材資料夾（例如 SOT自動寫稿測試\\{SLUG}）")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    import uvicorn
    print(f"掐BITE 工作台 → http://{args.host}:{args.port}")
    uvicorn.run(build_app(args.dir), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
