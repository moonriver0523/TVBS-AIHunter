# -*- coding: utf-8 -*-
"""R29（2026-09-08）：對帳桶鍵與窗尾一律走 `S2_CHECKPOINT`，不吃狀態檔頂層 checkpoint。

為什麼要釘死——0908-0100 那輪的兩個實錯，同一個根：`set-top checkpoint` 依 13c3
是**收工才下**，稽核跑在它之前，所以稽核看到的頂層 checkpoint 永遠停在上一輪。

  ① 桶鍵：本輪對帳被寫進 `reconcile_log["0907-2200"]`，**蓋掉 22:00 輪的原始留痕**
     （ts 由 22:3x 變 2026-09-08T01:22:19）；render 查本輪查不到，誤報「三站全缺」。
  ② 窗尾：窗變成 13:00–22:00，22:00 之後才上站的素材若真的漏收，會被歸進
     「窗外 N 則屬下一輪，不算漏」而**靜默放過**。那輪 40 則剛好全收，沒爆出來。

用法：python -X utf8 scripts/test_s2_r29_bucket.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.pop("S2_CHECKPOINT", None)      # 先清乾淨，下面每案自己設
import s2_render as R  # noqa: E402

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


def cap(state):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        R.warn_unreconciled(state)
    return buf.getvalue()


FULL = {"RT": {"missing": 0}, "AP": {"missing": 0}, "NS": {"missing": 0}}


def st(cp, log):
    return {"_top": {"checkpoint": cp, "reconcile_log": log}, "items": {}}


# ── ① render：桶鍵優先吃環境變數 ────────────────────────────────
try:
    os.environ["S2_CHECKPOINT"] = "0908-0100"
    out = cap(st("0907-2200", {"0908-0100": FULL}))
    report("render：本輪紀錄在 0908-0100、頂層還停在 0907-2200 → 報 OK",
           "OK 清單對帳三站齊全（0908-0100）" in out, out.strip()[:70])

    out = cap(st("0907-2200", {"0907-2200": FULL}))
    report("render：只有上一輪的成績 → 照樣警告，且點名本輪桶鍵",
           "沒有做清單對帳" in out and "（0908-0100）" in out, out.strip()[:80])

    os.environ["S2_CHECKPOINT"] = "亂寫的東西"
    out = cap(st("0907-2200", {"0907-2200": FULL}))
    report("render：環境變數格式不合就退回頂層 checkpoint（不當機、不誤判）",
           "OK 清單對帳三站齊全（0907-2200）" in out, out.strip()[:70])
finally:
    os.environ.pop("S2_CHECKPOINT", None)

out = cap(st("0907-2200", {"0907-2200": FULL}))
report("render：沒設環境變數時行為不變（手動跑稽核的情境）",
       "OK 清單對帳三站齊全（0907-2200）" in out, out.strip()[:70])


# ── ②③ s2_audit：桶鍵不覆蓋前一輪＋跨夜窗尾算得出來 ──────────
d = tempfile.mkdtemp()
state_path = os.path.join(d, "0907-s2-state.json")
txt_path = os.path.join(d, "0907晚班交接.txt")
list_path = os.path.join(d, "_audit_rt_0100.txt")

PREV = {"RT": {"list": 9, "got": 9, "missing": 0, "missing_ids": [], "cross_day": [],
               "ts": "2026-09-07T22:31:00+08:00"}}


def write_state():
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({
            "date": "0907",
            "checkpoint": "0907-2200",          # ⚠️ set-top 還沒下，停在上一輪
            "window_start": "2026-09-07 13:00",
            "reconcile_log": {"0907-2200": dict(PREV)},
            "items": [{"id": "RT0001", "source": "RT", "first_seen_checkpoint": "0907-2200",
                       "script_status": "has_script", "raw_entry": "RT0001 (甲) ▎乙。",
                       "category": {"大分類": "國際", "中主題": "測試", "小分題": "丙"},
                       "src_text": "x", "tc": {"T": ["政治"], "C": ["歐洲"]}}],
        }, f, ensure_ascii=False)


with open(txt_path, "w", encoding="utf-8") as f:
    f.write("測試用交接檔\n")
# RT0001 已在庫；RT0002 上站時間 09/08 00:30——落在 22:00→01:00 這段，是本輪窗內
with open(list_path, "w", encoding="utf-8") as f:
    f.write("RT0001|09/07/2026 21:10\nRT0002|09/08/2026 00:30\n")


def run_audit(env_cp):
    write_state()
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("S2_CHECKPOINT", None)
    if env_cp:
        env["S2_CHECKPOINT"] = env_cp
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "s2_audit.py"),
                        "--mmdd", "0907", "--file", state_path, "--txt", txt_path,
                        "--rt-list", list_path],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    with open(state_path, encoding="utf-8") as f:
        return (r.stdout or "") + (r.stderr or ""), json.load(f)


out, st_after = run_audit("0908-0100")
log = st_after.get("reconcile_log") or {}
report("audit：對帳寫進本輪桶（0908-0100）", "RT" in (log.get("0908-0100") or {}),
       str(sorted(log)))
report("audit：上一輪（0907-2200）的留痕沒被蓋掉",
       (log.get("0907-2200") or {}).get("RT", {}).get("ts") == PREV["RT"]["ts"],
       json.dumps(log.get("0907-2200"), ensure_ascii=False)[:120])
report("audit：跨夜窗尾算得出來，00:30 那則算窗內漏收（不是「窗外屬下一輪」）",
       "窗內未收 1" in out and "窗外 0" in out,
       [l for l in out.splitlines() if "清單" in l and "已收" in l][:1])

out, st_after = run_audit(None)
log = st_after.get("reconcile_log") or {}
report("audit：沒有環境變數時退回頂層 checkpoint（手動補跑的情境不變）",
       "RT" in (log.get("0907-2200") or {}) and "0908-0100" not in log, str(sorted(log)))

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
