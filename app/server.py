# -*- coding: utf-8 -*-
"""每日一卦 · 本地服务（仅监听 127.0.0.1）。

启动：  python3 app/server.py
静态页 + 运势 API + OpenAI 兼容接口代理。API Key 只在本机进程内转发，
不落盘；断语按日期缓存到 data/narratives/。
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import socket
import sys
import threading
import time
import traceback
from datetime import date as _date, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

import fortune  # noqa: E402
import llm      # noqa: E402

ROOT = APP_DIR.parent
STATIC = APP_DIR / "static"
DATA = Path(os.environ.get("FORTUNE_DATA_DIR") or (ROOT / "data")).expanduser()
CACHE = DATA / "narratives"
PROFILE_FILE = DATA / "profile.json"
VERSION = "1.0.0"
MAX_BODY = 512 * 1024

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/webp", ".webp")


# ---------------------------------------------------------------- 小工具
def _json_bytes(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def _signature(payload: dict, profile: dict) -> dict:
    return {
        "date": payload["date"],
        "day": payload["day"]["ganzhi"],
        "hexagram": payload["hexagram"]["number"],
        "moving": payload["hexagram"]["moving"]["line"],
        "profile": fortune.profile_key(profile),
    }


def _cache_path(sig: dict) -> Path:
    name = "%s-%s-%s.json" % (sig["date"], sig["hexagram"], sig["profile"])
    return CACHE / name


def _read_cache(sig: dict):
    path = _cache_path(sig)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("signature") != sig:
        return None
    return data.get("narrative")


def _write_cache(sig: dict, narrative: dict):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = _cache_path(sig)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "signature": sig, "narrative": narrative,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _parse_date(raw) -> _date:
    text = str(raw or "").strip()
    try:
        value = datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("日期格式应为 YYYY-MM-DD")
    today = datetime.now().date()
    if not (_date(1900, 1, 1) <= value <= _date(2100, 12, 31)):
        raise ValueError("日期超出可推算范围（1900–2100）")
    if abs((value - today).days) > 366:
        raise ValueError("只能查看一年以内的日期")
    return value


def _load_profile() -> dict:
    if PROFILE_FILE.exists():
        try:
            return fortune.normalize_profile(json.loads(PROFILE_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return fortune.default_profile()


# ---------------------------------------------------------------- 路由
class Handler(SimpleHTTPRequestHandler):
    server_version = "Yigua/" + VERSION

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    # --- 基础
    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"):
            sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def end_headers(self):
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        elif self.path.endswith((".html", ".css", ".js")):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _send(self, status: int, obj):
        body = _json_bytes(obj)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str, code: str = "error"):
        self._send(status, {"ok": False, "error": {"code": code, "message": message}})

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("请求体不是合法 JSON")
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    # --- GET
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/state":
                self._handle_state()
            elif path == "/api/health":
                self._send(200, {"ok": True, "version": VERSION})
            elif path == "/api/narratives":
                self._handle_narratives()
            else:
                super().do_GET()
        except BrokenPipeError:
            pass
        except Exception as exc:
            traceback.print_exc()
            self._error(500, "%s: %s" % (type(exc).__name__, exc))

    # --- POST
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            body = self._body()
            if path == "/api/fortune":
                self._handle_fortune(body)
            elif path == "/api/test-api":
                self._handle_test_api(body)
            elif path == "/api/profile":
                self._handle_profile(body)
            else:
                self._error(404, "没有这个接口：%s" % path, "not_found")
        except ValueError as exc:
            self._error(400, str(exc), "bad_request")
        except BrokenPipeError:
            pass
        except Exception as exc:
            traceback.print_exc()
            self._error(500, "%s: %s" % (type(exc).__name__, exc))

    # --- handlers
    def _handle_state(self):
        status = fortune.engine_status()
        payload = {
            "ok": True,
            "version": VERSION,
            "engine": status,
            "profile": _load_profile(),
            "today": datetime.now().strftime("%Y-%m-%d"),
            "now": datetime.now().strftime("%Y-%m-%dT%H:%M"),
            "defaults": {
                "base": os.environ.get("FORTUNE_API_BASE") or llm.DEFAULT_BASE,
                "model": os.environ.get("FORTUNE_API_MODEL") or llm.DEFAULT_MODEL,
            },
            "narratives": len(list(CACHE.glob("*.json"))) if CACHE.exists() else 0,
        }
        self._send(200, payload)

    def _handle_narratives(self):
        items = []
        if CACHE.exists():
            for path in sorted(CACHE.glob("*.json"), reverse=True)[:30]:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    sig = data.get("signature") or {}
                    items.append({
                        "date": sig.get("date"), "hexagram": sig.get("hexagram"),
                        "profile": sig.get("profile"),
                        "created_at": data.get("created_at"),
                        "judgement": (data.get("narrative") or {}).get("judgement"),
                        "source": (data.get("narrative") or {}).get("source"),
                    })
                except Exception:
                    continue
        self._send(200, {"ok": True, "items": items})

    def _handle_profile(self, body):
        profile = fortune.normalize_profile(body.get("profile") or body)
        DATA.mkdir(parents=True, exist_ok=True)
        PROFILE_FILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        self._send(200, {"ok": True, "profile": profile})

    def _handle_test_api(self, body):
        try:
            result = llm.test_connection(body.get("api") or {})
            self._send(200, {"ok": True, **result})
        except llm.ApiError as exc:
            self._send(200, {"ok": False, "error": {"code": exc.code, "message": exc.message}})

    def _handle_fortune(self, body):
        started = time.time()
        try:
            target = _parse_date(body.get("date"))
            profile = fortune.normalize_profile(body.get("profile") or _load_profile())
            cast_at = body.get("cast_at")
            ai_enabled = bool(body.get("ai"))
            api_cfg = body.get("api") or {}
            refresh = bool(body.get("refresh"))

            payload = fortune.compute(profile, target, cast_at)
            pub = fortune.public(payload)
            sig = _signature(pub, profile)
            result = {"ok": True, "data": pub, "meta": {
                "engine": payload["engine"], "elapsed_ms": int((time.time() - started) * 1000),
                "signature": sig,
            }}

            cached_before = _read_cache(sig)
            narrative = cached_before
            ai_error = None
            if ai_enabled and not narrative and not api_cfg.get("key") and not _looks_local(api_cfg):
                ai_error = "没有填 API Key，已显示本地断语。"
            elif ai_enabled and (refresh or not narrative):
                try:
                    narrative = llm.generate(pub, api_cfg)
                except llm.ApiError as exc:
                    ai_error = exc.message
                except Exception as exc:
                    ai_error = "%s: %s" % (type(exc).__name__, exc)
                if narrative:
                    try:
                        _write_cache(sig, narrative)
                    except Exception as exc:
                        result["meta"]["cache_error"] = "%s: %s" % (type(exc).__name__, exc)
            if narrative:
                result["data"]["narrative"] = narrative
                result["meta"]["narrative_source"] = narrative.get("source")
                result["meta"]["narrative_cached"] = bool(narrative is cached_before) and narrative is not None
            if ai_error:
                result["meta"]["ai_error"] = ai_error
            result["meta"]["elapsed_ms"] = int((time.time() - started) * 1000)
            self._send(200, result)
        except llm.ApiError as exc:
            self._error(exc.status, exc.message, exc.code)
        except Exception as exc:
            traceback.print_exc()
            self._error(500, "算卦出错了：%s" % exc, "compute_error")


def _looks_local(api_cfg: dict) -> bool:
    base = str(api_cfg.get("base") or "").lower()
    return any(h in base for h in ("127.0.0.1", "localhost", "0.0.0.0"))


# ---------------------------------------------------------------- 启动
def _pick_port(preferred: int) -> int:
    for port in range(preferred, preferred + 12):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("端口 %d-%d 都被占用，请先关闭其它服务" % (preferred, preferred + 11))


def main(argv=None):
    parser = argparse.ArgumentParser(description="每日一卦 · 本地服务")
    parser.add_argument("--port", type=int, default=int(os.environ.get("FORTUNE_PORT") or 5188))
    parser.add_argument("--no-open", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args(argv)

    if not STATIC.exists():
        raise SystemExit("缺少前端文件：%s" % STATIC)
    try:
        DATA.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SystemExit("无法创建数据目录 %s：%s" % (DATA, exc))

    parent_pid = os.environ.get("FORTUNE_PARENT_PID")
    if parent_pid:
        def _watch_parent():
            while True:
                if os.getppid() != int(parent_pid):
                    os._exit(0)
                time.sleep(2)
        threading.Thread(target=_watch_parent, daemon=True).start()

    status = fortune.engine_status()
    if not status["ok"]:
        print("✗ 运势引擎不可用：%s" % status["error"])
        print("  可用环境变量 FORTUNE_ENGINE_ROOT 指向「自动化任务」目录。")
        raise SystemExit(1)

    port = _pick_port(args.port)
    url = "http://127.0.0.1:%d/" % port
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True

    print("", flush=True)
    print("  每日一卦 · 本地服务", flush=True)
    print("  ─────────────────────────────", flush=True)
    print("  引擎  %s" % status["path"], flush=True)
    print("  地址  %s" % url, flush=True)
    print("  退出  Ctrl+C", flush=True)
    print("", flush=True)

    if not args.no_open:
        def _open():
            time.sleep(0.6)
            os.system("open %s" % json.dumps(url))
        threading.Thread(target=_open, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
