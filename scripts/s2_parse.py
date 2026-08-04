# -*- coding: utf-8 -*-
"""把 `raw_entry` 三段式字串拆成結構化欄位（2026-08-04 新增）。

**為什麼要有這支**：`raw_entry` 存的是「要印進 txt 的那一行原文」，render 照抄零加工。
好處是所見即所得，代價是**內容不可查詢**——想問「今天幾則有 BITE」「總時長多少」
「哪些限制條件最常出現」都只能字串硬搜。要做外電 dashboard 就得先有欄位。

**設計原則（重要，改動前先讀）**：

1. ⛔ **不取代 `raw_entry`，只是多存一份**。render 仍然吃 `raw_entry`，這條輸出路徑
   每天在跑，不為了加欄位去重寫它。欄位壞掉最多是 dashboard 少資料，不會害交接檔出不來。
2. ⛔ **由腳本推導，不叫 agent 多寫一份**。讓 agent 同時寫字串與欄位必然不同步
   （總有一邊漏字），還多花 token。agent 完全無感。
3. ⛔ **解析失敗不擋入庫**。標 `parse_ok: false` 照樣收——0804 實測 930 則有 23 則
   解析不了（YouTube 兩行式、時長寫成 HH:MM:SS 等），那些都是好素材，擋下來會害掃帶卡住。

實測解析率（2026-08-04，0731–0804 五天）：930 則成功 907（97.5%）。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2_validate as sv  # noqa: E402  共用 CODE／標記剝離，不另寫一套

# 時長：`01:34`（MM:SS）為標準；`01:01:01`（HH:MM:SS）舊資料有，一併收
_DUR = re.compile(r"^\d{1,3}:\d{2}(?::\d{2})?$")
_LABEL = re.compile(r"^(畫面|BITE)[：:]\s*")


def parse_entry(entry):
    """回傳 (fields dict, None) 或 (None, 失敗原因)。

    格式：`{標記} {代碼}[/{代碼}] (備註)… ▎摘要 ▎畫面：… ▎BITE：…|無BITE。 ▎MM:SS`
    ⚠️ 舊格式（0731／0801）摘要前面**沒有** `▎`，直接接在備註後——兩種都要吃。
    """
    _, line = sv.strip_mark((entry or "").lstrip("﻿"))
    line = line.strip()
    if not line:
        return None, "空白內容"
    m = re.match(rf"^({sv.CODE}(?:\s*/\s*{sv.CODE})*)\s*", line)
    if not m:
        return None, "抓不到素材代碼（YouTube 兩行式等非標準格式）"
    codes = re.findall(sv.CODE, m.group(1))
    rest = line[m.end():]

    notes = []
    while True:
        mn = re.match(r"^[（(]([^）)]*)[）)]\s*", rest)
        if not mn:
            break
        notes.append(mn.group(1).strip())
        rest = rest[mn.end():]

    segs = [s.strip() for s in rest.split("▎") if s.strip()]
    if not segs:
        return None, "沒有摘要／畫面等內容段"

    out = {"codes": codes, "notes": notes, "summary": None,
           "footage": None, "bite": [], "no_bite": False, "duration": None}
    for s in segs:
        lab = _LABEL.match(s)
        if lab and lab.group(1) == "畫面":
            out["footage"] = s[lab.end():].strip()
        elif lab:                                   # BITE：
            out["bite"].append(s[lab.end():].strip())
        elif s.startswith("無BITE"):
            out["no_bite"] = True
        elif _DUR.match(s):
            out["duration"] = s
        elif out["summary"] is None:
            out["summary"] = s
        elif out["bite"]:
            # 摘要之後的無標籤段落＝同一則的第二位講者（`▎BITE：A「…」▎B「…」`）
            out["bite"].append(s)
        else:
            return None, f"無法歸類的段落：{s[:24]}"

    if out["summary"] is None:
        return None, "沒有摘要段"
    if out["footage"] is None:
        return None, "沒有 ▎畫面： 段"
    if not out["no_bite"] and not out["bite"]:
        return None, "既沒有 無BITE 也沒有 ▎BITE： 段"
    return out, None


def skip_reason(item):
    """這一則該不該解析？回傳略過原因，None＝要解析。

    ⚠️ 略過 ≠ 解析失敗。這三類**本來就不是三段式**，硬要解只會製造假失敗、
    害真正該修的解析 bug 被淹在噪音裡。
    """
    if item.get("script_status") == "note":
        return "備註殼"
    src = str(item.get("source", ""))
    if src.startswith("SIDE_"):
        return "側錄逐字（非三段式）"
    if src == "YT":
        return "YouTube 兩行式（網址＋備註行，見 13b §4c）"
    return None


def derive(item):
    """就地補上 `fields`／`parse_ok`／`parse_note`。回傳 True＝有解析（含失敗）。

    略過的（側錄、備註殼）完全不動，不寫任何欄位——免得狀態檔多出一堆
    `parse_ok: null` 的雜訊。
    """
    if skip_reason(item):
        return False
    f, why = parse_entry(item.get("raw_entry") or "")
    if f:
        item["fields"] = f
        item["parse_ok"] = True
        item.pop("parse_note", None)
    else:
        item["parse_ok"] = False
        item["parse_note"] = why
        item.pop("fields", None)
    return True


if __name__ == "__main__":                          # 快速手測：印出單行解析結果
    import json
    src = " ".join(sys.argv[1:])
    if not src:
        print("用法：python s2_parse.py '<raw_entry 整行>'")
        sys.exit(2)
    f, why = parse_entry(src)
    print(json.dumps(f, ensure_ascii=False, indent=1) if f else f"解析失敗：{why}")
