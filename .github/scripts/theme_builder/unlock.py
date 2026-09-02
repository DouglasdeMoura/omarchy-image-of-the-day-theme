"""Lock-screen banner (unlock.png): a dimmed strip of the wallpaper with
palette dots and an accent border."""

from __future__ import annotations

from pathlib import Path

from PIL import ImageDraw, ImageFilter

from .imaging import center_strip, dim, hex_to_rgb, load_image

SIZE = (800, 188)


def render_unlock(wallpaper: Path, palette: dict[str, str], dest: Path) -> None:
    img = center_strip(load_image(wallpaper), *SIZE)
    img = dim(img.filter(ImageFilter.GaussianBlur(2)), hex_to_rgb(palette["background"]), 0.35)

    draw = ImageDraw.Draw(img)
    accent = hex_to_rgb(palette["accent"])
    draw.rectangle((6, 6, SIZE[0] - 7, SIZE[1] - 7), outline=accent, width=2)

    # Palette dots down the right edge: accent plus five hues.
    dots = ["accent", "red", "yellow", "green", "cyan", "magenta"]
    x = SIZE[0] - 24 - (len(dots) - 1) * 28
    y = SIZE[1] // 2
    for i, key in enumerate(dots):
        cx = x + i * 28
        draw.ellipse((cx - 8, y - 8, cx + 8, y + 8), fill=hex_to_rgb(palette[key]))

    img.save(dest, "PNG")
    print(f"wrote {dest} ({SIZE[0]}x{SIZE[1]})")
