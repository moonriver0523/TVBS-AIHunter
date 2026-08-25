# -*- coding: utf-8 -*-
"""PROTOTYPE — T/C 矩陣網頁試作，0821 晚班資料。勿當生產渲染器。

字典唯一來源：
E:\\GitHub\\TVBS-AIHunter-a10-p0\\common\\plans\\a10-p0-data\\TC-字典.md
機動議題不進字典、AI 不得自加。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import s2_render_html as H  # noqa: E402
import s2_render as R  # noqa: E402

STATE = r"G:\我的雲端硬碟\Claude共用\自動掃帶系統\Archive\20260821\0821-s2-state.json"
MMDD = "0821"
# 成品只寫 Downloads，不把晚班正文寫進 git 工作區
OUT = r"D:\Downloads\0821晚班交接-TC矩陣試作.html"
DL = OUT

T_FIXED = [
    ("烏俄", "🛡️"),
    ("美伊", "💥"),
    ("地緣衝突", "⚔️"),
    ("天災天氣", "🌪️"),
    ("政治", "🏛️"),
    ("社會", "🏘️"),
    ("財經", "💹"),
    ("科技醫藥", "💊"),
    ("娛樂藝文", "🎭"),
    ("體育", "⚽"),
    ("話題", "💬"),
]
C_FIXED = [
    ("臺灣", "tw"),
    ("中國大陸", "cn"),
    ("美國", "us"),
    ("加拿大", "ca"),
    ("日本", "jp"),
    ("南韓", "kr"),
    ("北韓", "kp"),
    ("泰國", "th"),
    ("新加坡", "sg"),
    ("東南亞", ""),
    ("南亞", ""),
    ("以色列", "il"),
    ("伊朗", "ir"),
    ("中東", ""),
    ("烏克蘭", "ua"),
    ("俄羅斯", "ru"),
    ("歐洲", "eu"),
    ("非洲", ""),
    ("中南美", ""),
    ("紐澳", "au"),
    ("國際", ""),
]
C_FALLBACK = {
    "東南亞": "🌴", "南亞": "🪔", "中東": "🕌",
    "非洲": "🦁", "中南美": "🌎", "國際": "🌐",
}
T_EMOJI = {k: v for k, v in T_FIXED}

# 列上額外顯示的「細國」旗（C 仍走封閉桶）——存 ISO，Windows 國旗 emoji 會壞
FLAG_KW = [
    ("香港", "hk"), ("中國", "cn"), ("北京", "cn"), ("印尼", "id"),
    ("日本", "jp"), ("南韓", "kr"), ("韓國", "kr"), ("三星", "kr"), ("現代", "kr"),
    ("美國", "us"), ("川普", "us"), ("夏威夷", "us"), ("紐約", "us"),
    ("德州", "us"), ("西雅圖", "us"), ("奧馬哈", "us"), ("甘迺迪", "us"),
    ("以色列", "il"), ("加薩", "ps"), ("黎巴嫩", "lb"), ("葉門", "ye"),
    ("阿曼", "om"), ("敘利亞", "sy"), ("伊朗", "ir"), ("希伯崙", "ps"),
    ("巴基斯坦", "pk"), ("古巴", "cu"), ("波蘭", "pl"), ("新加坡", "sg"),
    ("瑞士", "ch"), ("剛果", "cd"), ("澳洲", "au"), ("印度", "in"),
    ("匈牙利", "hu"), ("義大利", "it"), ("西西里", "it"), ("墨西哥", "mx"),
    ("哥倫比亞", "co"), ("加拿大", "ca"), ("西班牙", "es"), ("羅馬尼亞", "ro"),
    ("英國", "gb"), ("沙國", "sa"), ("沙聯", "sa"), ("柏林", "de"),
    ("巴黎", "fr"), ("北約", "eu"), ("歐盟", "eu"), ("烏克蘭", "ua"),
    ("基輔", "ua"), ("俄羅斯", "ru"), ("俄澳", "ru"), ("臺灣", "tw"), ("台灣", "tw"),
    ("泰國", "th"), ("曼谷", "th"), ("墨西哥", "mx"), ("加拿大", "ca"),
    ("北韓", "kp"), ("平壤", "kp"),
]


def _svg(*parts, vb="0 0 30 20"):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">{"".join(parts)}</svg>'


def _r(x, y, w, h, fill):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>'


FLAGS = {
    "tw": _svg(_r(0, 0, 30, 20, "#fe0000"), _r(0, 0, 15, 10, "#000095"),
               '<circle cx="7.5" cy="5" r="3.4" fill="#fff"/><circle cx="7.5" cy="5" r="2.1" fill="#000095"/>',
               '<circle cx="7.5" cy="5" r="1.15" fill="#fff"/>'),
    "cn": _svg(_r(0, 0, 30, 20, "#de2910"),
               '<polygon points="6,3.2 6.9,5.8 4.3,4.2 7.7,4.2 5.1,5.8" fill="#ffde00"/>',
               '<polygon points="10.6,2.4 11.1,3.8 9.7,2.9 11.5,2.9 10.1,3.8" fill="#ffde00"/>',
               '<polygon points="12.4,4.2 12.9,5.6 11.5,4.7 13.3,4.7 11.9,5.6" fill="#ffde00"/>',
               '<polygon points="12.4,6.8 12.9,8.2 11.5,7.3 13.3,7.3 11.9,8.2" fill="#ffde00"/>',
               '<polygon points="10.6,8.6 11.1,10 9.7,9.1 11.5,9.1 10.1,10" fill="#ffde00"/>'),
    "us": _svg(_r(0, 0, 30, 20, "#fff"),
               "".join(_r(0, i * 20 / 13, 30, 20 / 13 + 0.05, "#b22234") for i in range(0, 13, 2)),
               _r(0, 0, 12, 20 * 7 / 13, "#3c3b6e"),
               "".join(f'<circle cx="{1.2 + (j % 6) * 1.85 + (0.9 if j >= 30 else 0)}" cy="{1.1 + (j // 6) * 1.35}" r="0.38" fill="#fff"/>'
                       for j in range(50) if j < 30)),
    "jp": _svg(_r(0, 0, 30, 20, "#fff"), '<circle cx="15" cy="10" r="6" fill="#bc002d"/>'),
    "kr": _svg(_r(0, 0, 30, 20, "#fff"),
               '<circle cx="15" cy="10" r="4.6" fill="#cd2e3a"/>',
               '<path d="M10.4,10 A4.6,4.6 0 0 0 19.6,10 A2.3,2.3 0 0 1 15,10 A2.3,2.3 0 0 0 10.4,10" fill="#0047a0"/>'),
    "eu": _svg(_r(0, 0, 30, 20, "#003399"),
               "".join(f'<circle cx="{15 + 6.2 * __import__("math").cos((i * 30 - 90) * 3.1416 / 180):.2f}" cy="{10 + 6.2 * __import__("math").sin((i * 30 - 90) * 3.1416 / 180):.2f}" r="0.85" fill="#ffcc00"/>'
                       for i in range(12))),
    "ua": _svg(_r(0, 0, 30, 10, "#005bbb"), _r(0, 10, 30, 10, "#ffd500")),
    "ru": _svg(_r(0, 0, 30, 6.67, "#fff"), _r(0, 6.67, 30, 6.67, "#0039a6"), _r(0, 13.34, 30, 6.66, "#d52b1e")),
    "hk": _svg(_r(0, 0, 30, 20, "#de2910"),
               '<polygon points="15,4 16.2,8.2 20.6,8.2 17.2,10.7 18.4,14.9 15,12.4 11.6,14.9 12.8,10.7 9.4,8.2 13.8,8.2" fill="#fff"/>'),
    "id": _svg(_r(0, 0, 30, 10, "#ce1126"), _r(0, 10, 30, 10, "#fff")),
    "il": _svg(_r(0, 0, 30, 20, "#fff"), _r(0, 3.2, 30, 2.2, "#0038b8"), _r(0, 14.6, 30, 2.2, "#0038b8"),
               '<polygon points="15,6.6 17.6,11.2 12.4,11.2" fill="none" stroke="#0038b8" stroke-width="0.7"/>',
               '<polygon points="15,13.4 12.4,8.8 17.6,8.8" fill="none" stroke="#0038b8" stroke-width="0.7"/>'),
    "ps": _svg(_r(0, 0, 30, 6.67, "#000"), _r(0, 6.67, 30, 6.67, "#fff"), _r(0, 13.34, 30, 6.66, "#007a3d"),
               '<polygon points="0,0 10,10 0,20" fill="#ce1126"/>'),
    "lb": _svg(_r(0, 0, 30, 20, "#ed1c24"), _r(0, 5, 30, 10, "#fff"),
               '<polygon points="15,6.2 16.4,10.4 15,14 13.6,10.4" fill="#00a651"/>'),
    "ye": _svg(_r(0, 0, 30, 6.67, "#ce1126"), _r(0, 6.67, 30, 6.67, "#fff"), _r(0, 13.34, 30, 6.66, "#000")),
    "om": _svg(_r(9, 0, 21, 6.67, "#fff"), _r(9, 6.67, 21, 6.67, "#d80012"), _r(9, 13.34, 21, 6.66, "#009a44"),
               _r(0, 0, 9, 20, "#d80012")),
    "sy": _svg(_r(0, 0, 30, 6.67, "#ce1126"), _r(0, 6.67, 30, 6.67, "#fff"), _r(0, 13.34, 30, 6.66, "#000"),
               '<polygon points="10.5,8.2 11.4,10.8 8.8,9.2 12.2,9.2 9.6,10.8" fill="#007a3d"/>',
               '<polygon points="19.5,8.2 20.4,10.8 17.8,9.2 21.2,9.2 18.6,10.8" fill="#007a3d"/>'),
    "ir": _svg(_r(0, 0, 30, 6.67, "#239f40"), _r(0, 6.67, 30, 6.67, "#fff"), _r(0, 13.34, 30, 6.66, "#da0000"),
               '<circle cx="15" cy="10" r="2.1" fill="none" stroke="#da0000" stroke-width="0.7"/>'),
    "pk": _svg(_r(0, 0, 7.5, 20, "#fff"), _r(7.5, 0, 22.5, 20, "#01411c"),
               '<circle cx="18.5" cy="10" r="4.2" fill="#fff"/><circle cx="20" cy="9.2" r="3.3" fill="#01411c"/>',
               '<polygon points="22.6,6.4 23.4,8.8 21,7.4 24.2,7.4 21.8,8.8" fill="#fff"/>'),
    "cu": _svg("".join(_r(0, i * 4, 30, 4, "#002590" if i % 2 == 0 else "#fff") for i in range(5)),
               '<polygon points="0,0 13,10 0,20" fill="#cf142b"/>',
               '<polygon points="4.6,7.4 5.5,10.2 2.9,8.6 6.3,8.6 3.7,10.2" fill="#fff"/>'),
    "pl": _svg(_r(0, 0, 30, 10, "#fff"), _r(0, 10, 30, 10, "#dc143c")),
    "sg": _svg(_r(0, 0, 30, 10, "#ef3340"), _r(0, 10, 30, 10, "#fff"),
               '<circle cx="6.5" cy="5" r="2.6" fill="#fff"/><circle cx="7.6" cy="5" r="2.1" fill="#ef3340"/>'),
    "th": _svg(_r(0, 0, 30, 4, "#a51931"), _r(0, 4, 30, 4, "#f4f5f8"), _r(0, 8, 30, 4, "#2d2a4a"),
               _r(0, 12, 30, 4, "#f4f5f8"), _r(0, 16, 30, 4, "#a51931")),
    "kp": _svg(_r(0, 0, 30, 20, "#ed1c27"),
               '<circle cx="10" cy="10" r="4.6" fill="#fff"/>',
               '<polygon points="10,6.2 11.1,9.2 14.3,9.2 11.7,11.1 12.7,14.2 10,12.3 7.3,14.2 8.3,11.1 5.7,9.2 8.9,9.2" fill="#ed1c27"/>'),
    "ch": _svg(_r(0, 0, 30, 20, "#da291c"), _r(12.2, 4, 5.6, 12, "#fff"), _r(9, 7.2, 12, 5.6, "#fff")),
    "cd": _svg(_r(0, 0, 30, 20, "#007fff"),
               '<polygon points="3.4,2.2 4.3,4.8 1.7,3.2 5.1,3.2 2.5,4.8" fill="#f7d618"/>',
               '<polygon points="-2,20 32,-2 36,2 2,24" fill="#f7d618"/>',
               '<polygon points="0,20 30,-1 33,3 3,24" fill="#ce1021"/>'),
    "au": _svg(_r(0, 0, 30, 20, "#012169"), _r(0, 0, 15, 10, "#012169"),
               _r(0, 4.2, 15, 1.6, "#fff"), _r(6.7, 0, 1.6, 10, "#fff"),
               _r(0, 4.6, 15, 0.8, "#c8102e"), _r(7.1, 0, 0.8, 10, "#c8102e"),
               '<polygon points="22,12.4 22.7,14.6 20.6,13.3 23.4,13.3 21.3,14.6" fill="#fff"/>'),
    "in": _svg(_r(0, 0, 30, 6.67, "#ff9933"), _r(0, 6.67, 30, 6.67, "#fff"), _r(0, 13.34, 30, 6.66, "#138808"),
               '<circle cx="15" cy="10" r="2.2" fill="none" stroke="#000088" stroke-width="0.7"/>'),
    "hu": _svg(_r(0, 0, 30, 6.67, "#ce2939"), _r(0, 6.67, 30, 6.67, "#fff"), _r(0, 13.34, 30, 6.66, "#477050")),
    "it": _svg(_r(0, 0, 10, 20, "#009246"), _r(10, 0, 10, 20, "#fff"), _r(20, 0, 10, 20, "#ce2b37")),
    "mx": _svg(_r(0, 0, 10, 20, "#006847"), _r(10, 0, 10, 20, "#fff"), _r(20, 0, 10, 20, "#ce1126"),
               '<circle cx="15" cy="10" r="2.2" fill="#c4a35a"/>'),
    "co": _svg(_r(0, 0, 30, 10, "#fcd116"), _r(0, 10, 30, 5, "#003893"), _r(0, 15, 30, 5, "#ce1126")),
    "ca": _svg(_r(0, 0, 7.5, 20, "#d80621"), _r(22.5, 0, 7.5, 20, "#d80621"), _r(7.5, 0, 15, 20, "#fff"),
               '<polygon points="15,4.5 16.6,9 21.2,9 17.5,11.8 18.8,16.4 15,13.5 11.2,16.4 12.5,11.8 8.8,9 13.4,9" fill="#d80621"/>'),
    "es": _svg(_r(0, 0, 30, 5, "#aa151b"), _r(0, 5, 30, 10, "#f1bf00"), _r(0, 15, 30, 5, "#aa151b")),
    "ro": _svg(_r(0, 0, 10, 20, "#002b7f"), _r(10, 0, 10, 20, "#fcd116"), _r(20, 0, 10, 20, "#ce1126")),
    "gb": _svg(_r(0, 0, 30, 20, "#012169"),
               '<polygon points="0,0 30,20" stroke="#fff" stroke-width="3.2"/>',
               '<polygon points="30,0 0,20" stroke="#fff" stroke-width="3.2"/>',
               '<polygon points="0,0 30,20" stroke="#c8102e" stroke-width="1.2"/>',
               '<polygon points="30,0 0,20" stroke="#c8102e" stroke-width="1.2"/>',
               _r(0, 8, 30, 4, "#fff"), _r(13, 0, 4, 20, "#fff"),
               _r(0, 8.8, 30, 2.4, "#c8102e"), _r(13.8, 0, 2.4, 20, "#c8102e")),
    "sa": _svg(_r(0, 0, 30, 20, "#006c35"), _r(6, 13.5, 18, 1.6, "#fff"),
               '<polygon points="8,12.6 22,12.6 21.2,14.2 8.8,14.2" fill="#fff"/>'),
    "de": _svg(_r(0, 0, 30, 6.67, "#000"), _r(0, 6.67, 30, 6.67, "#dd0000"), _r(0, 13.34, 30, 6.66, "#ffce00")),
    "fr": _svg(_r(0, 0, 10, 20, "#002395"), _r(10, 0, 10, 20, "#fff"), _r(20, 0, 10, 20, "#ed2939")),
}


def blob(r):
    return " ".join([r.get("big") or "", r.get("mid") or "", r.get("sub") or "", r.get("text") or ""])


def has(s, *kws):
    return any(k in s for k in kws)


# 兜底截斷用的議題優先序：專項衝突 > 硬新聞 > 軟性收容。
T_PRIORITY = ["烏俄", "美伊", "地緣衝突", "天災天氣", "政治", "社會",
              "財經", "科技醫藥", "體育", "娛樂藝文", "話題"]


def tag_tc(r):
    """依 TC-字典.md 掛標。機動 TAG 不開。"""
    s = blob(r)
    big = r.get("big") or ""
    T, C = set(), set()

    # 烏俄／美伊：字典改為「所有與這場衝突有關」（含外交、經濟外溢），不是只收戰場
    ua_related = (
        big == "烏俄"
        or has(s, "基輔")
        or has(s, "烏克蘭")
        or (has(s, "俄羅斯") and has(s, "軍援", "停火", "戰場", "燃油", "油荒", "間諜", "遇襲"))
    )
    if ua_related and not (has(s, "白俄羅斯") and not has(s, "烏克蘭", "基輔")):
        T.add("烏俄")

    if big == "美伊" or has(s, "美伊") or (
        has(s, "伊朗") and has(s, "制裁", "核", "空襲", "衝突", "判刑")
    ):
        T.add("美伊")

    other_conflict = has(s, "加薩", "屯墾", "油輪遭劫", "戰時地道", "希伯崙", "以巴", "印巴", "義肢兒童")
    if (big == "中東" and has(s, "空襲", "屯墾", "遭劫", "戰時", "縱火", "士兵", "加薩")) or other_conflict:
        T.add("地緣衝突")
    if "烏俄" in T and "地緣衝突" in T and not has(s, "烏克蘭", "基輔", "羅馬尼亞"):
        T.discard("烏俄")

    if big == "天氣" or has(s, "風暴", "龍捲", "颶風", "淹水", "乾旱", "熱浪", "野火",
                            "水龍捲", "暴雨", "震後", "地震", "森林大火"):
        T.add("天災天氣")

    # 醫藥健康已併入科技醫藥（2026-08-25 使用者裁示）
    if (big == "科技" or has(s, "機器人", "科學",
                             "伊波拉", "眼藥水", "公衛", "醫研", "疫情")):
        T.add("科技醫藥")

    if big == "體育" or has(s, "足球", "網球", "羽球", "WNBA", "MLB", "拳擊",
                            "登山車", "美式足球", "西甲", "美網", "電競"):
        T.add("體育")

    if big == "娛樂" or has(s, "蠟像", "好萊塢", "寶萊塢", "電玩", "票房", "紀錄片", "聲光秀"):
        T.add("娛樂藝文")

    if big in ("財經", "關稅") or has(s, "財政", "罷工", "掛牌", "公債", "油價",
                                     "用電", "貿易", "預算", "自貿", "工會"):
        T.add("財經")

    hard_politics = (
        big in ("政治", "大陸") or
        has(s, "外交", "記者會", "命名爭議", "市長", "北約", "法務大臣", "大使",
            "制裁", "戰略對話", "國防合作", "議會", "六四", "天安門", "維園",
            "升旗", "航艦部署", "暗殺")
    )
    # 烏俄／美伊專項已收的衝突相關，不再另掛政治（無關內政才走政治）
    if hard_politics and "烏俄" not in T and "美伊" not in T:
        T.add("政治")

    if (big == "社會" or has(s, "治安", "命案", "起訴", "炸彈", "假酒", "移民",
                            "刺傷", "竊案", "失蹤", "大火", "911", "九一一")
            or big == "美國" and has(s, "治安", "命案", "起訴", "炸彈", "刺傷",
                                     "竊案", "失蹤", "Flock", "禁令", "審判")):
        T.add("社會")
    if big == "美國" and not T:
        T.add("社會")

    if big == "話題" or has(s, "趣聞", "貓咪", "熊貓", "企鵝", "人瑞", "小狗", "小豬",
                            "泳池派對", "歷史上的今天", "敬老"):
        T.add("話題")
    if has(s, "義肢兒童"):
        T.add("話題")

    # 硬新聞不准只掛話題
    if T == {"話題"} and big not in ("話題", "娛樂"):
        T.add("政治" if big in ("大陸", "政治", "美伊") else "社會")
    if not T:
        T.add("話題" if big == "話題" else "社會")

    # —— C：專項優先，區域桶不吞專項 ——
    if has(s, "臺灣", "台灣"):
        C.add("臺灣")
    if big == "大陸" or has(s, "中國", "香港", "北京", "天安門", "六四", "南海",
                            "少數民族", "機器人大會"):
        C.add("中國大陸")
    if (big == "美國" or has(s, "美國", "川普", "夏威夷", "紐約", "德州", "西雅圖",
                             "奧馬哈", "甘迺迪", "FDA", "洋基", "WNBA", "美網",
                             "辛辛那提", "克蘭西", "圖帕克", "Flock", "好萊塢")):
        C.add("美國")
    if has(s, "加拿大"):
        C.add("加拿大")
    if has(s, "日本"):
        C.add("日本")
    if has(s, "北韓", "平壤"):
        C.add("北韓")
    if has(s, "南韓", "三星", "現代") or ("韓國" in s and "北韓" not in s):
        C.add("南韓")
    # 泰、星有專項，但**專項與區域並存**：掛專項時東南亞也要掛
    # （2026-08-25 使用者裁示）。以、伊那組相反，掛專項就不掛中東。
    if has(s, "泰國", "曼谷"):
        C.add("泰國")
        C.add("東南亞")
    if has(s, "新加坡", "馬珠"):
        C.add("新加坡")
        C.add("東南亞")
    if has(s, "印尼", "加里曼丹", "越南", "菲律賓", "緬甸", "馬來"):
        C.add("東南亞")
    if has(s, "巴基斯坦", "印度", "阿富汗", "孟加拉", "古吉拉特"):
        C.add("南亞")
    if has(s, "以色列", "加薩", "希伯崙", "約旦河"):
        C.add("以色列")
    if has(s, "伊朗"):
        C.add("伊朗")
    if has(s, "黎巴嫩", "葉門", "阿曼", "敘利亞", "真主黨", "荷莫茲", "沙國", "沙聯", "卡達"):
        C.add("中東")
    if has(s, "基輔", "烏克蘭") and "白俄羅斯" not in s.replace("烏克蘭", ""):
        C.add("烏克蘭")
    if ("俄羅斯" in s and "白俄羅斯" not in s) or has(s, "俄澳"):
        C.add("俄羅斯")
    if has(s, "白俄羅斯"):
        C.add("歐洲")
    if has(s, "義大利", "匈牙利", "西西里", "波蘭", "羅馬尼亞", "西班牙", "北約",
            "歐盟", "多瑙河", "柏林", "巴黎", "瑞士", "英國", "王室"):
        C.add("歐洲")
    if has(s, "剛果", "伊波拉"):
        C.add("非洲")
    # 墨西哥沒有專項，收在中南美（2026-08-25 使用者裁示）
    if has(s, "古巴", "哥倫比亞", "墨西哥"):
        C.add("中南美")
    if has(s, "澳洲", "紐西蘭", "企鵝"):
        C.add("紐澳")
    # 「其他地區」已併入國際（2026-08-25 使用者裁示）
    if has(s, "太平洋島", "斐濟", "帛琉", "關島"):
        C.add("國際")
    if has(s, "APEC", "WHO", "國際油價", "歷史上的今天", "全球最長壽", "電競世界盃"):
        C.add("國際")
    if big == "體育" and not C:
        C.add("國際")
    if not C:
        C.add("國際")

    # heur 兜底同樣吃 T_MAX=3（2026-08-25）：顯示 4 個 T 會跟新規則當面打臉。
    # ⚠️ 這裡**可以**截斷——沒有 agent 在判，截的是關鍵詞湊出來的結果；
    #    但要按議題優先序截、不能按字母序（sorted 會讓「話題」贏過「政治」）。
    if len(T) > 3:
        T = set(sorted(T, key=lambda x: T_PRIORITY.index(x)
                       if x in T_PRIORITY else len(T_PRIORITY))[:3])

    flags = []
    seen = set()
    for kw, iso in FLAG_KW:
        if kw in s and iso not in seen:
            flags.append(iso)
            seen.add(iso)
    return sorted(T), sorted(C), flags


def slim_text(t):
    t = (t or "").strip()
    t = re.sub(r"^\s*[△▲■◆●🔴🟡⭐🟤]\s*", "", t)
    lines = t.split("\n")
    head = lines[0] if lines else ""
    if len(head) > 220:
        head = head[:220] + "…"
    return head


def header_bits(st, mmdd=None):
    """檔頭沿用生產 build_header 的文字，只挑「掃帶窗口」「建檔時稿」兩行。"""
    mmdd = mmdd or MMDD
    win = R.window_from_state(st, mmdd) or st.get("window_local", "")
    lines = H.build_header(st, mmdd, win)
    window_line = lines[1] if len(lines) > 1 else ""
    stats_line = lines[2] if len(lines) > 2 else ""
    stats_line = stats_line.split("；隔夜續掃")[0]
    return window_line, stats_line


def main():
    st = json.load(open(STATE, encoding="utf-8-sig"))
    window_line, stats_line = header_bits(st)
    rows = H.collect(st, MMDD)
    out = []
    for r in rows:
        if r.get("kind") == "empty":
            continue
        T, C, flags = tag_tc(r)
        out.append({
            "id": r.get("id") or "",
            "big": r.get("big") or "",
            "mid": r.get("mid") or "",
            "sub": r.get("sub") or "",
            "src": r.get("src") or "",
            "kind": r.get("kind") or "",
            "mark": r.get("mark") or "",
            "alert": r.get("alert") or "",
            "hilite": r.get("hilite") or "",
            "text": r.get("text") or "",
            "preview": slim_text(r.get("text") or ""),
            "q": (r.get("q") or "")[:400],
            "T": T,
            "C": C,
            "flags": flags,
        })
    html_path = os.path.join(HERE, "_template.html")
    tpl = open(html_path, encoding="utf-8").read()
    html = tpl.replace("__DATA__", json.dumps(out, ensure_ascii=False))
    html = html.replace("__T__", json.dumps(T_FIXED, ensure_ascii=False))
    html = html.replace("__C__", json.dumps(C_FIXED, ensure_ascii=False))
    html = html.replace("__C_FALLBACK__", json.dumps(C_FALLBACK, ensure_ascii=False))
    html = html.replace("__FLAGS__", json.dumps(FLAGS, ensure_ascii=False))
    html = html.replace("__WINDOW__", window_line)
    html = html.replace("__STATS__", stats_line)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("OK", OUT, "bytes", os.path.getsize(OUT), "rows", len(out))


if __name__ == "__main__":
    main()
