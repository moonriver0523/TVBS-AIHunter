#!/usr/bin/env python3
"""S2 掃帶 agent 的 PreToolUse hook：擋「用臨時 python 檢查 json／狀態檔」（MASTER D9 步驟②③）。

背景：0817 全日 `python -c:json` 呈 26/33/2/0/0/36/8/23（0430→2200）——13c §1a 的
文字澄清擋不住行為漂移，形狀跟 T2「Task 工具靠自律會漂移」一樣；T2 的解是工具層
硬排除。但 `python -c` 是 Bash/PowerShell 的**參數內容**，`--disallowedTools` 前綴
比對擋不乾淨（0817-2200 有 4 筆開頭是 `export PYTHONIOENCODING=utf-8` 換行才接
`python3 -c`），所以走 PreToolUse hook 做整串 regex（使用者 2026-08-17 裁決）。

判定範圍照步驟③收窄——只擋「python 內聯程式 ＋ 碰 .json／狀態檔」的組合：
  1. 命中 `-s2-state.json`：13c §2 本來就明文禁止直讀生產狀態檔 → deny，
     指路 `s2_state.py show/…`。
  2. 命中其他 `.json` 檔名：13d §4 的場景 → deny，把 agent 試圖碰的檔名代入訊息，
     指路 `s2_batch_prep.py inspect/search/compare/dedup-check/snapshot`
     （deny 訊息就是教學機制——0817-2200 的教訓是新工具存在但沒被想起）。
  3. 其餘（純計算、.txt、呼叫 repo 腳本）一律放行——fail-open，寧可漏擋不可誤擋，
     位移靠 A1 遙測 `--diff` 看。

輸入：stdin 一包 JSON（Claude Code hook 協定），只看 `tool_name` 與
`tool_input.command`。輸出：要擋時往 stdout 印 permissionDecision=deny 的 JSON
（`ensure_ascii=True`——cp950 吞中文有前例，R4／②樣板回滾），放行時什麼都不印。
任何解析失敗一律放行（exit 0）——hook 壞掉不准把整輪掃帶弄死。

回退：launcher `-NoBashGuard` 開關（不與 -NoToolBan 共用，單變因可歸因）。
"""
import json
import re
import sys

# python／python3／py（含 .exe），中間可夾 `-X utf8` 這類旗標，接 `-c`。
# ⚠️ 必須涵蓋 `python3`：0817 體檢實際踩過「用 `python -c` grep 會漏掉 11/14 筆」。
# 「命令列任何位置」都要找——export 前綴換行後才接 python3 的案例佔 0817-2200 的 4/23。
PY_INLINE = re.compile(
    r'\b(?:python3?|py)(?:\.exe)?'      # 直譯器
    r'(?:\s+-[^\s]+|\s+utf-?8)*'        # 中間旗標（-X utf8 / -u …），不吃檔名
    r'\s+-c(?=[\s"\'])'                 # -c 後面接空白或引號才算（不吃 --checkpoint）
)

# 命令列裡的 .json 檔名（含相對／絕對路徑；cwd＝scratch 夾，相對路徑就是暫存檔）
JSON_FILE = re.compile(r'[\w\-.:\\/]+\.json\b')

STATE_HINT = (
    '⛔ 不准用臨時 python 直讀生產狀態檔（13c §2 明文禁止，D9 hook 攔下）。'
    '請改用 s2_state.py 的查詢子指令，例如：\n'
    '  python E:/GitHub/TVBS-AIHunter/scripts/s2_state.py show --uncat\n'
    '  python E:/GitHub/TVBS-AIHunter/scripts/s2_state.py list-topics --compact\n'
    '  python E:/GitHub/TVBS-AIHunter/scripts/s2_state.py get --id <ID>'
)

RAW_HINT = (
    '⛔ 檢查 raw／batch json 不要自己寫臨時 python（13d §4，D9 hook 攔下）。'
    '你要碰的檔：{files}。請改用 s2_batch_prep.py 的標準子指令：\n'
    '  python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py inspect {first} --ids A,B --fields f1,f2 [--lengths]\n'
    '  python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py search {first} --contains 關鍵字\n'
    '  python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py compare --raw <raw檔> --batch <batch檔>\n'
    '  python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py dedup-check {first} --ids A,B\n'
    '  python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py snapshot {first} --site <站> --checkpoint <輪次>\n'
    '（AP 清單檔會自動看穿 _source；字數檢查用 inspect --lengths；'
    '要**產出／寫入** json 檔改用 Write 工具直接寫，不要換 heredoc 或先落 .py 檔繞）'
)


def decide(tool_name, command):
    """回傳 None＝放行；否則回傳 deny 理由字串。"""
    if tool_name not in ('Bash', 'PowerShell'):
        return None
    if not command or not PY_INLINE.search(command):
        return None

    if '-s2-state.json' in command:
        return STATE_HINT

    files = [f for f in JSON_FILE.findall(command)
             # 排除呼叫 repo 腳本本身可能帶到的設定檔名
             if 'guard_settings' not in f and 's2_mcp' not in f]
    if files:
        uniq = list(dict.fromkeys(files))[:3]
        return RAW_HINT.format(files='、'.join(uniq), first=uniq[0])

    return None


def main():
    try:
        payload = json.load(sys.stdin)
        tool_name = payload.get('tool_name', '')
        command = (payload.get('tool_input') or {}).get('command', '')
        reason = decide(tool_name, command)
    except Exception:
        # hook 自己壞掉不准弄死掃帶輪：靜默放行
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
