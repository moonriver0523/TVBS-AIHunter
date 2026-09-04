# -*- coding: utf-8 -*-
"""晚班交接 HTML 的 T/C 矩陣版（A10 v2，2026-08-24 上線為正式版）。

定位：**純呈現層薄殼**。資料層一律 import 生產函式（`s2_render_html.collect()`／
`build_header()`／`find_archive_dates()`／`build_datebar()`），本檔只負責
「把 row 換一種畫法」——矩陣熱圖＋依 T 分組的清單。

⛔ 這不是第三條 render 路。`s2_render.py`（排程每輪走的）與
   `s2_render_html.py --matrix`（獨立入口）**都呼叫本檔的 build_html()**。
   2026-08-11 事故就是歷史列只接了獨立入口、排程那條沒接，功能「上線」卻
   從來沒生效過（見 `s2_render.py:619` 註解）——**新功能兩條路都要接**。

T/C 來源優先序：**狀態檔已存的 → `tag_tc()` 關鍵詞兜底 → 「未分類」**。
這條 fallback 是「一條產線一條產線接、不會壞頁面」的技術基礎：還沒接上
`set-tc` 的產線沒有 `tc` 欄位，自動退回兜底，頁面照常。
"""
import html as _html
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "prototype"))

import s2_render_html as H          # noqa: E402  生產渲染器，唯讀使用
import build_tc_matrix_0821 as BASE  # noqa: E402  T/C 顯示順序、emoji、tag_tc 兜底
from s2_state import normalize_c, normalize_t, load_special_t  # noqa: E402  ⛔ 不要複製一份

# 模板放 scripts/ 而不是 scripts/prototype/——prototype 是試作區，不該在產線路徑上。
# 與 prototype/_template_v1.html 的差異只有兩處：拿掉「v1 試作」字樣、
# 不再自己包一層 .histbar（生產 build_datebar() 已經回傳完整的 histbar 元素）。
TPL = os.path.join(HERE, "s2_matrix_template.html")
UNKNOWN = "未分類"

# 「未分類」兜底改寫：`tag_tc()` 規則全沒命中時會靜默塞「社會」／「國際」，
# 於是「判出來的」和「猜的」在畫面上長得一樣。改成回傳「未分類」，讓它自成一格。
# 🔴 技術債：目前用 inspect.getsource() 字串替換後 exec，屬暫時外掛。
#    正式作法是直接改分類器本身。替換對不上時**直接失敗**，不靜默退回舊行為
#    ——靜默退回會讓「未分類」永遠是 0，比壞掉更難發現。
_FALLBACK_PATCHES = [
    ('T.add("話題" if big == "話題" else "社會")', f'T.add("{UNKNOWN}")'),
    ('if not C:\n        C.add("國際")', f'if not C:\n        C.add("{UNKNOWN}")'),
    ('if big == "美國" and not T:\n        T.add("社會")',
     f'if big == "美國" and not T:\n        T.add("{UNKNOWN}")'),
    ('if big == "體育" and not C:\n        C.add("國際")',
     f'if big == "體育" and not C:\n        C.add("{UNKNOWN}")'),
]


def _make_tagger():
    import inspect
    src = inspect.getsource(BASE.tag_tc)
    for old, new in _FALLBACK_PATCHES:
        if old not in src:
            raise RuntimeError(
                "tag_tc() 的兜底分支改寫失敗，原始碼可能已變動：\n"
                f"  找不到：{old!r}\n"
                "  請對照 build_tc_matrix_0821.py::tag_tc() 更新 _FALLBACK_PATCHES。")
        src = src.replace(old, new)
    ns = dict(BASE.__dict__)
    exec(compile(src, "<tag_tc+未分類>", "exec"), ns)
    return ns["tag_tc"]


tag_tc = _make_tagger()


def stored_tc(state):
    """從狀態檔撈已存的 T/C。

    為什麼要自己撈：`collect()` 是**用固定欄位清單**組 row 的，`items` 上新增的
    `tc` 欄位不會流到 renderer。⚠️ `state["items"]` 在 s2_state.load() 後是 dict、
    直接讀磁碟 JSON 則是陣列，兩種都要吃。
    """
    items = state.get("items") or []
    pairs = items.items() if isinstance(items, dict) else (
        (it.get("id"), it) for it in items)
    out = {}
    for i, it in pairs:
        tc = (it or {}).get("tc") or {}
        if i and (tc.get("T") or tc.get("C")):
            # ⚠️ 歷史狀態檔存著已刪的桶（0824 有 6 則墨西哥、2 則其他地區）。
            #    不在這裡改寫的話，重 render 舊檔時那些 C 在矩陣上**無格可放**。
            C, _ = normalize_c(tc.get("C") or [])
            T, _ = normalize_t(tc.get("T") or [])
            out[i] = {"T": T, "C": C}
    return out


def join_tc(r, stored):
    """有存的用存的 → 沒有的跑 tag_tc() → 再沒有就「未分類」。

    ⚠️ 側錄單元查的是 `tc_id`（單元內**第一個有 T/C 的段**）而不是 `id`
    （＝第一列）。`add-side` 現在會把 T/C 寫進區段每一段，兩者通常相同；
    但混合情形（舊格式先入庫、事後才用 `set-tc` 補標到某一段）下，
    只認第一列會讓整個單元看起來沒標。見 fold_side。
    """
    T, C, flags = tag_tc(r)
    s = stored.get(r.get("tc_id") or r.get("id") or "")
    if not s:
        return T, C, flags, "heur"
    got_t, got_c = bool(s["T"]), bool(s["C"])
    return (s["T"] if got_t else T, s["C"] if got_c else C, flags,
            "stored" if (got_t and got_c) else "mixed")


def fold_side(rows, stored=None):
    """側錄列依 (src,大,中,小) 摺成單元；其餘列原樣保留、順序不變。

    txt 檔頭的「側錄 N 則」就是這個數字（`s2_validate.side_units`）；
    網頁若照列數算，一段連線的十幾個 TC 會被當成十幾則、數字灌爆。

    `stored`（2026-08-25，A10 v2 收尾）：有給的話順便挑出單元內**第一個有 T/C
    的段**，記進 `tc_id` 供 `join_tc` 查。⛔ 不是改 `id`——`id` 是單元的身分
    （矩陣格、對帳都靠它），換掉會動到不相干的東西；只多帶一個查詢用的鍵。
    沒給 `stored` 時行為與改動前完全相同（`tc_id` 就是第一列的 id）。
    """
    stored = stored or {}

    def _has(r):
        s = stored.get(r.get("id") or "")
        return bool(s and (s.get("T") or s.get("C")))

    out, cur, curkey = [], None, None
    for r in rows:
        if r.get("kind") != "side":
            if cur:
                out.append(cur)
                cur, curkey = None, None
            out.append(r)
            continue
        k = (r.get("src"), r.get("big"), r.get("mid"), r.get("sub"))
        if cur and k == curkey:
            cur["text"] = cur["text"] + "\n" + (r.get("text") or "")
            cur["q"] = cur["q"] + " " + (r.get("q") or "")
            cur["segs"] += 1
            # 本輪新增（2026-09-04）：單元裡**任何一段**是這輪進來的，整個單元就算
            # 新一輪——側錄常是「同一段連線這輪又多錄了幾個 TC」，只認第一段
            # 會讓這輪真的有新內容的單元漏在篩選外。
            if r.get("fresh"):
                cur["fresh"] = r.get("fresh")
            if not cur.get("tc_id") and _has(r):
                cur["tc_id"] = r.get("id")
            continue
        if cur:
            out.append(cur)
        cur, curkey = dict(r), k
        cur["segs"] = 1
        cur["tc_id"] = r.get("id") if _has(r) else None
    if cur:
        out.append(cur)
    return out


def stats_line(rows):
    """檔頭則數行。2026-08-23 D1：側錄計入總則數，並在括號裡分列。
    分列的 AP/RT/NS 數字原封保留，三站清單對帳依據不受影響。"""
    n_side = sum(1 for r in rows if r.get("kind") == "side")
    by = {}
    for r in rows:
        if r.get("kind") == "side":
            continue
        src = r.get("src") or "?"
        if src in ("CNN", "CNN_newsource"):
            src = "NS"
        by[src] = by.get(src, 0) + 1
    order = ["AP", "RT", "NS"]
    head = [f"{s} {by[s]}則" for s in order if by.get(s)]
    other = sum(v for k, v in by.items() if k not in order)
    if other:
        head.append(f"其他 {other}則")
    if n_side:
        head.append(f"側錄 {n_side}則")
    return f"收錄外電共 {len(rows)} 則（{'／'.join(head)}）"


def build_html(state, base_mmdd, window, datebar_html=""):
    """跟 `s2_render_html.build_html()` **同一組參數**，可直接替換。

    datebar_html 由呼叫端算好傳進來（⛔ 不要在這裡自己算——2026-08-11 就是
    因為排程那條路沒帶 datebar，歷史列從來沒生效過）。
    """
    head = H.build_header(state, base_mmdd, window)
    title = head[0] if head else f"{base_mmdd} 晚班交接"
    window_line = head[1] if len(head) > 1 else window

    # 檔頭其餘各行（標記說明、🔴 重大提醒）。
    # 🔴 head[2] 是「收錄外電共 N 則」，本頁改用 stats_line() 自己算（D1：側錄計入
    #    總則數），所以跳過它以免同一個數字出現兩次、還可能不一致。
    # 🔴 重大提醒必須跳出來——那是編輯最需要一眼看到的東西。
    #    比照 s2_render_html.build_html()：先整段 escape，再把 🔴 那幾行包上 .alert。
    # 🔴 「標記：△=… 🔴=… 🟡=…」也不進網頁（2026-08-25 使用者要求）：那些符號
    #    在列上本來就看得到，側欄還能篩。⛔ TXT 版照舊——那份要能單獨貼給人看。
    meta_lines = [h for i, h in enumerate(head)
                  if i >= 2 and not h.startswith("收錄外電共")
                  and not h.startswith("標記：")]
    meta_html = _html.escape("\n".join(meta_lines))
    for a in (h for h in meta_lines if h.startswith("🔴")):
        meta_html = meta_html.replace(_html.escape(a),
                                      f'<span class="alert">{_html.escape(a)}</span>')

    raw = [r for r in H.collect(state, base_mmdd) if r.get("kind") != "empty"]
    stored = stored_tc(state)
    rows = fold_side(raw, stored)

    out = []
    for r in rows:
        T, C, flags, tcsrc = join_tc(r, stored)
        out.append({
            "id": r.get("id") or "", "big": r.get("big") or "",
            "mid": r.get("mid") or "", "sub": r.get("sub") or "",
            "src": r.get("src") or "", "kind": r.get("kind") or "",
            "mark": r.get("mark") or "", "alert": r.get("alert") or "",
            "hilite": r.get("hilite") or "", "fresh": r.get("fresh") or "",
            "text": r.get("text") or "",
            "preview": BASE.slim_text(r.get("text") or ""),
            "segs": r.get("segs") or 1,
            "q": (r.get("q") or "")[:400],
            "T": T, "C": C, "flags": flags, "tcsrc": tcsrc,
        })

    # 「未分類」只在**真的有**的時候才加進這一頁的顯示清單——沒有就不要多一列空格子。
    # ⚠️ 只影響本頁顯示，`TC-字典.md`（已裁決的權威名單）不動。
    # 機動 T 排在固定 12 類**之前**（比照大分類機動格在第一格）。
    # active 的一律顯示；retired 的只在本頁真的有素材掛著時才留一格——
    # ⛔ 不能因為退場就抽掉，那些素材會無格可放（同墨西哥併桶時踩到的形狀）。
    _sp_active, _sp_all = load_special_t()
    _used = {x for r in out for x in r["T"]}
    t_list = [(x["name"], "📌") for x in _sp_all
              if x.get("name") and (x["name"] in _sp_active or x["name"] in _used)]
    t_list += list(BASE.T_FIXED)
    c_list = list(BASE.C_FIXED)
    c_fb = dict(BASE.C_FALLBACK)
    if any(UNKNOWN in r["T"] for r in out):
        t_list.append((UNKNOWN, "❓"))
    if any(UNKNOWN in r["C"] for r in out):
        c_list.append((UNKNOWN, ""))
        c_fb[UNKNOWN] = "❓"

    # LOGO 抓不到就整塊不輸出（而不是留一個 src="" 的破圖）。
    # %%EXEC_URL%% 佔位由 Apps Script doGet() 換成部署固定網址；target="_top" 是因為
    # /exec 頁面最上層在 Google 沙盒網域，相對連結會解析到那層，必須用絕對網址跳出 iframe。
    uri = H.logo_data_uri()
    logo_html = (f'<a class="brand" href="%%EXEC_URL%%" target="_top" '
                 f'title="回到今天的晚班交接"><img src="{uri}" alt="Miniverse" '
                 f'width="80" height="80" loading="lazy"></a>') if uri else ""

    tpl = open(TPL, encoding="utf-8").read()
    return (tpl
            .replace("__DATA__", json.dumps(out, ensure_ascii=False))
            .replace("__T__", json.dumps(t_list, ensure_ascii=False))
            .replace("__C__", json.dumps(c_list, ensure_ascii=False))
            .replace("__C_FALLBACK__", json.dumps(c_fb, ensure_ascii=False))
            .replace("__FLAGS__", json.dumps(BASE.FLAGS, ensure_ascii=False))
            .replace("__TITLE__", title)
            .replace("__WINDOW__", window_line)
            .replace("__STATS__", stats_line(rows))
            .replace("__META__", meta_html)
            .replace("__LOGO__", logo_html)
            # 產出時間戳。⚠️ 用本機時間、格式固定 "%Y-%m-%d %H:%M"——前端拿它算
            # 「幾小時前」並在超過 3.5 小時時變紅（Apps Script 會無聲退回昨天那份，
            # 沒有這個示警編輯會照舊清單發稿）。跟 s2_render_html.py:786 同一套。
            .replace("__BUILT__", datetime.now().strftime("%Y-%m-%d %H:%M"))
            # 本輪 checkpoint（側欄「只看新一輪」的標籤）。判定本身在
            # H.collect() 就做完了（row 的 fresh 欄位），這裡只帶顯示字串。
            .replace("__FRESH_CP__",
                     json.dumps(H.fresh_label(H.fresh_info(state, base_mmdd)[1]),
                                ensure_ascii=False))
            .replace("__HISTPILLS__", datebar_html))


def tc_stats(state, base_mmdd):
    """驗收用：回傳 (總則數, 已存, 半存, 兜底, 與 tag_tc 相異的 id 清單)。"""
    raw = [r for r in H.collect(state, base_mmdd) if r.get("kind") != "empty"]
    stored = stored_tc(state)
    rows = fold_side(raw, stored)
    n_stored = n_mixed = 0
    diff = []
    for r in rows:
        T, C, _, src = join_tc(r, stored)
        if src == "stored":
            n_stored += 1
        elif src == "mixed":
            n_mixed += 1
        if src != "heur":
            hT, hC, _ = tag_tc(r)
            if sorted(T) != sorted(hT) or sorted(C) != sorted(hC):
                diff.append(r.get("id"))
    return len(rows), n_stored, n_mixed, len(rows) - n_stored - n_mixed, diff
