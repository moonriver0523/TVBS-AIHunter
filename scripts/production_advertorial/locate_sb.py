# -*- coding: utf-8 -*-
"""業配 SB 定位：只轉訪問段、中文對齊。路線 B：ASR 詞級後直接切、不再 VAD。"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sot_common import load_material_map, load_script, run, slug_from_script, write_text

ASR_MODEL = os.environ.get(
    "FW_MODEL", r"E:\GitHub\GPT-SoVITS\tools\asr\models\faster-whisper-large-v3")


def han(s):
    return re.sub(r"[^\u4e00-\u9fff]", "", s)


def transcribe_window(source, wav, start, end, lang="zh"):
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{end-start:.3f}",
         "-i", source, "-vn", "-ac", "1", "-ar", "16000", wav])
    from faster_whisper import WhisperModel
    model = WhisperModel(ASR_MODEL, device="cuda", compute_type="float16")
    segs, _ = model.transcribe(wav, language=lang, word_timestamps=True,
                               vad_filter=False, beam_size=5)
    words = []
    for s in segs:
        for w in (s.words or []):
            t = han(w.word)
            if t:
                words.append({"w": t, "s": round(w.start + start, 3),
                              "e": round(w.end + start, 3)})
    return words


def find_zh(words, zh, tc, slack=4.0):
    target = han(zh)
    if not target:
        return None
    lo, hi = tc[0] - slack, tc[1] + slack
    win = [w for w in words if lo <= w["s"] <= hi]
    if not win:
        return None
    cat, idx = "", []
    for w in win:
        cat += w["w"]
        idx.extend([w] * len(w["w"]))
    pos = cat.find(target[:8])
    if pos < 0:
        # 鬆一點：取最長前綴
        best = -1
        for n in range(min(12, len(target)), 3, -1):
            p = cat.find(target[:n])
            if p >= 0:
                best = p
                target_len = n
                break
        if best < 0:
            return None
        pos, tlen = best, target_len
    else:
        tlen = min(len(target), max(8, len(target)))
        # 從 pos 吃滿 target
        tlen = min(len(cat) - pos, len(target))
    a = idx[pos]["s"]
    b = idx[min(pos + tlen - 1, len(idx) - 1)]["e"]
    return a, b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--source", default=None)
    ap.add_argument("--outdir", default=None)
    args = ap.parse_args()

    base = args.outdir or os.path.dirname(os.path.abspath(args.script))
    os.makedirs(base, exist_ok=True)
    slug = slug_from_script(args.script)
    _, _, events = load_script(args.script)
    mmap = load_material_map(args.script)
    if args.source:
        mmap["01"] = args.source

    sbs = [e for e in events if e["kind"] == "sb"]
    if not sbs:
        raise SystemExit("沒有 SB")

    # 只轉訪問窗口（各 SB ±15s 合併）
    src = mmap[sbs[0]["num"]]
    win0 = min(s["tc"][0] for s in sbs) - 15
    win1 = max(s["tc"][1] for s in sbs) + 15
    wav = os.path.join(base, "sb_window16k.wav")
    words_path = os.path.join(base, "asr_words.json")
    if os.path.exists(words_path):
        words = json.load(open(words_path, encoding="utf-8"))
        print("reuse asr_words.json", len(words), "words")
    else:
        words = transcribe_window(src, wav, max(0, win0), win1)
        json.dump(words, open(words_path, "w", encoding="utf-8"),
                  ensure_ascii=False)
    lines = [f"{w['s']:.2f}-{w['e']:.2f}  {w['w']}" for w in words]
    write_text(os.path.join(base, f"{slug} ASR.txt"), "\n".join(lines) + "\n")

    spans = {}
    for e in sbs:
        hit = find_zh(words, e["zh"], e["tc"])
        tc0, tc1 = e["tc"]
        if hit:
            a, b = hit
            if (b - a) < 5.0 or (b - a) < 0.6 * (tc1 - tc0):
                print(f"  [{e['id']}] ASR 太短 {b-a:.2f}s，改用稿面 TC")
                a, b = tc0, tc1
        else:
            a, b = tc0, tc1
            print(f"  [{e['id']}] ASR 對不齊，用稿面 TC {a:.2f}-{b:.2f}")
        zhl = e.get("zh_lines") or (e["zh"].split("\n") if "\n" in e.get("zh", "") else wrap_caps(e.get("zh", "")))
        caps = [{"text": ln, "end": b} for ln in zhl]
        spans[e["id"]] = {
            "start": round(a, 3), "end": round(b, 3),
            "speaker": e["speaker"], "file": mmap.get(e["num"], src),
            "num": e["num"], "captions": caps, "zh": e["zh"],
            "zh_lines": e.get("zh_lines") or [c["text"] for c in caps],
        }
        print(f"{e['id']}: {a:.2f}-{b:.2f} ({b-a:.2f}s) {e['speaker']}")
    json.dump(spans, open(os.path.join(base, "sb_spans.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return 0


def wrap_caps(zh):
    from sot_common import wrap14
    return wrap14(zh)


if __name__ == "__main__":
    raise SystemExit(main())
