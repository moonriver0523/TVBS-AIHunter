# -*- coding: utf-8 -*-
"""步驟 1／4 — 轉譯素材、把完成文稿的每段 SB 對到精確的起訖秒數。

輸出（都放在 --outdir）：
  {SLUG} ASR.txt   段落級逐字稿（給人看、上傳用）
  asr_words.json   詞級時間戳（剪接切點與 SB 字幕錨詞都用它）
  sb_spans.json    每段 SB 的精確起訖 + 中文字幕的錨點

用法：
  python locate_sb.py --script "{SLUG} 完成文稿.txt" --source "{SLUG}.mp4"

⚠️ 邊界來自 ASR 詞級時間戳時，剪接**直接切**、不可再做 VAD 二次裁（09 B3）。
"""
import argparse
import json
import os

from ctv_common import (han_len, load_script, norm_word, parse_tc, run,
                        slug_from_script, write_text)

ASR_MODEL = os.environ.get(
    "FW_MODEL", r"E:\GitHub\GPT-SoVITS\tools\asr\models\faster-whisper-large-v3")


def mmss(t):
    return "%02d:%02d" % (int(t) // 60, int(t) % 60)


def transcribe(source, outdir, slug, lang):
    wav = os.path.join(outdir, "source16k.wav")
    if not os.path.exists(wav):
        run(["ffmpeg", "-y", "-v", "error", "-i", source, "-vn",
             "-ac", "1", "-ar", "16000", wav])
    from faster_whisper import WhisperModel
    model = WhisperModel(ASR_MODEL, device="cuda", compute_type="float16")
    segs, _ = model.transcribe(wav, language=lang, word_timestamps=True,
                               vad_filter=False, beam_size=5)
    lines, words = [], []
    for s in segs:
        lines.append("%s - %s  %s" % (mmss(s.start), mmss(s.end), s.text.strip()))
        for w in (s.words or []):
            words.append({"w": w.word, "s": round(w.start, 3), "e": round(w.end, 3)})
    write_text(os.path.join(outdir, f"{slug} ASR.txt"), "\n".join(lines) + "\n")
    json.dump(words, open(os.path.join(outdir, "asr_words.json"), "w",
                          encoding="utf-8"), ensure_ascii=False)
    return words


def find_span(words, english, tc, slack=6.0, min_ratio=0.5):
    """在 TC 附近找出這句英文原句的詞級起訖。

    做法是**在 TC 範圍內逐一嘗試起點、取對得最好的那個**，不是硬比句首／句末
    幾個詞——專有名詞（藥名、人名）常被 ASR 聽錯（`Daraxonrasib` → `Durexanracib`），
    寫死錨詞會整句找不到。對不上的頭尾 token 依數量往外補相同數量的詞。

    ⚠️ 句首那個詞若本身沒對上（就是被聽錯的專有名詞），它的 ASR 起始時間會偏晚，
    切下去會把字頭削掉；此時往前補「前一個詞到它之間空檔的一半」（上限 0.6 秒）。
    """
    toks = [norm_word(t) for t in english.split() if norm_word(t)]
    norm = [norm_word(w["w"]) for w in words]
    lo, hi = tc[0] - slack, tc[1] + slack

    best = None
    for i in range(len(norm)):
        if not (lo <= words[i]["s"] <= hi):
            continue
        # 由 i 開始逐詞貪婪對齊：對得上就兩邊前進，對不上就跳過該 token
        # （ASR 聽錯的詞）；連續 4 個 token 都對不上就放棄這個起點。
        ti = j = hits = miss = 0
        first_tok = first_word = last_tok = last_word = None
        j = i
        while j < len(norm) and ti < len(toks) and miss < 4:
            if norm[j] == toks[ti]:
                if first_tok is None:
                    first_tok, first_word = ti, j
                last_tok, last_word = ti, j
                hits += 1
                miss = 0
                ti += 1
                j += 1
            else:
                # 官方稿與 ASR 兩邊都可能多出東西：ASR 會多聽到贅詞
                # （"you know"），官方稿也可能有 ASR 沒聽出來的詞。先往前
                # 找 3 個詞看這個 token 是不是稍後才出現，找不到才跳過 token。
                ahead = [k for k in range(j + 1, min(j + 4, len(norm)))
                         if norm[k] == toks[ti]]
                if ahead:
                    j = ahead[0]
                else:
                    ti += 1
                    miss += 1
        if first_tok is None:
            continue
        ratio = hits / len(toks)
        cand = (ratio, -i, first_tok, first_word, last_tok, last_word)
        if best is None or cand[:2] > best[:2]:
            best = cand
    if best is None or best[0] < min_ratio:
        return None

    ratio, _, first_tok, first_word, last_tok, last_word = best
    wi = max(0, first_word - first_tok)          # 句首沒對上的詞往前補
    wj = min(len(words) - 1, last_word + (len(toks) - 1 - last_tok))
    start = words[wi]["s"]
    if first_tok > 0:                            # 起點那個詞是被聽錯的專有名詞
        prev_end = words[wi - 1]["e"] if wi else 0.0
        start -= min(0.6, max(0.0, (start - prev_end) * 0.5))
    return {"start": round(start, 3), "end": words[wj]["e"],
            "wi": wi, "wj": wj, "match": round(ratio, 2)}


def caption_anchors(words, wi, wj, zh_lines):
    """把中文字幕行按字數比例分配到英文詞上，邊界一律落在**詞的結尾**。

    這樣受訪者句中的自然停頓會被併進前一行，不會出現一整條字幕壓在空拍上
    （production/03）。需要更精準時用 --anchors 手動指定。
    """
    n = wj - wi + 1
    weights = [max(1, han_len(l)) for l in zh_lines]
    total = sum(weights)
    out, used = [], 0
    for k, w in enumerate(weights):
        if k == len(weights) - 1:
            take = n - used
        else:
            take = max(1, round(n * w / total))
            take = min(take, n - used - (len(weights) - k - 1))
        used += take
        out.append({"text": zh_lines[k],
                    "end": words[wi + used - 1]["e"]})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True, help="{SLUG} 完成文稿.txt")
    ap.add_argument("--source", required=True, help="素材 mp4")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--lang", default="en", help="素材語言（預設 en）")
    ap.add_argument("--anchors", default=None,
                    help="手動錨詞 JSON：{\"sb1\": [\"bedtime\", \"of\", null], …}")
    args = ap.parse_args()

    outdir = args.outdir or os.path.dirname(os.path.abspath(args.script))
    os.makedirs(outdir, exist_ok=True)
    slug = slug_from_script(args.script)
    _, blocks = load_script(args.script)

    words_path = os.path.join(outdir, "asr_words.json")
    if os.path.exists(words_path):
        words = json.load(open(words_path, encoding="utf-8"))
        print("沿用既有 asr_words.json（同一支片不重跑轉譯）")
    else:
        words = transcribe(args.source, outdir, slug, args.lang)

    manual = json.load(open(args.anchors, encoding="utf-8")) if args.anchors else {}
    spans, n = {}, 0
    for b in blocks:
        if not b["sb"]:
            continue
        n += 1
        sid = f"sb{n}"
        sb = b["sb"]
        got = find_span(words, sb["english"], parse_tc(sb["tc"]))
        if not got:
            raise SystemExit(f"{sid}：在 ASR 裡找不到這句英文原句，請確認 TC 或原句：{sb['english'][:60]}")
        if sid in manual:
            caps = []
            for text, anchor in zip(sb["zh_lines"], manual[sid]):
                if anchor is None:
                    caps.append({"text": text, "end": got["end"]})
                    continue
                w = next(w for w in words
                         if norm_word(w["w"]) == norm_word(anchor)
                         and got["start"] <= w["s"] <= got["end"] + 0.5)
                caps.append({"text": text, "end": w["e"]})
        else:
            caps = caption_anchors(words, got["wi"], got["wj"], sb["zh_lines"])
        spans[sid] = {"speaker": sb["speaker"], "tc": sb["tc"],
                      "start": got["start"], "end": got["end"], "captions": caps}
        print(f"{sid} {sb['speaker']}｜{got['start']:.2f}-{got['end']:.2f} "
              f"({got['end'] - got['start']:.2f}s)  文稿 TC={sb['tc']}")

    json.dump(spans, open(os.path.join(outdir, "sb_spans.json"), "w",
                          encoding="utf-8"), ensure_ascii=False, indent=2)
    print("寫出 sb_spans.json")


if __name__ == "__main__":
    main()
