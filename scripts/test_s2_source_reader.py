# -*- coding: utf-8 -*-
"""scoped 1259 step 4：reader classifier 接入 collect／writer 仍拒 CNN alias。"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SCRIPT = os.path.join(HERE, "s2_state.py")
import s2_render_html as H  # noqa: E402
import s2_render_matrix as M  # noqa: E402

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


ENTRY = "SN-1000MO (測) ▎摘要。▎無BITE。▎00:30 ▎畫面：無"


def state_from(items):
    return {
        "date": "0918",
        "items": {it["id"]: {k: v for k, v in it.items() if k != "id"} for it in items},
    }


def row_by_id(rows, iid):
    for r in rows:
        if r.get("id") == iid:
            return r
    return None


items = [
    {"id": "SN-1000MO", "source": "CNN_newsource", "script_status": "has_script",
     "raw_entry": ENTRY, "compiled": None,
     "category": {"大分類": "社會", "中主題": "測"}},
    {"id": "SN-1000TU", "source": "CNN", "script_status": "has_script",
     "raw_entry": "SN-1000TU (測) ▎摘要。▎無BITE。▎00:30 ▎畫面：無",
     "compiled": None, "category": {"大分類": "社會", "中主題": "測"}},
    {"id": "CNN 120000", "source": "SIDE_CNN", "script_status": "has_script",
     "raw_entry": "CNN 120000 (側錄) ▎摘要。▎無BITE。▎00:30",
     "compiled": None, "category": {"大分類": "社會", "中主題": "側錄"}},
    {"id": "YNA01", "source": "YT", "script_status": "has_script",
     "raw_entry": "YNA01 (韓聯) ▎摘要。▎無BITE。▎00:30",
     "compiled": None, "category": {"大分類": "社會", "中主題": "網址"}},
    {"id": "CNA02", "source": "CNA", "script_status": "has_script",
     "raw_entry": "CNA02 (中央社) ▎摘要。▎無BITE。▎00:30",
     "compiled": None, "category": {"大分類": "社會", "中主題": "網址"}},
    {"id": "OTH01", "source": "X", "script_status": "has_script",
     "raw_entry": "OTH01 (X) ▎摘要。▎無BITE。▎00:30",
     "compiled": None, "category": {"大分類": "社會", "中主題": "網址"}},
]
st = state_from(items)
rows = H.collect(st, "0918")

r = row_by_id(rows, "SN-1000MO")
report("CNN_newsource+NS → src=NS kind=wire",
       r is not None and r.get("src") == "NS" and r.get("kind") == "wire",
       repr(r and {k: r[k] for k in ("src", "kind")}))

r = row_by_id(rows, "SN-1000TU")
report("CNN+NS → src=NS kind=wire",
       r is not None and r.get("src") == "NS" and r.get("kind") == "wire",
       repr(r and {k: r[k] for k in ("src", "kind")}))

r = row_by_id(rows, "CNN 120000")
report("SIDE_CNN 不被 CNN alias 吞掉",
       r is not None and r.get("kind") == "side" and r.get("src") in ("SIDE_CNN", "CNN"),
       repr(r and {k: r[k] for k in ("src", "kind")}))

r = row_by_id(rows, "YNA01")
report("legacy YT+YNA → src=YNA kind=url",
       r is not None and r.get("src") == "YNA" and r.get("kind") == "url",
       repr(r and {k: r[k] for k in ("src", "kind")}))

r = row_by_id(rows, "CNA02")
report("direct CNA → src=CNA kind=url",
       r is not None and r.get("src") == "CNA" and r.get("kind") == "url",
       repr(r and {k: r[k] for k in ("src", "kind")}))

r = row_by_id(rows, "OTH01")
report("OTH+X 篩選鍵仍是 OTH",
       r is not None and r.get("src") == "OTH" and r.get("kind") == "url",
       repr(r and {k: r[k] for k in ("src", "kind")}))

line = M.stats_line([x for x in rows if x.get("kind") != "empty"])
report("stats_line 把 CNN_newsource 算進 NS 不是獨立來源",
       "NS" in line and "CNN_newsource" not in line,
       line)

st_miss = state_from([
    {"id": "AP4677621", "source": "AP", "script_status": "has_script",
     "raw_entry": "AP4677621 (測) ▎摘要。▎無BITE。▎00:30",
     "src_text_missing": True, "compiled": None,
     "category": {"大分類": "社會", "中主題": "測"}},
    {"id": "AP4677622", "source": "AP", "script_status": "has_script",
     "raw_entry": "AP4677622 (測) ▎摘要。▎無BITE。▎00:30",
     "src_text": "HEAD: ok\nSCRIPT: body", "compiled": None,
     "category": {"大分類": "社會", "中主題": "測"}},
])
rows_m = H.collect(st_miss, "0918")
r_m = row_by_id(rows_m, "AP4677621")
r_ok = row_by_id(rows_m, "AP4677622")
report("collect src_text_missing → src_missing=1",
       r_m is not None and r_m.get("src_missing") == 1,
       repr(r_m and r_m.get("src_missing")))
report("collect 有原文 → src_missing=0",
       r_ok is not None and not r_ok.get("src_missing"),
       repr(r_ok and r_ok.get("src_missing")))
js_src = open(os.path.join(HERE, "s2_render_html.py"), encoding="utf-8").read()
report("HTML JS 寫 data-src-missing",
       "data-src-missing" in js_src,
       "missing attr wiring")


def run(*argv, state=None):
    r = subprocess.run(
        [sys.executable, "-X", "utf8", SCRIPT, "--file", state, *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


fd, path = tempfile.mkstemp(suffix=".json")
os.close(fd)
with open(path, "w", encoding="utf-8") as f:
    json.dump({"date": "0918", "items": [
        {"id": "RT2880", "source": "RT", "script_status": "has_script",
         "raw_entry": "RT2880 (測) ▎摘要。▎無BITE。▎00:30",
         "compiled": None, "category": None},
    ]}, f, ensure_ascii=False)

rc, out = run("add", "--id", "SN-1MO", "--source", "CNN",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "SN-1MO (假) ▎摘要。▎無BITE。▎00:30", state=path)
with open(path, encoding="utf-8-sig") as f:
    keys = [it["id"] for it in json.load(f)["items"]]
report("new writer 拒收 NS+source=CNN",
       rc != 0 and "SN-1MO" not in keys,
       f"rc={rc} keys={keys} {out.strip()[:160]}")

rc, out = run("add", "--id", "SN-1TU", "--source", "CNN_newsource",
              "--checkpoint", "0918-1259", "--status", "pending",
              "--entry", "SN-1TU (假) ▎摘要。▎無BITE。▎00:30", state=path)
with open(path, encoding="utf-8-sig") as f:
    keys = [it["id"] for it in json.load(f)["items"]]
report("new writer 拒收 NS+source=CNN_newsource",
       rc != 0 and "SN-1TU" not in keys,
       f"rc={rc} keys={keys} {out.strip()[:160]}")

print()
print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
