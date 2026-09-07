# -*- coding: utf-8 -*-
"""R25（2026-09-07）：`add-batch` 收物件形 `category`／`tc`＋桶鍵改本輪＋P1b-2 救援路徑。

要解的問題：
  ① 13c2 §2 教 agent 狀態檔 `category` 是 `{"大分類","中主題","小分題"}` 物件，
     agent 照抄進 batch，`add-batch` 卻只吃字串「大/中/小」→ `str(dict)` 沒有 `/`，
     0907-1700 五站 141 則、0907-2200 三站 78 則全部「退回」，T12 一次入庫失效、
     P1b 閘門被 set-category（topic_mode off）繞過。
  ② `tc_rejected`／`tc_calls` 桶鍵只讀頂層 checkpoint，而 set-top 收工才下 →
     整輪退回與 set-tc 次數記到上一輪桶。改：`S2_CHECKPOINT` 環境變數 →
     batch 自帶 checkpoint → 頂層 checkpoint。
  ③ 閘門擋下（category 留空）那批，agent 補 new_topics 重送時素材已在庫，
     原本一律「已存在」跳過 → 🆕 訊息教的做法永遠做不到。改：已在庫且沒分類、
     這筆帶了分類 → 只補分類（仍過閘門）。

用法：python -X utf8 scripts/test_s2_add_batch_shapes.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "s2_state.py")

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


def new_dirs():
    d = tempfile.mkdtemp()
    return os.path.join(d, "s.json"), os.path.join(d, "registry.json"), d


def new_state(path, checkpoint="0999-1700"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": "0999", "checkpoint": checkpoint, "items": []}, f, ensure_ascii=False)


def new_registry(path, names=()):
    topics = [{"name": n, "charter": f"{n} charter", "aliases": [], "big": "社會",
               "tc": {"T": [], "C": []}, "first_seen": "2026-09-01", "last_seen": "2026-09-01",
               "resident": False} for n in names]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "topics": topics}, f, ensure_ascii=False)


def run(state_path, registry_path, *args, env_extra=None):
    env = dict(os.environ)
    env.pop("S2_CHECKPOINT", None)
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    r = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, "--file", state_path,
                        "--registry", registry_path, *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def load(path):
    """落檔的 items 是陣列；轉成 {id: item} 方便斷言。"""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    items = d.get("items") or []
    if isinstance(items, list):
        d["items"] = {x.get("id"): x for x in items if isinstance(x, dict)}
    return d


def entry(i, cat, tc=None, cp="0999-2000"):
    e = {"id": i, "source": "RT", "checkpoint": cp, "status": "has_script",
         "entry": f"{i} (測試 標題) (BITE) ▎測試摘要。", "sb_count": 1, "src_text": "STORY: test"}
    if cat is not None:
        e["category"] = cat
    if tc is not None:
        e["tc"] = tc
    return e


def write_batch(d, name, obj):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


# ① 舊格式（純陣列）＋物件形 category／tc → 照寫，行為等同字串
sp, rp, d = new_dirs()
new_state(sp)
new_registry(rp)
b = write_batch(d, "b1.json", [
    entry("RT0001", {"大分類": "社會", "中主題": "尼泊爾洪災", "小分題": "搜救進度"},
          {"T": ["天災天氣"], "C": ["南亞"]}),
    entry("RT0002", "社會/尼泊爾洪災/家屬抗議", "天災天氣/南亞"),
    entry("RT0003", {"大分類": "社會"}),   # 缺中主題 → 退回，不能 crash
])
code, out = run(sp, rp, "add-batch", "--entries", b)
st = load(sp)
it1 = st["items"].get("RT0001") or {}
it2 = st["items"].get("RT0002") or {}
report("① 物件 category 寫成三層", it1.get("category") == {"大分類": "社會", "中主題": "尼泊爾洪災", "小分題": "搜救進度"},
       str(it1.get("category")))
report("① 物件 tc 寫成 T/C", (it1.get("tc") or {}).get("T") == ["天災天氣"] and (it1.get("tc") or {}).get("C") == ["南亞"],
       str(it1.get("tc")))
report("① 字串形不受影響", it2.get("category", {}).get("中主題") == "尼泊爾洪災" and (it2.get("tc") or {}).get("C") == ["南亞"])
report("① 物件缺中主題 → 退回不 crash", code == 0 and "RT0003" in str(st.get("tc_rejected")) and "分類 2" in out,
       out[-300:])
# ② 桶鍵：沒有環境變數時取 batch 自帶的 checkpoint（0999-2000），不是頂層的 0999-1700
report("② 退回記在 batch 自帶的輪次桶", "0999-2000" in (st.get("tc_rejected") or {}) and "0999-1700" not in (st.get("tc_rejected") or {}),
       str(list((st.get("tc_rejected") or {}).keys())))

# ② set-tc：環境變數 S2_CHECKPOINT 優先於頂層 checkpoint
code, out = run(sp, rp, "set-tc", "--pairs", "RT0002=社會/南亞", env_extra={"S2_CHECKPOINT": "0999-2000"})
st = load(sp)
report("② set-tc 次數記在 S2_CHECKPOINT 桶", (st.get("tc_calls") or {}).get("0999-2000") == 1 and "0999-2000" in out,
       str(st.get("tc_calls")))
code, out = run(sp, rp, "set-tc", "--pairs", "RT0002=社會/南亞")
st = load(sp)
report("② 沒環境變數時 set-tc 仍走頂層 checkpoint", (st.get("tc_calls") or {}).get("0999-1700") == 1, str(st.get("tc_calls")))

# ③ 新格式閘門＋救援路徑
sp, rp, d = new_dirs()
new_state(sp)
new_registry(rp, names=["尼泊爾洪災"])
b = write_batch(d, "b2.json", {"entries": [
    entry("RT0011", {"大分類": "社會", "中主題": "尼泊爾洪災", "小分題": "搜救進度"}),
    entry("RT0012", {"大分類": "體育", "中主題": "全新主題", "小分題": "x"}, "體育/歐洲"),
]})
code, out = run(sp, rp, "add-batch", "--entries", b)
st = load(sp)
report("③ 新格式：已登記名照寫", (st["items"].get("RT0011") or {}).get("category", {}).get("中主題") == "尼泊爾洪災")
report("③ 新格式：未登記名擋下、素材已入庫、印 🆕", "RT0012" in st["items"] and not st["items"]["RT0012"].get("category")
       and "未登記中主題：全新主題" in out, out[-400:])
# 重送同一批但**沒帶** new_topics → 仍被擋：不准報「只補分類」、category 仍空、🆕 照印
code, out = run(sp, rp, "add-batch", "--entries", b)
st = load(sp)
report("③ 重送沒帶 new_topics → 不報補分類、仍 🆕", "只補分類" not in out and "未登記中主題：全新主題" in out
       and not (st["items"].get("RT0012") or {}).get("category"), out[-400:])
# 重送同一批＋new_topics → 只補分類，不再「已存在」跳過
b = write_batch(d, "b3.json", {"entries": [
    entry("RT0011", {"大分類": "社會", "中主題": "尼泊爾洪災", "小分題": "搜救進度"}),
    entry("RT0012", {"大分類": "體育", "中主題": "全新主題", "小分題": "x"}, "體育/歐洲"),
], "new_topics": {"全新主題": {"charter": "測試用新題", "big": "體育"}}})
code, out = run(sp, rp, "add-batch", "--entries", b)
st = load(sp)
it = st["items"].get("RT0012") or {}
report("③ 重送帶 new_topics → 已在庫只補分類", it.get("category", {}).get("中主題") == "全新主題"
       and (it.get("tc") or {}).get("T") == ["體育"] and "只補分類 1 則" in out, out[-400:])
report("③ 已有分類的已在庫不動、仍報已存在", "RT0011: 已存在" in out, out[-400:])
reg = load(rp)
report("③ new_topics 已登記", any(t.get("name") == "全新主題" for t in reg.get("topics", [])))
report("③ raw_entry 未被重送覆寫", it.get("raw_entry", "").startswith("RT0012"))

print("\nALL PASS" if ok else "\nSOME FAILED")
sys.exit(0 if ok else 1)
