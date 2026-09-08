# -*- coding: utf-8 -*-
"""A10 P1d-命名（2026-09-08）：收容式中主題名稱檢查。開新名時 A／B 兩級都硬擋。

**為什麼要機械檢查**：13f 命名三判準第 ③ 條「⛔ 不用『XX趣聞』『XX動態』
『暖新聞』這類收容式名稱」從 0907 就寫在規則裡，但只是文字，沒有人擋——
三天內登記簿從 241 漲到 500 多題，其中三十幾題是籮筐。P1b-2 的閘門逼出了
「登記」，逼不出「別開籮筐名」。

**判準是拿真實登記簿（500+ 題）調的，每一條都有測試釘死**：
  A 級：剝掉開頭的限定詞後整個是空話（捷克趣聞→趣聞）。實掃 15 題、零冤枉。
  B 級：尾綴是空話（美股動態、運動賽事花絮）。實掃 25 題。
  例外：名字含數字或 ≥9 字 → 放行。實掃只放行 3 個（紐約市長9-11風波、
        陸具身智能機器人展演、福島熊出沒緊急重量事件），這 3 個確實在講一件事。
  ⚠️ 一開始 B 只提醒，回測「當晚新登記的 158 題」才發現 A 級 0 命中、B 級 8 命中——
     A 級抓的是前一天的毛病，當晚的籮筐全長在 B 級。使用者因此裁決 B 也硬擋。

用法：python -X utf8 scripts/test_s2_topic_naming.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.pop("S2_CHECKPOINT", None)
import s2_state as S  # noqa: E402

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


# ── ① A 級：登記簿裡真實出現過的籮筐名 ──────────────────────────
for n in ("暖新聞", "生活趣聞", "捷克趣聞", "斯洛伐克趣聞", "川普動態",
          "名人動態", "白宮動態", "軍事動態", "國際趣聞", "動物趣聞",
          "美國軟性新聞", "氣候現象", "好萊塢動態", "演藝圈動態"):
    lv, why = S.collector_level(n)
    report(f"① A 級：{n}", lv == "A", f"實得 {lv}／{why}")

report("① A 級的說明講得出理由（agent 要看得懂為什麼被擋）",
       "類別詞" in S.collector_level("捷克趣聞")[1], S.collector_level("捷克趣聞")[1])

# ── ② 正常名字不可以被擋（誤判成本最高的一組）────────────────
for n in ("邁阿密貨機事故", "尼泊爾洪災", "習近平出訪埃及", "德國地方選舉",
          "札波羅熱電廠風險", "曼德茲兄弟假釋案", "荷姆茲海峽對峙",
          "巴拿馬運河首位女性掌舵人", "教宗訪法前哨", "澳洲野火季"):
    lv, why = S.collector_level(n)
    report(f"② 正常名字不被擋：{n}", lv is None, f"實得 {lv}／{why}")

# ── ③ B 級（尾綴是類別詞）也硬擋——使用者 2026-09-08 22:xx 裁決 ────
# 回測當晚新登記的 158 題：A 級 0 命中、B 級 8 命中，而那 8 個正是當晚長出來的
# 籮筐（美股動態／運動賽事花絮／資料畫面小品…）。A 級抓的是前一天的毛病。
for n in ("西太平洋颱風動態", "地方選舉動態", "阿根廷國家隊話題", "暖心人情故事",
          "美股動態", "運動賽事花絮", "資料畫面小品", "日本社會案件",
          "英國王室動態", "文化獎項動態", "動物園萌趣動態"):
    lv, _why = S.collector_level(n)
    report(f"③ B 級（擋）：{n}", lv == "B", f"實得 {lv}")
report("③ B 級的說明有給改法（去掉尾綴長什麼樣）",
       "西太平洋颱風" in S.collector_level("西太平洋颱風動態")[1],
       S.collector_level("西太平洋颱風動態")[1])

# 例外：有數字或 9 字以上，尾綴通常是敘述的一部分而不是籮筐。
# 實掃 28 個 B 級只放行這 3 個，其餘 25 個全擋。
for n in ("紐約市長9-11風波", "陸具身智能機器人展演", "福島熊出沒緊急重量事件"):
    lv, _why = S.collector_level(n)
    report(f"③ 例外放行（有數字／夠長，真的在講一件事）：{n}", lv is None, f"實得 {lv}")

# ── ④ 髒輸入不炸 ─────────────────────────────────────────────
for label, v in (("None", None), ("空字串", ""), ("只有空白", "   "),
                 ("純數字", "12345"), ("英文", "Miami cargo")):
    try:
        S.collector_level(v)
        report(f"④ 髒輸入不炸（{label}）", True)
    except Exception as e:                       # noqa: BLE001
        report(f"④ 髒輸入不炸（{label}）", False, f"{type(e).__name__}: {e}")


# ── ⑤ add-batch：A 級不登記、只拒這一題，同批好名字照常 ────────
def new_dirs():
    d = tempfile.mkdtemp()
    sp, rp = os.path.join(d, "s.json"), os.path.join(d, "reg.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump({"date": "0999", "checkpoint": "0999-1700", "items": []},
                  f, ensure_ascii=False)
    with open(rp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "topics": []}, f, ensure_ascii=False)
    return d, sp, rp


def run(sp, rp, *args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("S2_CHECKPOINT", None)
    r = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, "--file", sp,
                        "--registry", rp, *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def entry(i, cat):
    return {"id": i, "source": "RT", "checkpoint": "0999-1700", "status": "has_script",
            "entry": f"{i} (測試 標題) (BITE) ▎摘要。", "src_text": "x", "category": cat}


d, sp, rp = new_dirs()
bp = os.path.join(d, "b.json")
with open(bp, "w", encoding="utf-8") as f:
    json.dump({"entries": [entry("RT0001", "話題/暖新聞/救人"),
                           entry("RT0002", "美國/邁阿密貨機事故/衝出跑道")],
               "new_topics": {
                   "暖新聞": {"charter": "溫馨小故事", "big": "話題"},
                   "邁阿密貨機事故": {"charter": "亞馬遜貨機衝出邁阿密機場跑道", "big": "美國"}}},
              f, ensure_ascii=False)
code, out = run(sp, rp, "add-batch", "--entries", bp)
with open(rp, encoding="utf-8") as f:
    reg = json.load(f)
reg_names = {t["name"] for t in reg["topics"]}
with open(sp, encoding="utf-8") as f:
    items = {x["id"]: x for x in json.load(f)["items"]}

report("⑤ A 級的新題沒有進登記簿", "暖新聞" not in reg_names, str(sorted(reg_names)))
report("⑤ 同批的好名字照常登記（不整批退回）", "邁阿密貨機事故" in reg_names,
       str(sorted(reg_names)))
report("⑤ 好名字那則的 category 有寫",
       (items.get("RT0002", {}).get("category") or {}).get("中主題") == "邁阿密貨機事故",
       str(items.get("RT0002", {}).get("category")))
report("⑤ 籮筐名那則素材照樣入庫、但 category 不寫（落進既有 🆕 路徑）",
       "RT0001" in items and not (items.get("RT0001", {}).get("category") or {}).get("中主題"),
       str(items.get("RT0001", {}).get("category")))
report("⑤ stdout 明講被擋、指名是哪一個", "⛔" in out and "暖新聞" in out, out.strip()[-500:])
report("⑤ stdout 給改法（改掛既有格或用專有名詞重新命名）",
       "find-similar" in out and "專有名詞" in out, out.strip()[-500:])
report("⑤ 不整批失敗（exit 0，其餘欄位照走）", code == 0, f"code={code}")

# B 級也擋
d, sp, rp = new_dirs()
bp = os.path.join(d, "b2.json")
with open(bp, "w", encoding="utf-8") as f:
    json.dump({"entries": [entry("RT0003", "天氣/西太平洋颱風動態/路徑")],
               "new_topics": {"西太平洋颱風動態": {"charter": "西太平洋颱風生成與路徑",
                                                  "big": "天氣"}}}, f, ensure_ascii=False)
code, out = run(sp, rp, "add-batch", "--entries", bp)
with open(rp, encoding="utf-8") as f:
    reg = json.load(f)
with open(sp, encoding="utf-8") as f:
    it3 = {x["id"]: x for x in json.load(f)["items"]}.get("RT0003") or {}
report("⑤ B 級沒有進登記簿", not any(t["name"] == "西太平洋颱風動態"
                                    for t in reg["topics"]))
report("⑤ B 級那則 category 不寫", not (it3.get("category") or {}).get("中主題"),
       str(it3.get("category")))
report("⑤ B 級印 ⛔ 並指名", "⛔" in out and "西太平洋颱風動態" in out, out.strip()[-300:])

# 例外名字照樣過
d, sp, rp = new_dirs()
bp = os.path.join(d, "b2b.json")
with open(bp, "w", encoding="utf-8") as f:
    json.dump({"entries": [entry("RT0005", "美國/紐約市長9-11風波/爭議")],
               "new_topics": {"紐約市長9-11風波": {"charter": "紐約市長候選人的9-11言論爭議",
                                                  "big": "美國"}}}, f, ensure_ascii=False)
code, out = run(sp, rp, "add-batch", "--entries", bp)
with open(rp, encoding="utf-8") as f:
    reg = json.load(f)
report("⑤ 例外名字照樣登記、不印 ⛔",
       any(t["name"] == "紐約市長9-11風波" for t in reg["topics"]) and "⛔" not in out,
       out.strip()[-200:])

# ── ⑥ 舊的不碰：登記簿裡既有的籮筐名照樣可用（使用者 0908 裁決）──
d, sp, rp = new_dirs()
with open(rp, "w", encoding="utf-8") as f:
    json.dump({"version": 1, "topics": [
        {"name": "暖新聞", "charter": "既有的籮筐名", "aliases": [], "big": "話題",
         "tc": {"T": [], "C": []}, "first_seen": "2026-09-01",
         "last_seen": "2026-09-01", "resident": False}]}, f, ensure_ascii=False)
bp = os.path.join(d, "b3.json")
with open(bp, "w", encoding="utf-8") as f:
    json.dump({"entries": [entry("RT0004", "話題/暖新聞/救人")], "new_topics": {}},
              f, ensure_ascii=False)
code, out = run(sp, rp, "add-batch", "--entries", bp)
with open(sp, encoding="utf-8") as f:
    it4 = {x["id"]: x for x in json.load(f)["items"]}.get("RT0004") or {}
report("⑥ 登記簿裡既有的籮筐名照樣寫得進去（舊的先不碰）",
       (it4.get("category") or {}).get("中主題") == "暖新聞", str(it4.get("category")))
report("⑥ 用既有籮筐名不會冒出 ⛔", "⛔" not in out, out.strip()[-200:])

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
