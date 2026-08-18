#!/usr/bin/env python3
"""s2_token_metrics.py 的驗證測試（MASTER A1）。

三件事：
  1. **分桶不變量**——用真實 transcript replay，逐一驗
     `sum(tool_calls_by_name) == tool_calls`。分桶規則改壞（少一條 elif、
     關鍵字打錯）不會報錯，只會讓某一桶悄悄變 0，這個等式是唯一的守門員。
  2. **子指令 token 邊界**——`add` 不可以誤配到 `add-batch`、
     `set-top` 不可以誤配到 `set-topic-order`。
  3. **版本指紋**——五個規則檔都要抓得到 sha，抓不到會記 null（看得出來），
     而不是靜默省略。

用法：
    python test_s2_token_metrics.py                    # 自動找最近的 transcript 目錄
    python test_s2_token_metrics.py --transcript-dir <路徑>
"""
import argparse
import glob
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'tm', os.path.join(HERE, 's2_token_metrics.py'))
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

results = []


def check(name, cond, extra=''):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}{(" → " + extra) if extra else ""}')


# ── 2. 子指令 token 邊界（不需要 transcript，先跑）──
for cmd, want in (
    ('python scripts/s2_state.py add-batch --entries x.json', 's2_state:add-batch'),
    ('python scripts/s2_state.py add --id X', 's2_state:add'),
    ('python scripts/s2_state.py set-topic-order --cat 天氣', 's2_state:set-topic-order'),
    ('python scripts/s2_state.py set-top checkpoint 0817-1600', 's2_state:set-top'),
    ('python scripts/s2_state.py needs-review add --id X', 's2_state:needs-review'),
    ('python -c "import json; json.load(open(1))"', 'python -c:json'),
    ('python -c "print(len(x))"', 'python -c:length-check'),
    ('python scripts/s2_batch_prep.py inspect raw.json', 's2_batch_prep.py'),
    ('python scripts/s2_render.py --file x.json', 's2_render.py'),
    ('ls -la', 'Bash（其他）'),
):
    got = tm.classify_bash_tool(cmd)
    check(f'分桶：{want}', got == want, f'實得 {got}')

# ── 2b. 檔名 token 判站（MASTER A1，0430/0730 體檢發現）──
for file_hint, want in (
    ('G:/.../20260817/ns_batch_0430.json', 'NS'),   # 站名在前，兩側不夾底線
    ('G:/.../20260817/batch_ns_0730.json', 'NS'),   # 站名在中，兩側夾底線（舊字串比對已接得到）
    ('G:/.../20260817/ap_batch_0430.json', 'AP'),
    ('G:/.../20260817/batch_ap_0730.json', 'AP'),
    ('G:/.../20260817/rt_batch_0430.json', 'RT'),
    ('G:/.../20260817/batch_rt_0730.json', 'RT'),
    ('G:/.../20260817/rt_details_0430.json', 'RT'),
    ('cd E && python scripts/s2_state.py get --id AP4678987', None),   # id 不是獨立 token，不准誤判
    ('G:/.../20260817/apply_config.json', None),                      # 'apply' 整串，不是 'ap'
    ('G:/.../0817-s2-state.json', None),                               # 純狀態檔路徑無站名
):
    got = tm._site_from_filename(file_hint)
    check(f'檔名判站：{file_hint[-40:]} → {want}', got == want, f'實得 {got}')

# classify_phase 仍保留舊的字串比對優先，檔名 token 只是新的 fallback
check('classify_phase 舊 URL 關鍵字比對不受影響（NS）',
      tm.classify_phase('Bash', '{"command": "curl newsource.ns.cnn.com"}') == 'NS')
check('classify_phase 站名關鍵字仍優先於「分類」關鍵字判斷順序不變',
      tm.classify_phase('Bash', '{"command": "python s2_state.py list-topics"}') == '分類')
check('classify_phase 新 fallback：Write 到 ns_batch_0430.json 直接判 NS（不必靠繼承）',
      tm.classify_phase('Write', '{"file_path": "x"}', 'G:/x/ns_batch_0430.json') == 'NS')


# ── 2c. 時段回看重歸屬（長 gap＋下一筆直接命中別站才回看，MASTER A1）──
def synth_transcript(path, calls):
    """calls: [(offset_seconds, tool_name, command_or_filepath_kwargs), ...]
    每筆自動組一行 assistant tool_use＋usage，時間戳用 offset 累加。"""
    base = '2026-08-18T00:00:00.000Z'
    from datetime import datetime, timedelta
    t0 = datetime.fromisoformat(base.replace('Z', '+00:00'))
    with open(path, 'w', encoding='utf-8') as f:
        for i, (offset, name, inp) in enumerate(calls):
            ts = (t0 + timedelta(seconds=offset)).isoformat().replace('+00:00', 'Z')
            line = {
                'timestamp': ts,
                'message': {
                    'id': f'msg{i}',
                    'usage': {'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0,
                              'output_tokens': 0, 'input_tokens': 0},
                    'content': [{'type': 'tool_use', 'id': f't{i}', 'name': name, 'input': inp}],
                },
            }
            f.write(json.dumps(line, ensure_ascii=False) + '\n')
        # 收尾時間戳（last_ts）：最後一筆呼叫後 5 秒
        last_ts = (t0 + timedelta(seconds=calls[-1][0] + 5)).isoformat().replace('+00:00', 'Z')
        f.write(json.dumps({'timestamp': last_ts, 'message': {}}) + '\n')


TMP2 = tempfile.mkdtemp(prefix='s2_tm_test_')

# 情境 A：直接命中分類（list-topics）後長 gap（90s）→ 下一筆直接命中 NS（Write ns_batch）
# 對應 0818-0430 實錯：list-topics 本身就是直接命中，但後面的長思考其實在組 NS 稿。
p = os.path.join(TMP2, 'a.jsonl')
synth_transcript(p, [
    (0, 'Bash', {'command': 'python s2_state.py list-topics --compact'}),
    (90, 'Write', {'file_path': 'G:/x/ns_batch_0430.json', 'content': '...'}),
    (91, 'Bash', {'command': 'echo done'}),
])
r = tm.measure(p)
check('情境A：長 gap＋下一筆直接 NS → 回看重歸屬，分類時間清空',
      r['phases'].get('分類', {}).get('minutes', 0) == 0, str(r['phases']))
check('情境A：90 秒回看重歸屬後算進 NS', r['phases'].get('NS', {}).get('minutes', 0) >= 1.4,
      str(r['phases'].get('NS')))

# 情境 B：繼承分類（show --mid，不含站名關鍵字）後長 gap → 下一筆直接命中 NS
# 對應 0818-0730 實錯：list-topics 直接命中在更早之前，show --mid 本身是靠繼承來的分類。
p = os.path.join(TMP2, 'b.jsonl')
synth_transcript(p, [
    (0, 'Bash', {'command': 'python s2_state.py list-topics --compact'}),
    (5, 'Bash', {'command': 'python s2_state.py show --mid 某中主題 --fields id'}),
    (95, 'Write', {'file_path': 'G:/x/ns_batch_0730.json', 'content': '...'}),
    (96, 'Bash', {'command': 'echo done'}),
])
r = tm.measure(p)
check('情境B：繼承分類＋長 gap＋下一筆直接 NS → 一樣回看重歸屬',
      r['phases'].get('分類', {}).get('minutes', 0) < 0.2, str(r['phases']))

# 情境 C：短 gap（30s，< 60s 門檻）不回看，維持原歸屬
p = os.path.join(TMP2, 'c.jsonl')
synth_transcript(p, [
    (0, 'Bash', {'command': 'python s2_state.py list-topics --compact'}),
    (30, 'Write', {'file_path': 'G:/x/ns_batch_0430.json', 'content': '...'}),
    (31, 'Bash', {'command': 'echo done'}),
])
r = tm.measure(p)
check('情境C：短 gap（30s＜60s 門檻）不回看，仍算分類',
      r['phases'].get('分類', {}).get('minutes', 0) > 0.4, str(r['phases']))

# 情境 D：長 gap 但下一筆不是直接命中（靠繼承）→ 不回看，維持原歸屬
p = os.path.join(TMP2, 'd.jsonl')
synth_transcript(p, [
    (0, 'Bash', {'command': 'python s2_state.py list-topics --compact'}),
    (90, 'Bash', {'command': 'python s2_state.py get --id X'}),  # 無站名/分類關鍵字，靠繼承
    (91, 'Bash', {'command': 'echo done'}),
])
r = tm.measure(p)
check('情境D：長 gap 但下一筆非直接命中 → 不回看，仍算分類',
      r['phases'].get('分類', {}).get('minutes', 0) >= 1.4, str(r['phases']))

# 情境 E：長 gap 但下一筆直接命中的站別跟目前相同 → 不必回看（本來就對）
p = os.path.join(TMP2, 'e.jsonl')
synth_transcript(p, [
    (0, 'Bash', {'command': 'python scripts/s2_batch_prep.py inspect ns_full.json --site ns'}),
    (90, 'Write', {'file_path': 'G:/x/ns_batch_0430.json', 'content': '...'}),
    (91, 'Bash', {'command': 'echo done'}),
])
r = tm.measure(p)
check('情境E：同站別不必回看，NS 時間不因規則改動而變少',
      r['phases'].get('NS', {}).get('minutes', 0) >= 1.4, str(r['phases']))

shutil.rmtree(TMP2, ignore_errors=True)


# ── 3. 版本指紋 ──
shas = tm.rule_shas()
check('五個規則檔都抓得到 sha', all(v for v in shas.values()),
      ', '.join(f'{k}={v}' for k, v in shas.items()))
check('rule_shas 對缺檔記 null 而非省略',
      set(tm.rule_shas(repo=os.path.join(HERE, '不存在的repo')).keys()) == set(tm.RULE_FILES),
      '缺檔時鍵仍齊全')

flags = tm.parse_flags('model=sonnet;effort=medium;TestMode=False;NoToolBan=False')
check('parse_flags 正常解析', flags == {'model': 'sonnet', 'effort': 'medium',
                                    'TestMode': 'False', 'NoToolBan': 'False'}, str(flags))
check('parse_flags 格式壞掉要留原文',
      (tm.parse_flags('model=sonnet;亂寫') or {}).get('_raw') == 'model=sonnet;亂寫')
check('parse_flags 沒帶回 None', tm.parse_flags(None) is None)


# ── 1. 真實 transcript replay ──
def transcript_dirs(explicit):
    if explicit:
        return [explicit]
    base = os.path.expanduser(r'~\.claude\projects')
    if not os.path.isdir(base):
        return []
    ds = [d for d in glob.glob(os.path.join(base, '*'))
          if os.path.isdir(d) and glob.glob(os.path.join(d, '*.jsonl'))]
    # 掃帶 cwd 是每日 scratch 夾，目錄名尾巴是 YYYYMMDD；取最近幾個就夠
    return sorted(ds, key=os.path.getmtime, reverse=True)[:3]


ap = argparse.ArgumentParser()
ap.add_argument('--transcript-dir')
ap.add_argument('--max-files', type=int, default=12)
args = ap.parse_args()

dirs = transcript_dirs(args.transcript_dir)
files = []
for d in dirs:
    files += sorted(glob.glob(os.path.join(d, '*.jsonl')),
                    key=os.path.getmtime, reverse=True)
files = files[:args.max_files]

if not files:
    # 找不到就明確失敗——「沒有檔案所以全過」是假綠燈
    print('FAIL  replay：找不到任何 transcript，無法驗分桶不變量')
    results.append(False)
else:
    print(f'\n── replay：{len(files)} 份 transcript ──')
    for p in files:
        try:
            r = tm.measure(p)
        except Exception as e:                      # noqa: BLE001
            check(f'replay {os.path.basename(p)[:12]}', False, f'measure 例外：{e}')
            continue
        ok = r['classified_total'] == r['tool_calls']
        check(f'replay {os.path.basename(p)[:12]} 分桶總數＝呼叫數', ok,
              f'{r["classified_total"]} vs {r["tool_calls"]}（{r["tool_calls"]} 次呼叫）')
        # 有分段的話，階段呼叫數不可超過總呼叫數
        if r['phases']:
            check(f'replay {os.path.basename(p)[:12]} 階段呼叫數 ≤ 總呼叫數',
                  r['phase_calls_total'] <= r['tool_calls'],
                  f'{r["phase_calls_total"]} vs {r["tool_calls"]}')

print(f'\nPASS={sum(results)} FAIL={len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
