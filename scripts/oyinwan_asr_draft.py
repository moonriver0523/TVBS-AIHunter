#!/usr/bin/env python3
"""歐印萬掃帶 pipeline 前段：本機 whisper.cpp ASR，直接產出「原始逐字稿」。

見 common/15-歐印萬掃帶.md「原始逐字稿備份」。原本這份逐句原文（未翻譯、
未濃縮、相對時間戳）是靠 video_analyze 轉錄出來的，要花掉 LLM token 去
「聽」整支音檔。這支腳本改用本機 whisper.cpp（+VAD、與 scripts/bite_workbench.py
共用同一顆 large-v3-turbo 模型）做語音轉文字，輸出格式直接對齊規格，可
原封不動存成 `{檔名}_原始逐字稿.txt`。

下一步（TC 大段翻譯：敘事整併、講者角色判斷、專名訂正、150字摘要）
仍需要 Agent 讀這份草稿來寫，不在本腳本自動處理範圍內。

用法：
    python scripts/oyinwan_asr_draft.py "<來源media路徑>" [-o 輸出目錄]

輸出：`{來源檔名}_原始逐字稿.txt`，預設寫在來源檔案同一資料夾（可用 -o 覆寫）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

MODEL_DIR = os.path.expanduser("~/.claude-video-vision/models")
WHISPER_MODEL = os.path.join(MODEL_DIR, "ggml-large-v3-turbo.bin")
VAD_MODEL = os.path.join(MODEL_DIR, "ggml-silero-v5.1.2.bin")


def fmt_mmss(total_seconds: float) -> str:
    total = int(round(total_seconds))
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"


def transcribe(media_path: str, language: str = "auto") -> tuple[list[dict], float]:
    for p, what in ((WHISPER_MODEL, "whisper 模型"), (VAD_MODEL, "VAD 模型")):
        if not os.path.exists(p):
            raise FileNotFoundError(f"找不到{what}：{p}")
    if not shutil.which("whisper-cli"):
        raise FileNotFoundError("PATH 裡找不到 whisper-cli")

    tmp = tempfile.mkdtemp(prefix="oyinwan_asr_")
    try:
        wav = os.path.join(tmp, "audio.wav")
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", media_path,
             "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0 or not os.path.exists(wav):
            raise RuntimeError(f"ffmpeg 抽音軌失敗：{r.stderr.strip()[:400]}")

        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", wav],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        duration = float(r.stdout.strip() or 0)

        seg_prefix = os.path.join(tmp, "seg")
        r = subprocess.run(
            ["whisper-cli", "--model", WHISPER_MODEL, "--file", wav,
             "--language", language, "--vad", "--vad-model", VAD_MODEL,
             "--output-json", "--output-file", seg_prefix],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=1800,
        )
        if r.returncode != 0:
            raise RuntimeError(f"whisper-cli 失敗：{(r.stderr or r.stdout).strip()[:400]}")

        with open(seg_prefix + ".json", encoding="utf-8") as f:
            raw = json.load(f)
        segments = []
        for s in raw.get("transcription", []):
            off = s.get("offsets") or {}
            text = (s.get("text") or "").strip()
            if not text:
                continue
            segments.append({
                "start": off.get("from", 0) / 1000.0,
                "end": off.get("to", 0) / 1000.0,
                "text": text,
            })
        return segments, duration
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_output(media_path: str, segments: list[dict], duration: float) -> str:
    basename = os.path.basename(media_path)
    stem = os.path.splitext(basename)[0]
    lines = [
        f"原始逐字稿(未翻譯/未濃縮)— {stem}",
        f"來源檔案:{basename}(時長 {fmt_mmss(duration)})",
        "備註:逐句ASR原文(英語/日語等,未翻譯),保留原始時間戳(相對於音檔起點,未加TC偏移),"
        "供TC中文大段翻譯/雙語逐字稿製作參考。本檔由本機 whisper.cpp(large-v3-turbo+VAD)"
        "自動轉錄產生,未經人工/LLM校對,人名專名可能有誤,需於後續整併階段查證訂正。",
        "",
    ]
    for seg in segments:
        lines.append(f"[{fmt_mmss(seg['start'])}-{fmt_mmss(seg['end'])}] {seg['text']}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("media", help="來源音檔/影片路徑")
    ap.add_argument("-o", "--outdir", help="輸出目錄(預設:來源檔案同一資料夾)")
    ap.add_argument("--language", default="auto", help="whisper 語言代碼(預設 auto)")
    args = ap.parse_args()

    segments, duration = transcribe(args.media, args.language)
    text = build_output(args.media, segments, duration)

    stem = os.path.splitext(os.path.basename(args.media))[0]
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.media))
    outpath = os.path.join(outdir, f"{stem}_原始逐字稿.txt")
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"{len(segments)} 段, 時長 {fmt_mmss(duration)} -> {outpath}")


if __name__ == "__main__":
    main()
