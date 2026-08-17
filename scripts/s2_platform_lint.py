#!/usr/bin/env python3
"""s2_platform_lint.py — ENEX／ABC 候選檔交件前的格式與結構 lint（MASTER A9 子項⑥）。

🔴 **為什麼需要這支**：`common/18-交換平台素材整併.md` §4 那張格式表目前只能靠
agent「寫完自己對一遍」，0810 那批品質掃 38 個 HIT 裡 **ABC 佔 12、ENEX 佔 3**，
集中在「缺 ▎畫面：」「行尾掛時間碼」「摘要超 150 字」三種——而這些全都是等素材被
吃進**正式狀態檔之後**才由 `s2_validate.py` 抓到的。這支把同一套判準往前挪到
**候選檔交件的當下**，那時候修最便宜。

⚠️ **獨立流程，不併入三站掃帶輪**（2026-08-18 使用者訂）：本腳本不被 `s2_scan.ps1`
呼叫、不碰正式狀態檔、不寫任何東西，只讀候選檔並印報告。

⛔ **不做第二套 parser**：素材行判準一律轉呼 `s2_validate.check_entry()`（＝三站與
render 用的同一套）。本檔只加**候選檔階段特有**、`check_entry` 管不到的檢查：
  - 行首時段標記（`check_entry` 會先 `strip_mark` 剝掉，違規反而看不見，見 `_mark_issue`）
  - 候選 JSON 的結構與交叉一致性（id ↔ 站別欄位 ↔ raw_entry 行首）
  - 兩站的時長規則相反（ABC 必帶 `▎MM:SS`／ENEX 一律留白）

**分級**：❌＝交件前必修（§4 格式表＋結構錯、缺 `src_text`）；⚠️＝提醒（counts 對不上、
成對 txt 不在等）。`src_text` 自 2026-08-18 起是 18 檔 §2 的必帶欄位（A9 子項⑧ 落地），
所以由 ⚠️ 升為 ❌；**規則生效前交的舊候選檔**要跑本工具時帶 `--allow-missing-src-text`
降回 ⚠️。

離開碼：0＝通過（可能有 ⚠️）｜1＝有 ❌｜**2＝讀不到／檔壞（不是「沒問題」）**。

用法：
    python scripts/s2_platform_lint.py "…\\_待整併\\0818-ABC-state.json"
    python scripts/s2_platform_lint.py 舊候選.json --allow-missing-src-text
"""
import argparse
import importlib.util
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

# 🔴 這台機器的 python stdout 預設是 **cp950**（實測 `print('⛔')` 直接
# UnicodeEncodeError）。本檔的訊息全是中文＋⛔⚠️❌，不重設編碼的話，
# agent 在裸 PowerShell 一跑就炸——工具會直接被放棄（D9 那個「摩擦一大就彈回
# ad-hoc python」的形狀）。⛔ 不要改成叫使用者自己設 PYTHONIOENCODING。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass          # 被重導向到不支援 reconfigure 的物件時照舊，不擋執行

# 時段標記：18 檔 §2 只列了 △▲■◆ 四個，但 `s2_state.py set-mark` 的 choices 有五個
# （多一個舊符號 ●），候選檔若寫了 ● 一樣會在 render 時變成兩個標記，一併擋。
MARKS = "△▲■◆●"
CODE_RE = {"ENEX": re.compile(r"^ENEX\d{4,8}$"), "ABC": re.compile(r"^ABC\d{6,16}$")}
DUR_RE = re.compile(r"▎\d{1,3}:\d{2}\s*$")
CKPT_RE = re.compile(r"^\d{4}-\d{4}$")
# 分類名不能帶這三個字元：`set-category --pairs` 用 `;` 分筆、`=` 分 id、`/` 分層級，
# 混進去會被切成假的小分題（護欄：錯誤要帶原始值明確失敗，不是靜默切壞）。
BAD_CAT_CHARS = ";=/"
REQUIRED_TOP = ("window_start", "window_end", "checkpoint", "source",
                "merged_into_handover", "reviewed", "counts", "items")
REQUIRED_ITEM = ("id", "source", "first_seen_checkpoint", "script_status",
                 "raw_entry", "category")


def load_validate():
    """載入 `s2_validate.py`（素材行判準的唯一來源）。載不到就明確失敗，不靜默略過。"""
    spec = importlib.util.spec_from_file_location(
        "s2_validate", os.path.join(HERE, "s2_validate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mark_issue(entry):
    """行首時段標記檢查——**必須在轉呼 check_entry 之前自己做**。

    `check_entry()` 第一件事就是 `strip_mark()`，違規自帶的 `△▲■◆●` 會被剝乾淨後
    照常通過檢查，等於這條規則在下游完全看不見。18 檔 §2 明寫 render 依收錄時間
    自動補標記，候選檔自己寫了就會變成兩個。
    """
    first = (entry or "").strip().split("\n")[0]
    if first[:1] in MARKS:
        return f"raw_entry 自帶時段標記「{first[:1]}」（render 會再補一個，18 檔 §2）"
    return None


def lint(path, allow_missing_src=False):
    """回傳 (errors, warns)。讀不到／JSON 壞直接丟 SystemExit(2)。"""
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        # 護欄：錯誤帶原始訊息，不回單一 boolean
        raise SystemExit(f"⛔ 候選檔讀取失敗（{e}）\n   檔案：{path}")
    if not isinstance(data, dict):
        raise SystemExit(f"⛔ 候選檔頂層應為物件，實得 {type(data).__name__}\n   檔案：{path}")

    err, warn = [], []
    va = load_validate()

    missing = [k for k in REQUIRED_TOP if k not in data]
    if missing:
        err.append(f"頂層缺欄位：{'、'.join(missing)}（18 檔 §2）")
    for k in ("skipped", "needs_review", "known_gaps"):
        if k not in data:
            warn.append(f"頂層缺 `{k}`（18 檔 §2 的形狀有這個鍵，空的也要給空陣列）")

    site = data.get("source")
    if site not in ("ENEX", "ABC"):
        err.append(f"頂層 source 應為 ENEX／ABC，實得 {site!r}")
    ckpt = data.get("checkpoint")
    if ckpt is not None and not CKPT_RE.match(str(ckpt)):
        err.append(f"checkpoint 格式應為 MMDD-HHMM，實得 {ckpt!r}")
    for flag in ("merged_into_handover", "reviewed"):
        if data.get(flag) not in (False, True):
            err.append(f"{flag} 應為布林，實得 {data.get(flag)!r}")
        elif data.get(flag) is True:
            warn.append(f"{flag}=true——這份候選檔已被整併過，"
                        f"交件當下一律給 false（18 檔 §2）")

    items = data.get("items")
    if not isinstance(items, list):
        err.append(f"items 應為陣列，實得 {type(items).__name__}")
        items = []
    elif not items:
        warn.append("items 是空的（掃了一輪一則都沒收？確認不是抽取整段失敗）")

    seen = {}
    for n, it in enumerate(items, 1):
        if not isinstance(it, dict):
            err.append(f"第{n}筆不是物件")
            continue
        ident = it.get("id") or f"第{n}筆"
        for k in [k for k in REQUIRED_ITEM if not it.get(k)]:
            err.append(f"{ident}: 缺 `{k}`")
        i = str(it.get("id") or "")
        if i:
            if i in seen:
                err.append(f"{i}: id 重複（另一筆在第{seen[i]}筆）")
            else:
                seen[i] = n
        if site in CODE_RE and i and not CODE_RE[site].match(i):
            err.append(f"{ident}: id 不符 {site} 代碼格式（18 檔 §3）")
        if it.get("source") and it["source"] != site:
            err.append(f"{ident}: item.source={it['source']!r} 與頂層 source={site!r} 不一致")
        if it.get("script_status") not in (None, "has_script", "pending"):
            err.append(f"{ident}: script_status 須為 has_script／pending，"
                       f"實得 {it['script_status']!r}")
        err += _check_ids(site, ident, i, it)
        err += _check_category(ident, it.get("category"), warn)
        entry = it.get("raw_entry")
        if isinstance(entry, str) and entry.strip():
            err += _check_entry_line(va, site, ident, i, entry)
        elif entry is not None and not isinstance(entry, str):
            err.append(f"{ident}: raw_entry 須為字串，實得 {type(entry).__name__}")
        if "sb_count" in it and not isinstance(it["sb_count"], int):
            err.append(f"{ident}: sb_count 須為整數，實得 {it['sb_count']!r}")
        err += _check_src_text(ident, it, allow_missing_src, warn)

    warn += _check_counts(data, items)
    warn += _check_txt_pair(path, seen)
    return err, warn


def _check_src_text(ident, it, allow_missing, warn):
    """`src_text` ＝**站方原文**，18 檔 §2 自 2026-08-18 起列為必帶欄位（A9 子項⑧）。

    三站已經用實錯換過這個教訓：0804 回頭查 BITE 誤判時，RT 有 4 則、AP 有 9 則
    已經捲出 API 翻頁範圍，**永遠查不回來**——素材被推出清單就無法回溯。
    ⛔ 內容只准站方原文：RT4131 就是 agent 在原文尾巴接了一段中文說明，裡面的
    `SHOTLIST`／`SOUNDBITE` 字樣害同一則誤報連續四輪（13b §543）。
    """
    out = []
    src = it.get("src_text")
    if not src:
        msg = (f"{ident}: 缺 `src_text`（站方原文＝事後離線查證的唯一依據，18 檔 §2）")
        if allow_missing:
            warn.append(msg + "——已用 --allow-missing-src-text 降級")
        else:
            out.append(msg)
        return out
    if not isinstance(src, str):
        return [f"{ident}: src_text 須為字串，實得 {type(src).__name__}"]
    entry = str(it.get("raw_entry") or "").strip()
    if entry and src.strip() == entry:
        # 拿成品素材行充數＝完全失去查證價值（要比對的正是「原文 vs 我寫的摘要」）
        out.append(f"{ident}: src_text 與 raw_entry 一字不差——那是自己寫的摘要，"
                   f"不是站方原文")
    elif len(src.strip()) < 50:
        warn.append(f"{ident}: src_text 只有 {len(src.strip())} 字，"
                    f"確認不是只貼了標題（瘦身後單則通常 1KB 起跳）")
    return out


def _check_ids(site, ident, i, it):
    """交叉一致性：id 必須等於站別欄位裡的原始編號拼出來的值。

    這是最便宜的真錯偵測——0817 兩份真實候選檔兩邊都對得上，一旦對不上就代表
    抽取時張冠李戴（ABC 尤其危險：`/Delivery/Detail/{id}` 是投遞紀錄 id，不是
    Story Number，18 檔 §3 明列的地雷）。
    """
    out = []
    if site == "ENEX":
        raw = (it.get("enex") or {}).get("itemId")
        if raw and i and i != f"ENEX{raw}":
            out.append(f"{ident}: id 與 enex.itemId 對不上（{i} vs ENEX{raw}）")
    elif site == "ABC":
        abc = it.get("abc") or {}
        raw = abc.get("storyNumber")
        if raw and i and i != f"ABC{raw}":
            out.append(f"{ident}: id 與 abc.storyNumber 對不上（{i} vs ABC{raw}）")
        if i and CODE_RE["ABC"].match(i):
            mmddyy = i[3:9]
            try:
                datetime.strptime(mmddyy, "%m%d%y")
            except ValueError:
                out.append(f"{ident}: Story Number 前 6 碼 {mmddyy} 不是合法 MMDDYY 日期"
                           f"（18 檔 §3；抓錯欄位時最常見的形狀）")
    return out


def _check_category(ident, cat, warn):
    out = []
    if cat is None:
        warn.append(f"{ident}: category 是 null（整併時不會有分類，得事後補 set-category）")
        return out
    if not isinstance(cat, dict):
        out.append(f"{ident}: category 須為物件，實得 {type(cat).__name__}")
        return out
    for k in ("大分類", "中主題"):
        if not str(cat.get(k) or "").strip():
            out.append(f"{ident}: category 缺 `{k}`")
    for k in ("大分類", "中主題", "小分題"):
        v = str(cat.get(k) or "")
        bad = [c for c in BAD_CAT_CHARS if c in v]
        if bad:
            out.append(f"{ident}: category.{k} 含 {'／'.join(bad)}——"
                       f"set-category --pairs 會被切錯（原值：{v}）")
    return out


def _check_entry_line(va, site, ident, i, entry):
    out = []
    m = _mark_issue(entry)
    if m:
        out.append(f"{ident}: {m}")
    first = entry.strip().split("\n")[0]
    head = first.lstrip(MARKS).strip().split(" ", 1)[0]
    if i and head != i:
        out.append(f"{ident}: raw_entry 行首代碼是 {head!r}，與 id 不符")
    if "▎URL：" in first or "▎URL:" in first:
        out.append(f"{ident}: 寫了 ▎URL：（兩站都不寫，18 檔 §4）")
    has_dur = bool(DUR_RE.search(first))
    if site == "ABC" and not has_dur:
        out.append(f"{ident}: ABC 一律帶 ▎MM:SS 收尾（清單 Length 欄，18 檔 §4）")
    if site == "ENEX" and has_dur:
        out.append(f"{ident}: ENEX 目前抓不到時長，一律留白，"
                   f"⛔ 不要編數字或佔位（18 檔 §4）")
    # §4 表的其餘各項（缺 ▎畫面：、摘要 150 字、(BITE) 一致性、行尾多餘內容…）
    # 全部交給三站同一套 check_entry，這裡不重寫判準。
    out += [f"{ident}: {r}" for r in va.check_entry(first)]
    return out


def _check_counts(data, items):
    """counts 只給 ⚠️：它是 agent 自己宣稱的數字，本來就沒有第二層驗證
    （A9 子項④ 才是真解）；但「收錄 ≠ len(items)」這種自我矛盾當場就抓得出來。"""
    out = []
    c = data.get("counts")
    if not isinstance(c, dict):
        return [f"counts 應為物件，實得 {type(c).__name__}"] if c is not None else out
    got = {k: c.get(k) for k in ("掃描", "收錄", "排除")}
    if any(v is None for v in got.values()):
        out.append(f"counts 缺鍵（應有 掃描／收錄／排除，實得 {list(c)}）")
        return out
    if got["收錄"] != len(items):
        out.append(f"counts.收錄={got['收錄']} 與 items 筆數 {len(items)} 對不上")
    skipped = data.get("skipped")
    if isinstance(skipped, list) and got["排除"] != len(skipped):
        out.append(f"counts.排除={got['排除']} 與 skipped 筆數 {len(skipped)} 對不上")
    if got["掃描"] != got["收錄"] + got["排除"]:
        out.append(f"counts 掃描{got['掃描']} ≠ 收錄{got['收錄']}＋排除{got['排除']}"
                   f"（差 {got['掃描'] - got['收錄'] - got['排除']} 則；"
                   f"若是刻意的請寫進 known_gaps）")
    return out


def _check_txt_pair(path, ids):
    """18 檔 §2：`.txt`（人看的）與 `-state.json`（機器讀的）**兩份都要出**。"""
    out = []
    base = os.path.basename(path)
    if not base.endswith("-state.json"):
        return out
    txt = os.path.join(os.path.dirname(path), base[:-len("-state.json")] + ".txt")
    if not os.path.exists(txt):
        return [f"找不到成對的 {os.path.basename(txt)}（只出 json 會逼整併端重新剖析文字）"]
    try:
        body = open(txt, encoding="utf-8-sig").read()
    except OSError as e:
        return [f"成對 txt 讀取失敗（{e}）"]
    missing = [i for i in ids if i not in body]
    if missing:
        out.append(f"txt 裡找不到 {len(missing)} 個 id："
                   f"{'、'.join(missing[:5])}{' …' if len(missing) > 5 else ''}")
    return out


def main():
    ap = argparse.ArgumentParser(
        description="ENEX／ABC 候選檔交件前 lint（獨立流程，不碰正式狀態檔）")
    ap.add_argument("candidate", help="候選檔 {MMDD}-{站}-state.json")
    ap.add_argument("--allow-missing-src-text", action="store_true",
                    help="把「缺 src_text」降回 ⚠️（只給 2026-08-18 規則生效前交的舊候選檔）")
    args = ap.parse_args()

    err, warn = lint(args.candidate, args.allow_missing_src_text)
    print(f"候選檔：{args.candidate}")
    if err:
        print(f"\n❌ 交件前必修 {len(err)} 項：")
        print("\n".join("  " + x for x in err))
    if warn:
        print(f"\n⚠️ 提醒 {len(warn)} 項：")
        print("\n".join("  " + x for x in warn))
    if not err and not warn:
        print("✅ 乾淨：結構、交叉一致性、§4 格式表全數通過")
    elif not err:
        print(f"\n✅ 無必修項（{len(warn)} 項提醒不擋交件）")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
