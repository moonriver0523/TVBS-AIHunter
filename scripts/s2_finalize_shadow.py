#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""S2 收工流程唯讀 shadow 報告。

這支工具只讀狀態檔與 Claude Code 掃帶 log；不匯入、也不呼叫任何會寫入
production state 的 S2 模組。報告只印到 stdout，讓 shadow 試跑不會留下另一份
會被誤認為真相源的檔案。

用法：
    python scripts/s2_finalize_shadow.py --state <MMDD-s2-state.json> --log <掃帶log.txt>
    python scripts/s2_finalize_shadow.py --state <MMDD-s2-state.json> --log-dir D:/Downloads/S2掃帶log
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter


DEFAULT_LOG_DIR = r"D:\Downloads\S2掃帶log"
BASE_EXPECTED_CALLS = 3  # audit/reconcile + render + resume verification
MAX_EXPECTED_CALLS = 5   # 再加 ENEX、ABC 各一次 platform reconcile


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def _warning(warnings, message):
    warnings.append(message)


def load_state(path, warnings):
    """唯讀載入 state；任何缺漏都退成空資料並留下警告。"""
    if not path:
        _warning(warnings, "未指定狀態檔；無法檢查 reconcile_log。")
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        _warning(warnings, f"狀態檔讀取失敗：{path}（{exc}）")
        return {}
    if not isinstance(data, dict):
        _warning(warnings, f"狀態檔頂層不是 object：{path}")
        return {}
    return data


def state_top(state):
    """同時支援磁碟正式 schema（top 欄位在頂層）與 s2_state.load 的內部 schema。"""
    wrapped = state.get("_top")
    if isinstance(wrapped, dict):
        return wrapped
    if not isinstance(state, dict):
        return {}
    return {key: value for key, value in state.items() if key not in ("items", "date")}


def _tool_text(block):
    inp = block.get("input")
    if isinstance(inp, dict):
        command = inp.get("command")
        if isinstance(command, str):
            return command
        try:
            return json.dumps(inp, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return str(inp)
    return str(inp or "")


def load_tool_calls(path, warnings):
    """從 JSONL 掃帶 log 取出 assistant tool_use，依 tool_use id 去重。"""
    if not path:
        _warning(warnings, "找不到可比對的掃帶 log；只顯示固定流程規劃。")
        return []
    calls = []
    seen_ids = set()
    bad_lines = 0
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    bad_lines += 1
                    continue
                message = row.get("message")
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    call_id = block.get("id")
                    if call_id and call_id in seen_ids:
                        continue
                    if call_id:
                        seen_ids.add(call_id)
                    calls.append({
                        "id": call_id or f"line-{line_no}-{len(calls)}",
                        "name": str(block.get("name") or "unknown"),
                        "text": _tool_text(block),
                        "timestamp": str(row.get("timestamp") or ""),
                    })
    except OSError as exc:
        _warning(warnings, f"掃帶 log 讀取失敗：{path}（{exc}）")
        return []
    if bad_lines:
        _warning(warnings, f"掃帶 log 有 {bad_lines} 行不是合法 JSON，已略過。")
    if not calls:
        _warning(warnings, f"掃帶 log 內找不到 tool_use：{path}")
    return calls


def classify_call(call):
    text = call["text"].lower().replace("\\", "/")
    if "s2_audit.py" in text:
        return "audit+三站reconcile"
    if "s2_platform_reconcile.py" in text:
        return "平台reconcile"
    if "s2_render.py" in text:
        return "render"
    if "s2_state.py" in text and re.search(r"\bresume\b", text):
        return "render後驗證"
    if ("s2_topic_review.py" in text or "s2_topic_dedupe.py" in text or
            ("s2_state.py" in text and re.search(
                r"\b(set-top|set-run|set-tc|set-category|needs-review|patch-entry)\b", text))):
        return "收工判斷/修補"
    return "其他"


def finalize_slice(calls, warnings):
    """以第一個 audit 為實際收工比對窗起點；沒有時 fail-open 使用首個 render。"""
    for index, call in enumerate(calls):
        if "s2_audit.py" in call["text"].lower():
            return calls[index:], "第一個 s2_audit.py"
    for index, call in enumerate(calls):
        if "s2_render.py" in call["text"].lower():
            _warning(warnings, "log 找不到 s2_audit.py；改以第一個 s2_render.py 當收工窗起點。")
            return calls[index:], "第一個 s2_render.py（audit 缺漏）"
    _warning(warnings, "log 找不到 audit/render 收工錨點；無法估算實際收工段呼叫。")
    return [], "無"


def choose_log(explicit_log, log_dir, checkpoint, warnings):
    if explicit_log:
        return explicit_log
    if not log_dir or not os.path.isdir(log_dir):
        _warning(warnings, f"log 目錄不存在：{log_dir}")
        return None
    candidates = glob.glob(os.path.join(log_dir, "掃帶log-*.txt"))
    if checkpoint:
        compact = checkpoint.replace("-", "")
        mmdd = checkpoint[:4]
        hhmm_match = re.search(r"-(\d{4})", checkpoint)
        hhmm = hhmm_match.group(1) if hhmm_match else ""
        matched = [p for p in candidates
                   if compact in os.path.basename(p).replace("-", "") or
                   (mmdd and hhmm and f"{mmdd}-{hhmm}" in os.path.basename(p))]
        if matched:
            candidates = matched
        else:
            _warning(warnings, f"找不到 checkpoint {checkpoint} 的 log；改用目錄內最新一份。")
    if not candidates:
        _warning(warnings, f"log 目錄沒有 掃帶log-*.txt：{log_dir}")
        return None
    return max(candidates, key=os.path.getmtime)


def reconcile_summary(state, checkpoint, warnings):
    top = state_top(state)
    cp = checkpoint or str(top.get("checkpoint") or "")
    raw_log = top.get("reconcile_log")
    if not isinstance(raw_log, dict):
        _warning(warnings, "狀態檔缺少有效的 _top.reconcile_log。")
        return cp, [], ["RT", "AP", "NS"]
    row = raw_log.get(cp)
    if not isinstance(row, dict):
        _warning(warnings, f"reconcile_log 沒有本輪 {cp or '<空 checkpoint>'} 的資料。")
        return cp, [], ["RT", "AP", "NS"]
    present = [site for site in ("RT", "AP", "NS") if site in row]
    return cp, present, [site for site in ("RT", "AP", "NS") if site not in row]


def build_report(state_path, log_path=None, log_dir=DEFAULT_LOG_DIR, checkpoint=None):
    warnings = []
    state = load_state(state_path, warnings)
    top = state_top(state)
    effective_cp = checkpoint or str(top.get("checkpoint") or "")
    selected_log = choose_log(log_path, log_dir, effective_cp, warnings)
    calls = load_tool_calls(selected_log, warnings)
    final_calls, anchor = finalize_slice(calls, warnings)
    counts = Counter(classify_call(call) for call in final_calls)
    relevant = sum(counts.get(key, 0) for key in (
        "audit+三站reconcile", "平台reconcile", "render", "render後驗證"))
    cp, present, missing = reconcile_summary(state, effective_cp, warnings)

    repeats = []
    for label, allowed in (("audit+三站reconcile", 1), ("平台reconcile", 2),
                           ("render", 1), ("render後驗證", 1)):
        if counts[label] > allowed:
            repeats.append(f"{label} 多 {counts[label] - allowed} 次")

    lines = [
        "=== S2 finalize shadow（唯讀；未執行 audit/reconcile/render）===",
        f"狀態檔：{state_path or '<未指定>'}",
        f"掃帶 log：{selected_log or '<無>'}",
        f"checkpoint：{cp or '<無法判定>'}",
        "",
        "【收斂後固定流程（規劃，不執行）】",
        "1. 一次確認 state、txt 與三站清單快照路徑（由同一個收工命令接參數）。",
        "2. 一次 s2_audit.py，同時完成七項離線稽核與 RT/AP/NS 對帳。",
        "3. 排定有掃時，ENEX、ABC 各最多一次 s2_platform_reconcile.py。",
        "4. 所有必要修補完成後只跑一次 s2_render.py。",
        "5. 一次 s2_state.py resume 驗證 render 後無變動。",
        f"預期工具呼叫：約 {BASE_EXPECTED_CALLS}–{MAX_EXPECTED_CALLS} 次"
        "（三站輪 3 次；五站輪最多 5 次；人工修補另計）。",
        "",
        f"【實際收工段比對｜起點：{anchor}】",
        f"整份 log 工具呼叫：{len(calls)} 次",
        f"收工窗工具呼叫：{len(final_calls)} 次",
        f"其中 audit/reconcile/render/驗證：{relevant} 次",
        "分類：" + "｜".join(
            f"{label} {counts.get(label, 0)}" for label in
            ("audit+三站reconcile", "平台reconcile", "render", "render後驗證",
             "收工判斷/修補", "其他")),
        "重複訊號：" + ("；".join(repeats) if repeats else "未見超過固定流程上限"),
        "",
        "【狀態檔對帳留痕】",
        "已記錄：" + ("／".join(present) if present else "無"),
        "缺少：" + ("／".join(missing) if missing else "無"),
    ]
    if warnings:
        lines.extend(["", "【警告（fail-open）】"] + [f"- {item}" for item in warnings])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="唯讀比較 S2 收工固定流程與實際工具呼叫")
    parser.add_argument("--state", required=True, help="S2 狀態檔")
    parser.add_argument("--log", help="指定掃帶 JSONL log；省略時依 checkpoint 從 --log-dir 選")
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR, help="掃帶 log 目錄")
    parser.add_argument("--checkpoint", help="覆寫 state 內 checkpoint，只用於選 log／查留痕")
    args = parser.parse_args(argv)
    try:
        print(build_report(args.state, args.log, args.log_dir, args.checkpoint), end="")
    except Exception as exc:  # shadow 工具不得因未知髒資料拖垮無人輪次
        print("=== S2 finalize shadow（唯讀）===")
        print(f"警告：shadow 分析遇到未預期資料，已 fail-open：{type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
