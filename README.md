# Omarchy Image of the Day Theme

An [Omarchy](https://omarchy.org) theme that rebuilds itself every day from
[Bing's image of the day](https://www.bing.com). A GitHub Action downloads
the photo, extracts a color palette with
[aether](https://github.com/omacom/aether) (falling back to a built-in
extractor), decides whether the day is a dark or light theme, tunes every
color for WCAG contrast, and commits + releases the result.

Every day you get: a new 4K wallpaper, a matching palette, a preview, and a
lock-screen banner.

## Install

```
omarchy theme install https://github.com/DouglasdeMoura/omarchy-image-of-the-day-theme.git
```

Then pick it like any theme — `omarchy theme set image-of-the-day`.

## Stay current

The theme lives in your `~/.config/omarchy/themes/` as a git clone, so
updating is:

```
omarchy theme update && omarchy theme set image-of-the-day
```

(Re-running `theme set` re-applies the fresh palette and swaps in the new
wallpaper.) Each day is also published as a release tagged `vYYYY.MM.DD`
with the 4K image, `colors.toml`, and the palette as JSON.

## How it works

- `.github/workflows/daily.yml` runs after Bing's daily image rollover
  (with a catch-up run later in the day) and on manual dispatch.
- All executable code lives under `.github/` — the repo root is pure theme
  data (`colors.toml`, `backgrounds/`, `preview.png`, `preview-unlock.png`,
  `unlock.png`, `chromium.theme`, `icons.theme`, `theme.json`, `CREDITS.md`).
  Nothing in the theme runs on your machine.
- Dark vs light is decided from the image's mean perceptual luma.
- Colors are adjusted for contrast by shifting lightness only — hues are
  preserved. The contrast report for each day ships in `theme.json` and the
  release notes.
- `preview.png` is a pixel-measured reproduction of a real Omarchy desktop
  (bar, foot window, fastfetch output) rendered as self-contained HTML and
  screenshotted in a headless browser, colored by the day's palette.
- History is strictly append-only (one commit per day) because
  `omarchy theme update` is a plain `git pull`.

## Credits & licenses

- Wallpapers are Bing's image of the day: © Microsoft and the credited
  photographers/agencies, personal wallpaper use. See `LICENSE`.
- The preview embeds JetBrainsMono Nerd Font (JetBrains Mono under the
  SIL OFL 1.1, license in `.github/scripts/theme_builder/assets/fonts/`;
  Nerd Font glyphs under the MIT-licensed Nerd Fonts patch set) and the
  Omarchy logo glyph from `omarchy.ttf` (© the Omarchy project).
- The terminal fixture mimics `fastfetch` output on Omarchy defaults.
