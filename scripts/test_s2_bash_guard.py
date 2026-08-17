#!/usr/bin/env python3
"""s2_bash_guard.py 的測試（MASTER D9 步驟②③）。

重點：
  - 涵蓋 `python`/`python3`/`py`、中間旗標、export 前綴換行（0817-2200 的 4/23 鐵證）
  - 負向測試＝自我 DoS 檢查：標準工具呼叫（dedup-check/--checkpoint/s2_state show）
    與純計算 `python -c "print(1+1)"` 必須放行——防日後改 regex 弄壞
  - 狀態檔與一般 .json 走不同 deny 訊息（教學機制）
  - stdin 餵爛 JSON 不准炸，靜默放行

用法：python test_s2_bash_guard.py
"""
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, 's2_bash_guard.py')
spec = importlib.util.spec_from_file_location('guard', GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

results = []


def check(name, cond, extra=''):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}{(" → " + extra) if extra else ""}')


def d(tool, cmd):
    return guard.decide(tool, cmd)


# ── deny：臨時 python 檢查 json ──────────────────────────────
check('python -c 讀 raw json → deny 且訊息帶檔名',
      (r := d('Bash', 'python -c "import json; print(len(json.load(open(\'ap_list_2000.json\'))))"'))
      and 'ap_list_2000.json' in r and 'inspect' in r)

check('python3 -c（export 前綴換行）→ deny（0817-2200 的 4/23 案例）',
      (r := d('Bash', 'export PYTHONIOENCODING=utf-8\npython3 -c "import json; d=json.load(open(\'rt_details_2000.json\')); print(len(d))"'))
      and 'rt_details_2000.json' in r)

check('py -c 讀 json → deny',
      d('Bash', 'py -c "import json;json.load(open(\'batch_ns.json\'))"') is not None)

check('python -X utf8 -c 讀 json → deny（中間旗標）',
      d('Bash', 'python -X utf8 -c "import json;json.load(open(\'x.json\'))"') is not None)

check('python -c 自產稽核檔 _audit_ap_2200.json → deny（snapshot 被繞過的那筆）',
      (r := d('Bash', "python3 -c \"open('_audit_ap_2200.json','w').write('x')\""))
      and '_audit_ap_2200.json' in r)

check('PowerShell 工具跑 python -c 讀 json → 同樣 deny（0730 輪 29 次的繞道）',
      d('PowerShell', 'python -c "import json; json.load(open(\'ns_full.json\'))"') is not None)

# ── deny：直讀生產狀態檔 → 專屬訊息 ─────────────────────────
check('python -c 讀 -s2-state.json → deny 且指路 s2_state.py（13c §2）',
      (r := d('Bash', 'python3 -c "import json; d=json.load(open(\'G:/我的雲端硬碟/Claude共用/自動掃帶系統/0818-s2-state.json\')); print(d[\'alerts\'])"'))
      and 's2_state.py' in r and '13c' in r)

# ── allow：標準工具與純計算（自我 DoS 檢查）────────────────
check('dedup-check 標準呼叫（帶 .json 但無 -c）→ 放行',
      d('Bash', 'python scripts/s2_batch_prep.py dedup-check ns_full_2200.json --ids EN-32MO,EN-31MO --site ns') is None)

check('--checkpoint 不可被誤判成 -c → 放行',
      d('Bash', 'python scripts/s2_batch_prep.py snapshot rt_list.json --site rt --checkpoint 0818-1600') is None)

check('s2_state.py show → 放行',
      d('Bash', 'python scripts/s2_state.py show --uncat') is None)

check('純計算 python -c "print(1+1)" → 放行（fail-open）',
      d('Bash', 'python -c "print(1+1)"') is None)

check('python -c 數字串長度（無檔案）→ 放行',
      d('Bash', 'python3 -c "print(len(\'測試字串\'))"') is None)

check('python -c 讀 .txt → 放行（步驟③收窄，.txt 不擋）',
      d('Bash', 'python -c "print(open(\'_audit_rt_1600.txt\').read()[:100])"') is None)

check('git status → 放行',
      d('Bash', 'git status --short') is None)

check('非 Bash/PowerShell 工具 → 一律放行',
      d('Read', 'python -c "json.load(open(\'x.json\'))"') is None)

# ── 端到端：stdin 協定與爛輸入 ──────────────────────────────
def run_stdin(payload_text):
    p = subprocess.run([sys.executable, GUARD], input=payload_text,
                       capture_output=True, text=True, encoding='utf-8', timeout=30)
    return p.returncode, p.stdout


code, out = run_stdin(json.dumps({
    'tool_name': 'Bash',
    'tool_input': {'command': 'python -c "import json;json.load(open(\'a.json\'))"'}}))
parsed = json.loads(out) if out.strip() else {}
check('端到端 deny：stdout 是合法 JSON 且 permissionDecision=deny',
      code == 0 and parsed.get('hookSpecificOutput', {}).get('permissionDecision') == 'deny')
check('端到端 deny：輸出純 ASCII（cp950 防呆）',
      all(ord(c) < 128 for c in out))

code2, out2 = run_stdin(json.dumps({
    'tool_name': 'Bash', 'tool_input': {'command': 'git status'}}))
check('端到端 allow：stdout 空、exit 0', code2 == 0 and not out2.strip())

code3, out3 = run_stdin('這不是 JSON{{{')
check('爛 stdin 不炸、靜默放行（hook 壞掉不准弄死掃帶輪）',
      code3 == 0 and not out3.strip())

code4, out4 = run_stdin(json.dumps({'tool_name': 'Bash'}))
check('缺 tool_input 也放行不炸', code4 == 0 and not out4.strip())

# ── 收尾 ────────────────────────────────────────────────────
total, passed = len(results), sum(results)
print(f'\n{passed}/{total} PASS')
sys.exit(0 if passed == total else 1)
