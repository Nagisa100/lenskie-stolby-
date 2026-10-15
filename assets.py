import os, math, random
from collections import Counter, deque
from PIL import Image, ImageDraw

HOME = os.path.dirname(os.path.abspath(__file__))
ATLAS = Image.open(HOME + "/assets/tiny-town/Tilemap/tilemap_packed.png").convert("RGBA")
FONT_PATH = HOME + "/assets/fonts/Unifont.otf"
TILE = 16
_ACOLS = 12

def tile(idx):
    c, r = idx % _ACOLS, idx // _ACOLS
    return ATLAS.crop((c*TILE, r*TILE, c*TILE+TILE, r*TILE+TILE))

def _pal(idx, n=8):
    cnt = Counter()
    for p in tile(idx).getdata():
        if p[3] > 200:
            cnt[p[:3]] += 1
    return [c for c, _ in cnt.most_common(n)]

def _lum(c): return 0.3*c[0] + 0.59*c[1] + 0.11*c[2]
def blend(a, b, t): return tuple(int(a[i]*(1-t) + b[i]*t) for i in range(3))

def noise(x, y, s=0):
    v = (x*374761393 ^ y*668265263 ^ s*2246822519) & 0xffffffff
    v = (v ^ (v >> 13)) * 1274126177 & 0xffffffff
    return (v & 1023) / 1023.0

_BAYER = [[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]]
def bayer(x, y): return (_BAYER[y & 3][x & 3] + 0.5) / 16.0

def _noise_grid(w, h, s, cell):
    
    return [[noise(gx, gy, s) for gx in range(w // cell + 2)] for gy in range(h // cell + 2)]

def _smooth_at(grid, x, y, cell):
    gx, gy = x // cell, y // cell
    fx, fy = (x % cell) / cell, (y % cell) / cell
    fx, fy = fx*fx*(3 - 2*fx), fy*fy*(3 - 2*fy)
    r0, r1 = grid[gy], grid[gy+1]
    return (r0[gx]*(1-fx) + r0[gx+1]*fx)*(1-fy) + (r1[gx]*(1-fx) + r1[gx+1]*fx)*fy

GRASS_MD = _pal(0, 1)[0]
GRASS_DK = blend(GRASS_MD, (0, 0, 0), 0.28)
GRASS_LT = blend(GRASS_MD, (255, 255, 255), 0.12)
_dd = sorted([c for c in _pal(40, 8) if c[0] > c[1]], key=_lum)
DIRT_DK, DIRT_BASE, DIRT_LT = _dd[0], _dd[len(_dd)//2], _dd[-1]
_w = sorted([c for c in _pal(81, 8) if c[0] >= c[2]], key=_lum)
OUTLINE = _w[0]; WOOD_DK, WOOD_LT = _w[1], _w[-1]
WOOD_BASE = blend(WOOD_DK, WOOD_LT, 0.45)
SAND = (242, 208, 120)
SAND_DK = blend(DIRT_DK, SAND, 0.45); SAND_BASE = blend(DIRT_BASE, SAND, 0.5); SAND_LT = blend(DIRT_LT, SAND, 0.5)
PEBBLE = blend(DIRT_DK, (120, 112, 104), 0.5)
WOOD_END = blend(WOOD_LT, (236, 206, 150), 0.55); WOOD_RING = WOOD_DK
RIV, RIV_HI, RIV_LO = (63, 109, 140), (111, 166, 198), (45, 82, 112)
RIV_GLINT = blend(RIV_HI, (255, 255, 255), 0.55)
_st = sorted([c for c in _pal(96, 8) if c[2] > c[0]], key=_lum)
STONE_DK, STONE, STONE_LT = _st[0], _st[len(_st)//2], _st[-1]
FOREST = blend(GRASS_MD, GRASS_DK, 0.55)
DRY = blend(GRASS_MD, SAND, 0.38)
MOSS = blend(GRASS_DK, GRASS_MD, 0.35)
SHADOW = blend(GRASS_DK, (0, 0, 0), 0.5)
REED_HEAD = blend(WOOD_DK, OUTLINE, 0.45)
LEAF = _pal(1, 3)[-1]
CRACK = blend(DIRT_BASE, (176, 156, 124), 0.55)
CRACK_LT = blend(CRACK, SAND_LT, 0.35)
CRACK_DK = blend(DIRT_DK, OUTLINE, 0.4)
DRY_TUFT = blend(DRY, SAND_DK, 0.45)
ASPH = blend(STONE_DK, OUTLINE, 0.45)
ASPH_LT = blend(ASPH, STONE, 0.3)
ASPH_DK = blend(ASPH, OUTLINE, 0.4)
LINE = blend(STONE_LT, (255, 255, 255), 0.4)
LIME = blend(STONE_LT, SAND_LT, 0.45)
LIME_LT = blend(LIME, (255, 255, 255), 0.35)
LIME_DK = blend(STONE, SAND_DK, 0.4)
DEAD_WOOD = blend(WOOD_DK, STONE, 0.45)

UI_PANEL = (22, 35, 28); UI_PANEL2 = (30, 45, 36); UI_EDGE = (48, 71, 58)
UI_INK = (232, 240, 216); UI_FAINT = (159, 181, 162)
UI_GREEN = (95, 207, 134); UI_AMBER = (231, 160, 74); UI_RED = (224, 84, 74)

TREES_G = [28, 28, 5]; TREES_O = [27]
TALL_G = (4, 16); TALL_O = (3, 15)
MUSH, SIGN, RANGER = 29, 83, 104
# забор фермы и тачка из тайлсета
FENCE_TL, FENCE_H, FENCE_TR, FENCE_L, FENCE_R, FENCE_BL, FENCE_BR = 44, 45, 46, 56, 58, 68, 70
FENCE_END_L, FENCE_END_R, CART = 80, 82, 57

TUFT_P = {"Берег Лены": 0.20, "Тукулан": 0.08, "Кордон": 0.10, "Тайга": 0.12, "Засуха": 0.0,
          "Луга": 0.24, "Посёлок": 0.08}

FLOWER = ["..ppp..", ".pPWPp.", ".pPWPp.", "..ppp..", "...g...", "..lg...",
          "...gl..", "..lg...", "...g...", "...g..", "..ggg.."]

_P = {
    'H': (58, 90, 58), 'b': (150, 130, 70), 'S': (227, 180, 138),
    'U': (74, 122, 63), 'u': (52, 92, 48), 'B': (58, 42, 32), 'K': (150, 110, 60), 'e': (40, 30, 26),
}
PLAYER_DOWN = [
    "...HHHH...", "..HHHHHH..", "..bbbbbb..", "..SSSSSS..",
    "..SeSSeS..", "..SSSSSS..", ".UUUUUUUU.", "UUUUUUUUUU",
    "UuUUUUUUuU", ".UUUUUUUU.", "..BB..BB..", "..BB..BB..",
]
PLAYER_DOWN_STEP = PLAYER_DOWN[:6] + [
    ".UUUUUUUUU", "UUUUUUUUUU", "UuUUUUUUu.", "UUUUUUUUU.", "..BB..UU..", "..BB......",
]
PLAYER_UP = [
    "...HHHH...", "..HHHHHH..", "..bbbbbb..", "..HHHHHH..",
    "..KKKKKK..", ".UKKKKKKU.", "UUKKKKKKUU", "UuKKKKKKuU",
    ".UUUUUUUU.", "..UU..UU..", "..BB..BB..", "..BB..BB..",
]
PLAYER_UP_STEP = PLAYER_UP[:5] + [
    ".UKKKKKKUU", "UUKKKKKKUU", "UuKKKKKKu.", "UUUUUUUUU.", "..UU..UU..", "..BB..UU..", "..BB......",
]
PLAYER_RIGHT = [
    "..HHHHH...", ".HHHHHHH..", ".bbbbbS...", "..SSSSe...",
    "..SSSSS...", "..SSSS....", ".UUUUUU...", "UUUUUUU...",
    "UuUUUUK...", ".UUUUUU...", "..UUU.....", "..B.B.....",
]
PLAYER_RIGHT_STRIDE = PLAYER_RIGHT[:7] + [
    "UUUUUUU...", "uUUUUUUK..", ".UUUUUU...", ".UUUUU....", "BB...BB...",
]
PLAYER_RIGHT_PASS = PLAYER_RIGHT[:7] + [
    "UUUUUUU...", "UUuUUK....", ".UUUUUU...", "..UUU.....", "...BB.....",
]

BENCH = [
    "..LLLLLLLLLLLL..",
    "..wwdwwwwwwdww..",
    "...d........d...",
    "LLLLLLLLLLLLLLLL",
    "wwwwwdwwwwwdwwww",
    "dddddddddddddddd",
    ".dd..........dd.",
    ".dd..........dd.",
]
POST = [
    "......Pp........",
    "..LLLLLLLLLLL...",
    "..wkkwkwkkwwwL..",
    "..ddddddddddd...",
    "......Pp........",
    "...LLLLLLLLLLL..",
    "..LwwkkwkwkkwW..",
    "...ddddddddddd..",
    "......Pp........",
    "......Pp........",
    "......Pp........",
    "......Pp........",
    "......Pp........",
    ".....PPpp.......",
]

def _draw_grid(img, grid, pal, ox=0, oy=0):
    px = img.load()
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            col = pal.get(ch)
            if col:
                x, y = ox+c, oy+r
                if 0 <= x < img.width and 0 <= y < img.height:
                    px[x, y] = col + (255,)

def add_outline(img, color=OUTLINE):
    
    px = img.load(); W, H = img.size
    ring = []
    for y in range(H):
        for x in range(W):
            if px[x, y][3] < 40:
                for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    nx, ny = x+dx, y+dy
                    if 0 <= nx < W and 0 <= ny < H and px[nx, ny][3] > 120:
                        ring.append((x, y)); break
    for x, y in ring:
        px[x, y] = color + (255,)
    return img

def flower(base, light, grey=False, sway=0):
    
    pal = ({'p': (154,164,154), 'P': (107,117,107), 'W': (200,204,192), 'g': (90,99,88), 'l': (107,117,107)}
           if grey else {'p': light, 'P': base, 'W': (244,236,171), 'g': (47,107,69), 'l': (76,154,94)})
    img = Image.new("RGBA", (9, 13), (0, 0, 0, 0))
    _draw_grid(img, FLOWER[:5], pal, 1 + sway, 1)
    _draw_grid(img, FLOWER[5:], pal, 1, 6)
    return add_outline(img)

def _mirror(grid):
    return [row[::-1] for row in grid]

def player_palette(hair=None, shirt=None, shirt_dark=None):
    
    pal = dict(_P)
    if hair: pal['H'] = hair
    if shirt: pal['U'] = shirt
    if shirt_dark: pal['u'] = shirt_dark
    return pal

def player_sprites(palette=None):
    
    palette = palette or _P
    sets = {
        "down": (PLAYER_DOWN, PLAYER_DOWN_STEP, _mirror(PLAYER_DOWN_STEP)),
        "up": (PLAYER_UP, PLAYER_UP_STEP, _mirror(PLAYER_UP_STEP)),
        "right": (PLAYER_RIGHT, PLAYER_RIGHT_STRIDE, PLAYER_RIGHT_PASS),
    }
    out = {}
    for name, grids in sets.items():
        frames = []
        for grid in grids:
            img = Image.new("RGBA", (10, 13), (0, 0, 0, 0))
            _draw_grid(img, grid, palette)
            frames.append(add_outline(img))
        out[name] = frames
    out["left"] = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in out["right"]]
    return out

_RED, _RED_LT = _pal(29, 6)[1], _pal(29, 6)[4]
_ORANGE, _YELLOW = _pal(2, 5)[3], _pal(2, 5)[1]
TRASH = [
    (["..ttttt..", ".tTTWTTtcc", ".tTTTTTtcC", "..ttttt.."],
     {'t': (120, 160, 190), 'T': (150, 190, 215), 'W': (236, 244, 250), 'c': _RED, 'C': blend(_RED, OUTLINE, 0.3)}),
    ([".oOo...", "oOyOo..", "OyyyOo.", ".oOyOO.", "..oOo.."],
     {'o': _ORANGE, 'O': blend(_ORANGE, OUTLINE, 0.25), 'y': _YELLOW}),
    ([".rrrrr.", "rRWRRrs", "rRRRRrs", ".rrrrr."],
     {'r': blend(_RED, OUTLINE, 0.2), 'R': _RED, 'W': _RED_LT, 's': (200, 204, 192)}),
]

def trash_sprite(variant=0):
    
    grid, pal = TRASH[variant % len(TRASH)]
    img = Image.new("RGBA", (max(len(r) for r in grid) + 2, len(grid) + 2), (0, 0, 0, 0))
    _draw_grid(img, grid, pal, 1, 1)
    return add_outline(img)

ICON_MAP = ["aaAbbBaa", "agAbbBar", "aaAbgBaa", "aaAgbBga", "agAbbBaa", "aaAbbBaa"]
ICON_STATS = ["......GG", "......GG", "...YY.GG", "...YY.GG", "RR.YY.GG", "RR.YY.GG", "pppppppp"]

def icon_map():
    
    img = Image.new("RGBA", (10, 8), (0, 0, 0, 0))
    _draw_grid(img, ICON_MAP, {'a': SAND_LT, 'A': SAND_DK, 'b': SAND_BASE, 'B': SAND_DK,
                               'g': GRASS_DK, 'r': _RED}, 1, 1)
    return add_outline(img)

def icon_stats():
    
    img = Image.new("RGBA", (10, 9), (0, 0, 0, 0))
    _draw_grid(img, ICON_STATS, {'R': _RED, 'Y': _YELLOW, 'G': UI_GREEN, 'p': SAND_LT}, 1, 1)
    return add_outline(img)

CAR = [
    "....LLLLLLLLLLLLLL....",
    "...LbbbbbbbbbbbbbbbL..",
    "...bwwwbwwwbwwwbbwwwb.",
    "...bwwwbwwwbwwwbbwwwwb",
    "..LLLLLLLLLLLLLLLLLLLL",
    "..bbbbbbbbbbbbbbbbbbbh",
    "..BBBBBBBBBBBBBBBBBBBB",
    "..rBkkkkBBBBBBBkkkkBB.",
]
CAR_WHEELS = (["....kgkk.......kgkk...", "....kkkk.......kkkk..."],
              ["....kkgk.......kkgk...", "....kkkk.......kkkk..."])
_UAZ = blend(GRASS_DK, WOOD_DK, 0.35)
CAR_BODIES = [_UAZ, _RED, STONE, _YELLOW, STONE_LT]

def car_sprites(color=0):
    
    b = CAR_BODIES[color % len(CAR_BODIES)]
    pal = {'b': b, 'L': blend(b, (255, 255, 255), 0.3), 'B': blend(b, OUTLINE, 0.35),
           'w': blend(RIV_HI, (255, 255, 255), 0.35), 'h': (255, 240, 170), 'r': blend(_RED, OUTLINE, 0.2),
           'k': blend(OUTLINE, (0, 0, 0), 0.3), 'g': STONE}
    frames = []
    for wheels in CAR_WHEELS:
        img = Image.new("RGBA", (24, 12), (0, 0, 0, 0))
        _draw_grid(img, CAR + wheels, pal, 1, 1)
        frames.append(add_outline(img))
    return {"right": frames, "left": [f.transpose(Image.FLIP_LEFT_RIGHT) for f in frames]}

HORSE_BODY = [
    "..............m.....",
    ".............mHm....",
    "............mHHHH...",
    "...........mHHHeHH..",
    "...........mHHHHHHHn",
    "..m.......mHHHH.....",
    ".mmbbbbbbbbbHH......",
    "mm.bbbbbbbbbbb......",
    "m..bbbbbbbbbbb......",
    "...bbbbbbbbbbb......",
]
HORSE_LEGS = [
    ["...BB.bb...BB.bb....", "...BB.bb...BB.bb....", "...hh.hh...hh.hh...."],
    ["..BB..bb....BBbb....", "..BB...bb...BBbb....", "..hh...hh...hhhh...."],
    ["...BBbb...BB..bb....", "...BBbb..BB....bb...", "...hhhh..hh....hh..."],
]
HORSE_GRAZE = [
    "....................",
    "....................",
    "....................",
    "....................",
    "....................",
    "..m.................",
    ".mmbbbbbbbbbbm......",
    "mm.bbbbbbbbbbHm.....",
    "m..bbbbbbbbbbbHHm...",
    "...bbbbbbbbbbb.HHm..",
    "...BB.bb...BB.bbHHm.",
    "...BB.bb...BB.bb.HeH",
    "...hh.hh...hh.hh.HHn",
]
HORSE_COATS = [
    ((214, 212, 200), (96, 90, 88)),
    (WOOD_DK, (52, 36, 30)),
    (SAND_DK, (92, 70, 48)),
]

def horse_sprites(variant=0):
    
    coat, mane = HORSE_COATS[variant % len(HORSE_COATS)]
    pal = {'b': coat, 'H': coat, 'B': blend(coat, OUTLINE, 0.25), 'm': mane,
           'h': blend(mane, OUTLINE, 0.5), 'e': OUTLINE, 'n': blend(coat, OUTLINE, 0.45)}
    grids = [HORSE_BODY + legs for legs in HORSE_LEGS] + [HORSE_GRAZE]
    frames = []
    for grid in grids:
        img = Image.new("RGBA", (22, 15), (0, 0, 0, 0))
        _draw_grid(img, grid, pal, 1, 1)
        frames.append(add_outline(img))
    return {"right": frames, "left": [f.transpose(Image.FLIP_LEFT_RIGHT) for f in frames]}

# рейнджер верхом: сбоку — лошадь и торс игрока, спереди и сзади — свои сетки
RIDER_RIGHT = [
    "..HHHHH...", ".HHHHHHH..", ".bbbbbS...", "..SSSSe...", "..SSSSS...", "..SSSS....",
    ".UUUUUU...", "KUUUUUUS..", "KUuUUUU...", ".UUUUUU...", "..UUUU....", "...UUB....", "....BB....",
]
RIDE_DOWN = [
    "....HHHHH.....", "...HHHHHHH....", "...bbbbbbb....", "....SSSSS.....", "....SeSeS.....",
    "...UUSSSUU....", "..UUcUUUcUU...", "..UUcmmmcUU...", ".SUucmmmcuUS..", ".BCxocccoxCB..",
    ".BCxcccccxCB..", "..CCxcccxCC...", "..CCxcccxCC...", "..CCCxnxCCC...", "...CCxnxCC....",
]
RIDE_UP = [
    "....HHHHH.....", "...HHHHHHH....", "...bbbbbbb....", "....HHHHH.....", "....KKKKK.....",
    "...UKKKKKU....", "..UUKKKKKUU...", "..UuKKKKKuU...", ".BUUUUUUUUUB..", ".BcccUUUcccB..",
    "..ccccccccCC..", "..cccmmmccCC..", "..ccmmmmmcCC..", "...cmmmmmCC...", "...cCmmmCcC...",
]
RIDE_LEGS = [
    ["...cC....cC...", "...CC....CC...", "...kk....kk..."],
    ["...cC....cC...", "...kk....CC...", ".........kk..."],
    ["...cC....cC...", "...CC....kk...", "...kk........."],
]


def _horse_pal(variant):
    coat, mane = HORSE_COATS[variant % len(HORSE_COATS)]
    return {'c': coat, 'C': blend(coat, OUTLINE, 0.25), 'm': mane, 'k': blend(mane, OUTLINE, 0.5),
            'n': blend(coat, OUTLINE, 0.45), 'o': OUTLINE, 'x': blend(coat, OUTLINE, 0.6)}


def rider_sprites(variant=0):
    
    horse = horse_sprites(variant)["right"]
    out = {"right": []}
    for f in range(3):
        img = Image.new("RGBA", (24, 19), (0, 0, 0, 0))
        img.alpha_composite(horse[f], (0, 3))
        rider = Image.new("RGBA", (24, 19), (0, 0, 0, 0))
        _draw_grid(rider, RIDER_RIGHT, _P, 4, 1)
        img.alpha_composite(add_outline(rider))
        out["right"].append(img)
    out["left"] = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in out["right"]]
    pal = dict(_P)
    pal.update(_horse_pal(variant))
    for name, grid in (("down", RIDE_DOWN), ("up", RIDE_UP)):
        frames = []
        for legs in RIDE_LEGS:
            img = Image.new("RGBA", (16, len(grid) + len(legs) + 2), (0, 0, 0, 0))
            _draw_grid(img, grid + legs, pal, 1, 1)
            frames.append(add_outline(img))
        out[name] = frames
    return out


BUBBLE = [
    ".wwwwwwwww.", "wwwwwwwwwww", "wwwwwwwwwww", "wwwwwwwwwww", "wwwwwwwwwww",
    "wwwwwwwwwww", "wwwwwwwwwww", ".wwwwwwwww.", "...www.....", "...ww......", "...w.......",
]
BUBBLE_ICONS = {
    "intent": (["..r..", "..r..", "..r..", ".....", "..r.."], {'r': _RED}),
    "alarm": (["..a..", "..a..", "..a..", ".....", "..a.."], {'a': UI_AMBER}),
    "heart": ([".r.r.", "rrrrr", "rrrrr", ".rrr.", "..r.."], {'r': _RED}),
    "no": (["k...k", ".k.k.", "..k..", ".k.k.", "k...k"], {'k': blend(OUTLINE, (0, 0, 0), 0.3)}),
}


def bubble(kind):
    
    img = Image.new("RGBA", (13, 13), (0, 0, 0, 0))
    _draw_grid(img, BUBBLE, {'w': (248, 246, 236)}, 1, 1)
    grid, pal = BUBBLE_ICONS[kind]
    _draw_grid(img, grid, pal, 4, 2)
    return add_outline(img)


def dead_tree(seed=0):
    
    rnd = random.Random(seed)
    img = Image.new("RGBA", (16, 26), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lean = rnd.choice((-1, 0, 1))
    d.line([(8, 24), (8, 12), (8 + lean, 5)], fill=DEAD_WOOD + (255,), width=2)
    for y0, side, ln in ((15, -1, 5), (12, 1, 5), (9, -1, 4), (7, 1, 3)):
        if rnd.random() < 0.85:
            x0 = 8 + (lean if y0 < 10 else 0)
            x1, y1 = x0 + side * ln, y0 - ln + rnd.randrange(2)
            d.line([(x0, y0), (x1, y1)], fill=DEAD_WOOD + (255,), width=1)
            d.point((x1, y1 - 1), fill=DEAD_WOOD + (255,))
    px = img.load()
    for y in range(26):
        xs = [x for x in range(16) if px[x, y][3]]
        if len(xs) > 1:
            px[xs[-1], y] = blend(DEAD_WOOD, OUTLINE, 0.3) + (255,)
    return add_outline(img)

def pebbles(seed=0):
    
    rnd = random.Random(seed)
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    px = img.load()
    for _ in range(2 + rnd.randrange(2)):
        w, h = rnd.choice(((3, 2), (4, 3), (2, 2), (3, 3)))
        x0, y0 = 2 + rnd.randrange(16 - w - 4), 6 + rnd.randrange(16 - h - 8)
        for y in range(h):
            for x in range(w):
                px[x0 + x, y0 + y] = (STONE_LT if y == 0 and x < w - 1 else STONE) + (255,)
    return add_outline(img)

def rock_pillar(seed=0):
    
    W, H = 16, 32
    rnd = random.Random(seed)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = img.load()
    top = 3 + rnd.randrange(5)
    ph = rnd.uniform(0, 6.28)
    crack = rnd.uniform(-1.5, 1.5)
    for y in range(top, H - 1):
        t = (y - top) / (H - 1 - top)
        half = 2.8 + 3.0*t + 0.7*math.sin(y*0.9 + ph)
        cx = 8 + 0.7*math.sin(y*0.3 + ph)
        for x in range(1, W - 1):
            if abs(x + 0.5 - cx) > half:
                continue
            u = (x + 0.5 - (cx - half)) / (2*half)
            b = bayer(x, y) - 0.5
            col = LIME_LT if u < 0.28 + 0.2*b else (LIME if u < 0.68 + 0.2*b else LIME_DK)
            if (y + seed) % 6 == 0 and u > 0.15:
                col = blend(col, LIME_DK, 0.6)
            if abs(x + 0.5 - (cx + crack)) < 0.6 and noise(x, y, seed) < 0.6:
                col = LIME_DK
            px[x, y] = col + (255,)
    for dx, dy, col in ((-1, 0, GRASS_DK), (0, -1, GRASS_MD), (1, 0, GRASS_DK), (0, 0, GRASS_MD), (2, -1, GRASS_DK)):
        x, y = int(8 + 0.7*math.sin(top*0.3 + ph)) + dx, top + dy
        if 0 < x < W - 1 and 0 < y < H:
            px[x, y] = col + (255,)
    return add_outline(img)

P_SIGN = ["BBBBBBB", "BWWWBBB", "BWBBWBB", "BWWWBBB", "BWBBBBB", "BWBBBBB", "BBBBBBB",
          "...P...", "...P...", "...P...", "...P...", "..PPP.."]

def parking_sign():
    
    img = Image.new("RGBA", (9, 14), (0, 0, 0, 0))
    _draw_grid(img, P_SIGN, {'B': (58, 98, 168), 'W': (240, 244, 250), 'P': STONE}, 1, 1)
    return add_outline(img)

def litter_sprite():
    
    img = Image.new("RGBA", (12, 10), (0, 0, 0, 0))
    pal = {'t': (138, 150, 144), 'T': (168, 180, 172), 'r': (224, 84, 74),
           'c': (120, 160, 190), 'C': (150, 190, 215)}
    grid = [
        "....rr......", "...tTtt.....", "..tTTTTt..CC", ".tTtTtTt..Cc",
        ".tTTTTTt..Cc", ".tTtTtTt..Cc", ".tTTTTTt..CC", "..tttttt....",
        "............", "............",
    ]
    _draw_grid(img, grid, pal)
    return add_outline(img)

HAY = [
    "....yYyhy....",
    "..yYyyyyyYy..",
    ".yyhyyYyyhyy.",
    "yYyyyhyyyYyyy",
    "yyhyYyyyhyyYy",
    "YyyyyyYyyyyyY",
    "YYyYYyYYyYYYY",
]
TRAMPLED = [
    "..x....x.....",
    ".dgdx.dgdx.d.",
    "xgdgdgdxgdgdx",
    ".xdxx.xdx.xx.",
]


def haystack():
    
    img = Image.new("RGBA", (15, 9), (0, 0, 0, 0))
    _draw_grid(img, HAY, {'y': (226, 192, 96), 'Y': (184, 148, 64), 'h': (246, 222, 140)}, 1, 1)
    return add_outline(img)


def trampled():
    
    img = Image.new("RGBA", (15, 6), (0, 0, 0, 0))
    _draw_grid(img, TRAMPLED, {'g': (104, 116, 72), 'd': (128, 102, 64), 'x': (82, 66, 46)}, 1, 1)
    return img


def _fence_tile(world, r, c):
    
    f = world.fence
    up, down, left, right = (r-1, c) in f, (r+1, c) in f, (r, c-1) in f, (r, c+1) in f
    if (r, c+1) == world.gate:
        return FENCE_END_R
    if (r, c-1) == world.gate:
        return FENCE_END_L
    if down and not up:
        return FENCE_TL if right else (FENCE_TR if left else FENCE_L)
    if up and not down:
        return FENCE_BL if right else (FENCE_BR if left else FENCE_L)
    if up and down:
        return FENCE_L if (r, c+1) in world.pen else FENCE_R
    return FENCE_H


def portrait():
    return tile(RANGER).copy()

LOGO_PATH = HOME + "/assets/logo.png"

def logo():
    
    art = Image.open(LOGO_PATH).convert("RGBA")
    n = art.width
    img = Image.new("RGBA", (n + 6, n + 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, n + 5, n + 5), radius=5, fill=OUTLINE + (255,))
    d.rounded_rectangle((1, 1, n + 4, n + 4), radius=4, fill=(248, 246, 236, 255))
    mask = Image.new("L", art.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, n - 1, n - 1), radius=2, fill=255)
    img.paste(art, (3, 3), mask)
    return img

def bench():
    
    img = Image.new("RGBA", (18, 10), (0, 0, 0, 0))
    _draw_grid(img, BENCH, {'L': WOOD_LT, 'w': WOOD_BASE, 'd': WOOD_DK}, 1, 1)
    return add_outline(img)

def signpost():
    
    img = Image.new("RGBA", (18, 16), (0, 0, 0, 0))
    _draw_grid(img, POST, {'L': WOOD_LT, 'w': WOOD_BASE, 'd': WOOD_DK, 'W': WOOD_END,
                           'P': WOOD_DK, 'p': WOOD_BASE, 'k': OUTLINE}, 1, 1)
    return add_outline(img)

def boulder(seed=0, mossy=False):
    
    W, H = 16, 13
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px = img.load()
    rnd = random.Random(seed)
    cx, cy = 7.5 + rnd.uniform(-0.4, 0.4), 7.0
    rx, ry = 6.0 + rnd.uniform(-0.8, 0.4), 4.9 + rnd.uniform(-0.6, 0.3)
    ph = rnd.uniform(0, 6.28)
    for y in range(H):
        for x in range(W):
            dx, dy = (x + 0.5 - cx) / rx, (y + 0.5 - cy) / ry
            ang = math.atan2(dy, dx)
            wob = 1 + 0.09*math.sin(ang*3 + ph) + 0.05*math.sin(ang*5 + ph*2)
            if dx*dx + dy*dy > wob*wob or y > cy + ry*0.8:
                continue
            light = 0.5 - 0.45*dx - 0.6*dy
            b = bayer(x, y) - 0.5
            col = STONE_LT if light > 0.85 + 0.25*b else (STONE if light > 0.35 + 0.25*b else STONE_DK)
            if mossy and dy < -0.1 and noise(x, y, seed + 5) < 0.75 + 0.6*dy*-1 - 0.3:
                col = MOSS if light > 0.7 + 0.3*b else GRASS_DK
            px[x, y] = col + (255,)
    k = rnd.randrange(2)
    for i in range(3):
        x, y = int(cx) - 1 + i + k, int(cy) + (i % 2)
        if px[x, y][3]:
            px[x, y] = STONE_DK + (255,)
    return add_outline(img)

def reeds(seed=0):
    
    W, H = 16, 19
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    heads = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    px, hp = img.load(), heads.load()
    rnd = random.Random(seed)
    for k in range(5 + rnd.randrange(3)):
        x = 2 + rnd.randrange(12)
        ln = 4 + rnd.randrange(5)
        side = -1 if x < 8 else 1
        col = (GRASS_DK if k % 2 else LEAF) + (255,)
        for i in range(ln):
            xx = x + side * (i // 3)
            if 0 <= xx < W:
                px[xx, H-2-i] = col
    for k in range(2 + rnd.randrange(2)):
        x = 3 + k*4 + rnd.randrange(3)
        h = 10 + rnd.randrange(6)
        for i in range(h):
            px[x, H-2-i] = GRASS_DK + (255,)
        for i in range(4):
            for dx in (0, 1):
                hp[x + dx, H-2-h+2+i] =(WOOD_DK if i == 0 and dx == 0 else REED_HEAD) + (255,)
    img.alpha_composite(add_outline(heads))
    return img

def water_shimmer(frames=3, variants=4):
    
    out = []
    for f in range(frames):
        row = []
        for v in range(variants):
            rnd = random.Random(v*97 + 13)
            img = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
            px = img.load()
            for _ in range(3):
                y = 2 + rnd.randrange(9)
                x0 = rnd.randrange(12)
                ln = 2 + rnd.randrange(3)
                for i in range(ln):
                    px[(x0 + i + f*2) % 12 + 2, y] = RIV_HI + (255,)
            sx, sy = 3 + rnd.randrange(10), 3 + rnd.randrange(7)
            if (f + v) % frames == 0:
                px[sx, sy] = RIV_GLINT + (255,)
            row.append(img)
        out.append(row)
    return out

def _shadow(img, cx, cy, rx, ry):
    
    px = img.load(); BW, BH = img.size
    for y in range(int(cy - ry), int(cy + ry) + 1):
        for x in range(int(cx - rx), int(cx + rx) + 1):
            if 0 <= x < BW and 0 <= y < BH:
                d = ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2
                if d <= 1.0 and bayer(x, y) < (1 - d) * 0.9 + 0.08:
                    px[x, y] = blend(px[x, y][:3], SHADOW, 0.6) + (255,)

def _edge_pixels(size, cells):
    
    BW, BH = size
    DM = bytearray(BW * BH)
    for (r, c) in cells:
        for yy in range(r*TILE, r*TILE+TILE):
            off = yy*BW
            for xx in range(c*TILE, c*TILE+TILE):
                DM[off + xx] = 1
    II = [[0]*(BW+1) for _ in range(BH+1)]
    for y in range(BH):
        acc = 0; rp = II[y]; rn = II[y+1]
        for x in range(BW):
            acc += DM[y*BW + x]; rn[x+1] = rp[x+1] + acc
    def box(x0, y0, x1, y1):
        x0 = max(0, x0); y0 = max(0, y0); x1 = min(BW, x1); y1 = min(BH, y1)
        return II[y1][x1] - II[y0][x1] - II[y1][x0] + II[y0][x0]
    near = {(r+dr, c+dc) for (r, c) in cells for dr in (-1, 0, 1) for dc in (-1, 0, 1)}
    for (r, c) in near:
        if not (0 <= r*TILE < BH and 0 <= c*TILE < BW):
            continue
        for y in range(r*TILE, r*TILE+TILE):
            for x in range(c*TILE, c*TILE+TILE):
                s = box(x-2, y-2, x+3, y+3)
                if s:
                    yield x, y, s / 25.0

def _auto_ground(img, cells, dune):
    
    px = img.load()
    for x, y, e in _edge_pixels(img.size, cells):
        if e < 0.97:
            e += 0.16 * (noise(x, y, 9) - 0.5)
        if bayer(x, y) < e:
            is_d = (y//TILE, x//TILE) in dune
            nz = noise(x, y, 2)
            if is_d:
                col = SAND_DK if nz < 0.12 else (SAND_LT if nz < 0.26 else SAND_BASE)
            else:
                col = DIRT_DK if nz < 0.12 else (DIRT_LT if nz < 0.26 else DIRT_BASE)
            if e > 0.9 and noise(x, y, 3) < 0.02:
                col = PEBBLE
            elif 0.15 < e < 0.7 and noise(x, y, 4) < 0.12:
                col = GRASS_DK
            px[x, y] = col + (255,)

def _worley(x, y, cell, s):
    
    gx, gy = x // cell, y // cell
    d1 = d2 = 1e9
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            cx, cy = gx + ox, gy + oy
            fx = (cx + 0.15 + 0.7*noise(cx, cy, s)) * cell
            fy = (cy + 0.15 + 0.7*noise(cx, cy, s + 1)) * cell
            d = math.hypot(x + 0.5 - fx, y + 0.5 - fy)
            if d < d1:
                d1, d2 = d, d1
            elif d < d2:
                d2 = d
    return d1, d2

def _drought_ground(img, cells):
    
    px = img.load()
    for (r, c) in cells:
        for y in range(r*TILE, r*TILE+TILE):
            for x in range(c*TILE, c*TILE+TILE):
                px[x, y] = (DRY if noise(x, y, 37) > 0.2 else DRY_TUFT) + (255,)
    for x, y, e in _edge_pixels(img.size, cells):
        if e < 0.97:
            e += 0.22 * (noise(x, y, 31) - 0.5)
        if bayer(x, y) >= e:
            continue
        d1, d2 = _worley(x, y, 9, 41)
        nz = noise(x, y, 32)
        if d2 - d1 < 0.9:
            col = CRACK_DK
        elif d2 - d1 < 1.8 and nz < 0.5:
            col = CRACK_LT
        else:
            col = CRACK if nz > 0.15 else CRACK_LT
        px[x, y] = col + (255,)
    for (r, c) in sorted(cells):
        if noise(c, r, 34) < 0.45:
            ox, oy = 3 + int(noise(c, r, 35) * 9), 7 + int(noise(c, r, 36) * 6)
            for k, h in ((0, 3), (1, 4), (2, 2), (-1, 2)):
                for i in range(h):
                    x, y = c*TILE + ox + k, r*TILE + oy - i - (k == 2 and i > 1)
                    if 0 <= x < img.width and 0 <= y < img.height:
                        px[x, y] = (DRY_TUFT if i < h - 1 else DRY) + (255,)

def _draw_road(img, world):
    
    px = img.load()
    cells = world.road | world.parking
    BW, BH = img.size
    for (r, c) in cells:
        up, down = (r-1, c) not in cells, (r+1, c) not in cells
        left, right = c > 0 and (r, c-1) not in cells, c < world.W-1 and (r, c+1) not in cells
        for yy in range(TILE):
            for xx in range(TILE):
                x, y = c*TILE + xx, r*TILE + yy
                if y >= BH:
                    continue
                n = noise(x, y, 51)
                col = ASPH_LT if n < 0.1 else (ASPH_DK if n > 0.95 else ASPH)
                edge = min(yy if up else 9, TILE-1-yy if down else 9, xx if left else 9, TILE-1-xx if right else 9)
                if edge == 0:
                    col = ASPH_DK
                elif edge == 1:
                    col = STONE
                px[x, y] = col + (255,)
    rows = sorted({r for (r, c) in world.road})
    zebra = {c for (r, c) in world.crossing}
    if len(rows) >= 2:
        y = rows[1]*TILE
        for x in range(BW):
            if (x // 6) % 2 == 0 and x // TILE not in zebra:
                px[x, y-1] = SAND_LT + (255,)
                px[x, y] = SAND_LT + (255,)
    if zebra:
        # «зебра»
        x0, x1 = min(zebra)*TILE + 2, (max(zebra) + 1)*TILE - 2
        for y in range(rows[0]*TILE + 3, (rows[-1] + 1)*TILE - 3):
            if (y - rows[0]*TILE - 3) % 6 < 3:
                for x in range(x0, x1):
                    px[x, y] = (LINE if noise(x, y, 52) > 0.08 else STONE_LT) + (255,)
    for (r, c) in world.stalls:
        for x in (c*TILE - 3, (c+2)*TILE + 2):
            for y in range(r*TILE + 2, r*TILE + 15):
                if 0 <= x < BW:
                    px[x, y] = LINE + (255,)

def _zone_ground(img, world):
    
    BW, BH = img.size
    W, H = world.W, world.H
    dry_src = set(world.dune) | set(world.drought)
    dist = {cell: 0 for cell in dry_src}
    q = deque(dry_src)
    while q:
        r, c = q.popleft()
        if dist[(r, c)] >= 4:
            continue
        for n in ((r+1, c), (r-1, c), (r, c+1), (r, c-1)):
            if n not in dist and 0 <= n[0] < H and 0 <= n[1] < W:
                dist[n] = dist[(r, c)] + 1
                q.append(n)
    g_t = _noise_grid(BW, BH, 21, 12)
    g_d = _noise_grid(BW, BH, 22, 10)
    # только в парке
    mx, my, band = BW / 2, world.PH * TILE / 2, 2.5 * TILE
    px = img.load()
    for y in range(min(BH, world.PH * TILE)):
        south = max(0.0, min(1.0, (y - my) / band + 0.5))
        for x in range(int(mx - band), BW):
            if px[x, y][:3] != GRASS_MD:
                continue
            east = max(0.0, min(1.0, (x - mx) / band + 0.5))
            b = bayer(x, y)
            near = max(0.0, 1 - dist.get((y // TILE, x // TILE), 5) / 4) * 0.45
            if b < near:
                px[x, y] = DRY + (255,)
                continue
            wt = east * south
            if wt > 0:
                dens = wt * (0.2 + 0.55 * _smooth_at(g_t, x, y, 12))
                if b < dens:
                    px[x, y] = (GRASS_DK if b < dens * 0.3 else FOREST) + (255,)
                    continue
            wd = east * (1 - south)
            if wd > 0:
                dens = wd * (0.12 + 0.3 * _smooth_at(g_d, x, y, 10)) + near
                if b < dens:
                    px[x, y] = DRY + (255,)

def _draw_water(img, water):
    
    px = img.load()
    for (r, c) in water:
        below = (r+1, c) in water
        above = r == 0 or (r-1, c) in water  # у старицы есть верхний берег
        left = c == 0 or (r, c-1) in water
        right = (r, c+1) in water or (c+1)*TILE >= img.width
        for yy in range(TILE):
            y = r*TILE + yy
            for xx in range(TILE):
                x = c*TILE + xx
                col = RIV
                if (not below and yy >= TILE-3) or (not above and yy < 2):
                    col = RIV_LO
                elif (not left and xx < 2) or (not right and xx >= TILE-2):
                    col = RIV_LO
                elif r % 2 == 0 and x % 3 == 0 and yy == 6 + (x//3 % 3):
                    col = RIV_HI
                px[x, y] = col + (255,)

def _draw_log(img, x0, x1, yc):
    px = img.load(); hh = 4
    for x in range(x0 + 4, x1 - 4):
        for dy in range(-hh, hh + 1):
            col = WOOD_LT if dy <= -hh + 1 else (WOOD_DK if dy >= hh - 1 else WOOD_BASE)
            px[x, yc + dy] = col + (255,)
        px[x, yc - hh - 1] = OUTLINE + (255,)
        px[x, yc + hh + 1] = OUTLINE + (255,)
        if (x - (x0 + 4)) % 6 == 2:
            px[x, yc] = WOOD_DK + (255,)
    for ex in (x0 + 4, x1 - 5):
        for dy in range(-hh - 1, hh + 2):
            for dx in range(-4, 5):
                rr = (dx / 4.2) ** 2 + (dy / (hh + 1.3)) ** 2
                if rr <= 1.0:
                    col = (OUTLINE if rr > 0.74 else WOOD_END if rr > 0.50
                           else WOOD_RING if rr > 0.34 else WOOD_END if rr > 0.16 else WOOD_RING)
                    px[ex + dx, yc + dy] = col + (255,)

def _draw_house(img, house, door_cell):
    for (r, c), i in house.items():
        img.alpha_composite(tile(i), (c*TILE, r*TILE))
    BW, BH = img.size
    rs = [r for (r, c) in house]; cs = [c for (r, c) in house]
    hy1 = (max(rs) + 1) * TILE; hx0 = min(cs) * TILE; hx1 = (max(cs) + 1) * TILE; hy0 = min(rs) * TILE
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0)); shp = sh.load()
    SH = blend(GRASS_DK, (0, 0, 0), 0.5)
    for x in range(hx0 + 1, min(hx1 + 7, BW)):
        for y in range(hy1, min(hy1 + 7, BH)):
            if bayer(x, y) < (1 - (y - hy1) / 7.0) * 0.95:
                shp[x, y] = SH + (180,)
    for y in range(hy0 + 6, hy1):
        for x in range(hx1, min(hx1 + 6, BW)):
            if bayer(x, y) < (1 - (x - hx1) / 6.0) * 0.8:
                shp[x, y] = SH + (170,)
    img.alpha_composite(sh)
    if door_cell is None:  # у домиков посёлка дверь в тайле
        return
    px = img.load()
    dr0, dc0 = door_cell
    dcx = dc0 * TILE + 8; dbot = hy1 - 1; dw, dh = 8, 11
    dl, dr, dt = dcx - dw // 2, dcx + dw // 2, dbot - dh
    DOORP = blend(WOOD_DK, (12, 8, 8), 0.45)
    for x in range(dl, dr):
        for y in range(dt, dbot + 1):
            px[x, y] = (OUTLINE if (x in (dl, dr - 1) or y == dt) else DOORP) + (255,)
    for y in range(dt + 2, dbot):
        px[dcx, y] = OUTLINE + (255,)
    px[dr - 2, (dt + dbot) // 2] = WOOD_LT + (255,)

def build_map(world):
    
    random.seed(7)
    W, H = world.W, world.H
    BW, BH = W*TILE, H*TILE
    img = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    occupied = set(world.path) | set(world.dune) | set(world.water) | set(world.house.keys())
    occupied |= {(r, c) for (r, c, _) in world.trees}
    occupied |= set(world.benches) | set(world.posts) | set(world.reeds) | set(world.mushrooms)
    occupied |= {(r, c) for (r, c, _) in world.boulders}
    occupied |= set(world.pebbles) | set(world.wilted) | world.road | world.parking | world.drought
    occupied |= world.fence | {(r, c) for (r, c, _) in world.farm_props}
    occupied |= {cell for house in world.village for cell in house}
    gate = {world.gate, world.gate_out} if world.gate else set()
    for r in range(H):
        for c in range(W):
            if (r, c) in world.water:
                continue
            g = 0
            if (r, c) not in occupied and random.random() < TUFT_P.get(world.zone_at(r, c), 0.14):
                g = random.choice([1, 2])
            img.alpha_composite(tile(g), (c*TILE, r*TILE))
    _zone_ground(img, world)
    if world.water:
        _draw_water(img, world.water)
    if world.drought:
        _drought_ground(img, world.drought)
    _auto_ground(img, set(world.path) | set(world.dune) | gate, set(world.dune))
    if world.road or world.parking:
        _draw_road(img, world)
    for i, (r, c) in enumerate(sorted(world.reeds)):
        img.alpha_composite(reeds(i), (c*TILE, r*TILE - 3))
    if world.house:
        _draw_house(img, world.house, world.house_door)
    for house in world.village:
        _draw_house(img, house, None)
    if world.log:
        x0c, x1c, row = world.log
        _draw_log(img, x0c*TILE, x1c*TILE, row*TILE + 8)

    props = []
    for (r, c, kind) in world.trees:
        props.append((r, 1, c, "tree", kind))
    for i, (r, c, mossy) in enumerate(world.boulders):
        props.append((r, 0, c, "boulder", (i, mossy)))
    for (r, c) in world.benches:
        props.append((r, 0, c, "bench", None))
    for (r, c) in world.posts:
        props.append((r, 0, c, "post", None))
    for (r, c) in world.mushrooms:
        props.append((r, 0, c, "mush", None))
    for (r, c) in world.deco_signs:
        props.append((r, 2, c, "sign", None))
    for (r, c, seed) in world.pillars:
        props.append((r, 1, c, "pillar", seed))
    for i, (r, c) in enumerate(world.pebbles):
        props.append((r, -1, c, "pebbles", i))
    for (r, c) in world.wilted:
        props.append((r, 0, c, "wilted", None))
    for (r, c, color) in world.parked_cars:
        props.append((r, 1, c, "car", color))
    if world.p_sign:
        props.append((world.p_sign[0], 2, world.p_sign[1], "psign", None))
    for (r, c) in world.fence:
        props.append((r, 0, c, "fence", _fence_tile(world, r, c)))
    for (r, c, what) in world.farm_props:
        props.append((r, 0, c, what, None))
    bench_img, post_img = bench(), signpost()
    wilted_img = flower((0, 0, 0), (0, 0, 0), grey=True)
    cars = {}
    for (r, _, c, what, arg) in sorted(props, key=lambda p: (p[0], p[1], p[2])):
        x, y = c*TILE, r*TILE
        if what == "tree":
            if arg == "tallg":
                img.alpha_composite(tile(TALL_G[1]), (x, y)); img.alpha_composite(tile(TALL_G[0]), (x, y - TILE))
            elif arg == "tallo":
                img.alpha_composite(tile(TALL_O[1]), (x, y)); img.alpha_composite(tile(TALL_O[0]), (x, y - TILE))
            elif arg == "o":
                img.alpha_composite(tile(random.choice(TREES_O)), (x, y))
            elif arg == "dead":
                _shadow(img, x + 9, y + 15, 4.5, 1.5)
                img.alpha_composite(dead_tree(r * 31 + c), (x, y - 10))
            else:
                img.alpha_composite(tile(random.choice(TREES_G)), (x, y))
        elif what == "pillar":
            _shadow(img, x + 9, y + 15, 7.0, 2.0)
            img.alpha_composite(rock_pillar(arg * 13 + c), (x, y - 16))
        elif what == "pebbles":
            img.alpha_composite(pebbles(arg), (x, y))
        elif what == "wilted":
            img.alpha_composite(wilted_img, (x + (TILE - wilted_img.width) // 2, y + TILE - wilted_img.height))
        elif what == "car":
            if arg not in cars:
                cars[arg] = car_sprites(arg)
            side = "right" if (r + c) % 2 else "left"
            _shadow(img, x + 17, y + 14, 12.0, 2.2)
            img.alpha_composite(cars[arg][side][0], (x + 4, y + 3))
        elif what == "psign":
            img.alpha_composite(parking_sign(), (x + 3, y + 2))
        elif what == "boulder":
            _shadow(img, x + 9, y + 13, 7.5, 2.6)
            img.alpha_composite(boulder(arg[0] * 7 + 3, arg[1]), (x, y + 2))
        elif what == "bench":
            _shadow(img, x + 9, y + 14, 8.5, 2.2)
            img.alpha_composite(bench_img, (x - 1, y + 5))
        elif what == "post":
            _shadow(img, x + 9, y + 15, 4.5, 1.6)
            img.alpha_composite(post_img, (x - 1, y + 1))
        elif what == "mush":
            img.alpha_composite(tile(MUSH), (x, y))
        elif what == "fence":
            img.alpha_composite(tile(arg), (x, y))
        elif what == "cart":
            _shadow(img, x + 8, y + 14, 6.5, 1.8)
            img.alpha_composite(tile(CART), (x, y))
        elif what == "hay":
            _shadow(img, x + 8, y + 14, 7.5, 2.0)
            img.alpha_composite(haystack(), (x, y + 6))
        else:
            img.alpha_composite(tile(SIGN), (x, y))
    return img

MINI_CELL = 3
_ZONE_TINT = {
    "Берег Лены": GRASS_MD, "Тукулан": blend(GRASS_MD, SAND, 0.2),
    "Кордон": GRASS_MD, "Тайга": blend(GRASS_MD, GRASS_DK, 0.35), "Засуха": CRACK,
    "Луга": blend(GRASS_MD, (255, 255, 255), 0.08), "Посёлок": GRASS_MD,
}

def minimap_base(world):
    
    W, H = world.W, world.H
    img = Image.new("RGBA", (W*MINI_CELL, H*MINI_CELL), (0, 0, 0, 0))
    px = img.load()
    house = set(world.house.keys()) | {cell for h in world.village for cell in h}
    trees = {(r, c): kind for (r, c, kind) in world.trees}
    boulders = {(r, c) for (r, c, _) in world.boulders}
    pillars = {(r, c) for (r, c, _) in world.pillars}
    cars = {(r, c + dc): CAR_BODIES[col % len(CAR_BODIES)] for (r, c, col) in world.parked_cars for dc in (0, 1)}
    for r in range(H):
        for c in range(W):
            cell = (r, c)
            if cell in world.water:
                col = RIV
            elif cell in house or cell in world.fence:
                col = WOOD_BASE
            elif cell in world.dune:
                col = SAND_BASE
            elif cell in trees:
                col = DEAD_WOOD if trees[cell] == "dead" else FOREST
            elif cell in boulders:
                col = STONE
            elif cell in pillars:
                col = LIME_LT
            elif cell in cars:
                col = cars[cell]
            elif cell in world.crossing:
                col = LINE
            elif cell in world.road or cell in world.parking:
                col = ASPH_LT
            elif cell in world.path:
                col = DIRT_BASE
            else:
                col = _ZONE_TINT.get(world.zone_at(r, c), GRASS_MD)
            for yy in range(MINI_CELL):
                for xx in range(MINI_CELL):
                    px[c*MINI_CELL+xx, r*MINI_CELL+yy] = col + (255,)
    return img
