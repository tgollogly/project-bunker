#!/usr/bin/env python3
"""Repaint laptop calendar + contacts on docs/images/banner.png."""
from __future__ import annotations

import calendar as cal_mod
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BANNER = ROOT / "docs/images/banner.png"
REFERENCE = ROOT / "docs/images/banner-reference.png"

# Regions on the 1280×640 banner
CALENDAR_BOX = (165, 332, 310, 446)
CONTACTS_BOX = (298, 343, 403, 434)

# Geometry measured on banner-reference.png
COL_CENTERS = (181.2, 200.0, 220.3, 240.9, 259.7, 279.0, 297.4)
MONTH_Y = 366
ARROW_LEFT_X = 185
ARROW_RIGHT_X = 290
WEEKDAY_Y = 383
GRID_START_Y = 399
GRID_ROW_STEP = 11

CONTACT_ROW_Y = (352, 372, 392, 412, 432)
BADGE_CX = 309
NAME_X = 335
BADGE_FILL = (76, 94, 118)
BADGE_TEXT = (228, 234, 245)

CONTACT_NAMES = (
    "Office Manager",
    "IT Support",
    "Reception",
    "On-call Lead",
    "Facilities",
)

CALENDAR_BG = (19, 42, 66)
CONTACTS_BG = (7, 31, 55)
MONTH_TEXT = (213, 225, 241)
WEEKDAY_TEXT = (165, 178, 192)
DAY_TEXT = (146, 158, 170)
NAME_TEXT = (197, 209, 224)
ARROW_TEXT = (180, 196, 212)

YEAR, MONTH = 2026, 11


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    reg_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    path = bold_path if bold else reg_path
    if Path(path).is_file():
        return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _text_center(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font, fill) -> None:
    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x, y = xy
    draw.text((x - tw / 2, y - th / 2 - bb[1]), text, fill=fill, font=font)


def _november_grid() -> list[list[int]]:
    cal_mod.setfirstweekday(cal_mod.SUNDAY)
    return cal_mod.monthcalendar(YEAR, MONTH)


def _draw_calendar_patch() -> Image.Image:
    x0, y0, x1, y1 = CALENDAR_BOX
    w, h = x1 - x0, y1 - y0
    patch = Image.new("RGB", (w, h), CALENDAR_BG)
    draw = ImageDraw.Draw(patch)

    font_month = _font(11, bold=True)
    font_arrow = _font(10, bold=True)
    font_wd = _font(9)
    font_day = _font(10)

    month = " November 2026 "
    mid_x = (x0 + x1) / 2 - x0
    rel_y = MONTH_Y - y0
    _text_center(draw, (mid_x, rel_y), month, font_month, MONTH_TEXT)
    _text_center(draw, (ARROW_LEFT_X - x0, rel_y), "<", font_arrow, ARROW_TEXT)
    _text_center(draw, (ARROW_RIGHT_X - x0, rel_y), ">", font_arrow, ARROW_TEXT)

    for col_idx, cx in enumerate(COL_CENTERS):
        _text_center(draw, (cx - x0, WEEKDAY_Y - y0), "SMTWTFS"[col_idx], font_wd, WEEKDAY_TEXT)

    grid = _november_grid()
    for row_idx, week in enumerate(grid):
        row_y = GRID_START_Y + row_idx * GRID_ROW_STEP
        for col_idx, day in enumerate(week):
            if day == 0:
                continue
            _text_center(draw, (COL_CENTERS[col_idx] - x0, row_y - y0), str(day), font_day, DAY_TEXT)

    return patch


def _draw_badge(draw: ImageDraw.ImageDraw, cx: int, cy: int, letter: str) -> None:
    r = 8
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BADGE_FILL)
    _text_center(draw, (cx, cy), letter, _font(9, bold=True), BADGE_TEXT)


def _draw_contacts_patch(_reference: Image.Image) -> Image.Image:
    x0, y0, x1, y1 = CONTACTS_BOX
    w, h = x1 - x0, y1 - y0
    patch = Image.new("RGB", (w, h), CONTACTS_BG)
    draw = ImageDraw.Draw(patch)
    font = _font(11)

    for row_y, (letter, name) in zip(
        CONTACT_ROW_Y,
        zip("ABCDE", CONTACT_NAMES, strict=True),
        strict=True,
    ):
        rel_y = row_y - y0
        draw.rectangle((0, rel_y - 10, w - 1, rel_y + 10), fill=CONTACTS_BG)
        _draw_badge(draw, BADGE_CX - x0, rel_y, letter)

        name_x = NAME_X - x0
        bb = draw.textbbox((0, 0), name, font=font)
        th = bb[3] - bb[1]
        name_y = rel_y - th // 2 - bb[1]
        draw.text((name_x, name_y), name, fill=NAME_TEXT, font=font)

    return patch


def _validate(reference: Image.Image, after: Image.Image) -> None:
    import numpy as np

    b = np.array(reference)
    a = np.array(after)

    probes = [
        (235, 366),
        (240, 401),
        (338, 352),
        (338, 372),
        (338, 392),
        (350, 412),
        (350, 432),
    ]
    for x, y in probes:
        if int(b[y, x].sum()) < 360:
            continue
        if np.linalg.norm(a[y, x].astype(int) - b[y, x].astype(int)) < 18:
            raise SystemExit(f"legacy pixels still visible near ({x}, {y})")


def main() -> None:
    if not REFERENCE.is_file():
        raise SystemExit(f"Missing reference art: {REFERENCE}")

    reference = Image.open(REFERENCE).convert("RGB")
    banner = reference.copy()

    banner.paste(_draw_calendar_patch(), (CALENDAR_BOX[0], CALENDAR_BOX[1]))
    banner.paste(_draw_contacts_patch(reference), (CONTACTS_BOX[0], CONTACTS_BOX[1]))

    _validate(reference, banner)
    banner.save(BANNER, format="PNG", optimize=True)
    print(f"Updated {BANNER}")


if __name__ == "__main__":
    main()