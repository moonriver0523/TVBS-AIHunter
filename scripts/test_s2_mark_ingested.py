#!/usr/bin/env python3
"""s2_mark_ingested.py 的測試（MASTER A9 子項⑤）。

核心案例：ABC／ENEX 候選 `.txt` 裡的排除清單項目（`skipped`）不該被通用代碼
比對誤判成「還沒入庫」而擋下改名（18 檔「與 s2_mark_ingested.py 的分工」節
記錄的實錯）。修法是信任候選 JSON 的 `skipped` 陣列，不猜 txt 的段落標頭。

用法：python scripts/test_s2_mark_ingested.py
"""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mi = load("s2_mark_ingested")

TMP = tempfile.mkdtemp(prefix="s2_mark_ingested_test_")
results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"　{extra}" if extra and not cond else ""))


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def run_main(argv):
    old_argv = sys.argv
    sys.argv = ["s2_mark_ingested.py"] + argv
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            rc = mi.main()
    finally:
        sys.argv = old_argv
    return rc, buf.getvalue()


# --- fixture：一份 ABC 候選 txt + state.json，含一筆已收錄、一筆被排除 ---
pending = os.path.join(TMP, "_待整併")
os.makedirs(pending, exist_ok=True)

write(
    os.path.join(pending, "0826-ABC.txt"),
    "ABC082601 (ABC …) (BITE) ▎畫面：…▎00:30\n"
    "排除清單：\n"
    "ABC082602 (skip:體育)\n",
)
write_json(
    os.path.join(pending, "0826-ABC-state.json"),
    {
        "window_start": "2026-08-26 00:00", "window_end": "2026-08-26 12:00",
        "checkpoint": "0826-1200", "source": "ABC",
        "merged_into_handover": False, "reviewed": False,
        "counts": {"掃描": 2, "收錄": 1, "排除": 1},
        "skipped": [{"id": "ABC082602", "why": "skip:體育"}],
        "needs_review": [], "known_gaps": [],
        "items": [{
            "id": "ABC082601", "source": "ABC",
            "first_seen_checkpoint": "0826-1200", "script_status": "has_script",
            "raw_entry": "ABC082601 (ABC …) (BITE) ▎畫面：…▎00:30",
            "category": {"大分類": "美國", "中主題": "測試", "小分題": "測試"},
            "sb_count": 1, "src_text": "x" * 60,
            "abc": {"detailId": "1", "slug": "s", "storyNumber": "082601"},
        }],
    },
)

# 正式狀態檔：ABC082601 已入庫，ABC082602（被排除的那筆）本來就不該在裡面
main_state = os.path.join(TMP, "0826-s2-state.json")
write_json(main_state, {"items": [{"id": "ABC082601"}]})

rc, out = run_main(["--file", main_state, "--pending", pending])
check("排除清單項目不會被誤判成缺件（有修：全部視為已入庫）",
      "✅ 已全部入庫" in out and "⚠️" not in out, out)
check("離開碼 0", rc == 0, f"rc={rc}")

# --- 對照組：companion json 找不到時退回原行為（仍會誤判，證明修法只在有 companion 時生效） ---
pending2 = os.path.join(TMP, "_待整併2")
os.makedirs(pending2, exist_ok=True)
write(
    os.path.join(pending2, "0826-ENEX.txt"),
    "ENEX082601 (ENEX …) (PKG) ▎畫面：…▎00:45\n"
    "ENEX082699 (skip:體育)\n",
)
# 沒有 0826-ENEX-state.json
state2 = os.path.join(TMP, "0826-s2-state2.json")
write_json(state2, {"items": [{"id": "ENEX082601"}]})
rc2, out2 = run_main(["--file", state2, "--pending", pending2])
check("沒有 companion json 時退回原行為（仍列缺件，不誤判成已修好）",
      "⚠️" in out2 and "ENEX082699" in out2, out2)

# --- --apply 端到端：確認排除清單不擋改名 ---
rc3, out3 = run_main(["--file", main_state, "--pending", pending, "--apply"])
renamed = os.path.exists(os.path.join(pending, "已入庫_0826-ABC.txt"))
check("--apply 實際改名成功（排除清單不再擋改名）", renamed, out3)

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nPASS={sum(results)} FAIL={len(results) - sum(results)}")
sys.exit(0 if all(results) else 1)
