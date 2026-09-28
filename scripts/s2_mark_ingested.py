#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`_待整併` 交件檔入庫後標記檔名（2026-08-11 使用者訂案）。

## 要解決什麼

`_待整併/` 是跨天共用的交件夾，入庫後檔案還躺在那裡，**下一個 agent 無從判斷
「這是今天要整併的，還是已經入庫的」**。0810 那天躺了 16 個檔，只能寫臨時腳本
逐筆比對 239 個代碼／TC 才敢刪。

## 🔴 為什麼「驗證」與「標記」必須綁在同一支

直接改檔名很簡單，但**標了卻沒真的入庫**比不標更糟——下一輪看到「已入庫」就跳過，
那批素材就此消失，而且沒有任何人會發現。所以這支**先逐筆比對狀態檔，全部在庫才改名**；
只要缺一筆就整份不動並列出缺哪些。

## 用法

    python scripts/s2_mark_ingested.py --file "…/{MMDD}-s2-state.json"          # 全掃，只報告
    python scripts/s2_mark_ingested.py --file "…" --apply                        # 確認後改名
    python scripts/s2_mark_ingested.py --file "…" --apply --only 0810-ENEX-r2    # 只處理指定檔

改名規則：`0810-ENEX.txt` → `已入庫_0810-ENEX.txt`（前綴，讓已完成的排在一起）。
16:00 建檔輪歸檔時照樣整批搬走（`s2_scan.ps1`），這個前綴只影響人／agent 的辨識。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統"
PEND = os.path.join(BASE, "_待整併")
DONE = "已入庫_"

# 側錄：`CNN 08-10 223403 （主播）` 或裸 TC `16:24:45-16:25:33 (主播)`
SIDE_PREFIXED = re.compile(r"^(?:[🔴🟡△▲◇■◆●]\s*)*(?:CNN|NHK)\s+(?:\d{2}-\d{2}\s+)?(\d{1,2}:?\d{2}:?\d{2})")
SIDE_BARE = re.compile(r"^\(?(\d{1,2}:\d{2}:\d{2})")
# 通訊社素材代碼（含 ENEX／ABC／YNA／CNA 等）
CODE = re.compile(r"^(?:[🔴🟡△▲◇■◆●]\s*)*([A-Z]{2,6}[-\d][\w-]*)\s")


def _load_state_module():
    """延遲載入 s2_state（只有檔案裡真的有側錄行才需要），重用 add-side 的解析器。"""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import s2_state
    return s2_state


def _side_hints_from_name(path):
    """檔名推 (來源, MM-DD)：`0926-側錄候選.txt` → (None, '09-26')；`0926-CNN側錄.txt` → ('CNN', '09-26')。
    檔內行自帶的來源／日期優先（normalize_side 的既有規則），這裡只補裸 TC 行。"""
    base = os.path.basename(path)
    upper = base.upper()
    src = None
    if "CNN" in upper and "NHK" not in upper:
        src = "CNN"
    elif "NHK" in upper and "CNN" not in upper:
        src = "NHK"
    m = re.match(r"(?:已入庫_)?(\d{2})(\d{2})", base)
    return src, (f"{m.group(1)}-{m.group(2)}" if m else None)


def side_keys_in_file(path, text=None):
    """D24③（2026-09-28）：側錄改用**完整 canonical ID**（`CNN 09-26 150227`）比對。

    舊版只取 TC6、丟掉來源與日期——不同來源（CNN／NHK）或不同日期剛好同一個 TC 時，
    會被誤認成已入庫而改名，那批側錄就此消失。現在直接重用 add-side 的
    `parse_side_txt()` 產 ID（與入庫時同一套規則），任何一段湊不齊「來源＋日期＋TC」
    就回報問題、整份不改名，**不准退回只比 TC6**。

    回傳 (完整側錄 ID 集合, 問題清單)。
    """
    if text is None:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    side_lines = 0
    for raw in text.splitlines():
        s = raw.strip()
        if s and not s.startswith(("#", "擬歸位", "======", "【")) and (
                SIDE_PREFIXED.match(s) or SIDE_BARE.match(s)):
            side_lines += 1
    if not side_lines:
        return set(), []
    st = _load_state_module()
    src, tc_date = _side_hints_from_name(path)
    try:
        parsed = st.parse_side_txt(text, src, None, True, tc_date)
    except st.SideHomeError as e:
        return set(), [f"側錄擬歸位行格式不對，無法解析：{e}"]
    ids, problems = set(), []
    for pid, *_ in parsed:
        if len(pid.split()) != 3:
            problems.append(f"{pid} 缺來源或日期，湊不出完整 ID")
        else:
            ids.add(pid)
    if len(parsed) < side_lines:
        problems.append(f"側錄 TC 行 {side_lines} 行只解析出 {len(parsed)} 段"
                        "（多半是裸 TC 沒寫 CNN／NHK，檔名也看不出來源）")
    return ids, problems


def keys_in_file(path):
    """回傳檔案裡出現的 (側錄完整 ID 集合, 素材代碼集合)。"""
    codes = set()
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith(("#", "擬歸位", "======", "【")):
            continue
        if SIDE_PREFIXED.match(s) or SIDE_BARE.match(s):
            continue
        m = CODE.match(s)
        if m:
            codes.add(m.group(1))
    side_ids, _problems = side_keys_in_file(path, text)
    return side_ids, codes


def keys_in_state(state_path):
    j = json.load(open(state_path, encoding="utf-8-sig"))
    items = j.get("items", [])
    ids = set(items) if isinstance(items, dict) else {it["id"] for it in items}
    side_ids = {i for i in ids if i[:3] in ("CNN", "NHK")}
    return side_ids, ids


def companion_candidate_json(txt_path):
    """`{MMDD}-{站}.txt` 的整併用夥伴檔是 `{MMDD}-{站}-state.json`（§2 兩份一起交）。

    ENEX／ABC 候選 txt 裡的「排除清單」項目沒有固定的段落標頭（agent 手寫，
    格式不受控），CODE 正則沒有能力分辨「這行是收錄還是排除」——與其在 txt
    裡臆測段落邊界，不如直接信任候選 JSON 的 `skipped` 陣列，那是機器寫的、
    有結構的權威來源。找不到夥伴檔就回傳 None，呼叫端退回原本行為。
    """
    if not txt_path.endswith(".txt"):
        return None
    candidate = txt_path[: -len(".txt")] + "-state.json"
    return candidate if os.path.isfile(candidate) else None


def skipped_ids_in_candidate(json_path):
    try:
        jj = json.load(open(json_path, encoding="utf-8-sig"))
    except Exception:
        return set()
    return {s["id"] for s in jj.get("skipped", []) if isinstance(s, dict) and s.get("id")}


def main():
    ap = argparse.ArgumentParser(description="驗證 _待整併 交件檔是否已入庫，並標記檔名")
    ap.add_argument("--file", required=True, help="狀態檔路徑")
    ap.add_argument("--pending", default=PEND, help="交件夾路徑")
    ap.add_argument("--apply", action="store_true", help="真的改名（省略＝只報告）")
    ap.add_argument("--only", help="只處理檔名含此字串的檔")
    args = ap.parse_args()

    if not os.path.isdir(args.pending):
        print(f"ERROR 找不到交件夾：{args.pending}", file=sys.stderr)
        return 2
    side_ids, ids = keys_in_state(args.file)

    done, todo, skip = [], [], []
    for fn in sorted(os.listdir(args.pending)):
        p = os.path.join(args.pending, fn)
        if not os.path.isfile(p) or fn.startswith(DONE):
            continue
        if args.only and args.only not in fn:
            continue
        # `-state.json` 這類交件用 JSON：直接讀 items 的 id
        if fn.endswith(".json"):
            try:
                jj = json.load(open(p, encoding="utf-8-sig"))
                fcodes = {it["id"] for it in jj.get("items", [])}
                ftcs = set()
            except Exception as e:
                skip.append((fn, f"JSON 讀取失敗：{e}"))
                continue
        else:
            ftcs, fcodes = keys_in_file(p)
            _ids, side_problems = side_keys_in_file(p)
            if side_problems:
                # D24③：身分湊不齊就整份不動，交人工——寧可晚改名，不可誤改名
                skip.append((fn, "側錄身分不完整，不改名：" + "；".join(side_problems[:3])))
                continue
        total = len(ftcs) + len(fcodes)
        if total == 0:
            skip.append((fn, "解析不到任何代碼／TC——格式不認得，人工看"))
            continue
        companion = companion_candidate_json(p)
        skipped_ids = skipped_ids_in_candidate(companion) if companion else set()
        missing = [t for t in ftcs if t not in side_ids] + [
            c for c in fcodes if c not in ids and c not in skipped_ids
        ]
        if missing:
            todo.append((fn, total, missing))
        else:
            done.append((fn, total))

    print(f"✅ 已全部入庫（{len(done)} 個檔）")
    for fn, n in done:
        print(f"   {fn}  （{n} 筆全在庫）")
    if todo:
        print(f"\n⚠️ 尚未入庫或有缺（{len(todo)} 個檔）——**不改名**")
        for fn, n, miss in todo:
            print(f"   {fn}  解析{n} 筆，缺 {len(miss)}：{miss[:6]}")
    if skip:
        print(f"\n❓ 略過（{len(skip)} 個檔）")
        for fn, why in skip:
            print(f"   {fn}  {why}")

    if not args.apply:
        print("\n（未加 --apply，沒有改名）")
        return 0
    renamed = 0
    for fn, _n in done:
        src = os.path.join(args.pending, fn)
        dst = os.path.join(args.pending, DONE + fn)
        if os.path.exists(dst):
            # 同一天常分好幾批交件，同名已被前一批佔用——加時間戳尾碼避免撞名，
            # ⛔ 不能就這樣略過不改名：略過會讓這個交件檔留在「看起來還沒入庫」
            # 的原檔名下，下一批 agent 依「檔案已存在就 append」規則會誤把新內容
            # 併進這個其實已經入庫的檔案（2026-08-16 實例：手動改名才發現這個坑）。
            base, ext = os.path.splitext(fn)
            dst = os.path.join(args.pending, f"{DONE}{base}_{datetime.now():%H%M}{ext}")
            if os.path.exists(dst):
                print(f"   略過（連加時間戳都撞名，人工處理）：{fn}")
                continue
        os.rename(src, dst)
        renamed += 1
        print(f"   {fn} → {os.path.basename(dst)}")
    print(f"\nOK 已標記 {renamed} 個檔為「{DONE}」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
