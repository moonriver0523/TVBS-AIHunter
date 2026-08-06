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



def parse_list_file(path):
    """讀 agent 撈回來的清單快照。兩種格式都吃：

    ① 純文字，每行 `CODE|MM/DD/YYYY HH:MM` 或 `CODE|HH:MM`（多餘欄位忽略）
    ② JSON 陣列，每筆 {"code": "...", "at": "..."}／{"id": ..., "time": ...}
    """
    raw = open(path, encoding="utf-8-sig").read().strip()
    rows = []
    if raw.startswith("["):
        for it in json.loads(raw):
            c = it.get("code") or it.get("id") or ""
            t = it.get("at") or it.get("time") or ""
            if c:
                rows.append((c.strip(), str(t)))
    else:
        for line in raw.split("\n"):
            if not line.strip():
                continue
            parts = [x.strip() for x in line.split("|")]
            if parts[0]:
                rows.append((parts[0], parts[1] if len(parts) > 1 else ""))
    return rows


def _hhmm(t):
    m = re.search(r"(\d{1,2}):(\d{2})", t or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def reconcile(st, mmdd, path, label):
    """清單 vs 狀態檔對帳：算出**窗內該收而未收**的。"""
    rows = parse_list_file(path)
    cur = set(st["items"])
    prev = set()
    for f in glob.glob(os.path.join(BASE, "Archive", "**", "[01]*-s2-state.json"), recursive=True):
        try:
            prev |= set(S.load(f)["items"])
        except Exception:
            pass
    prev -= cur

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

    got = [c for c, _t in rows if c in cur]
    old_ = [c for c, _t in rows if c not in cur and c in prev]
    rest = [(c, t) for c, t in rows if c not in cur and c not in prev]
    inw = [(c, t) for c, t in rest if ws is None or we is None
           or (norm(t) is not None and ws <= norm(t) <= we)]
    after = [(c, t) for c, t in rest if (c, t) not in inw]

    print(f"     {label}：清單 {len(rows)}｜已收 {len(got)}｜前幾天收過 {len(old_)}"
          f"｜窗內未收 {len(inw)}｜窗外 {len(after)}")
    if inw:
        red(f"{label} 窗內漏收 {len(inw)} 則：" +
            "／".join(f"{c}({t[-5:]})" for c, t in inw[:12]))
    else:
        ok(f"{label} 窗內零漏收")
    if after:
        print(f"        （窗外 {len(after)} 則屬下一輪，不算漏：" +
              "／".join(c for c, _t in after[:8]) + "）")


    # ── Ⓐ 三站清單對帳（給 --rt-list／--ap-list／--ns-list 就做）──────
def _reconcile_section(st, mmdd, args):
    sec("Ⓐ 清單對帳（最高價值：0805 靠它抓到 47 則漏收）")
    any_ = False
    for opt, label in (("rt_list", "RT"), ("ap_list", "AP"), ("ns_list", "NS")):
        path = getattr(args, opt, None)
        if path:
            any_ = True
            if not os.path.exists(path):
                red(f"{label} 清單檔不存在：{path}")
            else:
                reconcile(st, mmdd, path, label)
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
    sec("② 時段標記")
    marks = collections.Counter()
    for v in items.values():
        mk = v.get("mark") if v.get("mark") in ("△", "▲", "■", "◆", "●") \
            else R.mark_for(v.get("first_seen_checkpoint"), mmdd)
        marks[mk] += 1
    print(f"     分佈：{dict(marks)}")
    if len(marks) == 1 and "△" in marks and len(items) > 60:
        red("全部都是 △——跨夜輪次應該要有 ▲／■／◆，多半是 checkpoint 格式問題（見 ①）")
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
    fake, missed, healed = [], [], []
    for f in sorted(glob.glob(os.path.join(scratch, "*batch*.json"))):
        try:
            data = json.load(open(f, encoding="utf-8-sig"))
        except Exception:
            continue
        for e in data if isinstance(data, list) else []:
            was, sb = e.get("entry", ""), e.get("sb_count")
            ent = cur_entry.get(e.get("id"), was)   # 狀態檔優先；已刪除的才退回 batch
            ft = str(e.get("footage_type") or "").strip().upper()
            nb["batch 筆數"] += 1
            if e.get("src_text"):
                nb["帶 src_text"] += 1
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
    if nb:
        print(f"     {dict(nb)}")
        n = nb["batch 筆數"]
        if nb["帶 src_text"] < n:
            yel(f"{n - nb['帶 src_text']} 筆沒帶 src_text——事後查證就得重開瀏覽器")
        if fake:
            red(f"標了 (BITE) 但 sb_count=0（假 BITE，0805 實錯 7 則）：{fake}")
        if missed:
            red(f"該有 BITE 卻標無BITE：{missed}")
        if healed:
            print(f"     （送出時標錯、狀態檔已修好 {len(healed)} 則，不用再處理："
                  f"{'／'.join(str(x) for x in healed[:8])}）")
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
        yel("同格內名稱互相包含（語意可能重複）：" +
            "／".join(f"{big}【{a}】⊂【{b}】" for a, b, big in dup[:6]))
    cross = [(m, bs) for m, bs in where.items() if len(bs) > 1 and m]
    if cross:
        red("同名中主題跨大分類：" + "／".join(f"【{m}】→{'+'.join(sorted(bs))}" for m, bs in cross[:6]))
    mis = S.misplaced_topics(st)
    if mis:
        red(f"疑似放錯大分類 {len(mis)} 組：" +
            "／".join(f"{b}【{m}】×{n}→{h}" for b, m, n, _w, h in mis[:6]))
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
        yel(f"{len(nofield)} 則沒有 fields：{nofield[:8]}")
    if parsebad:
        yel(f"{len(parsebad)} 則 parse_ok=False：{parsebad[:8]}")
    if not nofield and not parsebad:
        ok("fields／parse_ok 全數正常")
    print(f"     pending {len(pend)} 則{'：' + ','.join(pend[:8]) if pend else ''}")
    if rev:
        yel(f"待人工 {len(rev)} 則（處理完要 needs-review done 結案）")
        for i, m in rev[:8]:
            print(f"        {i}: {m}")
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
        else:
            ok("品質掃 0 命中")
    else:
        yel(f"找不到 {txt_path}——尚未 render？")

    _reconcile_section(st, mmdd, AUDIT_ARGS)


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
