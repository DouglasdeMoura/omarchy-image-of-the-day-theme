"""Provenance and outputs: theme.json (committed), palette.json and
release-notes.md (release assets)."""

from __future__ import annotations

import json
from pathlib import Path

import PIL

from . import __version__
from .colors import KEY_ORDER
from .contrast import BRIGHT_HUES, HUES

_CONTRAST_TARGETS = (
    [("foreground_vs_background", 7.0), ("accent_vs_background", 4.5), ("foreground_vs_selection", 4.5)]
    + [(f"{k}_vs_background", 3.0) for k in HUES + ["muted"]]
    + [(f"{k}_vs_background", 4.5) for k in BRIGHT_HUES]
    + [("foreground_vs_dark_background", 4.5), ("foreground_vs_lighter_background", 4.5)]
)

_REPO = "https://github.com/DouglasdeMoura/omarchy-image-of-the-day-theme"

_CREDITS_HEADER = """# Image credits

All wallpapers in this theme are Bing images of the day, © Microsoft.
They are used here as desktop wallpapers for personal use; Microsoft owns
the copyright, and images are removed on request.

| Date | Image | Credit |
| --- | --- | --- |
"""


def load_existing_state(root: Path) -> dict | None:
    state_file = root / "theme.json"
    if not state_file.is_file():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_meta(
    *, hsh: str, date: str, tag: str, startdate: str, title: str, copyright: str,
    copyrightlink: str, market: str, mode: str, source: str, icons: str,
    image_file: str, image_url: str, aether_version: str | None,
) -> dict:
    return {
        "hsh": hsh,
        "date": date,
        "tag": tag,
        "startdate": startdate,
        "title": title,
        "copyright": copyright,
        "copyrightlink": copyrightlink,
        "market": market,
        "mode": mode,
        "source": source,
        "icons": icons,
        "image_file": image_file,
        "image_url": image_url,
        "generator": {
            "theme_builder": __version__,
            "aether": aether_version if source == "aether" else None,
            "pillow": PIL.__version__,
        },
    }


def write_theme_json(root: Path, meta: dict, palette: dict[str, str], ratios: dict[str, float]) -> None:
    doc = dict(meta)
    doc["palette"] = {k: palette[k] for k in KEY_ORDER}
    doc["contrast"] = {k: round(r, 2) for k, r in ratios.items()}
    (root / "theme.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_palette_json(dist: Path, meta: dict, palette: dict[str, str], ratios: dict[str, float]) -> Path:
    doc = dict(meta)
    doc["palette"] = {k: palette[k] for k in KEY_ORDER}
    doc["contrast"] = {k: round(r, 2) for k, r in ratios.items()}
    dest = dist / "palette.json"
    dest.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return dest


def write_credits(root: Path, meta: dict) -> Path:
    """CREDITS.md: one row per image ever shipped; idempotent for the same date."""
    credit = meta["copyright"]
    if meta.get("copyrightlink"):
        credit = f"[{credit}]({meta['copyrightlink']})"
    row = f"| {meta['date']} | {meta['title']} | {credit} |"

    dest = root / "CREDITS.md"
    rows = []
    if dest.is_file():
        rows = [
            line for line in dest.read_text(encoding="utf-8").splitlines()
            if line.startswith("| ") and not line.startswith("| ---")
            and not line.startswith(f"| {meta['date']} |")
        ]
    rows.append(row)
    dest.write_text(_CREDITS_HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return dest


def write_release_notes(dist: Path, meta: dict, palette: dict[str, str], ratios: dict[str, float]) -> Path:
    targets = dict(_CONTRAST_TARGETS)
    # Relative asset links do not resolve on GitHub release pages — use the
    # absolute releases/download URL.
    wallpaper_asset = f"{_REPO}/releases/download/{meta['tag']}/{meta['image_file'].split('/')[-1]}"
    lines = [
        f"# {meta['title']} ({meta['date']})",
        "",
        f"[{meta['copyright']}]({meta['copyrightlink']})",
        "",
        f"![wallpaper]({wallpaper_asset})",
        "",
        f"Mode: **{meta['mode']}** · palette: **{meta['source']}** · icons: `{meta['icons']}`",
        "",
        "## Palette",
        "",
        "| Key | Color |",
        "| --- | --- |",
    ]
    # Each row shows a swatch dot image (a release asset) next to the hex.
    lines += [
        f"| `{k}` | ![{palette[k]}]({_REPO}/releases/download/{meta['tag']}/swatches/{k}.png) `{palette[k]}` |"
        for k in KEY_ORDER if k != "mode"
    ]

    lines += ["", "## Contrast (WCAG)", "", "| Check | Ratio | Target | Pass |", "| --- | --- | --- | --- |"]
    for check, target in _CONTRAST_TARGETS:
        got = ratios.get(check)
        if got is None:
            continue
        lines.append(f"| {check} | {got:.2f}:1 | ≥{target}:1 | {'✅' if got >= target else '❌'} |")

    lines += [
        "",
        "## Install",
        "",
        "```",
        f"omarchy theme install {_REPO}.git",
        "omarchy theme set image-of-the-day",
        "```",
        "",
        "Wallpaper © Microsoft / Bing image of the day — personal wallpaper use.",
        "",
    ]
    dest = dist / "release-notes.md"
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest
