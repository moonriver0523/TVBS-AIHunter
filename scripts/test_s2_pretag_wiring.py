# -*- coding: utf-8 -*-
"""A31 pre-tagger 四個出口的掛接迴歸（Task 3）。

`s2_pretag.py` 本體的六案例在 `test_s2_pretag.py`；這支只驗證「真的接上了」——
`from-raw` 提示表尾巴印出 `T?=`／`C?=`／🇹🇼、`build` 的 batch row 帶 `suggest`
（前者已在 test_s2_from_raw.py 間接驗過，這裡再明確斷言一次不怕重複）、
`add-batch` 缺 tc 印 💡 建議、涉臺無 🔴🟡 印 🇹🇼 提醒、`lint()` 的訊息併進
「⚠️ 格式待修」段。

用法：python test_s2_pretag_wiring.py
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}' + (f" -> {extra}" if extra else ""))


# ── from-raw：提示表尾加 T?/C?/🇹🇼（Step 1） ─────────────────────
spec = importlib.util.spec_from_file_location("bp_wiring", os.path.join(HERE, "s2_batch_prep.py"))
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)

TMP = tempfile.mkdtemp(prefix="s2_a31_wiring_")


def write_json(name, obj):
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def run_fn(fn, args):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            fn(args)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    return out.getvalue() + err.getvalue(), code


AP_RAW = write_json("ap_raw.json", [
    {"id": "AP2001", "head": "漢光演習今天登場，國軍模擬應變", "script": "SHOTLIST: drill scenes",
     "sb_count": 0, "has_sot": False, "prelim": False, "dur": "00:01:20", "src": "AP"},
])

skel_out = os.path.join(TMP, "ap_skeleton_1300.json")
fr_out, fr_code = run_fn(bp.cmd_from_raw, Args(
    site="ap", raw=AP_RAW, checkpoint="0907-1300", state=None, out=skel_out, page=None,
))
check("from-raw 正常結束", fr_code == 0, f"code={fr_code}\n{fr_out}")
check("from-raw 提示表尾巴印出 T?=／C?=",
      "｜T?=" in fr_out and "｜C?=" in fr_out, fr_out)
check("from-raw 命中涉臺詞印出 🇹🇼", "🇹🇼" in fr_out, fr_out)

# ── build：batch row 帶 suggest（Step 2） ─────────────────────
mini_entries = write_json("mini_entries.json", {
    "AP2001": "◆ AP2001 (備註) 漢光演習畫面。◇畫面重點：戰車機動◇備註：無",
})
batch_out = os.path.join(TMP, "ap_batch_1300.json")
b_out, b_code = run_fn(bp.cmd_build, Args(
    site="ap", raw=AP_RAW, entries=mini_entries, checkpoint="0907-1300",
    skeleton=skel_out, out=batch_out,
))
check("build --skeleton 正常結束", b_code == 0, f"code={b_code}\n{b_out}")
with open(batch_out, encoding="utf-8") as f:
    batch = json.load(f)
if isinstance(batch, dict):          # P1b-2（2026-09-07）：build --skeleton 新格式殼
    batch = batch.get("entries") or []
row = next((r for r in batch if r.get("id") == "AP2001"), {})
check("build row 帶 suggest 鍵", "suggest" in row, str(row))
check("build row 帶 suggest.taiwan/bite", isinstance(row.get("suggest"), dict)
      and "taiwan" in row["suggest"] and "bite" in row["suggest"], str(row.get("suggest")))


# ── add-batch：缺 tc 印 💡；涉臺無 🔴🟡 印 🇹🇼；lint 併進格式待修段（Step 3/4）──
STATE_SCRIPT = os.path.join(HERE, "s2_state.py")


def new_state():
    d = tempfile.mkdtemp(prefix="s2_a31_state_")
    p = os.path.join(d, "s.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"date": "0999", "checkpoint": "0999-1700", "items": []}, f, ensure_ascii=False)
    return d, p


def run_cli(state_path, *args):
    r = subprocess.run([sys.executable, "-X", "utf8", STATE_SCRIPT, "--file", state_path] + list(args),
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def add_batch_cli(state_path, entries):
    # P1b-2（2026-09-08 硬上線）：三站的 batch 一律要帶新格式外殼，
    # 純陣列會被 add-batch 當場退回。測試照生產契約走。
    if isinstance(entries, list):
        entries = {"entries": entries, "new_topics": {}}
    d = os.path.dirname(state_path)
    bp_path = os.path.join(d, "b.json")
    with open(bp_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    return run_cli(state_path, "add-batch", "--entries", bp_path)


d1, sp1 = new_state()
entry_taiwan = ("RT9101 (備註) ▎漢光演習開打，國軍模擬應變。"
                "▎畫面：實兵操演、戰車機動▎無BITE。▎00:30")
out1 = add_batch_cli(sp1, [
    {"id": "RT9101", "source": "RT", "checkpoint": "0999-1700", "status": "has_script",
     "entry": entry_taiwan, "src_text": "drill coverage"},
])
check("add-batch 缺 tc 印 💡 建議", "💡" in out1 and "RT9101" in out1, out1)
check("add-batch 涉臺無🔴🟡印🇹🇼提醒", "🇹🇼" in out1 and "RT9101" in out1, out1)

d2, sp2 = new_state()
long_summary = "測" * 160
entry_long = f"RT9102 (備註) ▎{long_summary}▎畫面：資料畫面▎無BITE。▎00:10"
out2 = add_batch_cli(sp2, [
    {"id": "RT9102", "source": "RT", "checkpoint": "0999-1700", "status": "has_script",
     "entry": entry_long, "src_text": "long summary case"},
])
check("add-batch 的 lint 📏 併進「格式待修」段", "格式待修" in out2 and "📏" in out2, out2)

print(f"\n共 {len(results)} 項，通過 {sum(results)}，失敗 {len(results) - sum(results)}")
sys.exit(0 if all(results) else 1)
