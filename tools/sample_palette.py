"""
Палитра по референс-фото из assets/reference/: доминантные цвета и приглушённые под игру.

    python tools/sample_palette.py              # все виды
    python tools/sample_palette.py Мак          # только «Мак»
    python tools/sample_palette.py --crops      # ещё сохранить вырезанные фото
"""
import os, sys, glob
from PIL import Image

HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(HOME, "assets", "reference")


def _longest(flags, gap=0):
    """самый длинный участок True с провалами до gap"""
    best, start, last = (0, -1), None, None
    for i, f in enumerate(flags + [False] * (gap + 1)):
        if f:
            start = i if start is None else start
            last = i
        elif start is not None and i - last > gap:
            if last - start > best[1] - best[0]:
                best = (start, last)
            start = None
    return best


def photo_box(im):
    """прямоугольник фото на странице"""
    W, H = im.size
    px = im.load()
    x0 = W // 2 - 30
    ink = lambda x, y: sum(px[x, y][:3]) < 700
    def long_run(y):
        a, b = _longest([ink(x, y) for x in range(x0, W)], gap=2)
        return b - a > 100
    y0, y1 = _longest([long_run(y) for y in range(H)], gap=10)
    if y1 - y0 < 60:  # рисунок на белом — рамка по умолчанию
        return (W // 2, 60, W - 20, 266)
    cols = [sum(ink(x, y) for y in range(y0, y1 + 1, 2)) > 0.8 * (y1 - y0) / 2 for x in range(x0, W)]
    c0, c1 = _longest(cols)
    return (x0 + c0, y0, x0 + c1 + 1, y1 + 1)


def crop(path):
    im = Image.open(path).convert("RGB")
    return im.crop(photo_box(im))


def dominant(im, n=5):
    """доминантные цвета"""
    small = im.copy()
    small.thumbnail((160, 160))
    q = small.quantize(colors=n + 3, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    out = []
    for cnt, idx in sorted(q.getcolors(), reverse=True):
        c = tuple(pal[idx*3: idx*3 + 3])
        if sum(c) > 720:
            continue
        out.append((cnt, c))
    total = sum(c for c, _ in out) or 1
    return [(round(100*c/total), col) for c, col in out[:n]]


def accents(im, n=4):
    """цвета объекта без зелёного фона"""
    import colorsys
    small = im.copy()
    small.thumbnail((160, 160))
    keep = []
    for p in small.getdata():
        h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in p))
        green = 0.17 < h < 0.47
        if (s > 0.35 and v > 0.35 and not green) or (v > 0.8 and s < 0.18):
            keep.append(p)
    if len(keep) < 20:
        return []
    acc = Image.new("RGB", (len(keep), 1))
    acc.putdata(keep)
    q = acc.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    total = len(keep)
    return [(round(100*cnt/total), tuple(pal[i*3: i*3 + 3])) for cnt, i in sorted(q.getcolors(), reverse=True)]


def mute(c, k=0.18):
    """приглушить под палитру Kenney"""
    g = (128, 120, 104)
    return tuple(int(c[i]*(1-k) + g[i]*k) for i in range(3))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = sorted(glob.glob(os.path.join(REF, "*.png")))
    if args:
        files = [f for f in files if any(a.lower() in os.path.basename(f).lower() for a in args)]
    if not files:
        print("нет референсов в", REF, "— скачай фото с lena-pillars.ru/keep/red-book/plants/")
        return
    if "--crops" in sys.argv:
        os.makedirs(os.path.join(REF, "crops"), exist_ok=True)
    for f in files:
        im = crop(f)
        name = os.path.splitext(os.path.basename(f))[0]
        if "--crops" in sys.argv:
            im.save(os.path.join(REF, "crops", name + ".png"))
        print(f"{name}  {im.size}")
        for pct, c in dominant(im):
            print(f"   фон {pct:3d}%  {c}  → {mute(c)}")
        for pct, c in accents(im):
            print(f"   акц {pct:3d}%  {c}  → {mute(c)}")


if __name__ == "__main__":
    main()
