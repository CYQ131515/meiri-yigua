# -*- coding: utf-8 -*-
"""本地联调用的 OpenAI 兼容假接口（不联网、不产生费用）。
    python3 tools/mock_api.py [port]
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NARRATIVE = {
    "poem": ["炉中火候自分明", "莫向急流争一程", "且把闲心收砚底", "晚来云破月华生"],
    "judgement": "守成得吉，缓进无咎",
    "reading": "今日庚午，火气偏旺，与你命里的水木略有些争。卦得水火既济，事已在半途，最忌再添一把急火。"
               "你手上那件拖了几日的事，今天适合收尾，不适合另开一摊。与人往来，把话说慢半拍，比说满更稳。"
               "傍晚之后气机转柔，读几页书、走一段路，比继续较劲有用。",
    "areas": {
        "情感": "对方在等一句软话，你先开口不吃亏。",
        "事业": "把手头收尾，别接新的口子。",
        "财运": "守住已有，不宜追高。",
        "健康": "火气上头，少熬夜，多喝水。",
        "人际": "旧友来讯，值得回一句。",
        "学业": "读进去比读得多要紧。",
    },
    "action": "把拖了三天的那件事收尾，只做这一件。",
    "caution": "别在情绪上来时回消息，晚一小时再答。",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[mock] " + (fmt % args) + "\n")

    def _send(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw.decode("utf-8"))
        except Exception:
            req = {}
        if not self.headers.get("Authorization"):
            self._send(401, {"error": {"message": "missing key"}})
            return
        if any(x in json.dumps(req.get("messages", []), ensure_ascii=False) for x in ("test", "可用")):
            content = "可用"
        else:
            content = json.dumps(NARRATIVE, ensure_ascii=False)
        self._send(200, {
            "id": "mock-1",
            "object": "chat.completion",
            "model": req.get("model", "mock"),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        })


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5199
    print("mock api on http://127.0.0.1:%d/v1" % port)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
