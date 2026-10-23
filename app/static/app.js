/* 每日一卦 —— 前端
   纯原生 JS，无构建步骤。数据全部来自本地服务 /api/*。 */
(function () {
  "use strict";

  /* ================================================================ 基础 */
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const NS = "http://www.w3.org/2000/svg";
  const REDUCE = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const ZHI = "子丑寅卯辰巳午未申酉戌亥".split("");
  const MOUNTAINS = "午丁未坤申庚酉辛戌乾亥壬子癸丑艮寅甲卯乙辰巽巳丙".split("");
  const TRIGRAMS = [
    { num: 1, name: "乾", nature: "天", attr: "健", dir: "西北", angle: 135, bits: [1, 1, 1] },
    { num: 2, name: "兑", nature: "泽", attr: "悦", dir: "正西", angle: 90, bits: [1, 1, 0] },
    { num: 3, name: "离", nature: "火", attr: "丽", dir: "正南", angle: 0, bits: [1, 0, 1] },
    { num: 4, name: "震", nature: "雷", attr: "动", dir: "正东", angle: 270, bits: [1, 0, 0] },
    { num: 5, name: "巽", nature: "风", attr: "入", dir: "东南", angle: 315, bits: [0, 1, 1] },
    { num: 6, name: "坎", nature: "水", attr: "陷", dir: "正北", angle: 180, bits: [0, 1, 0] },
    { num: 7, name: "艮", nature: "山", attr: "止", dir: "东北", angle: 225, bits: [0, 0, 1] },
    { num: 8, name: "坤", nature: "地", attr: "顺", dir: "西南", angle: 45, bits: [0, 0, 0] },
  ];
  const SWATCH = {
    青: "#3f5f52", 绿: "#5c7350", 红: "#9c352a", 橙: "#a9663a", 黄: "#a8924c",
    棕: "#77593f", 白: "#e6e0d2", 金: "#a8853f", 黑: "#2b2723", 蓝: "#33505e",
  };

  const store = {
    get(key, fallback) {
      try {
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : fallback;
      } catch (e) { return fallback; }
    },
    set(key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* 隐私模式 */ }
    },
    del(key) { try { localStorage.removeItem(key); } catch (e) {} },
  };

  const state = {
    meta: null,
    profile: null,
    api: { base: "", key: "", model: "" },
    date: "",
    castAt: null,
    payload: null,
    narrative: null,
    view: "today",
    aiToken: 0,
    typing: null,
    busy: false,
  };

  const pad = (n) => String(n).padStart(2, "0");
  const todayISO = () => {
    const d = new Date();
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  };
  const nowLocal = () => {
    const d = new Date();
    return todayISO() + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  };
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cnDate = (iso) => {
    const [y, m, d] = iso.split("-").map(Number);
    return y + "年" + m + "月" + d + "日";
  };
  const shortDate = (iso) => {
    const [, m, d] = iso.split("-").map(Number);
    return m + "月" + d + "日";
  };
  const weekdayOf = (iso) => "星期" + "日一二三四五六"[new Date(iso + "T12:00:00").getDay()];
  const castKey = (date) => "yigua.cast." + date;

  /* ================================================================ 网络 */
  async function getState() {
    const res = await fetch("/api/state", { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error("本地服务返回 " + res.status);
    return res.json();
  }

  async function post(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* 非 JSON */ }
    if (!res.ok) {
      const message = (data && data.error && data.error.message) || ("本地服务返回 " + res.status);
      const err = new Error(message);
      err.code = data && data.error && data.error.code;
      throw err;
    }
    return data;
  }

  const apiConfigured = () => {
    const base = (state.api.base || "").trim();
    return Boolean(state.api.key) || /127\.0\.0\.1|localhost|0\.0\.0\.0/.test(base);
  };

  /* ================================================================ 罗盘 */
  function svgEl(tag, attrs, text) {
    const el = document.createElementNS(NS, tag);
    if (attrs) Object.keys(attrs).forEach((k) => el.setAttribute(k, attrs[k]));
    if (text != null) el.textContent = text;
    return el;
  }
  const polar = (r, angle) => {
    const rad = (angle * Math.PI) / 180;
    return { x: 300 + r * Math.sin(rad), y: 300 - r * Math.cos(rad) };
  };

  // 三爻画成一个图形（不自造字符）
  function trigramGlyph(bits, opts) {
    const o = Object.assign({ w: 20, h: 2.6, gap: 3.4, color: "var(--ink-faint)", opacity: 1 }, opts || {});
    const g = svgEl("g", { opacity: o.opacity });
    const totalH = o.h * 3 + o.gap * 2;
    [2, 1, 0].forEach((idx, row) => {
      const y = row * (o.h + o.gap) - totalH / 2;
      if (bits[idx]) {
        g.appendChild(svgEl("rect", { x: -o.w / 2, y: y, width: o.w, height: o.h, fill: o.color }));
      } else {
        const seg = o.w * 0.36;
        g.appendChild(svgEl("rect", { x: -o.w / 2, y: y, width: seg, height: o.h, fill: o.color }));
        g.appendChild(svgEl("rect", { x: o.w / 2 - seg, y: y, width: seg, height: o.h, fill: o.color }));
      }
    });
    return g;
  }

  /* ---- 天幕：星、二十八宿圈、开运小罗盘 ------------------------------- */
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function buildStars(box, count, seed) {
    if (!box) return;
    box.innerHTML = "";
    const rnd = mulberry32(seed);
    for (let i = 0; i < count; i += 1) {
      const star = document.createElement("i");
      const size = (rnd() < 0.88 ? 0.8 : 1.5) + rnd() * 0.9;
      star.style.setProperty("--x", (rnd() * 100).toFixed(2) + "%");
      star.style.setProperty("--y", (rnd() * 100).toFixed(2) + "%");
      star.style.setProperty("--s", size.toFixed(1) + "px");
      star.style.setProperty("--o", (0.22 + rnd() * 0.62).toFixed(2));
      star.style.setProperty("--t", (3.2 + rnd() * 5.5).toFixed(1) + "s");
      star.style.setProperty("--d", (-rnd() * 8).toFixed(1) + "s");
      if (rnd() < 0.07) star.className = "is-gold";
      box.appendChild(star);
    }
  }

  const MANSIONS = "角亢氐房心尾箕斗牛女虚危室壁奎娄胃昴毕觜参井鬼柳星张翼轸".split("");

  function buildOrbit(selector) {
    const box = $(selector || "#stage-orbit");
    if (!box) return;
    const NSVG = 720;
    const c = NSVG / 2;
    const svg = svgEl("svg", { viewBox: "0 0 " + NSVG + " " + NSVG, "aria-hidden": "true", focusable: "false" });
    svg.appendChild(svgEl("circle", { cx: c, cy: c, r: 352, class: "orbit-line" }));
    svg.appendChild(svgEl("circle", { cx: c, cy: c, r: 326, class: "orbit-line" }));
    MANSIONS.forEach((name, i) => {
      const angle = (i * 360) / MANSIONS.length;
      const g = svgEl("g", { transform: "rotate(" + angle + " " + c + " " + c + ")" });
      g.appendChild(svgEl("text", { x: c, y: 16 }, name));
      const t1 = c - 350;
      const t2 = c - 339;
      g.appendChild(svgEl("line", { x1: c, y1: t1, x2: c, y2: t2, class: "orbit-tick" }));
      svg.appendChild(g);
    });
    [0, 90, 180, 270].forEach((angle) => {
      const g = svgEl("g", { transform: "rotate(" + angle + " " + c + " " + c + ")" });
      g.appendChild(svgEl("line", { x1: c, y1: 4, x2: c, y2: 30, class: "orbit-tick", style: "stroke:rgba(201,171,117,.75)" }));
      svg.appendChild(g);
    });
    box.appendChild(svg);
  }

  const DIR_ANGLE = { "正北": 0, "东北": 45, "正东": 90, "东南": 135, "正南": 180, "西南": 225, "正西": 270, "西北": 315 };
  function dirAngle(dir) {
    for (const key of Object.keys(DIR_ANGLE)) if (String(dir || "").indexOf(key) >= 0) return DIR_ANGLE[key];
    return 0;
  }

  function buildCompass(dir) {
    const box = $("#open-compass");
    if (!box) return;
    box.innerHTML = "";
    const size = 120;
    const c = 60;
    const svg = svgEl("svg", { viewBox: "0 0 " + size + " " + size, "aria-hidden": "true", focusable: "false" });
    svg.appendChild(svgEl("circle", { cx: c, cy: c, r: 54, class: "oc-ring" }));
    svg.appendChild(svgEl("circle", { cx: c, cy: c, r: 36, class: "oc-ring" }));
    [["北", 0], ["东北", 45], ["东", 90], ["东南", 135], ["南", 180], ["西南", 225], ["西", 270], ["西北", 315]].forEach(([label, angle]) => {
      const rad = (angle * Math.PI) / 180;
      const r = 45;
      svg.appendChild(svgEl("text", {
        x: (c + r * Math.sin(rad)).toFixed(1),
        y: (c - r * Math.cos(rad)).toFixed(1),
        class: "oc-text",
      }, label));
    });
    const angle = dirAngle(dir);
    const rad = (angle * Math.PI) / 180;
    const tip = { x: c + 30 * Math.sin(rad), y: c - 30 * Math.cos(rad) };
    const side = { x: 4 * Math.cos(rad), y: 4 * Math.sin(rad) };
    const back = { x: c - 12 * Math.sin(rad), y: c + 12 * Math.cos(rad) };
    svg.appendChild(svgEl("path", {
      d: "M" + tip.x + "," + tip.y + " L" + (c + side.x) + "," + (c + side.y) +
        " L" + back.x + "," + back.y + " L" + (c - side.x) + "," + (c - side.y) + " Z",
      class: "oc-needle",
    }));
    svg.appendChild(svgEl("circle", { cx: c, cy: c, r: 3, class: "oc-center" }));
    box.appendChild(svg);
  }

  function hexFigure(lines, opts) {
    const o = Object.assign({ w: 76, h: 9, gap: 13, dot: true }, opts || {});
    const total = o.w + (o.dot ? 20 : 0);
    const height = 6 * (o.h + o.gap) - o.gap;
    const svg = svgEl("svg", {
      viewBox: "0 0 " + total + " " + height,
      class: "hex-svg",
      "aria-hidden": "true",
      focusable: "false",
    });
    const ordered = lines.slice().reverse(); // 上爻在上
    ordered.forEach((line, i) => {
      const y = i * (o.h + o.gap);
      const group = svgEl("g", { class: "line-group" });
      const fill = line.moving ? "var(--cinnabar)" : "var(--ink)";
      if (line.yang) {
        group.appendChild(svgEl("rect", { x: 0, y: y, width: o.w, height: o.h, fill: fill, class: "line" }));
      } else {
        const seg = (o.w - o.w * 0.16) / 2;
        group.appendChild(svgEl("rect", { x: 0, y: y, width: seg, height: o.h, fill: fill, class: "line" }));
        group.appendChild(svgEl("rect", { x: o.w - seg, y: y, width: seg, height: o.h, fill: fill, class: "line" }));
      }
      if (line.moving && o.dot) {
        group.appendChild(svgEl("circle", { cx: o.w + 10, cy: y + o.h / 2, r: Math.max(3, o.h * 0.42), fill: "var(--cinnabar)", class: "hex-dot-mark" }));
      }
      svg.appendChild(group);
    });
    return svg;
  }

  function buildDial(dayZhi) {
    const svg = $("#dial");
    if (!svg) return;
    if (state.dialDay === dayZhi && svg.childElementCount) return;
    state.dialDay = dayZhi;
    svg.innerHTML = "";

    // 天心十道
    const cross = svgEl("g", { class: "cross" });
    [0, 90, 180, 270].forEach((a) => {
      const p1 = polar(58, a);
      const p2 = polar(294, a);
      cross.appendChild(svgEl("line", { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, class: "hairline" }));
    });
    svg.appendChild(cross);

    // 静态圈线
    [294, 260, 176, 136, 100].forEach((r) => {
      svg.appendChild(svgEl("circle", { cx: 300, cy: 300, r: r, class: "ring-line" }));
    });

    // 三层盘：外层顺时针、中层八卦逆时针、内层顺时针；起卦时整体再转一圈
    const rotator = svgEl("g", { class: "cast-rotator" });
    const outer = svgEl("g", { class: "ring-outer" });
    const mid = svgEl("g", { class: "ring-mid" });
    const inner = svgEl("g", { class: "ring-inner" });

    // 六十四卦刻度（随内层）
    const ticks = svgEl("g", { class: "tick-ring" });
    for (let i = 0; i < 64; i += 1) {
      const a = i * 5.625;
      const big = i % 8 === 0;
      const p1 = polar(big ? 106 : 110, a);
      const p2 = polar(big ? 130 : 124, a);
      ticks.appendChild(svgEl("line", { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y, class: "sector-tick" }));
    }
    inner.appendChild(ticks);

    // 二十四山（随外层）
    MOUNTAINS.forEach((ch, i) => {
      const g = svgEl("g", { transform: "rotate(" + i * 15 + " 300 300)" });
      g.appendChild(svgEl("text", { x: 300, y: 26, class: "t24" }, ch));
      outer.appendChild(g);
    });

    // 十二地支（随内层）
    ZHI.forEach((ch, i) => {
      const a = (i * 30 + 180) % 360;
      const g = svgEl("g", { transform: "rotate(" + a + " 300 300)" });
      const cls = "t-zhi" + (ch === dayZhi ? " is-day" : "");
      g.appendChild(svgEl("text", { x: 300, y: 148, class: cls }, ch));
      inner.appendChild(g);
    });

    // 后天八卦（中层，字正立，方便读；随盘缓转）
    TRIGRAMS.forEach((t) => {
      const pName = polar(202, t.angle);
      const pSym = polar(236, t.angle);
      const pRing = polar(218, t.angle);
      const g = svgEl("g", {
        class: "tri",
        "data-num": t.num,
        tabindex: "0",
        role: "button",
        "aria-label": t.name + " " + t.nature + " " + t.attr + "，" + t.dir,
      });
      g.appendChild(svgEl("circle", { cx: pRing.x, cy: pRing.y, r: 52, class: "tri-hit" }));
      g.appendChild(svgEl("circle", { cx: pRing.x, cy: pRing.y, r: 46, class: "tri-ring" }));
      const glyph = trigramGlyph(t.bits, { w: 18, h: 2.2, gap: 2.8, color: "var(--ink-faint)" });
      glyph.setAttribute("transform", "translate(" + pSym.x + "," + pSym.y + ")");
      g.appendChild(glyph);
      g.appendChild(svgEl("text", { x: pName.x, y: pName.y, class: "t-tri" }, t.name));
      mid.appendChild(g);
    });

    // 内圈八卦符号（随中层）
    TRIGRAMS.forEach((t) => {
      const p = polar(84, t.angle);
      const glyph = trigramGlyph(t.bits, { w: 14, h: 2, gap: 2.4, color: "var(--ink-faint)", opacity: 0.85 });
      glyph.setAttribute("transform", "translate(" + p.x + "," + p.y + ")");
      mid.appendChild(glyph);
    });

    // 日支标记随内层地支盘一起转，始终钉在「午」字旁边
    if (dayZhi) {
      const idx = ZHI.indexOf(dayZhi);
      const a = (idx * 30 + 180) % 360;
      const p = polar(161, a);
      inner.appendChild(svgEl("circle", { cx: p.x, cy: p.y, r: 3.2, class: "day-mark" }));
      inner.appendChild(svgEl("circle", { cx: p.x, cy: p.y, r: 8, class: "day-mark-ring" }));
    }

    rotator.appendChild(outer);
    rotator.appendChild(mid);
    rotator.appendChild(inner);
    svg.appendChild(rotator);

    // 天池与太极
    svg.appendChild(svgEl("circle", { cx: 300, cy: 300, r: 58, class: "pool", fill: "var(--paper)", stroke: "rgba(27,25,21,.45)", "stroke-width": "1" }));
    const taiji = svgEl("g", { class: "taiji" });
    taiji.appendChild(svgEl("path", {
      d: "M300,242 A58,58 0 0 1 300,358 A29,29 0 0 0 300,300 A29,29 0 0 1 300,242 Z",
      fill: "var(--ink)",
    }));
    taiji.appendChild(svgEl("circle", { cx: 300, cy: 271, r: 9, fill: "var(--paper)" }));
    taiji.appendChild(svgEl("circle", { cx: 300, cy: 329, r: 9, fill: "var(--ink)" }));
    svg.appendChild(taiji);

    // 起卦后的六爻
    const hex = svgEl("g", { class: "hex-group" });
    hex.setAttribute("data-slot", "hex");
    svg.appendChild(hex);

    // 涟漪
    svg.appendChild(svgEl("circle", { cx: 300, cy: 300, r: 58, class: "ripple" }));

    // 交互
    $$(".tri", svg).forEach((g) => {
      const num = Number(g.getAttribute("data-num"));
      const t = TRIGRAMS.find((x) => x.num === num);
      const show = () => {
        $("#dial-cap").textContent = t.name + " · " + t.nature + " · " + t.attr + "｜后天" + t.dir +
          (dayZhi ? "，今日日支「" + dayZhi + "」以朱砂标出" : "");
      };
      g.addEventListener("click", show);
      g.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); show(); }
      });
    });
  }

  function drawDialHex(payload, animate) {
    const svg = $("#dial");
    if (!svg || !payload) return;
    const old = $(".hex-group", svg);
    if (old) old.remove();
    const hex = svgEl("g", { class: "hex-group" });
    const lines = payload.hexagram.lines;
    const ordered = lines.slice().reverse();
    ordered.forEach((line, i) => {
      const y = 262 + i * 14;
      const g = svgEl("g", { class: "line-group" });
      const fill = "var(--ink)";
      if (line.yang) {
        g.appendChild(svgEl("rect", { x: 268, y: y, width: 64, height: 6, fill: fill, class: "hex-line" }));
      } else {
        g.appendChild(svgEl("rect", { x: 268, y: y, width: 27, height: 6, fill: fill, class: "hex-line" }));
        g.appendChild(svgEl("rect", { x: 305, y: y, width: 27, height: 6, fill: fill, class: "hex-line" }));
      }
      g.querySelectorAll(".hex-line").forEach((el) => {
        el.style.animationDelay = animate ? 90 * i + "ms" : "0ms";
      });
      hex.appendChild(g);
    });
    // 动爻
    const moving = payload.hexagram.moving.line;
    const dotY = 262 + (6 - moving) * 14 + 3;
    hex.appendChild(svgEl("circle", { cx: 342, cy: dotY, r: 3, class: "hex-dot" }));
    svg.appendChild(hex);
    const taiji = $(".taiji", svg);
    if (taiji) taiji.classList.add("is-gone");
    // 下一帧再触发，保证过渡/动画开始
    requestAnimationFrame(() => hex.classList.add("is-drawn"));
  }

  function resetDial() {
    const svg = $("#dial");
    if (!svg) return;
    svg.classList.remove("is-casting");
    const hex = $(".hex-group", svg);
    if (hex) hex.remove();
    const taiji = $(".taiji", svg);
    if (taiji) taiji.classList.remove("is-gone");
  }

  async function playCast(payloadPromise) {
    const svg = $("#dial");
    if (!svg) return payloadPromise;
    if (REDUCE) {
      const p = await payloadPromise;
      drawDialHex(p, false);
      return p;
    }
    svg.classList.add("is-casting");
    const stage = $("#stage");
    if (stage) {
      stage.classList.remove("is-casting");
      void stage.offsetWidth;
      stage.classList.add("is-casting");
      setTimeout(() => stage.classList.remove("is-casting"), 2400);
    }
    const taiji = $(".taiji", svg);
    await wait(820);
    const payload = await payloadPromise;
    if (payload) drawDialHex(payload, true);
    if (taiji) taiji.classList.add("is-gone");
    await wait(1150);
    svg.classList.remove("is-casting");
    return payload;
  }

  /* ================================================================ 今日视图 */
  function setHeroDate(iso) {
    $("#date-greg").textContent = cnDate(iso);
    $("#date-week").textContent = weekdayOf(iso);
  }

  function shortJieqi(text) {
    const m = String(text || "").match(/(?:已过|已到)\s*([^（(]+)\([^)]*\)[^；]*；下一节气\s*([^（(]+)\([^)]*?(\d+)\s*天后/);
    if (m) return m[1].trim() + "已过 · 距" + m[2].trim() + m[3] + "天";
    return text || "—";
  }

  function renderFacts(payload) {
    const dl = $("#today-facts");
    dl.innerHTML = "";
    const add = (label, value, opts) => {
      const wrap = document.createElement("div");
      if (opts && opts.wide) wrap.className = "fact-wide";
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      if (opts && opts.html) dd.innerHTML = value; else dd.textContent = value;
      wrap.append(dt, dd);
      dl.appendChild(wrap);
    };
    const d = payload.day;
    add("农历", payload.lunar.text + (payload.lunar.zodiac ? " · 肖" + payload.lunar.zodiac : ""));
    add("日课", d.ganzhi + "日 · " + d.jianchu.name + "日" + (d.nayin ? " · " + d.nayin : ""));
    add("建除", d.jianchu.name + "日 · " + d.jianchu.shen + (d.jianchu.huangdao ? "（黄道）" : "（黑道）"));
    add("值宿", d.xiu.name + "宿 · " + d.xiu.ji_xiong);
    add("冲煞", d.chong.text);
    add("月相", payload.moon.phase + " · 照亮 " + payload.moon.illum + "%");
    add("节气", shortJieqi(d.jieqi), { wide: true });
  }

  function renderHeroState(payload, opts) {
    const o = opts || {};
    const isToday = state.date === state.meta.today;
    const castBtn = $("#cast-btn");
    const readLink = $("#read-link");
    const status = $("#hero-status");
    $("#hero-title").textContent = isToday ? "今日一卦" : "往日一卦";
    setHeroDate(state.date);
    renderFacts(payload);
    const v1 = $("#v-line-1");
    if (v1) v1.textContent = payload.lunar.year_text + "年 " + payload.lunar.month_name + payload.lunar.day_name;
    const v2 = $("#v-line-2");
    if (v2) v2.textContent = payload.day.ganzhi + "日 " + payload.day.jianchu.name + "日 · " + payload.day.xiu.name + "宿";

    if (o.review) {
      castBtn.hidden = true;
      readLink.hidden = true;
      status.textContent = "正在回顾 " + shortDate(state.date) + " 的卦。往日不可再起，只可重读。";
      return;
    }
    if (state.castAt) {
      castBtn.hidden = true;
      readLink.hidden = false;
      const hhmm = state.castAt.slice(11, 16);
      status.textContent = "今日卦已起于 " + hhmm + "（" + payload.hexagram.inputs.时辰 + "）· " +
        payload.hexagram.name + " · 综合 " + payload.scores.overall + " 分";
      readLink.textContent = "查看今日卦";
    } else {
      castBtn.hidden = false;
      castBtn.disabled = false;
      readLink.hidden = true;
      status.textContent = "";
    }
  }

  function renderReading(payload) {
    state.payload = payload;
    state.narrative = payload.narrative;
    const hx = payload.hexagram;
    const narrative = payload.narrative || {};

    const fig = $("#hex-figure");
    fig.innerHTML = "";
    fig.appendChild(hexFigure(hx.lines, { w: 76, h: 9, gap: 13 }));

    $("#reading-title").textContent = hx.name;
    $("#hex-sub").textContent = "第" + hx.number + "卦 · 上" + hx.upper.name + hx.upper.nature + "，下" +
      hx.lower.name + hx.lower.nature + " · 动" + hx.moving.name + " · 变" + hx.changed.name +
      " · 体用" + hx.tiyong.word;

    const stamp = $("#score-stamp");
    stamp.setAttribute("aria-label", "综合运势 " + payload.scores.overall + " 分，" + payload.scores.word);
    $(".stamp-score", stamp).textContent = payload.scores.overall;
    $(".stamp-word", stamp).textContent = payload.scores.word;

    renderPoem(narrative);
    const slipSeal = $("#slip-seal");
    if (slipSeal) slipSeal.textContent = (payload.scores.word || "占").slice(0, 1);
    $("#yi").textContent = (payload.almanac.yi || []).join("、") || "—";
    $("#ji").textContent = (payload.almanac.ji || []).join("、") || "—";
    renderOpen(payload);
    renderHours(payload);
    renderBasis(payload);
    renderHistory();
    paintNarrative(narrative, { typewrite: false });

    const foot = $("#reading-footnote");
    const cast = state.castAt || (payload.hexagram.cast_at + ":00");
    foot.textContent = "本卦以 " + payload.date + " " + (cast.length > 10 ? cast.slice(11, 16) : "00:05") +
      "（" + hx.inputs.时辰 + "）起：年支" + hx.inputs.年支数 + " + 农历" + hx.inputs.农历月 + "月" +
      hx.inputs.农历日 + "日，上卦得" + hx.upper.name + "，加时得下卦" + hx.lower.name + "，动" +
      hx.moving.name + "。卦由时间定，不随机抽取；一日起一卦。";
  }

  function paintNarrative(n, opts) {
    const o = opts || {};
    if (!n) return;
    state.narrative = n;
    if (state.payload) state.payload.narrative = n;
    renderPoem(n);
    renderAreas(state.payload, n);
    const badge = $("#source-badge");
    badge.hidden = false;
    const isAi = n.source === "ai";
    badge.textContent = isAi ? "AI 解卦" : "本地断语";
    badge.className = "badge " + (isAi ? "is-live" : "is-local");
    const text = $("#reading-text");
    if (o.typewrite && !REDUCE) typeText(text, n.reading || "");
    else { text.textContent = n.reading || ""; text.classList.remove("is-typing"); }
    const tips = $("#reading-tips");
    if (tips) {
      if (n.action || n.caution) {
        tips.hidden = false;
        tips.innerHTML = '<div class="tip"><dt>可行</dt><dd>' + esc(n.action || "—") + "</dd></div>" +
          '<div class="tip"><dt>宜避</dt><dd>' + esc(n.caution || "—") + "</dd></div>";
      } else {
        tips.hidden = true;
      }
    }
    const status = $("#reading-status");
    if (isAi) {
      const fixed = (n.fixed_fields || []).length;
      status.innerHTML = "解卦由 " + esc(n.model || "AI") + " 生成" +
        (fixed ? "，其中 " + fixed + " 处按本地规则校正" : "") + "。今日卦与排盘在本地计算。";
    } else {
      status.textContent = "";
    }
  }

  function renderPoem(narrative) {
    const box = $("#poem");
    box.innerHTML = "";
    (narrative.poem || []).forEach((line) => {
      const p = document.createElement("p");
      p.textContent = line;
      box.appendChild(p);
    });
    $("#judgement").textContent = narrative.judgement || "";
  }

  function renderAreas(payload, narrative) {
    const list = $("#areas");
    list.innerHTML = "";
    const areaText = narrative.areas || {};
    payload.scores.areas.forEach((a, i) => {
      const li = document.createElement("li");
      li.style.setProperty("--i", i);
      const name = document.createElement("span");
      name.className = "area-name";
      name.textContent = a.area;
      const score = document.createElement("span");
      score.className = "area-score";
      score.textContent = a.score;
      const note = document.createElement("span");
      note.className = "area-note";
      note.textContent = areaText[a.area] || (a.notes && a.notes[0]) || "";
      const meter = document.createElement("span");
      meter.className = "meter";
      const bar = document.createElement("i");
      bar.style.width = Math.max(4, Math.min(100, a.score)) + "%";
      bar.style.transform = "scaleX(0)";
      meter.appendChild(bar);
      li.append(name, score, meter, note);
      list.appendChild(li);
      requestAnimationFrame(() => {
        setTimeout(() => { bar.style.transition = "transform 700ms cubic-bezier(.16,1,.3,1)"; bar.style.transform = "scaleX(1)"; }, REDUCE ? 0 : 120 + i * 60);
      });
    });
  }

  function renderOpen(payload) {
    const dl = $("#open-list");
    dl.innerHTML = "";
    const o = payload.open;
    const rows = [];
    const colorNames = String(o.color || "").split("、").filter(Boolean);
    const swatches = colorNames.map((c) => '<span class="swatch" style="background:' + (SWATCH[c] || "transparent") +
      ";border:1px solid rgba(27,25,21,.28)\" title=\"" + esc(c) + '"></span>').join("");
    rows.push(["五行", o.wuxing || "—"]);
    rows.push(["颜色", '<span>' + esc(o.color || "—") + '</span><span class="swatches">' + swatches + "</span>", true]);
    rows.push(["方位", '<span class="dir-arrow">' + arrowSvg(o.direction) + "</span>" + esc(o.direction || "—"), true]);
    rows.push(["数字", (o.numbers || []).join(" · ") || "—"]);
    const sf = o.shenfang || {};
    if (sf["喜神"]) rows.push(["喜神", sf["喜神"]]);
    if (sf["财神"]) rows.push(["财神", sf["财神"]]);
    rows.forEach(([dt, dd, html]) => {
      const row = document.createElement("div");
      row.className = "row";
      const t = document.createElement("dt");
      t.textContent = dt;
      const d = document.createElement("dd");
      if (html) d.innerHTML = dd; else d.textContent = dd;
      row.append(t, d);
      dl.appendChild(row);
    });
    buildCompass(o.direction);
  }

  function arrowSvg(dir) {
    const map = {
      正东: 90, 正南: 180, 正西: 270, 正北: 0,
      东南: 135, 西南: 225, 西北: 315, 东北: 45,
    };
    const deg = map[dir] != null ? map[dir] : 0;
    return '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" style="transform:rotate(' + deg + 'deg)"><path d="M7 1 L11 12 L7 9.6 L3 12 Z" fill="var(--ink)"/></svg>';
  }

  function renderHours(payload) {
    const list = $("#hours");
    list.innerHTML = "";
    const castShichen = payload.hexagram && payload.hexagram.inputs ? payload.hexagram.inputs.时辰 : "";
    (payload.hours || []).forEach((h) => {
      const li = document.createElement("li");
      li.title = h.note || "";
      if (castShichen && h.shichen === castShichen) li.className = "is-now";
      const name = document.createElement("span");
      name.className = "h-name";
      name.textContent = h.shichen.replace("时", "");
      const mark = document.createElement("span");
      mark.className = "h-mark " + (h.ji_xiong === "吉" ? "is-ji" : "is-xiong");
      mark.textContent = h.ji_xiong;
      li.append(name, mark);
      list.appendChild(li);
    });
  }

  function renderBasis(payload) {
    const box = $("#basis-body");
    const p = payload;
    const section = (title, rows) => {
      if (!rows.length) return "";
      return '<div class="basis-group"><p class="basis-sub">' + esc(title) + "</p><ul>" + rows.map((r) =>
        "<li><span>" + esc(r[0]) + "</span><span>" + esc(r[1]) + "</span></li>").join("") + "</ul></div>";
    };
    let html = "";
    html += section("日课", [
      ["干支", p.day.ganzhi + "日 · 旬" + (p.day.xun || "—") + " · 空亡" + ((p.day.kongwang || []).join("") || "—")],
      ["建除", p.day.jianchu.name + "日 · " + p.day.jianchu.shen + (p.day.jianchu.huangdao ? " · 黄道" : " · 黑道")],
      ["值宿", p.day.xiu.name + "宿 · " + p.day.xiu.gong + " · " + p.day.xiu.ji_xiong],
      ["冲煞", p.day.chong.text],
      ["节气", p.day.jieqi],
      ["月相", p.moon.phase + "，照亮 " + p.moon.illum + "% · " + p.moon.void],
    ]);
    const yj = [];
    if (p.almanac.score_detail) {
      Object.keys(p.almanac.score_detail).forEach((k) => {
        if (k !== "合计" && k !== "等级") yj.push([k, String(p.almanac.score_detail[k])]);
      });
    }
    html += section("黄历评分（" + (p.almanac.score_detail && p.almanac.score_detail["合计"] != null ? p.almanac.score_detail["合计"] : p.scores.almanac) + "）", yj);
    const rel = [];
    if (p.relation.text) rel.push(["日柱与命局", p.relation.text]);
    (p.relation.highlights || []).forEach((x) => rel.push(["加分", x]));
    (p.relation.cautions || []).forEach((x) => rel.push(["留意", x]));
    html += section("命理", rel);
    const st = (p.astro.aspects || []).slice(0, 5).map((a) => [
      a.nature || "—", a.transit + a.aspect + a.natal + " · " + a.orb + "°",
    ]);
    html += section("行运相位", st);
    html += section("起卦", [
      ["法", p.hexagram.method],
      ["数", "年支" + p.hexagram.inputs.年支数 + " / 月" + p.hexagram.inputs.农历月 + " / 日" +
        p.hexagram.inputs.农历日 + " / 时" + p.hexagram.inputs.时辰数 + "（" + p.hexagram.inputs.时辰 + "）"],
      ["体用", p.hexagram.tiyong.ti + "为体，" + p.hexagram.tiyong.yong + "为用 · " + p.hexagram.tiyong.note],
      ["变卦", p.hexagram.changed.name + " · 互卦" + p.hexagram.hu.name],
    ]);
    const warnings = (p.almanac.warnings || []).concat(p.bazi.warnings || []).slice(0, 3);
    if (warnings.length) html += section("流派提示", warnings.map((w) => ["存疑", w]));
    const src = [];
    src.push(["引擎", p.engine.path]);
    if (p.narrative && p.narrative.source === "ai") src.push(["解卦", p.narrative.model || "AI"]);
    else src.push(["解卦", "本地规则拼合"]);
    html += section("来源", src);
    html += '<div class="basis-group"><p class="note">黄历、八字、占星均为本地推算；梅花易数依年月日时起卦。不同流派在晚子时、二十八宿值日、旺衰权重等处存在分歧，结果只作自我参照。</p></div>';
    box.innerHTML = html;
  }

  function renderHistory() {
    const list = $("#history");
    if (!list) return;
    const items = store.get("yigua.history", []);
    list.innerHTML = "";
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "empty";
      li.textContent = "今日起卦后，卦象会记在这里。";
      list.appendChild(li);
      return;
    }
    items.slice(0, 7).forEach((it) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.innerHTML = '<span class="h-top"><span class="h-date">' + esc(shortDate(it.date)) +
        '</span><span class="h-score">' + esc(it.score) + " 分</span></span>" +
        '<span class="h-mid"><span class="h-symbol">' + esc(it.symbol || "") + '</span>' +
        '<span class="h-name">' + esc(it.name || "") + "</span></span>";
      btn.addEventListener("click", () => openDay(it.date, it.castAt, true));
      li.appendChild(btn);
      list.appendChild(li);
    });
  }

  function ensureHistory(payload) {
    if (!state.castAt || !payload || payload.date !== state.meta.today) return;
    const items = store.get("yigua.history", []);
    if (items.some((x) => x.date === payload.date)) return;
    items.unshift({
      date: payload.date,
      name: payload.hexagram.name,
      symbol: payload.hexagram.symbol,
      score: payload.scores.overall,
      castAt: state.castAt,
    });
    store.set("yigua.history", items.slice(0, 14));
    renderHistory();
  }

  function saveHistory(it) {
    let items = store.get("yigua.history", []);
    items = items.filter((x) => x.date !== it.date);
    items.unshift(it);
    items = items.slice(0, 14);
    store.set("yigua.history", items);
  }

  /* ================================================================ 阅读区显隐 */
  function makeRevealObserver() {
    if (state.revealObserver) return state.revealObserver;
    state.revealObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-in");
          state.revealObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });
    return state.revealObserver;
  }

  function observeReveals(root) {
    const io = makeRevealObserver();
    $$(".reveal", root).forEach((el) => {
      el.classList.remove("is-in");
      io.observe(el);
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight * 0.94) {
        el.classList.add("is-in");
        io.unobserve(el);
      }
    });
  }

  function revealReading(payload, opts) {
    const o = opts || {};
    renderReading(payload);
    const reading = $("#reading");
    reading.hidden = false;
    document.body.classList.add("has-reading");
    reading.classList.remove("is-open");
    void reading.offsetWidth;
    reading.classList.add("is-open");
    observeReveals(reading);
    if (o.scroll) {
      setTimeout(() => {
        reading.scrollIntoView({ behavior: REDUCE ? "auto" : "smooth", block: "start" });
      }, REDUCE ? 0 : 260);
    }
  }

  function updateReviewBar() {
    const reading = $("#reading");
    let bar = $(".review-bar", reading);
    if (state.date === state.meta.today) {
      if (bar) bar.remove();
      return;
    }
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "review-bar wrap";
      bar.innerHTML = '<span>正在读 <span class="review-date"></span> 的卦，今日尚未起卦。</span>';
      bar.appendChild(makeBackToday());
      reading.insertBefore(bar, reading.firstChild);
    }
    $(".review-date", bar).textContent = shortDate(state.date) + "（" + state.payload.day.ganzhi + "日）";
  }

  function makeBackToday() {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "回到今日";
    btn.addEventListener("click", () => goToday());
    return btn;
  }

  function goToday() {
    openDay(state.meta.today, store.get(castKey(state.meta.today), null));
  }

  /* ================================================================ 数据加载 */
  function applyNarrative(n, opts) {
    paintNarrative(n, opts);
    renderBasis(state.payload);
  }

  function typeText(el, text) {
    if (state.typing) cancelAnimationFrame(state.typing);
    el.textContent = "";
    el.classList.add("is-typing");
    const chars = Array.from(text);
    let i = 0;
    const start = performance.now();
    const speed = 9;
    const step = (now) => {
      const target = Math.min(chars.length, Math.floor((now - start) / speed));
      if (target > i) {
        i = target;
        el.textContent = chars.slice(0, i).join("");
      }
      if (i < chars.length) state.typing = requestAnimationFrame(step);
      else el.classList.remove("is-typing");
    };
    state.typing = requestAnimationFrame(step);
  }

  async function requestNarrative(opts) {
    const o = opts || {};
    if (!state.payload || !state.castAt) return;
    if (state.meta && state.date !== state.meta.today) return;
    if (!apiConfigured()) {
      const status = $("#reading-status");
      status.innerHTML = "本地断语由规则拼合。填入 API Key 后，这里会换成更贴合的 AI 解卦。" +
        '<button class="retry" type="button" data-open-settings>去填写</button>';
      const btn = $("[data-open-settings]", status);
      if (btn) btn.addEventListener("click", openSettings);
      return;
    }
    if (state.narrative && state.narrative.source === "ai" && !o.refresh) return;
    const token = ++state.aiToken;
    const status = $("#reading-status");
    status.textContent = "问天中：正在把卦象与命盘解成给你的话，通常十几秒。";
    try {
      const res = await post("/api/fortune", {
        date: state.date,
        cast_at: state.castAt,
        profile: state.profile,
        ai: true,
        refresh: Boolean(o.refresh),
        api: state.api,
      });
      if (token !== state.aiToken) return;
      const data = res.data;
      state.payload = data;
      const narrative = data.narrative;
      applyNarrative(narrative, { typewrite: o.typewrite !== false && narrative.source === "ai" });
      if (res.meta && res.meta.ai_error) {
        status.innerHTML = esc(res.meta.ai_error) + " 已显示本地断语。" +
          '<button class="retry" type="button" id="retry-ai">重试</button>';
        const retry = $("#retry-ai");
        if (retry) retry.addEventListener("click", () => requestNarrative({ refresh: true }));
      }
    } catch (err) {
      if (token !== state.aiToken) return;
      status.innerHTML = esc(err.message || "AI 解卦失败") + " 已显示本地断语。" +
        '<button class="retry" type="button" id="retry-ai">重试</button>';
      const retry = $("#retry-ai");
      if (retry) retry.addEventListener("click", () => requestNarrative({ refresh: true }));
    }
  }

  async function loadDay(opts) {
    const o = opts || {};
    if (state.busy) return;
    state.busy = true;
    try {
      const res = await post("/api/fortune", {
        date: state.date,
        cast_at: state.castAt,
        profile: state.profile,
        ai: false,
      });
      state.payload = res.data;
      state.narrative = res.data.narrative;
      renderHeroState(res.data, { review: state.date !== state.meta.today });
      renderChartPage(res.data);
      buildDial(res.data.day.zhi);
      const dzhi = res.data.day.zhi;
      const dcap = $("#dial-cap");
      if (dcap) {
        dcap.textContent = "罗盘 · 今日日支「" + dzhi + "」以朱砂标出 · 点八卦看卦象";
      }
      const hasReading = Boolean(state.castAt) || state.date !== state.meta.today;
      if (hasReading) {
        drawDialHex(res.data, !REDUCE);
        revealReading(res.data, { scroll: Boolean(o.scroll) });
      } else {
        resetDial();
        document.body.classList.remove("has-reading");
        const reading = $("#reading");
        reading.hidden = true;
        reading.classList.remove("is-open");
      }
      updateReviewBar();
      ensureHistory(res.data);
      if (!o.skipAi && state.castAt && state.date === state.meta.today) {
        requestNarrative({ typewrite: false });
      }
    } catch (err) {
      showError(err.message || "读取今日数据失败");
    } finally {
      state.busy = false;
    }
    if (state.view === "chart") renderChartPage(state.payload);
  }

  function openDay(date, castAt) {
    state.date = date;
    state.castAt = date === state.meta.today ? store.get(castKey(date), null) : (castAt || null);
    resetDial();
    loadDay({ reveal: true, scroll: false });
  }

  async function cast() {
    if (state.busy || state.date !== state.meta.today) return;
    if (!state.payload) return;
    const castAt = nowLocal();
    state.castAt = castAt;
    store.set(castKey(state.date), castAt);
    const btn = $("#cast-btn");
    btn.disabled = true;
    btn.classList.add("is-pressing");
    btn.setAttribute("aria-busy", "true");
    $("#hero-status").textContent = "拨盘、落爻、起卦……";
    const payloadPromise = post("/api/fortune", {
      date: state.date, cast_at: castAt, profile: state.profile, ai: false,
    }).then((r) => r.data).catch((err) => { showError(err.message); return null; });
    const payload = await playCast(payloadPromise);
    if (!payload) {
      btn.disabled = false;
      btn.classList.remove("is-pressing");
      btn.removeAttribute("aria-busy");
      $("#hero-status").textContent = "";
      return;
    }
    state.payload = payload;
    state.narrative = payload.narrative;
    btn.classList.remove("is-pressing");
    btn.removeAttribute("aria-busy");
    renderHeroState(payload);
    renderChartPage(payload);
    revealReading(payload, { scroll: true });
    saveHistory({
      date: payload.date,
      name: payload.hexagram.name,
      symbol: payload.hexagram.symbol,
      score: payload.scores.overall,
      castAt: castAt,
    });
    renderHistory();
    setTimeout(() => requestNarrative({ typewrite: true }), REDUCE ? 0 : 1200);
  }

  /* ================================================================ 命盘 */
  function renderChartPage(payload) {
    if (!payload) return;
    const p = payload;
    const bz = p.bazi;
    $("#chart-lede").textContent = (p.profile.name || "命主") + " · " + p.profile.gender + " · " +
      p.profile.birth + " 生于" + p.profile.place + "。真太阳时 " + (p.profile.true_solar_time || "—") +
      "（" + (p.profile.shichen || "") + "）。四柱 " + bz.pillars.map((x) => x.ganzhi).join(" ") + "。";

    // 四柱
    const table = $("#pillars-table");
    const rows = [
      ["天干", (x) => '<span class="ganzhi">' + esc(x.gan) + '</span><span class="sub">' + esc(x.shishen) + "</span>"],
      ["地支", (x) => '<span class="ganzhi">' + esc(x.zhi) + "</span>"],
      ["藏干", (x) => (x.canggan || []).join("、") || "—"],
      ["纳音", (x) => x.nayin || "—"],
      ["长生", (x) => x.changsheng || "—"],
    ];
    let html = "<thead><tr><th></th>" + bz.pillars.map((x) => "<th>" + esc(x.pos) + "</th>").join("") + "</tr></thead><tbody>";
    rows.forEach(([label, fn]) => {
      html += "<tr><th>" + esc(label) + "</th>" + bz.pillars.map((x) => "<td>" + fn(x) + "</td>").join("") + "</tr>";
    });
    html += "</tbody>";
    table.innerHTML = html;
    $("#pillars-note").textContent = "日主 " + (bz.day_master.gan || "") + (bz.day_master.wuxing || "") +
      "（" + (bz.day_master.yinyang || "") + "）· 身" + (bz.strength.verdict || "") +
      " · 当前大运 " + (bz.current_dayun ? bz.current_dayun.ganzhi + "（" + bz.current_dayun.shishen + "）" : "—") +
      " · 流年 " + (bz.liunian.ganzhi || "");

    // 五行
    const wx = $("#wuxing");
    wx.innerHTML = "";
    const max = Math.max.apply(null, bz.wuxing.map((x) => x.score || 0)) || 1;
    const favor = (bz.xiyong.favor || []);
    const avoid = (bz.xiyong.avoid || []);
    bz.wuxing.forEach((x) => {
      const col = document.createElement("div");
      col.className = "wx-col" + (favor.indexOf(x.name) >= 0 ? " is-favor" : avoid.indexOf(x.name) >= 0 ? " is-avoid" : "");
      const value = document.createElement("span");
      value.className = "wx-value";
      value.textContent = x.score;
      const bar = document.createElement("span");
      bar.className = "wx-bar";
      bar.style.height = Math.max(3, Math.round((x.score / max) * 100)) + "%";
      const name = document.createElement("span");
      name.className = "wx-name";
      name.textContent = x.name;
      col.append(value, bar, name);
      wx.appendChild(col);
      requestAnimationFrame(() => {
        setTimeout(() => col.classList.add("is-in"), REDUCE ? 0 : 160);
      });
    });
    $("#xiyong-text").textContent = "日主" + (bz.day_master.gan || "") + (bz.day_master.wuxing || "") + "，身" +
      (bz.strength.verdict || "") + "。喜 " + (favor.join("、") || "—") + "，忌 " + (avoid.join("、") || "—") +
      "。取用：" + (bz.xiyong.method || "—") + "。";
    $("#strength-text").textContent = bz.strength.detail || "";
    const facts = [
      ["日主", (bz.day_master.gan || "") + (bz.day_master.wuxing || "") + "（" + (bz.day_master.yinyang || "") + "）"],
      ["旺衰", (bz.strength.verdict || "—") + "（评分 " + (bz.strength.score != null ? bz.strength.score : "—") + "）"],
      ["喜用", (favor.join("、") || "—")],
      ["忌神", (avoid.join("、") || "—")],
      ["调候", (bz.xiyong.tiaohou || "—")],
      ["大运", bz.current_dayun ? bz.current_dayun.ganzhi + " · " + (bz.current_dayun.shishen || "") : "—"],
    ];
    $("#chart-facts").innerHTML = facts.map(([k, v]) =>
      "<div class='row'><dt>" + esc(k) + "</dt><dd>" + esc(v) + "</dd></div>").join("");

    // 大运
    const dayun = $("#dayun");
    dayun.innerHTML = "";
    (bz.dayun || []).forEach((d) => {
      const li = document.createElement("li");
      const current = d.start_year <= Number(state.date.slice(0, 4)) && Number(state.date.slice(0, 4)) < d.end_year;
      if (current) li.className = "is-current";
      li.innerHTML = '<span class="dy-gz">' + esc(d.ganzhi) + '</span><span class="dy-year">' +
        esc(d.start_year) + "–" + esc(d.end_year) + '</span><span class="dy-ss">' + esc(d.shishen || "") + "</span>";
      dayun.appendChild(li);
    });
    const qy = bz.qiyun || {};
    const ymd = qy.years_months_days;
    const qyText = ymd && ymd.length === 3 ? ymd[0] + " 岁 " + ymd[1] + " 个月起运" :
      (qy.age_years != null ? qy.age_years + " 岁起运" : "起运 —");
    $("#dayun-note").textContent = qyText + " · 流年 " + (bz.liunian.ganzhi || "") + "（" + (bz.liunian.year || "") + "）";

    // 本命行星
    const planets = $("#natal-planets");
    let ph = "<thead><tr><th>行星</th><th>位置</th><th>宫位</th></tr></thead><tbody>";
    (p.astro.natal.planets || []).forEach((x) => {
      ph += "<tr><td>" + esc(x.planet) + (x.retro ? '<span class="retro">逆</span>' : "") +
        "</td><td>" + esc(x.text) + '</td><td class="num">' + esc(x.house) + "</td></tr>";
    });
    ph += "</tbody>";
    planets.innerHTML = ph;

    const aspects = $("#natal-aspects");
    aspects.innerHTML = "";
    (p.astro.natal.aspects || []).slice(0, 10).forEach((a) => {
      const li = document.createElement("li");
      li.innerHTML = "<span>" + esc(a.a) + " " + esc(a.aspect) + " " + esc(a.b) + "</span>" +
        '<span class="nature' + (a.nature === "凶" ? " is-ji" : "") + '">' + esc(a.nature) + " · " + esc(a.orb) + "°</span>";
      aspects.appendChild(li);
    });

    // 行运
    const transits = $("#transits");
    transits.innerHTML = "";
    (p.astro.aspects || []).forEach((a) => {
      const li = document.createElement("li");
      li.innerHTML = "<span>行运" + esc(a.transit) + " " + esc(a.aspect) + " 本命" + esc(a.natal) + "</span>" +
        '<span class="t-nature' + (a.nature === "凶" ? " is-ji" : "") + '">' + esc(a.nature) + " · " + esc(a.orb) + "°</span>";
      transits.appendChild(li);
    });
    $("#engine-path").textContent = p.engine.path;
  }

  /* ================================================================ 设置 */
  function openSettings() {
    const dlg = $("#settings");
    if (!dlg) return;
    $("#api-base").value = state.api.base || (state.meta && state.meta.defaults.base) || "";
    $("#api-key").value = state.api.key || "";
    $("#api-model").value = state.api.model || (state.meta && state.meta.defaults.model) || "";
    const p = state.profile || {};
    $("#p-date").value = [p.year, pad(p.month), pad(p.day)].join("-");
    $("#p-time").value = pad(p.hour) + ":" + pad(p.minute);
    $("#p-gender").value = p.gender || "男";
    $("#p-name").value = p.name || "命主";
    $("#p-place").value = p.birth_place || "上海";
    $("#p-lon").value = p.longitude != null ? p.longitude : 121.47;
    $("#p-lat").value = p.latitude != null ? p.latitude : 31.23;
    $("#api-status").textContent = "";
    $("#api-status").className = "field-status";
    $("#cast-note").textContent = state.castAt ? "今日已起卦于 " + state.castAt.slice(11, 16) + "。" : "今日尚未起卦。";
    dlg.showModal();
    setTimeout(() => $("#api-base").focus(), 60);
  }

  function closeSettings() {
    const dlg = $("#settings");
    if (dlg && dlg.open) dlg.close();
  }

  function collectApi() {
    return {
      base: $("#api-base").value.trim(),
      key: $("#api-key").value.trim(),
      model: $("#api-model").value.trim(),
    };
  }

  async function testApi() {
    const status = $("#api-status");
    status.className = "field-status";
    status.textContent = "正在连接……";
    try {
      const res = await post("/api/test-api", { api: collectApi() });
      if (res.ok) {
        status.className = "field-status is-ok";
        status.textContent = res.message;
      } else {
        status.className = "field-status is-error";
        status.textContent = (res.error && res.error.message) || "连接失败";
      }
    } catch (err) {
      status.className = "field-status is-error";
      status.textContent = err.message;
    }
  }

  async function saveSettings() {
    const api = collectApi();
    const dateVal = $("#p-date").value;
    const timeVal = $("#p-time").value || "12:00";
    if (!dateVal) { toast("请填写出生日期"); return; }
    const [y, m, d] = dateVal.split("-").map(Number);
    const [hh, mm] = timeVal.split(":").map(Number);
    const profile = {
      name: $("#p-name").value.trim() || "命主",
      gender: $("#p-gender").value,
      year: y, month: m, day: d, hour: hh, minute: mm,
      birth_place: $("#p-place").value.trim() || "未知",
      longitude: Number($("#p-lon").value) || 121.47,
      latitude: Number($("#p-lat").value) || 31.23,
      tz_offset: 8,
    };
    state.api = { base: api.base || (state.meta.defaults.base || ""), key: api.key, model: api.model || (state.meta.defaults.model || "") };
    store.set("yigua.api", state.api);
    try {
      const res = await post("/api/profile", { profile: profile });
      state.profile = res.profile;
      closeSettings();
      toast("已保存。正在按新资料重排……");
      const wasCast = Boolean(state.castAt);
      await loadDay({ reveal: wasCast, scroll: false, skipAi: true });
      if (wasCast) requestNarrative({ typewrite: false, refresh: true });
    } catch (err) {
      toast(err.message || "保存失败");
    }
  }

  async function resetCast() {
    store.del(castKey(state.meta.today));
    state.castAt = null;
    state.date = state.meta.today;
    closeSettings();
    resetDial();
    document.body.classList.remove("has-reading");
    const reading = $("#reading");
    reading.hidden = true;
    reading.classList.remove("is-open");
    await loadDay({});
    toast("已清除今日卦，可以重新起卦。");
  }

  /* ================================================================ 视图 */
  function switchView(view) {
    state.view = view;
    const today = $("#view-today");
    const chart = $("#view-chart");
    if (view === "chart") {
      today.hidden = true;
      chart.hidden = false;
      renderChartPage(state.payload);
      observeReveals(chart);
      window.scrollTo({ top: 0, behavior: REDUCE ? "auto" : "smooth" });
    } else {
      chart.hidden = true;
      today.hidden = false;
      observeReveals(today);
      window.scrollTo({ top: 0, behavior: REDUCE ? "auto" : "smooth" });
    }
    $$(".nav-btn[data-view]").forEach((b) => b.classList.toggle("is-active", b.dataset.view === view));
  }

  function showError(message) {
    const status = $("#hero-status");
    if (status) status.textContent = message;
    toast(message);
  }

  let toastTimer = null;
  function toast(message) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 3000);
  }

  function initStageObservers() {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        entry.target.classList.toggle("is-paused", !entry.isIntersecting);
      });
    }, { rootMargin: "120px" });
    const stage = $("#stage");
    const footer = $(".footer");
    const chart = $(".chart-hero");
    if (stage) io.observe(stage);
    if (footer) io.observe(footer);
    if (chart) io.observe(chart);
  }

  function initParallax() {
    if (REDUCE) return;
    const stage = $("#stage");
    if (!stage) return;
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const y = window.scrollY || 0;
        if (y < window.innerHeight * 1.3) {
          stage.style.setProperty("--parallax", (y * 0.07).toFixed(1) + "px");
        }
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ================================================================ 启动 */
  async function init() {
    bindGlobal();
    let meta;
    try {
      meta = await getState();
    } catch (err) {
      showFatal("本地服务没有响应。请先运行「每日一卦/start.command」，再用它打开的地址访问。");
      return;
    }
    meta.today = todayISO();   // 以浏览者当地日期为准，避免跨时区时“今天”错位
    state.meta = meta;
    if (!meta.engine || !meta.engine.ok) {
      showFatal("运势引擎不可用：" + (meta.engine && meta.engine.error ? meta.engine.error : "未知错误") +
        "。请确认「自动化任务」目录还在，或设置环境变量 FORTUNE_ENGINE_ROOT 指向「自动化任务」目录。");
      return;
    }
    state.profile = meta.profile;
    state.api = Object.assign(
      { base: meta.defaults.base, key: "", model: meta.defaults.model },
      store.get("yigua.api", {})
    );
    state.date = meta.today;
    state.castAt = store.get(castKey(state.date), null);
    const params = new URLSearchParams(window.location.search);
    if (/^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "")) state.date = params.get("date");
    const qcast = params.get("cast");
    if (qcast && /^\d{2}:\d{2}$/.test(qcast)) {
      state.castAt = state.date + "T" + qcast;
      store.set(castKey(state.date), state.castAt);
    }
    const narrow = window.matchMedia("(max-width: 680px)").matches;
    buildStars($("#stars"), narrow ? 48 : 84, 20261023);
    buildStars($("#footer-stars"), narrow ? 34 : 56, 7713);
    buildOrbit();
    buildStars($("#chart-stars"), 54, 9917);
    buildOrbit("#chart-orbit");
    initParallax();
    initStageObservers();
    $("#cast-btn").disabled = true;
    buildDial("");
    await loadDay({ reveal: Boolean(state.castAt), scroll: false });
    $("#cast-btn").disabled = false;
    document.body.classList.add("is-ready");
    observeReveals(document);
    $("#footer-meta").textContent = "本地运行 · 数据不出本机 · 引擎 v" + meta.version + " · 已存断语 " + meta.narratives + " 份";
    if (params.get("view") === "chart") switchView("chart");
    setInterval(() => {
      if (todayISO() !== state.meta.today) window.location.reload();
    }, 60000);
  }

  function showFatal(message) {
    const status = $("#hero-status");
    if (status) status.textContent = message;
    const lede = $("#hero-lede");
    if (lede) lede.textContent = "应用没有连上本地数据。";
    $("#cast-btn").disabled = true;
    document.body.classList.add("is-ready");
    buildDial("");
    toast(message);
  }

  function bindGlobal() {
    $("#cast-btn").addEventListener("click", cast);
    $("#read-link").addEventListener("click", (e) => {
      e.preventDefault();
      $("#reading").scrollIntoView({ behavior: REDUCE ? "auto" : "smooth", block: "start" });
    });
    $$(".nav-btn[data-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view;
        if (view === "settings") { openSettings(); return; }
        if (view === "today" && state.meta && state.date !== state.meta.today) {
          switchView("today");
          goToday();
          return;
        }
        switchView(view);
      });
    });
    $$("[data-view-link]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        if (state.view !== "today") switchView("today");
        if (state.meta && state.date !== state.meta.today) {
          goToday();
        } else {
          window.scrollTo({ top: 0, behavior: REDUCE ? "auto" : "smooth" });
        }
      });
    });

    $("#close-settings").addEventListener("click", closeSettings);
    $("#cancel-settings").addEventListener("click", closeSettings);
    $("#settings-form").addEventListener("submit", (e) => {
      e.preventDefault();
      saveSettings();
    });
    $("#test-api").addEventListener("click", testApi);
    $("#toggle-key").addEventListener("click", () => {
      const input = $("#api-key");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      $("#toggle-key").textContent = show ? "隐藏" : "显示";
      $("#toggle-key").setAttribute("aria-pressed", String(show));
    });
    $("#reset-cast").addEventListener("click", resetCast);
    $("#settings").addEventListener("click", (e) => {
      if (e.target === $("#settings")) closeSettings(); // 点遮罩关闭
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && $("#settings").open) closeSettings();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
