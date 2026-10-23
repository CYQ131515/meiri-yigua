#!/usr/bin/env python3
"""生成桌面版 AppIcon.icns：宣纸底、朱砂卦印、金环。"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 2048
PAPER = "#e8e1d2"
PAPER_LIGHT = "#efe6d5"
CINNABAR = "#9c352a"
INK = "#1b1915"
GOLD = "#a8853f"

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Supplemental/Kaiti.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def build_master() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin, radius = 88, 430

    # 宣纸底
    draw.rounded_rectangle([margin, margin, S - margin, S - margin],
                           radius=radius, fill=PAPER)
    # 很淡的纸纹
    noise = Image.effect_noise((S, S), 14).convert("L").filter(ImageFilter.GaussianBlur(1))
    paper = Image.new("RGBA", (S, S), PAPER)
    dust = Image.new("RGBA", (S, S), (27, 25, 21, 0))
    dust.putalpha(noise.point(lambda v: int(v * 0.055)))
    paper.alpha_composite(dust)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([margin, margin, S - margin, S - margin],
                                          radius=radius, fill=255)
    img.alpha_composite(Image.composite(paper, Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask))

    # 内框与金环
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([margin + 18, margin + 18, S - margin - 18, S - margin - 18],
                           radius=radius - 18, outline=INK, width=5)
    cx = cy = S // 2
    ring = 760
    draw.ellipse([cx - ring, cy - ring, cx + ring, cy + ring], outline=GOLD, width=7)

    # 朱砂卦印
    seal_size = 1240
    pad = 90
    seal = Image.new("RGBA", (seal_size + pad * 2, seal_size + pad * 2), (0, 0, 0, 0))
    sd = ImageDraw.Draw(seal)
    x0, y0, x1, y1 = pad, pad, pad + seal_size, pad + seal_size
    sd.rounded_rectangle([x0, y0, x1, y1], radius=116, fill=CINNABAR)
    sd.rounded_rectangle([x0 + 48, y0 + 48, x1 - 48, y1 - 48],
                         radius=82, outline=PAPER_LIGHT, width=6)
    glyph = "卦"
    face = font(790)
    bbox = sd.textbbox((0, 0), glyph, font=face)
    gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    sd.text(((seal.width - gw) / 2 - bbox[0], (seal.height - gh) / 2 - bbox[1]),
            glyph, font=face, fill=PAPER_LIGHT)
    seal = seal.rotate(-2.4, resample=Image.BICUBIC, expand=False)
    img.alpha_composite(seal, (cx - seal.width // 2, cy - seal.height // 2))

    # 金环上的四点，压住印角之后仍能看到
    draw = ImageDraw.Draw(img)
    for angle in (0, 90, 180, 270):
        rad = math.radians(angle)
        x = cx + ring * math.sin(rad)
        y = cy - ring * math.cos(rad)
        draw.ellipse([x - 11, y - 11, x + 11, y + 11], fill=GOLD)

    return img.resize((1024, 1024), Image.LANCZOS)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("AppIcon.icns")
    master = build_master()
    iconset = out.parent / "AppIcon.iconset"
    if iconset.exists():
        for p in iconset.iterdir():
            p.unlink()
    iconset.mkdir(parents=True, exist_ok=True)
    specs = [
        ("16x16", 16), ("16x16@2x", 32),
        ("32x32", 32), ("32x32@2x", 64),
        ("128x128", 128), ("128x128@2x", 256),
        ("256x256", 256), ("256x256@2x", 512),
        ("512x512", 512), ("512x512@2x", 1024),
    ]
    for name, size in specs:
        master.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{name}.png")
    master.save(out.with_suffix(".png"))
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
    print(out, out.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
