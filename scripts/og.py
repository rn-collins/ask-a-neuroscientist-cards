#!/usr/bin/env python3
"""Draw one 1200x630 link-preview card per page, into og/<slug>.png.

A shared link with no preview image renders as a blank box, which is how every
card page looked before. These use the series paper and ink, the card's own
title and its one-line summary, so a link pasted into a message or a post looks
like the series it came from.
"""
import json
import pathlib
import textwrap

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
OUT = ROOT / "og"

PAPER = (250, 250, 246)
INK = (27, 25, 52)
SOFT = (86, 84, 106)
PINK = (255, 61, 154)
W, H = 1200, 630

# Verdana has no ʻokina (U+02BB), and the series writes ʻAwa, Hawaiʻi and
# ʻImiloa, so the card drew a blank box. Arial carries it.
FONTS = {
    "bold": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "reg": "/System/Library/Fonts/Supplemental/Arial.ttf",
}
# On a Linux build machine (the daily rebuild) Arial is not installed. DejaVu
# Sans carries the ʻokina too.
FALLBACK = {
    "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "reg": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
}


def font(kind, size):
    path = FONTS[kind] if pathlib.Path(FONTS[kind]).exists() else FALLBACK[kind]
    return ImageFont.truetype(path, size)


def draw_card(slug, title, dek, kicker):
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 12], fill=PINK)

    f_kick = font("bold", 20)
    x = 72
    for ch in kicker.upper():
        d.text((x, 86), ch, font=f_kick, fill=PINK)
        x += f_kick.getlength(ch) + 1.6

    size = 64 if len(title) <= 42 else (54 if len(title) <= 70 else 44)
    f_title = font("bold", size)
    wrap = max(18, int(W * 0.78 / (size * 0.58)))
    lines = textwrap.wrap(title, wrap)[:3]
    y = 150
    for line in lines:
        d.text((72, y), line, font=f_title, fill=INK)
        y += size * 1.18

    if dek:
        f_dek = font("reg", 26)
        y = min(max(y + 30, 360), 470)
        for line in textwrap.wrap(dek, 62)[:3]:
            d.text((72, y), line, font=f_dek, fill=SOFT)
            y += 38

    d.rectangle([0, H - 86, W, H], fill=INK)
    f_foot = font("bold", 22)
    d.text((72, H - 58), "ASK A NEUROSCIENTIST", font=f_foot, fill=PAPER)
    f_small = font("reg", 20)
    tail = "RN Collins"
    d.text((W - 72 - f_small.getlength(tail), H - 56), tail, font=f_small, fill=(170, 168, 185))
    return im


# The index pages share one card. Each card page has its own.
SITE = (
    "Ask a Neuroscientist",
    "How plants, places and daily life act on the brain, with the mechanism and the sources for each.",
    "the series",
)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    draw_card("_site", *SITE).save(OUT / "_site.png", optimize=True)
    n = 0
    for f in sorted(CONTENT.glob("*.json")):
        if f.stem.startswith("_"):
            continue
        c = json.loads(f.read_text())
        kicker = {"plant": "Plants", "place": "Place by place", "receptor": "How it works",
                  "term": "Glossary", "myth": "Myth or mechanism", "daily-life": "Everyday brain",
                  "organization": "Hawaiʻi", "series": "The series",
                  "archive": "From the archive"}.get(c.get("kind"), "The series")
        im = draw_card(f.stem, c["title"], c.get("dek", ""), kicker)
        im.save(OUT / f"{f.stem}.png", optimize=True)
        n += 1
    print(f"wrote {n} preview cards to {OUT}")


if __name__ == "__main__":
    main()
