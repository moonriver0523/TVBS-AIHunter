# -*- coding: utf-8 -*-
"""S2 晚班交接品質掃／檔頭統計／三方比對腳本（V2）。

用法：
  python s2_validate.py check <晚班交接.txt>       格式異常掃描
  python s2_validate.py stats <晚班交接.txt> [--window "16:00 - 23:00"]
                                                   輸出檔頭兩行
  python s2_validate.py diff3 <現行.txt> <機器版快照.txt>
                                                   列出人工編輯過的行

規則依據 common/13-S2-定時掃帶.md「最終整併：稿未到清查＋品質掃」。
"""
import argparse
import difflib
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 素材代碼（行首）：RT#### / AP####### / APcctv###### / CNN Newsource XX-##XX / 側錄 CNN|NHK ######
CODE = r"(?:RT\d{4}|APcctv\d{6}|AP\d{7}|[A-Z]{2}-\d{1,3}[A-Z]{2}|(?:CNN|NHK) \d{6})"
LINE_RE = re.compile(rf"^{CODE}(?:\s*/\s*{CODE})*\s")


def read(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read().splitlines()
    except OSError as e:
        print(f"ERROR: 檔案讀取失敗（{e}）。請確認路徑後重跑，不要手動掃。")
        sys.exit(2)


def material_lines(lines):
    return [(n, l) for n, l in enumerate(lines, 1) if LINE_RE.match(l)]


def check(path):
    lines = read(path)
    hits = []

    def hit(n, reason):
        hits.append((n, reason))

    seen_codes = {}
    for n, l in material_lines(lines):
        codes = re.findall(CODE, l.split("▎")[0])
        for c in codes:
            seen_codes.setdefault(c, []).append(n)

        has_bite_tag = "(BITE)" in l
        has_bite_seg = "▎BITE：" in l or "▎BITE:" in l
        has_nobite = "無BITE" in l

        if has_bite_tag and has_nobite:
            hit(n, "(BITE) 與 無BITE 矛盾")
        if has_bite_seg and not has_bite_tag:
            hit(n, "有 ▎BITE： 但缺 (BITE) 第二括號")
        if has_bite_tag and not has_bite_seg:
            hit(n, "有 (BITE) 但缺 ▎BITE： 段")
        if "▎畫面：" not in l and "▎畫面:" not in l:
            hit(n, "缺 ▎畫面： 段")
        if not has_bite_seg and not has_nobite:
            hit(n, "結尾既非 無BITE 也無 BITE： 段")

        m = re.match(rf"^{CODE}(?:\s*/\s*{CODE})*\s+\(([^)]*)\)", l)
        first_note = m.group(1) if m else ""
        if re.search(r"(?<![A-Za-z])BITE(?![A-Za-z])", first_note):
            hit(n, "第一備註寫了 BITE")
        if re.search(r"(?<![A-Za-z])(FILE|File)(?![A-Za-z])", first_note) or "檔案" in first_note:
            hit(n, "備註用 FILE/檔案（應為 資料畫面）")
        parens = re.findall(r"\(([^)]*)\)", l.split("▎")[0])
        if len(parens) >= 2 and parens[1].strip() != "BITE":
            hit(n, f"第二括號不是 (BITE)：({parens[1]})")
        if "GMT" in l:
            hit(n, "素材行出現 GMT")
        for bad in ("（列表摘要）", "（詳情頁待補）", "（急用請開Shotlist）",
                    "（script待補）", "（完整script待補）", "（early", "（待完整稿）"):
            if bad in l:
                hit(n, f"操作/狀態備註寫進素材行：{bad}")
        if re.search(r"▎BITE[：:]\s*「", l):
            hit(n, "▎BITE：無講者（引號前必須有講者）")
        wrap_note = "整理包" in first_note
        if re.search(r"(?<![A-Za-z])WRAP(?![A-Za-z])", l) and not wrap_note:
            hit(n, "出現 WRAP 但備註未標 整理包")

    for c, ns in seen_codes.items():
        if len(ns) > 1:
            hit(ns[-1], f"重複代碼 {c}（另見行 {ns[:-1]}）")

    hits.sort()
    if not hits:
        print("OK 品質掃 0 命中")
    else:
        print(f"HIT {len(hits)} 項，逐項回站核對後修正：")
        for n, r in hits:
            print(f"  行{n}: {r}")


def stats(path, window):
    lines = read(path)
    counts = {"AP": 0, "RT": 0, "NS": 0, "其他": 0}
    for _, l in material_lines(lines):
        first = re.match(CODE, l).group(0)
        if first.startswith(("AP", "APcctv")):
            counts["AP"] += 1
        elif first.startswith("RT"):
            counts["RT"] += 1
        elif re.match(r"[A-Z]{2}-\d", first):
            counts["NS"] += 1
        else:
            counts["其他"] += 1
    total = sum(counts.values())
    if window:
        try:
            s, e = [x.strip() for x in window.split("-")]
            h = (int(e[:2]) * 60 + int(e[3:5]) - int(s[:2]) * 60 - int(s[3:5])) / 60
            print(f"已完成掃帶時段 {s} - {e}（約{h:g}hrs）")
        except (ValueError, IndexError):
            print(f"已完成掃帶時段 {window}")
    parts = [f"AP {counts['AP']}則", f"RT {counts['RT']}則", f"NS {counts['NS']}則"]
    if counts["其他"]:
        parts.append(f"其他 {counts['其他']}則")
    print(f"收錄外電共{total}則（{'／'.join(parts)}）")


def diff3(cur_path, snap_path):
    cur, snap = read(cur_path), read(snap_path)
    edited = [l for l in difflib.unified_diff(snap, cur, lineterm="", n=0)
              if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    if not edited:
        print("OK 無人工編輯，整併可直接以機器版為底")
    else:
        print(f"人工編輯 {len(edited)} 行（-為快照原文、+為現行；整併時保留人工版）：")
        for l in edited:
            print("  " + l)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("path")
    s = sub.add_parser("stats")
    s.add_argument("path")
    s.add_argument("--window", default="")
    d = sub.add_parser("diff3")
    d.add_argument("current")
    d.add_argument("snapshot")
    args = p.parse_args()
    if args.cmd == "check":
        check(args.path)
    elif args.cmd == "stats":
        stats(args.path, args.window)
    else:
        diff3(args.current, args.snapshot)


if __name__ == "__main__":
    main()
