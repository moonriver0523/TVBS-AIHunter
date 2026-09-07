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
用來覆蓋機械推導出的 status（例如初稿還沒補正式稿）。物件還可以帶
`category`（`"大分類/中主題[/小分題]"`）／`tc`（`"T1,T2/C1,C2"`）兩鍵，
`build` 會原樣帶進 batch row，交給 `add-batch` 一次入庫＋分類＋標 T/C
（2026-09-07 T12）。

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
        🔴 **`--ids` 請一次帶多則**（`--ids A,B,C,…`）。全文總長吃得下
        28,000 字元就**整批印全文**；塞不下才退回 200 字元預覽，並明講、
        附上前 N 筆的分批指令。一次只查一則跟一次查 20 則**成本一樣**
        （每次呼叫都要重付整個 context ≈ $0.089），所以逐則翻是純浪費。

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
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2_state  # noqa: E402  from-raw 讀狀態檔（唯讀，D12 已在庫標記）

# Windows 主控台常是 cp950，print() 中文欄位（entry／script 原文）會直接炸掉。
# 這不影響 --out 落檔（那條路本來就明寫 UTF-8），只補救不帶 --out 直接印到終端機的情境。
#
# 🔴 2026-08-31 改（全流程 locale 編碼稽核）：原本用 `io.TextIOWrapper` 包一層，
# 那正是 WP1（2026-08-03）記過的寫法——包第二層時其中一個 wrapper 被回收會關掉
# 底層 buffer，整支腳本以 "I/O operation on closed file" 掛掉。本檔目前沒有 import
# 其他 s2 模組所以還沒踩到，但這是最常被呼叫的工具（inspect 每輪 25–34 次），
# 哪天有人加一行 `import s2_state` 就會炸。統一改成 repo 其餘 20 支在用的
# `reconfigure` 寫法，順便補 `errors="replace"`（外電原文偶爾夾代理字元）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # py<3.7
        pass

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

# `inspect --fields` 一次能印多少字元的全文預算（T9，2026-08-25）。
# 沿用 R15 的 `SAFE_BUDGET`＝28,000 同一個數字：Read 結果約 30,000 字元會**靜默**
# 截斷，超過就等於白花一次呼叫。
INSPECT_TEXT_BUDGET = 28000

# 塞不下預算時每個欄位的預覽長度（原本的固定行為，現在只在超預算時才走）。
INSPECT_PREVIEW_CHARS = 200


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
    entries = load_json(args.entries)

    # A24（2026-09-07）：`from-raw` 產的骨架已經把機械欄位（id/source/checkpoint/
    # status/src_text/站別專屬欄位）全填好，agent 只需要寫極小的
    # `{id: {entry, category, tc}}`。這條路徑直接以骨架為底，不重讀 raw——
    # 骨架本身就是「dedup＋機械排除＋D12 已在庫標記」跑完之後的結果，
    # 沒有理由再對 raw 重跑一次同樣的判斷。
    if getattr(args, 'skeleton', None):
        rows = load_json(args.skeleton)
        batch, missing = [], []
        for row in rows:
            item_id = row.get('id')
            raw_entry = entries.get(item_id)
            if isinstance(raw_entry, dict):
                entry_text = raw_entry.get('entry', '')
                category = raw_entry.get('category')
                tc = raw_entry.get('tc')
                status_override = raw_entry.get('status')
            elif isinstance(raw_entry, str):
                entry_text, category, tc, status_override = raw_entry, None, None, None
            else:
                entry_text, category, tc, status_override = '', None, None, None
            if not entry_text:
                missing.append(item_id)
                continue
            # 骨架的 entry/category/tc 是留空的佔位鍵，hint／prev_status 是
            # 骨架內部給 agent 看的提示，三者都不該原樣流進 batch.json。
            new_row = {k: v for k, v in row.items()
                       if k not in ('entry', 'category', 'tc', 'hint', 'prev_status')}
            new_row['entry'] = entry_text
            if status_override is not None:
                new_row['status'] = status_override
            if category is not None:
                new_row['category'] = category
            if tc is not None:
                new_row['tc'] = tc
            batch.append(new_row)

        out = json.dumps(batch, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f:
                f.write(out)
            print(f'已寫入 {args.out}（{len(batch)} 則）', file=sys.stderr)
        else:
            print(out)
        if missing:
            print(f'⚠️ 骨架裡有、entries.json 沒填 entry 的 id（未填，不算錯，'
                  f'但確認是不是漏判，不進 batch）：{", ".join(str(m) for m in missing)}',
                  file=sys.stderr)
        return

    spec = SITE_SPEC[args.site]
    items = dedup_by_id(spec, load_json(args.raw))

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
            category = raw_entry.get('category')
            tc = raw_entry.get('tc')
        else:
            entry_text = raw_entry
            status_override = None
            category = None
            tc = None

        row = {
            'id': item_id,
            'source': spec['source'],
            'checkpoint': args.checkpoint,
            'status': status_override or spec['status_of'](it),
            'entry': entry_text,
            'src_text': spec['src_text_of'](it),
        }
        # T12（2026-09-07）：entries.json 的值若是物件，category／tc 兩鍵
        # 原樣帶進 batch row，交給 add-batch 一次入庫＋分類＋標 T/C。
        # 純字串 entries（舊格式）沒有這兩鍵可帶，行為完全不變。
        if category is not None:
            row['category'] = category
        if tc is not None:
            row['tc'] = tc
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


def cmd_from_raw(args):
    """站方 detail raw ＋ 狀態檔 → 一次產出提示表＋骨架 JSON＋已在庫標記（A24，2026-09-07）。

    砍呼叫主線第二刀：`inspect` 逐則翻頁改成先看這支印出的提示表；agent
    只需要 Write 一份極小的 `{id: {entry, category, tc}}`（`build --skeleton`
    合併成 batch，見上）。

    **D12（跨批已查標記）**：`--state` 給了才排除——只排除狀態檔裡已經是
    `has_script` 的 id，`pending`／其他任何狀態一律保留（並標 `prev_status`），
    因為 prelim／early access 稿隨時可能補正式稿，機械排除等於永久漏收。
    """
    spec = SITE_SPEC[args.site]
    items = dedup_by_id(spec, load_json(args.raw))

    have = {}
    if args.state:
        state = s2_state.load(args.state)
        have = {i: (v.get('script_status') or '') for i, v in state['items'].items()}

    skeleton = []
    machine_excluded = 0
    already_have = []
    pending_kept = []
    for it in items:
        item_id = spec['id_of'](it)
        if spec['skip_of'](it):
            machine_excluded += 1
            continue

        prev_status = have.get(item_id) if item_id in have else None
        if prev_status == 'has_script':
            already_have.append(item_id)
            continue

        src_text = spec['src_text_of'](it)
        row = {
            'id': item_id,
            'source': spec['source'],
            'checkpoint': args.checkpoint,
            'status': spec['status_of'](it),
            'src_text': src_text,
        }
        row.update(spec['extra_of'](it))
        # entry／category／tc 是 agent 判斷欄位，骨架只留空位——
        # 這支腳本不生成、不翻譯、不判斷 BITE（同 build 開頭的說明）。
        row['entry'] = ''
        row['category'] = ''
        row['tc'] = ''
        if prev_status is not None:
            row['prev_status'] = prev_status
            if prev_status == 'pending':
                pending_kept.append(item_id)

        dur = it.get('dur')
        if dur is None:
            dur = it.get('dur_ms', '')
        sb_count = spec['extra_of'](it).get('sb_count', 0)
        # first150：src_text 正文前 150 字、去換行（提示表用，不是稽核落檔欄位）。
        first150 = re.sub(r'\s+', ' ', src_text).strip()[:150]
        row['hint'] = {
            'head': _title_of_any(it),
            'dur': dur,
            'sb_count': sb_count,
            'first150': first150,
        }
        skeleton.append(row)

    out = args.out
    if not out:
        hhmm = args.checkpoint.split('-')[-1]
        base = os.path.dirname(os.path.abspath(args.raw))
        out = os.path.join(base, f'{args.site}_skeleton_{hhmm}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(skeleton, f, ensure_ascii=False, indent=2)

    # 提示表：#序｜id｜dur｜sb｜head｜first150。累計字元逼近 28,000（跟
    # inspect 全文預算同一個數字，見 INSPECT_TEXT_BUDGET）就分頁，不靜默截斷。
    all_lines = [
        f"#{idx}｜{row['id']}｜{row['hint']['dur']}｜{row['hint']['sb_count']}｜"
        f"{row['hint']['head']}｜{row['hint']['first150']}"
        for idx, row in enumerate(skeleton, 1)
    ]
    pages, cur, cur_len = [], [], 0
    for ln in all_lines:
        ln_len = len(ln) + 1
        if cur and cur_len + ln_len > INSPECT_TEXT_BUDGET:
            pages.append(cur)
            cur, cur_len = [], 0
        cur.append(ln)
        cur_len += ln_len
    pages.append(cur)  # 0 則時也留一頁空的，--page 1 才有東西可選

    page_no = args.page or 1
    if page_no < 1 or page_no > len(pages):
        print(f'✗ --page {page_no} 超出範圍（共 {len(pages)} 頁）', file=sys.stderr)
        sys.exit(1)

    print('\n'.join(pages[page_no - 1]))
    if len(pages) > 1:
        if page_no < len(pages):
            print(f'— 第 {page_no}/{len(pages)} 頁，--page {page_no + 1} 看下一頁 —')
        else:
            print(f'— 第 {page_no}/{len(pages)} 頁（最後一頁）—')

    if already_have:
        print(f'已在庫略過 {len(already_have)} 則：{", ".join(already_have)}', file=sys.stderr)
    if pending_kept:
        print(f'pending 保留 {len(pending_kept)} 則：{", ".join(pending_kept)}', file=sys.stderr)
    if machine_excluded:
        print(f'機械排除 {machine_excluded} 則（見 dump 輸出的排除原因）', file=sys.stderr)
    print(f'骨架已寫 {out}（{len(skeleton)} 則）', file=sys.stderr)


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
    # `edit`（T9，2026-08-25）：RT **detail** 檔的素材編號存在 `edit`，清單檔才是
    # `code`，於是 `SITE_SPEC['rt']['id_of']` 在 detail 上永遠回空字串、掉到這裡
    # 又撿不到，最後變成 `#index`——`--ids` 因此對 RT detail 形同不存在，agent
    # 只剩 `--index` 一則一則翻。0825-0100 那 15 次 `--index N --fields story`
    # 的根因就是這個（既有缺陷，非本次改動造成）。
    for key in ('id', 'code', 'edit', '_id', 'itemid', 'guid'):
        v = item.get(key)
        if not v:
            continue
        s = str(v)
        # ⚠️ `edit` 上游有**退化值**：實測 20260824 六份 rt_detail 裡有五份含裸前綴
        #    `'RT'`（沒有編號），1800 那份 39 筆裡就有 19 筆。撞名的 id 比沒有 id
        #    更糟——`--ids RT` 會一次撈到 19 筆（爆預算）、`dedup-check` 會**靜默**
        #    拿第一個比（比錯還不報錯），而改動前 `'RT'` 不是合法 id、是 fail-loud 的。
        #    1600 那份還有 `RTRT7400` 雙前綴，可見上游值本來就髒。
        if key == 'edit' and not re.search(r'\d', s):
            continue
        return s
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


# ── AP 的一層 nitf 殼：三條查詢路徑共用同一份攤平邏輯（A13，2026-08-18）──
#
# 🔴 **為什麼要抽出來**：AP 詳情 API 的 `script`／`caption` 不是字串，是
# `{'words': 89, 'nitf': '<p>SHOTLIST:</p>…'}` 這種一層 dict。本檔原本有三條路徑
# 各自處理（或不處理）這件事，結果彼此不一致：
#   ✅ `_title_of_any`／`cmd_search --field all`  → 會看穿 `.nitf`
#   ❌ `cmd_inspect --lengths`                    → 只挑 `isinstance(v, str)`，dict 直接漏掉
#   ❌ `cmd_search --field <指名欄位>`             → 同樣只認 str，指名 script 永遠 0 命中
#
# 0818-2200 實錯就是踩這個：AP API **明明成功**、15/15 筆的 `_source.script.nitf`
# 都有完整 SHOTLIST／SOUNDBITE，但 `inspect --lengths` 沒列出 script／caption、
# `search --field script` 回 0 命中，掃帶 agent 兩個訊號都看到「沒有」，於是判定
# 「AP API 缺欄位」，照 13c §1a 退 §1b **逐則開了 14 個詳情頁**——整段白做，
# AP 那站 12 則燒掉 89 次呼叫／10.5 分（前一輪 14 則只要 31 次／5.7 分）。
# ⛔ **工具答錯比沒有工具更糟**：agent 沒有違規，它是照著工具給的答案做判斷的。
# 所以修法是把攤平邏輯收成這兩支共用 helper，不要再讓任何一條路徑自己寫一份。

def _nitf_text(value):
    """AP 一層 dict 殼 → 內文字串；不是這個形狀就回 None。"""
    if isinstance(value, dict) and isinstance(value.get('nitf'), str):
        return value['nitf']
    return None


def flatten_text_fields(item):
    """一筆 item 的所有文字欄位 → `[(欄位名, 文字)]`，含攤平後的 `{k}.nitf`。

    順序：先原生字串欄位，再 `.nitf`——跟 `cmd_search --field all` 原本的行為一致，
    改用本函式後輸出不變（既有測試據此把關）。
    """
    out = [(k, v) for k, v in item.items() if isinstance(v, str)]
    out += [(f'{k}.nitf', t) for k, v in item.items()
            if (t := _nitf_text(v)) is not None]
    return out


def text_field(item, key):
    """查某個具名欄位的文字內容，回傳 `(顯示名, 文字, 狀態)`。

    狀態三分，**呼叫端要能講出不同的話**——0818-2200 的誤導有一半來自
    「欄位不存在」與「欄位在、只是不是字串」共用同一句 `<無此欄位或非文字>`：
      `'str'`     欄位本身就是字串
      `'nitf'`    欄位是 AP 的 dict 殼，已取出 `.nitf`（顯示名會變成 `key.nitf`）
      `'absent'`  真的沒有這個欄位
      `'nontext'` 欄位存在但既非字串也不是 nitf 殼（例如 `shots` 是 list）
    """
    if key not in item:
        return (key, None, 'absent')
    v = item[key]
    if isinstance(v, str):
        return (key, v, 'str')
    t = _nitf_text(v)
    if t is not None:
        return (f'{key}.nitf', t, 'nitf')
    return (key, None, 'nontext')


def _plan_full_detail(shown, fields, site):
    """決定這批 `--fields` 查詢能不能**整批印全文**；塞不下就備妥可直接貼的分批指令。

    回傳 `(cap, note)`：`cap` 是每個欄位的截斷長度，`None`＝不截斷（整批全文）。
    `note` 不是 None 時，呼叫端要原樣印到 stderr。

    為什麼要有這個（T9，2026-08-25）：原本的判準是
    `fields is not None and len(indexed) <= 3`——**只有查 ≤3 筆才印全文**，於是
    「我要看完整 script」在操作上就等於「一次只能查 3 筆」。0825-0100 實測 56 次
    `inspect` 裡 **31 次是一次只看一則**（`ap_detail` 連續 11 次同 `--fields script`、
    `rt_detail` 連續 15 次 `--index N --fields story`，其中兩次參數完全重複），
    每次呼叫 ≈ 296k cache_read ≈ **$0.089**，光這一輪就 ≈ $2.5。

    ⛔ 塞不下時**不靜默截斷**——會明講並印出下一步指令。R15 的教訓是靜默截斷
    會讓 agent 合理地退回逐則查詢，那正是這一刀要消滅的形狀。
    """
    # ⚠️ 量的是**序列化後**的長度，不是 raw `len(v)` 總和——保證要落在真正印出去的
    #    那串位元組上。JSON escape（`\n` 變兩字元、引號）實測讓 NS 型內容膨脹 4.9%，
    #    近飽和時足以把「宣告整批全文」的輸出推破 Bash 的 30k 靜默截斷線。
    #    順帶解掉 dict 欄位（AP 的 nitf 殼）被算成 0 的洞：`json.dumps` 會把整包算進去。
    total_len, fit_ids = 0, []
    for i, it in shown:
        item_id = _dedup_id(site, it, i)
        one = len(json.dumps({k: it.get(k, '<無此欄位>') for k in fields},
                             ensure_ascii=False)) + len(item_id) + 2  # id + \t + \n
        if total_len + one > INSPECT_TEXT_BUDGET:
            break
        fit_ids.append(item_id)
        total_len += one
    if len(fit_ids) == len(shown):
        return None, None
    if not fit_ids:
        # 第一則自己就超過預算（RT 的 TIMELINE 長稿實測有 30,270 字元）。
        # ⛔ 這裡**不能**掉到 200 字元預覽——舊制單則查是印全文的，掉下去等於
        #    agent 再也拿不到這則的內容，是功能退步。改成截到預算為止，
        #    拿到的量跟舊制被工具攔下時差不多，但這次有明講截在哪。
        return INSPECT_TEXT_BUDGET, (
            f'ℹ️ 第一則的 {",".join(fields)} 自己就超過 {INSPECT_TEXT_BUDGET:,} 字元預算，'
            f'已截到預算為止（**不是**全文）。這種長稿逐則查是對的。')
    head = (f'ℹ️ 這 {len(shown)} 筆的 {",".join(fields)} 全文超過 {INSPECT_TEXT_BUDGET:,} '
            f'字元預算，已改印 {INSPECT_PREVIEW_CHARS} 字元預覽（**不是**全文）。')
    # ⚠️ 沒帶 `--site` 時 `_dedup_id` 回退成 `#index`，那不是能貼回 `--ids` 的東西
    #    ——印出來會變成一條**跑不動的**建議指令，比不給建議更糟。
    # ⚠️ 認不出 id 的筆數會是 `#N` 序號——那**也是可以貼回 `--ids` 的**（`cmd_inspect`
    #    一律受理 `#N`），所以不必因此拒絕給建議，照樣印出去就好。
    # 🔴 建議指令必須 **round-trip**：貼回去要剛好撈到這幾筆，不能多。
    #    id 撞名時貼回去會撈到一整群 → 再度爆預算 → 再印同一條壞建議，**不收斂**，
    #    agent 照做只是白燒呼叫，正好是這一刀要救的那條路。寧可不給建議，
    #    也不要給一條跑起來不對的指令。
    want = set(fit_ids)
    hit = sum(1 for i, it in shown if _dedup_id(site, it, i) in want)
    if len(want) != len(fit_ids) or hit != len(fit_ids):
        return INSPECT_PREVIEW_CHARS, (
            f'{head}\n'
            f'   ⚠️ 這個檔的 id 有重複，貼回 `--ids` 會撈到多餘的筆數，'
            f'因此不給分批指令。請改用 `--limit`／`--index` 逐段取。')
    return INSPECT_PREVIEW_CHARS, (
        f'{head}\n'
        f'   要全文請分批，前 {len(fit_ids)} 筆可一次取：\n'
        f'   --ids {",".join(fit_ids)}')


def cmd_inspect(args):
    try:
        items, shell_desc = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    print(f'# {args.raw}：{shell_desc}', file=sys.stderr)

    site = getattr(args, 'site', None)
    # id 與欄位一律走 `_dedup_view` 合併視圖：AP 清單檔是 ES 形狀（欄位包在
    # `_source` 底下、頂層 `_id` 是雜湊），不看穿的話 `--ids AP5467681` 找不到、
    # `--fields` 全回「無此欄位」，agent 只會彈回 python -c（0817-2200 實測，
    # D9 步驟②的前置條件）。
    indexed = [(i, _dedup_view(it) if isinstance(it, dict) else {'value': it})
               for i, it in enumerate(items)]

    if args.index is not None:
        if not (0 <= args.index < len(items)):
            print(f'✗ --index {args.index} 超出範圍（共 {len(items)} 筆，0-based）', file=sys.stderr)
            sys.exit(1)
        indexed = [indexed[args.index]]
    elif args.ids:
        want = set(x.strip() for x in args.ids.split(','))
        # `#N` 序號定址一律受理：id 撲空時本工具自己就是印 `#0…#N`，只認真 id
        # 會讓自己印出來的東西貼不回去（RT detail 補了 `edit` 之後實測到的回歸）。
        indexed = [(i, it) for i, it in indexed
                   if _dedup_id(site, it, i) in want or f'#{i}' in want]
        found = set(_dedup_id(site, it, i) for i, it in indexed)
        found |= set(f'#{i}' for i, _ in indexed)
        missing = want - found
        if missing:
            print(f'⚠️ 找不到這些 id：{", ".join(sorted(missing))}', file=sys.stderr)

    fields = [f.strip() for f in args.fields.split(',')] if args.fields else None
    lengths = getattr(args, 'lengths', False)

    limit = args.limit or 100
    shown, total = indexed[:limit], len(indexed)

    # 全文 vs 預覽改由**字元預算**決定，不再由筆數決定（T9，見 _plan_full_detail）。
    # `cap` 是每欄位截斷長度，None＝整批全文。
    cap, budget_note = (
        _plan_full_detail(shown, fields, site) if (fields and not lengths)
        else (INSPECT_PREVIEW_CHARS, None))

    lines = []
    for i, it in shown:
        item_id = _dedup_id(site, it, i)
        if lengths:
            # 字數模式：只印長度不印內容（例：檢查摘要有沒有超過 150 字）。
            # 這是 D9 查出的工具缺口——以前 agent 只能自己寫 python 數。
            # ⚠️ A13（2026-08-18）：這裡原本只挑 `isinstance(v, str)`，AP 的
            # `script`／`caption` 是 `{'words':N,'nitf':…}` dict，**整個沒被列出**，
            # 讓 agent 以為站方沒給稿。改走 `flatten_text_fields`／`text_field`
            # 共用 helper（見其上方大段說明），三條查詢路徑對齊。
            if fields:
                parts = []
                for k in fields:
                    name, text, state = text_field(it, k)
                    if text is not None:
                        parts.append(f'{name}=len:{len(text)}')
                    elif state == 'nontext':
                        # 跟「沒有這個欄位」講不同的話：欄位在，只是不是文字，
                        # 合起來講會被讀成「站方沒給」——那正是 0818-2200 的誤導源頭。
                        parts.append(f'{k}=<欄位存在但非文字>')
                    else:
                        parts.append(f'{k}=<無此欄位>')
                lines.append(f'{item_id}\t' + ' '.join(parts))
            else:
                flds = [(n, t) for n, t in flatten_text_fields(it)
                        if t and not n.startswith('_')]
                if not flds:
                    lines.append(f'{item_id}\t（無可量長度的文字欄位）')
                else:
                    lines.append(f'{item_id}\t' + ' '.join(
                        f'{n}=len:{len(t)}' for n, t in sorted(flds)))
        elif fields:
            picked = {}
            for k in fields:
                v = it.get(k, '<無此欄位>')
                if isinstance(v, str) and cap and len(v) > cap:
                    v = v[:cap] + '...[略]'
                picked[k] = v
            lines.append(f'{item_id}\t{json.dumps(picked, ensure_ascii=False)}')
        else:
            lines.append(f'{item_id}\t{_title_of_any(it)}')

    print('\n'.join(lines))
    if total > limit:
        print(f'…另 {total - limit} 筆略，用 --limit 調整', file=sys.stderr)
    print(f'共 {len(items)} 筆，本次顯示 {min(total, limit)} 筆', file=sys.stderr)
    if budget_note:
        print(budget_note, file=sys.stderr)
    # 逐則翻閱的觸發點（T9）。比照 A10 v2 的 T/C 覆蓋率閘門：光把「請批次」寫進
    # 規則檔沒有用（0824-2000 實證「載入 ≠ 遵守」），要在**用到的當下**給提示。
    elif fields and total == 1 and len(items) > 1:
        print(f'💡 這次只看了 1 則，同檔還有 {len(items) - 1} 筆。'
              f'`--ids a,b,c` 可一次取多則，總長吃得下 {INSPECT_TEXT_BUDGET:,} 字元'
              f'就整批印全文——分開叫每次都要重付一次 context。', file=sys.stderr)


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
    site = getattr(args, 'site', None)
    hits = []
    for i, raw_it in enumerate(items):
        # 同 inspect：走 `_dedup_view` 看穿 AP 的 `_source` 殼，否則 AP 清單檔
        # 頂層沒有任何字串欄位，search 永遠空手（D9 步驟②前置）。
        it = _dedup_view(raw_it) if isinstance(raw_it, dict) else {}
        item_id = _dedup_id(site, it, i)
        # AP 的標題／內文在 `caption.nitf`／`script.nitf` 這種一層 dict 底下，
        # 一併攤出來搜（A13 起改走共用 helper，見其上方說明）。
        if field_candidates is None:
            fields_to_check = flatten_text_fields(it)
        else:
            # ⚠️ A13：這條**指名欄位**的路徑原本只認 `isinstance(str)`，於是
            # `search --contains SOUNDBITE --field script` 在 AP 檔上永遠 0 命中
            # （script 是 dict）——跟 `--field all` 行為不一致，同一份檔案換個參數
            # 就得到相反的答案。改用 `text_field` 後兩條路徑一致。
            fields_to_check = []
            for k in field_candidates:
                name, text, _ = text_field(it, k)
                if text is not None:
                    fields_to_check.append((name, text))
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

# ENEX／ABC 只在 `concat --site` 的去重用得到（兩站的 raw→候選檔走
# `s2_platform_extract.py`，不經 SITE_SPEC 的 dump／build）。所以**不塞進
# SITE_SPEC**——那份的每個鍵都被 dump／build 當必備欄位讀，補半套只會讓
# `--site abc dump` 死在 KeyError，比現在的 invalid choice 更難查。
# 🔴 2026-09-05（0905-0430）：ABC 進固定輪後，agent 要合併分頁清單時
# `concat --site abc` 回 invalid choice，只能改用不去重的純合併。
PLATFORM_ID_OF = {
    'abc': lambda it: (str(it.get('News Story') or it.get('storyNumber') or '').strip()
                       and 'ABC' + str(it.get('News Story')
                                       or it.get('storyNumber')).strip()),
    'enex': lambda it: (str(it.get('id') or it.get('itemId') or '').strip()
                        and 'ENEX' + str(it.get('id') or it.get('itemId')).strip()
                        .removeprefix('ENEX')),
}


def _site_id_of(site, item, index):
    """有 --site 就走 per-site adapter（RT 用 `code` 不是 `id`），
    沒有就走通用猜測。猜測只在沒指定站別時用，指定了就以規則為準。"""
    if site in PLATFORM_ID_OF:
        return PLATFORM_ID_OF[site](item) or _id_of_any(item, index)
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
    for i, raw_it in enumerate(items):
        # 同 inspect／search：AP 清單檔（ES 形狀）要看穿 `_source`，否則快照
        # 印出的是 `_id` 雜湊，agent 對不回 state 只能自己重造（0817-2200 實錯）。
        it = _dedup_view(raw_it) if isinstance(raw_it, dict) else {}
        item_id = _dedup_id(args.site, it, i)
        desc = _title_of_any(it)
        if not desc:
            # 清單檔常常只有 `code` ＋ `at`（沒有標題欄）。這種時候印剩下的短欄位，
            # 比留一整排空白有用——快照的用途是「當時清單長什麼樣」。
            desc = ' '.join(
                f'{k}={v}' for k, v in it.items()
                if k != 'id' and not k.startswith('_')
                and isinstance(v, (str, int, float, bool))
                and len(str(v)) <= 40 and str(v) != item_id)
        lines.append(f'{item_id}\t{desc}')

    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'快照已寫入 {out}（{len(items)} 筆）')


# 三站清單各自的「上站時間」欄位＋格式。NS `created`＝ISO 帶微秒 UTC（13c/13d §8：
# `created: it.createdDate`）；AP `ts`＝ISO 秒 UTC（13c §2：`ts: s.firstcreated`）；
# RT `at`＝DOM 直接擷取的 `MM/DD/YYYY HH:MM`。
#
# 🔴 **2026-08-31 訂正（獨立 review 抓到、已用真實落檔覆核）**：原本這裡寫
# 「RT `at` 已經是台北當地時間，不要再 +8h」——13c2 §1b 那句「判窗內外用」
# 只是講這個欄位的**用途**，不是講它的**時區**，是我自己誤讀成當地時間，
# 不是規則文件寫錯。實測反證（`20260830/_rt_list_1600.json`，檔案落地時間
# 台北 16:08）：40 筆 `at` 最大值 `08/30/2026 07:57`——比擷取當下早 8 小時
# 11 分。同一輪 AP `ap_list_1600.json`（落地 16:31）`ts` 最大值換算 UTC+8
# 後是 16:27，跟擷取時間吻合。兩站抓的都是「最新 N 筆」，時間窗理應重疊：
# 把 RT 當 UTC 轉換，兩站窗口幾乎完全重合；當成當地時間則整整差 8 小時、
# 等於路透在擷取前連續 8 小時零產出，不合理。**RT `at` 其實也是 UTC**，
# 跟 NS／AP 同一套規則，不要再假設它免轉。
TIMELINE_SPEC = {
    'ns': {'fields': ('created', 'createdDate'), 'utc': True,
           'fmt': '%Y-%m-%dT%H:%M:%S.%fZ'},
    'ap': {'fields': ('ts', 'firstcreated'), 'utc': True,
           'fmt': '%Y-%m-%dT%H:%M:%SZ'},
    'rt': {'fields': ('at',), 'utc': True, 'fmt': '%m/%d/%Y %H:%M'},
}


def _parse_ts(raw_ts, spec):
    """回傳台北當地時間字串 `MM/DD/YYYY HH:MM`，解析失敗回 None（不猜、不吞）。"""
    if not raw_ts:
        return None
    if not spec['utc']:
        return raw_ts.strip() or None
    fmts = [spec['fmt'], '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ',
            '%m/%d/%Y %H:%M']
    for fmt in fmts:
        try:
            dt = datetime.datetime.strptime(raw_ts, fmt) + datetime.timedelta(hours=8)
            return dt.strftime('%m/%d/%Y %H:%M')
        except ValueError:
            continue
    return None


def cmd_timeline(args):
    """把一份 raw 檔轉成「id｜台北當地時間」清單，供跨站對帳（窗內外／有沒有
    銜接落差）用。取代 0730 那種自寫 `_mk_*_snapshot.py` 逐站算時區的臨時腳本——
    三站欄位名與是否要 +8h 全部寫死在 TIMELINE_SPEC，不必每輪重寫換算邏輯。"""
    try:
        items, shell_desc = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)

    spec = TIMELINE_SPEC[args.site]
    rows = []
    no_ts = []
    for i, raw_it in enumerate(items):
        it = _dedup_view(raw_it) if isinstance(raw_it, dict) else {}
        item_id = _dedup_id(args.site, it, i)
        raw_ts = next((it[f] for f in spec['fields'] if it.get(f)), None)
        local = _parse_ts(raw_ts, spec)
        if local is None:
            no_ts.append(item_id)
        rows.append((item_id, local or ''))

    # 依時間排序（沒有時間的排最後，方便一眼看出哪些缺時間）——跟 raw 原始
    # 順序無關，跨站對帳要的是時間軸，不是抽取順序。
    rows.sort(key=lambda r: (r[1] == '', r[1]))

    lines = [f'{iid}|{ts}' for iid, ts in rows]
    out = args.out
    if out:
        with open(out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        print(f'時間軸已寫入 {out}（{len(rows)} 筆，{shell_desc}）', file=sys.stderr)
    for ln in lines:
        print(ln)
    if no_ts:
        print(f'⚠️ {len(no_ts)} 筆解不出時間（欄位缺或格式不符，見 {spec["fields"]}）：'
              f'{", ".join(no_ts[:20])}', file=sys.stderr)


# 各站原始 detail 檔裡，正文欄位的名字（依序嘗試，第一個有內容的勝出）——
# 跟 SITE_SPEC 的 src_text_of 是同一組欄位，只是這裡不強制併成固定格式，
# 讓 fill-src-text 用 raw 的「一個」欄位就好（多欄位ときは join）。
FILL_SRC_FIELDS = {
    'ns': ('desc', 'script'),
    'ap': ('head', 'script'),
    'rt': ('head', 'story'),
}


def cmd_fill_src_text(args):
    """把 raw／detail 檔的正文，依 id 對應填進 batch.json 的 `src_text` 欄位——
    取代 0818/0820/0825/0828/0829 反覆出現的 `_merge_src_*.py`／`_fill_*srctext.py`／
    `_fix_src_*.py` 這批臨時腳本（都是同一件事：raw 有正文、batch 還沒填，逐 id 對應
    貼過去）。**只填空的**，不覆寫 batch 裡已經有內容的 `src_text`（避免蓋掉手動修過
    的原文）。"""
    try:
        raw_items, raw_shell = _load_raw_any(args.raw)
    except ValueError as e:
        print(f'✗ raw 讀取失敗：{e}', file=sys.stderr)
        sys.exit(1)
    try:
        with open(args.batch, encoding='utf-8') as f:
            batch = json.load(f)
    except OSError as e:
        print(f'✗ batch 讀不到：{e}', file=sys.stderr)
        sys.exit(1)
    if not isinstance(batch, list):
        print(f'✗ {args.batch} 頂層不是陣列，不像 add-batch 用的 batch.json', file=sys.stderr)
        sys.exit(1)

    fields = ([f.strip() for f in args.fields.split(',') if f.strip()]
              if args.fields else list(FILL_SRC_FIELDS[args.site]))

    # 保留第一次出現的那筆、重複的丟掉並警告——跟 dedup_by_id／build 同一套
    # 規則（2026-08-31 review 修正：原本後面的會靜默蓋掉前面的，沒有任何提示）。
    raw_by_id = {}
    dup_ids = []
    for i, raw_it in enumerate(raw_items):
        it = _dedup_view(raw_it) if isinstance(raw_it, dict) else {}
        rid = _dedup_id(args.site, it, i)
        if rid in raw_by_id:
            dup_ids.append(rid)
            continue
        raw_by_id[rid] = it
    if dup_ids:
        print(f'⚠️ raw 裡有重複 id，只保留第一次出現的那筆：{", ".join(dup_ids)}',
              file=sys.stderr)

    filled, already, missing = [], [], []
    for item in batch:
        iid = item.get('id')
        if item.get('src_text'):
            already.append(iid)
            continue
        r = raw_by_id.get(iid)
        if not r:
            missing.append(iid)
            continue
        parts = [str(r[f]) for f in fields if r.get(f)]
        if not parts:
            missing.append(iid)
            continue
        item['src_text'] = truncate('\n---\n'.join(parts))
        filled.append(iid)

    out = args.out or args.batch
    with open(out, 'w', encoding='utf-8') as f:
        # indent=2 對齊 build 的輸出格式（2026-08-31 review 修正：原本 indent=1，
        # 就地覆寫時會把整份 batch.json 的排版跟 build 的產物不一致）。
        json.dump(batch, f, ensure_ascii=False, indent=2)

    print(f'已寫入 {out}（raw：{raw_shell}）', file=sys.stderr)
    print(f'填入 {len(filled)} 則：{", ".join(filled) if filled else "（無）"}')
    if already:
        print(f'已有 src_text 未動 {len(already)} 則：{", ".join(already)}', file=sys.stderr)
    if missing:
        print(f'⚠️ raw 裡找不到或欄位都空、沒填到 {len(missing)} 則'
              f'（要嘛 id 對不起來、要嘛 raw 那批本來就沒收這幾則）：'
              f'{", ".join(missing)}', file=sys.stderr)


def cmd_collate_category(args):
    """把一批（或多批）batch.json 裡各則自己標好的 `category`
    （`{"大分類":…, "中主題":…, "小分題":…}`）收成一條可以直接貼給
    `s2_state.py set-category --pairs` 的字串。取代 0810／0827-1000 那種
    `run_setcat_1000.py`／`_tmp_ns_cat.py`——手動把三站 batch 掃過一遍拼字串
    再自己 subprocess 呼叫 set-category 的臨時腳本。**只組字串，不呼叫
    set-category**——送不送、送之前要不要再看一眼，仍是 agent 的判斷。"""
    pairs = []
    skipped = []
    for path in args.batches:
        try:
            with open(path, encoding='utf-8') as f:
                items = json.load(f)
        except OSError as e:
            print(f'✗ 讀不到 {path}：{e}', file=sys.stderr)
            sys.exit(1)
        if not isinstance(items, list):
            print(f'✗ {path} 頂層不是陣列，不像 batch.json', file=sys.stderr)
            sys.exit(1)
        for item in items:
            iid = item.get('id')
            cat = item.get('category') or {}
            big, mid, sub = cat.get('大分類'), cat.get('中主題'), cat.get('小分題')
            if not (big and mid):
                skipped.append(iid or f'({path} 裡無 id 的一筆)')
                continue
            seg = f'{big}/{mid}' + (f'/{sub}' if sub else '')
            pairs.append(f'{iid}={seg}')

    if not pairs:
        print('✗ 一則可用的 category 都沒收到——batch.json 裡的 items 要先自己標好'
              ' `category` 欄位，這支只負責收集、不負責判斷分類', file=sys.stderr)
        sys.exit(1)

    print(';'.join(pairs))
    print(f'共 {len(pairs)} 則可送出', file=sys.stderr)
    if skipped:
        print(f'⚠️ {len(skipped)} 則缺 category（或缺大分類／中主題），沒收進來：'
              f'{", ".join(str(s) for s in skipped)}', file=sys.stderr)


def cmd_concat(args):
    """把兩份以上的 json 陣列檔案（分頁清單、多來源分批的 batch 等）合併成一份。
    取代 0813／0814／0820／0821／0825／0827／0829／0831 反覆出現的
    `python -c "a=json.load(...); b=json.load(...); json.dump(a+b, ...)"`
    這批臨時合併腳本——出現頻率比 fill-src-text 還高（23 個命中／約 9-10 個
    不同日期），形狀卻更單純：純粹合併陣列，頂多再去重，沒有 timeline 那種
    per-site 時區假設要猜（那次猜錯過一次，這支刻意不猜任何語意）。

    給 `--site` 才會去重（保留第一次出現的 id，其餘丟棄並警告）；不給就是
    純合併、保留全部（例如合併 batch.json 這種本來就不該去重的用途）。"""
    all_items = []
    shells = []
    for path in args.files:
        try:
            items, shell_desc = _load_raw_any(path)
        except ValueError as e:
            print(f'✗ 讀取失敗 {path}：{e}', file=sys.stderr)
            sys.exit(1)
        shells.append(f'{os.path.basename(path)}（{shell_desc}）')
        all_items.extend(items)

    dup_ids = []
    if args.site:
        seen = {}
        kept = []
        for i, it in enumerate(all_items):
            view = _dedup_view(it) if isinstance(it, dict) else {}
            rid = _dedup_id(args.site, view, i)
            if rid in seen:
                dup_ids.append(rid)
                continue
            seen[rid] = True
            kept.append(it)
        all_items = kept

    out = args.out
    if out:
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)
        print(f'已寫入 {out}（{len(all_items)} 筆，來源：{"、".join(shells)}）', file=sys.stderr)
    else:
        print(json.dumps(all_items, ensure_ascii=False, indent=2))
        print(f'共 {len(all_items)} 筆（來源：{"、".join(shells)}）', file=sys.stderr)
    if dup_ids:
        print(f'⚠️ 給了 --site，去重時丟掉 {len(dup_ids)} 個重複 id（保留第一次出現的）：'
              f'{", ".join(dup_ids)}', file=sys.stderr)


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
    不是 ES 的 `_id` 雜湊——比對時要用人看得懂、跟 state 對得起來的那個。
    沒給 --site 但看得到 `editorialid` 時也走 AP 規則：那個欄位只有 AP 的
    ES 清單檔才有，靠它自動判站比回傳雜湊有用（D9 步驟②前置）。"""
    view = _dedup_view(item)
    if site in (None, 'ap') and view.get('editorialid'):
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
    p_build.add_argument('--skeleton', help='from-raw 產的骨架 json；給了就以它為底，'
                          '--entries 只需 {id:{entry,category,tc}} 覆蓋（A24）')
    p_build.set_defaults(func=cmd_build)

    p_fr = sub.add_parser('from-raw', help='raw ＋ 狀態檔一次產出提示表＋骨架 JSON＋已在庫標記（D12，A24）')
    p_fr.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_fr.add_argument('--raw', required=True)
    p_fr.add_argument('--checkpoint', required=True)
    p_fr.add_argument('--state', help='狀態檔路徑；給了才排除已 has_script 的 id'
                       '（D12：pending／其他狀態一律保留並標 prev_status）')
    p_fr.add_argument('--out', help='骨架 json 路徑；不給就用 raw 所在目錄組 {site}_skeleton_{HHMM}.json')
    p_fr.add_argument('--page', type=int, help='提示表分頁（每頁 ≤28,000 字元），預設第 1 頁')
    p_fr.set_defaults(func=cmd_from_raw)

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
    p_inspect.add_argument('--site', choices=['ns', 'ap', 'rt'],
                           help='per-site id 規則（RT 是 code；AP 清單檔自動看穿 _source）')
    p_inspect.add_argument('--lengths', action='store_true',
                           help='只印各欄位字數不印內容（檢查摘要 150 字上限這類需求）')
    p_inspect.set_defaults(func=cmd_inspect)

    p_search = sub.add_parser('search', help='在 raw 檔的指定欄位裡找關鍵字')
    p_search.add_argument('raw')
    p_search.add_argument('--contains', required=True)
    p_search.add_argument('--field', default='all', choices=['script', 'story', 'head', 'all'])
    p_search.add_argument('--limit', type=int, help='最多顯示幾筆命中，預設 100')
    p_search.add_argument('--site', choices=['ns', 'ap', 'rt'],
                          help='per-site id 規則（RT 是 code；AP 清單檔自動看穿 _source）')

    p_snap = sub.add_parser('snapshot', help='把 raw 檔壓成純文字稽核快照（不覆寫舊檔）')
    p_snap.add_argument('raw')
    p_snap.add_argument('--site', choices=['ns', 'ap', 'rt'], help='指定站別才用得到 per-site id 規則（RT 是 code）')
    p_snap.add_argument('--checkpoint', help='用來組預設檔名 _audit_{site}_{HHMM}.txt')
    p_snap.add_argument('--out', help='輸出路徑；不給就用 --checkpoint 組')
    p_snap.set_defaults(func=cmd_snapshot)

    p_tl = sub.add_parser('timeline', help='raw 檔轉成「id｜台北當地時間」清單，供跨站對帳窗內外用')
    p_tl.add_argument('raw')
    p_tl.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_tl.add_argument('--out', help='同時存成檔案（不給只印到 stdout）')
    p_tl.set_defaults(func=cmd_timeline)

    p_fill = sub.add_parser('fill-src-text', help='raw／detail 檔的正文依 id 填進 batch.json 的 src_text（只填空的）')
    p_fill.add_argument('--batch', required=True)
    p_fill.add_argument('--raw', required=True)
    p_fill.add_argument('--site', required=True, choices=['ns', 'ap', 'rt'])
    p_fill.add_argument('--fields', help='raw 裡取正文的欄位，逗號分隔、依序取第一個有內容的；不給用預設 (desc/script、head/script、head/story)')
    p_fill.add_argument('--out', help='輸出路徑；不給就地覆寫 --batch')
    p_fill.set_defaults(func=cmd_fill_src_text)

    p_cat = sub.add_parser('collate-category', help='把 batch.json 裡各則的 category 收成 set-category --pairs 吃得下的字串')
    p_cat.add_argument('batches', nargs='+', help='一或多個 batch.json（例如三站各一個）')
    p_cat.set_defaults(func=cmd_collate_category)

    p_cat_c = sub.add_parser('concat', help='合併兩份以上 json 陣列檔案（分頁清單、多來源分批 batch）')
    p_cat_c.add_argument('files', nargs='+', help='兩個以上的檔案（裸陣列或已知殼型皆可）')
    p_cat_c.add_argument('--site', choices=['ns', 'ap', 'rt', 'enex', 'abc'],
                         help='給了才去重（保留第一次出現的 id）；不給就純合併。'
                              'enex／abc 只有這個子指令支援（其餘子指令走 SITE_SPEC，不含這兩站）')
    p_cat_c.add_argument('--out', help='輸出路徑；不給就印到 stdout')
    p_cat_c.set_defaults(func=cmd_concat)

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
