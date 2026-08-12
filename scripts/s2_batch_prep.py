#!/usr/bin/env python3
"""S2 掃帶三站批次整備工具（②，2026-08-12）。

三站（NS／AP／RT）都要走同一組流程：先看 raw 抽取結果判斷要不要收、
sb_count／has_sot／footage_type 這些機械欄位，再把 agent 自己寫的 `entry`
（中文三段式摘要，這是編輯判斷，不可能機械生成）併回去、湊成能直接
`add-batch` 的 batch.json。0730 那輪這五步被拆成 15 次臨時 `python -c`
（含兩次純重複），這支腳本把「機械的部分」收成兩個子指令：

    dump   讀 raw.json，印出（或存成 .txt）每則的關鍵欄位，取代
           手打 print 確認格式那幾步。**只印機械欄位，不判斷、不寫 entry**。
    build  讀 raw.json ＋ agent 自己寫的 entries.json（{id: entry 文字}），
           機械併出最終 batch.json：id／source／checkpoint／status／
           站別專屬欄位（sb_count／has_sot／footage_type）／entry／src_text。

⚠️ **`entry` 欄位（中文三段式摘要、BITE 判斷、分類措辭）永遠是 agent 自己
寫**，這支腳本不生成、不翻譯、不判斷 BITE——那是編輯判斷，機械做不到。
腳本只負責「把 agent 已經判斷完的結果，跟 raw 裡的機械欄位對好、湊成
add-batch 吃得下的格式」，正是原本 15 次臨時 python 裡唯一真正機械、
可以收成固定流程的那部分。

用法：
    python s2_batch_prep.py dump --site ap --raw ap_batch_0730_raw.json
    python s2_batch_prep.py dump --site ap --raw ap_batch_0730_raw.json --out ap_dump_0730.txt

    python s2_batch_prep.py build --site ap --raw ap_batch_0730_raw.json \\
        --entries ap_entries_0730.json --checkpoint 0812-0730 \\
        --out ap_batch_0730.json

entries.json 格式：`{"AP4677906": "◆ AP4677906 (…) …"}`；
值也可以是 `{"entry": "…", "status": "pending"}` 這種物件，
用來覆蓋機械推導出的 status（例如初稿還沒補正式稿）。

三站欄位不統一，per-site adapter 寫死在 SITE_SPEC 裡；raw.json 的欄位名
以 13c 規則檔為準（NS: id/ft/dur_ms/desc/script/skip；
AP: id/head/cap/script/role/sb_count/has_sot/prelim；
RT: code/head/story/sb_count/early）。
"""
import argparse
import io
import json
import os
import sys

# Windows 主控台常是 cp950，print() 中文欄位（entry／script 原文）會直接炸掉。
# 這不影響 --out 落檔（那條路本來就明寫 UTF-8），只補救不帶 --out 直接印到終端機的情境。
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# src_text 是「瘦身後的站方原文」留存用（13c 規則：只准站方原文，不准判斷／說明）。
# 跟正文擷取（script 正文取前 4,000 字元）用同一個上限，避免落檔無限長。
SRC_TEXT_LIMIT = 4000


def truncate(s, limit=SRC_TEXT_LIMIT):
    s = s or ''
    return s if len(s) <= limit else s[:limit] + '…(截斷)'


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


# ── per-site adapter ──────────────────────────────────────────────
# id_of：從 raw item 取狀態檔用的 id（三站前綴規則不同，見 13c）
# skip_of：機械排除判準（NS 的 AUDIO TRACK／GRAPHIC 初稿佔位；13c §3）；
#          回傳非空字串＝這則不收，不進 batch.json
# status_of：機械推導 script_status（prelim／early access → pending）
# extra_of：站別專屬欄位（NS: footage_type；AP: sb_count/has_sot；RT: sb_count）
# src_text_of：機械組「瘦身後的站方原文」，跟現行 batch.json 既有格式對齊

SITE_SPEC = {
    'ns': {
        'source': 'NS',
        'id_of': lambda it: it.get('id', ''),
        'skip_of': lambda it: it.get('skip', '') or '',
        'status_of': lambda it: 'has_script',
        'extra_of': lambda it: {'footage_type': it.get('ft', '')},
        'src_text_of': lambda it: truncate(
            f"DESC: {it.get('desc', '')}\nSCRIPT: {it.get('script', '')}"
        ),
        'dump_fields': ['id', 'ft', 'dur_ms', 'created', 'skip', 'desc'],
    },
    'ap': {
        'source': 'AP',
        'id_of': lambda it: it.get('id', ''),
        'skip_of': lambda it: '',
        'status_of': lambda it: 'pending' if it.get('prelim') else 'has_script',
        'extra_of': lambda it: {
            'sb_count': it.get('sb_count', 0),
            'has_sot': bool(it.get('has_sot')),
        },
        'src_text_of': lambda it: truncate(
            f"HEAD: {it.get('head', '')}\nSCRIPT: {it.get('script', '')}"
        ),
        'dump_fields': ['id', 'role', 'sb_count', 'has_sot', 'prelim', 'dur', 'src', 'head'],
    },
    'rt': {
        'source': 'RT',
        'id_of': lambda it: it.get('code', ''),
        'skip_of': lambda it: '',
        'status_of': lambda it: 'pending' if it.get('early') else 'has_script',
        'extra_of': lambda it: {'sb_count': it.get('sb_count', 0)},
        'src_text_of': lambda it: truncate(
            f"HEAD: {it.get('head', '')}\nSTORY: {it.get('story', '')}"
        ),
        'dump_fields': ['code', 'sb_count', 'early', 'dur', 'src', 'head'],
    },
}


def dedup_by_id(spec, items):
    """raw 裡不該有重複 id（13c：逐字完全相同才准跳過，抽取階段就該濾掉），但抽取端
    萬一分頁重疊、agent 重複收錄還是可能發生。保留第一次出現的那筆，其餘丟棄並警告，
    避免兩筆同 id 原樣送進 add-batch（下游行為未定義）。"""
    seen, kept, dups = set(), [], []
    for it in items:
        item_id = spec['id_of'](it)
        if item_id in seen:
            dups.append(item_id)
            continue
        seen.add(item_id)
        kept.append(it)
    if dups:
        print(f'⚠️ raw 裡有重複 id，只保留第一次出現的那筆：{", ".join(dups)}', file=sys.stderr)
    return kept


def cmd_dump(args):
    spec = SITE_SPEC[args.site]
    items = dedup_by_id(spec, load_json(args.raw))
    lines = []
    kept = skipped = 0
    for it in items:
        item_id = spec['id_of'](it)
        skip_reason = spec['skip_of'](it)
        if skip_reason:
            skipped += 1
            lines.append(f"[排除:{skip_reason}] {item_id}")
            continue
        kept += 1
        fields = {k: it.get(k) for k in spec['dump_fields']}
        lines.append(f"{item_id}\t{json.dumps(fields, ensure_ascii=False)}")
    lines.append(f"\n共 {len(items)} 則，收 {kept}、機械排除 {skipped}")
    out = '\n'.join(lines)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(out + '\n')
        print(f'已寫入 {args.out}（{kept} 則）', file=sys.stderr)
    else:
        print(out)


def cmd_build(args):
    spec = SITE_SPEC[args.site]
    items = dedup_by_id(spec, load_json(args.raw))
    entries = load_json(args.entries)

    batch = []
    missing = []
    excluded = 0
    for it in items:
        item_id = spec['id_of'](it)
        if spec['skip_of'](it):
            excluded += 1
            continue
        if item_id not in entries:
            missing.append(item_id)
            continue
        raw_entry = entries[item_id]
        if isinstance(raw_entry, dict):
            entry_text = raw_entry.get('entry', '')
            status_override = raw_entry.get('status')
        else:
            entry_text = raw_entry
            status_override = None

        row = {
            'id': item_id,
            'source': spec['source'],
            'checkpoint': args.checkpoint,
            'status': status_override or spec['status_of'](it),
            'entry': entry_text,
            'src_text': spec['src_text_of'](it),
        }
        row.update(spec['extra_of'](it))
        batch.append(row)

    out = json.dumps(batch, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(out)
        print(f'已寫入 {args.out}（{len(batch)} 則）', file=sys.stderr)
    else:
        print(out)

    if missing:
        print(f'⚠️ raw 裡有但 entries.json 沒寫的 id（未收進 batch，不算錯，'
              f'但確認是不是漏判）：{", ".join(missing)}', file=sys.stderr)
    if excluded:
        print(f'機械排除 {excluded} 則（見 dump 輸出的排除原因）', file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_dump = sub.add_parser('dump', help='印出/存出 raw.json 的機械欄位摘要')
    p_dump.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_dump.add_argument('--raw', required=True)
    p_dump.add_argument('--out')
    p_dump.set_defaults(func=cmd_dump)

    p_build = sub.add_parser('build', help='raw.json ＋ entries.json 併成 add-batch 用的 batch.json')
    p_build.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_build.add_argument('--raw', required=True)
    p_build.add_argument('--entries', required=True)
    p_build.add_argument('--checkpoint', required=True)
    p_build.add_argument('--out')
    p_build.set_defaults(func=cmd_build)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
