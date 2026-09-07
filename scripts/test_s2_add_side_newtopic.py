# -*- coding: utf-8 -*-
"""A10 P1b：`add-side` 新題閘門（自動 register，⛔ 不是擋）迴歸。

側錄（歐印萬）與「17-網址素材整併」的韓聯社／CNA／OTH 交件檔最終都是走
`add-side` 這支吃三層排版 TXT，兩者都**沒有** `new_topics` 這種結構化欄位
可以附 charter，而 13c2／13f 規則檔這一輪凍結不改——沒有任何產線 agent
會記得帶旗標。所以這裡跟 `add-batch` 的新格式閘門刻意不同調：

  - **預設 `auto_register=True`**：遇到登記簿沒有的中主題 → 自動
    `_register_topic(auto=True)`（charter 取該段摘要前 40 字或內容首句）
    再照寫 category，**不擋、不留空**。
  - `--no-auto-register`：退回「不查登記簿、照寫」的舊行為（P1a 之前）——
    ⛔ 不是 gate，那樣還是會弄丟分類，跟這條交件端的處境矛盾。

用法：python test_s2_add_side_newtopic.py
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
    return os.path.join(d, "s.json"), os.path.join(d, "registry.json")


def new_state(state_path, checkpoint="0907-1700"):
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"date": "0907", "checkpoint": checkpoint, "items": []}, f,
                  ensure_ascii=False)


def run(state_path, registry_path, *args):
    r = subprocess.run(
        [sys.executable, SCRIPT, "--file", state_path, "--registry", registry_path, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def get(state_path, registry_path, id_):
    return json.loads(run(state_path, registry_path, "get", "--id", id_))


def registry_topics(registry_path):
    if not os.path.exists(registry_path):
        return []
    with open(registry_path, encoding="utf-8") as f:
        return (json.load(f) or {}).get("topics") or []


def by_name(topics, name):
    return next((t for t in topics if t.get("name") == name), None)


def write_txt(d, name, text):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


TXT_TEMPLATE = """擬歸位：======社會====== → 【{mid}】
CNN 09-07 160106 （主播）
內容一。
"""
SIDE_ID = "CNN 09-07 160106"


# ── ① 預設（不帶旗標）：未登記中主題 → 自動登記＋照寫 category ──────────
sp1, rp1 = new_dirs()
new_state(sp1)
d1 = os.path.dirname(sp1)
txt1 = write_txt(d1, "side1.txt", TXT_TEMPLATE.format(mid="全新側錄主題"))
out1 = run(sp1, rp1, "add-side", "--txt", txt1, "--checkpoint", "0907-1700")
report("① add-side 成功收錄", "OK 收錄側錄" in out1, out1.strip()[:200])
v1 = get(sp1, rp1, SIDE_ID)
report("① category 有寫（中主題＝全新側錄主題）",
       (v1.get("category") or {}).get("中主題") == "全新側錄主題", f"實得 {v1.get('category')!r}")
t1 = by_name(registry_topics(rp1), "全新側錄主題")
report("① 登記簿自動新增這一筆並標 auto:true", bool(t1) and t1.get("auto") is True,
       f"實得 {t1!r}")
report("① stdout 提到「待補 charter」", "待補 charter" in out1, out1.strip()[:300])

# ── ② --no-auto-register：未登記中主題**仍然照寫**，但不動登記簿 ────────
sp2, rp2 = new_dirs()
new_state(sp2)
d2 = os.path.dirname(sp2)
txt2 = write_txt(d2, "side2.txt", TXT_TEMPLATE.format(mid="不登記的側錄主題"))
out2 = run(sp2, rp2, "add-side", "--txt", txt2, "--checkpoint", "0907-1700",
          "--no-auto-register")
v2 = get(sp2, rp2, SIDE_ID)
report("② --no-auto-register：category 仍照寫（不是擋）",
       (v2.get("category") or {}).get("中主題") == "不登記的側錄主題",
       f"實得 {v2.get('category')!r}")
report("② --no-auto-register：登記簿沒有多出這一筆",
       by_name(registry_topics(rp2), "不登記的側錄主題") is None)
report("② stdout 不提「待補 charter」", "待補 charter" not in out2, out2.strip()[:200])

# ── ③ 已登記過的中主題（走 alias）：改寫成 canonical，不觸發自動登記 ─────
sp3, rp3 = new_dirs()
new_state(sp3)
run(sp3, rp3, "topic-register", "--name", "側錄常駐格", "--charter", "已登記",
   "--big", "社會", "--aliases", "側錄舊名")
d3 = os.path.dirname(sp3)
txt3 = write_txt(d3, "side3.txt", TXT_TEMPLATE.format(mid="側錄舊名"))
out3 = run(sp3, rp3, "add-side", "--txt", txt3, "--checkpoint", "0907-1700")
v3 = get(sp3, rp3, SIDE_ID)
report("③ alias 命中：狀態檔存的是 canonical「側錄常駐格」",
       (v3.get("category") or {}).get("中主題") == "側錄常駐格", f"實得 {v3.get('category')!r}")
report("③ stdout 印改寫說明", "側錄舊名→側錄常駐格（alias）" in out3, out3.strip()[:200])
report("③ 沒有多登記一筆（本來就有）",
       sum(1 for t in registry_topics(rp3) if t.get("name") == "側錄常駐格") == 1)

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
