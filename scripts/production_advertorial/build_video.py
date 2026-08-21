# -*- coding: utf-8 -*-
"""業配剪接：NS 原聲原畫、OS 依稿面 TC 起點、SB ASR 切點。不循環、不用 -shortest。"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sot_common import load_material_map, load_script, probe_duration, run

FPS = "30000/1001"
HEAD_PAD, TAIL_PAD = 0.10, 0.30
VNORM = ["-vf", "scale=1920:1080,setsar=1,fps=" + FPS,
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
ANORM = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--source", default=None)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    base = args.outdir or os.path.dirname(os.path.abspath(args.script))
    osd = os.path.join(base, "os")
    tmp = os.path.join(base, "seg")
    os.makedirs(tmp, exist_ok=True)

    _, _, events = load_script(args.script)
    mmap = load_material_map(args.script)
    if args.source:
        mmap["01"] = args.source
    timings = json.load(open(os.path.join(osd, "os_timings.json"), encoding="utf-8"))
    spans = json.load(open(os.path.join(base, "sb_spans.json"), encoding="utf-8"))

    sb_holes = []
    for s in spans.values():
        sb_holes.append((s["start"] - HEAD_PAD, s["end"] + TAIL_PAD, s.get("file") or mmap["01"]))

    def avoid_sb(file, a, dur):
        b = a + dur
        for hs, he, hf in sb_holes:
            if hf == file and a < he and b > hs:
                if a < hs:
                    return max(0.0, hs - dur)
        return a

    last_ns_end = {}
    segments, timeline = [], []
    for e in events:
        ident = e["id"]
        out = os.path.join(tmp, ident + ".mp4")
        if e["kind"] == "ns":
            src = mmap[e["num"]]
            a, b = e["start"], e["end"]
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", src,
                 "-t", f"{b-a:.3f}", *VNORM, *ANORM, out])
            last_ns_end[e["num"]] = b
        elif e["kind"] == "os":
            alen = timings[ident]["dur"]
            shots = e.get("shots") or []
            num = shots[0]["num"] if shots else "01"
            src = mmap[num]
            start = shots[0]["tc"] if shots else 0.0
            if last_ns_end.get(num, -1) >= start:
                start = last_ns_end[num]
            start = avoid_sb(src, start, alen)
            vslice = os.path.join(tmp, ident + "_v.mp4")
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", src,
                 "-t", f"{alen + 0.3:.3f}", "-an", *VNORM, vslice])
            wav = os.path.join(osd, ident + ".wav")
            run(["ffmpeg", "-y", "-v", "error", "-i", vslice, "-i", wav,
                 "-map", "0:v", "-map", "1:a", "-t", f"{alen:.3f}",
                 *VNORM, *ANORM, out])
            last_ns_end[num] = start + alen
        else:
            s = spans[ident]
            src = s.get("file") or mmap[s.get("num", "01")]
            a, b = s["start"] - HEAD_PAD, s["end"] + TAIL_PAD
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", src,
                 "-t", f"{b-a:.3f}", *VNORM, *ANORM, out])
        segments.append(out)
        timeline.append((e["kind"], ident, probe_duration(out)))

    t, abs_tl = 0.0, []
    for kind, ident, d in timeline:
        abs_tl.append({"kind": kind, "id": ident, "start": round(t, 3), "dur": round(d, 3)})
        t += d
    print("timeline:", [(x["kind"], x["id"], x["start"], x["dur"]) for x in abs_tl])

    lst = os.path.join(tmp, "all.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        for f in segments:
            fh.write("file '%s'\n" % f.replace("\\", "/"))
    assembled = os.path.join(base, "assembled.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", assembled])
    json.dump({"timeline": abs_tl, "total": round(t, 3)},
              open(os.path.join(base, "timeline.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("assembled", assembled, f"{t:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
