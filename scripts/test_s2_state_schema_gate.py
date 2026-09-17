#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""項目3：state source/ID schema gate 測試（2026-09-17）。"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "s2_state.py")

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
    d = tempfile.mkdtemp(prefix="s2_schema_gate_")
    sp = os.path.join(d, "0917-s2-state.json")
    rp = os.path.join(d, "registry.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump({"date": "0917", "checkpoint": "0917-1200", "items": []}, f, ensure_ascii=False)
    with open(rp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "topics": []}, f, ensure_ascii=False)
    return sp, rp, d


def run_cmd(state_path, registry_path, *args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, "-X", "utf8", SCRIPT, "--file", state_path, "--registry", registry_path, *args],
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


# 1. 正常各來源素材均可正常寫入
sp, rp, d = new_dirs()
valid_entries = [
    {"id": "RT1001", "source": "RT", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "RT1001 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "RTV1002", "source": "RT", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "RT1002 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "AP1234567", "source": "AP", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "AP1234567 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "APcctv123456", "source": "AP", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "APcctv123456 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "WE-006WE", "source": "NS", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "WE-006WE (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "CNN 09-17 123456", "source": "SIDE_CNN", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "CNN 09-17 123456 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "NHK 123456", "source": "SIDE_NHK", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "NHK 123456 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "YT:abc_123-xyz", "source": "YT", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "YT:abc_123-xyz (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "YNA01", "source": "YT", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "YNA01 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "CNA02", "source": "CNA", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "CNA02 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "ENEX12345", "source": "ENEX", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "ENEX12345 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "ABC12345678", "source": "ABC", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "ABC12345678 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
    {"id": "OTH99", "source": "ReutersConnect", "checkpoint": "0917-1200", "status": "has_script",
     "entry": "OTH99 (地方) ▎摘要。▎畫面：現場。無BITE。", "src_text": "text"},
]
batch_file = write_json(os.path.join(d, "valid_batch.json"), {"entries": valid_entries, "new_topics": {}})
code, out = run_cmd(sp, rp, "add-batch", "--entries", batch_file)
check("正常各來源素材（含 RTV/OTH/相容寫法）add-batch 成功 exit 0", code == 0, out[-300:])
st = load_state(sp)
check("正常素材全部寫入且 RTV1002 正規化為 RT1002",
      "RT1001" in st["items"] and "RT1002" in st["items"] and "WE-006WE" in st["items"] and "OTH99" in st["items"],
      str(list(st["items"].keys())))

# 2. cmd_add 正常寫入與 RTV 正規化
code, out = run_cmd(sp, rp, "add", "--id", "RTV2001", "--source", "RT", "--checkpoint", "0917-1200",
                    "--status", "has_script", "--entry", "RT2001 (地方) ▎單筆。▎畫面：無。無BITE。")
check("cmd_add 支援正常素材寫入 exit 0", code == 0, out[-300:])
st = load_state(sp)
check("cmd_add RTV2001 正規化為 RT2001 入庫", "RT2001" in st["items"])

# 3. 非法 source / placeholder ID / source-ID 不匹配測試
bad_cases = [
    ("CNN_newsource", "CNN_newsource", "source 不在白名單"),
    ("SCRIPT-TODO", "RT", "placeholder ID SCRIPT-TODO"),
    ("CATEGORY-FIX-1", "RT", "placeholder ID CATEGORY-FIX-1"),
    ("RT-MISC-20-30", "RT", "placeholder ID RT-MISC-20-30"),
    ("WE-006WE", "AP", "source=AP 但 ID=WE-006WE（不匹配）"),
    ("RT9999", "INVALID_SOURCE", "source 不合法"),
]

for test_id, test_src, label in bad_cases:
    sp_bad, rp_bad, d_bad = new_dirs()
    code, out = run_cmd(sp_bad, rp_bad, "add", "--id", test_id, "--source", test_src,
                        "--checkpoint", "0917-1200", "--status", "has_script", "--entry", "摘要")
    check(f"cmd_add 攔截非法素材：{label} -> exit 2", code == 2 and "⛔ state schema gate" in out, out[-300:])
    st_bad = load_state(sp_bad)
    check(f"cmd_add 未寫入 state：{label}", len(st_bad["items"]) == 0)

# 4. add-batch 整批 preflight 攔截（一批 3 筆，第 2 筆非法，全不寫入）
sp_b3, rp_b3, d_b3 = new_dirs()
batch_3 = [
    {"id": "RT3001", "source": "RT", "checkpoint": "0917-1200", "status": "has_script", "entry": "RT3001 摘要"},
    {"id": "CATEGORY-FIX-1", "source": "RT", "checkpoint": "0917-1200", "status": "has_script", "entry": "假素材"},
    {"id": "RT3003", "source": "RT", "checkpoint": "0917-1200", "status": "has_script", "entry": "RT3003 摘要"},
]
b3_file = write_json(os.path.join(d_b3, "b3.json"), {
    "entries": batch_3,
    "new_topics": {"新主題": {"charter": "新主題描述", "big": "社會"}}
})
code, out = run_cmd(sp_b3, rp_b3, "add-batch", "--entries", b3_file)
check("add-batch 一批 3 筆中第 2 筆非法 -> 整批 exit 2 擋下", code == 2, str(code))
check("add-batch 錯誤訊息點名 CATEGORY-FIX-1", "CATEGORY-FIX-1" in out, out[-300:])
st_b3 = load_state(sp_b3)
check("add-batch 攔截時 items 保持為空（零部分寫入）", len(st_b3["items"]) == 0)
with open(rp_b3, encoding="utf-8") as f:
    reg_data = json.load(f)
check("add-batch 攔截時 registry 保持為空（new_topics 未登記）", len(reg_data["topics"]) == 0)

# 5. needs-review add 備忘殼例外保留
sp_nr, rp_nr, d_nr = new_dirs()
code, out = run_cmd(sp_nr, rp_nr, "needs-review", "add", "--id", "SCRIPT-TODO", "--note", "待確認稿件")
check("needs-review add 建立 note 殼不受真素材 gate 阻擋 -> exit 0", code == 0, out[-300:])
st_nr = load_state(sp_nr)
check("needs-review add 成功記錄 SCRIPT-TODO note 殼",
      "SCRIPT-TODO" in st_nr["items"] and st_nr["items"]["SCRIPT-TODO"].get("script_status") == "note")

# 6. add-batch 嘗試送入 note 殼假素材 -> 拒絕
batch_note = write_json(os.path.join(d_nr, "note_batch.json"), {
    "entries": [{"id": "RT9990", "source": "RT", "status": "note", "checkpoint": "0917-1200", "entry": ""}],
    "new_topics": {}
})
code, out = run_cmd(sp_nr, rp_nr, "add-batch", "--entries", batch_note)
check("add-batch 拒絕送入 note 殼假素材 -> exit 2", code == 2 and "needs-review add" in out, out[-300:])

print(f"\nPASS={sum(results)} FAIL={len(results) - sum(results)}")
sys.exit(0 if all(results) else 1)
