#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""歐印萬 `.wav.txt` → S2b 側錄候選 TXT（純機械擷取，不改任何一個字）。

用途：把「掃帶歐印萬」資料夾裡公司自動化系統產出的 `{基名}.wav.txt`
擷取出**中文段**，寫成 `add-side --normalize` 吃得下的候選檔。

⚠️ **這支只做擷取，不做篩選、不做摘要、不改字**——側錄的逐字鐵律
（見 `common/14-S2b-側錄轉譯摘要.md`）在這一層一樣成立。歸位（大分類／
中主題／小分題）與 SUPER 補強由呼叫端的 agent 判斷，本工具只提供線索
（`--report`），**線索不寫進候選檔**，否則 normalize 會把它當內容行。

觀察到的**四種**產生器變體（2026-08-09 實測 10 支）：
  A. `### 中文 ###` → `文稿` → TC 段（5 支）
  B. `### 中文 ###` → **直接** TC 段，**沒有 `文稿` 行**（3 支：150102／150648／160106）
  C. **沒有 `###` 標頭**，重點摘要 → `#####` → `文稿` → TC 段（1 支：163927）
  D. **沒有 `###` 標頭、也沒有 `文稿` 行**，重點摘要 → `#####` → TC 段
     （1 支：NHK 170011）

⛔ **所以不要用關鍵字當錨點，用「第一個 TC 行」**。這四種變體唯一的共同點就是
中文段永遠在最前面、而且一定由 TC 行起頭。`### 中文 ###` 存在時仍優先採用
（那是明講的），但**沒有它時不准退回找 `文稿`**——

  · 變體 B 的中文段沒有 `文稿`，錨點會滑到**原文段**的 `文稿` → 收到英文（第一版實錯）
  · 變體 D 同理 → 收到**日文**（第二版實錯，NHK 170011）

## 兩道內容防線（都要留，各擋各的）

  1. **CJK 比例 < 30% → 擋**：擋英文原文段。
  2. **假名比例過高 → 擋**：擋**日文**原文段。⚠️ 日文漢字也算 CJK，防線 1
     對日文完全無效——NHK 那次就是這樣整段日文過關的。分辨中文與日文
     **只能看假名**（ひらがな／カタカナ），不能看漢字。

⛔ **TC 不再換算**（2026-08-09 使用者定案）：這些檔案裡的 TC 已經是母帶
絕對時間（實測 `150102`→`15:01:02`、`150648`→`15:06:48`、`151018`→
`15:10:18`），`common/02-tc-offset-filename.md` 的偏移加總**只適用 AI 自行
轉錄的流程**，套在這裡會把 15:14:39 變成 30:29:18。
"""
import argparse
import os
import re
import sys
from datetime import datetime, timedelta

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
# 純分隔線（`#####`），中間不夾任何字——夾了字就是標頭，交給 _ZH_HEAD／_END 認
_SEP_ONLY = re.compile(r"^#{3,}$")
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


def _kana_ratio(text):
    """\u5047\u540d\u4f54 CJK \u7684\u6bd4\u4f8b\u2014\u2014**\u5206\u8fa8\u4e2d\u6587\u8207\u65e5\u6587\u53ea\u80fd\u9760\u9019\u500b**\u3002

    \u65e5\u6587\u6f22\u5b57\u540c\u6a23\u843d\u5728 `\\u4e00-\\u9fff`\uff0c\u6240\u4ee5 `_cjk_ratio` \u5c0d\u65e5\u6587\u5b8c\u5168\u7121\u6548
    \uff08NHK 170011 \u6574\u6bb5\u65e5\u6587\u5c31\u662f\u9019\u6a23\u904e\u95dc\u7684\uff09\u3002\u4e2d\u6587\u9010\u5b57\u7a3f\u593e\u96dc\u7684\u5047\u540d\u5e7e\u4e4e\u53ea\u6703\u662f
    \u5c08\u540d\u88e1\u7684\u96f6\u661f\u5e7e\u500b\u5b57\uff0c\u65e5\u6587\u6b63\u6587\u5247\u662f\u6eff\u7bc7\u52a9\u8a5e\uff0c\u5169\u8005\u5dee\u8ddd\u5f88\u5927\uff0c\u9580\u6abb\u597d\u6293\u3002
    """
    kana = sum(1 for ch in text
               if "\u3040" <= ch <= "\u309f" or "\u30a0" <= ch <= "\u30ff")
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return kana / (kana + cjk) if (kana + cjk) else 0.0


def extract_zh(raw):
    """回傳 (中文段的行 list, 錯誤訊息 or None)。"""
    lines = raw.splitlines()
    # 錨點＝**第一個 TC 行**。四種變體唯一的共同點就是中文段永遠在最前面、
    # 由 TC 行起頭。`### 中文 ###` 存在時優先用它（明講的），但沒有它時
    # **不准退回找 `文稿`**——變體 B 會滑到英文段、變體 D 會滑到日文段。
    heads = [i for i, l in enumerate(lines) if _ZH_HEAD.match(l.strip())]
    tcs = [i for i, l in enumerate(lines)
           if _SEG.match(l.strip()) and _SEG.match(l.strip()).group(1)]
    if not tcs:
        return None, "整份找不到任何 TC 行"
    b = tcs[0] - 1 if not heads else heads[0]
    if heads and tcs[0] <= heads[0]:
        # `### 中文 ###` 之前就有 TC 行 → 版面跟認知不符，別硬猜
        return None, "`### 中文 ###` 之前就出現 TC 行，版面不明"
    # 中文段的結尾有兩種寫法，**兩種都要認**：
    #   ① `時間軸`／`### 原文 ###`（明講的，`_END`）
    #   ② 一整行只有 `#####`（變體 E，2026-08-09 實錯：210130 美伊美國經濟專家分析）
    # ② 沒認的話中英文會被當成同一段，CJK 比例被稀釋到 19%、整支被防線擋掉。
    # ⚠️ `#####` 只認**第一個 TC 之後**的：變體 C 的摘要與正文之間也有一個 `#####`，
    #    但那個在首個 TC 之前，拿來當結尾會把整段切光。
    # ⛔ 不要改成認 `文稿` 行——變體 A 的 `文稿` 在中文段**開頭**（`### 中文 ###` 的下一行），
    #    當成結尾會直接回報「文稿段是空的」。
    ends = [i for i, l in enumerate(lines) if i > b and _END.match(l.strip())]
    seps = [i for i, l in enumerate(lines)
            if i > tcs[0] and _SEP_ONLY.match(l.strip())]
    cands = [x[0] for x in (ends, seps) if x]
    e = min(cands) if cands else len(lines)
    body = [l for l in lines[b + 1:e]]
    joined = "\n".join(body)
    if not joined.strip():
        return None, "文稿段是空的"
    # ── 兩道內容防線，各擋各的（都要留）──────────────────────────
    # ① 英文原文段：163927 證明區塊順序不是靠標頭保證的。
    if _cjk_ratio(joined) < 0.30:
        return None, f"第一段疑似不是中文（CJK 比例 {_cjk_ratio(joined):.0%}）"
    # ② 日文原文段：日文漢字也算 CJK，①對日文完全無效（NHK 170011 實錯）。
    if _kana_ratio(joined) > 0.15:
        return None, (f"第一段疑似是日文原文（假名佔 CJK "
                      f"{_kana_ratio(joined):.0%}）")
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
            tc, rest = m.group(1), m.group(2)
            # ⚠️ 來源檔的起始 TC 有可能多打一段（實例 NHK 181723 第 20 行：
            #    `18:19:19:45-18:19:45（小朋友）咦？`）。不處理的話 group(1) 會咬到
            #    `18:19:19`、剩下的 `:45-18:19:45（小朋友）` 全被當成**逐字內容**——
            #    TC 錯了、SUPER 消失、內容多出一串亂碼，三個症狀一起來。
            #    修法：起始壞掉就**改用範圍終點**（那一行的終點正好是 18:19:45）。
            #    ⛔ 不要自己拼湊「應該是幾點」——那是造 TC，下游沒辦法查證。
            mm = re.match(r"^:\d{2}\s*[-–~]\s*(\d{1,2}:\d{2}:\d{2})\s*(.*)$", rest)
            if mm:
                tc, rest = mm.group(1), mm.group(2)
            tc6 = tc.replace(":", "").zfill(6)[-6:]
            role, text = _split_role(rest.strip())
            out.append([tc6, role, text.strip()])
        elif out:
            out[-1][2] = (out[-1][2] + "\n" + t).strip()
        # 沒有任何 TC 就出現的散行（重點摘要殘留等）直接丟掉——不是逐字內容
    return [tuple(x) for x in out]


def source_of(path, fallback="CNN"):
    """從檔名認來源。⚠️ **不要靠 `--source` 手動給**：一個資料夾裡 CNN 與 NHK
    混放，用單一 `--source` 跑整個資料夾，另一台的檔案會全部被貼錯前綴——
    而錯的前綴讓 id 對不上，症狀是「明明入庫了卻判定沒入庫」（2026-08-09 實錯，
    歸檔腳本用預設 CNN 掃到 NHK 檔，4 支全被判成一段都沒入庫）。
    """
    b = os.path.basename(path)
    for src in ("NHK", "CNN"):
        if src in b:
            return src
    return fallback


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
    """角色連續段＝一個小分題的候選（使用者 2026-08-09 定案：換講者就換小分題）。

    ⚠️ 只比對角色的第一個詞，所以 `記者 A` → `記者 B` 會併成同一段。這是**線索**
    不是判決，最終切點由 agent 判；實際資料裡角色都是交錯的，沒踩到。
    不要把它「修」成硬規則。
    """
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
    ap.add_argument("--source", default=None,
                    help="來源前綴；省略＝從檔名自動認（CNN／NHK），認不出才用 CNN")
    ap.add_argument("--out", help="候選 TXT 輸出路徑（省略＝只印報告不寫檔）")
    ap.add_argument("--since", help="只收 mtime 晚於此時間的檔（HH:MM 或 MM-DD HH:MM）")
    ap.add_argument("--report", action="store_true", help="印出歸位線索")
    args = ap.parse_args()

    paths = args.files or sorted(
        os.path.join(args.dir, f) for f in os.listdir(args.dir)
        if f.endswith(".wav.txt")
    )
    if args.since:
        now = datetime.now()
        cut = args.since if " " in args.since else f"{now:%m-%d} {args.since}"
        cutd = datetime.strptime(f"{now:%Y}-{cut}", "%Y-%m-%d %H:%M")
        # ⚠️ 跨夜：01:00 那輪下 `--since 23:00`，配今天的日期會算出**未來時間**，
        #    於是一支都收不到——不會報錯，只會靜靜空手而回。算出未來就退一天。
        if " " not in args.since and cutd > now:
            cutd -= timedelta(days=1)
        paths = [p for p in paths
                 if datetime.fromtimestamp(os.path.getmtime(p)) >= cutd]

    cand, failed, total = [], [], 0
    # ⚠️ TC 就是入庫的 id（`CNN MM-DD 6碼`）。來源檔**真的會出現重複的起始 TC**
    #    （實例 NHK 181723：`18:19:58` 出現兩次，一段童聲、一段主播高溫警戒），
    #    此時 add-side 會把第二段當成「已在庫」**靜靜略過** —— 段數對不上而且不報錯。
    #    這裡先攔下來大聲講，讓人決定要捨哪一段或請上游修 TC。
    seen_tc = {}
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
        src = args.source or source_of(p)
        for tc6, role, text in segs:
            key = f"{src} {d} {tc6}"
            if key in seen_tc:
                print(f"🔴 TC 重複：{key}")
                print(f"     已有 [{seen_tc[key]}]")
                print(f"     又見 [{os.path.basename(p)}] （{role}）{text[:30]}")
                print("     → add-side 會靜靜略過後者，**入庫前要先決定怎麼辦**")
            else:
                seen_tc[key] = os.path.basename(p)
            head = key
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
