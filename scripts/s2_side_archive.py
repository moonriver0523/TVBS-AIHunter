#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""歐印萬歸檔：**已入庫**的側錄素材整組搬進日期資料夾（`0809/`）。

使用者定案（2026-08-09）：
  1. **觸發點＝入庫完成後**，不是轉譯完成後。
     ⭐ 用意在於「**根目錄剩下的就是還沒入庫的**」——資料夾本身變成漏收清單，
     不必另外維護一份已處理紀錄。C 通道（`s2_side_from_oyw.py`）也因此**只掃根目錄**。
  2. **有幾個搬幾個**：三件套（`.wav`／`.wav.txt`／`.wav(雙語對照版).txt`）缺哪個就
     報哪個，不因為缺一個就整組卡住。泰國槍擊那支的音檔就真的消失過。

判定「已入庫」的方式：把該檔的中文段擷取出來（同 C 通道的邏輯），拿 TC 去狀態檔
比對 `CNN MM-DD 6碼` 這個 id。

⚠️ **不能用「有任一段在庫就搬」**——第一版是這樣寫的，dry-run 當場打臉：
`151247 野火 台灣龍捲風` 只入庫 2/8 段（其餘 6 段是先前人工挑過的），照樣被判定
「已處理」要搬走。**那 6 段就此從根目錄消失，漏收也看不出來**——直接毀掉使用者
選這個觸發點的唯一理由（「根目錄剩下的就是還沒入庫的」）。

改成**容許零星剔除、不容許大量未收**：未入庫段數 ≤ `max(1, 總段數×10%)` 才搬。
- 交接語那種剔 1 段的（`151018`，16 段剔 1）→ 搬。
- 只收 2/8 的 → **留在根目錄**，報告標「部分入庫」。
需要強制搬走再加 `--max-miss`。

跑法：
    python scripts/s2_side_archive.py --dry-run      # 先看要搬什麼
    python scripts/s2_side_archive.py
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime

import s2_side_from_oyw as OYW

# 三件套的副檔名（順序＝報告顯示順序）
SUFFIXES = [".wav", ".wav.txt", ".wav(雙語對照版).txt"]

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def state_ids(path):
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    return {i.get("id") for i in s.get("items", []) if i.get("id")}


def main():
    ap = argparse.ArgumentParser(description="歐印萬已入庫素材歸檔到日期資料夾")
    ap.add_argument("--dir", default=OYW.DEFAULT_DIR, help="來源資料夾")
    ap.add_argument("--state", required=True, help="狀態檔路徑")
    ap.add_argument("--source", default=None,
                    help="來源前綴；省略＝從檔名自動認（見 OYW.source_of）")
    ap.add_argument("--dry-run", action="store_true", help="只列出要搬什麼，不動檔案")
    ap.add_argument("--max-miss", type=int, default=None,
                    help="容許幾段未入庫仍照搬（省略＝max(1, 總段數×10%%)）")
    args = ap.parse_args()

    ids = state_ids(args.state)
    moved = skipped = 0

    for fn in sorted(os.listdir(args.dir)):
        if not fn.endswith(".wav.txt"):
            continue
        p = os.path.join(args.dir, fn)
        base = fn[:-len(".wav.txt")]                       # `許岱軒CNN 151018 烏俄`
        with open(p, encoding="utf-8-sig", errors="replace") as f:
            raw = f.read()
        body, err = OYW.extract_zh(raw)
        if err:
            print(f"⏭ {base}：擷取不了（{err}）→ 留在根目錄")
            skipped += 1
            continue
        d = f"{datetime.fromtimestamp(os.path.getmtime(p)):%m-%d}"
        segs = OYW.segments(body)
        # ⚠️ 來源要**逐檔**從檔名認，不能整批套同一個 `--source`——CNN 與 NHK
        #    混在同一個資料夾，套錯前綴 id 就對不上，已入庫的會被判成沒入庫。
        src = args.source or OYW.source_of(p)
        hit = [t for t, _, _ in segs if f"{src} {d} {t}" in ids]
        miss = [t for t, _, _ in segs if f"{src} {d} {t}" not in ids]
        if not hit:
            print(f"⏭ {base}：{len(segs)} 段一段都沒入庫 → 留在根目錄")
            skipped += 1
            continue
        limit = args.max_miss if args.max_miss is not None \
            else max(1, int(len(segs) * 0.1))
        if len(miss) > limit:
            print(f"⏭ {base}：只入庫 {len(hit)}/{len(segs)} 段，未入庫 {len(miss)} 段"
                  f"（容許 {limit}）→ 留在根目錄")
            print(f"     未入庫：{','.join(miss)}")
            skipped += 1
            continue

        # ── 要搬了 ──────────────────────────────────────────────────
        # 日期資料夾取**來源檔 mtime**，與側錄 id 的日期同一個來源。用執行當下
        # 的日期會讓凌晨補歸檔的昨晚素材掉進今天的格子裡。
        dest = os.path.join(args.dir, f"{datetime.fromtimestamp(os.path.getmtime(p)):%m%d}")
        note = f"（未入庫 {len(miss)} 段：{','.join(miss)}）" if miss else ""
        print(f"📦 {base} → {os.path.basename(dest)}/  入庫 {len(hit)}/{len(segs)} 段{note}")
        if not args.dry_run:
            os.makedirs(dest, exist_ok=True)
        for suf in SUFFIXES:
            # ⚠️ 別叫 `src`——上面的來源前綴已經佔用那個名字，撞號現在剛好無害
            #    （用完才被蓋掉），但下次有人在迴圈後面加一行用到前綴就中招。
            srcpath = os.path.join(args.dir, base + suf)
            if not os.path.exists(srcpath):
                print(f"     ⚠️ 缺 {suf}")
                continue
            if args.dry_run:
                print(f"     · {suf}")
                continue
            tgt = os.path.join(dest, base + suf)
            if os.path.exists(tgt):
                print(f"     ⚠️ 目的地已有同名檔，跳過 {suf}")
                continue
            shutil.move(srcpath, tgt)
            print(f"     ✓ {suf}")
        moved += 1

    tag = "（dry-run，沒有真的搬）" if args.dry_run else ""
    print(f"\n歸檔 {moved} 組／留在根目錄 {skipped} 組{tag}")
    if skipped:
        print("⚠️ 留在根目錄的就是**還沒入庫**的——這是刻意的，資料夾本身當漏收清單。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
