# -*- coding: utf-8 -*-
"""中主題登記簿（charter／aliases）迴歸（A10 P1a，2026-09-07）。

要解的是「同一條新聞不同輪各開中主題、跨天異名」：登記簿讓 agent 看得到
「這格收什麼」與別名；`set-category` 寫入前把 alias 改寫成 canonical，
並印改寫說明；`list-topics --compact` 每行帶 charter。

「只併不改名」鐵律：canonical 名寫下就不改；改名＝加 alias，見
common/plans/2026-09-07-全檢實作/13-A10P1-登記簿與find-similar與判例庫.md。

用法：python test_s2_topic_registry.py
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
    state_path = os.path.join(d, "s.json")
    registry_path = os.path.join(d, "registry.json")
    return state_path, registry_path


def run(state_path, registry_path, *args, items=None):
    """items：正式 schema 的清單（每筆帶 id），比照 test_s2_listtopics.py 的 run()。"""
    if items is not None:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({"date": "0907", "items": items}, f, ensure_ascii=False)
    r = subprocess.run(
        [sys.executable, SCRIPT, "--file", state_path, "--registry", registry_path, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def it(i, big=None, mid=None, sub=""):
    e = {"id": i, "source": "RT", "script_status": "has_script",
         "raw_entry": f"{i} (x) ▎a。▎畫面：b。▎無BITE。"}
    if big:
        c = {"大分類": big, "中主題": mid}
        if sub:
            c["小分題"] = sub
        e["category"] = c
    return e


# ── ① topic-register → registry.json 有一筆 ─────────────────────────────
state_path, registry_path = new_dirs()
out = run(state_path, registry_path,
          "topic-register", "--name", "美網", "--charter", "美國網球公開賽賽事與戰報",
          "--big", "體育", "--aliases", "美網戰報,美網賽事,網球")
def by_name(topics, name):
    return next((t for t in topics if t.get("name") == name), {})


with open(registry_path, encoding="utf-8") as f:
    reg = json.load(f)
topics = reg.get("topics") or []
# 登記簿是從常駐題（烏打俄／俄打烏）種子生成，所以「新增一筆」看的是
# 找不找得到「美網」這筆，不是 len(topics)==1（種子筆數不是這裡的測試對象）。
t0 = by_name(topics, "美網")
report("topic-register 寫入「美網」這一筆", bool(t0), f"得到 {topics}")
report("charter／big 正確",
       t0.get("charter") == "美國網球公開賽賽事與戰報" and t0.get("big") == "體育",
       f"得到 {t0}")
report("aliases 三個都在",
       set(t0.get("aliases") or []) == {"美網戰報", "美網賽事", "網球"},
       f"得到 {t0.get('aliases')}")
report("topic-register 有 OK 回報", "OK" in out, out.strip()[:60])

# ── ② set-category 命中 alias → canonical 改寫＋印說明 ──────────────────
out = run(state_path, registry_path, "set-category", "--pairs", "X=體育/美網戰報",
          items=[it("X")])
report("stdout 印改寫說明", "美網戰報→美網（alias）" in out, out.strip())
with open(state_path, encoding="utf-8") as f:
    saved = json.load(f)
x_item = next((it_ for it_ in (saved.get("items") or []) if it_.get("id") == "X"), {})
mid_saved = (x_item.get("category") or {}).get("中主題")
report("狀態檔存的是 canonical「美網」而不是別名", mid_saved == "美網", f"得到 {mid_saved}")

# ── ③ list-topics --compact 行尾有 charter ──────────────────────────────
out = run(state_path, registry_path, "list-topics", "--compact")
report("compact 輸出行尾帶 charter",
       "體育｜美網｜1｜美國網球公開賽賽事與戰報" in out, out.strip())

# ── ④ 同名再 register 只更新 charter，不重複 ────────────────────────────
out = run(state_path, registry_path,
          "topic-register", "--name", "美網", "--charter", "美國網球公開賽：戰況、名次、賽程")
with open(registry_path, encoding="utf-8") as f:
    reg2 = json.load(f)
topics2 = reg2.get("topics") or []
t2 = by_name(topics2, "美網")
report("同名 register 不新增第二筆",
       sum(1 for t in topics2 if t.get("name") == "美網") == 1, f"得到 {topics2}")
report("charter 已更新成新值",
       t2.get("charter") == "美國網球公開賽：戰況、名次、賽程",
       f"得到 {t2.get('charter')}")
report("aliases 沒被清掉（只更新 charter）",
       set(t2.get("aliases") or []) == {"美網戰報", "美網賽事", "網球"},
       f"得到 {t2.get('aliases')}")

# ── ⑤ topic-alias 追加別名 ───────────────────────────────────────────────
out = run(state_path, registry_path, "topic-alias", "--name", "美網", "--alias", "網球公開賽")
with open(registry_path, encoding="utf-8") as f:
    reg3 = json.load(f)
aliases3 = by_name(reg3.get("topics") or [], "美網").get("aliases") or []
report("topic-alias 追加成功", "網球公開賽" in aliases3, f"得到 {aliases3}")
report("topic-alias 舊別名還在（追加不是取代）",
       {"美網戰報", "美網賽事", "網球"} <= set(aliases3), f"得到 {aliases3}")
report("topic-alias 對不存在的中主題明確失敗（不靜默造格）",
       "ERROR" in run(state_path, registry_path,
                      "topic-alias", "--name", "不存在的主題", "--alias", "隨便"))

# ── 不影響既有 list-topics（無 charter 的中主題照舊，不多印一段空的）──────
out = run(state_path, registry_path, "list-topics", "--compact",
          items=[it("Y", "社會", "沒登記的主題")])
report("沒登記過的中主題不硬印 charter 欄",
       "社會｜沒登記的主題｜1" in out and "社會｜沒登記的主題｜1｜" not in out,
       out.strip())

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
