# -*- coding: utf-8 -*-
"""步驟 4／4 — 三層字幕（Cap／Bar／Super）＋ 硬燒。規則見 production/03。

  * OS 字幕用合成階段的詞級對齊結果（無零長度、尾字 +0.15s，09 C1／C2）
  * SB 字幕錨到原文詞尾（locate_sb.py 產出），受訪者句中停頓不會吃掉整條字幕
  * 補洞（09 C3）：cue 間有聲音卻沒字幕就把前一句延長
  * MarginV 依 TVBS 安全框（1920×1080 下緣 y=860）
  * 燒錄時 cd 到 .ass 所在目錄、用相對檔名（09 D1）

用法：
  python make_subs.py --script "{SLUG} 完成文稿.txt"
"""
import argparse
import json
import os

import numpy as np
import soundfile as sf

from ctv_common import load_script, run, slug_from_script

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Microsoft JhengHei,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,140,140,220,1
Style: Bar,Microsoft JhengHei,52,&H0000FFFF,&H0000FFFF,&H00000000,&HA0401800,-1,0,0,0,100,100,0,0,3,6,0,2,140,140,300,1
Style: Super,Microsoft JhengHei,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&HA0801000,-1,0,0,0,100,100,0,0,3,6,0,1,140,140,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
SB_HEAD, SB_TAIL = 0.10, 0.30      # 與 build_video.py 的切點 pad 一致


def ts(t):
    t = max(0.0, t)
    return "%d:%02d:%05.2f" % (int(t // 3600), int(t % 3600 // 60), t % 60)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    base = args.outdir or os.path.dirname(os.path.abspath(args.script))
    slug = slug_from_script(args.script)
    assembled = os.path.join(base, "assembled.mp4")
    wav = os.path.join(base, "assembled.wav")
    ass = os.path.join(base, "subs.ass")
    out = os.path.join(base, f"{slug} 完成帶.mp4")

    doc, _ = load_script(args.script)
    timings = json.load(open(os.path.join(base, "os", "os_timings.json"), encoding="utf-8"))
    spans = json.load(open(os.path.join(base, "sb_spans.json"), encoding="utf-8"))
    tl = json.load(open(os.path.join(base, "timeline.json"), encoding="utf-8"))

    if not os.path.exists(wav):
        run(["ffmpeg", "-y", "-v", "error", "-i", assembled, "-vn",
             "-ac", "1", "-ar", "16000", wav])
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

    cap, bar, sup = [], [], []
    for item in tl["timeline"]:
        st, d, ident = item["start"], item["dur"], item["id"]
        if item["kind"] == "os":
            n = int(ident.replace("os", ""))
            bar.append([st, st + d, doc.cards[n]])
            for ln in timings[ident]["lines"]:
                cap.append([st + ln["start"], st + min(ln["end"], d), ln["text"]])
        else:
            s = spans[ident]
            sup.append([st, st + d, s["speaker"]])
            clip_start = s["start"] - SB_HEAD          # 素材時間 → 節目時間
            cur, last = st + SB_HEAD, st + d - SB_TAIL
            for i, c in enumerate(s["captions"]):
                end = last if i == len(s["captions"]) - 1 else \
                    min(last, st + (c["end"] - clip_start))
                if end <= cur:
                    end = min(last, cur + 0.3)
                cap.append([cur, end, c["text"]])
                cur = end

    cap.sort(key=lambda c: c[0])
    for i in range(len(cap)):                          # 09 C2 尾字延長
        nxt = cap[i + 1][0] if i + 1 < len(cap) else tl["total"]
        cap[i][1] = min(cap[i][1] + 0.15, nxt)

    filled = 0                                         # 09 C3 補洞
    if cap and cap[0][0] > 0.30 and rms(0, cap[0][0]) > 0.02:
        cap[0][0] = 0.0
        filled += 1
    for i in range(len(cap) - 1):
        if cap[i + 1][0] - cap[i][1] > 0.30 and rms(cap[i][1], cap[i + 1][0]) > 0.02:
            cap[i][1] = cap[i + 1][0]
            filled += 1
    if tl["total"] - cap[-1][1] > 0.30 and rms(cap[-1][1], tl["total"]) > 0.02:
        cap[-1][1] = tl["total"]
        filled += 1

    zero = [c for c in cap if c[1] - c[0] <= 0.05]
    silent = [c for c in cap if peak_rms(c[0], c[1]) < 0.02]
    orphan = [(round(cap[i][1], 2), round(cap[i + 1][0], 2))
              for i in range(len(cap) - 1)
              if cap[i + 1][0] - cap[i][1] > 0.30
              and rms(cap[i][1], cap[i + 1][0]) > 0.02]
    print(f"cues={len(cap)} filled={filled} zero_len={len(zero)} "
          f"silent_cue={len(silent)} orphan_audio={len(orphan)}")
    for c in silent:
        print("  [有字幕沒配音]", round(c[0], 2), round(c[1], 2), c[2])
    for o in orphan:
        print("  [有配音沒字幕]", o)

    with open(ass, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(HEADER)
        for a, b, t in bar:
            f.write(f"Dialogue: 0,{ts(a)},{ts(b)},Bar,,0,0,0,,{t}\n")
        for a, b, t in sup:
            f.write(f"Dialogue: 0,{ts(a)},{ts(b)},Super,,0,0,0,,{t}\n")
        for a, b, t in cap:
            f.write(f"Dialogue: 1,{ts(a)},{ts(b)},Cap,,0,0,0,,{t}\n")

    cwd = os.getcwd()
    os.chdir(base)                                     # 09 D1
    run(["ffmpeg", "-y", "-v", "error", "-i", os.path.basename(assembled),
         "-vf", "subtitles=subs.ass", "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy",
         os.path.basename(out)])
    os.chdir(cwd)
    json.dump({"cap": cap, "bar": bar, "super": sup},
              open(os.path.join(base, "cues.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("burned:", out)


if __name__ == "__main__":
    main()
