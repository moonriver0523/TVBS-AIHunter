# -*- coding: utf-8 -*-
"""scoped 1259 step 5：單筆 src-only UNSET 與 resulting-item src_text_missing。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SCRIPT = os.path.join(HERE, "s2_state.py")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def run(path, *argv):
    r = subprocess.run(
        [sys.executable, "-X", "utf8", SCRIPT, "--file", path, *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def write_state(items):
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": "0918", "items": items}, f, ensure_ascii=False)
    return path


def load_item(path, iid):
    with open(path, encoding="utf-8-sig") as f:
        d = json.load(f)
    for it in d["items"]:
        if it["id"] == iid:
            return it
    return None


RAW = "AP4677621 (測) ▎摘要。▎無BITE。▎00:30"
TS = "2026-09-18T01:00:00+08:00"

p = write_state([{
    "id": "AP4677621", "source": "AP", "script_status": "has_script",
    "raw_entry": RAW, "compiled": None, "category": None,
    "src_text": "HEAD: old\nSCRIPT: old body",
    "needs_review": "BITE 待確認",
    "sb_count": 2,
    "entry_updated": "0918-0100",
    "entry_updated_ts": TS,
    "first_seen_checkpoint": "0918-0100",
}])

# 無任何 mutation → 拒絕
rc, out = run(p, "update-entry", "--id", "AP4677621")
report("無 entry/src mutation 拒絕",
       rc == 2,
       f"rc={rc} {out.strip()[:160]}")

# --clear-src-text 無 entry
it_before = load_item(p, "AP4677621")
rc, out = run(p, "update-entry", "--id", "AP4677621", "--clear-src-text")
it = load_item(p, "AP4677621")
report("--clear-src-text 無 entry 成功",
       rc == 0 and it is not None and it.get("src_text") == "",
       f"rc={rc} src={it.get('src_text')!r} {out.strip()[:120]}")
report("src-only 保留 raw/needs_review/timestamps/sb_count",
       it["raw_entry"] == RAW and it.get("needs_review") == "BITE 待確認"
       and it.get("entry_updated_ts") == TS and it.get("sb_count") == 2
       and it.get("script_status") == "has_script",
       f"raw_changed={it['raw_entry']!=RAW} nr={it.get('needs_review')!r} ts={it.get('entry_updated_ts')}")
report("AP explicit empty 設 src_text_missing",
       it.get("src_text_missing") is True,
       f"flag={it.get('src_text_missing')!r}")

# --src-text-file 無 entry
fd, srcf = tempfile.mkstemp(suffix=".txt")
os.close(fd)
with open(srcf, "w", encoding="utf-8") as f:
    f.write("HEAD: filled\nSCRIPT: body")
rc, out = run(p, "update-entry", "--id", "AP4677621", "--src-text-file", srcf)
it = load_item(p, "AP4677621")
report("--src-text-file 無 entry 成功",
       rc == 0 and "filled" in (it.get("src_text") or ""),
       f"rc={rc} {out.strip()[:120]}")
report("補上原文只 pop flag、不清 needs_review",
       "src_text_missing" not in it and it.get("needs_review") == "BITE 待確認",
       f"flag={it.get('src_text_missing')!r} nr={it.get('needs_review')!r}")

# src-only 不得夾帶 --status
rc, out = run(p, "update-entry", "--id", "AP4677621", "--clear-src-text",
              "--status", "pending")
report("src-only 夾帶 --status 拒絕",
       rc == 2,
       f"rc={rc} {out.strip()[:160]}")

# NS explicit empty blocking、原值不動
p2 = write_state([{
    "id": "SN-1MO", "source": "NS", "script_status": "has_script",
    "raw_entry": "SN-1MO (測) ▎摘要。▎無BITE。▎00:30",
    "src_text": "DESC: keep\nSCRIPT: keep",
    "compiled": None, "category": None,
}])
rc, out = run(p2, "update-entry", "--id", "SN-1MO", "--clear-src-text")
it = load_item(p2, "SN-1MO")
report("NS explicit empty blocking 且原值不動",
       rc == 2 and it.get("src_text") == "DESC: keep\nSCRIPT: keep"
       and "src_text_missing" not in it,
       f"rc={rc} src={it.get('src_text')!r} {out.strip()[:160]}")

# batch src-only：key 存在且空字串 = explicit empty（不能靠 truthiness 跳過）
p3 = write_state([{
    "id": "RT2880", "source": "RT", "script_status": "has_script",
    "raw_entry": "RT2880 (測) ▎摘要。▎無BITE。▎00:30",
    "src_text": "HEAD: old\nSTORY: old",
    "compiled": None, "category": None,
}])
fd, batch = tempfile.mkstemp(suffix=".json")
os.close(fd)
with open(batch, "w", encoding="utf-8") as f:
    json.dump([{"id": "RT2880", "src_text": ""}], f)
rc, out = run(p3, "update-entry", "--batch", batch)
it = load_item(p3, "RT2880")
report("batch key 存在空字串 = explicit empty 可達",
       rc == 0 and it.get("src_text") == "" and it.get("src_text_missing") is True
       and it.get("raw_entry").startswith("RT2880"),
       f"rc={rc} src={it.get('src_text')!r} flag={it.get('src_text_missing')!r} {out.strip()[:160]}")

# add 新 AP 無 src_text → resulting item 設 flag
p4 = write_state([])
# empty items still need allow_create path — add with existing file
with open(p4, "w", encoding="utf-8") as f:
    json.dump({"date": "0918", "items": []}, f)
rc, out = run(p4, "add", "--id", "AP1111111", "--source", "AP",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "AP1111111 (測) ▎摘要。▎無BITE。▎00:30")
it = load_item(p4, "AP1111111")
report("add AP 無 src_text 設 src_text_missing",
       rc == 0 and it is not None and it.get("src_text_missing") is True,
       f"rc={rc} it={None if it is None else {k: it.get(k) for k in ('src_text','src_text_missing')}} {out.strip()[:120]}")

rc, out = run(p4, "resume")
report("resume 印 原文待補:N",
       rc == 0 and "原文待補:1" in out,
       out.strip()[:200])

import s2_render as R  # noqa: E402
with open(p4, encoding="utf-8-sig") as f:
    raw = json.load(f)
st = {"date": raw["date"], "items": {x["id"]: {k: v for k, v in x.items() if k != "id"} for x in raw["items"]}}
txt = R.render(st, window="", base_mmdd="0918", date="")
report("txt 檔頭警告原文待補",
       "原文待補" in txt,
       txt.split("\n")[:8].__repr__())

print()
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
