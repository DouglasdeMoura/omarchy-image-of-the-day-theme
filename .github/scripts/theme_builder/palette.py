"""Palette extraction: dark/light decision, aether invocation, Pillow fallback.

The extractor only supplies the "identity" colors (background, foreground,
accent, selection, muted, the hues and brights). Shade ramps are always
re-derived by colors.derive_ramps, and contrast is always enforced by
contrast.enforce_core — both extractors flow through the same pipeline.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

from PIL import Image

from .imaging import blend, hex_to_rgb, hsl_to_rgb, load_image, rec709_luma, rgb_to_hex, rgb_to_hsl

# Mean-luma thresholds for the dark/light decision. The middle band defaults
# to dark: Omarchy skews dark and dark UI reads well over most wallpapers.
LIGHT_THRESHOLD = 0.60
DARK_THRESHOLD = 0.45

# aether colors.toml key -> omarchy colors.toml key. Keys not listed here are
# dropped (cursor, selection_*, fg, bg, color0-15 and aether's own shade
# ramps, which we re-derive).
_AETHER_RENAMES = {
    "lighter_bg": "lighter_background",
    "dark_bg": "dark_background",
    "darker_bg": "darker_background",
    "light_fg": "light_foreground",
    "bright_fg": "bright_foreground",
    "dark_fg": "dark_foreground",
}
_KEEP = {
    "mode", "accent", "selection", "muted", "background", "foreground",
    "red", "yellow", "orange", "green", "cyan", "blue", "magenta", "brown",
    "bright_red", "bright_yellow", "bright_green", "bright_cyan",
    "bright_blue", "bright_magenta",
}

# Canonical hue angles for the eight named colors, used by the fallback.
_CANONICAL_HUES = [
    ("red", 0), ("orange", 30), ("yellow", 55), ("green", 120),
    ("cyan", 180), ("blue", 225), ("magenta", 300), ("brown", 25),
]


class AetherError(RuntimeError):
    pass


def decide_mode(img_path: Path) -> str:
    luma = rec709_luma(load_image(img_path))
    mode = "light" if luma >= LIGHT_THRESHOLD else "dark"
    print(f"mode: {mode} (mean luma {luma:.3f})")
    return mode


def run_aether(aether_path: str, img: Path, mode: str, out_dir: Path) -> dict[str, str]:
    """Run aether headless and return its mapped palette (or raise AetherError)."""
    cmd = [aether_path, "--generate", str(img)]
    if mode == "light":
        cmd.append("--light-mode")
    cmd += ["--no-apply", "--no-zed", "--no-vscode", "--no-neovim", "--output", str(out_dir)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as err:
        raise AetherError(f"aether not found at {aether_path}") from err
    except subprocess.TimeoutExpired as err:
        raise AetherError("aether timed out after 120s") from err
    if proc.returncode != 0:
        raise AetherError(f"aether exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:300]}")

    colors_file = out_dir / "colors.toml"
    if not colors_file.is_file():
        raise AetherError(f"aether produced no colors.toml in {out_dir}")
    raw = tomllib.loads(colors_file.read_text(encoding="utf-8"))

    palette = {k: v.lower() for k, v in raw.items() if k in _KEEP}
    palette.update({_AETHER_RENAMES[k]: v.lower() for k, v in raw.items() if k in _AETHER_RENAMES})
    # Keep only the identity keys; our ramps/contrast own everything else.
    identity = _KEEP | {"mode"}
    palette = {k: v for k, v in palette.items() if k in identity}
    missing = {"background", "foreground", "accent", "red", "blue", "green"} - palette.keys()
    if missing:
        raise AetherError(f"aether palette missing keys: {sorted(missing)}")
    palette["mode"] = mode  # our decision wins, not aether's default
    return palette


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def fallback_extract(img_path: Path, mode: str) -> dict[str, str]:
    """Median-cut extraction: a valid, decent palette with zero dependencies."""
    img = load_image(img_path).resize((64, 36))
    q = img.quantize(colors=16, method=Image.Quantize.MEDIANCUT)  # type: ignore[attr-defined]
    palette_rgb = q.getpalette() or []
    ranked: list[tuple[int, int, int]] = []
    for count, index in sorted(q.getcolors(16) or [], reverse=True):
        base = index * 3
        ranked.append(tuple(palette_rgb[base:base + 3]))  # type: ignore[arg-type]

    def luma(c: tuple[int, int, int]) -> float:
        return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255

    def sat(c: tuple[int, int, int]) -> float:
        return rgb_to_hsl(c)[1]

    # Background: the most frequent color at the mode-appropriate luma end.
    top = ranked[:8]
    bg = (min if mode == "dark" else max)(top, key=luma)

    # Foreground: near-white/near-black, faintly tinted by the accent hue.
    most_saturated = max(ranked, key=sat)
    fg_pole = (255, 255, 255) if mode == "dark" else (0, 0, 0)
    fg = blend(fg_pole, most_saturated, 0.08)

    # Accent: the most saturated mid-luma color.
    mid = [c for c in ranked if 0.20 <= luma(c) <= 0.80] or ranked
    accent = max(mid, key=sat)

    # Named hues: greedy nearest-hue assignment without replacement.
    pool = list(dict.fromkeys(ranked))  # dedupe, frequency order kept
    palette: dict[str, str] = {"mode": mode, "background": rgb_to_hex(bg), "foreground": rgb_to_hex(fg),
                               "accent": rgb_to_hex(accent)}
    for name, target_hue in _CANONICAL_HUES:
        if pool:
            pick_i = min(range(len(pool)), key=lambda i: _hue_distance(rgb_to_hsl(pool[i])[0], target_hue))
            palette[name] = rgb_to_hex(pool.pop(pick_i))
        else:  # pragma: no cover - 16 quantized colors always cover 8 slots
            palette[name] = rgb_to_hex(accent)

    # Brights (the six official ones only): shift lightness toward the text
    # pole; selection and muted start near the poles.
    pole_up = mode == "dark"
    for name in ("red", "yellow", "green", "cyan", "blue", "magenta"):
        h, s, l = rgb_to_hsl(hex_to_rgb(palette[name]))
        bright_l = min(l + 0.12, 0.95) if pole_up else max(l - 0.12, 0.05)
        palette["bright_" + name] = rgb_to_hex(hsl_to_rgb((h, s, bright_l)))
    palette["selection"] = rgb_to_hex(blend(bg, fg, 0.18))
    palette["muted"] = rgb_to_hex(blend(fg, bg, 0.45))
    return palette


def extract(img_path: Path, mode: str, aether_path: str | None, work_dir: Path) -> tuple[dict[str, str], str]:
    """Extract the palette: aether when available, Pillow fallback otherwise."""
    resolved = aether_path or shutil.which("aether")
    if resolved:
        try:
            return run_aether(resolved, img_path, mode, work_dir / "aether-out"), "aether"
        except AetherError as err:
            print(f"WARN: aether failed ({err}); using Pillow fallback")
    else:
        print("WARN: aether not found; using Pillow fallback")
    return fallback_extract(img_path, mode), "fallback"
