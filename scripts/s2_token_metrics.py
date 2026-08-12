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
import json
import os
import sys

TRANSCRIPT_DIR = os.path.expanduser(
    r'~\.claude\projects\E--GitHub-TVBS-AIHunter'
)
METRICS_FILE = (
    r'G:\我的雲端硬碟\Claude共用\自動掃帶系統\S2掃帶log\_token_metrics.jsonl'
)
METRICS_FILE_FALLBACK = r'D:\Downloads\S2掃帶log\_token_metrics.jsonl'


def find_latest_session():
    files = glob.glob(os.path.join(TRANSCRIPT_DIR, '*.jsonl'))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def resolve_session_path(session_arg):
    if session_arg:
        p = os.path.join(TRANSCRIPT_DIR, f'{session_arg}.jsonl')
        if not os.path.exists(p):
            sys.exit(f'找不到 session transcript：{p}')
        return p
    p = find_latest_session()
    if not p:
        sys.exit(f'{TRANSCRIPT_DIR} 底下沒有任何 .jsonl')
    return p


def classify_bash_tool(cmd):
    """把 Bash 呼叫依實際做的事分桶，而不是全部算 'Bash'——
    呼叫次數是主要成本變數，混在一起看不出是哪個指令在爆。"""
    if 's2_state.py' in cmd or 's2_state ' in cmd:
        for sub in ('set-category', 'update-entry', 'add-batch', 'add-side',
                    'set-alert', 'done', 'show', 'diff', 'get', 'list-topics'):
            if f' {sub}' in cmd or cmd.strip().endswith(sub):
                return f's2_state:{sub}'
        return 's2_state:?'
    if 'python -c' in cmd or 'python3 -c' in cmd:
        return 'python -c（臨時腳本）'
    if 's2_batch_prep' in cmd:
        return 's2_batch_prep.py'
    if 's2_render' in cmd:
        return 's2_render.py'
    return 'Bash（其他）'


PHASES = ('稽核', 'render', '分類', 'NS', 'AP', 'RT', '其他')


def classify_phase(name, input_str):
    """P2 分段遙測（2026-08-12）：依 tool input 內容把呼叫標到階段。
    這是把 0812 事後手工爬 2MB log 拆階段的方法寫死成程式——
    沒有它，每次異常都得重新手工拆，而且第一次就因此答錯方向。
    判斷順序有意義：稽核／render／分類的指令裡常夾著站名（--rt-list、
    _rt_batch），所以**流程階段先判、站別後判**。"""
    s = input_str.lower()
    if 's2_audit' in s:
        return '稽核'
    if 's2_render' in s:
        return 'render'
    if any(k in s for k in ('set-category', 's2_topic_dedupe', 'list-topics',
                            'set-topic-order', 'set-resident-topics')):
        return '分類'
    if any(k in s for k in ('reuters', '_rt_', 'rt_list')):
        return 'RT'
    if any(k in s for k in ('newsroom.ap.org', 'apnewsroom', '_ap_')):
        return 'AP'
    if any(k in s for k in ('ns.cnn.com', 'newsource', '_ns_', 'cnn.com')):
        return 'NS'
    return '其他'


def measure(session_path):
    last_usage = {}  # message.id -> usage dict（保留最後一筆）
    tool_calls = 0
    tool_by_name = {}
    events = []  # (timestamp_iso, phase) 每個 tool_use 一筆，for 分段遙測
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
                raw_input = json.dumps(block.get('input') or {}, ensure_ascii=False)
                if name == 'Bash':
                    cmd = (block.get('input') or {}).get('command', '')
                    name = classify_bash_tool(cmd)
                tool_by_name[name] = tool_by_name.get(name, 0) + 1
                if ts:
                    ph = classify_phase(name, raw_input)
                    if ph == '其他' and prev_phase:
                        ph = prev_phase
                    prev_phase = ph
                    events.append((ts, ph))

    # 分段耗時：呼叫 i 的「時段」＝t[i]～t[i+1]（含工具執行＋下一步思考），
    # 歸給呼叫 i 的階段；最後一個呼叫用 transcript 末行時間戳收尾。
    # 邊界歸屬跟手工拆帳的口徑不完全相同（手工版把整備／組稿時間留白，
    # 本版沿連續區段全額歸給所屬階段），絕對值差 1～3 分；但方法每輪一致，
    # **跨輪比較**才是這個遙測的用途（實測 0812-2000：AP 7.0/23 vs 手工 6.6/22、
    # RT 14.3/70 vs 11.4/58，異常階段一眼可辨）。
    phase_stat = {}
    if events:
        from datetime import datetime

        def parse(ts):
            return datetime.fromisoformat(ts.replace('Z', '+00:00'))

        times = [parse(ts) for ts, _ in events]
        times.append(parse(last_ts) if last_ts else times[-1])
        for i, (_, ph) in enumerate(events):
            sec = max(0.0, (times[i + 1] - times[i]).total_seconds())
            st = phase_stat.setdefault(ph, {'calls': 0, 'minutes': 0.0})
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
        'phases': phase_stat,
        'tool_calls_by_name': dict(sorted(tool_by_name.items(), key=lambda kv: -kv[1])),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--checkpoint', required=True, help='輪次代號，例如 0812-1200')
    ap.add_argument('--session', help='session id（不帶副檔名）。不帶則自動抓最新修改的 transcript')
    ap.add_argument('--dry-run', action='store_true', help='只印結果，不寫入 _token_metrics.jsonl')
    args = ap.parse_args()

    session_path = resolve_session_path(args.session)
    result = measure(session_path)
    result = {'checkpoint': args.checkpoint, **result}

    print(json.dumps(result, ensure_ascii=False, indent=2))

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
