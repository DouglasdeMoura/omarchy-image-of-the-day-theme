"""Theme previews rendered as deterministic desktop mockups.

preview.png mimics the official previews (1800×1012: a top bar over a 2×2
window grid on the wallpaper); preview-unlock.png mocks the lock screen.
Everything is drawn from fixed patterns — no clocks, no randomness — so the
same input always renders the same bytes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .imaging import cover_crop, dim, hex_to_rgb, load_font, load_image, rounded_rect

PREVIEW_SIZE = (1800, 1012)
UNLOCK_PREVIEW_SIZE = (1920, 1080)
MOCK_CLOCK = "09:41"

# Editor mock: rows of syntax-token bars. Each row is a list of
# (palette key, width in "characters") rendered at 8px per char.
_EDITOR_ROWS = [
    [("muted", 3), ("blue", 6), ("foreground", 14), ("yellow", 4)],
    [("blue", 5), ("green", 3), ("foreground", 22), ("red", 2)],
    [("muted", 3), ("foreground", 8), ("cyan", 9), ("yellow", 6)],
    [("foreground", 4), ("green", 7), ("foreground", 18)],
    [("muted", 3), ("red", 3), ("foreground", 26)],
    [("blue", 6), ("foreground", 10), ("cyan", 5), ("yellow", 3)],
    [("muted", 3), ("foreground", 30)],
    [("green", 4), ("foreground", 12), ("magenta", 8)],
]
# Monitor mock: (label width, fill fraction, palette key).
_GAUGES = [(70, 0.22, "green"), (56, 0.48, "green"), (84, 0.71, "yellow"),
           (62, 0.33, "green"), (76, 0.86, "red"), (68, 0.55, "green")]
# Terminal mock rows: list of (palette key, char width) after the prompt.
_TERMINAL_ROWS = [
    [("foreground", 30)],
    [("green", 6), ("yellow", 3), ("foreground", 18)],
    [("foreground", 24), ("red", 6)],
    [("muted", 40)],
]


def _rgb(p: dict[str, str], key: str) -> tuple[int, int, int]:
    return hex_to_rgb(p[key])


def _text(draw: ImageDraw.ImageDraw, xy, text, font, fill):
    draw.text(xy, text, font=font, fill=fill)


def _top_bar(img: Image, p: dict[str, str]) -> None:
    draw = ImageDraw.Draw(img)
    w, h = img.size
    bar = h // 23  # 44px at 1800×1012
    draw.rectangle((0, 0, w, bar), fill=_rgb(p, "background"))

    font = load_font(bar * 16 // 24)
    fg, accent, muted = _rgb(p, "foreground"), _rgb(p, "accent"), _rgb(p, "muted")

    # Left: workspace pills, "1" active.
    x = 24
    pill_w, pill_h = bar - 12, bar - 16
    for i, label in enumerate(("1", "2", "3")):
        y0 = (bar - pill_h) // 2
        if i == 0:
            rounded_rect(draw, (x, y0, x + pill_w, y0 + pill_h), pill_h // 2, fill=accent)
            _text(draw, (x + pill_w // 2 - 6, y0 - 1), label, font, _rgb(p, "background"))
        else:
            _text(draw, (x + pill_w // 2 - 6, y0 - 1), label, font, muted)
        x += pill_w + 12

    # Center: fixed clock.
    clock_w = draw.textlength(MOCK_CLOCK, font=font)
    _text(draw, ((w - clock_w) // 2, (bar - pill_h) // 2 - 1), MOCK_CLOCK, font, fg)

    # Right: tray dots.
    for i in range(5):
        cx = w - 24 - (4 - i) * 22
        cy = bar // 2
        draw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=accent if i == 3 else muted)


def _window(img: Image, box, p: dict[str, str], *, active: bool) -> tuple[int, int, int, int]:
    """Draw a titled window; return the content box inside it."""
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    title_h = 34
    radius = 14
    fill = _rgb(p, "dark_background")
    border = _rgb(p, "accent") if active else _rgb(p, "darker_background")
    rounded_rect(draw, box, radius, fill=fill, outline=border, width=3 if active else 1)

    # Title band: rounded top corners, squared bottom edge.
    band = (x0 + 2, y0 + 2, x1 - 2, y0 + title_h)
    rounded_rect(draw, band, radius - 2, fill=_rgb(p, "lighter_background"))
    draw.rectangle((x0 + 2, y0 + title_h - radius, x1 - 2, y0 + title_h), fill=_rgb(p, "lighter_background"))

    for i, key in enumerate(("red", "yellow", "green")):
        cx = x0 + 22 + i * 20
        cy = y0 + 2 + title_h // 2
        draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=_rgb(p, key))

    inset = 18
    return (x0 + inset, y0 + title_h + inset, x1 - inset, y1 - inset)


def _bar_row(draw, x, y, tokens, p, char_px=8, bar_h=10, gap=6):
    for key, chars in tokens:
        w = chars * char_px
        if key == "none":
            x += w
            continue
        draw.rounded_rectangle((x, y, x + w, y + bar_h), radius=3, fill=_rgb(p, key))
        x += w + gap
    return x


def _mock_editor(img: Image, box, p: dict[str, str]) -> None:
    draw = ImageDraw.Draw(img)
    x0, y0, _, y1 = box
    row_h = 22
    y = y0
    for row in _EDITOR_ROWS:
        if y + row_h > y1:
            break
        draw.rounded_rectangle((x0, y + 2, x0 + 14, y + 12), radius=2, fill=_rgb(p, "darker_background"))
        _bar_row(draw, x0 + 26, y, row, p)
        y += row_h


def _mock_monitor(img: Image, box, p: dict[str, str]) -> None:
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    track_w = x1 - x0 - 90
    row_h = 30
    y = y0 + 6
    for label_w, frac, key in _GAUGES:
        if y + 16 > y1:
            break
        draw.rounded_rectangle((x0, y + 2, x0 + label_w, y + 12), radius=3, fill=_rgb(p, "muted"))
        tx0 = x0 + 90
        draw.rounded_rectangle((tx0, y, x1, y + 16), radius=8, fill=_rgb(p, "darker_background"))
        fill_w = int(track_w * frac)
        draw.rounded_rectangle((tx0, y, tx0 + fill_w, y + 16), radius=8, fill=_rgb(p, key))
        y += row_h


def _mock_terminal(img: Image, box, p: dict[str, str]) -> None:
    draw = ImageDraw.Draw(img)
    x0, y0, _, y1 = box
    font = load_font(18, mono=True)
    row_h = 26
    y = y0 + 4
    for i, row in enumerate(_TERMINAL_ROWS):
        if y + row_h > y1:
            break
        _text(draw, (x0, y), "$", font, _rgb(p, "green"))
        _bar_row(draw, x0 + 22, y + 4, row, p)
        if i == 2:  # a red error line for contrast
            _text(draw, (x0 + 22 + 24 * 8 + 12, y - 2), "err", font, _rgb(p, "red"))
        y += row_h


def _mock_files(img: Image, box, p: dict[str, str]) -> None:
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    cols, rows = 4, 2
    fw, fh = 64, 48
    cell_w = (x1 - x0) / cols
    cell_h = (y1 - y0) / rows
    for r in range(rows):
        for c in range(cols):
            cx = x0 + c * cell_w + (cell_w - fw) / 2
            cy = y0 + r * cell_h + (cell_h - fh - 14) / 2
            color = _rgb(p, "accent" if (r + c) % 2 == 0 else "orange")
            rounded_rect(draw, (cx, cy + 10, cx + fw, cy + 10 + fh - 10), 6, fill=color)
            draw.rounded_rectangle((cx, cy + 4, cx + fw * 0.45, cy + 14), radius=3, fill=color)
            draw.rounded_rectangle((cx + 4, cy + fh + 6, cx + fw - 4, cy + fh + 14), radius=3, fill=_rgb(p, "muted"))


def render_preview(wallpaper: Path, palette: dict[str, str], dest: Path) -> None:
    img = cover_crop(load_image(wallpaper), *PREVIEW_SIZE)
    img = dim(img, hex_to_rgb(palette["background"]), 0.10)

    w, h = PREVIEW_SIZE
    margin, gap = 60, 36
    top = 44 + 36
    grid_w = (w - 2 * margin - gap) // 2
    grid_h = (h - top - 48 - gap) // 2
    cells = [
        (margin, top, margin + grid_w, top + grid_h),
        (margin + grid_w + gap, top, w - margin, top + grid_h),
        (margin, top + grid_h + gap, margin + grid_w, h - 48),
        (margin + grid_w + gap, top + grid_h + gap, w - margin, h - 48),
    ]

    _top_bar(img, palette)
    content = [_mock_editor, _mock_monitor, _mock_terminal, _mock_files]
    for i, (box, mock) in enumerate(zip(cells, content)):
        inner = _window(img, box, palette, active=(i == 0))
        mock(img, inner, palette)

    img.save(dest, "PNG")
    print(f"wrote {dest} ({PREVIEW_SIZE[0]}x{PREVIEW_SIZE[1]})")


def render_preview_unlock(palette: dict[str, str], unlock_png: Path, dest: Path) -> None:
    """Official composition: solid theme background with the logo centered."""
    img = Image.new("RGB", UNLOCK_PREVIEW_SIZE, _rgb(palette, "background"))
    banner = Image.open(unlock_png).convert("RGBA")
    w, h = UNLOCK_PREVIEW_SIZE
    img.paste(banner, ((w - banner.width) // 2, (h - banner.height) // 2), banner)
    img.save(dest, "PNG")
    print(f"wrote {dest} ({UNLOCK_PREVIEW_SIZE[0]}x{UNLOCK_PREVIEW_SIZE[1]})")


SWATCH_SIZE = 48


def render_swatch(color_hex: str, dest: Path) -> None:
    """A solid dot on transparency: the color preview in the release notes'
    palette table. GitHub strips CSS from release pages, so the dot has to be
    a real image shipped alongside the wallpaper as a release asset."""
    img = Image.new("RGBA", (SWATCH_SIZE, SWATCH_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((2, 2, SWATCH_SIZE - 2, SWATCH_SIZE - 2), fill=(*hex_to_rgb(color_hex), 255))
    img.save(dest, "PNG")
