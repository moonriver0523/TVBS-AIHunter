# -*- coding: utf-8 -*-
"""比對 SOT 稿單／素材清單，把已經做成新聞的素材標成 🟤 已做過。

用途：稿子播完之後，回頭把「這批素材本台已經做過」標進晚班交接庫存，
讓後面幾輪的編輯一眼略過已處理的（素材仍留庫存，後續發展還可能再做）。

**純字串比對，不需要 LLM 判斷**——稿單裡的素材代碼與庫存的 id 是同一套編碼，
逐則讀稿再逐則比對只是把機械工作交給模型做，既慢又會漏。

用法：
  # 先看會標到哪些（預設 dry-run，不寫檔）
  python s2_mark_aired.py --rundown "…/野火燒屋1730 素材清單.txt"

  # 確認沒問題再實際寫入
  python s2_mark_aired.py --rundown "…/素材清單.txt" --apply

  # 指定要比對的庫存（可重複；省略＝自動找 自動掃帶系統/ 與 Archive/ 底下全部）
  python s2_mark_aired.py --rundown "…" --file "…/0804-s2-state.json" --apply

寫入後**記得跑 `s2_render.py` 重新渲染**，否則 txt 看不到變化
（狀態檔是唯一真相源、txt 是單向投影，見 13b §2a）。
"""
import argparse
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_state as S      # noqa: E402
import s2_validate as sv  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

BASE = os.path.dirname(S.DEFAULT_FILE)


def codes_from(path):
    """抽出稿單裡的素材代碼，保留出現順序、去重。

    直接用 `s2_validate.CODE`（庫存行辨識用的同一個正則），不另外寫一套——
    兩邊用不同正則遲早會分叉，出現「稿單抓得到但庫存比不到」的假漏標。
    ⚠️ 稿單的 `#01`／`(新)`／`△` 這些前綴不影響：CODE 只認代碼本身。
    """
    try:
        with open(path, encoding="utf-8-sig") as f:
            txt = f.read()
    except OSError as e:
        print(f"ERROR: 稿單讀取失敗（{e}）")
        sys.exit(2)
    out = []
    for c in re.findall(sv.CODE, txt):
        c = S.norm_id(c)
        if c not in out:
            out.append(c)
    return out


def state_files(args):
    if args.file:
        return args.file
    # 省略時：正式庫存檔在 自動掃帶系統/ 這層，收工後會歸檔進 Archive/{YYYYMMDD}/
    found = sorted(glob.glob(os.path.join(BASE, "*-s2-state.json")) +
                   glob.glob(os.path.join(BASE, "Archive", "**", "*-s2-state.json"),
                             recursive=True))
    # 排除備份檔（`…回寫前備份.json` 這類），只認 {MMDD}-s2-state.json
    return [f for f in found if re.match(r"^\d{4}-s2-state\.json$", os.path.basename(f))]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rundown", required=True, help="SOT 稿單／素材清單 txt")
    p.add_argument("--file", action="append", help="要比對的狀態檔（可重複，省略＝自動找）")
    p.add_argument("--apply", action="store_true", help="實際寫入；省略＝只報告不動檔案")
    args = p.parse_args()

    codes = codes_from(args.rundown)
    if not codes:
        print("稿單裡找不到任何素材代碼——確認檔案對不對，或代碼格式是否非標準。")
        sys.exit(1)
    print(f"稿單：{os.path.basename(args.rundown)}")
    print(f"抓到 {len(codes)} 個代碼：{'、'.join(codes)}\n")

    files = state_files(args)
    if not files:
        print("ERROR: 找不到任何狀態檔，請用 --file 明確指定")
        sys.exit(2)

    found, total_new = {}, 0
    for f in files:
        st = S.load(f)
        inv = st["items"]
        hits = [c for c in codes if c in inv]
        if not hits:
            continue
        new = [c for c in hits if not inv[c].get("aired")]
        already = [c for c in hits if inv[c].get("aired")]
        name = os.path.basename(f)
        print(f"■ {name}（庫存 {len(inv)} 則）")
        for c in hits:
            tag = "已標過" if c in already else "要標記"
            head = (inv[c].get("raw_entry") or "").split("▎")[0].strip()
            print(f"   [{tag}] {c:12} {head[:56]}")
        for c in hits:
            found.setdefault(c, []).append(name)
        if new and args.apply:
            for c in new:
                inv[c]["aired"] = True
            S.save(st, f)
            print(f"   → 已寫入 {len(new)} 則")
        total_new += len(new)
        print()

    missing = [c for c in codes if c not in found]
    if missing:
        print(f"⚠️ 不在任何庫存裡的 {len(missing)} 則：{'、'.join(missing)}")
        print("   （常見原因：更早幾天收的、已歸檔；或側錄／非通訊社素材不進庫存）\n")

    if args.apply:
        print(f"✅ 共標記 {total_new} 則。⚠️ 記得跑 s2_render.py 重新渲染，否則 txt 看不到變化。")
    else:
        print(f"（dry-run，未寫檔）確認無誤後加 --apply 實際寫入：{total_new} 則會被標記。")


if __name__ == "__main__":
    main()
