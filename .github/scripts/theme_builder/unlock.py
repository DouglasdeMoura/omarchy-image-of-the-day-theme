"""Lock-screen banner (unlock.png): Omarchy's logo tinted with the accent.

The logo is the shared alpha mask every official theme ships (extracted from
gruvbox's unlock.png); official themes render it as one flat palette color —
the accent. Same recipe here, so the banner is indistinguishable in shape
from an official theme's.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from .imaging import hex_to_rgb

SIZE = (800, 188)
_LOGO_MASK = Path(__file__).parent / "assets" / "unlock-mask.png"


def render_unlock(palette: dict[str, str], dest: Path) -> None:
    mask = Image.open(_LOGO_MASK).convert("L")
    if mask.size != SIZE:
        mask = mask.resize(SIZE)
    r, g, b = hex_to_rgb(palette["accent"])
    img = Image.merge("RGBA", (
        Image.new("L", SIZE, r),
        Image.new("L", SIZE, g),
        Image.new("L", SIZE, b),
        mask,
    ))
    img.save(dest, "PNG")
    print(f"wrote {dest} ({SIZE[0]}x{SIZE[1]})")
