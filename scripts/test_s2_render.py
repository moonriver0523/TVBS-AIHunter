# -*- coding: utf-8 -*-
"""WP1 render 迴歸：拿 0802 真實狀態檔＋定版 txt 對驗收條件逐項檢查。

用法：python regress.py <state.json> <定版.txt> <render產物.txt>
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import s2_validate as sv  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

state_p, ref_p, out_p = sys.argv[1:4]
ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def mat(path, red=False):
    lines = sv.read(path)
    d = {}
    for n, mk, l in sv.material_lines(lines, with_mark=True):
        d[re.match(sv.CODE, l).group(0)] = (mk, sv.is_red(lines[n - 1]), l)
    return d


def sides(path):
    lines, out = sv.read(path), {}
    for n, l, block in sv.side_lines(lines):
        key = re.match(rf"^(CNN|NHK) ({sv._TC})", l).group(0)
        out[key] = lines[n - 1] + "\n" + "\n".join(lines[n:n + len(block)])
    return out


a, b = mat(ref_p), mat(out_p)
common = [c for c in a if c in b]

# 1) 素材行內容零差異（僅比對兩邊都有的則；state 比 txt 新的不算差異）
bad = [c for c in common if a[c][2] != b[c][2]]
report("① 素材行內容零差異", not bad, f"共比對 {len(common)} 則；差異 {len(bad)} 則 {bad[:5]}")

# 2) 時段標記：與定版 txt 全對（△/▲/●）
bad_mk = [(c, a[c][0], b[c][0]) for c in common if a[c][0] != b[c][0]]
n_ov = sum(1 for c in b if b[c][0] in ("▲", "●"))
report("② 時段標記全對", not bad_mk, f"隔夜標記 {n_ov} 則；不符 {bad_mk[:5]}")

# 3) 側錄往返 byte 級一致
sa, sb = sides(ref_p), sides(out_p)
miss = [k for k in sa if k not in sb]
diff = [k for k in sa if k in sb and sa[k] != sb[k]]
report("③ 側錄 byte 級一致", not miss and not diff,
  f"{len(sa)} 段 → {len(sb)} 段；遺失 {miss[:3]}；不一致 {diff[:3]}")

# 3b) 隔夜再 render 一次：側錄不消失，且產物冪等
subprocess.run([sys.executable, os.path.join(HERE, "s2_render.py"), "--file", state_p, "--out", out_p + ".2",
                "--window", "2026-08-02 14:00 - 2026-08-03 09:00", "--base-date", "0802",
                "--no-touch-state", "--force", "--no-check"], check=True, capture_output=True)
s2 = sides(out_p + ".2")
same = open(out_p, encoding="utf-8").read() == open(out_p + ".2", encoding="utf-8").read()
report("③b 隔夜再 render 側錄不消失且冪等", len(s2) == len(sa) and same,
  f"第二次 render 側錄 {len(s2)} 段；兩次產物相同={same}")

# 4) 🔴 標過永久保留
bad_red = [c for c in common if a[c][1] != b[c][1]]
report("④ 🔴 素材標記保留", not bad_red, f"🔴 共 {sum(1 for c in b if b[c][1])} 則；不符 {bad_red[:5]}")

# 4b) 檔頭 🔴 重大提醒行來自狀態檔
st = json.load(open(state_p, encoding="utf-8-sig"))
head_alerts = [l for l in sv.header_lines(sv.read(out_p)) if sv.ALERT_RE.match(l)]
report("④b 檔頭重大提醒行由 _top.alerts 產出",
  len(head_alerts) == len(st.get("alerts") or []) and bool(head_alerts),
  f"狀態檔 {len(st.get('alerts') or [])} 則 → 檔頭 {len(head_alerts)} 行")

# 5) s2_validate check 0 命中
r = subprocess.run([sys.executable, os.path.join(HERE, "s2_validate.py"), "check", out_p],
                   capture_output=True, text=True, encoding="utf-8")
report("⑤ 品質掃 0 命中", r.stdout.startswith("OK"), r.stdout.splitlines()[0] if r.stdout else "")

print("\n" + ("全部通過" if ok else "有未通過項目"))
sys.exit(0 if ok else 1)
