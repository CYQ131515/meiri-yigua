# -*- coding: utf-8 -*-
"""生成宣纸纹理，并把馆藏图片压成网页用尺寸。

用法： python3 tools/make_assets.py
产物： app/static/assets/paper.webp、paper-dark.webp、*.webp
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "app" / "static" / "assets"
SIZE = 1280


def seamless_waves(size: int, rng) -> np.ndarray:
    """低频斑驳：用整数频率正弦叠加，天然四方连续。"""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    out = np.zeros((size, size), dtype=np.float32)
    for _ in range(14):
        fx = rng.integers(1, 5)
        fy = rng.integers(1, 5)
        phase = rng.uniform(0, math.tau)
        amp = rng.uniform(0.25, 1.0)
        out += amp * np.sin(math.tau * (fx * xx + fy * yy) / size + phase)
    out -= out.min()
    out /= max(out.max(), 1e-6)
    return out


def make_paper() -> Image.Image:
    rng = np.random.default_rng(20261023)
    base = np.array([216, 208, 190], dtype=np.float32)   # 生宣
    mottle = seamless_waves(SIZE, rng) - 0.5
    img = base[None, None, :] + mottle[..., None] * 3.0

    # 细颗粒
    grain = rng.normal(0, 1.0, (SIZE, SIZE, 1))
    img = img + grain * 1.4

    canvas = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(canvas, "RGBA")

    # 纸纤维：短而淡的横纹，跨边界重复绘制。
    for _ in range(2600):
        x, y = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        length = rng.uniform(6, 34)
        alpha = int(rng.uniform(3, 8))
        tone = tuple(int(c) for c in (rng.uniform(150, 200),) * 3)
        for dx in (-SIZE, 0, SIZE):
            for dy in (-SIZE, 0, SIZE):
                draw.line([(x + dx, y + dy), (x + dx + length, y + dy + rng.uniform(-0.6, 0.6))],
                          fill=tone + (alpha,), width=1)
    # 极淡的水渍
    stains = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stains)
    for _ in range(3):
        cx, cy = rng.uniform(0, SIZE), rng.uniform(0, SIZE)
        r = rng.uniform(60, 200)
        sd.ellipse([cx - r, cy - r * 0.7, cx + r, cy + r * 0.7],
                   fill=(146, 132, 108, int(rng.uniform(3, 6))))
    stains = stains.filter(ImageFilter.GaussianBlur(26))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), stains).convert("RGB")
    return canvas


def make_dark(size: int = 1024) -> Image.Image:
    """墨底：几乎纯黑，只留一点纸的杂色，避免死黑。"""
    rng = np.random.default_rng(7)
    base = np.array([27, 24, 20], dtype=np.float32)
    noise = rng.normal(0, 1.0, (size, size, 1))
    mottle = seamless_waves(size, rng) - 0.5
    img = base[None, None, :] + noise * 1.6 + mottle[..., None] * 5.0
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def optimize(src: Path, dst: Path, width: int, quality: int = 82):
    im = Image.open(src).convert("RGB")
    ratio = width / im.width
    im = im.resize((width, int(im.height * ratio)), Image.LANCZOS)
    im.save(dst, "WEBP", quality=quality, method=6)
    print("  %s -> %s (%d KB, %dx%d)" % (src.name, dst.name, dst.stat().st_size // 1024, im.width, im.height))


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    paper = make_paper()
    paper.save(ASSETS / "paper.webp", "WEBP", quality=88, method=6)
    print("paper.webp %d KB" % ((ASSETS / "paper.webp").stat().st_size // 1024))

    dark = make_dark()
    dark.save(ASSETS / "ink.webp", "WEBP", quality=82, method=6)
    print("ink.webp %d KB" % ((ASSETS / "ink.webp").stat().st_size // 1024))

    if (ASSETS / "feng-shui-geometric-compass.jpg").exists():
        optimize(ASSETS / "feng-shui-geometric-compass.jpg", ASSETS / "luopan.webp", 900, 80)
    song = Path("/tmp/yigua-assets/i-ching-song-dynasty-print.jpg")
    if song.exists():
        optimize(song, ASSETS / "zhouyi-song.webp", 760, 78)


if __name__ == "__main__":
    main()
