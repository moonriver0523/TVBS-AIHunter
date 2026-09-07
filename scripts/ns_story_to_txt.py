#!/usr/bin/env python3
"""把 NS `/api/v3/stories` 的白名單回應轉成 CTV 的「<ID> 原始文稿.txt」。

用法（見 cnn/01-auto-script-writing.md 步驟 1）：
    python scripts/ns_story_to_txt.py --json "<evaluate 存出的 json>" --id WE-018FR --out "<ID> 原始文稿.txt"

輸入 json 形狀：browser_evaluate 回傳的 list，每項至少有
    id / title / description / owner(list) / embargo(list|str) / footageType / duration(ms) / reporter / createdDate / script(html)
（多一些鍵無妨；也接受 {"items": [...]} 包一層。）

行為：
- 只留 id 完全相同的項；story ID 每週重用，可能多於一則 → 取 createdDate 最新，其餘列出來給 agent 印給使用者。
- 0 則 → exit 2，代表要退 UI 舊步驟。
- 最新那則 createdDate 距今超過 STALE_DAYS → 仍輸出，但印 ⚠️（可能拿到的是舊素材，要人工確認標題）。
- script 是 HTML（<p>／<b>／實體）→ 轉成與 ≡Q Preview 一致的純文字：每個 <p> 一行、空 <p> 一個空行、粗體標籤直接刪、實體解碼。
- 檔頭 8 行與既有原始文稿一致（Story Number／Title／Description／Source／Embargo／Footage Type／TRT／Reporter），validate_sot --source-script 不用改。
- 結尾印一段精簡摘要（ID／Title／Source／Embargo／TRT／Reporter／引言句估計），agent 只回這段，不回全文。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

STALE_DAYS = 7
HEADER_KEYS = ("Story Number", "Title", "Description", "Source", "Embargo", "Footage Type", "TRT", "Reporter")


def html_to_text(s: str) -> str:
    """NS script HTML → 與 UI Preview 逐字一致的純文字。"""
    s = s or ""
    s = s.replace("\r", "")
    # 粗體／斜體／pi 這類行內標籤直接刪，不換行（否則 --SUPERS-- 會被切成兩行）
    s = re.sub(r"</?(b|i|u|strong|em|span|pi|font)\b[^>]*>", "", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<p\b[^>]*>", "", s, flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace(" ", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).rstrip() for ln in s.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def fmt_trt(ms) -> str:
    try:
        total = int(round(float(ms) / 1000))
    except (TypeError, ValueError):
        return ""
    return f"{total // 60:02d}:{total % 60:02d}"


def join_list(v) -> str:
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v if str(x).strip())
    return str(v or "")


def parse_dt(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


ALIASES = {"footageType": "ft", "duration": "dur", "createdDate": "created", "description": "desc"}


def normalize(it: dict) -> dict:
    """接受 13c §1a 白名單常用的短鍵（ft／dur／created／desc），補成本檔用的長鍵。"""
    out = dict(it)
    for long, short in ALIASES.items():
        if long not in out and short in out:
            out[long] = out[short]
    if "id" not in out and isinstance(out.get("alternateIds"), dict):
        out["id"] = out["alternateIds"].get("bitcentralId")
    return out


def pick(items: list, story_id: str):
    """回 (chosen, others)。chosen 為 createdDate 最新；沒有符合 id 的回 (None, [])。"""
    items = [normalize(it) for it in items]
    same = [it for it in items if str(it.get("id") or "").strip().upper() == story_id.strip().upper()]
    if not same:
        return None, []
    same.sort(key=lambda it: parse_dt(it.get("createdDate")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return same[0], same[1:]


def build_txt(it: dict) -> str:
    header = {
        "Story Number": it.get("id", ""),
        "Title": it.get("title", ""),
        "Description": it.get("description", ""),
        "Source": join_list(it.get("owner")),
        "Embargo": join_list(it.get("embargo")),
        "Footage Type": it.get("footageType", ""),
        "TRT": fmt_trt(it.get("duration")),
        "Reporter": it.get("reporter", ""),
    }
    head = "\n".join(f"{k}: {header[k]}" for k in HEADER_KEYS)
    return head + "\n\n" + html_to_text(it.get("script", "")) + "\n"


QUOTE_RE = re.compile(r'^\s*(?:[A-Z][A-Za-z .\'\-]{1,60}:\s*\S|"[^"]{8,}"\s*$)', re.M)


def estimate_quotes(text: str) -> int:
    return len(QUOTE_RE.findall(text))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--json", required=True, help="browser_evaluate 存出的 json 檔")
    ap.add_argument("--id", required=True, help="story ID，例 WE-018FR")
    ap.add_argument("--out", required=True, help="輸出的原始文稿 txt 路徑")
    ap.add_argument("--stale-days", type=int, default=STALE_DAYS)
    a = ap.parse_args(argv)

    data = json.loads(Path(a.json).read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        print("✗ json 不是 list 也沒有 items 鍵", file=sys.stderr)
        return 1

    chosen, others = pick(items, a.id)
    if chosen is None:
        print(f"✗ API 沒有 {a.id}（{len(items)} 則都不是）→ 退 cnn/01 步驟 1 的 UI 舊做法", file=sys.stderr)
        return 2

    txt = build_txt(chosen)
    Path(a.out).write_text(txt, encoding="utf-8")

    created = parse_dt(chosen.get("createdDate"))
    age_days = (datetime.now(timezone.utc) - created).days if created else None
    print(f"✓ 已寫 {a.out}（{len(txt)} 字元）")
    for k in HEADER_KEYS:
        v = txt.split("\n")[HEADER_KEYS.index(k)]
        print("  " + v[:120])
    body = txt.split("\n\n", 1)[1] if "\n\n" in txt else ""
    print(f"  createdDate: {chosen.get('createdDate', '')}  引言句估計（僅供盤點提示，以步驟 5 為準）: {estimate_quotes(body)}")
    if others:
        print(f"⚠️ 同一 ID 另有 {len(others)} 則（story ID 每週重用），已取最新；請把標題印給使用者確認：")
        for o in others:
            print(f"   - {str(o.get('createdDate', ''))[:10]} | {o.get('title', '')}")
    if age_days is not None and age_days > a.stale_days:
        print(f"⚠️ 最新那則 createdDate 距今 {age_days} 天（>{a.stale_days}），可能不是使用者要的素材，標題核對後再繼續")
    if not html_to_text(chosen.get("script", "")).strip():
        print("⚠️ script 為空——官方稿可能尚未上架，依 cnn/01 步驟 5 鐵則不可交完成版")
    return 0


if __name__ == "__main__":
    sys.exit(main())
