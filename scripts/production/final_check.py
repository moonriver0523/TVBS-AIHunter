# -*- coding: utf-8 -*-
"""交付前終檢（production/09 定版流程第 7 步）。有紅字就不要交。

同時管兩個方向：
  * 該有的有沒有 —— 每句 OS 的 ASR 覆蓋率（繁→簡正規化後比對，09 A8）
  * 不該有的有沒有混進來 —— 全片「聽得到卻沒有任何字幕覆蓋」的區段（09 A7）
另檢查：零長度 cue、有字幕沒配音、clip%、容器規格。

用法：
  python final_check.py --script "{SLUG} 完成文稿.txt"
"""
import argparse
import json
import os
import re
import subprocess

import numpy as np
import soundfile as sf

from ctv_common import run, slug_from_script

ASR_MODEL = os.environ.get(
    "FW_MODEL", r"E:\GitHub\GPT-SoVITS\tools\asr\models\faster-whisper-large-v3")


def han(s, _t2s=[None]):
    import cn2an
    if _t2s[0] is None:
        import opencc
        _t2s[0] = opencc.OpenCC("t2s")
    try:
        s = cn2an.transform(s, "an2cn")
    except Exception:
        pass
    return re.sub(r"[^\u4e00-\u9fff]", "", _t2s[0].convert(s).replace("著", "着"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    base = args.outdir or os.path.dirname(os.path.abspath(args.script))
    slug = slug_from_script(args.script)
    master = os.path.join(base, f"{slug} 完成帶.mp4")
    wav = os.path.join(base, "final16k.wav")
    if not os.path.exists(wav):
        run(["ffmpeg", "-y", "-v", "error", "-i", master, "-vn",
             "-ac", "1", "-ar", "16000", wav])

    print(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=codec_name,width,height,r_frame_rate,channels,sample_rate",
         "-of", "default=nw=1", master],
        capture_output=True, text=True, check=True).stdout.strip())

    from faster_whisper import WhisperModel
    from pypinyin import lazy_pinyin

    timings = json.load(open(os.path.join(base, "os", "os_timings.json"), encoding="utf-8"))
    os_lines = [l["text"] for b in sorted(timings) for l in timings[b]["lines"]]
    model = WhisperModel(ASR_MODEL, device="cuda", compute_type="float16")
    segs, _ = model.transcribe(wav, language="zh", beam_size=5)
    got = lazy_pinyin("".join(han(s.text) for s in segs))

    weak = []
    for ln in os_lines:
        seq = lazy_pinyin(han(ln))
        if not seq:
            continue
        i = hit = 0
        for p in got:
            if i < len(seq) and p == seq[i]:
                hit += 1
                i += 1
        if hit / len(seq) < 0.8:
            weak.append((ln, round(hit / len(seq), 2)))
    print(f"OS lines={len(os_lines)} weak(<0.80)={len(weak)}")
    for w in weak:
        print("  weak:", w)

    cues = json.load(open(os.path.join(base, "cues.json"), encoding="utf-8"))["cap"]
    y, sr = sf.read(wav)

    def rms(a, b):
        seg = y[int(max(0, a) * sr):int(b * sr)]
        return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0

    def peak_rms(a, b, win=0.1):
        best, t = 0.0, a
        while t < b:
            best = max(best, rms(t, min(t + win, b)))
            t += win
        return best

    total = len(y) / sr
    zero = [c for c in cues if c[1] - c[0] <= 0.05]
    silent = [c for c in cues if peak_rms(c[0], c[1]) < 0.02]
    uncaptioned, prev = [], 0.0
    for a, b, _ in cues:
        if a - prev > 0.4 and rms(prev, a) > 0.02:
            uncaptioned.append((round(prev, 2), round(a, 2)))
        prev = max(prev, b)
    if total - prev > 0.4 and rms(prev, total) > 0.02:
        uncaptioned.append((round(prev, 2), round(total, 2)))
    clip = float(np.mean(np.abs(y) > 0.99))

    print(f"cues={len(cues)} zero_len={len(zero)} silent_cue={len(silent)} "
          f"uncaptioned_audio={len(uncaptioned)} clip%={clip}")
    for c in silent:
        print("  有字幕沒配音:", round(c[0], 2), round(c[1], 2), c[2])
    for u in uncaptioned:
        print("  有聲音沒字幕:", u)

    bad = bool(weak or zero or silent or uncaptioned or clip)
    print("\n" + ("[FAIL] 有問題，先修再交" if bad else "[PASS] 終檢全過"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
