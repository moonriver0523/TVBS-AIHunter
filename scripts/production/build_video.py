# -*- coding: utf-8 -*-
"""步驟 3／4 — 剪接組裝。規則見 production/02。

  * SB 邊界來自 ASR 詞級時間戳 → **直接切**（頭 -0.10、尾 +0.30），不做 VAD 二次裁（09 B3）
  * B-roll 池 = 各 SB 之外的畫面串接，依序切給每段 OS，**不重複使用**
  * OS 段影片取「音訊長 + 0.3」、輸出 `-t 音訊長`，**不用 -shortest**（09 B1）
  * 每段先統一規格再 concat，否則接起來會壞

用法：
  python build_video.py --script "{SLUG} 完成文稿.txt" --source "{SLUG}.mp4"
"""
import argparse
import json
import os

from ctv_common import load_script, probe_duration, run

FPS = "30000/1001"
HEAD_PAD, TAIL_PAD = 0.10, 0.30
VNORM = ["-vf", "scale=1920:1080,setsar=1,fps=" + FPS,
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
ANORM = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    base = args.outdir or os.path.dirname(os.path.abspath(args.script))
    osd = os.path.join(base, "os")
    tmp = os.path.join(base, "seg")
    os.makedirs(tmp, exist_ok=True)

    _, blocks = load_script(args.script)
    timings = json.load(open(os.path.join(osd, "os_timings.json"), encoding="utf-8"))
    spans = json.load(open(os.path.join(base, "sb_spans.json"), encoding="utf-8"))

    order = []                     # [("os","os1"), ("sb","sb1"), …] 播出順序
    n = 0
    for b in blocks:
        order.append(("os", f"os{b['bar']}"))
        if b["sb"]:
            n += 1
            order.append(("sb", f"sb{n}"))

    # --- B-roll 池：把 SB（含 pad）以外的畫面串起來 ---
    src_dur = probe_duration(args.source)
    holes = sorted((spans[s]["start"] - HEAD_PAD, spans[s]["end"] + TAIL_PAD)
                   for s in spans)
    parts, cursor = [], 0.0
    for a, b in holes:
        if a - cursor > 0.5:
            parts.append((cursor, a))
        cursor = b
    if src_dur - cursor > 0.5:
        parts.append((cursor, src_dur))
    print("pool parts:", [(round(a, 2), round(b, 2)) for a, b in parts])

    pool_files = []
    for i, (a, b) in enumerate(parts):
        f = os.path.join(tmp, f"pool{i}.mp4")
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", args.source,
             "-t", f"{b - a:.3f}", "-an", *VNORM, f])
        pool_files.append(f)
    lst = os.path.join(tmp, "pool.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        for f in pool_files:
            fh.write("file '%s'\n" % f.replace("\\", "/"))
    pool = os.path.join(tmp, "pool.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", pool])
    pool_dur = probe_duration(pool)
    need = sum(timings[ident]["dur"] for kind, ident in order if kind == "os")
    print(f"pool={pool_dur:.2f}s  OS needs={need:.2f}s")
    if pool_dur < need:
        raise SystemExit("B-roll 比 OS 短：刪冗餘句或 atempo≤1.05（同步 /sp 字幕），"
                         "絕不循環重播畫面（production/02）")

    # --- 逐段輸出 ---
    segments, timeline, offset = [], [], 0.0
    for kind, ident in order:
        if kind == "os":
            alen = timings[ident]["dur"]
            vslice = os.path.join(tmp, ident + "_v.mp4")
            take = min(alen + 0.3, pool_dur - offset)
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{offset:.3f}", "-i", pool,
                 "-t", f"{take:.3f}", "-an", "-c:v", "copy", vslice])
            out = os.path.join(tmp, ident + ".mp4")
            run(["ffmpeg", "-y", "-v", "error", "-i", vslice,
                 "-i", os.path.join(osd, ident + ".wav"),
                 "-map", "0:v", "-map", "1:a", "-t", f"{alen:.3f}",
                 *VNORM, *ANORM, out])
            offset += alen
        else:
            s = spans[ident]
            a, b = s["start"] - HEAD_PAD, s["end"] + TAIL_PAD
            out = os.path.join(tmp, ident + ".mp4")
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", args.source,
                 "-t", f"{b - a:.3f}", *VNORM, *ANORM, out])
        segments.append(out)
        timeline.append((kind, ident, probe_duration(out)))

    t, abs_tl = 0.0, []
    for kind, ident, d in timeline:
        abs_tl.append({"kind": kind, "id": ident, "start": round(t, 3), "dur": round(d, 3)})
        t += d
    print("timeline:", [(x["kind"], x["id"], x["start"], x["dur"]) for x in abs_tl])

    lst2 = os.path.join(tmp, "all.txt")
    with open(lst2, "w", encoding="utf-8") as fh:
        for f in segments:
            fh.write("file '%s'\n" % f.replace("\\", "/"))
    assembled = os.path.join(base, "assembled.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", lst2, "-c", "copy", assembled])
    json.dump({"timeline": abs_tl, "total": round(t, 3)},
              open(os.path.join(base, "timeline.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("assembled:", round(probe_duration(assembled), 2), "s")


if __name__ == "__main__":
    main()
