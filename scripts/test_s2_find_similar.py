# -*- coding: utf-8 -*-
"""A10 P1c（2026-09-08）：`find-similar` 粗篩＋`add-batch` 開新名時的相似格警告。

**來由是 0908-1100 的實錯**：agent 開了【邁阿密貨機墜舉】（還是錯字），而登記簿
已經有【邁阿密貨機事故】40 則、【邁阿密貨機衝跑道】9 則、【邁阿密機場貨機意外】
3 則、【邁阿密空難】2 則——五個格子講同一件事共 54 則。P1b-2 的閘門只逼「登記」，
逼不出「別開重複的名」，所以補這一層。

⚠️ 門檻是拿 0908 的**真實登記簿**調出來的，不是憑感覺。下面兩組是判準：
  真陽性：邁阿密那五個名字彼此要互相認得出來（含只共用「邁阿密」＋「貨機」的語序變體）。
  真陰性：`美國期中選舉造勢` vs `美國緝毒行動` 只共用「美國」——**不可以**互相命中，
          否則每個「美國X」都會互相警告，這條警告線就會像 0806 的對帳警告一樣被當雜訊。

用法：python -X utf8 scripts/test_s2_find_similar.py
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


def topic(name, charter="", aliases=(), big=""):
    return {"name": name, "charter": charter, "aliases": list(aliases), "big": big,
            "tc": {"T": [], "C": []}, "first_seen": "2026-09-01",
            "last_seen": "2026-09-01", "resident": False}


# 0908 真實登記簿裡那五個邁阿密格子（charter 用當時的實際語意重寫，長度相當）
REG = {"version": 1, "topics": [
    topic("邁阿密貨機事故", "亞馬遜 Prime Air 波音767貨機在邁阿密機場衝出跑道的後續", big="美國"),
    topic("邁阿密貨機衝跑道", "貨機衝出跑道當下的畫面與塔台通聯", big="美國"),
    topic("邁阿密機場貨機意外", "邁阿密國際機場貨機意外的機場運作影響", big="美國"),
    topic("邁阿密空難", "邁阿密貨機墜毀事故傷亡與救援", big="美國"),
    topic("美國期中選舉造勢", "期中選舉各州造勢場合與候選人發言", big="美國"),
    topic("美國緝毒行動", "美國緝毒署與海上緝毒行動", big="美國"),
    topic("尼泊爾洪災", "尼泊爾洪水與土石流災情、搜救",
          aliases=["尼泊爾水電廠隧道搜救"], big="社會"),
    topic("中尼邊境洪災", "中國尼泊爾邊境洪災", big="社會"),
    topic("德國地方選舉", "德國各邦地方選舉", big="政治"),
]}

STATE = {"date": "0999", "checkpoint": "0999-1700", "items": [
    {"id": f"RT{n:04d}", "source": "RT", "first_seen_checkpoint": "0999-1700",
     "script_status": "has_script", "raw_entry": f"RT{n:04d} (測試) ▎摘要。",
     "category": {"大分類": "美國", "中主題": "邁阿密貨機事故", "小分題": "後續"},
     "src_text": "x", "tc": {"T": ["社會"], "C": ["美國"]}}
    for n in range(1, 41)
]}


def new_dirs():
    d = tempfile.mkdtemp()
    sp, rp = os.path.join(d, "s.json"), os.path.join(d, "reg.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(STATE, f, ensure_ascii=False)
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(REG, f, ensure_ascii=False)
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


def names(rows):
    return [r[1] for r in rows]


# ── ① 真陽性：邁阿密五格互相認得出來 ────────────────────────────
rows = S.similar_topics("邁阿密貨機墜舉", REG, STATE, top=5)
report("① 邁阿密貨機墜舉 → 四個既有邁阿密格全部命中",
       set(names(rows)) == {"邁阿密貨機事故", "邁阿密貨機衝跑道",
                            "邁阿密機場貨機意外", "邁阿密空難"}, str(names(rows)))
report("① 則數最多的巨格排在最前（agent 要併進去的就是它）",
       names(rows)[0] == "邁阿密貨機事故", str(rows[0]))
report("① 只共用「邁阿密」的語序變體也抓得到（貪婪多段比對，不是只認最長那段）",
       "邁阿密機場貨機意外" in names(rows))
report("① 命中片段有印出來（agent 要看得到為什麼被判相似）",
       any("邁阿密" in s for s in rows[0][3]), str(rows[0][3]))

# ── ② 真陰性：只共用國名／通用詞不可以互相命中 ──────────────
rows2 = S.similar_topics("美國期中選舉造勢", REG, STATE, top=5)
report("② 美國期中選舉造勢 → 不命中美國緝毒行動（只共用「美國」）",
       "美國緝毒行動" not in names(rows2), str(names(rows2)))
rows3 = S.similar_topics("美國緝毒行動", REG, STATE, top=5)
report("② 反向也不命中（對稱）", "美國期中選舉造勢" not in names(rows3), str(names(rows3)))
report("② 邁阿密那五格不會被「美國X」誤掃進來",
       not any("邁阿密" in n for n in names(rows2) + names(rows3)),
       str(names(rows2) + names(rows3)))

# ── ③ 規格書的原始案例（尼泊爾）────────────────────────────────
rows4 = S.similar_topics("尼泊爾努瓦科特洪災搜救 隧道工人獲救", REG, STATE, top=5)
report("③ 短摘要也能比（不只名稱）：尼泊爾洪災與中尼邊境洪災都在候選裡",
       {"尼泊爾洪災", "中尼邊境洪災"} <= set(names(rows4)), str(names(rows4)))
report("③ 命中 alias 的那筆排在前面", names(rows4)[0] == "尼泊爾洪災", str(names(rows4)))
rows5 = S.similar_topics("德國地方選舉", REG, STATE, top=5)
report("③ 名稱與登記簿完全相同 → 不把自己列成候選",
       "德國地方選舉" not in names(rows5), str(names(rows5)))

# ── ④ CLI ────────────────────────────────────────────────────
d, sp, rp = new_dirs()
code, out = run(sp, rp, "find-similar", "--text", "邁阿密貨機墜舉")
report("④ CLI 印出候選與今日則數", code == 0 and "邁阿密貨機事故（今日 40 則）" in out,
       out.strip()[:160])
report("④ CLI 標高信度", "[高" in out, out.strip()[:160])
code, out_w = run(sp, rp, "find-similar", "--text", "尼泊爾努瓦科特洪災搜救 隧道工人獲救")
report("④ 弱信度也標得出來（中尼邊境洪災只共用「尼泊爾/洪災」）",
       "[弱" in out_w and "中尼邊境洪災" in out_w, out_w.strip()[:200])
code, out = run(sp, rp, "find-similar", "--text", "冰島火山噴發", "--top", "3")
report("④ 沒候選時印「無相似項」而不是空輸出", code == 0 and "無相似項" in out,
       out.strip()[:120])
code, out = run(sp, rp, "find-similar", "--text", "邁阿密貨機墜舉", "--top", "2")
report("④ --top 生效", code == 0 and out.count("[") == 2, out.strip()[:160])

# ── ⑤ add-batch 開新名時的警告（不擋）──────────────────────────
d, sp, rp = new_dirs()
bp = os.path.join(d, "b.json")
with open(bp, "w", encoding="utf-8") as f:
    json.dump({"entries": [
        {"id": "RT9001", "source": "RT", "checkpoint": "0999-1700", "status": "has_script",
         "entry": "RT9001 (邁阿密貨機 新聞) ▎摘要。", "src_text": "x",
         "category": "美國/邁阿密貨機墜舉/後續", "tc": "社會/美國"}],
        "new_topics": {"邁阿密貨機墜舉": {"charter": "貨機衝出跑道", "big": "美國"}}},
        f, ensure_ascii=False)
code, out = run(sp, rp, "add-batch", "--entries", bp)
with open(sp, encoding="utf-8") as f:
    st_after = json.load(f)
it = {x["id"]: x for x in st_after["items"]}.get("RT9001") or {}
report("⑤ 開新名撞相似格 → 印 ⚠️ 警告並列出候選",
       "撞到既有相似格" in out and "邁阿密貨機事故" in out, out.strip()[-400:])
report("⑤ 只警告不擋：素材照樣入庫、category 照樣寫",
       code == 0 and (it.get("category") or {}).get("中主題") == "邁阿密貨機墜舉",
       f"code={code} cat={it.get('category')}")
with open(rp, encoding="utf-8") as f:
    reg_after = json.load(f)
report("⑤ 只警告不擋：新名照樣進登記簿",
       any(t["name"] == "邁阿密貨機墜舉" for t in reg_after["topics"]))
report("⑤ 警告有給下一步（改掛既有格＋掛 alias）",
       "topic-alias" in out and "set-category" in out, out.strip()[-300:])

# 不相似的新名不該冒出警告
d, sp, rp = new_dirs()
bp = os.path.join(d, "b2.json")
with open(bp, "w", encoding="utf-8") as f:
    json.dump({"entries": [
        {"id": "RT9002", "source": "RT", "checkpoint": "0999-1700", "status": "has_script",
         "entry": "RT9002 (冰島 新聞) ▎摘要。", "src_text": "x",
         "category": "國際/冰島火山噴發/疏散", "tc": "天災天氣/歐洲"}],
        "new_topics": {"冰島火山噴發": {"charter": "冰島火山噴發與疏散", "big": "國際"}}},
        f, ensure_ascii=False)
code, out = run(sp, rp, "add-batch", "--entries", bp)
report("⑤ 不相似的新名不印警告（避免每次開名都響）",
       code == 0 and "撞到既有相似格" not in out, out.strip()[-200:])

# ── ⑥ 髒資料不炸 ─────────────────────────────────────────────
for label, args_ in (("登記簿是空的", ("邁阿密", {"topics": []}, STATE)),
                     ("登記簿沒有 topics 鍵", ("邁阿密", {}, STATE)),
                     ("state 是 None", ("邁阿密", REG, None)),
                     ("text 是空字串", ("", REG, STATE)),
                     ("topics 裡混入非 dict", ("邁阿密", {"topics": ["壞", None]}, STATE))):
    try:
        S.similar_topics(*args_)
        report(f"⑥ 髒資料不炸（{label}）", True)
    except Exception as e:                       # noqa: BLE001
        report(f"⑥ 髒資料不炸（{label}）", False, f"{type(e).__name__}: {e}")

print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
