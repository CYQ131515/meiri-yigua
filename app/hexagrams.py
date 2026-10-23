# -*- coding: utf-8 -*-
"""六十四卦 · 梅花易数时间起卦。

只负责"算卦"，不负责吉凶叙述。卦名、卦意与关键字为整理后的通行说法，
用于界面展示与本地兜底断语；卦爻符号按《周易》通行本（王弼本）卦序排布。

起卦法（梅花易数·年月日时起卦）：
    上卦 = (年支数 + 农历月 + 农历日) % 8，余 0 作 8
    下卦 = (年支数 + 农历月 + 农历日 + 时支数) % 8，余 0 作 8
    动爻 = 同一和 % 6，余 0 作 6（自下往上数）
体用：动爻所在之卦为「用」，另一卦为「体」，以体用五行生克断吉凶。
"""
from __future__ import annotations

import datetime as _dt

ZHI = "子丑寅卯辰巳午未申酉戌亥"

# 八经卦：数序 1-8 即梅花易数取卦数
# bits 自下而上：1 为阳爻，0 为阴爻
TRIGRAMS = [
    {"num": 1, "name": "乾", "symbol": "☰", "nature": "天", "element": "金", "attr": "健", "bits": (1, 1, 1)},
    {"num": 2, "name": "兑", "symbol": "☱", "nature": "泽", "element": "金", "attr": "悦", "bits": (1, 1, 0)},
    {"num": 3, "name": "离", "symbol": "☲", "nature": "火", "element": "火", "attr": "丽", "bits": (1, 0, 1)},
    {"num": 4, "name": "震", "symbol": "☳", "nature": "雷", "element": "木", "attr": "动", "bits": (1, 0, 0)},
    {"num": 5, "name": "巽", "symbol": "☴", "nature": "风", "element": "木", "attr": "入", "bits": (0, 1, 1)},
    {"num": 6, "name": "坎", "symbol": "☵", "nature": "水", "element": "水", "attr": "陷", "bits": (0, 1, 0)},
    {"num": 7, "name": "艮", "symbol": "☶", "nature": "山", "element": "土", "attr": "止", "bits": (0, 0, 1)},
    {"num": 8, "name": "坤", "symbol": "☷", "nature": "地", "element": "土", "attr": "顺", "bits": (0, 0, 0)},
]

TRIGRAM_BY_NUM = {t["num"]: t for t in TRIGRAMS}
TRIGRAM_BY_BITS = {t["bits"]: t for t in TRIGRAMS}

# 王弼本卦序：[上卦][下卦] -> 卦序。行列顺序同为 乾兑离震巽坎艮坤。
_KINGWEN_GRID = {
    1: [1, 10, 13, 25, 44, 6, 33, 12],
    2: [43, 58, 49, 17, 28, 47, 31, 45],
    3: [14, 38, 30, 21, 50, 64, 56, 35],
    4: [34, 54, 55, 51, 32, 40, 62, 16],
    5: [9, 61, 37, 42, 57, 59, 53, 20],
    6: [5, 60, 63, 3, 48, 29, 39, 8],
    7: [26, 41, 22, 27, 18, 4, 52, 23],
    8: [11, 19, 36, 24, 46, 7, 15, 2],
}

# 六十四卦：卦序 -> (卦名, 关键字, 卦意)
# 卦名用"上卦+下卦"的通行别名（如"泽火革"），关键字与卦意为通行卦义的白话提炼。
HEXAGRAMS = {
    1: ("乾为天", "刚健", "天行健，君子自强不息"),
    2: ("坤为地", "厚载", "地势坤，厚德以载物"),
    3: ("水雷屯", "始难", "云雷交动，宜守待时"),
    4: ("山水蒙", "启蒙", "山下出泉，启蒙以养正"),
    5: ("水天需", "待时", "云上于天，饮食宴乐以待"),
    6: ("天水讼", "止争", "天与水违，作事宜谋其始"),
    7: ("地水师", "律众", "地中有水，师出以律"),
    8: ("水地比", "亲附", "地上有水，比辅而相亲"),
    9: ("风天小畜", "小蓄", "密云不雨，小有蓄积"),
    10: ("天泽履", "慎行", "上天下泽，履虎尾而慎"),
    11: ("地天泰", "通泰", "天地交而万物通"),
    12: ("天地否", "闭塞", "天地不交，俭德以辟难"),
    13: ("天火同人", "和同", "同人于野，利涉大川"),
    14: ("火天大有", "丰有", "火在天上，顺天而休命"),
    15: ("地山谦", "谦益", "地中有山，裒多而益寡"),
    16: ("雷地豫", "和乐", "雷出地奋，顺动而和乐"),
    17: ("泽雷随", "随时", "泽中有雷，随时而向晦"),
    18: ("山风蛊", "整饬", "山下有风，振民而育德"),
    19: ("地泽临", "临下", "泽上有地，教思于无穷"),
    20: ("风地观", "观仰", "风行地上，观民而设教"),
    21: ("火雷噬嗑", "明法", "雷电合章，明罚而敕法"),
    22: ("山火贲", "文饰", "山下有火，文饰而有节"),
    23: ("山地剥", "剥落", "山附于地，顺时而止之"),
    24: ("地雷复", "复始", "雷在地中，反复其道"),
    25: ("天雷无妄", "循理", "天下雷行，物与无妄"),
    26: ("山天大畜", "蓄德", "天在山中，刚健而笃实"),
    27: ("山雷颐", "养正", "山下有雷，慎言语节饮食"),
    28: ("泽风大过", "过甚", "泽灭木，独立而不惧"),
    29: ("坎为水", "重险", "水洊至，常德行习教事"),
    30: ("离为火", "附丽", "明两作，照于四方"),
    31: ("泽山咸", "感应", "山上有泽，虚己以受人"),
    32: ("雷风恒", "恒久", "雷风相与，立不易其方"),
    33: ("天山遁", "退避", "天下有山，遁世而无闷"),
    34: ("雷天大壮", "壮正", "雷在天上，非礼而弗履"),
    35: ("火地晋", "晋进", "明出地上，昭明其德"),
    36: ("地火明夷", "晦明", "明入地中，用晦而明"),
    37: ("风火家人", "齐家", "风自火出，言有物行有恒"),
    38: ("火泽睽", "乖离", "上火下泽，异而求其同"),
    39: ("水山蹇", "险阻", "山上有水，反身而修德"),
    40: ("雷水解", "解难", "雷雨作，赦过而宥罪"),
    41: ("山泽损", "损余", "山下有泽，惩忿而窒欲"),
    42: ("风雷益", "增益", "风雷相益，见善则迁"),
    43: ("泽天夬", "决断", "泽上于天，施禄以及下"),
    44: ("天风姤", "邂逅", "天下有风，施命诰四方"),
    45: ("泽地萃", "聚集", "泽上于地，除戎器戒不虞"),
    46: ("地风升", "积升", "地中生木，积小以高大"),
    47: ("泽水困", "困守", "泽无水，致命而遂志"),
    48: ("水风井", "养人", "木上有水，劳民而劝相"),
    49: ("泽火革", "变革", "泽中有火，治历而明时"),
    50: ("火风鼎", "鼎新", "木上有火，正位而凝命"),
    51: ("震为雷", "震动", "洊雷震，恐惧而修省"),
    52: ("艮为山", "止止", "兼山艮，思不出其位"),
    53: ("风山渐", "渐进", "山上有木，居贤德善俗"),
    54: ("雷泽归妹", "归待", "泽上有雷，永终而知敝"),
    55: ("雷火丰", "丰盛", "雷电皆至，折狱而致刑"),
    56: ("火山旅", "羁旅", "山上有火，明慎而用刑"),
    57: ("巽为风", "顺入", "随风巽，申命而行事"),
    58: ("兑为泽", "和悦", "丽泽兑，朋友讲习"),
    59: ("风水涣", "涣聚", "风行水上，享帝而立庙"),
    60: ("水泽节", "节制", "泽上有水，制数度议德行"),
    61: ("风泽中孚", "诚信", "泽上有风，议狱而缓死"),
    62: ("雷山小过", "小过", "山上有雷，行过乎恭"),
    63: ("水火既济", "守成", "水在火上，思患而预防"),
    64: ("火水未济", "未济", "火在水上，慎辨物居方"),
}

# 卦符：Unicode 易经六十四卦符号区 U+4DC0..U+4DFF 按王弼本卦序排列
_SYMBOL_BASE = 0x4DC0

_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def shichen_index(dt: _dt.datetime) -> int:
    """时辰序：子=1，丑=2 …… 亥=12（23:00–00:59 为子时）。"""
    return ((dt.hour + 1) // 2) % 12 + 1


def yezhi_number(lunar_year_ganzhi: str) -> int:
    """农历年地支数：子=1 …… 亥=12。"""
    zhi = (lunar_year_ganzhi or "")[-1:]
    return ZHI.index(zhi) + 1 if zhi in ZHI else 1


def _guize(n: int) -> int:
    """余 0 作 8。"""
    return 8 if n % 8 == 0 else n % 8


def _lines_of(upper: int, lower: int) -> tuple:
    up = TRIGRAM_BY_NUM[upper]["bits"]
    lo = TRIGRAM_BY_NUM[lower]["bits"]
    return tuple(lo) + tuple(up)


def _trigram_of_bits(bits: tuple) -> dict:
    return TRIGRAM_BY_BITS[tuple(bits)]


def hexagram_by_lines(lines: tuple) -> dict:
    """由六爻（自下而上）反查卦。"""
    lower = _trigram_of_bits(lines[0:3])["num"]
    upper = _trigram_of_bits(lines[3:6])["num"]
    return _hexagram_payload(upper, lower)


def _hexagram_payload(upper: int, lower: int) -> dict:
    up, lo = TRIGRAM_BY_NUM[upper], TRIGRAM_BY_NUM[lower]
    num = _KINGWEN_GRID[upper][lower - 1]
    name, keyword, meaning = HEXAGRAMS[num]
    return {
        "number": num,
        "name": name,
        "short": up["name"] + lo["name"],
        "symbol": chr(_SYMBOL_BASE + num - 1),
        "upper": {"num": upper, "name": up["name"], "nature": up["nature"], "element": up["element"], "symbol": up["symbol"]},
        "lower": {"num": lower, "name": lo["name"], "nature": lo["nature"], "element": lo["element"], "symbol": lo["symbol"]},
        "keyword": keyword,
        "meaning": meaning,
    }


def _tiyong(ti: dict, yong: dict) -> dict:
    """体用五行生克。ti/yong 为经卦 dict。"""
    a, b = ti["element"], yong["element"]
    if a == b:
        code, word, note = "bihe", "比和", "体用同气，彼此相扶"
    elif _SHENG[a] == b:
        code, word, note = "ti_sheng_yong", "泄气", "体生用，己力外泄，付出多于所得"
    elif _SHENG[b] == a:
        code, word, note = "yong_sheng_ti", "大吉", "用生体，外力来助，事有进益"
    elif _KE[a] == b:
        code, word, note = "ti_ke_yong", "小吉", "体克用，我能制事，费力而可成"
    else:
        code, word, note = "yong_ke_ti", "受制", "用克体，外势压身，宜守不宜攻"
    return {"code": code, "word": word, "note": note,
            "ti": ti["name"], "yong": yong["name"]}


def cast_hexagram(lunar: dict, cast_dt: _dt.datetime) -> dict:
    """梅花易数·年月日时起卦。

    lunar: {"year": int, "month": int, "day": int, "year_ganzhi": "丙午"}
    cast_dt: 起卦时刻（按命主当地钟表时间）
    """
    y = yezhi_number(lunar.get("year_ganzhi", ""))
    m = int(lunar.get("month") or 1)
    d = int(lunar.get("day") or 1)
    h = shichen_index(cast_dt)

    upper = _guize(y + m + d)
    lower = _guize(y + m + d + h)
    moving = (y + m + d + h) % 6 or 6

    base = _hexagram_payload(upper, lower)
    lines = _lines_of(upper, lower)
    changed_lines = list(lines)
    changed_lines[moving - 1] = 1 - changed_lines[moving - 1]
    changed_lines = tuple(changed_lines)
    changed = hexagram_by_lines(changed_lines)

    # 互卦：二三四爻为下卦，三四五爻为上卦
    hu = hexagram_by_lines(tuple(lines[1:4]) + tuple(lines[2:5]))

    upper_is_yong = moving >= 4
    ti_num = lower if upper_is_yong else upper
    yong_num = upper if upper_is_yong else lower
    ti = TRIGRAM_BY_NUM[ti_num]
    yong = TRIGRAM_BY_NUM[yong_num]
    tiyong = _tiyong(ti, yong)

    return {
        **base,
        "method": "梅花易数·年月日时起卦",
        "cast_at": cast_dt.strftime("%Y-%m-%d %H:%M"),
        "inputs": {"年支数": y, "农历月": m, "农历日": d, "时辰数": h,
                   "时辰": ZHI[h - 1] + "时", "上卦数": upper, "下卦数": lower},
        "moving": {
            "line": moving,
            "name": ("初", "二", "三", "四", "五", "上")[moving - 1] + "爻",
            "text": "动爻在%s，%s为用、%s为体" % (
                ("初", "二", "三", "四", "五", "上")[moving - 1] + "爻", yong["name"], ti["name"]),
        },
        "lines": [{"yang": bool(x), "moving": i == moving - 1} for i, x in enumerate(lines)],
        "changed": {
            "number": changed["number"], "name": changed["name"], "symbol": changed["symbol"],
            "lines": [{"yang": bool(x), "moving": False} for x in changed_lines],
        },
        "hu": {"number": hu["number"], "name": hu["name"], "symbol": hu["symbol"]},
        "tiyong": tiyong,
    }


if __name__ == "__main__":
    # 自测：一九九九年三月廿八午时（己卯年 三月廿八 午时）
    lun = {"year": 1999, "month": 3, "day": 28, "year_ganzhi": "己卯"}
    r = cast_hexagram(lun, _dt.datetime(1999, 5, 13, 12, 30))
    print(r["name"], r["symbol"], "动", r["moving"]["name"], "变", r["changed"]["name"],
          "互", r["hu"]["name"], "体用", r["tiyong"])
    # 同年月日，子时
    r2 = cast_hexagram(lun, _dt.datetime(1999, 5, 13, 0, 5))
    print(r2["name"], r2["symbol"], "动", r2["moving"]["name"])
