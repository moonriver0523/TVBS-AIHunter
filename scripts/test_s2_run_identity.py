# -*- coding: utf-8 -*-
"""scoped 1259 步驟 8–9：run identity（select / pick / metrics --run-id / set-run）。

用法：python -X utf8 scripts/test_s2_run_identity.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ok = True
RID_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
RID_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CP = "0918-1300"


def report(name, passed, detail=""):
    global ok
    ok = ok and bool(passed)
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


import s2_material_schema as M  # noqa: E402
MR = _load("s2_metrics_report", os.path.join(HERE, "s2_metrics_report.py"))


def test_select_run_items():
    both = {
        "id": "AP1111111",
        "first_seen_checkpoint": CP,
        "first_seen_run_id": RID_A,
    }
    only_cp = {
        "id": "AP2222222",
        "first_seen_checkpoint": CP,
        "first_seen_run_id": RID_B,
    }
    only_run = {
        "id": "AP3333333",
        "first_seen_checkpoint": "0918-1700",
        "first_seen_run_id": RID_A,
    }
    neither = {
        "id": "AP4444444",
        "first_seen_checkpoint": "0918-0900",
        "first_seen_run_id": RID_B,
    }
    missing_run = {
        "id": "AP5555555",
        "first_seen_checkpoint": CP,
    }
    empty_run = {
        "id": "AP6666666",
        "first_seen_checkpoint": CP,
        "first_seen_run_id": "",
    }
    null_run = {
        "id": "AP7777777",
        "first_seen_checkpoint": CP,
        "first_seen_run_id": None,
    }

    r = M.select_run_items(
        [both, only_cp, only_run, neither, missing_run, empty_run, null_run],
        CP, RID_A)
    ids = [it.get("id") for it in r["items"]]
    issue_ids = [i.get("id") for i in r["issues"]]
    codes = {i.get("code") for i in r["issues"]}
    report("v2 both-equal include", ids == ["AP1111111"], str(ids))
    report("v2 both-miss no DIAG",
           "AP4444444" not in issue_ids,
           str(issue_ids))
    report("v2 one-sided DIAG",
           set(issue_ids) == {"AP2222222", "AP3333333",
                              "AP5555555", "AP6666666", "AP7777777"}
           and codes == {"RUN_ITEM_TUPLE_MISMATCH"},
           str(issue_ids))
    report("v2 one-sided excluded from items",
           "AP2222222" not in ids and "AP3333333" not in ids)

    legacy = [{"id": "AP8888888", "first_seen_checkpoint": CP}]
    r = M.select_run_items(legacy, CP, run_id=None, root_run_id=None)
    report("legacy checkpoint-only include",
           [it["id"] for it in r["items"]] == ["AP8888888"] and not r["issues"])

    mixed = [legacy[0], {"id": "AP9999999", "first_seen_checkpoint": CP,
                         "first_seen_run_id": RID_A}]
    r = M.select_run_items(mixed, CP, run_id=None, root_run_id=None)
    report("legacy mixed refuses fallback",
           r["items"] == [] and any(i.get("code") == "RUN_ITEM_LEGACY_AMBIGUOUS"
                                    for i in r["issues"]))

    r = M.select_run_items(legacy, CP, run_id=None, root_run_id=RID_A)
    report("legacy blocked when root has run_id", r["items"] == [])


def _pick(rows, checkpoint, run_id=None):
    try:
        return MR.pick(rows, checkpoint, run_id), None
    except SystemExit as e:
        return None, e.code


def test_pick():
    v2a = {"schema_version": 2, "checkpoint": CP, "run_id": RID_A, "n": 1}
    v2b = {"schema_version": 2, "checkpoint": CP, "run_id": RID_B, "n": 2}
    v2a2 = {"schema_version": 2, "checkpoint": CP, "run_id": RID_A, "n": 3}
    v1 = {"checkpoint": CP, "n": 0}

    row, code = _pick([v2a], CP, RID_A)
    report("pick exact tuple", row and row["n"] == 1 and code is None)

    row, code = _pick([v2a, v2a2], CP, RID_A)
    report("pick same tuple last", row and row["n"] == 3)

    row, code = _pick([v2a], CP, RID_B)
    report("pick missing tuple exit 2", code == 2)

    row, code = _pick([v2a, v2b], CP)
    report("pick checkpoint-only ≥2 v2 run_ids exit 2", code == 2)

    row, code = _pick([v2a, v2a2], CP)
    report("pick checkpoint-only single v2 run last", row and row["n"] == 3)

    row, code = _pick([v1, v1], CP)
    report("pick legacy checkpoint-only last", row and row["n"] == 0)

    parse = getattr(MR, "parse_selector", None)
    report("parse_selector exists", callable(parse))
    if callable(parse):
        report("parse checkpoint only", parse(CP) == (CP, None))
        report("parse CHECKPOINT/RUN_ID", parse(f"{CP}/{RID_A}") == (CP, RID_A))


def test_token_metrics_run_id():
    py = sys.executable
    script = os.path.join(HERE, "s2_token_metrics.py")
    r = subprocess.run(
        [py, script, "--checkpoint", CP],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    report("metrics missing --run-id nonzero", r.returncode != 0,
           f"code={r.returncode} err={r.stderr[-200:]}")
    help_r = subprocess.run(
        [py, script, "-h"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    blob = (help_r.stdout or "") + (help_r.stderr or "")
    report("metrics help lists --run-id", "--run-id" in blob)


def test_set_run():
    py = sys.executable
    script = os.path.join(HERE, "s2_state.py")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "0918-s2-state.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": "2026-09-18", "checkpoint": "0918-0900",
                       "items": []}, f)
        r = subprocess.run(
            [py, "-X", "utf8", script, "--file", path, "set-run",
             "--checkpoint", CP, "--run-id", RID_A,
             "--checkpoint-label", "補漏"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        report("set-run exit 0", r.returncode == 0,
               f"code={r.returncode} out={r.stdout!r} err={r.stderr[-300:]}")
        with open(path, encoding="utf-8") as f:
            disk = json.load(f)
        report("set-run flat root checkpoint", disk.get("checkpoint") == CP)
        report("set-run flat root run_id", disk.get("run_id") == RID_A)
        report("set-run flat root label", disk.get("checkpoint_label") == "補漏")
        report("set-run no _top on disk", "_top" not in disk)

        r2 = subprocess.run(
            [py, "-X", "utf8", script, "--file", path, "set-run",
             "--checkpoint", "18:00", "--run-id", RID_A],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        report("set-run bad checkpoint exit 2", r2.returncode == 2)


if __name__ == "__main__":
    test_select_run_items()
    test_pick()
    test_token_metrics_run_id()
    test_set_run()
    sys.exit(0 if ok else 1)
