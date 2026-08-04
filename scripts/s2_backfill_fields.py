# -*- coding: utf-8 -*-
"""替既有狀態檔補上結構化欄位（`fields`／`parse_ok`），供 dashboard 使用。

2026-08-04 新增。新收的素材由 `s2_state.new_item()`／`update-entry` 自動推導，
這支是**一次性回填**歷史——不回填的話 dashboard 只有從導入當天起的資料。

⚠️ **只加欄位，不動 `raw_entry`、不動 `category`、不動任何既有欄位**，
所以不影響 render 產出（實測：回填後重跑 render 與原 txt 逐字元一致）。

用法：
  python s2_backfill_fields.py                      # dry-run，只報告解析率
  python s2_backfill_fields.py --apply              # 實際寫入
  python s2_backfill_fields.py --file "…/0803-s2-state.json" --apply
  python s2_backfill_fields.py --show-fail          # 列出解析失敗的原文，供修正解析器
"""
import argparse
import collections
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_parse as sp    # noqa: E402
import s2_state as S     # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

BASE = os.path.dirname(S.DEFAULT_FILE)


def state_files(args):
    if args.file:
        return args.file
    found = sorted(glob.glob(os.path.join(BASE, "*-s2-state.json")) +
                   glob.glob(os.path.join(BASE, "Archive", "**", "*-s2-state.json"),
                             recursive=True))
    return [f for f in found if re.match(r"^\d{4}-s2-state\.json$", os.path.basename(f))]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", action="append", help="指定狀態檔（可重複，省略＝自動找全部）")
    p.add_argument("--apply", action="store_true", help="實際寫入；省略＝只報告")
    p.add_argument("--show-fail", action="store_true", help="列出解析失敗的 raw_entry 原文")
    args = p.parse_args()

    files = state_files(args)
    if not files:
        print("ERROR: 找不到狀態檔，請用 --file 指定")
        sys.exit(2)

    g_ok = g_fail = g_skip = 0
    all_reasons = collections.Counter()
    for f in files:
        st = S.load(f)
        ok = fail = skip = 0
        reasons = collections.Counter()
        fails = []
        for i, v in st["items"].items():
            if sp.skip_reason(v):
                skip += 1
                continue
            sp.derive(v)
            if v.get("parse_ok"):
                ok += 1
            else:
                fail += 1
                reasons[v.get("parse_note", "?")] += 1
                fails.append((i, v.get("raw_entry") or ""))
        tot = ok + fail
        rate = f"{ok * 100 / tot:.1f}%" if tot else "—"
        print(f"■ {os.path.basename(f)}：{tot} 則 → 成功 {ok}／失敗 {fail}（{rate}）"
              f"｜略過 {skip}（側錄／備註殼）")
        for why, n in reasons.most_common():
            print(f"    ✗ {why}：{n} 則")
        if args.show_fail:
            for i, raw in fails:
                print(f"      · {i}: {raw[:110]}")
        if args.apply:
            S.save(st, f)
            print("    → 已寫入")
        g_ok += ok
        g_fail += fail
        g_skip += skip
        all_reasons.update(reasons)

    tot = g_ok + g_fail
    print(f"\n總計 {tot} 則：成功 {g_ok}（{g_ok * 100 / tot:.1f}%）、失敗 {g_fail}、略過 {g_skip}")
    if all_reasons:
        print("失敗原因彙總：")
        for why, n in all_reasons.most_common():
            print(f"  {n:3} 則  {why}")
    if not args.apply:
        print("\n（dry-run，未寫檔）確認無誤後加 --apply 實際寫入。")


if __name__ == "__main__":
    main()
