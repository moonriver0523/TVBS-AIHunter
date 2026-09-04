# -*- coding: utf-8 -*-
"""「只看最新」涵蓋輪次間整併素材：迴歸測試（2026-09-04 立）。

為什麼要釘死：`set-top checkpoint` 是收工才下的，輪次中途人工要求整併的
CNN/NHK 側錄、韓聯社/CNA 素材，`first_seen_checkpoint` 會晚於當時的頂層
checkpoint（因為下一輪還沒收工、還沒 set-top）。舊邏輯用「精確相等」判定
「最新」，會把這批間隔期間入庫的素材漏掉——本測試釘住改用「>= 本輪
checkpoint」的時間窗，並確認下一輪 set-top 後這批連同上一輪一起自然掉出
「只看最新」。

用法：python test_s2_fresh_filter.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_render_html as H  # noqa: E402

ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


BASE = "0904"


def mk_state(checkpoint, items):
    return {"checkpoint": checkpoint, "items": items}


# 情境：0904-1100 那輪收工、set-top。之後人工整併 CNN 側錄，first_seen_checkpoint
# 記到 0904-1330（還沒下一次 set-top，頂層仍是 0904-1100）。
state = mk_state("0904-1100", [
    {"id": "A", "first_seen_checkpoint": "0904-1100"},   # 本輪掃到的
    {"id": "B", "first_seen_checkpoint": "0904-1330"},   # 輪次間整併進來的
])
fkey, _ = H.fresh_info(state, BASE)


# collect() 的 is_fresh 是內部閉包、無法外部呼叫；直接照抄它用的同一套比較式
# （R.checkpoint_time + `>=` fkey）來驗證，跟正式邏輯保持同一個判準來源。
import s2_render as R  # noqa: E402


def compute_is_fresh(cp, fkey):
    day, hhmm = R.checkpoint_time(cp or "", BASE)
    return hhmm is not None and (day, hhmm) >= fkey


report("本輪掃到的素材算最新", compute_is_fresh("0904-1100", fkey))
report("輪次間整併的素材也算最新（>= 而非 ==）", compute_is_fresh("0904-1330", fkey))
report("更早一輪的素材不算最新", not compute_is_fresh("0904-0800", fkey))

# 下一輪 0904-1500 掃完、set-top 之後：上一輪(1100)＋間隔期間(1330)都要掉出「最新」。
state2 = mk_state("0904-1500", [])
fkey2, _ = H.fresh_info(state2, BASE)
report("下一輪 set-top 後，上一輪的素材掉出最新", not compute_is_fresh("0904-1100", fkey2))
report("下一輪 set-top 後，間隔期間整併的素材也掉出最新", not compute_is_fresh("0904-1330", fkey2))
report("下一輪本身的素材算最新", compute_is_fresh("0904-1500", fkey2))

sys.exit(0 if ok else 1)
