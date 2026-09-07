# -*- coding: utf-8 -*-
"""側錄擬歸位行的 T／C 後綴與 arity 護欄迴歸（A10 v2 收尾，2026-08-25）。

這支要守的三件事，每一件都對應一個踩過或差點踩到的形狀：

  ① **arity 不可靜默丟棄**。改動前 `segs[3]` 以後直接被丟掉、沒有任何檢查，
     於是「多一段沒人看得懂的東西」跟「格式正確」在回傳碼上完全一樣（都是 0）。
     那正是計畫書把它排在所有事情前面的理由：不修就加欄位，等於在一個會靜默
     吞資料的 parser 上疊功能。

  ② **T／C 用標籤不用位置**。小分題可省略，若 T/C 靠 `segs[3]`／`segs[4]` 定位，
     省略小分題的那些則會把 `T:…` 讀成小分題——靜默錯位，而且錯得很像對的。

  ③ **區段內每一段都要有 T/C**。render 的 `fold_side()` 摺單元時取第一列，
     只標第一段會讓「第一段沒標、後面有標」的單元整個看起來沒標。

另外守兩條資料安全鐵律：舊格式永久合法（照樣入庫、只是沒標），
以及補標**絕不可以**動到 `raw_entry`（那是 S2b 子系統存在的目的）。

用法：python test_s2_side_tc.py
"""
import json
import os
import sys
import tempfile

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


def parse(text):
    return st.parse_side_txt(text, source=None, tc_date="08-25")


def tc_of(rows, idx=0):
    return rows[idx][4]


# ══ ① 標籤式解析 ═══════════════════════════════════════════════════════
NEW_FULL = """擬歸位：======社會====== → 【首爾大火】 → 延燒五小時 → T:社會 → C:南韓
CNN 08-25 160106 （主播）
內容一。
CNN 08-25 160130 （記者旁白）
內容二。
"""
rows = parse(NEW_FULL)
report("新格式：三層歸位照舊解出來",
       len(rows) == 2 and rows[0][2] == {"大分類": "社會", "中主題": "首爾大火", "小分題": "延燒五小時"},
       f"得到 {rows[0][2] if rows else None}")
report("新格式：T/C 解析正確",
       tc_of(rows) == {"T": ["社會"], "C": ["南韓"]}, f"得到 {tc_of(rows) if rows else None}")
report("③ 區段內每一段都有 T/C（不是只有第一段）",
       len(rows) == 2 and rows[1][4] == {"T": ["社會"], "C": ["南韓"]},
       f"第二段得到 {rows[1][4] if len(rows) > 1 else None}")

# ══ ② 省略小分題不可錯位 ═══════════════════════════════════════════════
NO_SUB = """擬歸位：======天氣====== → 【北海道地震】 → T:天災天氣 → C:日本
NHK 08-25 215012 （主播）
內容。
"""
rows = parse(NO_SUB)
report("② 省略小分題：T 沒有被讀成小分題",
       rows[0][2].get("小分題") in (None, ""), f"小分題＝{rows[0][2].get('小分題')!r}")
report("② 省略小分題：T/C 仍然解得到",
       tc_of(rows) == {"T": ["天災天氣"], "C": ["日本"]}, f"得到 {tc_of(rows)}")

# 只有 C、沒有 T（單側可留空）
rows = parse("擬歸位：======話題====== → 【貓咪市長】 → C:日本\nNHK 08-25 210000 （主播）\n內容。\n")
report("單側標籤：只有 C 也吃",
       tc_of(rows) == {"T": [], "C": ["日本"]}, f"得到 {tc_of(rows)}")

# 全形冒號＋全形／頓號分隔
rows = parse("擬歸位：======美國====== → 【關稅】 → T：財經，政治 → C：美國、南韓\n"
             "CNN 08-25 120000 （主播）\n內容。\n")
report("全形冒號與全形／頓號分隔都吃",
       tc_of(rows) == {"T": ["財經", "政治"], "C": ["美國", "南韓"]}, f"得到 {tc_of(rows)}")

# ══ 舊格式永久合法 ════════════════════════════════════════════════════
OLD = """擬歸位：======社會====== → 【栃木線意外】 → 4死最新調查
NHK 08-25 215128 （記者旁白）
內容。
"""
rows = parse(OLD)
report("舊格式：照樣解得出來（不是錯誤）",
       len(rows) == 1 and rows[0][2].get("小分題") == "4死最新調查")
report("舊格式：T/C 兩邊都空，不是 None（下游一律 .get 得到 list）",
       tc_of(rows) == {"T": [], "C": []}, f"得到 {tc_of(rows)}")

# ══ ① arity 明確失敗 ═════════════════════════════════════════════════
BAD_ARITY = """擬歸位：======社會====== → 【中主題】 → 小分題 → 多出來的第四段
NHK 08-25 215128 （記者旁白）
內容。
"""
try:
    parse(BAD_ARITY)
    report("① 4 個位置段要明確失敗", False, "沒有拋例外（＝又回到靜默丟棄）")
except st.SideHomeError as e:
    report("① 4 個位置段要明確失敗", True)
    report("① 失敗訊息要帶原值（不然交件者不知道改哪一行）",
           "多出來的第四段" in str(e), f"訊息＝{str(e)[:80]}")
except Exception as e:                                       # noqa: BLE001
    report("① 4 個位置段要明確失敗", False, f"拋了 {type(e).__name__}")

# T/C 段不算位置段——三層＋T＋C＝5 段也必須合法
rows = parse(NEW_FULL)
report("① T/C 段不佔位置額度（三層＋T＋C 共 5 段仍合法）", len(rows) == 2)

# ══ T/C 不可跨區段沿用 ════════════════════════════════════════════════
CARRY = """擬歸位：======社會====== → 【首爾大火】 → T:社會 → C:南韓
CNN 08-25 160106 （主播）
內容一。

======天氣======

【颱風】
CNN 08-25 170000 （主播）
內容二。
"""
rows = parse(CARRY)
by_id = {r[0]: r for r in rows}
report("換大分類後 T/C 不沿用",
       by_id["CNN 08-25 170000"][4] == {"T": [], "C": []},
       f"得到 {by_id['CNN 08-25 170000'][4]}")

CARRY2 = """擬歸位：======社會====== → 【首爾大火】 → T:社會 → C:南韓
CNN 08-25 160106 （主播）
內容一。
【另一個中主題】
CNN 08-25 180000 （主播）
內容二。
"""
rows = parse(CARRY2)
by_id = {r[0]: r for r in rows}
report("換中主題後 T/C 不沿用",
       by_id["CNN 08-25 180000"][4] == {"T": [], "C": []},
       f"得到 {by_id['CNN 08-25 180000'][4]}")


# ══ cmd_add_side 端 ═══════════════════════════════════════════════════
class _Args:
    def __init__(self, **kw):
        self.txt = kw["txt"]
        self.checkpoint = kw.get("checkpoint", "0825-1600")
        self.source = kw.get("source")
        self.homes = kw.get("homes", "")
        self.normalize = kw.get("normalize", False)
        self.tc_date = kw.get("tc_date", "08-25")
        self.overwrite = kw.get("overwrite", False)
        self.dry_run = kw.get("dry_run", False)
        self.file = kw["file"]
        # A10 P1b：`cmd_add_side` 現在會查／寫中主題登記簿（新題自動
        # register）。這支測試在驗證 T/C 字典邏輯，跟登記簿無關——
        # ⛔ 不能讓它落到真正的 `scripts/s2_topic_registry.json`
        # （0907 實錯：直接呼叫 `cmd_add_side` 沒有 argparse 的 `--registry`
        # 預設可用，`getattr` 退回 `REGISTRY_PATH` 就是正式檔，測試資料
        # 就這樣寫了進去）。固定指到隔離的空登記簿，且關掉自動登記
        # （這支不測這塊，關掉最單純、也最貼近「舊行為」）。
        self.registry = kw.get("registry", os.path.join(tempfile.mkdtemp(), "registry.json"))
        self.auto_register = kw.get("auto_register", False)


def _write(tmp, name, text):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def _fresh_state(p, items=None):
    json.dump({"checkpoint": "0825-1600", "items": items or []},
              open(p, "w", encoding="utf-8"), ensure_ascii=False)
    return st.load(p)


tmp = tempfile.mkdtemp()
sp = os.path.join(tmp, "0825-s2-state.json")

txt = _write(tmp, "new.txt", NEW_FULL)
s = _fresh_state(sp)
st.cmd_add_side(s, _Args(txt=txt, file=sp))
saved = {x["id"]: x for x in json.load(open(sp, encoding="utf-8"))["items"]}
report("add-side：T/C 寫進頂層 tc 鍵（⛔ 不是 category）",
       saved["CNN 08-25 160106"].get("tc") == {"T": ["社會"], "C": ["南韓"]}
       and "T" not in saved["CNN 08-25 160106"]["category"],
       f"得到 {saved['CNN 08-25 160106'].get('tc')}")
report("add-side：單元內兩段都寫到",
       saved["CNN 08-25 160130"].get("tc") == {"T": ["社會"], "C": ["南韓"]})

# 舊格式：照樣入庫、不進 bad
txt = _write(tmp, "old.txt", OLD)
s = _fresh_state(sp)
st.cmd_add_side(s, _Args(txt=txt, file=sp))
saved = {x["id"]: x for x in json.load(open(sp, encoding="utf-8"))["items"]}
report("舊格式：照樣入庫（素材消失補不回來，分類可以事後補）",
       "NHK 08-25 215128" in saved)
report("舊格式：沒有 tc 鍵（不是寫一個空的進去）",
       not (saved["NHK 08-25 215128"].get("tc") or {}).get("T"))

# 字典外的名稱視同沒標，不寫進狀態檔
txt = _write(tmp, "badname.txt",
             "擬歸位：======社會====== → 【X】 → T:亂寫的議題 → C:南韓\n"
             "CNN 08-25 190000 （主播）\n內容。\n")
s = _fresh_state(sp)
st.cmd_add_side(s, _Args(txt=txt, file=sp))
saved = {x["id"]: x for x in json.load(open(sp, encoding="utf-8"))["items"]}
report("字典外的 T 名稱不寫進狀態檔（合法的 C 照留）",
       saved["CNN 08-25 190000"].get("tc") == {"T": [], "C": ["南韓"]},
       f"得到 {saved['CNN 08-25 190000'].get('tc')}")

# 🔴 補標不可動 raw_entry
txt = _write(tmp, "new.txt", NEW_FULL)
s = _fresh_state(sp, [{"id": "CNN 08-25 160106", "source": "SIDE_CNN",
                       "raw_entry": "人工定稿過的逐字內容，一個字都不准動",
                       "category": {"大分類": "社會", "中主題": "首爾大火"},
                       "script_status": "has_script"}])
st.cmd_add_side(s, _Args(txt=txt, file=sp))
saved = {x["id"]: x for x in json.load(open(sp, encoding="utf-8"))["items"]}
report("🔴 已在庫補標：raw_entry 一個字都沒動",
       saved["CNN 08-25 160106"]["raw_entry"] == "人工定稿過的逐字內容，一個字都不准動",
       f"得到 {saved['CNN 08-25 160106']['raw_entry'][:20]!r}")
report("已在庫補標：tc 有補上（候選檔是 append、每輪重讀，事後補 T:／C: 才會生效）",
       saved["CNN 08-25 160106"].get("tc") == {"T": ["社會"], "C": ["南韓"]},
       f"得到 {saved['CNN 08-25 160106'].get('tc')}")

# 🔴 純補標的重跑（整份都已在庫、added 是空的）也**必須存檔**。
#    只看 `added` 的話會印出「補標已在庫 N」卻什麼都沒寫進去——宣稱成功、
#    實際丟失。上一版 fixture 剛好有一段是新的，`added` 非空、save 順便發生了，
#    這個形狀從沒被測到。這正是 14 C-3b 承諾「事後補寫 T:/C: 也會生效」的路徑。
s = _fresh_state(sp, [
    {"id": "CNN 08-25 160106", "source": "SIDE_CNN", "raw_entry": "a",
     "category": {"大分類": "社會", "中主題": "首爾大火"}, "script_status": "has_script"},
    {"id": "CNN 08-25 160130", "source": "SIDE_CNN", "raw_entry": "b",
     "category": {"大分類": "社會", "中主題": "首爾大火"}, "script_status": "has_script"},
])
st.cmd_add_side(s, _Args(txt=txt, file=sp))
saved = {x["id"]: x for x in json.load(open(sp, encoding="utf-8"))["items"]}
report("🔴 純補標重跑（added 空）也要真的存檔",
       saved["CNN 08-25 160106"].get("tc") == {"T": ["社會"], "C": ["南韓"]}
       and saved["CNN 08-25 160130"].get("tc") == {"T": ["社會"], "C": ["南韓"]},
       f"得到 {saved['CNN 08-25 160106'].get('tc')} / {saved['CNN 08-25 160130'].get('tc')}")
report("純補標重跑：raw_entry 仍然沒動",
       saved["CNN 08-25 160106"]["raw_entry"] == "a"
       and saved["CNN 08-25 160130"]["raw_entry"] == "b")

# 已有 tc 的不覆蓋（人工用 set-tc 改過的優先）
s = _fresh_state(sp, [{"id": "CNN 08-25 160106", "source": "SIDE_CNN",
                       "raw_entry": "x", "category": {"大分類": "社會", "中主題": "首爾大火"},
                       "tc": {"T": ["政治"], "C": ["美國"]}, "script_status": "has_script"}])
st.cmd_add_side(s, _Args(txt=txt, file=sp))
saved = {x["id"]: x for x in json.load(open(sp, encoding="utf-8"))["items"]}
report("已有 tc 的不被候選檔蓋掉（set-tc 手動改過的優先）",
       saved["CNN 08-25 160106"]["tc"] == {"T": ["政治"], "C": ["美國"]},
       f"得到 {saved['CNN 08-25 160106']['tc']}")

# arity 壞掉時：整份不入庫、離開碼 2
txt = _write(tmp, "bad.txt", BAD_ARITY)
s = _fresh_state(sp)
try:
    st.cmd_add_side(s, _Args(txt=txt, file=sp))
    report("① arity 壞掉：cmd_add_side 要 exit 2", False, "沒有 exit")
except SystemExit as e:
    report("① arity 壞掉：cmd_add_side 要 exit 2", e.code == 2, f"離開碼 {e.code}")
after = json.load(open(sp, encoding="utf-8"))["items"]
report("① arity 壞掉：一個字都沒寫進狀態檔（改好重跑即可，素材不會消失）",
       after == [], f"得到 {len(after)} 則")


# ══ set-tc 的兩個觸發點（2026-08-25，「大量未分類」診斷後補）═══════════════
# 🔴 使用者觀察到頁面常有大量未分類、要事後再請 agent 補。診斷結果是**時序**，
#    不是 agent 沒標：
#    ① render → 覆蓋率閘門報「N 則還沒標」→ agent 補標 → 收工，**沒有人再
#       render 一次**，所以頁面永遠缺當輪那一批（0825-1200 實測 618 列有 53 列
#       落回關鍵詞兜底，狀態檔卻 100%）。
#    ② `set-top checkpoint` 是收工才下的，於是輪次中途的 set-tc 被記到**前一輪**
#       的桶（0825-0430 實測用掉 0100 的第 7、8 格），撞到上限就整輪標不完。
import contextlib                                             # noqa: E402
import io as _io                                              # noqa: E402


class _TcArgs:
    def __init__(self, file, pairs):
        self.file, self.pairs = file, pairs
        self.id = self.tc = None


def _run_set_tc(items, pairs, top=None):
    doc = {"checkpoint": "0825-1600", "items": items}
    doc.update(top or {})
    json.dump(doc, open(sp, "w", encoding="utf-8"), ensure_ascii=False)
    s = st.load(sp)
    buf = _io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf):
            st.cmd_set_tc(s, _TcArgs(sp, pairs))
    except SystemExit as e:
        code = e.code
    return code, buf.getvalue()


_it = [{"id": "AP1", "source": "AP", "raw_entry": "x", "category": None,
        "script_status": "has_script"}]

_code, _out = _run_set_tc(_it, "AP1=政治/美國",
                          {"last_render_ts": "2026-08-25T12:18:14.027672"})
report("① render 之後才標 → 要印出「再跑一次 render」",
       _code == 0 and "s2_render.py" in _out, f"離開碼 {_code}；輸出 {_out[-90:]!r}")
report("① 重跑指令必須帶 --out（少了它 render 只印到 stdout、什麼都不寫）",
       "--out" in _out and "晚班交接.txt" in _out, f"輸出 {_out[-140:]!r}")


_code, _out = _run_set_tc(_it, "AP1=政治/美國")
report("① 還沒 render 過就不要囉嗦（避免變成每次都印的雜訊）",
       _code == 0 and "s2_render.py" not in _out, f"輸出 {_out[-90:]!r}")

_code, _out = _run_set_tc(_it, "AP1=政治/美國",
                          {"tc_calls": {"0825-1600": st.TC_CALLS_PER_CHECKPOINT}})
report("② 撞上限時要指出「checkpoint 可能還停在上一輪」並給自救指令",
       _code == 3 and "set-top checkpoint" in _out, f"離開碼 {_code}；輸出 {_out[-120:]!r}")


# ══ render 端：fold_side 要記住「單元內第一個有 T/C 的段」 ═══════════════
# 🔴 為什麼：`fold_side` 摺單元時取 `dict(第一列)`。舊格式先入庫、事後用
#    `set-tc` 補標到單元中間某一段時，只認第一列會讓**整個單元看起來沒標**。
sys.path.insert(0, os.path.join(HERE, "prototype"))
try:
    import s2_render_matrix as M      # noqa: E402
except Exception as e:                # noqa: BLE001
    report("render 端 fold_side（import 失敗，未測）", False, f"{type(e).__name__}: {e}")
else:
    _rows = [
        {"kind": "side", "id": "CNN 08-25 160106", "src": "CNN", "big": "社會",
         "mid": "火", "sub": "a", "text": "x", "q": "x"},
        {"kind": "side", "id": "CNN 08-25 160130", "src": "CNN", "big": "社會",
         "mid": "火", "sub": "a", "text": "y", "q": "y"},
        {"kind": "mat", "id": "AP123", "big": "社會", "mid": "火", "sub": "a",
         "text": "z", "q": "z"},
    ]
    _stored = {"CNN 08-25 160130": {"T": ["社會"], "C": ["南韓"]}}
    _u = M.fold_side(_rows, _stored)[0]
    report("fold_side：單元 id 不可被改掉（矩陣格與對帳都靠它）",
           _u["id"] == "CNN 08-25 160106", f"得到 {_u['id']}")
    report("fold_side：tc_id 指向單元內第一個有 T/C 的段",
           _u.get("tc_id") == "CNN 08-25 160130", f"得到 {_u.get('tc_id')}")
    _T, _C, _, _src = M.join_tc(_u, _stored)
    report("join_tc：單元不再看起來沒標", _src == "stored", f"得到 {_src}")
    _o = M.fold_side(_rows)
    report("fold_side：沒給 stored 時行為與改動前相同",
           len(_o) == 2 and _o[0]["segs"] == 2)
    report("fold_side：第一段就有 T/C 時 tc_id＝第一段",
           M.fold_side(_rows, {"CNN 08-25 160106": {"T": ["社會"], "C": []}})[0]["tc_id"]
           == "CNN 08-25 160106")

print("\n全部通過" if ok else "\n有失敗項")
sys.exit(0 if ok else 1)
