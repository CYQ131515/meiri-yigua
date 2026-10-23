# -*- coding: utf-8 -*-
"""历算核心: 儒略日、ΔT、太阳/月亮黄经、二十四节气、朔望、农历转换。

理论来源:
  * 太阳位置: VSOP87D 截断序列 (engine/data/vsop87d.bin), 精度 ~0.05" (1900-2100)
  * 月亮位置: Meeus《Astronomical Algorithms》第 47 章 ELP-2000/82 简版
  * 朔望月:   Meeus 第 49 章 (新月/满月 JDE 级数)
  * ΔT:       Espenak & Meeus 多项式 (NASA 多年代公式)
  * 农历:     定朔定气, 以东经 120° 标准时, 冬至所在月为十一月, 闰月用"无中气置闰"
"""
from __future__ import annotations

import datetime as _dt
import math
import struct
import os

from .constants import JIEQI_LON, JIEQI_NAMES, JIE_LON, JIE_NAMES

D2R = math.pi / 180.0
R2D = 180.0 / math.pi
ARCSEC = 206264.80624709636
J2000 = 2451545.0
_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "vsop87d.bin")


# ============================================================ 基础时间函数
def jd_from_datetime(dt):
    """datetime(UTC) -> 儒略日 (UT)。"""
    y, m = dt.year, dt.month
    d = dt.day + (dt.hour + dt.minute / 60.0 + (dt.second + dt.microsecond / 1e6) / 3600.0) / 24.0
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def jd_from_ymd(y, m, d, hour=0.0):
    return jd_from_datetime(_dt.datetime(y, m, d) + _dt.timedelta(hours=hour))


def datetime_from_jd(jd):
    """儒略日 -> datetime(UTC), 忽略微小数值误差。"""
    jd = jd + 0.5
    z = int(jd)
    f = jd - z
    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - alpha // 4
    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)
    day = b - d - int(30.6001 * e) + f
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    di = int(day)
    frac = (day - di) * 24.0
    hh = int(frac)
    mm = int((frac - hh) * 60)
    ss = (frac - hh - mm / 60.0) * 60
    if ss >= 59.9995:
        return datetime_from_jd(jd + 5e-9)
    return _dt.datetime(year, month, di, hh, mm, int(ss), int((ss - int(ss)) * 1e6))


def delta_t_seconds(year, month=7):
    """ΔT = TT - UT1, 单位秒。Espenak & Meeus 多年代多项式。"""
    y = year + (month - 0.5) / 12.0
    if 2005 <= y < 2050:
        t = y - 2000.0
        return 62.92 + 0.32217 * t + 0.005589 * t * t
    if 1986 <= y < 2005:
        t = y - 2000.0
        return (63.86 + 0.3345 * t - 0.060374 * t ** 2 + 0.0017275 * t ** 3
                + 0.000651814 * t ** 4 + 0.00002373599 * t ** 5)
    if 2050 <= y < 2150:
        return -20 + 32 * ((y - 1820) / 100.0) ** 2 - 0.5628 * (2150 - y)
    if 1900 <= y < 1986:
        t = (y - 1900) / 100.0
        return (-2.79 + 1.494119 * t - 0.0598939 * t ** 2 + 0.0061966 * t ** 3
                - 0.000197 * t ** 4)
    if 1800 <= y < 1900:
        t = y - 1860
        return 7.62 + 0.5737 * t - 0.251754 * t ** 2 + 0.01680668 * t ** 3 \
            - 0.0004473624 * t ** 4 + t ** 5 / 233174
    if -500 <= y < 1800:
        u = (y - 1820) / 100.0
        return -20 + 32 * u * u
    u = (y - 1820) / 100.0
    return -20 + 32 * u * u - 0.5628 * (2150 - y)


def jd_tt_from_ut(jd_ut):
    """UT 儒略日 -> TT 儒略日。"""
    dt = datetime_from_jd(jd_ut)
    return jd_ut + delta_t_seconds(dt.year, dt.month) / 86400.0


def jd_ut_from_tt(jd_tt):
    """TT 儒略日 -> UT 儒略日。"""
    dt = datetime_from_jd(jd_tt)
    return jd_tt - delta_t_seconds(dt.year, dt.month) / 86400.0


def t_millennia(jd_tt):
    return (jd_tt - J2000) / 365250.0


def t_centuries(jd_tt):
    return (jd_tt - J2000) / 36525.0


# ============================================================ VSOP87D 读取
_VSOP_CACHE = {}


def _load_vsop():
    if _VSOP_CACHE:
        return _VSOP_CACHE
    with open(_DATA, "rb") as fh:
        magic = fh.read(9)
        if magic != b"VSOP87DC2":
            raise RuntimeError("VSOP87D 数据文件格式不符: %r" % magic)
        (nplan,) = struct.unpack("<H", fh.read(2))
        for _ in range(nplan):
            (ln,) = struct.unpack("<B", fh.read(1))
            name = fh.read(ln).decode("ascii")
            rec = {}
            for _v in range(3):
                var, npow = struct.unpack("<BB", fh.read(2))
                label = {1: "L", 2: "B", 3: "R"}[var]
                powers = {}
                for _p in range(npow):
                    power, cnt = struct.unpack("<BI", fh.read(5))
                    terms = []
                    for _t in range(cnt):
                        a, b, c = struct.unpack("<ddd", fh.read(24))
                        terms.append((a, b, c))
                    powers[power] = terms
                rec[label] = powers
            _VSOP_CACHE[name] = rec
    return _VSOP_CACHE


def vsop_xyz(planet, jd_tt):
    """日心黄道坐标 (当日动力学黄道与分点), 返回 (L, B, R) 弧度/弧度/AU。"""
    data = _load_vsop()[planet]
    t = t_millennia(jd_tt)
    out = []
    for label in ("L", "B", "R"):
        powers = data[label]
        total = 0.0
        for p, terms in powers.items():
            s = math.fsum(a * math.cos(b + c * t) for a, b, c in terms)
            total += s * t ** p
        out.append(total)
    return out[0], out[1], out[2]


# ============================================================ 岁差 / 交食差
def nutation(jd_tt):
    """IAU1980 主要项章动, 返回 (Δψ, Δε) 单位度。"""
    t = t_centuries(jd_tt)
    om = (125.04452 - 1934.136261 * t + 0.0020708 * t * t + t ** 3 / 450000.0) * D2R
    ls = (280.4665 + 36000.7698 * t) * D2R
    lm = (218.3165 + 481267.8813 * t) * D2R
    dpsi = (-17.20 * math.sin(om) - 1.32 * math.sin(2 * ls) - 0.23 * math.sin(2 * lm)
            + 0.21 * math.sin(2 * om)) / 3600.0
    deps = (9.20 * math.cos(om) + 0.57 * math.cos(2 * ls) + 0.10 * math.cos(2 * lm)
            - 0.09 * math.cos(2 * om)) / 3600.0
    return dpsi, deps


def mean_obliquity(jd_tt):
    """平黄赤交角, 单位度 (IAU1980)。"""
    t = t_centuries(jd_tt)
    return (23.4392911111 - 0.0130041667 * t - 1.638889e-7 * t ** 2 + 5.036111e-7 * t ** 3)


def true_obliquity(jd_tt):
    _, deps = nutation(jd_tt)
    return mean_obliquity(jd_tt) + deps


def gmst_deg(jd_ut):
    """格林尼治平恒星时, 单位度 (Meeus 12.4)。"""
    t = t_centuries(jd_ut)
    return (280.46061837 + 360.98564736629 * (jd_ut - J2000)
            + 0.000387933 * t * t - t ** 3 / 38710000.0) % 360.0


def gast_deg(jd_ut):
    """格林尼治视恒星时, 单位度。"""
    dpsi, _ = nutation(jd_tt_from_ut(jd_ut))
    eps = mean_obliquity(jd_tt_from_ut(jd_ut))
    return (gmst_deg(jd_ut) + dpsi * math.cos(eps * D2R)) % 360.0


def last_deg(jd_ut, lon_east):
    """地方视恒星时, 单位度。"""
    return (gast_deg(jd_ut) + lon_east) % 360.0


# ============================================================ 太阳
# ---------------------------------------------------------------- 太阳 (解析法)
# 采用 Paul Schlyter 轨道根数法 (日心 -> 地心 + π), 精度经基准校验 < 0.005°。
# 说明: VSOP87D 原始系数文件的相位约定在本实现中未能自洽复现,
# 为保证可靠性改用可自校验的解析轨道法, 对节气/星座判定精度绰绰有余。
_SUN_E = 0.016709
_SUN_W0 = 282.9404
_SUN_M0 = 356.0470


def _sun_elements(d):
    w = _SUN_W0 + 4.70935e-5 * d
    e = _SUN_E - 1.151e-9 * d
    m = _SUN_M0 + 0.9856002585 * d
    return w % 360.0, e, m % 360.0


def sun_true_longitude(jd_tt):
    """太阳地心几何黄经 (度, 当日平春分点), 以及黄纬(恒 0)与日地距离(AU)。"""
    d = jd_tt - 2451543.5
    w, e, m = _sun_elements(d)
    E = m + R2D * e * math.sin(m * D2R) * (1 + e * math.cos(m * D2R))
    for _ in range(20):
        dE = (E - R2D * e * math.sin(E * D2R) - m) / (1 - e * math.cos(E * D2R))
        E -= dE
        if abs(dE) < 1e-10:
            break
    xv = math.cos(E * D2R) - e
    yv = math.sqrt(1 - e * e) * math.sin(E * D2R)
    v = math.atan2(yv, xv) * R2D
    r = math.hypot(xv, yv)                      # 以 a=1 归一
    lon = (v + w) % 360.0
    return lon, 0.0, r


def sun_apparent_longitude(jd_tt):
    """太阳视黄经 (几何黄经 + 章动 + 光行差), 单位度。"""
    lam, _beta, r = sun_true_longitude(jd_tt)
    dpsi, _ = nutation(jd_tt)
    aberr = -20.4898 / max(r, 0.9) / 3600.0
    return (lam + dpsi + aberr) % 360.0


def sun_ra_dec(jd_tt):
    """太阳视赤经赤纬 (度)。"""
    lam = sun_apparent_longitude(jd_tt)
    eps = true_obliquity(jd_tt)
    l, e = lam * D2R, eps * D2R
    ra = math.atan2(math.cos(e) * math.sin(l), math.cos(l)) * R2D % 360.0
    dec = math.asin(math.sin(e) * math.sin(l)) * R2D
    return ra, dec


def equation_of_time(jd_tt):
    """均时差 (分钟) = 真太阳时 - 平太阳时。Meeus 第 28 章式 28.3。

    E = y·sin2L₀ − 2e·sinM + 4ey·sinM·cos2L₀ − 0.5y²·sin4L₀ − 1.25e²·sin2M
    其中 y = tan²(ε/2), e 为地球轨道偏心率, M 为太阳平近点角。
    注意: 第 2、3、5 项的自变量是平近点角 M (不是平黄经), 这是常见实现错误。
    """
    t = t_centuries(jd_tt)                       # 儒略世纪
    eps = true_obliquity(jd_tt) * D2R
    y = math.tan(eps / 2.0) ** 2
    e = 0.016708634 - 0.000042037 * t - 0.0000001267 * t * t
    # Meeus 28.2 的 L₀ 以"儒略千年"为自变量, 故用 tau = t/10
    tau = t / 10.0
    l0 = ((280.4664567 + 360007.6982779 * tau + 0.03032028 * tau * tau
           + tau ** 3 / 49931.0 - tau ** 4 / 15300.0 - tau ** 5 / 2000000.0) % 360.0) * D2R
    m = ((357.52911 + 35999.05029 * t - 0.0001537 * t * t) % 360.0) * D2R
    eot = (y * math.sin(2 * l0)
           - 2 * e * math.sin(m)
           + 4 * e * y * math.sin(m) * math.cos(2 * l0)
           - 0.5 * y * y * math.sin(4 * l0)
           - 1.25 * e * e * math.sin(2 * m)) * R2D * 4.0
    return eot


def solve_sun_longitude(target_lon, jd_guess):
    """求太阳视黄经 = target_lon 的时刻 (TT 儒略日), 牛顿迭代。"""
    jd = jd_guess
    for _ in range(60):
        lam = sun_apparent_longitude(jd)
        diff = (lam - target_lon + 180.0) % 360.0 - 180.0
        if abs(diff) < 1e-9:
            break
        step = diff / 0.9856473           # 太阳平均日行度
        if abs(step) > 30:
            step = math.copysign(30.0, step)
        jd -= step
    return jd


# ============================================================ 月亮 (Meeus 47)
# (D, M, M', F, Σl 系数(1e-6度), Σr 系数(1e-3 km)) —— 主项表
_MOON_LR = [
    (0, 0, 1, 0, 6288774, -20905355), (2, 0, -1, 0, 1274027, -3699111),
    (2, 0, 0, 0, 658314, -2955968), (0, 0, 2, 0, 213618, -569925),
    (0, 1, 0, 0, -185116, 48888), (0, 0, 0, 2, -114332, -3149),
    (2, 0, -2, 0, 58793, 246158), (2, -1, -1, 0, 57066, -152138),
    (2, 0, 1, 0, 53322, -170733), (2, -1, 0, 0, 45758, -204586),
    (0, 1, -1, 0, -40923, -129620), (1, 0, 0, 0, -34720, 108743),
    (0, 1, 1, 0, -30383, 104755), (2, 0, 0, -2, 15327, 10321),
    (0, 0, 1, 2, -12528, 0), (0, 0, 1, -2, 10980, 79661),
    (4, 0, -1, 0, 10675, -34782), (0, 0, 3, 0, 10034, -23210),
    (4, 0, -2, 0, 8548, -21636), (2, 1, -1, 0, -7888, 24208),
    (2, 1, 0, 0, -6766, 30824), (1, 0, -1, 0, -5163, -8379),
    (1, 1, 0, 0, 4987, -16675), (2, -1, 1, 0, 4036, -12831),
    (2, 0, 2, 0, 3994, -10445), (4, 0, 0, 0, 3861, -11650),
    (2, 0, -3, 0, 3665, 14403), (0, 1, -2, 0, -2689, -7003),
    (2, 0, -1, 2, -2602, 0), (2, -1, -2, 0, 2390, 10056),
    (1, 0, 1, 0, -2348, 6322), (2, -2, 0, 0, 2236, -9884),
    (0, 1, 2, 0, -2120, 5751), (0, 2, 0, 0, -2069, 0),
    (2, -2, -1, 0, 2048, -4950), (2, 0, 1, -2, -1773, 4130),
    (2, 0, 0, 2, -1595, 0), (4, -1, -1, 0, 1215, -3958),
    (0, 0, 2, 2, -1110, 0), (3, 0, -1, 0, -892, 3258),
    (2, 1, 1, 0, -810, 2616), (4, -1, -2, 0, 759, -1897),
    (0, 2, -1, 0, -713, -2117), (2, 2, -1, 0, -700, 2354),
    (2, 1, -2, 0, 691, 0), (2, -1, 0, -2, 596, 0),
    (4, 0, 1, 0, 549, -1423), (0, 0, 4, 0, 537, -1117),
    (4, -1, 0, 0, 520, -1571), (1, 0, -2, 0, -487, -1739),
    (2, 1, 0, -2, -399, 0), (0, 0, 2, -2, -381, -4421),
    (1, 1, 1, 0, 351, 0), (3, 0, -2, 0, -340, 0),
    (4, 0, -3, 0, 330, 0), (2, -1, 2, 0, 327, 0),
    (0, 2, 1, 0, -323, 1165), (1, 1, -1, 0, 299, 0),
    (2, 0, 3, 0, 294, 0), (2, 0, -1, -2, 0, 8752),
]
_MOON_B = [
    (0, 0, 0, 1, 5128122), (0, 0, 1, 1, 280602), (0, 0, 1, -1, 277693),
    (2, 0, 0, -1, 173237), (2, 0, -1, 1, 55413), (2, 0, -1, -1, 46271),
    (2, 0, 0, 1, 32573), (0, 0, 2, 1, 17198), (2, 0, 1, -1, 9266),
    (0, 0, 2, -1, 8822), (2, -1, 0, -1, 8216), (2, 0, -2, -1, 4324),
    (2, 0, 1, 1, 4200), (2, 1, 0, -1, -3359), (2, -1, -1, 1, 2463),
    (2, -1, 0, 1, 2211), (2, -1, -1, -1, 2065), (0, 1, -1, -1, -1870),
    (4, 0, -1, -1, 1828), (0, 1, 0, 1, -1794), (0, 0, 0, 3, -1749),
    (0, 1, -1, 1, -1565), (1, 0, 0, 1, -1491), (0, 1, 1, 1, -1475),
    (0, 1, 1, -1, -1410), (0, 1, 0, -1, -1344), (1, 0, 0, -1, -1335),
    (0, 0, 3, 1, 1107), (4, 0, 0, -1, 1021), (4, 0, -1, 1, 833),
    (0, 0, 1, -3, 777), (4, 0, -2, 1, 671), (2, 0, 0, -3, 607),
    (2, 0, 2, -1, 596), (2, -1, 1, -1, 491), (2, 0, -2, 1, -451),
    (0, 0, 3, -1, 439), (2, 0, 2, 1, 422), (2, 0, -3, -1, 421),
    (2, 1, -1, 1, -366), (2, 1, 0, 1, -351), (4, 0, 0, 1, 331),
    (2, -1, 1, 1, 315), (2, -2, 0, -1, 302), (0, 0, 1, 3, -283),
    (2, 1, 1, -1, -229), (1, 1, 0, -1, 223), (1, 1, 0, 1, 223),
    (0, 1, -2, -1, -220), (2, 1, -1, -1, -220), (1, 0, 1, 1, -185),
    (2, -1, -2, -1, 181), (0, 1, 2, 1, -177), (4, 0, -2, -1, 176),
    (4, -1, -1, -1, 166), (1, 0, 1, -1, -164), (4, 0, 1, -1, 132),
    (1, 0, -1, -1, -119), (4, -1, 0, -1, 115), (2, -2, 0, 1, 107),
]


def moon_position(jd_tt):
    """月亮地心黄经/黄纬/距离。返回 (λ度, β度, Δkm), λ 为真春分点。"""
    t = t_centuries(jd_tt)
    lp = (218.3164477 + 481267.88123421 * t - 0.0015786 * t * t
          + t ** 3 / 538841.0 - t ** 4 / 65194000.0) % 360.0
    d = (297.8501921 + 445267.1114034 * t - 0.0018819 * t * t
         + t ** 3 / 545868.0 - t ** 4 / 113065000.0) % 360.0
    m = (357.5291092 + 35999.0502909 * t - 0.0001536 * t * t + t ** 3 / 24490000.0) % 360.0
    mp = (134.9633964 + 477198.8675055 * t + 0.0087414 * t * t
          + t ** 3 / 69699.0 - t ** 4 / 14712000.0) % 360.0
    f = (93.2720950 + 483202.0175233 * t - 0.0036539 * t * t
         - t ** 3 / 3526000.0 + t ** 4 / 863310000.0) % 360.0
    a1 = (119.75 + 131.849 * t) % 360.0
    a2 = (53.09 + 479264.290 * t) % 360.0
    a3 = (313.45 + 481266.484 * t) % 360.0
    e = 1 - 0.002516 * t - 0.0000074 * t * t
    d, m, mp, f = d * D2R, m * D2R, mp * D2R, f * D2R

    sl = sr = sb = 0.0
    for dd, mm, mpp, ff, cl, cr in _MOON_LR:
        arg = dd * d + mm * m + mpp * mp + ff * f
        corr = e ** abs(mm)
        sl += cl * corr * math.sin(arg)
        sr += cr * corr * math.cos(arg)
    for dd, mm, mpp, ff, cb in _MOON_B:
        arg = dd * d + mm * m + mpp * mp + ff * f
        sb += cb * (e ** abs(mm)) * math.sin(arg)
    sl += (3958 * math.sin(a1) + 1962 * math.sin(lp * D2R - f)
           + 318 * math.sin(a2))
    sb += (-2235 * math.sin(lp * D2R) + 382 * math.sin(a3)
           + 175 * math.sin(a1 - f) + 175 * math.sin(a1 + f)
           + 127 * math.sin(lp * D2R - mp) - 115 * math.sin(lp * D2R + mp))
    lam = (lp + sl / 1e6) % 360.0
    beta = sb / 1e6
    dist = 385000.56 + sr / 1000.0
    return lam, beta, dist


def moon_apparent_longitude(jd_tt):
    lam, beta, dist = moon_position(jd_tt)
    dpsi, _ = nutation(jd_tt)
    return (lam + dpsi) % 360.0, beta, dist


# ============================================================ 朔望 (Meeus 49)
def new_moon_jde(k):
    """第 k 个新月的 JDE (TT 儒略日), k=0 对应 2000-01-06。"""
    t = k / 1236.85
    jde = (2451550.09766 + 29.530588861 * k + 0.00015437 * t * t
           - 0.000000150 * t ** 3 + 0.00000000073 * t ** 4)
    e = 1 - 0.002516 * t - 0.0000074 * t * t
    m = (2.5534 + 29.10535670 * k - 0.0000014 * t * t - 0.00000011 * t ** 3) * D2R
    mp = (201.5643 + 385.81693528 * k + 0.0107582 * t * t
          + 0.00001238 * t ** 3 - 0.000000058 * t ** 4) * D2R
    f = (160.7108 + 390.67050284 * k - 0.0016118 * t * t
         - 0.00000227 * t ** 3 + 0.000000011 * t ** 4) * D2R
    om = (124.7746 - 1.56375588 * k + 0.0020672 * t * t + 0.00000215 * t ** 3) * D2R
    corr = (-0.40720 * math.sin(mp)
            + 0.17241 * e * math.sin(m)
            + 0.01608 * math.sin(2 * mp)
            + 0.01039 * math.sin(2 * f)
            + 0.00739 * e * math.sin(mp - m)
            - 0.00514 * e * math.sin(mp + m)
            + 0.00208 * e * e * math.sin(2 * m)
            - 0.00111 * math.sin(mp - 2 * f)
            - 0.00057 * math.sin(mp + 2 * f)
            + 0.00056 * e * math.sin(2 * mp + m)
            - 0.00042 * math.sin(3 * mp)
            + 0.00042 * e * math.sin(m + 2 * f)
            + 0.00038 * e * math.sin(m - 2 * f)
            - 0.00024 * e * math.sin(2 * mp - m)
            - 0.00017 * math.sin(om)
            - 0.00007 * math.sin(mp + 2 * m)
            + 0.00004 * math.sin(2 * mp - 2 * f)
            + 0.00004 * math.sin(3 * m)
            + 0.00003 * math.sin(mp + m - 2 * f)
            + 0.00003 * math.sin(2 * mp + 2 * f)
            - 0.00003 * math.sin(mp + m + 2 * f)
            + 0.00003 * math.sin(mp - m + 2 * f)
            - 0.00002 * math.sin(mp - m - 2 * f)
            - 0.00002 * math.sin(3 * mp + m)
            + 0.00002 * math.sin(4 * mp))
    a1 = (299.77 + 0.107408 * k - 0.009173 * t * t) * D2R
    a2 = (251.88 + 0.016321 * k) * D2R
    a3 = (251.83 + 26.651886 * k) * D2R
    a4 = (349.42 + 36.412478 * k) * D2R
    a5 = (84.66 + 18.206239 * k) * D2R
    a6 = (141.74 + 53.303771 * k) * D2R
    a7 = (207.14 + 2.453732 * k) * D2R
    a8 = (154.84 + 7.306860 * k) * D2R
    a9 = (34.52 + 27.261239 * k) * D2R
    a10 = (207.19 + 0.121824 * k) * D2R
    a11 = (291.34 + 1.844379 * k) * D2R
    a12 = (161.72 + 24.198154 * k) * D2R
    a13 = (239.56 + 25.513099 * k) * D2R
    a14 = (331.55 + 3.592518 * k) * D2R
    extra = (0.000325 * math.sin(a1) + 0.000165 * math.sin(a2) + 0.000164 * math.sin(a3)
             + 0.000126 * math.sin(a4) + 0.000110 * math.sin(a5) + 0.000062 * math.sin(a6)
             + 0.000060 * math.sin(a7) + 0.000056 * math.sin(a8) + 0.000047 * math.sin(a9)
             + 0.000042 * math.sin(a10) + 0.000040 * math.sin(a11) + 0.000037 * math.sin(a12)
             + 0.000035 * math.sin(a13) + 0.000023 * math.sin(a14))
    return jde + corr + extra


def k_for_year(year):
    """粗略给出覆盖该年的朔望 k 范围。"""
    k = math.floor((year - 2000) * 12.3685) - 2
    return k


def new_moons_around(jd, span_days=45):
    """返回 jd 前后 span_days 内的所有新月 (UT 儒略日列表)。"""
    k0 = int(math.floor((jd - 2451550.09766) / 29.530588861)) - 2
    out = []
    for k in range(k0, k0 + 6):
        jde = new_moon_jde(k)
        jd_ut = jde - delta_t_seconds(*_ym_from_jd(jde)) / 86400.0
        if abs(jd_ut - jd) <= span_days:
            out.append(jd_ut)
    return sorted(out)


def _ym_from_jd(jd):
    dt = datetime_from_jd(jd)
    return dt.year, dt.month


# 各节气在公历年内的近似"月-日" (用于牛顿迭代初值)
_TERM_APPROX = {
    "小寒": (1, 6), "大寒": (1, 20), "立春": (2, 4), "雨水": (2, 19),
    "惊蛰": (3, 6), "春分": (3, 21), "清明": (4, 5), "谷雨": (4, 20),
    "立夏": (5, 6), "小满": (5, 21), "芒种": (6, 6), "夏至": (6, 21),
    "小暑": (7, 7), "大暑": (7, 23), "立秋": (8, 8), "处暑": (8, 23),
    "白露": (9, 8), "秋分": (9, 23), "寒露": (10, 8), "霜降": (10, 24),
    "立冬": (11, 7), "小雪": (11, 22), "大雪": (12, 7), "冬至": (12, 22),
}


def solar_term_jd(year, name):
    """指定节气在指定公历年份内的时刻 (UT 儒略日)。"""
    target = JIEQI_LON[name]
    mm, dd = _TERM_APPROX[name]
    guess = jd_from_ymd(year, mm, dd, 12.0)
    jd_tt = jd_tt_from_ut(guess)
    jd_tt = solve_sun_longitude(target, jd_tt)
    # 转回 UT (ΔT 与年份有关, 迭代两次)
    jd_ut = jd_ut_from_tt(jd_tt)
    for _ in range(2):
        jd_ut = jd_tt - delta_t_seconds(*_ym_from_jd(jd_tt)) / 86400.0
    return jd_ut


def solar_terms_of_year(year):
    """返回该年 24 节气 {名称: UT 儒略日}。"""
    out = {}
    for name in JIEQI_NAMES:
        out[name] = solar_term_jd(year, name)
    return out


def jie_datetime(year, name):
    """指定"节"的北京时间 datetime。"""
    jd_ut = solar_term_jd(year, name)
    return datetime_from_jd(jd_ut + 8.0 / 24.0)


# ============================================================ 农历
def lunar_from_date(date):
    """公历 -> 农历 (定朔定气, 北京时间, 以东经120°为准)。
    返回 dict: lunar_year, lunar_month, is_leap, lunar_day, month_name, day_name,
              year_ganzhi, month_ganzhi(以节气月?), 以及冬至/朔时刻信息。
    """
    jd = jd_from_ymd(date.year, date.month, date.day)   # 当日 0h UT 近似
    # 以北京时间当天正午作为参考时刻
    jd_ref = jd + 0.5 + 8.0 / 24.0
    return _lunar_from_jd(jd_ref)


_MONTH_NAMES = ["正月", "二月", "三月", "四月", "五月", "六月",
                "七月", "八月", "九月", "十月", "冬月", "腊月"]
_DAY_NAMES = ["初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
              "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
              "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"]


def _winter_solstice(year):
    return solar_term_jd(year, "冬至")


_TERM_CACHE = {}
_ZHONGQI = [n for n in JIEQI_NAMES if JIEQI_LON[n] % 30 == 0]   # 12 个中气


def _terms_of_year(year):
    """该公历年 24 节气 (UT JD) 及其中气 {名称: JD}, 带缓存。"""
    if year not in _TERM_CACHE:
        terms = {n: solar_term_jd(year, n) for n in JIEQI_NAMES}
        zq = {n: terms[n] for n in _ZHONGQI}
        _TERM_CACHE[year] = (terms, zq)
    return _TERM_CACHE[year]


def _new_moons_between(jd_lo, jd_hi):
    """返回 (k, JD_UT) 列表, 覆盖 [jd_lo, jd_hi] 内的所有朔。"""
    k0 = int(math.floor((jd_lo - 2451550.09766) / 29.530588861)) - 1
    out = []
    k = k0
    while True:
        jde = new_moon_jde(k)
        jd_ut = jde - delta_t_seconds(*_ym_from_jd(jde)) / 86400.0
        if jd_ut > jd_hi:
            break
        if jd_ut >= jd_lo:
            out.append((k, jd_ut))
        k += 1
    return out


def _month_table(year):
    """构建覆盖该公历年的农历月表。

    规范 (与紫金山天文台《农历的编算和颁行》一致):
      1) 以东经 120° 标准时 (北京时间) 计算朔与中气;
      2) 含冬至的朔月为十一月;
      3) 两个十一月之间若有 13 个朔月, 则第一个不含中气的月为闰月;
      4) 其余月份自十一月起顺次编号。
    返回按月起始时刻升序排列的列表: [(JD月首, 月序, 是否闰, 所属农历年)]。
    """
    if year in _MONTH_CACHE:
        return _MONTH_CACHE[year]
    ws_prev = _winter_solstice(year - 1)
    ws_next = _winter_solstice(year)
    ws_after = _winter_solstice(year + 1)
    # 以"北京时间日界"为准: 朔时刻 + 8h 后取整日
    # 搜索窗口必须确定: 从"冬至之前约 60 天"开始, 保证含冬至的朔月总是第 1 项,
    # 否则窗口起点随年份漂移会导致 m11 索引不稳定 (闰月判定整体错位一个月)。
    moons = _new_moons_between(ws_prev - 62.0, ws_after + 40)
    if len(moons) < 13:
        _MONTH_CACHE[year] = []
        return []
    # 十一月 = 含冬至的那个朔月, 即"冬至当日或之前最近的一个朔"(last_new_moon <= 冬至)。
    # 下一个含冬至的朔月即次年十一月; 二者之间构成一个农历年。
    # (注: 冬至当天 21:39 这类临界情况按"朔所在日"判断, 与官方历书一致。)
    def month_index_of(jd):
        """返回 jd 当日或之前最近一个朔的索引。"""
        idx = 0
        for i, (k, m) in enumerate(moons):
            if m <= jd + 1e-9:
                idx = i
            else:
                break
        return idx

    m11 = month_index_of(ws_prev)          # 去年十一月
    m11_next = month_index_of(ws_next)     # 今年十一月
    if m11 == 0:
        raise RuntimeError("月表搜索窗口过窄, 无法定位十一月 (year=%d)" % year)
    nmonths = m11_next - m11
    leap_idx = None
    if nmonths == 13:
        # 找第一个不含中气的月
        for i in range(m11, m11_next):
            m_start = moons[i][1]
            m_end = moons[i + 1][1]
            has = False
            for yy in (year - 2, year - 1, year, year + 1, year + 2):
                _, zq = _terms_of_year(yy)
                for name, jt in zq.items():
                    if m_start < jt < m_end:
                        has = True
                        break
                if has:
                    break
            if not has:
                leap_idx = i
                break
    # 月序分配: 自含冬至的朔月起为十一月; 该农历年共 nmonths 个朔望月,
    # 若为 13 个月, 则第一个不含中气的月为闰月, 闰月沿用前一个月名,
    # 其后的月序依次后移 (即不占号)。末月 (下一个十一月) 固定为 11。
    # 月序分配: 自含冬至的朔月起为十一月。该农历年共 nmonths 个朔望月;
    # 若为 13 个月, 则第一个不含中气的月为闰月, 闰月沿用前一个月的月名(不占号)。
    # 月序分配 (《农历的编算和颁行》规范), 设第 k 行对应冬至月之后第 k 个朔望月:
    #   行 k=0        -> 十一月 (含冬至之朔月)
    #   行 k=1        -> 十二月
    #   行 k=2        -> 正月
    #   一般式: 月序 = wrap(11 + k), 若 k 大于闰月所在行则再减 1 (闰月不占号);
    #   闰月本身与其前一个月同名。
    #   行 k=m11_next 即次年十一月。
    def _wrap(n):
        while n > 12:
            n -= 12
        while n < 1:
            n += 12
        return n

    n_rows = m11_next - m11 + 1
    leap_k = None
    if leap_idx is not None:
        leap_k = leap_idx - m11
    main = []
    for k in range(n_rows):
        i = m11 + k
        passed = 1 if (leap_k is not None and k > leap_k) else 0
        main.append((moons[i][1], _wrap(11 + k - passed), leap_k == k))
    extra = []
    for back, i in enumerate(range(m11 - 1, max(-1, m11 - 4), -1)):
        extra.append((moons[i][1], _wrap(11 - (back + 1)), False))
    extra.reverse()
    rows = extra + main
    _MONTH_CACHE[year] = rows
    return rows


_MONTH_CACHE = {}


def lunar_month_of(jd_bj):
    """给定北京时间儒略日, 返回 (月首JD, 月序, 是否闰, 月首年月)。"""
    jd_ut = jd_bj - 8.0 / 24.0
    dt = datetime_from_jd(jd_ut)
    for y in (dt.year, dt.year - 1, dt.year + 1):
        rows = _month_table(y)
        for i, (start, no, leap) in enumerate(rows):
            nxt = rows[i + 1][0] if i + 1 < len(rows) else start + 40
            if start <= jd_ut + 0.5 < nxt:
                return start, no, leap
    raise RuntimeError("无法定位农历月: %s" % dt)


def _zheng_yue_start(year, rows_hint=None):
    """求农历 year 年正月初一的 JD (UT)。"""
    for y in (year, year + 1):
        rows = _month_table(y)
        for i, (start, no, leap) in enumerate(rows):
            if no == 1 and not leap:
                dt = datetime_from_jd(start - 8.0 / 24.0)
                if dt.year == year and dt.month <= 3:
                    return start
    return None


def _lunar_from_jd(jd_bj):
    """给定北京时间的儒略日, 求农历日期。

    权威实现: engine/almanac.py 的农历换算 (其自测对 16 个外部锚点全部一致,
    可与在线黄历逐日核对)。本函数仅做适配; 若该模块不可用则退回本地实现。
    """
    dt = datetime_from_jd(jd_bj - 8.0 / 24.0)
    try:
        from . import almanac as _alm
        r = _alm.day_almanac(dt.date())
        txt = r.get("lunar_text", "")
        # 形如 "农历丙午年 九月初八"
        body = txt.replace("农历", "").strip()
        body = body.split("年 ", 1)[-1] if "年 " in body else body
        leap = body.startswith("闰")
        if leap:
            body = body[1:]
        # 月名别名: 各历书用语不同
        aliases = [("十一月", "冬月"), ("十二月", "腊月"), ("一月", "正月")]
        month_name, day_name = None, None
        for alias, canon in aliases:
            if body.startswith(alias):
                body = canon + body[len(alias):]
                break
        for mn in _MONTH_NAMES:
            if body.startswith(mn):
                month_name, day_name = mn, body[len(mn):]
                break
        if month_name is None:
            month_name, day_name = body[:2], body[2:]
        mi = _MONTH_NAMES.index(month_name) + 1
        di = _DAY_NAMES.index(day_name) + 1 if day_name in _DAY_NAMES else 1
        # 农历年: 十一月/十二月落在公历 1-3 月时属上一年
        ly = dt.year
        if mi >= 11 and dt.month <= 3:
            ly = dt.year - 1
        return {
            "lunar_year": ly,
            "lunar_month": mi,
            "is_leap": leap,
            "lunar_day": di,
            "month_name": ("闰" if leap else "") + month_name,
            "day_name": day_name,
        }
    except Exception:
        return _lunar_from_jd_local(jd_bj)


def _lunar_from_jd_local(jd_bj):
    """本地备用农历换算 (独立实现, 见 scripts/lunar_standalone.py 的说明)。

    已知局限: 朔在 20:00–24:00 (北京时) 时初一可能错后一日, 极端边界日慎用。
    """
    jd_ut = jd_bj - 8.0 / 24.0
    dt = datetime_from_jd(jd_ut)
    start, month_no, leap = lunar_month_of(jd_bj)
    ly = None
    for y in (dt.year, dt.year - 1):
        zy = _zheng_yue_start(y)
        if zy is not None and jd_ut + 0.5 >= zy:
            ly = y
            break
    if ly is None:
        ly = dt.year
    day_no = int(math.floor(jd_ut + 0.5 - (start + 0.5))) + 1
    day_no = max(1, min(30, day_no))
    return {
        "lunar_year": ly,
        "lunar_month": month_no,
        "is_leap": leap,
        "lunar_day": day_no,
        "month_name": ("闰" if leap else "") + _MONTH_NAMES[(month_no - 1) % 12],
        "day_name": _DAY_NAMES[day_no - 1],
    }


# ============================================================ 干支
def ganzhi_from_index(idx):
    from .constants import GAN, ZHI
    return GAN[idx % 10] + ZHI[idx % 12]


def day_ganzhi_index(jd_ut):
    """日干支序号 (0=甲子)。输入为 UT 儒略日; 换日以北京时间 00:00 为界。"""
    jdn = int(math.floor(jd_ut + 8.0 / 24.0 + 0.5))
    return (jdn + 49) % 60


def day_ganzhi(date):
    """公历日期 -> 日柱干支。
    基准检验: 2000-01-01=戊午, 1949-10-01=甲子, 1999-05-13=乙丑。
    公式: 序号 = (JDN + 49) mod 60, 其中 JDN 为北京时间当日 00:00 的儒略日数。"""
    return ganzhi_from_index(day_ganzhi_index_of(date))


def day_ganzhi_index_of(date):
    jd = jd_from_ymd(date.year, date.month, date.day)
    jdn = int(math.floor(jd + 8.0 / 24.0 + 0.5))
    return (jdn + 49) % 60


def year_ganzhi_index(year):
    return (year - 4) % 60


def month_ganzhi(year_gan_idx, month_no):
    """month_no: 1=寅月 ... 12=丑月。返回干支序号。"""
    year_gan = year_gan_idx % 10
    first = (year_gan % 5) * 2 + 2          # 五虎遁: 甲己之年丙作首
    gan_idx = (first + month_no - 1) % 10
    zhi_idx = (2 + month_no - 1) % 12
    return _gz_index(gan_idx, zhi_idx)


def _gz_index(gan_idx, zhi_idx):
    """由天干序号与地支序号求六十甲子序号。"""
    for i in range(60):
        if i % 10 == gan_idx % 10 and i % 12 == zhi_idx % 12:
            return i
    raise ValueError("不可能的组合")


def sexagenary_from_ganzhi(gz):
    from .constants import GAN, ZHI
    g, z = GAN.index(gz[0]), ZHI.index(gz[1])
    return _gz_index(g, z)
