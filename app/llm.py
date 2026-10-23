# -*- coding: utf-8 -*-
"""OpenAI 兼容接口的调用与断语校验。

只支持一种协议：POST {base}/chat/completions —— DeepSeek、OpenAI、Moonshot、
SiliconFlow、Ollama、LM Studio 等主流服务都兼容。密钥只在本次请求里使用，
不写入磁盘；断语结果按"日期 + 卦 + 命主"缓存，避免重复计费。
"""
from __future__ import annotations

import json
import re
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from fortune import local_narrative

DEFAULT_BASE = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
TIMEOUT = 100

SYSTEM_PROMPT = """你是一位精研《周易》梅花易数与四柱八字的命理师，替同一位命主每日断卦。
你的文字古朴、克制、具体，能落到今天可做的一件小事上；不堆术语，不作绝对断言，
不涉医疗、投资、法律、婚恋等专业建议，也不制造焦虑。
只输出一个 JSON 对象，不要 Markdown 代码块，不要多余解释。"""

_SCHEMA_HINT = """请输出如下结构的 JSON：
{
  "poem": ["七言句", "七言句", "七言句", "七言句"],
  "judgement": "一句断语，14-22 字",
  "reading": "解卦白话，180-260 字，第二人称，先释卦象，再落到今日处境",
  "areas": {"情感": "12-30 字", "事业": "12-30 字", "财运": "12-30 字", "健康": "12-30 字", "人际": "12-30 字", "学业": "12-30 字"},
  "action": "今日可执行的一件事，16-30 字",
  "caution": "今日宜避开的一件事，16-30 字"
}
要求：
1. poem 四句，每句七字，押韵与否皆可，要有画面，不要口号；
2. judgement 是今日一句总断，须与卦象、体用、六事分数一致；
3. reading 用第二人称"你"，结合卦名、动爻、体用与命主八字喜忌，不作吉凶恐吓；
4. areas 六个领域各一句，须与给定分数的高低方向一致（分高写顺，分低写缓）；
5. action 与 caution 必须具体、当天可做，不要写"保持好心态"这类空话。"""


class ApiError(Exception):
    def __init__(self, message: str, code: str = "api_error", status: int = 502):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def normalize_api(api: dict | None) -> dict:
    api = api or {}
    base = str(api.get("base") or "").strip() or DEFAULT_BASE
    base = base.rstrip("/")
    for suffix in ("/chat/completions", "/v1/chat/completions"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    if not re.match(r"^https?://", base):
        base = "https://" + base
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError("接口地址格式不对，应形如 https://api.deepseek.com/v1", "bad_base", 400)
    if parsed.path in ("", "/"):     # 只填到域名时，按主流约定补 /v1
        base = base.rstrip("/") + "/v1"
        parsed = urllib.parse.urlparse(base)
    return {
        "base": base,
        "key": str(api.get("key") or "").strip(),
        "model": str(api.get("model") or "").strip() or DEFAULT_MODEL,
        "host": parsed.netloc,
    }


def _post(api: dict, body: dict) -> dict:
    url = api["base"] + "/chat/completions"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api.get("key"):
        headers["Authorization"] = "Bearer " + api["key"]
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    ctx = ssl.create_default_context()
    local = any(h in (api.get("host") or "") for h in ("127.0.0.1", "localhost", "0.0.0.0", "[::1]"))
    try:
        if local:                      # 本机服务（Ollama / LM Studio）绕开系统代理
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", "replace")
        else:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        message, code = _http_error(exc.code, detail)
        raise ApiError(message, code, 502 if exc.code >= 500 else 400)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, socket.timeout):
            raise ApiError("连接超时：服务端 100 秒内没有回应", "timeout", 504)
        raise ApiError("连不上接口：%s。请检查网络与接口地址" % reason, "unreachable", 502)
    except socket.timeout:
        raise ApiError("连接超时：服务端 100 秒内没有回应", "timeout", 504)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ApiError("接口返回的不是 JSON：%s" % raw[:120], "bad_response", 502)


def _http_error(status: int, detail: str) -> tuple:
    snippet = (detail or "").strip().replace("\n", " ")[:160]
    mapping = {
        400: ("请求被拒绝（400）。可能是模型名不对，或该服务不支持 JSON 输出", "bad_request"),
        401: ("API Key 无效或已过期（401）", "unauthorized"),
        403: ("Key 没有这个模型的权限（403）", "forbidden"),
        404: ("接口地址不对（404）。检查 Base URL 是否包含 /v1", "not_found"),
        429: ("请求太频繁或额度不足（429）", "rate_limited"),
        502: ("网关错误（502），服务或代理没能转发请求", "bad_gateway"),
        503: ("服务不可用（503）；若走本机代理，可能是代理拦下了请求", "unavailable"),
        504: ("网关超时（504）", "gateway_timeout"),
    }
    message, code = mapping.get(status, ("接口出错（%d）" % status, "http_%d" % status))
    if snippet:
        message += "：" + snippet
    return message, code


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ApiError("模型没有返回可解析的 JSON", "bad_json", 502)
        try:
            obj = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            raise ApiError("模型返回的 JSON 不完整", "bad_json", 502)
    if not isinstance(obj, dict):
        raise ApiError("模型返回的 JSON 不是对象", "bad_json", 502)
    return obj


def _clean(value, limit: int) -> str:
    text = re.sub(r"\s+", "", str(value or "")).strip("，,。.")
    return text[:limit]


def _validate(raw: dict, fallback: dict) -> tuple[dict, list]:
    """校验并补全模型输出；返回 (断语, 修复记录)。"""
    notes = []
    out = {
        "source": "ai",
        "poem": list(fallback["poem"]),
        "judgement": fallback["judgement"],
        "reading": fallback["reading"],
        "areas": dict(fallback["areas"]),
        "action": fallback["action"],
        "caution": fallback["caution"],
    }

    poem = raw.get("poem")
    if isinstance(poem, list) and len(poem) == 4:
        lines = [_clean(x, 16) for x in poem]
        if all(5 <= len(x) <= 16 for x in lines):
            out["poem"] = lines
        else:
            notes.append("poem")
    else:
        notes.append("poem")

    for key, lo, hi in (("judgement", 6, 40), ("reading", 70, 520), ("action", 8, 60), ("caution", 8, 60)):
        value = _clean(raw.get(key), hi)
        if lo <= len(value) <= hi:
            out[key] = value
        else:
            notes.append(key)

    areas = raw.get("areas")
    if isinstance(areas, dict):
        valid = 0
        for key in ("情感", "事业", "财运", "健康", "人际", "学业"):
            value = _clean(areas.get(key), 48)
            if 6 <= len(value) <= 48:
                out["areas"][key] = value
                valid += 1
        if valid < 5:
            notes.append("areas")
    else:
        notes.append("areas")
    return out, notes


def build_messages(payload: dict) -> list:
    hx = payload["hexagram"]
    scores = payload["scores"]
    rel = payload["relation"]
    bz = payload["bazi"]
    areas = "；".join("%s %d 分（%s）" % (a["area"], a["score"], a["word"]) for a in scores["areas"])
    top_areas = sorted(scores["areas"], key=lambda x: x["score"], reverse=True)
    yi = "、".join(payload["almanac"]["yi"][:6]) or "无"
    ji = "、".join(payload["almanac"]["ji"][:4]) or "无"
    favor = "、".join(bz["xiyong"].get("favor") or [])
    avoid = "、".join(bz["xiyong"].get("avoid") or [])
    pil = " ".join(p["ganzhi"] for p in bz["pillars"])
    highlights = "；".join(rel.get("highlights") or [])[:200] or "无"
    cautions = "；".join(rel.get("cautions") or [])[:200] or "无"
    tiyong = hx["tiyong"]

    user = """【命主】{birth} 生于{gender}，{place}。四柱 {pil}，日主 {gan}{wx}，身{strength}，喜 {favor}，忌 {avoid}。
【今日】公历 {date} {weekday}，农历 {lunar}，干支 {ganzhi} 日，{jianchu}日，值宿{xiu}（{xius}）。
黄历宜：{yi}；忌：{ji}。
【日课】日柱与命局：{reltext}。加分：{highlights}。留意：{cautions}。
【星象】月相{phase}；当日行运相位：{transits}。
【卦象】{hxnum} {hxname}（{symbol}），{upper}上{upper_nature}、{lower}下{lower_nature}。卦意：{meaning}。
动爻：{moving}。变卦：{changed}。体用：{tiyong}（{tiyong_note}）。
【六事】{areas}。最顺：{best}；最需留意：{worst}。
【开运】幸运五行{favor0}、{color}、{direction}、数字{numbers}。综合 {overall} 分（{word}）。
今日一句：{one_liner}

{schema}

只输出 JSON。""".format(
        birth=payload["profile"]["birth"], gender=payload["profile"]["gender"],
        place=payload["profile"]["place"], pil=pil,
        gan=bz["day_master"].get("gan", ""), wx=bz["day_master"].get("wuxing", ""),
        strength=bz["strength"].get("verdict", ""), favor=favor or "—", avoid=avoid or "—",
        date=payload["date"], weekday=payload["weekday"], lunar=payload["lunar"]["text"],
        ganzhi=payload["day"]["ganzhi"], jianchu=payload["day"]["jianchu"]["name"],
        xiu=payload["day"]["xiu"]["name"], xius=payload["day"]["xiu"].get("ji_xiong", ""),
        yi=yi, ji=ji, reltext=rel.get("text") or "无明显冲合",
        highlights=highlights, cautions=cautions, phase=payload["moon"]["phase"],
        transits="；".join("%s%s%s" % (t["transit"], t["aspect"], t["natal"]) for t in payload["astro"]["aspects"][:6]),
        hxnum=hx["number"], hxname=hx["name"], symbol=hx["symbol"],
        upper=hx["upper"]["name"], upper_nature=hx["upper"]["nature"],
        lower=hx["lower"]["name"], lower_nature=hx["lower"]["nature"],
        meaning=hx["meaning"], moving=hx["moving"]["text"], changed=hx["changed"]["name"],
        tiyong=tiyong["word"], tiyong_note=tiyong["note"],
        areas=areas, best=top_areas[0]["area"], worst=top_areas[-1]["area"],
        favor0=payload["open"]["wuxing"], color=payload["open"]["color"],
        direction=payload["open"]["direction"], numbers="/".join(str(n) for n in payload["open"]["numbers"]),
        overall=scores["overall"], word=scores["word"], one_liner=payload["one_liner"],
        schema=_SCHEMA_HINT,
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def generate(payload: dict, api_cfg: dict) -> dict:
    """调用模型生成断语；失败抛 ApiError。"""
    api = normalize_api(api_cfg)
    messages = build_messages(payload)
    body = {
        "model": api["model"],
        "messages": messages,
        "temperature": 0.85,
        "max_tokens": 1400,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = _post(api, body)
    except ApiError as exc:
        if exc.code in ("bad_request",) and "JSON" in exc.message:
            body.pop("response_format", None)
            resp = _post(api, body)
        else:
            raise
    try:
        content = resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ApiError("接口返回里没有 choices 内容", "bad_response", 502)
    raw = _extract_json(content)
    narrative, fixed = _validate(raw, local_narrative(payload))
    narrative["model"] = api["model"]
    narrative["fixed_fields"] = fixed
    narrative["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return narrative


def test_connection(api_cfg: dict) -> dict:
    api = normalize_api(api_cfg)
    body = {
        "model": api["model"],
        "messages": [{"role": "user", "content": "只回复两个字：可用"}],
        "max_tokens": 8,
        "temperature": 0,
    }
    started = datetime.now()
    resp = _post(api, body)
    try:
        text = resp["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        raise ApiError("接口有响应，但没有 choices 内容", "bad_response", 502)
    elapsed = int((datetime.now() - started).total_seconds() * 1000)
    return {"ok": True, "message": "连接正常：%s · %s（%d ms）" % (api["host"], api["model"], elapsed),
            "reply": text[:40], "elapsed_ms": elapsed}
