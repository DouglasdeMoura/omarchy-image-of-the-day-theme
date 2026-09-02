"""Bing image-of-the-day metadata fetch and wallpaper download."""

from __future__ import annotations

import json
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .imaging import load_image

BING_API = "https://www.bing.com/HPImageArchive.aspx"
_UA = "Mozilla/5.0 (X11; Linux x86_64) omarchy-image-of-the-day-theme/1.0"
_RETRY_DELAYS = (2, 8)


class BingError(RuntimeError):
    pass


@dataclass(frozen=True)
class BingImage:
    title: str
    copyright: str
    copyrightlink: str
    urlbase: str
    url_1080: str
    hsh: str
    startdate: str  # "YYYYMMDD"

    @property
    def uhd_url(self) -> str:
        return f"https://www.bing.com{self.urlbase}_UHD.jpg"

    @property
    def url_1080_abs(self) -> str:
        return f"https://www.bing.com{self.url_1080}"


def _get_bytes(url: str, params: dict[str, str] | None = None, timeout: int = 30) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    last_err: Exception | None = None
    for attempt in range(1 + len(_RETRY_DELAYS)):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as err:  # noqa: BLE001 - report the last failure verbatim
            last_err = err
            if attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt])
    raise BingError(f"GET {url} failed after {1 + len(_RETRY_DELAYS)} attempts: {last_err}") from last_err


def fetch_metadata(market: str = "en-US") -> BingImage:
    """Fetch today's image metadata, failing loudly on any API shape change."""
    raw = _get_bytes(BING_API, {"format": "js", "idx": "0", "n": "1", "mkt": market})
    try:
        data = json.loads(raw)
        img = data["images"][0]
    except (json.JSONDecodeError, KeyError, IndexError) as err:
        raise BingError(f"unexpected Bing API response: {err}: {raw[:200]!r}") from err

    fields = ["title", "copyright", "copyrightlink", "urlbase", "url", "hsh", "startdate"]
    for field in fields:
        if not str(img.get(field, "")).strip():
            raise BingError(f"Bing API response is missing non-empty '{field}'")

    return BingImage(
        title=img["title"].strip(),
        copyright=img["copyright"].strip(),
        copyrightlink=img["copyrightlink"].strip(),
        urlbase=img["urlbase"].strip(),
        url_1080=img["url"].strip(),
        hsh=img["hsh"].strip(),
        startdate=img["startdate"].strip(),
    )


def download_image(meta: BingImage, dest: Path) -> tuple[Path, str]:
    """Download UHD with 1080p fallback; verify it decodes and is wide enough.

    Returns (path, resolved_url).
    """
    for label, url in (("UHD", meta.uhd_url), ("1080p", meta.url_1080_abs)):
        try:
            blob = _get_bytes(url)
            dest.write_bytes(blob)
            width = load_image(dest).width
            if width < 1920:
                raise BingError(f"{label} image is only {width}px wide")
            print(f"wallpaper: {label} ({len(blob) / 1e6:.1f} MB, {width}px)")
            return dest, url
        except BingError as err:
            print(f"WARN: {label} download failed ({err})")
    raise BingError("neither UHD nor 1080p wallpaper could be downloaded")


def slugify(title: str, max_len: int = 48) -> str:
    """Lowercase ascii slug: "Painted along the shore" -> "painted-along-the-shore"."""
    folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    kept = "".join(ch if ch.isalnum() else "-" for ch in folded.lower())
    slug = "-".join(part for part in kept.split("-") if part)
    return slug[:max_len].rstrip("-") or "untitled"
