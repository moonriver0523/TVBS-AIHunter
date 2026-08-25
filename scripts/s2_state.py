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
              "alerts", "special_category", "last_render_ts", "window_start",
              # resident_topics（2026-08-11）＝{大分類: [中主題,…]}，指定的中主題
              # 不論當天有沒有素材，render 都要印出空標題（跟 topic_order 不同——
              # topic_order 只管排序，沒素材的中主題照樣自動略過）。見 cmd_set_resident_topics。
              "resident_topics")


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
    # R2（2026-08-13）：這裡只吃 id，判不出「RT Edit No 跨日撞號」——RT 的號碼
    # 會跨日重複使用，同 id 不等於同一則素材，這條指令只看 id 有沒有出現過，
    # 撞號時「已在庫」會靜默蓋掉真正的新素材。真正查得出跨日撞號的是
    # `s2_audit.py --rt-list <帶日期時間戳的清單快照>`（reconcile 那條路，吃得到
    # `CODE|MM/DD/YYYY HH:MM` 格式），RT 收單那輪務必也跑一次那個。
    rt_seen = [i for i in seen if i.startswith("RT")]
    if rt_seen:
        print("⚠️ RT 的 Edit No 會跨日重複使用，上面「已在庫」不保證真的是同一則——"
              "跨日撞號要靠 s2_audit.py --rt-list（帶日期時間戳的清單）才驗得出來。")


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


def new_item(source, checkpoint, status, entry, sb_count=None, src_text=None, footage_type=None):
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
    # src_text／footage_type 也要進狀態檔（2026-08-12 修，實錯：兩者原本只活在
    # batch 中間檔裡，new_item() 沒有對應參數，add-batch／add 送進來的值全被丟棄——
    # §2「每筆必帶 src_text／footage_type」形同虛設，離線查證與稽核③失去依據）。
    if src_text:
        it["src_text"] = src_text
    if footage_type:
        it["footage_type"] = footage_type
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
    state["items"][i] = new_item(args.source, args.checkpoint, args.status, entry,
                                  args.sb_count, src_text=args.src_text,
                                  footage_type=args.footage_type)
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
    no_src = []   # R11 防呆（2026-08-13）：漏帶 src_text 要當場喊，不能等稽核翻舊帳
    for n, e in enumerate(data, 1):
        if not isinstance(e, dict):
            skipped.append(f"第{n}筆: 不是物件")
            continue
        missing = [k for k in ("id", "source", "checkpoint", "status", "entry") if not e.get(k)]
        if missing:
            skipped.append(f"第{n}筆({e.get('id','?')}): 缺 {','.join(missing)}")
            continue
        # 0818-2000 實錯：checkpoint 誤填成查詢視窗講法（如「18:00」）而非
        # `{MMDD}-{HHMM}`，first_seen_checkpoint 存進去的格式錯了，外層 s2_scan.ps1
        # 用精確比對算「本輪新增」時全部漏算，誤報成「本輪 0 則」。這裡當場擋下，
        # 不要等稽核事後才抓——照收會讓錯誤格式先入庫，之後還得靠 fix-first-seen 補救。
        if not CHECKPOINT_RE.match(str(e["checkpoint"])):
            skipped.append(f"{e.get('id','?')}: checkpoint 格式錯誤（需為 {{MMDD}}-{{HHMM}}，"
                           f"如 0818-2000，收到的是 {e['checkpoint']!r}）")
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
                                     e["entry"].strip(), sb,
                                     src_text=e.get("src_text"), footage_type=ft)
        if not e.get("src_text"):
            no_src.append(i)
        if doubt:
            state["items"][i]["needs_review"] = doubt
            flagged.append(f"{i}: {doubt}")
        for reason in fmt_issues(e["entry"]):
            fmt.append(f"{i}: {reason}")
        added.append(i)
    if added:
        save(state, args.file)
    print(f"OK 新增 {len(added)} 則" + (f"：{','.join(added)}" if added else ""))
    if no_src:
        print(f"⚠️ {len(no_src)} 則沒帶 src_text（站方原文＝事後離線查證的唯一依據，13b §543）："
              f"{','.join(no_src[:8])}{'…' if len(no_src) > 8 else ''}")
        print("   趁本輪瀏覽器還開著回補最便宜：`update-entry --batch <檔>`，每筆只要 "
              "{id, src_text}。整批都缺＝組 batch 時漏了欄位"
              "（0812-2200／0813-1200 實錯各 65／80 則）。")
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


def apply_update(state, i, entry, sb_count=None, status=None, checkpoint=None,
                 footage_type=None, src_text=None):
    """把一則的 raw_entry 覆寫掉。單筆與批次共用同一份邏輯，回傳 (doubt, fmt問題清單)。

    ⚠️ **不在這裡 save**：批次要的是「全部改完只寫一次檔」，寫檔次數等於
    Google Drive 同步次數，逐筆存在遠端資料夾上很慢（同 add-batch 的做法）。
    """
    it = state["items"][i]
    # 🎯 BITE 兜底（同 add-batch，2026-08-05 由「直接擋」改為「照收＋標記」）：
    # 覆寫時擋下更危險——舊內容已經在庫存裡，擋下只會讓它停在舊版本，
    # 而 agent 以為自己更新過了。
    doubt = bite_doubt(entry, sb_count, footage_type)
    it["raw_entry"] = entry
    # 站方補上完整稿後 sb_count 會變（0→5），**這條路就是唯一的回寫時機**——
    # 沒帶就別動舊值（`None` ＝ 沒帶，不是 0；見下方 argparse 的 default 說明）。
    if isinstance(sb_count, int):
        it["sb_count"] = sb_count
    if status:
        it["script_status"] = status
    if src_text:
        # R9（2026-08-13）：站方補完整稿／整批漏帶的回補時機。沒帶就不動舊值，
        # 跟 sb_count 同一套「None＝沒帶」約定。
        it["src_text"] = src_text
    it["entry_updated"] = checkpoint or it.get("last_checked_checkpoint", "")
    it["entry_updated_ts"] = now_ts()
    sp.derive(it)                        # 內容變了，結構化欄位跟著重推（見 s2_parse）
    if doubt:
        it["needs_review"] = doubt
    else:
        it.pop("needs_review", None)     # 改好了就自動結案，不用手動 done
    return doubt, [f"{i}: {r}" for r in fmt_issues(it.get("raw_entry") or "")]


def cmd_update_entry(state, args):
    """單筆覆寫；帶 `--batch` 就走批次（見 cmd_update_batch 的說明）。"""
    if getattr(args, "batch", None):
        return cmd_update_batch(state, args)
    # ⚠️ 順序不能顛倒：`norm_id(None)` 會炸。先確認有帶 id 再正規化。
    if not args.id:
        print("ERROR: 需要 --id（單筆）或 --batch（批次）")
        sys.exit(2)
    i = norm_id(args.id)
    if i not in state["items"]:
        print(f"ERROR: {i} 不存在，請先 add")
        sys.exit(2)
    src = getattr(args, "src_text", None)
    if getattr(args, "src_text_file", None):
        with open(args.src_text_file, encoding="utf-8-sig") as f:
            src = f.read().strip()
    doubt, fmt = apply_update(state, i, read_entry(args), args.sb_count,
                              args.status, args.checkpoint,
                              getattr(args, "footage_type", None), src_text=src)
    save(state, args.file)
    print(f"OK 已覆寫 {i}（{state['items'][i]['script_status']}）")
    report_fmt(fmt)


def cmd_update_batch(state, args):
    """整批覆寫既有素材的 raw_entry（2026-08-11 加）。

    🔴 **為什麼要有這支**：`add-batch` 有批次、`set-category --pairs` 有批次，
    **唯獨「修正既有稿子」只能一則一則來**。於是每次品質閘擋下 N 則要改，
    agent 就自己寫一支 python subprocess 迴圈去跑 N 次 update-entry——
    0811-2000 那輪 67 次 Bash 裡有 12 次是這種臨時腳本，而臨時腳本每輪重寫一次、
    每次都可能寫錯（0811 就修了兩次路徑）。缺工具就會長出即興腳本，
    這是工具箱的缺口，不是 agent 的紀律問題。

    檔案格式：JSON 陣列，每筆 `{"id", "entry"}`，可選 `sb_count`／`status`／
    `checkpoint`／`footage_type`。不存在的 id 跳過並回報（要新增請用 `add-batch`），
    其餘照樣改完——單筆失敗不中斷整批，同 `add-batch` 的一貫做法。
    """
    try:
        with open(args.batch, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: --batch 檔讀取失敗（{e}）")
        sys.exit(2)
    if isinstance(data, dict):
        data = data.get("entries")
    if not isinstance(data, list):
        print("ERROR: --batch 需為 JSON 陣列（或含 entries 陣列的物件）")
        sys.exit(2)
    done, skipped, flagged, fmt = [], [], [], []
    for n, e in enumerate(data, 1):
        if not isinstance(e, dict) or not e.get("id") or not (
                isinstance(e.get("entry"), str) or e.get("src_text")):
            skipped.append(f"第{n}筆({e.get('id','?') if isinstance(e, dict) else '?'}): "
                           f"需要 id 與字串 entry（或只帶 src_text 走回補）")
            continue
        i = norm_id(str(e["id"]))
        if i not in state["items"]:
            skipped.append(f"{i}: 不存在（要新增請用 add-batch）")
            continue
        if not isinstance(e.get("entry"), str):
            # 只回補 src_text、不動稿子本體——R11 整批漏帶的回補路徑（2026-08-13）。
            # 不走 apply_update：那條會覆寫 raw_entry＋重推結構化欄位，回補原文不該動這些。
            state["items"][i]["src_text"] = e["src_text"]
            done.append(i)
            continue
        doubt, issues = apply_update(
            state, i, e["entry"].strip(), e.get("sb_count"), e.get("status"),
            e.get("checkpoint") or getattr(args, "checkpoint", None),
            e.get("footage_type"), src_text=e.get("src_text"))
        if doubt:
            flagged.append(f"{i}: {doubt}")
        fmt += issues
        done.append(i)
    if done:
        save(state, args.file)           # 全部改完只寫一次檔
    print(f"OK 已覆寫 {len(done)} 則" + (f"：{','.join(done)}" if done else ""))
    report_fmt(fmt)
    if flagged:
        print(f"⚠️ BITE 待確認 {len(flagged)} 則（**已寫入**，已記進 needs-review）：")
        print("\n".join("  " + x for x in flagged))
    if skipped:
        print(f"跳過 {len(skipped)} 則：")
        print("\n".join("  " + s for s in skipped))


# ── patch-entry：機械標記修補（A12 桶①，2026-08-18）────────────────────
#
# 🔴 **為什麼要有這支**：`update-entry` 只有「全文替換」一條路。於是每輪為了在
# 已經寫好的素材行前面插一個 🔴／🟡、或補一個第二括號 `(BITE)`，agent 只能把
# **整條 entry 一字不差重打一遍**。0818-1600 那輪四支臨時腳本
# （`_fix_ns_bite` / `_fix_ap` / `_fix_markers` / `_fix_combined2`）的全部內容
# 就是這件事，約 12KB 中文重打；`WE-021MO` 同一條 entry 被輸出**三遍**。
# 而 🔴／🟡 是 `s2_scan_prompt.md:113–122` 的**每輪必做步驟**（「拿不準就標 🟡」），
# 所以這不是偶發，是每輪固定的損失。形狀同 `cmd_update_batch` 上方那段註解記的
# 「缺工具就會長出即興腳本」，只是這次缺的是**部分修補**而不是批次。
#
# ⛔ **不做第二套 parser**：標記位置、互斥關係、素材行判準全部走 `s2_validate`
# 既有的 `strip_mark()`／`RED_RE`／`SUBALERT_RE`／`AIRED_RE`／`HILITE_RE`／
# `LINE_RE`／`SIDE_RE`（不變式清單第 2 條的同一個原則）。本函式只負責「拆開→
# 換標記→照原順序組回去」，一個判準都不自己重寫。
#
# ⚠️ **只做機械可導的，不替 agent 做判斷**：
#   - `--alert red|yellow|none` 是**明令**才動（重大與否是編輯判斷，機械推不出來）。
#   - `--bite` 只補 `s2_validate` 已經在報的那一種（有 `▎BITE：` 段但缺 `(BITE)`
#     第二括號）。缺 BITE 段、已寫「無BITE」、或本來就有 `(BITE)` 一律拒絕不動，
#     免得把「有 (BITE) 但缺 ▎BITE： 段」這種相反的錯誤製造出來。
#   - ⛔ 刻意**不**做成寫入時自動補：13c §497 訂的是品質掃「只警告不修」，
#     靜默改稿會牴觸那條原則。要不要改成自動導出屬裁決題（MASTER A12）。

ALERT_MARKS = {"red": "🔴", "yellow": "🟡", "star": "⭐", "none": ""}
# ⭐ 推薦（2026-08-19）：跟 🔴／🟡 走同一個 `--alert` 欄位、同一條「明令才動」路徑，
# 但語意更嚴格——🔴／🟡 是「重大與否，agent 可自行判斷」，⭐ 是「編輯覺得適合做成
# 新聞才標，agent 不可自行判斷、只能在使用者明確指示時才下這個值」。程式碼層面
# 兩者呼叫方式相同（都是 `--alert star`），這條限制是給下指令的 agent／使用者看的
# 政策，機械本身不擋（沒有「誰下的令」這種資訊可查）。


def patch_marks(sv, entry, alert=None, add_bite=False):
    """回傳 (新 entry, 說明)。不需要改動時 `新 entry` 為 None（呼叫端據此跳過）。

    `alert`：`'red'`／`'yellow'`／`'star'`／`'none'`／`None`（不動）。🔴／🟡／⭐ 三者
    互斥，換標記＝先剝掉舊的再插新的，不會同時並存（同 `s2_render.strip_marks` 的約定）。
    """
    first = (entry or "").strip().split("\n")[0]
    rest_lines = (entry or "").strip().split("\n")[1:]
    if not first:
        return None, "空內容"
    # 側錄（多行 TC 兩行式）與非素材行不套這套格式，同 `check_entry()` 的守門。
    _, bare = sv.strip_mark(first)
    if sv.SIDE_RE.match(bare) or not sv.LINE_RE.match(bare):
        return None, "非素材行（側錄／兩行式），不套標記格式"

    # 拆：時段標記 → 🔴/🟡 → 🟤 → 🔖 → 本體。順序是 s2_validate 訂的，照它拆照它組。
    m = sv.MARK_RE.match(first)
    period, tail = (m.group(1), first[m.end():]) if m else ("", first)
    had_red = bool(sv.RED_RE.match(tail))
    if had_red:
        tail = sv.RED_RE.sub("", tail, count=1)
    had_yellow = bool(sv.SUBALERT_RE.match(tail))
    if had_yellow:
        tail = sv.SUBALERT_RE.sub("", tail, count=1)
    had_star = bool(sv.STAR_RE.match(tail))
    if had_star:
        tail = sv.STAR_RE.sub("", tail, count=1)
    had_aired = bool(sv.AIRED_RE.match(tail))
    if had_aired:
        tail = sv.AIRED_RE.sub("", tail, count=1)
    had_hilite = bool(sv.HILITE_RE.match(tail))
    if had_hilite:
        tail = sv.HILITE_RE.sub("", tail, count=1)

    notes = []
    new_alert = "🔴" if had_red else ("🟡" if had_yellow else ("⭐" if had_star else ""))
    if alert is not None:
        want = ALERT_MARKS[alert]
        if want == new_alert:
            notes.append("標記已是" + (want or "無"))
        else:
            notes.append(f"{new_alert or '無'} → {want or '無'}")
            new_alert = want

    if add_bite:
        ok, why = bite_tag_patchable(tail)
        if not ok:
            return None, why
        tail = insert_bite_tag(tail)
        notes.append("補上 (BITE)")

    prefix = "".join(x + " " for x in (period, new_alert,
                                       "🟤" if had_aired else "",
                                       "🔖" if had_hilite else "") if x)
    new_first = prefix + tail
    if new_first == first:
        return None, "；".join(notes) or "無變更"
    return "\n".join([new_first] + rest_lines), "；".join(notes)


def bite_tag_patchable(line):
    """`(BITE)` 第二括號能不能機械補上？回傳 (可以嗎, 原因)。

    判準對齊 `s2_validate._run_line_checks()` 報的那三條，**只補其中一種**：
    有 `▎BITE：` 段、沒有 `(BITE)`、沒寫「無BITE」——其餘一律拒絕，
    因為那些要嘛是編輯判斷（該不該有 BITE），要嘛補了反而製造相反的錯誤。
    """
    if "(BITE)" in line:
        return False, "已有 (BITE)，不需補"
    if "無BITE" in line:
        return False, "寫著「無BITE」，補 (BITE) 會自相矛盾（要改請用 update-entry）"
    if "▎BITE：" not in line and "▎BITE:" not in line:
        return False, "沒有 ▎BITE： 段，補了會變成「有 (BITE) 但缺 ▎BITE： 段」"
    # `CODE (備註) (BITE) ▎…`：第一個備註括號是 (BITE) 的錨點。沒有它就不猜，
    # 硬塞會變成第一括號＝BITE，撞上 s2_validate 的「第一備註寫了 BITE」。
    # ⚠️ 判準必須跟 `insert_bite_tag()` **看同一段字**（第一個 `▎` 之前的 head）：
    # 只要條件掃整行、插入卻只切 head，遇到括號裡夾了 `▎` 的畸形行就會
    # 放行卻找不到 `)`，`rfind` 回 -1 → 產出開頭多一個空格的壞行，而
    # `check_entry()` 對 LINE_RE 不 match 的行回空清單＝**壞掉還不報**，
    # 整行接著從品質掃與檔頭統計裡靜默消失（本 repo 記過三次的同一種坑）。
    if ")" not in line.split("▎", 1)[0]:
        return False, "摘要前沒有備註括號可接，不猜插入位置（請用 update-entry）"
    return True, ""


def insert_bite_tag(line):
    """在摘要（第一個 `▎`）之前的**最後一個**括號後面插 `(BITE)`。"""
    head = line.split("▎", 1)[0]
    tail = line[len(head):]
    idx = head.rfind(")")
    return head[:idx + 1] + " (BITE)" + head[idx + 1:].rstrip() + " " + tail.lstrip()


def cmd_patch_entry(state, args):
    """機械修補既有素材行的標記，不必重打整條 entry（見上方大段說明）。"""
    if args.alert is None and not args.bite:
        print("ERROR: 至少要帶 --alert 或 --bite（兩者可同時）")
        sys.exit(2)
    sv = load_validate()
    ids = [norm_id(x) for x in args.ids.split(",") if x.strip()]
    if not ids:
        print("ERROR: --ids 是空的")
        sys.exit(2)
    missing = [i for i in ids if i not in state["items"]]
    if missing:
        # 同 set-aired：先全部驗完才動手，不做「改一半再報錯」。
        print(f"ERROR: 不存在的 id：{','.join(missing)}（其餘未變更，請修正後重跑）")
        sys.exit(2)

    done, unchanged, fmt = [], [], []
    for i in ids:
        old = state["items"][i].get("raw_entry", "") or ""
        new, why = patch_marks(sv, old, args.alert, args.bite)
        if new is None:
            unchanged.append(f"{i}: {why}")
            continue
        # 走 apply_update 而不是直接寫 raw_entry：entry_updated／sp.derive／
        # bite_doubt 這一整串記帳邏輯只該有一份。
        #
        # 🔴 **但 needs_review 要原樣保住**（2026-08-18 上線當天實測抓到）：
        # `apply_update` 的收尾是「重算 doubt，算不出來就 `pop("needs_review")`」，
        # 那條的前提是呼叫端**帶著新的 sb_count 進來**（`update-entry` 補完整稿的
        # 情境＝真的有新資訊，才有資格宣告結案）。`patch-entry` 只動標記，
        # 手上沒有 sb_count 也沒有 footage_type，重算出來的 doubt 幾乎必為 None，
        # 於是**光是標一個 🟡 就會把留痕清掉**。實測：RT6164（稿未到、needs-review
        # 記著跨輪交辦）跑一次 `--alert yellow`，留痕就沒了。
        # ⛔ 這是靜默資料遺失，而且踩的正好是 R6 的教訓——**跨輪交辦要走狀態檔的
        # needs-review，不是帳本**——留痕被無聲吃掉等於那條路也斷了。
        # 所以本指令對 needs_review **一律中性**：改完原樣放回（本來沒有就維持沒有）。
        had_review = state["items"][i].get("needs_review")
        _, issues = apply_update(state, i, new, checkpoint=args.checkpoint)
        if had_review is not None:
            state["items"][i]["needs_review"] = had_review
        else:
            state["items"][i].pop("needs_review", None)
        fmt += issues
        done.append(f"{i}: {why}")
    if done:
        save(state, args.file)           # 全部改完只寫一次檔（同 update-batch）
    print(f"OK 已修補 {len(done)} 則")
    if done:
        print("\n".join("  " + x for x in done))
    report_fmt(fmt)
    if unchanged:
        print(f"未變更 {len(unchanged)} 則：")
        print("\n".join("  " + x for x in unchanged))


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
        if args.compact:
            # 0812 T6：每主題一行、不列小分題明細——agent 一輪只需要「有哪些中主題」
            # 這個事實，小分題細節等真的要合併時再用 topic_review 看。
            for m in order_topics(list(mids)):
                print(f"{big}｜{m}｜{len(mids[m])}")
            continue
        print(f"■ {big}（{n} 則 / {len(mids)} 個中主題）")
        for m in order_topics(list(mids)):
            subs = [x for x in mids[m] if x]
            tail = f"　└ {'／'.join(sorted(set(subs)))}" if args.subs and subs else ""
            print(f"    【{m}】×{len(mids[m])}{tail}")
    print(f"\n合計 {total} 則 / {sum(len(v) for v in rows.values())} 個中主題")
    if not args.compact:
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


# ── T/C 議題／地緣標籤（A10 v2，2026-08-24 上線） ─────────────────────────────
# 🔴 T/C 一律存 item 的**頂層 `tc` 鍵**，⛔ 絕對不放進 `category`。
#    `_set_one_category()` 是 `items[i]["category"] = c` **整包覆寫**、只重建三鍵；
#    T/C 若寄生在 category 裡，之後任何一次 set-category／s2_apply_reclass MOVE
#    都會無聲抹掉它，而 render 的兜底（沒有就跑 tag_tc()）會把損失蓋住——
#    畫面完全正常，永遠發現不了。頂層鍵安全：apply_update 原地改鍵、
#    add-batch 撞 id 跳過，補稿與批次路徑都不波及。
#
# 名單**只認 `common/plans/a10-p0-data/TC-字典.md`**，不在這裡寫死第三份拷貝
# （`build_tc_matrix_0821.py` 已經是第二份；17 檔把「雙真相源」列為具名失效模式）。
TC_DICT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "common", "plans", "a10-p0-data", "TC-字典.md")
# 每個 checkpoint 的 set-tc 呼叫上限（A23 式硬上限）。
# 訂 6 而不是 4：checkpoint 就是輪次，set-category 實測已穩定 4 次／輪，
# T/C 綁同批再加上各產線整併端補標，4 會讓**合法呼叫**撞牆。
# 🔴 2026-08-25 上調 6 → 8：0825-0100 輪（79 則）實際用滿 6 次、**正好頂到上限**，
#    再多一點素材就會拒絕到合法呼叫——那會變成成本乘數（每次拒絕＝一次重試呼叫
#    ≈$0.07），正是這個上限想避免的東西。上限的用意是擋「逐則呼叫」的失控形狀，
#    不是擋正常批次；8 仍遠低於逐則呼叫的量級（79 則逐則＝79 次）。
TC_CALLS_PER_CHECKPOINT = 8


# ── C 正規化：併入表與「專項帶區域」表（2026-08-25 使用者裁示） ──────────────
# 🔴 **只在這裡定義一次。** render 端的 `stored_tc()` 直接 import 這兩張表——
#    複製一份到 renderer 會漂，而漂掉的那天畫面與狀態檔會各說各話。
# ⚠️ 放在**寫入端**而不是只做驗證：13f／17 的來源預設寫的是「CNA→新加坡」，
#    若只驗不改寫，每一處預設都得改成「新加坡,東南亞」，漏一處就退回舊行為。
C_MERGED = {"墨西哥": "中南美", "其他地區": "國際"}   # 舊桶已刪，改寫不退件
# T 軸同理：醫藥健康併入科技，合併後更名「科技醫藥」（2026-08-25 使用者裁示）。
# ⚠️ **改名的那一側也要列**（科技→科技醫藥），否則舊名會被當成打錯字退件。
T_MERGED = {"醫藥健康": "科技醫藥", "科技": "科技醫藥"}
C_IMPLIES = {"新加坡": "東南亞", "泰國": "東南亞"}    # 專項與區域並存


def normalize_t(names):
    """T 的併入／改名正規化。回傳 (名單, 改寫說明)。"""
    out, notes = [], []
    for x in names:
        y = T_MERGED.get(x)
        if y:
            notes.append(f"{x}→{y}")
            x = y
        if x not in out:
            out.append(x)
    return out, notes


def normalize_c(names):
    """回傳 (正規化後的 C 名單, 改寫說明)。順序穩定、不重複。

    ⛔ 以色列／伊朗**不在** `C_IMPLIES` 裡——那組的規則相反（掛專項就不掛中東）。
       三種形狀寫在 TC-字典.md 的表下方，不要互相類推。
    """
    out, notes = [], []
    for x in names:
        y = C_MERGED.get(x)
        if y:
            notes.append(f"{x}→{y}")
            x = y
        if x not in out:
            out.append(x)
        imp = C_IMPLIES.get(x)
        if imp and imp not in out:
            out.append(imp)
            notes.append(f"{x}＋{imp}")
    return out, notes


# ── 機動 T：議題軸的臨時 TAG（2026-08-25 上線，規劃書 §6b-2） ────────────────
# ⛔ **只有使用者下令才開**，agent 不自行新增、不自行命名——跟大分類機動格
#    （`special_category`）同一條鐵律。
# 🔴 為什麼放在**設定檔**而不是狀態檔頂層：狀態檔每天重建，颱風不會只活一天。
#    比照 `s2_resident_topics.json` 的既有模式，單一真相源、跨天生效。
#    ⛔ 不要另外在狀態檔存一份鏡像——兩份會漂。
SPECIAL_T_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "s2_special_t.json")


def load_special_t():
    """回傳 (active 名單, 全部條目)。檔案不存在或壞掉都當「沒開機動 T」。

    ⚠️ 壞檔不硬失敗：機動 T 是加分項，讓它擋掉整輪掃帶不划算。
    """
    try:
        with open(SPECIAL_T_PATH, encoding="utf-8-sig") as f:
            tags = (json.load(f) or {}).get("tags") or []
    except (OSError, json.JSONDecodeError):
        return [], []
    if not isinstance(tags, list):
        return [], []
    active = [x.get("name") for x in tags
              if isinstance(x, dict) and x.get("name")
              and (x.get("status") or "active") == "active"]
    return active, tags


def _save_special_t(tags):
    with open(SPECIAL_T_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"_說明": _SPECIAL_T_NOTE, "tags": tags}, f,
                  ensure_ascii=False, indent=2)
        f.write("\n")


_SPECIAL_T_NOTE = (
    "機動 T（議題軸的臨時 TAG）。⛔ 只有使用者下令才開，agent 不自行新增、"
    "不自行命名。開了就是全域生效（跨天），與 TC-字典.md 的固定 12 類並存"
    "複選——颱風素材同時掛「颱風」＋「天災天氣」。事件冷卻後 "
    "set-special-t --retire，⛔ 不要刪除條目：歷史狀態檔還掛著它，"
    "刪掉那些素材在矩陣上會無格可放。")


def cmd_special_t(state, args):
    """開／收／看機動 T。⛔ 使用者下令才動。

    例：`set-special-t --open 颱風 --charter "納里颱風相關：路徑、災情、撤離、復原"`
        `set-special-t --retire 颱風`
        `set-special-t`（不帶參數＝看目前有哪些）

    「只併不改名」比照中主題鐵律：同名重開只更新 charter，不會產生第二筆。
    """
    active, tags = load_special_t()
    if not args.open and not args.retire:
        if not tags:
            print("目前沒有機動 T。開一個："
                  'set-special-t --open 颱風 --charter "收什麼"')
            return
        for x in tags:
            mark = "●" if (x.get("status") or "active") == "active" else "○退場"
            print(f"{mark} {x.get('name')}｜{x.get('charter') or '（沒寫 charter）'}"
                  f"｜開於 {x.get('opened') or '?'}")
        return
    if args.open and args.retire:
        print("ERROR --open 與 --retire 擇一", file=sys.stderr)
        raise SystemExit(2)

    if args.retire:
        hit = [x for x in tags if x.get("name") == args.retire]
        if not hit:
            print(f"ERROR 沒有叫「{args.retire}」的機動 T", file=sys.stderr)
            raise SystemExit(2)
        # ⛔ 不刪除條目：歷史狀態檔還掛著它，刪掉那些素材在矩陣上無格可放。
        hit[0]["status"] = "retired"
        _save_special_t(tags)
        print(f"OK 機動 T「{args.retire}」已退場，不再收新素材；"
              f"已標的歷史資料不動、矩陣照樣顯示。")
        return

    ok_t, _ = _load_tc_dict()
    if args.open in ok_t:
        print(f"ERROR「{args.open}」是 TC-字典 的固定 T，本來就能用，"
              f"不需要開機動 T", file=sys.stderr)
        raise SystemExit(2)
    if not args.charter:
        # charter 是規劃書 §6b-2 的要求：開 TAG 當下寫一句「收什麼」，
        # 否則下一輪的 agent 只能望文生義，機動 T 收什麼會每輪漂一次。
        print("ERROR 需要 --charter「收什麼」，一句話即可", file=sys.stderr)
        raise SystemExit(2)
    hit = [x for x in tags if x.get("name") == args.open]
    if hit:
        hit[0]["charter"] = args.charter
        hit[0]["status"] = "active"
        _save_special_t(tags)
        print(f"OK 機動 T「{args.open}」已更新 charter（同名只併不改名）")
        return
    tags.append({"name": args.open, "charter": args.charter,
                 "opened": datetime.now().strftime("%Y-%m-%d"),
                 "status": "active"})
    _save_special_t(tags)
    print(f"OK 已開機動 T「{args.open}」：{args.charter}")
    print(f"⚠️ 這是**加掛**，不是取代——符合的素材要同時掛既有固定 T"
          f"（例：颱風素材掛「{args.open}」＋「天災天氣」）。")


def _load_tc_dict():
    """從 TC-字典.md 解析出 (T 名單, C 名單)。單一真相源，解析不到就硬失敗。"""
    try:
        txt = open(TC_DICT_PATH, encoding="utf-8-sig").read()
    except OSError as e:
        sys.exit(f"⛔ 讀不到 TC 字典 {TC_DICT_PATH}：{e}")
    T, C, cur = [], [], None
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("## 議題 T"):
            cur = T
            continue
        if s.startswith("## 地緣 C"):
            cur = C
            continue
        if cur is None or not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        name = cells[0] if cells else ""
        if not name or name.startswith("-") or name in ("名稱",):
            continue
        cur.append(name)
    if not T or not C:
        sys.exit(f"⛔ TC 字典解析失敗（T {len(T)} 個／C {len(C)} 個），"
                 f"格式可能已變動：{TC_DICT_PATH}")
    return T, C


def _special_t_sweep(state):
    """回傳 (機動 T 名稱 → 疑似漏標的 id 清單)。

    🔴 2026-08-25 實測：`13f` 的機動 T 規則**完整進了 context**（0825-1800
       transcript 第 29 行讀得到），render 也印了 📌 觸發點——但那行印在
       **第 682 行**，而三次 `set-tc` 在 **620／626／629**。觸發點在決策之後
       等於沒有，跟 T10 是同一個形狀。所以改成在**寫入端**掃：素材文字出現
       機動 T 的名字、T 卻沒掛它，就當場點名。
    ⚠️ 只比對**名稱**、不猜語意——「風災」不是颱風，寧可漏報也不要亂報。
    """
    active, _ = load_special_t()
    if not active:
        return {}
    out = {}
    for i, it in (state.get("items") or {}).items():
        if (it or {}).get("script_status") == "note":
            continue
        raw = (it or {}).get("raw_entry") or ""
        have = ((it or {}).get("tc") or {}).get("T") or []
        for name in active:
            if name in raw and name not in have:
                out.setdefault(name, []).append(i)
    return out


# ── T 的數量上限（2026-08-25 使用者定：上限 3，預設 1，有需要才多掛）──────
# 🔴 **機動 T 不佔這 3 格。** 颱風素材是「颱風＋天災天氣」兩個；機動 T 若也計數，
#    `_special_t_sweep` 點名「加掛颱風、原本的 T 要留著」時，就會把已滿格的素材
#    逼去違規——自己的機制打自己。
# ⛔ 超過上限**退該則**，不截斷取前 N：哪幾個是主軸是判斷題，機器替 agent 挑
#    等於把判斷藏進 stdout。退件走既有 skipped 路徑，會落進 `tc_rejected`。
T_MAX = 3


def _set_one_tc(state, raw_id, spec, ok_t, ok_c, notes=None, special=()):
    """設定單筆 T/C。回傳錯誤訊息字串，成功回 None。

    spec 格式：`T1,T2/C1,C2`（T 與 C 以 `/` 分隔，各自以 `,` 分隔多個）。
    T 或 C 任一側可留空（例：`/臺灣` 只設 C），但不能兩側都空。
    """
    i = norm_id(raw_id)
    if i not in state["items"]:
        return f"{i}: 不存在"
    if "/" not in spec:
        return f"{i}: tc 需為「T1,T2/C1,C2」（例：政治,社會/臺灣）"
    tside, cside = spec.split("/", 1)
    T = [x.strip() for x in tside.split(",") if x.strip()]
    C = [x.strip() for x in cside.split(",") if x.strip()]
    if not T and not C:
        return f"{i}: T 與 C 不能都是空的"
    # 先正規化再驗字典：墨西哥／其他地區是**已刪的舊桶**，改寫比退件好——
    # 退件會逼 agent 多一次呼叫（≈$0.07），而正確答案是唯一的、沒有歧義。
    T, _tnotes = normalize_t(T)
    C, _notes = normalize_c(C)
    _notes = _tnotes + _notes
    if _notes and notes is not None:
        notes.append(f"{i}: " + "、".join(_notes))
    bad = [x for x in T if x not in ok_t] + [x for x in C if x not in ok_c]
    if bad:
        return f"{i}: 不在 TC-字典 裡的名稱 {'／'.join(bad)}"
    fixed = [x for x in T if x not in set(special)]
    if len(fixed) > T_MAX:
        return (f"{i}: T 掛了 {len(fixed)} 個（{'、'.join(fixed)}），上限 {T_MAX} 個"
                f"（機動 T 不計）。挑掉次要的重下這一則——判準是"
                f"**拿掉它這則就分類錯了**，答不出來就不該掛。")
    tc = dict(state["items"][i].get("tc") or {})
    if T:
        tc["T"] = T
    if C:
        tc["C"] = C
    state["items"][i]["tc"] = tc
    return None


def cmd_set_tc(state, args):
    """寫 T/C 標籤。牙齒放寫入端，但**整批回報一次、不逐則退回**——
    每次拒絕都是一次重試呼叫（≈$0.07），逐則退回會把品質訊號變成成本乘數。
    """
    ok_t, ok_c = _load_tc_dict()
    # 機動 T 只認 active 的：retired 的歷史資料照樣留著，但不再收新素材。
    _sp_active, _sp_all = load_special_t()
    ok_t = list(ok_t) + _sp_active
    # 上限只數固定 T：機動 T（含已退場的，歷史資料還掛著）一律不佔格。
    _sp_names = {x.get("name") for x in _sp_all if x.get("name")}
    if args.pairs and (args.id or args.tc):
        print("ERROR: --pairs 與 --id/--tc 擇一，不可混用")
        sys.exit(2)

    # A23 式硬上限：同一個 checkpoint 的呼叫次數。
    # 🔴 頂層鍵一律走 `state["_top"]`——`save()` 寫的是 `dict(state["_top"])`，
    #    直接掛在 `state` 上的鍵**會被靜默丟棄**（2026-08-24 離線試跑實測到）。
    top = state.setdefault("_top", {})
    cp = top.get("checkpoint") or ""
    calls = dict(top.get("tc_calls") or {})
    used = int(calls.get(cp) or 0)
    if used >= TC_CALLS_PER_CHECKPOINT:
        print(f"⛔ set-tc 在 checkpoint {cp} 已呼叫 {used} 次，達上限 "
              f"{TC_CALLS_PER_CHECKPOINT}。請整批一次下，不要逐則呼叫。")
        # 🔴 2026-08-25：實測 0825-0430 那輪的 set-tc 全部被記到 **前一輪**
        #    （`0825-0100`）的桶裡，用掉它的第 7、8 格——因為 `set-top checkpoint`
        #    是收工才下的，寫 T/C 的當下頂層 checkpoint 還停在上一輪。
        #    後果：本輪的額度沒用到，卻先撞上一輪的牆，131 則裡只標到 29 則，
        #    其餘留到下一輪才補——正是「大量未分類」的來源之一。
        #    上限的用意是擋逐則呼叫，不是擋跨輪誤記，所以這裡要把自救路徑講出來。
        print(f"⚠️ 若 checkpoint 還停在上一輪（目前狀態檔寫的是 {cp!r}），"
              f"**本輪的額度其實還沒用**。先下 "
              f"`set-top checkpoint {{MMDD}}-{{HHMM}}` 更新成本輪，再重下這批。")
        sys.exit(3)

    if not args.pairs:
        if not (args.id and args.tc):
            print('ERROR: 單筆需 --id 與 --tc；批次用 --pairs "id=T/C;..."')
            sys.exit(2)
        pairs = f"{args.id}={args.tc}"
    else:
        pairs = args.pairs

    sep = ";" if ";" in pairs else "\n"
    done, skipped, rewrites = [], [], []
    for tok in (t.strip() for t in pairs.split(sep)):
        if not tok:
            continue
        if "=" not in tok:
            skipped.append(f"「{tok}」: 缺 =（格式 id=T1,T2/C1,C2）")
            continue
        i, spec = tok.split("=", 1)
        err = _set_one_tc(state, i, spec, ok_t, ok_c, rewrites, _sp_names)
        (skipped if err else done).append(err or norm_id(i))

    # 拒絕要留得下痕跡：遙測只記呼叫次數、不記離開碼，整份 jsonl 沒有欄位
    # 承載「這次失敗了」。落在狀態檔 needs_review（既有人工複核通道）。
    if skipped:
        rej = dict(top.get("tc_rejected") or {})
        rej[cp] = (rej.get(cp) or []) + skipped
        top["tc_rejected"] = rej

    calls[cp] = used + 1
    top["tc_calls"] = calls
    save(state, args.file)
    print(f"OK 設定 {len(done)} 則 T/C"
          f"（checkpoint {cp} 第 {used + 1}/{TC_CALLS_PER_CHECKPOINT} 次呼叫）")
    if done:
        _dist = {}
        for _i in done:
            _n = len(((state["items"].get(_i) or {}).get("tc") or {}).get("T") or [])
            _dist[_n] = _dist.get(_n, 0) + 1
        print("ℹ️ 本批 T 數分布："
              + "／".join(f"{k} 個×{v}" for k, v in sorted(_dist.items()))
              + f"（**含機動 T**，機動 T 不佔上限；固定 T 預設 1 個、上限 {T_MAX}。"
              + "多掛一個要能說出「拿掉它這則就分類錯了」）")
    if rewrites:
        # 改寫要看得見，否則使用者會以為 C 是 agent 自己判的。
        print(f"ℹ️ T／C 依字典改寫 {len(rewrites)} 則（併入桶／改名／專項帶區域）：")
        for _x in rewrites:
            print("  " + _x)
    # 機動 T 漏標掃描：擺在**寫入端**，因為 render 的 📌 提示印在 set-tc 之後。
    _miss = _special_t_sweep(state)
    for _name, _ids in _miss.items():
        _show = "、".join(_ids[:10]) + ("…" if len(_ids) > 10 else "")
        print(f"🔴 機動 T「{_name}」疑似漏標 {len(_ids)} 則（文字裡有「{_name}」"
              f"但 T 沒掛）：{_show}")
        print(f"   確認是同一事件就補：set-tc --pairs "
              f'"{_ids[0]}={_name},{{原本的T}}/{{原本的C}}"'
              f"（**加掛**，原本的 T 要留著）")

    # 🔴 補標在 render 之後 → 頁面還是舊的（2026-08-25 實測到的「大量未分類」主因）。
    #    現行流程是 render → 覆蓋率閘門報「N 則還沒標」→ agent 補標 → **收工**，
    #    沒有人再 render 一次。0825-1200 實例：頁面上 618 列有 53 列是 heur
    #    （22 列 C＝未分類、7 列 T＝未分類），而狀態檔其實 100% 標好了。
    #    使用者看到的頁面因此每一輪都缺當輪那一批。
    #    比照 `list-topics` 的成功模式：**在用到的當下給觸發點**，不是寫進規則等它遵守。
    if done and (top.get("last_render_ts") or ""):
        # ⚠️ 一定要把 `--out` 也印出來：`s2_render.py` 少了它只會把 txt 印到
        #    stdout、**什麼都不寫**（`s2_render.py:591` 的 `if not args.out: return`），
        #    照著跑會以為更新了、其實頁面沒動——那比不提示更糟。
        _m = re.search(r"(\d{4})-s2-state", os.path.basename(args.file))
        _out = (os.path.join(os.path.dirname(args.file), f"{_m.group(1)}晚班交接.txt")
                if _m else "…/{MMDD}晚班交接.txt")
        print(f"🔴 這批是在 render（{top['last_render_ts'][:19]}）之後才標的，"
              f"**網頁與 txt 還是舊的**。收工前請再跑一次：")
        print(f'   python scripts/s2_render.py --file "{args.file}" --out "{_out}"')
    if skipped:
        # 退場的機動 T 被退件時，訊息會長得像「打錯字」——講清楚是退場不是筆誤，
        # 否則 agent 會反覆改字重試。
        _retired = [x.get("name") for x in load_special_t()[1]
                    if (x.get("status") or "active") != "active"]
        for _r in _retired:
            if any(_r and _r in s for s in skipped):
                print(f"ℹ️「{_r}」是**已退場**的機動 T，不是打錯字：歷史資料照樣"
                      f"顯示，但不再收新素材。要重開請使用者下 set-special-t --open。")
        print(f"⚠️ 退回 {len(skipped)} 則（已記進 tc_rejected，不必逐則重試，"
              f"整批改好再下一次）：")
        print("\n".join("  " + s for s in skipped))


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
    # 機動 T 的觸發點之一：set-category 跑在 set-tc **之前**，這裡講才來得及。
    _sp = load_special_t()[0]
    if _sp:
        print(f"📌 今天有機動 T：{'、'.join(_sp)}——待會下 set-tc 時，符合的素材"
              f"要**加掛**（連同既有固定 T 一起下，不是取代）。")
    # 🔴 T/C 的觸發點要落在 render **之前**（T10）。set-category 是最後一個
    #    「還在分類脈絡裡」的位置，這裡提醒最便宜；等 render 的覆蓋率閘門才講，
    #    補標就會發生在 render 之後、頁面停在舊的。
    _no_tc = [i for i, it in (state.get("items") or {}).items()
              if (it or {}).get("script_status") != "note"
              and not (((it or {}).get("tc") or {}).get("T")
                       or ((it or {}).get("tc") or {}).get("C"))]
    if _no_tc:
        print(f"🔴 本檔還有 {len(_no_tc)} 則沒有 T／C，**趁現在跟這批一起下**："
              f"{'、'.join(_no_tc[:8])}{'…' if len(_no_tc) > 8 else ''}")
        print('   set-tc --pairs "id=T1,T2/C1,C2;…"（名單見 13f「議題 T」／「地緣 C」）')
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


# 側錄「擬歸位」行的 T／C 後綴標籤（2026-08-25，A10 v2 收尾）。
# 認 `T:`／`C:`（全形冒號也吃），值以 `,`／`，`／`、` 分隔多個。
SIDE_TC_RE = re.compile(r"^([TC])\s*[：:]\s*(.*)$")


class SideHomeError(Exception):
    """側錄「擬歸位」行的形狀不對。帶原始值往上拋，由 cmd_add_side 明確失敗。"""


def _split_home_line(body):
    """把「擬歸位：」後面那串切成 (位置段, T 名單, C 名單)。

    格式（2026-08-25 起）：

        擬歸位：======大分類====== → 【中主題】 → 小分題 → T:政治,社會 → C:日本
        擬歸位：======大分類====== → 【中主題】 → T:天災天氣 → C:日本   ← 省略小分題

    ⛔ **T／C 用標籤不用位置。** 小分題是可省略的（`14:36`、本檔 `sub = segs[2]
       if len(segs) > 2 else ""`），若 T/C 靠 `segs[3]`／`segs[4]` 定位，
       省略小分題的那些則會把 `T:…` 讀成小分題——**靜默錯位，而且錯得很像對的**。
       改成認前綴之後，舊格式（沒有 T:／C: 段）自然落在「沒有 T/C」的分支，
       **不需要版本旗標，舊格式永久合法**。

    🔴 **arity 明確失敗（本函式存在的第一個理由，2026-08-25 前是靜默丟棄）**：
       原本 `segs[3]` 以後直接被丟掉、沒有任何檢查，於是「多一段沒人看得懂的東西」
       跟「格式正確」在回傳碼上完全一樣（都是 0）。比照
       `s2_platform_merge.py:110-115` 的「帶原始值明確失敗」精神改成拋例外——
       ⚠️ 這是**既有缺陷**，跟 T/C 無關，所以先單獨修、單獨 commit，才能獨立回退。
    """
    segs = [x.strip() for x in re.split(r"→|->", body)]
    pos, T, C = [], [], []
    for s in segs:
        m = SIDE_TC_RE.match(s)
        if not m:
            pos.append(s)
            continue
        names = [x.strip() for x in re.split(r"[,，、]", m.group(2)) if x.strip()]
        (T if m.group(1) == "T" else C).extend(names)
    if len(pos) > 3:
        raise SideHomeError(
            f"擬歸位行有 {len(pos)} 個位置段，最多只認 3 個"
            f"（大分類 → 中主題 → 小分題）。T／C 要寫成 `→ T:…`／`→ C:…` 才認得。\n"
            f"   原值：擬歸位：{body}")
    return pos, T, C


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

    回傳 [(id, source, category, raw_entry, tc)]；`tc` ＝ `{"T": [...], "C": [...]}`，
    來自該段所屬「擬歸位」行的 `T:`／`C:` 後綴（舊格式沒有 → 兩個都是空 list）。
    raw_entry 是**去掉時段標記後的原文**
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
    home_t, home_c = [], []
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
            segs, home_t, home_c = _split_home_line(m_home.group(1))
            big = segs[0].strip("= ") if segs else big
            mid = segs[1].strip("【】 ") if len(segs) > 1 else ""
            sub = segs[2].strip() if len(segs) > 2 else ""
            continue
        if s.startswith("======") or (s.startswith("=") and s.endswith("=")):
            flush()
            cur = None
            big, mid, sub = s.strip("= "), "", ""
            home_t, home_c = [], []      # 換大分類＝離開上一個擬歸位區段，T/C 不可沿用
            continue
        if s.startswith("【") and s.endswith("】"):
            flush()
            cur = None
            mid, sub = s.strip("【】"), ""
            home_t, home_c = [], []      # 同上：純 txt 排版換中主題時也要清掉
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
            # 🔴 T／C 寫進**這個區段的每一段**，不是只寫第一段。
            #    render 的 `fold_side()` 把單元摺成一列時取的是第一列，
            #    只標第一段的話「第一段沒標、後面有標」整個單元就會看起來沒標；
            #    反過來只標第一段、後面沒有，補標時又會漏掉後面那些 item。
            cur = (key, f"SIDE_{src}", cat, l.rstrip(),
                   {"T": list(home_t), "C": list(home_c)})
            continue
        if sv.LINE_RE.match(l):   # 通訊社素材行：不是側錄，跳過（供混排 txt 直接餵）
            flush()
            cur = None
            continue
        if cur:                   # 內容行：接在 TC 行底下
            cur = (cur[0], cur[1], cur[2], cur[3] + "\n" + l.rstrip(), cur[4])
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
    try:
        parsed = parse_side_txt(text, args.source, homes, args.normalize, tc_date)
    except SideHomeError as e:
        # ⛔ 明確失敗、且**一個字都還沒寫進狀態檔**——交件者改好檔案重跑即可，
        #    素材不會消失。比照 s2_platform_merge.py:110-115。
        print(f"⛔ 側錄檔的擬歸位行格式不對，整份未入庫：\n   {e}")
        sys.exit(2)

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
    # T／C 名稱一律對 TC-字典 驗名（單一真相源，與 set-tc 同一份）。
    # ⚠️ 字典外的名稱**不寫進狀態檔**，視同沒標並列進 uncat_tc 回報——
    #    寫進去會讓網頁出現一個沒有人認得的格子，比留空更難發現。
    ok_t, ok_c = _load_tc_dict()
    _sp_active, _sp_all = load_special_t()
    ok_t = list(ok_t) + _sp_active
    _sp_names = {x.get("name") for x in _sp_all if x.get("name")}
    added, updated, bad, tc_set, tc_filled, uncat_tc, tc_bad = [], [], [], [], [], [], []
    for i, src, cat, entry, tc in parsed:
        if not cat.get("大分類"):
            bad.append(f"{i}: 沒有大分類（候選 TXT 需標擬歸位，或沿用 txt 三層排版）")
            continue
        T, _ = normalize_t((tc or {}).get("T") or [])
        T = [x for x in T if x in ok_t]
        # ⚠️ 先正規化再過濾：舊桶（墨西哥／其他地區）在這裡會被**靜默丟棄**
        C, _ = normalize_c((tc or {}).get("C") or [])
        C = [x for x in C if x in ok_c]
        rej = [x for x in ((tc or {}).get("T") or []) if x not in ok_t] + \
              [x for x in ((tc or {}).get("C") or []) if x not in ok_c]
        # 上限同 set-tc（機動 T 不計）。⚠️ 這裡沒有「重下一次」的機會——
        # 來源是交件端的候選檔，所以違規的段落 T 視同沒標、C 照留，並點名回報。
        _fixed = [x for x in T if x not in _sp_names]
        if len(_fixed) > T_MAX:
            tc_bad.append(f"{i}: T 掛了 {len(_fixed)} 個（{chr(12289).join(_fixed)}），"
                          f"上限 {T_MAX} 個（機動 T 不計）；該段 T 視同沒標，"
                          f"請交件端改候選檔後重跑")
            T = []
        if rej:
            tc_bad.append(f"{i}: 不在 TC-字典 裡的名稱 {'／'.join(rej)}（該段視同沒標）")
        if not (T or C):
            uncat_tc.append(i)
        if i in state["items"] and not args.overwrite:
            updated.append(i)      # 已在庫＝往輪次重跑，內容照舊不動（側錄人工定稿）
            # ⚠️ 但 T／C 是**另一條軸**、不是逐字內容：已在庫卻還沒標的，這裡補上。
            #    候選檔是 append 模式、add-side 每輪重讀整份，交件端事後補了 T:／C:
            #    才有機會生效；⛔ 不可為此改走 --overwrite——那會連 raw_entry
            #    （人工定稿的逐字內容）一起蓋掉。
            cur_tc = state["items"][i].get("tc") or {}
            if (T or C) and not (cur_tc.get("T") or cur_tc.get("C")):
                state["items"][i]["tc"] = {"T": T, "C": C}
                tc_filled.append(i)
            continue
        it = state["items"].get(i) or new_item(src, args.checkpoint, "has_script", entry)
        it["source"] = src
        it["raw_entry"] = entry
        it["category"] = cat
        it["entry_updated"] = args.checkpoint
        it["entry_updated_ts"] = now_ts()
        if T or C:
            # ⛔ 頂層 `tc` 鍵，**不可以塞進 `category`**——`_set_one_category`
            #    是整包覆寫，寄生其中會被後續 set-category／apply_reclass 無聲抹掉。
            it["tc"] = {"T": T, "C": C}
            tc_set.append(i)
        state["items"][i] = it
        added.append(i)
    if args.dry_run:
        print(f"DRY-RUN 解析 {len(parsed)} 段：新增/覆寫 {len(added)}、已在庫略過 {len(updated)}")
        # 預覽前兩段：格式錯了要當場看得出來，不要等進了狀態檔才發現
        for i, src, cat, entry, tc in parsed[:2]:
            print(f"  ── {i}（{src}）→ {cat.get('大分類') or '(缺大分類)'}／"
                  f"{cat.get('中主題') or '(缺中主題)'}／{cat.get('小分題') or '-'}")
            for ln in entry.split("\n")[:2]:
                print(f"     {ln[:60]}")
    else:
        # ⚠️ `tc_filled` 也要觸發存檔：純補標的重跑（整份都已在庫、只是事後補了
        #    `T:`／`C:`）`added` 是空的，只看 `added` 會**印出「補標已在庫 N」卻
        #    什麼都沒寫進去**——宣稱成功、實際丟失，正是這條工程要消滅的形狀。
        #    而 `14` C-3b 白紙黑字承諾「事後在候選檔上補寫 T:/C: 也會生效」。
        if added or tc_filled:
            save(state, args.file)
        print(f"OK 收錄側錄 {len(added)} 段" + (f"：{','.join(added[:8])}…" if len(added) > 8
                                            else (f"：{','.join(added)}" if added else "")))
        if updated:
            print(f"已在庫略過 {len(updated)} 段（要覆蓋加 --overwrite）")
    # ── T／C 回報（2026-08-25，A10 v2 收尾）─────────────────────────────
    # 過渡期要看得出「新格式幾段／舊格式幾段」，才知道交件端跟上了沒有（計畫 2.7）。
    n_new = len(parsed) - len(uncat_tc)
    print(f"T/C：新格式 {n_new} 段已標／舊格式 {len(uncat_tc)} 段沒標"
          + (f"（本次寫入 {len(tc_set)}、補標已在庫 {len(tc_filled)}）" if (tc_set or tc_filled) else ""))
    if uncat_tc:
        # 🔴 缺 T/C **照樣入庫**（比照 s2_platform_merge.py:78-80 的裁定：
        #    分類可以事後補、素材消失補不回來）。舊格式永久合法，⛔ 不設旗標。
        print(f"   ℹ️ 沒標的那 {len(uncat_tc)} 段照樣入庫，網頁會退回關鍵詞兜底／未分類。"
              f"要補標走 set-tc（⛔ 不要用 add-side --overwrite，會蓋掉 raw_entry）。")
    if tc_bad:
        # 這桶現在收兩種：名稱不在字典裡、T 超過上限。標題只講前者的話，
        # 超標那則的訊息會跟標題自相矛盾，交件端會去查一個不存在的錯字。
        print(f"⚠️ {len(tc_bad)} 段的 T/C 被退（名稱不在字典裡，或 T 超過上限）"
              f"——該段視同沒標，其餘照常入庫：")
        print("\n".join("  " + b for b in tc_bad))
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


CHECKPOINT_RE = re.compile(r"^\d{4}-\d{4}$")


def cmd_fix_first_seen(state, args):
    """修正既有素材的 `first_seen_checkpoint` 欄位（格式錯誤救援用）。

    0818-2000 實錯：agent 組 add-batch 的來源檔時，checkpoint 誤填成查詢視窗的
    講法（如「18:00」）而非正確格式 `{MMDD}-{HHMM}`；`update-entry`／`patch-entry`
    的 `--checkpoint` 寫的是 `entry_updated`，都碰不到 `first_seen_checkpoint`——
    這個欄位本來就沒有專門的修改路徑，才需要這支。一般情況不該用到（正常寫入時
    格式已由 add-batch 的檢查擋住），只在事後補救舊資料時用。
    """
    if not CHECKPOINT_RE.match(args.checkpoint):
        print(f"ERROR: --checkpoint 格式錯誤（需為 {{MMDD}}-{{HHMM}}，如 0818-2000）：{args.checkpoint}")
        sys.exit(2)
    ids = [norm_id(x) for x in args.ids.split(",") if x.strip()]
    missing = [i for i in ids if i not in state["items"]]
    if missing:
        print(f"ERROR: 不存在的 id：{','.join(missing)}（其餘未變更，請修正後重跑）")
        sys.exit(2)
    for i in ids:
        state["items"][i]["first_seen_checkpoint"] = args.checkpoint
    save(state, args.file)
    print(f"OK {len(ids)} 則 first_seen_checkpoint 已改為 {args.checkpoint}")


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


def cmd_set_resident_topics(state, args):
    """人工指定某大分類底下「每天都要列出、即使 0 則」的中主題（2026-08-11 使用者訂案）。

    跟 `set-topic-order` 是兩件事：那個只管「有出現時排哪」，清單裡今天不存在的
    中主題自動略過、不會生空標題。這個反過來——**指定的中主題不論當天有沒有
    素材，render 都要印出【中主題】空標題**，讓編輯知道這條線每天都在追、
    不是漏看或漏歸類。

    實作見 `s2_render.group_items()`（txt／html 共用同一份分組）：對
    `resident_topics` 裡列的每個大分類，把指定的中主題當空字典塞進分組結果，
    render_block 遇到空字典只印標題、不印任何素材行——跟真的有素材時完全同一套
    排版邏輯，不必另外處理。

    例：`set-resident-topics --cat 烏俄 --topics "俄轟烏;烏轟俄"`

    ⚠️ 2026-08-17 起分兩層，別搞混：
      · **每天都要的固定中分類**＝寫在 `scripts/s2_resident_topics.json`，建檔輪由
        `s2_scan.ps1 New-ShiftState` 自動寫進當天的新狀態檔（見 `13b §5a`）。
      · **這個指令**＝只改今天這一份狀態檔的當日覆寫，隔天建檔會照設定檔重來。
        要讓某組中主題「以後每天都有」，改設定檔，不要每天下這個指令。
    """
    top = state.setdefault("_top", {})
    resident = top.setdefault("resident_topics", {})
    if args.clear:
        resident.pop(args.cat, None)
        save(state, args.file)
        print(f"OK 已撤掉「{args.cat}」的常駐中主題，不再強制顯示空標題")
        return
    mids = [x.strip() for x in re.split(r"[;；]", args.topics or "") if x.strip()]
    if not mids:
        print("ERROR 需要 --topics（用分號分隔）或 --clear", file=sys.stderr)
        raise SystemExit(2)
    resident[args.cat] = mids
    save(state, args.file)
    print(f"OK 「{args.cat}」常駐中主題：{'、'.join(mids)}（0 則也會列出空標題）")


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


# `show` 的欄位取法。多半是巢狀的（category／fields 底下），所以用取值函式而不是
# 直接 `it[key]`——agent 最常要問的就是分類與摘要，那兩個都不在頂層。
SHOW_FIELDS = {
    "id":     lambda i, it: i,
    "cat":    lambda i, it: "/".join(x for x in cat_tuple(it) if x),
    "大分類":  lambda i, it: cat_tuple(it)[0],
    "中主題":  lambda i, it: cat_tuple(it)[1],
    "小分題":  lambda i, it: cat_tuple(it)[2],
    "entry":  lambda i, it: (it.get("raw_entry") or "").replace("\n", " "),
    "source": lambda i, it: it.get("source") or "",
    "status": lambda i, it: it.get("script_status") or "",
    "cp":     lambda i, it: it.get("first_seen_checkpoint") or "",
    "sb":     lambda i, it: it.get("sb_count"),
    "review": lambda i, it: it.get("needs_review") or "",
    "summary": lambda i, it: (it.get("fields") or {}).get("summary") or "",
    "bite":   lambda i, it: "；".join((it.get("fields") or {}).get("bite") or []),
    "dur":    lambda i, it: (it.get("fields") or {}).get("duration") or "",
    # A10 v2（2026-08-24）：沒有這兩個鍵，agent 沒有任何合規途徑查證自己這輪標了幾則
    # ——show --fields 對不認得的欄位是 sys.exit(2) 硬錯，而 s2_bash_guard 又擋掉
    # python -c 讀狀態檔，只剩 get --id 一則一則倒。
    "T":      lambda i, it: ",".join((it.get("tc") or {}).get("T") or []),
    "C":      lambda i, it: ",".join((it.get("tc") or {}).get("C") or []),
}
DEFAULT_SHOW = ("id", "cat", "source", "cp", "status")


def cat_tuple(it):
    c = it.get("category")
    if isinstance(c, dict):
        return (c.get("大分類") or "", c.get("中主題") or "", c.get("小分題") or "")
    if isinstance(c, str) and "/" in c:
        p = [x.strip() for x in c.split("/", 2)] + ["", ""]
        return p[0], p[1], p[2]
    return "", "", ""


def cmd_show(state, args):
    """批次查看多則的**指定欄位**（2026-08-11 加）。

    🔴 **為什麼要有這支**：`get` 一次只吃一個 id、而且整包 JSON 全 dump。
    所以「這 20 則各自的分類是什麼」這種最常見的問題，用 `get` 要叫 20 次、
    每次還噴一大包無關欄位——agent 於是理性地選擇自己寫
    `python -c "import json; d=json.load(...)"`。0811-2000 那輪 67 次 Bash 裡
    **有 22 次是這種臨時查詢腳本**，是單一最大宗的可消除呼叫。

    用法：
      show --ids RT4519,AP4677743                     # 預設欄位
      show --ids RT4519 --fields cat,entry,bite       # 指定欄位
      show --cat 烏俄 --fields id,中主題               # 依大分類篩，不必先知道 id
      show --checkpoint 0811-2000 --fields id,cat     # 依本輪 checkpoint 篩
    ⚠️ 不給任何篩選條件會列出**全部**，量大時請務必帶 `--fields` 只取要用的欄位——
       這支的意義就是少搬東西進 context，整包倒出來就白費了。
    """
    bad = [f for f in (args.fields or "").split(",") if f.strip() and f.strip() not in SHOW_FIELDS]
    if bad:
        print(f"ERROR: 不認得的欄位 {','.join(bad)}；可用："
              f"{'／'.join(SHOW_FIELDS)}", file=sys.stderr)
        sys.exit(2)
    fields = [f.strip() for f in (args.fields or "").split(",") if f.strip()] or list(DEFAULT_SHOW)

    if args.ids:
        want = [norm_id(x) for x in args.ids.split(",") if x.strip()]
        missing = [i for i in want if i not in state["items"]]
        rows = [(i, state["items"][i]) for i in want if i in state["items"]]
    else:
        missing = []
        rows = list(state["items"].items())
        if args.cat:
            rows = [(i, it) for i, it in rows if cat_tuple(it)[0] == args.cat]
        if args.mid:
            rows = [(i, it) for i, it in rows if cat_tuple(it)[1] == args.mid]
        if args.checkpoint:
            rows = [(i, it) for i, it in rows
                    if it.get("first_seen_checkpoint") == args.checkpoint]
        if args.needs_review:
            rows = [(i, it) for i, it in rows if it.get("needs_review")]
        if args.uncat:
            # 0812 T5：空分類（category={} 或大分類缺）不等於 `--cat "?"` 查得到——
            # `--cat` 只認非空字串，要單獨開一條路才找得到真正沒分類的素材。
            # 排除 script_status=note 的備註殼——那本來就不進分類流程，不算異常。
            rows = [(i, it) for i, it in rows
                    if not cat_tuple(it)[0] and it.get("script_status") != "note"]

    if args.json:
        print(json.dumps([{f: SHOW_FIELDS[f](i, it) for f in fields} for i, it in rows],
                         ensure_ascii=False))
    else:
        for i, it in rows:
            print("\t".join(str(SHOW_FIELDS[f](i, it)) for f in fields))
    print(f"（{len(rows)} 則）", file=sys.stderr)
    if missing:
        print(f"⚠️ 不存在 {len(missing)} 則：{','.join(missing)}", file=sys.stderr)


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
    lt.add_argument("--compact", action="store_true",
                     help="精簡輸出：每主題一行（大分類｜中主題｜則數），不列小分題明細")
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
    a.add_argument("--src-text", help="瘦身後的站方原文（離線查證用，同 add-batch）")
    ab = sub.add_parser("add-batch")
    ab.add_argument("--entries", required=True,
                    help="JSON 陣列檔，每筆含 id/source/checkpoint/status/entry")
    u = sub.add_parser("update-entry")
    # ⚠️ `--id` 不再 required：批次走 `--batch`，兩者擇一（函式裡檢查）。
    u.add_argument("--id")
    u.add_argument("--batch", help="批次覆寫：JSON 陣列檔，每筆 {id, entry[, sb_count,"
                                   "status, checkpoint, footage_type]}。改 N 則不必寫迴圈")
    u.add_argument("--status", choices=["has_script", "pending"])
    u.add_argument("--checkpoint")
    u.add_argument("--entry", help="行內短內容（與 --entry-file 擇一）")
    u.add_argument("--entry-file", help="長內容檔案路徑（與 --entry 擇一）")
    # R9（2026-08-13）：回寫站方原文。批次檔每筆也可帶 src_text；只帶 {id, src_text}
    # 的批次筆＝純回補原文，不動 raw_entry（R11 整批漏帶的救援路徑）。
    u.add_argument("--src-text", help="站方原文（行內；與 --src-text-file 擇一）")
    u.add_argument("--src-text-file", help="站方原文檔案路徑")
    # ⚠️ default 由 0 改為 None（2026-08-09）：0 是**有意義的值**（真的沒有 SOUNDBITE），
    # 拿它當「沒帶參數」的預設，會讓每一次沒帶 --sb-count 的 update-entry 都撞上
    # bite_doubt 的反向判準（`(BITE)` 且 sb_count==0 → 假 BITE），憑空生出 needs_review
    # 雜訊；改存進狀態檔之後更嚴重，會把好的舊值蓋成 0。**None ＝ 沒帶，不要動舊值。**
    u.add_argument("--sb-count", type=int, default=None,
                   help="抽取白名單數出的 SOUNDBITE 段數；>0 且 entry 寫「無BITE」會擋下。"
                        "站方補完整稿後回寫用（不帶＝不動舊值）")
    pe = sub.add_parser("patch-entry",
                        help="機械修補既有素材行的標記（🔴／🟡／⭐／補 (BITE)），"
                             "不必重打整條 entry")
    pe.add_argument("--ids", required=True, help="逗號分隔；不存在的 id 一律先擋下不改")
    pe.add_argument("--alert", choices=["red", "yellow", "star", "none"],
                    help="🔴 重大（進檔頭）／🟡 重大未進檔頭／⭐ 推薦／none 撤掉；三者互斥，"
                         "換標記自動剝舊插新。⛔ 重大與否是編輯判斷，只有明令才動；"
                         "⭐ 更嚴格——只能是使用者親自明示才可以標，agent 不可自行判斷該標")
    pe.add_argument("--bite", action="store_true",
                    help="補第二括號 (BITE)。只補「有 ▎BITE： 段但缺 (BITE)」這一種；"
                         "已有／寫著無BITE／沒有 BITE 段一律拒絕不動")
    pe.add_argument("--checkpoint")
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
    ffs = sub.add_parser("fix-first-seen",
                         help="修正 first_seen_checkpoint 格式錯誤（update-entry/patch-entry 都碰不到這個欄位）")
    ffs.add_argument("--ids", required=True)
    ffs.add_argument("--checkpoint", required=True, help="正確格式 {MMDD}-{HHMM}，如 0818-2000")
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
    spt = sub.add_parser("set-special-t",
                         help="開／收機動 T（議題軸臨時 TAG）；⛔ 使用者下令才動")
    spt.add_argument("--open", help="要開的機動 T 名稱，如 颱風")
    spt.add_argument("--charter", help="這個 TAG 收什麼，一句話")
    spt.add_argument("--retire", help="要退場的機動 T 名稱")

    srt = sub.add_parser("set-resident-topics",
                         help="釘住某大分類每天都要列出的中主題（0 則也印空標題，跟 set-topic-order 不同）")
    srt.add_argument("--cat", required=True, help="大分類，如 烏俄")
    srt.add_argument("--topics", help="中主題清單，分號分隔")
    srt.add_argument("--clear", action="store_true", help="撤掉常駐設定")
    c = sub.add_parser("set-category")
    c.add_argument("--id")
    c.add_argument("--cat", help="大分類/中主題[/小分題]")
    c.add_argument("--pairs", help='批次："id=大分類/中主題[/小分題];id2=..."（分隔符優先認分號）')
    tc = sub.add_parser("set-tc", help="寫 T（議題）／C（地緣）標籤；名單只認 TC-字典.md")
    tc.add_argument("--id")
    tc.add_argument("--tc", help="T1,T2/C1,C2（單側可留空，例：/臺灣）")
    tc.add_argument("--pairs", help='批次："id=T1,T2/C1,C2;id2=..."（分隔符優先認分號）。'
                                    f'⚠️ 每 checkpoint 上限 {TC_CALLS_PER_CHECKPOINT} 次，請整批一次下')
    st = sub.add_parser("set-top")
    st.add_argument("field")
    st.add_argument("value")
    g = sub.add_parser("get")
    g.add_argument("--id", required=True)
    sh = sub.add_parser("show",
                        help="批次查多則的指定欄位（取代自己寫 python 讀狀態檔）")
    sh.add_argument("--ids", help="逗號分隔；不給就用下面的條件篩")
    sh.add_argument("--cat", help="只看某大分類")
    sh.add_argument("--mid", help="只看某中主題")
    sh.add_argument("--checkpoint", help="只看某輪收進來的")
    sh.add_argument("--needs-review", action="store_true", help="只看有 needs_review 的")
    sh.add_argument("--uncat", action="store_true",
                     help="只看大分類為空的（排除 script_status=note 的備註殼）")
    sh.add_argument("--fields", help=f"逗號分隔，預設 {','.join(DEFAULT_SHOW)}；"
                                     f"可用：{','.join(SHOW_FIELDS)}")
    sh.add_argument("--json", action="store_true", help="輸出 JSON 而非 TSV")
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
        "update-entry": cmd_update_entry, "patch-entry": cmd_patch_entry,
        "pending": cmd_pending,
        "add-side": cmd_add_side, "set-alert": cmd_set_alert,
        "set-topic-order": cmd_set_topic_order,
        "set-special-t": cmd_special_t,
        "set-resident-topics": cmd_set_resident_topics,
        "set-mark": cmd_set_mark, "set-aired": cmd_set_aired,
        "fix-first-seen": cmd_fix_first_seen,
        "set-category": cmd_set_category, "set-tc": cmd_set_tc,
        "get": cmd_get, "show": cmd_show,
        "remove": cmd_remove,
        "needs-review": cmd_needs_review, "set-top": cmd_set_top,
        "scratch-dir": cmd_scratch_dir, "list-topics": cmd_list_topics,
    }[args.cmd](state, args)


if __name__ == "__main__":
    main()
