# -*- coding: utf-8 -*-
"""業配／SOT 完成稿解析。不改 scripts/production/。"""
from __future__ import annotations

import os
import re
import subprocess
from types import SimpleNamespace

NS_RE = re.compile(
    r"^NS\s+#(?P<num>\d+)\s+(?P<start>\d{4,6})-(?P<end>\d{4,6})\b(?:\s+(?P<desc>.*))?$"
)
SHOT_RE = re.compile(
    r"^#(?P<num>\d+)\s+TC(?P<tc>\d{4,6})\s+\"(?P<desc>[^\"]*)\""
)
SB_TC_RE = re.compile(
    r"^(?:#(?P<num>\d+)\s+)?(?P<start>\d{4,6})-(?P<end>\d{4,6})\s*$"
)
BAR_CARD_RE = re.compile(r"^BAR\s+([1-4])$")
BAR_MARK_RE = re.compile(r"^BAR([1-4])$")


def mmss_to_sec(d: str) -> float:
    d = d.strip()
    if len(d) == 4:
        return int(d[:2]) * 60 + int(d[2:])
    if len(d) == 6:
        return int(d[:2]) * 3600 + int(d[2:4]) * 60 + int(d[4:])
    raise ValueError(d)


def sec_to_mmss(t: float) -> str:
    t = int(round(t))
    return "%02d%02d" % (t // 60, t % 60)


def slug_from_script(path: str) -> str:
    base = os.path.basename(path)
    return re.sub(r"\s*完成文稿\.txt$", "", base)


def group_os_lines(lines, prefer=2):
    groups = [lines[i:i + prefer] for i in range(0, len(lines), prefer)]
    if len(groups) > 1 and len(groups[-1]) == 1:
        groups[-2] = groups[-2] + groups[-1]
        groups.pop()
    return groups


def split_os_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[。！？])", text)
    return [p.strip() for p in parts if p.strip()]


def char_width(ch: str) -> float:
    import unicodedata
    return 1.0 if unicodedata.east_asian_width(ch) in ("F", "W") else 0.5


def line_width(s: str) -> float:
    return sum(char_width(ch) for ch in s)


def wrap14(text: str, limit: float = 14.0) -> list[str]:
    """CTV 口白折行：每行 ≤14 全形；優先在逗號句號切；殘片（<3）併回上一行。"""
    text = text.strip()
    if not text:
        return []
    lines, buf, acc, last_break = [], "", 0.0, -1
    for i, ch in enumerate(text):
        cw = char_width(ch)
        if buf and acc + cw > limit:
            if last_break >= 1:
                keep, rest = buf[:last_break + 1], buf[last_break + 1:]
                lines.append(keep)
                buf = rest + ch
                acc = line_width(buf)
                last_break = -1
                for j, c2 in enumerate(buf):
                    if c2 in "，。、；！？":
                        last_break = j
            else:
                lines.append(buf)
                buf, acc, last_break = ch, cw, -1
        else:
            buf += ch
            acc += cw
            if ch in "，。、；！？":
                last_break = len(buf) - 1
    if buf:
        lines.append(buf)
    # 殘片「人。」「。」併回
    out = []
    for ln in lines:
        if out and line_width(ln) < 3.0:
            out[-1] += ln
            if line_width(out[-1]) > limit + 1.5:
                # 併完仍過長就維持兩行，但至少不是單標點
                pass
        else:
            out.append(ln)
    return out or [text]


def fit_bar_ctv(title: str, lo: float = 16.5, hi: float = 17.5) -> str:
    """上字 BAR 走 CTV 16.5–17.5；完成稿主標仍可 17.5–18.5。"""
    w = line_width(title)
    if lo <= w <= hi:
        return title
    if w > hi:
        # 先去掉「圓滿」再量
        t = title.replace("圓滿", "", 1)
        if lo <= line_width(t) <= hi:
            return t
        t = title.replace("謝幕", "收", 1)
        if lo <= line_width(t) <= hi:
            return t
        # 逐字從後半刪到落入區間
        t = title
        while line_width(t) > hi and len(t) > 8:
            # 刪後半最後一個全形字
            t = t[:-1].rstrip()
        if line_width(t) < lo:
            t = title[:len(t) + 1]
        return t
    return title


def run(args, **kw):
    return subprocess.run(args, check=True, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE, **kw)


def probe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def write_text(path: str, text: str):
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)


def load_material_map(script_path: str) -> dict[str, str]:
    folder = os.path.dirname(os.path.abspath(script_path))
    slug = slug_from_script(script_path)
    lst = os.path.join(folder, f"{slug} 素材清單.txt")
    mapping = {}
    if os.path.exists(lst):
        for line in open(lst, encoding="utf-8"):
            m = re.match(r"^#(\d+)\s*→\s*(.+\.mp4)\s*$", line.strip())
            if m:
                mapping[m.group(1).zfill(2)] = m.group(2).strip()
            m2 = re.match(r"^#(\d+)\s*→\s*(.+)$", line.strip())
            if m2 and m2.group(1) not in mapping:
                p = m2.group(2).strip()
                if p.lower().endswith(".mp4"):
                    mapping[m2.group(1).zfill(2)] = p
    default = os.path.join(
        r"D:\Downloads\花蓮暑假2400",
        "2026 0816 花蓮鯉魚潭FUN暑假.mp4")
    mapping.setdefault("01", default)
    return mapping


def load_script(path: str):
    """回傳 (doc, blocks, events)。完成稿＝CTV 骨架 + NS 指令行。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    cards = {}
    title = ""
    i = 0
    # skip 稿頭 until SUPER: or BAR 1 or 【
    while i < len(lines):
        s = lines[i].strip()
        if s in ("SUPER:", "SUPER") or BAR_CARD_RE.match(s) or s.startswith("【主標題】"):
            break
        i += 1
    speakers = []
    if i < len(lines) and lines[i].strip() in ("SUPER:", "SUPER"):
        i += 1
        while i < len(lines):
            s = lines[i].strip()
            if not s:
                i += 1
                continue
            if BAR_CARD_RE.match(s) or BAR_MARK_RE.match(s):
                break
            speakers.append(s)
            i += 1
    while i < len(lines):
        s = lines[i].strip()
        if not s or s == "##":
            i += 1
            continue
        m = BAR_CARD_RE.match(s)
        if not m:
            if s.startswith("【主標題】"):
                i += 1
                if i < len(lines):
                    title = lines[i].strip()
                    i += 1
                continue
            break
        n = int(m.group(1))
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines):
            cards[n] = lines[i].strip()
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    title = title or cards.get(1, "")
    while i < len(lines) and not lines[i].strip():
        i += 1
    body_lines = lines[i:]
    events = []
    pending_shots = []
    pending_os = []
    sb_n = 0
    os_n = 0
    cur_bar = 1
    j = 0
    ctv = bool(cards) or "SUPER:" in text

    def flush_os():
        nonlocal pending_os, pending_shots, os_n
        if not pending_os:
            pending_shots = []
            return
        os_n += 1
        events.append({
            "kind": "os", "id": f"os{os_n}", "bar": cur_bar,
            "os": pending_os[:], "shots": pending_shots[:], "sb": None,
        })
        pending_os, pending_shots = [], []

    while j < len(body_lines):
        s = body_lines[j].strip()
        j += 1
        if not s or s.startswith("SLUG") or s.startswith("TVBS") or s == "##":
            continue
        bm = BAR_MARK_RE.match(s)
        if bm:
            flush_os()
            cur_bar = int(bm.group(1))
            continue
        ns = NS_RE.match(s)
        if ns:
            flush_os()
            events.append({
                "kind": "ns",
                "id": f"ns{len([e for e in events if e['kind']=='ns'])+1}",
                "num": ns.group("num").zfill(2),
                "start": mmss_to_sec(ns.group("start")),
                "end": mmss_to_sec(ns.group("end")),
                "desc": (ns.group("desc") or "").strip(),
            })
            pending_shots = [{
                "num": ns.group("num").zfill(2),
                "tc": mmss_to_sec(ns.group("end")),
                "desc": (ns.group("desc") or "").strip(),
            }]
            continue
        sh = SHOT_RE.match(s)
        if sh:
            pending_shots.append({
                "num": sh.group("num").zfill(2),
                "tc": mmss_to_sec(sh.group("tc")),
                "desc": sh.group("desc"),
            })
            continue
        if s == "SB":
            flush_os()
            speaker = body_lines[j].strip() if j < len(body_lines) else ""
            j += 1
            zh = []
            while j < len(body_lines) and not SB_TC_RE.match(body_lines[j].strip()):
                if body_lines[j].strip() and body_lines[j].strip() != "SB":
                    zh.append(body_lines[j].strip())
                j += 1
            tc_line = body_lines[j].strip() if j < len(body_lines) else ""
            j += 1
            orig = ""
            if j < len(body_lines) and body_lines[j].strip() and body_lines[j].strip() not in ("SB",) \
                    and not BAR_MARK_RE.match(body_lines[j].strip()) \
                    and not NS_RE.match(body_lines[j].strip()):
                orig = body_lines[j].strip()
                j += 1
            tm = SB_TC_RE.match(tc_line)
            sb_n += 1
            events.append({
                "kind": "sb",
                "id": f"sb{sb_n}",
                "speaker": speaker,
                "zh": "\n".join(zh),
                "zh_lines": zh[:],
                "orig": orig or " ".join(zh),
                "num": (tm.group("num") or "01").zfill(2) if tm else "01",
                "tc": (mmss_to_sec(tm.group("start")), mmss_to_sec(tm.group("end"))) if tm else (0, 0),
            })
            continue
        if ctv:
            pending_os.append(s)
        else:
            pending_os.extend(split_os_sentences(s))
    flush_os()

    blocks = [{"bar": e["bar"], "os": e["os"], "sb": None, "id": e["id"]}
              for e in events if e["kind"] == "os"]
    if not cards:
        cards = {b["bar"]: title for b in blocks}
    doc = SimpleNamespace(title=title or cards.get(1, ""), cards=cards,
                          speakers=speakers, body_lines=body_lines)
    return doc, blocks, events
