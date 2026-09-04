# -*- coding: utf-8 -*-
"""S2 每輪快速稽核——**另一個 agent 用一道指令抓漏、抓誤判**（2026-08-06 上線）。

    python scripts/s2_audit.py --mmdd 0805

為什麼需要：0805–0806 那一夜，**每一個問題都是事後才發現的，當輪 agent 全部
回報「正常完成」**——RT 漏收 36 則＋11 則、NS 漏 5 則、時段標記錯 85 則、
AP 假 BITE 7 則、中主題 92→62。共同形狀是**當輪 agent 看不見自己的盲區**：
它按規則做了、也覺得做完了，但規則有洞或視野被縮小。**只有換一雙眼睛才看得到。**

⚡ **①–⑦ 全部離線**：只讀狀態檔與當晚暫存檔，零瀏覽器呼叫、數秒跑完。
Ⓐ **清單對帳**要一份 agent 剛撈的清單快照（`--rt-list` 等）——**稽核的時機
必然是掃帶剛結束、Playwright 正好空著**，所以這一項做得到，別跳過：
它是價值最高的檢查（0805 靠它抓到 47 則漏收）。
⚠️ 這正是 `src_text`／`_rt_list_{HHMM}.json` 落檔規則存在的理由——
沒有那兩份，稽核就得重開瀏覽器，成本差一個數量級。

離開碼：0＝全過；1＝有 🔴（要處理）；🟡 提醒不影響離開碼。
"""
import argparse
import collections
import glob
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_state as S      # noqa: E402
import s2_render as R     # noqa: E402
import s2_validate as sv  # noqa: E402
import s2_parse as sp     # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

BASE = os.path.dirname(S.DEFAULT_FILE)
RED, YEL = [], []
AUDIT_ARGS = None


def red(msg):
    RED.append(msg)
    print(f"  🔴 {msg}")


def yel(msg):
    YEL.append(msg)
    print(f"  🟡 {msg}")


def ok(msg):
    print(f"  ✅ {msg}")


def sec(title):
    print(f"\n── {title} " + "─" * max(0, 56 - len(title) * 2))


def more_note(total, shown, unit="則", bare=False):
    """R8（2026-08-13）：清單超過顯示上限時補「還有 N 未列出」，跟 ④ 既有寫法
    （384d9de）保持一致——只列前幾筆又不提示還有更多，人工／agent 照著顯示的
    修完就以為修好了，其實還有沒被看到的那幾筆（0812-1600 的教訓）。
    total<=shown 時回傳空字串；`bare=True` 給已經包在自家括號裡的訊息用
    （不再套一層括號，改成逗號接的短句），其餘情形回傳帶括號的獨立提示。
    """
    if total <= shown:
        return ""
    n = total - shown
    return f"，其餘 {n} {unit}未列出" if bare else f"（還有 {n} {unit}未列出）"


def split_logged(items, ids):
    """把已在 needs_review 留痕（且未結案）的 id 從一批問題 id 裡篩掉。

    去重不另建 fingerprint 檔——`needs_review` 欄位本身就是留痕：`needs-review add`
    寫入、`needs-review done` 才會 pop 掉。同一則同一類問題只要留痕還在，就不再
    重複列 🔴，改成集中一行 🟡「已留痕待人工」；結案後問題若還在，下一輪自動恢復紅燈
    （因為 needs_review 已被清空，id 會回到「仍紅」那一邊）。

    回傳 (仍紅, 已留痕)，兩份都是原本傳入的 id list 的子集，順序不變。
    """
    still, logged = [], []
    for i in ids:
        if (items.get(i) or {}).get("needs_review"):
            logged.append(i)
        else:
            still.append(i)
    return still, logged



def _norm_snapshot_ts(t):
    """快照時間戳正規化成本地 `MM/DD/YYYY HH:MM`。

    0814-0100 實錯：R6 之後 agent 用 API 撈 AP 清單，時間欄是 ISO UTC
    （`2026-08-13T17:07:29Z`＝台北 0814 01:07）。不轉時區的話 `_hhmm`
    會把 17:07 當本地時間、`_list_mmdd` 把日期算成 0813——窗判斷與
    跨日判斷雙雙全錯。非 ISO 格式（本來的 MM/DD/YYYY、純 HH:MM）原樣回傳。
    """
    m = re.match(
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)(Z|[+-]\d{2}:?\d{2})?$",
        (t or "").strip())
    if not m:
        return t
    try:
        dt = datetime.fromisoformat((t or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return t
    if dt.tzinfo is not None:
        dt = dt.astimezone()          # UTC／帶時區 → 本機時區（台北）
    return dt.strftime("%m/%d/%Y %H:%M")


def parse_list_file(path):
    """讀 agent 撈回來的清單快照。三種格式都吃：

    ① 純文字，每行 `CODE|MM/DD/YYYY HH:MM` 或 `CODE|HH:MM`（多餘欄位忽略）
    ②' 純文字 tab 分隔，每行 `CODE\\tFT\\tISO時間\\t標題…`（0814-0100 起
       agent 走 API 撈清單的實際落地格式；`total:N` 表頭行跳過）
    ② JSON 陣列，每筆 {"code": "...", "at": "..."}／{"id": ..., "time": ...}

    時間欄一律過 `_norm_snapshot_ts()`（ISO UTC → 本地 MM/DD/YYYY HH:MM）。
    """
    raw = open(path, encoding="utf-8-sig").read().strip()
    rows = []
    if raw.startswith(("[", "{", '"')):
        data = json.loads(raw)
        # ⚠️ 實際落地的 `_rt_list_{HHMM}.json` 是**雙層編碼**的（整包 JSON 又被
        # json.dumps 成一個字串），外層還包了 {"count":N,"items":[…]}。0806 實測
        # 才發現——原本只認純陣列，遇到真檔會把**整個檔當成一筆**，然後印出
        # 「清單 1 則」還一路 ✅ 過去。**對帳報 ✅ 卻其實沒對到，比不對帳更危險。**
        for _ in range(3):                       # 最多剝三層字串
            if isinstance(data, str):
                data = json.loads(data)
            else:
                break
        if isinstance(data, dict):
            data = data.get("items") or data.get("list") or data.get("rows") or []
        for it in data if isinstance(data, list) else []:
            if isinstance(it, str):              # 只有代碼、沒有時間
                rows.append((it.strip(), ""))
                continue
            c = it.get("code") or it.get("id") or ""
            t = it.get("at") or it.get("time") or ""
            if c:
                rows.append((c.strip(), _norm_snapshot_ts(str(t))))
    else:
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            if re.match(r"^total\s*[:=]\s*\d+$", line, re.IGNORECASE):
                continue                      # tab 格式的表頭行，不是素材
            sep = "|" if "|" in line else "\t"
            parts = [x.strip() for x in line.split(sep)]
            if not parts[0]:
                continue
            # 時間欄不固定在第 2 欄（tab 格式是 CODE、FT、時間、標題）——
            # 取第一個「看得出時間」的欄位，找不到就空字串維持舊行為。
            t = next((f for f in parts[1:] if re.search(r"\d{1,2}:\d{2}", f)), "")
            rows.append((parts[0], _norm_snapshot_ts(t)))
    return rows


def _hhmm(t):
    m = re.search(r"(\d{1,2}):(\d{2})", t or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _cp_mmdd(cp):
    """checkpoint（`{MMDD}-{HHMM}`）開頭的 4 位數字 → 'MMDD' 字串，抓不到回 None。"""
    m = re.match(r"(\d{4})", cp or "")
    return m.group(1) if m else None


def _list_mmdd(t):
    """清單快照時間戳（`MM/DD/YYYY HH:MM`）裡的日期 → 'MMDD' 字串。
    只有 `HH:MM`（沒有日期）的舊格式抓不到，回 None——這種格式判不出跨日撞號。"""
    m = re.search(r"(\d{1,2})/(\d{1,2})/\d{4}", t or "")
    if not m:
        return None
    return f"{int(m.group(1)):02d}{int(m.group(2)):02d}"


def _first_seen_index(cur_items, archive_glob):
    """id → 目前已知最新的 first_seen 'MMDD'（跨當前檔＋Archive 彙整，同 id 取較新日期）。
    只用來判斷「站方清單這筆的日期是不是比我們收過的還新」，不是精確歷史記錄。"""
    idx = {}

    def feed(items):
        for k, v in items.items():
            fs = _cp_mmdd(v.get("first_seen_checkpoint"))
            if fs and (k not in idx or fs > idx[k]):
                idx[k] = fs

    feed(cur_items)
    for f in glob.glob(archive_glob, recursive=True):
        try:
            feed(S.load(f)["items"])
        except Exception:
            pass
    return idx


def reconcile(st, mmdd, path, label):
    """清單 vs 狀態檔對帳：算出**窗內該收而未收**的。"""
    rows = parse_list_file(path)
    cur = set(st["items"])
    archive_glob = os.path.join(BASE, "Archive", "**", "[01]*-s2-state.json")
    prev = set()
    for f in glob.glob(archive_glob, recursive=True):
        try:
            prev |= set(S.load(f)["items"])
        except Exception:
            pass
    prev -= cur

    # R2（2026-08-13）：RT 的 Edit No 會跨日重複使用，同 id 不等於同一則素材。
    # 原本 prev/cur 只看 id 有沒有出現過——昨天收過 RT3609、今天站方又出一個全新的
    # RT3609，會被當成「前幾天收過」（或「已收」）**靜默吞掉**。這裡只對 RT 開這條路
    # （NS／AP 的 id 不重複使用，不動）：清單快照這筆的日期比我們收過的 first_seen
    # 晚一天以上 → 視為新素材，不算「前幾天收過」，照樣走窗內漏收判斷＋⚠️ 跨日同號。
    # 清單快照沒帶日期（舊版純 `HH:MM`）判不出跨日，維持原行為並提醒改善清單格式。
    cross_day, cross_day_seen = set(), set()
    if label == "RT":
        has_dates = any(_list_mmdd(t) for _, t in rows)
        if has_dates:
            fs_idx = _first_seen_index(st["items"], archive_glob)
            for code, t in rows:
                ld = _list_mmdd(t)
                fs = fs_idx.get(code)
                if ld and fs and ld > fs:
                    (cross_day_seen if code in cur else cross_day).add(code)
        elif rows:
            yel(f"{label} 清單快照沒有日期（純 HH:MM）——跳過跨日同號判斷，"
                f"Edit No 撞號時可能靜默漏收；清單改存 `CODE|MM/DD/YYYY HH:MM` 才驗得出來")

    # 窗：window_start → 目前 checkpoint（都取 HH:MM，跨夜用 +24h 折算）
    ws = _hhmm(st["_top"].get("window_start") or "")
    _d, end = R.checkpoint_time(st["_top"].get("checkpoint"), mmdd)
    we = (end // 100 * 60 + end % 100) if end is not None else None
    if we is not None and ws is not None and we < ws:
        we += 1440

    def norm(t):
        v = _hhmm(t)
        if v is None or ws is None:
            return v
        return v + 1440 if v < ws else v      # 跨夜：小於起點的算隔天

    # 已在 needs-review 裁定過「不收／重複／排除」的，不再報成漏收。
    # ⚠️ 0806 實況：RT3426／RT3551 裁定不收後，每一輪稽核都照樣報 🔴，agent 得
    # 每次解釋一遍「非新問題」。**重複誤報會把警告訓練成雜訊**，那比不報還糟。
    # 代價很低：要讓它閉嘴就得寫 needs-review——正好就是我們要的留痕紀律。
    ruled = set()
    for k, v in st["items"].items():
        note = v.get("needs_review")
        if not isinstance(note, str) or not any(
                w in note for w in ("不收", "重複", "排除", "未收", "跳過")):
            continue
        for code, _t in rows:
            if code in note or code == k:
                ruled.add(code)

    # 跨日撞號的 code 不算「前幾天收過」——當作沒被 prev 蓋到，重新走窗內判斷。
    effective_prev = prev - cross_day

    got = [c for c, _t in rows if c in cur]
    old_ = [c for c, _t in rows if c not in cur and c in effective_prev]
    rest = [(c, t) for c, t in rows
            if c not in cur and c not in effective_prev and c not in ruled]

    def before_window(t):
        """0814-0100 實錯：窗判斷原本只看 HH:MM 不看日期——快照裡一則
        08/12 16:00 的舊素材（AP4678173）被當成本班（0813 起）窗內漏收。
        快照時間戳帶日期且早於班次日 → 開窗前的舊素材，不算窗內。
        跨夜（0814 凌晨）的日期 > 班次日，不受影響；跨年極端狀況與 R2
        同樣不處理（MMDD 字串比較的既知限制）。"""
        ld = _list_mmdd(t)
        return ld is not None and ld < mmdd

    inw = [(c, t) for c, t in rest if not before_window(t)
           and (ws is None or we is None
                or (norm(t) is not None and ws <= norm(t) <= we))]
    after = [(c, t) for c, t in rest if (c, t) not in inw]

    hit = sorted(c for c in ruled if c in {x for x, _ in rows} and c not in cur)
    print(f"     {label}：清單 {len(rows)}｜已收 {len(got)}｜前幾天收過 {len(old_)}"
          f"｜已裁定不收 {len(hit)}｜窗內未收 {len(inw)}｜窗外 {len(after)}")
    if hit:
        print(f"        （已裁定不收，不重複報：{'／'.join(hit[:8])}"
              f"{more_note(len(hit), 8, bare=True)}）")
    if cross_day:
        red(f"{label} 跨日同號 {len(cross_day)} 則（Edit No 跟舊素材撞號，但站方清單日期"
            f"較新，已視為新素材列入漏收判斷，不算靜默吞掉）：⚠️ " +
            "／".join(sorted(cross_day)[:12]) + more_note(len(cross_day), 12))
    if cross_day_seen:
        yel(f"{label} 跨日同號 {len(cross_day_seen)} 則但今天已收（同天內已在庫，非漏收，"
            f"僅提醒覆核是不是把新素材誤記到舊筆記錄上）：" +
            "／".join(sorted(cross_day_seen)[:12]) + more_note(len(cross_day_seen), 12))
    if inw:
        red(f"{label} 窗內漏收 {len(inw)} 則：" +
            "／".join(f"{c}({t[-5:]})" + ("⚠️跨日同號" if c in cross_day else "")
                      for c, t in inw[:12]) + more_note(len(inw), 12))
    else:
        ok(f"{label} 窗內零漏收")
    if after:
        print(f"        （窗外 {len(after)} 則屬下一輪，不算漏：" +
              "／".join(c for c, _t in after[:8]) +
              more_note(len(after), 8, bare=True) + "）")
    return {"list": len(rows), "got": len(got), "missing": len(inw),
            "missing_ids": [c for c, _t in inw[:20]], "cross_day": sorted(cross_day)}


def _log_reconcile(state_path, checkpoint, done):
    """把對帳結果寫回狀態檔，讓 render 查得到這一輪到底做了沒。

    ⚠️ 這是整條鏈的關鍵：0806 RT 漏收的根因不是不會做，是**做了一半就忘了回頭補**
    （10:41 那輪 agent 寫下「留待下次補做」，然後直接 render 收工）。留痕之後
    render 會在收工那一刻把沒對帳的輪次喊出來，而不是等別人事後查。
    """
    if not checkpoint or not done:
        return
    st = S.load(state_path)
    log = st["_top"].setdefault("reconcile_log", {})
    log.setdefault(checkpoint, {}).update(done)
    S.save(st, state_path)
    print(f"     📌 已記錄本輪對帳（{checkpoint}：{'／'.join(sorted(done))}）")


    # ── Ⓐ 三站清單對帳（給 --rt-list／--ap-list／--ns-list 就做）──────
def _find_list_snapshot(scratch, station):
    """本輪的清單快照是不是**已經躺在暫存夾裡**了？

    🔴 0901-2000 實錯：`_audit_rt_2000.txt` 明明已經產出來了，agent 下 `s2_audit.py`
    時卻只帶了 `--ap-list`／`--ns-list`，RT 就這樣沒進 reconcile_log，
    收工通知報「本輪沒留下清單對帳紀錄」。當時的提醒只說「補撈清單再跑一次」——
    可是根本不用補撈，檔就在那裡。指名檔案，把提醒變成一行可以直接貼的指令。
    """
    if not scratch or not os.path.isdir(scratch):
        return None
    s = station.lower()
    for pat in (f"_audit_{s}_*.txt", f"{s}_list_*.json", f"_{s}_list_*.json",
                f"{s}_timeline*.txt"):
        hits = glob.glob(os.path.join(scratch, pat))
        if hits:
            # 取**最後修改**的那個，不是檔名排序：同一站一天會留下好幾輪的快照
            # （`_audit_rt_1700.txt`／`_audit_rt_2000.txt`），而且還有 `_desc` 之類
            # 的變體，檔名排序挑不出「本輪那份」。
            return max(hits, key=os.path.getmtime)
    return None


def _reconcile_section(st, mmdd, args, state_path=None, scratch=None):
    sec("Ⓐ 清單對帳（最高價值：0805 靠它抓到 47 則漏收）")
    any_, done = False, {}
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    for opt, label in (("rt_list", "RT"), ("ap_list", "AP"), ("ns_list", "NS")):
        path = getattr(args, opt, None)
        if path:
            any_ = True
            if not os.path.exists(path):
                red(f"{label} 清單檔不存在：{path}")
            else:
                r = reconcile(st, mmdd, path, label)
                if r:
                    done[label] = dict(r, ts=ts)
    if done and state_path:
        _log_reconcile(state_path, st["_top"].get("checkpoint"), done)
    if any_ and len(done) < 3:
        missing = [s for s in ("RT", "AP", "NS") if s not in done]
        yel("三站只對了 " + ("／".join(sorted(done)) or "0 站") +
            f"——**缺 {'／'.join(missing)}**，缺的那幾站等於沒驗過，"
            f"收工通知會報「本輪沒留下清單對帳紀錄」")
        # 快照就在暫存夾的話，直接把指令拼給他，不要只喊「補撈」（0901-2000 實錯）
        opt = {"RT": "--rt-list", "AP": "--ap-list", "NS": "--ns-list"}
        found = [(s, _find_list_snapshot(scratch, s)) for s in missing]
        have = [(s, p) for s, p in found if p]
        if have:
            print("        ⭐ 這幾站的快照**已經在暫存夾裡**，不必重撈，直接補跑：")
            print(f"        python scripts/s2_audit.py --mmdd {mmdd} " +
                  " ".join(f'{opt[s]} "{p}"' for s, p in have))
        for s, p in found:
            if not p:
                print(f"        {s}：暫存夾裡找不到快照——若該站本輪整站進不去"
                      f"（登出／連不上），那是正常的，記進 needs-review 即可，不用補撈")
    if not any_:
        yel("沒給 --rt-list／--ap-list／--ns-list，**這一項沒做**——"
            "它是價值最高的檢查，別跳過")
        print("        做法：稽核時剛好是掃帶剛結束、Playwright 空著的時候。")
        print("        ① agent 撈各站清單（RT 見 13b §1b 第 3 條的容器捲動寫法）")
        print("        ② 存成每行 `CODE|MM/DD/YYYY HH:MM` 的純文字或 JSON 陣列")
        print("        ③ 重跑本模組並帶上 --rt-list <檔案>")
        print("        ⚠️ 開瀏覽器前先確認下一輪掃帶還沒開始，否則 Playwright 互鎖。")


def audit(mmdd, state_path, txt_path, scratch):
    st = S.load(state_path)
    items = st["items"]
    print(f"稽核 {mmdd}｜{len(items)} 則｜{os.path.basename(state_path)}")

    # ── ① checkpoint 格式 ──────────────────────────────────────────
    sec("① checkpoint 格式")
    bad_cp = collections.Counter()
    for v in items.values():
        cp = v.get("first_seen_checkpoint") or ""
        if cp and not re.search(r"\d{4}", cp):
            bad_cp[cp] += 1
    if bad_cp:
        red(f"{sum(bad_cp.values())} 則的 checkpoint 沒有 4 位數字群："
            f"{dict(bad_cp)}——mark_for() 判不出時段會退回預設 △（0806 實錯 85 則）。"
            f"格式應為 {{MMDD}}-{{HHMM}}；已入庫的用 set-mark 補救")
    else:
        ok("全部含 4 位數字群，時段可正確推算")

    # ── ② 時段標記 ────────────────────────────────────────────────
    # 🔴 2026-08-12 修過一次誤報：`mark_for()` 的規則是「跟建檔基準日同一天
    # （day==0，也就是 16:00～23:00 這段晚班）本來就固定回 △」，不是「同一天
    # 收太多則就可疑」。原本 `len(items) > 60` 這個判準完全沒對齊這條規則——
    # 0812-1600（剛建檔，window_start=13:00）66 則全部落在 day==0，全部 △
    # 是**設計上唯一可能的結果**，不是資料壞了；卻連續誤報 3 次逼 agent 花時間
    # 去讀 s2_state.py／s2_render.py 原始碼排查一個根本不存在的問題。
    # 真正該抓的是：**有 item 的 checkpoint 明明落在 day>=1（跨夜之後）卻標成 △**
    # ——那才是「checkpoint 格式認錯日期」的真實故障形狀。
    sec("② 時段標記")
    marks = collections.Counter()
    mis_tagged = []   # day>=1 卻仍是 △ 的異常項目：checkpoint 格式判日失敗的真訊號
    for k, v in items.items():
        # P0-3（2026-08-13）：`mark` 欄位若存在，就是 set-mark 寫死的合法 override
        # （見 s2_state.cmd_set_mark）——使用者／agent 已經人工判過該則實際屬哪個時段，
        # 不是 mark_for() 自動推算的。就算覆寫後的值剛好也是 △，那也是「人工判定
        # 就是 △」，不是「checkpoint 判日失敗、自動退回預設 △」，兩者形狀不同，
        # 不該混在一起報。只有**沒有 override、純靠 mark_for() 自動推算出 △**
        # 時才可能是判日失敗的訊號。
        explicit = v.get("mark") if v.get("mark") in ("△", "▲", "◇", "■", "◆", "●") else None
        mk = explicit if explicit is not None else R.mark_for(v.get("first_seen_checkpoint"), mmdd)
        marks[mk] += 1
        day, _ = R.checkpoint_time(v.get("first_seen_checkpoint"), mmdd)
        if day >= 1 and mk == "△" and explicit is None:
            mis_tagged.append(k)
    print(f"     分佈：{dict(marks)}")
    if mis_tagged:
        still_mt, logged_mt = split_logged(items, mis_tagged)
        if still_mt:
            red(f"{len(still_mt)} 則的 checkpoint 明明是隔天卻標成 △（checkpoint 格式判日失敗，見 ①）："
                + "／".join(still_mt[:10]) + more_note(len(still_mt), 10))
        if logged_mt:
            yel(f"已留痕待人工 {len(logged_mt)} 則（checkpoint 判日問題，略）："
                + "／".join(logged_mt[:10]) + more_note(len(logged_mt), 10))
    elif len(marks) == 1 and "△" in marks:
        ok("全部都是 △——本班還在同一天（16:00～23:00），這是 mark_for() 設計上唯一可能的結果，不是問題")
    else:
        ok("有多種時段標記，未見全部塌陷成 △")

    # ── ③ BITE 一致性 ─────────────────────────────────────────────
    sec("③ BITE 一致性（機械欄位取自 batch，判準文字取自狀態檔）")
    # ⚠️ batch 是**中間檔**、停在送出當下，事後修正不會回寫。0806 實錯：7 則 AP 假 BITE
    # 昨晚已在狀態檔改成「無BITE」，稽核卻照 batch 判成 🔴，逼人重查一次已經修好的東西。
    # 所以 sb_count／footage_type 這種**機械事實**才讀 batch（狀態檔沒存），
    # 「現在標成什麼」一律以**狀態檔**為準——那才是唯一真相源。
    cur_entry = {k: (v.get("raw_entry") or "") for k, v in items.items()}
    nb = collections.Counter()
    fake, missed, healed, polluted = [], [], [], []
    whole_missing = []   # R11（2026-08-13）：單一 batch 檔「整批」漏 src_text＝組批漏欄位
    for f in sorted(glob.glob(os.path.join(scratch, "*batch*.json"))):
        try:
            data = json.load(open(f, encoding="utf-8-sig"))
        except Exception:
            continue
        f_total = f_src = 0
        for e in data if isinstance(data, list) else []:
            was = e.get("entry", "")
            ent = cur_entry.get(e.get("id"), was)   # 狀態檔優先；已刪除的才退回 batch
            # sb_count 同樣狀態檔優先（2026-08-09）：batch 停在送出當下，素材由 pending
            # 轉正、站方 RESENDING 補完整稿之後 batch 的值就過期了，會對同一則**永久
            # 重複誤報**假 BITE（0809-0100 的 RT4098：batch 記 0，實際已有 5 個）。
            # 舊狀態檔沒有這個欄位，退回 batch 值，行為與過去一致。
            st_sb = (items.get(e.get("id")) or {}).get("sb_count")
            sb = st_sb if isinstance(st_sb, int) else e.get("sb_count")
            # 🎯 跟 add-batch 用同一把尺（2026-08-09 補）：`sb_count=0` 只有在
            # 「這份稿本來就會寫 SOUNDBITE」時才代表「沒有引言」，路透 captioned／
            # rough-cut 短片根本不寫，0 是**數不出來**。
            # ⚠️ 沒有這一段的話，入庫端修好了、稽核端還在報——RT4107／RT4131／RT4125
            # 就是這樣**連四輪**被重複命中，每一輪都要 agent 再查證、再寫一次備註。
            # **重複誤報會把警告訓練成雜訊，那比不報還糟。**
            if not S.sb_applicable(e.get("src_text")):
                sb = None
            ft = str(e.get("footage_type") or "").strip().upper()
            nb["batch 筆數"] += 1
            f_total += 1
            if e.get("src_text"):
                nb["帶 src_text"] += 1
                f_src += 1
                # src_text 只該有站方原文。混進 agent 的中文說明，會讓每一個
                # 讀它的機制都不可靠——RT4131 就是這樣害假 BITE 判準誤判連四輪。
                if S.strip_agent_note(e["src_text"])[1]:
                    polluted.append(e.get("id"))
            if isinstance(sb, int):
                nb["帶 sb_count"] += 1
            if ft:
                nb["帶 footage_type"] += 1
            bad_now = ("(BITE)" in ent and isinstance(sb, int) and sb == 0)
            bad_was = ("(BITE)" in was and isinstance(sb, int) and sb == 0)
            if bad_now:
                fake.append(e.get("id"))
            elif bad_was:
                healed.append(e.get("id"))     # 送出時有問題、狀態檔已修好——不是待辦
            if "無BITE" in ent and ((isinstance(sb, int) and sb > 0) or ft in S.FT_MUST_BITE):
                missed.append(e.get("id"))
        # 迴圈外、檔案內：≥3 筆而一筆 src_text 都沒有＝整批漏帶（散發個案仍走下面的 🟡）。
        # update／fix 用途的批次檔（修稿子、回補欄位）本來就不必帶 src_text，不算。
        if f_total >= 3 and f_src == 0 and not any(
                k in os.path.basename(f).lower() for k in ("update", "fix")):
            whole_missing.append(f"{os.path.basename(f)}（{f_total} 筆）")
    if nb:
        print(f"     {dict(nb)}")
        n = nb["batch 筆數"]
        if whole_missing:
            # R11 升紅（2026-08-13）：0812-2200（65 則）／0813-1200（80 則）兩輪整批
            # 漏帶才發現黃燈會被略過——整批漏＝組 batch 時漏了欄位，是行為漂移不是個案。
            red(f"整批漏帶 src_text：{'／'.join(whole_missing)}——趁瀏覽器還開著用 "
                f"`update-entry --batch`（每筆 {{id, src_text}}）回補，越晚素材越難撈")
        if nb["帶 src_text"] < n:
            yel(f"{n - nb['帶 src_text']} 筆沒帶 src_text——事後查證就得重開瀏覽器")
        if polluted:
            _pol = sorted(set(polluted))
            yel(f"{len(polluted)} 筆的 src_text 混入 agent 的中文說明："
                f"{'／'.join(str(x) for x in _pol[:8])}"
                f"{more_note(len(_pol), 8, unit='筆')}"
                f"——src_text 只放站方原文（13b §543），它是事後離線查證的唯一依據；"
                f"判斷寫進 needs-review，不要寫進原文（RT4131 曾害假 BITE 判準誤判連四輪）")
        if fake:
            still_fk, logged_fk = split_logged(items, fake)
            if still_fk:
                red(f"標了 (BITE) 但 sb_count=0（假 BITE，0805 實錯 7 則）：{still_fk}")
            if logged_fk:
                yel(f"已留痕待人工 {len(logged_fk)} 則（假 BITE，略）："
                    + "／".join(str(x) for x in logged_fk[:8]) + more_note(len(logged_fk), 8))
        if missed:
            still_ms, logged_ms = split_logged(items, missed)
            if still_ms:
                red(f"該有 BITE 卻標無BITE：{still_ms}")
            if logged_ms:
                yel(f"已留痕待人工 {len(logged_ms)} 則（該有 BITE 卻標無BITE，略）："
                    + "／".join(str(x) for x in logged_ms[:8]) + more_note(len(logged_ms), 8))
        if healed:
            print(f"     （送出時標錯、狀態檔已修好 {len(healed)} 則，不用再處理："
                  f"{'／'.join(str(x) for x in healed[:8])}"
                  f"{more_note(len(healed), 8, bare=True)}）")
        if not fake and not missed:
            ok("未見漏標或假 BITE")
    else:
        yel(f"{scratch} 找不到 batch 檔——無法查 BITE 一致性與落檔情形")

    # ── ④ 中主題 ─────────────────────────────────────────────────
    sec("④ 中主題")
    bm = collections.Counter()
    where = collections.defaultdict(set)
    for v in items.values():
        c = v.get("category") or {}
        if c.get("大分類"):
            bm[(c["大分類"], c.get("中主題") or "")] += 1
            where[c.get("中主題") or ""].add(c["大分類"])
    print(f"     {sum(bm.values())} 則 / {len(bm)} 個中主題")
    dup = [(a, b, big) for (big, a) in bm for (bb, b) in bm
           if big == bb and a != b and a and b and a in b]
    if dup:
        yel(f"同格內名稱互相包含（語意可能重複，共 {len(dup)} 組）：" +
            "／".join(f"{big}【{a}】⊂【{b}】" for a, b, big in dup[:6]) +
            more_note(len(dup), 6, unit="組"))
    cross = [(m, bs) for m, bs in where.items() if len(bs) > 1 and m]
    if cross:
        red(f"同名中主題跨大分類（共 {len(cross)} 組）：" +
            "／".join(f"【{m}】→{'+'.join(sorted(bs))}" for m, bs in cross[:6]) +
            more_note(len(cross), 6, unit="組"))
    # 🔴 2026-08-12 修過一次漏抓：只印前 6 組又不提示「還有更多」，人工／agent 照著
    # 顯示出來的名字去修，會漏掉沒被印出來的那幾組（實例：0812-1600 顯示 6 組全是
    # 「美國」系列，修完才發現總數 11 組裡還藏了 5 組「中國／台灣」系列從沒被看到）。
    mis = S.misplaced_topics(st)
    if mis:
        shown = "／".join(f"{b}【{m}】×{n}→{h}" for b, m, n, _w, h in mis[:6])
        more = f"（還有 {len(mis) - 6} 組未列出，全部清單見 s2_state.misplaced_topics()）" \
            if len(mis) > 6 else ""
        red(f"疑似放錯大分類 {len(mis)} 組：{shown}{more}")
    if not dup and not cross and not mis:
        ok("未見重複、跨格同名或放錯格")

    # ── ⑤ 暫存檔落地 ─────────────────────────────────────────────
    sec("⑤ 暫存檔落地")
    lists = sorted(os.path.basename(x) for x in glob.glob(os.path.join(scratch, "_rt_list_*.json")))
    rounds = sorted({re.search(r"\d{4}", str(v.get("first_seen_checkpoint") or "")).group(0)
                     for v in items.values()
                     if re.search(r"\d{4}", str(v.get("first_seen_checkpoint") or ""))})
    print(f"     _rt_list 快照：{lists or '（無）'}")
    if not lists:
        red("完全沒有 _rt_list_{HHMM}.json——漏收無從查證，RT 清單會滾動，事後撈不回來")
    elif len(lists) < max(1, len(rounds) // 2):
        yel(f"只有 {len(lists)} 份清單快照，輪次卻有 {len(rounds)} 個——多數輪次沒留證據")
    else:
        ok(f"{len(lists)} 份清單快照")

    # ── ⑥ 結構化欄位與 pending ───────────────────────────────────
    sec("⑥ 結構化欄位／pending／待人工")
    need = [(i, v) for i, v in items.items() if not sp.skip_reason(v)]
    nofield = [i for i, v in need if not v.get("fields")]
    parsebad = [i for i, v in need if v.get("parse_ok") is False]
    pend = [i for i, v in items.items() if v.get("script_status") == "pending"]
    rev = [(i, str(v.get("needs_review"))[:46]) for i, v in items.items() if v.get("needs_review")]
    if nofield:
        yel(f"{len(nofield)} 則沒有 fields：{nofield[:8]}{more_note(len(nofield), 8)}")
    if parsebad:
        yel(f"{len(parsebad)} 則 parse_ok=False：{parsebad[:8]}{more_note(len(parsebad), 8)}")
    if not nofield and not parsebad:
        ok("fields／parse_ok 全數正常")
    pend_note = ""
    if pend:
        pend_note = "：" + ",".join(pend[:8]) + more_note(len(pend), 8, bare=True)
    print(f"     pending {len(pend)} 則{pend_note}")
    if rev:
        yel(f"待人工 {len(rev)} 則（處理完要 needs-review done 結案）")
        for i, m in rev[:8]:
            print(f"        {i}: {m}")
        note = more_note(len(rev), 8)
        if note:
            print(f"        {note}")
    else:
        ok("沒有待人工項目")

    # ── ⑦ 品質掃（txt）───────────────────────────────────────────
    sec("⑦ 品質掃（txt 格式）")
    if os.path.exists(txt_path):
        lines = sv.read(txt_path)
        hits = []
        try:
            import io as _io
            import contextlib
            buf = _io.StringIO()
            with contextlib.redirect_stdout(buf):
                sv.check(txt_path)
            out = buf.getvalue()
            hits = [l for l in out.split("\n") if l.strip().startswith("行")]
        except SystemExit:
            pass
        print(f"     {len(sv.material_lines(lines))} 素材行")
        if hits:
            red(f"品質掃 {len(hits)} 命中：")
            for h in hits[:8]:
                print(f"        {h.strip()}")
            note = more_note(len(hits), 8)
            if note:
                print(f"        {note}")
        else:
            ok("品質掃 0 命中")
    else:
        yel(f"找不到 {txt_path}——尚未 render？")

    _reconcile_section(st, mmdd, AUDIT_ARGS, state_path, scratch)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mmdd", required=True, help="晚班起始日，如 0805")
    p.add_argument("--file", help="狀態檔路徑（省略＝依 --mmdd 自動組）")
    p.add_argument("--txt", help="晚班交接 txt（省略＝依 --mmdd 自動組）")
    p.add_argument("--rt-list", help="RT 清單快照（對帳用；每行 CODE|時間 或 JSON 陣列）")
    p.add_argument("--ap-list", help="AP 清單快照")
    p.add_argument("--ns-list", help="NS 清單快照")
    a = p.parse_args()
    global AUDIT_ARGS
    AUDIT_ARGS = a
    state = a.file or os.path.join(BASE, f"{a.mmdd}-s2-state.json")
    txt = a.txt or os.path.join(BASE, f"{a.mmdd}晚班交接.txt")
    scratch = os.path.join(BASE, f"2026{a.mmdd}")
    if not os.path.exists(state):
        # 收班後會歸檔到 Archive/{YYYYMMDD}/
        alt = glob.glob(os.path.join(BASE, "Archive", "**", f"{a.mmdd}-s2-state.json"), recursive=True)
        if alt:
            state = alt[0]
            scratch = os.path.dirname(state)
            txt = os.path.join(os.path.dirname(state), f"{a.mmdd}晚班交接.txt")
        else:
            print(f"ERROR: 找不到 {state}")
            sys.exit(2)
    audit(a.mmdd, state, txt, scratch)
    print("\n" + "=" * 60)
    print(f"稽核結果：🔴 {len(RED)} 項要處理｜🟡 {len(YEL)} 項提醒")
    if RED:
        print("⚠️ 🔴 的項目請直接處理，或用 `needs-review add` 記錄後再交班——"
              "**不要只在回報裡講一句**，那等於沒發生過（0805 教訓）。")
    sys.exit(1 if RED else 0)


if __name__ == "__main__":
    main()
