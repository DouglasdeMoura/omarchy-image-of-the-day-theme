"""WCAG 2.1 contrast math and the palette contrast-enforcement pass.

Adjustment only ever shifts HSL lightness — hue and saturation are preserved
so the extracted palette keeps its character. All ratios are WCAG relative
luminance ratios (1..21).
"""

from __future__ import annotations

from .imaging import hex_to_rgb, hsl_to_rgb, rgb_to_hex, rgb_to_hsl

# The eight normal hues plus muted must clear 3:1 against the background;
# the six bright hues and the accent clear 4.5:1 (WCAG AA for text).
HUES = ["red", "yellow", "orange", "green", "cyan", "blue", "magenta", "brown"]
BRIGHT_HUES = ["bright_red", "bright_yellow", "bright_green", "bright_cyan", "bright_blue", "bright_magenta"]


def _channel(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def rel_lum(hex_color: str) -> float:
    r, g, b = hex_to_rgb(hex_color)
    return 0.2126 * _channel(r / 255) + 0.7152 * _channel(g / 255) + 0.0722 * _channel(b / 255)


def ratio(fg: str, bg: str) -> float:
    l1, l2 = rel_lum(fg), rel_lum(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def adjust_to_target(color: str, bg: str, target: float) -> str:
    """Shift lightness away from bg until ratio >= target, or as far as possible.

    Walks L in 0.01 steps toward the pole (black or white) that is farther
    from the background in WCAG luminance and returns the color achieving
    the best ratio along the way. The direction cannot be inferred from HSL
    lightness alone: a dark-yellow background such as #735230 has L≈0.32 but
    very low luminance, so lightening reaches far higher ratios (the poles
    are exactly #000000/#ffffff regardless of hue and saturation).
    """
    h, s, l = rgb_to_hsl(hex_to_rgb(color))
    step = 0.01 if ratio("#ffffff", bg) >= ratio("#000000", bg) else -0.01
    best, best_ratio = color, ratio(color, bg)
    cur = l
    for _ in range(100):
        cur += step
        if cur <= 0.0 or cur >= 1.0:
            cur = min(max(cur, 0.0), 1.0)
        cand = rgb_to_hex(hsl_to_rgb((h, s, cur)))
        r = ratio(cand, bg)
        if r > best_ratio:
            best, best_ratio = cand, r
        if best_ratio >= target or cur <= 0.0 or cur >= 1.0:
            break
    return best


def enforce_core(palette: dict[str, str]) -> dict[str, float]:
    """Steps 1–5 of the target table (everything checked against background).

    Mutates `palette` in place and returns the achieved ratios. Must run
    BEFORE colors.derive_ramps primes the shade keys.
    """
    bg = palette["background"]
    report: dict[str, float] = {}

    # 1. Body text: AAA.
    palette["foreground"] = adjust_to_target(palette["foreground"], bg, 7.0)
    report["foreground_vs_background"] = ratio(palette["foreground"], bg)

    # 2. Bright foreground mirrors foreground (as official themes do).
    palette["bright_foreground"] = palette["foreground"]
    report["bright_foreground_vs_background"] = report["foreground_vs_background"]

    # 3. Accent: AA for text-sized highlights.
    palette["accent"] = adjust_to_target(palette["accent"], bg, 4.5)
    report["accent_vs_background"] = ratio(palette["accent"], bg)

    # 4. Normal hues (and muted) readable as terminal colors.
    for key in HUES + ["muted"]:
        palette[key] = adjust_to_target(palette[key], bg, 3.0)
        report[f"{key}_vs_background"] = ratio(palette[key], bg)
        if key == "muted" and report[f"{key}_vs_background"] < 2.5:
            print(f"WARN: muted clamped at {report[key + '_vs_background']:.2f}:1 (target 3.0)")

    # 5. Bright hues: AA.
    for key in BRIGHT_HUES:
        palette[key] = adjust_to_target(palette[key], bg, 4.5)
        report[f"{key}_vs_background"] = ratio(palette[key], bg)

    return report


def check_ramps(palette: dict[str, str]) -> dict[str, float]:
    """Step 6: foreground must stay readable on the derived shades."""
    report = {}
    for key in ("dark_background", "lighter_background"):
        r = ratio(palette["foreground"], palette[key])
        report[f"foreground_vs_{key}"] = r
        if r < 4.5:
            raise ValueError(
                f"foreground vs {key} is {r:.2f}:1 (need 4.5) — ramp derivation is broken"
            )
    return report


def enforce_selection(palette: dict[str, str]) -> dict[str, float]:
    """Step 7: selected text stays readable — nudge selection's lightness."""
    fg, sel = palette["foreground"], palette["selection"]
    if ratio(fg, sel) < 4.5:
        palette["selection"] = adjust_to_target(sel, fg, 4.5)
    return {"foreground_vs_selection": ratio(palette["foreground"], palette["selection"])}
