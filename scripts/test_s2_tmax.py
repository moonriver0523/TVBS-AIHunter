# -*- coding: utf-8 -*-
"""T 數量上限（T_MAX=3）的迴歸（2026-08-25 使用者定：上限 3、預設 1）。

守三件事，每一件都對應一個推理上會走偏的地方：

  ① **超過上限要退該則、不可截斷取前 N**。哪幾個是主軸是判斷題；機器替 agent
     挑等於把判斷藏進 stdout，而 stdout agent 未必讀。退件走既有 skipped 路徑，
     會落進 `tc_rejected`，audit 免費。

  ② **機動 T 不佔這 3 格**。否則已掛 3 個固定 T 的素材被 `_special_t_sweep`
     點名「加掛颱風、原本的 T 要留著」時就會變成 4 個——自己的機制逼自己違規。

  ③ **先正規化再數**。`科技` 與 `醫藥健康` 併成同一個 `科技醫藥`，合併後是 1 個
     不是 2 個；先數再併會把合法的組合誤退。

用法：python test_s2_tmax.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_state as st       # noqa: E402

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


OK_T, OK_C = st._load_tc_dict()
# ⚠️ 機動 T 名單**寫死在測試裡**、不讀 s2_special_t.json：那份檔案會隨事件開關，
#    讓測試跟著它漂，等於哪天颱風退場這支就無聲失效。
SPECIAL = {"颱風"}
OK_T_ALL = list(OK_T) + list(SPECIAL)


def try_set(spec, special=SPECIAL):
    state = {"items": {"X1": {}}}
    err = st._set_one_tc(state, "X1", spec, OK_T_ALL, OK_C, None, special)
    return err, (state["items"]["X1"].get("tc") or {})


report("T_MAX 是 3", st.T_MAX == 3, f"得到 {st.T_MAX}")

err, tc = try_set("政治,財經,社會/美國")
report("3 個固定 T：放行", err is None and len(tc.get("T") or []) == 3, f"err={err}")

err, tc = try_set("政治,財經,社會,體育/美國")
report("① 4 個固定 T：退該則", err is not None and "上限 3" in (err or ""), f"err={err}")
report("① 退件時什麼都不寫進狀態檔", not tc, f"得到 {tc}")

err, tc = try_set("政治,財經,社會,颱風/美國")
report("② 3 固定＋1 機動：放行", err is None, f"err={err}")
report("② 機動 T 有寫進去（加掛不是取代）",
       (tc.get("T") or [])[-1] == "颱風" and len(tc["T"]) == 4, f"得到 {tc.get('T')}")

err, tc = try_set("颱風,天災天氣/中國大陸")
report("② 颱風＋天災天氣（實際在跑的組合）：放行", err is None, f"err={err}")

# ③ 科技／醫藥健康都會被 normalize_t 併成「科技醫藥」，合併後只算 1 個。
err, tc = try_set("科技,醫藥健康,政治,社會/臺灣")
report("③ 正規化後降到 3 個：放行", err is None, f"err={err}")
report("③ 正規化確實去重", (tc.get("T") or []) == ["科技醫藥", "政治", "社會"],
       f"得到 {tc.get('T')}")

# 兜底分類器：heur 不能湊出 4 個 T（顯示端跟規則對得起來）
sys.path.insert(0, os.path.join(HERE, "prototype"))
import build_tc_matrix_0821 as M       # noqa: E402

report("兜底：T_PRIORITY 涵蓋字典全部 11 類",
       set(M.T_PRIORITY) == {n for n, _ in M.T_FIXED},
       f"差異 {set(M.T_PRIORITY) ^ {n for n, _ in M.T_FIXED}}")

_hit = 0
for _big, _txt in (("大陸", "北京機器人大會 外交 記者會 暴雨 貿易 足球"),
                   ("美國", "命案 起訴 貿易 野火 外交 電競 好萊塢")):
    _T, _C, _ = M.tag_tc({"big": _big, "mid": "", "sub": "", "text": _txt, "q": _txt})
    _hit += 1
    report(f"兜底：{_big} 這種塞滿關鍵詞的列也不超過 3 個 T",
           len(_T) <= 3, f"得到 {_T}")
report("兜底測資有跑到", _hit == 2)

print("\n全部通過" if ok else "\n有失敗項")
sys.exit(0 if ok else 1)
