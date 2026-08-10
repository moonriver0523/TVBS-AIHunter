# -*- coding: utf-8 -*-
"""S2 定時掃帶狀態檔代管腳本（V2）。

agent 一律透過本腳本讀寫狀態，不直接開 JSON。
用法見 common/13b-S2-定時掃帶-v2省token.md。

狀態檔預設路徑：G:\\我的雲端硬碟\\Claude共用\\自動掃帶系統\\s2-state.json
（可用 --file 覆蓋；找不到時自動建立空狀態。）
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s2_parse as sp  # noqa: E402  raw_entry → 結構化欄位（寫入時自動推導）

# ⚠️ 用 reconfigure 不用 TextIOWrapper：包第二層時（例如 s2_state 匯入 s2_validate）
# 舊寫法會讓其中一個 wrapper 被回收時關掉底層 buffer，整支腳本以 "I/O operation on
# closed file" 掛掉（2026-08-03 WP1 實錯）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # py<3.7
        pass

STATE_DIR = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統"


def default_file():
    """`--file` 沒給時要用哪一份狀態檔——**自動找資料夾裡最新的那份**。

    ⚠️ **這裡曾經是一個很傷的陷阱**（2026-08-09 實錯，改掉的就是它）：
    原本寫死 `{STATE_DIR}\\s2-state.json`，而**正式檔名一律帶日期前綴**
    （`0808-s2-state.json`），所以那個路徑**永遠不會存在**。任何忘了帶 `--file`
    的指令都會讀到一份空檔、印出「共 0 則」——

    而 `13b §5a` 第 2 條又把「共 0 則」寫成『確認自己真的在建新檔』的證明。
    **規則反過來替錯誤背書**：0809-0900 那輪的 agent 因此判定自己是當天第一輪，
    把還在使用的 0808 檔整個歸檔、另開新檔，資料斷成兩份（沒丟，但要人工併回）。

    📌 **這類錯誤的形狀值得記住**：一個「檢查」的通過條件，
    竟然與最常見的失敗模式長得一模一樣，那它就不是檢查，是背書。

    現在的行為：資料夾裡有 `{MMDD}-s2-state.json` 就用**最新修改**的那份；
    一份都沒有（真的是全新的一天）才回退到今天日期的新檔名。
    ⛔ **不再回傳無日期前綴的路徑**——那個檔名本身就是不合規的。

    ⚠️ **然後它又從反方向錯了一次（2026-08-10 實錯，本次補的就是這個）**：
    今天（MMDD）的檔還沒建、而現在已經過了 16:00＝**班次已經換日但沒開新檔**，
    這時候「回傳最新的那份」就是回傳**昨天**那份。0810-1600 就是這樣來的——
    agent 開 `0810-s2-state.json` 拿到 FileNotFoundError，退回昨天那份繼續寫，
    昨天的 398 則全被當成今天的，**全程不報錯**。

    📌 **同一個函式的兩次錯誤方向剛好相反**：原本永遠找不到 → 把還在用的檔切成兩份；
    改成永遠找得到 → 從此不開新檔。**兩次都是靜默的**，所以這次改成大聲失敗。
    正常情況下 `s2_scan.ps1` 的 `New-ShiftState` 會在 16:00 那輪先把檔建好，
    這個例外只在「那一步沒跑到」時觸發——那時候就該停下來，不該猜。
    """
    try:
        cands = [f for f in os.listdir(STATE_DIR) if re.fullmatch(r"\d{4}-s2-state\.json", f)]
    except OSError:
        cands = []
    if cands:
        today = datetime.now().strftime("%m%d")
        if datetime.now().hour >= 16 and f"{today}-s2-state.json" not in cands:
            newest = max(cands, key=lambda f: os.path.getmtime(os.path.join(STATE_DIR, f)))
            raise SystemExit(
                f"⛔ 班次已換日但今天的狀態檔還沒建：找不到 {today}-s2-state.json，"
                f"現有最新的是 {newest}（那是上一班的）。\n"
                f"   **不要**就這樣用上一班那份——0810-1600 就是這樣把昨天 398 則"
                f"整包當成今天的。\n"
                f"   正常流程：`s2_scan.ps1` 的 16:00 輪會自動建檔。手動要建就跑：\n"
                f"     pwsh -File scripts\\s2_scan.ps1 -Checkpoint {today}-1600 -DryRun\n"
                f"   確定要對上一班那份動作，就明確帶 --file 指定它。")
        newest = max(cands, key=lambda f: os.path.getmtime(os.path.join(STATE_DIR, f)))
        return os.path.join(STATE_DIR, newest)
    return os.path.join(STATE_DIR, f"{datetime.now().strftime('%m%d')}-s2-state.json")


DEFAULT_FILE = default_file()


TOP_FIELDS = ("checkpoint", "updated_at", "window_local",
              "rt_status", "ap_status", "cnn_status", "notes",
              # WP1（2026-08-03）：render 全量重生成 txt，這三個只能存在狀態檔裡——
              # alerts＝檔頭 🔴 重大提醒行（沒有舊 txt 可沿用了）；
              # special_category＝第一格機動大分類的顯示名（如「熊本地震」）；
              # last_render_ts＝上次 render 時間，resume 用來算「距上次 render 有變動」。
              # window_start（2026-08-04）＝這份交接檔「開檔」的時間（第一輪掃描窗的
              # 起點，如 `2026-08-04 13:00`），**建檔那一輪寫一次就不要再動**。
              # 檔頭時間窗＝window_start → 目前 checkpoint，才看得出累計掃了多久；
              # window_local 是單輪區間、每輪覆蓋，不能拿來當檔頭（0804 實錯）。
              "alerts", "special_category", "last_render_ts", "window_start")


def load(path):
    """讀取正式 schema（items 為陣列）並在記憶體中轉成 dict 方便索引。"""
    if not os.path.exists(path):
        return {"date": datetime.now().strftime("%m%d"), "_top": {}, "items": {}}
    try:
        with open(path, encoding="utf-8-sig") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: 狀態檔讀取失敗（{e}）。請確認檔案未損壞後重跑；不要手動改 JSON。")
        sys.exit(2)
    # 頂層一律全收（不只白名單）：白名單漏掉的欄位會在下一次 save 靜默消失，
    # 未來新增欄位若忘了加進 TOP_FIELDS 就會掉資料。TOP_FIELDS 只管 set-top 能改哪些。
    top = {k: v for k, v in raw.items() if k not in ("items", "date")}
    items = raw.get("items", [])
    if isinstance(items, list):  # 正式 schema
        items = {it["id"]: {k: v for k, v in it.items() if k != "id"} for it in items}
    return {"date": raw.get("date", datetime.now().strftime("%m%d")),
            "_top": top, "items": items}


def save(state, path):
    """寫回正式 schema：items 還原成陣列、每筆帶回 id。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    out = dict(state.get("_top", {}))
    out["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    out["items"] = [dict(id=i, **v) for i, v in state["items"].items()]
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def norm_id(s):
    return s.strip().replace("RTV", "RT", 1) if s.strip().startswith("RTV") else s.strip()


def scratch_dir(mmdd, base_dir=None):
    """回傳（並確保建立）某晚班次的暫存檔資料夾：{base_dir}/{YYYYMMDD}/。

    2026-08-03 深夜訂案：每輪批次擷取的暫存檔（_ap_*／_rt_*／{MMDD}-batch-*
    這類中間檔）一律進這個資料夾，不要散在 `自動掃帶系統/` 這層——
    正式庫存檔（{MMDD}-s2-state.json／{MMDD}晚班交接.txt）不受影響，維持原位。
    日期用「晚班起始日」的 MMDD，不是實際掃帶當下的日曆日，跟「檔名不換日」同邏輯：
    8/3 晚班開的班次，8/4 凌晨到早上的暫存檔一樣進 `20260803/`。
    """
    base = base_dir or os.path.dirname(DEFAULT_FILE)
    d = os.path.join(base, f"{datetime.now().year}{mmdd}")
    os.makedirs(d, exist_ok=True)
    return d


def now_ts():
    # 微秒精度：同一秒內「整併完又改一次」的更新必須抓得到，秒精度會相等而漏掉
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")


def changed_since_render(v, last_render_ts):
    """距上次 render 後有變動？（WP1 取代原本的「待整併」）

    render 每輪全量重生成 txt，「哪些還沒整併」不再影響產出——這個數字只剩
    「上次 render 之後動過幾則」的參考值。比較一律用腳本自己寫的 `entry_updated_ts`，
    不要用 checkpoint 標籤：標籤是 agent 自由命名的字串，字串比較會出錯
    （`"r10" < "r8"`，0803 實錯漏掉 50 則）。
    note（needs-review 的純備註殼）不算——它沒有內容可整併。
    """
    if v.get("script_status") == "note":
        return False
    if not last_render_ts:
        return True                      # 還沒 render 過＝全部都待 render
    return (v.get("entry_updated_ts") or "") > last_render_ts


def cmd_resume(state, args):
    items = state["items"]
    last_render = state.get("_top", {}).get("last_render_ts") or ""
    pend = [i for i, v in items.items() if v.get("script_status") == "pending"]
    todo = [i for i, v in items.items() if changed_since_render(v, last_render)]
    review = [i for i, v in items.items() if v.get("needs_review")]
    cps = sorted({v.get("last_checked_checkpoint", "") for v in items.values() if v.get("last_checked_checkpoint")})
    print(f"日期:{state.get('date','?')} 共{len(items)}則 pending:{len(pend)} "
          f"上次render後有變動:{len(todo)} 待人工:{len(review)}")
    print(f"最近檢查點:{cps[-1] if cps else '無'}｜上次render:{last_render or '（尚未）'}")
    if pend:
        print("pending: " + ",".join(sorted(pend)))
    if review:
        print("待人工: " + ",".join(sorted(review)))
    print("下一步：批次擷取用 diff 找新素材；整併用 set-category --pairs 後跑 s2_render.py。")


def cmd_diff(state, args):
    ids = [norm_id(x) for x in args.ids.split(",") if x.strip()]
    new, seen = [], []
    for i in ids:
        if i in state["items"]:
            state["items"][i]["last_checked_checkpoint"] = args.checkpoint
            seen.append(i)
        else:
            new.append(i)
    save(state, args.file)
    print("NEW: " + (",".join(new) if new else "(無)"))
    pend_seen = [i for i in seen if state["items"][i].get("script_status") == "pending"]
    if pend_seen:
        print("已在庫但稿未到（順手可補）: " + ",".join(pend_seen))
    print(f"已在庫 {len(seen)} 則已更新 last_checked={args.checkpoint}")


def read_entry(args):
    if args.entry is not None and args.entry_file:
        print("ERROR: --entry 與 --entry-file 擇一，不可同時給")
        sys.exit(2)
    if args.entry is not None:
        return args.entry.strip()
    if args.entry_file:
        with open(args.entry_file, encoding="utf-8-sig") as f:
            return f.read().strip()
    print("ERROR: 需要 --entry（行內短內容）或 --entry-file（長內容）")
    sys.exit(2)


# NS `footageType` → 有無訪問聲音（2026-08-04 依 0731–0804 全庫存交叉統計訂定，
# 非憑印象列舉；完整對照表與實測數字見 13b §1a-3）。
# 這是 NS 的 BITE 兜底依據——NS 稿件不用 SOUNDBITE 這個詞、數不出 sb_count，
# 在此之前 NS 是三站裡唯一完全沒有兜底的。
FT_MUST_BITE = {"SOT", "BUTTED SOTS", "SOT RAW", "ISO", "DONUT", "INTERVIEW", "RAW"}
FT_GRAY = {"PKG"}          # 實測 7 無／8 有，真的混合——只印提醒，不寫 needs_review


CJK_RE = re.compile(r"[㐀-鿿豈-﫿　-〿＀-￯]")


def strip_agent_note(src_text):
    """剝掉 agent 附在 `src_text` 尾巴的中文說明，回傳 (乾淨原文, 被剝掉的說明)。

    ⚠️ **`src_text` 應該只放站方原文**（`13b` §543：抽取白名單瘦身後的稿件全文），
    它是**事後離線查證的唯一依據**——混進判斷說明，後面每一個讀它的機制都會不可靠。

    **實錯（2026-08-09，RT4131）**：agent 在原文尾巴接了一段
    「（說明：sb_count=0 係因路透 captioned 格式，story 以「STORY: ::」開頭、
    無 SHOTLIST 段，故數不到 SOUNDBITE 字樣…）」，裡面的「SHOTLIST」「SOUNDBITE」
    字樣**害假 BITE 判準誤判**、讓同一則誤報連續四輪。

    判準：三站原文一律是英／西文，**只要出現中文就幾乎必然是 agent 寫的**。
    ⚠️ 不可用「中文字比英文字多」當判準（第一版就是這樣寫、當場失效）：
    agent 的說明裡夾了 `sb_count`／`captioned`／`SHOTLIST` 等英文詞，
    字母數反而多過中文字，整段就被放行了。**有沒有中文才是訊號，不是誰比較多。**

    只剝**尾端連續**的含中文行，遇到第一行完全沒有中文的就停手——
    ⛔ 不從中間挖，也不改動檔案本身（證據要留著）。
    """
    t = src_text or ""
    if not t:
        return t, ""
    lines = t.split("\n")
    cut = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if not s:                      # 空行跟著一起帶走，但不單獨當判準
            continue
        if CJK_RE.search(s):
            cut = i
        else:
            break
    if cut >= len(lines):
        return t, ""
    return "\n".join(lines[:cut]).rstrip(), "\n".join(lines[cut:]).strip()


def sb_applicable(src_text):
    """`sb_count` 這個數字有沒有意義？（2026-08-09）

    它是數稿件裡 `SOUNDBITE` 字樣的次數。**只有在「這種格式本來就會寫 SOUNDBITE」
    的前提下，0 才等於「沒有引言」**；否則 0 只代表「數不出來」，兩者天差地遠。

    路透的 captioned／rough-cut 社群短片**沒有 SHOTLIST 段、也不寫 SOUNDBITE**，
    引言是直接以「姓名，職銜」＋引號段落呈現的。0808–0809 一夜就誤報三次
    （RT4107／RT4131／RT4125），每一則都要人工回頭查證再結案。
    ⚠️ **重複誤報會把警告訓練成雜訊，那比不報還糟。**

    NS 早就撞過同一個問題（NS 稿件不用 SOUNDBITE 這個詞），解法是改看
    `footage_type`（見 FT_MUST_BITE）——這裡是同一個道理的第二次應用。

    ⛔ **判準刻意保守**：只要稿內出現 shotlist 的**結構標記**，就代表這份稿子
    「會寫」，`sb_count=0` 仍然有意義、照樣要擋。這樣才不會把 0805 那批
    AP Live Choice 假 BITE（那些是有 SHOTLIST 的）一起放行。
    沒有原文可判時（`src_text` 空）維持原行為。

    ⚠️ **只認結構標記，不認裸字**（2026-08-09 二次修正）：第一版寫成
    `"SHOTLIST" in t`，結果被 **agent 自己寫進 `src_text` 的中文說明**騙倒——
    RT4131 的 `src_text` 尾巴被附了一段判斷備註，裡面剛好有「無 SHOTLIST 段」
    「數不到 SOUNDBITE 字樣」，裸字比對就命中了，於是照樣誤報。
    真正的標記長這樣：`SHOTLIST:`（帶冒號）、`(SOUNDBITE)`（帶括號），
    散文提到時不會這樣寫。
    📌 附帶問題：`src_text` 應該只放站方原文，不該混入 agent 的判斷說明——
    但偵測本身不該假設上游一定乾淨，所以這裡自己擋住。
    """
    clean, _ = strip_agent_note(src_text)   # agent 的中文說明不算原文（RT4131 實錯）
    t = clean.upper()
    if not t:
        return True                       # 沒有原文就照舊，不放寬
    return bool(re.search(r"SHOTLIST\s*:", t) or re.search(r"\(\s*SOUNDBITE", t))


def bite_doubt(entry, sb_count=None, footage_type=None):
    """BITE 標記可疑嗎？回傳疑慮說明，沒問題回 None。

    ⚠️ **只判斷「BITE 標記對不對」，不判斷「該不該收錄」**（2026-08-05 訂正）。

    原本這兩條判準寫成**拒收閘門**（`continue` 整筆丟棄），那是設計錯誤：
    統計上的「零例外」被當成邏輯上的必然。0805 實錯 `SE-005WE`——曼菲斯主播
    直播打瞌睡的花絮，`footageType=RAW` 但**真的沒有任何引言**（稿內只有
    `(pause :12 seconds for nat)` 留 12 秒自然音）。`RAW` 是「原始素材」，
    不是「一定有人講話」。素材被整筆丟棄、只在終端機印一行就消失，
    使用者與下一輪 agent 都無從得知曾經有過這則。

    現在改成**照收＋把疑慮寫進 `needs_review`**：資料不會消失，疑慮也不會消失
    （`resume` 每輪列出「待人工」，確認後用 `needs-review done` 結案）。
    ⛔ **不要再改回拒收**——兜底的價值是提醒漏標，不是替使用者決定收不收。
    """
    e = entry or ""
    # ── 反向：標了 (BITE) 卻一個 SOUNDBITE 都沒有（2026-08-05 補，AP 實錯 7 則）──
    # 這比漏標更糟：編輯看到 (BITE) 以為有可掐的話，調出來只有環境音，白費一趟。
    # 典型來源是 **AP Live Choice**（直播原始錄影、未經編審、沒有逐字稿）——
    # `editorialrole` 標 SOT 只代表「素材形式含現場聲」，不代表「有可引用的引言」。
    if "無BITE" not in e and "(BITE)" in e and isinstance(sb_count, int) and sb_count == 0:
        return ("標了 (BITE) 但稿內沒有任何 SOUNDBITE——"
                "「現場原音」「逐字稿未附」不是 BITE；確認有可引用的引言原文，"
                "否則改標「無BITE。」並在第一括號寫素材形態（如 直播原始帶／現場原音）")
    if "無BITE" not in e:
        return None
    if isinstance(sb_count, int) and sb_count > 0:
        return (f"稿內有 {sb_count} 個 SOUNDBITE 卻標「無BITE」——"
                f"多半是漏把引言寫進 ▎BITE： 段；確認真的沒有可用引言才留著")
    ft = str(footage_type or "").strip().upper()
    if ft in FT_MUST_BITE:
        return (f"footageType={ft} 通常必有訪問聲音卻標「無BITE」——"
                f"確認是真的沒有引言（純花絮／自然音／字卡）還是漏寫")
    return None


def new_item(source, checkpoint, status, entry, sb_count=None):
    it = {
        "source": source,
        "first_seen_checkpoint": checkpoint,
        "last_checked_checkpoint": checkpoint,
        "script_status": status,
        "raw_entry": entry,
        "entry_updated": checkpoint,
        "entry_updated_ts": now_ts(),
        "compiled": None,
        "category": None,
    }
    # sb_count 存進狀態檔（2026-08-09）：在此之前它只活在 batch 中間檔裡，
    # 而 batch **停在送出當下、事後不回寫**——素材由 pending 轉正、站方補上完整稿之後
    # sb_count 就過期了，稽核③ 會對同一則**永久重複誤報**假 BITE
    # （0809-0100 的 RT4098：收錄時真的 0 個，站方 RESENDING 後實際有 5 個）。
    # 狀態檔＝唯一真相源，機械事實也該存在這裡。
    if isinstance(sb_count, int):
        it["sb_count"] = sb_count
    # 結構化欄位由腳本推導（2026-08-04 新增，見 s2_parse）：agent 完全無感、
    # 不必多寫一份。解析失敗只標 parse_ok:false，**不擋入庫**。
    sp.derive(it)
    return it


def cmd_add(state, args):
    i = norm_id(args.id)
    if i in state["items"]:
        print(f"ERROR: {i} 已存在，要更新內容請用 update-entry")
        sys.exit(2)
    entry = read_entry(args)
    state["items"][i] = new_item(args.source, args.checkpoint, args.status, entry)
    # BITE 疑慮判斷與 add-batch 一致（2026-08-05 補）：原本單筆完全不檢查，
    # 是意外留下的後門——0805 那則被 add-batch 擋掉的素材就是靠 `add` 繞過收進來的。
    # 兩條路徑行為不一致時，人會往阻力小的那條走，兜底等於形同虛設。
    doubt = bite_doubt(entry, args.sb_count, args.footage_type)
    if doubt:
        state["items"][i]["needs_review"] = doubt
    save(state, args.file)
    print(f"OK 已新增 {i}（{args.status}）")
    report_fmt([f"{i}: {r}" for r in fmt_issues(entry)])
    if doubt:
        print(f"⚠️ BITE 待確認（已入庫，已記進 needs-review）：{doubt}")


def fmt_issues(entry):
    """寫入當下就跑一次素材行格式檢查（2026-08-11 加）。

    🔴 **為什麼要在這裡檢查**：品質掃原本只綁在 `s2_render.py` 上，等於「有人記得
    render 才會被檢查」。0811-0100 那輪 01:20 收工並 render 完畢後，**另有 35 則素材
    在 01:33–01:35 才寫進狀態檔**——那批完全沒經過任何一次品質掃，交接單就帶著
    52 項格式問題掛在那裡給編輯看。輪次外寫入等於從側門進來，直接繞過關卡。

    把關卡挪到寫入當下，不管誰寫、有沒有 render 都躲不掉。
    ⚠️ 只警告不擋——擋下會中斷整輪掃帶，代價比格式瑕疵大得多。
    """
    try:
        return load_validate().check_entry(entry)
    except Exception:
        return []            # 檢查本身壞掉絕不能擋住入庫


def report_fmt(fmt):
    """把寫入當下抓到的格式問題印出來。訊息要吵，因為這是最省成本的修正時機。"""
    if not fmt:
        return
    print(f"⚠️ 格式待修 {len(fmt)} 項（**已入庫**，請直接用 `update-entry` 改掉，"
          f"不要等 render 才發現）：")
    print("\n".join("  " + x for x in fmt))


def cmd_add_batch(state, args):
    """整批新增。撞已存在 id 或格式錯的單筆一律跳過並回報，不中斷；只在結尾 save 一次。"""
    try:
        with open(args.entries, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: --entries 檔讀取失敗（{e}）")
        sys.exit(2)
    if isinstance(data, dict):
        data = data.get("entries")
    if not isinstance(data, list):
        print("ERROR: --entries 需為 JSON 陣列（或含 entries 陣列的物件）")
        sys.exit(2)
    added, skipped, notes, flagged, fmt = [], [], [], [], []
    for n, e in enumerate(data, 1):
        if not isinstance(e, dict):
            skipped.append(f"第{n}筆: 不是物件")
            continue
        missing = [k for k in ("id", "source", "checkpoint", "status", "entry") if not e.get(k)]
        if missing:
            skipped.append(f"第{n}筆({e.get('id','?')}): 缺 {','.join(missing)}")
            continue
        if e["status"] not in ("has_script", "pending"):
            skipped.append(f"{e['id']}: status 須為 has_script/pending")
            continue
        if not isinstance(e["entry"], str):
            skipped.append(f"{e['id']}: entry 須為字串")
            continue
        i = norm_id(str(e["id"]))
        if i in state["items"]:
            skipped.append(f"{i}: 已存在（要更新請用 update-entry）")
            continue
        # 🎯 BITE 機械兜底：**照收，把疑慮寫進 needs_review**（2026-08-05 訂正，
        # 原本是 continue 拒收——那會靜默丟掉素材，理由見 bite_doubt()）。
        ft = str(e.get("footage_type") or "").strip().upper()
        # `sb_count=0` 在「這份稿本來就不寫 SOUNDBITE」的格式下是**數不出來**，
        # 不是「沒有」——當成未知（None），別拿去擋（見 sb_applicable）。
        sb = e.get("sb_count")
        if not sb_applicable(e.get("src_text")):
            sb = None
        doubt = bite_doubt(e["entry"], sb, ft)
        if ft in FT_GRAY and "無BITE" in e["entry"]:
            # 灰區訊號弱（實測 7 無／8 有），只印提醒不寫 needs_review，免得洗版
            notes.append(f"{i}: footageType={ft} 標了「無BITE」——PKG 有一半以上其實有訪問，"
                         f"若是 1 分鐘以上的記者包裝請回頭確認一次")
        # 存 `sb` 不是 `e["sb_count"]`：數不出來的格式要存成「沒有這個欄位」，
        # 否則稽核③ 讀狀態檔時又會拿 0 去報一次假 BITE（誤報只是換個地方出現）。
        state["items"][i] = new_item(e["source"], e["checkpoint"], e["status"],
                                     e["entry"].strip(), sb)
        if doubt:
            state["items"][i]["needs_review"] = doubt
            flagged.append(f"{i}: {doubt}")
        for reason in fmt_issues(e["entry"]):
            fmt.append(f"{i}: {reason}")
        added.append(i)
    if added:
        save(state, args.file)
    print(f"OK 新增 {len(added)} 則" + (f"：{','.join(added)}" if added else ""))
    report_fmt(fmt)
    if flagged:
        print(f"⚠️ BITE 待確認 {len(flagged)} 則（**已入庫**，已記進 needs-review，"
              f"確認後用 `needs-review done --ids …` 結案）：")
        print("\n".join("  " + n for n in flagged))
    if notes:
        print(f"提醒 {len(notes)} 則（已入庫，請自行確認）：")
        print("\n".join("  " + n for n in notes))
    if skipped:
        print(f"跳過 {len(skipped)} 則：")
        print("\n".join("  " + s for s in skipped))


def cmd_update_entry(state, args):
    i = norm_id(args.id)
    if i not in state["items"]:
        print(f"ERROR: {i} 不存在，請先 add")
        sys.exit(2)
    it = state["items"][i]
    entry = read_entry(args)
    # 🎯 BITE 兜底（同 add-batch，2026-08-05 由「直接擋」改為「照收＋標記」）：
    # 覆寫時擋下更危險——舊內容已經在庫存裡，擋下只會讓它停在舊版本，
    # 而 agent 以為自己更新過了。
    doubt = bite_doubt(entry, args.sb_count, getattr(args, "footage_type", None))
    it["raw_entry"] = entry
    # 站方補上完整稿後 sb_count 會變（0→5），**這條路就是唯一的回寫時機**——
    # 沒帶就別動舊值（`None` ＝ 沒帶，不是 0；見下方 argparse 的 default 說明）。
    if isinstance(args.sb_count, int):
        it["sb_count"] = args.sb_count
    if args.status:
        it["script_status"] = args.status
    it["entry_updated"] = args.checkpoint or it.get("last_checked_checkpoint", "")
    it["entry_updated_ts"] = now_ts()
    sp.derive(it)                        # 內容變了，結構化欄位跟著重推（見 s2_parse）
    if doubt:
        it["needs_review"] = doubt
    else:
        it.pop("needs_review", None)     # 改好了就自動結案，不用手動 done
    save(state, args.file)
    print(f"OK 已覆寫 {i}（{it['script_status']}）")
    report_fmt([f"{i}: {r}" for r in fmt_issues(it.get("raw_entry") or "")])


# 地區詞 → 樣板上該去的大分類（2026-08-06 訂）。用來抓「中主題放錯大分類」。
# 為什麼有效：agent 命名時會自己把地區寫進中主題名（【美國治安】【美國地方】），
# 它知道這是哪裡的事，只是**沒去想樣板上有沒有專屬的那一格**。名稱就是現成線索。
# ⚠️ 只抓得到「名稱含地區詞」的——【布朗克斯爆炸】放社會格就抓不到。
#    但 0805 實測 7 組全部都有地區詞（那是 agent 自然的命名習慣），
#    所以這是「便宜且抓得到大多數」的方案，不是完備方案。
GEO_HOME = {
    "美國": "美國", "中國": "大陸", "中共": "大陸", "北京": "大陸",
    "台灣": "政治", "台海": "政治", "漢光": "政治",
    "俄羅斯": "烏俄", "俄軍": "烏俄", "俄烏": "烏俄", "烏克蘭": "烏俄", "基輔": "烏俄",
    "伊朗": "美伊", "荷莫茲": "美伊", "德黑蘭": "美伊",
    "以色列": "中東", "加薩": "中東", "黎巴嫩": "中東", "耶路撒冷": "中東",
    "關稅": "關稅",
}
# 題材格：主題明確、獨立收，優先級高於地緣格（2026-08-04 使用者裁示）。
# 落在這幾格的中主題即使名稱含地區詞也不提示（美股歸財經是對的）。
# ⚠️ `社會`／`天氣`／`話題` 算不算題材格**尚未裁定**，所以暫不列入——
#    未裁定的案例會持續被提示，等於提醒使用者去裁定，而不是靜靜累積。
TOPIC_SLOTS = {"財經", "娛樂", "體育"}


def misplaced_topics(state):
    """找出「中主題名稱含地區詞、卻放在別的大分類」的組合。

    回傳 [(現在的大分類, 中主題, 則數, 命中的地區詞, 建議的大分類)]。
    """
    counts = {}
    for v in state.get("items", {}).values():
        c = v.get("category") or {}
        big, mid = c.get("大分類"), c.get("中主題") or ""
        if big:
            counts[(big, mid)] = counts.get((big, mid), 0) + 1
    out = []
    for (big, mid), n in sorted(counts.items()):
        if big in TOPIC_SLOTS:
            continue                      # 題材格優先，不提示
        for word, home in GEO_HOME.items():
            if word in mid and big != home:
                out.append((big, mid, n, word, home))
                break
    return out


def cmd_list_topics(state, args):
    """印出目前各大分類底下的中主題與則數——**開新中主題前必跑**。

    2026-08-05 訂案。要解的是中主題重複的**真正成因：agent 每輪獨立命名、
    看不到既有清單**。0805 實例：20:00 那輪替基輔攻擊開了【俄襲烏克蘭】，
    但 16:30 輪已經有【基輔空襲】——兩個名稱都合理，卻分裂成兩個中主題
    （當天 77 個中主題人工合併後剩 55）。這是「看不到」不是「不想用」，
    所以先給視野、再談命名規則。

    成本近乎零：只讀狀態檔，零瀏覽器呼叫、零 API。
    """
    rows = {}
    for v in state["items"].values():
        c = v.get("category") or {}
        big, mid = c.get("大分類"), c.get("中主題")
        if not big:
            continue
        rows.setdefault(big, {}).setdefault(mid or "(未填)", []).append(c.get("小分題") or "")
    if not rows:
        print("(目前沒有任何已分類的素材)")
        return
    # 大分類依則數排序；中主題用 render 的靠攏順序，看到的排列與 txt 一致
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from s2_render import order_topics
    except Exception:
        def order_topics(x):
            return x
    total = 0
    for big in sorted(rows, key=lambda b: -sum(len(v) for v in rows[b].values())):
        mids = rows[big]
        n = sum(len(v) for v in mids.values())
        total += n
        print(f"■ {big}（{n} 則 / {len(mids)} 個中主題）")
        for m in order_topics(list(mids)):
            subs = [x for x in mids[m] if x]
            tail = f"　└ {'／'.join(sorted(set(subs)))}" if args.subs and subs else ""
            print(f"    【{m}】×{len(mids[m])}{tail}")
    print(f"\n合計 {total} 則 / {sum(len(v) for v in rows.values())} 個中主題")
    print("⚠️ 要開新中主題前先看這份：同一事件已經有名字就沿用，不要另起爐灶。")
    mis = misplaced_topics(state)
    if mis:
        print(f"\n🔴 疑似放錯大分類 {len(mis)} 組（名稱含地區詞、但樣板上有專屬格）：")
        for big, mid, n, word, home in mis:
            print(f"    {big}／【{mid}】×{n}  ← 含「{word}」，樣板上「{home}」在前")
        print("    處置：確認後用 set-category 搬過去；若判定該留原格，"
              "代表該格是題材格——回報使用者裁定，不要自己改規則。")


def cmd_scratch_dir(state, args):
    """印出（並建立）今晚班次的暫存檔資料夾路徑，供 agent 開工時取用。"""
    print(scratch_dir(args.mmdd))


def cmd_pending(state, args):
    pend = sorted(i for i, v in state["items"].items() if v.get("script_status") == "pending")
    print("\n".join(pend) if pend else "(無 pending)")


def cmd_set_category(state, args):
    if args.pairs and (args.id or args.cat):
        print("ERROR: --pairs 與 --id/--cat 擇一，不可混用")
        sys.exit(2)
    if not args.pairs:
        if not (args.id and args.cat):
            print("ERROR: 單筆需 --id 與 --cat；批次用 --pairs \"id=大分類/中主題;...\"")
            sys.exit(2)
        _set_one_category(state, args.id, args.cat, strict=True)
        save(state, args.file)
        return
    # 批次：分隔符優先用「;」；沒有分號才退回逗號（中主題含逗號時務必用分號）
    sep = ";" if ";" in args.pairs else ","
    done, skipped = [], []
    for tok in (t.strip() for t in args.pairs.split(sep)):
        if not tok:
            continue
        if "=" not in tok:
            skipped.append(f"「{tok}」: 缺 =（格式 id=大分類/中主題）")
            continue
        i, cat = tok.split("=", 1)
        err = _set_one_category(state, i, cat, strict=False)
        (skipped if err else done).append(err or norm_id(i))
    if done:
        save(state, args.file)
    print(f"OK 設定 {len(done)} 則" + (f"：{','.join(done)}" if done else ""))
    if skipped:
        print(f"跳過 {len(skipped)} 則：")
        print("\n".join("  " + s for s in skipped))


def _set_one_category(state, raw_id, cat, strict):
    """設定單筆 category。strict=True 出錯直接 exit；否則回傳錯誤訊息字串。

    cat 格式：`大分類/中主題` 或 `大分類/中主題/小分題`（小分題選填）。
    小分題是 WP1 加的第三層——render 全生三層結構（裸行標題＋`+` 分隔），
    舊資料沒這欄位時該層省略，屬正常（見 13「三層骨架」）。
    """
    i = norm_id(raw_id)
    if i not in state["items"]:
        msg = f"{i}: 不存在"
    elif "/" not in cat:
        msg = f"{i}: cat 需為「大分類/中主題[/小分題]」（例：社會/休達移民/岸際動態）"
    else:
        parts = [p.strip() for p in cat.split("/", 2)]
        big, mid = parts[0], parts[1]
        sub = parts[2] if len(parts) > 2 else ""
        c = {"大分類": big, "中主題": mid}
        if sub:
            c["小分題"] = sub
        state["items"][i]["category"] = c
        print(f"OK {i} category={big}／{mid}" + (f"／{sub}" if sub else ""))
        return None
    if strict:
        print("ERROR: " + msg)
        sys.exit(2)
    return msg


def load_validate():
    """載入同目錄的 s2_validate（共用行辨識 regex，不重寫一套）。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import s2_validate
    return s2_validate


def parse_side_txt(text, source=None, homes=None, normalize=False, tc_date=None):
    """把側錄 TXT 解析成狀態檔項目。

    吃兩種寫法（都用同一套三層結構辨識）：
      1. 直接沿用晚班交接 txt 的排版：`======大分類======` / `【中主題】` /
         小分題裸行 / `+` 分隔 / 側錄兩行式區塊。
      2. 篩選 agent 的候選 TXT：每則前面帶
         `擬歸位：======大分類====== → 【中主題】 → 小分題`（見 14-S2b）。

    `source`（CNN／NHK）：檔案裡的 TC 行**沒有來源前綴**時（歐印萬原始檔多半如此，
    只有裸 TC）自動補上。不補的話 `SIDE_RE` 認不出來，整份會解析出 0 段。
    `homes`：`{TC 數字: (大分類, 中主題, 小分題)}`，給檔內沒寫「擬歸位」的情形——
    agent 只要吐 TC 就能指定歸位，不必把整段逐字內容重打一遍（省 token）。

    回傳 [(id, source, category, raw_entry)]；raw_entry 是**去掉時段標記後的原文**
    （TC 行＋內容行），時段標記由 render 依 first_seen_checkpoint 自動補。
    """
    sv = load_validate()
    lines = text.replace("\r\n", "\n").split("\n")
    if normalize:  # 先把隨手存的格式整成定版兩行式（純位置搬移，見 normalize_side）
        lines = normalize_side(lines, source, sv, tc_date)
    if source:   # 裸 TC 行補來源前綴：`160106（主播）` → `CNN 160106（主播）`
        bare = re.compile(rf"^({sv._TC})(?=[\s（(]|$)")
        lines = [bare.sub(source + r" \1", l.strip(), count=1)
                 if bare.match(l.strip()) else l for l in lines]
    homes = homes or {}
    big = mid = sub = ""
    out, cur = [], None

    def flush():
        if cur:
            out.append(cur)

    for raw in lines:
        _, l = sv.strip_mark(raw)
        s = l.strip()
        m_home = re.match(r"^擬歸位[：:]\s*(.+)$", s)
        if m_home:
            flush()
            cur = None
            segs = [x.strip() for x in re.split(r"→|->", m_home.group(1))]
            big = segs[0].strip("= ") if segs else big
            mid = segs[1].strip("【】 ") if len(segs) > 1 else ""
            sub = segs[2].strip() if len(segs) > 2 else ""
            continue
        if s.startswith("======") or (s.startswith("=") and s.endswith("=")):
            flush()
            cur = None
            big, mid, sub = s.strip("= "), "", ""
            continue
        if s.startswith("【") and s.endswith("】"):
            flush()
            cur = None
            mid, sub = s.strip("【】"), ""
            continue
        if s == "+":
            flush()
            cur = None
            sub = ""            # 下一個裸行＝新的小分題
            continue
        if not s:
            flush()
            cur = None
            continue
        if sv.SIDE_RE.match(l):
            flush()
            # 日期段可有可無（舊資料沒有），有的話要一起進 id
            src, dt, tc = re.match(
                rf"^(CNN|NHK) (?:(\d{{2}}-\d{{2}}) )?({sv._TC})", l).groups()
            h = homes.get(re.sub(r"\D", "", tc))    # --homes 指定的歸位優先（用純數字 TC 當鍵）
            b2, m2, s2 = h if h else (big, mid, sub)
            cat = {"大分類": b2, "中主題": m2}
            if s2:
                cat["小分題"] = s2
            key = " ".join(x for x in (src, dt or "", tc) if x)
            cur = (key, f"SIDE_{src}", cat, l.rstrip())
            continue
        if sv.LINE_RE.match(l):   # 通訊社素材行：不是側錄，跳過（供混排 txt 直接餵）
            flush()
            cur = None
            continue
        if cur:                   # 內容行：接在 TC 行底下
            cur = (cur[0], cur[1], cur[2], cur[3] + "\n" + l.rstrip())
        else:                     # 裸行且不在區塊內＝小分題標題
            sub = s
    flush()
    return out


def normalize_side(lines, source, sv, tc_date=None):
    """把上傳者隨手存的側錄檔整成 14-S2b 定版兩行式（**純位置搬移，不改任何一個字**）。

    上傳側錄的人不一定懂格式（2026-08-03 使用者指出），所以能用機械規則解掉的
    一律在這裡解掉，不要丟給模型逐字重打——側錄有「逐字一字不能改」的鐵律，
    模型重打就有潤稿風險。認不得的形狀一律原樣留著，交給 add-side 回報。

    做四件事：
      1. TC 正規化：`16:01:06-16:01:51` 範圍 → 取起點；冒號去掉 → 6 碼 `160106`。
      2. TC 行與內容黏在同一行 → 拆成兩行（TC 行／內容行）。
      3. 內容行開頭的 `（角色…）` → 搬到 TC 行尾（TC 行本身沒有 SUPER 時才搬）。
      4. 純分隔線（`---`／`___`／`***`）丟掉；其餘雜訊行原樣保留。
      5. **補日期**（`tc_date`，格式 `MM-DD`，2026-08-09 加）：側錄是跨夜的，
         光看 `151542` 分不出是哪一天。原本已帶日期的行不重複加。
    """
    # ⚠️ 日期段要**可有可無**：檔案可能已經帶日期（重跑正規化、或上傳者自己寫了），
    #    不認的話整行會被當成內容行、TC 就此消失。
    tc_head = re.compile(rf"^(?:(CNN|NHK)\s+)?(?:(\d{{2}}-\d{{2}})\s+)?({sv._TC})\s*(.*)$")
    role = re.compile(r"^\s*([（(][^）)]{1,30}[）)])\s*")
    out = []
    for raw in lines:
        l = raw.rstrip()
        t = l.strip()
        if re.fullmatch(r"[-_*=]{3,}", t):
            continue                                   # 純分隔線
        # `=== 0803 CNN側錄 ===` 這種標題行是雜訊，但 `======大分類======`（6個等號）
        # 是候選 TXT 的歸位標記，不能丟——只砍等號少於 6 個的
        if re.fullmatch(r"={1,5}[^=]+={1,5}", t):
            continue
        m = tc_head.match(l.strip())
        if not m:
            # 內容行：開頭若有角色標示，且上一行是剛產出的 TC 行且沒 SUPER，就搬上去
            r = role.match(l)
            if r and out and tc_head.match(out[-1]) and not role.search(out[-1]):
                out[-1] = out[-1] + " " + r.group(1)
                l = l[r.end():]
                if not l.strip():
                    continue
            out.append(l)
            continue
        src, date_in, tc, rest = m.groups()
        tc6 = re.sub(r"\D", "", re.split(r"\s*[-–~]\s*", tc)[0])[:6]   # 範圍取起點、去冒號
        # 檔案自己帶的日期優先——那是上傳者的判斷，不要用推算的蓋掉
        head = " ".join(x for x in (src or source or "", date_in or tc_date or "", tc6) if x)
        r = role.match(rest)
        if r:                                          # `160106（主播）內容…`
            head += " " + r.group(1)
            rest = rest[r.end():]
        out.append(head)
        if rest.strip():                               # TC 行後面黏著內容 → 拆行
            out.append(rest.strip())
    return out


def cmd_add_side(state, args):
    """把側錄 TXT 收進狀態檔（WP1 前提二：不入狀態檔，隔夜 render 會把它刪掉）。"""
    try:
        with open(args.txt, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as e:
        print(f"ERROR: 側錄檔讀取失敗（{e}）")
        sys.exit(2)
    homes = {}
    for tok in (t.strip() for t in (args.homes or "").split(";")):
        if not tok:
            continue
        if "=" not in tok:
            print(f"ERROR: --homes 格式為 大分類/中主題[/小分題]=TC,TC;… ，這段不合：{tok}")
            sys.exit(2)
        cat, tcs = tok.split("=", 1)
        parts = [x.strip() for x in cat.split("/", 2)] + ["", ""]
        for tc in tcs.split(","):
            if tc.strip():
                homes[re.sub(r"\D", "", tc)] = (parts[0], parts[1], parts[2])
    # ── TC 日期（2026-08-09 加）：側錄跨夜，光看 `151542` 分不出哪一天 ──
    # 預設取本輪 checkpoint 的日期；檔案自己帶日期時以檔案為準（見 normalize_side）。
    tc_date = args.tc_date
    if not tc_date:
        m = re.match(r"(\d{2})(\d{2})", args.checkpoint or "")
        tc_date = f"{m.group(1)}-{m.group(2)}" if m else None
    parsed = parse_side_txt(text, args.source, homes, args.normalize, tc_date)

    # ⚠️ 跨夜防呆：凌晨的輪次收到晚上的 TC，多半是**前一天**錄的。
    #    這裡只警告不自動改——猜錯會把日期寫成錯的，而錯的日期比沒有日期更難發現。
    cp_h = int(re.search(r"-(\d{2})", args.checkpoint or "-99").group(1) or 99)
    if not args.tc_date and cp_h < 6:
        late = [p[0] for p in parsed
                if re.search(r"(\d{2})\d{4}$", p[0]) and int(re.search(r"(\d{2})\d{4}$", p[0]).group(1)) >= 18]
        if late:
            print(f"⚠️ 本輪是凌晨 {cp_h:02d} 點，但有 {len(late)} 段 TC 是晚上（18:00 後）——"
                  f"多半是前一天錄的，日期可能要用前一天。確認後用 --tc-date MM-DD 指定。")
            print("   涉及：" + "／".join(late[:5]))

    if not parsed:
        print("ERROR: 沒解析到任何側錄段落（TC 行格式須為 `CNN 160106（主播）`）")
        sys.exit(2)
    added, updated, bad = [], [], []
    for i, src, cat, entry in parsed:
        if not cat.get("大分類"):
            bad.append(f"{i}: 沒有大分類（候選 TXT 需標擬歸位，或沿用 txt 三層排版）")
            continue
        if i in state["items"] and not args.overwrite:
            updated.append(i)      # 已在庫＝往輪次重跑，內容照舊不動（側錄人工定稿）
            continue
        it = state["items"].get(i) or new_item(src, args.checkpoint, "has_script", entry)
        it["source"] = src
        it["raw_entry"] = entry
        it["category"] = cat
        it["entry_updated"] = args.checkpoint
        it["entry_updated_ts"] = now_ts()
        state["items"][i] = it
        added.append(i)
    if args.dry_run:
        print(f"DRY-RUN 解析 {len(parsed)} 段：新增/覆寫 {len(added)}、已在庫略過 {len(updated)}")
        # 預覽前兩段：格式錯了要當場看得出來，不要等進了狀態檔才發現
        for i, src, cat, entry in parsed[:2]:
            print(f"  ── {i}（{src}）→ {cat.get('大分類') or '(缺大分類)'}／"
                  f"{cat.get('中主題') or '(缺中主題)'}／{cat.get('小分題') or '-'}")
            for ln in entry.split("\n")[:2]:
                print(f"     {ln[:60]}")
    else:
        if added:
            save(state, args.file)
        print(f"OK 收錄側錄 {len(added)} 段" + (f"：{','.join(added[:8])}…" if len(added) > 8
                                            else (f"：{','.join(added)}" if added else "")))
        if updated:
            print(f"已在庫略過 {len(updated)} 段（要覆蓋加 --overwrite）")
    if bad:
        print(f"跳過 {len(bad)} 段：")
        print("\n".join("  " + b for b in bad))


def cmd_set_mark(state, args):
    """寫死某幾則的時段標記（render 預設由 first_seen_checkpoint 推）。

    用在 checkpoint 判不準的輪次——最典型是**補掃輪**：09:10 的 `r13-…-RT補掃`
    撈回的是稍早該收而漏掉的素材，照 checkpoint 會標成 `■`（07:00–09:00 新增），
    但它們實際屬 `▲` 那個時段。標記寫進該則的 `mark` 欄位，render 一律優先採用。
    """
    ids = [norm_id(x) for x in args.ids.split(",") if x.strip()]
    missing = [i for i in ids if i not in state["items"]]
    if missing:
        print(f"ERROR: 不存在的 id：{','.join(missing)}（其餘未變更，請修正後重跑）")
        sys.exit(2)
    for i in ids:
        if args.clear:
            state["items"][i].pop("mark", None)
        else:
            state["items"][i]["mark"] = args.mark
    save(state, args.file)
    print(f"OK {len(ids)} 則標記" + ("已清除（改回自動推算）" if args.clear else f"寫死為 {args.mark}"))


def cmd_set_aired(state, args):
    """標記／取消「本台已做過這則新聞」（render 會在代碼前印 🟤）。

    2026-08-04 使用者訂案。**素材仍照常留在庫存、照常摘要**——後續發展可能還要再做，
    🟤 只是把優先度降下來，讓編輯一眼略過已處理的，不是「刪掉」也不是「不要收」。
    ⛔ 這是**人工判斷**：外電網站不會知道 TVBS 播過什麼，agent 不得自行推測，
    一律由使用者下令才標（同 `set-alert` 的性質）。
    """
    ids = [norm_id(x) for x in args.ids.split(",") if x.strip()]
    missing = [i for i in ids if i not in state["items"]]
    if missing:
        print(f"ERROR: 不存在的 id：{','.join(missing)}（其餘未變更，請修正後重跑）")
        sys.exit(2)
    for i in ids:
        if args.clear:
            state["items"][i].pop("aired", None)
        else:
            state["items"][i]["aired"] = True
    save(state, args.file)
    verb = "已取消已播標記" if args.clear else "已標為本台已做過（🟤，仍留庫存）"
    print(f"OK {len(ids)} 則{verb}：{','.join(ids)}")


def cmd_set_topic_order(state, args):
    """人工指定某個大分類底下的中主題順序（2026-08-10 使用者訂案）。

    🔴 **為什麼要有這個欄位**：中主題順序原本**完全是 render 當下推導的**
    （到貨順序＋`order_topics()` 相近名稱靠攏），**沒有任何地方存**。
    所以「幫我重排一次」排完就沒了——下一輪 render 照舊演算法重算就蓋掉，
    跟「不要手改 txt」是同一個道理：render 是狀態檔的單向投影。

    - 清單裡**今天不存在**的中主題自動略過，不會憑空生出空標題。
    - 今天**新出現、清單裡沒有**的中主題仍走自動排（插到名稱相近的旁邊），
      所以這份順序不必每天重寫。
    - `--clear` 撤掉某格的人工順序，退回全自動。
    """
    # ⚠️ 頂層欄位一定要寫進 `state["_top"]`，**不是 `state` 本身**——
    #    `save()` 是 `out = dict(state.get("_top", {}))`，寫在 state 上的鍵
    #    根本不會被序列化。2026-08-10 首版寫成 `state.setdefault("topic_order")`，
    #    結果 13 個大分類全部印「OK 已釘住」但**一個都沒存進檔案**，
    #    是典型的靜默失敗（同 `cmd_set_alert` 的寫法才對）。
    top = state.setdefault("_top", {})
    order = top.setdefault("topic_order", {})
    if args.clear:
        order.pop(args.cat, None)
        save(state, args.file)
        print(f"OK 已撤掉「{args.cat}」的人工順序，退回自動排")
        return
    mids = [x.strip() for x in re.split(r"[;；]", args.order or "") if x.strip()]
    if not mids:
        print("ERROR 需要 --order（用分號分隔）或 --clear", file=sys.stderr)
        raise SystemExit(2)
    order[args.cat] = mids
    save(state, args.file)
    print(f"OK 「{args.cat}」中主題順序已釘住 {len(mids)} 個：{'／'.join(mids)}")
    # 對照今天實際有的中主題，把落差講清楚——避免「排了卻沒生效」的靜默困惑
    # ⚠️ 記憶體裡的 `state["items"]` 是 **dict（id → 內容）**，不是陣列——
    #    陣列是 `save()` 寫檔時才還原的。直接 `for it in state["items"]`
    #    會拿到一串 **id 字串**，然後 `it.get(...)` 炸掉（首版實錯）。
    have = {(v.get("category") or {}).get("中主題")
            for v in state.get("items", {}).values()
            if (v.get("category") or {}).get("大分類") == args.cat}
    have.discard(None)
    missing = [m for m in mids if m not in have]
    extra = sorted(have - set(mids))
    if missing:
        print(f"  · 清單有、今天沒有（本輪自動略過）：{'／'.join(missing)}")
    if extra:
        print(f"  · 今天有、清單沒有（走自動排，插到相近主題旁）：{'／'.join(extra)}")


def cmd_set_alert(state, args):
    """檔頭 🔴 重大提醒行（WP1 前提四）。

    render 全量覆蓋 txt，舊 txt 檔頭讀不到了——重大提醒行必須存在狀態檔頂層，
    每輪 render 從這裡取。最多 3 行（全都重大＝都不重大）。
    """
    top = state.setdefault("_top", {})
    cur = list(top.get("alerts") or [])
    if args.clear:
        top["alerts"] = []
    elif args.set:
        # 一次整組取代（與 s2_validate stats --alert 語意一致）
        top["alerts"] = [re.sub(r"^\s*🔴\s*重大[：:]\s*", "", a).strip() for a in args.set][:3]
        if len(args.set) > 3:
            print("(略過超過 3 則的部分：重大提醒上限 3 行)")
    elif args.add:
        cur.append(re.sub(r"^\s*🔴\s*重大[：:]\s*", "", args.add).strip())
        top["alerts"] = cur[-3:]
    else:
        print("\n".join(f"🔴 重大：{a}" for a in cur) if cur else "(無重大提醒行)")
        return
    save(state, args.file)
    print("目前重大提醒：")
    print("\n".join(f"  🔴 重大：{a}" for a in top["alerts"]) or "  (無)")


def cmd_set_top(state, args):
    """設定頂層欄位（window_local／rt_status／ap_status／cnn_status／notes／checkpoint）。"""
    if args.field not in TOP_FIELDS:
        print(f"ERROR: 欄位須為 {'／'.join(TOP_FIELDS)}")
        sys.exit(2)
    state.setdefault("_top", {})[args.field] = args.value
    save(state, args.file)
    print(f"OK {args.field}={args.value}")


def cmd_get(state, args):
    i = norm_id(args.id)
    v = state["items"].get(i)
    if not v:
        print(f"ERROR: {i} 不存在")
        sys.exit(2)
    print(json.dumps(v, ensure_ascii=False, indent=1))


def cmd_remove(state, args):
    """整則刪除（誤收、排除白名單命中等）——與 needs-review 不同：這裡是真的不要，
    不是留著待人工。刪除後 render 那則就不會再出現，不留殼。
    """
    ids = [norm_id(x) for x in args.ids.split(",") if x.strip()]
    missing = [i for i in ids if i not in state["items"]]
    if missing:
        print(f"ERROR: 不存在的 id：{','.join(missing)}（其餘未刪除，請修正後重跑）")
        sys.exit(2)
    for i in ids:
        del state["items"][i]
    save(state, args.file)
    print(f"OK 已刪除 {len(ids)} 則：{','.join(ids)}")


def cmd_needs_review(state, args):
    if args.action == "add":
        if not args.id:
            print("ERROR: add 需要 --id")
            sys.exit(2)
        i = norm_id(args.id)
        # 對不存在的 id（純備註，如「RT-r9-空白」）建 status="note" 的殼，
        # 不是 pending——0803 實錯：7 筆備註殼灌水 pending 計數（60 裡有 7 假的），
        # 且永遠不會被清掉。note 不計入 pending／待整併，只出現在 needs-review list。
        state["items"].setdefault(i, {"source": "?", "script_status": "note",
                                      "raw_entry": "", "compiled": None, "category": None})
        state["items"][i]["needs_review"] = args.note or "待人工"
        save(state, args.file)
        print(f"OK {i} 已記待人工：{args.note}")
    elif args.action == "done":
        # 結案。缺這個動作時「待人工」只進不出，resume 每輪重印同一批已處理完的項目，
        # 久了整個清單失去警示作用（0803 立案時的另一半問題）。
        # 兩種項目結案方式不同，不能一律 del：
        #   純備註殼（status=note、無內文）→ 整筆刪掉，它本來就不是素材
        #   真素材（有 raw_entry）→ 只拿掉 needs_review 旗標，素材本身留著
        if not args.ids:
            print("ERROR: done 需要 --ids（逗號分隔）")
            sys.exit(2)
        ids = [norm_id(x) for x in args.ids.split(",") if x.strip()]
        missing = [i for i in ids if i not in state["items"]]
        if missing:
            print(f"ERROR: 不存在的 id：{','.join(missing)}（全部未處理，請修正後重跑）")
            sys.exit(2)
        idle = [i for i in ids if not state["items"][i].get("needs_review")]
        if idle:
            print(f"ERROR: 這些本來就沒有待人工標記：{','.join(idle)}（全部未處理）")
            sys.exit(2)
        dropped, cleared = [], []
        for i in ids:
            v = state["items"][i]
            if v.get("script_status") == "note" and not (v.get("raw_entry") or "").strip():
                del state["items"][i]
                dropped.append(i)
            else:
                v.pop("needs_review", None)
                cleared.append(i)
        save(state, args.file)
        msg = []
        if dropped:
            msg.append(f"刪除備註殼 {len(dropped)} 筆：{','.join(dropped)}")
        if cleared:
            msg.append(f"素材解除標記 {len(cleared)} 筆（素材保留）：{','.join(cleared)}")
        print("OK " + "；".join(msg))
    else:
        rows = [(i, v["needs_review"]) for i, v in sorted(state["items"].items()) if v.get("needs_review")]
        print("\n".join(f"{i}: {n}" for i, n in rows) if rows else "(無待人工項目)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", default=DEFAULT_FILE)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("resume")
    lt = sub.add_parser("list-topics", help="列出目前各大分類的中主題與則數（開新中主題前必跑）")
    lt.add_argument("--subs", action="store_true", help="連小分題一起列出")
    sc = sub.add_parser("scratch-dir", help="印出並建立今晚班次的暫存檔資料夾（{YYYYMMDD}/）")
    sc.add_argument("--mmdd", required=True, help="晚班起始日 MMDD（不是實際掃帶當下的日曆日）")
    d = sub.add_parser("diff")
    d.add_argument("--checkpoint", required=True)
    d.add_argument("--ids", required=True)
    a = sub.add_parser("add")
    a.add_argument("--id", required=True)
    a.add_argument("--source", required=True)
    a.add_argument("--checkpoint", required=True)
    a.add_argument("--status", required=True, choices=["has_script", "pending"])
    a.add_argument("--entry", help="行內短內容（與 --entry-file 擇一）")
    a.add_argument("--entry-file", help="長內容檔案路徑（與 --entry 擇一）")
    a.add_argument("--sb-count", type=int, help="SOUNDBITE 段數（BITE 疑慮判斷用，同 add-batch）")
    a.add_argument("--footage-type", help="NS footageType（BITE 疑慮判斷用，同 add-batch）")
    ab = sub.add_parser("add-batch")
    ab.add_argument("--entries", required=True,
                    help="JSON 陣列檔，每筆含 id/source/checkpoint/status/entry")
    u = sub.add_parser("update-entry")
    u.add_argument("--id", required=True)
    u.add_argument("--status", choices=["has_script", "pending"])
    u.add_argument("--checkpoint")
    u.add_argument("--entry", help="行內短內容（與 --entry-file 擇一）")
    u.add_argument("--entry-file", help="長內容檔案路徑（與 --entry 擇一）")
    # ⚠️ default 由 0 改為 None（2026-08-09）：0 是**有意義的值**（真的沒有 SOUNDBITE），
    # 拿它當「沒帶參數」的預設，會讓每一次沒帶 --sb-count 的 update-entry 都撞上
    # bite_doubt 的反向判準（`(BITE)` 且 sb_count==0 → 假 BITE），憑空生出 needs_review
    # 雜訊；改存進狀態檔之後更嚴重，會把好的舊值蓋成 0。**None ＝ 沒帶，不要動舊值。**
    u.add_argument("--sb-count", type=int, default=None,
                   help="抽取白名單數出的 SOUNDBITE 段數；>0 且 entry 寫「無BITE」會擋下。"
                        "站方補完整稿後回寫用（不帶＝不動舊值）")
    sub.add_parser("pending")
    # ⚠️ WP1（2026-08-03）廢除 to-compile／mark-compiled／compiled 欄位：
    # 它們存在的唯一理由是「讓 agent 不用每輪重寫整份 txt」，改用 s2_render.py
    # 全量渲染後重寫是免費的，增量機制反而多一次呼叫又會漏（0803 標籤比較實錯）。
    sd = sub.add_parser("add-side", help="側錄 TXT 入狀態檔（SIDE_CNN／SIDE_NHK）")
    sd.add_argument("--txt", required=True, help="側錄候選 TXT（或直接餵晚班交接 txt）")
    sd.add_argument("--checkpoint", required=True)
    sd.add_argument("--normalize", action="store_true",
                    help="先做機械正規化（範圍TC取起點去冒號成6碼、角色搬到TC行、拆黏行）；"
                         "上傳者不懂格式時用，純位置搬移不改字")
    sd.add_argument("--tc-date", help="TC 的日期 MM-DD（省略＝取 --checkpoint 的日期）。"
                                      "跨夜時用得到：凌晨的輪次收到晚上的 TC，那多半是前一天錄的")
    sd.add_argument("--source", choices=["CNN", "NHK"],
                    help="TC 行沒有來源前綴時自動補（歐印萬原始檔多半是裸 TC）")
    sd.add_argument("--homes", default="",
                    help='用 TC 指定歸位："大分類/中主題[/小分題]=TC,TC;…"（檔內沒寫擬歸位時用）')
    sd.add_argument("--overwrite", action="store_true", help="已在庫的段落也覆寫")
    sd.add_argument("--dry-run", action="store_true", help="只解析不寫檔")
    sm = sub.add_parser("set-mark", help="寫死時段標記（補掃輪等 checkpoint 判不準時）")
    sm.add_argument("--ids", required=True)
    # `●` 是舊符號（2026-08-04 起改用 `■`），仍收但不建議新用——舊資料不回頭改，
    # 萬一要對舊檔動 set-mark 時還得指定得出來。
    sm.add_argument("--mark", choices=["△", "▲", "■", "◆", "●"])
    sm.add_argument("--clear", action="store_true", help="清除寫死值，改回自動推算")
    sr = sub.add_parser("set-aired", help="🟤 本台已做過（仍留庫存、仍可做後續）；人工判斷，agent 不自行標")
    sr.add_argument("--ids", required=True)
    sr.add_argument("--clear", action="store_true", help="取消已播標記")
    sa = sub.add_parser("set-alert", help="檔頭 🔴 重大提醒行（存狀態檔，render 每輪取用）")
    sa.add_argument("--set", action="append", help="整組取代（可重複，最多3則）")
    sa.add_argument("--add", help="追加一則（超過3則丟最舊的）")
    sa.add_argument("--clear", action="store_true", help="全部撤掉")
    sto = sub.add_parser("set-topic-order",
                         help="釘住某大分類的中主題順序（render 每輪照用；沒釘的走自動排）")
    sto.add_argument("--cat", required=True, help="大分類，如 天氣")
    sto.add_argument("--order", help="中主題順序，分號分隔")
    sto.add_argument("--clear", action="store_true", help="撤掉人工順序，退回自動排")
    c = sub.add_parser("set-category")
    c.add_argument("--id")
    c.add_argument("--cat", help="大分類/中主題[/小分題]")
    c.add_argument("--pairs", help='批次："id=大分類/中主題[/小分題];id2=..."（分隔符優先認分號）')
    st = sub.add_parser("set-top")
    st.add_argument("field")
    st.add_argument("value")
    g = sub.add_parser("get")
    g.add_argument("--id", required=True)
    rm = sub.add_parser("remove", help="整則刪除（誤收、排除白名單命中等），不是留待人工")
    rm.add_argument("--ids", required=True)
    r = sub.add_parser("needs-review")
    r.add_argument("action", choices=["add", "list", "done"])
    r.add_argument("--id", help="add 用：要標記的素材代碼或備註代號")
    r.add_argument("--note", help="add 用：備註內容")
    r.add_argument("--ids", help="done 用：結案的 id，逗號分隔")

    args = p.parse_args()
    state = load(args.file)
    {
        "resume": cmd_resume, "diff": cmd_diff, "add": cmd_add,
        "add-batch": cmd_add_batch,
        "update-entry": cmd_update_entry, "pending": cmd_pending,
        "add-side": cmd_add_side, "set-alert": cmd_set_alert,
        "set-topic-order": cmd_set_topic_order,
        "set-mark": cmd_set_mark, "set-aired": cmd_set_aired,
        "set-category": cmd_set_category, "get": cmd_get, "remove": cmd_remove,
        "needs-review": cmd_needs_review, "set-top": cmd_set_top,
        "scratch-dir": cmd_scratch_dir, "list-topics": cmd_list_topics,
    }[args.cmd](state, args)


if __name__ == "__main__":
    main()
