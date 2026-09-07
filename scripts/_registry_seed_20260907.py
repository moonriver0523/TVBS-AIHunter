# -*- coding: utf-8 -*-
"""一次性腳本（A10 P1a Task 3，2026-09-07）：從近 11 天 Archive 狀態檔
統計中主題出現天數／則數，人工核定同事件異名合併表＋charter，寫出
`s2_topic_registry.json` 草稿與人可讀摘要 `_registry_seed_20260907_summary.txt`。

只讀 Archive／今日狀態檔，不改任何來源檔案。草稿寫出後仍要**給使用者看過
再算數**——commit 訊息會註明「草稿待使用者審」。

合併判準：只併「確定是同一件事╱同一個持續中事件的不同稱呼」——地名、
人名、機構名都一致，只是綴詞（賽事/戰報/動態/爭議…）或近義詞
（去世/駕崩）不同，或是同一種「當日雜項通用桶」（足球／國會／治安…
這類每天都在收、講的是同一整類東西而非同一件事）。凡是「可能只是題材
相近但實際是不同事件」的一律不併，留在 `CONSIDERED_NOT_MERGED` 裡
供使用者裁決（例：習近平出訪埃及 vs 訪吉爾吉斯，兩國不同行程）。

用法：
    python _registry_seed_20260907.py            # 只印候選統計表，不寫檔
    python _registry_seed_20260907.py --build     # 套用下面的合併表，
                                                    # 寫出 s2_topic_registry.json
                                                    # 草稿＋摘要
"""
import argparse
import glob
import json
import os
import re
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_REGISTRY = os.path.join(HERE, "s2_topic_registry.json")
OUT_SUMMARY = os.path.join(HERE, "_registry_seed_20260907_summary.txt")

ARCHIVE_GLOB = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive\2026*\*-s2-state.json"
TODAY_FILE = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\0906-s2-state.json"
# 近 11 天：0827–0905（Archive）＋0906（當日）
WANTED_MMDD = {f"08{d:02d}" for d in range(27, 32)} | {f"09{d:02d}" for d in range(1, 7)}


def load_items(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            d = json.load(f) or {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"# 跳過（讀取失敗）{path}：{e}")
        return []
    items = d.get("items") or []
    if isinstance(items, dict):
        items = list(items.values())
    return items


def collect():
    files = {}
    for p in glob.glob(ARCHIVE_GLOB):
        mmdd = os.path.basename(p)[:4]
        if mmdd in WANTED_MMDD:
            files[mmdd] = p
    if os.path.exists(TODAY_FILE):
        files["0906"] = TODAY_FILE
    # 中主題 → {days: set(mmdd), count: int, bigs: [大分類,…], sample: 第一則 summary}
    stat = defaultdict(lambda: {"days": set(), "count": 0, "bigs": [], "sample": ""})
    for mmdd, path in sorted(files.items()):
        for it in load_items(path):
            c = (it or {}).get("category") or {}
            mid = c.get("中主題")
            big = c.get("大分類")
            if not mid or not big:
                continue
            s = stat[mid]
            s["days"].add(mmdd)
            s["count"] += 1
            s["bigs"].append(big)
            if not s["sample"]:
                summ = ((it.get("fields") or {}).get("summary") or "")[:40]
                if summ:
                    s["sample"] = summ
    return files, stat


def print_candidates():
    files, stat = collect()
    print(f"讀到 {len(files)} 份狀態檔：{'、'.join(sorted(files))}")
    kept = {m: s for m, s in stat.items() if len(s["days"]) >= 2 or s["count"] >= 8}
    print(f"中主題總數 {len(stat)}，符合門檻（≥2 天或 ≥8 則）{len(kept)} 個\n")
    rows = sorted(kept.items(), key=lambda kv: (-len(kv[1]["days"]), -kv[1]["count"]))
    for mid, s in rows:
        bigs = "／".join(sorted(set(s["bigs"])))
        print(f"{mid}\t天數={len(s['days'])}\t則數={s['count']}\t大分類={bigs}\t"
              f"例：{s['sample']}")


# ═══════════════════════════════════════════════════════════════════════
# ── --build：人工核定的合併表＋charter（2026-09-07 產出）───────────────
# ═══════════════════════════════════════════════════════════════════════

RESIDENT_CHARTERS = {
    "烏打俄": "烏克蘭（含其盟友如英美武器援助）主動發起的攻擊、反攻、突襲行動",
    "俄打烏": "俄羅斯主動發起的攻擊、飛彈／無人機空襲、地面進攻",
}
RESIDENT_BIG = {"烏打俄": "烏俄", "俄打烏": "烏俄"}

# canonical -> [aliases]（都是同一件事／同一持續事件的異名，或同一種通用桶）
MERGES = {
    "尼泊爾洪災": [
        "尼泊爾水電廠隧道搜救", "尼泊爾洪災：生還者與家屬故事", "尼泊爾洪災：搜救行動",
        "尼泊爾洪災搜救生還者", "尼泊爾洪災：國際人道馳援", "尼泊爾洪災死傷與搜救現況",
        "尼泊爾隧道受困工人搜救", "尼泊爾洪災：罹難失蹤統計", "尼泊爾國際與陸方援助行動",
        "尼泊爾洪災救援專訪", "尼泊爾洪災：外籍旅客與健行團失蹤", "尼泊爾洪災搜救",
        "尼泊爾洪災死傷統計", "尼泊爾洪災：肇因與後續風險", "尼泊爾家屬尋親與心聲",
        "尼泊爾洪災衝擊", "尼泊爾聯合國援助協調", "尼泊爾隧道搜救官方說明", "尼泊爾國際馳援",
    ],
    "中尼邊境洪災": ["中尼邊境泥石流", "尼泊爾洪災：中國西藏境內衝擊"],
    "美網": ["美網戰報", "美網賽事", "美網公開賽", "美網賽前記者會"],
    "克蘭西殺子案": ["琳賽克蘭西殺子案", "麻州殺子案審判", "克蘭西殺子案審判"],
    "大峽谷洪災": ["大峽谷洪水撤離"],
    "911週年": ["911事發資料", "911事件週年", "911周年紀念"],
    "荷姆茲海峽情勢": ["荷姆茲海峽軍事對峙"],
    "挪威國王駕崩": ["挪威國王去世"],
    "日本秋雨豪雨": ["日本秋雨鋒面豪雨"],
    "美伊衝突評估": ["美伊衝突升級"],
    "趣聞快訊": ["趣聞快報"],
    "圖帕克命案": ["圖帕克夏庫爾案宣判"],
    "休達移民": ["休達移民危機"],
    "移民執法": ["移民執法爭議", "ICE執法爭議"],
    "高爾夫": ["高爾夫賽事"],
    "MLB": ["MLB看點"],
    "印尼火山": ["印尼火山噴發"],
    "賽普勒斯船難": ["賽普勒斯渡輪翻覆"],
    "上合峰會": ["上合組織峰會", "上合組織峰會（比什凱克）"],
    "期中選舉": ["期中選戰", "期中選舉金源", "美國期中選舉"],
    "足球": ["足球賽事", "足球戰報"],
    "網球": ["網球賽事"],
    "治安": ["治安動態"],
    "美股": ["美股動態"],
    "國會": ["國會動態"],
    "賽車": ["賽車賽事"],
    "明尼阿波利斯槍擊案": ["明尼亞波利斯槍擊"],  # 同一起槍擊案，純音譯差異
    "熱帶風暴愛德華": ["德州熱帶風暴愛德華水患"],
    "美委石油協議": ["委內瑞拉石油協議"],
    "美軍空襲拉拉克島": ["美軍攻伊朗拉拉克島"],
    "福克蘭群島爭議": ["阿根廷福克蘭爭議"],
    "自由車": ["英倫自由車賽"],  # 兩則樣本都在講同一個「環英自由車賽」
    "川普動態": ["川普動向"],
    "冰島入歐公投": ["冰島歐盟公投"],
    "環西賽": ["環西自行車賽"],  # 都是環西班牙自行車賽，只是分站報導各自簡稱
    "意外": ["意外事故"],  # 同一種「當日雜項意外」通用桶，不是同一起意外，比照足球/國會等通用桶邏輯併
    "英超": ["英超足球", "英超轉會"],
    "太空探索": ["羅曼太空望遠鏡發射"],  # 樣本都在講同一顆羅曼太空望遠鏡任務；「太空」另有所指，不併
    # ⚠️ 這組刻意不用「最短名」規則：「影展」太泛用（未來可能有別的影展），
    # 用更明確的「威尼斯影展」當 canonical 比較不會誤導。
    "威尼斯影展": ["影展"],
}

# 手寫 charter（合併群 canonical 用；比自動摘要更準）
CHARTERS = {
    "尼泊爾洪災": "尼泊爾（含中國西藏境外段）豪雨土石流：死傷失蹤統計、搜救行動、國際人道援助、生還者與家屬故事",
    "中尼邊境洪災": "同一波豪雨在中國（西藏吉隆口岸等）境內造成的洪災泥石流衝擊與搶修，跟尼泊爾洪災分開放——是同一氣候系統但不同國家災情",
    "美網": "美國網球公開賽賽事戰報、選手動態與賽前賽後訪問",
    "克蘭西殺子案": "麻州普利茅斯琳賽・克蘭西殺害3名子女案的審判進度",
    "大峽谷洪災": "美國大峽谷國家公園暴雨洪水災情與遊客撤離",
    "911週年": "911事件週年紀念活動與相關回顧報導",
    "荷姆茲海峽情勢": "荷姆茲海峽美伊軍事對峙與情勢評估",
    "挪威國王駕崩": "挪威國王哈拉爾五世駕崩相關報導",
    "日本秋雨豪雨": "日本秋雨鋒面豪雨造成的災情",
    "美伊衝突評估": "美國與伊朗軍事衝突情勢的評估與升級動態",
    "趣聞快訊": "各地趣聞、暖新聞等輕鬆話題快訊",
    "圖帕克命案": "饒舌歌手圖帕克·夏庫爾命案相關法律程序與宣判",
    "休達移民": "西班牙屬地休達的移民（含闖關、營地拆除）相關新聞",
    "移民執法": "美國本土移民執法行動（ICE等）與相關爭議",
    "高爾夫": "高爾夫球賽事戰報",
    "MLB": "美國職棒大聯盟賽事戰報與球員動態",
    "印尼火山": "印尼火山活動與噴發災情",
    "賽普勒斯船難": "賽普勒斯附近渡輪翻覆船難的搜救與生還者報導",
    "上合峰會": "上海合作組織峰會（含比什凱克場次）議程、宣言與相關外交",
    "期中選舉": "美國期中選舉選情、選戰與政治獻金動態",
    "足球": "各項足球賽事戰報與球隊動態",
    "網球": "網球賽事戰報（美網以外的一般網球新聞）",
    "治安": "美國本土治安事件動態",
    "美股": "美國股市每日開盤／收盤等短訊動態",
    "國會": "美國國會議事動態",
    "賽車": "賽車相關賽事戰報",
    "明尼阿波利斯槍擊案": "明尼亞波利斯市中心公寓大樓槍擊案（含警員傷亡）後續",
    "熱帶風暴愛德華": "熱帶風暴愛德華侵襲德州、路易斯安那州的路徑與水患",
    "美委石油協議": "美國與委內瑞拉石油儲量／股權協議",
    "美軍空襲拉拉克島": "美軍空襲伊朗拉拉克島相關軍事行動",
    "福克蘭群島爭議": "阿根廷與英國的福克蘭（馬爾維納斯）群島主權爭議",
    "自由車": "自由車（公路自行車）賽事戰報，如環英自由車賽",
    "川普動態": "美國總統川普的例行公開行程與直播畫面",
    "冰島入歐公投": "冰島是否重啟歐盟入會談判的公投",
    "環西賽": "環西班牙自行車賽各分站戰報",
    "意外": "當日雜項意外事故通用桶（車禍、墜機、氣爆等單一意外事件）",
    "英超": "英格蘭足球超級聯賽賽事、轉會與球隊動態",
    "太空探索": "NASA南希·格瑞斯·羅曼太空望遠鏡發射與後續任務進展",
    "威尼斯影展": "威尼斯影展（含頒獎、影人動態、參展作品）",
}

# 「考慮過但決定先不併」——不寫進登記簿，只在摘要標「?」讓使用者裁決；
# 這些名稱各自照候選資料生成自己獨立的 canonical 條目。
CONSIDERED_NOT_MERGED = [
    ("挪威國王哈孔繼位", "挪威國王駕崩",
     "同一王室交接故事的下一步（繼位）還是該併＝同一持續事件？先分開，交你定。"),
    ("上合峰會中國戰略", "上合峰會", "是分析角度不是純會議報導，先分開。"),
    ("習近平出訪", "上合峰會／習近平出訪埃及",
     "同一趟出訪的泛稱，可能該併進上合峰會或埃及行程其中一邊，先分開。"),
    ("習近平訪吉爾吉斯", "上合峰會",
     "吉爾吉斯國是訪問是同一趟上合峰會行程的一站，可能該併，先分開。"),
    ("習近平出訪埃及", "（無，獨立即可）", "確定是不同國家的獨立行程，不太可能該併，僅列以求完整。"),
    ("G20邀俄羅斯財長爭議", "G20財長會議", "是外交爭議角度不是例行會議報導，先分開。"),
    ("好萊塢動態／好萊塢一分鐘／好萊塢星光大道", "（互相間）",
     "字面像異名但其實是三種不同性質的娛樂新聞（一般動態／固定短講段／星光大道典禮），判定不併。"),
    ("敘利亞局勢／敘利亞化武銷毀", "（互相間）", "判定是不同角度的敘利亞新聞，不併。"),
    ("義大利遊客洪水死裡逃生／義大利梅洛尼執政紀錄／義大利大使專訪", "（互相間）",
     "同開頭純屬巧合，三則完全不同主題，不併。"),
]

_MMDD_TO_DATE = {}
for _m in range(8, 10):
    for _d in range(1, 32):
        try:
            _MMDD_TO_DATE[f"{_m:02d}{_d:02d}"] = datetime(2026, _m, _d).strftime("%Y-%m-%d")
        except ValueError:
            pass


def _date_of(mmdd):
    return _MMDD_TO_DATE.get(mmdd, mmdd)


def build():
    _files, stat = collect()
    data = {m: {"days": s["days"], "count": s["count"], "bigs": s["bigs"], "sample": s["sample"]}
            for m, s in stat.items() if len(s["days"]) >= 2 or s["count"] >= 8}

    alias_to_canon = {a: canon for canon, aliases in MERGES.items() for a in aliases}

    missing = [a for aliases in MERGES.values() for a in aliases if a not in data]
    if missing:
        raise SystemExit(f"MERGES 裡有候選資料找不到的名字，檢查手抄有沒有打錯：{missing}")
    missing_canon = [c for c in MERGES if c not in data]
    if missing_canon:
        raise SystemExit(f"MERGES 的 canonical 名字本身不在候選資料裡：{missing_canon}")

    topics = []
    today = datetime.now().strftime("%Y-%m-%d")
    for name, charter in RESIDENT_CHARTERS.items():
        topics.append({
            "name": name, "charter": charter, "aliases": [], "big": RESIDENT_BIG[name],
            "tc": {"T": [], "C": []}, "first_seen": today, "last_seen": today, "resident": True,
        })

    used = set(RESIDENT_CHARTERS)
    for name, info in data.items():
        if name in alias_to_canon or name in RESIDENT_CHARTERS:
            continue
        used.add(name)
        aliases = list(MERGES.get(name, []))
        all_days = set(info["days"])
        all_bigs = list(info["bigs"])
        for a in aliases:
            all_days |= set(data[a]["days"])
            all_bigs += data[a]["bigs"]
        first_seen = _date_of(min(all_days))
        last_seen = _date_of(max(all_days))
        big = max(set(all_bigs), key=all_bigs.count)
        if name in CHARTERS:
            charter = CHARTERS[name]
        else:
            # 沒手寫 charter 的：用實際樣本句子清出第一子句當草稿——真實出現過
            # 的敘述，不是憑空編；仍是「草稿」，之後用 topic-register 覆寫即可。
            sample = info.get("sample") or ""
            sample = re.split(r"[，；;,]", sample)[0].strip()
            charter = sample or f"{name}相關報導"
        topics.append({
            "name": name, "charter": charter, "aliases": aliases, "big": big,
            "tc": {"T": [], "C": []}, "first_seen": first_seen, "last_seen": last_seen,
            "resident": False,
        })

    unaccounted = set(data) - used - set(alias_to_canon)
    if unaccounted:
        raise SystemExit(f"有候選名字沒被歸類（既不是 canonical 也不是 alias）：{unaccounted}")

    topics.sort(key=lambda t: (0 if t["resident"] else 1, t["big"], -len(t.get("aliases", []))))

    with open(OUT_REGISTRY, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"topics": topics}, f, ensure_ascii=False, indent=2)
        f.write("\n")

    merged_count = sum(1 for t in topics if t.get("aliases"))
    with open(OUT_SUMMARY, "w", encoding="utf-8") as f:
        f.write(f"登記簿草稿：{len(topics)} 題（含常駐題 {len(RESIDENT_CHARTERS)}）／"
                f"候選 {len(data)} 個名字\n")
        f.write(f"合併了 {merged_count} 組異名（共吸收 {len(alias_to_canon)} 個別名）\n")
        f.write(f"考慮過但決定不併、標「?」共 {len(CONSIDERED_NOT_MERGED)} 組\n\n")
        f.write("=== canonical｜aliases｜charter（依大分類排序）===\n")
        for t in topics:
            alias_s = "、".join(t.get("aliases") or []) or "（無）"
            mark = "🔒常駐 " if t["resident"] else ""
            f.write(f"{mark}[{t['big']}] {t['name']}｜別名：{alias_s}｜{t['charter']}\n")
        f.write("\n=== 標「?」：考慮過但決定先不併（交使用者裁決）===\n")
        for name, target, why in CONSIDERED_NOT_MERGED:
            f.write(f"? {name} —— 可能該併進「{target}」？{why}\n")

    print(f"OK 寫出登記簿草稿：{OUT_REGISTRY}（{len(topics)} 題）")
    print(f"OK 寫出摘要：{OUT_SUMMARY}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true",
                    help="套用人工核定的合併表＋charter，寫出登記簿草稿與摘要"
                         "（不帶這個旗標只印候選統計表，不寫檔）")
    args = ap.parse_args()
    if args.build:
        build()
    else:
        print_candidates()


if __name__ == "__main__":
    main()
