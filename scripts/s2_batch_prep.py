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

── raw 檢查工具層（③，2026-08-13）──────────────────────────
掃帶 agent 每輪要反覆檢查 scratch 目錄裡的 raw json（站方清單／詳情／
batch 檔），實測發現三站清單原始檔各包一層不同的站方外殼：
    AP 清單：dict，實際陣列在 `Items` 鍵下（AP Newsroom API 原生回應）。
    RT 清單：dict，實際陣列在 `items` 鍵下（`{boxFound,count,items}`）。
    NS 清單：常常根本不是 JSON，是 `id|日期` 逐行純文字（.json 副檔名誤導）。
    已抽取的 detail／batch 檔則多半已經是裸陣列，不必卸殼。
這三個子指令把「先搞清楚這份檔案的殼長什麼樣」跟「從一堆欄位裡挑出要看的
那幾筆」收成固定流程，取代逐輪用 Read 整檔／PowerShell 切片／`python -c`
即興重寫。

    unwrap  <檔> [--out 檔]
        自動偵測外殼（Items／items／裸陣列／NS 純文字清單）並卸成規範化
        的裸陣列，寫回同目錄、檔名加 `_unwrapped`（或用 --out 指定）。
        偵測不出已知殼型時，回報實際看到的頂層型別／鍵，不靜默假裝成功。

    inspect <檔> [--ids A,B] [--fields f1,f2] [--limit N] [--index i]
        讀取（會自動卸殼，不必先跑 unwrap）並精準印出指定項目／欄位。
        不給 --ids/--index/--fields 時預設印摘要：筆數＋每筆 id＋標題行。

    search  <檔> --contains 關鍵字 [--field script|story|head|all]
        列出命中項的 id＋命中欄位裡關鍵字前後片段。

    python s2_batch_prep.py unwrap _ap_list_1000.json
    python s2_batch_prep.py inspect _rt_batch_1000.json --limit 5
    python s2_batch_prep.py inspect ap_detail_0430.json --ids AP4678110 --fields head,script
    python s2_batch_prep.py search rt_raw_1600.json --contains "Milei" --field all
"""
import argparse
import io
import json
import os
import re
import sys

# Windows 主控台常是 cp950，print() 中文欄位（entry／script 原文）會直接炸掉。
# 這不影響 --out 落檔（那條路本來就明寫 UTF-8），只補救不帶 --out 直接印到終端機的情境。
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# src_text 是「瘦身後的站方原文」留存用（13c 規則：只准站方原文，不准判斷／說明）。
# 跟正文擷取（script 正文取前 4,000 字元）用同一個上限，避免落檔無限長。
SRC_TEXT_LIMIT = 4000


# RT 站方稿的引言區段結構標記，跟 s2_state.sb_applicable() 用同一組判準
# （只認結構標記如 `SHOTLIST:`／`(SOUNDBITE`，不認裸字——RT4131 教訓：裸字比對
# 會被 agent 自己寫進 src_text 的中文說明騙倒）。SUPERS 是 CNN/NS 側常見的同類欄位，
# 一併收，行為對 NS/AP 沒有 SOUNDBITE 段的稿子不影響（下面找不到就直接走原本截斷）。
SOUNDBITE_RE = re.compile(r"\(\s*SOUNDBITE|SOUNDBITE\s*:|SUPERS\s*:", re.IGNORECASE)

# 硬保留的頭段長度：SOUNDBITE 區段太靠前面時直接原樣收（走 plain cut 那條路即可），
# 只有「頭段還沒截到就會先把 SOUNDBITE 砍掉」時才切換成保留策略。
HEAD_KEEP = 500


def truncate(s, limit=SRC_TEXT_LIMIT):
    """截斷標記絕對不能含中文。

    2026-08-12 0812-1600 輪實錯：原本用「…(截斷)」，直接踩到
    `s2_state.strip_agent_note()` 的判準——那條規則是 RT4131 連錯四輪換來的鐵律
    （三站原文一律英／西文，出現中文幾乎必然是 agent 混進去的判斷）。
    `strip_agent_note` 是整行砍，不是只砍標記本身，所以中文標記把它接上的
    整個最後一行（最長可達近 250 字的真實原文）一起當「agent 污染」剝掉，
    稽核（`s2_audit.py` §3）因此對 13 筆全部誤判成「混入中文說明」——
    查證後 13 筆全部是純英文站方原文被我這個標記拖累，沒有一筆是真的污染。

    2026-08-13 R4/R12 修正：
    - R4：原本 `s[:limit] + '...[TRUNCATED]'` 是「取滿 limit 字再加標記」，
      含標記總長會超過 limit（實錯 4014>4000）。改成標記也算在 limit 裡。
    - R12：RT 稿的 SOUNDBITE／SUPERS 段（逐字引言，寫稿驗 BITE 的唯一依據）
      常常落在 4000 字之後，傻取前 N 字會把它整段砍光（RT9878：sb_count=9
      但截斷文字內無任何引言，agent 只能標無BITE 送人工）。這種情況改成
      「頭段＋中段標記＋SOUNDBITE 起的區段」，SOUNDBITE 段本身超長時只保留
      它的前段——全部含標記仍 ≤ limit。中段標記同樣不能含中文（同上一條）。
    """
    s = s or ''
    if len(s) <= limit:
        return s
    end_marker = '...[TRUNCATED]'
    plain_cut = max(limit - len(end_marker), 0)

    m = SOUNDBITE_RE.search(s)
    if m and m.start() >= plain_cut:
        # 頭段截斷本來就會把 SOUNDBITE 段砍在外面，改保留策略
        mid_marker = '...[SNIP]...'
        head = s[:min(HEAD_KEEP, plain_cut)]
        budget_for_tail = limit - len(head) - len(mid_marker)
        tail = s[m.start():]
        if len(tail) > budget_for_tail:
            tail_cut = max(budget_for_tail - len(end_marker), 0)
            tail = tail[:tail_cut] + end_marker
        result = head + mid_marker + tail
        return result[:limit]  # 保險：理論上不會超過，但不賭

    return s[:plain_cut] + end_marker


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


# ── raw 檢查工具層：卸殼／inspect／search ──────────────────────

# 已知的站方外殼：頂層是 dict、實際陣列包在這些鍵之一底下。
# 依序嘗試，第一個「值是非空 list」的鍵勝出。
KNOWN_WRAPPER_KEYS = ['Items', 'items', 'PeopleItems', 'results', 'data', 'entries']


def _load_raw_any(path):
    """讀 raw 檔，回傳 (items, shell_desc)。

    items：規範化後的裸陣列（list of dict）。
    shell_desc：人看得懂的殼型描述，供 unwrap/inspect 回報用；
    偵測不出已知殼型時丟 ValueError，附上實際看到的型別／鍵，不猜、不吞錯。
    """
    with open(path, encoding='utf-8') as f:
        text = f.read()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        # NS 清單常見：不是 JSON，是 `id|日期` 逐行純文字（.json 副檔名誤導）。
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines and all('|' in ln for ln in lines[:5]):
            items = []
            for ln in lines:
                parts = ln.split('|', 1)
                items.append({'id': parts[0].strip(),
                              'created': parts[1].strip() if len(parts) > 1 else ''})
            return items, f'非 JSON，NS 純文字清單（id|日期），共 {len(items)} 行'
        raise ValueError(
            f'{path} 不是合法 JSON，也不像 NS 的 id|日期 純文字清單。'
            f'原始錯誤：{e}；前 200 字元：{text[:200]!r}'
        )

    if isinstance(data, list):
        return data, f'裸陣列（無殼），{len(data)} 筆'

    if isinstance(data, dict):
        for key in KNOWN_WRAPPER_KEYS:
            val = data.get(key)
            if isinstance(val, list) and val:
                return val, f'dict 殼，陣列在 "{key}" 鍵下，{len(val)} 筆'
        raise ValueError(
            f'{path} 頂層是 dict，但已知殼鍵 {KNOWN_WRAPPER_KEYS} 都沒有非空陣列。'
            f'實際頂層鍵：{list(data.keys())}'
        )

    raise ValueError(f'{path} 頂層既非 list 也非 dict：{type(data)}')


def cmd_unwrap(args):
    try:
        items, shell_desc = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 卸殼失敗：{e}', file=sys.stderr)
        sys.exit(1)

    if shell_desc.startswith('裸陣列'):
        note = '無殼，原樣複製'
    else:
        note = f'已卸殼（{shell_desc}）'

    out = args.out
    if not out:
        base, ext = os.path.splitext(args.raw)
        out = f'{base}_unwrapped{ext or ".json"}'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f'{note} → 已寫入 {out}（{len(items)} 筆）')


def _id_of_any(item, index):
    for key in ('id', 'code', '_id', 'itemid', 'guid'):
        if item.get(key):
            return str(item[key])
    return f'#{index}'


def _title_of_any(item):
    # AP 清單原始檔（Items 殼卸完後）是 Elasticsearch 風格，實際欄位包在
    # `_source` 底下（`_source.caption.nitf` 才是標題），不是頂層。
    candidates = [item]
    if isinstance(item.get('_source'), dict):
        candidates.append(item['_source'])
    for cand in candidates:
        for key in ('head', 'title', 'desc', 'story', 'cap', 'entry', 'src_text', 'text'):
            v = cand.get(key)
            if isinstance(v, str) and v:
                return v if len(v) <= 100 else v[:100] + '...'
            if isinstance(v, dict) and v.get('nitf'):
                return v['nitf'][:100]
    return ''


def cmd_inspect(args):
    try:
        items, shell_desc = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    print(f'# {args.raw}：{shell_desc}', file=sys.stderr)

    indexed = list(enumerate(items))

    if args.index is not None:
        if not (0 <= args.index < len(items)):
            print(f'✗ --index {args.index} 超出範圍（共 {len(items)} 筆，0-based）', file=sys.stderr)
            sys.exit(1)
        indexed = [(args.index, items[args.index])]
    elif args.ids:
        want = set(x.strip() for x in args.ids.split(','))
        indexed = [(i, it) for i, it in indexed if _id_of_any(it, i) in want]
        found = set(_id_of_any(it, i) for i, it in indexed)
        missing = want - found
        if missing:
            print(f'⚠️ 找不到這些 id：{", ".join(sorted(missing))}', file=sys.stderr)

    fields = [f.strip() for f in args.fields.split(',')] if args.fields else None
    full_detail = fields is not None and len(indexed) <= 3  # 少量精準查詢時不截斷

    limit = args.limit or 100
    shown, total = indexed[:limit], len(indexed)

    lines = []
    for i, it in shown:
        item_id = _id_of_any(it, i)
        if fields:
            picked = {}
            for k in fields:
                v = it.get(k, '<無此欄位>')
                if isinstance(v, str) and not full_detail and len(v) > 200:
                    v = v[:200] + '...[略]'
                picked[k] = v
            lines.append(f'{item_id}\t{json.dumps(picked, ensure_ascii=False)}')
        else:
            lines.append(f'{item_id}\t{_title_of_any(it)}')

    print('\n'.join(lines))
    if total > limit:
        print(f'…另 {total - limit} 筆略，用 --limit 調整', file=sys.stderr)
    print(f'共 {len(items)} 筆，本次顯示 {min(total, limit)} 筆', file=sys.stderr)


def cmd_search(args):
    try:
        items, shell_desc = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    print(f'# {args.raw}：{shell_desc}', file=sys.stderr)

    if args.field == 'all':
        field_candidates = None  # 每筆的所有字串欄位都搜
    elif args.field == 'script':
        field_candidates = ['script', 'story']  # RT 用 story 取代 script
    else:
        field_candidates = {
            'story': ['story', 'script'],
            'head': ['head', 'title'],
        }.get(args.field, [args.field])

    needle = args.contains.lower()
    hits = []
    for i, it in enumerate(items):
        item_id = _id_of_any(it, i)
        fields_to_check = (
            [(k, v) for k, v in it.items() if isinstance(v, str)]
            if field_candidates is None
            else [(k, it.get(k)) for k in field_candidates if isinstance(it.get(k), str)]
        )
        for field_name, text in fields_to_check:
            pos = text.lower().find(needle)
            if pos == -1:
                continue
            start = max(0, pos - 40)
            end = min(len(text), pos + len(args.contains) + 40)
            snippet = text[start:end].replace('\n', ' ')
            hits.append(f'{item_id}\t[{field_name}]\t...{snippet}...')

    limit = args.limit or 100
    shown = hits[:limit]
    print('\n'.join(shown) if shown else '（無命中）')
    if len(hits) > limit:
        print(f'…另 {len(hits) - limit} 筆命中略，用 --limit 調整', file=sys.stderr)
    print(f'共 {len(items)} 筆項目，命中 {len(hits)} 處', file=sys.stderr)


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

    p_unwrap = sub.add_parser('unwrap', help='自動偵測外殼並卸成規範化裸陣列')
    p_unwrap.add_argument('raw')
    p_unwrap.add_argument('--out')
    p_unwrap.set_defaults(func=cmd_unwrap)

    p_inspect = sub.add_parser('inspect', help='精準印出 raw 檔的指定項目/欄位')
    p_inspect.add_argument('raw')
    p_inspect.add_argument('--ids', help='逗號分隔的 id 清單')
    p_inspect.add_argument('--fields', help='逗號分隔的欄位名清單')
    p_inspect.add_argument('--limit', type=int, help='最多顯示幾筆，預設 100')
    p_inspect.add_argument('--index', type=int, help='只看第 i 筆（0-based）')
    p_inspect.set_defaults(func=cmd_inspect)

    p_search = sub.add_parser('search', help='在 raw 檔的指定欄位裡找關鍵字')
    p_search.add_argument('raw')
    p_search.add_argument('--contains', required=True)
    p_search.add_argument('--field', default='all', choices=['script', 'story', 'head', 'all'])
    p_search.add_argument('--limit', type=int, help='最多顯示幾筆命中，預設 100')
    p_search.set_defaults(func=cmd_search)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
