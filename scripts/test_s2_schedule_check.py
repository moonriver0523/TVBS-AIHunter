#!/usr/bin/env python3
"""s2_schedule_check.py 的負向測試（MASTER A4）。

重點只有一個：**任何一個真相源讀不到／解析不出東西，都必須明確失敗**，
不可以回空清單讓比對變成「兩邊都沒有，所以一致」——那是最糟的假綠燈，
也是共同護欄「欄位全空必須明確失敗」的直接落地。

用法：python test_s2_schedule_check.py
"""
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'sc', os.path.join(HERE, 's2_schedule_check.py'))
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

TMP = tempfile.mkdtemp(prefix='s2_a4_test_')
results = []


def case(name, fn, want):
    try:
        r = fn()
    except sc.SourceError as e:
        ok = want in str(e)
        results.append(ok)
        print(f'{"PASS" if ok else "FAIL"}  {name} → SourceError: {str(e)[:120]}')
        if not ok:
            print(f'      預期訊息含：{want}')
        return
    results.append(False)
    print(f'FAIL  {name} → 沒有丟錯，回傳 {r}')


def write(name, text):
    p = os.path.join(TMP, name)
    with open(p, 'w', encoding='utf-8-sig') as f:
        f.write(text)
    return p


case('看門狗檔不存在要明確失敗',
     lambda: sc.read_watchdog_source(os.path.join(TMP, 'nope.ps1')),
     '找不到')

case('看門狗沒有 $Slots 要明確失敗',
     lambda: sc.read_watchdog_source(write('a.ps1', 'param()\n# 什麼都沒有\n')),
     '找不到 $Slots')

# 最危險的一種：$Slots 寫在那裡但解析出 0 個時刻
case('$Slots 解析出 0 個時刻要明確失敗（不可報一致）',
     lambda: sc.read_watchdog_source(
         write('b.ps1', "[string[]]$Slots = @(),\n$x = @('-Model', 'sonnet')\n")),
     '解析出 0 個時刻')

case('看門狗沒有代打 -Model 要明確失敗',
     lambda: sc.read_watchdog_source(
         write('c.ps1', "[string[]]$Slots = @('01:00','04:30'),\n")),
     '找不到代打用的 -Model')

case('排程工作不存在要明確失敗',
     lambda: sc.read_live_task('S2這個工作不存在請不要建立它'),
     'pwsh 離開碼')

case('備份 XML 不是 XML 要明確失敗',
     lambda: sc.read_backup_xml(write('d.xml', '這不是 XML')),
     '讀不出可辨識的 XML')


# ── 正向：本 repo 的真實檔案要解析得出東西（解析器本身沒壞掉）──
def positive():
    wd = sc.read_watchdog_source(sc.WATCHDOG_PS1)
    ok = len(wd['slots']) > 0 and wd['model']
    results.append(bool(ok))
    print(f'{"PASS" if ok else "FAIL"}  真實 s2_watchdog.ps1 解析得出 '
          f'{len(wd["slots"])} 個時刻、model={wd["model"]}')

    bk = sc.read_backup_xml(sc.BACKUP_XML)
    ok2 = len(bk['slots']) > 0
    results.append(bool(ok2))
    print(f'{"PASS" if ok2 else "FAIL"}  真實 S2掃帶.xml 解析得出 '
          f'{len(bk["slots"])} 個時刻、model={bk["model"]}')


positive()

# ── 比對邏輯：看門狗多出時段要判 🔴（那正是「取消的輪次被代打回來」）──
live = {'slots': ['01:00', '04:30'], 'model': 'sonnet', 'test_mode': False,
        'state': 'Ready', 'script': 's2_scan.ps1', 'raw_args': ''}
wd_extra = {'slots': ['01:00', '04:30', '23:00'], 'model': 'sonnet'}
f, worst = sc.compare(live, wd_extra, None, None, True)
ok = worst == 2 and any('看門狗多出 23:00' in d for _, _, d in f)
results.append(ok)
print(f'{"PASS" if ok else "FAIL"}  看門狗多出時段要判 🔴（worst={worst}）')

# ── 完全一致時要安靜 ──
f2, worst2 = sc.compare(live, {'slots': ['01:00', '04:30'], 'model': 'sonnet'},
                        None, None, True)
ok2 = worst2 == 0 and not f2
results.append(ok2)
print(f'{"PASS" if ok2 else "FAIL"}  完全一致時無任何 finding')

# ── 代打 model 不一致要判 🔴 ──
f3, worst3 = sc.compare(live, {'slots': ['01:00', '04:30'], 'model': 'opus'},
                        None, None, True)
ok3 = worst3 == 2 and any('代打 model' in t for _, t, _ in f3)
results.append(ok3)
print(f'{"PASS" if ok3 else "FAIL"}  代打 model 不一致要判 🔴')

print(f'\nPASS={sum(results)} FAIL={len(results) - sum(results)}')
sys.exit(0 if all(results) else 1)
