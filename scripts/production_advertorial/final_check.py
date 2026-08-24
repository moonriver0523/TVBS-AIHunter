# -*- coding: utf-8 -*-
"""交付前終檢（production/09 定版流程第 7 步）。有紅字就不要交。

同時管兩個方向：
  * 該有的有沒有 —— 每句 OS 的 ASR 覆蓋率（繁→簡正規化後比對，09 A8）
  * 不該有的有沒有混進來 —— 全片「聽得到卻沒有任何字幕覆蓋」的區段（09 A7）
另檢查：零長度 cue、有字幕沒配音、clip%、容器規格。

**09 A9（2026-08-24 加）：NS 乾淨度 + SB 逐字比對**
  * NS 段（人潮歡呼等原聲）不該有聽得懂的完整人聲內容——只查「有沒有字幕」會漏，
    因為 NS 本來就沒有字幕，過去曾經整段是主持人在說話而沒被抓到（花蓮暑假2400 案例）。
    做法：全片詞級 ASR 落在每個 NS 區間的中文字數，超過門檻就是「疑似夾帶清晰人聲」。
  * SB 段（受訪 SOT）舊查法只驗證覆蓋率（該講的有沒有講），不驗證「有沒有多講」——
    受訪者常見的贅語／口頭禪如果剪點沒卡準，會被靜靜地剪進成片而沒有任何檢查攔下來
    （同案例：SB 混進未核定的「的平均，這樣的數字」）。
    做法：用 difflib 對齊該段實際說的話跟核定逐字稿，抓出「說了但稿子沒有」的插入片段。

用法：
  python final_check.py --script "{SLUG} 完成文稿.txt"
"""
import argparse
import difflib
import json
import os
import re
import subprocess

import numpy as np
import soundfile as sf

from sot_common import run, slug_from_script

ASR_MODEL = os.environ.get(
    "FW_MODEL", r"E:\GitHub\GPT-SoVITS\tools\asr\models\faster-whisper-large-v3")

NS_SPEECH_MAX_HAN = 2      # NS 區間容許的中文字數上限，超過視為夾帶人聲
SB_INSERT_TOL_HAN = 4      # SB 對齊後，容許的「稿子沒有、但講了」連續字數上限


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


def check_ns_windows(words, timeline):
    """NS 區間裡有幾個中文字被 ASR 聽到——超過門檻代表夾帶了聽得懂的人聲。"""
    bad = []
    for item in timeline:
        if item["kind"] != "ns":
            continue
        a, b = item["start"], item["start"] + item["dur"]
        pad = 0.15
        heard = "".join(w["w"] for w in words if a + pad <= w["s"] <= b - pad)
        if len(heard) > NS_SPEECH_MAX_HAN:
            bad.append((item["id"], round(a, 2), round(b, 2), heard))
    return bad


def check_sb_extra_speech(words, timeline, sb_spans):
    """SB 區間實際講的話 vs 核定逐字稿，抓「講了但稿子沒有」的插入片段。"""
    bad = []
    for item in timeline:
        if item["kind"] != "sb":
            continue
        span = sb_spans.get(item["id"])
        if not span:
            continue
        a, b = item["start"], item["start"] + item["dur"]
        heard = "".join(w["w"] for w in words if a <= w["s"] <= b)
        target = han("".join(span.get("zh_lines") or [span.get("zh", "")]))
        if not heard or not target:
            continue
        sm = difflib.SequenceMatcher(None, target, heard, autojunk=False)
        extras = [heard[j1:j2] for tag, i1, i2, j1, j2 in sm.get_opcodes()
                  if tag in ("insert", "replace") and (j2 - j1) >= SB_INSERT_TOL_HAN]
        if extras:
            bad.append((item["id"], round(a, 2), round(b, 2), extras))
    return bad


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
    segs, _ = model.transcribe(wav, language="zh", word_timestamps=True, beam_size=5)
    segs = list(segs)
    words = []
    for s in segs:
        for w in (s.words or []):
            t = han(w.word)
            if t:
                words.append({"w": t, "s": w.start, "e": w.end})
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

    tl_path = os.path.join(base, "timeline.json")
    sb_path = os.path.join(base, "sb_spans.json")
    ns_bad, sb_bad = [], []
    if os.path.exists(tl_path):
        timeline = json.load(open(tl_path, encoding="utf-8"))["timeline"]
        ns_bad = check_ns_windows(words, timeline)
        print(f"NS段={sum(1 for t in timeline if t['kind']=='ns')} 疑似夾帶人聲={len(ns_bad)}")
        for nid, a, b, heard in ns_bad:
            print(f"  [NS有清晰人聲] {nid} {a}-{b}s 聽到:「{heard}」")
        if os.path.exists(sb_path):
            sb_spans = json.load(open(sb_path, encoding="utf-8"))
            sb_bad = check_sb_extra_speech(words, timeline, sb_spans)
            print(f"SB段={sum(1 for t in timeline if t['kind']=='sb')} 混入未核定內容={len(sb_bad)}")
            for sid, a, b, extras in sb_bad:
                print(f"  [SB混入贅語] {sid} {a}-{b}s 多講了:{extras}")
    else:
        print("  [略過 NS/SB 檢查] 找不到 timeline.json")

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

    bad = bool(weak or zero or silent or uncaptioned or clip or ns_bad or sb_bad)
    print("\n" + ("[FAIL] 有問題，先修再交" if bad else "[PASS] 終檢全過"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
