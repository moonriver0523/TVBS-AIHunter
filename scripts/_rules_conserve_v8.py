# -*- coding: utf-8 -*-
"""V8 五層合一——非空行多重集合守恆證明。

比照 `_rules_conserve_13c.py`（逐字節逐行版），改成**多重集合**版：
允許新檔把舊檔的行重新排列（切塊搬移、分檔），但不允許遺漏、不允許改字。

輸入：
  - 原五份（守恆的「應有」內容）：common/_rules_backup_20260907/*.md
  - 新五份執行版 ＋ 一份歸檔附錄（守恆的「實有」內容）：
      common/13c-S2-執行版-上-入口與三站擷取.md
      common/13c1-S2-執行版-中-ENEX.md
      common/13c1b-S2-執行版-中-ABC.md          （2026-09-07 裁決①：13c1 直接拆
                                                 ENEX／ABC 兩檔，不等超字元才拆）
      common/13c2-S2-執行版-下-狀態檔與指令.md
      common/13c3-S2-執行版-下-收工與防卡.md
      common/13c-V8-已取代條文.md              （歸檔附錄，不在必讀清單內）

豁免（**兩邊都套用**——原檔與新檔都不計入比對，避免結構性標記/標題被誤判為
遺漏或多出；這些是排版骨架，不是規則內容）：
  - Markdown 標題行（`#` 開頭，1~6 級都算——包含舊檔自己的規則小節標題，
    也包含歸檔附錄裡新加的「### 原 X §Y（被 Z 取代）」分隔標題）
  - `<!--BODY-->`／`<!--ENDBODY-->` 標記
  - `<!-- RULES-EOF ...` 收尾標記
  - 純分隔線 `---`（整行只有三個以上減號）

**不豁免**（必須逐字比對到）：
  - 舊檔的「> 」前言／沿革區塊（changelog、rollback 說明）——這些是實質內容，
    只是不再放進新檔必讀本文，所以規則是**全部搬進歸檔附錄**，不是被豁免不用管。
  - 舊檔內文的「> 📌／> 🔴」等強調型 blockquote——同上，逐字保留在對應位置。
  - 一切表格、程式碼區塊、條列規則文字。

新檔自己新增的說明文字（例如每份新檔頂部 5 行導覽、「（2026-09-07 訂正／搬移）」
這種新加註記句）**不特別豁免**，會算進「多出的行」——這是預期中的少量差異，
不是缺陷；Task 2 交付時會逐行列出並說明來源，不追求「多 0」，只追求「缺 0」
（team-lead 2026-09-07 裁決③：多出的行只要能逐行解釋來源就過關）。

用法：
  python -X utf8 scripts/_rules_conserve_v8.py
  在 Task 2 剪貼完成前跑，新檔都還不存在，預期印出「缺 N 行／多 0 行」，
  N＝五份原檔非空行總數（扣掉標題/標記/分隔線豁免後）——證明腳本真的在比較。

  python -X utf8 scripts/_rules_conserve_v8.py --selftest
  自證模式：把「新檔」換成 common/ 下現行的五份原檔本身，預期 ✅ 缺 0 行／多 0 行。
"""
import argparse
import glob
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMON = os.path.join(ROOT, "common")
BACKUP_DIR = os.path.join(COMMON, "_rules_backup_20260907")

OLD_FILES = [
    "13c-S2-定時掃帶-v3省token.md",
    "13c2-S2-定時掃帶-v3省token-下.md",
    "13d-S2-定時掃帶-v4.md",
    "13g-S2-定時掃帶-v5-四站.md",
    "13h-S2-定時掃帶-v7-五站.md",
]

NEW_FILE_GLOBS = [
    "13c-S2-執行版-上-*.md",
    "13c1-S2-執行版-中-*.md",
    "13c1b-S2-執行版-中-*.md",
    "13c2-S2-執行版-下-狀態檔與指令*.md",
    "13c3-S2-執行版-下-收工與防卡*.md",
    "13c-V8-已取代條文.md",
]

HEADING_RE = re.compile(r"^#{1,6}(\s|$)")
HR_RE = re.compile(r"^-{3,}$")


def is_structural(line: str) -> bool:
    s = line.strip()
    if HEADING_RE.match(s):
        return True
    if s in ("<!--BODY-->", "<!--ENDBODY-->"):
        return True
    if s.startswith("<!-- RULES-EOF"):
        return True
    if HR_RE.match(s):
        return True
    return False


def content_lines(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        lines = [l.rstrip("\n").rstrip("\r") for l in f]
    out = []
    for l in lines:
        if not l.strip():
            continue
        if is_structural(l):
            continue
        out.append(l)
    return out


def collect_new_files() -> list:
    found = []
    for pattern in NEW_FILE_GLOBS:
        found.extend(sorted(glob.glob(os.path.join(COMMON, pattern))))
    # 去重（同一份檔案可能被多個 glob 命中）
    seen = []
    for p in found:
        if p not in seen:
            seen.append(p)
    return seen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="新檔換成 common/ 現行五份原檔本身，驗證比對機制本身正確",
    )
    args = parser.parse_args()

    old_lines = []
    old_present = []
    for fn in OLD_FILES:
        p = os.path.join(BACKUP_DIR, fn)
        ls = content_lines(p)
        old_present.append((fn, os.path.exists(p), len(ls)))
        old_lines.extend(ls)

    if args.selftest:
        print("*** --selftest 模式：新檔＝common/ 現行五份原檔本身 ***\n")
        new_paths = [os.path.join(COMMON, fn) for fn in OLD_FILES]
    else:
        new_paths = collect_new_files()

    new_lines = []
    for p in new_paths:
        new_lines.extend(content_lines(p))

    print("=== 原五份（backup）===")
    for fn, exists, n in old_present:
        flag = "" if exists else "  ⚠️ 檔案不存在（backup 應該五份都在，缺檔要先查）"
        print(f"  {fn}: {n} 行{flag}")
    print(f"  原檔非結構行合計：{len(old_lines)}")

    print("=== 新檔（目前找到 %d 份） ===" % len(new_paths))
    if not new_paths:
        print("  （一份都還沒有——Task 2 剪貼前執行本腳本本來就該是這樣）")
    for p in new_paths:
        print(f"  {os.path.relpath(p, ROOT)}")
    print(f"  新檔非結構行合計：{len(new_lines)}")

    old_ctr = Counter(old_lines)
    new_ctr = Counter(new_lines)

    missing = old_ctr - new_ctr  # 原有、新無
    extra = new_ctr - old_ctr    # 新有、原無

    missing_total = sum(missing.values())
    extra_total = sum(extra.values())

    print()
    if missing_total == 0 and extra_total == 0:
        print("✅ 缺 0 行／多 0 行（結構行豁免除外）——非空行多重集合完全守恆")
    elif missing_total == 0:
        print(f"✅ 缺 0 行（硬性通過）／多 {extra_total} 行（需逐行說明來源，見下）")
    else:
        print(f"❌ 缺 {missing_total} 行／多 {extra_total} 行（結構行豁免除外）")
    if missing:
        print(f"--- 缺少的行（原有、新無），前 40 筆 ---")
        for i, (line, cnt) in enumerate(missing.items()):
            if i >= 40:
                print(f"  ...（還有 {len(missing) - 40} 種缺行未列出）")
                break
            print(f"  x{cnt}  {line[:160]}")
    if extra:
        print(f"--- 多出的行（新有、原無），前 40 筆 ---")
        for i, (line, cnt) in enumerate(extra.items()):
            if i >= 40:
                print(f"  ...（還有 {len(extra) - 40} 種多出行未列出）")
                break
            print(f"  x{cnt}  {line[:160]}")


if __name__ == "__main__":
    main()
