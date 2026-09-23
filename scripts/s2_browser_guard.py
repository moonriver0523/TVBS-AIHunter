#!/usr/bin/env python3
"""PreToolUse guard for browser-evaluate mistakes seen repeatedly in S2 runs."""
import json
import re
import shutil
import subprocess
import sys


PARAM_ITEMIDS = re.compile(r'\basync\s*\(\s*itemids\s*\)\s*=>')


def _syntax_error(function_text):
    node = shutil.which('node')
    if node:
        try:
            proc = subprocess.run(
                [node, '--check'], input=f'({function_text})\n', text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
            if proc.returncode:
                lines = [line.strip() for line in proc.stderr.splitlines() if line.strip()]
                return lines[-1] if lines else 'Node.js 語法檢查失敗'
            return None
        except (OSError, subprocess.SubprocessError):
            pass
    # Deterministic fallback for the most common malformed assignment in the logs.
    if re.search(r'=\s*;', function_text):
        return '賦值運算子後缺少值'
    return None


def decide(tool_name, tool_input):
    if tool_name != 'mcp__browser__browser_evaluate' or not isinstance(tool_input, dict):
        return None
    function_text = tool_input.get('function')
    if not isinstance(function_text, str) or not function_text.strip():
        return None
    if PARAM_ITEMIDS.search(function_text) and re.search(r'\bitemids\s*\.\s*map\b', function_text):
        return (
            '⛔ browser_evaluate 不會替 `async (itemids)` 注入參數，itemids 會是 undefined。'
            '請改成無參數函式並把本輪 ID 直接貼進函式：'
            '`async () => { const itemids = ["<GUID1>", "<GUID2>"]; '
            'if (!itemids.length) throw new Error("AP itemids is empty"); ... }`。'
        )
    syntax = _syntax_error(function_text)
    if syntax:
        return f'⛔ browser_evaluate JavaScript 語法檢查未通過：{syntax}。修正後再送出。'
    return None


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode('utf-8', 'replace'))
        reason = decide(payload.get('tool_name', ''), payload.get('tool_input') or {})
    except Exception:
        return 0
    if reason:
        print(json.dumps({
            'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': 'deny',
                'permissionDecisionReason': reason,
            }
        }, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
