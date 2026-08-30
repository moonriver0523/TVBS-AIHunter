#!/usr/bin/env python3
"""S2 掃帶 agent 的 PreToolUse hook：擋「用臨時 python 檢查 json／狀態檔」（MASTER D9 步驟②③），
以及「臨場寫／跑一次性 .py 腳本」這個 D9 上線後才浮現的繞道變體（2026-08-30 補）。

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

**2026-08-30 補的破口**：`python -c` 只擋「內聯」程式，MASTER A9③早就記過 agent
會改用「Write 先落一支 .py 檔（hook 完全看不到 Write）→ Bash 跑 `python 檔名.py`
（不是 `-c`，PY_INLINE 也對不上）」這條路完全繞過上面三條。0830-0730 輪實錯：
自寫 `_mk_audit_snapshots.py`、`_mk_ns_snapshot.py` 兩支腳本落地執行，NS 站因此
多花數分鐘、`inspect` 被叫到 34 次（當天最高）。這兩件事其實都是
`s2_batch_prep.py snapshot`（0817/0818 就已經補上）該做的事——工具缺口不成立，
純粹是繞道，比照既有邏輯補上兩個判定點：
  4. **Write 工具寫一支不在 `scripts/` 目錄下的 `.py`** → deny，指路
     `s2_batch_prep.py` 現有子指令；真的沒有對應功能才准記進回報，不准落地跑。
  5. **Bash／PowerShell 執行一支不在 `scripts/` 目錄下的 `.py`**（跑存檔腳本，
     不是 `-c` 內聯）→ 同上 deny，防繞過④用 heredoc／`Set-Content` 先落檔
     再跑（那一步就算真的漏放行，這一步照樣攔下來）。
  沿用同一套 fail-open 哲學：只認「路徑裡有沒有 `scripts` 這一段」，不維護
  檔名白名單——`scripts/` 底下的既有工具（含新加的）永遠放行，判斷邏輯不會
  因為 repo 加新腳本而跟著改。

輸入：stdin 一包 JSON（Claude Code hook 協定）。Bash／PowerShell 看
`tool_input.command`；Write 看 `tool_input.file_path`。輸出：要擋時往 stdout 印
permissionDecision=deny 的 JSON（`ensure_ascii=True`——cp950 吞中文有前例，
R4／②樣板回滾），放行時什麼都不印。任何解析失敗一律放行（exit 0）——hook
壞掉不准把整輪掃帶弄死。

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

# python／python3／py 跑一支「存檔」腳本（不是 -c 內聯）——中間可夾旗標，
# 抓最後那個 .py 路徑。刻意跟 PY_INLINE 分開判定：呼叫方只在 PY_INLINE
# 沒命中時才檢查這條，兩者互斥不會重疊誤判。
# 🔴 2026-08-31 訂正（獨立 review F2）：改用 finditer 逐一檢查，不能只看
# `.search()` 的第一個命中——`python <標準工具> && python <一次性腳本>`
# 這種串接指令，第一個 `python` 呼叫是合規的，只看第一個命中會整條放行。
PY_RUN_FILE = re.compile(
    r'\b(?:python3?|py)(?:\.exe)?'
    r'(?:\s+-[^\s]+)*'                  # 中間旗標（-u／-X utf8…）
    r'\s+([^\s"\']+\.py)\b'
)

# python 讀 stdin 執行（heredoc／管線灌程式碼），跟落檔案再跑是同一件事的
# 變體——`common/13c2 §…` 明文列為禁止形式（`python - << PYEOF`），但正則
# 上不會被 PY_RUN_FILE 抓到（沒有 .py 路徑），也不會被 PY_INLINE 抓到
# （不是 -c）。2026-08-31 補（獨立 review F4）。
PY_STDIN_HEREDOC = re.compile(r'\b(?:python3?|py)(?:\.exe)?\s+-?\s*<<')

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

SCRIPT_HINT = (
    '⛔ 不准臨場寫／跑一次性 .py 腳本（13d §4／§10，D9 hook 攔下，2026-08-30 補；'
    '0830-0730 輪 `_mk_audit_snapshots.py`／`_mk_ns_snapshot.py` 就是這樣繞過去的）。'
    '你碰的檔：{file}。先看 s2_batch_prep.py 有沒有現成子指令能做同一件事：\n'
    '  跨站對帳／查窗內外時間 → python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py '
    'timeline <raw檔> --site ns|ap|rt [--out <檔>]（三站清單都是 UTC，自動 +8h '
    '轉台北——2026-08-31 訂正：RT 的 at 欄位原本誤判成免轉，其實也要轉）\n'
    '  raw 正文回填 batch 的 src_text → python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py '
    'fill-src-text --batch <batch.json> --raw <raw檔> --site ns|ap|rt（只填空的，不覆寫已有內容；'
    '取代 `_merge_src_*.py`／`_fix_src_*.py` 這批）\n'
    '  合併多份 json 陣列檔（分頁清單、多來源分批 batch）→ python '
    'E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py concat <檔1> <檔2> [...] [--site ns|ap|rt] [--out <檔>]'
    '（給 --site 才去重；取代 `a=json.load(...); b=json.load(...); json.dump(a+b,...)` 這批）\n'
    '  batch.json 裡的 category 收成 set-category --pairs 字串 → python '
    'E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py collate-category <batch1.json> [<batch2.json> ...]'
    '（只組字串，送不送仍是你判斷；取代 `run_setcat_1000.py`／`_tmp_ns_cat.py`）\n'
    '  內容稽核快照 → python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py snapshot <raw檔> --site <站> --checkpoint <輪次>\n'
    '  其餘查詢 → python E:/GitHub/TVBS-AIHunter/scripts/s2_batch_prep.py inspect/search/compare/dedup-check ...\n'
    '真的沒有對應功能，記進回報／`needs-review`，不要自己寫腳本落地跑——'
    '工具缺口要回頭補進 `s2_batch_prep.py`，不是每輪重寫一次。'
)


# 標準工具的檔名慣例——這批（含測試）全部是 `s2_` 或 `test_s2_` 開頭，整個
# 語料庫查過的 ~100 支一次性腳本沒有一支用這個前綴。**檔名符合就直接放行，
# 不管路徑怎麼寫**（含相對路徑、cd 進 scripts/ 之後的裸檔名）——這是給
# 2026-08-31 review F3 抓到的「合規呼叫反而被誤擋」補的防呆：`--setting-sources
# project` 的絕對路徑慣例不保證每次都被照抄，deny 一個合規呼叫比漏放一個
# 一次性腳本更糟（fail-open 的方向不能反過來）。
_REPO_SCRIPT_NAME = re.compile(r'^(?:s2_|test_s2_)[a-zA-Z0-9_]*\.py$', re.IGNORECASE)


_REPO_ROOT = 'e:/github/tvbs-aihunter'


def _is_repo_script(path):
    """判斷這支 `.py` 是不是本 repo 認可的標準工具。

    🔴 2026-08-31 訂正（獨立 review F1，兩輪修正）：
    第一版只問「路徑裡有沒有 `scripts` 這一段」，語料庫裡就有 15 支一次性
    腳本直接寫在 `scripts/_tmp_*.py`／`scripts/_tmp/`（含 repo 裡確實存在的
    未追蹤 `scripts/_tmp/`），靠這個洞全部繞過去。
    第二版加了 `_tmp` 排除，但 review 又抓到更根本的問題：任何路徑只要
    **某一段剛好叫 `scripts`** 就會放行，跟是不是這個 repo 的 `scripts/`
    無關——`C:/scratch/scripts/_evil.py` 一樣過。改成：①檔名本身是
    `s2_*`／`test_s2_*` 就直接放行（不管路徑，涵蓋相對路徑／`cd` 進
    `scripts/` 之後的裸檔名這些合規呼叫，見 F3）；②否則要求路徑**真的錨定**
    在這個 repo 底下——絕對路徑要以 repo 根目錄開頭，相對路徑要以
    `scripts/`（或 `./scripts/`）開頭——且路徑裡任何一段都不是 `_tmp` 開頭。
    """
    norm = path.replace('\\', '/')
    basename = norm.rsplit('/', 1)[-1]
    if _REPO_SCRIPT_NAME.match(basename):
        return True

    low = norm.lower()
    if low.startswith('./'):
        low = low[2:]
    if low.startswith(_REPO_ROOT + '/'):
        rel = low[len(_REPO_ROOT) + 1:]
    elif low.startswith('scripts/'):
        rel = low
    else:
        return False

    if not rel.startswith('scripts/'):
        return False
    return not any(p.startswith('_tmp') for p in rel.split('/'))


def decide(tool_name, command):
    """Bash／PowerShell 專用：回傳 None＝放行；否則回傳 deny 理由字串。"""
    if tool_name not in ('Bash', 'PowerShell'):
        return None
    if not command:
        return None

    if PY_INLINE.search(command):
        if '-s2-state.json' in command:
            return STATE_HINT
        files = [f for f in JSON_FILE.findall(command)
                 # 排除呼叫 repo 腳本本身可能帶到的設定檔名
                 if 'guard_settings' not in f and 's2_mcp' not in f]
        if files:
            uniq = list(dict.fromkeys(files))[:3]
            return RAW_HINT.format(files='、'.join(uniq), first=uniq[0])
        return None

    if PY_STDIN_HEREDOC.search(command):
        return SCRIPT_HINT.format(file='（heredoc／stdin 灌程式碼，沒有檔名）')

    # 逐一檢查每個 `python 檔名.py` 呼叫，不能只看第一個——串接指令
    # （`python 標準工具 && python 一次性腳本`）第一個合規不代表整條都合規。
    for m in PY_RUN_FILE.finditer(command):
        if not _is_repo_script(m.group(1)):
            return SCRIPT_HINT.format(file=m.group(1))

    return None


def decide_write(file_path):
    """Write 工具專用：回傳 None＝放行；否則回傳 deny 理由字串。"""
    if not file_path or not file_path.lower().endswith('.py'):
        return None
    if _is_repo_script(file_path):
        return None
    return SCRIPT_HINT.format(file=file_path)


def main():
    try:
        payload = json.load(sys.stdin)
        tool_name = payload.get('tool_name', '')
        tool_input = payload.get('tool_input') or {}
        if tool_name == 'Write':
            reason = decide_write(tool_input.get('file_path', ''))
        else:
            reason = decide(tool_name, tool_input.get('command', ''))
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
