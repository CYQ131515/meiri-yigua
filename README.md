# 每日一卦

> 本地优先的梅花易数每日一卦 · macOS 原生桌面版 + 浏览器版
> A local-first I Ching (Meihua Yishu) daily reading app for macOS.

**下载**：[Releases](https://github.com/CYQ131515/meiri-yigua/releases) · **源码**：[github.com/CYQ131515/meiri-yigua](https://github.com/CYQ131515/meiri-yigua)

把「每天算一卦」这件事做成一个可以双击打开的本地小应用：深墨天幕、二十八宿、
罗盘与朱砂卦签，每日按年月日时起卦，接上你自己的 API 就能得到一段针对当天的解卦。

- 界面：夜观星盘，晨读卦签。行楷写卦名与签诗，宋体排正文，楷体作旁注；
  罗盘按当日干支重绘：二十四山、后天八卦、十二地支三层以不同速度缓缓转动，
  外圈顺时针、内圈逆时针；外圈二十八宿另转一圈。起卦时三层再一起拨转、落爻、盖印。
- 算法：`engine/` 内置历法、四柱、黄历、占星实现（原为作者自动化任务的一部分），不重复造轮子。
- 起卦：梅花易数·年月日时起卦，一日一卦，同一日同一时辰只出一卦。
- 解卦：可接入任意 OpenAI 兼容接口（DeepSeek、Moonshot、SiliconFlow、Ollama…）；
  不填 API Key 时用本地规则给出断语，功能完整可离线使用。
- 隐私：只监听 127.0.0.1；API Key 只保存在浏览器或桌面版本地存储，请求直发你填的地址，
  不写入项目文件；卦象与断语缓存在本机。桌面版数据在 `~/Library/Application Support/每日一卦/`。

![首屏](preview.jpg)

---

## 一、启动

### 桌面版（推荐）

![桌面版窗口](preview-desktop.jpg)

在本目录双击 **`每日一卦.app`**。它会打开一个原生 macOS 窗口，不需要终端，也不需要浏览器。

- 桌面版自带网页、运势引擎和图标，约 2.3 MB；整个 `.app` 可以直接拖到「应用程序」或桌面。
- 发布的构建面向 macOS 13+ / Apple Silicon（arm64）；从 Releases 下载 zip，解压后双击即可。
- 数据单独保存在 `~/Library/Application Support/每日一卦/`：出生资料、AI 断语缓存、运行日志。
- 桌面版与浏览器版存储彼此独立；浏览器里填过的 API Key 不会自动带过来，第一次打开请在「设置」里重填一次。
- 菜单：`⌘R` 重新载入、`⌘,` 设置、`⌘↩` 起卦、`⌘J` 跳到今日卦；「帮助」里可以直接打开数据目录和运行日志。
- 关窗即退出，本地 Python 服务会一起停止。首次打开若被 macOS 拦下，右键应用 →「打开」。
- 修改网页或引擎后，先退出桌面版，再运行 `bash tools/build_desktop.sh` 重新打包；
  桌面版内置的是打包时的网页与引擎快照。

桌面版使用 DSH 自带 Python 3.12；找不到时回退到系统 `python3`。

### 浏览器版

在本目录双击 **`start.command`**。

第一次打开若被 macOS 拦截：右键 `start.command` → 打开；或在「系统设置 → 隐私与安全性」里允许。

它会：

1. 用 DSH 自带 Python 启动本地服务（默认端口 5188，被占用会顺延）；
2. 自动打开 `http://127.0.0.1:5188/`；
3. 保持这个终端窗口不关，应用就在运行。要停止，回到终端按 `Ctrl+C`。

如果本机没有 DSH 的 Python，会退回系统 `python3`。Python 3.9+ 即可（建议 3.10+）。

---

## 二、第一次用

1. 首屏出现今天的农历、干支、值宿、冲煞、节气与月相；点朱砂方印「起卦」。
2. 罗盘旋转 → 盘心落六爻 → 今日卦象、卦辞、六事、宜忌、时辰、开运一起展开。
![卦签与解卦](preview-reading.jpg)

3. 想换成 AI 解卦：右上「设置」→「解卦接口」填 Base URL、API Key、模型 →「测试连接」→「保存」。
   保存后会立刻用当天卦象重新问一次；以后每天只在第一次打开时调用一次，结果缓存在本机。

常用接口填法：

| 服务 | Base URL | 模型示例 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V3` |
| Ollama（本机） | `http://127.0.0.1:11434/v1` | `qwen2.5:7b`（Key 可留空） |

> API Key 只存在当前浏览器或桌面版本地存储里。换浏览器/清缓存/换机器后需要重填；项目文件里不会出现 Key。
> 接口地址只填到域名（如 `https://api.deepseek.com`）时，会自动补上 `/v1`。

---

## 三、每天怎么用

- 一天只起一卦：起卦时刻记在本机，重新打开还是同一卦；换一天自动换卦。
- 「近七日」里点任意一天，可以重读那天的卦；「回到今日」回到今天。
- 设置里「重新起卦」会用当下时辰换掉今天的卦（原来的今日卦被替换）。
- 页脚会显示本地引擎版本和已缓存断语数量。

---

## 四、它算得准吗

算法来自已有的「每日运势」自动化系统，那套引擎做过独立基准校核：

- 太阳黄经、月亮位置与 Meeus《Astronomical Algorithms》例题对比；
- 节气时刻、农历换算与外部锚点逐日比对；
- 日柱干支四个独立锚点、黄历 1500 天在线对照、50 项自检。

已知限度写在「推演依据与限度」和「命盘 → 依据与限度」里：节气时刻可能差 1–12 分钟，
二十八宿值日、晚子时、旺衰权重等存在流派差异。它是一个自洽的参照系，不是事实断言。

本应用属传统文化与自我参照用途，不构成医疗、投资、法律、婚恋等专业建议。

---

## 五、文件结构

```
每日一卦/
├── 每日一卦.app              双击打开的原生桌面版（构建产物，不入库）
├── start.command            浏览器版启动
├── desktop/
│   └── main.swift           Swift + WKWebView 桌面外壳
├── engine/                  历法/四柱/黄历/占星引擎（原自动化任务的引擎）
├── app/
│   ├── server.py            本地服务（静态页 + /api/*，仅 127.0.0.1）
│   ├── fortune.py           把自动化引擎包装成 JSON；本地兜底断语
│   ├── hexagrams.py         六十四卦 + 梅花易数起卦
│   ├── llm.py               OpenAI 兼容接口、提示词、JSON 校验
│   └── static/              index.html / styles.css / app.js
│       └── assets/          罗盘、宋刻本、敦煌星图、米友仁云山、宣纸纹理
├── data/
│   ├── narratives/          已生成的 AI 断语缓存（按日期+卦+命主）
│   └── profile.json         最近一次保存的出生资料（可选）
├── tools/
│   ├── build_desktop.sh     重新打包 每日一卦.app
│   ├── make_icon.py         生成桌面版 AppIcon.icns
│   ├── make_assets.py       重新生成宣纸纹理、压缩馆藏图片
│   ├── mock_api.py          本地假的 OpenAI 接口（联调用，不联网）
│   ├── test_browser.mjs     真浏览器端到端测试
│   └── lib/cdp.mjs          零依赖 CDP 测试辅助
├── preview*.jpg             首屏 / 卦签 / 桌面窗口预览
├── LICENSE                  MIT
├── CONTRIBUTING.md          参与开发
└── README.md
```

引擎已内置在 `engine/`。若想改用别处的引擎，设置 `FORTUNE_ENGINE_ROOT` 指向包含
`engine/` 的目录即可（默认优先使用内置版本）。

---

## 六、开发与验收

```bash
# 重新生成纹理与图片（需要 Pillow）
python3 tools/make_assets.py

# 本地假接口：测试 AI 链路不花钱
python3 tools/mock_api.py 5199
# 设置里填 http://127.0.0.1:5199/v1，Key 随便填

# 端到端测试（需先启动本地服务；需要 Node 22+ 与本机 Chrome/Edge）
node tools/test_browser.mjs
```

> 测试会清空 `data/narratives/` 里的断语缓存；CDP 辅助已内置在 `tools/lib/cdp.mjs`，
> 只在开发时用，平时使用不需要 Node。

`test_browser.mjs` 覆盖：首屏、点八卦、起卦动画、盘心六爻、本地断语、API 测试连接、
AI 解卦、刷新读缓存、API 出错回落、回顾往日、移动端起卦无横向溢出、`prefers-reduced-motion`。
最近一次：**39/39 通过**；`inspect.mjs --app` 在 1440/768/390 三档均为 **0 FAIL**。
桌面版在 macOS 26 / Apple Silicon 上实际编译、启动、起卦、打开设置、缩放窗口和退出都验证过；
`每日一卦.app` 可整体复制到别处运行（验证时从 `/tmp` 启动过）。
保留两条可解释的 WARN：首屏 h1 为 82px（刻意的仪式感标题），以及三种字体
（行楷写卦名/签诗、宋体排正文、楷体作旁注，都是这本「卦书」的材料）。

---

## 七、图片版权

- 风水罗盘：Wellcome Collection，CC BY 4.0，via Wikimedia Commons；
- 宋刻本周易：公有领域，via Wikimedia Commons；
- 敦煌星图：公有领域，via Wikimedia Commons；
- 南宋 米友仁《雲山圖》卷：CC0，via Wikimedia Commons（夜色天幕与页脚的墨山，
  已去色、反相处理为夜色中的淡墨）。

界面中的罗盘是按当日干支用 SVG 重绘、二十八宿圈由 JS 生成，不是照片；照片仅作「器物」对照，
已统一处理成墨色并保留出处与许可。

---

## 八、与原有自动化任务的关系

本项目的 `engine/` 来自作者的「自动化任务」，开源时一并内置；应用运行时不改任何外部配置，
断语缓存在自己的数据目录里。原有定时任务与本项目互不影响。

---

## 九、License

代码以 [MIT](LICENSE) 发布；`engine/` 随主项目一同以 MIT 发布。
图片与馆藏素材的许可见「七、图片版权」。
欢迎提交 Issue / PR，开发方式见 [CONTRIBUTING.md](CONTRIBUTING.md)。
