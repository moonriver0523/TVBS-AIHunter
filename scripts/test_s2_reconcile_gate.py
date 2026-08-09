# -*- coding: utf-8 -*-
"""清單對帳留痕 → render 收工警告：迴歸測試（2026-08-06 立）。

為什麼要釘死：0806 RT 兩次漏收的根因**不是不會做，是沒做完**——10:41 那輪
agent 知道有 `--rt-list`，因為 profile 被鎖而寫下「留待下次補做」，然後直接
render 收工，就再也沒回去。這條鏈補的正是那個缺口：

    s2_audit.py --rt-list …  →  寫 _top.reconcile_log[checkpoint]
    s2_render.py             →  查不到就在收工那一刻大聲喊

⚠️ **最關鍵的一項是「只警告不擋」**：無人值守時段硬擋會讓整輪卡死
（違反 13b §5「半夜禁問」）。若哪天有人把它改成 sys.exit，這支測試要先炸。

用法：python test_s2_reconcile_gate.py
"""
import io
import os
import sys
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
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
    """跑 warn_unreconciled 並收走它印的東西（順便確認它不會中止程式）。"""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            R.warn_unreconciled(state)
    except SystemExit as e:                       # ← 這正是不准發生的事
        return f"__EXIT__{e.code}"
    return buf.getvalue()


def st(cp, log=None):
    top = {"checkpoint": cp}
    if log is not None:
        top["reconcile_log"] = log
    return {"_top": top, "items": {}}


FULL = {"RT": {"missing": 0}, "AP": {"missing": 0}, "NS": {"missing": 0}}

# ── 三站齊全：不吵 ────────────────────────────────────────────────
out = cap(st("0806-1300", {"0806-1300": FULL}))
report("三站齊全 → 報 OK", "OK 清單對帳三站齊全" in out, out.strip()[:60])
report("三站齊全 → 不出現警告橫幅", "!!!!" not in out)

# ── 完全沒對帳：要吵，而且要吵得看得見 ──────────────────────────
out = cap(st("0806-1300"))
report("沒有 reconcile_log → 出現警告", "沒有做清單對帳" in out)
report("沒有 reconcile_log → 標明三站全缺", "（三站全缺）" in out, out.strip()[:80])
report("警告有醒目橫幅（收工時不會被淹沒）", out.count("!" * 60) == 2)
report("警告帶補做指令", "s2_audit.py" in out and "--rt-list" in out)
report("警告寫明做不了要留痕", "needs-review" in out)

# ── 只對了一部分：要指名缺哪站（0806 的實況）──────────────────
out = cap(st("0806-1300", {"0806-1300": {"NS": {"missing": 0}}}))
report("只對 NS → 仍然警告", "沒有做清單對帳" in out)
report("只對 NS → 指名 RT／AP 缺", "RT／AP 缺" in out, out.strip()[:80])
report("只對一部分 → 不說「三站全缺」", "（三站全缺）" not in out)

# ── 對帳記在別輪：不能拿上一輪的成績當這一輪的（最陰險的一種）──
out = cap(st("0806-1300", {"0806-1000": FULL}))
report("上一輪對過、這一輪沒對 → 照樣警告", "沒有做清單對帳" in out, out.strip()[:60])

# ── 只警告不擋：整條設計的紅線 ──────────────────────────────────
for label, s in (("三站全缺", st("0806-1300")),
                 ("缺一站", st("0806-1300", {"0806-1300": {"RT": {}}})),
                 ("checkpoint 空", st("")),
                 ("log 是 None", st("0806-1300", None))):
    report(f"不 sys.exit（{label}）——硬擋會讓無人值守輪次卡死",
           not str(cap(s)).startswith("__EXIT__"))

# ── 髒資料不炸（狀態檔什麼都可能長出來）────────────────────────
for label, s in (("_top 缺", {"items": {}}),
                 ("reconcile_log 是字串", st("0806-1300", "x")),
                 ("該輪的值是 None", st("0806-1300", {"0806-1300": None})),
                 ("完全空 dict", {})):
    try:
        cap(s)
        report(f"髒資料不炸（{label}）", True)
    except Exception as e:                        # noqa: BLE001
        report(f"髒資料不炸（{label}）", False, f"{type(e).__name__}: {e}")

# ── set-top 漏做：對帳查核會被上一輪的成績騙過去（2026-08-09 實錯）────
# 0809-0800 那輪收了 13 則、也做了三站對帳，但 agent 忘了 set-top，頂層停在
# 0809-0700。這道查核去查 0700、看到齊全就放行——**漏做 set-top 會順便讓
# 對帳查核失效**，兩個問題疊起來變成無聲通過。
def st_items(cp, log, seen):
    """seen＝狀態檔裡出現過的 first_seen_checkpoint（模擬素材已寫入）"""
    s = st(cp, log)
    s["items"] = [{"id": f"X{n}", "first_seen_checkpoint": c} for n, c in enumerate(seen)]
    return s


out = cap(st_items("0809-0700", {"0809-0700": FULL}, ["0809-0700", "0809-0800"]))
report("素材比頂層 checkpoint 新 → 抓出「忘了 set-top」",
       "忘了 set-top" in out, out.strip()[:60])
report("並且點名是哪一輪沒登記", "0809-0800" in out)
report("補救指令語法正確（set-top checkpoint X，不是 --checkpoint）",
       "set-top checkpoint 0809-0800" in out and "--checkpoint" not in out)

out = cap(st_items("0809-0800", {"0809-0800": FULL}, ["0809-0700", "0809-0800"]))
report("checkpoint 有推進時不要誤報", "忘了 set-top" not in out, out.strip()[:60])

out = cap(st_items("0809-0800", {"0809-0800": FULL}, ["0809-0800", None, None]))
report("first_seen_checkpoint 是 None 的舊資料不觸發誤報",
       "忘了 set-top" not in out, out.strip()[:60])

for label, s in (("items 是 dict（舊格式）", st("0809-0700", {"0809-0700": FULL})),
                 ("items 裡混入非 dict",
                  {"_top": {"checkpoint": "0809-0700"},
                   "items": ["壞掉的資料", {"first_seen_checkpoint": "0809-0800"}]})):
    try:
        cap(s)
        report(f"髒資料不炸（{label}）", True)
    except Exception as e:                        # noqa: BLE001
        report(f"髒資料不炸（{label}）", False, f"{type(e).__name__}: {e}")

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
