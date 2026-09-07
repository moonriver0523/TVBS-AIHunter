# -*- coding: utf-8 -*-
"""規則載入完整性檢查（R15，2026-08-24）。唯讀，不到一秒，掃帶開工第一件事跑。

為什麼要有這支：**Read 工具的結果約 30,000 字元就會靜默截斷**——沒有錯誤訊息、
沒有提示。實測 0820／0821／0823 每一輪的 `common/13`（53,676 字元）都只載入約一半，
大分類清單、素材行寫法、時區換算、RT 連讀鐵律從沒進過 context，連續三天沒人發現。

檢查三件事：
  1. 八份必讀檔都在，且尺寸都低於安全預算（估計載入量 < 28,000）
  2. 每份檔尾都有 RULES-EOF 標記（agent 讀完要能對照）
  3. 高風險規則字串仍存在於某一份必讀檔裡（＝規則沒有在分檔時掉字）

2026-09-07 V8 五層合一：13d／13g／13h 三份增量檔退役（內容已合一進 13c/13c1/
13c1b/13c2/13c3，舊文逐字存查於 `13c-V8-已取代條文.md`），不再有版本切換制，
移除 VERSIONED 機制。

離開碼：0＝全過；1＝有問題（⛔ 不要開始掃帶，先回報使用者）

用法：
    python scripts/s2_rules_check.py          # 完整輸出
    python scripts/s2_rules_check.py --quiet  # 只印結論與問題
"""
import os
import sys

# Windows 預設 cp950 主控台印不出 ✅／❌，會讓本檢查以 UnicodeEncodeError 假性失敗
# （0824-1000 輪實際踩到）。強制 UTF-8 輸出，呼叫端就不必自己加 PYTHONIOENCODING。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
C = os.path.join(REPO, "common")

# 估計載入量＝檔案字元數 ＋ 每行的行號前綴（Read 會在每行前面加 "123\t"）
SAFE_BUDGET = 28000      # 實測截斷點落在 30,4xx~31,0xx，留約 10% 安全邊際

REQUIRED = [
    ("13",     "13-S2-定時掃帶.md",                        "一部：六項決策／流程／狀態／輸出"),
    ("13e",    "13e-S2-素材行與分類規則.md",                "二部：檔頭／庫存檔格式／素材行寫法"),
    ("13f",    "13f-S2-大分類與各站規則.md",                "三部：大分類／各站／時區／RT 連讀"),
    ("13c",    "13c-S2-執行版-上-入口與三站擷取.md",         "執行版上：三站入口／§1a API 直查／掃描順序（五站）"),
    ("13c1",   "13c1-S2-執行版-中-ENEX.md",                "執行版中：ENEX API 直查／整併／對帳"),
    ("13c1b",  "13c1b-S2-執行版-中-ABC.md",                "執行版中：ABC 清單直查／整併／對帳"),
    ("13c2",   "13c2-S2-執行版-下-狀態檔與指令.md",          "執行版下：狀態檔代管／稽核／指令用法"),
    ("13c3",   "13c3-S2-執行版-下-收工與防卡.md",            "執行版下：品質掃／防卡／建檔輪／收工清單總表"),
]

# 高風險規則：掉了不會有錯誤訊息，只會某天某站靜靜地做錯
# （沿用「省Token計畫 Task 4 Step 3 完整性對照測試」的要求）
CRITICAL = [
    ("摘要 150 字硬上限",        "硬上限150字"),
    ("大分類清單權威樣板",        "======話題======"),
    ("大分類歸位通則",            "清單越前面＝優先層級越高"),
    ("地緣格主體歸屬制",          "主體歸屬制"),
    ("開新中主題前必跑 list-topics", "開新中主題前必跑"),
    ("小分題要夠粗",              "不要一則一個"),
    ("NS 沒稿也要收",             "沒稿也要收"),
    ("CNN GMT 換算口訣",          "CNN 換算口訣"),
    ("RT 連讀口訣",               "列表最新 → 點進去 → Next 往早"),
    ("RT 禁則 LOAD MORE",         "LOAD MORE"),
    ("BITE 必寫講者",             "必寫講者"),
    ("分隔符 ▎不加空格",          "分隔符用全形直線"),
    ("per-source 數量回報",       "per-source 數量回報"),
    ("素材編號前的時段標記",       "素材編號前的時段標記"),
    ("_待整併 交件夾",            "_待整併"),
    ("烏俄固定兩中主題",          "【烏打俄】"),
    ("畫面亮點 🔖",               "畫面亮點標記"),
    ("三站入口 NS 網址",          "newsource.ns.cnn.com"),
    ("狀態檔代管禁直接開 JSON",    "agent 禁止直接開 JSON"),
    ("每輪稽核 s2_audit",         "s2_audit.py"),
    ("render 前中小分題檢視",      "s2_topic_review.py"),
    ("防卡設計",                  "防卡"),
    ("建檔輪額外動作",            "建檔輪"),
]


def main():
    quiet = "--quiet" in sys.argv
    bad = []
    blob = ""
    required = REQUIRED

    if not quiet:
        print("=== 必讀規則檔（估計載入量須 < %s）=== V8 五層合一，無版本切換制"
              % f"{SAFE_BUDGET:,}")
    for tag, fname, desc in required:
        path = os.path.join(C, fname)
        if not os.path.isfile(path):
            bad.append(f"缺檔：{fname}")
            print(f"  ❌ 缺檔 {fname}")
            continue
        txt = open(path, encoding="utf-8").read()
        blob += txt
        nlines = txt.count("\n") + 1
        est = len(txt) + nlines * 5
        over = est >= SAFE_BUDGET
        has_eof = f"RULES-EOF {tag} " in txt
        if over:
            bad.append(f"{fname} 估計載入 {est:,} ≥ 預算 {SAFE_BUDGET:,}（會被截斷）")
        if not has_eof:
            bad.append(f"{fname} 檔尾缺 RULES-EOF {tag}")
        if not quiet:
            mark = "❌" if (over or not has_eof) else "✅"
            print(f"  {mark} {tag:<5}{fname:<36}{len(txt):>7} 字元 {nlines:>4} 行 "
                  f"估計載入 {est:>7,}  EOF{'有' if has_eof else '無'}")
            print(f"        {desc}")

    if not quiet:
        print("\n=== 高風險規則存在性 ===")
    for name, needle in CRITICAL:
        if needle not in blob:
            bad.append(f"高風險規則不見了：{name}（找不到「{needle}」）")
            print(f"  ❌ {name}")
        elif not quiet:
            print(f"  ✅ {name}")

    print()
    if bad:
        print(f"❌ 規則載入檢查未通過（{len(bad)} 項）——⛔ 不要開始掃帶，先回報使用者：")
        for b in bad:
            print(f"   - {b}")
        return 1
    print("✅ 規則載入檢查全過。讀完每一份時，記得對照這 %d 個 RULES-EOF 代號："
          % len(required))
    print("   " + "／".join(t for t, _, _ in required))
    return 0


if __name__ == "__main__":
    sys.exit(main())
