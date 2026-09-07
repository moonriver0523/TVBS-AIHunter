# -*- coding: utf-8 -*-
"""A10 P1b：`add-batch` 新題閘門＋`set-category --auto-register` 迴歸。

要解的問題：登記簿（P1a）只是視野，`add-batch`／`set-category` 誰都能拿
陌生中主題名直接寫進 category，登記簿很快就跟實際分類脫鉤。這裡驗證：

  ① **新格式** `{"entries":[…], "new_topics":{…}}` 才會走新題閘門——
     命中不到登記簿的中主題就**不寫 category**（不擋入庫），除非 batch
     頂層 `new_topics` 附了 charter，或那個名字已經在登記簿裡。
  ② **舊格式**（純陣列；P1b-2 硬上線後只剩平台線 ENEX／ABC 合法
     用的就是這個形狀）行為**完全不變**——照寫，不查登記簿。這條分界線
     是刻意的：主力三站（AP/RT/CNN）走 `s2_batch_prep.py` 出的就是純陣列，
     沒有 new_topics 這回事，改成一律 gate 會擋掉現行production 產線。
  ③ `--auto-register`（給 ENEX/ABC 整併端這種沒有 new_topics 可用的呼叫端）：
     不擋、自動登記（charter 取該則摘要前 40 字，標 auto:true）。
  ④ `set-category` 預設**不查登記簿**（跟 P1a 之前行為一致，⛔ 不能改成
     預設 gate——它天天被人工／既有呼叫端拿陌生名字呼叫）；帶
     `--auto-register` 才會在遇到未登記名時順手登記，同時把 category
     寫進去。

用法：python test_s2_add_batch_newtopic.py
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


def new_state(state_path, checkpoint="0999-1700"):
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"date": "0999", "checkpoint": checkpoint, "items": []}, f,
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


def item(id_, extra=None, source="RT"):
    e = {"id": id_, "source": source, "checkpoint": "0999-1700",
         "status": "has_script", "entry": f"{id_} (測試) ▎摘要。▎畫面：測試。▎無BITE。"}
    if extra:
        e.update(extra)
    return e


def add_batch(state_path, registry_path, payload, extra_args=()):
    d = os.path.dirname(state_path)
    bp = os.path.join(d, f"b_{os.urandom(4).hex()}.json")
    with open(bp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return run(state_path, registry_path, "add-batch", "--entries", bp, *extra_args)


# ── ① 舊格式（純陣列）：未登記中主題照寫，行為完全不變（同 T12 迴歸）─────
# ⚠️ P1b-2 硬上線（2026-09-08）後，純陣列只剩**平台線**（ENEX／ABC）合法，
# 三站（RT／NS／AP）送純陣列會被 `_reject_bare_array` 當場退回（見案 ⑧）。
# 這一案改用 ENEX，驗的還是同一件事：off 模式不查登記簿、照寫。
sp1, rp1 = new_dirs()
new_state(sp1)
out1 = add_batch(sp1, rp1, [item("OLD1", {"category": "體育/舊格式沒登記過"},
                                 source="ENEX")])
v1 = get(sp1, rp1, "OLD1")
report("① 舊格式（平台線純陣列）：未登記中主題照樣寫入 category",
       v1.get("category") == {"大分類": "體育", "中主題": "舊格式沒登記過"},
       f"實得 {v1.get('category')!r}")
report("① 舊格式：不印新題閘門訊息（走 off，不查登記簿）",
       "未登記中主題" not in out1, out1.strip()[:200])

# ── ② 新格式、無 new_topics、未登記中主題 → 素材入庫、category 不寫 ──────
sp2, rp2 = new_dirs()
new_state(sp2)
out2 = add_batch(sp2, rp2, {"entries": [item("NEW1", {"category": "體育/全新主題"})]})
v2 = get(sp2, rp2, "NEW1")
report("② 新格式：素材照樣入庫", v2.get("script_status") == "has_script")
report("② 新格式：category 不寫（未登記、沒有 new_topics）",
       not v2.get("category"), f"實得 {v2.get('category')!r}")
report("② stdout 印新題閘門訊息",
       "🆕 未登記中主題：全新主題" in out2 and "new_topics" in out2, out2.strip()[:300])

# ── ③ 新格式 + batch 頂層 new_topics 附 charter → 自動 register＋寫 category ──
sp3, rp3 = new_dirs()
new_state(sp3)
out3 = add_batch(sp3, rp3, {
    "entries": [item("NEW2", {"category": "體育/全新主題二"})],
    "new_topics": {"全新主題二": {"charter": "測試用 charter 二", "big": "體育"}},
})
v3 = get(sp3, rp3, "NEW2")
report("③ new_topics 覆蓋：category 有寫",
       v3.get("category") == {"大分類": "體育", "中主題": "全新主題二"},
       f"實得 {v3.get('category')!r}")
t3 = by_name(registry_topics(rp3), "全新主題二")
report("③ new_topics 覆蓋：登記簿有這一筆且 charter 正確",
       bool(t3) and t3.get("charter") == "測試用 charter 二" and t3.get("big") == "體育",
       f"實得 {t3!r}")
report("③ new_topics 不是 auto（是 batch 明講的，不該標 auto:true）",
       not (t3 or {}).get("auto"), f"實得 {t3!r}")

# ── ④ 新格式、中主題已經登記過（不靠 new_topics） → 照寫 ────────────────
sp4, rp4 = new_dirs()
new_state(sp4)
run(sp4, rp4, "topic-register", "--name", "既有格", "--charter", "已經登記過了", "--big", "社會")
out4 = add_batch(sp4, rp4, {"entries": [item("NEW3", {"category": "社會/既有格"})]})
v4 = get(sp4, rp4, "NEW3")
report("④ 已登記過的中主題：新格式照寫，不用附 new_topics",
       v4.get("category") == {"大分類": "社會", "中主題": "既有格"},
       f"實得 {v4.get('category')!r}")
report("④ 不印未登記訊息", "未登記中主題" not in out4, out4.strip()[:200])

# ── ⑤ 新格式 + --auto-register：不擋、自動登記，stdout 有「待補 charter」──
sp5, rp5 = new_dirs()
new_state(sp5)
out5 = add_batch(sp5, rp5, {"entries": [item("NEW4", {"category": "娛樂/自動登記格",
                                                       "src_text": "x" * 5})]},
                 extra_args=("--auto-register",))
v5 = get(sp5, rp5, "NEW4")
report("⑤ --auto-register：素材入庫且 category 有寫",
       v5.get("category") == {"大分類": "娛樂", "中主題": "自動登記格"},
       f"實得 {v5.get('category')!r}")
t5 = by_name(registry_topics(rp5), "自動登記格")
report("⑤ --auto-register：登記簿自動新增這一筆並標 auto:true",
       bool(t5) and t5.get("auto") is True, f"實得 {t5!r}")
report("⑤ stdout 提到「待補 charter」", "待補 charter" in out5, out5.strip()[:300])

# ── ⑥ set-category 預設（無 --auto-register）：未登記中主題照樣寫 ────────
sp6, rp6 = new_dirs()
run(sp6, rp6, "add", "--id", "SC1", "--source", "RT", "--checkpoint", "0999-1700",
   "--status", "has_script", "--entry", "SC1 (測試) ▎摘要。▎畫面：測試。▎無BITE。")
out6 = run(sp6, rp6, "set-category", "--id", "SC1", "--cat", "財經/沒登記過的中主題")
v6 = get(sp6, rp6, "SC1")
report("⑥ set-category 預設：未登記中主題照樣寫（不查登記簿）",
       v6.get("category") == {"大分類": "財經", "中主題": "沒登記過的中主題"},
       f"實得 {v6.get('category')!r}")
report("⑥ 登記簿沒有多出這一筆（off 模式不碰登記簿）",
       by_name(registry_topics(rp6), "沒登記過的中主題") is None)

# ── ⑦ set-category --auto-register：未登記中主題自動登記＋照寫 ──────────
sp7, rp7 = new_dirs()
run(sp7, rp7, "add", "--id", "SC2", "--source", "RT", "--checkpoint", "0999-1700",
   "--status", "has_script", "--entry", "SC2 (測試) ▎摘要。▎畫面：測試。▎無BITE。")
out7 = run(sp7, rp7, "set-category", "--id", "SC2", "--cat", "財經/自動登記格二",
          "--auto-register")
v7 = get(sp7, rp7, "SC2")
report("⑦ set-category --auto-register：category 有寫",
       v7.get("category") == {"大分類": "財經", "中主題": "自動登記格二"},
       f"實得 {v7.get('category')!r}")
t7 = by_name(registry_topics(rp7), "自動登記格二")
report("⑦ set-category --auto-register：登記簿自動新增並標 auto:true",
       bool(t7) and t7.get("auto") is True, f"實得 {t7!r}")
report("⑦ stdout 提到「待補 charter」", "待補 charter" in out7, out7.strip()[:300])

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
