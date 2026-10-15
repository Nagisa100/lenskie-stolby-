"""
Лист-превью всех видов: референс-фото (если есть в assets/reference/), спрайт карты,
спрайт карточки и силуэт → preview/species_sheet.png.

    python tools/species_sheet.py
"""
import os, sys, glob
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOME)
sys.path.insert(0, os.path.join(HOME, "tools"))

from PIL import Image, ImageDraw, ImageFont
import assets
import plants_art
from species import SPECIES, kind_info, zones
from sample_palette import crop

COLS = 3
CELL_W, CELL_H = 600, 178
PHOTO = 150


def _ref(i):
    """фото вида по номеру на сайте (файлы скачаны как NN_Название.png)"""
    files = glob.glob(os.path.join(HOME, "assets", "reference", f"{i + 1:02d}_*.png"))
    return crop(files[0]) if files else None


def _up(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def main():
    rows = (len(SPECIES) + COLS - 1) // COLS
    sheet = Image.new("RGBA", (COLS * CELL_W, rows * CELL_H + 40), assets.UI_PANEL + (255,))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(assets.FONT_PATH, 16)
    small = ImageFont.truetype(assets.FONT_PATH, 13)
    d.text((12, 10), f"Виды парка: {len(SPECIES)} · фото Красной книги РС(Я) → спрайт карты (x4) → карточка (x4) → силуэт",
           fill=assets.UI_GREEN, font=font)
    for i, sp in enumerate(SPECIES):
        x0, y0 = (i % COLS) * CELL_W + 10, (i // COLS) * CELL_H + 40
        d.rectangle((x0 - 4, y0 - 2, x0 + CELL_W - 14, y0 + CELL_H - 8), outline=assets.UI_EDGE, width=2)
        d.text((x0 + 4, y0 + 2), f"{i + 1}. {sp['name']}", fill=assets.UI_INK, font=font)
        d.text((x0 + 4, y0 + 20), f"{kind_info(sp)['label']} · {', '.join(zones(sp))} · {sp['habitat']}", fill=assets.UI_FAINT, font=small)
        ph = _ref(i)
        px = x0 + 4
        if ph:
            ph = ph.convert("RGBA")
            ph.thumbnail((PHOTO, PHOTO - 24))
            sheet.alpha_composite(ph, (px, y0 + 38))
        else:
            d.rectangle((px, y0 + 38, px + PHOTO - 10, y0 + 38 + PHOTO - 30), outline=assets.UI_EDGE)
            d.text((px + 8, y0 + 90), "нет фото", fill=assets.UI_FAINT, font=small)
        px += PHOTO + 6
        for s in (-1, 0, 1):
            m = _up(plants_art.plant_sprite(sp, sway=s), 3)
            sheet.alpha_composite(m, (px, y0 + CELL_H - 14 - m.height))
            px += m.width + 2
        px += 8
        card = _up(plants_art.plant_sprite(sp, big=True), 4)
        sheet.alpha_composite(card, (px, y0 + CELL_H - 12 - card.height))
        px += card.width + 8
        g = _up(plants_art.plant_sprite(sp, grey=True), 3)
        sheet.alpha_composite(g, (px, y0 + CELL_H - 14 - g.height))
    out = os.path.join(HOME, "preview", "species_sheet.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print("saved", out)
    probs = plants_art.check_art()
    for p in probs:
        print("!", p)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
