# -*- coding: utf-8 -*-
"""步驟 2／4 — OS 配音（GPT-SoVITS 本人聲音）。規則見 production/01。

守住的硬約束：
  * 2–3 行一組（逐句品質差、整段會跳句）
  * int16 修正 + 峰值 0.8 正規化，輸出前驗 clip% = 0（09 A1）
  * 組尾接犧牲字 `。嗯。` 再依 ASR 詞級對齊切掉（09 A5）
  * **組首裁到第一個辨識詞之前**（09 A7）
  * 覆蓋率 <0.80 或**出現無詞覆蓋的雜訊**就換 seed（09 A7）
  * 覆蓋率比對前先繁→簡正規化，`著`→`着`（09 A8）

用法：
  python synth_os.py --script "{SLUG} 完成文稿.txt" [--only os3]
"""
import argparse
import json
import os
import re
import sys

import numpy as np
import soundfile as sf

from ctv_common import group_os_lines, load_script

GPT_SOVITS = os.environ.get("GPT_SOVITS_DIR", r"E:\GitHub\GPT-SoVITS")
SR = 32000
GAP, LEAD, TAILPAD = 0.12, 0.15, 0.35
SEEDS = [42, 1042, 2042, 7, 123, 888, 3407, 9999]
COVER_OK = 0.80
JUNK_MIN, JUNK_RMS, WORD_PAD = 0.6, 0.02, 0.15


def build_argparser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True)
    ap.add_argument("--outdir", default=None, help="預設為完成文稿所在目錄下的 os/")
    ap.add_argument("--only", default="", help="只重配某幾段，例：os3 或 os3,os4")
    ap.add_argument("--ref", default=r"D:\voice-training\os_segments\os_0169.wav")
    ap.add_argument("--list", dest="listfile",
                    default=r"D:\voice-training\work\os_segments.list")
    ap.add_argument("--gpt", default=os.path.join(
        GPT_SOVITS, r"GPT_weights_v2\os_voice3-e12.ckpt"))
    ap.add_argument("--sovits", default=os.path.join(
        GPT_SOVITS, r"SoVITS_weights_v2\os_voice3_e8_s1064.pth"))
    ap.add_argument("--asr-model", default=os.environ.get(
        "FW_MODEL", os.path.join(GPT_SOVITS, r"tools\asr\models\faster-whisper-large-v3")))
    ap.add_argument("--dry-run", action="store_true",
                    help="只印出分組結果，不呼叫 TTS")
    return ap


def han(s, _t2s=[None]):
    import cn2an
    if _t2s[0] is None:
        import opencc
        _t2s[0] = opencc.OpenCC("t2s")
    try:
        s = cn2an.transform(s, "an2cn")
    except Exception:
        pass
    # 還/还、著/着 的預設讀音不同，不正規化會讓對的句子算成沒唸到（09 A8）
    return re.sub(r"[^\u4e00-\u9fff]", "", _t2s[0].convert(s).replace("著", "着"))


def junk_spans(y, words, hop=0.05):
    """有聲音、卻沒有任何辨識詞覆蓋的區段 —— 模型多唸出來的東西（09 A7）。"""
    dur = len(y) / SR
    if not words:
        return [(0.0, dur)] if dur > JUNK_MIN else []
    covered = np.zeros(int(dur / hop) + 1, bool)
    for a, b, _ in words:
        covered[max(0, int((a - WORD_PAD) / hop)):int((b + WORD_PAD) / hop) + 1] = True
    out, i, n = [], 0, len(covered)
    while i < n:
        if covered[i]:
            i += 1
            continue
        j = i
        while j < n and not covered[j]:
            j += 1
        a, b = i * hop, min(j * hop, dur)
        if b - a >= JUNK_MIN:
            seg = y[int(a * SR):int(b * SR)]
            if len(seg) and float(np.sqrt(np.mean(seg ** 2))) > JUNK_RMS:
                out.append((a, b))
        i = j
    return out


def main():
    args = build_argparser().parse_args()
    base = os.path.dirname(os.path.abspath(args.script))
    outdir = args.outdir or os.path.join(base, "os")
    os.makedirs(outdir, exist_ok=True)
    _, blocks = load_script(args.script)
    groups_by_block = {f"os{b['bar']}": group_os_lines(b["os"]) for b in blocks}

    only = [b for b in args.only.split(",") if b]
    for blk, groups in groups_by_block.items():
        print(f"{blk}: {sum(len(g) for g in groups)} 行 / {len(groups)} 組")
        for gi, g in enumerate(groups):
            print(f"   g{gi}: " + " ｜ ".join(g))
    if args.dry_run:
        return 0

    os.chdir(GPT_SOVITS)
    sys.path.insert(0, GPT_SOVITS)
    sys.path.insert(0, os.path.join(GPT_SOVITS, "GPT_SoVITS"))
    from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config
    from faster_whisper import WhisperModel
    from pypinyin import lazy_pinyin
    import librosa

    prompt_text = ""
    ref_name = os.path.basename(args.ref)
    with open(args.listfile, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("|", 3)
            if len(p) == 4 and os.path.basename(p[0]) == ref_name:
                prompt_text = p[3]
                break

    cfg = TTS_Config("GPT_SoVITS/configs/tts_infer.yaml")
    cfg.device, cfg.is_half, cfg.version = "cuda", True, "v2"
    cfg.t2s_weights_path, cfg.vits_weights_path = args.gpt, args.sovits
    tts = TTS(cfg)
    asr = WhisperModel(args.asr_model, device="cuda", compute_type="float16")

    def synth(text, seed):
        inputs = {"text": text, "text_lang": "zh", "ref_audio_path": args.ref,
                  "prompt_text": prompt_text, "prompt_lang": "zh",
                  "top_k": 15, "top_p": 1.0, "temperature": 1.0,
                  "text_split_method": "cut0", "batch_size": 1,
                  "speed_factor": 1.0, "seed": seed}
        sr = audio = None
        for sr, audio in tts.run(inputs):
            pass
        y = np.asarray(audio, dtype=np.float32)
        if np.max(np.abs(y)) > 2.0:      # tts.run() 回 int16 範圍（09 A1）
            y = y / 32768.0
        if sr != SR:
            y = librosa.resample(y, orig_sr=sr, target_sr=SR)
        return y

    def asr_words(wav):
        tmp = os.path.join(outdir, "_grp.wav")
        sf.write(tmp, wav, SR)
        segs, _ = asr.transcribe(tmp, language="zh", word_timestamps=True, beam_size=5)
        out = []
        for s in segs:
            for w in (s.words or []):
                t = han(w.word)
                if t:
                    out.append((w.start, w.end, t))
        return out

    def coverage(lines, words):
        got = lazy_pinyin("".join(w[2] for w in words))
        covs = []
        for ln in lines:
            seq = lazy_pinyin(han(ln))
            i = hit = 0
            for p in got:
                if i < len(seq) and p == seq[i]:
                    hit += 1
                    i += 1
            covs.append(hit / max(1, len(seq)))
        return covs

    tpath = os.path.join(outdir, "os_timings.json")
    timings = {}
    if only and os.path.exists(tpath):
        timings = json.load(open(tpath, encoding="utf-8"))
    report, junk_report = {}, []

    for blk, groups in groups_by_block.items():
        if only and blk not in only:
            continue
        parts = [np.zeros(int(LEAD * SR), np.float32)]
        cur, cues, weak_lines = LEAD, [], []
        for gi, lines in enumerate(groups):
            gtext = "，".join(lines) + "。嗯。"          # 犧牲字（09 A5）
            real_chars = sum(len(han(l)) for l in lines)
            best = None
            for seed in SEEDS:
                y = synth(gtext, seed)
                _, idx = librosa.effects.trim(y, top_db=45)
                y = y[max(0, idx[0] - int(0.05 * SR)):min(len(y), idx[1] + int(0.15 * SR))]
                w = asr_words(y)
                if w:                                   # 組首雜訊（09 A7）
                    head = max(0.0, w[0][0] - 0.12)
                    if head > 0.05:
                        y = y[int(head * SR):]
                        w = [(a - head, b - head, t) for a, b, t in w]
                covs = coverage(lines, w)
                junk = junk_spans(y, w)
                score = (min(covs), -sum(b - a for a, b in junk))
                if best is None or score > best[0]:
                    best = (score, y, w, covs, junk)
                if score[0] >= COVER_OK and not junk:
                    break
                msg = "; ".join(f"{l}({c:.2f})" for l, c in zip(lines, covs)
                                if c < COVER_OK)
                if junk:
                    msg += " junk=" + str([(round(a, 2), round(b, 2)) for a, b in junk])
                print(f"  [{blk} g{gi} seed={seed}] weak {msg}")
            score, y, w, covs, junk = best
            if score[0] < COVER_OK:
                weak_lines += [l for l, c in zip(lines, covs) if c < COVER_OK]
            if junk:
                junk_report.append([blk, gi, [(round(a, 2), round(b, 2)) for a, b in junk]])
            acc, last_real_end, wj = 0, None, 0
            while wj < len(w) and acc < real_chars:
                last_real_end = w[wj][1]
                acc += len(w[wj][2])
                wj += 1
            if last_real_end is not None and acc >= real_chars:
                y = y[:min(len(y), int((last_real_end + 0.12) * SR))]
            gdur = len(y) / SR
            wi = 0
            for ln in lines:
                need = len(han(ln))
                if wi < len(w):
                    st = en = w[wi][0]
                    acc = 0
                    while wi < len(w) and acc < need:
                        en = w[wi][1]
                        acc += len(w[wi][2])
                        wi += 1
                    en = min(en, gdur)
                else:
                    st = (cues[-1][1] - cur) if cues else 0.0
                    en = gdur
                cues.append([cur + st, cur + en, ln])
            parts += [y, np.zeros(int(GAP * SR), np.float32)]
            cur += gdur + GAP
        parts.append(np.zeros(int(TAILPAD * SR), np.float32))
        block = np.concatenate(parts)
        block = block / (float(np.max(np.abs(block))) or 1.0) * 0.8
        dur = len(block) / SR
        for i in range(len(cues)):
            nxt = cues[i + 1][0] if i + 1 < len(cues) else dur
            cues[i][1] = min(cues[i][1] + 0.15, nxt)
        cues[-1][1] = dur
        silent = [ln for a, b, ln in cues
                  if b - a <= 0 or float(np.sqrt(np.mean(
                      block[int(a * SR):int(b * SR)] ** 2))) < 0.02]
        clip = float(np.mean(np.abs(block) > 0.99))
        sf.write(os.path.join(outdir, blk + ".wav"), block, SR)
        timings[blk] = {"dur": round(dur, 3),
                        "lines": [{"text": l, "start": round(a, 3), "end": round(b, 3)}
                                  for a, b, l in cues]}
        report[blk] = {"weak": weak_lines, "silent": silent,
                       "dur": round(dur, 2), "clip_pct": clip}
        print(f"{blk}: {dur:.2f}s weak={len(weak_lines)} silent={len(silent)} clip%={clip}")

    json.dump(timings, open(tpath, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\nREPORT:", json.dumps(report, ensure_ascii=False))
    print("JUNK:", json.dumps(junk_report, ensure_ascii=False))
    print("TOTAL OS:", round(sum(v["dur"] for v in timings.values()), 2), "s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
