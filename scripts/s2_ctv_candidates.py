# -*- coding: utf-8 -*-
"""s2_ctv_candidates.py — CTV（CNN Newsource 單一 story 全流程寫稿，`cnn/01`）候選清單機械篩
（全檢 2026-09-07 §11／MASTER A34）。

**判準（用狀態檔既有欄位，全部由腳本機械算，不判讀內容）**：
`source=="NS"` ∧ `script_status=="has_script"` ∧ `len(src_text)>=500`（有完整官方稿，
不是備註）∧ `fields.no_bite==False`（有 SOT）∧ `60s<=duration<=210s`（01:00–03:30）
∧ notes 無限制字（`限用|限非|僅授權|不得|禁止|embargo`）。

**排序**：🔴>🟡>🔖>其餘（標記取自 `raw_entry` 行首，同 `s2_validate` 判準），
涉臺（`tc.C` 含「臺灣」）在同層級內前置，🟤（已播）沉底（不論其他標記）。

⛔ **純讀取**：不寫狀態檔、不改任何既有欄位，只印摘要並另存 txt／json 到 `--out`。

用法：
    python s2_ctv_candidates.py --file "…\\0906-s2-state.json" [--out "…\\_稿單提案"]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_render as sr  # noqa: E402  load_state；DEFAULT_FILE 沿用同一份預設狀態檔路徑
import s2_validate as sv  # noqa: E402  🔴／🟡／🔖 標記判準的唯一來源，不重寫一套

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# 限制字（全檢 §11）：符合任一即整則排除，不再細分「哪一種限制」。
RESTRICT_RE = re.compile(r"限用|限非|僅授權|不得|禁止|embargo", re.IGNORECASE)
DUR_RE = re.compile(r"^(\d{1,3}):(\d{2})$")
MIN_SRC_LEN = 500
MIN_DUR_SEC = 60    # 01:00
MAX_DUR_SEC = 210   # 03:30

# 排除原因（依 §11 判準檢查順序；同一則只算第一個命中的原因）
R_NOT_NS = "非NS"
R_INCOMPLETE = "稿未全"     # script_status != has_script，或 src_text 太短，或 fields 缺
R_NO_BITE = "無BITE"
R_DURATION = "時長"
R_RESTRICT = "限制"


def _dur_seconds(s):
    """`MM:SS` → 秒數；解析失敗回 `None`（視同不合格，計入「時長」排除）。"""
    m = DUR_RE.match((s or "").strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def is_candidate(it):
    """回傳 `(合格與否, 排除原因)`；合格時原因為 `None`。"""
    if it.get("source") != "NS":
        return False, R_NOT_NS
    if it.get("script_status") != "has_script":
        return False, R_INCOMPLETE
    if len(it.get("src_text") or "") < MIN_SRC_LEN:
        return False, R_INCOMPLETE
    fields = it.get("fields")
    if not fields:
        return False, R_INCOMPLETE
    if fields.get("no_bite"):
        return False, R_NO_BITE
    sec = _dur_seconds(fields.get("duration"))
    if sec is None or not (MIN_DUR_SEC <= sec <= MAX_DUR_SEC):
        return False, R_DURATION
    notes = " ".join(fields.get("notes") or [])
    if RESTRICT_RE.search(notes):
        return False, R_RESTRICT
    return True, None


def _marks(raw_entry):
    """回傳 `(red, orange, hilite, aired)`：raw_entry 首行行首標記，判準同 `s2_validate`。"""
    line = (raw_entry or "").strip().split("\n")[0]
    rest = sv._after_mark(line)  # 剝掉時段標記 △▲◇■◆●（若有）
    red = bool(sv.RED_RE.match(rest))
    if red:
        rest2 = sv.RED_RE.sub("", rest, count=1)
    else:
        rest2 = rest
    orange = (not red) and bool(sv.SUBALERT_RE.match(rest2))
    if orange:
        rest2 = sv.SUBALERT_RE.sub("", rest2, count=1)
    star = bool(sv.STAR_RE.match(rest2))
    if star:
        rest2 = sv.STAR_RE.sub("", rest2, count=1)
    aired = bool(sv.AIRED_RE.match(rest2))
    if aired:
        rest2 = sv.AIRED_RE.sub("", rest2, count=1)
    hilite = bool(sv.HILITE_RE.match(rest2))
    return red, orange, hilite, aired


def _mark_str(it):
    red, orange, hilite, aired = _marks(it.get("raw_entry"))
    return "".join(m for m in (
        "🔴" if red else ("🟡" if orange else ""),
        "🟤" if aired else "",
        "🔖" if hilite else "",
    ) if m)


def _is_taiwan(it):
    return "臺灣" in ((it.get("tc") or {}).get("C") or [])


def rank_key(it):
    """排序鍵：🟤 沉底最優先考量，其次 🔴>🟡>🔖>其餘，同層級內涉臺前置。"""
    red, orange, hilite, aired = _marks(it.get("raw_entry"))
    tier = 0 if red else (1 if orange else (2 if hilite else 3))
    taiwan = 0 if _is_taiwan(it) else 1
    return (1 if aired else 0, tier, taiwan, str(it.get("id") or ""))


def _title(it):
    notes = (it.get("fields") or {}).get("notes") or []
    return notes[0] if notes else ""


def _restrict_note(it):
    """候選必定已過濾掉限制字；欄位保留給人工核對用（正常應為空字串）。"""
    for n in (it.get("fields") or {}).get("notes") or []:
        if RESTRICT_RE.search(n):
            return n
    return ""


def _txt_row(idx, it):
    fields = it.get("fields") or {}
    cols = [
        str(idx),
        str(it.get("id") or ""),
        _mark_str(it),
        _title(it),
        fields.get("duration") or "",
        str(len(fields.get("bite") or [])),
        _restrict_note(it),
        "、".join((it.get("tc") or {}).get("C") or []),
    ]
    return "｜".join(cols)


def derive_mmdd(state, file_path):
    """`{MMDD}` 檔名前綴：優先狀態檔 `checkpoint`（如 `0906-2200`），
    不成再退回 `--file` 檔名開頭 4 位數字；都沒有就明確失敗（不猜日期）。"""
    ckpt = str(state.get("checkpoint") or "")
    if re.match(r"^\d{4}", ckpt):
        return ckpt[:4]
    base = os.path.basename(file_path)
    m = re.match(r"^(\d{4})", base)
    if m:
        return m.group(1)
    return None


def run(file_path, out_dir=None):
    """核心流程：讀狀態檔 → 機械篩＋排序 → 寫 txt／json（若 `out_dir` 給了）→ 回傳摘要 dict。"""
    raw = sr.load_state(file_path)
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        print("ERROR: 狀態檔 items 不是陣列（非正式 schema）")
        sys.exit(2)

    ns_items = [it for it in items if it.get("source") == "NS"]
    excluded = {R_INCOMPLETE: 0, R_NO_BITE: 0, R_DURATION: 0, R_RESTRICT: 0}
    candidates = []
    for it in ns_items:
        ok, reason = is_candidate(it)
        if ok:
            candidates.append(it)
        else:
            excluded[reason] = excluded.get(reason, 0) + 1

    candidates.sort(key=rank_key)

    mmdd = derive_mmdd(raw, file_path)
    result = {
        "ns_total": len(ns_items),
        "candidate_count": len(candidates),
        "excluded": excluded,
        "candidates": candidates,
        "mmdd": mmdd,
    }

    print(f"NS {len(ns_items)} 則 → 候選 {len(candidates)} 則"
          f"（排除：稿未全 {excluded[R_INCOMPLETE]}／無BITE {excluded[R_NO_BITE]}／"
          f"時長 {excluded[R_DURATION]}／限制 {excluded[R_RESTRICT]}）")

    if out_dir is not None:
        if not mmdd:
            print("ERROR: 無法判斷 {MMDD}（狀態檔缺 checkpoint、檔名也不是 4 位數字開頭），"
                  "不寫檔——請確認 --file 對象正確")
            sys.exit(2)
        os.makedirs(out_dir, exist_ok=True)
        txt_path = os.path.join(out_dir, f"{mmdd}-CTV候選.txt")
        json_path = os.path.join(out_dir, f"{mmdd}-CTV候選.json")
        with open(txt_path, "w", encoding="utf-8") as f:
            for i, it in enumerate(candidates, start=1):
                f.write(_txt_row(i, it) + "\n")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=1)
        print(f"已寫出：{txt_path}")
        print(f"已寫出：{json_path}")
        result["txt_path"] = txt_path
        result["json_path"] = json_path

    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", required=True, help="狀態檔路徑（{MMDD}-s2-state.json）")
    ap.add_argument("--out", default=None,
                     help="輸出目錄（預設：狀態檔同目錄下 _稿單提案/）")
    args = ap.parse_args()

    out_dir = args.out
    if out_dir is None:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(args.file)), "_稿單提案")
    run(args.file, out_dir)


if __name__ == "__main__":
    main()
