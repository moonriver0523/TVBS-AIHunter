# -*- coding: utf-8 -*-
"""needs-review 迴歸：備註殼不得灌水 pending，且必須有結案出口。

背景（0803 立案的兩半問題）：
  前半 `add` 對不存在的 id 建 status="pending" 的空殼 → pending 計數虛增
       （0803 早上 60 則裡有 7 則是假的）。已於 ebc324c 改成 status="note"。
  後半 只有 add／list、沒有任何結案方式 → 標記只進不出，resume 每輪重印
       同一批已處理完的項目。本測試連同新增的 `done` 一起鎖住。

用法：python test_s2_needs_review.py
"""
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

ok = True


def report(name, passed, detail=""):
    global ok
    ok = ok and passed
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def run(path, *argv):
    r = subprocess.run([sys.executable, SCRIPT, "--file", path, *argv],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return {it["id"]: it for it in json.load(f)["items"]}


def fresh():
    """建一份含 1 則真素材的狀態檔。"""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"date": "0804", "items": [
            {"id": "AP1234567", "source": "AP", "script_status": "has_script",
             "raw_entry": "AP1234567 (測試) ▎摘要。▎無BITE。▎00:30",
             "compiled": None, "category": None},
        ]}, f, ensure_ascii=False)
    return path


# ── 前半：add 不得灌水 pending ────────────────────────────────────────────
p = fresh()
run(p, "needs-review", "add", "--id", "RT-r9-空白", "--note", "該輪 0 items")
it = read(p)
report("備註殼 status=note 不是 pending",
       it["RT-r9-空白"]["script_status"] == "note",
       f'實際 {it["RT-r9-空白"]["script_status"]!r}')
_, out = run(p, "resume")
report("resume 的 pending 計數不含備註殼", "pending:0" in out, out.strip().splitlines()[0])
report("resume 的待人工計數含備註殼", "待人工:1" in out, out.strip().splitlines()[0])

# ── 後半：done 結案 ───────────────────────────────────────────────────────
rc, out = run(p, "needs-review", "done", "--ids", "RT-r9-空白")
it = read(p)
report("done 刪掉備註殼（不留殼）", rc == 0 and "RT-r9-空白" not in it, out.strip())
_, out = run(p, "needs-review", "list")
report("結案後 list 清空", "(無待人工項目)" in out, out.strip())

# 真素材：結案只脫旗標，素材本身必須留著
run(p, "needs-review", "add", "--id", "AP1234567", "--note", "BITE 待補")
rc, out = run(p, "needs-review", "done", "--ids", "AP1234567")
it = read(p)
report("真素材結案後仍在庫", rc == 0 and "AP1234567" in it, out.strip())
report("真素材結案後脫掉 needs_review", "needs_review" not in it.get("AP1234567", {}))
report("真素材結案後內文未動",
       it.get("AP1234567", {}).get("raw_entry", "").startswith("AP1234567 (測試)"))
report("真素材結案後 status 未被改成 note",
       it.get("AP1234567", {}).get("script_status") == "has_script")

# ── 防呆 ─────────────────────────────────────────────────────────────────
rc, out = run(p, "needs-review", "done", "--ids", "NOT-EXIST")
report("done 遇不存在 id 報錯且不寫檔", rc == 2 and "不存在" in out, out.strip())

rc, out = run(p, "needs-review", "done", "--ids", "AP1234567")
report("done 遇本來就沒標記者報錯", rc == 2 and "本來就沒有" in out, out.strip())

# 全有全無：一批裡有一個壞的，好的那個也不能被處理掉
run(p, "needs-review", "add", "--id", "AP1234567", "--note", "再標一次")
rc, out = run(p, "needs-review", "done", "--ids", "AP1234567,NOT-EXIST")
it = read(p)
report("done 批次含壞 id 時整批不處理（全有全無）",
       rc == 2 and it["AP1234567"].get("needs_review") == "再標一次", out.strip())

rc, out = run(p, "needs-review", "done")
report("done 缺 --ids 報錯", rc == 2 and "需要 --ids" in out, out.strip())

rc, out = run(p, "needs-review", "add")
report("add 缺 --id 報錯（不是 crash）", rc == 2 and "需要 --id" in out, out.strip())

os.unlink(p)
print("\n" + ("全部通過" if ok else "有項目失敗"))
sys.exit(0 if ok else 1)
