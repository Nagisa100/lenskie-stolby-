"""
Трейлер игры: кадры рисует движок по раскадровке, к ним — процедурная музыка,
ffmpeg собирает MP4 1920x1080.

    python tools/trailer.py               # → trailer/trailer.mp4
    python tools/trailer.py --png 600     # черновик: каждый 30-й кадр в trailer/frames/
"""
import os, sys, math, random, array, shutil, subprocess, wave, glob
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOME)
os.chdir(HOME)
ARGS = sys.argv[1:]
sys.argv = [sys.argv[0], "--shot"]  # офскрин

import pygame
import main
import assets
import audio
import actors
from world import TILE
from species import SPECIES

FPS = 60
W, H = 960, 540  # кадр движка, в видео ×2
SCALE = main.SCALE
BAR = 60 / 128 * 4               # такт музыки, с
LETTERBOX = 66  # чёрные поля сверху и снизу
OUT_DIR = os.path.join(HOME, "trailer")
# сцены и их длина в тактах
SHOTS = (("title", 2), ("escape", 2), ("chase", 5), ("herd", 4), ("card", 3), ("end", 2.4))
CAPTIONS = {
    "escape": ((0.4, 3.5, "Якутские лошади сбежали с фермы…"),),
    "chase": ((0.3, 3.0, "…а туристы мусорят на экотропе"), (3.4, 6.2, "Рейнджер — в седле!"),
              (6.6, 9.2, "Ни фантика мимо!")),
    "herd": ((0.3, 5.0, "Беглецов — обратно в загон"),),
    "card": ((2.4, 5.5, "27 краснокнижных видов Ленских столбов"),),
}
PLAYER_SHIRT = (74, 122, 63)


def ffmpeg_path():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    found = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffmpeg.exe"))
    return found[0] if found else None


class Mover:
    """актёр сцены, идёт по точкам"""
    def __init__(self, x, y, speed):
        self.x, self.y, self.speed = x, y, speed
        self.path = []

    def go(self, *points):
        self.path = list(points)

    def step(self, dt):
        """шаг по маршруту; True — ещё идёт"""
        left = self.speed * dt
        while self.path and left > 0:
            tx, ty = self.path[0]
            d = math.hypot(tx - self.x, ty - self.y)
            if d <= left:
                self.x, self.y = tx, ty
                self.path.pop(0)
                left -= d
            else:
                self.x += (tx - self.x) / d * left
                self.y += (ty - self.y) / d * left
                left = 0
        return bool(self.path)


class Trailer:
    def __init__(self):
        g = self.g = main.Game()
        g.display.w, g.display.h = W, H
        g.display.frame = pygame.Surface((W, H)).convert()
        g._sync_display()
        g.state = "play"
        for name in ("_draw_icons", "_draw_zone_toast", "_draw_toast", "_draw_ride_hint"):
            setattr(g, name, lambda: None)  # без интерфейса
        self.cam = [0.0, 0.0]
        g.camera = lambda: (int(self.cam[0]), int(self.cam[1]))
        self.w = g.world
        for t in self.w.triggers:
            t.resolved = True  # без мусора на тропе
        g.npcs, g.horses, g.npc_litters = [], [], []
        g.near = None
        self.rnd = random.Random(7)
        self.events = []  # (время, звук)
        self.fx = []
        self.t = 0.0
        self.gate_closed = None
        self.f_title = pygame.font.Font(assets.FONT_PATH, 44)
        self.f_cap = pygame.font.Font(assets.FONT_PATH, 20)
        self.f_end = pygame.font.Font(assets.FONT_PATH, 56)
        self.f_tag = pygame.font.Font(assets.FONT_PATH, 22)
        self.gate_tile = main.scaled(main.pil_to_surf(assets.tile(assets.FENCE_H)))
        self.hold_trash = main.scaled(main.pil_to_surf(assets.trash_sprite(1)), 2)
        random.seed(5)

    def trail_y(self, x):
        """середина экотропы по высоте"""
        c = x / TILE - 0.5
        c0 = math.floor(c)
        f = c - c0
        m = self.w._middle(c0) * (1 - f) + self.w._middle(c0 + 1) * f
        return m * TILE + 12

    def follow(self, x, y, dt, lead=0.4, k=3.5, snap=False):
        """камера плавно догоняет точку; lead — где по горизонтали держать героя"""
        g = self.g
        tx = min(max(0, x * SCALE - W * lead), g.map_w - W)
        ty = min(max(0, y * SCALE - H * 0.56), g.map_h - H)
        a = 1.0 if snap else 1 - math.exp(-k * dt)
        self.cam[0] += (tx - self.cam[0]) * a
        self.cam[1] += (ty - self.cam[1]) * a

    def screen(self, x, y):
        return x * SCALE - self.cam[0], y * SCALE - self.cam[1]

    def sound(self, name, t=None):
        self.events.append((self.t if t is None else t, name))

    def ride(self, x, y, face, moving, dt):
        g = self.g
        g.riding = self.mount
        g.px, g.py, g.face, g.moving = x - 5, y - 12, face, moving
        if moving:
            g.walk_t += dt * 1.25
            self.hooves(x, y, dt)

    def hooves(self, x, y, dt, key="rider"):
        """стук копыт и пыль"""
        k = f"_hoof_{key}"
        t = getattr(self, k, 0.0) - dt
        if t <= 0:
            t = 0.26
            for d in (0.0, 0.07, 0.13):
                self.sound("hoof", self.t + d)
            sx, sy = self.screen(x, y)
            self.g._burst(sx, sy, 3, [assets.DIRT_LT, assets.DIRT_BASE, assets.SAND_LT], (30, 80), (0.25, 0.5), 300.0)
        setattr(self, k, t)

    def horse(self, variant, x, y):
        h = actors.Horse(self.w, variant, random.Random(variant))
        h.x, h.y, h.state, h.face = x, y, "stand", "right"
        return h

    def run_horse(self, h, mover, dt):
        """лошадь бежит по маршруту: кадры шага ускорены, тревога «!» над головой"""
        moving = mover.step(dt)
        if abs(mover.x - h.x) > 0.05:
            h.face = "right" if mover.x > h.x else "left"
        h.x, h.y = mover.x, mover.y
        if moving:
            h.state, h.route = "leave", [(0, 0)]
            h.walk_t += dt * 1.8
            self.hooves(h.x, h.y, dt, key=id(h))
        return moving

    def tourist(self, variant, x, mood="hurry"):
        n = main.NPC(0, 0, variant, mood)
        n.px, n.py = x - 5, self.trail_y(x) - 12
        n.face, n.moving, n.bubble = "left", False, ("intent", 99)
        n.scare = None
        return n

    def float_text(self, text, x, y, col):
        self.fx.append(dict(kind="text", text=text, x=x, y=y, col=col, t=0.0))

    def shot_title(self, t, dt, d, first):
        g = self.g
        if first:
            g.riding = None
            g.px, g.py = 5 * TILE, 31 * TILE
            self.cam = [560.0, 0.0]
        self.cam = [560 + 320 * (t / d), 0.0]

    def shot_escape(self, t, dt, d, first):
        g, w = self.g, self.w
        gx, gy = w.gate[1] * TILE + 8, w.gate[0] * TILE + 12
        if first:
            spots = ((29, 4), (30, 6), (29, 8))
            g.horses = [self.horse(i, c * TILE + 8, r * TILE + 12) for i, (r, c) in enumerate(spots)]
            self.esc = []
            for i, h in enumerate(g.horses):
                m = Mover(h.x, h.y, 78)
                ty = self.trail_y(gx)
                m.go((gx, gy + 18), (gx, gy), (gx, gy - 16), (gx + 10, ty), (gx + 420, self.trail_y(gx + 420) + (i - 1) * 6))
                self.esc.append(m)
            self.follow(gx + 40, gy - 30, dt, lead=0.45, snap=True)
            self.sound("alert", self.t + 0.25)
            self.sound("neigh", self.t + 0.35)
        lead = None
        for i, (h, m) in enumerate(zip(g.horses, self.esc)):
            if t > 0.3 + 0.32 * i:
                self.run_horse(h, m, dt)
                lead = lead or m
        if lead:
            self.follow(max(gx + 40, lead.x - 30), gy - 30 - min(1.0, t / d) * 40, dt, lead=0.45, k=2.0)

    def shot_chase(self, t, dt, d, first):
        g = self.g
        v = 58.0
        x = 4.5 * TILE + v * t
        y = self.trail_y(x)
        if first:
            self.mount = self.horse(1, 0, 0)
            g.walk_t = 0.0
            g.horses = [self.horse(i, (41.5 + 1.6 * i) * TILE, self.trail_y((41.5 + 1.6 * i) * TILE) + (i - 1) * 5)
                        for i in range(3)]
            for h in g.horses:
                h.state, h.timer, h.face = "graze", 3.0, "left"
            g.npcs = [self.tourist(i % 6, (13 + 9 * i) * TILE + 8, ("hurry", "stubborn", "friendly")[i])
                      for i in range(3)]
            self.follow(x, y, dt, snap=True)
            self.sound("neigh")
        self.ride(x, y, "right", True, dt)
        for h in g.horses:
            h.timer -= dt * 0.3
        for n in g.npcs:
            self.scare_tourist(n, x, y, dt)
        # в кадре всадник и ближайший турист
        ty = y
        ahead = [n for n in g.npcs if -30 < n.px + 5 - x < 150]
        if ahead:
            n = min(ahead, key=lambda n: n.px)
            w = max(0.0, min(1.0, (150 - (n.px + 5 - x)) / 90))
            ty = y + (min(n.py + 12, y) - y) * 0.55 * w
        self.follow(x, ty, dt, lead=0.38, snap=first)

    def scare_tourist(self, n, rx, ry, dt):
        """турист пугается, фантик летит рейнджеру"""
        tx = n.px + 5
        if n.scare is None and rx >= tx - 62:
            n.scare = 0.0
            n.base_py = n.py
            n.bubble = ("alarm", 1.4)
            n.face = "down"
            sx, sy = self.screen(tx + 6, n.py + 8)
            self.fx.append(dict(kind="trash", x=sx, y=sy, t=0.0, dur=0.42))
            self.sound("fright")
        if n.scare is not None:
            n.scare += dt
            p = min(1.0, n.scare / 0.45)
            n.py = n.base_py - 15 * p - 10 * math.sin(math.pi * p)
            if n.bubble and n.bubble[1] > 0:
                n.bubble = (n.bubble[0], n.bubble[1] - dt)
            else:
                n.bubble = None

    def shot_herd(self, t, dt, d, first):
        g, w = self.g, self.w
        gx, gy = w.gate[1] * TILE + 8, w.gate[0] * TILE + 12
        v = 74.0
        if first:
            g.npcs = []
            self.rider = Mover(34 * TILE, self.trail_y(34 * TILE), v)
            stop = 10 * TILE
            self.rider.go(*[(x, self.trail_y(x)) for x in range(int(self.rider.x) - 8, stop, -8)],
                          (gx + 30, gy - 22))
            spots = ((29, 4), (30, 6), (29, 8))
            self.herd = []
            g.horses = []
            for i in range(3):
                x0 = self.rider.x - 62 - 26 * i
                h = self.horse(i, x0, self.trail_y(x0) + (-4, 5, -2)[i])
                g.horses.append(h)
                m = Mover(h.x, h.y, v)
                pts = [(x, self.trail_y(x) + (-4, 5, -2)[i]) for x in range(int(x0) - 8, gx + 12, -8)]
                r, c = spots[i]
                m.go(*pts, (gx, self.trail_y(gx)), (gx, gy - 16), (gx, gy), (gx, gy + 20), (c * TILE + 8, r * TILE + 12))
                self.herd.append(m)
            self.follow(self.rider.x, self.rider.y, dt, lead=0.62, snap=True)
            self.sound("neigh", self.t + 0.2)
        moving = self.rider.step(dt)
        self.ride(self.rider.x, self.rider.y, "left", moving, dt)
        inside = 0
        for h, m in zip(g.horses, self.herd):
            if not self.run_horse(h, m, dt):
                h.state, h.route = "graze", []
                h.timer -= dt
                inside += 1
        if inside == len(g.horses) and self.gate_closed is None:
            self.gate_closed = self.t
            self.sound("gate")
            self.sound("ok", self.t + 0.05)
            self.sound("neigh", self.t + 0.3)
            sx, sy = self.screen(gx, gy - 6)
            g._burst(sx, sy, 22, [assets.UI_GREEN, assets.UI_AMBER, (255, 246, 210)], (60, 200), (0.5, 1.0))
            self.float_text("+3 SAVE · лошади дома", gx, gy - 30, assets.UI_GREEN)
        # в кадре всадник, табун и загон
        xs = [self.rider.x] + [h.x for h in g.horses]
        ys = [self.rider.y] + [h.y for h in g.horses]
        near = max(0.0, min(1.0, (gx + 140 - min(xs)) / 140))
        cy = (min(ys) + max(ys)) / 2 * (1 - 0.5 * near) + (gy - 4) * 0.5 * near
        self.follow((min(xs) + max(xs)) / 2, cy, dt, lead=0.5, k=2.5, snap=first)

    def shot_card(self, t, dt, d, first):
        g, w = self.g, self.w
        if first:
            hx, hy = self.rider.x, self.rider.y
            self.mount.x, self.mount.y, self.mount.state, self.mount.face = hx, hy, "stand", "left"
            g.horses = g.horses + [self.mount]
            g.riding = None
            self.walker = Mover(hx + 14, hy, 34)
            fr, fc = self.flower_cell(hx)
            self.walker.go((fc * TILE + 8, (fr + 1) * TILE + 12))
            self.flower = (fr, fc)
            self.card_open = False
            self.sound("hop")
            g.face = "right"
        moving = t > 0.45 and self.walker.step(dt)
        g.px, g.py = self.walker.x - 5, self.walker.y - 12
        g.moving = moving
        g.walk_t = g.walk_t + dt if moving else 0.0
        if t <= 0.45:  # спрыгнул с лошади
            p = t / 0.45
            g.py -= 9 * math.sin(math.pi * p)
        elif not moving:
            g.face = "up"
        if t > 1.9 and not self.card_open:
            self.card_open = True
            sp = next(s for s in SPECIES if s["name"] == "Лилия пенсильванская")
            g.species = {s["name"] for s in SPECIES[1:10]}
            g._collect(sp, main._PlantRef(self.flower, sp), main.XP["trigger"])
            g.card_t = 0.0
            self.sound("new")
        if g.card:
            g.card_t += dt
        self.follow(self.walker.x, self.walker.y - 10, dt, lead=0.5, k=3.0)

    def flower_cell(self, hx):
        """место для сардааны у тропы"""
        w = self.w
        tops = {(r - 1, c) for (r, c, k) in w.trees if k in ("tallg", "tallo")}
        c0 = int(hx // TILE)
        for c in range(c0 + 3, c0 + 9):
            for r in range(10, 30):
                cell = (r, c)
                if (cell not in w.path and (r + 1, c) in w.path and not w.solid(c, r)
                        and cell not in tops and not w.plant_at(cell)):
                    sp = next(s for s in SPECIES if s["name"] == "Лилия пенсильванская")
                    w.flowers.append((r, c, sp))
                    return cell
        raise RuntimeError("нет места для цветка у тропы")

    def shot_end(self, t, dt, d, first):
        pass

    def draw_fx(self, dt):
        g = self.g
        alive = []
        for f in self.fx:
            f["t"] += dt
            if f["kind"] == "trash":
                p = min(1.0, f["t"] / f["dur"])
                tx, ty = self.screen(g.px + 5, g.py + 2)
                x = f["x"] + (tx - f["x"]) * p
                y = f["y"] + (ty - f["y"]) * p - 70 * math.sin(math.pi * p)
                if p >= 1.0:                            # поймал на скаку
                    g._burst(tx, ty, 14, [assets.UI_AMBER, (255, 246, 210), assets.UI_GREEN], (60, 180), (0.35, 0.7), 160.0)
                    self.float_text("+1 SAVE", g.px + 5, g.py - 6, assets.UI_GREEN)
                    self.sound("catch")
                    continue
                img = pygame.transform.rotate(self.hold_trash, f["t"] * 720)
                g.screen.blit(img, (int(x - img.get_width() / 2), int(y - img.get_height() / 2)))
            else:
                if f["t"] > 1.1:
                    continue
                s = g.txt(g.f_md, f["text"], f["col"])
                s.set_alpha(int(255 * min(1.0, (1.1 - f["t"]) / 0.3)))
                x, y = self.screen(f["x"], f["y"])
                g.screen.blit(s, (int(x - s.get_width() / 2), int(y - 30 * f["t"])))
            alive.append(f)
        self.fx = alive
        for n in g.npcs:  # фантик в руке туриста
            if n.scare is None:
                x, y = self.screen(n.px, n.py)
                g.screen.blit(self.hold_trash, (int(x - 6), int(y + 18)))

    def draw_gate(self):
        if self.gate_closed is None:
            return
        g, w = self.g, self.w
        p = min(1.0, (self.t - self.gate_closed) / 0.22)
        x, y = self.screen(w.gate[1] * TILE, w.gate[0] * TILE)
        g.screen.blit(self.gate_tile, (int(x - (1 - p) * TILE * SCALE), int(y)))

    def draw_letterbox(self, name, t):
        g = self.g
        pygame.draw.rect(g.screen, (0, 0, 0), (0, 0, W, LETTERBOX))
        pygame.draw.rect(g.screen, (0, 0, 0), (0, H - LETTERBOX, W, LETTERBOX))
        for a, b, text in CAPTIONS.get(name, ()):
            if a <= t <= b:
                k = min(1.0, (t - a) / 0.25, (b - t) / 0.25)
                s = g.txt(self.f_cap, text, assets.UI_INK)
                s.set_alpha(int(255 * k))
                g.screen.blit(s, (W // 2 - s.get_width() // 2, H - LETTERBOX // 2 - s.get_height() // 2))

    def draw_title(self, t, d):
        g = self.g
        k = max(0.0, min(1.0, (t - 0.6) / 0.6, (d - t) / 0.4))
        if k <= 0:
            return
        band = pygame.Surface((W, 120), pygame.SRCALPHA)
        band.fill((8, 14, 10, int(150 * k)))
        g.screen.blit(band, (0, H // 2 - 70))
        title = g.txt(self.f_title, "ХРАНИТЕЛИ СТОЛБОВ", assets.UI_GREEN)
        title.set_alpha(int(255 * k))
        g.screen.blit(title, (W // 2 - title.get_width() // 2, H // 2 - 58))
        k2 = max(0.0, min(1.0, (t - 1.3) / 0.5, (d - t) / 0.4))
        sub = g.txt(g.f_sm, "природный парк «Ленские столбы» · Якутия", assets.UI_INK)
        sub.set_alpha(int(255 * k2))
        g.screen.blit(sub, (W // 2 - sub.get_width() // 2, H // 2 + 6))

    def draw_end(self, t, d):
        g = self.g
        g._menu_backdrop(dim=215)
        title = g.txt(self.f_end, "ХРАНИТЕЛИ СТОЛБОВ", assets.UI_GREEN)
        g.screen.blit(title, (W // 2 - title.get_width() // 2, 70))
        lines = ((self.f_tag, "27 краснокнижных видов · туристы · сбежавшие лошади", assets.UI_INK),
                 (g.f_md, "Береги Ленские столбы", assets.UI_FAINT))
        for i, (font, s, col) in enumerate(lines):
            surf = g.txt(font, s, col)
            g.screen.blit(surf, (W // 2 - surf.get_width() // 2, 150 + i * 36))
        names = ("Лилия пенсильванская", "Башмачок настоящий", "Адонис сибирский", "Гериций коралловидный",
                 "Живокость крупноцветковая", "Кувшинка четырёхгранная", "Хвойник односемянный")
        icons = [pygame.transform.scale_by(g.flower_surf[n][0], 2) for n in names]
        gap = 18
        total = sum(i.get_width() for i in icons) + gap * (len(icons) - 1)
        x = W // 2 - total // 2
        for k, img in enumerate(icons):
            bob = int(4 * math.sin(self.t * 3 + k))
            g.screen.blit(img, (x, 360 - img.get_height() + bob))
            x += img.get_width() + gap
        g.screen.blit(g.portrait, (W // 2 - g.portrait.get_width() // 2, 390))

    def fade(self, t, d, first_shot, last_shot):
        """затемнение на стыках сцен"""
        tin = 0.8 if first_shot else 0.15
        tout = 1.0 if last_shot else 0.15
        k = min(1.0, t / tin, (d - t) / tout)
        if k < 1.0:
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, int(255 * (1 - max(0.0, k)))))
            self.g.screen.blit(ov, (0, 0))

    def frames(self, limit=None):
        """генератор кадров: (номер, поверхность)"""
        g = self.g
        dt = 1 / FPS
        n = 0
        for si, (name, bars) in enumerate(SHOTS):
            d = bars * BAR
            steps = int(round(d * FPS))
            for k in range(steps):
                t = k * dt
                g.t = self.t
                getattr(self, "shot_" + name)(t, dt, d, k == 0)
                g._update_particles(dt)
                for car in g.cars:
                    car.update(dt, (-999, -999, 1, 1), g.cars, g.bw)
                if name == "end":
                    self.draw_end(t, d)
                else:
                    g.draw()
                    self.draw_gate()
                    self.draw_fx(dt)
                    if name == "title":
                        self.draw_title(t, d)
                    self.draw_letterbox(name, t)
                self.fade(t, d, si == 0, si == len(SHOTS) - 1)
                yield n, g.screen
                n += 1
                self.t += dt
                if limit and n >= limit:
                    return

    def soundtrack(self, total):
        rate = audio.RATE
        buf = music(total, rate)
        g = self.g
        sfx = {"neigh": (g.snd_neigh, 0.55), "alert": (g.snd_alert, 0.35), "catch": (g.snd_litter, 0.7),
               "ok": (g.snd_ok, 0.6), "new": (g.snd_new, 0.7), "gate": (g.snd_click, 0.8),
               "fright": (g.snd_fail, 0.25), "hop": (g.snd_page, 0.5)}
        raw = {k: samples(s) for k, (s, _) in sfx.items() if s}
        hooves = [samples(s) for s in g.step_sounds.get("path", ())]
        rnd = random.Random(3)
        for t, name in self.events:
            if name == "hoof":
                src, vol = (rnd.choice(hooves) if hooves else []), 0.35
            elif name in raw:
                src, vol = raw[name], sfx[name][1]
            else:
                continue
            i0 = int(t * rate)
            for i, s in enumerate(src):
                if 0 <= i0 + i < len(buf):
                    buf[i0 + i] += s * vol
        peak = max(1e-6, max(abs(x) for x in buf))
        k = 0.9 / peak
        return array.array("h", (int(max(-32767, min(32767, x * k * 32767))) for x in buf))


def samples(snd):
    """звук игры → список float"""
    data = array.array("h", snd.get_raw())
    if audio.CHANNELS > 1:
        data = data[::audio.CHANNELS]
    return [x / 32768 for x in data]


def music(total, rate):
    """музыка трейлера: ля минор, 128 BPM, части по сценам"""
    n = int(total * rate) + rate
    buf = [0.0] * n
    beat = BAR / 4
    rnd = random.Random(11)

    def hz(m):
        return 440.0 * 2 ** ((m - 69) / 12)

    def note(t0, dur, m, vol, wave_="sq", decay=3.0, duty=0.5):
        f = hz(m)
        i0, cnt = int(t0 * rate), int(dur * rate)
        for i in range(cnt):
            if i0 + i >= n:
                break
            t = i / rate
            ph = (f * t) % 1.0
            if wave_ == "sq":
                s = 1.0 if ph < duty else -1.0
            else:
                s = 2 * abs(2 * ph - 1) - 1
            env = min(1.0, t / 0.006) * math.exp(-decay * t) * min(1.0, (dur - t) / 0.02)
            buf[i0 + i] += s * env * vol

    def kick(t0, vol=0.9):
        i0 = int(t0 * rate)
        ph = 0.0
        for i in range(int(0.18 * rate)):
            t = i / rate
            ph += (45 + 110 * math.exp(-t * 30)) / rate
            if i0 + i < n:
                buf[i0 + i] += math.sin(2 * math.pi * ph) * math.exp(-t * 16) * vol

    def noise(t0, dur, vol, decay, hp=False):
        i0 = int(t0 * rate)
        prev = 0.0
        for i in range(int(dur * rate)):
            t = i / rate
            x = rnd.uniform(-1, 1)
            s = x - prev if hp else x
            prev = x
            if i0 + i < n:
                buf[i0 + i] += s * math.exp(-t * decay) * vol

    chords = ((57, 60, 64), (53, 57, 60), (55, 60, 64), (55, 59, 62))       # Am F C G
    roots = (45, 41, 48, 43)
    melody = (((0, 1, 69), (1, .5, 72), (1.5, .5, 76), (2, 1, 74), (3, 1, 72)),
              ((0, 1.5, 69), (1.5, .5, 65), (2, 1, 69), (3, 1, 72)),
              ((0, 1, 67), (1, .5, 72), (1.5, .5, 76), (2, 1, 79), (3, 1, 76)),
              ((0, 1.5, 74), (1.5, .5, 71), (2, 1, 74), (3, 1, 67)))
    starts, t = {}, 0.0
    for name, bars in SHOTS:
        starts[name] = (t, bars)
        t += bars * BAR
    bar_i = 0
    for name, (t0, bars) in starts.items():
        for b in range(int(math.ceil(bars))):
            tb = t0 + b * BAR
            if tb >= total - 0.01:
                break
            ci = bar_i % 4
            ch, root = chords[ci], roots[ci]
            bar_i += 1
            if name in ("title", "card"):  # пэд и арпеджио
                for m in ch:
                    note(tb, BAR, m, 0.07, "tri", decay=0.6)
                for k in range(8):
                    note(tb + k * beat / 2, beat / 2, ch[k % 3] + (12 if name == "title" else 24), 0.05, "tri", decay=5)
                note(tb, BAR, root, 0.12, "tri", decay=0.8)
                continue
            if name == "end":
                if b == 0:                                # финальный аккорд и тарелка
                    for m in (45, 57, 60, 64, 69):
                        note(tb, 3.6, m, 0.09, "tri", decay=0.7)
                    note(tb, 2.5, 76, 0.06, "sq", decay=1.2, duty=0.25)
                    kick(tb, 1.0)
                    noise(tb, 1.6, 0.25, 2.5, hp=True)
                continue
            full = name in ("chase", "herd")
            for k in range(4):
                if full or k % 2 == 0 or b == bars - 1:
                    kick(tb + k * beat, 0.8)
                if full and k in (1, 3):
                    noise(tb + k * beat, 0.18, 0.35, 18)
                if full:
                    for h in (0, 0.5):
                        noise(tb + (k + h) * beat, 0.05, 0.12, 70, hp=True)
            if name == "escape" and b == bars - 1:          # дробь перед погоней
                for k in range(8):
                    noise(tb + 2 * beat + k * beat / 4, 0.08, 0.15 + 0.03 * k, 20)
            for k in range(8):  # бас восьмыми
                note(tb + k * beat / 2, beat / 2, root + (12 if k % 2 else 0), 0.16, "sq", decay=6, duty=0.5)
            if full:
                up = 12 if name == "herd" and b < 2 else 0
                for (o, ln, m) in melody[ci]:
                    note(tb + o * beat, ln * beat * 0.95, m + up, 0.11, "sq", decay=1.5, duty=0.25)
            else:
                for m in ch:
                    note(tb, BAR, m, 0.05, "tri", decay=0.8)
    return buf


def main_trailer():
    sys.stdout.reconfigure(encoding="utf-8")
    tr = Trailer()
    total = sum(b * BAR for _, b in SHOTS)
    os.makedirs(OUT_DIR, exist_ok=True)
    if "--png" in ARGS:
        limit = int(ARGS[ARGS.index("--png") + 1])
        os.makedirs(os.path.join(OUT_DIR, "frames"), exist_ok=True)
        for n, surf in tr.frames(limit):
            if n % 30 == 0:
                pygame.image.save(surf, os.path.join(OUT_DIR, "frames", f"{n:05d}.png"))
        print("кадры —", os.path.join(OUT_DIR, "frames"))
        return
    ff = ffmpeg_path()
    if not ff:
        sys.exit("нужен ffmpeg (winget install Gyan.FFmpeg)")
    video = os.path.join(OUT_DIR, "_video.mp4")
    cmd = [ff, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-vf", f"scale={W*2}:{H*2}:flags=neighbor", "-c:v", "libx264", "-preset", "medium",
           "-crf", "16", "-pix_fmt", "yuv420p", video]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n, surf in tr.frames():
        proc.stdin.write(pygame.image.tobytes(surf, "RGB"))
        if n % 300 == 0:
            print(f"кадр {n} / {int(total * FPS)}")
    proc.stdin.close()
    proc.wait()
    wav = os.path.join(OUT_DIR, "_audio.wav")
    pcm = tr.soundtrack(total)
    with wave.open(wav, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(audio.RATE)
        f.writeframes(pcm.tobytes())
    out = os.path.join(OUT_DIR, "trailer.mp4")
    subprocess.run([ff, "-v", "error", "-y", "-i", video, "-i", wav, "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-ar", "48000", "-shortest", out], check=True)
    os.remove(video)
    os.remove(wav)
    print("готово:", out)


if __name__ == "__main__":
    main_trailer()
