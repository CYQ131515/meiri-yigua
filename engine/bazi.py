# -*- coding: utf-8 -*-
"""八字(四柱)排盘引擎 —— 子平法, 纯标准库实现。

======================= 算法依据与流派选择 (集中声明) =======================

1. 日柱: 儒略日数(JDN)推算法。
   - JDN 用 Fliegel–Van Flandern 整数公式(公历日期 -> 当日中午的儒略日数)。
   - 干支序号 = (JDN + 49) % 60 (甲子 = 0), 等价于 (JDN - 2433191) % 60。
   - 锚点核对: 1949-10-01 JDN=2433191 -> 甲子日;
              2000-01-01 JDN=2451545 -> 戊午日;
              1999-05-13 JDN=2451312 -> 乙丑日 (本模块 __main__ 自检断言)。
   - 口径说明(重要): 有的资料把 1999-05-13 的儒略日记作 2451310.5, 那是"儒略日 JD"
     的另一口径: JD 2451310.5 = 1999-05-12 00:00 UT, 1999-05-13 00:00 UT = JD 2451311.5,
     1999-05-13 中午 = JDN 2451312。本模块统一使用"日期 -> JDN 整数"公式,
     两者相差 1 天但与"1999-05-13 = 乙丑日"的结论一致。

2. 年柱: 以"立春"为界换年(不是正月初一)。
3. 月柱: 以十二"节"(立春/惊蛰/清明/…/小寒)为界换月; 月干用五虎遁(年干推寅月干)。
4. 时柱: 用真太阳时定时辰; 时干用五鼠遁(日干推子时干)。
   - 晚子时(23:00–24:00)规则: 本模块默认 LATE_ZI_ROLLS_DAY = True,
     即采用"晚子时算次日"(子初换日): 日柱进位到次日, 时柱为次日子时。
     另一流派"晚子时不换日"(日柱仍用当日, 时干用当日日干, 又称夜子时),
     把 LATE_ZI_ROLLS_DAY 置为 False 即可切换。此分歧会写入 warnings。存疑/流派分歧。
5. 真太阳时 = 钟表时间 + (经度 - 15×tz_offset) × 4 分钟 + 均时差。
   - 经度差: 每度 4 分钟, 以时区中央经线为基准(UTC+8 -> 120°E)。
   - 均时差(视太阳时 - 平太阳时): NOAA 近似式(见 _equation_of_time_minutes),
     与权威均时差表吻合到 ±0.3 分钟内, 足够定时辰。
6. 年柱/月柱的节气边界比较: 用"钟表时间(平太阳时) vs 节气时刻"直接比较。
   理由: 节气是一个客观的天文时刻(以标准时公布), 不应叠加经度差/均时差;
   真太阳时只用于"定时辰"和"定日界"。此为流派选择, 另一派主张全部用真太阳时比较。
7. 五行力量评分权重表(本实现自定, 明确列出数值, 不声称引自古籍):
   见 W_GAN / W_ZHI / CANGGAN_RATIO, 合计 105 分。日干本身不计分(避免自我加权)。
8. 旺衰: "得令 / 得地 / 得势"三因子加权 45/30/25 = 100 分, 见 S_* 常量与 _strength()。
9. 喜用神: 扶抑法为主(身弱扶、身强抑), 辅以调候(月令寒暖燥湿), 见 _xiyong()。
   调候采用"按季节寒暖燥湿"的简化取法(非《穷通宝鉴》逐日干细表), 属存疑处。
10. 大运: 阳年(年干阳)男 / 阴年女 顺排; 阴年男 / 阳年女 逆排。
    起运 = 出生到下一个(顺)/上一个(逆)"节"的天数 ÷ 3;
    换算: 3 天 = 1 年, 1 天 = 4 个月, 1 时辰 = 10 天 (等价于 1 实际天 = 120 命理天,
    1 年 = 360 命理天), 折算到年/月/日。每步 10 年, 输出前 8 步。
11. 纳音: 完整六十甲子纳音表(60 条, 校验两两成对共 30 个名称)。
12. 旬空: 六甲旬空表(甲子旬空戌亥 … 甲寅旬空子丑)。
13. 神煞: 天乙贵人、桃花(咸池)、驿马、华盖、将星、羊刃、文昌、禄神、空亡、
    孤辰寡宿、红艳煞, 另附天德贵人、月德贵人。流派有分歧者均已标注"存疑"。
14. 节气数据来源优先级: 调用方传入的 calendar 对象 > 同目录 engine.calendar_cn >
    本模块内置低精度太阳黄经算法(近似值, 会写入 warnings)。
    calendar 需提供 jieqi_datetime(year, name) 与/或 jieqi_between(y, m);
    实际已兼容 engine.calendar_cn 的命名: jie_datetime(year, name) -> 北京时间 datetime,
    solar_term_jd(year, name) -> UT 儒略日。外部来源会做合理性校验(与常年日期相差 > 5 天即弃用),
    均时差也会与内置 NOAA 近似式交叉校验(容差 1 分钟), 避免把明显有误的值带进时辰。

存疑/流派分歧清单(不编造权威来源, 仅标注):
  (a) 晚子时换日规则 (见 4);
  (b) 节气比较是否用真太阳时 (见 6);
  (c) 羊刃: 阳干取"禄前一位"(甲卯/丙戊午/庚酉/壬子)无争议; 阴干有"乙寅/丁己巳/辛申/癸亥"
      与"乙辰/丁己未/辛戌/癸丑"两说, 本模块取后者(顺行禄前), 已标注存疑;
  (d) 天乙贵人: "甲戊庚牛羊, 六辛逢马虎"与"甲戊并牛羊, 庚辛逢虎马"两版本,
      区别在庚、辛; 本模块取前者(庚->丑未, 辛->午寅), 已标注存疑;
  (e) 红艳煞: 歌诀"甲乙午申"有歧义(甲午乙申 或 甲午乙午), 本模块取"甲午、乙申";
  (f) 孤辰寡宿以年支起(另有以日支起);
  (g) 本模块全部量化权重(五行分、旺衰分、日运分)均为本实现自定义, 可复核、可调整,
      不代表任何古籍原数。
"""

from __future__ import annotations

import math
from datetime import date as Date, datetime, timedelta, timezone

try:  # 包方式导入: python -m engine.bazi
    from .constants import (
        GAN, ZHI, GAN_WUXING, GAN_YINYANG, ZHI_WUXING, ZHI_YINYANG, ZHI_SHENGXIAO,
        ZHI_CANGGAN, WUXING, SHENG, KE, BEI_SHENG, BEI_KE,
        ZHI_LIUHE, ZHI_SANHE, ZHI_CHONG, ZHI_HAI, ZHI_XING,
        CHANGSHENG_ORDER, CHANGSHENG_START,
        JIEQI_LON, JIE_NAMES, JIE_ZHI, SHICHEN,
    )
except ImportError:  # 脚本方式运行: python engine/bazi.py (sys.path[0] = engine/)
    from constants import (  # type: ignore
        GAN, ZHI, GAN_WUXING, GAN_YINYANG, ZHI_WUXING, ZHI_YINYANG, ZHI_SHENGXIAO,
        ZHI_CANGGAN, WUXING, SHENG, KE, BEI_SHENG, BEI_KE,
        ZHI_LIUHE, ZHI_SANHE, ZHI_CHONG, ZHI_HAI, ZHI_XING,
        CHANGSHENG_ORDER, CHANGSHENG_START,
        JIEQI_LON, JIE_NAMES, JIE_ZHI, SHICHEN,
    )

__all__ = [
    "compute_bazi", "day_ganzhi", "day_relation", "plan_day",
    "true_solar_time", "nayin", "kongwang", "LATE_ZI_ROLLS_DAY",
]

# ============================================================ 全局开关与权重表

#: 晚子时规则: True = 23:00 起算次日(子初换日, 日柱进位), 与主流万年历一致;
#: False = 晚子时不换日(日柱仍用当日, 时干用当日日干推子时)。存疑/流派分歧。
LATE_ZI_ROLLS_DAY = True

# ---- 五行力量评分权重表 (本实现自定义, 单位: 分) ----------------------------
# 天干: 月干最重(月令透干), 次时干, 次年干; 日干为"我", 不计入(避免自我加权)。
W_GAN = {"year": 8.0, "month": 12.0, "day": 0.0, "hour": 10.0}          # 合计 30
# 地支: 月支(月令)最高, 日支(坐下)次之, 再时支, 年支最轻。
W_ZHI = {"year": 12.0, "month": 30.0, "day": 18.0, "hour": 15.0}        # 合计 75
# 藏干分配比例: 单藏 100%; 两藏 本气70%/中气30%; 三藏 本气60%/中气30%/余气10%。
CANGGAN_RATIO = {1: (1.0,), 2: (0.7, 0.3), 3: (0.6, 0.3, 0.1)}

# ---- 旺衰三因子权重 (合计 100) ---------------------------------------------
S_LING = 45.0   # 得令: 月令藏干中"同党"(比劫+印)所占份额
S_DI = 30.0     # 得地: 日支/时支/年支中"同党"份额
S_SHI = 25.0    # 得势: 年干/月干/时干中"同党"份额
S_DI_SUB = {"day": 0.5, "hour": 0.3, "year": 0.2}      # 得地内部权重
S_SHI_SUB = {"month": 0.4, "year": 0.3, "hour": 0.3}   # 得势内部权重
# 判定阈值: 同党份额恰好 50% 时三因子合计 = 50 分, 故以 50±8 为"中和"带。
STRONG_TH = 58.0
WEAK_TH = 42.0

# ---- 日运(day_relation)评分表 (本实现自定义) -------------------------------
DAY_VS_NATAL = {           # 当日干/支 与 命局四支 的关系扣加分(日支全权重, 其余支半权重)
    "冲": -8.0, "六合": 4.0, "刑": -4.0, "害": -3.0, "半合": 2.0, "自刑": -3.0,
}
DAY_SHENSHA_SCORE = {      # 当日地支/天干触发命局神煞的加减分
    "天乙贵人": 8.0, "天德贵人": 6.0, "月德贵人": 6.0, "禄神": 6.0, "文昌": 4.0,
    "将星": 3.0, "华盖": 2.0, "桃花": 2.0, "驿马": 1.0, "红艳煞": 1.0,
    "羊刃": -5.0, "空亡": -4.0, "孤辰": -3.0, "寡宿": -3.0,
}
#: 日运五行权重: 日干 1.0; 日支本气 1.0, 中气 0.5, 余气 0.25。
DAY_WUXING_ADD = {1: (1.0,), 2: (1.0, 0.5), 3: (1.0, 0.5, 0.25)}
#: 喜/忌神每"单位五行"的加减分, 单元素上限 2.5 单位(即 ±15 分)。
DAY_FAVOR_UNIT = 6.0
DAY_FAVOR_CAP = 2.5

_POS = (("year", "年"), ("month", "月"), ("day", "日"), ("hour", "时"))
_POS_LABEL = {p: lab for p, lab in _POS}

# ============================================================ 一、基础干支与儒略日


def _ganzhi(idx: int) -> str:
    """六十甲子序号(甲子=0) -> 干支字符串。"""
    idx %= 60
    return GAN[idx % 10] + ZHI[idx % 12]


def _ganzhi_index(gz: str) -> int:
    """干支字符串 -> 六十甲子序号(0..59)。

    解同余: idx ≡ 干序 (mod 10), idx ≡ 支序 (mod 12) -> idx = (6*干序 - 5*支序) mod 60。
    """
    gi, zi = GAN.index(gz[0]), ZHI.index(gz[1])
    return (gi * 6 - zi * 5) % 60


def _jdn_from_ymd(y: int, m: int, d: int) -> int:
    """公历 (年,月,日) -> 儒略日数 JDN(整数, Fliegel–Van Flandern 公式)。

    JDN 定义: 该日中午的儒略日数。例: 1999-05-13 -> 2451312; 1949-10-01 -> 2433191。
    """
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def _day_index(d: Date) -> int:
    """公历日期的日柱六十甲子序号。

    依据: 干支纪日 60 日一循环, 锚点 1949-10-01 = 甲子日 (JDN 2433191),
    等价公式 (JDN + 49) % 60。
    """
    return (_jdn_from_ymd(d.year, d.month, d.day) + 49) % 60


def _datetime_to_jd(dt: datetime, tz_offset: float = 8.0) -> float:
    """本地钟表时间(UTC+tz_offset) -> 儒略日 JD(UT 口径)。"""
    y, m = dt.year, dt.month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    jd = (math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1))
          + dt.day + b - 1524.5)
    hours = dt.hour + dt.minute / 60.0 + dt.second / 3600.0 + dt.microsecond / 3.6e9
    return jd + (hours - tz_offset) / 24.0


def _jd_to_datetime(jd: float, tz_offset: float = 8.0) -> datetime:
    """儒略日 JD(UT) -> 本地钟表时间 datetime(UTC+tz_offset), 取整到秒。"""
    jd = jd + 0.5 + tz_offset / 24.0
    z = math.floor(jd)
    f = jd - z
    if z < 2299161:
        a = z
    else:
        alpha = math.floor((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - math.floor(alpha / 4)
    b = a + 1524
    c = math.floor((b - 122.1) / 365.25)
    d = math.floor(365.25 * c)
    e = math.floor((b - d) / 30.6001)
    day = b - d - math.floor(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    day_int = int(math.floor(day))
    frac = day - day_int
    secs = int(round(frac * 86400.0))
    out = datetime(year, month, day_int) + timedelta(seconds=secs)
    return out.replace(microsecond=0)


def _fmt(dt: datetime) -> str:
    """datetime -> 'YYYY-MM-DD HH:MM:SS' 字符串。"""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _add_ymd(dt: datetime, years: int = 0, months: int = 0, days: int = 0) -> datetime:
    """日期加"年/月/日"(日历年月, 日数溢出时按当月天数截断)。"""
    import calendar as _cal
    y = dt.year + years
    m = dt.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    d = min(dt.day, _cal.monthrange(y, m)[1])
    out = dt.replace(year=y, month=m, day=d)
    if days:
        out += timedelta(days=days)
    return out


# ============================================================ 二、真太阳时


def _equation_of_time_minutes(dt: datetime) -> float:
    """均时差 EoT = 视太阳时 - 平太阳时, 单位分钟 (NOAA 近似式)。

    公式: γ = 2π(n - 1 + (h - 12)/24)/365 (n 为年积日, h 为当地钟点时)
          EoT = 229.18 × (0.000075 + 0.001868cosγ - 0.032077sinγ
                          - 0.014615cos2γ - 0.040849sin2γ)   [分钟]
    符号约定: 11 月初约 +16 分钟, 2 月中约 -14 分钟。
    精度: 与权威均时差表(2/11 -14.24, 5/14 +3.65, 7/26 -6.54, 11/3 +16.45 分钟)偏差 < 0.3 分钟。
    """
    n = dt.timetuple().tm_yday
    h = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    gamma = 2.0 * math.pi * (n - 1 + (h - 12.0) / 24.0) / 365.0
    return 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                     - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))


def _eot_from_calendar(calendar, dt_local: datetime, tz_offset: float):
    """取 calendar.equation_of_time(jd_tt) 的均时差, 并与内置近似式交叉校验。

    返回 (eot 或 None, note 或 None)。校验容差 1.0 分钟:
    内置 NOAA 近似式与权威均时差表在 ±0.4 分钟内吻合(例: 2 月中约 -14.2 分,
    11 月初约 +16.4 分), 若外部实现偏差超容差则弃用并提示, 避免把明显错误的
    均时差带进真太阳时(会推移时辰)。
    """
    if calendar is None:
        return None, None
    fn = getattr(calendar, "equation_of_time", None)
    if not callable(fn):
        return None, None
    try:
        jd_ut = _datetime_to_jd(dt_local, tz_offset)
        conv = getattr(calendar, "jd_tt_from_ut", None)
        jd_tt = float(conv(jd_ut)) if callable(conv) else jd_ut
        cand = float(fn(jd_tt))
    except Exception:
        return None, None
    mine = _equation_of_time_minutes(dt_local)
    if abs(cand - mine) > 1.0:
        return None, ("calendar.equation_of_time 返回 %.2f 分钟, 与内置 NOAA 近似式 %.2f 分钟"
                      "相差 %.2f 分钟(超出 1 分钟容差): 已改用内置近似式, 请核对 calendar 的均时差实现。"
                      % (cand, mine, abs(cand - mine)))
    return cand, None


def true_solar_time(dt_local: datetime, longitude: float = 121.47,
                    tz_offset: float = 8.0, calendar=None):
    """真太阳时 = 钟表时间 + 经度差 + 均时差。

    参数:
        dt_local: 出生地钟表时间(该时区标准时)
        longitude: 出生地经度(东经为正)
        tz_offset: 时区偏移(小时), 中央经线 = 15 × tz_offset
        calendar: 可选; 若提供 equation_of_time(jd_tt) 则优先用其均时差(需通过 1 分钟容差校验),
                  否则用内置 NOAA 近似式(与权威均时差表吻合到 ±0.4 分钟内)
    返回:
        (真太阳时 datetime, 明细 dict{longitude_minutes, equation_of_time, total_minutes,
         equation_of_time_source[, equation_of_time_note]})
    """
    lon_min = (longitude - tz_offset * 15.0) * 4.0
    eot, note = _eot_from_calendar(calendar, dt_local, tz_offset)
    eot_src = "calendar.equation_of_time"
    if eot is None:
        eot = _equation_of_time_minutes(dt_local)
        eot_src = "内置 NOAA 近似式"
    detail = {"longitude_minutes": round(lon_min, 3),
              "equation_of_time": round(eot, 3),
              "total_minutes": round(lon_min + eot, 3),
              "equation_of_time_source": eot_src}
    if note:
        detail["equation_of_time_note"] = note
    return dt_local + timedelta(minutes=lon_min + eot), detail


# ============================================================ 三、节气

#: 各节气在新历年的近似日期(月, 日), 用作牛顿迭代的初值(误差 < 2 天即可收敛)
_JIEQI_APPROX = {
    "小寒": (1, 6), "大寒": (1, 20), "立春": (2, 4), "雨水": (2, 19),
    "惊蛰": (3, 6), "春分": (3, 21), "清明": (4, 5), "谷雨": (4, 20),
    "立夏": (5, 6), "小满": (5, 21), "芒种": (6, 6), "夏至": (6, 21),
    "小暑": (7, 7), "大暑": (7, 23), "立秋": (8, 8), "处暑": (8, 23),
    "白露": (9, 8), "秋分": (9, 23), "寒露": (10, 8), "霜降": (10, 23),
    "立冬": (11, 7), "小雪": (11, 22), "大雪": (12, 7), "冬至": (12, 22),
}


def _sun_apparent_longitude(jd: float) -> float:
    """太阳视黄经(度, 0..360), Meeus《天文算法》第 25 章低精度公式(精度约 0.01°)。

    L0 = 280.46646 + 36000.76983T + 0.0003032T²            (几何平黄经)
    M  = 357.52911 + 35999.05029T - 0.0001537T²            (平近点角)
    C  = 中心差(三项正弦级数)
    视黄经 = L0 + C - 0.00569 - 0.00478·sinΩ               (光行差 + 黄经章动)
    """
    t = (jd - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    m = math.radians(357.52911 + 35999.05029 * t - 0.0001537 * t * t)
    c = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * math.sin(m)
         + (0.019993 - 0.000101 * t) * math.sin(2 * m)
         + 0.000289 * math.sin(3 * m))
    omega = math.radians(125.04 - 1934.136 * t)
    return (l0 + c - 0.00569 - 0.00478 * math.sin(omega)) % 360.0


def _solve_solar_longitude(jd_guess: float, target_lon: float) -> float:
    """牛顿法求太阳视黄经等于 target_lon 的时刻(返回 JD)。

    太阳黄经日变化约 0.9856°/日, 迭代格式 jd += (目标 - 当前)/0.9856。
    初值由 _JIEQI_APPROX 给出(误差 < 2 天), 收敛稳定。
    """
    jd = jd_guess
    for _ in range(30):
        diff = (target_lon - _sun_apparent_longitude(jd) + 180.0) % 360.0 - 180.0
        jd += diff / 0.9856473
        if abs(diff) < 1e-7:
            break
    return jd


_FALLBACK_CACHE = {}


def _fallback_jieqi_datetime(year: int, name: str, tz_offset: float = 8.0) -> datetime:
    """内置近似节气算法(无外部数据时使用): 低精度太阳黄经 + 牛顿迭代。

    精度: 公式黄经误差约 0.01°(折合约 ±15 分钟); 实测与 engine.calendar_cn 的
    VSOP87 结果在 1900–2100 抽样中最大偏差 3.1 分钟, 但仍属"近似值"。
    """
    key = (year, name, tz_offset)
    hit = _FALLBACK_CACHE.get(key)
    if hit is not None:
        return hit
    if name not in JIEQI_LON or name not in _JIEQI_APPROX:
        raise KeyError("未知节气: %s" % name)
    mm, dd = _JIEQI_APPROX[name]
    jd_guess = _datetime_to_jd(datetime(year, mm, dd, 12, 0), tz_offset)
    out = _jd_to_datetime(_solve_solar_longitude(jd_guess, float(JIEQI_LON[name])), tz_offset)
    _FALLBACK_CACHE[key] = out
    return out


def _coerce_naive(dt, tz_offset: float) -> datetime:
    """把结果统一成"该时区的 naive datetime"; 带时区的值先换算到 UTC+tz_offset。"""
    if not isinstance(dt, datetime):
        raise TypeError("节气时刻应为 datetime, 得到 %r" % type(dt))
    if dt.tzinfo is not None:
        return dt.astimezone(timezone(timedelta(hours=tz_offset))).replace(tzinfo=None)
    return dt


def _parse_jieqi_payload(payload) -> dict:
    """把 calendar 对象可能返回的各种结构解析成 {节气名: datetime}。

    兼容: [(名, 时刻), ...] / {名: 时刻} / [(名, 时刻, 名, 时刻)] /
          [{"name":…, "datetime":…}, …] / 单个 (名, 时刻)。
    解析不出的部分直接忽略(调用方会回退到其它来源)。
    """
    out = {}
    if payload is None:
        return out

    def _name_of(key) -> str:
        """键 -> 合法节气名(不合法返回空串)。"""
        return key if isinstance(key, str) and key in JIEQI_LON else ""

    def _put(name, value):
        """收录 (节气名, datetime) 组合, 重复者保留先出现的。"""
        if isinstance(name, str) and name in JIEQI_LON and isinstance(value, datetime):
            out.setdefault(name, value)

    if isinstance(payload, dict):
        for k, v in payload.items():
            _put(_name_of(k), v)
            if isinstance(v, dict):
                for kk, vv in v.items():
                    _put(_name_of(kk), vv)
        return out
    if isinstance(payload, (tuple, list)):
        items = list(payload)
        if items and isinstance(items[0], str) and len(items) == 2:
            _put(items[0], items[1])
            return out
        for it in items:
            if isinstance(it, dict):
                nm = it.get("name") or it.get("jieqi") or it.get("term")
                val = it.get("datetime") or it.get("dt") or it.get("time") or it.get("moment")
                if isinstance(val, str):
                    try:
                        val = datetime.fromisoformat(val)
                    except ValueError:
                        val = None
                _put(nm, val)
            elif isinstance(it, (tuple, list)) and len(it) >= 2:
                _put(it[0], it[1])
        return out
    return out


#: 可接受的节气接口名(按优先级): 规范名 -> 常见别名 -> 儒略日接口
_JIEQI_ATTR_NAMES = ("jieqi_datetime", "jie_datetime", "jieqi_dt", "get_jieqi", "jieqi",
                     "jieqi_between", "solar_term_jd", "jieqi_jd", "term_jd")


class JieqiSource:
    """节气数据来源封装: 注入的 calendar > engine.calendar_cn > 内置近似算法。

    只需要两种能力(有其一即可):
      - jieqi_datetime(year, name) / 别名 jie_datetime(year, name): 某公历年某节气的时刻
      - jieqi_between(y, m): 某公历年的某个月内的节气(结构不限, 见 _parse_jieqi_payload)
      - 或只提供儒略日接口 solar_term_jd(year, name): UT 儒略日
    """

    def __init__(self, calendar=None, tz_offset: float = 8.0):
        """确定节气来源(注入 calendar > engine.calendar_cn > 内置近似)并准备缓存。"""
        self.tz_offset = float(tz_offset)
        self.notes = []
        self.calendar = calendar
        self._dt_cache = {}
        self._month_cache = {}
        self._bad_count = 0
        self._bad_reported = False
        self._calendar_disabled = False
        self.used_fallback = False
        no_autoimport = (calendar is False)   # calendar=False 表示显式禁用外部节气源
        if no_autoimport:
            self.calendar = None
        if self.calendar is None and not no_autoimport:
            self.calendar = _try_import_calendar_cn()
        #: engine.calendar_cn 的节气接口固定返回北京时间(UTC+8), tz_offset≠8 时换算一次
        self._assume_bj = bool(self.calendar) and \
            str(getattr(self.calendar, "__name__", "")).endswith("calendar_cn")
        if self.calendar is None:
            self.source_name = "内置近似算法(Meeus 低精度太阳黄经)"
            self.notes.append(
                "未注入 calendar 且 engine.calendar_cn 不可用: 节气使用内置近似算法"
                "(低精度太阳黄经; 实测与 engine.calendar_cn 的 VSOP87 结果在 1900–2100 抽样中"
                "相差 < 4 分钟, 但仍属近似值), 年柱/月柱/大运起运在节气边界附近需复核。")
        else:
            ifaces = [a for a in _JIEQI_ATTR_NAMES if callable(getattr(self.calendar, a, None))]
            self.source_name = "%s(%s)" % (
                getattr(self.calendar, "__name__", None) or type(self.calendar).__name__,
                ",".join(ifaces) or "无可用节气接口")
            if not ifaces:
                self.calendar = None
                self.notes.append(
                    "传入的 calendar 对象既无 jieqi_datetime(year,name)/jieqi_between(y,m) "
                    "也无 jie_datetime/solar_term_jd: 已回退到内置近似节气算法(近似值)。")
            elif self._assume_bj and abs(self.tz_offset - 8.0) > 1e-9:
                self.notes.append(
                    "calendar_cn 的节气时刻为北京时间(UTC+8); 因 tz_offset=%.1f≠8, "
                    "本模块已统一换算到该时区, 请确认这是预期语义。" % self.tz_offset)

    def _to_local(self, dt: datetime) -> datetime:
        """calendar_cn 的 jie_datetime 返回北京时间; tz_offset≠8 时平移到目标时区。"""
        if self._assume_bj and abs(self.tz_offset - 8.0) > 1e-9:
            return dt + timedelta(hours=self.tz_offset - 8.0)
        return dt

    # -------------------------------------------------- 内部取值
    def _from_month_table(self, year: int, name: str):
        """优先从 calendar.jieqi_between(y, m) 取该月节气。"""
        cal = self.calendar
        if cal is None:
            return None
        fn = getattr(cal, "jieqi_between", None)
        if not callable(fn):
            return None
        mm = _JIEQI_APPROX.get(name, (None, None))[0]
        if mm is None:
            return None
        key = (year, mm)
        if key not in self._month_cache:
            try:
                self._month_cache[key] = _parse_jieqi_payload(fn(year, mm))
            except Exception:
                self._month_cache[key] = {}
        val = self._month_cache[key].get(name)
        return _coerce_naive(val, self.tz_offset) if isinstance(val, datetime) else None

    def _from_datetime_api(self, year: int, name: str):
        """再从"时刻型"或"儒略日型"接口取值(兼容若干别名与返回结构)。

        兼容 engine.calendar_cn 的实际接口: jie_datetime(year, name) -> 北京时间 datetime,
        solar_term_jd(year, name) -> UT 儒略日。
        """
        cal = self.calendar
        if cal is None:
            return None
        # (a) 时刻型接口: jieqi_datetime / jie_datetime / ...
        for attr in ("jieqi_datetime", "jie_datetime", "jieqi_dt", "get_jieqi", "jieqi"):
            fn = getattr(cal, attr, None)
            if not callable(fn):
                continue
            for args, kwargs in (((year, name), {}), ((name, year), {}),
                                 ((), {"year": year, "name": name})):
                try:
                    val = fn(*args, **kwargs)
                except Exception:
                    continue
                if isinstance(val, datetime):
                    return self._to_local(_coerce_naive(val, self.tz_offset))
                parsed = _parse_jieqi_payload(val)
                if name in parsed:
                    return self._to_local(_coerce_naive(parsed[name], self.tz_offset))
        # (b) 儒略日型接口: solar_term_jd(year, name) -> UT 儒略日
        for attr in ("solar_term_jd", "jieqi_jd", "term_jd"):
            fn = getattr(cal, attr, None)
            if not callable(fn):
                continue
            for args in ((year, name), (name, year)):
                try:
                    val = fn(*args)
                except Exception:
                    continue
                if isinstance(val, (int, float)):
                    return _jd_to_datetime(float(val), self.tz_offset)
        return None

    def _plausible(self, year: int, name: str, dt):
        """校验外部来源的节气时刻是否可信: 与"常年日期 ±5 天"比较。

        节气在公历中的日期非常稳定(如立春恒在 2/3–2/5), 因此偏差超过 5 天即可判定来源有误。
        这样即使注入的 calendar 实现有缺陷, 本模块也不会输出明显错误的年柱/月柱/大运。
        """
        if dt is None:
            return None
        mm, dd = _JIEQI_APPROX[name]
        ref = datetime(year, mm, dd, 12, 0)
        if abs((dt - ref).total_seconds()) > 5 * 86400:
            self._bad_count += 1
            if not self._bad_reported:
                self._bad_reported = True
                self.notes.append(
                    "calendar 返回的节气时刻明显有误(例: %d 年 %s -> %s, 与常年日期相差>5 天): "
                    "已弃用该来源并回退内置近似算法, 请检查 calendar 的节气实现。"
                    % (year, name, _fmt(dt)))
            if self._bad_count >= 3:
                self._calendar_disabled = True
            return None
        return dt

    def jie_dt(self, year: int, name: str) -> datetime:
        """取某公历年某节气的本地时刻(含缓存, 并对外部来源做合理性校验)。"""
        key = (year, name)
        if key in self._dt_cache:
            return self._dt_cache[key]
        dt = None
        if not self._calendar_disabled:
            try:
                dt = self._from_month_table(year, name) or self._from_datetime_api(year, name)
            except Exception:
                dt = None
            dt = self._plausible(year, name, dt)
        if dt is None:
            if self.calendar is not None:
                self.used_fallback = True
            dt = _fallback_jieqi_datetime(year, name, self.tz_offset)
        self._dt_cache[key] = dt
        return dt

    def boundaries(self, moment: datetime):
        """求 moment 所辖的十二"节"区间: 返回 (上一个节, 下一个节)。

        每个元素为 (节名, 该节时刻)。扫描 moment 前后各一年的十二节,
        排序后取"最后一个 <= moment"与"第一个 > moment"。节时刻按标准时比较(见模块说明 6)。
        """
        cands = []
        for y in (moment.year - 1, moment.year, moment.year + 1):
            for nm in JIE_NAMES:
                try:
                    cands.append((nm, self.jie_dt(y, nm)))
                except Exception:
                    continue
        cands.sort(key=lambda kv: kv[1])
        prev = next_ = None
        for nm, dt in cands:
            if dt <= moment:
                prev = (nm, dt)
            elif next_ is None:
                next_ = (nm, dt)
        if prev is None or next_ is None:
            raise RuntimeError("无法确定节气区间(节气数据不足): moment=%s" % moment)
        return prev, next_


def _try_import_calendar_cn():
    """尝试导入同目录的 engine.calendar_cn(由 Lead 提供, 本模块只读不改)。"""
    try:
        from . import calendar_cn  # type: ignore
        return calendar_cn
    except Exception:
        pass
    try:
        import calendar_cn  # type: ignore  # 脚本方式运行
        return calendar_cn
    except Exception:
        return None


# ============================================================ 四、纳音 / 旬空 / 十神 / 长生

#: 六十甲子纳音表(完整 60 条, 与六十甲子顺序一一对应, 两两成对共 30 个名称)
NAYIN_60 = [
    "海中金", "海中金", "炉中火", "炉中火", "大林木", "大林木", "路旁土", "路旁土",
    "剑锋金", "剑锋金", "山头火", "山头火", "涧下水", "涧下水", "城头土", "城头土",
    "白蜡金", "白蜡金", "杨柳木", "杨柳木", "泉中水", "泉中水", "屋上土", "屋上土",
    "霹雳火", "霹雳火", "松柏木", "松柏木", "长流水", "长流水", "沙中金", "沙中金",
    "山下火", "山下火", "平地木", "平地木", "壁上土", "壁上土", "金箔金", "金箔金",
    "覆灯火", "覆灯火", "天河水", "天河水", "大驿土", "大驿土", "钗钏金", "钗钏金",
    "桑柘木", "桑柘木", "大溪水", "大溪水", "沙中土", "沙中土", "天上火", "天上火",
    "石榴木", "石榴木", "大海水", "大海水",
]

#: 六甲旬空表: 旬首(甲X) -> 该旬空亡的两个地支
XUNKONG = {
    "甲子": ("戌", "亥"), "甲戌": ("申", "酉"), "甲申": ("午", "未"),
    "甲午": ("辰", "巳"), "甲辰": ("寅", "卯"), "甲寅": ("子", "丑"),
}


def nayin(ganzhi: str) -> str:
    """六十甲子纳音(如 己卯 -> 城头土)。依据: 纳音以六十甲子每两位为一组, 共 30 组。"""
    return NAYIN_60[_ganzhi_index(ganzhi)]


def xun_and_kongwang(ganzhi: str):
    """返回 (旬首, 旬空两字元组)。

    依据: 六十甲子分六旬, 每旬十组; 旬空 = 旬首(甲X)所在支顺数第 11、12 位,
    等价于 (旬首支序 + 10) % 12 与 +11。例: 乙丑属甲子旬 -> 空戌亥。
    """
    idx = _ganzhi_index(ganzhi)
    head_idx = idx - (idx % 10)
    head = _ganzhi(head_idx)
    zi = ZHI.index(head[1])
    return head, (ZHI[(zi + 10) % 12], ZHI[(zi + 11) % 12])


def kongwang(ganzhi: str):
    """某柱旬空(列表形式, 便于直接放进返回值)。"""
    return list(xun_and_kongwang(ganzhi)[1])


def _shishen(day_gan: str, other_gan: str) -> str:
    """以日干为我, 求另一天干的十神(子平法)。

    同五行: 同性=比肩 / 异性=劫财
    我生者: 同性=食神 / 异性=伤官
    我克者: 同性=偏财 / 异性=正财
    克我者: 同性=七杀 / 异性=正官
    生我者: 同性=偏印 / 异性=正印
    """
    dw, ow = GAN_WUXING[day_gan], GAN_WUXING[other_gan]
    same = GAN_YINYANG[day_gan] == GAN_YINYANG[other_gan]
    if ow == dw:
        return "比肩" if same else "劫财"
    if SHENG[dw] == ow:
        return "食神" if same else "伤官"
    if KE[dw] == ow:
        return "偏财" if same else "正财"
    if BEI_KE[dw] == ow:
        return "七杀" if same else "正官"
    return "偏印" if same else "正印"


def _changsheng(gan: str, zhi: str) -> str:
    """十二长生: 阳干顺行、阴干逆行, 由各干长生位起算 (取自 constants.CHANGSHENG_*)。"""
    start = ZHI.index(CHANGSHENG_START[gan])
    step = ZHI.index(zhi) - start
    if GAN_YINYANG[gan] == "阴":
        step = -step
    return CHANGSHENG_ORDER[step % 12]


# ============================================================ 五、五行得分 / 旺衰 / 喜用


def _wuxing_score(pillars: dict):
    """五行力量评分(权重表见模块顶部 W_GAN / W_ZHI / CANGGAN_RATIO)。

    规则: 天干按位置取权重记入其五行; 地支权重按藏干比例(本气/中气/余气)摊到藏干五行。
    日干自身不计分(它是"我", 计入会造成自我加权)。总分 105。
    返回 (五元素得分 dict, 明细 list[str])。
    """
    score = {w: 0.0 for w in WUXING}
    detail = []
    for pos, lab in _POS:
        g, z = pillars[pos]["gan"], pillars[pos]["zhi"]
        wg = W_GAN[pos]
        if wg:
            score[GAN_WUXING[g]] += wg
        wz = W_ZHI[pos]
        cg = ZHI_CANGGAN[z]
        ratios = CANGGAN_RATIO[len(cg)]
        parts = []
        for c, r in zip(cg, ratios):
            v = wz * r
            score[GAN_WUXING[c]] += v
            parts.append("%s%.1f" % (c, v))
        detail.append("%s干%s %.1f; %s支%s[%s]" % (lab, g, wg, lab, z, " ".join(parts)))
    return score, detail


def _self_wuxing(day_gan: str):
    """日主的同党五行: (比劫=自身五行, 印=生我五行)。"""
    me = GAN_WUXING[day_gan]
    return me, BEI_SHENG[me]


def _zhi_ally_share(zhi: str, ally) -> float:
    """某地支中"同党五行"所占的藏干比例份额(0..1)。"""
    cg = ZHI_CANGGAN[zhi]
    ratios = CANGGAN_RATIO[len(cg)]
    return sum(r for c, r in zip(cg, ratios) if GAN_WUXING[c] in ally)


def _strength(pillars: dict, day_gan: str):
    """旺衰判定: 得令(45) + 得地(30) + 得势(25) 三因子加权, 满分 100。

    - 得令: 月支藏干中"同党"(比劫+印)的份额 × 45。
    - 得地: 日支(0.5)/时支(0.3)/年支(0.2) 同党份额加权 × 30。
    - 得势: 月干(0.4)/年干(0.3)/时干(0.3) 中同党天数比例 × 25。
    判定: 同党恰好一半时得分 50, 故取 50±8 为"中和"带 -> ≥58 偏强, ≤42 偏弱。
    (本评分为本实现自定义的量化方案, 见模块顶部说明 7/8; 不含合化、三合局加成, 存疑。)
    """
    me, yin = _self_wuxing(day_gan)
    ally = {me, yin}

    def gan_share(pos):
        """某天干位置属于同党(比劫/印)则 1.0, 否则 0.0。"""
        return 1.0 if GAN_WUXING[pillars[pos]["gan"]] in ally else 0.0

    def zhi_share(pos):
        """某地支位置藏干中同党五行所占份额(0..1)。"""
        return _zhi_ally_share(pillars[pos]["zhi"], ally)

    ling = S_LING * zhi_share("month")
    di = S_DI * sum(S_DI_SUB[p] * zhi_share(p) for p in ("day", "hour", "year"))
    shi = S_SHI * sum(S_SHI_SUB[p] * gan_share(p) for p in ("year", "month", "hour"))
    total = ling + di + shi
    verdict = "偏强" if total >= STRONG_TH else ("偏弱" if total <= WEAK_TH else "中和")
    detail = ("日主%s(%s); 同党=比劫%s+印%s。"
              "得令 %.1f/45 (月支%s, 同党份额%.0f%%); "
              "得地 %.1f/30 (日支%s %.0f%% ×0.5, 时支%s %.0f%% ×0.3, 年支%s %.0f%% ×0.2); "
              "得势 %.1f/25 (年干%s, 月干%s, 时干%s); 合计 %.1f/100 -> %s"
              % (day_gan, me, me, yin,
                 ling, pillars["month"]["zhi"], zhi_share("month") * 100,
                 di, pillars["day"]["zhi"], zhi_share("day") * 100,
                 pillars["hour"]["zhi"], zhi_share("hour") * 100,
                 pillars["year"]["zhi"], zhi_share("year") * 100,
                 shi, pillars["year"]["gan"], pillars["month"]["gan"], pillars["hour"]["gan"],
                 total, verdict))
    return {"score": round(total, 2), "verdict": verdict, "detail": detail}


#: 简化调候表: 按月令寒暖燥湿取"调候五行"。
#: 冬(亥子丑)寒湿取火暖局; 夏(巳午未)燥热取水润局; 春(寅卯辰)木旺喜火发荣; 秋(申酉戌)金旺气燥喜水。
#: 依据: 调候思想的季节性简化, 非《穷通宝鉴》逐日干细表 —— 存疑, 仅作辅助。
TIAOHOU = {
    "亥": "火", "子": "火", "丑": "火",
    "寅": "火", "卯": "火", "辰": "火",
    "巳": "水", "午": "水", "未": "水",
    "申": "水", "酉": "水", "戌": "水",
}


def _xiyong(pillars: dict, day_gan: str, wuxing_score: dict, strength: dict):
    """喜用神/忌神: 扶抑法为主, 调候为辅。

    扶抑法则:
      - 身弱: 喜"印(生我)"与"比劫(同我)"扶身; 忌"财(我克)/官杀(克我)/食伤(我生)"。
              若印之五行力量 ≥ 比劫, 则印在先(印能生身兼化官杀/制食伤), 否则比劫在先。
      - 身强: 喜"食伤(泄)/财(耗)/官杀(克)" (默认按 食伤>财>官杀 排序);
              忌"印/比劫", 按力量降序排出最忌者。
    调候法则(简化, 存疑):
      - 冬月寒湿取火、夏月燥热取水、春取火、秋取水(见 TIAOHOU);
      - 调候五行若已在喜用中则提到首位(急则治标); 若落在忌神中, 则从忌神移除并记入 conflicts
        (寒暖失衡时的调候优先级高于扶抑, 属流派分歧)。
    返回 dict 含 favor/avoid/method/detail + 扩展键 tiaohou/conflicts/party_scores。
    """
    me, yin = _self_wuxing(day_gan)
    shi, cai, guan = SHENG[me], KE[me], BEI_KE[me]
    weak = strength["verdict"] == "偏弱"

    if weak:
        favor = [yin, me] if wuxing_score.get(yin, 0.0) >= wuxing_score.get(me, 0.0) else [me, yin]
        others = sorted(((e, wuxing_score.get(e, 0.0)) for e in (shi, cai, guan)),
                        key=lambda kv: -kv[1])
        avoid = [e for e, _ in others]
        method = "扶抑法(身弱扶身) + 调候"
        reason = "日主%s%s, 旺衰得分 %.2f -> %s, 取印%s与比劫%s扶身" % (
            day_gan, me, strength["score"], strength["verdict"], yin, me)
    else:
        favor = [shi, cai, guan]
        others = sorted(((e, wuxing_score.get(e, 0.0)) for e in (yin, me)), key=lambda kv: -kv[1])
        avoid = [e for e, _ in others]
        method = "扶抑法(身强抑泄) + 调候"
        reason = "日主%s%s, 旺衰得分 %.2f -> %s, 取食伤%s/财%s/官杀%s泄耗克制" % (
            day_gan, me, strength["score"], strength["verdict"], shi, cai, guan)

    th = TIAOHOU.get(pillars["month"]["zhi"], None)
    conflicts = []
    if th:
        if th in favor:
            favor = [th] + [e for e in favor if e != th]
        else:
            if th in avoid:
                conflicts.append(
                    "调候取%s(月令%s寒暖燥湿所需)与扶抑所忌冲突, 已按'调候优先'移入喜用(存疑/流派分歧)"
                    % (th, pillars["month"]["zhi"]))
                avoid = [e for e in avoid if e != th]
            favor = [th] + favor

    party = {"比劫": wuxing_score.get(me, 0.0), "印": wuxing_score.get(yin, 0.0),
             "食伤": wuxing_score.get(shi, 0.0), "财": wuxing_score.get(cai, 0.0),
             "官杀": wuxing_score.get(guan, 0.0)}
    detail = ("%s。%s。五行力量: 比劫%s %.1f / 印%s %.1f / 食伤%s %.1f / 财%s %.1f / 官杀%s %.1f。"
              "月令%s -> 调候取%s。喜: %s; 忌: %s。"
              % (method, reason, me, party["比劫"], yin, party["印"], shi, party["食伤"],
                 cai, party["财"], guan, party["官杀"], pillars["month"]["zhi"],
                 th or "无", "/".join(favor), "/".join(avoid)))
    return {"favor": favor, "avoid": avoid, "method": method, "detail": detail,
            "tiaohou": th, "conflicts": conflicts, "party_scores": party}


# ============================================================ 六、神煞

#: 天乙贵人 (以日干/年干查四支): 口诀"甲戊庚牛羊, 乙己鼠猴乡, 丙丁猪鸡位,
#: 壬癸兔蛇藏, 六辛逢马虎"。存疑: 另有"甲戊并牛羊, 庚辛逢虎马"版本(庚辛归属不同)。
TIANYI = {"甲": ("丑", "未"), "戊": ("丑", "未"), "庚": ("丑", "未"),
          "乙": ("子", "申"), "己": ("子", "申"),
          "丙": ("亥", "酉"), "丁": ("亥", "酉"),
          "壬": ("卯", "巳"), "癸": ("卯", "巳"),
          "辛": ("午", "寅")}
#: 三合局查法(以年支/日支查): 桃花(咸池)、驿马、华盖、将星
_SANHE_GROUP = {"申": "申子辰", "子": "申子辰", "辰": "申子辰",
                "寅": "寅午戌", "午": "寅午戌", "戌": "寅午戌",
                "巳": "巳酉丑", "酉": "巳酉丑", "丑": "巳酉丑",
                "亥": "亥卯未", "卯": "亥卯未", "未": "亥卯未"}
TAOHUA = {"申子辰": "酉", "寅午戌": "卯", "巳酉丑": "午", "亥卯未": "子"}
YIMA = {"申子辰": "寅", "寅午戌": "申", "巳酉丑": "亥", "亥卯未": "巳"}
HUAGAI = {"申子辰": "辰", "寅午戌": "戌", "巳酉丑": "丑", "亥卯未": "未"}
JIANGXING = {"申子辰": "子", "寅午戌": "午", "巳酉丑": "酉", "亥卯未": "卯"}
#: 羊刃(阳刃): 阳干取"禄前一位"(无争议); 阴干存疑, 本模块取"顺行禄前一位"
#: (乙辰/丁己未/辛戌/癸丑); 另有"乙寅/丁己巳/辛申/癸亥"及"阴干无刃"之说。
YANGREN = {"甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子",
           "乙": "辰", "丁": "未", "己": "未", "辛": "戌", "癸": "丑"}
#: 禄神(临官位): 甲寅 乙卯 丙戊巳 丁己午 庚申 辛酉 壬亥 癸子
LUSHEN = {"甲": "寅", "乙": "卯", "丙": "巳", "戊": "巳", "丁": "午", "己": "午",
          "庚": "申", "辛": "酉", "壬": "亥", "癸": "子"}
#: 文昌贵人: 甲乙巳午报君知, 丙戊申宫丁己鸡, 庚猪辛鼠壬逢虎, 癸人见卯入云梯
WENCHANG = {"甲": "巳", "乙": "午", "丙": "申", "戊": "申", "丁": "酉", "己": "酉",
            "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯"}
#: 红艳煞 (以日干/年干查支)。存疑: 歌诀"甲乙午申"歧义, 本模块取 甲->午、乙->申。
HONGYAN = {"甲": "午", "乙": "申", "丙": "寅", "丁": "未", "戊": "辰", "己": "辰",
           "庚": "戌", "辛": "酉", "壬": "子", "癸": "申"}
#: 孤辰寡宿(以年支三会方查): 亥子丑->孤寅寡戌; 寅卯辰->孤巳寡丑;
#: 巳午未->孤申寡辰; 申酉戌->孤亥寡未。存疑: 亦有以日支查者。
_GUCHEN = {"亥": ("寅", "戌"), "子": ("寅", "戌"), "丑": ("寅", "戌"),
           "寅": ("巳", "丑"), "卯": ("巳", "丑"), "辰": ("巳", "丑"),
           "巳": ("申", "辰"), "午": ("申", "辰"), "未": ("申", "辰"),
           "申": ("亥", "未"), "酉": ("亥", "未"), "戌": ("亥", "未")}
#: 天德贵人(以月支查, 值可为天干或地支)
TIANDE = {"寅": "丁", "卯": "申", "辰": "壬", "巳": "辛", "午": "亥", "未": "甲",
          "申": "癸", "酉": "寅", "戌": "丙", "亥": "乙", "子": "巳", "丑": "庚"}
#: 月德贵人(以月支三合局查天干): 寅午戌->丙; 申子辰->壬; 亥卯未->甲; 巳酉丑->庚
YUEDE = {"寅午戌": "丙", "申子辰": "壬", "亥卯未": "甲", "巳酉丑": "庚"}


def _pillar_maps(pillars: dict):
    """返回 (支 -> [位置标签...], 干 -> [位置标签...]), 标签如 '年支' / '月干'。"""
    zhi_map, gan_map = {}, {}
    for pos, lab in _POS:
        zhi_map.setdefault(pillars[pos]["zhi"], []).append(lab + "支")
        gan_map.setdefault(pillars[pos]["gan"], []).append(lab + "干")
    return zhi_map, gan_map


def _shensha(pillars: dict):
    """四柱神煞推算。每个神煞都标注"所查地支"(where 字段)与查法依据(note)。

    实现: 天乙贵人、桃花(咸池)、驿马、华盖、将星、羊刃、文昌、禄神、空亡、
          孤辰、寡宿、红艳煞, 另附天德贵人、月德贵人。
    流派分歧见模块顶部"存疑清单"。
    """
    out = []
    seen = set()
    zhi_map, gan_map = _pillar_maps(pillars)
    day_gan = pillars["day"]["gan"]
    year_gan = pillars["year"]["gan"]
    day_zhi = pillars["day"]["zhi"]
    year_zhi = pillars["year"]["zhi"]
    month_zhi = pillars["month"]["zhi"]

    def add(name, where_list, note):
        """按位置登记神煞(同名同位置去重)。"""
        for w in where_list:
            key = (name, w)
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": name, "where": w, "note": note})

    def hit_zhi(target):
        """四支中等于 target 的位置标签列表。"""
        return list(zhi_map.get(target, []))

    def hit_any(target):
        """四柱天干或地支中等于 target 的位置标签列表(天德等值可为干或支)。"""
        return list(zhi_map.get(target, [])) + list(gan_map.get(target, []))

    # 天乙贵人(以日干为主, 兼查年干)
    for base, g in (("日干", day_gan), ("年干", year_gan)):
        for t in TIANYI.get(g, ()):
            add("天乙贵人", hit_zhi(t),
                "以%s%s查天乙贵人, 见%s支 (口诀: 甲戊庚牛羊, 乙己鼠猴乡…六辛逢马虎; 庚辛归属存疑)"
                % (base, g, t))
    # 桃花 / 驿马 / 华盖 / 将星(以年支与日支各查一次)
    for base, z in (("年支", year_zhi), ("日支", day_zhi)):
        grp = _SANHE_GROUP[z]
        add("桃花", hit_zhi(TAOHUA[grp]), "以%s%s(%s三合)查咸池桃花, 见%s" % (base, z, grp, TAOHUA[grp]))
        add("驿马", hit_zhi(YIMA[grp]), "以%s%s(%s三合)查驿马, 见%s" % (base, z, grp, YIMA[grp]))
        add("华盖", hit_zhi(HUAGAI[grp]), "以%s%s(%s三合)查华盖, 见%s" % (base, z, grp, HUAGAI[grp]))
        add("将星", hit_zhi(JIANGXING[grp]), "以%s%s(%s三合)查将星, 见%s" % (base, z, grp, JIANGXING[grp]))
    # 羊刃(以日干查)
    add("羊刃", hit_zhi(YANGREN[day_gan]),
        "以日干%s查羊刃, 见%s (阴干羊刃取法存疑: 另有乙寅/丁己巳/辛申/癸亥等说)" % (day_gan, YANGREN[day_gan]))
    # 禄神 / 文昌 / 红艳(日干为主, 禄与文昌兼查年干)
    for base, g in (("日干", day_gan), ("年干", year_gan)):
        add("禄神", hit_zhi(LUSHEN[g]), "以%s%s查禄神(临官位), 见%s" % (base, g, LUSHEN[g]))
        add("文昌", hit_zhi(WENCHANG[g]), "以%s%s查文昌贵人, 见%s" % (base, g, WENCHANG[g]))
    add("红艳煞", hit_zhi(HONGYAN[day_gan]),
        "以日干%s查红艳煞, 见%s (歌诀'甲乙午申'歧义, 存疑)" % (day_gan, HONGYAN[day_gan]))
    # 空亡(以日柱旬空查四支)
    head, kw = xun_and_kongwang(pillars["day"]["ganzhi"])
    for t in kw:
        for w in hit_zhi(t):
            add("空亡", [w], "日柱%s属%s旬, 旬空%s%s, 见%s支" % (pillars["day"]["ganzhi"], head, kw[0], kw[1], t))
    # 孤辰寡宿(以年支查)
    gu, gua = _GUCHEN[year_zhi]
    add("孤辰", hit_zhi(gu), "以年支%s查孤辰, 见%s (亦有以日支查者, 存疑)" % (year_zhi, gu))
    add("寡宿", hit_zhi(gua), "以年支%s查寡宿, 见%s (亦有以日支查者, 存疑)" % (year_zhi, gua))
    # 天德 / 月德(以月支查; 天德之值可为干或支)
    td = TIANDE[month_zhi]
    add("天德贵人", hit_any(td), "以月支%s查天德贵人, 值%s" % (month_zhi, td))
    yd = YUEDE[_SANHE_GROUP[month_zhi]]
    add("月德贵人", hit_any(yd), "以月支%s(%s三合)查月德贵人, 值%s" % (month_zhi, _SANHE_GROUP[month_zhi], yd))
    return out


def _trigger_sets(pillars: dict):
    """某命盘的"神煞触发集合": 用于日运(day_relation)判断当日干支是否引动神煞。

    返回 {神煞名: set(触发用天干或地支)}, 含义为"当日的干/支落在该集合中即引动"。
    """
    day_gan = pillars["day"]["gan"]
    year_gan = pillars["year"]["gan"]
    day_zhi = pillars["day"]["zhi"]
    year_zhi = pillars["year"]["zhi"]
    month_zhi = pillars["month"]["zhi"]
    sets = {
        "天乙贵人": set(TIANYI[day_gan]) | set(TIANYI[year_gan]),
        "羊刃": {YANGREN[day_gan]},
        "禄神": {LUSHEN[day_gan], LUSHEN[year_gan]},
        "文昌": {WENCHANG[day_gan], WENCHANG[year_gan]},
        "红艳煞": {HONGYAN[day_gan]},
        "天德贵人": {TIANDE[month_zhi]},
        "月德贵人": {YUEDE[_SANHE_GROUP[month_zhi]]},
        "空亡": set(kongwang(pillars["day"]["ganzhi"])),
    }
    for base, z in (("年", year_zhi), ("日", day_zhi)):
        grp = _SANHE_GROUP[z]
        sets.setdefault("桃花", set()).add(TAOHUA[grp])
        sets.setdefault("驿马", set()).add(YIMA[grp])
        sets.setdefault("华盖", set()).add(HUAGAI[grp])
        sets.setdefault("将星", set()).add(JIANGXING[grp])
    gu, gua = _GUCHEN[year_zhi]
    sets["孤辰"] = {gu}
    sets["寡宿"] = {gua}
    return sets


# ============================================================ 七、四支关系(冲合刑害)


def _zhi_relations(target_zhi: str, pillars: dict):
    """某个地支(如流日支)与命局四支的关系。

    返回 list[(类型, 位置标签, 命局支)], 类型 ∈ {冲, 六合, 刑, 自刑, 害, 半合}。
    依据: ZHI_CHONG/ZHI_LIUHE/ZHI_XING/ZHI_HAI/ZHI_SANHE (constants)。
    简化说明: 半合只判断"与命局某支同属一个三合局"(未细辨是否含旺支), 存疑。
    """
    rels = []
    for pos, lab in _POS:
        z = pillars[pos]["zhi"]
        if ZHI_CHONG[z] == target_zhi:
            rels.append(("冲", lab + "支", z))
        if ZHI_LIUHE[z] == target_zhi:
            rels.append(("六合", lab + "支", z))
        if ZHI_HAI[z] == target_zhi:
            rels.append(("害", lab + "支", z))
        if ZHI_XING.get(z) == target_zhi or ZHI_XING.get(target_zhi) == z:
            rels.append(("刑", lab + "支", z))
        if z == target_zhi and target_zhi in ("辰", "午", "酉", "亥"):
            rels.append(("自刑", lab + "支", z))
        if z != target_zhi and ZHI_SANHE[z] == ZHI_SANHE[target_zhi]:
            rels.append(("半合", lab + "支", z))
    return rels


def _rel_text(rels, kind: str, with_label=False) -> str:
    """把关系列表格式化成 '冲申(猴)' / '合巳(蛇)' 形式, 多命中用'、'连接。

    与需求示例一致: '冲申(猴)' —— 地支后附生肖; with_label=True 时附命局位置。
    """
    items = []
    for k, lab, z in rels:
        if k != kind:
            continue
        kind_txt = "合" if kind == "六合" else kind
        s = "%s%s(%s)" % (kind_txt, z, ZHI_SHENGXIAO[z])
        if with_label:
            s += "[%s]" % lab
        if s not in items:
            items.append(s)
    return "、".join(items)


# ============================================================ 八、大运 / 起运


def _is_yang_year(year_gan: str) -> bool:
    """年干是否阳干(甲丙戊庚壬)。"""
    return GAN_YINYANG[year_gan] == "阳"


def _dayun(pillars: dict, dt_local: datetime, gender: str, src: JieqiSource):
    """排大运与起运。

    顺逆: 阳年男 / 阴年女 顺排; 阴年男 / 阳年女 逆排 (子平法)。
    起运: 顺排 -> 从出生时刻到"下一个节"的天数; 逆排 -> 到"上一个节"的天数。
    折算: 3 天 = 1 年, 1 天 = 4 个月, 1 时辰 = 10 天
          (即 1 实际天 = 120 命理天, 1 年 = 360 命理天, 1 月 = 30 命理天)。
    每步 10 年, 输出前 8 步; start_date = 出生日期 + 起运年月日 (+10 年 × 步序)。
    返回 (dayun list, qiyun dict)。
    """
    year_gan = pillars["year"]["gan"]
    yang = _is_yang_year(year_gan)
    male = gender == "男"
    forward = (yang and male) or ((not yang) and (not male))
    prev_jie, next_jie = src.boundaries(dt_local)
    ref_name, ref_dt = (next_jie if forward else prev_jie)
    days = abs((ref_dt - dt_local).total_seconds()) / 86400.0

    total_age_days = days * 120.0            # 1 实际天 = 120 命理天
    y = int(total_age_days // 360)           # 360 命理天 = 1 年
    mo = int((total_age_days % 360) // 30)   # 30 命理天 = 1 月
    dd = int(round(total_age_days % 30))
    if dd >= 30:
        dd -= 30
        mo += 1
    if mo >= 12:
        mo -= 12
        y += 1
    age_years = days / 3.0
    start_date = _add_ymd(dt_local, y, mo, dd)

    month_idx = _ganzhi_index(pillars["month"]["ganzhi"])
    steps = []
    for i in range(1, 9):
        idx = (month_idx + i) % 60 if forward else (month_idx - i) % 60
        gz = _ganzhi(idx)
        sd = _add_ymd(start_date, 10 * (i - 1), 0, 0)
        steps.append({
            "index": i,
            "ganzhi": gz,
            "gan": gz[0], "zhi": gz[1],
            "start_age": round(age_years + 10 * (i - 1), 2),
            "start_year": sd.year,
            "start_date": "%04d-%02d-%02d" % (sd.year, sd.month, sd.day),
            "end_age": round(age_years + 10 * i, 2),
            "end_year": sd.year + 10,
            "shishen": _shishen(pillars["day"]["gan"], gz[0]),
            "zhi_shishen": _shishen(pillars["day"]["gan"], ZHI_CANGGAN[gz[1]][0]),
        })
    qiyun = {
        "age_years": round(age_years, 2),
        "detail": ("年柱%s(%s年) %s -> %s排; 起运参照%s %s; 出生到该节 %.4f 天; "
                   "÷3 = %.4f 年 = %d 年 %d 个月 %d 天; 交运日期 %s"
                   % (pillars["year"]["ganzhi"], "阳" if yang else "阴",
                      "男" if male else "女", "顺" if forward else "逆",
                      ref_name, _fmt(ref_dt), days, age_years, y, mo, dd,
                      "%04d-%02d-%02d" % (start_date.year, start_date.month, start_date.day))),
        "direction": "顺排" if forward else "逆排",
        "reference_jie": ref_name,
        "reference_jie_datetime": _fmt(ref_dt),
        "days_to_jie": round(days, 4),
        "start_date": "%04d-%02d-%02d" % (start_date.year, start_date.month, start_date.day),
        "years_months_days": [y, mo, dd],
        "rule": "3天=1年, 1天=4个月, 1时辰=10天",
    }
    return steps, qiyun


# ============================================================ 九、流年 / 流月


def _month_ganzhi_from_jie(year_gan: str, jie_name: str) -> str:
    """由"年干 + 所辖节名"定月柱干支(五虎遁: 甲己之年丙作首…)。"""
    zhi = JIE_ZHI[JIE_NAMES.index(jie_name)]
    offset = (ZHI.index(zhi) - ZHI.index("寅")) % 12      # 寅=0 … 丑=11
    gan = GAN[(GAN.index(year_gan) * 2 + 2 + offset) % 10]
    return gan + zhi


def _hour_ganzhi(day_gan: str, hour_zhi: str) -> str:
    """由日干与时辰地支定时柱天干(五鼠遁: 甲己还加甲…)。"""
    return GAN[(GAN.index(day_gan) * 2 + ZHI.index(hour_zhi)) % 10] + hour_zhi


def _pillar_brief(gz: str, day_gan: str, pillars: dict):
    """给流年/流月等外部干支生成简要说明。"""
    rels = _zhi_relations(gz[1], pillars)
    return {
        "ganzhi": gz, "gan": gz[0], "zhi": gz[1],
        "nayin": nayin(gz),
        "shishen_gan": _shishen(day_gan, gz[0]),
        "shishen_zhi": _shishen(day_gan, ZHI_CANGGAN[gz[1]][0]),
        "chong": _rel_text(rels, "冲"),
        "he": _rel_text(rels, "六合"),
        "xing": _rel_text(rels, "刑"),
        "hai": _rel_text(rels, "害"),
    }


def _current_section(dt_local: datetime, src: JieqiSource, pillars: dict,
                     day_gan: str, dayun_steps: list):
    """以 dt_local 所在年份计算流年与流月(流年以立春为界, 流月以节为界)。"""
    y = dt_local.year
    lichun = src.jie_dt(y, "立春")
    ln_year = y if dt_local >= lichun else y - 1
    ln_gz = _ganzhi((ln_year - 4) % 60)
    prev_jie, next_jie = src.boundaries(dt_local)
    ly_gz = _month_ganzhi_from_jie(ln_gz[0], prev_jie[0])

    liunian = _pillar_brief(ln_gz, day_gan, pillars)
    liunian.update({"year": ln_year, "boundary": "立春", "lichun": _fmt(lichun)})
    liuyue = _pillar_brief(ly_gz, day_gan, pillars)
    liuyue.update({"jie": prev_jie[0], "jie_datetime": _fmt(prev_jie[1]),
                   "next_jie": next_jie[0], "next_jie_datetime": _fmt(next_jie[1])})

    cur_dy = None
    key = "%04d-%02d-%02d" % (dt_local.year, dt_local.month, dt_local.day)
    for st in dayun_steps:
        if key >= st["start_date"]:
            cur_dy = {"index": st["index"], "ganzhi": st["ganzhi"], "start_date": st["start_date"]}
    return {"liunian": liunian, "liuyue": liuyue, "current_dayun": cur_dy}


# ============================================================ 十、主接口


def _coerce_dt(value, tz_offset: float) -> datetime:
    """把输入统一为"本地钟表时间"的 naive datetime(带时区者先换算)。"""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone(timedelta(hours=tz_offset))).replace(tzinfo=None)
        return value
    if isinstance(value, Date):
        return datetime(value.year, value.month, value.day, 12, 0)
    raise TypeError("dt_local 应为 datetime 或 date, 得到 %r" % type(value))


def compute_bazi(dt_local, longitude: float = 121.47, tz_offset: float = 8.0,
                 calendar=None, gender: str = "男") -> dict:
    """四柱八字排盘(主接口)。

    参数:
        dt_local: 出生地钟表时间(datetime; 若是 date 则按当日 12:00 处理;
                  带时区者先换算到 UTC+tz_offset)
        longitude: 出生地经度(东经为正), 默认 121.47 (上海)
        tz_offset: 时区偏移(小时), 默认 8 (北京时间)
        calendar: 可选注入对象, 需提供 jieqi_between(y, m) 与/或 jieqi_datetime(year, name)
                  (亦兼容 engine.calendar_cn 的 jie_datetime(year,name) / solar_term_jd(year,name));
                  为 None 时自动尝试 engine.calendar_cn, 再退回内置近似节气算法;
                  传 False 可显式禁用外部节气源(强制使用内置近似算法)
        gender: "男" / "女", 决定大运顺逆
    返回:
        dict, 含 true_solar_time/shichen/pillars/day_master/canggan/shishen/wuxing_score/
        strength/xiyong/nayin/kongwang/shensha/dayun/qiyun/current/warnings 等键。
    规则依据与流派选择见模块顶部说明。
    """
    warn_list = []
    dt_local = _coerce_dt(dt_local, tz_offset)
    if gender in ("女", "女性", "F", "f", "female", "Female"):
        gender = "女"
    elif gender in ("男", "男性", "M", "m", "male", "Male"):
        gender = "男"
    else:
        warn_list.append("gender=%r 无法识别, 已按'男'处理(大运顺逆依赖性别)。" % (gender,))
        gender = "男"

    src = JieqiSource(calendar, tz_offset)

    def _collect_src_notes():
        """把节气来源的说明同步进 warnings(来源在运行中还会追加"回退/数据有误"等说明)。"""
        for w in src.notes:
            if w not in warn_list:
                warn_list.append(w)

    _collect_src_notes()
    warn_list.append(
        "晚子时规则: 本模块采用%s (LATE_ZI_ROLLS_DAY=%s)。"
        % ("「晚子时算次日」(23:00 起日柱进位次日, 时柱为次日子时)"
           if LATE_ZI_ROLLS_DAY else "「晚子时不换日」(日柱仍用当日, 时干用当日日干, 又称夜子时)",
           LATE_ZI_ROLLS_DAY))
    warn_list.append(
        "节气边界比较使用钟表时间(平太阳时)与节气时刻直接比较, 真太阳时仅用于定时辰与日界(流派选择, 见模块说明 6)。")

    # ---------- 真太阳时与时辰
    tst, corr = true_solar_time(dt_local, longitude, tz_offset, calendar=src.calendar)
    if corr.get("equation_of_time_note"):
        warn_list.append(corr["equation_of_time_note"])
    hour_zhi_idx = ((tst.hour + 1) // 2) % 12
    hour_zhi = ZHI[hour_zhi_idx]
    late_zi = (tst.hour == 23)
    tst_date = tst.date()
    if late_zi and LATE_ZI_ROLLS_DAY:
        tst_date = tst_date + timedelta(days=1)
        warn_list.append("真太阳时 %s 落在晚子时(23:00-24:00): 按所选流派日柱进位到次日。" % _fmt(tst))

    # ---------- 四柱
    lichun_this = src.jie_dt(dt_local.year, "立春")
    year_num = dt_local.year if dt_local >= lichun_this else dt_local.year - 1
    year_gz = _ganzhi((year_num - 4) % 60)
    prev_jie, next_jie = src.boundaries(dt_local)
    month_gz = _month_ganzhi_from_jie(year_gz[0], prev_jie[0])
    day_idx = _day_index(tst_date)
    day_gz = _ganzhi(day_idx)
    hour_gz = _hour_ganzhi(day_gz[0], hour_zhi)
    if late_zi and LATE_ZI_ROLLS_DAY:
        warn_list.append("晚子时: 日柱取次日 %s, 时柱 %s。" % (day_gz, hour_gz))

    pillars = {}
    for pos, lab in _POS:
        gz = {"year": year_gz, "month": month_gz, "day": day_gz, "hour": hour_gz}[pos]
        pillars[pos] = {"gan": gz[0], "zhi": gz[1], "ganzhi": gz}
    day_gan = pillars["day"]["gan"]
    day_master = {"gan": day_gan, "wuxing": GAN_WUXING[day_gan],
                  "yinyang": GAN_YINYANG[day_gan]}

    # ---------- 藏干 / 十神 / 长生 / 纳音 / 旬空
    canggan, shishen_zhi, changsheng = {}, {}, {}
    for pos, _lab in _POS:
        z = pillars[pos]["zhi"]
        canggan[pos] = list(ZHI_CANGGAN[z])
        shishen_zhi[pos] = [_shishen(day_gan, c) for c in ZHI_CANGGAN[z]]
        changsheng[pos] = _changsheng(day_gan, z)
    shishen_gan = {pos: ("日主" if pos == "day" else _shishen(day_gan, pillars[pos]["gan"]))
                   for pos, _lab in _POS}
    nayin_map = {pos: nayin(pillars[pos]["ganzhi"]) for pos, _lab in _POS}
    kw = kongwang(day_gz)

    # ---------- 五行 / 旺衰 / 喜用
    wscore, wdetail = _wuxing_score(pillars)
    wscore = {w: round(wscore[w], 2) for w in WUXING}
    strength = _strength(pillars, day_gan)
    xiyong = _xiyong(pillars, day_gan, wscore, strength)
    warn_list.extend(xiyong.pop("conflicts", []))

    # ---------- 神煞 / 大运 / 流年流月
    shensha = _shensha(pillars)
    dayun_steps, qiyun = _dayun(pillars, dt_local, gender, src)
    current = _current_section(dt_local, src, pillars, day_gan, dayun_steps)
    if src.used_fallback:
        warn_list.append("部分节气时刻由内置近似算法补足(近似值)。")
    _collect_src_notes()

    total_w = round(sum(wscore.values()), 2)
    return {
        "birth": _fmt(dt_local),
        "gender": gender,
        "true_solar_time": tst,
        "true_solar_offset": corr,
        "shichen": SHICHEN[hour_zhi_idx],
        "pillars": pillars,
        "day_master": day_master,
        "canggan": canggan,
        "changsheng": changsheng,
        "shishen": {"gan": shishen_gan, "zhi": shishen_zhi},
        "wuxing_score": wscore,
        "wuxing_score_total": total_w,
        "wuxing_detail": wdetail,
        "strength": strength,
        "xiyong": xiyong,
        "nayin": nayin_map,
        "kongwang": kw,
        "xun": xun_and_kongwang(day_gz)[0],
        "shensha": shensha,
        "dayun": dayun_steps,
        "qiyun": qiyun,
        "current": current,
        "jieqi": {"year_lichun": _fmt(lichun_this),
                  "prev_jie": {"name": prev_jie[0], "datetime": _fmt(prev_jie[1])},
                  "next_jie": {"name": next_jie[0], "datetime": _fmt(next_jie[1])},
                  "source": src.source_name},
        "warnings": warn_list,
    }


# ============================================================ 十一、每日运势接口

#: 建除十二神(以月建为"建", 日支顺行十二位)
JIANCHU = ["建", "除", "满", "平", "定", "执", "破", "危", "成", "收", "开", "闭"]


def day_ganzhi(date, calendar=None, tz_offset: float = 8.0) -> dict:
    """某公历日的日柱干支及其"建除/月建"所需信息(供每日运势使用)。

    参数:
        date: datetime.date 或 datetime(取其中日期; 若给日期则按当日 12:00 论节气)
    返回:
        dict{date, ganzhi, gan, zhi, nayin, xun, kongwang, wuxing_zhi, wuxing_gan,
             yue_zhi(月建), jie(所辖节), jianchu(建除十二神), day_index, warnings}
    说明: 月建以"节"为界; 建除 = (日支序 - 月建支序) mod 12 对应 建除满平定执破危成收开闭。
    """
    dt = _coerce_dt(date, tz_offset)
    idx = _day_index(dt.date())
    gz = _ganzhi(idx)
    src = JieqiSource(calendar, tz_offset)
    prev_jie, next_jie = src.boundaries(dt.replace(hour=12, minute=0, second=0, microsecond=0))
    yue_zhi = JIE_ZHI[JIE_NAMES.index(prev_jie[0])]
    head, kw = xun_and_kongwang(gz)
    return {
        "date": "%04d-%02d-%02d" % (dt.year, dt.month, dt.day),
        "ganzhi": gz, "gan": gz[0], "zhi": gz[1],
        "day_index": idx,
        "nayin": nayin(gz),
        "xun": head, "kongwang": list(kw),
        "wuxing_gan": GAN_WUXING[gz[0]], "wuxing_zhi": ZHI_WUXING[gz[1]],
        "shengxiao": ZHI_SHENGXIAO[gz[1]],
        "yue_zhi": yue_zhi,
        "jie": prev_jie[0],
        "next_jie": next_jie[0],
        "jianchu": JIANCHU[(ZHI.index(gz[1]) - ZHI.index(yue_zhi)) % 12],
        "warnings": list(src.notes),
    }


def day_relation(natal: dict, date, calendar=None, tz_offset: float = 8.0) -> dict:
    """某一天与某个命盘(compute_bazi 结果)的互动结果 —— 每日运势用。

    评分算法(本实现自定义, 全部明细写入 score_detail 以便复核):
        base = 50
        (1) 五行到位: 当日干支五行量(日干 1.0; 日支本气 1.0/中气 0.5/余气 0.25)
            命中喜用 +6 × min(量, 2.5) / 命中忌神 -6 × min(量, 2.5)  (单元素上限 ±15)
        (2) 与命局四支的冲合刑害(见 DAY_VS_NATAL): 日支位置全权重, 其余支半权重
        (3) 当日干支引动命局神煞(见 DAY_SHENSHA_SCORE): 吉神加分, 凶煞减分
        最终 score = clamp(round(base), 0, 100)。
    返回:
        {"day_ganzhi", "shishen_gan", "chong", "he", "xing", "hai", "wuxing_add",
         "favor_hit", "avoid_hit", "score", "highlights", "cautions"} + 若干扩展键。
    说明: chong/he/xing/hai 为字符串(地支后附生肖, 多命中用'、'连接); "he" 只列六合,
          半合/自刑的明细在扩展键 relations 与 score_detail 中。
    """
    natal_pillars = natal.get("pillars") or {}
    day_gan_master = (natal.get("day_master") or {}).get("gan") or natal_pillars.get("day", {}).get("gan")
    if not day_gan_master:
        raise ValueError("natal 缺少 day_master/pillars, 请先调用 compute_bazi()")
    favor = list((natal.get("xiyong") or {}).get("favor") or [])
    avoid = list((natal.get("xiyong") or {}).get("avoid") or [])
    warnings_ = []
    if not favor and not avoid:
        warnings_.append("natal 缺少 xiyong.favor/avoid(喜用神): 本日评分只计冲合刑害与神煞, 五行项不计分。")

    info = day_ganzhi(date, calendar=calendar, tz_offset=tz_offset)
    gz = info["ganzhi"]
    dg, dz = gz[0], gz[1]

    # (1) 五行增减
    add = {w: 0.0 for w in WUXING}
    add[GAN_WUXING[dg]] += 1.0
    cg = ZHI_CANGGAN[dz]
    for c, r in zip(cg, DAY_WUXING_ADD[len(cg)]):
        add[GAN_WUXING[c]] += r
    add = {w: round(v, 2) for w, v in add.items()}

    score = 50.0
    detail, highlights, cautions = [], [], []

    for w, amt in add.items():
        if amt <= 0:
            continue
        if w in favor:
            d = DAY_FAVOR_UNIT * min(amt, DAY_FAVOR_CAP)
            score += d
            detail.append("喜用%s到位 +%.1f" % (w, d))
            highlights.append("喜用神%s到位(+%.0f)" % (w, d))
        elif w in avoid:
            d = DAY_FAVOR_UNIT * min(amt, DAY_FAVOR_CAP)
            score -= d
            detail.append("忌神%s到位 -%.1f" % (w, d))
            cautions.append("忌神%s到位(-%.0f)" % (w, d))

    # (2) 冲合刑害
    rels = _zhi_relations(dz, natal_pillars) if natal_pillars else []
    rel_summary = {}
    for kind, label, z in rels:
        weight = 1.0 if label == "日支" else 0.5
        d = DAY_VS_NATAL.get(kind, 0.0) * weight
        score += d
        rel_summary.setdefault(kind, []).append((label, z, d))
        txt = "%s%s%s(%s) %+.1f" % (kind, label, z, ZHI_SHENGXIAO[z], d)
        detail.append(txt)
        if d >= 0:
            highlights.append("%s %s%s" % (kind, label, z))
        else:
            cautions.append("%s %s%s(%s)" % (kind, label, z, ZHI_SHENGXIAO[z]))

    # (3) 神煞引动
    ss_sets = _trigger_sets(natal_pillars) if natal_pillars else {}
    ss_hits = []
    for name, targets in ss_sets.items():
        if dz in targets:
            d = DAY_SHENSHA_SCORE.get(name, 0.0)
            score += d
            ss_hits.append((name, "日支", d))
            detail.append("%s临日支 %+.1f" % (name, d))
            (highlights if d >= 0 else cautions).append("%s临日支(%+.0f)" % (name, d))
        if dg in targets and name in ("天德贵人", "月德贵人", "禄神", "文昌", "天乙贵人"):
            d = DAY_SHENSHA_SCORE.get(name, 0.0)
            score += d
            ss_hits.append((name, "日干", d))
            detail.append("%s临日干 %+.1f" % (name, d))
            highlights.append("%s临日干(%+.0f)" % (name, d))

    score = int(max(0, min(100, round(score))))
    rel_texts = {k: "、".join("%s(%s)" % (z, ZHI_SHENGXIAO[z]) for _l, z, _d in v)
                 for k, v in rel_summary.items()}

    def _rel(kind):
        """把某类关系渲染成 '冲申(猴)' 形式的字符串(无命中返回空串)。"""
        s = rel_texts.get(kind, "")
        if not s:
            return ""
        return ("合" if kind == "六合" else kind) + s

    shishen_gan = _shishen(day_gan_master, dg)
    if info.get("warnings"):
        warnings_.extend(info["warnings"])

    out = {
        "date": info["date"],
        "day_ganzhi": gz,
        "shishen_gan": shishen_gan,
        "shishen_zhi": _shishen(day_gan_master, ZHI_CANGGAN[dz][0]),
        "chong": _rel("冲"), "he": _rel("六合"), "xing": _rel("刑"), "hai": _rel("害"),
        "wuxing_add": add,
        "favor_hit": sorted([w for w in favor if add.get(w, 0) > 0], key=lambda w: -add[w]),
        "avoid_hit": sorted([w for w in avoid if add.get(w, 0) > 0], key=lambda w: -add[w]),
        "score": score,
        "highlights": highlights,
        "cautions": cautions,
        "score_detail": detail,
        "relations": {k: [{"position": l, "zhi": z, "delta": d} for l, z, d in v]
                      for k, v in rel_summary.items()},
        "shensha_hits": [{"name": n, "where": w, "delta": d} for n, w, d in ss_hits],
        "day_info": info,
        "nayin": info["nayin"],
        "kongwang": info["kongwang"],
        "jianchu": info["jianchu"],
        "yue_zhi": info["yue_zhi"],
        "warnings": warnings_,
    }
    return out


def plan_day(natal: dict, target_date, calendar=None, tz_offset: float = 8.0) -> dict:
    """「每日运势」入口: 在 day_relation 基础上补充当日所处大运。

    返回与 day_relation 相同的 dict, 另加 dayun_step(所处大运, 可能为 None)。
    """
    res = day_relation(natal, target_date, calendar=calendar, tz_offset=tz_offset)
    step = None
    key = res["date"]
    for st in (natal.get("dayun") or []):
        if key >= st["start_date"]:
            step = {"index": st["index"], "ganzhi": st["ganzhi"], "start_date": st["start_date"],
                    "shishen": st["shishen"]}
    res["dayun_step"] = step
    return res


# ============================================================ 十二、自检


def _print_chart(natal: dict) -> None:
    """打印完整排盘(自检用)。"""
    p = natal["pillars"]
    print("=" * 78)
    print("八字排盘自检: %s (性别 %s)" % (natal["birth"], natal["gender"]))
    c = natal["true_solar_offset"]
    print("真太阳时: %s  (经度差 %+.2f 分 + 均时差 %+.2f 分 = %+.2f 分)"
          % (_fmt(natal["true_solar_time"]), c["longitude_minutes"],
             c["equation_of_time"], c["total_minutes"]))
    print("时辰: %s" % natal["shichen"])
    print("四柱: %s %s %s %s   (年/月/日/时)"
          % (p["year"]["ganzhi"], p["month"]["ganzhi"], p["day"]["ganzhi"], p["hour"]["ganzhi"]))
    print("日主: %s(%s, %s)   旬空: %s (日柱属%s旬)"
          % (natal["day_master"]["gan"], natal["day_master"]["wuxing"],
             natal["day_master"]["yinyang"], "".join(natal["kongwang"]), natal["xun"]))
    print("纳音: 年%s 月%s 日%s 时%s"
          % (natal["nayin"]["year"], natal["nayin"]["month"], natal["nayin"]["day"], natal["nayin"]["hour"]))
    print("藏干: " + "; ".join("%s支%s" % (lab, "".join(natal["canggan"][pos]))
                              for pos, lab in _POS))
    print("十神: 天干 " + " ".join("%s=%s" % (lab + "干", natal["shishen"]["gan"][pos])
                                  for pos, lab in _POS))
    for pos, lab in _POS:
        print("      %s支%s藏干十神: %s" % (lab, p[pos]["zhi"],
              " ".join("%s(%s)" % (c, s) for c, s in
                       zip(natal["canggan"][pos], natal["shishen"]["zhi"][pos]))))
    print("十二长生(日干对各支): " + " ".join("%s=%s" % (lab + "支", natal["changsheng"][pos])
                                             for pos, lab in _POS))
    ws = natal["wuxing_score"]
    print("五行得分(权重表见模块顶部, 合计%.0f): %s"
          % (natal["wuxing_score_total"], " ".join("%s %.2f" % (w, ws[w]) for w in WUXING)))
    print("旺衰: %s (%.2f/100)" % (natal["strength"]["verdict"], natal["strength"]["score"]))
    print("      " + natal["strength"]["detail"])
    xy = natal["xiyong"]
    print("喜用: 喜 %s / 忌 %s   [%s]" % ("、".join(xy["favor"]), "、".join(xy["avoid"]), xy["method"]))
    print("      " + xy["detail"])
    print("神煞: " + ("; ".join("%s@%s" % (s["name"], s["where"]) for s in natal["shensha"]) or "无"))
    print("起运: " + natal["qiyun"]["detail"])
    print("大运(前8步):")
    for st in natal["dayun"]:
        print("   %d. %s  %s年起 (%.1f-%.1f岁) %s  十神=%s"
              % (st["index"], st["ganzhi"], st["start_year"], st["start_age"],
                 st["end_age"], st["start_date"], st["shishen"]))
    cur = natal["current"]
    print("流年: %s (%d年, 立春界) 十神=%s 冲=%s" % (cur["liunian"]["ganzhi"], cur["liunian"]["year"],
                                                 cur["liunian"]["shishen_gan"], cur["liunian"]["chong"] or "无"))
    print("流月: %s (辖节%s %s) 十神=%s" % (cur["liuyue"]["ganzhi"], cur["liuyue"]["jie"],
                                        cur["liuyue"]["jie_datetime"], cur["liuyue"]["shishen_gan"]))
    print("节气源: %s" % natal["jieqi"]["source"])
    print("warnings:")
    for w in natal["warnings"]:
        print("   - " + w)
    print("=" * 78)


def _self_check() -> None:
    """自检: 基准四柱 + 日柱公式锚点 + 纳音/旬空完整性 + 大运方向 + 每日运势。"""
    natal = compute_bazi(datetime(1999, 5, 13, 12, 30), longitude=121.47, tz_offset=8.0, gender="男")
    _print_chart(natal)

    p = natal["pillars"]
    assert _jdn_from_ymd(1999, 5, 13) == 2451312, "JDN(1999-05-13) 应为 2451312"
    assert p["year"]["ganzhi"] == "己卯", "年柱应为己卯, 实得 %s" % p["year"]["ganzhi"]
    assert p["month"]["ganzhi"] == "己巳", "月柱应为己巳, 实得 %s" % p["month"]["ganzhi"]
    assert p["day"]["ganzhi"] == "乙丑", "日柱应为乙丑, 实得 %s" % p["day"]["ganzhi"]
    assert p["hour"]["ganzhi"] == "壬午", "时柱应为壬午, 实得 %s" % p["hour"]["ganzhi"]
    assert natal["shichen"] == "午时"
    assert natal["day_master"] == {"gan": "乙", "wuxing": "木", "yinyang": "阴"}
    assert natal["shishen"]["gan"] == {"year": "偏财", "month": "偏财", "day": "日主", "hour": "正印"}
    assert natal["nayin"] == {"year": "城头土", "month": "大林木", "day": "海中金", "hour": "杨柳木"}
    assert natal["kongwang"] == ["戌", "亥"], "日柱乙丑属甲子旬, 旬空戌亥"
    assert natal["dayun"][0]["ganzhi"] == "戊辰", "阴年男逆排, 首运应为戊辰"

    # 日柱公式锚点
    assert _ganzhi(_day_index(Date(1949, 10, 1))) == "甲子"
    assert _ganzhi(_day_index(Date(2000, 1, 1))) == "戊午"
    assert _ganzhi(_day_index(Date(2024, 1, 1))) == "甲子"
    # 纳音表完整性
    assert len(NAYIN_60) == 60 and len(set(NAYIN_60)) == 30
    assert NAYIN_60[0] == "海中金" and NAYIN_60[59] == "大海水"
    # 旬空表
    assert kongwang("甲子") == ["戌", "亥"] and kongwang("癸酉") == ["戌", "亥"]
    assert kongwang("甲寅") == ["子", "丑"] and kongwang("乙卯") == ["子", "丑"]
    # 五虎遁 / 五鼠遁
    assert _month_ganzhi_from_jie("甲", "立春") == "丙寅"
    assert _month_ganzhi_from_jie("甲", "小寒") == "丁丑"
    assert _month_ganzhi_from_jie("己", "立夏") == "己巳"
    assert _hour_ganzhi("乙", "午") == "壬午" and _hour_ganzhi("甲", "子") == "甲子"
    # 十神
    assert _shishen("乙", "己") == "偏财" and _shishen("乙", "壬") == "正印"
    assert _shishen("甲", "庚") == "七杀" and _shishen("甲", "辛") == "正官"
    # 大运方向轮换
    for gender, expect in (("男", "逆排"), ("女", "顺排")):
        n2 = compute_bazi(datetime(1999, 5, 13, 12, 30), gender=gender)
        assert n2["qiyun"]["direction"] == expect, (gender, n2["qiyun"]["direction"])
    # 晚子时: 23:30 -> 日柱进次日
    n3 = compute_bazi(datetime(1999, 5, 13, 23, 30), longitude=121.47)
    assert n3["pillars"]["day"]["ganzhi"] == "丙寅", n3["pillars"]["day"]["ganzhi"]
    assert n3["pillars"]["hour"]["ganzhi"] == "戊子", n3["pillars"]["hour"]["ganzhi"]
    # 立春界: 1999-02-03 应属戊寅年, 1999-02-05 应属己卯年
    assert compute_bazi(datetime(1999, 2, 3, 12, 0))["pillars"]["year"]["ganzhi"] == "戊寅"
    assert compute_bazi(datetime(1999, 2, 5, 12, 0))["pillars"]["year"]["ganzhi"] == "己卯"
    # 节界: 1999-05-05 应属戊辰月, 1999-05-08 应属己巳月 (立夏 5/6)
    assert compute_bazi(datetime(1999, 5, 5, 12, 0))["pillars"]["month"]["ganzhi"] == "戊辰"
    assert compute_bazi(datetime(1999, 5, 8, 12, 0))["pillars"]["month"]["ganzhi"] == "己巳"

    # 每日运势
    dr = day_relation(natal, Date(2026, 10, 16))
    print("日运示例 2026-10-16: %s 十神=%s 冲=%s 合=%s 刑=%s 害=%s score=%d"
          % (dr["day_ganzhi"], dr["shishen_gan"], dr["chong"] or "无", dr["he"] or "无",
             dr["xing"] or "无", dr["hai"] or "无", dr["score"]))
    print("   highlights:", "；".join(dr["highlights"]) or "无")
    print("   cautions  :", "；".join(dr["cautions"]) or "无")
    assert 0 <= dr["score"] <= 100
    assert set(dr["wuxing_add"]) == set(WUXING)
    dg2 = day_ganzhi(Date(2026, 10, 16))
    print("日柱信息: %s 纳音%s 月建%s 建除%s 旬空%s"
          % (dg2["ganzhi"], dg2["nayin"], dg2["yue_zhi"], dg2["jianchu"], "".join(dg2["kongwang"])))
    pd = plan_day(natal, Date(2026, 10, 16))
    assert "dayun_step" in pd and pd["dayun_step"] is not None
    print("所处大运: %s (第%d步, %s起)" % (pd["dayun_step"]["ganzhi"], pd["dayun_step"]["index"],
                                        pd["dayun_step"]["start_date"]))
    print("★ 自检全部通过 (1999-05-13 12:30 -> 己卯 己巳 乙丑 壬午)")


if __name__ == "__main__":
    _self_check()
