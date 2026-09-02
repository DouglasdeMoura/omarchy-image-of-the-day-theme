"""Shade-ramp derivation, colors.toml emission and the Yaru icon choice.

Aether/Pillow-fallback supply background, foreground, accent, selection,
muted and the hue colors. The background/foreground ramps are derived here
so they always follow Omarchy's conventions (calibrated against the official
gruvbox and catppuccin-latte themes), regardless of what the extractor did.
"""

from __future__ import annotations

from pathlib import Path

from .imaging import blend, hex_to_rgb, rgb_to_hex, rgb_to_hsl

# The complete official key set, in emission order (matches gruvbox exactly).
KEY_ORDER = [
    "mode",
    "accent",
    "selection",
    "muted",
    "background",
    "dark_background",
    "darker_background",
    "lighter_background",
    "foreground",
    "dark_foreground",
    "light_foreground",
    "bright_foreground",
    "red",
    "yellow",
    "orange",
    "green",
    "cyan",
    "blue",
    "magenta",
    "brown",
    "bright_red",
    "bright_yellow",
    "bright_green",
    "bright_cyan",
    "bright_blue",
    "bright_magenta",
]

_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)

# Yaru icon variants that ship with Omarchy, mapped from the accent's hue.
# Bands are (low, high, variant) degrees, low exclusive. Low saturation falls
# back to the default variant.
YARU_VARIANTS = {
    "Yaru",
    "Yaru-blue",
    "Yaru-magenta",
    "Yaru-olive",
    "Yaru-prussiangreen",
    "Yaru-purple",
    "Yaru-red",
    "Yaru-sage",
    "Yaru-wartybrown",
    "Yaru-yellow",
}
_YARU_BANDS = [
    (345, 360, "Yaru-red"),
    (0, 15, "Yaru-red"),
    (15, 45, "Yaru-wartybrown"),
    (45, 95, "Yaru-olive"),
    (95, 150, "Yaru-prussiangreen"),
    (150, 200, "Yaru-sage"),
    (200, 255, "Yaru-blue"),
    (255, 290, "Yaru-purple"),
    (290, 345, "Yaru-magenta"),
]


def derive_ramps(palette: dict[str, str]) -> None:
    """Fill in the background/foreground shade keys, in place.

    Dark mode goes darker for sunken surfaces and slightly lighter for
    elevated ones; light mode darkens for both (lighter_background included —
    official light themes darken it too, the names are dark-mode-perspective).
    """
    mode = palette["mode"]
    bg = hex_to_rgb(palette["background"])
    fg = hex_to_rgb(palette["foreground"])

    if mode == "dark":
        palette["dark_background"] = rgb_to_hex(blend(bg, _BLACK, 0.25))
        palette["darker_background"] = rgb_to_hex(blend(bg, _BLACK, 0.45))
        palette["lighter_background"] = rgb_to_hex(blend(bg, _WHITE, 0.10))
        palette["light_foreground"] = rgb_to_hex(blend(fg, bg, 0.15))
    else:
        palette["dark_background"] = rgb_to_hex(blend(bg, _BLACK, 0.05))
        palette["darker_background"] = rgb_to_hex(blend(bg, _BLACK, 0.18))
        palette["lighter_background"] = rgb_to_hex(blend(bg, _BLACK, 0.08))
        palette["light_foreground"] = rgb_to_hex(blend(fg, bg, 0.10))
    palette["dark_foreground"] = rgb_to_hex(blend(fg, bg, 0.50))


def emit_colors_toml(palette: dict[str, str], header: str, credit: str | None = None) -> str:
    """Render colors.toml in the exact official layout."""
    p = palette
    lines = [
        f"# image-of-the-day — {header}",
        "# Generated daily by GitHub Actions from Bing's image of the day. Do not edit.",
    ]
    if credit:
        lines.append(f"# Image: {credit}")
    lines += [
        "",
        f'mode = "{p["mode"]}"',
        "",
        f'accent = "{p["accent"]}"',
        f'selection = "{p["selection"]}"',
        f'muted = "{p["muted"]}"',
        "",
        "# Backgrounds",
        f'background = "{p["background"]}"',
        f'dark_background = "{p["dark_background"]}"',
        f'darker_background = "{p["darker_background"]}"',
        f'lighter_background = "{p["lighter_background"]}"',
        "",
        "# Foregrounds",
        f'foreground = "{p["foreground"]}"',
        f'dark_foreground = "{p["dark_foreground"]}"',
        f'light_foreground = "{p["light_foreground"]}"',
        f'bright_foreground = "{p["bright_foreground"]}"',
        "",
        "# Normal colors",
        f'red = "{p["red"]}"',
        f'yellow = "{p["yellow"]}"',
        f'orange = "{p["orange"]}"',
        f'green = "{p["green"]}"',
        f'cyan = "{p["cyan"]}"',
        f'blue = "{p["blue"]}"',
        f'magenta = "{p["magenta"]}"',
        f'brown = "{p["brown"]}"',
        "",
        "# Bright colors",
        f'bright_red = "{p["bright_red"]}"',
        f'bright_yellow = "{p["bright_yellow"]}"',
        f'bright_green = "{p["bright_green"]}"',
        f'bright_cyan = "{p["bright_cyan"]}"',
        f'bright_blue = "{p["bright_blue"]}"',
        f'bright_magenta = "{p["bright_magenta"]}"',
        "",
    ]
    return "\n".join(lines)


def icons_for_accent(accent_hex: str) -> str:
    """Pick the Yaru variant whose hue family matches the accent."""
    h, s, _ = rgb_to_hsl(hex_to_rgb(accent_hex))
    if s < 0.15:
        return "Yaru"
    for lo, hi, variant in _YARU_BANDS:
        if lo <= h <= hi:
            return variant
    return "Yaru"


def write_colors_toml(root: Path, palette: dict[str, str], header: str, credit: str | None = None) -> None:
    (root / "colors.toml").write_text(emit_colors_toml(palette, header, credit), encoding="utf-8")


def write_icons_theme(root: Path, accent_hex: str) -> str:
    variant = icons_for_accent(accent_hex)
    (root / "icons.theme").write_text(variant + "\n", encoding="utf-8")
    return variant


def write_chromium_theme(root: Path, background_hex: str) -> None:
    """chromium.theme: the background as 'R,G,B'. omarchy-theme-set-browser
    converts it to hex and applies it as the Chromium/Chrome/Edge/Brave
    frame color, so the browser matches the theme's dominant surface."""
    r, g, b = hex_to_rgb(background_hex)
    (root / "chromium.theme").write_text(f"{r},{g},{b}\n", encoding="utf-8")
