#!/usr/bin/env python3
"""S2 排程一致性檢查（MASTER A4，2026-08-17）——**唯讀，只報不改**。

排程時刻表有三個真相源，改了一個忘了改另一個不會有任何錯誤訊息：

  A. **實際排程**（工作排程器裡的 `S2掃帶` 工作）＝真正會叫起掃帶的那個，
     這支以它為基準。
  B. **看門狗** `s2_watchdog.ps1` 的 `$Slots`／代打用的 `-Model`／`-TestMode`。
     ⚠️ 這裡沒跟著改的話，**看門狗會把已取消的輪次判定成「這輪沒開」而去代打**
     ——等於把取消掉的輪次又跑回來（0812 省 token 從 12 輪砍到 9 輪時差點發生，
     檔案裡那段警語就是為此而寫）。
  C. **repo 裡的 `scripts/S2掃帶.xml`**＝匯出的備份／文件。它跟實際排程不一致
     不會讓系統做錯事，但會誤導下一個看檔案的人。

另外附帶回報看門狗本身的啟用狀態：**排程停用或旗標檔不存在時，代打與
A5 中途死亡偵測都不會動作**——這件事光看程式碼看不出來。

用法：
    python s2_schedule_check.py              # 人看的報表
    python s2_schedule_check.py --json       # 給其他工具吃

離開碼：0＝全部一致；1＝有不一致；2＝讀不到／解析不出來（**不是**「一致」）。

🔴 設計鐵律：任何一個來源解析不出東西，一律**明確失敗**（離開碼 2），
   絕對不可以因為抓到空的就報「一致」——那是最糟的一種假綠燈。
"""
import argparse
import json
import locale
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

# ⚠️ 2026-08-31 補（全流程 locale 編碼稽核）：本檔印出的 `ℹ`／`✅`／`🔴` 在 cp950
# 下不可編碼，stdout 一旦是管線（agent 用 Bash 呼叫時**必定**是管線）就會在
# `main()` 印結論那一段丟 UnicodeEncodeError 整支掛掉——而且崩潰的離開碼 1 跟
# 本工具自己的「有不一致＝1」撞號，看起來像正常回報。用 reconfigure 不用
# TextIOWrapper（WP1 2026-08-03 實錯：雙層包覆會 "I/O operation on closed file"）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # py<3.7
        pass

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHDOG_PS1 = os.path.join(REPO, 'scripts', 's2_watchdog.ps1')
BACKUP_XML = os.path.join(REPO, 'scripts', 'S2掃帶.xml')
SCAN_TASK = 'S2掃帶'
WATCHDOG_TASK = 'S2看門狗'
FLAG_FILE = os.path.expandvars(r'%USERPROFILE%\.s2-watchdog-enabled')

# S2-NS保活.xml 是另一件事（登入保活），不在比對範圍
IGNORED_XML = ('S2-NS保活.xml',)


class SourceError(Exception):
    """某個真相源讀不到／解析不出來。一律往上丟，不吞、不猜、不當成一致。"""


# ── A. 實際排程 ───────────────────────────────────────────────

def _decode(b):
    """UTF-8 優先，不行退回本機字碼頁，再不行才用替代字元。"""
    if not b:
        return ''
    for enc in ('utf-8', locale.getpreferredencoding(False) or 'cp950'):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode('utf-8', errors='replace')


def _pwsh(script):
    """跑一段 PowerShell 拿 JSON 回來。pwsh 不在或非零離開一律當 SourceError。"""
    try:
        # 收 bytes 自己解碼：pwsh 的 **stdout** 是 UTF-8，**stderr** 走主控台
        # 字碼頁（本機 cp950）。統一用 text=True 會在讀取執行緒裡丟
        # UnicodeDecodeError，結果錯誤原因整段變空白——錯誤訊息要帶原文，
        # 不能因為解碼問題被吃掉。
        p = subprocess.run(
            ['pwsh', '-NoProfile', '-NonInteractive', '-Command', script],
            capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SourceError(f'呼叫 pwsh 失敗：{e}')
    if p.returncode != 0:
        raise SourceError(f'pwsh 離開碼 {p.returncode}：{_decode(p.stderr).strip()[:300]}')
    out = _decode(p.stdout).strip()
    if not out:
        raise SourceError('pwsh 沒有輸出')
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise SourceError(f'pwsh 輸出不是 JSON（{e}）：{out[:300]}')


def read_live_task(task_name):
    """讀工作排程器裡的實際定義。找不到工作＝SourceError，不是「沒有時刻」。"""
    script = f'''
$ErrorActionPreference = 'Stop'
$t = Get-ScheduledTask -TaskName '{task_name}'
[pscustomobject]@{{
    State    = [string]$t.State
    Triggers = @($t.Triggers | ForEach-Object {{
        [pscustomobject]@{{ StartBoundary = [string]$_.StartBoundary; Enabled = [bool]$_.Enabled }}
    }})
    Actions  = @($t.Actions | ForEach-Object {{
        [pscustomobject]@{{ Execute = [string]$_.Execute; Arguments = [string]$_.Arguments }}
    }})
}} | ConvertTo-Json -Depth 5 -Compress
'''
    d = _pwsh(script)

    slots = []
    for tr in d.get('Triggers') or []:
        if not tr.get('Enabled'):
            continue
        sb = tr.get('StartBoundary') or ''
        m = re.search(r'T(\d{2}:\d{2})', sb)
        if m:
            slots.append(m.group(1))
    args = ' '.join((a.get('Arguments') or '') for a in (d.get('Actions') or []))
    if not args.strip():
        raise SourceError(f'工作「{task_name}」沒有任何動作引數，無法判斷 model／TestMode')

    return {
        'state': d.get('State'),
        'slots': sorted(set(slots)),
        'model': _model_of(args),
        'test_mode': '-TestMode' in args,
        'script': _script_of(args),
        'raw_args': args.strip(),
    }


def _model_of(args):
    m = re.search(r'-Model\s+([^\s"]+)', args)
    return m.group(1) if m else None


def _script_of(args):
    m = re.search(r'-File\s+"?([^"]+\.ps1)"?', args)
    return os.path.basename(m.group(1)) if m else None


# ── B. 看門狗原始碼 ───────────────────────────────────────────

def read_watchdog_source(path):
    """從 s2_watchdog.ps1 抓 $Slots 與代打用的 -Model。

    抓不到＝SourceError。**不准回空清單**——空清單會讓比對變成
    「兩邊都沒有時刻，所以一致」，正是這支要防的假綠燈。"""
    if not os.path.exists(path):
        raise SourceError(f'找不到 {path}')
    with open(path, encoding='utf-8-sig') as f:
        src = f.read()

    m = re.search(r'\$Slots\s*=\s*@\((.*?)\)', src, re.S)
    if not m:
        raise SourceError(f'{os.path.basename(path)} 裡找不到 $Slots = @(...)')
    slots = re.findall(r"'(\d{2}:\d{2})'", m.group(1))
    if not slots:
        raise SourceError(f'$Slots 解析出 0 個時刻，原文：{m.group(1)[:200]!r}')

    mm = re.search(r"'-Model'\s*,\s*'([^']+)'", src)
    if not mm:
        raise SourceError(f'{os.path.basename(path)} 裡找不到代打用的 -Model')

    return {'slots': sorted(set(slots)), 'model': mm.group(1)}


# ── C. repo 備份 XML ──────────────────────────────────────────

def read_backup_xml(path):
    if not os.path.exists(path):
        raise SourceError(f'找不到 {path}')
    # 工作排程器匯出的是 UTF-16
    for enc in ('utf-16', 'utf-8-sig'):
        try:
            with open(path, encoding=enc) as f:
                text = f.read()
            if '<Task' in text:
                break
        except (UnicodeError, UnicodeDecodeError):
            continue
    else:
        raise SourceError(f'{os.path.basename(path)} 讀不出可辨識的 XML')

    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise SourceError(f'{os.path.basename(path)} XML 解析失敗：{e}')
    ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}

    slots = []
    for tr in root.findall('.//t:CalendarTrigger', ns):
        en = tr.find('t:Enabled', ns)
        if en is not None and (en.text or '').strip().lower() == 'false':
            continue
        sb = tr.find('t:StartBoundary', ns)
        if sb is not None and sb.text:
            m = re.search(r'T(\d{2}:\d{2})', sb.text)
            if m:
                slots.append(m.group(1))
    if not slots:
        raise SourceError(f'{os.path.basename(path)} 解析出 0 個 CalendarTrigger 時刻')

    node = root.find('.//t:Actions/t:Exec/t:Arguments', ns)
    if node is None or not (node.text or '').strip():
        raise SourceError(f'{os.path.basename(path)} 找不到 Actions/Exec/Arguments')
    args = node.text

    return {
        'slots': sorted(set(slots)),
        'model': _model_of(args),
        'test_mode': '-TestMode' in args,
        'script': _script_of(args),
    }


# ── 比對 ──────────────────────────────────────────────────────

def compare(live_scan, wd_src, live_wd, backup, flag_exists):
    """回傳 (findings, worst)。findings 每筆是 (級別, 標題, 說明)。

    級別：🔴＝會讓系統做錯事；🟡＝誤導人但不會做錯事；ℹ️＝狀態說明。"""
    f = []

    # 🔴 看門狗時刻表對不上實際排程＝取消的輪次會被代打回來
    if live_scan['slots'] != wd_src['slots']:
        only_live = [s for s in live_scan['slots'] if s not in wd_src['slots']]
        only_wd = [s for s in wd_src['slots'] if s not in live_scan['slots']]
        detail = []
        if only_wd:
            detail.append(f'看門狗多出 {", ".join(only_wd)}——**這些時段會被代打回來**')
        if only_live:
            detail.append(f'實際排程多出 {", ".join(only_live)}——這些時段沒人守')
        f.append(('🔴', '看門狗 $Slots 與實際排程不一致',
                  f'實際={",".join(live_scan["slots"])}；'
                  f'看門狗={",".join(wd_src["slots"])}。' + '；'.join(detail)))

    # 🔴 代打 model 不一致＝代打那一輪會用錯模型
    if live_scan['model'] != wd_src['model']:
        f.append(('🔴', '代打 model 與實際排程不一致',
                  f'實際={live_scan["model"]}；看門狗代打={wd_src["model"]}'))

    # 🔴 TestMode 不一致＝代打那一輪會用錯模式
    wd_test = live_wd['test_mode'] if live_wd else None
    if live_wd is not None and live_scan['test_mode'] != wd_test:
        f.append(('🔴', 'TestMode 與實際排程不一致',
                  f'掃帶 TestMode={live_scan["test_mode"]}；'
                  f'看門狗 TestMode={wd_test}'))

    # 🟡 repo 備份 XML 過期
    if backup is not None:
        diffs = []
        if backup['slots'] != live_scan['slots']:
            diffs.append(f'時刻（備份={",".join(backup["slots"])}）')
        if backup['model'] != live_scan['model']:
            diffs.append(f'model（備份={backup["model"]}）')
        if backup['test_mode'] != live_scan['test_mode']:
            diffs.append(f'TestMode（備份={backup["test_mode"]}）')
        if diffs:
            f.append(('🟡', 'repo 的 S2掃帶.xml 已過期',
                      '與實際排程不符：' + '、'.join(diffs) +
                      '。不影響運作，但會誤導下一個看檔案的人'))

    # ℹ️ 看門狗到底有沒有在守
    if live_wd is not None:
        off = []
        if live_wd['state'] != 'Ready':
            off.append(f'排程狀態={live_wd["state"]}')
        if not flag_exists:
            off.append('旗標檔不存在')
        if off:
            f.append(('ℹ️', '看門狗目前不會動作',
                      '、'.join(off) + '——代打與 A5 中途死亡偵測都不會執行'))

    worst = 0
    for level, _, _ in f:
        worst = max(worst, {'🔴': 2, '🟡': 1, 'ℹ️': 0}[level])
    return f, worst


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--json', action='store_true', help='輸出 JSON 而非人看的報表')
    args = ap.parse_args()

    errors = []
    live_scan = wd_src = live_wd = backup = None

    # 掃帶排程與看門狗原始碼是比對的基礎，缺任一個就沒得比 → 直接離開碼 2
    for name, fn, setter in (
        ('實際排程 S2掃帶', lambda: read_live_task(SCAN_TASK), 'live_scan'),
        ('看門狗原始碼', lambda: read_watchdog_source(WATCHDOG_PS1), 'wd_src'),
    ):
        try:
            val = fn()
        except SourceError as e:
            errors.append(f'{name}：{e}')
            val = None
        if setter == 'live_scan':
            live_scan = val
        else:
            wd_src = val

    # 這兩個缺了只是少幾條檢查，不算致命
    soft = []
    try:
        live_wd = read_live_task(WATCHDOG_TASK)
    except SourceError as e:
        soft.append(f'看門狗排程：{e}')
    try:
        backup = read_backup_xml(BACKUP_XML)
    except SourceError as e:
        soft.append(f'備份 XML：{e}')

    if errors:
        if args.json:
            print(json.dumps({'ok': False, 'errors': errors, 'soft_errors': soft},
                             ensure_ascii=False, indent=2))
        else:
            print('✗ 讀不到必要的真相源，**無法判定是否一致**（不是「一致」）：')
            for e in errors:
                print(f'  - {e}')
            for e in soft:
                print(f'  - （次要）{e}')
        return 2

    flag_exists = os.path.exists(FLAG_FILE)
    findings, worst = compare(live_scan, wd_src, live_wd, backup, flag_exists)

    if args.json:
        print(json.dumps({
            'ok': worst == 0,
            'live_scan': live_scan,
            'watchdog_source': wd_src,
            'live_watchdog': live_wd,
            'backup_xml': backup,
            'watchdog_flag_exists': flag_exists,
            'findings': [{'level': lv, 'title': t, 'detail': d} for lv, t, d in findings],
            'soft_errors': soft,
        }, ensure_ascii=False, indent=2))
        return 1 if worst >= 1 else 0

    print('S2 排程一致性檢查（唯讀，不會改任何設定）')
    print('=' * 60)
    print(f'實際排程 S2掃帶：{len(live_scan["slots"])} 輪 '
          f'{",".join(live_scan["slots"])}')
    print(f'                  model={live_scan["model"]} '
          f'TestMode={live_scan["test_mode"]} 狀態={live_scan["state"]}')
    print(f'看門狗 $Slots  ：{len(wd_src["slots"])} 輪 {",".join(wd_src["slots"])}')
    print(f'                  代打 model={wd_src["model"]}')
    if live_wd:
        print(f'看門狗排程      ：狀態={live_wd["state"]} '
              f'TestMode={live_wd["test_mode"]} 旗標檔={"在" if flag_exists else "不在"}')
    if backup:
        print(f'repo 備份 XML   ：{len(backup["slots"])} 輪 model={backup["model"]} '
              f'TestMode={backup["test_mode"]}')
    for e in soft:
        print(f'（次要來源讀不到）{e}')
    print('-' * 60)
    if not findings:
        print('✅ 全部一致')
    for lv, title, detail in findings:
        print(f'{lv} {title}')
        print(f'   {detail}')
    return 1 if worst >= 1 else 0


if __name__ == '__main__':
    sys.exit(main())
