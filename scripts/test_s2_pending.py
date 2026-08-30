# -*- coding: utf-8 -*-
"""`_待整併/` 偵測的迴歸（`s2_pending.py`，2026-08-26 上線；本測試 2026-08-30 補）。

這支守的是一件事：**「有東西沒整併」這個提醒不可以無聲消失**。
0825-2200 那輪 4 份交件檔一份都沒整併，就是因為程式端零偵測；補上偵測之後，
真正的風險換成「偵測還在、但條件寫歪了所以永遠印不出來」——那比沒有偵測更糟，
因為看起來有一道閘門。以下每一條都對應一個會讓它靜靜失效的地方：

  ① **`已入庫_` 前綴＝已完成**。前綴比對寫反或用 `in` 而不是 `startswith`，
     整個資料夾會永遠是「零筆待整併」（那夾子裡絕大多數檔都有這個前綴）。
  ② **時間窗口**。`hours` 邊界搞錯方向，舊檔會天天重報到沒人再看它。
  ③ **目錄不存在要回 `[]` 不可以炸**。雲端硬碟沒掛載是常態，
     ⛔ 這道提醒**不准擋住整輪**——漏整併是少收素材，整輪掛掉是整晚白做。
  ④ **子目錄不是交件檔**。`os.listdir` 不分檔案與資料夾。
  ⑤ **`where="render"` 要多印「補完要重跑 render」**。收工才看到的話，
     那份 txt 已經少了這批；少了這句，agent 補完整併就收工了。
  ⑥ **零筆時完全安靜**。每輪都印一行「目前 0 筆」會讓真的有筆數時被當雜訊略過。

⛔ 全程用 tmp dir 注入 `pend_dir`，一個字都不碰生產的
`G:\我的雲端硬碟\Claude共用\自動掃帶系統\_待整併`。

用法：python test_s2_pending.py
"""
import io
import os
import sys
import tempfile
import time
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_pending as P       # noqa: E402

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


NOW = time.time()
D = tempfile.mkdtemp(prefix="s2pend_")


def mk(name, age_h=1.0, body="x"):
    """建一份假交件檔，mtime 往回推 `age_h` 小時。"""
    p = os.path.join(D, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    t = NOW - age_h * 3600
    os.utime(p, (t, t))
    return p


def cap(**kw):
    """跑 warn()，回傳 (筆數, stdout 全文)。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        n = P.warn(**kw)
    return n, buf.getvalue()


# ── 佈景 ─────────────────────────────────────────────────────────────
mk("0830-ENEX.txt", age_h=2, body="ENEX" * 10)          # 該報
mk("0830-側錄候選_2237.txt", age_h=0.5)                  # 該報（較新，排序在後）
mk("0830-ABC-pairs.txt", age_h=1)                        # 該報（中間產物也算）
mk("已入庫_0830-韓聯社.txt", age_h=0.5)                  # ① 已完成
mk("~$0830-暫存.txt", age_h=0.5)                         # Office 鎖檔
mk(".DS_Store", age_h=0.5)                               # 隱藏檔
mk("0829-ENEX.txt", age_h=30)                            # ② 超出 24h
os.makedirs(os.path.join(D, "0830-子資料夾"), exist_ok=True)   # ④

names = [r[0] for r in P.pending_files(pend_dir=D)]

report("① `已入庫_` 前綴不列入", "已入庫_0830-韓聯社.txt" not in names)
report("Office 鎖檔／隱藏檔不列入",
       not any(n.startswith(("~$", ".")) for n in names), f"得到 {names}")
report("② 超出 24h 的不列入", "0829-ENEX.txt" not in names)
report("② 放寬到 48h 就抓得到", "0829-ENEX.txt" in [r[0] for r in P.pending_files(hours=48, pend_dir=D)])
report("④ 子資料夾不列入", "0830-子資料夾" not in names)
report("該報的三份都在", set(names) == {"0830-ENEX.txt", "0830-側錄候選_2237.txt", "0830-ABC-pairs.txt"},
       f"得到 {sorted(names)}")
report("依 mtime 由舊到新排序", names == ["0830-ENEX.txt", "0830-ABC-pairs.txt", "0830-側錄候選_2237.txt"],
       f"得到 {names}")

_sizes = {n: sz for n, _, sz in P.pending_files(pend_dir=D)}
report("回傳位元組數（agent 判空檔用）", _sizes["0830-ENEX.txt"] == 40, f"得到 {_sizes['0830-ENEX.txt']}")

# ③ 目錄不存在
report("③ 目錄不存在回 [] 不拋例外", P.pending_files(pend_dir=os.path.join(D, "不存在")) == [])
_n_missing, _out_missing = cap(where="resume", pend_dir=os.path.join(D, "不存在"))
report("③ 目錄不存在時 warn 回 0 且不印字", _n_missing == 0 and _out_missing == "",
       repr(_out_missing[:60]))

# warn() 內容
n_resume, out_resume = cap(where="resume", pend_dir=D)
report("warn 回傳筆數", n_resume == 3, f"得到 {n_resume}")
report("warn 逐檔列名", all(x in out_resume for x in
                            ("0830-ENEX.txt", "0830-ABC-pairs.txt", "0830-側錄候選_2237.txt")))
report("warn 指出整併方式（三條產線）",
       all(x in out_resume for x in ("s2_platform_merge.py", "add-side", "common/17")))
report("warn 提醒 mark_ingested 是整併「之後」才跑", "s2_mark_ingested.py --apply" in out_resume)

n_render, out_render = cap(where="render", pend_dir=D)
report("⑤ render 分支多印「重跑 render」", "重跑 render" in out_render)
report("⑤ resume 分支不印那句", "重跑 render" not in out_resume)
report("render 與 resume 筆數一致", n_render == n_resume == 3)

# ⑥ 零筆＝完全安靜
_empty = os.path.join(D, "0830-子資料夾")
n_zero, out_zero = cap(where="render", pend_dir=_empty)
report("⑥ 零筆時回 0 且一個字都不印", n_zero == 0 and out_zero == "", repr(out_zero[:60]))

# 兩個呼叫點確實掛著（規則字數 0 的那個承諾，靠這兩行守住）
_src_state = open(os.path.join(HERE, "s2_state.py"), encoding="utf-8").read()
_src_render = open(os.path.join(HERE, "s2_render.py"), encoding="utf-8").read()
report("呼叫點：cmd_resume 有喊 warn", 's2_pending.warn(where="resume")' in _src_state)
report("呼叫點：s2_render 收工有喊 warn", 's2_pending.warn(where="render")' in _src_render)
# ⛔ render 那道只警告不擋：不可以出現 sys.exit／raise 綁在它後面同一區塊。
_after = _src_render.split('s2_pending.warn(where="render")', 1)[1].splitlines()[1:3]
report("⛔ render 的 warn 後面沒有立刻 exit（只警告不擋）",
       not any("sys.exit" in ln for ln in _after), f"後兩行 {_after}")

print("\n全部通過" if ok else "\n有失敗項")
sys.exit(0 if ok else 1)
