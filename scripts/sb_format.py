# -*- coding: utf-8 -*-
"""SB 五行格式的唯一機械實作——agent 流程與掐BITE前台共用同一支。

**這裡不定義規格，只實作規格。** 規格的唯一來源是
`common/00-寫稿通則.md` 第 4 節（SB 五行格式）與其 TC 欄位寫法表；
本檔任何行為若與該文件不一致，**以該文件為準，並修正本檔**。

為什麼要有這支：`common/plans/2026-08-24-S5至S8產線UI前台可行性評估.md` §七
訂的護欄——前台不得把 SB 排版規則分叉進 JS，否則兩邊各自演化。
比照 `s2_render_html.py` 的立場：**前台是投影，不是第二份真相。**

實作的四種 TC 欄位寫法（00-寫稿通則 §4 的表）：

    numbered   `#03 0033-0044`              有 #編號 的外電素材（檔案自己從 0 算，4 碼 MMSS）
    side       `CNN 7/28 060900-060923`     側錄素材（不編 #XX，6 碼 HHMMSS，已套檔名 offset）
    ctv        `0006-0013`                  自動寫稿(CTV) 單支素材，純 4 碼無前綴
    plain      `060900-060923`／`0033-0044` 其他無編號素材，有 offset 用 6 碼、沒有用 4 碼

檔名 offset 的解析依 `common/02-tc-offset-filename.md`：檔名前 6 碼數字
＝該檔 00:00:00 對應的母帶真實時間；非數字或 000000 則 offset 為 0。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- TC offset


def offset_from_filename(name: str) -> int:
    """依 `common/02-tc-offset-filename.md` 從檔名取 TC offset（秒）。

    取檔名開頭連續數字的**前 6 碼**解析成 HHMMSS；不足 6 碼、非數字開頭、
    或解析結果為 000000 一律回 0（不做偏移）。8 碼（SMPTE 風格含影格）
    仍只取前 6 碼，其餘忽略。
    """
    stem = os.path.basename(name)
    m = re.match(r"(\d{6,})", stem)
    if not m:
        return 0
    digits = m.group(1)[:6]
    hh, mm, ss = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
    if (hh, mm, ss) == (0, 0, 0):
        return 0
    if mm > 59 or ss > 59 or hh > 23:
        return 0  # 不像時間碼（例如 AP 的 7 碼編號），視為無 offset
    return hh * 3600 + mm * 60 + ss


def fmt_tc(seconds: float, digits: int) -> str:
    """秒 → 4 碼 MMSS 或 6 碼 HHMMSS。

    ⚠️ `00-寫稿通則` §4 明訂「抽格時記的是秒、寫進稿是 MMSS，換算務必過
    一次算式」——這支就是那個算式，不要在別處手算。
    """
    s = int(round(seconds))
    if s < 0:
        raise ValueError(f"TC 不可為負：{seconds}")
    if digits == 4:
        mm, ss = divmod(s, 60)
        if mm > 99:
            raise ValueError(f"{s} 秒超過 4 碼 MMSS 可表示範圍，應改用 6 碼")
        return f"{mm:02d}{ss:02d}"
    if digits == 6:
        hh, rem = divmod(s, 3600)
        mm, ss = divmod(rem, 60)
        return f"{hh:02d}{mm:02d}{ss:02d}"
    raise ValueError(f"TC 只支援 4 碼或 6 碼，收到 {digits}")


# ---------------------------------------------------------------- TC 欄位

def tc_field(
    kind: str,
    start: float,
    end: float,
    *,
    material_no: str | None = None,
    source: str | None = None,
    md: str | None = None,
    offset: int = 0,
) -> str:
    """組出 SB 第 4 行的 TC 欄位。`kind` 為 numbered／side／ctv／plain。

    `start`／`end` 一律是**該檔案內部的相對秒數**（從 0 開始）；offset 在
    這裡才加上去，呼叫端不要自己先加，避免加兩次。
    """
    if end < start:
        raise ValueError(f"TC 訖點早於起點：{start} → {end}")

    if kind == "numbered":
        if not material_no:
            raise ValueError("numbered 需要 material_no（例 '03'）")
        no = material_no.lstrip("#")
        return f"#{no} {fmt_tc(start, 4)}-{fmt_tc(end, 4)}"

    if kind == "side":
        if not source or not md:
            raise ValueError("side 需要 source（例 'CNN'）與 md（例 '7/28'）")
        return (
            f"{source} {md} "
            f"{fmt_tc(start + offset, 6)}-{fmt_tc(end + offset, 6)}"
        )

    if kind == "ctv":
        return f"{fmt_tc(start, 4)}-{fmt_tc(end, 4)}"

    if kind == "plain":
        d = 6 if offset else 4
        return f"{fmt_tc(start + offset, d)}-{fmt_tc(end + offset, d)}"

    raise ValueError(f"未知的 TC 欄位型別：{kind}")


# ---------------------------------------------------------------- 五行組裝

@dataclass
class SB:
    """一段 SB。`zh` 允許多行——`00-寫稿通則` §4 明訂五行指的是五個欄位
    的順序，不是中文只能佔一行；解析以 TC 那行為界。"""

    speaker: str          # 第 2 行：{職稱} {姓名}
    zh: str               # 第 3 行：中文翻譯（可多行，不帶「」）
    tc: str               # 第 4 行：TC 欄位（用 tc_field() 產生）
    original: str         # 第 5 行：原文逐字（一律取自官方文稿，不用 ASR 文字）
    warnings: list[str] = field(default_factory=list)


_QUOTE_CHARS = "「」“”\"＂"


def render_sb(sb: SB) -> str:
    """輸出純文字五行。**不包 code fence**（`00-寫稿通則` §4 明訂）。"""
    return "\n".join([
        "SB",
        sb.speaker.strip(),
        sb.zh.strip(),      # 可含換行，維持原樣（多行中文合法）
        sb.tc.strip(),
        sb.original.strip(),
    ])


def lint_sb(sb: SB, *, duration: float | None = None, mode: str = "sot") -> list[str]:
    """交付前的機械自查。**只查機械可判的部分**——「不可殘譯」「新聞價值」
    「講者是不是真的出鏡」這些是人的判斷，這裡不假裝能查。

    `mode='sot'` 套 `P-015` 的秒數門檻（<2 秒 FAIL、2–5 秒 WARN）。
    """
    out: list[str] = []

    if not sb.speaker.strip():
        out.append("[FAIL] 第 2 行講者（職稱 姓名）是空的")
    if not sb.zh.strip():
        out.append("[FAIL] 第 3 行中文翻譯是空的")
    if not sb.original.strip():
        out.append("[FAIL] 第 5 行原文是空的")

    if any(ch in sb.zh for ch in _QUOTE_CHARS):
        out.append("[FAIL] 中文翻譯不可帶「」引號（00-寫稿通則 §4）")
    if any(ch in sb.original for ch in _QUOTE_CHARS):
        out.append("[FAIL] 原文不可加任何引號（00-寫稿通則 §4）")

    # P-037：原文有代名詞、中文卻沒補主詞時提醒（只提醒，不代人判斷指涉）
    if re.search(r"\b(he|she|they|it)\b", sb.original, re.I) and "(" not in sb.zh:
        out.append(
            "[WARN] 原文有代名詞但中文沒有用半形括號補主詞——"
            "SB 上畫面時觀眾沒有前後文，確認是否需要補（P-037）"
        )

    if duration is not None and mode == "sot":
        if duration < 2:
            out.append(f"[FAIL] 單段 SB 只有 {duration:.1f} 秒（<2 秒，多半是 TC 打錯或殘句，P-015）")
        elif duration < 5:
            out.append(f"[WARN] 單段 SB {duration:.1f} 秒（2–5 秒），確認是完整一句而非被砍短（P-015）")

    return out
