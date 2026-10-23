# -*- coding: utf-8 -*-
"""把「每日运势」自动化引擎包装成一份前端可用的 JSON。

复用 ../自动化任务/engine 下的历法、八字、黄历、占星实现（单一事实来源），
只做三件事：组装数据结构、起卦、生成不依赖外部 API 的本地断语。
"""
from __future__ import annotations

import calendar
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

from hexagrams import cast_hexagram

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ---------------------------------------------------------------- 引擎定位
def _engine_root() -> Path:
    env = os.environ.get("FORTUNE_ENGINE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    # 开源版把引擎内置在项目根目录的 engine/ 下
    if (ROOT / "engine" / "report.py").exists():
        return ROOT.resolve()
    # 兼容原先「自动化任务」与工具目录并列的布局
    return (ROOT.parent.parent / "自动化任务").resolve()


ENGINE_ROOT = _engine_root()
_ENGINE_ERROR = None
R = C = BZ = A = None


def _load_engine():
    global R, C, BZ, A, _ENGINE_ERROR
    if R is not None:
        return
    if not (ENGINE_ROOT / "engine" / "report.py").exists():
        _ENGINE_ERROR = "找不到运势引擎：%s" % ENGINE_ROOT
        raise RuntimeError(_ENGINE_ERROR)
    if str(ENGINE_ROOT) not in sys.path:
        sys.path.insert(0, str(ENGINE_ROOT))
    try:
        from engine import astro as _A, bazi as _BZ, calendar_cn as _C, report as _R
        R, C, BZ, A = _R, _C, _BZ, _A
    except Exception as exc:                    # 引擎损坏时给出可读信息
        _ENGINE_ERROR = "%s: %s" % (type(exc).__name__, exc)
        raise RuntimeError(_ENGINE_ERROR)


def engine_status() -> dict:
    try:
        _load_engine()
        return {"ok": True, "path": str(ENGINE_ROOT), "error": None}
    except Exception as exc:
        return {"ok": False, "path": str(ENGINE_ROOT), "error": str(exc)}


# ---------------------------------------------------------------- 命主资料
def default_profile() -> dict:
    _load_engine()
    try:
        cfg = R.load_config()
        n = dict(cfg.NATAL)
    except Exception:
        n = {"name": "命主", "gender": "男", "year": 1999, "month": 5, "day": 13,
             "hour": 12, "minute": 30, "birth_place": "上海", "longitude": 121.47,
             "latitude": 31.23, "tz_offset": 8.0}
    return normalize_profile(n)


_PROFILE_FIELDS = {
    "name": str, "gender": str, "year": int, "month": int, "day": int,
    "hour": int, "minute": int, "birth_place": str, "longitude": float,
    "latitude": float, "tz_offset": float,
}


def normalize_profile(raw: dict | None) -> dict:
    base = {
        "name": "命主", "gender": "男", "year": 1999, "month": 5, "day": 13,
        "hour": 12, "minute": 30, "birth_place": "上海",
        "longitude": 121.47, "latitude": 31.23, "tz_offset": 8.0,
    }
    if isinstance(raw, dict):
        base.update({k: v for k, v in raw.items() if k in _PROFILE_FIELDS})
    # 类型与范围校正
    for key, caster in _PROFILE_FIELDS.items():
        try:
            value = caster(base[key])
        except (TypeError, ValueError):
            value = caster({"int": 0, "float": 0.0, "str": ""}[caster.__name__])
        base[key] = value
    base["year"] = min(max(base["year"], 1900), 2100)
    base["month"] = min(max(base["month"], 1), 12)
    max_day = calendar.monthrange(base["year"], base["month"])[1]
    base["day"] = min(max(base["day"], 1), max_day)
    base["hour"] = min(max(base["hour"], 0), 23)
    base["minute"] = min(max(base["minute"], 0), 59)
    base["longitude"] = min(max(base["longitude"], -180.0), 180.0)
    base["latitude"] = min(max(base["latitude"], -90.0), 90.0)
    base["tz_offset"] = min(max(base["tz_offset"], -12.0), 14.0)
    base["gender"] = "女" if str(base["gender"]).startswith("女") else "男"
    base["birth_place"] = (base["birth_place"] or "未知")[:24]
    base["name"] = (base["name"] or "命主")[:16]
    return base


def profile_key(profile: dict) -> str:
    blob = json.dumps(profile, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- 小工具
def _word(score) -> str:
    if not isinstance(score, (int, float)):
        return "—"
    if score >= 85:
        return "极佳"
    if score >= 72:
        return "顺遂"
    if score >= 60:
        return "平顺"
    if score >= 48:
        return "平稳"
    if score >= 36:
        return "偏弱"
    return "低迷"


def _short(text, limit=60) -> str:
    text = str(text or "").strip()
    first = text.split("。")[0]
    return (first[:limit] + "…") if len(first) > limit else first


def _parse_local_dt(value, date: _dt.date, fallback: _dt.time = _dt.time(0, 5)) -> _dt.datetime:
    """把前端的本地时间字符串解析成 naive datetime。"""
    if isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "")
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return _dt.datetime.strptime(raw[:19], fmt)
            except ValueError:
                continue
    return _dt.datetime.combine(date, fallback)


def _pillars(bz: dict) -> list:
    out = []
    for pos, key in (("年柱", "year"), ("月柱", "month"), ("日柱", "day"), ("时柱", "hour")):
        p = (bz.get("pillars") or {}).get(key) or {}
        out.append({
            "pos": pos,
            "gan": p.get("gan", "—"),
            "zhi": p.get("zhi", "—"),
            "ganzhi": p.get("ganzhi", "—"),
            "shishen": ((bz.get("shishen") or {}).get("gan") or {}).get(key, ""),
            "zhi_shishen": ((bz.get("shishen") or {}).get("zhi") or {}).get(key, []),
            "canggan": ((bz.get("canggan") or {}).get(key) or []),
            "nayin": (bz.get("nayin") or {}).get(key, ""),
            "changsheng": (bz.get("changsheng") or {}).get(key, ""),
        })
    return out


def _current_dayun(bz: dict, date: _dt.date) -> dict | None:
    for d in bz.get("dayun") or []:
        sy, ey = d.get("start_year"), d.get("end_year")
        if sy is not None and ey is not None and sy <= date.year < ey:
            return d
    return None


def _area_word(score) -> str:
    return _word(score)


# ---------------------------------------------------------------- 本地断语

def _plain_note(note: str) -> str:
    text = str(note or "")
    text = text.replace("行运", "")
    if "（吉，" in text:
        text = text.split("（吉，")[0] + "，为助"
    elif "（需留意，" in text:
        text = text.split("（需留意，")[0] + "，需留意"
    return text.strip("。； ")



_COLOR_MAP = {"木": "青、绿", "火": "红、橙", "土": "黄、棕", "金": "白、金", "水": "黑、蓝"}
_DIR_MAP = {"木": "正东", "火": "正南", "土": "西南", "金": "正西", "水": "正北"}
_NUM_MAP = {"木": [3, 8], "火": [2, 7], "土": [5, 10], "金": [4, 9], "水": [1, 6]}


def _open_tips(xiyong: dict) -> dict:
    """开运提示：取喜用五行第一位。"""
    favor = xiyong.get("favor") or []
    wx = favor[0] if favor else "木"
    return {
        "wuxing": wx,
        "color": _COLOR_MAP.get(wx, "—"),
        "direction": _DIR_MAP.get(wx, "—"),
        "numbers": _NUM_MAP.get(wx, []),
    }


def _relation_text(day_rel: dict) -> str:
    if not isinstance(day_rel, dict) or "error" in day_rel:
        return "—"
    parts = []
    for key, label in (("chong", "冲"), ("he", "合"), ("xing", "刑"), ("hai", "害")):
        value = day_rel.get(key)
        if value:
            value = str(value)
            parts.append(value if value.startswith(label) else label + value)
    favor = day_rel.get("favor_hit") or []
    avoid = day_rel.get("avoid_hit") or []
    if favor:
        parts.append("喜用神到位：" + "、".join(favor))
    if avoid:
        parts.append("忌神出现：" + "、".join(avoid))
    return "；".join(parts) if parts else "与命局无明显冲合"


def _area_hint(score) -> str:
    if not isinstance(score, (int, float)):
        return ""
    if score >= 72:
        return "气机相助，可主动些"
    if score >= 60:
        return "顺多于阻，照常推进"
    if score >= 48:
        return "平顺，按既定节奏"
    if score >= 36:
        return "略有牵制，宜缓不宜急"
    return "阻力偏大，宜静守"


def local_narrative(payload: dict) -> dict:
    """不调用 API 时的兜底断语：全部由已算出的结构化数据拼成，不作虚构。"""
    hx = payload["hexagram"]
    rel = payload["relation"]
    bz = payload["bazi"]
    areas = payload["scores"]["areas"]
    yi = payload["almanac"]["yi"]
    ji = payload["almanac"]["ji"]
    overall = payload["scores"]["overall"]
    ranked = sorted(areas, key=lambda x: x["score"], reverse=True)
    best, worst = ranked[0], ranked[-1]
    rel_bits = [x for x in (rel.get("text"), ) if x]
    tiyong = hx["tiyong"]

    poem = [
        "%s之象 · %s" % (hx["name"], hx["keyword"]),
        hx["meaning"],
        "%s日 · %s，%s" % (payload["day"]["ganzhi"], rel.get("shishen_gan", ""), _word(overall)),
        "体用%s，动在%s" % (tiyong["word"], hx["moving"]["name"]),
    ]
    judgement = payload.get("one_liner") or "%s，%s" % (_word(overall), hx["keyword"])
    reading = (
        "今日%s日，%s。卦得%s，%s；动爻在%s，%s；变卦%s，互卦%s。"
        "六事之中%s最顺（%d），%s宜缓（%d）。%s"
    ) % (
        payload["day"]["ganzhi"],
        (rel_bits[0] if rel_bits else "与命局无明显冲合"),
        hx["name"], hx["meaning"], hx["moving"]["name"], tiyong["note"],
        hx["changed"]["name"], hx["hu"]["name"],
        best["area"], best["score"], worst["area"], worst["score"],
        (R._bazi_narrative(bz["_raw"], rel["_raw"], payload["_date"])
         .replace("**", "").split("\n\n")[-1] if bz.get("_raw") else ""),
    )
    area_text = {}
    for a in areas:
        notes = a.get("notes") or []
        note = _plain_note(notes[0]) if notes else ""
        hint = _area_hint(a["score"])
        area_text[a["area"]] = "%s。%s%s" % (
            _area_word(a["score"]), hint, ("。" + note) if note else "")
    action = "宜%s；出行取%s，衣色用%s。" % (
        "、".join(yi[:2]) or "静守", payload["open"]["direction"], payload["open"]["color"])
    avoid_hint = {
        "火": "火气偏旺，慎急躁与熬夜",
        "土": "土重，慎拖延与贪多",
        "金": "金锐，慎口舌与争胜",
        "水": "水寒，慎思虑过度",
        "木": "木旺，慎一意孤行",
    }
    avoid = payload["bazi"]["xiyong"].get("avoid") or []
    hint = avoid_hint.get(avoid[0], "凡事宜缓，不宜争先") if avoid else "凡事宜缓，不宜争先"
    caution = "忌%s；%s。" % ("、".join(ji[:2]) or "冒进", hint)
    return {
        "source": "local",
        "poem": poem,
        "judgement": judgement,
        "reading": reading,
        "areas": area_text,
        "action": action,
        "caution": caution,
        "model": None,
    }


# ---------------------------------------------------------------- 主计算
_cache = {}
_cache_lock = threading.Lock()


def compute(profile: dict, date: _dt.date, cast_at: str | None) -> dict:
    """算出某日某时的完整数据（不含 AI 叙述）。结果做进程内缓存。"""
    _load_engine()
    profile = normalize_profile(profile)
    cast_dt = _parse_local_dt(cast_at, date)
    key = (profile_key(profile), date.isoformat(), cast_dt.strftime("%Y-%m-%dT%H:%M"))
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit

    cfg = SimpleNamespace(NATAL=profile)
    natal = R.build_natal(cfg)
    bz = natal["bazi"]
    tz = float(profile.get("tz_offset") or 8.0)
    day_gz = C.day_ganzhi(date)
    alm_data = R.collect_almanac(date, day_gz)
    alm = alm_data.get("almanac") or {}
    lunar = alm_data.get("lunar") or C.lunar_from_date(date)
    transits = R.collect_transits(natal["chart"], date, tz)
    try:
        day_rel = BZ.day_relation(bz, date)
    except Exception as exc:
        day_rel = {"error": "%s: %s" % (type(exc).__name__, exc)}
    alm_score = alm.get("score")
    areas = R.area_readings(transits, day_rel, alm_score)
    yi, ji = R.day_advice(day_rel, alm, bz.get("xiyong") or {})
    luck = R._luck_score(day_rel, alm_score, areas)
    tiyong_open = _open_tips(bz.get("xiyong") or {})
    phase = transits.get("phase") or (0, "—", 0)

    lunar_year_ganzhi = (alm.get("lunar") or {}).get("year_ganzhi") or R._gz_year(date)
    hexagram = cast_hexagram(
        {"year": lunar.get("lunar_year"), "month": lunar.get("lunar_month"),
         "day": lunar.get("lunar_day"), "year_ganzhi": lunar_year_ganzhi},
        cast_dt,
    )

    rel_text = _relation_text(day_rel)
    one_liner = R._one_liner(luck, day_rel, areas) if day_rel and "error" not in day_rel else ""

    payload = {
        "date": date.isoformat(),
        "weekday": alm.get("weekday") or "星期" + "一二三四五六日"[date.weekday()],
        "generated_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "profile": {
            "name": profile["name"], "gender": profile["gender"],
            "birth": "%04d-%02d-%02d %02d:%02d" % (profile["year"], profile["month"], profile["day"],
                                                    profile["hour"], profile["minute"]),
            "place": profile["birth_place"], "longitude": profile["longitude"],
            "latitude": profile["latitude"], "tz_offset": profile["tz_offset"],
            "true_solar_time": bz.get("true_solar_time").strftime("%H:%M:%S") if isinstance(bz.get("true_solar_time"), _dt.datetime) else bz.get("true_solar_time"),
            "true_solar_offset": bz.get("true_solar_offset"),
            "shichen": bz.get("shichen"),
        },
        "lunar": {
            "text": "%s年 %s%s" % (lunar_year_ganzhi, lunar.get("month_name", ""), lunar.get("day_name", "")),
            "year_text": lunar_year_ganzhi,
            "month_name": lunar.get("month_name", ""),
            "day_name": lunar.get("day_name", ""),
            "month": lunar.get("lunar_month"),
            "day": lunar.get("lunar_day"),
            "is_leap": bool(lunar.get("is_leap")),
            "zodiac": ((day_rel.get("day_info") if isinstance(day_rel, dict) else {}) or {}).get("shengxiao", ""),
        },
        "day": {
            "ganzhi": day_gz,
            "zhi": day_gz[-1],
            "gan": day_gz[0],
            "nayin": (day_rel.get("nayin") if isinstance(day_rel, dict) else "") or "",
            "xun": ((day_rel.get("day_info") if isinstance(day_rel, dict) else {}) or {}).get("xun", ""),
            "kongwang": (day_rel.get("kongwang") if isinstance(day_rel, dict) else "") or [],
            "jianchu": {
                "name": (alm.get("jianchu") or {}).get("name", "—"),
                "shen": (alm.get("jianchu") or {}).get("shen", ""),
                "huangdao": (alm.get("jianchu") or {}).get("huangdao"),
                "note": _short((alm.get("jianchu") or {}).get("note", ""), 90),
            },
            "xiu": {
                "name": (alm.get("xiu") or {}).get("name", "—"),
                "gong": (alm.get("xiu") or {}).get("gong", ""),
                "ji_xiong": (alm.get("xiu") or {}).get("ji_xiong", ""),
                "note": _short((alm.get("xiu") or {}).get("note", ""), 80),
            },
            "chong": {
                "text": (alm.get("chong") or {}).get("text", "—"),
                "zhi": (alm.get("chong") or {}).get("zhi", ""),
                "sha": (alm.get("chong") or {}).get("sha", ""),
            },
            "pengzu": [v for v in (alm.get("pengzu") or {}).values() if v],
            "jieqi": R._near_term_text(date),
            "shengxiao": ((day_rel.get("day_info") if isinstance(day_rel, dict) else {}) or {}).get("shengxiao", ""),
        },
        "moon": {
            "phase": phase[1],
            "illum": int(round(phase[2] * 100)),
            "void": R._void_text(transits.get("void"), tz).replace("｜", "").strip(),
        },
        "scores": {
            "overall": luck,
            "word": _word(luck),
            "day": day_rel.get("score") if isinstance(day_rel, dict) else None,
            "almanac": alm_score,
            "areas": [{
                "area": a["area"], "score": a["score"], "word": _area_word(a["score"]),
                "notes": a.get("notes", []), "houses": a.get("houses", ""),
            } for a in areas],
        },
        "one_liner": one_liner,
        "almanac": {
            "score_detail": alm.get("score_detail") or {},
            "jishen": [{"name": j.get("name"), "type": j.get("type"), "note": _short(j.get("note"), 70)}
                       for j in (alm.get("jishen") or [])][:4],
            "yi": yi[:8],
            "ji": ji[:6],
            "shenfang": alm.get("shenfang") or {},
            "yi_detail": [{"item": y.get("item"), "reason": _short(y.get("reason"), 60)}
                          for y in (alm.get("yi_detail") or [])][:4],
            "warnings": alm.get("warnings") or [],
        },
        "bazi": {
            "pillars": _pillars(bz),
            "day_master": bz.get("day_master") or {},
            "strength": {"verdict": (bz.get("strength") or {}).get("verdict", ""),
                         "score": (bz.get("strength") or {}).get("score"),
                         "detail": (bz.get("strength") or {}).get("detail", "")},
            "xiyong": {k: (bz.get("xiyong") or {}).get(k) for k in ("favor", "avoid", "method", "detail", "tiaohou")},
            "wuxing": [{"name": k, "score": v} for k, v in (bz.get("wuxing_score") or {}).items()],
            "dayun": [{"ganzhi": d.get("ganzhi"), "shishen": d.get("shishen"),
                       "start_year": d.get("start_year"), "end_year": d.get("end_year"),
                       "start_age": d.get("start_age")} for d in (bz.get("dayun") or [])],
            "current_dayun": _current_dayun(bz, date),
            "liunian": {"ganzhi": R._gz_year(date), "year": date.year},
            "qiyun": bz.get("qiyun") or {},
            "shensha": [{"name": s.get("name"), "where": s.get("where")} for s in (bz.get("shensha") or [])][:10],
            "warnings": bz.get("warnings") or [],
        },
        "relation": {
            "score": day_rel.get("score") if isinstance(day_rel, dict) else None,
            "shishen_gan": day_rel.get("shishen_gan", "") if isinstance(day_rel, dict) else "",
            "shishen_zhi": day_rel.get("shishen_zhi", "") if isinstance(day_rel, dict) else "",
            "text": rel_text,
            "highlights": (day_rel.get("highlights") or [])[:6] if isinstance(day_rel, dict) else [],
            "cautions": (day_rel.get("cautions") or [])[:6] if isinstance(day_rel, dict) else [],
            "score_detail": (day_rel.get("score_detail") or [])[:10] if isinstance(day_rel, dict) else [],
            "shensha": (day_rel.get("shensha_hits") or [])[:6] if isinstance(day_rel, dict) else [],
        },
        "astro": {
            "natal": {
                "sun": natal["chart"].get("sun_sign", ""),
                "moon": natal["chart"].get("moon_sign", ""),
                "asc": natal["chart"].get("asc_text", ""),
                "mc": natal["chart"].get("mc_text", ""),
                "planets": [{
                    "planet": name, "text": (p or {}).get("lon_text", ""), "sign": (p or {}).get("sign", ""),
                    "house": (p or {}).get("house"), "retro": bool((p or {}).get("retro")),
                } for name, p in (natal["chart"].get("planets") or {}).items()],
                "aspects": [{
                    "a": x.get("a") or x.get("p1"), "b": x.get("b") or x.get("p2"),
                    "aspect": x.get("aspect"), "orb": round(float(x.get("orb") or 0), 2),
                    "nature": x.get("nature"),
                } for x in (natal["chart"].get("aspects") or [])][:10],
            },
            "transits": [{
                "planet": p.get("planet"), "text": p.get("text"), "sign": p.get("sign"),
                "house": p.get("house"), "retro": bool(p.get("retro")),
            } for p in (transits.get("planets") or [])],
            "aspects": [{
                "transit": x.get("transit"), "natal": x.get("natal"), "aspect": x.get("aspect"),
                "nature": x.get("nature"), "orb": round(float(x.get("orb") or 0), 2),
                "trend": x.get("trend"),
            } for x in (transits.get("aspects") or [])][:8],
        },
        "hexagram": hexagram,
        "open": {
            "wuxing": tiyong_open.get("wuxing"),
            "color": tiyong_open.get("color"),
            "direction": tiyong_open.get("direction"),
            "numbers": tiyong_open.get("numbers"),
            "shenfang": alm.get("shenfang") or {},
        },
        "hours": [{
            "shichen": h.get("shichen"), "ganzhi": h.get("ganzhi"),
            "ji_xiong": h.get("ji_xiong"), "shen": h.get("shen"),
            "note": _short(h.get("note"), 46),
        } for h in (alm.get("hour_ji") or [])],
        "narrative": None,
        "engine": {"path": str(ENGINE_ROOT), "version": "1.0"},
    }

    # 只给本地断语用的内部引用（不序列化给前端）
    payload["_date"] = date
    payload["narrative"] = local_narrative({
        **payload,
        "bazi": {**payload["bazi"], "_raw": bz},
        "relation": {**payload["relation"], "_raw": day_rel},
    })

    with _cache_lock:
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = payload
    return payload


def public(payload: dict) -> dict:
    """去掉内部字段，得到可 JSON 序列化的干净结构。"""
    out = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    out.pop("_date", None)
    return out
