#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scoped 1259 步驟 6：_load_raw_any → RawLoadResult 與 11 個呼叫端契約。

用法：python -X utf8 scripts/test_s2_raw_loader.py
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

spec = importlib.util.spec_from_file_location(
    'bp', os.path.join(HERE, 's2_batch_prep.py'))
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)

import s2_material_schema as M  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

TMP = tempfile.mkdtemp(prefix='s2_raw_loader_')
results = []


def check(name, cond, extra=''):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}{(" -> " + str(extra)) if extra else ""}')


def write_json(name, obj):
    p = os.path.join(TMP, name)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


def write_text(name, text):
    p = os.path.join(TMP, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    return p


def _offload_shell(payload_text):
    return [{'type': 'text', 'text': f'### Result\n{payload_text}\n### Page 1'}]


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def run(fn, args):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            fn(args)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    return out.getvalue() + err.getvalue(), code


def load_ok(path):
    try:
        return bp._load_raw_any(path), None
    except Exception as e:
        return None, e


# ── selector（schema，零 I/O）────────────────────────────────
key, val = M.select_payload_key({'entries': [], 'items': [{'id': 1}]})
check('selector：entries 存在即使空也贏過 items',
      key == 'entries' and val == [])

key, val = M.select_payload_key({'Items': [{'id': 'A'}], 'count': 2})
check('selector：Items 保留大小寫', key == 'Items' and len(val) == 1)

key, err = M.select_payload_key({'Items': {'not': 'list'}, 'items': [1]})
check('selector：高順位鍵型別錯不往下掉',
      key is None and err is not None)


# ── RawLoadResult 回傳型別與形狀 ─────────────────────────────
p_bare = write_json('bare.json', [{'id': 'A'}])
r, e = load_ok(p_bare)
check('_load_raw_any 回 RawLoadResult（裸陣列）',
      type(r).__name__ == 'RawLoadResult', type(r).__name__ if r else e)
if r is not None and hasattr(r, 'root_shape'):
    check('bare_list shape', r.root_shape == 'bare_list' and r.payload_key is None
          and r.envelope is None)
else:
    check('bare_list shape', False, 'no root_shape')

p_items = write_json('items_env.json', {
    'Items': [{'id': 'AP1'}], 'count': 2, 'checkpoint': '0917-1300',
})
r, e = load_ok(p_items)
check('dict_envelope 回 RawLoadResult',
      type(r).__name__ == 'RawLoadResult', type(r).__name__ if r else e)
if r is not None and hasattr(r, 'payload_key'):
    check('payload_key 精確為 Items', r.payload_key == 'Items')
    check('root_shape=dict_envelope', r.root_shape == 'dict_envelope')
    check('envelope 是完整原始 root（含 count）',
          isinstance(r.envelope, dict) and r.envelope.get('count') == 2
          and 'Items' in r.envelope)
    check('envelope_meta 不含 payload_key',
          'Items' not in r.envelope_meta and r.envelope_meta.get('count') == 2)
else:
    check('payload_key 精確為 Items', False)
    check('root_shape=dict_envelope', False)
    check('envelope 是完整原始 root（含 count）', False)
    check('envelope_meta 不含 payload_key', False)

p_empty_entries = write_json('empty_entries.json', {
    'entries': [], 'items': [{'id': 'should_not_win'}],
})
r, e = load_ok(p_empty_entries)
if r is not None and hasattr(r, 'payload_key'):
    check('{entries:[], items:[...]} 選 entries 即使空',
          r.payload_key == 'entries' and r.items == [])
else:
    check('{entries:[], items:[...]} 選 entries 即使空', False,
          e or type(r).__name__)

p_wrong = write_json('wrong_type.json', {
    'Items': {'nested': True}, 'items': [{'id': 1}],
})
r, e = load_ok(p_wrong)
check('高順位鍵型別錯 → loader 失敗（不吃 items）',
      r is None, type(r).__name__ if r is not None else '')


# ── with_items 只換 payload_key，Items 維持 Items ────────────
base = M.RawLoadResult(
    items=[{'id': 'A'}], shell_desc='x', root_shape='dict_envelope',
    payload_key='Items', envelope={'Items': [{'id': 'A'}], 'count': 2})
w = base.with_items([{'id': 'A'}, {'id': 'B'}])
check('with_items 仍用 Items 鍵',
      'Items' in w.envelope and 'entries' not in w.envelope
      and len(w.envelope['Items']) == 2 and w.envelope['count'] == 2)


# ── offload：envelope 是內層 dict，不是 display 殼 ───────────
inner = {'items': [{'id': 'RT1'}], 'boxFound': True, 'count': 1}
p_off = write_json('offload.json', _offload_shell(json.dumps(inner)))
r, e = load_ok(p_off)
if r is not None and hasattr(r, 'root_shape'):
    check('offload_dict_envelope', r.root_shape == 'offload_dict_envelope')
    check('offload envelope 是內層 dict 不是 type/text 殼',
          isinstance(r.envelope, dict) and r.envelope.get('boxFound') is True
          and 'type' not in r.envelope and r.payload_key == 'items')
else:
    check('offload_dict_envelope', False, e)
    check('offload envelope 是內層 dict 不是 type/text 殼', False)

p_off_bare = write_json('offload_bare.json',
                        _offload_shell(json.dumps([{'id': 'X'}])))
r, e = load_ok(p_off_bare)
if r is not None and hasattr(r, 'root_shape'):
    check('offload_bare_list', r.root_shape == 'offload_bare_list'
          and r.payload_key is None and r.envelope is None)
else:
    check('offload_bare_list', False, e)


# ── NS pipe text ────────────────────────────────────────────
p_ns = write_text('ns_list.json', 'SN-1MO|2026-09-17\nSE-005WE|2026-09-16\n')
r, e = load_ok(p_ns)
if r is not None and hasattr(r, 'root_shape'):
    check('ns_pipe_text', r.root_shape == 'ns_pipe_text'
          and r.payload_key is None and r.envelope is None
          and len(r.items) == 2)
else:
    check('ns_pipe_text', False, e)


# ── unwrap：stderr 列出將移除的 metadata keys；stdout 仍是裸陣列 ─
p_un = write_json('unwrap_meta.json', {
    'Items': [{'id': 'A'}], 'count': 9, 'checkpoint': '0917-1300',
})
out_un = os.path.join(TMP, 'unwrapped.json')
o, c = run(bp.cmd_unwrap, Args(raw=p_un, out=out_un))
check('unwrap exit 0', c == 0, o)
check('unwrap 輸出仍是裸陣列',
      os.path.exists(out_un) and isinstance(json.load(open(out_un, encoding='utf-8')), list))
check('unwrap stderr 列出將移除的 metadata keys',
      'count' in o and 'checkpoint' in o and 'metadata' in o.lower() or '移除' in o,
      o)


# ── snapshot：envelope checkpoint 與 CLI 衝突 ───────────────
p_snap = write_json('snap_cp.json', {
    'items': [{'code': 'RT1', 'head': 'h'}],
    'checkpoint': '0917-1300',
})
snap_out = os.path.join(TMP, 'snap_conflict.txt')
o, c = run(bp.cmd_snapshot, Args(
    raw=p_snap, site='rt', checkpoint='0817-1600', out=snap_out))
check('snapshot checkpoint 衝突 exit 非 0', c not in (0, None), c)
check('snapshot 衝突不寫檔', not os.path.exists(snap_out), o)


# ── timeline：有 context 才印三行標頭 ────────────────────────
p_tl = write_json('tl_ctx.json', {
    'items': [{'id': 'AP1', 'ts': '2026-09-17T04:00:00Z'}],
    'checkpoint': '0917-1300',
    'checkpoint_label': '補漏',
    'run_id': '2fc482da-2bc8-4e9e-b43a-55922e17dd3e',
})
o, c = run(bp.cmd_timeline, Args(raw=p_tl, site='ap', out=None))
check('timeline 有 context 時印三行標頭',
      c == 0 and '# checkpoint:' in o and '# checkpoint_label:' in o
      and '# run_id:' in o, o[:400])

p_tl_bare = write_json('tl_bare.json', [
    {'id': 'AP2', 'ts': '2026-09-17T04:00:00Z'},
])
o, c = run(bp.cmd_timeline, Args(raw=p_tl_bare, site='ap', out=None))
check('timeline 無 context 不印三行標頭',
      c == 0 and '# checkpoint:' not in o, o[:200])


# ── fill-src-text：Items 殼 round-trip ──────────────────────
p_fill_raw = write_json('fill_raw.json', [
    {'id': 'AP1', 'head': 'H', 'script': 'BODY'},
])
p_fill_batch = write_json('fill_batch.json', {
    'Items': [{'id': 'AP1', 'src_text': '', 'entry': 'x'}],
    'count': 1,
})
p_fill_out = os.path.join(TMP, 'fill_out.json')
o, c = run(bp.cmd_fill_src_text, Args(
    raw=p_fill_raw, batch=p_fill_batch, site='ap', fields=None, out=p_fill_out))
check('fill-src-text Items 殼成功', c == 0, o)
if os.path.exists(p_fill_out):
    got = json.load(open(p_fill_out, encoding='utf-8'))
    check('fill-src-text with_items 仍用 Items',
          isinstance(got, dict) and 'Items' in got and 'entries' not in got
          and got.get('count') == 1 and got['Items'][0].get('src_text'))
else:
    check('fill-src-text with_items 仍用 Items', False, 'no out')


# ── concat：未知 metadata 型別敏感 deep-equal；衝突先 exit 2 ─
p_ca = write_json('ca.json', {
    'entries': [{'id': 'A'}],
    'checkpoint': '0917-1300',
    'extra': {'k': 1},
})
p_cb = write_json('cb.json', {
    'entries': [{'id': 'B'}],
    'checkpoint': '0917-1300',
    'extra': {'k': 2},
})
p_cout = os.path.join(TMP, 'concat_conflict.json')
o, c = run(bp.cmd_concat, Args(files=[p_ca, p_cb], site=None, out=p_cout))
check('concat 未知 key 值不同 → exit 2', c == 2, c)
check('concat 衝突列 key 與兩路徑與 JSON 值',
      'extra' in o and 'ca.json' in o and 'cb.json' in o
      and '{"k": 1}' in o.replace(' ', '') or '"k": 1' in o or '"k":1' in o, o)
check('concat 衝突不寫 output', not os.path.exists(p_cout))

p_cc = write_json('cc.json', {
    'entries': [{'id': 'C'}],
    'checkpoint': '0917-1300',
    'extra': {'k': 1},
    'new_topics': {'甲': {'n': 1}, '乙': {'n': 2}},
})
p_cd = write_json('cd.json', {
    'entries': [{'id': 'D'}],
    'checkpoint': '0917-1300',
    'extra': {'k': 1},
    'new_topics': {'乙': {'n': 2}, '丙': {'n': 3}},
})
p_cmerge = os.path.join(TMP, 'concat_ok.json')
o, c = run(bp.cmd_concat, Args(files=[p_cc, p_cd], site=None, out=p_cmerge))
check('concat 相同 extra + new_topics 依 key 合併', c == 0, o)
if os.path.exists(p_cmerge):
    m = json.load(open(p_cmerge, encoding='utf-8'))
    check('concat 輸出仍是 entries 殼', 'entries' in m and len(m['entries']) == 2)
    check('concat new_topics 聯集',
          set((m.get('new_topics') or {}).keys()) == {'甲', '乙', '丙'})
    check('concat extra 保留單一值', m.get('extra') == {'k': 1})
else:
    check('concat 輸出仍是 entries 殼', False)
    check('concat new_topics 聯集', False)
    check('concat extra 保留單一值', False)

p_ce = write_json('ce.json', {
    'entries': [{'id': 'E'}], 'checkpoint': '0917-1300',
})
p_cf = write_json('cf.json', {
    'entries': [{'id': 'F'}], 'checkpoint': '0917-1400',
})
p_ccp = os.path.join(TMP, 'concat_cp.json')
o, c = run(bp.cmd_concat, Args(files=[p_ce, p_cf], site=None, out=p_ccp))
check('concat checkpoint 不一致 exit 2', c == 2 and not os.path.exists(p_ccp), o)

p_cg = write_json('cg.json', {
    'entries': [{'id': 'G'}],
    'new_topics': {'甲': {'n': 1}},
})
p_ch = write_json('ch.json', {
    'entries': [{'id': 'H'}],
    'new_topics': {'甲': {'n': 9}},
})
p_cnt = os.path.join(TMP, 'concat_nt.json')
o, c = run(bp.cmd_concat, Args(files=[p_cg, p_ch], site=None, out=p_cnt))
check('concat new_topics 同 key 內容不同 exit 2',
      c == 2 and not os.path.exists(p_cnt), o)

p_ci = write_json('ci.json', {'Items': [{'id': 'I'}]})
p_cj = write_json('cj.json', {'entries': [{'id': 'J'}]})
p_cshape = os.path.join(TMP, 'concat_shape.json')
o, c = run(bp.cmd_concat, Args(files=[p_ci, p_cj], site=None, out=p_cshape))
check('concat payload_key 不相容 exit 2',
      c == 2 and not os.path.exists(p_cshape), o)

p_ck = write_json('ck.json', {
    'entries': [{'id': 'K'}],
    'advisory_issues': [
        {'code': 'X', 'site': 'AP', 'id': '1', 'message': 'a'},
    ],
})
p_cl = write_json('cl.json', {
    'entries': [{'id': 'L'}],
    'advisory_issues': [
        {'code': 'X', 'site': 'AP', 'id': '1', 'message': 'a'},
        {'code': 'Y', 'site': 'RT', 'id': '2', 'message': 'b'},
    ],
})
p_cadv = os.path.join(TMP, 'concat_adv.json')
o, c = run(bp.cmd_concat, Args(files=[p_ck, p_cl], site=None, out=p_cadv))
check('concat advisory_issues 聯集去重', c == 0, o)
if os.path.exists(p_cadv):
    m = json.load(open(p_cadv, encoding='utf-8'))
    adv = m.get('advisory_issues') or []
    check('concat advisory 2 筆（去重後）', len(adv) == 2, adv)
else:
    check('concat advisory 2 筆（去重後）', False)


# ── json_values_equal（schema）────────────────────────────────
if hasattr(M, 'json_values_equal'):
    check('json_values_equal dict 鍵序無關',
          M.json_values_equal({'a': 1, 'b': 2}, {'b': 2, 'a': 1}))
    check('json_values_equal list 順序有關',
          not M.json_values_equal([1, 2], [2, 1]))
    check('json_values_equal 1 vs 1.0 型別不同',
          not M.json_values_equal(1, 1.0))
    check('json_values_equal missing 與 null 不相等（None vs 缺鍵由呼叫端處理）',
          not M.json_values_equal(None, 0))
else:
    check('json_values_equal dict 鍵序無關', False, 'missing helper')
    check('json_values_equal list 順序有關', False, 'missing helper')
    check('json_values_equal 1 vs 1.0 型別不同', False, 'missing helper')
    check('json_values_equal missing 與 null 不相等（None vs 缺鍵由呼叫端處理）', False)


# ── compare --json-result ────────────────────────────────────
p_raw = write_json('cmp_raw.json', {
    'items': [
        {'code': 'RT1001', 'head': 'one'},
        {'code': 'RT1002', 'head': 'two'},
    ],
})
FULL = {'source': 'RT', 'checkpoint': '0917-1300', 'status': 'has_script',
        'entry': '◆', 'src_text': 'HEAD: x'}
p_batch_ok = write_json('cmp_ok.json', {
    'entries': [dict(id='RT1001', **FULL), dict(id='RT1002', **FULL)],
    'advisory_issues': [{'code': 'OLD', 'site': 'RT', 'id': 'RT1001', 'message': 'keep'}],
})
p_jr = os.path.join(TMP, 'cmp.json')
o, c = run(bp.cmd_compare, Args(
    raw=p_raw, batch=p_batch_ok, site='rt', require=None, json_result=p_jr))
check('compare 乾淨 exit 0', c == 0, o)
check('compare --json-result 寫出', os.path.exists(p_jr), o)
if os.path.exists(p_jr):
    doc = json.load(open(p_jr, encoding='utf-8'))
    check('compare json schema_version', doc.get('schema_version') == 1)
    for side in ('raw', 'batch'):
        block = doc.get(side) or {}
        check(f'compare json {side} 含 shell/root_shape/payload_key/metadata',
              set(block) >= {'shell', 'root_shape', 'payload_key', 'metadata'})
    check('compare json 頂層 advisory 先複製 batch 再去重',
          any(a.get('code') == 'OLD' for a in (doc.get('advisory_issues') or [])))
else:
    check('compare json schema_version', False)
    check('compare json raw 含 shell/root_shape/payload_key/metadata', False)
    check('compare json batch 含 shell/root_shape/payload_key/metadata', False)
    check('compare json 頂層 advisory 先複製 batch 再去重', False)

p_batch_adv = write_json('cmp_adv.json', [
    dict(id='RT1001', **FULL),
    {k: v for k, v in dict(id='RT1002', **FULL).items() if k != 'src_text'},
])
p_jr2 = os.path.join(TMP, 'cmp_adv.jsonl')  # path
p_jr2 = os.path.join(TMP, 'cmp_adv_result.json')
o, c = run(bp.cmd_compare, Args(
    raw=p_raw, batch=p_batch_adv, site='rt', require=None, json_result=p_jr2))
check('compare AP/RT 缺 src_text 預設 advisory、非 blocking',
      c == 0 and '無差異' in o, f'code={c}\n{o}')
if os.path.exists(p_jr2):
    doc = json.load(open(p_jr2, encoding='utf-8'))
    adv_codes = [a.get('code') for a in (doc.get('advisory_issues') or [])]
    check('compare json 含 SRC_TEXT_MISSING advisory',
          'SRC_TEXT_MISSING' in adv_codes, adv_codes)
    check('compare json issues 不含缺 src_text blocking',
          not any('src_text' in str(x).lower() and x.get('kind') == 'missing_field'
                  for x in (doc.get('issues') or []) if isinstance(x, dict)))
else:
    check('compare json 含 SRC_TEXT_MISSING advisory', False)
    check('compare json issues 不含缺 src_text blocking', False)

o, c = run(bp.cmd_compare, Args(
    raw=p_raw, batch=p_batch_adv, site='rt', require='src_text', json_result=None))
check('--require src_text 把 missing 升 blocking',
      c == 2 and '缺 src_text' in o, f'code={c}\n{o}')

p_ns_raw = write_json('cmp_ns_raw.json', [{'id': 'SN-1MO'}])
p_ns_batch = write_json('cmp_ns_batch.json', [{
    'id': 'SN-1MO', 'source': 'NS', 'checkpoint': '0917-1300',
    'status': 'has_script', 'entry': '◆', 'src_text': '',
}])
o, c = run(bp.cmd_compare, Args(
    raw=p_ns_raw, batch=p_ns_batch, site='ns', require=None, json_result=None))
check('compare NS 缺 src_text 維持 failure',
      c == 2, f'code={c}\n{o}')


# ── platform_bridge 不再 tuple unpack ───────────────────────
import s2_platform_bridge as br  # noqa: E402
p_enex = write_json('enex_items.json', {
    'items': [{'id': 'ENEX1', 'desc': 'hello', 'title': 't'}],
})
try:
    items = br._load_items(p_enex)
    check('platform_bridge._load_items 不因 RawLoadResult 炸掉',
          isinstance(items, list) and items[0].get('id') == 'ENEX1')
except Exception as ex:
    check('platform_bridge._load_items 不因 RawLoadResult 炸掉', False, ex)


shutil.rmtree(TMP, ignore_errors=True)
print(f'\nPASS={sum(results)} FAIL={len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
