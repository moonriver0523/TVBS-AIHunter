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

── 稽核快照與比對（A2，2026-08-17）─────────────────────────

    snapshot <檔> [--site ns|ap|rt] [--checkpoint 0817-1600] [--out 檔]
        把 raw 壓成純文字快照（標頭記殼型／筆數，之後每行 `id\t標題`），
        供事後對帳比對，不必重開瀏覽器重抓。不給 --out 就用 --checkpoint
        組 `_audit_{site}_{HHMM}.txt`。**已存在的快照一律不覆寫**——
        覆寫等於靜默銷毀稽核依據。

    compare --raw <raw檔> --batch <batch檔> [--site ns|ap|rt] [--require 欄位,…]
        只印差異：raw 有 batch 沒有的 id、batch 有 raw 沒有的 id、
        batch 內重複 id、batch 缺欄位（預設查
        id/source/checkpoint/status/entry/src_text）。乾淨就一行「無差異」。
        在 `add-batch` 之前跑，一次擋掉漏收與整批漏帶 src_text 兩種坑。

    python s2_batch_prep.py snapshot _rt_list_1600.json --site rt --checkpoint 0817-1600
    python s2_batch_prep.py compare --raw _rt_list_1600.json --batch rt_batch_1600.json --site rt

── 去重比對（D9 第一步，2026-08-17）────────────────────────

    dedup-check <檔> --ids A,B[,C…] [--site ns|ap|rt] [--fields script,desc,…]
        兩則以上的指定欄位逐字比對，回答「是不是同一則的不同版本」。
        四種判定分開講，不混為一談：
            ✓ 逐字相同
            ≈ 只差空白／換行
            ≈ 只差 HTML 標記／空白（NS 的 script 夾 <p>／<b>）
            ✗ 不同——並指出剝掉標記後第幾字起不同、印出兩邊該處前後文
        **只回答機械問題。要不要當重複、留哪一則，是編輯判斷，這裡不做。**
        id 打錯／找不到／欄位不存在一律明確失敗中止，不會只比得出來的那幾則
        ——否則「打錯 id」跟「兩則不同」看起來會一樣。
        AP 清單檔是 ES 形狀，會自動看穿 `_source` 並用 `AP<editorialid>`
        當 id（跟 state 對得起來），不是頂層的 `_id` 雜湊。

    python s2_batch_prep.py dedup-check ns_full_2200.json --site ns --ids EN-32MO,EN-31MO
    python s2_batch_prep.py dedup-check ap_list_2200.json --site ap --ids AP5467677,AP5467678 --fields title,headline
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
    # 檔案打不開也要走 ValueError 這條路：呼叫端全都只接 ValueError，
    # 讓 OSError 逃出去只會噴一整段 traceback，agent 還得自己解讀
    # （2026-08-17 A2 測試抓到；unwrap／inspect／search 原本都有這個洞）。
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except OSError as e:
        raise ValueError(f'讀不到 {path}：{e}')

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


# ── 稽核快照與比對（A2，2026-08-17）──────────────────────────

def _site_id_of(site, item, index):
    """有 --site 就走 per-site adapter（RT 用 `code` 不是 `id`），
    沒有就走通用猜測。猜測只在沒指定站別時用，指定了就以規則為準。"""
    if site:
        return SITE_SPEC[site]['id_of'](item) or _id_of_any(item, index)
    return _id_of_any(item, index)


def cmd_snapshot(args):
    """把一份 raw 檔壓成穩定、可事後比對的純文字快照。

    用途是稽核留痕：這一輪站方清單「當時長什麼樣」。之後對帳有爭議時
    可以直接比兩份快照，不必重開瀏覽器重抓。"""
    try:
        items, shell_desc = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)

    out = args.out
    if not out:
        if not args.checkpoint:
            print('✗ 要嘛給 --out，要嘛給 --checkpoint（用來組 _audit_{site}_{HHMM}.txt）',
                  file=sys.stderr)
            sys.exit(1)
        hhmm = args.checkpoint.split('-')[-1]
        site = args.site or 'raw'
        out = os.path.join(os.path.dirname(os.path.abspath(args.raw)),
                           f'_audit_{site}_{hhmm}.txt')

    # 護欄：**不覆寫舊快照**。快照的價值就在於它是當時的樣子，
    # 覆寫掉等於把稽核依據銷毀，而且是靜默銷毀。
    if os.path.exists(out):
        print(f'✗ {out} 已存在，快照不覆寫舊檔（那會靜默銷毀稽核依據）。'
              f'要另存請給不同的 --out', file=sys.stderr)
        sys.exit(1)

    lines = [
        f'# 來源：{os.path.basename(args.raw)}',
        f'# 殼型：{shell_desc}',
        f'# 站別：{args.site or "（未指定，id 用通用猜測）"}',
        f'# 輪次：{args.checkpoint or "（未指定）"}',
        f'# 筆數：{len(items)}',
        '',
    ]
    for i, it in enumerate(items):
        item_id = _site_id_of(args.site, it, i)
        desc = _title_of_any(it)
        if not desc:
            # 清單檔常常只有 `code` ＋ `at`（沒有標題欄）。這種時候印剩下的短欄位，
            # 比留一整排空白有用——快照的用途是「當時清單長什麼樣」。
            desc = ' '.join(
                f'{k}={v}' for k, v in it.items()
                if k != 'id' and isinstance(v, (str, int, float, bool))
                and len(str(v)) <= 40 and str(v) != item_id)
        lines.append(f'{item_id}\t{desc}')

    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'快照已寫入 {out}（{len(items)} 筆）')


# batch 每筆該有的欄位。src_text 是 13d §5 的鐵律（事後查證的唯一依據），
# 漏帶過兩次整批（0812-2200 的 65 則、0813-1200 的 80 則），所以預設就要查。
DEFAULT_REQUIRED = ('id', 'source', 'checkpoint', 'status', 'entry', 'src_text')


def cmd_compare(args):
    """raw 與 batch 對照，**只印差異**：raw 有 batch 沒有的 id、batch 有 raw
    沒有的 id、batch 缺欄位的則。乾淨就一行「無差異」，不印整批。"""
    try:
        raw_items, raw_shell = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ raw 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    try:
        batch_items, batch_shell = _load_raw_any(args.batch)
    except ValueError as e:
        print(f'✗ batch 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)

    print(f'# raw  ：{os.path.basename(args.raw)}（{raw_shell}）', file=sys.stderr)
    print(f'# batch：{os.path.basename(args.batch)}（{batch_shell}）', file=sys.stderr)

    raw_ids = [_site_id_of(args.site, it, i) for i, it in enumerate(raw_items)]
    batch_ids = [(it.get('id') or _id_of_any(it, i)) for i, it in enumerate(batch_items)]
    raw_set, batch_set = set(raw_ids), set(batch_ids)

    required = ([f.strip() for f in args.require.split(',') if f.strip()]
                if args.require else list(DEFAULT_REQUIRED))

    missing = [i for i in raw_ids if i not in batch_set]
    extra = [i for i in batch_ids if i not in raw_set]

    gaps = []
    for i, it in enumerate(batch_items):
        item_id = it.get('id') or _id_of_any(it, i)
        lack = [f for f in required
                if it.get(f) in (None, '', [], {})]
        if lack:
            gaps.append((item_id, lack))

    dup_batch = sorted({i for i in batch_ids if batch_ids.count(i) > 1})

    found = False
    if missing:
        found = True
        print(f'raw 有、batch 沒有（{len(missing)} 則——可能是刻意排除，'
              f'但要說得出理由）：')
        for i in missing:
            print(f'  - {i}')
    if extra:
        found = True
        print(f'batch 有、raw 沒有（{len(extra)} 則——來源不明，要查）：')
        for i in extra:
            print(f'  - {i}')
    if dup_batch:
        found = True
        print(f'batch 內重複 id（{len(dup_batch)} 個）：{", ".join(dup_batch)}')
    if gaps:
        found = True
        print(f'batch 缺欄位（{len(gaps)} 則，查的是 {"/".join(required)}）：')
        for item_id, lack in gaps:
            print(f'  - {item_id}：缺 {", ".join(lack)}')

    if not found:
        print(f'無差異（raw {len(raw_items)} 筆、batch {len(batch_items)} 筆，'
              f'id 全對得上，{"/".join(required)} 都有）')


DEDUP_FIELDS = ('script', 'desc', 'head', 'headline', 'story', 'cap', 'title')


def _dedup_view(item):
    """AP 清單檔是 Elasticsearch 形狀，真正的欄位包在 `_source` 底下，
    頂層只有 `_id` 這種雜湊。不看穿這層的話，AP 清單上的去重完全比不動——
    而 0817-2200 的 AP 去重正是在清單檔上做的。"""
    src = item.get('_source')
    if isinstance(src, dict):
        merged = dict(item)
        merged.update(src)
        return merged
    return item


def _dedup_id(site, item, index):
    """去重比對用的 id。AP 站的人看的是 `AP<editorialid>`（state 裡也是這個），
    不是 ES 的 `_id` 雜湊——比對時要用人看得懂、跟 state 對得起來的那個。"""
    view = _dedup_view(item)
    if site == 'ap' and view.get('editorialid'):
        return 'AP' + str(view['editorialid'])
    return _site_id_of(site, view, index)


def _norm(s):
    """去重比對用的正規化：吃掉全形/半形空白與換行差異，其餘不動。
    只用來回答「排版不同但內容相同嗎」，不改變逐字比對的結論。"""
    return ''.join(str(s).split())


TAG_RE = re.compile(r'<[^>]+>')


def _norm_markup(s):
    """再多剝一層 HTML 標記。NS 的 script 夾著 <p>／<b>，同一則的不同剪輯版
    常常只差在標記上——不剝掉的話，「第一個差異」會指到 `<b>` 這種雜訊，
    而不是真正的內容差異（0817-2200 EN-32MO vs EN-31MO 就是這樣）。"""
    return _norm(TAG_RE.sub('', str(s)))


def _first_diff(a, b):
    """回傳第一個相異字元的 0-based 位置；完全相同回 None。
    其中一邊是另一邊的前綴時，位置就是較短那邊的長度。"""
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return i
    return None if len(a) == len(b) else min(len(a), len(b))


def cmd_dedup_check(args):
    """兩則以上的指定欄位逐字比對，回答「是不是同一則的不同版本」。

    0817-2200 那輪 NS 去重花了 5 次臨時 python 做這件事（撈出兩則 script
    再自己算 a==b）——`inspect` 能把兩段印出來，但沒有「相同與否」的答案，
    agent 只能自己算。這個子指令補的就是那個洞。

    **只回答機械問題（逐字是否相同、差在哪）；要不要當成重複、留哪一則，
    是編輯判斷，這裡不做也不建議。**"""
    try:
        items, shell_desc = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    print(f'# {os.path.basename(args.raw)}：{shell_desc}', file=sys.stderr)

    ids = [i.strip() for i in args.ids.split(',') if i.strip()]
    if len(ids) < 2:
        print(f'✗ --ids 至少要兩個才比得出來（收到 {len(ids)} 個）', file=sys.stderr)
        sys.exit(1)
    dup_in_arg = sorted({i for i in ids if ids.count(i) > 1})
    if dup_in_arg:
        print(f'✗ --ids 裡有重複：{", ".join(dup_in_arg)}', file=sys.stderr)
        sys.exit(1)

    table = {}
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        table.setdefault(_dedup_id(args.site, it, idx), _dedup_view(it))

    absent = [i for i in ids if i not in table]
    if absent:
        # 找不到就明講並中止，不能只比得出來的那幾則——那會讓
        # 「打錯 id」跟「兩則不同」看起來一樣。
        print(f'✗ 這些 id 不在 {os.path.basename(args.raw)} 裡：{", ".join(absent)}',
              file=sys.stderr)
        print(f'  （檔內共 {len(table)} 個 id，可用 inspect 確認拼法）', file=sys.stderr)
        sys.exit(1)

    picked = [(i, table[i]) for i in ids]

    if args.fields:
        fields = [f.strip() for f in args.fields.split(',') if f.strip()]
        lacking = [f for f in fields
                   if not any(isinstance(it.get(f), str) for _, it in picked)]
        if lacking:
            print(f'✗ 指定的欄位在這幾則裡都不是文字或不存在：{", ".join(lacking)}',
                  file=sys.stderr)
            sys.exit(1)
    else:
        fields = [f for f in DEDUP_FIELDS
                  if any(isinstance(it.get(f), str) and it.get(f) for _, it in picked)]
        if not fields:
            print(f'✗ 這幾則裡找不到任何可比對的文字欄位'
                  f'（找過 {"/".join(DEDUP_FIELDS)}），請用 --fields 指定',
                  file=sys.stderr)
            sys.exit(1)

    pairs = [(a, b) for x, a in enumerate(ids) for b in ids[x + 1:]]
    verdicts = {}

    for f in fields:
        print(f'── {f} ──')
        for i, it in picked:
            v = it.get(f)
            if isinstance(v, str):
                print(f'  {i}  len={len(v)}')
            else:
                print(f'  {i}  （無此欄位或不是文字：{type(v).__name__}）')
        for a, b in pairs:
            va, vb = table[a].get(f), table[b].get(f)
            if not isinstance(va, str) or not isinstance(vb, str):
                verdicts[(f, a, b)] = 'n/a'
                print(f'  ? {a} vs {b}：有一邊沒有這個欄位，無法比對')
                continue
            if not va and not vb:
                # 兩邊都空「逐字相同」在機械上成立，但拿來當去重依據是假訊號。
                verdicts[(f, a, b)] = 'both_empty'
                print(f'  ? {a} vs {b}：兩邊這個欄位都是空的，不足以判斷重複')
            elif va == vb:
                verdicts[(f, a, b)] = 'same'
                print(f'  ✓ {a} vs {b}：逐字相同')
            elif _norm(va) == _norm(vb):
                verdicts[(f, a, b)] = 'same_normalized'
                print(f'  ≈ {a} vs {b}：**只差空白／換行**，去掉空白後逐字相同')
            elif _norm_markup(va) == _norm_markup(vb):
                verdicts[(f, a, b)] = 'same_markup'
                print(f'  ≈ {a} vs {b}：**只差 HTML 標記／空白**，剝掉標記後逐字相同')
            else:
                verdicts[(f, a, b)] = 'diff'
                # 差異位置一律算在「剝掉標記與空白」之後的文字上，否則
                # 指標會停在 <b> 這種排版雜訊，看不到真正差在哪。
                ca, cb = _norm_markup(va), _norm_markup(vb)
                pos = _first_diff(ca, cb)
                print(f'  ✗ {a} vs {b}：不同（剝掉標記後第 {pos} 字起不同）')
                lo = max(0, pos - 30)
                print(f'      {a}：…{ca[lo:pos + 30]}…')
                print(f'      {b}：…{cb[lo:pos + 30]}…')
        print()

    print('── 結論（機械判斷，收不收由編輯決定）──')
    # 四種判定在結論行也要分開講——折成「相同」會讓「逐字相同」跟
    # 「剝掉標記才相同」看起來一樣，而這支工具存在的理由就是把它們分開。
    labels = [('same', '相同'), ('same_normalized', '去空白後相同'),
              ('same_markup', '剝標記後相同'), ('diff', '不同'),
              ('both_empty', '兩邊皆空'), ('n/a', '無法比')]
    for a, b in pairs:
        bits = []
        for key, word in labels:
            hit = [f for f in fields if verdicts.get((f, a, b)) == key]
            if hit:
                bits.append(f'{"/".join(hit)} {word}')
        unresolved = [f for f in fields if (f, a, b) not in verdicts]
        if unresolved:
            # 結論行是掃帶 agent 唯一會讀的一行，寧可炸掉也不能印半行空白。
            print(f'✗ 內部錯誤：{a} vs {b} 的 {"/".join(unresolved)} 沒有判定結果',
                  file=sys.stderr)
            sys.exit(1)
        print(f'  {a} vs {b}：{"、".join(bits)}')


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

    p_snap = sub.add_parser('snapshot', help='把 raw 檔壓成純文字稽核快照（不覆寫舊檔）')
    p_snap.add_argument('raw')
    p_snap.add_argument('--site', choices=['ns', 'ap', 'rt'], help='指定站別才用得到 per-site id 規則（RT 是 code）')
    p_snap.add_argument('--checkpoint', help='用來組預設檔名 _audit_{site}_{HHMM}.txt')
    p_snap.add_argument('--out', help='輸出路徑；不給就用 --checkpoint 組')
    p_snap.set_defaults(func=cmd_snapshot)

    p_cmp = sub.add_parser('compare', help='raw 與 batch 對照，只印缺 id／缺欄位')
    p_cmp.add_argument('--raw', required=True)
    p_cmp.add_argument('--batch', required=True)
    p_cmp.add_argument('--site', choices=['ns', 'ap', 'rt'])
    p_cmp.add_argument('--require', help=f'要檢查的欄位，逗號分隔。預設 {",".join(DEFAULT_REQUIRED)}')

    p_dc = sub.add_parser('dedup-check', help='兩則以上的指定欄位逐字比對，判斷是不是同一則的不同版本')
    p_dc.add_argument('raw')
    p_dc.add_argument('--ids', required=True, help='逗號分隔，至少兩個')
    p_dc.add_argument('--site', choices=['ns', 'ap', 'rt'], help='指定站別才用得到 per-site id 規則（RT 是 code）')
    p_dc.add_argument('--fields', help=f'要比的欄位，逗號分隔。不給就自動挑 {"/".join(DEDUP_FIELDS)} 裡有內容的')
    p_cmp.set_defaults(func=cmd_compare)
    p_dc.set_defaults(func=cmd_dedup_check)
    p_search.set_defaults(func=cmd_search)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
