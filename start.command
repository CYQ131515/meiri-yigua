#!/bin/bash
# 每日一卦 · 双击启动
cd "$(dirname "$0")" || exit 1

URL="http://127.0.0.1:5188/"
# 已经在运行就直接打开，不重复起服务
if curl -s --max-time 1 "${URL}api/health" 2>/dev/null | grep -q '"ok"'; then
  open "$URL"
  exit 0
fi

PY="$HOME/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi
if [ -z "$PY" ]; then
  echo "找不到 Python 3。请先安装 Python，或修改本脚本里的 PY 路径。"
  read -r -p "按回车退出…" _
  exit 1
fi

ARGS="--port 5188"
[ -n "$YIGUA_NO_OPEN" ] && ARGS="$ARGS --no-open"
exec "$PY" app/server.py $ARGS
