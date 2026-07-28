# -*- coding: utf-8 -*-
"""共用解析與工具 — 製片產出（production）流程。

把「完成文稿」解析成配音／剪接／上字都用得到的結構，解析一律沿用
`scripts/validate_sot.py` 的 `parse_ctv`／`split_ctv_body`，不另寫一套
（common/08：驗證與解析要依實際標記，不要用行號猜位置）。
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from validate_sot import parse_ctv, split_ctv_body  # noqa: E402


def slug_from_script(path: str) -> str:
    """`{SLUG} 完成文稿.txt` → `{SLUG}`。"""
    base = os.path.basename(path)
    return re.sub(r"\s*完成文稿\.txt$", "", base)


def load_script(path: str):
    """回傳 (doc, blocks)。

    blocks = [{"bar": 1, "os": [口白行…], "sb": {…} 或 None}, …]，順序即播出順序。
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    doc = parse_ctv(text)
    items = split_ctv_body(doc.body_lines)
    blocks, cur = [], None
    for kind, payload in items:
        if kind == "mark":
            cur = {"bar": payload, "os": [], "sb": None}
            blocks.append(cur)
        elif cur is None:
            continue
        elif kind == "os":
            cur["os"].append(payload)
        else:
            cur["sb"] = payload
    return doc, blocks


def group_os_lines(lines, prefer=2):
    """把一段 OS 的字幕行切成 2–3 行一組（GPT-SoVITS 的甜蜜點，見 production/01）。

    逐句合成品質差、整段合成會跳句，所以固定 2 行一組；行數為奇數時讓
    **最後一組**放 3 行，避免落單的單行組。
    """
    groups = [lines[i:i + prefer] for i in range(0, len(lines), prefer)]
    if len(groups) > 1 and len(groups[-1]) == 1:
        groups[-2] = groups[-2] + groups[-1]
        groups.pop()
    return groups


def parse_tc(tc: str):
    """`MMSS-MMSS` → (起秒, 訖秒)。"""
    m = re.match(r"^(\d{4})-(\d{4})$", tc.strip())
    if not m:
        raise ValueError(f"TC 格式不是 MMSS-MMSS：{tc!r}")
    out = []
    for d in m.groups():
        out.append(int(d[:2]) * 60 + int(d[2:]))
    return out[0], out[1]


def norm_word(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def han_len(s: str) -> int:
    return len(re.sub(r"\s+", "", s))


def run(args, **kw):
    return subprocess.run(args, check=True, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, **kw)


def probe_duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of", "default=nw=1:nk=1", path],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def write_text(path: str, text: str):
    """落檔一律 CRLF（common/08：剪接電腦用記事本開）。"""
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)
