#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""項目2：五站統一 reconcile 與 s2_finish.py 測試（2026-09-17）。"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import s2_state
FINISH_SCRIPT = os.path.join(HERE, "s2_finish.py")
STATE_SCRIPT = os.path.join(HERE, "s2_state.py")
RENDER_SCRIPT = os.path.join(HERE, "s2_render.py")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {extra}" if extra else ""))


def new_env():
    d = tempfile.mkdtemp(prefix="s2_finish_test_")
    sp = os.path.join(d, "0917-s2-state.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump({
            "date": "0917",
            "checkpoint": "0917-1200",
            "_top": {
                "checkpoint": "0917-1200",
                "window_start": "09:00",
                "reconcile_log": {},
            },
            "items": {}
        }, f, ensure_ascii=False)
    scratch = os.path.join(d, "scratch_1200")
    os.makedirs(scratch, exist_ok=True)
    return sp, scratch, d


def run_finish(*args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, "-X", "utf8", FINISH_SCRIPT, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


# 1. RT/AP/NS 三站快照正常，ENEX/ABC 明確 not-scheduled：完成且 exit 0
sp, sc, d = new_env()
# 建立 RT, AP, NS 正常快照（格式: CODE|MM/DD/YYYY HH:MM 或 CODE\t...）
rt_snap = write_file(os.path.join(sc, "_audit_rt_1200.txt"), "RT1001|09/17/2026 10:30\nRT1002|09/17/2026 11:00\n")
ap_snap = write_file(os.path.join(sc, "_audit_ap_1200.txt"), "AP1000001|09/17/2026 10:00\n")
ns_snap = write_file(os.path.join(sc, "_audit_ns_1200.txt"), "WE-001WE|09/17/2026 10:15\n")

# 在狀態檔中填入這幾則素材，模擬全部已收
with open(sp, encoding="utf-8") as f:
    st = json.load(f)
st["items"] = {
    "RT1001": {"source": "RT", "first_seen_checkpoint": "0917-1200"},
    "RT1002": {"source": "RT", "first_seen_checkpoint": "0917-1200"},
    "AP1000001": {"source": "AP", "first_seen_checkpoint": "0917-1200"},
    "WE-001WE": {"source": "NS", "first_seen_checkpoint": "0917-1200"},
}
write_json(sp, st)

code, out = run_finish(
    "--checkpoint", "0917-1200", "--state-file", sp, "--scratch", sc,
    "--not-scheduled", "ENEX", "--not-scheduled", "ABC"
)
check("三站快照正常＋ENEX/ABC 未排程 -> finish exit 0", code == 0, out[-300:])
st_after = s2_state.load(sp)
rl = st_after["_top"]["reconcile_log"]["0917-1200"]
check("reconcile_log 包含 _schema: s2-reconcile/v1", rl.get("_schema") == "s2-reconcile/v1")
check("RT/AP/NS 為 ok，ENEX/ABC 為 not-scheduled",
      rl["RT"]["status"] == "ok" and rl["AP"]["status"] == "ok" and rl["NS"]["status"] == "ok"
      and rl["ENEX"]["status"] == "not-scheduled" and rl["ABC"]["status"] == "not-scheduled")

# 2. 五站全有 evidence 且數量一致：五站 status 全為 ok
enex_cand = write_json(os.path.join(sc, "0917-ENEX-state.json"), {"counts": {"掃描": 5, "收錄": 5}})
abc_cand = write_json(os.path.join(sc, "0917-ABC-state.json"), {"counts": {"掃描": 8, "收錄": 8}})
code, out = run_finish(
    "--checkpoint", "0917-1200", "--state-file", sp, "--scratch", sc,
    "--enex-candidate", enex_cand, "--enex-true-count", "5",
    "--abc-candidate", abc_cand, "--abc-true-count", "8"
)
check("五站均有證據且對帳一致 -> finish exit 0", code == 0, out[-300:])
rl5 = s2_state.load(sp)["_top"]["reconcile_log"]["0917-1200"]
check("五站 status 全為 ok", all(rl5[s]["status"] == "ok" for s in ("RT", "AP", "NS", "ENEX", "ABC")))

# 3. ENEX/ABC count mismatch：formal log 寫入 needs-review
code, out = run_finish(
    "--checkpoint", "0917-1200", "--state-file", sp, "--scratch", sc,
    "--enex-candidate", enex_cand, "--enex-true-count", "7",  # 差 2 則
    "--abc-candidate", abc_cand, "--abc-true-count", "8"
)
check("ENEX count mismatch 仍能正常收工 exit 0（已留痕待人工）", code == 0, out[-300:])
rl_mis = s2_state.load(sp)["_top"]["reconcile_log"]["0917-1200"]
check("ENEX 記錄為 needs-review 且 reason_code=COUNT_MISMATCH",
      rl_mis["ENEX"]["status"] == "needs-review" and rl_mis["ENEX"]["reason_code"] == "COUNT_MISMATCH"
      and rl_mis["ENEX"]["missing"] == 2)

# 4. RT/AP/NS 明確 unavailable -> 寫入 STATION_UNAVAILABLE，不阻塞收工（exit 0）
code, out = run_finish(
    "--checkpoint", "0917-1200", "--state-file", sp,
    "--unavailable", "NS=登入逾時，無法取得清單",
    "--rt-list", rt_snap, "--ap-list", ap_snap,
    "--not-scheduled", "ENEX", "--not-scheduled", "ABC"
)
check("NS 明確標記 unavailable -> exit 0", code == 0, out[-300:])
rl_un = s2_state.load(sp)["_top"]["reconcile_log"]["0917-1200"]
check("NS status=needs-review 且 reason_code=STATION_UNAVAILABLE",
      rl_un["NS"]["status"] == "needs-review" and rl_un["NS"]["reason_code"] == "STATION_UNAVAILABLE"
      and "登入逾時" in rl_un["NS"]["reason"])

# 5. 找不到快照且沒有 unavailable 宣告 -> 寫 missing-evidence 並 exit 1
sp_empty, sc_empty, d_empty = new_env()
code, out = run_finish(
    "--checkpoint", "0917-1200", "--state-file", sp_empty, "--scratch", sc_empty,
    "--not-scheduled", "ENEX", "--not-scheduled", "ABC"
)
check("缺快照且未宣告例外 -> exit 1 警告", code == 1, str(code))
check("報出缺證據站別", "缺證據站別" in out and "RT" in out and "AP" in out and "NS" in out, out[-300:])
rl_missing = s2_state.load(sp_empty)["_top"]["reconcile_log"]["0917-1200"]
check("未提供快照站別寫入 missing-evidence",
      rl_missing["RT"]["status"] == "missing-evidence" and rl_missing["AP"]["status"] == "missing-evidence")

# 6. 不可把上一輪快照當本輪 evidence
# 在 scratch 裡放 _audit_rt_0900.txt（上一輪），但當前 checkpoint 是 1200
write_file(os.path.join(sc_empty, "_audit_rt_0900.txt"), "RT9999|09/17/2026 08:30\n")
code, out = run_finish(
    "--checkpoint", "0917-1200", "--state-file", sp_empty, "--scratch", sc_empty,
    "--not-scheduled", "ENEX", "--not-scheduled", "ABC"
)
check("不撿上一輪 0900 快照頂替 1200 -> RT 依然 missing-evidence", code == 1)
rl_not_picked = s2_state.load(sp_empty)["_top"]["reconcile_log"]["0917-1200"]
check("RT 仍為 missing-evidence", rl_not_picked["RT"]["status"] == "missing-evidence")

# 7. 同一 checkpoint 連跑兩次具冪等性
run_finish(
    "--checkpoint", "0917-1200", "--state-file", sp, "--scratch", sc,
    "--enex-candidate", enex_cand, "--enex-true-count", "5",
    "--abc-candidate", abc_cand, "--abc-true-count", "8"
)
st_run1 = s2_state.load(sp)
run_finish(
    "--checkpoint", "0917-1200", "--state-file", sp, "--scratch", sc,
    "--enex-candidate", enex_cand, "--enex-true-count", "5",
    "--abc-candidate", abc_cand, "--abc-true-count", "8"
)
st_run2 = s2_state.load(sp)
check("連跑兩次狀態檔結構一致、冪等不重複",
      list(st_run1["_top"]["reconcile_log"]["0917-1200"].keys()) == list(st_run2["_top"]["reconcile_log"]["0917-1200"].keys()))
check("連跑兩次狀態檔結構一致、冪等不重複",
      list(st_run1["_top"]["reconcile_log"]["0917-1200"].keys()) == list(st_run2["_top"]["reconcile_log"]["0917-1200"].keys()))

print(f"\nPASS={sum(results)} FAIL={len(results) - sum(results)}")
sys.exit(0 if all(results) else 1)
