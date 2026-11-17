#!/usr/bin/env python3
"""Repaint calendar + contact labels on docs/images/banner.png (laptop screen)."""
from __future__ import annotations

import calendar as cal_mod
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BANNER = ROOT / "docs/images/banner.png"

# Regions on the 1280×640 banner (pixels already include perspective)
CALENDAR_BOX = (162, 300, 308, 422)
CONTACTS_BOX = (298, 325, 405, 438)

CONTACT_NAME_STRIPES = [
    (35, 2, 128, 16),
    (40, 20, 125, 34),
    (40, 38, 125, 52),
    (40, 56, 125, 70),
    (40, 69, 125, 83),
]
CONTACT_NAMES = [
    "Office Manager",
    "IT Support",
    "Reception",
    "On-call Lead",
    "Facilities",
]

CALENDAR_BG = (19, 42, 66)
CONTACT_BG = (12, 32, 52)
TEXT_MAIN = (178, 233, 212)
TEXT_DIM = (210, 220, 232)
WEEKDAY_COLOR = (160, 175, 190)
MONTH_COLOR = (195, 235, 218)
CONTACT_COLOR = (186, 192, 206)

YEAR, MONTH = 2026, 11


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    reg_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    path = bold_path if bold else reg_path
    if Path(path).is_file():
        return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _november_grid() -> list[list[int]]:
    cal_mod.setfirstweekday(cal_mod.SUNDAY)
    return cal_mod.monthcalendar(YEAR, MONTH)


def _render_calendar_patch() -> Image.Image:
    x0, y0, x1, y1 = CALENDAR_BOX
    w, h = x1 - x0, y1 - y0
    patch = Image.new("RGB", (w, h), CALENDAR_BG)
    draw = ImageDraw.Draw(patch)

    font_month = _font(10, bold=True)
    font_wd = _font(7)
    font_day = _font(8)

    month_label = "November 2026"
    bb = draw.textbbox((0, 0), month_label, font=font_month)
    tw = bb[2] - bb[0]
    draw.text(((w - tw) // 2, 10), month_label, fill=MONTH_COLOR, font=font_month)

    weekdays = "SMTWTFS"
    col_w = w / 7.0
    wd_y = 26
    for i, ch in enumerate(weekdays):
        cx = col_w * i + col_w / 2
        bb = draw.textbbox((0, 0), ch, font=font_wd)
        twd = bb[2] - bb[0]
        draw.text((cx - twd / 2, wd_y), ch, fill=WEEKDAY_COLOR, font=font_wd)

    grid = _november_grid()
    row_h = 13
    start_y = 38
    for row_idx, week in enumerate(grid):
        for col_idx, day in enumerate(week):
            if day == 0:
                continue
            cx = col_w * col_idx + col_w / 2
            cy = start_y + row_idx * row_h
            label = str(day)
            color = TEXT_DIM if col_idx in (0, 6) else TEXT_MAIN
            bb = draw.textbbox((0, 0), label, font=font_day)
            twd = bb[2] - bb[0]
            draw.text((cx - twd / 2, cy), label, fill=color, font=font_day)

    return patch


def _render_contacts_patch(source_banner: Image.Image) -> Image.Image:
    x0, y0, x1, y1 = CONTACTS_BOX
    patch = source_banner.crop((x0, y0, x1, y1)).copy()
    draw = ImageDraw.Draw(patch)
    font = _font(8)
    for name, (rx0, ry0, rx1, ry1) in zip(CONTACT_NAMES, CONTACT_NAME_STRIPES, strict=True):
        draw.rectangle([rx0, ry0, rx1, ry1], fill=CONTACT_BG)
        draw.text((rx0, ry0 - 1), name, fill=CONTACT_COLOR, font=font)
    return patch


def main() -> None:
    source = Image.open(BANNER).convert("RGB")
    banner = source.copy()
    cal_patch = _render_calendar_patch()
    contact_patch = _render_contacts_patch(source)
    banner.paste(cal_patch, (CALENDAR_BOX[0], CALENDAR_BOX[1]))
    banner.paste(contact_patch, (CONTACTS_BOX[0], CONTACTS_BOX[1]))
    banner.save(BANNER, format="PNG", optimize=True)
    print(f"Updated {BANNER}")


if __name__ == "__main__":
    main()