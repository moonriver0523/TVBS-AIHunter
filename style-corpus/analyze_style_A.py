#!/usr/bin/env python3
"""Step A of the 人味 style study — pure statistical analysis (no LLM reading).

Reads style-corpus/draft_corpus.jsonl (許岱軒's finished TVBS scripts, the
`Draft` field) and produces quantitative style measurements, then compares
them against the current mechanical rules:
  - CTV OS / SB spoken line cap: 14 full-width chars/line
  - CTV BAR card: 16.5–17.5 full-width
  - SOT headline / subheadline: 17.5–18.5 full-width
  - CTV lead (稿頭): target 100–150 chars, must keep 句讀

This does NOT read texts into an LLM — it only computes aggregates and writes
a markdown report. Step B (qualitative voice reading) is separate.

Width counting matches scripts/validate_sot.py::script_width AFTER the P-019
fix: 中文全形 = 1, 半形英數/半形空格 = 0.5.

Usage:
    python analyze_style_A.py
Writes:
    style-corpus/analysis_A_report.md
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
CORPUS = HERE / "draft_corpus.jsonl"
REPORT = HERE / "analysis_A_report.md"

PUNCT = "，。、；：！？"          # 中文句讀（正文斷句字幕理應不含這些）
CJK_RE = re.compile(r"[一-鿿]")


def width(line: str) -> float:
    """Full-width units, matching validate_sot.script_width (P-019: space=0.5)."""
    return sum(1.0 if unicodedata.east_asian_width(ch) in ("F", "W") else 0.5 for ch in line)


# ---- line classification --------------------------------------------------

MARKER_PREFIXES = ("SB", "NS", "SOT", "BAR", "OS", "TVBS", "tvbs", "Q", "Live",
                   "http", "#", "==", "＝＝", "网路標", "網路標", "CG")
FULLWIDTH_DIGITS = "０１２３４５６７８９"


# boilerplate / non-voice lines that must not be counted as narration:
# 版權來源標示、網路標區塊殘留、求助專線、記者署名等。
BOILERPLATE_SUBSTR = ("畫面來源", "來源:", "來源 :", "來源：", "達志影像", "圖達志",
                      "美聯社", "路透社", "網路標", "標示寫圖", "請撥打", "詳細情形",
                      "詳情交給", "TVBS", "記者許岱軒", "許岱軒", "翻攝", "資料畫面",
                      "本新聞", "安心專線", "生命線", "張老師", "求助")


def is_marker_line(ln: str) -> bool:
    s = ln.strip()
    if not s:
        return True
    if any(b in s for b in BOILERPLATE_SUBSTR):
        return True
    if s in ("##", "＃＃", "==CG==", "=CG==", "==", "+", "-", ">"):
        return True
    if s.startswith(("##", "＃＃", "==", "＝＝", ">", "|")):
        return True
    # ruler lines like १２३... or 1234567890...
    if set(s) <= set(FULLWIDTH_DIGITS + "1234567890 "):
        return True
    for p in MARKER_PREFIXES:
        if s.startswith(p + " ") or s == p:
            return True
    # SB/NS marker with speaker + TC on one line: `SB 基輔市民 #04 0037-0044`
    if re.match(r"^(SB|NS|OS|SOT|BAR)\b", s):
        return True
    # a whole-line stage direction wrapped in ( ) / （ ）
    if (s.startswith("(") and s.endswith(")")) or (s.startswith("（") and s.endswith("）")):
        return True
    # material-number / TC only line
    if re.fullmatch(r"[#\d\s\-：:]+", s):
        return True
    # english-only line (SB 英文原句 in some drafts)
    if not CJK_RE.search(s):
        return True
    # `。詳情交給國際中心記者` live handback etc. keep as prose (has 句讀) — fine
    return False


def has_internal_cjk_space(s: str) -> bool:
    """Heuristic for a title line: two CJK halves separated by a space."""
    for m in re.finditer(r"\s+", s):
        i, j = m.start(), m.end()
        if 0 < i and j < len(s) and CJK_RE.search(s[i - 1]) and CJK_RE.search(s[j]):
            return True
    return False


TITLE_PUNCT = set('!"+:.%')


def analyze():
    records = [json.loads(l) for l in CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()]

    n_drafts = len(records)
    lead_chars: list[int] = []
    lead_no_punct = 0
    lead_present = 0

    os_line_widths: list[float] = []       # body prose lines (narration + SB translation)
    os_lines_over_14 = 0
    os_lines_with_punct = 0
    os_total_lines = 0
    # split: clean subtitle-style lines (no 句讀) vs punctuated prose lines
    clean_widths: list[float] = []         # no 句讀 → 直接可比 14 字字幕上限
    clean_over_14 = 0
    punct_widths: list[float] = []         # 有句讀 → 屬草稿散文語體，不直接比字幕上限

    title_widths: list[float] = []
    title_with_bang = 0
    title_with_space = 0
    title_bad_punct = 0

    char_counter: Counter = Counter()
    bigram_counter: Counter = Counter()
    trigram_counter: Counter = Counter()

    # signature connective / rhetoric words worth counting
    SIGNATURE = ["同時", "同一時間", "另一邊", "另外", "然而", "不過", "儘管", "就算",
                 "即使", "一邊", "別人", "如今", "沒想到", "竟然", "甚至", "彷彿",
                 "宛如", "猶如", "無語問蒼天", "但願", "這是", "卻", "更", "而"]
    sig_counter: Counter = Counter()
    drafts_with_sig: Counter = Counter()

    for rec in records:
        draft = rec["draft"]
        # --- lead: text before first `##` line ---
        parts = re.split(r"(?m)^\s*(?:##|＃＃)\s*$", draft, maxsplit=1)
        lead = parts[0].strip()
        # drop placeholder blockquote lines
        lead = "\n".join(ln for ln in lead.splitlines() if ln.strip() not in ("", ">"))
        if lead.strip():
            lead_present += 1
            lc = len(re.sub(r"\s", "", lead))
            lead_chars.append(lc)
            if not any(p in lead for p in PUNCT):
                lead_no_punct += 1

        # --- body / title lines over the whole draft ---
        seen_sig_in_draft = set()
        for ln in draft.splitlines():
            s = ln.strip()
            if not s or is_marker_line(s):
                continue
            # title-like?
            if has_internal_cjk_space(s) and width(s) >= 12:
                w = width(s)
                title_widths.append(w)
                if "!" in s or "！" in s:
                    title_with_bang += 1
                title_with_space += 1
                bad = [c for c in s if not c.isspace()
                       and unicodedata.east_asian_width(c) not in ("F", "W")
                       and not c.isalnum() and c not in TITLE_PUNCT]
                if bad:
                    title_bad_punct += 1
                continue
            # otherwise treat as body OS/SB prose line
            os_total_lines += 1
            w = width(s)
            os_line_widths.append(w)
            if w > 14:
                os_lines_over_14 += 1
            has_punct = any(p in s for p in PUNCT)
            if has_punct:
                os_lines_with_punct += 1
                punct_widths.append(w)
            else:
                clean_widths.append(w)
                if w > 14:
                    clean_over_14 += 1
            # char / n-gram freq over CJK-only
            cjk = "".join(CJK_RE.findall(s))
            char_counter.update(cjk)
            for i in range(len(cjk) - 1):
                bigram_counter[cjk[i:i + 2]] += 1
            for i in range(len(cjk) - 2):
                trigram_counter[cjk[i:i + 3]] += 1
            for sig in SIGNATURE:
                c = s.count(sig)
                if c:
                    sig_counter[sig] += c
                    seen_sig_in_draft.add(sig)
        for sig in seen_sig_in_draft:
            drafts_with_sig[sig] += 1

    def pct(a, b):
        return f"{100*a/b:.1f}%" if b else "n/a"

    def dist(vals):
        if not vals:
            return {}
        v = sorted(vals)
        n = len(v)
        return {
            "n": n, "min": v[0], "max": v[-1],
            "p10": v[int(n*0.10)], "p25": v[int(n*0.25)],
            "median": v[n//2], "p75": v[int(n*0.75)], "p90": v[int(n*0.90)],
            "mean": sum(v)/n,
        }

    lead_d = dist(lead_chars)
    os_d = dist(os_line_widths)
    title_d = dist(title_widths)

    lines = []
    A = lines.append
    A("# 風格研究 · A 步：純統計分析報告")
    A("")
    A("來源：`style-corpus/draft_corpus.jsonl`（許岱軒過去 TVBS 完成稿的 `Draft` 區塊）。")
    A("字寬換算與 `scripts/validate_sot.py::script_width` 一致（P-019 後：中文全形=1、半形英數/半形空格=0.5）。")
    A("本步驟純程式統計，未讓 LLM 讀全文；質性語感分析屬 B 步，另行處理。")
    A("")
    A(f"- 完成稿總數：**{n_drafts}** 篇")
    A(f"- 有稿頭（首個 `##` 之前有內容）：{lead_present} 篇（{pct(lead_present, n_drafts)}）")
    A("")

    A("## 1. 稿頭（主播口播稿）")
    A("")
    A(f"對照現行 CTV 規則：稿頭目標 **100–150 字**（軟性 WARN）、**必須保留中文句讀**。")
    A("")
    if lead_d:
        A(f"- 字數分布（去空白後字元數）：min {lead_d['min']}、p10 {lead_d['p10']}、p25 {lead_d['p25']}、"
          f"**中位數 {lead_d['median']}**、p75 {lead_d['p75']}、p90 {lead_d['p90']}、max {lead_d['max']}、平均 {lead_d['mean']:.0f}")
        in_range = sum(1 for c in lead_chars if 100 <= c <= 150)
        A(f"- 落在 100–150 字區間：{in_range} 篇（{pct(in_range, len(lead_chars))}）")
        A(f"- 短於 100 字：{sum(1 for c in lead_chars if c < 100)} 篇；長於 150 字：{sum(1 for c in lead_chars if c > 150)} 篇")
        A(f"- 稿頭「完全沒有中文句讀」：{lead_no_punct} 篇（{pct(lead_no_punct, len(lead_chars))}）"
          "（比例極低才符合規則預期）")
    A("")

    A("## 2. 正文口白 / SB 中文斷行（OS 語感的核心）")
    A("")
    A(f"對照現行 CTV 規則：正文每行 OS/SB 口白 **上限 14 全形字**、斷行字幕**去除所有標點**。")
    A("（本節把所有非標記、非標題的中文行都算進來，含旁白 OS 與 SB 中文翻譯，兩者同屬短斷行語體。）")
    A("")
    clean_d = dist(clean_widths)
    punct_d = dist(punct_widths)
    if os_d:
        A(f"- 全部正文中文行：{os_total_lines} 行，每行字寬 min {os_d['min']:.1f}、"
          f"中位數 {os_d['median']:.1f}、p75 {os_d['p75']:.1f}、p90 {os_d['p90']:.1f}、平均 {os_d['mean']:.1f}")
        A(f"- 含中文句讀的行：{os_lines_with_punct} 行（{pct(os_lines_with_punct, os_total_lines)}）"
          "——這些是**草稿散文語體**（成句、帶標點），不是最終字幕格式，不直接比 14 字上限。")
        A("")
        A("**關鍵區分**：真正能對照「14 字斷行字幕」規則的，只有『無句讀的乾淨斷行』那一桶：")
        A("")
        if clean_d:
            A(f"- 乾淨斷行（無句讀）：{clean_d['n']} 行，字寬 min {clean_d['min']:.1f}、p10 {clean_d['p10']:.1f}、"
              f"p25 {clean_d['p25']:.1f}、**中位數 {clean_d['median']:.1f}**、p75 {clean_d['p75']:.1f}、"
              f"p90 {clean_d['p90']:.1f}、平均 {clean_d['mean']:.1f}")
            A(f"- **乾淨斷行超過 14 全形字：{clean_over_14} 行（{pct(clean_over_14, clean_d['n'])}）**"
              "——這才是人稿斷行習慣與現行 14 字上限的真實落差。")
        if punct_d:
            A(f"- 帶句讀散文行：{punct_d['n']} 行，字寬中位數 {punct_d['median']:.1f}、p90 {punct_d['p90']:.1f}、平均 {punct_d['mean']:.1f}"
              "（草稿常直接寫成完整句，之後才在剪接階段拆成字幕）")
    A("")

    A("## 3. 標題 / 網路標（近似偵測：含內部空格的兩段式中文行）")
    A("")
    A(f"對照現行規則：CTV BAR **16.5–17.5**、SOT 主標/次標 **17.5–18.5**；標題可用半形標點只准 `! \" + : . %`。")
    A("（此為近似值：以『有內部空格且 ≥12 全形字』的中文行當標題候選，可能混入少量非標題行。）")
    A("")
    if title_d:
        A(f"- 標題候選數：{title_d['n']}")
        A(f"- 字寬分布：min {title_d['min']:.1f}、p10 {title_d['p10']:.1f}、p25 {title_d['p25']:.1f}、"
          f"**中位數 {title_d['median']:.1f}**、p75 {title_d['p75']:.1f}、p90 {title_d['p90']:.1f}、max {title_d['max']:.1f}、平均 {title_d['mean']:.1f}")
        in_bar = sum(1 for w in title_widths if 16.5 <= w <= 17.5)
        in_sot = sum(1 for w in title_widths if 17.5 <= w <= 18.5)
        A(f"- 落在 BAR 區間 16.5–17.5：{in_bar}（{pct(in_bar, len(title_widths))}）")
        A(f"- 落在 SOT 區間 17.5–18.5：{in_sot}（{pct(in_sot, len(title_widths))}）")
        A(f"- 用了 `!`／`！` 的標題：{title_with_bang}（{pct(title_with_bang, len(title_widths))}）"
          "（人稿標題愛用驚嘆號的程度）")
        A(f"- 含白名單以外半形標點的標題：{title_bad_punct}（{pct(title_bad_punct, len(title_widths))}）")
    A("")

    A("## 4. 高頻字 / 詞組（字元 n-gram，無斷詞）")
    A("")
    A("以正文斷行的中文字元計算（未用 jieba 斷詞，改用字元 bigram/trigram 逼近常見語詞）。")
    A("")
    A("**最高頻單字（前 30）**：")
    A("｜".join(f"{c}({n})" for c, n in char_counter.most_common(30)))
    A("")
    A("**最高頻二字組（前 40）**：")
    A("｜".join(f"{g}({n})" for g, n in bigram_counter.most_common(40)))
    A("")
    A("**最高頻三字組（前 30）**：")
    A("｜".join(f"{g}({n})" for g, n in trigram_counter.most_common(30)))
    A("")

    A("## 5. 標誌性連接／修辭詞出現次數")
    A("")
    A("（手選一組能反映『人味』的轉場/對比/情緒詞，計總出現次數與出現於幾篇稿。）")
    A("")
    A("| 詞 | 總次數 | 出現篇數 | 出現率 |")
    A("|---|---|---|---|")
    for sig in sorted(sig_counter, key=lambda s: -sig_counter[s]):
        A(f"| {sig} | {sig_counter[sig]} | {drafts_with_sig[sig]} | {pct(drafts_with_sig[sig], n_drafts)} |")
    A("")

    A("---")
    A("")
    A("> A 步只給量化骨架。語感、節奏、對比句法、稿頭到收尾的敘事手法等質性層面，")
    A("> 需要 B 步抽樣讀全文才能捕捉——本報告刻意不下風格結論，留給 B 步與最終風格指南。")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written to {REPORT}")
    print(f"drafts={n_drafts} lead_present={lead_present} os_lines={os_total_lines} "
          f"os_over14={os_lines_over_14} titles={len(title_widths)}")


if __name__ == "__main__":
    analyze()
