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


def write_batch(d, name, obj, wrap=True):
    # P1b-2（2026-09-08 硬上線）：三站的 batch 純陣列會被退回，測試預設包殼；
    # `wrap=False` 留給專門驗退回行為的那幾案。
    if wrap and isinstance(obj, list):
        obj = {"entries": obj, "new_topics": {}}
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


# ① 物件形 category／tc → 照寫，行為等同字串（P1b-2 後外殼由 write_batch 補）
sp, rp, d = new_dirs()
new_state(sp)
new_registry(rp, ("尼泊爾洪災",))   # 過閘用：這一案驗的是形狀，不是閘門
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

# ④ P1b-2 硬上線（2026-09-08 使用者裁決）：三站的純陣列一律退回
# 0908-0100 實測：agent 三站全部用 Write 手寫純陣列、`build --skeleton` 一次都沒
# 被呼叫，軟上線的閘門（要有 `_new_topics` 鍵才過閘）等於從來沒啟動過，48 個中
# 主題 43 個未登記。所以改成在入口擋，並且錯誤訊息要能直接照抄修好。
sp, rp, d = new_dirs()
new_state(sp)
new_registry(rp, ("尼泊爾洪災",))
b = write_batch(d, "b_bare.json", [entry("RT0021", "社會/尼泊爾洪災/搜救")], wrap=False)
code, out = run(sp, rp, "add-batch", "--entries", b)
report("④ RT 純陣列 → 退回（exit 2）", code == 2, f"實得 {code}；{out.strip()[:120]}")
report("④ 退回訊息含可直接照抄的外殼寫法",
       '{"entries": [ …原本的陣列… ], "new_topics": {}}' in out, out.strip()[:200])
report("④ 退回訊息說明救援路徑（補 charter 重送、只補分類）",
       "charter" in out and "只補分類" in out, out.strip()[:200])
report("④ 退回時一則都沒進庫", not (load(sp).get("items") or {}))

for _src in ("NS", "AP"):
    sp2, rp2, d2 = new_dirs()
    new_state(sp2)
    new_registry(rp2, ("尼泊爾洪災",))
    _e = entry(f"{_src}0001", "社會/尼泊爾洪災/搜救")
    _e["source"] = _src
    b2 = write_batch(d2, "b.json", [_e], wrap=False)
    code2, _o = run(sp2, rp2, "add-batch", "--entries", b2)
    report(f"④ {_src} 純陣列同樣退回", code2 == 2, f"實得 {code2}")

# 平台線（ENEX／ABC）與側錄線的純陣列**仍然合法**，不可誤傷
sp3, rp3, d3 = new_dirs()
new_state(sp3)
new_registry(rp3, ("尼泊爾洪災",))
e3 = entry("ENEX0001", "社會/尼泊爾洪災/搜救")
e3["source"] = "ENEX"
b3 = write_batch(d3, "b.json", [e3], wrap=False)
code3, out3 = run(sp3, rp3, "add-batch", "--entries", b3)
report("④ ENEX 純陣列照收（平台線不受影響）", code3 == 0 and "OK 新增 1 則" in out3,
       f"實得 {code3}；{out3.strip()[:120]}")

# `--auto-register` 是平台線自己的旗標：帶了就照收，不是三站的逃生門
sp4, rp4, d4 = new_dirs()
new_state(sp4)
new_registry(rp4)
b4 = write_batch(d4, "b.json", [entry("RT0031", "社會/自動登記格/子題")], wrap=False)
code4, out4 = run(sp4, rp4, "add-batch", "--entries", b4, "--auto-register")
report("④ --auto-register 的純陣列不被退回", code4 == 0 and "OK 新增 1 則" in out4,
       f"實得 {code4}；{out4.strip()[:120]}")

# 混批：只要有一則是三站就退回（不可以放行整批）
sp5, rp5, d5 = new_dirs()
new_state(sp5)
new_registry(rp5, ("尼泊爾洪災",))
b5 = write_batch(d5, "b.json", [e3, entry("RT0041", "社會/尼泊爾洪災/搜救")], wrap=False)
code5, out5 = run(sp5, rp5, "add-batch", "--entries", b5)
report("④ 混批含三站 → 整批退回", code5 == 2 and "RT" in out5, f"實得 {code5}")

print("\nALL PASS" if ok else "\nSOME FAILED")
sys.exit(0 if ok else 1)
