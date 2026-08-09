#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""歐印萬 `.wav.txt` → S2b 側錄候選 TXT（純機械擷取，不改任何一個字）。

用途：把「掃帶歐印萬」資料夾裡公司自動化系統產出的 `{基名}.wav.txt`
擷取出**中文段**，寫成 `add-side --normalize` 吃得下的候選檔。

⚠️ **這支只做擷取，不做篩選、不做摘要、不改字**——側錄的逐字鐵律
（見 `common/14-S2b-側錄轉譯摘要.md`）在這一層一樣成立。歸位（大分類／
中主題／小分題）與 SUPER 補強由呼叫端的 agent 判斷，本工具只提供線索
（`--report`），**線索不寫進候選檔**，否則 normalize 會把它當內容行。

觀察到的**三種**產生器變體（2026-08-09 實測 9 支）：
  A. `### 中文 ###` → `文稿` → TC 段（5/9）
  B. `### 中文 ###` → **直接** TC 段，**沒有 `文稿` 行**（3/9：150102／150648／160106）
  C. **完全沒有 `###` 標頭**，重點摘要條列 → `#####` → `文稿` → TC 段（1/9：163927）
所以錨點要**兩層**：先找 `### 中文 ###`，找不到才退回第一個獨立成行的
`文稿`；結束點取其後第一個 `時間軸` 或 `### 原文 ###`。

⚠️ 只認 `文稿` 會踩到變體 B——中文段沒有那行，錨點會一路滑到**原文段**的
`文稿`，然後把英文逐字稿當成中文收進庫存。這不是假設，是本工具第一版
的實錯（靠下面的 CJK 比例防呆才擋下來）。**兩道防線都要留著。**

⛔ **TC 不再換算**（2026-08-09 使用者定案）：這些檔案裡的 TC 已經是母帶
絕對時間（實測 `150102`→`15:01:02`、`150648`→`15:06:48`、`151018`→
`15:10:18`），`common/02-tc-offset-filename.md` 的偏移加總**只適用 AI 自行
轉錄的流程**，套在這裡會把 15:14:39 變成 30:29:18。
"""
import argparse
import os
import re
import sys
from datetime import datetime

# Windows 主控台預設 cp950，印不出 `▸`／`■` 會整支炸掉（不是資料問題卻長得像）
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

DEFAULT_DIR = r"G:\我的雲端硬碟\Autopilot\(掃帶歐印萬) 檔名取TC起頭 6位數"

_ZH_HEAD = re.compile(r"^#+\s*中文\s*#+$")
_BEGIN = re.compile(r"^文稿[：:]?\s*$")
_END = re.compile(r"^(?:時間軸[：:]?|#+\s*原文\s*#+)\s*$")
# 允許 `HH:MM:SS` 與 `HH:MM:SS-HH:MM:SS` 兩種；角色括號另外用配對掃描（見 _split_role）
_SEG = re.compile(
    r"^(\d{1,2}:\d{2}:\d{2})(?:\s*[-–~]\s*\d{1,2}:\d{2}:\d{2})?\s*(.*)$"
)
_PAIR = {"（": "）", "(": ")"}


def _split_role(rest):
    """把開頭的 `（角色）` 切出來，回傳 (role, 內容)。

    ⚠️ **要配對計數，不能用 `[^）)]*`**：實際資料有巢狀——
    `(記者 茱莉亞·本布魯克（Julia Benbrook）) 知情人士…`（外半形、內全形）。
    非配對版會停在內層的 `）`，把外層的 `)` 留在內容開頭——那是**多改了一個字**，
    踩到側錄「逐字一字不能動」的鐵律，而且長得像資料本來就髒，很難察覺。
    """
    if not rest or rest[0] not in _PAIR:
        return "", rest
    close = _PAIR[rest[0]]
    depth = 0
    for i, ch in enumerate(rest):
        if ch == rest[0]:
            depth += 1
        elif ch == close:
            depth -= 1
            if depth == 0:
                if i > 41:                     # 角色標示不該這麼長 → 當成沒有
                    return "", rest
                return rest[1:i].strip(), rest[i + 1:].lstrip()
    return "", rest                            # 沒收尾＝不是角色標示，原樣留著
_BULLET = re.compile(r"^[-•]\s*(.+)$")


def _cjk_ratio(text):
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    letters = sum(1 for ch in text if ch.isalpha())
    return cjk / letters if letters else 0.0


def extract_zh(raw):
    """回傳 (中文段的行 list, 錯誤訊息 or None)。"""
    lines = raw.splitlines()
    # 第一層錨點：`### 中文 ###`。變體 B 的中文段沒有 `文稿` 行，只認 `文稿`
    # 會滑到原文段去。
    heads = [i for i, l in enumerate(lines) if _ZH_HEAD.match(l.strip())]
    if heads:
        b = heads[0]
        # `### 中文 ###` 後面緊接的 `文稿` 只是標籤，跳過（有沒有都能跑）
        while b + 1 < len(lines) and (not lines[b + 1].strip()
                                      or _BEGIN.match(lines[b + 1].strip())):
            b += 1
            if _BEGIN.match(lines[b].strip()):
                break
    else:
        starts = [i for i, l in enumerate(lines) if _BEGIN.match(l.strip())]
        if not starts:
            return None, "找不到 `### 中文 ###` 或獨立成行的『文稿』錨點"
        b = starts[0]
    ends = [i for i, l in enumerate(lines) if i > b and _END.match(l.strip())]
    e = ends[0] if ends else len(lines)
    body = [l for l in lines[b + 1:e]]
    joined = "\n".join(body)
    if not joined.strip():
        return None, "文稿段是空的"
    # 防呆：163927 證明區塊順序不是靠標頭保證的。萬一哪天英文段跑到前面，
    # 要**大聲失敗**，不要默默把英文逐字稿收進庫存。
    if _cjk_ratio(joined) < 0.30:
        return None, f"第一段疑似不是中文（CJK 比例 {_cjk_ratio(joined):.0%}）"
    return body, None


def segments(body):
    """把中文段切成 [(tc6, role, text)]；認不得的行黏回上一段（原樣保留）。"""
    out = []
    for l in body:
        t = l.strip()
        if not t:
            continue
        m = _SEG.match(t)
        if m and m.group(1):
            tc6 = m.group(1).replace(":", "").zfill(6)[-6:]
            role, text = _split_role(m.group(2).strip())
            out.append([tc6, role, text.strip()])
        elif out:
            out[-1][2] = (out[-1][2] + "\n" + t).strip()
        # 沒有任何 TC 就出現的散行（重點摘要殘留等）直接丟掉——不是逐字內容
    return [tuple(x) for x in out]


def hints(raw, path):
    """給 agent 判歸位／小分題用的線索。⚠️ 不寫進候選檔。"""
    base = os.path.basename(path)
    kw = re.sub(r"^.*?\d{6}\s*", "", base).replace(".wav.txt", "").strip()
    bullets = []
    for l in raw.splitlines():
        if _BEGIN.match(l.strip()) or _END.match(l.strip()):
            break
        m = _BULLET.match(l.strip())
        if m and _cjk_ratio(m.group(1)) > 0.3:
            bullets.append(m.group(1).strip())
    return kw, bullets


def role_runs(segs):
    """角色連續段＝一個小分題的候選（使用者 2026-08-09 定案：換講者就換小分題）。"""
    runs = []
    for tc6, role, _ in segs:
        key = re.sub(r"\s+.*$", "", role)          # `記者 Ivan Watson` → `記者`
        if runs and runs[-1][0] == key:
            runs[-1][1].append(tc6)
        else:
            runs.append([key, [tc6], role])
    return runs


def main():
    ap = argparse.ArgumentParser(description="歐印萬 .wav.txt → S2b 側錄候選 TXT")
    ap.add_argument("--dir", default=DEFAULT_DIR, help="來源資料夾")
    ap.add_argument("--files", nargs="*", help="指定檔案（省略＝掃整個資料夾）")
    ap.add_argument("--source", default="CNN", help="來源前綴（CNN／NHK）")
    ap.add_argument("--out", help="候選 TXT 輸出路徑（省略＝只印報告不寫檔）")
    ap.add_argument("--since", help="只收 mtime 晚於此時間的檔（HH:MM 或 MM-DD HH:MM）")
    ap.add_argument("--report", action="store_true", help="印出歸位線索")
    args = ap.parse_args()

    paths = args.files or sorted(
        os.path.join(args.dir, f) for f in os.listdir(args.dir)
        if f.endswith(".wav.txt")
    )
    if args.since:
        cut = args.since if " " in args.since else \
            f"{datetime.now():%m-%d} {args.since}"
        cutd = datetime.strptime(f"{datetime.now():%Y}-{cut}", "%Y-%m-%d %H:%M")
        paths = [p for p in paths
                 if datetime.fromtimestamp(os.path.getmtime(p)) >= cutd]

    cand, failed, total = [], [], 0
    for p in paths:
        with open(p, encoding="utf-8-sig", errors="replace") as f:
            raw = f.read()
        body, err = extract_zh(raw)
        if err:
            failed.append((os.path.basename(p), err))
            continue
        segs = segments(body)
        if not segs:
            failed.append((os.path.basename(p), "擷取到 0 段 TC"))
            continue
        total += len(segs)
        # ⚠️ 日期取**來源檔 mtime**，不是執行當下——跨夜輪次跑昨晚的檔會標錯日期，
        #    而 dedup id 是 `CNN MM-DD 6碼`，日期錯＝新內容被當成已入庫而靜靜消失。
        d = f"{datetime.fromtimestamp(os.path.getmtime(p)):%m-%d}"
        kw, bullets = hints(raw, p)
        for tc6, role, text in segs:
            head = f"{args.source} {d} {tc6}"
            if role:
                head += f" （{role}）"
            cand.append(head)
            cand.extend(text.splitlines())
        if args.report:
            print(f"\n■ {os.path.basename(p)}  mtime {d}  {len(segs)} 段")
            print(f"  檔名關鍵字：{kw}")
            for b in bullets:
                print(f"  重點：{b}")
            for key, tcs, full in role_runs(segs):
                print(f"  ▸ 角色連續段 {key or '(無)'}"
                      f"（{full}）：{','.join(tcs)}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(cand) + "\n")
        print(f"\n候選檔已寫出：{args.out}（{total} 段 / {len(paths) - len(failed)} 支）")
    else:
        print(f"\n（未指定 --out，未寫檔）共 {total} 段 / "
              f"{len(paths) - len(failed)} 支")
    for name, err in failed:
        print(f"⚠️ 跳過 {name}：{err}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
