#!/usr/bin/env python3
"""s2_platform_lint.py／s2_platform_merge.py 的測試（MASTER A9 子項⑥③）。

護欄（照 MASTER「實作共同護欄」）：
  - 不覆寫既有輸出（覆寫＝靜默銷毀依據）
  - 錯誤帶原始訊息、不回單一 boolean；欄位全空要明確失敗
  - **不靜默丟素材**：缺欄位的單筆要出現在報告裡
  - 離開碼 2＝讀不到，不是「沒問題」

除合成 fixture 外，另用 0817 兩份**真實候選檔**做 replay，把產出的 entries／pairs
與當時實際入庫的 `0817-s2-state.json` 逐則比對（那 32 則是現成 ground truth）。
真實檔不在本機時**明印跳過**，不靜默略過、也不計成 PASS。

用法：python scripts/test_s2_platform.py
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint_mod = load("s2_platform_lint")
merge = load("s2_platform_merge")

TMP = tempfile.mkdtemp(prefix="s2_a9_test_")
results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(f'{"PASS" if cond else "FAIL"}  {name}{(" → " + extra) if extra else ""}')


ABC_LINE = ("ABC081726007 (ABC) ▎聯準會9月降息機率升高，市場押注一碼。"
            "▎畫面：交易大廳、聯準會大樓外觀。▎無BITE。▎01:26")
ENEX_LINE = ("ENEX927228 (CCTV) ▎陸方公布黃海演訓區域，禁止船隻進入。"
             "▎畫面：海上艦艇航行、雷達畫面。▎無BITE。")


def abc_doc(**over):
    d = {
        "window_start": "2026-08-17 13:00", "window_end": "2026-08-17 16:50",
        "checkpoint": "0817-1650", "source": "ABC",
        "merged_into_handover": False, "reviewed": False,
        "counts": {"掃描": 3, "收錄": 1, "排除": 2},
        "skipped": [{"id": "ABC081726001", "why": "skip:體育"},
                    {"id": "ABC081726002", "why": "skip:外電"}],
        "needs_review": [], "known_gaps": [],
        "items": [{"id": "ABC081726007", "source": "ABC",
                   "first_seen_checkpoint": "0817-1650",
                   "script_status": "has_script", "raw_entry": ABC_LINE,
                   "category": {"大分類": "財經", "中主題": "聯準會利率"},
                   "sb_count": 0, "abc": {"storyNumber": "081726007"}}],
    }
    d.update(over)
    return d


def enex_doc(**over):
    d = {
        "window_start": "2026-08-17 13:00", "window_end": "2026-08-17 16:50",
        "checkpoint": "0817-1650", "source": "ENEX",
        "merged_into_handover": False, "reviewed": False,
        "counts": {"掃描": 1, "收錄": 1, "排除": 0},
        "skipped": [], "needs_review": [], "known_gaps": ["ENEX 抓不到時長"],
        "items": [{"id": "ENEX927228", "source": "ENEX",
                   "first_seen_checkpoint": "0817-1650",
                   "script_status": "has_script", "raw_entry": ENEX_LINE,
                   "category": {"大分類": "大陸", "中主題": "解放軍演訓",
                                "小分題": "黃海實彈射擊"},
                   "sb_count": 0, "enex": {"itemId": "927228"}}],
    }
    d.update(over)
    return d


def write(name, obj):
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return p


def run_lint(doc, name="0817-ABC-state.json", strict=False):
    return lint_mod.lint(write(name, doc), strict)


def has(msgs, frag):
    return any(frag in m for m in msgs)


# ── lint：素材行判準（轉呼 check_entry，不重寫）────────────────────────────
err, warn = run_lint(abc_doc())
check("乾淨 ABC 候選：0 必修", not err, "；".join(err))

d = abc_doc()
d["items"][0]["raw_entry"] = ABC_LINE.replace("▎畫面：交易大廳、聯準會大樓外觀。", "")
err, _ = run_lint(d)
check("缺 ▎畫面： 被 check_entry 抓到", has(err, "缺 ▎畫面："))

d = abc_doc()
d["items"][0]["raw_entry"] = ABC_LINE.replace("聯準會9月降息機率升高，市場押注一碼。",
                                              "聯" * 151 + "。")
err, _ = run_lint(d)
check("摘要超 150 字硬上限", has(err, "150"))

# ── lint：check_entry 管不到、候選檔階段特有的 ─────────────────────────────
d = abc_doc()
d["items"][0]["raw_entry"] = "△ " + ABC_LINE
err, _ = run_lint(d)
check("raw_entry 自帶時段標記（check_entry 會剝掉，必須自己抓）",
      has(err, "自帶時段標記"))

d = abc_doc()
d["items"][0]["raw_entry"] = "● " + ABC_LINE
err, _ = run_lint(d)
check("舊符號 ● 也算時段標記（18 檔 §2 只列四個，set-mark 有五個）",
      has(err, "自帶時段標記"))

d = abc_doc()
d["items"][0]["raw_entry"] = ABC_LINE.replace("▎01:26", "")
err, _ = run_lint(d)
check("ABC 缺 ▎MM:SS 收尾", has(err, "ABC 一律帶"))

d = enex_doc()
d["items"][0]["raw_entry"] = ENEX_LINE + "▎02:10"
err, _ = run_lint(d, "0817-ENEX-state.json")
check("ENEX 不准編時長（兩站規則相反）", has(err, "ENEX 目前抓不到時長"))

d = abc_doc()
d["items"][0]["raw_entry"] = ABC_LINE.replace("▎01:26", "▎URL：https://x▎01:26")
err, _ = run_lint(d)
check("寫了 ▎URL：（兩站都不寫）", has(err, "▎URL："))

# ── lint：結構與交叉一致性 ────────────────────────────────────────────────
d = abc_doc()
d["items"][0]["abc"]["storyNumber"] = "081726999"
err, _ = run_lint(d)
check("id 與 abc.storyNumber 對不上（抓到投遞紀錄 id 的形狀）", has(err, "對不上"))

d = abc_doc()
d["items"][0]["id"] = "ABC991326007"
d["items"][0]["raw_entry"] = ABC_LINE.replace("ABC081726007", "ABC991326007")
d["items"][0]["abc"]["storyNumber"] = "991326007"
err, _ = run_lint(d)
check("ABC Story Number 前 6 碼不是合法 MMDDYY", has(err, "MMDDYY"))

d = abc_doc()
d["items"].append(json.loads(json.dumps(d["items"][0])))
d["counts"]["收錄"] = 2
d["counts"]["掃描"] = 4
err, _ = run_lint(d)
check("id 重複", has(err, "id 重複"))

d = abc_doc()
d["items"][0]["category"]["中主題"] = "聯準會/利率"
err, _ = run_lint(d)
check("分類含 /（pairs 會被切成假小分題）", has(err, "set-category --pairs 會被切錯"))

d = abc_doc()
d["items"][0]["raw_entry"] = ABC_LINE.replace("ABC081726007", "ABC081726099")
err, _ = run_lint(d)
check("raw_entry 行首代碼與 id 不符", has(err, "行首代碼"))

d = abc_doc(source="ENEX")
err, _ = run_lint(d)
check("item.source 與頂層不一致", has(err, "不一致"))

d = abc_doc()
del d["items"][0]["script_status"]
err, _ = run_lint(d)
check("item 缺必要欄位明確報出", has(err, "缺 `script_status`"))

# ── lint：分級（缺 src_text 只給 ⚠️，否則工具會被跳過）────────────────────
err, warn = run_lint(abc_doc())
check("缺 src_text 預設是 ⚠️ 不是 ❌", not err and has(warn, "src_text"))
err, _ = run_lint(abc_doc(), strict=True)
check("--strict-src-text 才升為 ❌", has(err, "src_text"))

_, warn = run_lint(abc_doc(counts={"掃描": 9, "收錄": 1, "排除": 2}))
check("counts 掃描≠收錄+排除 給 ⚠️", has(warn, "≠"))
_, warn = run_lint(abc_doc(merged_into_handover=True))
check("merged_into_handover=true 交件當下不該是 true", has(warn, "已被整併過"))
_, warn = run_lint(abc_doc())
check("成對 .txt 不存在要提醒", has(warn, ".txt"))

try:
    lint_mod.lint(os.path.join(TMP, "不存在.json"))
    check("讀不到檔 → SystemExit(2)", False)
except SystemExit as e:
    check("讀不到檔 → 明確失敗且帶原始訊息", "讀取失敗" in str(e))

bad = os.path.join(TMP, "壞檔-state.json")
open(bad, "w", encoding="utf-8").write("{不是 json")
try:
    lint_mod.lint(bad)
    check("JSON 壞 → SystemExit", False)
except SystemExit as e:
    check("JSON 壞 → 明確失敗（不是回空清單當通過）", "讀取失敗" in str(e))

# 成對 txt 存在但少 id
p = write("0817-ABC2-state.json", abc_doc())
open(os.path.join(TMP, "0817-ABC2.txt"), "w", encoding="utf-8").write("完全沒有代碼")
_, warn = lint_mod.lint(p)
check("成對 txt 裡找不到 id 要提醒", has(warn, "找不到"))


# ── merge：欄位對照與輸出 ─────────────────────────────────────────────────
entries, pairs, misc = merge.build(abc_doc())
check("entries 欄位對照（first_seen_checkpoint→checkpoint 等）",
      entries[0]["checkpoint"] == "0817-1650" and entries[0]["status"] == "has_script"
      and entries[0]["entry"] == ABC_LINE and entries[0]["source"] == "ABC")
check("sb_count 帶過去（狀態檔要存，稽核③ 靠它）", entries[0]["sb_count"] == 0)
check("pairs 兩層分類", pairs == "ABC081726007=財經/聯準會利率", pairs)

e2, p2, _ = merge.build(enex_doc())
check("pairs 三層分類", p2 == "ENEX927228=大陸/解放軍演訓/黃海實彈射擊", p2)
check("缺 src_text 逐則點名", merge.build(abc_doc())[2]["no_src"] == ["ABC081726007"])

d = abc_doc()
d["items"][0]["category"] = None
entries, pairs, misc = merge.build(d)
check("無分類：照樣入庫但列進報告（素材消失補不回來）",
      len(entries) == 1 and pairs == "" and misc["uncat"] == ["ABC081726007"])

d = abc_doc()
del d["items"][0]["raw_entry"]
entries, _, misc = merge.build(d)
check("缺 raw_entry：不靜默丟掉，進 dropped 並指名候選檔欄位",
      not entries and has(misc["dropped"], "raw_entry"))

d = abc_doc()
d["items"][0]["category"]["中主題"] = "聯準會;利率"
try:
    merge.build(d)
    check("分類含 ; → 明確失敗", False)
except SystemExit as e:
    check("分類含 ; → 明確失敗且帶原值", "原值" in str(e))

cand = write("0818-ABC-state.json", abc_doc())
ep, pp = merge.out_paths(cand)
check("輸出檔落在候選檔旁，不是 CWD（R13 那個坑的形狀）",
      os.path.dirname(ep) == TMP and ep.endswith("0818-ABC-entries.json"))
merge.write_out(ep, "x", False)
try:
    merge.write_out(ep, "y", False)
    check("既有輸出不覆寫", False)
except SystemExit as e:
    check("既有輸出不覆寫（覆寫＝銷毀依據）", "不覆寫" in str(e))
merge.write_out(ep, "y", True)
check("--overwrite 才覆寫", open(ep, encoding="utf-8").read() == "y")


def run_main(argv):
    buf = io.StringIO()
    old = sys.argv
    sys.argv = ["s2_platform_merge.py"] + argv
    try:
        with redirect_stdout(buf):
            rc = merge.main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
        buf.write(str(e))
    finally:
        sys.argv = old
    return rc, buf.getvalue()


d = abc_doc()
d["items"][0]["raw_entry"] = ABC_LINE.replace("▎01:26", "")   # lint 必修
cand_bad = write("0818-BAD-state.json", d)
rc, out = run_main([cand_bad])
check("lint 有必修項 → 回 1 且不產檔", rc == 1 and
      not os.path.exists(os.path.join(TMP, "0818-BAD-entries.json")))
rc, out = run_main([cand_bad, "--force"])
check("--force 才硬上（並印出警告）", rc == 0 and "--force" in out)

cand2 = write("0818-OK-state.json", abc_doc())
rc, out = run_main([cand2])
check("dry 預設：產檔＋印下一步指令，不碰狀態檔",
      rc == 0 and os.path.exists(os.path.join(TMP, "0818-OK-entries.json"))
      and "add-batch" in out and "s2_topic_dedupe" in out)

cand3 = write("已入庫_0818-OK-state.json", abc_doc())
rc, out = run_main([cand3, "--apply", "--file", "x.json"])
check("檔名帶「已入庫_」+ --apply → 拒絕，避免重複入庫",
      rc == 1 and "重複入庫" in out)

cand4 = write("0818-M-state.json", abc_doc(merged_into_handover=True))
rc, out = run_main([cand4, "--apply", "--file", "x.json"])
check("merged_into_handover=true + --apply → 拒絕", rc == 1 and "重複入庫" in out)

cand5 = write("0818-N-state.json", abc_doc())
rc, out = run_main([cand5, "--apply"])
check("--apply 沒帶 --file → 不猜狀態檔", rc == 1 and "不猜" in out)

# 鎖檔：⛔ 只看存在、不 open（open 會害正要啟動的掃帶輪 SKIP）
lock = os.path.join(TMP, ".s2-scan.lock")
open(lock, "w").write("")
old_lock = merge.LOCK
merge.LOCK = lock
buf = io.StringIO()
with redirect_stdout(buf):
    rc, _ = merge.run_state("x.json", ["add-batch", "--entries", "e.json"], dry=False)
check("鎖檔存在 → 拒絕動狀態檔（沒有檔案鎖，同時寫會靜靜蓋掉）",
      rc == 1 and "鎖檔" in buf.getvalue())
check("run_state dry 不看鎖檔、只回指令字串",
      merge.run_state("x.json", ["add-batch"], dry=True)[0] == 0)
merge.LOCK = old_lock

cand6 = write("0818-K-state.json", abc_doc())
doc = merge.read_candidate(cand6)
merge.mark_merged(cand6, doc, "0818-1650")
after = json.load(open(cand6, encoding="utf-8"))
check("整併後翻 merged_into_handover=true 並留 merged_log",
      after["merged_into_handover"] is True and after["merged_log"][0]["by"]
      == "s2_platform_merge.py")
check("reviewed 不動（工具不能替人蓋章）", after["reviewed"] is False)

d = abc_doc()
d["needs_review"] = ["ABC081726007 分類拿不準"]
d["items"][0]["needs_review_note"] = "疑似與 NS 同一場訪問"
cand7 = write("0818-R-state.json", d)
rc, out = run_main([cand7])
check("候選檔的人工註記（頂層＋單筆 needs_review_note）不會靜默蒸發",
      "分類拿不準" in out and "同一場訪問" in out and "needs-review add" in out)


# ── 真實檔 replay：0817 兩份候選 vs 實際已入庫的狀態檔 ─────────────────────
GD = os.environ.get("S2_STATE_DIR") or r"G:\我的雲端硬碟\Claude共用\自動掃帶系統"
STATE = os.path.join(GD, "0817-s2-state.json")
PEND = os.path.join(GD, "_待整併")
real_pairs = [("已入庫_0817-ENEX-state.json", "ENEX"), ("已入庫_0817-ABC-state.json", "ABC")]
if not os.path.exists(STATE):
    print(f"\n⚠️ replay 跳過：找不到 {STATE}（本機沒有雲端硬碟時的正常情形，不計 PASS）")
else:
    # 正式 schema 的 items 是**陣列**（`s2_state.load()` 只在記憶體裡轉 dict），
    # 這裡自己索引，不 import s2_state——它 import 當下就會跑 default_file()，
    # 找不到當班狀態檔會直接 SystemExit，測試不該被那條規則綁住。
    raw_items = json.load(open(STATE, encoding="utf-8-sig"))["items"]
    state = ({it["id"]: it for it in raw_items} if isinstance(raw_items, list)
             else raw_items)
    va = lint_mod.load_validate()
    for fn, site in real_pairs:
        p = os.path.join(PEND, fn)
        if not os.path.exists(p):
            print(f"⚠️ replay 跳過 {fn}：檔案不存在")
            continue
        doc = merge.read_candidate(p)
        entries, pairs, misc = merge.build(doc)
        # ⚠️ 入庫後的 raw_entry 行首會被 render／set-mark 補上時段標記（△▲■◆），
        # 那是入庫之後才加的，比對前要剝掉（用 s2_validate 同一支 strip_mark）。
        diff = []
        for e in entries:
            got = state.get(e["id"])
            if got is None:
                diff.append(f"{e['id']}: 不在狀態檔")
                continue
            if va.strip_mark(got["raw_entry"])[1] != va.strip_mark(e["entry"])[1]:
                diff.append(f"{e['id']}: 內容不同")
        check(f"replay {site}：{len(entries)} 則 entries 的 raw_entry 與實際入庫逐字相同",
              not diff, f"{len(diff)} 則有差：" + "；".join(diff[:3]))
        pmap = dict(x.split("=", 1) for x in pairs.split(";") if x)
        bad = []
        for i, cat in pmap.items():
            got = state.get(i, {}).get("category") or {}
            want = "/".join(x for x in (got.get("大分類"), got.get("中主題"),
                                        got.get("小分題")) if x)
            if want != cat:
                bad.append(f"{i}: 產出 {cat} vs 實際 {want}")
        # ⚠️ 分類**不能**要求逐筆相同：0817 整併時使用者另下令做過一次全量分類複核，
        # 有素材被人工搬了大分類（落差報告 §8 記載的那 3 筆就是這麼抓出來的）。
        # 工具的責任是「照候選檔忠實產出」，不是猜人工後來會怎麼改。
        # 所以這裡只驗「pairs 指到的 id 都真的在狀態檔裡」，分歧逐筆印出來備查。
        missing = [i for i in pmap if i not in state]
        check(f"replay {site}：{len(pmap)} 筆 pairs 的 id 全在狀態檔內",
              not missing, "；".join(missing[:3]))
        if bad:
            print(f"      （{site} 有 {len(bad)} 筆分類與候選檔不同＝整併時人工複核搬過，"
                  f"非工具錯：{'；'.join(bad)}）")
        err, _ = lint_mod.lint(p)
        # 真實檔跑 lint 只印結果不判 PASS/FAIL——它們是 0817 規則下交的件，
        # 用今天的判準回頭打分沒有意義，但看得出 lint 在真檔上不會爆掉。
        print(f"      （lint 真實檔 {fn}：{len(err)} 項必修，僅供參考不計分）")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nPASS={sum(results)} FAIL={len(results) - sum(results)}")
sys.exit(0 if all(results) else 1)
