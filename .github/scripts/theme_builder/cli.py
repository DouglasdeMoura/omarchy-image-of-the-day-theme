"""Build orchestration: fetch → decide → extract → contrast → write → validate.

Run identically locally and in CI:

    PYTHONPATH=.github/scripts python -m theme_builder [flags]

Flags for testing: --check (write under .github/dist/check-repo, repo
untouched), --image/--date/--title (offline), --aether (path override),
--force (rebuild even when the image is unchanged), --market.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from . import bing, colors, contrast, palette, preview, report, unlock
from .imaging import load_image

DENIED_NAMES = {"alacritty.toml", "foot.ini", "ghostty.conf", "kitty.conf", "vscode.json"}
BACKGROUND_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
WALLPAPER_MAX_BYTES = 3_000_000  # repo-size guard; UHD always ships on the release
JPEG_QUALITY = 87

_EXPECTED_DIMENSIONS = {
    "preview.png": (1800, 1012),
    "unlock.png": (800, 188),
    "preview-unlock.png": (1920, 1080),
}
_HEX_RE = re.compile(r"^#[0-9a-f]{6}$")


def _repo_root() -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Omarchy image-of-the-day theme")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--dist-dir", type=Path, default=None, help="default: <repo>/.github/dist")
    parser.add_argument("--force", action="store_true", help="rebuild even if the image is unchanged")
    parser.add_argument("--check", action="store_true", help="build into dist/check-repo; leave the repo untouched")
    parser.add_argument("--image", type=Path, help="offline test: use this image instead of Bing's")
    parser.add_argument("--date", help="offline test: override the date (YYYY-MM-DD)")
    parser.add_argument("--title", help="offline test: override the image title")
    parser.add_argument("--market", default="en-US")
    parser.add_argument("--aether", default=None, help="aether binary (default: $AETHER_PATH, then PATH)")
    return parser


def emit_outputs(**kv) -> None:
    for key, value in kv.items():
        line = f"{key}={value}"
        gh_output = os.environ.get("GITHUB_OUTPUT")
        if gh_output:
            with open(gh_output, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        print(line)


def validate_theme(root: Path) -> list[str]:
    """Return a list of problems; an empty list means the theme is shippable."""
    errors: list[str] = []

    colors_file = root / "colors.toml"
    if not colors_file.is_file():
        return [f"missing {colors_file}"]
    data = tomllib.loads(colors_file.read_text(encoding="utf-8"))
    if list(data.keys()) != colors.KEY_ORDER:
        errors.append("colors.toml keys diverge from the official set/order")
    for key, value in data.items():
        if key == "mode":
            if value not in ("dark", "light"):
                errors.append(f"mode must be dark|light, got {value!r}")
        elif not _HEX_RE.match(str(value)):
            errors.append(f"{key} = {value!r} is not a lowercase #rrggbb hex")

    bg_dir = root / "backgrounds"
    files = sorted(f for f in bg_dir.iterdir() if f.is_file()) if bg_dir.is_dir() else []
    if len(files) != 1:
        errors.append(f"backgrounds/ must hold exactly 1 file, found {len(files)}")
    for f in files:
        if f.suffix.lower() not in BACKGROUND_EXTS:
            errors.append(f"background {f.name}: unsupported extension")
        else:
            try:
                if load_image(f).width < 1920:
                    errors.append(f"background {f.name} is narrower than 1920px")
            except Exception as err:  # noqa: BLE001
                errors.append(f"background {f.name} is not decodable: {err}")

    for name, size in _EXPECTED_DIMENSIONS.items():
        path = root / name
        if not path.is_file():
            errors.append(f"missing {name}")
            continue
        with Image.open(path) as im:
            if im.size != size:
                errors.append(f"{name} is {im.size}, expected {size}")

    icons_file = root / "icons.theme"
    if not icons_file.is_file():
        errors.append("missing icons.theme")
    else:
        variant = icons_file.read_text(encoding="utf-8").strip()
        if variant not in colors.YARU_VARIANTS:
            errors.append(f"icons.theme {variant!r} is not a known Yaru variant")

    # Security: nothing a repo theme may not ship, and no symlinks at all.
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in (".git", ".github"):
            continue
        if path.is_symlink():
            errors.append(f"symlink in theme tree: {rel}")
        elif path.is_file() and (path.name in DENIED_NAMES or path.suffix == ".lua"):
            errors.append(f"denied file in theme tree: {rel}")

    theme_json = root / "theme.json"
    if not theme_json.is_file():
        errors.append("missing theme.json")
    else:
        try:
            if not json.loads(theme_json.read_text(encoding="utf-8")).get("hsh"):
                errors.append("theme.json is missing hsh")
        except Exception as err:  # noqa: BLE001
            errors.append(f"theme.json is unreadable: {err}")

    return errors


def _encode_wallpaper(src: Path, dest: Path) -> None:
    """Re-encode as optimized JPEG; downscale to 1080p if UHD is too heavy."""
    img = load_image(src)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
    blob = buf.getvalue()
    if len(blob) > WALLPAPER_MAX_BYTES and img.width > 1920:
        smaller = img.resize((1920, round(img.height * 1920 / img.width)))
        buf = io.BytesIO()
        smaller.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
        blob = buf.getvalue()
        print(f"WARN: UHD exceeded {WALLPAPER_MAX_BYTES} bytes; committed 1080p instead")
    dest.write_bytes(blob)
    print(f"wallpaper committed: {dest.name} ({len(blob) / 1e6:.1f} MB)")


def _aether_version(aether_path: str | None) -> str | None:
    resolved = aether_path or shutil.which("aether")
    if not resolved:
        return None
    try:
        proc = subprocess.run([resolved, "--version"], capture_output=True, text=True, timeout=15)
        return (proc.stdout or proc.stderr).strip()[:60] or None
    except Exception:  # noqa: BLE001 - version is cosmetic provenance
        return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = (args.repo_root or _repo_root()).resolve()
    dist = (args.dist_dir or repo_root / ".github" / "dist").resolve()
    work = dist / "work"
    work.mkdir(parents=True, exist_ok=True)

    aether_path = args.aether or os.environ.get("AETHER_PATH")

    # --- Fetch metadata (or synthesize it in offline test mode) -------------
    if args.image:
        blob = args.image.read_bytes()
        hsh = hashlib.sha256(blob).hexdigest()[:12]
        title = args.title or args.image.stem.replace("-", " ").title()
        startdate = (args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")).replace("-", "")
        copyright_text = f"local test image {args.image.name}"
        copyrightlink = ""
        image_url = str(args.image)
        wallpaper_src = args.image
    else:
        try:
            meta = bing.fetch_metadata(args.market)
        except bing.BingError as err:
            print(f"ERROR: {err}", file=sys.stderr)
            return 1
        hsh = meta.hsh
        title = meta.title
        startdate = meta.startdate
        copyright_text = meta.copyright
        copyrightlink = meta.copyrightlink
        image_url = ""
        # Idempotency: skip cleanly when today's image is already committed.
        # --check always rebuilds (it is diagnostic and never touches the repo).
        prev = report.load_existing_state(repo_root)
        if prev and prev.get("hsh") == hsh and not args.force and not args.check:
            print(f"no new image (hsh {hsh} unchanged)")
            emit_outputs(updated="false")
            return 0
        wallpaper_src, image_url = bing.download_image(meta, work / "today.jpg")

    date = f"{startdate[:4]}-{startdate[4:6]}-{startdate[6:8]}"

    # --- Palette pipeline ----------------------------------------------------
    mode = palette.decide_mode(wallpaper_src)
    pal, source = palette.extract(wallpaper_src, mode, aether_path, work)
    ratios = contrast.enforce_core(pal)
    colors.derive_ramps(pal)
    ratios.update(contrast.check_ramps(pal))
    ratios.update(contrast.enforce_selection(pal))

    # --- Write the theme -----------------------------------------------------
    target_root = dist / "check-repo" if args.check else repo_root
    target_root.mkdir(parents=True, exist_ok=True)
    (target_root / "backgrounds").mkdir(exist_ok=True)

    image_name = f"1-{bing.slugify(title)}.jpg"
    _encode_wallpaper(wallpaper_src, target_root / "backgrounds" / image_name)
    for old in (target_root / "backgrounds").iterdir():
        if old.name != image_name:
            old.unlink()

    colors.write_colors_toml(target_root, pal, header=f"{date} — {title}")
    icons_variant = colors.write_icons_theme(target_root, pal["accent"])

    unlock.render_unlock(wallpaper_src, pal, target_root / "unlock.png")
    preview.render_preview(wallpaper_src, pal, target_root / "preview.png")
    preview.render_preview_unlock(wallpaper_src, pal, target_root / "unlock.png", target_root / "preview-unlock.png")

    # --- Provenance, then validate before anything is declared done ----------
    meta_out = report.build_meta(
        hsh=hsh, date=date, startdate=startdate, title=title, copyright=copyright_text,
        copyrightlink=copyrightlink or image_url, market=args.market, mode=mode, source=source,
        icons=icons_variant, image_file=f"backgrounds/{image_name}", image_url=image_url,
        aether_version=_aether_version(aether_path),
    )
    report.write_theme_json(target_root, meta_out, pal, ratios)

    errors = validate_theme(target_root)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    report_dir = target_root if args.check else dist
    report.write_palette_json(report_dir, meta_out, pal, ratios)
    report.write_release_notes(report_dir, meta_out, pal, ratios)

    emit_outputs(
        updated="true", hsh=hsh, date=date, tag="v" + date.replace("-", "."),
        title=title, mode=mode, source=source, slug=image_name,
        commit_title=f"{date}: {title}",
    )
    return 0
