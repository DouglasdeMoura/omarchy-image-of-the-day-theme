"""preview.png — a pixel-faithful 1920x1080 Omarchy desktop, rendered in HTML.

The composition is a reproduction of a real Omarchy desktop screenshot
(assets/reference-preview.png), measured to the pixel:

  - bar: 26px tall, solid background, items at measured ink-x positions
  - window: (1054,512) 859x559, 2px border, square corners, no shadow
  - terminal: foot's grid — origin (1070,528), cell 7x17px, 29 lines

Theme-dependent pieces are driven by the day's palette: the wallpaper, the
bar/window surfaces, the SGR colors of the fastfetch output, the window
border (blue hue) and the notification badge (accent). Everything else —
fonts, glyphs, layout, terminal content — is a fixed fixture so the same
palette always renders the same bytes.

The page is self-contained (fonts and wallpaper embedded as data URIs) and
screenshotted with headless Chromium/Chrome.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .imaging import cover_crop, load_image

SIZE = (1920, 1080)
ASSETS = Path(__file__).parent / "assets"
FONT_FILES = {
    "JB": ASSETS / "fonts" / "JetBrainsMonoNerdFont-Regular.ttf",
    "OM": ASSETS / "fonts" / "omarchy.ttf",
}
N_TERM_LINES = 29
LOGO_LINES = 26   # omarchy-logo.txt rows, terminal lines 2..27
INFO_LINES = 27   # fastfetch-template.txt rows, terminal lines 2..28

# SGR code -> palette key, as foot sees the theme (color8=muted, color1-6
# are the hues in colors.toml order: red yellow green cyan blue magenta).
SGR_TO_KEY = {"31": "red", "32": "green", "33": "yellow", "34": "blue",
              "35": "magenta", "36": "cyan", "90": "muted"}

# Box-drawing glyphs and █ are drawn as CSS, not font glyphs: the browser
# rasterizes the font's strokes 2px thick where foot renders 1px. Measured
# from the reference: cell is 7x17; horizontal strokes sit on cell row 8;
# verticals at cell x+3; mid-rails (│ ├) run rows 0..19 (3px into the next
# cell so consecutive lines connect); corner verticals stop at their arm.
GLYPH = {
    "─": "hz", "│": "v", "┌": "tl", "┐": "tr", "└": "bl", "┘": "br",
    "├": "lm", "█": "fb",
}

# Bar glyphs verified against the reference by rendering candidates in
# Chromium and pixel-matching (shell sources identified most; pixels settled
# the rest). Items are (glyph, x, size, top, family).
MENU = "\ue900"             # omarchy logo, from the custom omarchy.ttf
FOCUSED = "\U000f14fb"      # Workspaces.qml focused workspace glyph
TRAY = "\uf053"             # Tray.qml chevron
AGENTS = "\U000f16a3"       # agents Panel.qml
BT = "\U000f00b1"           # bluetooth Panel.qml (connected)
NET = "\U000f0928"          # wifi-strength-4 (network Model.js)
AUD = "\uf028"              # volume (pixel match, not the Panel hero glyph)
MON = "\U000f037a"          # monitor (pixel match)
PWR = "\U000f0085"          # battery charging full (power Model.js)
NOTIF = "\U000f009a"        # notification-center Panel.qml bell
SYSUPD = "\U000f0902"       # SystemUpdate status ring (pixel match)
BAR_LEFT = [(MENU, 16, 12, 7, "OM"), (FOCUSED, 41, 12, 7, "JB"),
            ("2", 62, 12, 7, "JB"), ("3", 83, 12, 7, "JB"),
            ("4", 104, 12, 7, "JB"), ("5", 125, 12, 7, "JB"),
            ("6", 146, 12, 7, "JB"), ("8", 167, 12, 7, "JB"),
            ("9", 188, 12, 7, "JB")]
BAR_RIGHT = [(TRAY, 1706, 13, 6, "JB"), (AGENTS, 1731, 13, 6, "JB"),
             (BT, 1759, 13, 6, "JB"), (NET, 1785, 13, 6, "JB"),
             (AUD, 1811, 13, 6, "JB"), (MON, 1839, 13, 6, "JB"),
             (PWR, 1866, 13, 6, "JB"), (NOTIF, 1894, 13, 6, "JB")]
CLOCK = "Wednesday 18:57"   # fixed fixture — never datetime.now()

BROWSER_CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium",
                      "chromium-browser")


def _browser_works(path: str) -> bool:
    """A --version probe: Ubuntu's snap-stub chromium accepts the exec but
    hangs on any real run, so verify the binary answers before using it."""
    try:
        proc = subprocess.run([path, "--version"], capture_output=True, timeout=15, text=True)
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _gly(t: str) -> str:
    """One terminal cell per character (foot's fixed grid)."""
    out = []
    for c in t:
        if c in GLYPH:
            out.append(f'<span class="gb {GLYPH[c]}"></span>')
        else:
            out.append(f'<span class="gc">{_esc(c)}</span>')
    return "".join(out)


def _spans(line: str, fg: str, colors: dict[str, str]) -> str:
    """ANSI line -> HTML spans, mapping SGR colors onto the day's palette."""
    out, color, buf = [], fg, ""
    for tok in re.split(r"(\x1b\[[0-9;]*m)", line):
        m = re.fullmatch(r"\x1b\[([0-9;]*)m", tok)
        if m:
            if buf:
                out.append((buf, color))
                buf = ""
            codes = (m.group(1) or "0").split(";")
            if codes in (["0"], [""]):
                color = fg
            elif len(codes) == 1 and codes[0] in colors:
                color = colors[codes[0]]
            # SGR "38" alone is invalid; foot leaves the color untouched
        else:
            buf += tok
    if buf:
        out.append((buf, color))
    return "".join(f'<span style="color:{c}">{_gly(t)}</span>' for t, c in out)


def _term_html(pal: dict[str, str]) -> list[str]:
    logo = ASSETS.joinpath("omarchy-logo.txt").read_text(encoding="utf-8").splitlines()
    assert len(logo) == LOGO_LINES, f"omarchy-logo.txt: {len(logo)} lines"

    sgr = {code: pal[key] for code, key in SGR_TO_KEY.items()}
    info = ASSETS.joinpath("fastfetch-template.txt").read_text(encoding="utf-8").splitlines()
    assert len(info) == INFO_LINES, f"fastfetch-template.txt: {len(info)} lines"

    html = []
    for n in range(N_TERM_LINES):
        row = logo[n - 2] if 2 <= n <= 27 else None
        seg = [f'<span style="color:{pal["green"]}">{_gly("  " + row)}</span>'] if row else []
        if 0 <= n - 2 < len(info) and info[n - 2]:
            # logo prefix occupies cols 0-55; info column starts at col 62
            seg.append(" " * (6 if row else 62) + _spans(info[n - 2], pal["foreground"], sgr))
        html.append("".join(seg))
    return html


def _bar_span(item, fg: str) -> str:
    glyph, x, size, top, fam = item
    style = (f"position:absolute;left:{x}px;top:{top}px;font-size:{size}px;"
             f"line-height:1;color:{fg};font-family:'{fam}'")
    return f'<span style="{style}">{_esc(glyph)}</span>'


def _bar_row(items, fg: str) -> str:
    return chr(10).join(_bar_span(i, fg) for i in items)


def _badge(x: int, y: int, d: int, color: str) -> str:
    """Solid dot badge (notification-center unread marker: Color.accent)."""
    return (f'<span style="position:absolute;left:{x}px;top:{y}px;width:{d}px;'
            f'height:{d}px;border-radius:50%;background:{color}"></span>')


def build_page(wallpaper_png: Path, pal: dict[str, str]) -> str:
    fg, bg = pal["foreground"], pal["background"]
    fonts = "\n".join(
        f'@font-face {{ font-family: "{fam}"; src: url("{_data_uri(path, "font/ttf")}") format("truetype"); }}'
        for fam, path in FONT_FILES.items()
    )
    term = _term_html(pal)
    page = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Omarchy theme preview</title>
<style>
{fonts}
* {{ margin: 0; padding: 0; }}
html, body {{ width: {SIZE[0]}px; height: {SIZE[1]}px; overflow: hidden; background: {bg}; }}
#wall {{ position: absolute; left: 0; top: 0; width: {SIZE[0]}px; height: {SIZE[1]}px; }}
#bar {{ position: absolute; left: 0; top: 0; width: {SIZE[0]}px; height: 26px;
        background: {bg}; font-family: "JB"; }}
#win {{ position: absolute; left: 1054px; top: 512px; width: 859px; height: 559px;
        border: 2px solid {pal["blue"]}; box-sizing: border-box; background: {bg}; }}
#term {{ position: absolute; left: 14px; top: 15px; font-family: "JB";
         font-size: 11.687px; line-height: 17px; white-space: pre; color: {fg};
         font-kerning: none; font-variant-ligatures: none; }}
#term div {{ height: 17px; line-height: 0; }}
.gc {{ display: inline-block; width: 7px; height: 17px; vertical-align: top;
       line-height: 17px; }}
.gb {{ display: inline-block; position: relative; top: -1px; width: 7px; height: 17px;
       vertical-align: top; }}
.fb {{ background: currentColor; }}
.gb::before, .gb::after {{ content: ""; position: absolute; background: currentColor; }}
.v::before  {{ left: 3px; top: 0; width: 1px; height: 20px; }}
.hz::before {{ left: 0; top: 8px; width: 7px; height: 1px; }}
.tl::before {{ left: 3px; top: 8px; width: 1px; height: 9px; }}
.tl::after  {{ left: 3px; top: 8px; width: 4px; height: 1px; }}
.tr::before {{ left: 3px; top: 8px; width: 1px; height: 9px; }}
.tr::after  {{ left: 0; top: 8px; width: 4px; height: 1px; }}
.bl::before {{ left: 3px; top: 0; width: 1px; height: 9px; }}
.bl::after  {{ left: 3px; top: 8px; width: 4px; height: 1px; }}
.br::before {{ left: 3px; top: 0; width: 1px; height: 9px; }}
.br::after  {{ left: 0; top: 8px; width: 4px; height: 1px; }}
.lm::before {{ left: 3px; top: 0; width: 1px; height: 20px; }}
.lm::after  {{ left: 3px; top: 8px; width: 4px; height: 1px; }}
</style></head>
<body>
<img id="wall" src="{_data_uri(wallpaper_png, "image/png")}">
<div id="bar">
{_bar_row(BAR_LEFT, pal['foreground'])}
<span style="position:absolute;left:906px;top:7px;font-size:12px;line-height:1;color:{pal["foreground"]}">{CLOCK}</span>
{_bar_span((SYSUPD, 1029, 10, 8, "JB"), pal['foreground'])}
{_bar_row(BAR_RIGHT, pal['foreground'])}
{_badge(1903, 5, 6, pal["accent"])}
</div>
<div id="win"><div id="term">{''.join("<div>" + l + "</div>" for l in term)}</div>
</body></html>
"""
    return page


def _find_browser() -> str:
    override = os.environ.get("CHROME_PATH")
    if override:
        return override  # explicit choice: no probing
    for name in BROWSER_CANDIDATES:
        path = shutil.which(name)
        if path and _browser_works(path):
            return path
    raise RuntimeError(
        "preview renderer needs headless Chromium/Chrome; tried "
        f"{', '.join(BROWSER_CANDIDATES)} (set CHROME_PATH to override)"
    )


def _screenshot(html_path: Path, dest: Path, profile_dir: Path) -> None:
    # Flags tuned against the reference render: device scale 1, no scrollbar,
    # and virtual-time-budget so embedded fonts/wallpaper are fully decoded
    # before the compositor draws.
    cmd = [
        _find_browser(),
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        f"--screenshot={dest}",
        f"--window-size={SIZE[0]},{SIZE[1]}",
        "--hide-scrollbars",
        "--force-device-scale-factor=1",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=10000",
        f"--user-data-dir={profile_dir}",
        f"file://{html_path}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180, text=True)
    except subprocess.TimeoutExpired as err:
        raise RuntimeError(f"browser timed out rendering the preview: {err}") from err
    if proc.returncode != 0 or not dest.is_file():
        raise RuntimeError(f"browser failed ({proc.returncode}): {proc.stderr.strip()[:500]}")


def render_preview(wallpaper: Path, palette: dict[str, str], dest: Path, work: Path) -> Path:
    """Build the self-contained page and screenshot it to dest (1920x1080)."""
    work.mkdir(parents=True, exist_ok=True)

    # The wallpaper region must be lossless from here on: a JPEG data URI
    # would show compression artifacts against the reference composition.
    wall_png = work / "preview-wallpaper.png"
    cover_crop(load_image(wallpaper), *SIZE).save(wall_png, "PNG")

    html_path = work / "preview.html"
    html_path.write_text(build_page(wall_png, palette), encoding="utf-8")

    shot = work / "preview-shot.png"
    _screenshot(html_path, shot, work / "browser-profile")
    with Image.open(shot) as im:
        if im.size != SIZE:
            raise RuntimeError(f"preview screenshot is {im.size}, expected {SIZE}")
    shutil.move(shot, dest)
    print(f"wrote {dest} ({SIZE[0]}x{SIZE[1]}, browser render)")
    return dest
