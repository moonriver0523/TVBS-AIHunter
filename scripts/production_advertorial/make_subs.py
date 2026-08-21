# -*- coding: utf-8 -*-
"""業配上字：Cap／Bar／Super 規格跟 CTV production/03。

  * Cap 每行 ≤14 全形；時間鎖在該 OS／SB 段內，禁止拉去填 NS
  * Bar 16.5–17.5（上字專用壓縮，不改完成稿主標）
  * Super ≤16.5；只在 SB
  * OS 用 synth 詞級區間，折行按字數比例切在該句語音裡
  * SB 用 asr_words 錨中文行；沒有才在有聲區間等比例
  * NS 只出 Bar、不出 Cap
"""
import argparse
import json
import os
import re

import numpy as np
import soundfile as sf

from sot_common import (fit_bar_ctv, line_width, load_script, run,
                        slug_from_script, wrap14)

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
SB_HEAD, SB_TAIL = 0.10, 0.30


def ts(t):
    t = max(0.0, t)
    return "%d:%02d:%05.2f" % (int(t // 3600), int(t % 3600 // 60), t % 60)


def han(s):
    return re.sub(r"[^一-鿿0-9]", "", s)


def split_by_weight(chunks, t0, t1):
    weights = [max(1.0, line_width(c)) for c in chunks]
    tot = sum(weights) or 1.0
    out, cur = [], t0
    span = max(0.05, t1 - t0)
    for i, ch in enumerate(chunks):
        nxt = t1 if i == len(chunks) - 1 else cur + span * (weights[i] / tot)
        if nxt - cur < 0.20 and i < len(chunks) - 1:
            nxt = min(t1, cur + 0.20)
        out.append([cur, nxt, ch])
        cur = nxt
    if out:
        out[-1][1] = t1
    return out


def sb_from_asr(zh, words, src0, src1, prog0, prog1):
    chunks = wrap14(zh)
    win = [w for w in words if src0 - 0.2 <= w["s"] <= src1 + 0.2]
    if not win or not chunks:
        return split_by_weight(chunks, prog0, prog1)
    cat = "".join(w["w"] for w in win)
    idx = []
    for w in win:
        idx.extend([w] * max(1, len(han(w["w"]))))
    target = han(zh)
    pos = cat.find(han(chunks[0])[:4]) if chunks else 0
    if pos < 0:
        pos = 0
    out, cursor = [], pos
    for i, ch in enumerate(chunks):
        n = max(1, len(han(ch)))
        a = idx[min(cursor, len(idx) - 1)]
        b = idx[min(cursor + n - 1, len(idx) - 1)]
        cursor += n
        def to_prog(src_t):
            # 素材時間 → 節目時間
            r = 0.0 if src1 == src0 else (src_t - src0) / (src1 - src0)
            return prog0 + r * (prog1 - prog0)
        t0, t1 = to_prog(a["s"]), to_prog(b["e"])
        if t1 <= t0:
            t1 = t0 + 0.25
        out.append([t0, t1, ch])
    if out:
        out[0][0] = max(out[0][0], prog0)
        out[-1][1] = min(max(out[-1][1], out[-1][0] + 0.25), prog1)
    return out


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

    doc, _, events = load_script(args.script)
    bar_of = {e["id"]: e["bar"] for e in events if e["kind"] == "os"}
    timings = json.load(open(os.path.join(base, "os", "os_timings.json"), encoding="utf-8"))
    spans = json.load(open(os.path.join(base, "sb_spans.json"), encoding="utf-8"))
    tl = json.load(open(os.path.join(base, "timeline.json"), encoding="utf-8"))
    words = []
    wp = os.path.join(base, "asr_words.json")
    if os.path.exists(wp):
        words = json.load(open(wp, encoding="utf-8"))

    bar_text = fit_bar_ctv(doc.title)
    print("BAR on-air:", bar_text, "w=", line_width(bar_text))

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
    seg_of = []  # cap index → (seg_start, seg_end, kind)

    for item in tl["timeline"]:
        st, d, ident = item["start"], item["dur"], item["id"]
        kind = item["kind"]
        if kind == "os":
            n = bar_of.get(ident, 1)
            card = doc.cards.get(n, bar_text)
            if line_width(card) > 17.5:
                card = fit_bar_ctv(card)
            bar.append([st, st + d, card])
            for ln in timings[ident]["lines"]:
                t0 = st + ln["start"]
                t1 = st + min(ln["end"], d)
                t0 = max(st, t0)
                t1 = min(st + d, max(t0 + 0.20, t1))
                text = ln["text"].strip()
                chunks = [text] if line_width(text) <= 14.01 else wrap14(text)
                for a, b, t in split_by_weight(chunks, t0, t1):
                    cap.append([a, b, t])
                    seg_of.append((st, st + d, "os"))
        elif kind == "ns":
            bar.append([st, st + d, bar_text if line_width(bar_text) <= 17.5 else fit_bar_ctv(bar_text)])
        else:
            s = spans[ident]
            sup.append([st, st + d, s["speaker"]])
            p0, p1 = st + SB_HEAD, st + d - SB_TAIL
            if p1 <= p0:
                p0, p1 = st, st + d
            zh_lines = s.get("zh_lines") or None
            if zh_lines:
                local = split_by_weight(zh_lines, p0, p1)
            else:
                local = sb_from_asr(s.get("zh", ""), words, s["start"], s["end"], p0, p1)
            for a, b, t in local:
                a = max(p0, a)
                b = min(p1, max(a + 0.20, b))
                cap.append([a, b, t])
                seg_of.append((st, st + d, "sb"))

    # 尾字 +0.15，但不得跨出本段、不得吃到下一句
    for i in range(len(cap)):
        seg_end = seg_of[i][1]
        nxt = cap[i + 1][0] if i + 1 < len(cap) else seg_end
        # 若下一句已是別段，不要延長進去
        if i + 1 < len(cap) and seg_of[i + 1][2] != seg_of[i][2]:
            nxt = min(nxt, seg_end)
        cap[i][1] = min(cap[i][1] + 0.15, nxt, seg_end)

    # 補洞：只在同一 OS／SB 段內；NS 原聲不准用 OS 字幕去填
    filled = 0
    for i in range(len(cap) - 1):
        if seg_of[i][2] != seg_of[i + 1][2]:
            continue
        if seg_of[i][0] != seg_of[i + 1][0]:
            continue
        gap0, gap1 = cap[i][1], cap[i + 1][0]
        if 0.12 < gap1 - gap0 < 1.20 and rms(gap0, gap1) > 0.02:
            cap[i][1] = gap1
            filled += 1

    over14 = [c[2] for c in cap if line_width(c[2]) > 14.01]
    zero = [c for c in cap if c[1] - c[0] <= 0.05]
    silent = [c for c in cap if peak_rms(c[0], c[1]) < 0.02]
    print(f"cues={len(cap)} filled={filled} zero_len={len(zero)} "
          f"silent_cue={len(silent)} over14={len(over14)} bar_w={line_width(bar_text)}")
    for t in over14:
        print("  [超過14字]", line_width(t), t)
    for c in silent:
        print("  [有字幕沒配音]", round(c[0], 2), round(c[1], 2), c[2])

    with open(ass, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(HEADER)
        for a, b, t in bar:
            f.write(f"Dialogue: 0,{ts(a)},{ts(b)},Bar,,0,0,0,,{t}\n")
        for a, b, t in sup:
            f.write(f"Dialogue: 0,{ts(a)},{ts(b)},Super,,0,0,0,,{t}\n")
        for a, b, t in cap:
            f.write(f"Dialogue: 1,{ts(a)},{ts(b)},Cap,,0,0,0,,{t}\n")

    cwd = os.getcwd()
    os.chdir(base)
    run(["ffmpeg", "-y", "-v", "error", "-i", os.path.basename(assembled),
         "-vf", "subtitles=subs.ass", "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy",
         os.path.basename(out)])
    os.chdir(cwd)
    json.dump({"cap": cap, "bar": bar, "super": sup, "bar_text": bar_text},
              open(os.path.join(base, "cues.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("burned:", out)


if __name__ == "__main__":
    main()
