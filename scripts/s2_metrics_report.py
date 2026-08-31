#!/usr/bin/env python3
"""S2 遙測趨勢報表（MASTER A1，2026-08-17）——唯讀，只讀 `_token_metrics.jsonl`。

驗收標準寫在 MASTER A1：**報表要能解釋任一輪多出的呼叫去了哪裡**。
所以主力是 `--diff`：兩輪逐桶相減、依差距排序，一眼看出多出來的呼叫落在
哪個工具、哪個階段，不用再手工爬 transcript。

用法：
    python s2_metrics_report.py                      # 最近 10 輪總表
    python s2_metrics_report.py --last 20
    python s2_metrics_report.py --diff 0817-0730 0817-1200   # 兩輪逐桶相減
    python s2_metrics_report.py --tool "python -c"   # 單一工具跨輪趨勢
    python s2_metrics_report.py --rules              # 規則版本何時變動

離開碼：0＝正常；2＝讀不到遙測檔或指定的輪次不存在（**不是**「沒有差異」）。
"""
import argparse
import json
import os
import sys

# ⚠️ 2026-08-31 補（全流程 locale 編碼稽核）：`cmd_diff()` 在兩輪 rule sha 不同時
# 會印 `⚠️`，cp950 不可編碼 → stdout 是管線就丟 UnicodeEncodeError。`--diff` 正是
# MASTER A1 的驗收功能本身，而且只在「規則有變」那次才炸，看起來像偶發。
# 用 reconfigure 不用 TextIOWrapper（WP1 2026-08-03 實錯：雙層包覆會
# "I/O operation on closed file"）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # py<3.7
        pass

METRICS_FILE = (
    r'G:\我的雲端硬碟\Claude共用\自動掃帶系統\S2掃帶log\_token_metrics.jsonl'
)
METRICS_FILE_FALLBACK = r'D:\Downloads\S2掃帶log\_token_metrics.jsonl'


def load(path=None):
    """讀遙測檔。找不到就明確失敗，不回空清單——空清單會讓每張報表都變成
    「一切正常，沒有資料」，那是假綠燈。"""
    candidates = [path] if path else [METRICS_FILE, METRICS_FILE_FALLBACK]
    for p in candidates:
        if p and os.path.exists(p):
            rows = []
            with open(p, encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(f'警告：{os.path.basename(p)} 第 {i} 行不是 JSON，'
                              f'略過（{e}）', file=sys.stderr)
            if not rows:
                print(f'✗ {p} 裡沒有任何可用紀錄', file=sys.stderr)
                sys.exit(2)
            return rows, p
    print(f'✗ 找不到遙測檔：{" 或 ".join(str(c) for c in candidates)}', file=sys.stderr)
    sys.exit(2)


def pick(rows, checkpoint):
    """同一個 checkpoint 可能被量測多次（補跑、事後重記），取最後一筆。"""
    hits = [r for r in rows if r.get('checkpoint') == checkpoint]
    if not hits:
        avail = ', '.join(r.get('checkpoint', '?') for r in rows[-12:])
        print(f'✗ 找不到輪次 {checkpoint}。最近有的是：{avail}', file=sys.stderr)
        sys.exit(2)
    return hits[-1]


def fmt_k(n):
    if n is None:
        return '-'
    if n >= 1_000_000:
        return f'{n / 1_000_000:.1f}M'
    if n >= 1_000:
        return f'{n / 1_000:.0f}k'
    return str(n)


def cmd_table(rows, args):
    rows = rows[-args.last:]
    print(f'{"輪次":<14}{"呼叫":>5}{"請求":>5}{"cache讀":>8}{"輸出":>7}'
          f'{"每呼叫":>8}  階段（分）')
    print('-' * 88)
    for r in rows:
        ph = r.get('phases') or {}
        phtxt = ' '.join(f'{k}{v["minutes"]:g}' for k, v in ph.items()) or '（無分段）'
        print(f'{r.get("checkpoint", "?"):<14}'
              f'{r.get("tool_calls", 0):>5}'
              f'{r.get("requests", 0):>5}'
              f'{fmt_k(r.get("cache_read_input_tokens")):>8}'
              f'{fmt_k(r.get("output_tokens")):>7}'
              f'{fmt_k(r.get("cache_read_per_tool_call")):>8}  {phtxt}')

    # 分桶不變量：這兩個數字對不上代表分桶規則改壞了（見 s2_token_metrics.py）
    bad = [r for r in rows
           if r.get('classified_total') is not None
           and r['classified_total'] != r.get('tool_calls')]
    if bad:
        print()
        for r in bad:
            print(f'⚠️ {r["checkpoint"]}：分類總數 {r["classified_total"]} '
                  f'≠ 工具呼叫數 {r.get("tool_calls")}')


def cmd_diff(rows, args):
    a, b = pick(rows, args.diff[0]), pick(rows, args.diff[1])
    print(f'{args.diff[0]} → {args.diff[1]}（正數＝後者比較多）')
    print('=' * 60)
    for key, label in (('tool_calls', '工具呼叫'), ('requests', '請求'),
                       ('output_tokens', '輸出 token'),
                       ('cache_read_input_tokens', 'cache 讀取')):
        av, bv = a.get(key) or 0, b.get(key) or 0
        print(f'{label:<12}{fmt_k(av):>8} → {fmt_k(bv):>8}   {bv - av:+,}')

    print('\n── 逐工具（差距由大到小，只列有變動的）──')
    ta, tb = a.get('tool_calls_by_name') or {}, b.get('tool_calls_by_name') or {}
    keys = set(ta) | set(tb)
    deltas = sorted(((k, tb.get(k, 0) - ta.get(k, 0)) for k in keys),
                    key=lambda kv: -abs(kv[1]))
    shown = 0
    for k, d in deltas:
        if d == 0:
            continue
        print(f'  {d:+4}  {k:<38}({ta.get(k, 0)} → {tb.get(k, 0)})')
        shown += 1
    if not shown:
        print('  （逐工具完全相同）')

    print('\n── 逐階段（呼叫數／分鐘）──')
    pa, pb = a.get('phases') or {}, b.get('phases') or {}
    for k in sorted(set(pa) | set(pb)):
        ca, cb = (pa.get(k) or {}).get('calls', 0), (pb.get(k) or {}).get('calls', 0)
        ma, mb = (pa.get(k) or {}).get('minutes', 0), (pb.get(k) or {}).get('minutes', 0)
        if ca == cb and ma == mb:
            continue
        print(f'  {k:<8}{ca:>4} → {cb:<4}呼叫   {ma:>6g} → {mb:<6g}分')

    # 規則版本有沒有一起變——沒有這段就會把規則的效果算到腳本頭上
    ra, rb = a.get('rule_shas') or {}, b.get('rule_shas') or {}
    if ra or rb:
        changed = [k for k in set(ra) | set(rb) if ra.get(k) != rb.get(k)]
        print('\n── 規則版本 ──')
        if changed:
            print(f'  ⚠️ 這兩輪之間有改過：{", ".join(sorted(changed))}'
                  f'——數字的變化不一定是腳本的功勞')
        else:
            print('  規則檔沒變（差異可歸因於腳本／行為）')
    else:
        print('\n── 規則版本 ──\n  兩輪都沒有版本指紋（2026-08-17 之前的紀錄）'
              '，無法判斷規則是否同時變動')


def cmd_tool(rows, args):
    pat = args.tool.lower()
    rows = rows[-args.last:]
    print(f'工具趨勢：含「{args.tool}」的桶')
    print('-' * 60)
    any_hit = False
    for r in rows:
        t = r.get('tool_calls_by_name') or {}
        hits = {k: v for k, v in t.items() if pat in k.lower()}
        total = sum(hits.values())
        if hits:
            any_hit = True
        detail = ' '.join(f'{k}={v}' for k, v in sorted(hits.items(), key=lambda kv: -kv[1]))
        print(f'{r.get("checkpoint", "?"):<14}{total:>4}  {detail}')
    if not any_hit:
        print(f'（最近 {len(rows)} 輪都沒有符合「{args.tool}」的桶）')


def cmd_rules(rows, args):
    print('規則版本變動（只列跟前一輪不同的輪次）')
    print('-' * 60)
    prev = None
    seen_any = False
    for r in rows:
        cur = r.get('rule_shas')
        if cur is None:
            continue
        seen_any = True
        if prev is None:
            print(f'{r["checkpoint"]:<14}（起點）'
                  + ' '.join(f'{k}={v}' for k, v in sorted(cur.items())))
        else:
            changed = [k for k in set(prev) | set(cur) if prev.get(k) != cur.get(k)]
            if changed:
                print(f'{r["checkpoint"]:<14}改動：'
                      + ', '.join(f'{k} {prev.get(k)}→{cur.get(k)}'
                                  for k in sorted(changed)))
        prev = cur
    if not seen_any:
        print('（還沒有任何一輪帶版本指紋——2026-08-17 才上線，'
              '要等下一輪掃帶才會有）')


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--file', help='遙測檔路徑（預設雲端，退回本機）')
    ap.add_argument('--last', type=int, default=10, help='看最近幾輪，預設 10')
    ap.add_argument('--diff', nargs=2, metavar=('前一輪', '後一輪'),
                    help='兩輪逐桶相減——「多出的呼叫去了哪裡」')
    ap.add_argument('--tool', help='單一工具桶的跨輪趨勢（子字串比對）')
    ap.add_argument('--rules', action='store_true', help='規則版本何時變動')
    args = ap.parse_args()

    rows, path = load(args.file)
    print(f'# 來源：{path}（共 {len(rows)} 輪）\n', file=sys.stderr)

    if args.diff:
        cmd_diff(rows, args)
    elif args.tool:
        cmd_tool(rows, args)
    elif args.rules:
        cmd_rules(rows, args)
    else:
        cmd_table(rows, args)
    return 0


if __name__ == '__main__':
    sys.exit(main())
