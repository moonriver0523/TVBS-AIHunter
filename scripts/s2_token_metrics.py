#!/usr/bin/env python3
"""S2 掃帶基線量測器（Task 1，2026-08-12）。

資料來源固定是 session transcript（~/.claude/projects/<sanitized-repo>/<session_id>.jsonl），
不是 掃帶log-*.txt ——外殼 pwsh 一死，*> $runLog 重導向就斷，log 會被截斷
（0811-2200 實例：log 凍在 22:24:05，掃帶本體其實跑到 22:29:34 才收工）。

去重規則：JSONL 每個 content block 一行，同一則 message 的 usage 會重複出現，
不去重會灌水約 1.8 倍（2026-08-12 實錯）。本檔只計每個 message.id 的最後一筆 usage。

用法：
    python s2_token_metrics.py --checkpoint 0812-1200
    python s2_token_metrics.py --checkpoint 0812-1200 --session <session_id>
    python s2_token_metrics.py --checkpoint 0812-1200 --dry-run   # 只印不寫檔

不帶 --session 時，抓 transcript 目錄裡最新修改的 .jsonl（跟排程時間點最接近的通常就是它，
但排程本身也可能在同時間留下多個 session——不確定時務必帶 --session 明講）。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

TRANSCRIPT_DIR = os.path.expanduser(
    r'~\.claude\projects\E--GitHub-TVBS-AIHunter'
)
METRICS_FILE = (
    r'G:\我的雲端硬碟\Claude共用\自動掃帶系統\S2掃帶log\_token_metrics.jsonl'
)
METRICS_FILE_FALLBACK = r'D:\Downloads\S2掃帶log\_token_metrics.jsonl'


# ── 版本指紋（MASTER A1，2026-08-17）────────────────────────────
# 每輪把「這一輪照的是哪一版規則」記下來。沒有它，規則一改就會把規則的效果
# 誤算到腳本頭上——0817 就發生過：13c §1a 補了一句澄清，下一輪 `python -c:json`
# 從 26~33 次掉到 0 次，當下只能靠人工翻 commit 才確定歸因。
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULE_FILES = {
    'prompt': os.path.join('scripts', 's2_scan_prompt.md'),
    '13': os.path.join('common', '13-S2-定時掃帶.md'),
    # 2026-08-24（R15）：Read 結果約 30,000 字元會靜默截斷，13（53,676 字元）與
    # 13c（42,998 字元）實測每輪都只載入約一半。已切成 13＋13e＋13f 與 13c＋13c2，
    # 逐字保留（附 SHA-256 守恆證明）。五份都是必讀，指紋都要記。
    '13e': os.path.join('common', '13e-S2-素材行與分類規則.md'),
    '13f': os.path.join('common', '13f-S2-大分類與各站規則.md'),
    '13c2': os.path.join('common', '13c2-S2-定時掃帶-v3省token-下.md'),
    '13b': os.path.join('common', '13b-S2-定時掃帶-v2省token.md'),
    '13c': os.path.join('common', '13c-S2-定時掃帶-v3省token.md'),
    '13d': os.path.join('common', '13d-S2-定時掃帶-v4.md'),
}


def rule_shas(repo=REPO):
    """規則檔內容指紋。讀不到的記 null——檔案被改名／搬走要看得出來，
    不是靜默省略（省略會讓後人以為那一版沒有這個檔案）。"""
    out = {}
    for key, rel in RULE_FILES.items():
        try:
            with open(os.path.join(repo, rel), 'rb') as f:
                out[key] = hashlib.sha256(f.read()).hexdigest()[:12]
        except OSError:
            out[key] = None
    return out


def repo_head(repo=REPO):
    """repo 的 commit 與髒不髒。規則檔 sha 已經很精準，這個是給人回頭查用的。"""
    def git(*a):
        try:
            p = subprocess.run(['git', '-C', repo, *a],
                               capture_output=True, timeout=15)
            if p.returncode != 0:
                return None
            return p.stdout.decode('utf-8', errors='replace').strip()
        except (OSError, subprocess.TimeoutExpired):
            return None

    head = git('rev-parse', '--short', 'HEAD')
    status = git('status', '--porcelain')
    return {'head': head, 'dirty': bool(status) if status is not None else None}


def parse_flags(s):
    """把 launcher 傳來的 `model=sonnet;effort=medium;NoToolBan=False` 拆成 dict。
    格式不對不吞——直接把原字串留在 `_raw`，事後看得出來是誰寫壞的。"""
    if not s:
        return None
    out = {}
    bad = []
    for part in s.split(';'):
        part = part.strip()
        if not part:
            continue
        if '=' in part:
            k, v = part.split('=', 1)
            out[k.strip()] = v.strip()
        else:
            bad.append(part)
    if bad:
        out['_raw'] = s
    return out


def find_latest_session(tdir):
    files = glob.glob(os.path.join(tdir, '*.jsonl'))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def resolve_session_path(session_arg, transcript_dir=None):
    # D7（2026-08-13）：launcher 把掃帶 cwd 設到 scratch 夾後，transcript 目錄
    # 跟著 cwd 命名、每天換資料夾——launcher 會帶 --transcript-dir 明講。
    # 指定目錄不存在／沒檔案時退回舊預設（repo cwd 時代的目錄）並警告，不硬炸。
    tdir = transcript_dir or TRANSCRIPT_DIR
    if transcript_dir and not glob.glob(os.path.join(transcript_dir, '*.jsonl')):
        print(f'警告：--transcript-dir 無 transcript（{transcript_dir}），'
              f'退回預設 {TRANSCRIPT_DIR}', file=sys.stderr)
        tdir = TRANSCRIPT_DIR
    if session_arg:
        p = os.path.join(tdir, f'{session_arg}.jsonl')
        if not os.path.exists(p):
            sys.exit(f'找不到 session transcript：{p}')
        return p
    p = find_latest_session(tdir)
    if not p:
        sys.exit(f'{tdir} 底下沒有任何 .jsonl')
    return p


# s2_state.py 的完整 subparser 名單（2026-08-13 對照 s2_state.py 逐一抓齊，
# 而非憑印象列——之前漏掉的子指令全部落到 's2_state:?'，看不出實際熱點）。
# 'needs-review' 要放在 'add' 前面：`needs-review add` 這種帶次動詞（add/list/
# done）的呼叫要記成 's2_state:needs-review'，不能被次動詞 'add' 搶先比對到。
# 2026-08-24（A10 v2）：補 'set-tc'，並補回**本來就漏掉**的 'patch-entry' 與
# 'fix-first-seen'——s2_state.py 有 23 個 subparser，這個 tuple 之前只列 20 個，
# 那兩支的呼叫一直落在 's2_state:?'、--diff 看不到（既有缺陷，非 v2 造成）。
# ⚠️ 'set-tc' 要排在 'set-top' 之前：兩者都以 'set-t' 開頭，順序反了會被搶先比對。
S2_STATE_SUBCOMMANDS = (
    'needs-review', 'resume', 'pending', 'scratch-dir', 'diff', 'add-batch',
    'add-side', 'update-entry', 'patch-entry', 'fix-first-seen',
    'set-mark', 'set-aired', 'set-alert',
    'set-topic-order', 'set-resident-topics', 'set-category', 'set-tc', 'set-top',
    'remove', 'list-topics', 'show', 'get', 'add',
)


def _has_subcommand_token(cmd, sub):
    """精確比對子指令 token，不吃子字串——避免 'add' 誤配到 'add-batch'／
    'set-top' 誤配到 'set-topic-order'（兩者都以該字串開頭）。"""
    return re.search(r'(?<![\w-])' + re.escape(sub) + r'(?![\w-])', cmd) is not None


def classify_python_c(cmd):
    """python -c 依用途分桶（2026-08-13）——原本全部記成一桶
    '臨時腳本'，看不出 other 佔比，也就看不出還有多少沒被歸類的用途。
    判斷順序有意義：先認生產狀態檔（最重、最該留意的一類），
    再認一般 json 讀寫，其餘依關鍵字歸類，都不中才落 other。"""
    if '-s2-state.json' in cmd:
        return 'python -c:read-state'
    if 'json.load' in cmd or 'json.dump' in cmd:
        return 'python -c:json'
    if 'len(' in cmd or 'wc' in cmd or '字數' in cmd or '長度' in cmd:
        return 'python -c:length-check'
    if 'strftime' in cmd or 'datetime' in cmd or 'timedelta' in cmd:
        return 'python -c:time-convert'
    return 'python -c:other'


def classify_bash_tool(cmd):
    """把 Bash 呼叫依實際做的事分桶，而不是全部算 'Bash'——
    呼叫次數是主要成本變數，混在一起看不出是哪個指令在爆。"""
    if 's2_state.py' in cmd or 's2_state ' in cmd:
        for sub in S2_STATE_SUBCOMMANDS:
            if _has_subcommand_token(cmd, sub):
                return f's2_state:{sub}'
        return 's2_state:?'
    if 'python -c' in cmd or 'python3 -c' in cmd:
        return classify_python_c(cmd)
    if 's2_batch_prep' in cmd:
        # 分到子指令（T9，2026-08-25）。原本一桶到底，於是遙測只看得到
        # 「batch_prep 60 次」、看不出 56 次都是 `inspect`——0825-0100 的診斷
        # 因此只能回頭爬 transcript。沒有這一刀，任何修法都無法用 --diff 驗收。
        m = re.search(r's2_batch_prep\.py["\']?\s+([a-z][a-z-]*)', cmd)
        return f's2_batch_prep:{m.group(1)}' if m else 's2_batch_prep.py'
    if 's2_render' in cmd:
        return 's2_render.py'
    return 'Bash（其他）'


PHASES = ('稽核', 'render', '分類', 'NS', 'AP', 'RT', '其他')


_FILENAME_TOKEN_RE = re.compile(r'[a-z0-9]+')


def _site_from_filename(file_hint):
    """2026-08-18（0430/0730 體檢發現）：從檔名／路徑找站別，只認**完整
    alnum token**（ns_batch.json → token 'ns'；ap4678987 不算，因為
    正規表示式把連續英數字一起吃掉，不會拆出單獨的 'ap'）——避免跟
    素材 id（AP4678987）或內文字樣（apply／capital）誤撞。
    只傳入檔名／指令這種「路徑用字」，不要傳整段組稿內容，否則摘要
    正文提到「美聯社」英文字樣一樣會誤判。"""
    tokens = set(_FILENAME_TOKEN_RE.findall(file_hint.lower()))
    if 'rt' in tokens:
        return 'RT'
    if 'ap' in tokens:
        return 'AP'
    if 'ns' in tokens:
        return 'NS'
    return None


def classify_phase(name, input_str, file_hint=''):
    """P2 分段遙測（2026-08-12）：依 tool input 內容把呼叫標到階段。
    這是把 0812 事後手工爬 2MB log 拆階段的方法寫死成程式——
    沒有它，每次異常都得重新手工拆，而且第一次就因此答錯方向。
    判斷順序有意義：稽核／render／分類的指令裡常夾著站名（--rt-list、
    _rt_batch），所以**流程階段先判、站別後判**。

    回傳 '其他' 以外的值＝「直接命中」（direct）；呼叫端會拿這個
    區分「真的判到」vs「靠前一筆繼承」，供時段回看規則使用（見
    measure() 的 phase_stat 回看重歸屬，MASTER A1 0430/0730 體檢）。"""
    s = input_str.lower()
    if 's2_audit' in s:
        return '稽核'
    if 's2_render' in s:
        return 'render'
    if any(k in s for k in ('set-category', 'set-tc', 's2_topic_dedupe', 'list-topics',
                            'set-topic-order', 'set-resident-topics')):
        return '分類'
    if any(k in s for k in ('reuters', '_rt_', 'rt_list')):
        return 'RT'
    if any(k in s for k in ('newsroom.ap.org', 'apnewsroom', '_ap_')):
        return 'AP'
    if any(k in s for k in ('ns.cnn.com', 'newsource', '_ns_', 'cnn.com')):
        return 'NS'
    # 檔名 token 判站：Write ns_batch_0430.json／batch_ns_0730.json 這種
    # 站名不夾在底線兩側的變體，原本的字串比對接不到，只能靠上一筆繼承——
    # 而繼承來源常常是稍早的 list-topics（真的是分類），造成組稿的長思考
    # 被算進分類桶（0818-0430：15.0 分裡 12.2 分其實是三站組稿）。
    by_file = _site_from_filename(file_hint)
    if by_file:
        return by_file
    return '其他'


def measure(session_path):
    last_usage = {}  # message.id -> usage dict（保留最後一筆）
    tool_calls = 0
    tool_by_name = {}
    events = []  # (timestamp_iso, phase, is_direct) 每個 tool_use 一筆，for 分段遙測
    n = 0
    last_ts = None
    prev_phase = None  # 沿用「連續區段」假設：無標記的呼叫（click／snapshot／
    #                    讀寫暫存檔）繼承前一個呼叫的階段，跟手工拆帳同一套邏輯
    with open(session_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = d.get('timestamp')
            if ts:
                last_ts = ts
            msg = d.get('message') or {}
            usage = msg.get('usage')
            if usage:
                n += 1
                mid = msg.get('id') or f'_noid_{n}'
                last_usage[mid] = usage
            for block in (msg.get('content') or []):
                if not isinstance(block, dict) or block.get('type') != 'tool_use':
                    continue
                tool_calls += 1
                name = block.get('name') or '?'
                inp = block.get('input') or {}
                raw_input = json.dumps(inp, ensure_ascii=False)
                # 只取路徑／指令這種「用字」給檔名 token 判站，不要把 Write
                # 的 content 全文（組稿正文）也丟進去——摘要正文提到「美聯社」
                # 這類字樣一樣會誤判站別（見 classify_phase／_site_from_filename）。
                file_hint = inp.get('command') or inp.get('file_path') or ''
                if name == 'Bash':
                    cmd = (block.get('input') or {}).get('command', '')
                    name = classify_bash_tool(cmd)
                tool_by_name[name] = tool_by_name.get(name, 0) + 1
                if ts:
                    # Task 類工具（TaskCreate/TaskUpdate/TaskList/TaskGet/
                    # TaskOutput/TaskStop……)一律不看 input 內容分類——
                    # 0813-0430 實例：TaskCreate 待辦描述文字含「set-category」
                    # 字樣，被關鍵字比對誤判成「分類」階段，把後面 NS 寫摘要的
                    # 長思考全記歪（顯示 7.2 分，真值約 2.5 分）。直接當「其他」
                    # 走繼承前一階段的路徑，跟 click／snapshot 等無標記呼叫同一套邏輯。
                    if name.startswith('Task'):
                        raw_ph = '其他'
                    else:
                        raw_ph = classify_phase(name, raw_input, file_hint)
                    is_direct = raw_ph != '其他'  # 給 phase_stat 回看規則用
                    ph = raw_ph if is_direct else (prev_phase or raw_ph)
                    prev_phase = ph
                    events.append((ts, ph, is_direct))

    # 分段耗時：呼叫 i 的「時段」＝t[i]～t[i+1]（含工具執行＋下一步思考），
    # 歸給呼叫 i 的階段；最後一個呼叫用 transcript 末行時間戳收尾。
    # 邊界歸屬跟手工拆帳的口徑不完全相同（手工版把整備／組稿時間留白，
    # 本版沿連續區段全額歸給所屬階段），絕對值差 1～3 分；但方法每輪一致，
    # **跨輪比較**才是這個遙測的用途（實測 0812-2000：AP 7.0/23 vs 手工 6.6/22、
    # RT 14.3/70 vs 11.4/58，異常階段一眼可辨）。
    #
    # 回看重歸屬（2026-08-18，0430/0730 體檢發現）：長時段預設歸給「呼叫 i」，
    # 但 list-topics／show --mid 這類分類查詢後面接的長思考，實際上常常是
    # 「正在組下一批 NS/AP/RT 稿子」，不是分類本身在想事情——真正洩漏底的
    # 訊號是**下一筆呼叫（i+1）是不是直接判到別的站**（不是靠繼承）。
    # 只在「gap 夠長（≥60 秒，跟這個 repo 其他健檢工具的停頓判準一致）
    # 且 i+1 是直接命中、站別跟 i 不同」才回看重歸屬；短 gap／i+1 也是繼承
    # 一律維持原歸屬——避免把正常的分類節奏也打散。
    REATTRIBUTE_GAP_SEC = 60

    phase_stat = {}
    if events:
        from datetime import datetime

        def parse(ts):
            return datetime.fromisoformat(ts.replace('Z', '+00:00'))

        times = [parse(ts) for ts, _, _ in events]
        times.append(parse(last_ts) if last_ts else times[-1])
        for i, (_, ph, _direct) in enumerate(events):
            sec = max(0.0, (times[i + 1] - times[i]).total_seconds())
            use_ph = ph
            if i + 1 < len(events) and sec >= REATTRIBUTE_GAP_SEC:
                nxt_ph, nxt_direct = events[i + 1][1], events[i + 1][2]
                if nxt_direct and nxt_ph != ph:
                    use_ph = nxt_ph
            st = phase_stat.setdefault(use_ph, {'calls': 0, 'minutes': 0.0})
            st['calls'] += 1
            st['minutes'] += sec / 60
        for st in phase_stat.values():
            st['minutes'] = round(st['minutes'], 1)
        phase_stat = {ph: phase_stat[ph] for ph in PHASES if ph in phase_stat}

    cache_read = sum(u.get('cache_read_input_tokens', 0) for u in last_usage.values())
    cache_creation = sum(u.get('cache_creation_input_tokens', 0) for u in last_usage.values())
    output = sum(u.get('output_tokens', 0) for u in last_usage.values())
    input_tok = sum(u.get('input_tokens', 0) for u in last_usage.values())

    return {
        'session_file': os.path.basename(session_path),
        'requests': len(last_usage),
        'tool_calls': tool_calls,
        'cache_read_input_tokens': cache_read,
        'cache_creation_input_tokens': cache_creation,
        'output_tokens': output,
        'input_tokens': input_tok,
        'cache_read_per_tool_call': round(cache_read / tool_calls, 3) if tool_calls else None,
        # A1 驗收不變量：分類總數必須等於原始工具呼叫數。分桶規則改壞（少一條
        # elif、關鍵字打錯）不會報錯，只會讓某一桶悄悄變 0——這兩個數字對不上
        # 就是唯一會叫出來的訊號。
        'classified_total': sum(tool_by_name.values()),
        'phase_calls_total': sum(v['calls'] for v in phase_stat.values()),
        'phases': phase_stat,
        'tool_calls_by_name': dict(sorted(tool_by_name.items(), key=lambda kv: -kv[1])),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--checkpoint', required=True, help='輪次代號，例如 0812-1200')
    ap.add_argument('--session', help='session id（不帶副檔名）。不帶則自動抓最新修改的 transcript')
    ap.add_argument('--transcript-dir', help='transcript 目錄（D7 之後 launcher 每輪帶入；不帶用舊預設）')
    ap.add_argument('--dry-run', action='store_true', help='只印結果，不寫入 _token_metrics.jsonl')
    ap.add_argument('--flags', help='launcher 旗標，格式 `model=sonnet;effort=medium;NoToolBan=False`')
    args = ap.parse_args()

    session_path = resolve_session_path(args.session, args.transcript_dir)
    result = measure(session_path)
    result = {
        'checkpoint': args.checkpoint,
        **result,
        # A1：這一輪照的是哪一版規則、launcher 帶了什麼旗標。
        # 沒有這兩欄，規則改動的效果會被誤算到腳本頭上。
        'rule_shas': rule_shas(),
        'repo': repo_head(),
        'launcher_flags': parse_flags(args.flags),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result['classified_total'] != result['tool_calls']:
        print(f'⚠️ 分類總數 {result["classified_total"]} ≠ 工具呼叫數 '
              f'{result["tool_calls"]}——分桶規則可能改壞了', file=sys.stderr)

    if args.dry_run:
        return

    target = METRICS_FILE
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'a', encoding='utf-8') as f:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
    except OSError as e:
        print(f'警告：寫入 {target} 失敗（{e}），改寫本機 {METRICS_FILE_FALLBACK}', file=sys.stderr)
        target = METRICS_FILE_FALLBACK
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, 'a', encoding='utf-8') as f:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')

    print(f'\n已寫入 {target}', file=sys.stderr)


if __name__ == '__main__':
    main()
