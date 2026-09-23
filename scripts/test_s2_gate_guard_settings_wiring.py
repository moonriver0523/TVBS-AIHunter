#!/usr/bin/env python3
"""驗證 gate lock Edit 技術鎖的 hook 真的掛在兩份 settings.json 上
（R43方向1/任務B，2026-09-18）——防止未來改動這兩份設定檔時不小心
漏掉或改壞這道防線，卻沒有任何測試會失敗。

只驗設定檔結構（JSON 合法、matcher／command 對到 `s2_gate_guard.py`），
不驗 hook 執行時的行為——那部分已經由 `test_s2_gate_guard.py` 的
subprocess 測試涵蓋。這裡刻意額外驗證**既有**的 matcher（D9 `s2_bash_guard.py`、
`.claude/settings.json` 的 `hook-handler.cjs` pre-edit/post-edit/pre-bash/
post-bash）**沒有被這次改動動到或覆蓋掉**——這是這次任務唯一會動到共用設定檔
的地方，回歸測試比程式碼測試更重要。

用法：python test_s2_gate_guard_settings_wiring.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
GUARD_SETTINGS = os.path.join(REPO_ROOT, 'scripts', 's2_guard_settings.json')
CLAUDE_SETTINGS = os.path.join(REPO_ROOT, '.claude', 'settings.json')

results = []


def check(name, cond, extra=''):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}{(" -> " + extra) if extra else ""}')


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def hooks_for(event_list, matcher):
    """從某個 hook event 的 array 裡，找出 matcher 完全相符的那組，
    回傳其 hooks[*].command 清單（找不到回空 list）。"""
    for group in event_list or []:
        if group.get('matcher') == matcher:
            return [h.get('command', '') for h in group.get('hooks', [])]
    return []


# ── s2_guard_settings.json（S2 掃帶 session 用，--settings 帶入）─────────
guard = load(GUARD_SETTINGS)
check('s2_guard_settings.json：JSON 合法', isinstance(guard, dict))

pre = guard.get('hooks', {}).get('PreToolUse', [])
post = guard.get('hooks', {}).get('PostToolUse', [])

bash_cmds = hooks_for(pre, 'Bash|PowerShell|Write')
check('s2_guard_settings.json：既有 D9 bash guard matcher 沒被動到',
      any('s2_bash_guard.py' in c for c in bash_cmds), str(bash_cmds))

edit_cmds = hooks_for(pre, 'Edit|MultiEdit')
check('s2_guard_settings.json：PreToolUse 新增 Edit|MultiEdit matcher 指到 s2_gate_guard.py',
      any('s2_gate_guard.py' in c for c in edit_cmds), str(edit_cmds))

post_write_cmds = hooks_for(post, 'Write')
check('s2_guard_settings.json：PostToolUse 新增 Write matcher 指到 s2_gate_guard.py',
      any('s2_gate_guard.py' in c for c in post_write_cmds), str(post_write_cmds))

# ── .claude/settings.json（互動 session 共用設定，任務B新掛的）─────────
claude = load(CLAUDE_SETTINGS)
check('.claude/settings.json：JSON 合法', isinstance(claude, dict))

c_pre = claude.get('hooks', {}).get('PreToolUse', [])
c_post = claude.get('hooks', {}).get('PostToolUse', [])

check('.claude/settings.json：既有 Bash pre-hook（hook-handler.cjs pre-bash）沒被動到',
      any('pre-bash' in c for c in hooks_for(c_pre, 'Bash')))
check('.claude/settings.json：既有 Write|Edit|MultiEdit pre-hook（pre-edit）沒被動到',
      any('pre-edit' in c for c in hooks_for(c_pre, 'Write|Edit|MultiEdit')))
check('.claude/settings.json：既有 Write|Edit|MultiEdit post-hook（post-edit）沒被動到',
      any('post-edit' in c for c in hooks_for(c_post, 'Write|Edit|MultiEdit')))
check('.claude/settings.json：既有 Bash post-hook（post-bash）沒被動到',
      any('post-bash' in c for c in hooks_for(c_post, 'Bash')))

c_edit_cmds = hooks_for(c_pre, 'Edit|MultiEdit')
check('.claude/settings.json：PreToolUse 的 Edit|MultiEdit matcher 指到 s2_gate_guard.py（跟既有 pre-edit 那組分開，不互相覆蓋）',
      any('s2_gate_guard.py' in c for c in c_edit_cmds), str(c_edit_cmds))

c_post_write_cmds = hooks_for(c_post, 'Write')
check('.claude/settings.json：PostToolUse 新增獨立 Write matcher 指到 s2_gate_guard.py',
      any('s2_gate_guard.py' in c for c in c_post_write_cmds), str(c_post_write_cmds))

# 兩份都指到同一支腳本（唯一實作、不要分岔成兩份邏輯）
check('兩份 settings.json 的 Edit deny hook 指到同一支腳本檔案（絕對路徑字串相同）',
      edit_cmds and c_edit_cmds and edit_cmds[0].strip().endswith('s2_gate_guard.py')
      and c_edit_cmds[0].strip().endswith('s2_gate_guard.py')
      and edit_cmds[0].split('python', 1)[-1].strip() == c_edit_cmds[0].split('python', 1)[-1].strip(),
      f'{edit_cmds} vs {c_edit_cmds}')

# 腳本本身真的存在（設定檔指到的路徑不是空話）
GATE_GUARD_PATH = os.path.join(REPO_ROOT, 'scripts', 's2_gate_guard.py')
check('s2_gate_guard.py 檔案真的存在於設定檔指到的路徑', os.path.exists(GATE_GUARD_PATH), GATE_GUARD_PATH)

print(f'\n共 {len(results)} 項，通過 {sum(results)}，失敗 {len(results) - sum(results)}')
import sys
sys.exit(0 if all(results) else 1)
