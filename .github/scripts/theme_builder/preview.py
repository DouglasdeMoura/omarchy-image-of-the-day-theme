"""Theme previews, rendered deterministically.

preview.png is the HTML reproduction of an Omarchy desktop (see
preview_html.py): wallpaper of the day, bar, foot window and fastfetch
output, all colored by the day's palette. preview-unlock.png is the
official lock-screen composition — solid theme background with the unlock
banner centered. Everything is drawn from fixed fixtures — no clocks, no
randomness — so the same input always renders the same bytes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from .imaging import hex_to_rgb
from .preview_html import SIZE as PREVIEW_SIZE, render_preview  # noqa: F401 — re-exported

UNLOCK_PREVIEW_SIZE = (1920, 1080)


def render_preview_unlock(palette: dict[str, str], unlock_png: Path, dest: Path) -> None:
    """Official composition: solid theme background with the logo centered."""
    img = Image.new("RGB", UNLOCK_PREVIEW_SIZE, hex_to_rgb(palette["background"]))
    banner = Image.open(unlock_png).convert("RGBA")
    w, h = UNLOCK_PREVIEW_SIZE
    img.paste(banner, ((w - banner.width) // 2, (h - banner.height) // 2), banner)
    img.save(dest, "PNG")
    print(f"wrote {dest} ({UNLOCK_PREVIEW_SIZE[0]}x{UNLOCK_PREVIEW_SIZE[1]})")
