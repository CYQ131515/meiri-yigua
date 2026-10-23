# -*- coding: utf-8 -*-
"""每日运势报告生成引擎。

用法:
    python3 -m engine.report                 # 生成今天的报告
    python3 -m engine.report --date 2026-10-17
    python3 -m engine.report --tomorrow
    python3 -m engine.report --summary       # 只输出当日摘要到 stdout
    python3 -m engine.report --list          # 列出已生成报告

输出: reports/YYYY-MM-DD_运势报告.md  以及 reports/latest.md (当日摘要版)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import math
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from . import astro as A                                  # noqa: E402
from . import bazi as BZ                                  # noqa: E402
from . import calendar_cn as C                            # noqa: E402
from .constants import (ASPECTS, GAN, HOUSE_THEME, PLANET_SYMBOL,  # noqa: E402
                        SHENG, KE, SIGN_ELEMENT, SIGN_MODE, SIGN_RULER, SIGNS,
                        WUXING, ZHI, ZHI_CANGGAN, ZHI_CHONG, ZHI_SHENGXIAO)

# 相位名 -> 标准角度 (行运相位记录里存的是名称)
_ASPECT_ANGLE = {a[0]: a[1] for a in ASPECTS}

try:
    import almanac as _alm_probe  # noqa: F401
except ImportError:
    try:
        from . import almanac as ALM
    except ImportError:
        ALM = None
else:
    from . import almanac as ALM


# ============================================================ 配置加载
def load_config():
    path = os.path.join(_ROOT, "config", "natal.py")
    spec = importlib.util.spec_from_file_location("natal_config", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ============================================================ 命盘计算
def build_natal(cfg):
    """计算并缓存本命盘 (八字 + 星盘)。"""
    n = cfg.NATAL
    birth = _dt.datetime(n["year"], n["month"], n["day"], n["hour"], n["minute"])
    bz = BZ.compute_bazi(birth, longitude=n["longitude"], tz_offset=n["tz_offset"],
                         gender=n["gender"])
    chart = A.compute_chart(birth, tz_offset=n["tz_offset"],
                            lon_east=n["longitude"], lat_geog=n["latitude"])
    lunar = C.lunar_from_date(_dt.date(n["year"], n["month"], n["day"]))
    return {
        "birth": birth,
        "cfg": n,
        "bazi": bz,
        "chart": chart,
        "lunar": lunar,
    }


# ============================================================ 文本工具
def _bar(v, total=5, full="█", empty="░"):
    k = int(round(max(0.0, min(1.0, v)) * total))
    return full * k + empty * (total - k)


def _score_word(s):
    if s >= 85:
        return "极佳"
    if s >= 72:
        return "顺遂"
    if s >= 60:
        return "平顺偏吉"
    if s >= 48:
        return "平稳"
    if s >= 36:
        return "偏弱, 宜守"
    return "低迷, 宜静"


def _fmt_time(dt):
    return dt.strftime("%H:%M")


# ============================================================ 日课数据
def collect_almanac(date, day_gz):
    """调用黄历引擎; 若不可用则返回最小可用结构。"""
    lunar = C.lunar_from_date(date)
    out = {"lunar": lunar}
    if ALM is not None and hasattr(ALM, "day_almanac"):
        try:
            out["almanac"] = ALM.day_almanac(date, lunar={
                "lunar_year": lunar["lunar_year"], "lunar_month": lunar["lunar_month"],
                "lunar_day": lunar["lunar_day"], "is_leap": lunar["is_leap"],
                "month_name": lunar["month_name"], "day_name": lunar["day_name"],
            }, day_ganzhi=day_gz)
        except Exception as exc:                       # 引擎异常不应中断报告
            out["almanac"] = None
            out["almanac_error"] = "%s: %s" % (type(exc).__name__, exc)
    else:
        out["almanac"] = None
    return out


# ============================================================ 行运计算
def _exact_time_within_day(natal_lon, transit_name, jd_start, target_angle, orb_limit):
    """在当日 [jd_start, jd_start+1) 内找行运行星与本命点最接近目标相位的时刻。

    做法: 先粗扫找 |sep - angle| 的最小值点, 再在该点附近做三分搜索细化。
    若全日最接近值仍超出容许度, 返回 None (表示当日不成精确相位)。
    """
    def f(jd):
        t = A.planet_longitude(transit_name, jd)
        return abs(A.angular_sep(t, natal_lon) - target_angle)

    n = 24
    best_jd, best_v = None, 1e9
    for i in range(n + 1):
        jd = jd_start + i / float(n)
        v = f(jd)
        if v < best_v:
            best_v, best_jd = v, jd
    if best_jd is None or best_v > orb_limit:
        return None
    # 只在"日内内部"的最小点才算精确时刻; 若最接近点落在当日边界,
    # 说明相位在当日之外才精确 (整日维持), 不输出时刻。
    if best_jd <= jd_start + 1e-9 or best_jd >= jd_start + 1.0 - 1e-9:
        return None
    lo = max(jd_start, best_jd - 1.0 / n)
    hi = min(jd_start + 1.0, best_jd + 1.0 / n)
    for _ in range(60):
        m1 = lo + (hi - lo) / 3.0
        m2 = hi - (hi - lo) / 3.0
        if f(m1) <= f(m2):
            hi = m2
        else:
            lo = m1
    jd = (lo + hi) / 2.0
    return jd if f(jd) <= orb_limit else None


def collect_transits(natal_chart, date, tz_offset):
    """当日行运: 行运行星位置、与本命盘的相位。"""
    jd0 = C.jd_from_datetime(_dt.datetime(date.year, date.month, date.day) - _dt.timedelta(hours=tz_offset))
    jd_noon = jd0 + 0.5
    natal = natal_chart["planets"]
    rows = []
    for p in A.PLANETS:
        lon = A.planet_longitude(p, jd_noon)
        rows.append({
            "planet": p, "lon": lon, "text": A.lon_text(lon),
            "sign": A.sign_of(lon), "house": A.house_of(lon, natal_chart["cusps"]),
            "retro": A.is_retrograde(p, jd_noon),
            "speed": A.speed_deg_per_day(p, jd_noon),
        })
    # 相位: 行运行星 对 本命行星/上升/天顶
    targets = dict(natal)
    targets["上升"] = {"lon": natal_chart["asc"]}
    targets["天顶"] = {"lon": natal_chart["mc"]}
    hits = []
    for r in rows:
        for tname, tval in targets.items():
            if tname == r["planet"] and r["planet"] not in ("太阳", "月亮"):
                pass          # 行运本星对本命同星 (如行运木星拱本命木星) 是有效相位, 保留
            sep = A.angular_sep(r["lon"], tval["lon"])
            for aname, ang, orb, nature in A.ASPECTS:
                o = A.ASPECT_ORB.get(ang, orb)
                if r["planet"] in A.LUMINARIES or tname in A.LUMINARIES:
                    o *= 1.25
                d = abs(sep - ang)
                if d <= o:
                    exact_jd = _exact_time_within_day(tval["lon"], r["planet"], jd0, ang, o)
                    # 入相/出相: 比较 12 小时后的容许度
                    later = A.planet_longitude(r["planet"], jd_noon + 0.5)
                    d_later = abs(A.angular_sep(later, tval["lon"]) - ang)
                    trend = "入相" if d_later < d else "出相"
                    hits.append({
                        "transit": r["planet"], "natal": tname, "aspect": aname,
                        "nature": nature, "orb": d, "exact": sep,
                        "exact_time": exact_jd, "trend": trend,
                    })
    hits.sort(key=lambda x: x["orb"])
    phase = A.moon_phase(jd_noon)
    void = A.moon_void_period(jd0, jd0 + 1.0)
    return {"jd0": jd0, "jd_noon": jd_noon, "planets": rows,
            "aspects": hits, "phase": phase, "void": void}


# ============================================================ 分领域解读
# 领域 -> (主导行运行星, 关键本命点位) ；只有"行运行星"落在这组里才算该领域主事件，
# "本命点位"被触发算次要事件。这样避免同一个相位在多个领域被重复计分。
_AREA_DEF = [
    ("情感", {"金星", "月亮", "火星"}, {"金星", "月亮", "上升", "太阳"}, "5宫/7宫"),
    ("事业", {"太阳", "土星", "木星", "火星"}, {"太阳", "天顶", "土星", "木星"}, "10宫/6宫"),
    ("财运", {"木星", "金星", "土星"}, {"木星", "金星", "月亮"}, "2宫/8宫"),
    ("健康", {"火星", "土星", "月亮"}, {"月亮", "上升", "太阳"}, "6宫/1宫"),
    ("人际", {"水星", "金星", "月亮"}, {"金星", "月亮", "水星", "上升"}, "11宫/3宫"),
    ("学业", {"水星", "木星"}, {"水星", "木星", "太阳"}, "9宫/3宫"),
]

# 领域基准分: 不同领域对"中性"的锚点不同 (健康/学业更依赖长期状态)
_AREA_BASE = {"情感": 58.0, "事业": 58.0, "财运": 56.0, "健康": 60.0, "人际": 60.0, "学业": 58.0}


def area_readings(transits, day_rel, almanac_score):
    """按领域给出评分与文字建议。

    计分规则 (可解释):
      基准 58 分 (各领域略有差异);
      + 该领域的"主导行运行星"参与的行运吉相位, 权重 8×(1 - 容许度/容许范围);
      − 同上但为凶相位, 权重 9×...  (凶相位略重);
      + 该领域关键本命点位被吉相触发, 权重 4×...;  凶相 −4.5×...  (次要事件减半);
      + 行运行星落入该领域相关宫位 +2;
      最后与"当日日柱吉凶"和"黄历吉凶分"做加权融合。
    """
    base_all = 55.0
    if day_rel and isinstance(day_rel.get("score"), (int, float)):
        base_all = day_rel["score"]
    if isinstance(almanac_score, (int, float)):
        base_all = 0.6 * base_all + 0.4 * almanac_score

    out = []
    for area, rulers, points, houses in _AREA_DEF:
        score = _AREA_BASE.get(area, 58.0)
        notes = []
        for h in transits["aspects"]:
            ang = h.get("angle") or _ASPECT_ANGLE.get(h.get("aspect"), 6)
            orb_max = A.ASPECT_ORB.get(ang, 6.0)
            strength = max(0.0, 1.0 - h["orb"] / max(orb_max, 1e-6))
            if h["transit"] in rulers:                 # 主事件
                w = (8.0 if h["nature"] == "吉" else 9.0 if h["nature"] == "凶" else 0.0) * strength
                sign = 1.0 if h["nature"] == "吉" else -1.0 if h["nature"] == "凶" else 0.0
            elif h["natal"] in points:                 # 次要事件
                w = (4.0 if h["nature"] == "吉" else 4.5 if h["nature"] == "凶" else 0.0) * strength
                sign = 1.0 if h["nature"] == "吉" else -1.0 if h["nature"] == "凶" else 0.0
            else:
                continue
            if sign == 0.0:
                continue
            score += sign * w
            if h["nature"] == "吉":
                notes.append("行运%s与%s%s（吉，容许度%.1f°）" % (
                    h["transit"], h["natal"], h["aspect"], h["orb"]))
            else:
                notes.append("行运%s与%s%s（需留意，容许度%.1f°）" % (
                    h["transit"], h["natal"], h["aspect"], h["orb"]))
        for r in transits["planets"]:
            if r["planet"] in rulers and r["house"] in (1, 2, 5, 6, 7, 10, 11):
                score += 2.0
        # 融合当日整体气机 (权重 35%), 避免领域分与总分脱节
        score = 0.65 * score + 0.35 * base_all
        score = max(25.0, min(92.0, score))
        # 排序: 取与该领域最相关的 3 条
        notes = notes[:3]
        out.append({"area": area, "score": round(score),
                    "notes": notes, "houses": houses})
    return out


def day_advice(day_rel, almanac, xi):
    """综合宜忌建议。只保留"可执行的黄历事项", 命理提示另归入 notes。"""
    yi, ji = [], []
    if almanac:
        yi += list(almanac.get("yi") or [])[:8]
        ji += list(almanac.get("ji") or [])[:8]
    if day_rel:
        # 命盘侧的加分/扣分项是"说明", 不是黄历事项; 只取其中的具体宜忌词
        for key, bucket in (("highlights", yi), ("cautions", ji)):
            for item in (day_rel.get(key) or []):
                t = str(item)
                # 形如 "喜用神木到位(+6)" / "冲 月支巳(蛇)" 之类归入 notes, 不进宜忌表
                # 命理侧的注释 (含括号加分说明、或"冲 月支巳"这类带空格的描述) 不进宜忌表
                if any(ch in t for ch in "+-()（）：") or " " in t:
                    continue
                if t.startswith(("喜用神", "忌神", "冲", "合", "刑", "害", "空亡", "天乙")):
                    continue
                bucket.append(t)
    # 去重保序
    def uniq(xs):
        seen, out = set(), []
        for x in xs:
            x = str(x).strip()
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out
    return uniq(yi)[:10], uniq(ji)[:10]


def color_and_direction(day_ganzhi, xi):
    """幸运色 / 方位 / 数字。"""
    wx = None
    if xi and xi.get("wuxing_score"):
        favor = xi.get("favor") or []
        if favor:
            wx = favor[0]
    color_map = {"木": "青、绿", "火": "红、橙", "土": "黄、棕", "金": "白、金", "水": "黑、蓝"}
    dir_map = {"木": "正东", "火": "正南", "土": "西南", "金": "正西", "水": "正北"}
    num_map = {"木": [3, 8], "火": [2, 7], "土": [5, 10], "金": [4, 9], "水": [1, 6]}
    if not wx:
        wx = "木"
    return {
        "wuxing": wx,
        "color": color_map.get(wx, "—"),
        "direction": dir_map.get(wx, "—"),
        "numbers": num_map.get(wx, []),
    }


# ============================================================ 报告渲染
def render_report(cfg, natal, date, alm_data, transits, day_rel, areas, yi, ji, luck):
    n = cfg.NATAL
    bz = natal["bazi"]
    ch = natal["chart"]
    lunar = alm_data["lunar"]
    almanac = alm_data.get("almanac")
    L = []
    add = L.append

    add("# %s · 每日运势报告" % date.strftime("%Y年%m月%d日"))
    add("")
    add("> 命主：%s（%s）  ·  生成时间：%s" % (
        n["name"], n["gender"], _dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
    add("")

    # ---------------- 一、当日速览
    add("## 一、当日速览")
    add("")
    add("| 项目 | 内容 |")
    add("|---|---|")
    add("| 公历 | %s 星期%s |" % (date.strftime("%Y-%m-%d"), "一二三四五六日"[date.weekday()]))
    add("| 农历 | %s年 %s%s |" % (lunar["lunar_year"], lunar["month_name"], lunar["day_name"]))
    add("| 干支 | %s年 %s月 %s日 |" % (
        _gz_year(date), _gz_month(date), C.day_ganzhi(date)))
    if almanac:
        add("| 建除 | %s日 |" % (almanac.get("jianchu", {}).get("name") or "—"))
        add("| 值宿 | %s（%s） |" % (
            almanac.get("xiu", {}).get("name") or "—",
            almanac.get("xiu", {}).get("ji_xiong") or "—"))
        add("| 冲煞 | %s |" % (almanac.get("chong", {}).get("text") or "—"))
        add("| 彭祖百忌 | %s；%s |" % (
            almanac.get("pengzu", {}).get("gan") or "—",
            almanac.get("pengzu", {}).get("zhi") or "—"))
    if almanac and almanac.get("score") is not None:
        add("| 黄历吉凶 | %s 分 |" % almanac["score"])
    if almanac and almanac.get("shenfang"):
        sf0 = almanac["shenfang"]
        add("| 吉神方位 | 喜神%s · 财神%s |" % (sf0.get("喜神", "—"), sf0.get("财神", "—")))
    add("| 节气 | %s |" % _near_term_text(date))
    add("| 月亮 | %s（照亮 %.0f%%）%s |" % (
        transits["phase"][1], transits["phase"][2] * 100,
        _void_text(transits["void"], cfg.REPORT["timezone_offset"])))
    add("")
    add("**综合运势：%s %s（%.0f/100）**" % (_bar(luck / 100.0), _score_word(luck), luck))
    add("")

    # ---------------- 二、八字部分
    add("## 二、八字命盘与当日吉凶")
    add("")
    p = bz["pillars"]
    add("**本命四柱**：%s年 %s月 %s日 %s时　（日主：%s%s，%s）" % (
        p["year"]["ganzhi"], p["month"]["ganzhi"], p["day"]["ganzhi"],
        p["hour"]["ganzhi"], bz["day_master"]["gan"], bz["day_master"]["wuxing"],
        bz["day_master"]["yinyang"]))
    add("")
    add("| 四柱 | 天干 | 地支 | 藏干 | 天干十神 |")
    add("|---|---|---|---|---|")
    for key, label in (("year", "年柱"), ("month", "月柱"), ("day", "日柱"), ("hour", "时柱")):
        pl = p[key]
        cg = "、".join(bz["canggan"].get(key, []) or [])
        ss = bz["shishen"]["gan"].get(key, "—")
        add("| %s | %s | %s | %s | %s |" % (label, pl["gan"], pl["zhi"], cg, ss))
    add("")
    ws = bz.get("wuxing_score") or {}
    if ws:
        add("**五行力量**：%s" % "　".join(
            "%s %s %.1f" % (k, _bar(v / max(1e-9, max(ws.values()))), v) for k, v in ws.items()))
        add("")
    st = bz.get("strength") or {}
    xy = bz.get("xiyong") or {}
    add("- 日主强弱：**%s**（评分 %s）" % (st.get("verdict", "—"), st.get("score", "—")))
    add("- 喜用：**%s**　忌神：**%s**（%s）" % (
        "、".join(xy.get("favor") or []) or "—",
        "、".join(xy.get("avoid") or []) or "—",
        xy.get("method", "")))
    add("- 当前大运：**%s**　流年：**%s**" % (_current_dayun(bz, date), _gz_year(date)))
    add("")
    if day_rel:
        add("**当日与命盘的关系**：日柱 %s（十神：%s）" % (
            day_rel.get("day_ganzhi", "—"), day_rel.get("shishen_gan", "—")))
        add("")
        add("- 与命盘互动：%s" % _rel_text(day_rel))
        add("- 当日评分：**%s/100**" % day_rel.get("score", "—"))
        if day_rel.get("highlights"):
            add("- 有利：%s" % "；".join(day_rel["highlights"][:4]))
        if day_rel.get("cautions"):
            add("- 留意：%s" % "；".join(day_rel["cautions"][:4]))
        add("")
    add(_bazi_narrative(bz, day_rel, date))
    add("")

    # ---------------- 三、西方占星
    add("## 三、西方占星")
    add("")
    add("**本命盘**：太阳 %s　月亮 %s　上升 %s　天顶 %s" % (
        ch["planets"]["太阳"]["lon_text"], ch["planets"]["月亮"]["lon_text"],
        ch["asc_text"], ch["mc_text"]))
    add("")
    add("**本命行星落座落宫**")
    add("")
    add("| 行星 | 位置 | 宫位 | 宫位主题 | 状态 |")
    add("|---|---|---|---|---|")
    for pl in A.PLANETS:
        v = ch["planets"][pl]
        add("| %s %s | %s | 第%d宫 | %s | %s |" % (
            PLANET_SYMBOL.get(pl, ""), pl, v["lon_text"], v["house"],
            HOUSE_THEME.get(v["house"], ""), "逆行" if v["retro"] else "顺行"))
    add("")
    add("**本命主要相位**")
    add("")
    add("| 相位 | 容许度 | 性质 |")
    add("|---|---|---|")
    for h in ch["aspects"][:10]:
        add("| %s %s %s | %.2f° | %s |" % (h["a"], h["aspect"], h["b"], h["orb"], h["nature"]))
    add("")
    add("### 今日行运")
    add("")
    add("| 行运行星 | 位置 | 落入本命宫位 | 状态 | 速度 |")
    add("|---|---|---|---|---|")
    for r in transits["planets"]:
        add("| %s %s | %s | 第%d宫 | %s | %+.3f°/日 |" % (
            PLANET_SYMBOL.get(r["planet"], ""), r["planet"], r["text"], r["house"],
            "逆行" if r["retro"] else "顺行", r["speed"]))
    add("")
    add("**今日行运相位（对本命盘）**")
    add("")
    if transits["aspects"]:
        add("| 行运 | 本命 | 相位 | 容许度 | 性质 | 趋势 | 精确时刻 |")
        add("|---|---|---|---|---|---|---|")
        # 只有快速移动的行星才有"当日精确时刻"的意义; 外行星相位通常持续数日
        FAST = ("月亮", "太阳", "水星", "金星", "火星")
        for h in transits["aspects"][:cfg.REPORT["top_transits"]]:
            et = h.get("exact_time")
            if et and h["transit"] in FAST:
                ets = C.datetime_from_jd(et + cfg.REPORT["timezone_offset"] / 24.0).strftime("%H:%M")
            elif et:
                ets = "全天有效"
            else:
                ets = "—"
            add("| %s | %s | %s | %.2f° | %s | %s | %s |" % (
                h["transit"], h["natal"], h["aspect"], h["orb"], h["nature"],
                h.get("trend", "—"), ets))
    else:
        add("_今日无紧密行运相位_")
    add("")
    add(_astro_narrative(transits, ch))
    add("")

    # ---------------- 四、分领域
    add("## 四、分领域运势")
    add("")
    for a in areas:
        add("### %s　%s %.0f/100" % (a["area"], _bar(a["score"] / 100.0), a["score"]))
        add("")
        if a["notes"]:
            for nt in a["notes"]:
                add("- %s" % nt)
        else:
            add("- 今日无显著行运触发，维持常态。")
        add("- %s" % _area_tip(a["area"], a["score"], bz))
        add("")

    # ---------------- 五、宜忌
    add("## 五、今日宜忌")
    add("")
    if almanac:
        add("**黄历宜**：%s" % ("、".join(almanac.get("yi") or []) or "—"))
        add("")
        add("**黄历忌**：%s" % ("、".join(almanac.get("ji") or []) or "—"))
        add("")
    add("**结合你命盘的宜**：%s" % ("、".join(yi) or "—"))
    add("")
    add("**结合你命盘的忌**：%s" % ("、".join(ji) or "—"))
    add("")
    if almanac and almanac.get("yi_detail"):
        add("<details><summary>宜忌判定理由</summary>")
        add("")
        for d in almanac["yi_detail"][:10]:
            add("- 宜 **%s**：%s" % (d.get("item"), d.get("reason", "")))
        for d in (almanac.get("ji_detail") or [])[:10]:
            add("- 忌 **%s**：%s" % (d.get("item"), d.get("reason", "")))
        add("")
        add("</details>")
        add("")

    # ---------------- 六、时辰
    if almanac and almanac.get("hour_ji"):
        add("## 六、十二时辰吉凶")
        add("")
        add("| 时辰 | 干支 | 吉凶 | 宜忌提示 |")
        add("|---|---|---|---|")
        seen = set()
        for h in almanac["hour_ji"]:
            note = h.get("note", "") or ""
            # 引擎在每条说明里重复了同一句推算依据, 这里只保留"值神+宜忌"部分
            short = note.split("。推算：")[0].split("推算：")[0]
            if short in seen:
                short = short.split("，")[0]
            seen.add(short)
            add("| %s | %s | %s | %s |" % (
                h.get("shichen"), h.get("ganzhi"), h.get("ji_xiong"), short))
        add("")
        add("_（时辰吉凶依「日支起青龙」的黄黑道十二神与五鼠遁时干推算，流派细节见规则查证文档。）_")
        add("")

    # ---------------- 七、开运
    cd = color_and_direction(C.day_ganzhi(date), bz.get("xiyong") or {})
    add("## 七、开运提示")
    add("")
    add("| 项目 | 建议 |")
    add("|---|---|")
    add("| 幸运五行 | %s |" % cd["wuxing"])
    add("| 幸运颜色 | %s |" % cd["color"])
    add("| 有利方位 | %s |" % cd["direction"])
    add("| 幸运数字 | %s |" % "、".join(str(x) for x in cd["numbers"]))
    if almanac and almanac.get("shenfang"):
        sf = almanac["shenfang"]
        add("| 喜神方位 | %s |" % sf.get("喜神", "—"))
        add("| 财神方位 | %s |" % sf.get("财神", "—"))
    add("| 黄历吉凶分 | %s |" % (almanac.get("score", "—") if almanac else "—"))
    add("")
    add("---")
    add("")
    add(_disclaimer(bz))
    return "\n".join(L)


def _disclaimer(bz):
    ws = (bz.get("warnings") or [])
    lines = ["> **说明**：本报告由本地程序自动生成，依据传统四柱八字、黄历择日与西方占星三套体系，",
             "> 属传统文化娱乐与自我参照用途，不构成医疗、投资、法律等专业建议。",
             "> 命理推断存在流派差异，请理性看待。"]
    if ws:
        lines.append(">")
        for w in ws[:4]:
            lines.append("> · %s" % w)
    return "\n".join(lines)


def _near_term_text(date):
    """显示当前节气月所属的"节", 以及最近的节气。"""
    try:
        y = date.year
        prev_name = prev_dt = None
        next_name = next_dt = None
        for name in C.JIEQI_NAMES:
            for yy in (y - 1, y, y + 1):
                try:
                    jt = C.solar_term_jd(yy, name)
                except Exception:
                    continue
                d = C.datetime_from_jd(jt + 8.0 / 24.0)
                if d.date() <= date and (prev_dt is None or d > prev_dt):
                    prev_name, prev_dt = name, d
                if d.date() > date and (next_dt is None or d < next_dt):
                    next_name, next_dt = name, d
        parts = []
        if prev_name:
            parts.append("已过 %s(%s)" % (prev_name, prev_dt.strftime("%m-%d %H:%M")))
        if next_name:
            days = (next_dt.date() - date).days
            parts.append("下一节气 %s(%s, %d天后)" % (
                next_name, next_dt.strftime("%m-%d %H:%M"), days))
        return "；".join(parts) or "—"
    except Exception:
        return "—"


def _void_text(void, tz):
    if not void or not void.get("void_start"):
        return ""
    s = C.datetime_from_jd(void["void_start"] + tz / 24.0)
    e = C.datetime_from_jd(void["void_end"] + tz / 24.0)
    if e.date() != s.date():
        day = "次日" if (e.date() - s.date()).days == 1 else e.strftime("%m-%d")
        return "｜月亮空亡 %s–%s%s" % (s.strftime("%H:%M"), day, e.strftime("%H:%M"))
    return "｜月亮空亡 %s–%s" % (s.strftime("%H:%M"), e.strftime("%H:%M"))


def _gz_year(date):
    """以立春换年的年柱。"""
    y = date.year
    lichun = C.jie_datetime(y, "立春")
    if _dt.datetime(date.year, date.month, date.day) < lichun.replace(hour=0, minute=0):
        y -= 1
    return C.ganzhi_from_index((y - 4) % 60)


def _gz_month(date):
    """以节气换月的月柱。

    月建以"节"为界: 立春=寅月, 惊蛰=卯月, 清明=辰月, 立夏=巳月, 芒种=午月,
    小暑=未月, 立秋=申月, 白露=酉月, 寒露=戌月, 立冬=亥月, 大雪=子月, 小寒=丑月。
    注意: 小寒/大寒属公历次年 1 月, 因此必须按"节气月"而非公历年来判定。
    """
    y = date.year
    # 十二月建对应的"节"名 (1=寅月 ... 12=丑月)
    order = [("立春", 1), ("惊蛰", 2), ("清明", 3), ("立夏", 4), ("芒种", 5),
             ("小暑", 6), ("立秋", 7), ("白露", 8), ("寒露", 9), ("立冬", 10),
             ("大雪", 11), ("小寒", 12)]
    lichun = C.jie_datetime(y, "立春")
    if date < lichun.date():
        # 立春前: 属上一年, 且必然在丑月 (小寒之后)
        y2, month_no = y - 1, 12
    else:
        y2, month_no = y, 1
        for name, no in order:
            if name == "小寒":
                # 小寒属次年 1 月, 本年内不参与
                continue
            try:
                jt = C.jie_datetime(y, name)
            except Exception:
                continue
            if jt.date() <= date:
                month_no = no
    yg = (y2 - 4) % 60
    return C.ganzhi_from_index(C.month_ganzhi(yg, month_no))


def _current_dayun(bz, on_date=None):
    """返回 on_date 当日所处的大运。"""
    dys = bz.get("dayun") or []
    if not dys:
        return "—"
    now_y = (on_date or _dt.date.today()).year
    for d in dys:
        sy, ey = d.get("start_year"), d.get("end_year")
        if sy is not None and ey is not None and sy <= now_y < ey:
            return "%s（%s，%d–%d）" % (d.get("ganzhi"), d.get("shishen", ""), sy, ey)
    return dys[-1].get("ganzhi", "—")


def _rel_text(day_rel):
    parts = []
    for k, label in (("chong", "冲"), ("he", "合"), ("xing", "刑"), ("hai", "害")):
        v = day_rel.get(k)
        if v:
            parts.append("%s%s" % (label, v))
    if day_rel.get("favor_hit"):
        parts.append("喜用神到位：%s" % "、".join(day_rel["favor_hit"]))
    if day_rel.get("avoid_hit"):
        parts.append("忌神出现：%s" % "、".join(day_rel["avoid_hit"]))
    return "；".join(parts) if parts else "无明显冲合"


def _bazi_narrative(bz, day_rel, date):
    dm = bz["day_master"]
    xy = bz.get("xiyong") or {}
    favor = "、".join(xy.get("favor") or [])
    st = (bz.get("strength") or {}).get("verdict", "中和")
    out = ["**命理小结**：日主%s%s，八字%s；取用%s。" % (
        dm["gan"], dm["wuxing"], st, favor or "—")]
    if day_rel:
        sc = day_rel.get("score")
        if isinstance(sc, (int, float)):
            if sc >= 68:
                out.append("今日日柱与命局相生得助，气机顺畅，适合推进需要主动性的安排。")
            elif sc >= 50:
                out.append("今日日柱与命局平顺，宜按既定节奏行事，不必强求突破。")
            else:
                out.append("今日日柱与命局略有冲克，宜守成、少变动，重要决策可延后。")
    return "\n\n".join(out)


def _astro_narrative(transits, natal_chart):
    out = []
    ph, pname, frac = transits["phase"]
    out.append("**月相**：今日为%s（照亮 %.0f%%）——%s" % (
        pname, frac * 100, {
            "新月": "适合开启新计划、立定意图。",
            "娥眉月": "适合推进已启动的事，积蓄力量。",
            "上弦月": "适合行动、做决定、处理阻力。",
            "盈凸月": "适合完善细节、调整方向。",
            "满月": "情绪与结果同时显现，适合收尾与感恩，避免情绪化决策。",
            "亏凸月": "适合分享、复盘、对外沟通。",
            "下弦月": "适合清理、放下、结束不必要的事。",
            "残月": "适合休息、内省、为下一轮做准备。",
        }.get(pname, "")))
    moon_sign = A.sign_of(A.planet_longitude("月亮", transits["jd_noon"]))
    out.append("**月亮落%s**：%s。" % (moon_sign, {
        "白羊座": "情绪直接、行动力强，注意急躁",
        "金牛座": "情绪稳定，重视实际与舒适",
        "双子座": "思绪活跃，宜沟通但易分心",
        "巨蟹座": "情绪敏感，宜陪伴家人与自我照顾",
        "狮子座": "渴望被看见，适合表达与创作",
        "处女座": "注重细节，适合整理与修正",
        "天秤座": "重视关系和谐，宜协商",
        "天蝎座": "情绪深刻，适合专注与洞察",
        "射手座": "心态开放，宜学习与远行",
        "摩羯座": "务实克制，适合处理正事",
        "水瓶座": "理性抽离，宜社交与创新",
        "双鱼座": "感受力强，宜艺术与休息",
    }.get(moon_sign, "")))
    strong = [h for h in transits["aspects"] if h["orb"] <= 2.0][:4]
    if strong:
        out.append("**今日最强行运**：")
        for h in strong:
            out.append("- 行运%s %s 本命%s（容许度 %.2f°）" % (
                h["transit"], h["aspect"], h["natal"], h["orb"]))
    return "\n\n".join(out)


def _area_tip(area, score, bz):
    tips = {
        "情感": {True: "宜主动表达心意、安排相处时间。", False: "宜多倾听少评判，避免在情绪高点讨论敏感话题。"},
        "事业": {True: "适合推进关键事项、向上沟通、争取资源。", False: "宜稳守既有进度，避免签署重大文件或正面冲突。"},
        "财运": {True: "适合规划理财、追回应收、理性消费。", False: "避免冲动消费与高风险投入，宜记账与守成。"},
        "健康": {True: "精力较足，适合运动与规律作息。", False: "注意休息与肠胃/颈肩，避免熬夜与过度消耗。"},
        "人际": {True: "适合社交、联络朋友、拓展合作。", False: "少参与是非讨论，重要沟通留到状态好时再说。"},
        "学业": {True: "专注力好，适合攻克难点、深度学习。", False: "宜复习巩固而非强行学新，拆分任务降低压力。"},
    }
    return tips.get(area, {True: "", False: ""})[score >= 62]


# ============================================================ 摘要
def render_summary(cfg, natal, date, alm_data, transits, day_rel, areas, yi, ji, luck):
    lunar = alm_data["lunar"]
    almanac = alm_data.get("almanac") or {}
    bz = natal["bazi"]
    cd = color_and_direction(C.day_ganzhi(date), bz.get("xiyong") or {})
    L = []
    add = L.append
    add("## %s 今日运势摘要" % date.strftime("%Y-%m-%d"))
    add("")
    add("农历 %s年%s%s ｜ %s日 ｜ %s %s" % (
        lunar["lunar_year"], lunar["month_name"], lunar["day_name"],
        C.day_ganzhi(date), almanac.get("jianchu", {}).get("name", "—") + "日",
        transits["phase"][1]))
    add("")
    add("**综合运势：%s %s（%.0f/100）**" % (_bar(luck / 100.0), _score_word(luck), luck))
    add("")
    add("| 领域 | 运势 |")
    add("|---|---|")
    for a in areas:
        add("| %s | %s %d |" % (a["area"], _bar(a["score"] / 100.0, 5), a["score"]))
    add("")
    add("**宜**：%s" % ("、".join(yi[:8]) or "—"))
    add("")
    add("**忌**：%s" % ("、".join(ji[:8]) or "—"))
    add("")
    add("**开运**：幸运色 %s ｜ 方位 %s ｜ 数字 %s" % (
        cd["color"], cd["direction"], "、".join(str(x) for x in cd["numbers"])))
    add("")
    add("**一句话**：%s" % _one_liner(luck, day_rel, areas))
    add("")
    add("_完整报告见 reports/%s_运势报告.md_" % date.strftime("%Y-%m-%d"))
    return "\n".join(L)


def _one_liner(luck, day_rel, areas):
    weakest = min(areas, key=lambda a: a["score"]) if areas else None
    strongest = max(areas, key=lambda a: a["score"]) if areas else None
    if luck >= 72:
        head = "整体气机顺畅，可主动出击"
    elif luck >= 55:
        head = "整体平稳，按计划推进即可"
    else:
        head = "整体偏弱，宜守不宜攻"
    tail = ""
    if strongest and weakest and strongest["area"] != weakest["area"]:
        tail = "；%s较顺，%s需留意" % (strongest["area"], weakest["area"])
    return head + tail + "。"


# ============================================================ 主流程
def generate(date=None, cfg=None, quiet=False, output_dir=None, write_latest=True):
    """生成某日报告。

    output_dir: 覆盖输出目录 (自检/预览时可指向临时目录, 避免污染 reports/)
    write_latest: 是否更新 latest.md / latest.json (预览时设 False)
    """
    cfg = cfg or load_config()
    if date is None:
        today = _dt.datetime.now(_tz(cfg.REPORT["timezone_offset"])).date()
        date = today + _dt.timedelta(days=1 if cfg.REPORT["target_day"] == "tomorrow" else 0)
    natal = build_natal(cfg)
    day_gz = C.day_ganzhi(date)
    alm_data = collect_almanac(date, day_gz)
    transits = collect_transits(natal["chart"], date, cfg.REPORT["timezone_offset"])
    try:
        day_rel = BZ.day_relation(natal["bazi"], date)
    except Exception as exc:
        day_rel = {"error": "%s: %s" % (type(exc).__name__, exc)}
    alm_score = (alm_data.get("almanac") or {}).get("score")
    areas = area_readings(transits, day_rel, alm_score)
    yi, ji = day_advice(day_rel, alm_data.get("almanac"), natal["bazi"].get("xiyong") or {})
    luck = _luck_score(day_rel, alm_score, areas)

    out_dir = output_dir or os.path.join(_ROOT, cfg.REPORT["output_dir"])
    os.makedirs(out_dir, exist_ok=True)
    full = render_report(cfg, natal, date, alm_data, transits, day_rel, areas, yi, ji, luck)
    summary = render_summary(cfg, natal, date, alm_data, transits, day_rel, areas, yi, ji, luck)
    fname = "%s_运势报告.md" % date.strftime("%Y-%m-%d")
    fpath = os.path.join(out_dir, fname)
    with open(fpath, "w", encoding="utf-8") as fh:
        fh.write(full)
    if write_latest:
        latest = os.path.join(out_dir, "latest.md")
        with open(latest, "w", encoding="utf-8") as fh:
            fh.write("# 每日运势（最新）\n\n" + summary +
                     "\n\n---\n\n" + _disclaimer(natal["bazi"]) + "\n")
    # 结构化数据, 便于其他程序读取
    if write_latest:
        with open(os.path.join(out_dir, "latest.json"), "w", encoding="utf-8") as fh:
            json.dump({
            "date": date.isoformat(),
            "luck": luck,
            "day_ganzhi": day_gz,
            "yi": yi, "ji": ji,
            "areas": areas,
            "almanac_score": alm_score,
            "moon_phase": transits["phase"][1],
        }, fh, ensure_ascii=False, indent=2)
    if not quiet:
        print("已生成: %s" % fpath)
    return {"path": fpath, "summary": summary, "luck": luck, "date": date}


def _tz(offset):
    return _dt.timezone(_dt.timedelta(hours=offset))


def _luck_score(day_rel, alm_score, areas):
    base = 55.0
    if day_rel and isinstance(day_rel.get("score"), (int, float)):
        base = day_rel["score"]
    if isinstance(alm_score, (int, float)):
        base = 0.6 * base + 0.4 * alm_score
    if areas:
        base = 0.75 * base + 0.25 * (sum(a["score"] for a in areas) / len(areas))
    return int(round(max(10, min(95, base))))


def notify(title, message):
    """macOS 系统通知 (失败不报错)。"""
    try:
        script = 'display notification %s with title %s' % (
            json.dumps(message, ensure_ascii=False), json.dumps(title, ensure_ascii=False))
        subprocess.run(["/usr/bin/osascript", "-e", script], check=False,
                       timeout=10, capture_output=True)
        return True
    except Exception:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="每日运势报告生成器")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD")
    ap.add_argument("--tomorrow", action="store_true", help="生成明天的报告")
    ap.add_argument("--summary", action="store_true", help="只输出摘要")
    ap.add_argument("--notify", action="store_true", help="生成后发系统通知")
    ap.add_argument("--list", action="store_true", help="列出已生成报告")
    args = ap.parse_args(argv)

    cfg = load_config()
    if args.list:
        out_dir = os.path.join(_ROOT, cfg.REPORT["output_dir"])
        for f in sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []:
            if f.endswith("_运势报告.md"):
                print(os.path.join(out_dir, f))
        return 0

    date = None
    if args.date:
        date = _dt.date.fromisoformat(args.date)
    elif args.tomorrow:
        date = _dt.datetime.now(_tz(cfg.REPORT["timezone_offset"])).date() + _dt.timedelta(days=1)

    res = generate(date=date, cfg=cfg)
    if args.summary:
        print(res["summary"])
    if args.notify or cfg.REPORT.get("notify"):
        notify("今日运势已生成 · %s" % res["date"].strftime("%m月%d日"),
               "综合运势 %d/100，点击查看 reports 目录" % res["luck"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
