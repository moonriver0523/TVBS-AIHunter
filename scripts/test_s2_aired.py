# -*- coding: utf-8 -*-
"""🟤 已播標記迴歸。

最大風險是**標記沒被剝乾淨**：LINE_RE 不 match 的話，該行會從品質掃與檔頭
統計裡整個消失（🔴／△ 上線時各踩過一次），而且是靜默的——數字少算不會報錯。
所以這裡逐項鎖住「🟤 行仍被辨識為素材行」。

用法：python test_s2_aired.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_validate as sv  # noqa: E402
import s2_render as sr    # noqa: E402

STATE_SCRIPT = os.path.join(HERE, "s2_state.py")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


BODY = "AP4676455 (美股) ▎美股大漲逼近紀錄。▎畫面：交易鈴。▎無BITE。▎01:00"

# ── 解析層：四種前綴組合都要被認成素材行 ──────────────────────────────
for pre, want_red, want_aired, label in (
    ("△ ", False, False, "只有時段標記"),
    ("△ 🔴 ", True, False, "時段＋🔴"),
    ("△ 🟤 ", False, True, "時段＋🟤"),
    ("△ 🔴 🟤 ", True, True, "時段＋🔴＋🟤（並存）"),
):
    line = pre + BODY
    mark, rest = sv.strip_mark(line)
    report(f"{label}：剝乾淨後仍 match LINE_RE",
           bool(sv.LINE_RE.match(rest)), repr(rest[:40]))
    report(f"{label}：時段標記正確", mark == "△", repr(mark))
    report(f"{label}：is_red={want_red}", sv.is_red(line) == want_red)
    report(f"{label}：is_aired={want_aired}", sv.is_aired(line) == want_aired)

# 反例：🟤 出現在代碼「之後」不算已播標記（避免摘要內文誤觸）
report("🟤 在代碼之後不算已播標記",
       not sv.is_aired("△ AP4676455 (美股) ▎報導提到 🟤 符號。"))

# ── 檔頭統計：🟤 行必須照常計入則數 ───────────────────────────────────
lines = ["△ " + BODY, "△ 🟤 RT2880 (NYSE) ▎美股開高。▎畫面：開市鐘。▎無BITE。▎00:55"]
hdr = sv.header_from_lines(lines, mmdd="0804")
joined = "\n".join(hdr)
report("🟤 行計入檔頭則數（應為 2 則）", "共2則" in joined, joined)
report("🟤 用到時圖例才出現", "🟤=本台已做過" in joined, joined)
report("沒用到 🟤 時圖例不出現",
       "🟤" not in "\n".join(sv.header_from_lines(["△ " + BODY], mmdd="0804")))

# ── render：欄位與字串兩種來源都要生出 🟤，且不重複 ──────────────────
report("strip_marks 認得 raw_entry 裡手打的 🟤",
       sr.strip_marks("△ 🟤 " + BODY) == (False, True, BODY))

it = {"raw_entry": BODY, "first_seen_checkpoint": "0804-1600", "aired": True}
out = sr.render_item(it, "0804")[0]
report("aired 欄位 → 印出 🟤", "🟤" in out, out[:30])
report("🟤 只印一次（欄位＋字串不重複）",
       sr.render_item({**it, "raw_entry": "🟤 " + BODY}, "0804")[0].count("🟤") == 1)
report("沒有 aired 就不印 🟤",
       "🟤" not in sr.render_item({"raw_entry": BODY,
                                   "first_seen_checkpoint": "0804-1600"}, "0804")[0])
report("🟤 排在時段標記與 🔴 之後",
       sr.render_item({**it, "raw_entry": "🔴 " + BODY}, "0804")[0].startswith("△ 🔴 🟤 "),
       sr.render_item({**it, "raw_entry": "🔴 " + BODY}, "0804")[0][:14])

# ── CLI：set-aired 寫入與取消 ────────────────────────────────────────
fd, p = tempfile.mkstemp(suffix=".json")
os.close(fd)
with open(p, "w", encoding="utf-8") as f:
    json.dump({"date": "0804", "items": [
        {"id": "AP4676455", "source": "AP", "script_status": "has_script",
         "raw_entry": BODY, "compiled": None, "category": None}]}, f, ensure_ascii=False)


def run(*a):
    r = subprocess.run([sys.executable, STATE_SCRIPT, "--file", p, *a],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def item():
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)["items"][0]


rc, out = run("set-aired", "--ids", "AP4676455")
report("set-aired 寫入 aired=True", rc == 0 and item().get("aired") is True, out.strip())
report("set-aired 不動 raw_entry", item()["raw_entry"] == BODY)
rc, out = run("set-aired", "--ids", "AP4676455", "--clear")
report("--clear 移除 aired 欄位", rc == 0 and "aired" not in item(), out.strip())
rc, out = run("set-aired", "--ids", "NOT-EXIST")
report("不存在的 id 報錯不寫檔", rc == 2 and "不存在" in out, out.strip())

os.unlink(p)
print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
