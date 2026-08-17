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
import os
import sys

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
