"""Pillow primitives shared by the preview/unlock renderers and palette code.

No theme logic lives here — just image operations and color math. (The
desktop preview needs no system fonts: preview_html.py embeds its own.)
"""

from __future__ import annotations

import colorsys
from pathlib import Path

from PIL import Image, ImageDraw


def load_image(path: Path) -> Image.Image:
    """Open an image as upright RGB (EXIF-rotated), verifying it decodes."""
    with Image.open(path) as im:
        img = im.convert("RGB")
    return img


def cover_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    """Aspect-fill center crop to exactly w×h (LANCZOS downscale)."""
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:  # source too wide -> crop sides
        new_w = round(img.height * dst_ratio)
        x0 = (img.width - new_w) // 2
        box = (x0, 0, x0 + new_w, img.height)
    else:  # too tall -> crop top/bottom
        new_h = round(img.width / dst_ratio)
        y0 = (img.height - new_h) // 2
        box = (0, y0, img.width, y0 + new_h)
    return img.crop(box).resize((w, h), Image.LANCZOS)


def center_strip(img: Image.Image, w: int, h: int) -> Image.Image:
    """Full-width horizontal band of height h from the vertical center."""
    h = min(h, img.height)
    y0 = (img.height - h) // 2
    return img.crop((0, y0, img.width, y0 + h)).resize((w, h), Image.LANCZOS)


def dim(img: Image.Image, toward: tuple[int, int, int], alpha: float) -> Image.Image:
    """Blend the image toward a solid color (alpha 0 = untouched, 1 = solid)."""
    return Image.blend(img, Image.new("RGB", img.size, toward), alpha)


def rec709_luma(img: Image.Image) -> float:
    """Mean perceptual luma (Rec.709) of the image, 0..1."""
    small = img.resize((256, 144), Image.BILINEAR)
    means = small.resize((1, 1), Image.BOX).getpixel((0, 0))
    r, g, b = means
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def rounded_rect(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int] | None = None,
    outline: tuple[int, int, int] | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def hex_to_rgb(s: str) -> tuple[int, int, int]:
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def rgb_to_hex(c: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*c)


def rgb_to_hsl(c: tuple[int, int, int]) -> tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(c[0] / 255, c[1] / 255, c[2] / 255)
    return (h * 360, s, l)


def hsl_to_rgb(hsl: tuple[float, float, float]) -> tuple[int, int, int]:
    h, s, l = hsl
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l, s)
    return (round(r * 255), round(g * 255), round(b * 255))


def blend(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Linear RGB blend: t=0 -> c1, t=1 -> c2."""
    return tuple(round(a + (b - a) * t) for a, b in zip(c1, c2))
