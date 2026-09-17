#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""項目4：src_text 寫入前硬閘及 compare gate 測試（2026-09-17）。"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_SCRIPT = os.path.join(HERE, "s2_state.py")
BP_SCRIPT = os.path.join(HERE, "s2_batch_prep.py")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

results = []


def check(name, cond, extra=""):
    results.append(bool(cond))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {extra}" if extra else ""))


def new_dirs():
    d = tempfile.mkdtemp(prefix="s2_src_gate_")
    sp = os.path.join(d, "0917-s2-state.json")
    rp = os.path.join(d, "registry.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump({"date": "0917", "checkpoint": "0917-1200", "items": []}, f, ensure_ascii=False)
    with open(rp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "topics": []}, f, ensure_ascii=False)
    return sp, rp, d


def run_state(state_path, registry_path, *args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, "-X", "utf8", STATE_SCRIPT, "--file", state_path, "--registry", registry_path, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run_bp(*args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, "-X", "utf8", BP_SCRIPT, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
    )
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_state(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    items = d.get("items") or []
    if isinstance(items, list):
        d["items"] = {x.get("id"): x for x in items if isinstance(x, dict)}
    return d


# 1. 正常 RT/AP/NS 皆有純站方英文原文 -> 正常寫入 exit 0
sp, rp, d = new_dirs()
valid_batch = write_json(os.path.join(d, "valid.json"), {
    "entries": [
        {"id": "RT1001", "source": "RT", "checkpoint": "0917-1200", "status": "has_script",
         "entry": "RT1001 (地方) ▎摘要。▎畫面：資料畫面。無BITE。", "src_text": "STORY: Valid story text"},
        {"id": "AP1234567", "source": "AP", "checkpoint": "0917-1200", "status": "has_script",
         "entry": "AP1234567 (地方) ▎摘要。▎畫面：資料畫面。無BITE。", "src_text": "SCRIPT: Valid AP script text"},
        {"id": "WE-006WE", "source": "NS", "checkpoint": "0917-1200", "status": "has_script",
         "entry": "WE-006WE (地方) ▎摘要。▎畫面：資料畫面。無BITE。", "src_text": "DESC: Valid NS description\nSCRIPT: content"},
    ],
    "new_topics": {}
})
code, out = run_state(sp, rp, "add-batch", "--entries", valid_batch)
check("正常三站素材帶合規 src_text -> exit 0", code == 0, out[-300:])
st = load_state(sp)
check("正常三站素材全部成功寫入", len(st["items"]) == 3)

# 2. 缺漏 src_text（任一筆缺少、空字串、全空白）-> exit 2 擋下，零寫入
bad_missing_cases = [
    ("缺少 src_text 鍵", {"id": "RT1002", "source": "RT", "checkpoint": "0917-1200", "status": "has_script", "entry": "e"}),
    ("src_text 為空字串", {"id": "RT1003", "source": "RT", "checkpoint": "0917-1200", "status": "has_script", "entry": "e", "src_text": ""}),
    ("src_text 為全空白", {"id": "RT1004", "source": "RT", "checkpoint": "0917-1200", "status": "has_script", "entry": "e", "src_text": "   \n  "}),
]
for label, bad_item in bad_missing_cases:
    sp_m, rp_m, d_m = new_dirs()
    batch_m = write_json(os.path.join(d_m, "missing.json"), {
        "entries": [
            {"id": "RT1001", "source": "RT", "checkpoint": "0917-1200", "status": "has_script", "entry": "e", "src_text": "ok text"},
            bad_item,
        ],
        "new_topics": {}
    })
    code, out = run_state(sp_m, rp_m, "add-batch", "--entries", batch_m)
    check(f"缺 src_text 攔截（{label}）-> exit 2", code == 2 and "⛔ src_text 寫入前硬閘" in out, out[-300:])
    st_m = load_state(sp_m)
    check(f"缺 src_text 攔截時 state 完全無寫入（{label}）", len(st_m["items"]) == 0)

# 3. 尾端混入中文 agent 說明 -> exit 2 擋下
sp_c, rp_c, d_c = new_dirs()
batch_contam = write_json(os.path.join(d_c, "contam.json"), {
    "entries": [
        {"id": "RT4131", "source": "RT", "checkpoint": "0917-1200", "status": "has_script", "entry": "e",
         "src_text": "STORY: Headline text\n（說明：sb_count=0 係因路透 captioned 格式…）"},
    ],
    "new_topics": {}
})
code, out = run_state(sp_c, rp_c, "add-batch", "--entries", batch_contam)
check("混入中文 agent 說明 -> exit 2 擋下", code == 2 and "混入 agent 說明" in out, out[-300:])
st_c = load_state(sp_c)
check("污染 src_text 未寫入 state", len(st_c["items"]) == 0)

# 4. --allow-missing-src-text 放行缺漏，但自動掛 needs_review
sp_rec, rp_rec, d_rec = new_dirs()
batch_rec = write_json(os.path.join(d_rec, "rec.json"), {
    "entries": [
        {"id": "RT1005", "source": "RT", "checkpoint": "0917-1200", "status": "has_script",
         "entry": "RT1005 (地方) ▎摘要。▎畫面：資料畫面。無BITE。"},
    ],
    "new_topics": {}
})
code, out = run_state(sp_rec, rp_rec, "add-batch", "--entries", batch_rec, "--allow-missing-src-text")
check("--allow-missing-src-text 放行缺漏素材 -> exit 0", code == 0, out[-300:])
st_rec = load_state(sp_rec)
check("--allow-missing-src-text 成功寫入並標註 needs_review",
      "src_text_missing" in st_rec["items"].get("RT1005", {}).get("needs_review", ""))

# 5. 污染的 src_text 即使帶 --allow-missing-src-text 仍拒絕
sp_rec_bad, rp_rec_bad, d_rec_bad = new_dirs()
code, out = run_state(sp_rec_bad, rp_rec_bad, "add-batch", "--entries", batch_contam, "--allow-missing-src-text")
check("污染 src_text 帶 recovery flag 仍拒絕 -> exit 2", code == 2 and "混入 agent 說明" in out, out[-300:])

# 6. 非 GATED_SOURCES（如 YT/ENEX/ABC）不受三站 src_text gate 阻擋
sp_non, rp_non, d_non = new_dirs()
batch_non = write_json(os.path.join(d_non, "non_gated.json"), {
    "entries": [
        {"id": "ENEX12345", "source": "ENEX", "checkpoint": "0917-1200", "status": "has_script",
         "entry": "ENEX12345 (地方) ▎摘要。▎畫面：資料畫面。無BITE。"},
    ],
    "new_topics": {}
})
code, out = run_state(sp_non, rp_non, "add-batch", "--entries", batch_non)
check("非 GATED_SOURCES 不受三站 src_text 硬閘限制 -> exit 0", code == 0, out[-300:])

# 7. build compare gate：當 batch 缺欄位（如缺 src_text）時，build 與 build --dry-run 均拒絕產生 batch.json
d_bld = tempfile.mkdtemp(prefix="s2_bld_cmp_")
skel_file = write_json(os.path.join(d_bld, "skel.json"), [
    {"id": "RT6001", "source": "RT", "checkpoint": "0917-1200", "status": "has_script",
     "src_text": "", "sb_count": 0, "entry": "", "category": "", "tc": ""}
])
entries_file = write_json(os.path.join(d_bld, "entries.json"), {
    "RT6001": {"entry": "RT6001 (地方) ▎摘要。▎畫面：資料畫面。無BITE。"}
})
bld_out = os.path.join(d_bld, "bld_out.json")

code, out = run_bp("build", "--site", "rt", "--raw", skel_file, "--skeleton", skel_file,
                   "--entries", entries_file, "--checkpoint", "0917-1200", "--out", bld_out)
check("build compare gate 阻擋缺 src_text -> exit 2", code == 2 and "⛔ build 比對門檻未通過" in out, out[-300:])
check("build 阻擋時不寫入 batch 輸出檔", not os.path.exists(bld_out))

# dry-run 也阻擋
code_d, out_d = run_bp("build", "--site", "rt", "--raw", skel_file, "--skeleton", skel_file,
                       "--entries", entries_file, "--checkpoint", "0917-1200", "--out", bld_out, "--dry-run")
check("build --dry-run 遇 compare 失敗亦 exit 2", code_d == 2 and "⛔ build 比對門檻未通過" in out_d, out_d[-300:])

# 8. standalone compare 抓到污染 src_text -> exit 1
cmp_raw = write_json(os.path.join(d_bld, "cmp_raw.json"), [
    {"code": "RT7001", "head": "h", "story": "s"}
])
cmp_batch_contam = write_json(os.path.join(d_bld, "cmp_batch_contam.json"), [
    {"id": "RT7001", "source": "RT", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "RT7001 (地方) ▎摘要。▎畫面：資料畫面。無BITE。", "src_text": "STORY: text\n（說明：中文備註）"}
])
code_c, out_c = run_bp("compare", "--site", "rt", "--raw", cmp_raw, "--batch", cmp_batch_contam)
check("standalone compare 抓到污染 src_text -> exit 1", code_c == 1 and "src_text 格式錯誤" in out_c, out_c[-300:])

print(f"\nPASS={sum(results)} FAIL={len(results) - sum(results)}")
sys.exit(0 if all(results) else 1)
