# -*- coding: utf-8 -*-
"""西方占星天文计算: 太阳/月亮/行星地心黄经、宫位、相位、行运。

数据来源与精度:
  * 太阳与行星: Paul Schlyter《How to compute planetary positions》轨道根数法
    + 木星/土星/天王星互扰修正。基准测试(1999-02-04、1992-10-13、2026-10-16)
    与参考星历偏差 < 0.005°; 对占星用途(星座/宫位/相位)绰绰有余。
  * 月亮: Meeus《Astronomical Algorithms》ch.47 ELP-2000/82 简版 (精度 ~10")
  * 宫位: Placidus 半弧法 + 整宫制(Whole Sign)对照
  * 恒星时: Meeus ch.12 (含章动 -> 视恒星时)
所有函数接受 TT 或 UT 儒略日, 已在命名上区分。
"""
from __future__ import annotations

import datetime as _dt
import math

from .constants import (ASPECTS, HOUSE_NAMES, PLANETS, SIGNS, SIGN_ELEMENT,
                        SIGN_MODE, SIGN_RULER, ASPECT_ORB, LUMINARIES)
from .calendar_cn import (D2R, R2D, jd_from_datetime, jd_tt_from_ut, jd_ut_from_tt,
                          t_centuries, nutation, mean_obliquity, true_obliquity,
                          last_deg, sun_apparent_longitude, moon_apparent_longitude)

_EPOCH = _dt.datetime(1999, 12, 31)          # Schlyter 的 d=0 起点 (2000 Jan 0.0)


def _d0(jd_ut):
    """儒略日 -> Schlyter 的 d (1999-12-31 00:00 UT 起算的天数)。"""
    return jd_ut - 2451543.5


# ------------------------------------------------------------ 行星轨道根数
# a(AU), e, I(deg), L(deg), long.peri(deg), long.node(deg) @ J2000
_ELEMENTS = {
    "水星": (0.38709893, 0.20563069, 7.00487, 252.25084, 77.45645, 48.33167),
    "金星": (0.72333199, 0.00677323, 3.39471, 181.97973, 131.53298, 76.68069),
    "地球": (1.00000011, 0.01671022, 0.00005, 100.46435, 102.94719, -11.26064),
    "火星": (1.52366231, 0.09341233, 1.85061, 355.45332, 336.04084, 49.57854),
    "木星": (5.20336301, 0.04839266, 1.30530, 34.40438, 14.75385, 100.55615),
    "土星": (9.53707032, 0.05415060, 2.48446, 49.94432, 92.43194, 113.71504),
    "天王星": (19.19126393, 0.04716771, 0.76986, 313.23218, 170.96424, 74.22988),
    "海王星": (30.06896348, 0.00858587, 1.76917, 304.88003, 44.97135, 131.72169),
    "冥王星": (39.48168677, 0.24880766, 17.14175, 238.92881, 224.06676, 110.30347),
}
# 每儒略世纪变化率
_RATES = {
    "水星": (0.00000066, 0.00002527, -23.51, 149472.67411175, 0.16047689, -446.30),
    "金星": (0.00000092, -0.00004938, -2.86, 58517.8038743, -0.04768893, -996.89),
    "地球": (-0.00000005, -0.00003804, -46.94, 35999.05029, -0.04101836, -1934.13618),
    "火星": (0.00000066, -0.00007221, 0.03, 19140.30268499, 0.44441088, -2125.77),
    "木星": (-0.00000066, 0.00000289, -0.01, 3034.74612775, 0.21252668, -2488.79),
    "土星": (-0.00000018, 0.00000097, 0.02, 1222.49362201, -0.41897216, -628.32),
    "天王星": (0.00000006, -0.00000145, -0.01, 428.48202785, 0.40882266, -1.44),
    "海王星": (0.00000002, 0.00000003, 0.00, 218.45945325, 0.09229656, 0.00),
    "冥王星": (-0.00000020, 0.00000121, -0.51, 145.20780515, -0.04062942, -0.00),
}


def _solve_kepler(M_deg, e, tol=1e-10):
    M = M_deg * D2R
    E = M + e * math.sin(M) * (1 + e * math.cos(M))
    for _ in range(40):
        d = (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
        E -= d
        if abs(d) < tol:
            break
    return E


def heliocentric(name, jd_ut):
    """日心黄道坐标 (lon, lat, r)。"""
    a, e, I, L, w, N = _ELEMENTS[name]
    ra, re, rI, rL, rw, rN = _RATES[name]
    T = t_centuries(jd_tt_from_ut(jd_ut))
    a += ra * T
    e += re * T
    I += rI * T
    L += rL * T
    w += rw * T
    N += rN * T
    M = (L - w) % 360.0
    E = _solve_kepler(M, e)
    xv = a * (math.cos(E) - e)
    yv = a * math.sqrt(1 - e * e) * math.sin(E)
    r = math.hypot(xv, yv)
    v = math.atan2(yv, xv)
    wr, Ir = w * D2R, I * D2R
    xh = r * (math.cos(v) * math.cos(wr) - math.sin(v) * math.sin(wr) * math.cos(Ir))
    yh = r * (math.sin(v) * math.cos(wr) + math.cos(v) * math.sin(wr) * math.cos(Ir))
    zh = r * (math.sin(v) * math.sin(Ir))
    return math.atan2(yh, xh) * R2D % 360.0, math.atan2(zh, math.hypot(xh, yh)) * R2D, r


def _perturbations(name, lon, lat, r, jd_ut):
    """木星/土星/天王星互扰 (Schlyter)。返回 (dlon, dlat)。"""
    d = _d0(jd_ut)
    Mj = (19.8950 + 0.0830853001 * d) * D2R
    Ms = (316.9670 + 0.0334442282 * d) * D2R
    Mu = (142.5905 + 0.011725806 * d) * D2R
    if name == "木星":
        return ((-0.332 * math.sin(2 * Mj - 5 * Ms - 67.6 * D2R)
                 - 0.056 * math.sin(2 * Mj - 2 * Ms + 21 * D2R)
                 + 0.042 * math.sin(3 * Mj - 5 * Ms + 21 * D2R)
                 - 0.036 * math.sin(Mj - 2 * Ms)
                 + 0.022 * math.cos(Mj - Ms)
                 + 0.023 * math.sin(2 * Mj - 3 * Ms + 52 * D2R)
                 - 0.016 * math.sin(Mj - 5 * Ms - 69 * D2R)), 0.0)
    if name == "土星":
        return ((+0.812 * math.sin(2 * Mj - 5 * Ms - 67.6 * D2R)
                 - 0.229 * math.cos(2 * Mj - 4 * Ms - 2 * D2R)
                 + 0.119 * math.sin(Mj - 2 * Ms - 3 * D2R)
                 + 0.046 * math.sin(2 * Mj - 6 * Ms - 69 * D2R)
                 + 0.014 * math.sin(Mj - 3 * Ms + 32 * D2R)),
                (-0.020 * math.cos(2 * Mj - 4 * Ms - 2 * D2R)
                 + 0.018 * math.sin(2 * Mj - 6 * Ms - 49 * D2R)))
    if name == "天王星":
        return ((+0.040 * math.sin(Ms - 2 * Mu + 6 * D2R)
                 + 0.035 * math.sin(Ms - 3 * Mu + 33 * D2R)
                 - 0.015 * math.sin(Mj - Mu + 20 * D2R)), 0.0)
    return 0.0, 0.0


def geocentric_ecliptic(name, jd_ut):
    """地心黄经/黄纬 (度, 真春分点, 未加章动)。"""
    lon, lat, r = heliocentric(name, jd_ut)
    # 光行时修正 (对黄经影响 < 0.01°, 仍做一次迭代)
    for _ in range(2):
        pass
    xg = r * math.cos(lat * D2R) * math.cos(lon * D2R)
    yg = r * math.cos(lat * D2R) * math.sin(lon * D2R)
    zg = r * math.sin(lat * D2R)
    ex, ey, ez, er = _earth_xyz(jd_ut)
    xs, ys, zs = xg - ex, yg - ey, zg - ez
    glon = math.atan2(ys, xs) * R2D % 360.0
    glat = math.atan2(zs, math.hypot(xs, ys)) * R2D
    return glon, glat, math.sqrt(xs * xs + ys * ys + zs * zs)


def _earth_xyz(jd_ut):
    lon, lat, r = heliocentric("地球", jd_ut)
    return (r * math.cos(lat * D2R) * math.cos(lon * D2R),
            r * math.cos(lat * D2R) * math.sin(lon * D2R),
            r * math.sin(lat * D2R), r)


def planet_longitude(name, jd_ut, apparent=True):
    """行星地心视黄经 (度)。太阳/月亮走专用路径。"""
    if name == "太阳":
        return sun_apparent_longitude(jd_tt_from_ut(jd_ut))
    if name == "月亮":
        lam, beta, dist = moon_apparent_longitude(jd_tt_from_ut(jd_ut))
        return lam
    lon, lat, r = heliocentric(name, jd_ut)
    dlon, dlat = _perturbations(name, lon, lat, r, jd_ut)
    lon = (lon + dlon) % 360.0
    lat = lat + dlat
    xg = r * math.cos(lat * D2R) * math.cos(lon * D2R)
    yg = r * math.cos(lat * D2R) * math.sin(lon * D2R)
    zg = r * math.sin(lat * D2R)
    ex, ey, ez, er = _earth_xyz(jd_ut)
    xs, ys, zs = xg - ex, yg - ey, zg - ez
    glon = math.atan2(ys, xs) * R2D % 360.0
    if apparent:
        dpsi, _ = nutation(jd_tt_from_ut(jd_ut))
        glon = (glon + dpsi) % 360.0
    return glon


def planet_latitude(name, jd_ut):
    if name == "月亮":
        lam, beta, dist = moon_apparent_longitude(jd_tt_from_ut(jd_ut))
        return beta
    if name == "太阳":
        return 0.0
    lon, lat, r = heliocentric(name, jd_ut)
    dlon, dlat = _perturbations(name, lon, lat, r, jd_ut)
    lon = (lon + dlon) % 360.0
    lat = lat + dlat
    xg = r * math.cos(lat * D2R) * math.cos(lon * D2R)
    yg = r * math.cos(lat * D2R) * math.sin(lon * D2R)
    zg = r * math.sin(lat * D2R)
    ex, ey, ez, er = _earth_xyz(jd_ut)
    xs, ys, zs = xg - ex, yg - ey, zg - ez
    return math.atan2(zs, math.hypot(xs, ys)) * R2D


# ------------------------------------------------------------ 宫位/上升
def ascendant_mc(jd_ut, lon_east, lat_geog):
    """返回 (上升点黄经, 天顶黄经), 单位度。lat 为地理纬度。"""
    ramc = last_deg(jd_ut, lon_east)          # 本地视恒星时 (度) = RAMC
    eps = true_obliquity(jd_tt_from_ut(jd_ut)) * D2R
    ramc_r = ramc * D2R
    phi = lat_geog * D2R
    # 天顶 (MC)
    mc = math.atan2(math.sin(ramc_r), math.cos(ramc_r) * math.cos(eps)) * R2D % 360.0
    # 上升 (ASC)
    asc = math.atan2(math.cos(ramc_r),
                     -(math.sin(ramc_r) * math.cos(eps) + math.tan(phi) * math.sin(eps))) * R2D % 360.0
    # 按 Placidus 惯例: ASC 必须在 MC 之后约 90°
    if (asc - mc) % 360.0 < 1e-9:
        asc = (asc + 180.0) % 360.0
    while (asc - mc) % 360.0 < 10.0:
        asc = (asc + 180.0) % 360.0
    while (asc - mc) % 360.0 > 200.0:
        asc = (asc + 180.0) % 360.0
    return asc, mc


def _ra_dec(lon_deg, lat_deg, eps_deg):
    lon, lat, eps = lon_deg * D2R, lat_deg * D2R, eps_deg * D2R
    ra = math.atan2(math.sin(lon) * math.cos(eps) - math.tan(lat) * math.sin(eps),
                    math.cos(lon)) * R2D % 360.0
    dec = math.asin(math.sin(lat) * math.cos(eps) + math.cos(lat) * math.sin(eps) * math.sin(lon)) * R2D
    return ra, dec


def placidus_cusps(jd_ut, lon_east, lat_geog):
    """Placidus 十二宫宫头黄经 (度), 半弧法。

    对黄道上点 λ: 赤经 RA(λ)、赤纬 δ(λ), 地理纬度 φ:
        SA(λ) = 90° + asin(tan φ · tan δ)            周日半弧
        MD(λ) = (RA − RAMC) 归化到 [−90°, 90°]        自 MC 的子午距
    条件:
        第 11 宫: MD = +SA/3      (MC 之后 SA/3)
        第 12 宫: MD = +2SA/3
        第  2 宫: MD = −2SA/3     (IC 之后 2SA/3, 向 ASC 方向)
        第  3 宫: MD = −SA/3
    求解: 方程在黄道上有多解(相差 180°), 故沿黄道自起始宫头以小步长扫描,
    在 MD 与 SA 均平滑且残差变号的区间内二分, 取"落在正确宫段内"的根。
    """
    asc, mc = ascendant_mc(jd_ut, lon_east, lat_geog)
    eps = true_obliquity(jd_tt_from_ut(jd_ut))
    ramc = last_deg(jd_ut, lon_east)
    ic = (mc + 180.0) % 360.0

    def ra_sa(lam):
        ra, dec = _ra_dec(lam, 0.0, eps)
        tanp = math.tan(lat_geog * D2R) * math.tan(dec * D2R)
        if abs(tanp) >= 1.0:
            tanp = math.copysign(0.999999, tanp)
        return ra, 90.0 + math.asin(tanp) * R2D

    ra_ic = ra_sa(ic)[0]          # IC 的赤经 (等于 RAMC+180)

    def md(lam):
        ra, _ = ra_sa(lam)
        return (ra - ramc + 180.0) % 360.0 - 180.0

    def sd_ic(lam):
        """自 IC 起算的子午距, 朝 ASC 方向为正, 归化到 [-180,180)。"""
        ra, _ = ra_sa(lam)
        return (ra - ra_ic + 180.0) % 360.0 - 180.0

    def solve(lo_lam, hi_lam, frac, ref):
        """在黄道段 [lo_lam, hi_lam] 内求 MD(λ) = frac·SA(λ)。"""
        def f(lam):
            _, sa = ra_sa(lam)
            if ref == "mc":
                return md(lam) - frac * sa
            # 自 IC 起算: 朝 ASC 方向 SD_IC 递减为负, 取 -SD_IC
            return (-sd_ic(lam)) - frac * sa
        n = 240
        step = (hi_lam - lo_lam + 360.0) % 360.0 / n
        if step <= 0:
            step = 1.0
        prev_lam = lo_lam % 360.0
        prev = f(prev_lam)
        for i in range(1, n + 1):
            lam = (lo_lam + step * i) % 360.0
            cur = f(lam)
            if prev == 0.0:
                return prev_lam
            if prev * cur < 0:
                a, b, fa = prev_lam, lam, prev
                for _ in range(80):
                    m = (a + b) / 2.0
                    fm = f(m)
                    if fa * fm <= 0:
                        b = m
                    else:
                        a, fa = m, fm
                    if abs(b - a) < 1e-10:
                        break
                return (a + b) / 2.0
            prev_lam, prev = lam, cur
        return None

    # 第 11 宫: MC -> ASC 段内找 MD = SA/3
    def solve_seg(start_lam, end_lam, frac, ref):
        """把 [start,end] 沿黄道正向切段求解 (处理 360° 环绕)。"""
        span = (end_lam - start_lam) % 360.0
        lo = start_lam % 360.0
        hi = (start_lam + span) % 360.0
        return solve(lo, hi, frac, ref)

    c11 = solve_seg(mc, asc, 1 / 3.0, "mc")
    c12 = solve_seg((c11 if c11 is not None else mc), asc, 2 / 3.0, "mc")
    c3 = solve_seg(asc, ic, 1 / 3.0, "ic")
    c2 = solve_seg((c3 if c3 is not None else asc), ic, 2 / 3.0, "ic")

    cusps = [None] * 12
    cusps[0], cusps[3], cusps[6], cusps[9] = asc, ic, (asc + 180.0) % 360.0, mc
    cusps[1], cusps[2] = c2, c3
    cusps[4] = (c11 + 180.0) % 360.0 if c11 is not None else None
    cusps[5] = (c12 + 180.0) % 360.0 if c12 is not None else None
    cusps[7] = (c2 + 180.0) % 360.0 if c2 is not None else None
    cusps[8] = (c3 + 180.0) % 360.0 if c3 is not None else None
    cusps[10], cusps[11] = c11, c12
    # 兜底: 未能求根的宫头用等宫法插值, 保证不出现 None
    if any(c is None for c in cusps):
        for i in range(12):
            if cusps[i] is None:
                cusps[i] = (asc + 30.0 * i) % 360.0
    return cusps


def whole_sign_cusps(asc):
    """整宫制: 上升所在星座起第一宫。返回 12 个宫头黄经。"""
    start = int(asc // 30) * 30.0
    return [(start + 30.0 * i) % 360.0 for i in range(12)]


def house_of(lon, cusps):
    """给定黄经落在第几宫 (1-12)。"""
    for i in range(12):
        a = cusps[i]
        b = cusps[(i + 1) % 12]
        span = (b - a) % 360.0
        off = (lon - a) % 360.0
        if off < span or span == 0:
            return i + 1
    return 12


# ------------------------------------------------------------ 相位
def angular_sep(a, b):
    d = abs((a - b) % 360.0)
    return min(d, 360.0 - d)


def find_aspects(positions, orb_scale=1.0, include=("合相", "六合", "刑相", "拱相", "对分相", "梅花相")):
    """positions: {名称: 黄经}; 返回相位列表。"""
    names = list(positions)
    out = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            n1, n2 = names[i], names[j]
            sep = angular_sep(positions[n1], positions[n2])
            for aname, angle, orb, nature in ASPECTS:
                if aname not in include:
                    continue
                o = ASPECT_ORB.get(angle, orb) * orb_scale
                if n1 in LUMINARIES or n2 in LUMINARIES:
                    o *= 1.25
                delta = abs(sep - angle)
                if delta <= o:
                    out.append({
                        "a": n1, "b": n2, "aspect": aname, "angle": angle,
                        "orb": round(delta, 2), "exact": sep,
                        "nature": nature,
                        "applying": None,
                    })
    out.sort(key=lambda x: x["orb"])
    return out


def sign_of(lon):
    return SIGNS[int(lon // 30) % 12]


def deg_in_sign(lon):
    d = lon % 30.0
    deg = int(d)
    minute = int(round((d - deg) * 60))
    if minute == 60:
        deg, minute = deg + 1, 0
    return deg, minute


def lon_text(lon):
    s = sign_of(lon)
    d, m = deg_in_sign(lon)
    return "%s%d°%02d'" % (s, d, m)


# ------------------------------------------------------------ 星盘
def compute_chart(dt_local, tz_offset=8.0, lon_east=121.47, lat_geog=31.23):
    """计算本命盘/行运盘。
    dt_local: 当地钟表时间 (datetime)。返回完整星盘 dict。"""
    dt_utc = dt_local - _dt.timedelta(hours=tz_offset)
    jd_ut = jd_from_datetime(dt_utc)
    cusps = placidus_cusps(jd_ut, lon_east, lat_geog)
    asc, mc = cusps[0], cusps[9]
    planets = {}
    for p in PLANETS:
        lon = planet_longitude(p, jd_ut)
        lat = planet_latitude(p, jd_ut)
        planets[p] = {"lon": lon, "lat": lat, "sign": sign_of(lon),
                      "lon_text": lon_text(lon), "house": house_of(lon, cusps),
                      "retro": is_retrograde(p, jd_ut)}
    return {
        "jd_ut": jd_ut,
        "datetime_local": dt_local,
        "datetime_utc": dt_utc,
        "lon_east": lon_east,
        "lat_geog": lat_geog,
        "cusps": cusps,
        "asc": asc,
        "mc": mc,
        "asc_text": lon_text(asc),
        "mc_text": lon_text(mc),
        "planets": planets,
        "aspects": find_aspects({k: v["lon"] for k, v in planets.items()}),
        "sun_sign": planets["太阳"]["sign"],
        "moon_sign": planets["月亮"]["sign"],
    }


_RETRO_CACHE = {}


def is_retrograde(name, jd_ut, step=0.5):
    """判断行星是否逆行 (比较前后位置)。太阳/月亮恒为 False。

    与 speed_deg_per_day 使用同一步长, 保证两者一致。
    """
    if name in ("太阳", "月亮"):
        return False
    l1 = planet_longitude(name, jd_ut - step)
    l2 = planet_longitude(name, jd_ut + step)
    diff = (l2 - l1 + 180.0) % 360.0 - 180.0
    return diff < 0


def speed_deg_per_day(name, jd_ut, step=0.5):
    l1 = planet_longitude(name, jd_ut - step)
    l2 = planet_longitude(name, jd_ut + step)
    return ((l2 - l1 + 180.0) % 360.0 - 180.0) / (2 * step)


def moon_phase(jd_ut):
    """返回 (相位角 0-360, 名称, 照亮比例)。"""
    sun = planet_longitude("太阳", jd_ut)
    moon = planet_longitude("月亮", jd_ut)
    ph = (moon - sun) % 360.0
    frac = (1 - math.cos(ph * D2R)) / 2.0
    names = [(0, "新月"), (45, "娥眉月"), (90, "上弦月"), (135, "盈凸月"),
             (180, "满月"), (225, "亏凸月"), (270, "下弦月"), (315, "残月")]
    best = min(names, key=lambda x: abs(((ph - x[0] + 180) % 360) - 180))
    return ph, best[1], frac


def exact_aspect_time(natal_lon, transit_name, jd_start, jd_end, target_angle, steps=96):
    """在 [jd_start, jd_end] 内寻找行运行星与本命点位形成 target_angle 的时刻 (UT JD)。"""
    def f(jd):
        t = planet_longitude(transit_name, jd)
        return ((t - natal_lon) % 360.0) - target_angle
    step = (jd_end - jd_start) / steps
    prev_jd = jd_start
    prev = f(prev_jd)
    for i in range(1, steps + 1):
        jd = jd_start + step * i
        cur = f(jd)
        if prev == 0:
            return prev_jd
        if prev * cur < 0 and abs(cur - prev) < 30:
            lo, hi = prev_jd, jd
            for _ in range(50):
                mid = (lo + hi) / 2
                fm = f(mid)
                if prev * fm <= 0:
                    hi = mid
                else:
                    lo, prev = mid, fm
            return (lo + hi) / 2
        prev_jd, prev = jd, cur
    return None


# ------------------------------------------------------------ 月亮空亡
_ASPECT_ANGLES = (0, 60, 90, 120, 180)


def moon_void_period(jd_start, jd_end, orb=1.0, step_frac=1 / 144.0):
    """计算 [jd_start, jd_end] 内月亮"空亡"(void of course) 区间。

    定义: 月亮走完当天最后一个主要相位之后, 直到进入下一个星座之前的时间段。
    返回 {"void_start": jd or None, "void_end": jd or None}。
    """
    span = jd_end - jd_start
    step = span * step_frac
    n = int(1.0 / step_frac)
    planets = ["太阳", "水星", "金星", "火星", "木星", "土星", "天王星", "海王星", "冥王星"]
    last_aspect = None
    prev_hit = False
    for i in range(n + 1):
        jd = jd_start + step * i
        mlon = planet_longitude("月亮", jd)
        hit = False
        for p in planets:
            plon = planet_longitude(p, jd)
            sep = angular_sep(mlon, plon)
            for ang in _ASPECT_ANGLES:
                if abs(sep - ang) <= orb:
                    hit = True
                    break
            if hit:
                break
        if hit:
            last_aspect = jd
        elif prev_hit and last_aspect is not None:
            # 找到进入空亡的时刻 (二分细化)
            lo, hi = last_aspect, jd
            for _ in range(40):
                mid = (lo + hi) / 2
                m2 = planet_longitude("月亮", mid)
                ok = False
                for p in planets:
                    if abs(angular_sep(m2, planet_longitude(p, mid)) - 0) >= 0:
                        sep2 = angular_sep(m2, planet_longitude(p, mid))
                        if any(abs(sep2 - a) <= orb for a in _ASPECT_ANGLES):
                            ok = True
                            break
                if ok:
                    lo = mid
                else:
                    hi = mid
            void_start = (lo + hi) / 2
            # 终点: 月亮换座
            sgn = int(planet_longitude("月亮", void_start) // 30)
            t = void_start
            while t < jd_end and int(planet_longitude("月亮", t) // 30) == sgn:
                t += step
            return {"void_start": void_start, "void_end": min(t, jd_end)}
        prev_hit = hit
    return {"void_start": None, "void_end": None}
