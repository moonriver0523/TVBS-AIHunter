# -*- coding: utf-8 -*-
"""V8 五層合一——非空行多重集合守恆證明。

比照 `_rules_conserve_13c.py`（逐字節逐行版），改成**多重集合**版：
允許新檔把舊檔的行重新排列（切塊搬移、分檔），但不允許遺漏、不允許改字。

輸入：
  - 原五份（守恆的「應有」內容）：common/_rules_backup_20260907/*.md
  - 新四份執行版 ＋ 一份歸檔附錄（守恆的「實有」內容）：
      common/13c-S2-執行版-上-入口與三站擷取.md
      common/13c1-S2-執行版-中-ENEX與ABC.md   （若因超字元上限拆成 13c1/13c1b 兩份，
                                                 兩份都會被本腳本掃到，見 NEW_FILES 的
                                                 glob 規則）
      common/13c2-S2-執行版-下-狀態檔與指令.md
      common/13c3-S2-執行版-下-收工與防卡.md
      common/13c-V8-已取代條文.md              （歸檔附錄，不在必讀清單內）

豁免（只在「新檔」那邊算，不影響原檔那邊）：
  - 新檔的 H1 標題行（開頭 `# `）
  - `<!-- RULES-EOF ...` 收尾標記行
  - 含「（2026-09-07 」的訂正/搬移註記行（例如 13f 指路那種新增的一行說明）

用法：
  python -X utf8 scripts/_rules_conserve_v8.py
  在 Task 2 剪貼完成前跑，新檔都還不存在，預期印出「缺 N 行／多 0 行」，
  N＝五份原檔非空行總數——證明腳本真的在比較，不是空跑一定過。

  python -X utf8 scripts/_rules_conserve_v8.py --selftest
  自證模式：把「新檔」換成 common/ 下現行的五份原檔本身（Task 2 還沒動它們，
  內容跟 backup 逐字相同），預期 ✅ 缺 0 行／多 0 行——證明多重集合比對機制
  本身正確，不是腳本邏輯有洞才巧合印出 ✅。
"""
import argparse
import glob
import os
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

# 新檔用 glob：13c1 若超字元上限被拆成 13c1／13c1b 兩份，這裡都吃得到；
# 13c-S2-執行版-上-*.md 之類同理，不寫死單一檔名，避免 Task 2 微調命名就要改腳本。
NEW_FILE_GLOBS = [
    "13c-S2-執行版-上-*.md",
    "13c1*-S2-執行版-中-*.md",
    "13c2-S2-執行版-下-狀態檔與指令*.md",
    "13c3-S2-執行版-下-收工與防卡*.md",
    "13c-V8-已取代條文.md",
]

EXEMPT_PREFIXES = ("# ",)
EXEMPT_SUBSTRINGS = ("<!-- RULES-EOF", "（2026-09-07 ")


def is_exempt(line: str) -> bool:
    s = line.strip()
    if any(s.startswith(p) for p in EXEMPT_PREFIXES):
        return True
    if any(sub in s for sub in EXEMPT_SUBSTRINGS):
        return True
    return False


def nonempty_lines(path: str, exempt: bool) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        lines = [l.rstrip("\n").rstrip("\r") for l in f]
    out = []
    for l in lines:
        if not l.strip():
            continue
        if exempt and is_exempt(l):
            continue
        out.append(l)
    return out


def collect_new_files() -> list:
    found = []
    for pattern in NEW_FILE_GLOBS:
        found.extend(sorted(glob.glob(os.path.join(COMMON, pattern))))
    return found


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
        ls = nonempty_lines(p, exempt=False)
        old_present.append((fn, os.path.exists(p), len(ls)))
        old_lines.extend(ls)

    if args.selftest:
        print("*** --selftest 模式：新檔＝common/ 現行五份原檔本身 ***\n")
        new_paths = [os.path.join(COMMON, fn) for fn in OLD_FILES]
    else:
        new_paths = collect_new_files()

    new_lines = []
    for p in new_paths:
        # selftest 用原檔比對，不套用「新檔豁免行」規則（H1/RULES-EOF 本來就都
        # 该在，套不套豁免不影響一致性；保留 exempt=not selftest 讓兩種模式互不干擾）
        new_lines.extend(nonempty_lines(p, exempt=not args.selftest))

    print("=== 原五份（backup）===")
    for fn, exists, n in old_present:
        flag = "" if exists else "  ⚠️ 檔案不存在（backup 應該五份都在，缺檔要先查）"
        print(f"  {fn}: {n} 行{flag}")
    print(f"  原檔非空行合計：{len(old_lines)}")

    print("=== 新檔（目前找到 %d 份） ===" % len(new_paths))
    if not new_paths:
        print("  （一份都還沒有——Task 2 剪貼前執行本腳本本來就該是這樣）")
    for p in new_paths:
        print(f"  {os.path.relpath(p, ROOT)}")
    print(f"  新檔非空行合計（已扣豁免行）：{len(new_lines)}")

    old_ctr = Counter(old_lines)
    new_ctr = Counter(new_lines)

    missing = old_ctr - new_ctr  # 原有、新無
    extra = new_ctr - old_ctr    # 新有、原無

    missing_total = sum(missing.values())
    extra_total = sum(extra.values())

    print()
    if missing_total == 0 and extra_total == 0:
        print("✅ 缺 0 行／多 0 行（豁免行除外）——非空行多重集合完全守恆")
    else:
        print(f"❌ 缺 {missing_total} 行／多 {extra_total} 行（豁免行除外）")
        if missing:
            print(f"--- 缺少的行（原有、新無），前 20 筆 ---")
            for i, (line, cnt) in enumerate(missing.items()):
                if i >= 20:
                    print(f"  ...（還有 {len(missing) - 20} 種缺行未列出）")
                    break
                print(f"  x{cnt}  {line[:120]}")
        if extra:
            print(f"--- 多出的行（新有、原無），前 20 筆 ---")
            for i, (line, cnt) in enumerate(extra.items()):
                if i >= 20:
                    print(f"  ...（還有 {len(extra) - 20} 種多出行未列出）")
                    break
                print(f"  x{cnt}  {line[:120]}")


if __name__ == "__main__":
    main()
