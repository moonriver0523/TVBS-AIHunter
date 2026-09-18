# -*- coding: utf-8 -*-
"""scoped 1259 step 2：s2_state 16 路徑 writer vs lookup。

cmd_add 走嚴格 writer；其餘走 dispatcher（RTV→RT、NS trim+upper）。
needs-review add 不得用非法 NS 形狀開備註殼。
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SCRIPT = os.path.join(HERE, "s2_state.py")
import s2_state as S  # noqa: E402
import s2_mark_aired as MA  # noqa: E402

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
    r = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, "--file", path, *argv],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return {it["id"]: it for it in json.load(f)["items"]}


def fresh(**extra):
    items = [
        {"id": "RT2880", "source": "RT", "script_status": "has_script",
         "raw_entry": "RT2880 (測試) ▎摘要。▎無BITE。▎00:30",
         "compiled": None, "category": None},
        {"id": "AP1234567", "source": "AP", "script_status": "has_script",
         "raw_entry": "AP1234567 (測試) ▎摘要。▎無BITE。▎00:30",
         "compiled": None, "category": None},
    ]
    items.extend(extra.get("items", []))
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": "0918", "items": items}, f, ensure_ascii=False)
    return path


# ── writer：cmd_add ──────────────────────────────────────────────────────────
p = fresh()
rc, out = run(p, "add", "--id", "SN-1000XX", "--source", "NS",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "SN-1000XX (假) ▎摘要。▎無BITE。▎00:30")
report("cmd_add 拒收非法 NS 星期尾碼 SN-1000XX",
       rc != 0 and "SN-1000XX" not in read(p),
       f"rc={rc} {out.strip()[:160]}")

p = fresh()
rc, out = run(p, "add", "--id", "  sn-1000mo  ", "--source", "NS",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "SN-1000MO (西語) ▎摘要。▎無BITE。▎00:30")
report("cmd_add NS trim+upper 入庫 SN-1000MO",
       rc == 0 and "SN-1000MO" in read(p),
       f"rc={rc} keys={list(read(p))} {out.strip()[:120]}")

p = fresh()
rc, out = run(p, "add", "--id", "ap4677621", "--source", "AP",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "AP4677621 (假) ▎摘要。▎無BITE。▎00:30")
report("cmd_add 拒收 AP 小寫",
       rc != 0 and "ap4677621" not in read(p) and "AP4677621" not in read(p),
       f"rc={rc} {out.strip()[:160]}")

p = fresh()
rc, out = run(p, "add", "--id", "RTV2881", "--source", "RT",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "RT2881 (假) ▎摘要。▎無BITE。▎00:30")
report("cmd_add writer 不收 RTV",
       rc != 0 and "RTV2881" not in read(p) and "RT2881" not in read(p),
       f"rc={rc} {out.strip()[:160]}")

p = fresh()
rc, out = run(p, "add", "--id", "YNA01", "--source", "YNA",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "YNA01 (韓聯) ▎摘要。▎無BITE。▎00:30")
report("cmd_add 收 YNA01",
       rc == 0 and "YNA01" in read(p),
       f"rc={rc} {out.strip()[:120]}")

p = fresh()
rc, out = run(p, "add", "--id", "CNA02", "--source", "CNA",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "CNA02 (中央社) ▎摘要。▎無BITE。▎00:30")
report("cmd_add 收 CNA02",
       rc == 0 and "CNA02" in read(p),
       f"rc={rc} {out.strip()[:120]}")

p = fresh()
rc, out = run(p, "add", "--id", "OTH03", "--source", "X",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "OTH03 (X) ▎摘要。▎無BITE。▎00:30")
report("cmd_add OTH 真實平台 X",
       rc == 0 and "OTH03" in read(p),
       f"rc={rc} {out.strip()[:120]}")

p = fresh()
rc, out = run(p, "add", "--id", "OTH04", "--source", "OTH",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "OTH04 (假) ▎摘要。▎無BITE。▎00:30")
report("cmd_add 拒收 OTH source=OTH",
       rc != 0 and "OTH04" not in read(p),
       f"rc={rc} {out.strip()[:160]}")

# ── lookup：get / diff ───────────────────────────────────────────────────────
p = fresh()
rc, out = run(p, "get", "--id", "RTV2880")
report("cmd_get dispatcher RTV2880 → 既有 RT2880",
       rc == 0 and "RT2880" not in out.split("ERROR", 1)[0] or rc == 0,
       f"rc={rc} {out.strip()[:80]}")
report("cmd_get RTV 找得到（非 ERROR）",
       rc == 0 and "ERROR" not in out,
       f"rc={rc} {out.strip()[:80]}")

p = fresh()
rc, out = run(p, "diff", "--checkpoint", "0918-1259", "--ids", "RTV2880,RT9999")
report("cmd_diff RTV2880 視為已在庫",
       rc == 0 and "NEW: RT9999" in out and "已在庫 1" in out,
       f"rc={rc} {out.strip()[:200]}")

# ── _set_one_tc / _set_one_category 回 (canonical, err) ──────────────────────
st = {"items": {"RT2880": {"source": "RT", "raw_entry": "x", "script_status": "has_script"}}}
result = S._set_one_tc(st, "RTV2880", "政治/臺灣", {"政治"}, {"臺灣"}, [], ())
report("_set_one_tc 回 tuple", isinstance(result, tuple) and len(result) == 2,
       repr(result))
if isinstance(result, tuple) and len(result) == 2:
    cid, err = result
    report("_set_one_tc RTV 命中 RT2880 且成功", cid == "RT2880" and err is None,
           f"cid={cid!r} err={err!r}")
else:
    report("_set_one_tc RTV 命中 RT2880 且成功", False, repr(result))

result = S._set_one_category(st, "RTV2880", "社會/測試題", strict=False)
report("_set_one_category 回 tuple", isinstance(result, tuple) and len(result) == 2,
       repr(result))
if isinstance(result, tuple) and len(result) == 2:
    cid, err = result
    report("_set_one_category RTV 命中 RT2880", cid == "RT2880" and err is None,
           f"cid={cid!r} err={err!r} cat={st['items']['RT2880'].get('category')}")
else:
    report("_set_one_category RTV 命中 RT2880", False, repr(result))

# ── needs-review：非法 NS 不開殼；自由備註仍可 ──────────────────────────────
p = fresh()
rc, out = run(p, "needs-review", "add", "--id", "SN-1000XX", "--note", "假備註")
it = read(p)
report("needs-review add 拒收非法 NS 形狀、不開殼",
       rc != 0 and "SN-1000XX" not in it,
       f"rc={rc} keys={list(it)} {out.strip()[:160]}")

p = fresh()
rc, out = run(p, "needs-review", "add", "--id", "RT-r9-空白", "--note", "該輪 0 items")
it = read(p)
report("needs-review add 仍收自由備註殼",
       rc == 0 and it.get("RT-r9-空白", {}).get("script_status") == "note",
       f"rc={rc} {out.strip()[:120]}")

p = fresh()
rc, out = run(p, "needs-review", "done", "--ids", "RTV9999")
report("needs-review done 只處理既有（RTV 對不到就整批擋）",
       rc != 0,
       f"rc={rc} {out.strip()[:160]}")

# ── mark_aired：稿單 RTV 對到庫存 RT ─────────────────────────────────────────
fd, rundown = tempfile.mkstemp(suffix=".txt")
os.close(fd)
with open(rundown, "w", encoding="utf-8") as f:
    f.write("RTV2880 (測試) ▎摘要。\nSN-1000XX 不是合法 NS\n")
codes = MA.codes_from(rundown)
report("codes_from 只 trim、不在抽碼階段把 RTV 改成 RT",
       "RTV2880" in codes,
       repr(codes))
p = fresh()
st = S.load(p)
inv = st["items"]
hits = []
for c in codes:
    key = S.lookup_id(c, st)
    if key in inv:
        hits.append(key)
report("mark_aired dispatcher 讓稿單 RTV2880 命中庫存 RT2880",
       hits == ["RT2880"],
       repr(hits))
os.remove(rundown)

print()
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
