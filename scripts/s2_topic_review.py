# -*- coding: utf-8 -*-
"""整併後、render 前的中／小分題檢視表（2026-08-09）。

**要解決的問題**：中主題與小分題會出現同義不同名、同一事件被拆成好幾格。
0809 實例（`s2_topic_dedupe` 全部漏掉，回報 0 命中）：

  體育【高爾夫】1則 ＋【高球】1則                      ← 同義不同名
  社會【泰國校園槍擊】3則 ＋【校園槍案】1則            ← 同事件拆成兩個中主題
  體育【足球】底下「悼念老梅西／梅西家族／梅西父喪／美斯家事」
                                                       ← 同一件事拆成四個小分題

**為什麼現有的偵測器抓不到**：`s2_topic_dedupe` 只做「分級 A」——同名小分題
跨大分類，那是高信度、零誤報的訊號。它**設計上就不管**同一大分類內的相似名稱
（當初試過內文模糊比對、雜訊太高而放棄，那個決定不推翻）。

⚠️ **機械判斷不可能做完**：「美斯家事」與「梅西父喪」是港譯與台譯，**零共同字**，
只有讀得懂中文的才知道是同一個人。所以這支的定位是**幫 agent 省眼力，不是取代它**：
印出一張夠小的檢視表（約 60 行，成本極低），把機械看得出來的候選標出來，
**其餘要靠 agent 自己看過整張表**。

⛔ **只印不改**。分類的自動修正在「全盤檢討分類問題」結案前一律不做
（見 TODO；現行大分類優先序規則本身與實務衝突，機械修正會把對的判成錯的）。
本支只碰中／小分題的「同義合併」，不碰大分類歸屬，兩者是不同的軸。

用法：
  python scripts/s2_topic_review.py --file "…/0808-s2-state.json"
"""
import argparse
import os
import sys
from collections import OrderedDict, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_render as R  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# 相似度門檻：最長共同子序列 ÷ 較短的那個名稱長度。
# 0.5 是刻意訂鬆的——這裡的代價不對稱：**多印一個候選只是多看一眼，
# 漏掉一組就會留在交接檔裡給編輯看到**。誤報成本遠低於漏報。
SIM = 0.5
MIN_LEN = 2          # 一個字的名稱不比（「火」對上什麼都像）


COMMON_AT = 4        # 同組裡出現 N 次以上的字＝沒有鑑別力（見 common_chars）


def common_chars(names):
    """挑出同一組名稱裡「到處都有」的字——它們不能拿來當相似的證據。

    第一版沒做這件事，53 組候選裡大半是雜訊：
      「美國野火」vs「美國社會」（共同「美國」——那一格 16 個中主題有 8 個叫美國×）
      「高球」vs「棒球」、「足球」vs「美式足球」（共同「球」——體育當然都有球）
    **誤報會把警告訓練成雜訊，比不報更糟**（今天已經在 sb_count 上學過一次）。
    """
    cnt = {}
    for n in names:
        for ch in set(n or ""):
            cnt[ch] = cnt.get(ch, 0) + 1
    return {ch for ch, c in cnt.items() if c >= COMMON_AT}


def sim(a, b, dull=frozenset()):
    if not a or not b or min(len(a), len(b)) < MIN_LEN:
        return 0.0
    # 共同的部分若**全部**由沒有鑑別力的字組成，就不算相似
    shared = (set(a) & set(b)) - dull
    if not shared:
        return 0.0
    return R._lcs_len(a, b) / min(len(a), len(b))


def collect(state):
    """大分類 → 中主題 → 小分題 → 則數（保持狀態檔原順序）。"""
    tree = OrderedDict()
    for it in state.get("items", []):
        if it.get("script_status") == "note":
            continue
        if not (it.get("raw_entry") or "").strip():
            continue
        c = it.get("category") or {}
        big = c.get("大分類") or "(未分類)"
        mid = c.get("中主題") or "(無中主題)"
        sub = c.get("小分題") or ""
        tree.setdefault(big, OrderedDict()).setdefault(mid, defaultdict(int))[sub] += 1
    return tree


def pairs_in(names):
    """同一層裡兩兩比對，回傳超過門檻的候選（相似度由高到低）。"""
    dull = common_chars(names)
    out = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            s = sim(names[i], names[j], dull)
            if s >= SIM:
                out.append((s, names[i], names[j]))
    return sorted(out, reverse=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default=R.DEFAULT_FILE)
    p.add_argument("--quiet", action="store_true", help="只印候選，不印完整檢視表")
    args = p.parse_args()

    tree = collect(R.load_state(args.file))
    cands, singles = [], []

    if not args.quiet:
        print("=" * 64)
        print("中／小分題檢視表——render 前看過一次，發現同義就用 set-category 合併")
        print("=" * 64)

    for big, mids in tree.items():
        total = sum(sum(s.values()) for s in mids.values())
        if not args.quiet:
            print(f"\n====== {big}（{total} 則 / {len(mids)} 個中主題）======")
        for mid, subs in mids.items():
            n = sum(subs.values())
            names = [s for s in subs if s]
            if not args.quiet:
                tail = "｜".join(f"{s}({subs[s]})" for s in names) if names else "(無小分題)"
                print(f"  【{mid}】{n} 則　{tail}")
            # 同一中主題底下的小分題兩兩比
            for s, a, b in pairs_in(names):
                cands.append((f"{big}／【{mid}】", "小分題", a, b, s))
            if n == 1:
                singles.append(f"{big}／【{mid}】")
        # 同一大分類底下的中主題兩兩比
        for s, a, b in pairs_in(list(mids)):
            cands.append((big, "中主題", a, b, s))

    print("\n" + "=" * 64)
    if cands:
        print(f"🔎 機械挑出的合併候選 {len(cands)} 組（**不是判決，要自己確認**）：")
        for where, kind, a, b, s in sorted(cands, key=lambda x: -x[4]):
            print(f"  [{s:.0%}] {where} 的{kind}：「{a}」 vs 「{b}」")
    else:
        print("🔎 機械沒挑出候選——**但這不代表沒有問題**")

    if singles:
        print(f"\n📌 只有 1 則的中主題 {len(singles)} 個（過度細分的訊號，看看能不能併）：")
        print("   " + "、".join(singles[:20]) + ("…" if len(singles) > 20 else ""))

    print("\n⚠️ 機械只認字面。**同義不同名（例如港譯「美斯」vs 台譯「梅西」）零共同字，"
          "永遠挑不出來**——整張表還是要自己看過一遍。")
    print("   合併方式：`s2_state.py set-category --pairs`，改完再 render。")


if __name__ == "__main__":
    main()
