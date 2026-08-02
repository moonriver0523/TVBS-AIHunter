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


TOP_FIELDS = ("checkpoint", "updated_at", "window_local",
              "rt_status", "ap_status", "cnn_status", "notes")


def load(path):
    """讀取正式 schema（items 為陣列）並在記憶體中轉成 dict 方便索引。"""
    if not os.path.exists(path):
        return {"date": datetime.now().strftime("%m%d"), "_top": {}, "items": {}}
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: 狀態檔讀取失敗（{e}）。請確認檔案未損壞後重跑；不要手動改 JSON。")
        sys.exit(2)
    top = {k: raw[k] for k in TOP_FIELDS if k in raw}
    items = raw.get("items", [])
    if isinstance(items, list):  # 正式 schema
        items = {it["id"]: {k: v for k, v in it.items() if k != "id"} for it in items}
    return {"date": raw.get("date", datetime.now().strftime("%m%d")),
            "_top": top, "items": items}


def save(state, path):
    """寫回正式 schema：items 還原成陣列、每筆帶回 id。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    out = dict(state.get("_top", {}))
    out["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    out["items"] = [dict(id=i, **v) for i, v in state["items"].items()]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
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
    if args.entry is not None and args.entry_file:
        print("ERROR: --entry 與 --entry-file 擇一，不可同時給")
        sys.exit(2)
    if args.entry is not None:
        return args.entry.strip()
    if args.entry_file:
        with open(args.entry_file, encoding="utf-8-sig") as f:
            return f.read().strip()
    print("ERROR: 需要 --entry（行內短內容）或 --entry-file（長內容）")
    sys.exit(2)


def new_item(source, checkpoint, status, entry):
    return {
        "source": source,
        "first_seen_checkpoint": checkpoint,
        "last_checked_checkpoint": checkpoint,
        "script_status": status,
        "raw_entry": entry,
        "entry_updated": checkpoint,
        "compiled": None,
        "category": None,
    }


def cmd_add(state, args):
    i = norm_id(args.id)
    if i in state["items"]:
        print(f"ERROR: {i} 已存在，要更新內容請用 update-entry")
        sys.exit(2)
    state["items"][i] = new_item(args.source, args.checkpoint, args.status, read_entry(args))
    save(state, args.file)
    print(f"OK 已新增 {i}（{args.status}）")


def cmd_add_batch(state, args):
    """整批新增。撞已存在 id 或格式錯的單筆一律跳過並回報，不中斷；只在結尾 save 一次。"""
    try:
        with open(args.entries, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: --entries 檔讀取失敗（{e}）")
        sys.exit(2)
    if isinstance(data, dict):
        data = data.get("entries")
    if not isinstance(data, list):
        print("ERROR: --entries 需為 JSON 陣列（或含 entries 陣列的物件）")
        sys.exit(2)
    added, skipped = [], []
    for n, e in enumerate(data, 1):
        if not isinstance(e, dict):
            skipped.append(f"第{n}筆: 不是物件")
            continue
        missing = [k for k in ("id", "source", "checkpoint", "status", "entry") if not e.get(k)]
        if missing:
            skipped.append(f"第{n}筆({e.get('id','?')}): 缺 {','.join(missing)}")
            continue
        if e["status"] not in ("has_script", "pending"):
            skipped.append(f"{e['id']}: status 須為 has_script/pending")
            continue
        if not isinstance(e["entry"], str):
            skipped.append(f"{e['id']}: entry 須為字串")
            continue
        i = norm_id(str(e["id"]))
        if i in state["items"]:
            skipped.append(f"{i}: 已存在（要更新請用 update-entry）")
            continue
        state["items"][i] = new_item(e["source"], e["checkpoint"], e["status"], e["entry"].strip())
        added.append(i)
    if added:
        save(state, args.file)
    print(f"OK 新增 {len(added)} 則" + (f"：{','.join(added)}" if added else ""))
    if skipped:
        print(f"跳過 {len(skipped)} 則：")
        print("\n".join("  " + s for s in skipped))


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
            c = v.get("category")
            cat = f"{c['大分類']}/{c['中主題']}" if isinstance(c, dict) else (c or "(未分類)")
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
    if args.pairs and (args.id or args.cat):
        print("ERROR: --pairs 與 --id/--cat 擇一，不可混用")
        sys.exit(2)
    if not args.pairs:
        if not (args.id and args.cat):
            print("ERROR: 單筆需 --id 與 --cat；批次用 --pairs \"id=大分類/中主題;...\"")
            sys.exit(2)
        _set_one_category(state, args.id, args.cat, strict=True)
        save(state, args.file)
        return
    # 批次：分隔符優先用「;」；沒有分號才退回逗號（中主題含逗號時務必用分號）
    sep = ";" if ";" in args.pairs else ","
    done, skipped = [], []
    for tok in (t.strip() for t in args.pairs.split(sep)):
        if not tok:
            continue
        if "=" not in tok:
            skipped.append(f"「{tok}」: 缺 =（格式 id=大分類/中主題）")
            continue
        i, cat = tok.split("=", 1)
        err = _set_one_category(state, i, cat, strict=False)
        (skipped if err else done).append(err or norm_id(i))
    if done:
        save(state, args.file)
    print(f"OK 設定 {len(done)} 則" + (f"：{','.join(done)}" if done else ""))
    if skipped:
        print(f"跳過 {len(skipped)} 則：")
        print("\n".join("  " + s for s in skipped))


def _set_one_category(state, raw_id, cat, strict):
    """設定單筆 category。strict=True 出錯直接 exit；否則回傳錯誤訊息字串。"""
    i = norm_id(raw_id)
    if i not in state["items"]:
        msg = f"{i}: 不存在"
    elif "/" not in cat:
        msg = f"{i}: cat 需為「大分類/中主題」（例：社會/休達移民）"
    else:
        big, mid = cat.split("/", 1)
        state["items"][i]["category"] = {"大分類": big.strip(), "中主題": mid.strip()}
        print(f"OK {i} category={big.strip()}／{mid.strip()}")
        return None
    if strict:
        print("ERROR: " + msg)
        sys.exit(2)
    return msg


def cmd_set_top(state, args):
    """設定頂層欄位（window_local／rt_status／ap_status／cnn_status／notes／checkpoint）。"""
    if args.field not in TOP_FIELDS:
        print(f"ERROR: 欄位須為 {'／'.join(TOP_FIELDS)}")
        sys.exit(2)
    state.setdefault("_top", {})[args.field] = args.value
    save(state, args.file)
    print(f"OK {args.field}={args.value}")


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
    a.add_argument("--entry", help="行內短內容（與 --entry-file 擇一）")
    a.add_argument("--entry-file", help="長內容檔案路徑（與 --entry 擇一）")
    ab = sub.add_parser("add-batch")
    ab.add_argument("--entries", required=True,
                    help="JSON 陣列檔，每筆含 id/source/checkpoint/status/entry")
    u = sub.add_parser("update-entry")
    u.add_argument("--id", required=True)
    u.add_argument("--status", choices=["has_script", "pending"])
    u.add_argument("--checkpoint")
    u.add_argument("--entry", help="行內短內容（與 --entry-file 擇一）")
    u.add_argument("--entry-file", help="長內容檔案路徑（與 --entry 擇一）")
    sub.add_parser("pending")
    sub.add_parser("to-compile")
    m = sub.add_parser("mark-compiled")
    m.add_argument("--checkpoint", required=True)
    m.add_argument("--ids", required=True)
    c = sub.add_parser("set-category")
    c.add_argument("--id")
    c.add_argument("--cat", help="大分類/中主題")
    c.add_argument("--pairs", help='批次："id=大分類/中主題;id2=..."（分隔符優先認分號）')
    st = sub.add_parser("set-top")
    st.add_argument("field")
    st.add_argument("value")
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
        "add-batch": cmd_add_batch,
        "update-entry": cmd_update_entry, "pending": cmd_pending,
        "to-compile": cmd_to_compile, "mark-compiled": cmd_mark_compiled,
        "set-category": cmd_set_category, "get": cmd_get,
        "needs-review": cmd_needs_review, "set-top": cmd_set_top,
    }[args.cmd](state, args)


if __name__ == "__main__":
    main()
