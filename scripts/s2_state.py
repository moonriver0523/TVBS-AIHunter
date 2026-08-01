# -*- coding: utf-8 -*-
"""S2 定時掃帶狀態檔代管腳本（V2）。

agent 一律透過本腳本讀寫狀態，不直接開 JSON。
用法見 common/13b-S2-定時掃帶-v2省token.md。

狀態檔預設路徑：G:\\我的雲端硬碟\\Claude共用\\自動掃帶系統\\s2-state.json
（可用 --file 覆蓋；找不到時自動建立空狀態。）
"""
import argparse
import io
import json
import os
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

DEFAULT_FILE = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\s2-state.json"


def load(path):
    if not os.path.exists(path):
        return {"date": datetime.now().strftime("%m%d"), "items": {}}
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: 狀態檔讀取失敗（{e}）。請確認檔案未損壞後重跑；不要手動改 JSON。")
        sys.exit(2)


def save(state, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def norm_id(s):
    return s.strip().replace("RTV", "RT", 1) if s.strip().startswith("RTV") else s.strip()


def cmd_resume(state, args):
    items = state["items"]
    pend = [i for i, v in items.items() if v.get("script_status") == "pending"]
    todo = [i for i, v in items.items()
            if v.get("compiled") is None or v.get("entry_updated", "") > (v.get("compiled") or "")]
    review = [i for i, v in items.items() if v.get("needs_review")]
    cps = sorted({v.get("last_checked_checkpoint", "") for v in items.values() if v.get("last_checked_checkpoint")})
    print(f"日期:{state.get('date','?')} 共{len(items)}則 pending:{len(pend)} 待整併:{len(todo)} 待人工:{len(review)}")
    print(f"最近檢查點:{cps[-1] if cps else '無'}")
    if pend:
        print("pending: " + ",".join(sorted(pend)))
    if todo:
        print("待整併: " + ",".join(sorted(todo)))
    if review:
        print("待人工: " + ",".join(sorted(review)))
    print("下一步：批次擷取用 diff 找新素材；整併用 to-compile。")


def cmd_diff(state, args):
    ids = [norm_id(x) for x in args.ids.split(",") if x.strip()]
    new, seen = [], []
    for i in ids:
        if i in state["items"]:
            state["items"][i]["last_checked_checkpoint"] = args.checkpoint
            seen.append(i)
        else:
            new.append(i)
    save(state, args.file)
    print("NEW: " + (",".join(new) if new else "(無)"))
    pend_seen = [i for i in seen if state["items"][i].get("script_status") == "pending"]
    if pend_seen:
        print("已在庫但稿未到（順手可補）: " + ",".join(pend_seen))
    print(f"已在庫 {len(seen)} 則已更新 last_checked={args.checkpoint}")


def read_entry(args):
    if args.entry_file:
        with open(args.entry_file, encoding="utf-8-sig") as f:
            return f.read().strip()
    print("ERROR: 需要 --entry-file")
    sys.exit(2)


def cmd_add(state, args):
    i = norm_id(args.id)
    if i in state["items"]:
        print(f"ERROR: {i} 已存在，要更新內容請用 update-entry")
        sys.exit(2)
    state["items"][i] = {
        "source": args.source,
        "first_seen_checkpoint": args.checkpoint,
        "last_checked_checkpoint": args.checkpoint,
        "script_status": args.status,
        "raw_entry": read_entry(args),
        "entry_updated": args.checkpoint,
        "compiled": None,
        "category": None,
    }
    save(state, args.file)
    print(f"OK 已新增 {i}（{args.status}）")


def cmd_update_entry(state, args):
    i = norm_id(args.id)
    if i not in state["items"]:
        print(f"ERROR: {i} 不存在，請先 add")
        sys.exit(2)
    it = state["items"][i]
    it["raw_entry"] = read_entry(args)
    if args.status:
        it["script_status"] = args.status
    it["entry_updated"] = args.checkpoint or it.get("last_checked_checkpoint", "")
    save(state, args.file)
    print(f"OK 已覆寫 {i}（{it['script_status']}）")


def cmd_pending(state, args):
    pend = sorted(i for i, v in state["items"].items() if v.get("script_status") == "pending")
    print("\n".join(pend) if pend else "(無 pending)")


def cmd_to_compile(state, args):
    out = []
    for i, v in sorted(state["items"].items()):
        if v.get("compiled") is None or v.get("entry_updated", "") > (v.get("compiled") or ""):
            cat = v.get("category") or "(未分類)"
            out.append(f"### {i} [{cat}] {v.get('script_status')}\n{v.get('raw_entry','')}")
    print("\n\n".join(out) if out else "(無待整併項目)")


def cmd_mark_compiled(state, args):
    ids = [norm_id(x) for x in args.ids.split(",") if x.strip()]
    missing = [i for i in ids if i not in state["items"]]
    if missing:
        print(f"ERROR: 不存在的 id：{','.join(missing)}（其餘未標記，請修正後重跑）")
        sys.exit(2)
    for i in ids:
        state["items"][i]["compiled"] = args.checkpoint
    save(state, args.file)
    print(f"OK 已標記 {len(ids)} 則 compiled={args.checkpoint}")


def cmd_set_category(state, args):
    i = norm_id(args.id)
    if i not in state["items"]:
        print(f"ERROR: {i} 不存在")
        sys.exit(2)
    state["items"][i]["category"] = args.cat
    save(state, args.file)
    print(f"OK {i} category={args.cat}")


def cmd_get(state, args):
    i = norm_id(args.id)
    v = state["items"].get(i)
    if not v:
        print(f"ERROR: {i} 不存在")
        sys.exit(2)
    print(json.dumps(v, ensure_ascii=False, indent=1))


def cmd_needs_review(state, args):
    if args.action == "add":
        i = norm_id(args.id)
        state["items"].setdefault(i, {"source": "?", "script_status": "pending",
                                      "raw_entry": "", "compiled": None, "category": None})
        state["items"][i]["needs_review"] = args.note or "待人工"
        save(state, args.file)
        print(f"OK {i} 已記待人工：{args.note}")
    else:
        rows = [(i, v["needs_review"]) for i, v in sorted(state["items"].items()) if v.get("needs_review")]
        print("\n".join(f"{i}: {n}" for i, n in rows) if rows else "(無待人工項目)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default=DEFAULT_FILE)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("resume")
    d = sub.add_parser("diff")
    d.add_argument("--checkpoint", required=True)
    d.add_argument("--ids", required=True)
    a = sub.add_parser("add")
    a.add_argument("--id", required=True)
    a.add_argument("--source", required=True)
    a.add_argument("--checkpoint", required=True)
    a.add_argument("--status", required=True, choices=["has_script", "pending"])
    a.add_argument("--entry-file", required=True)
    u = sub.add_parser("update-entry")
    u.add_argument("--id", required=True)
    u.add_argument("--status", choices=["has_script", "pending"])
    u.add_argument("--checkpoint")
    u.add_argument("--entry-file", required=True)
    sub.add_parser("pending")
    sub.add_parser("to-compile")
    m = sub.add_parser("mark-compiled")
    m.add_argument("--checkpoint", required=True)
    m.add_argument("--ids", required=True)
    c = sub.add_parser("set-category")
    c.add_argument("--id", required=True)
    c.add_argument("--cat", required=True)
    g = sub.add_parser("get")
    g.add_argument("--id", required=True)
    r = sub.add_parser("needs-review")
    r.add_argument("action", choices=["add", "list"])
    r.add_argument("--id")
    r.add_argument("--note")

    args = p.parse_args()
    state = load(args.file)
    {
        "resume": cmd_resume, "diff": cmd_diff, "add": cmd_add,
        "update-entry": cmd_update_entry, "pending": cmd_pending,
        "to-compile": cmd_to_compile, "mark-compiled": cmd_mark_compiled,
        "set-category": cmd_set_category, "get": cmd_get,
        "needs-review": cmd_needs_review,
    }[args.cmd](state, args)


if __name__ == "__main__":
    main()
