#!/usr/bin/env python3
"""s2_platform_merge.py — ENEX／ABC 候選檔 → `s2_state.py` 整併輸入（MASTER A9 子項③）。

🔴 **為什麼需要這支**：三站有 `s2_batch_prep.py` 做「raw → batch.json」的轉換層，
ENEX／ABC 這一段**完全沒有工具**——0817 那批 42 則的整併，是整併端當場手寫一支
一次性 Python 讀候選 JSON、組出 entries 陣列與 category pairs 字串再呼叫
`s2_state.py`。每次整併都重刻一次，正是 A9 落差報告 §4 點名的缺口。

⚠️ **獨立流程，不併入三站掃帶輪**（2026-08-18 使用者訂）：本腳本不被 `s2_scan.ps1`
呼叫、不寫規則、不 render。預設**只產檔＋印指令**，要它自己動狀態檔得明講 `--apply`。

## 為什麼 `--apply` 要一直檢查鎖檔

狀態檔 `os.replace` 寫入**沒有檔案鎖**，跟每 2 小時一輪的掃帶輪同時寫會互相蓋掉
（18 檔 §0 記過 2026-08-10 一次 44 處差點被無聲覆蓋）。所以 `--apply` 在**每一次**
呼叫 `s2_state.py` 之前都重查一次鎖檔，不是開頭查一次就放行。

🔴 **例外：`--in-round`（2026-08-31，V5 四站）**——ENEX 進固定輪之後，本腳本會由
**掃帶輪內的 agent** 呼叫，而那把鎖正是該輪自己握著的，護欄會 100% 誤擋。
帶 `--in-round` 才略過這道檢查。⛔ 人工流程一律不要帶。

⛔ **判活只看檔案存在，絕不 open 鎖檔**：`s2_scan.ps1` 用 `FileShare::None` 獨佔開啟，
去讀它會讓**正要啟動的那一輪直接 SKIP**——為了偵測衝突而製造衝突（同 A5 看門狗
踩過的坑）。存在性檢查與實際寫入之間仍有秒級 TOCTOU 窗口，以 2 小時輪距來說可接受；
真要零風險就等掃帶輪之間的空檔跑。

離開碼：0＝成功｜1＝lint 有必修項／鎖檔存在／s2_state 失敗｜**2＝讀不到（不是「沒差異」）**。

用法：
    # 只產檔（預設）——產出 entries.json ＋ pairs.txt，印出可直接貼的兩行指令
    python scripts/s2_platform_merge.py "…\\_待整併\\0818-ABC-state.json"

    # 直接整併進狀態檔
    python scripts/s2_platform_merge.py 候選.json --apply --file "…\\0818-s2-state.json"
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

# 🔴 同 `s2_platform_lint.py`：本機 python stdout 預設 cp950，印 ⛔ 會
# UnicodeEncodeError。工具在裸 PowerShell 就要能跑，不能要求先設環境變數。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

LOCK = os.path.join(os.environ.get("USERPROFILE") or os.path.expanduser("~"),
                    ".s2-scan.lock")
# entries 每筆帶進 add-batch 的欄位。⚠️ 候選檔的鍵名與 add-batch 的參數名不同
# （first_seen_checkpoint→checkpoint、script_status→status、raw_entry→entry），
# 這層對照就是本腳本存在的理由，別在別處再抄一份。
FIELD_MAP = {"checkpoint": "first_seen_checkpoint", "status": "script_status",
             "entry": "raw_entry"}


def load_lint():
    spec = importlib.util.spec_from_file_location(
        "s2_platform_lint", os.path.join(HERE, "s2_platform_lint.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_candidate(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"⛔ 候選檔讀取失敗（{e}）\n   檔案：{path}")


def build(data):
    """候選 JSON → (entries 陣列, pairs 字串, 報告用的雜項)。

    ⚠️ 不合格的單筆**不靜默丟掉**：沒有 raw_entry／沒有 id 的會進 `dropped`，
    沒有 category 的照樣入庫但進 `uncat`（分類可以事後補，素材消失補不回來）。
    """
    entries, pairs, dropped, uncat, no_src = [], [], [], [], []
    for n, it in enumerate(data.get("items") or [], 1):
        if not isinstance(it, dict):
            dropped.append(f"第{n}筆: 不是物件")
            continue
        i = str(it.get("id") or "").strip()
        entry = it.get("raw_entry")
        miss = [k for k, src in FIELD_MAP.items() if not it.get(src)]
        if not i or miss:
            dropped.append(f"{i or f'第{n}筆'}: 缺 {'、'.join(miss) or 'id'}"
                           f"（候選檔欄位 {'、'.join(FIELD_MAP[k] for k in miss) or 'id'}）")
            continue
        e = {"id": i, "source": it.get("source") or data.get("source"),
             "checkpoint": it[FIELD_MAP["checkpoint"]],
             "status": it[FIELD_MAP["status"]], "entry": entry}
        # sb_count／src_text 有就帶：add-batch 會把它們存進狀態檔，稽核③ 與離線
        # 查證都靠這兩個欄位。src_text 目前兩站都沒有（A9 子項⑧），所以要點名。
        if isinstance(it.get("sb_count"), int):
            e["sb_count"] = it["sb_count"]
        if it.get("src_text"):
            e["src_text"] = it["src_text"]
        else:
            no_src.append(i)
        # 站台專屬 metadata（`enex`／`abc` 那包：newslinkId／partner／時長／slug…）
        # 🔴 2026-09-01 實錯：這裡原本只組固定幾個欄位，那包**整個沒帶過去**，
        # 於是 extract 量到的東西一路活到候選檔就消失。AP／RT 沒事是因為它們的
        # 時長寫在 raw_entry 文字裡，ENEX 的只活在子物件裡——一整併就蒸發。
        # 收成單一 `platform` 鍵而不是各站各長一個鍵：狀態檔的欄位不必每加一站就長一個。
        for site_key in ("enex", "abc"):
            sub = it.get(site_key)
            if isinstance(sub, dict) and sub:
                e["platform"] = dict(sub, site=site_key.upper())
                break
        entries.append(e)
        cat = it.get("category")
        if not isinstance(cat, dict) or not str(cat.get("大分類") or "").strip():
            uncat.append(i)
            continue
        parts = [str(cat.get(k) or "").strip() for k in ("大分類", "中主題", "小分題")]
        parts = [p for p in parts if p]
        bad = [c for c in ";=/" if any(c in p for p in parts)]
        if bad:
            # 護欄：帶原始值明確失敗，不要靜默切壞成假的小分題
            raise SystemExit(f"⛔ {i} 的分類含 {'／'.join(bad)}，"
                             f"set-category --pairs 會被切錯\n   原值：{cat}")
        pairs.append(f"{i}={'/'.join(parts)}")
    return entries, ";".join(pairs), {"dropped": dropped, "uncat": uncat,
                                      "no_src": no_src}


def out_paths(cand, out_dir=None):
    """輸出檔預設落在**候選檔旁**，不是 CWD。

    R13 連三輪再犯的坑就是這個形狀（中間檔先落在當下工作目錄，再搬一次），
    這裡從一開始就不給它機會。
    """
    d = out_dir or os.path.dirname(os.path.abspath(cand))
    base = os.path.basename(cand)
    stem = base[:-len("-state.json")] if base.endswith("-state.json") else \
        os.path.splitext(base)[0]
    return (os.path.join(d, f"{stem}-entries.json"),
            os.path.join(d, f"{stem}-pairs.txt"))


def write_out(path, body, overwrite):
    """⛔ 已存在一律不覆寫——覆寫等於靜默銷毀上一次整併的依據（同 snapshot 的規矩）。"""
    if os.path.exists(path) and not overwrite:
        raise SystemExit(f"⛔ {path} 已存在，不覆寫（要覆寫請明講 --overwrite）")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def lock_busy():
    """存在＝掃帶輪可能正在寫狀態檔。⛔ 只看存在，不 open（open 會害那一輪 SKIP）。"""
    return os.path.exists(LOCK)


def run_state(state_file, args, dry, in_round=False):
    cmd = [sys.executable, os.path.join(HERE, "s2_state.py"),
           "--file", state_file] + args
    if dry:
        return 0, " ".join(f'"{c}"' if " " in c else c for c in cmd)
    if in_round:
        # 🔴 V5（2026-08-31）：ENEX 進固定掃帶輪之後，這支會**在輪次內**被呼叫。
        # 而 `s2_scan.ps1:301-304` 在叫 claude 之前就用 FileShare::None 開了鎖檔、
        # 一路握到 finally——所以輪次內鎖檔**必定存在**，下面那道護欄會 100% 誤擋。
        # `--in-round` 就是呼叫端明說「握著鎖的就是我自己」。
        # ⛔ 人工流程永遠不要帶這個旗標：那道護欄對人工流程仍然必要
        #    （18 檔 §0 記過 0810 一次 44 處差點被無聲覆蓋）。
        pass
    elif lock_busy():
        print(f"⛔ 偵測到掃帶鎖檔 {LOCK}——掃帶輪可能正在寫狀態檔，中止。\n"
              f"   狀態檔沒有檔案鎖，同時寫會靜靜蓋掉對方（18 檔 §0，0810 實例 44 處）。\n"
              f"   等該輪跑完（約 19 分）再重跑本指令。")
        return 1, ""
    # 子行程也要吃 UTF-8：`s2_state.py` 的訊息含 ⛔／⚠️，在 cp950 的預設下
    # 它自己 print 就會炸（我們是用 utf-8 解它的輸出，不設等於兩邊講不同語言）。
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    print(p.stdout or "", end="")
    if p.stderr:
        print(p.stderr, end="")
    return p.returncode, ""


def mark_merged(cand, data, checkpoint):
    """整併成功後把候選檔的 `merged_into_handover` 翻成 true。

    18 檔 §2 說「整併端事後改 true」——`--apply` 的情境下整併端就是這支腳本。
    不翻的話，下一個 agent 分不出哪份候選檔已經進過狀態檔，重跑一次就是重複入庫
    （add-batch 會擋 id 重複，但那時候已經在追一個不存在的問題了）。
    `reviewed` 刻意**不動**：那是人看過的意思，工具不能替人蓋章。
    """
    data["merged_into_handover"] = True
    data.setdefault("merged_log", []).append(
        {"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         "by": "s2_platform_merge.py", "checkpoint": checkpoint})
    tmp = cand + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, cand)


def report(data, misc, entries_path, pairs_path, pairs):
    site = data.get("source")
    print(f"\n── {site} 候選 → 整併輸入 ──")
    print(f"素材 {len(misc['entries'])} 則｜分類 pairs {pairs.count('=') if pairs else 0} 筆")
    print(f"  entries：{entries_path}")
    print(f"  pairs  ：{pairs_path}")
    if misc["dropped"]:
        print(f"\n⛔ 未納入 {len(misc['dropped'])} 筆（缺必要欄位，**不是靜默丟掉**）：")
        print("\n".join("  " + x for x in misc["dropped"]))
    if misc["uncat"]:
        print(f"\n⚠️ 無分類 {len(misc['uncat'])} 則（照樣入庫，事後補 set-category）："
              f"{'、'.join(misc['uncat'])}")
    if misc["no_src"]:
        print(f"\n⚠️ 缺 src_text {len(misc['no_src'])} 則（18 檔 §2 起為必帶；"
              f"入庫後 add-batch 會再喊一次，離線查證會沒有原文可比對）")
    # 候選檔的三處人工註記：不轉成 needs-review 就會在整併時整批蒸發。
    notes = []
    for k in ("needs_review", "known_gaps"):
        for x in data.get(k) or []:
            notes.append(f"[{k}] {x}")
    for it in data.get("items") or []:
        if isinstance(it, dict) and it.get("needs_review_note"):
            notes.append(f"[{it.get('id')}] {it['needs_review_note']}")
    if notes:
        print(f"\n📌 候選檔的人工註記 {len(notes)} 條——**整併時不會自動跟著進狀態檔**，"
              f"請逐條決定要不要 `s2_state.py needs-review add`：")
        print("\n".join("  " + x for x in notes))


def main():
    ap = argparse.ArgumentParser(
        description="ENEX／ABC 候選檔 → add-batch／set-category 輸入（獨立流程）")
    ap.add_argument("candidate", help="候選檔 {MMDD}-{站}-state.json")
    ap.add_argument("--out-dir", help="輸出目錄（預設＝候選檔所在目錄）")
    ap.add_argument("--apply", action="store_true",
                    help="產檔後直接呼叫 s2_state.py add-batch＋set-category")
    ap.add_argument("--file", help="--apply 用：正式狀態檔路徑（不給就用 s2_state 預設）")
    ap.add_argument("--overwrite", action="store_true", help="允許覆寫既有輸出檔")
    ap.add_argument("--force", action="store_true",
                    help="lint 有必修項／候選檔已整併過時仍繼續（要有明確理由）")
    ap.add_argument("--skip-lint", action="store_true", help="不跑 lint（不建議）")
    ap.add_argument("--in-round", action="store_true",
                    help="**只有掃帶輪內的 agent 可以用**（V5 四站）：略過鎖檔檢查，"
                         "因為那把鎖就是本輪自己握著的。⛔ 人工流程不要帶")
    ap.add_argument("--allow-missing-src-text", action="store_true",
                    help="轉給 lint：缺 src_text 降回 ⚠️（只給 0818 規則生效前的舊檔）")
    args = ap.parse_args()

    data = read_candidate(args.candidate)
    if not args.skip_lint:
        err, warn = load_lint().lint(args.candidate, args.allow_missing_src_text)
        if err:
            print(f"❌ lint 有 {len(err)} 項必修（先修再整併，或 --force 硬上）：")
            print("\n".join("  " + x for x in err))
            if not args.force:
                return 1
            print("⚠️ --force：帶著上述問題繼續整併")
        elif warn:
            print(f"⚠️ lint 提醒 {len(warn)} 項（不擋整併）：")
            print("\n".join("  " + x for x in warn))

    if data.get("merged_into_handover") is True or \
            os.path.basename(args.candidate).startswith("已入庫_"):
        msg = ("⚠️ 這份候選檔看起來已經整併過"
               "（merged_into_handover=true 或檔名帶「已入庫_」）")
        if args.apply and not args.force:
            print(f"{msg}——拒絕 --apply，避免重複入庫（確定要重跑請加 --force）")
            return 1
        print(msg)

    entries, pairs, misc = build(data)
    misc["entries"] = entries
    if not entries:
        print("⛔ 沒有任何可整併的素材（items 全空或全數缺欄位）")
        return 1

    entries_path, pairs_path = out_paths(args.candidate, args.out_dir)
    write_out(entries_path, json.dumps(entries, ensure_ascii=False, indent=2),
              args.overwrite)
    write_out(pairs_path, pairs, args.overwrite)
    report(data, misc, entries_path, pairs_path, pairs)

    state_file = args.file
    add_args = ["add-batch", "--entries", entries_path]
    cat_args = ["set-category", "--pairs", pairs] if pairs else None
    if not args.apply:
        # ⚠️ 這裡刻意印 `python scripts/s2_state.py` 而不是 sys.executable 的絕對路徑——
        # 直譯器路徑因機器而異（本機就有 hermes venv 的 python 會被抓到），
        # 貼給別人時會直接壞掉。
        sf = state_file or "{狀態檔}"
        print("\n▶ 下一步（未加 --apply，以下指令請自行確認狀態檔路徑後執行）：")
        print(f'  python scripts/s2_state.py --file "{sf}" '
              f'add-batch --entries "{entries_path}"')
        if cat_args:
            print(f'  python scripts/s2_state.py --file "{sf}" set-category '
                  f'--pairs "{{貼上 {os.path.basename(pairs_path)} 的內容}}"')
            print(f"    PowerShell 可直接展開："
                  f'--pairs "$(Get-Content -Raw "{pairs_path}")"')
        print("\n▶ 整併完**要跑** `python scripts/s2_topic_dedupe.py --file {狀態檔}`"
              "——18 檔 §7 的收尾步驟，不是選配")
        return 0

    if not state_file:
        print("⛔ --apply 請明確帶 --file 指定狀態檔（不猜，避免寫錯班次那份）")
        return 1
    if args.in_round:
        print("ℹ️ --in-round：略過鎖檔檢查（掃帶輪自己握著 .s2-scan.lock）")
    rc, _ = run_state(state_file, add_args, dry=False, in_round=args.in_round)
    if rc != 0:
        print(f"⛔ add-batch 失敗（離開碼 {rc}），停手，不做 set-category")
        return 1
    if cat_args:
        rc, _ = run_state(state_file, cat_args, dry=False, in_round=args.in_round)
        if rc != 0:
            print(f"⛔ set-category 失敗（離開碼 {rc}）——素材**已經入庫**，"
                  f"分類要自己補：\n   pairs 在 {pairs_path}")
            return 1
    mark_merged(args.candidate, data, data.get("checkpoint"))
    print(f"\n✅ 整併完成：{len(entries)} 則入庫，候選檔 merged_into_handover 已翻 true")
    print(f"▶ 收尾（18 檔 §7，不是選配）：\n"
          f'  python scripts/s2_topic_dedupe.py --file "{state_file}"\n'
          f"  命中逐條覆核；決定不動就用 needs-review add 留痕，並視需要重 render")
    return 0


if __name__ == "__main__":
    sys.exit(main())
