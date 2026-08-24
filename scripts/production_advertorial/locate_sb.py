# -*- coding: utf-8 -*-
"""業配 SB 定位：只轉訪問段、中文對齊。路線 B：ASR 詞級後直接切、不再 VAD。

**09 A9（2026-08-24 加）**：舊版 find_zh 抓到起點後，是「從 pos 起連續切 len(target)
個字」，沒有驗證這段字真的等於 target——受訪者若在核定逐字稿中間夾雜贅語／口頭禪
（花蓮暑假2400 案例：「…大概一萬多人[的平均，這樣的數字]那不只是…」），切出來的
(a,b) 會混進贅語卻沒有任何檢查攔下來。現在 locate 完會用 difflib 逐字比對，只要有
連續 SB_INSERT_TOL_HAN 個字以上「講了但稿子沒有」，就印出 [SB對不準] 警告並列出正
確的分段時間點，供人工/下游決定要不要拆成多段剪掉贅語。"""
import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sot_common import load_material_map, load_script, run, slug_from_script, write_text

SB_INSERT_TOL_HAN = 4

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


def verify_span(words, a, b, target_zh):
    """核對 (a,b) 這段實際講的話跟核定逐字稿——回傳 [(start,end,extra_text), ...] 插入片段。"""
    target = han(target_zh)
    heard_words = [w for w in words if a <= w["s"] <= b]
    if not target or not heard_words:
        return []
    heard = "".join(w["w"] for w in heard_words)
    sm = difflib.SequenceMatcher(None, target, heard, autojunk=False)
    gaps = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag not in ("insert", "replace") or (j2 - j1) < SB_INSERT_TOL_HAN:
            continue
        gap_start = heard_words[j1 - 1]["e"] if j1 > 0 else a
        gap_end = heard_words[j2]["s"] if j2 < len(heard_words) else b
        gaps.append((round(gap_start, 3), round(gap_end, 3), heard[j1:j2]))
    return gaps


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
        gaps = verify_span(words, a, b, e.get("zh_lines") or e["zh"])
        spans[e["id"]] = {
            "start": round(a, 3), "end": round(b, 3),
            "speaker": e["speaker"], "file": mmap.get(e["num"], src),
            "num": e["num"], "captions": caps, "zh": e["zh"],
            "zh_lines": e.get("zh_lines") or [c["text"] for c in caps],
        }
        if gaps:
            spans[e["id"]]["extra_speech"] = gaps
            print(f"{e['id']}: {a:.2f}-{b:.2f} ({b-a:.2f}s) {e['speaker']}")
            print(f"  [SB對不準] 混入未核定內容，共 {len(gaps)} 段：")
            for gs, ge, text in gaps:
                print(f"    {gs:.2f}-{ge:.2f}s 講了「{text}」——稿子裡沒有，剪片前要挖掉這段")
        else:
            print(f"{e['id']}: {a:.2f}-{b:.2f} ({b-a:.2f}s) {e['speaker']} [對齊OK]")
    json.dump(spans, open(os.path.join(base, "sb_spans.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    bad = any(spans[e["id"]].get("extra_speech") for e in sbs)
    print("\n" + ("[FAIL] SB混入未核定內容，先挖掉贅語再繼續" if bad else "[PASS] SB定位全對齊"))
    return 1 if bad else 0


def wrap_caps(zh):
    from sot_common import wrap14
    return wrap14(zh)


if __name__ == "__main__":
    raise SystemExit(main())
