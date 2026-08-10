#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""套用「分類收斂建議」檔（2026-08-10 使用者訂案）。

## 這支存在的理由

每一輪掃帶 agent 都會分類**自己收的那批**，但**跨輪的一致性沒有人負責**——
0810 實例（哥倫比亞強震）：卡利的素材散在【強震速報】三個小分題、佩雷拉被歸進
【卡利災情】、馬尼薩雷斯被歸進【波哥大災情】。每一輪各自看自己那批，沒有人回頭
看整天長成什麼樣，於是同一個城市散在三處。

缺的不是「分類」，是**收斂**。收斂由**獨立的分類檢視 agent** 在輪次之間做，
但它 ⛔ **不直接寫狀態檔**——`s2_state.py` 沒有檔案鎖，兩邊同時寫就是 lost update
（0810 差點覆蓋 44 處修正的實例見 `13`「`_待整併/`：外部 agent 的交件夾」）。
它只產出一份建議檔，由**掃帶輪**跑這支套用。

## 為什麼要有這支，而不是叫掃帶 agent 自己看建議檔照做

套用階段**不該再有判斷**。讓 agent 讀建議檔再自己拼 `set-category`，等於把同一個
判斷做兩次，而且多一次打錯的機會（素材 id 含空格，如 `CNN 08-10 224714`，
手拼分號字串特別容易斷錯）。這支把套用變成一道零 token、零判斷的機械步驟。

## 建議檔格式（`_待整併/{MMDD}-分類收斂建議.txt`）

只認兩種指令行，其餘（空行、`#` 註解、說明文字）一律略過：

    MOVE  {素材id}={大分類}/{中主題}/{小分題}
    ORDER {大分類}={中主題1};{中主題2};…

⚠️ 用 `MOVE`／`ORDER` 前綴而不是靠分號切——**素材 id 本身含空格**
（側錄是 `CNN 08-10 224714`），一行一筆才不會切錯。

用法：
    python scripts/s2_apply_reclass.py --file "…/{MMDD}-s2-state.json" \
        --suggest "…/_待整併/{MMDD}-分類收斂建議.txt" --dry-run
    # 看過沒問題再拿掉 --dry-run
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2_state  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

MOVE = re.compile(r"^MOVE\s+(.+?)=(.+?)/(.+?)(?:/(.*))?$")
ORDER = re.compile(r"^ORDER\s+(.+?)=(.+)$")


def parse(path):
    """回傳 (moves, orders, 壞行)。moves=[(id, 大, 中, 小)]、orders=[(大, [中主題…])]"""
    moves, orders, bad = [], [], []
    with open(path, encoding="utf-8-sig") as f:
        for n, raw in enumerate(f, 1):
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            m = MOVE.match(s)
            if m:
                mid, big, topic, sub = m.group(1).strip(), m.group(2).strip(), \
                    m.group(3).strip(), (m.group(4) or "").strip()
                if not (mid and big and topic):
                    bad.append((n, "MOVE 缺欄位", s))
                else:
                    moves.append((mid, big, topic, sub))
                continue
            m = ORDER.match(s)
            if m:
                big = m.group(1).strip()
                mids = [x.strip() for x in re.split(r"[;；]", m.group(2)) if x.strip()]
                if not (big and mids):
                    bad.append((n, "ORDER 缺欄位", s))
                else:
                    orders.append((big, mids))
                continue
            # ⚠️ 認不得的行**大聲報**，不要默默略過——建議檔是人／agent 寫的，
            #    打錯前綴（`MOVE:` 而不是 `MOVE `）會讓那筆修正靜靜消失。
            bad.append((n, "認不得的指令行", s))
    return moves, orders, bad


def main():
    ap = argparse.ArgumentParser(description="套用分類收斂建議檔")
    ap.add_argument("--file", help="狀態檔路徑（省略＝預設今天那份）")
    ap.add_argument("--suggest", required=True, help="建議檔路徑")
    ap.add_argument("--dry-run", action="store_true", help="只檢查不寫檔")
    args = ap.parse_args()

    if not os.path.exists(args.suggest):
        print(f"ERROR 找不到建議檔：{args.suggest}", file=sys.stderr)
        return 2

    moves, orders, bad = parse(args.suggest)
    for n, why, s in bad:
        print(f"⚠️ 第{n}行 {why}：{s[:90]}")
    if not moves and not orders:
        print("建議檔裡沒有任何 MOVE／ORDER 指令，什麼都沒做")
        return 1 if bad else 0

    state = s2_state.load(args.file)
    items = state.get("items", {})

    # 先驗 id 存不存在——套到不存在的 id 是靜默失敗的經典形狀
    missing = [m[0] for m in moves if m[0] not in items]
    if missing:
        print(f"🔴 建議檔有 {len(missing)} 個 id 不在狀態檔裡，**整份不套用**：")
        for i in missing[:10]:
            print("   ", i)
        print("   → 多半是 id 打錯或那則已被 remove；修好建議檔再跑一次")
        return 2

    changed = 0
    for mid, big, topic, sub in moves:
        cat = {"大分類": big, "中主題": topic}
        if sub:
            cat["小分題"] = sub
        if items[mid].get("category") != cat:
            changed += 1
            if not args.dry_run:
                items[mid]["category"] = cat

    top = state.setdefault("_top", {})
    torder = top.setdefault("topic_order", {})
    for big, mids in orders:
        if torder.get(big) != mids and not args.dry_run:
            torder[big] = mids

    tag = "DRY-RUN " if args.dry_run else ""
    print(f"{tag}MOVE {len(moves)} 筆（實際有變動 {changed} 筆）／"
          f"ORDER {len(orders)} 個大分類")
    for mid, big, topic, sub in moves[:5]:
        print(f"   {mid} → {big}／{topic}" + (f"／{sub}" if sub else ""))
    if len(moves) > 5:
        print(f"   …其餘 {len(moves) - 5} 筆")

    if args.dry_run:
        print("（--dry-run，未寫檔）")
        return 0
    s2_state.save(state, args.file)
    print("OK 已寫回狀態檔——接著跑 s2_render.py 重新渲染")
    return 0


if __name__ == "__main__":
    sys.exit(main())
