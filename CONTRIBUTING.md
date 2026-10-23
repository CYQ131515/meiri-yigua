# 参与开发

## 本地运行

```bash
# 浏览器版
bash start.command
# 或
python3 app/server.py --port 5188 --no-open
```

需要 Python 3.9+（建议 3.10+）。桌面版构建需要 macOS + Xcode Command Line Tools：

```bash
bash tools/build_desktop.sh
open 每日一卦.app
```

## 测试

```bash
# 一个终端：本地假接口
python3 tools/mock_api.py 5199
# 一个终端：应用服务
python3 app/server.py --port 5188 --no-open
# 第三个终端
node tools/test_browser.mjs http://127.0.0.1:5188
```

要求 Node 22+ 与本机 Chrome / Edge / Chromium。测试会清空 `data/narratives/`。

## 约定

- 不要在仓库里提交 API Key、`data/profile.json`、`data/narratives/*.json`、构建出的 `.app`。
- 视觉改动请保留 `#hero-title`、`#cast-btn`、`#reading` 等测试选择器；改完跑一遍端到端测试。
- 引擎代码在 `engine/`，只依赖标准库；改引擎时请遵守各模块头部的算法依据说明。
- 提交前可跑 `python3 -m py_compile app/*.py engine/*.py` 和 `node --check app/static/app.js`。

## 许可

提交的代码默认以 MIT 许可进入本项目。
