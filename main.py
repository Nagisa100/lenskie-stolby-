import os, sys, math, random

SHOT = None
if "--shot" in sys.argv:
    i = sys.argv.index("--shot")
    SHOT = sys.argv[i+1] if i+1 < len(sys.argv) else "preview/game_shot.png"
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import assets
import audio
import actors
import plants_art
import tourists
from display import Display, dpi_aware
from world import World, TILE, CAR_COLORS
from species import SPECIES, KIND_ORDER, KINDS, kind_info, zones
from tourists import NPC, NpcLitter, NPC_LITTER_LIFETIME
from encyclopedia import Encyclopedia

SCALE = 3
WIN_W, WIN_H = 720, 540
MENU_BUTTONS_Y = 268  # кнопки меню под логотипом
FPS = 60
WALK_SEQ, WALK_DT = (1, 0, 2, 0), 0.12
RIDE_DT = 0.1
SWAY_SEQ, SWAY_DT = (0, 1, 0, 2), 0.42
WATER_DT = 0.32

# наряды и характеры туристов
NPC_VARIANTS = [
    dict(hair=(90, 62, 40), shirt=(214, 128, 58), shirt_dark=(165, 92, 40)),
    dict(hair=(226, 198, 140), shirt=(78, 118, 178), shirt_dark=(54, 86, 132)),
    dict(hair=(40, 34, 30), shirt=(196, 64, 70), shirt_dark=(146, 44, 52)),
    dict(hair=(150, 150, 150), shirt=(128, 96, 170), shirt_dark=(94, 68, 130)),
    dict(hair=(120, 70, 36), shirt=(222, 190, 74), shirt_dark=(176, 146, 50)),
    dict(hair=(70, 50, 40), shirt=(70, 150, 140), shirt_dark=(48, 110, 100)),
]
NPC_MOODS = ("friendly", "hurry", "stubborn", "friendly", "stubborn", "hurry")
NPC_COUNT = 6
NPC_SOUTH = 1  # сколько туристов за дорогой
HORSES = 4
MAX_NPC_LITTER = 3
NPC_LITTER_WARN = 8.0

# события: туристы нарушают по одному, лошади сбегают 1–3 раза за игру
EVENT_FIRST, EVENT_GAP = (8.0, 12.0), (10.0, 16.0)
INTENT_KINDS = (("pick", 0.45), ("litter", 0.40), ("offroad", 0.15))
ESCAPE_FIRST, ESCAPE_GAP, MAX_ESCAPES = (40.0, 70.0), (90.0, 150.0), 3
HORSE_GIVE_UP = 120.0  # через столько секунд лошадь уводит фермер
WALK_SPEED, RIDE_SPEED = 1.4, 2.3
NEAR_DC, NEAR_DR = 1.6, 1.8  # радиус E в клетках
FLASH_TIME = 2.0
DIALOG_AUTOCLOSE = 2.6
GAME_SEED = 2024  # сид уговоров для тестов
THREAT_COL = (236, 96, 200)
HORSE_COL = (214, 150, 72)

# карточка вида
CARD_W, CARD_H = 540, 300
CARD_MAX_H = 440
CARD_PAD = 16
CARD_HEAD_H = 34
CARD_FOOT_H = 30
CARD_GAP = 8
CARD_PORTRAIT_W = 150
CARD_CAPTION_H = 22
CARD_ART_SCALE = 5
CARD_TX = CARD_PAD * 2 + CARD_PORTRAIT_W

# очки опыта
XP = dict(trigger=10, new_bonus=5, litter=5, persuade=8, horse=20)
STAT_PER_ROW, STAT_CELL = 9, 36  # сетка коллекции в статистике


def pil_to_surf(im):
    return pygame.image.frombytes(im.tobytes(), im.size, "RGBA").convert_alpha()


def scaled(surf, s=SCALE):
    return pygame.transform.scale(surf, (surf.get_width()*s, surf.get_height()*s))


class Game:
    def __init__(self):
        dpi_aware()
        pygame.mixer.pre_init(audio.RATE, -16, 1, 512)
        pygame.init()
        self._init_audio()
        pygame.display.set_caption("Хранители столбов")
        self._set_window_icon()
        self.fullscreen = False
        self.display = Display(WIN_W, WIN_H, offscreen=bool(SHOT))
        self.screen = self.display.frame
        self._sync_display()
        self.clock = pygame.time.Clock()
        self.world = World()
        if not SHOT:
            random.seed()  # события каждый раз свои
        self._load()
        pc, pr = self.world.player_start
        self.px = pc*TILE + 3
        self.py = pr*TILE + 2
        self.face = "down"
        self.moving = False
        self.walk_t = 0.0
        self._step_idx = -1
        self.t = 0.0
        self.saved = 0
        self.lost = 0
        self.xp = 0
        self.species = set()
        self.found = []
        self.card = None
        self.card_t = 0.0
        self.card_new = False
        self.card_bg = None
        self.card_flower = None
        self.particles = []
        self._twinkle_t = 0.0
        self.near = None
        self.state = "menu"
        self.started = False
        self.menu_sel = 0
        self.show_map = False
        self.show_stats = False
        self.stat_icon_rects = {}  # иконки коллекции с прошлого кадра: имя → rect
        self.stat_hover = None
        self._hand = False         # курсор-рука
        self.book = Encyclopedia(self)
        self.toast = None
        self.zone_toast = None
        self._last_zone = None
        self.task = "Патрулируй экотропу, убирай нарушения"
        self.rng = random.Random(GAME_SEED if SHOT else None)
        self.key_override = None  # клавиши для smoke-теста
        self.dialog = None
        self._dialog_rects = []
        self.pending_card = None  # карточка после диалога
        self.event_t = random.uniform(*EVENT_FIRST)
        self.escape_t = random.uniform(*ESCAPE_FIRST)
        self.escapes = 0
        self.horses_home = 0
        self.riding = None
        self.trampled = []
        self.flashes = []
        self._dust_t = 0.0

    def _init_audio(self):
        self.sound_on = True
        self.vol_music = 0.3     # громкость фоновой музыки (0..1)
        self.vol_sfx = 1.0       # общий множитель громкости эффектов (0..1)
        self._drag_key = None    # какой ползунок тянут мышью
        self.step_sounds = {}
        self.snd_card = self.snd_new = self.snd_litter = self.snd_click = None
        self.snd_lost = self.snd_page = self.snd_horn = None
        self.snd_talk = self.snd_ok = self.snd_fail = None
        self.snd_neigh = self.snd_trample = self.snd_alert = None
        self.snd_music = None
        self.music_chan = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=audio.RATE, size=-16, channels=1, buffer=512)
            if not audio.setup():
                raise pygame.error("unsupported mixer format")
            pygame.mixer.set_reserved(1)           # канал 0 — только под фоновую музыку
            self.music_chan = pygame.mixer.Channel(0)
            self.step_sounds = {k: [audio.footstep(seed=i, kind=k) for i in range(3)] for k in audio.STEP_KINDS}
            self.snd_card = audio.chime()
            self.snd_new = audio.jingle()
            self.snd_litter = audio.crinkle()
            self.snd_click = audio.click()
            self.snd_lost = audio.lost()
            self.snd_page = audio.page()
            self.snd_horn = audio.horn()
            self.snd_talk = audio.talk()
            self.snd_ok = audio.success()
            self.snd_fail = audio.fail()
            self.snd_neigh = audio.neigh()
            self.snd_trample = audio.trample()
            self.snd_alert = audio.alert()
            self.snd_music = audio.ambient()
            self._apply_volumes()
            self._start_music()
        except Exception:
            self.sound_on = False

    # базовые громкости эффектов — микшер множит их на ползунок «Эффекты»
    _SFX_BASE = (
        ("snd_card", 0.55), ("snd_new", 0.5), ("snd_litter", 0.45),
        ("snd_click", 0.3), ("snd_lost", 0.45), ("snd_page", 0.3), ("snd_horn", 0.3),
        ("snd_talk", 0.3), ("snd_ok", 0.45), ("snd_fail", 0.35),
        ("snd_neigh", 0.4), ("snd_trample", 0.5), ("snd_alert", 0.3),
    )
    _STEP_BASE = (("path", 0.35), ("grass", 0.3), ("sand", 0.3))

    def _apply_volumes(self):
        
        if not pygame.mixer.get_init():
            return
        if self.music_chan is not None:
            self.music_chan.set_volume(self.vol_music)
        for attr, base in self._SFX_BASE:
            snd = getattr(self, attr, None)
            if snd:
                snd.set_volume(base * self.vol_sfx)
        for kind, base in self._STEP_BASE:
            for s in self.step_sounds.get(kind, ()):
                s.set_volume(base * self.vol_sfx)

    def _play(self, snd):
        if self.sound_on and snd:
            snd.play()

    def _start_music(self):
        
        if self.sound_on and self.snd_music and self.music_chan is not None:
            if not self.music_chan.get_busy():
                self.music_chan.play(self.snd_music, loops=-1)
                self.music_chan.set_volume(self.vol_music)

    def _set_window_icon(self):
        
        try:
            im = assets.logo().resize((64, 64), assets.Image.LANCZOS)
            pygame.display.set_icon(pygame.image.frombytes(im.tobytes(), im.size, "RGBA"))
        except Exception:
            pass

    def _apply_display(self):
        self.display.set_fullscreen(self.fullscreen)
        self._sync_display()

    def _sync_display(self):
        
        global WIN_W, WIN_H
        self.display.sync()
        if (WIN_W, WIN_H) == (self.display.w, self.display.h) and self.screen is self.display.frame:
            return
        WIN_W, WIN_H = self.display.w, self.display.h
        self.screen = self.display.frame
        if hasattr(self, "map_surf"):
            self.menu_bg = self._menu_bg()

    def _menu_bg(self):
        
        k = max(WIN_W / self.map_w, WIN_H / self.map_h)
        w, h = math.ceil(self.map_w * k), math.ceil(self.map_h * k)
        bg = pygame.transform.smoothscale(self.map_surf, (w, h))
        return bg.subsurface(((w - WIN_W) // 2, (h - WIN_H) // 2, WIN_W, WIN_H)).copy()

    def _load(self):
        base = assets.build_map(self.world)
        self.bw, self.bh = base.size
        self.map_surf = scaled(pil_to_surf(base))
        self.map_w, self.map_h = self.map_surf.get_size()
        ps = assets.player_sprites()
        self.player_surf = {k: [scaled(pil_to_surf(f)) for f in v] for k, v in ps.items()}
        self.npc_surf, self.npc_portrait = [], []
        for v in NPC_VARIANTS:
            ns = assets.player_sprites(assets.player_palette(**v))
            self.npc_surf.append({k: [scaled(pil_to_surf(f)) for f in fr] for k, fr in ns.items()})
            self.npc_portrait.append(scaled(pil_to_surf(ns["down"][0]), 6))
        self.litter_surf = scaled(pil_to_surf(assets.litter_sprite()))
        self.trash_surf = [scaled(pil_to_surf(assets.trash_sprite(i))) for i in range(len(assets.TRASH))]
        self.icon_map = scaled(pil_to_surf(assets.icon_map()))
        self.icon_stats = scaled(pil_to_surf(assets.icon_stats()))
        self.portrait = scaled(pil_to_surf(assets.portrait()), 4)
        self.logo = pil_to_surf(assets.logo())
        self.trampled_surf = scaled(pil_to_surf(assets.trampled()))
        self.bubble_surf = {k: scaled(pil_to_surf(assets.bubble(k))) for k in assets.BUBBLE_ICONS}
        # спрайты видов: 3 кадра покачивания и иконки коллекции
        self.flower_surf, self.plant_icon = {}, {}
        for sp in SPECIES:
            self.flower_surf[sp["name"]] = [scaled(pil_to_surf(plants_art.plant_sprite(sp, sway=s)))
                                            for s in (0, -1, 1)]
            self.plant_icon[sp["name"]] = (scaled(pil_to_surf(plants_art.plant_sprite(sp)), 2),
                                           scaled(pil_to_surf(plants_art.plant_sprite(sp, grey=True)), 2))
        self.water_surf = [[scaled(pil_to_surf(im)) for im in row] for row in assets.water_shimmer()]
        self.minimap_surf = pil_to_surf(assets.minimap_base(self.world))
        self.menu_bg = self._menu_bg()
        self.f_big = pygame.font.Font(assets.FONT_PATH, 28)
        self.f_md = pygame.font.Font(assets.FONT_PATH, 18)
        self.f_sm = pygame.font.Font(assets.FONT_PATH, 15)
        self.f_xs = pygame.font.Font(assets.FONT_PATH, 13)
        self.f_key = pygame.font.Font(assets.FONT_PATH, 16)
        self.f_it = pygame.font.Font(assets.FONT_PATH, 15)
        self.f_it.italic = True  # латынь курсивом
        # часть туристов гуляет за дорогой
        park = sorted(p for p in self.world.path if p[0] < self.world.PH)
        south = sorted(p for p in self.world.path if p[0] >= self.world.PH)
        cells = random.sample(park, NPC_COUNT - NPC_SOUTH) + random.sample(south, NPC_SOUTH)
        self.npcs = [NPC(c, r, i % len(NPC_VARIANTS), NPC_MOODS[i % len(NPC_MOODS)])
                     for i, (r, c) in enumerate(cells)]
        self.npc_litters = []
        self.horse_surf = [{k: [scaled(pil_to_surf(f)) for f in v] for k, v in assets.horse_sprites(i).items()}
                           for i in range(len(assets.HORSE_COATS))]
        self.rider_surf = [{k: [scaled(pil_to_surf(f)) for f in v] for k, v in assets.rider_sprites(i).items()}
                           for i in range(len(assets.HORSE_COATS))]
        self.car_surf = [{k: [scaled(pil_to_surf(f)) for f in v] for k, v in assets.car_sprites(i).items()}
                         for i in range(CAR_COLORS)]
        life_rnd = random.Random(21)
        self.horses = [actors.Horse(self.world, i % len(assets.HORSE_COATS), life_rnd) for i in range(HORSES)]
        lanes = sorted({r for (r, c) in self.world.road})
        self.cars = []
        if len(lanes) >= 2:
            self.cars = [actors.Car(lanes[0], -1, self.bw * 0.75, 2, 58.0),
                         actors.Car(lanes[1], 1, self.bw * 0.10, 0, 70.0),
                         actors.Car(lanes[1], 1, self.bw * 0.55, 3, 70.0)]

    def txt(self, font, s, col, aa=False):
        return font.render(s, aa, col)

    def _feet(self, x, y):
        return int(x)+1, int(y)+8, 8, 5

    def _car_hit(self, x, y):
        """машины твёрдые, но если игрок уже внутри (машина въехала с края) — выпускаем"""
        def overlap(a, b):
            return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
        new, now = self._feet(x, y), self._feet(self.px, self.py)
        return any(overlap(new, car.rect()) and not overlap(now, car.rect()) for car in getattr(self, "cars", ()))

    def _collide(self, x, y):
        bx, by, bw, bh = self._feet(x, y)
        for cx in range(bx // TILE, (bx+bw-1)//TILE + 1):
            for cy in range(by // TILE, (by+bh-1)//TILE + 1):
                if self.world.solid(cx, cy):
                    return True
        return self._car_hit(x, y)

    def _player_cell(self):
        return int(self.py + 10) // TILE, int(self.px + 5) // TILE

    def _menu_buttons(self):
        cx = WIN_W // 2
        items = [("Продолжить" if self.started else "Играть", "play"), ("Энциклопедия", "book"),
                 ("Настройки", "settings"), ("Выход", "quit")]
        rects = []
        y = MENU_BUTTONS_Y
        for label, action in items:
            rects.append((pygame.Rect(cx-110, y, 220, 46), label, action))
            y += 58
        return rects

    def _settings_items(self):
        cx = WIN_W // 2
        rows = [
            ("slider", "Музыка", "vol_music"),
            ("slider", "Эффекты", "vol_sfx"),
            ("button", f"Звук: {'Вкл' if self.sound_on else 'Выкл'}", "toggle_sound"),
            ("button", f"Полный экран: {'Вкл' if self.fullscreen else 'Выкл'}", "toggle_fullscreen"),
            ("button", "Назад", "back"),
        ]
        items = []
        y = 196
        for kind, label, key in rows:
            items.append({"kind": kind, "label": label, "key": key,
                          "rect": pygame.Rect(cx-170, y, 340, 46)})
            y += 58
        return items

    def _slider_track(self, rect):
        
        return pygame.Rect(rect.x + 112, rect.centery - 4, rect.width - 172, 8)

    def _slider_set_from_x(self, row, mx):
        track = self._slider_track(row["rect"])
        v = (mx - track.x) / max(1, track.width)
        self._set_vol(row["key"], v)

    def _set_vol(self, key, v):
        setattr(self, key, max(0.0, min(1.0, round(v, 2))))
        self._apply_volumes()

    def _activate(self, action):
        self._play(self.snd_click)
        if action == "play":
            self.state = "play"
            self.started = True
        elif action == "book":
            self._open_book()
        elif action == "settings":
            self.state = "settings"; self.menu_sel = 0
        elif action == "quit":
            self.state = "quit"
        elif action == "toggle_sound":
            self.sound_on = not self.sound_on and self.snd_click is not None
            if self.sound_on:
                self._start_music()
            elif pygame.mixer.get_init():
                pygame.mixer.stop()
            self._play(self.snd_click)
        elif action == "toggle_fullscreen":
            self.fullscreen = not self.fullscreen
            self._apply_display()
        elif action == "back":
            self.state = "menu"; self.menu_sel = 0

    def _on_key(self, key):
        if key == pygame.K_F11:
            self.fullscreen = not self.fullscreen
            self._apply_display()
            return
        if self.state == "menu":
            items = self._menu_buttons()
            if key in (pygame.K_UP, pygame.K_w):
                self.menu_sel = (self.menu_sel - 1) % len(items)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.menu_sel = (self.menu_sel + 1) % len(items)
            elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                self._activate(items[self.menu_sel][2])
            elif key == pygame.K_b:
                self._open_book()
        elif self.state == "book":
            if self.book.on_key(key):
                self._close_book()
        elif self.state == "settings":
            items = self._settings_items()
            self.menu_sel %= len(items)
            row = items[self.menu_sel]
            if key in (pygame.K_UP, pygame.K_w):
                self.menu_sel = (self.menu_sel - 1) % len(items)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.menu_sel = (self.menu_sel + 1) % len(items)
            elif key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d) and row["kind"] == "slider":
                step = 0.05 if key in (pygame.K_RIGHT, pygame.K_d) else -0.05
                self._set_vol(row["key"], getattr(self, row["key"]) + step)
                self._play(self.snd_click)
            elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e) and row["kind"] == "button":
                self._activate(row["key"])
            elif key == pygame.K_ESCAPE:
                self._activate("back")
        elif self.state == "play":
            if self.dialog and not self.card:
                self._dialog_key(key)
                return
            if key == pygame.K_b:  # с карточки вида — сразу на его страницу
                name = self.card.plant["name"] if self.card else None
                self._close_card(force=True)
                self._open_book(name)
            elif key == pygame.K_ESCAPE:
                if self.card:
                    self._close_card(force=True)
                elif self.show_map:
                    self._toggle_map()
                elif self.show_stats:
                    self._toggle_stats()
                else:
                    self.state = "menu"; self.menu_sel = 0
            elif key in (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE):
                self.act()
            elif key == pygame.K_m:
                self._toggle_map()
            elif key == pygame.K_TAB:
                self._toggle_stats()

    def _toggle_map(self):
        self.show_map = not self.show_map
        self._play(self.snd_page)

    def _toggle_stats(self):
        self.show_stats = not self.show_stats
        self.stat_hover = None
        self._set_hand(False)
        self._play(self.snd_page)

    def _open_book(self, name=None):
        
        self.book.open(self.state, name)
        self.state = "book"
        self.stat_hover = None
        self._set_hand(False)
        self._play(self.snd_page)

    def _close_book(self):
        
        self.state = self.book.origin
        self._set_hand(False)
        self._play(self.snd_page)

    def _set_hand(self, on):
        if on == self._hand:
            return
        self._hand = on
        try:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if on else pygame.SYSTEM_CURSOR_ARROW)
        except pygame.error:  # без окна (smoke-тест) курсора нет
            pass

    def _stat_icon_at(self, pos):
        
        if not self.show_stats or self.card or self.dialog:
            return None
        for name, rect in self.stat_icon_rects.items():
            if rect.collidepoint(pos) and name in self.species:
                return name
        return None

    def _on_click(self, pos):
        pos = self.display.to_logical(pos)
        if self.state == "book":
            if self.book.on_click(pos):
                self._close_book()
            return
        if self.state == "play" and self.card:
            self._close_card()
            return
        if self.state == "play" and self.dialog:
            if self.dialog["result"]:
                self._close_dialog()
                return
            for i, rect in enumerate(self._dialog_rects):
                if rect.collidepoint(pos):
                    self.dialog["sel"] = i
                    self._dialog_choose(i)
                    return
            return
        if self.state == "menu":
            for i, (rect, label, action) in enumerate(self._menu_buttons()):
                if rect.collidepoint(pos):
                    self.menu_sel = i; self._activate(action); return
        elif self.state == "settings":
            for i, row in enumerate(self._settings_items()):
                if row["rect"].collidepoint(pos):
                    self.menu_sel = i
                    if row["kind"] == "slider":
                        self._drag_key = row["key"]
                        self._slider_set_from_x(row, pos[0])
                    else:
                        self._activate(row["key"])
                    return
        elif self.state == "play":
            if getattr(self, "map_icon_rect", None) and self.map_icon_rect.collidepoint(pos):
                self._toggle_map()
            elif getattr(self, "stats_icon_rect", None) and self.stats_icon_rect.collidepoint(pos):
                self._toggle_stats()
            else:
                name = self._stat_icon_at(pos)
                if name:
                    self._open_book(name)

    def _on_hover(self, pos):
        pos = self.display.to_logical(pos)
        if self.state == "book":
            self._set_hand(self.book.on_hover(pos))
            return
        if self.state == "play":
            self.stat_hover = self._stat_icon_at(pos)
            self._set_hand(self.stat_hover is not None)
            return
        self._set_hand(False)
        if self.state == "settings":
            if self._drag_key:                       # тянем ползунок — обновляем на лету
                for row in self._settings_items():
                    if row["key"] == self._drag_key:
                        self._slider_set_from_x(row, pos[0])
                        return
            for i, row in enumerate(self._settings_items()):
                if row["rect"].collidepoint(pos):
                    self.menu_sel = i
                    return
            return
        for i, (rect, label, action) in enumerate(self._menu_buttons()):
            if rect.collidepoint(pos):
                self.menu_sel = i
                return

    def _find_near(self):
        
        if self.riding:
            return "gate" if self._at_gate() else None
        pcx, pcy = (self.px+5)/TILE, (self.py+10)/TILE
        spots = [(t, t.c + 0.5, t.r + 0.5) for t in self.world.triggers if not t.resolved]
        spots += [(nl, nl.c + 0.5, nl.r + 0.5) for nl in self.npc_litters if not nl.resolved]
        spots += [(n, (n.px + 5) / TILE, (n.py + 10) / TILE) for n in self.npcs if n.intent]
        spots += [(h, h.x / TILE, h.y / TILE - 0.3) for h in self.horses if h.escaped and h.state != "ridden"]
        best, best_d = None, 1e9
        for obj, x, y in spots:
            dc, dr = abs(pcx - x), abs(pcy - y)
            if dc < NEAR_DC and dr < NEAR_DR and dc + dr < best_d:
                best, best_d = obj, dc + dr
        return best

    def _at_gate(self):
        r, c = self._player_cell()
        gr, gc = self.world.gate_out
        return max(abs(r - gr), abs(c - gc)) <= 1 or (r, c) == self.world.gate or (r, c) in self.world.pen

    def _spawn_npc_litter(self, npc):
        if len([l for l in self.npc_litters if not l.resolved]) >= MAX_NPC_LITTER:
            return
        r, c = npc.cell()
        if self.world.solid(c, r):
            return
        if any(max(abs(nl.r - r), abs(nl.c - c)) < 2 for nl in self.npc_litters):
            return
        if any(not t.resolved and max(abs(t.r - r), abs(t.c - c)) < 2 for t in self.world.triggers):
            return
        self.npc_litters.append(NpcLitter(r, c, random.randrange(len(self.trash_surf))))
        npc.route, npc.wait_t = [], 0.9
        if not self._visible(r, c, *self.camera()):
            self._toast(f"Турист намусорил · {self.world.zone_at(r, c)}", bad=True)

    def _toast(self, text, bad=False):
        self.toast = [text, 0.0, bad]

    def _update_footsteps(self):
        if not self.moving:
            self._step_idx = -1
            return
        dt = RIDE_DT if self.riding else WALK_DT
        idx = int(self.walk_t / dt) % len(WALK_SEQ)
        if idx != self._step_idx:
            self._step_idx = idx
            if WALK_SEQ[idx] != 0 and self.sound_on and self.step_sounds:
                cell = (int(self.py + 12) // TILE, int(self.px + 5) // TILE)
                kind = "path" if self.riding else self.world.ground_at(*cell)
                random.choice(self.step_sounds[kind]).play()

    def _burst(self, x, y, n, colors, speed, life=(0.6, 1.2), grav=220.0):
        for _ in range(n):
            a, v, L = random.uniform(0, 2*math.pi), random.uniform(*speed), random.uniform(*life)
            self.particles.append([x, y, math.cos(a)*v, math.sin(a)*v - 60, L, L,
                                   random.choice(colors), random.choice((1, 2, 2, 3)), grav])

    def _burst_at_cell(self, r, c, n, colors, speed=(40, 120), life=(0.3, 0.7), grav=160.0):
        """брызги частиц в клетке карты"""
        cx, cy = self.camera()
        if self._visible(r, c, cx, cy):
            ts = TILE*SCALE
            self._burst(c*ts - cx + ts//2, r*ts - cy + ts//2, n, colors, speed, life, grav)

    def _update_particles(self, dt):
        alive = []
        for p in self.particles:
            p[4] -= dt
            if p[4] <= 0:
                continue
            p[2] *= max(0.0, 1 - 1.6*dt)
            p[3] += p[8] * dt
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            alive.append(p)
        self.particles = alive
        if self.card and self.card_t > 0.25:
            self._twinkle_t -= dt
            if self._twinkle_t <= 0:
                self._twinkle_t = 0.07
                rect = self._card_rect().inflate(20, 20)
                x0, y0, w, h = rect
                k = random.uniform(0, 2*(w + h))
                if k < w:
                    x, y = x0 + k, y0
                elif k < w + h:
                    x, y = x0 + w, y0 + k - w
                elif k < 2*w + h:
                    x, y = x0 + 2*w + h - k, y0 + h
                else:
                    x, y = x0, y0 + 2*(w + h) - k
                pl = self.card.plant
                L = random.uniform(0.45, 0.8)
                self.particles.append([x, y, random.uniform(-12, 12), random.uniform(-25, -5), L, L,
                                       random.choice((assets.UI_AMBER, pl["light"], (255, 246, 210))), 2, 0.0])

    def _spark(self, x, y, size, col):
        
        x, y = int(x) - 1, int(y) - 1
        pygame.draw.rect(self.screen, col, (x, y, 3, 3))
        for k in range(1, size):
            d = 3 * k
            for dx, dy in ((d, 0), (-d, 0), (0, d), (0, -d)):
                pygame.draw.rect(self.screen, col, (x + dx, y + dy, 3, 3))

    def _draw_particles(self):
        for x, y, vx, vy, life, mx, col, size, g in self.particles:
            self._spark(x, y, max(1, round(size * min(1.0, life / mx * 1.6))), col)

    def _open_card(self, t, new, xp, head=None):
        pl = t.plant
        self.card, self.card_t, self.card_new = t, 0.0, new
        self.card_bg = self._card_surface(pl, new, xp, head)
        art = plants_art.plant_sprite(pl, big=True)
        self.card_flower = pygame.transform.scale(pil_to_surf(art), (art.width*CARD_ART_SCALE, art.height*CARD_ART_SCALE))
        rect = self._card_rect()
        self._edge_burst(rect, 46, [assets.UI_AMBER, pl["light"], pl["base"], (255, 246, 210)])
        self._edge_burst(rect, 16, [assets.UI_GREEN, assets.UI_AMBER])
        self._play(self.snd_new if new else self.snd_card)

    def _edge_burst(self, rect, n, colors):
        
        w, h = rect.size
        for _ in range(n):
            k = random.uniform(0, 2*(w + h))
            if k < w:
                x, y, nx, ny = rect.x + k, rect.y, 0, -1
            elif k < w + h:
                x, y, nx, ny = rect.right, rect.y + k - w, 1, 0
            elif k < 2*w + h:
                x, y, nx, ny = rect.x + k - w - h, rect.bottom, 0, 1
            else:
                x, y, nx, ny = rect.x, rect.y + k - 2*w - h, -1, 0
            v, L = random.uniform(80, 240), random.uniform(0.5, 1.1)
            self.particles.append([x, y, nx*v + random.uniform(-40, 40), ny*v + random.uniform(-40, 40) - 30,
                                   L, L, random.choice(colors), random.choice((1, 2, 2, 3)), 160.0])

    def _close_card(self, force=False):
        if force or self.card_t > 0.3:
            self.card = None

    def _collect(self, sp, t, xp, head=None):
        
        name = sp["name"]
        new = name not in self.species
        if new:
            xp += XP["new_bonus"]
            self.species.add(name)
            self.found.append(name)
        self.xp += xp
        self._open_card(t, new, xp, None if new else head)

    def _keys(self):
        
        return self.key_override if self.key_override is not None else pygame.key.get_pressed()

    def update(self, dt=0.0):
        self._update_particles(dt)
        if self.card:
            self.moving = False
            self.walk_t = 0.0
            self.card_t += dt
            return
        if self.dialog:  # во время разговора мир стоит
            self.moving = False
            self.dialog["t"] += dt
            if self.dialog["result"] and self.dialog["t"] > DIALOG_AUTOCLOSE:
                self._close_dialog()
            return
        if self.pending_card:
            sp, t, xp, head = self.pending_card
            self.pending_card = None
            self.near = None
            self._collect(sp, t, xp, head)
            return
        self._move_player(dt)
        self.near = self._find_near()

        zone = self.world.zone_at(int(self.py+10) // TILE, int(self.px+5) // TILE)
        if zone != self._last_zone:
            self._last_zone = zone
            self.zone_toast = [zone, 0.0]
        if self.zone_toast:
            self.zone_toast[1] += dt
            if self.zone_toast[1] > 2.4:
                self.zone_toast = None
        if self.toast:
            self.toast[1] += dt
            if self.toast[1] > 2.6:
                self.toast = None

        self._update_npcs(dt)
        self._director(dt)
        self._update_horses(dt)
        for car in self.cars:
            if car.update(dt, self._feet(self.px, self.py), self.cars, self.bw):
                self._play(self.snd_horn)
        for nl in list(self.npc_litters):
            nl.age += dt
            if nl.age > NPC_LITTER_LIFETIME:
                self.npc_litters.remove(nl)
                self.lost += 1
                self._toast("Мусор так и остался у тропы · LOST +1", bad=True)
                self._play(self.snd_lost)
        for f in self.flashes:
            f[2] -= dt
        self.flashes = [f for f in self.flashes if f[2] > 0]

    def _move_player(self, dt):
        keys = self._keys()
        dx = dy = 0.0
        sp = RIDE_SPEED if self.riding else WALK_SPEED
        if keys[pygame.K_LEFT] or keys[pygame.K_a]: dx -= sp
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: dx += sp
        if keys[pygame.K_UP] or keys[pygame.K_w]: dy -= sp
        if keys[pygame.K_DOWN] or keys[pygame.K_s]: dy += sp
        if dx or dy:
            self.face = ("left" if dx < 0 else "right") if abs(dx) > abs(dy) else ("up" if dy < 0 else "down")
        self.moving = bool(dx or dy)
        self.walk_t = self.walk_t + dt if self.moving else 0.0
        nx = self.px + dx
        if not self._collide(nx, self.py):
            self.px = max(0, min(self.bw-10, nx))
        ny = self.py + dy
        if not self._collide(self.px, ny):
            self.py = max(0, min(self.bh-13, ny))
        if self.riding:                       # лошадь едет под игроком
            self.riding.x, self.riding.y = self.px + 5, self.py + 12
            if self.face in ("left", "right"):
                self.riding.face = self.face
        self._update_footsteps()

    def act(self):
        if self.card:
            self._close_card()
            return
        if self.dialog:
            return
        if self.riding:
            if self._at_gate():
                self._return_horse()
            else:
                self._dismount()
            return
        t = self.near
        if t is None:
            return
        if isinstance(t, NPC):
            if t.intent:
                self._open_dialog(t)
            return
        if isinstance(t, actors.Horse):
            if t.escaped and t.state != "ridden":
                self._mount(t)
            return
        if t.resolved:
            return
        t.resolved = True
        if isinstance(t, NpcLitter):
            self.saved += 1
            self.xp += XP["litter"]
            self._toast(f"+1 SAVE · +{XP['litter']} XP · спасибо за уборку!")
            self._play(self.snd_litter)
            self._burst_at_cell(t.r, t.c, 12, [assets.SAND_LT, assets.UI_GREEN, (255, 255, 255)])
            if t in self.npc_litters:
                self.npc_litters.remove(t)
        else:
            self.saved += 1
            self._collect(t.plant, t, XP["trigger"])
        self.near = None

    def _destroy_plant(self, cell, by):
        """растение погибло: убрать с карты, LOST +1"""
        plant = self.world.remove_plant(cell)
        if not plant:
            return
        sp = plant[2]
        self.lost += 1
        if cell not in self.world.water:
            self.trampled.append(cell)
        self.flashes.append([cell[0], cell[1], FLASH_TIME])
        if getattr(self.near, "plant", None) is sp and (self.near.r, self.near.c) == cell:
            self.near = None
        self._toast(f"{by}: {sp['name']} · LOST +1", bad=True)
        self._play(self.snd_lost)
        self._burst_at_cell(cell[0], cell[1], 16, [sp["base"], sp["light"], assets.GRASS_DK, assets.DIRT_LT])

    def _update_npcs(self, dt):
        for npc in self.npcs:
            it = npc.intent
            if it and it.get("plant") and not self.world.plant_at(it["cell"]):
                npc.intent = None  # растения уже нет
                npc._go_back(self.world)
            ev = npc.update(dt, self)
            if not ev:
                continue
            kind, data = ev
            if kind == "act":
                if data["kind"] == "litter":
                    self._spawn_npc_litter(npc)
                elif data["kind"] == "pick":
                    self._destroy_plant(data["cell"], "Турист сорвал")
                elif data["kind"] == "offroad_go":
                    self._toast("Турист сошёл с тропы и идёт напролом!", bad=True)
            elif kind == "trample":
                self._destroy_plant(data, "Турист вытоптал")
            elif kind == "cleaned" and data in self.npc_litters:
                self.npc_litters.remove(data)
                self.saved += 1
                self._toast("Турист сам убрал мусор · +1 SAVE")
                self._burst_at_cell(data.r, data.c, 10, [assets.SAND_LT, assets.UI_GREEN, (255, 255, 255)])

    def _director(self, dt):
        
        if any(n.intent for n in self.npcs):
            return
        self.event_t -= dt
        if self.event_t > 0:
            return
        self.event_t = random.uniform(*EVENT_GAP)
        free = [n for n in self.npcs if n.state == "walk" and not n.busy and n.cell() in self.world.path]
        if not free:
            self.event_t = 3.0
            return
        pr, pc = self._player_cell()
        free.sort(key=lambda n: abs(n.cell()[0] - pr) + abs(n.cell()[1] - pc))
        if random.random() > 0.6:
            random.shuffle(free)
        kind = random.choices([k for k, _ in INTENT_KINDS], [w for _, w in INTENT_KINDS])[0]
        npc, target = free[0], None
        if kind != "litter":
            for cand in free:
                target = self._plant_target(cand, kind)
                if target:
                    npc = cand
                    break
        if target is None:
            kind = "litter"
        if kind == "litter" and sum(1 for l in self.npc_litters if not l.resolved) >= MAX_NPC_LITTER:
            self.event_t = 4.0
            return
        if not npc.start_intent(kind, self, target):
            npc.start_intent("litter", self)
        r, c = npc.cell()
        if not self._visible(r, c, *self.camera()):
            self._toast(f"{tourists.intent_title(npc.intent).capitalize()} · {self.world.zone_at(r, c)}", bad=True)
            self._play(self.snd_alert)

    def _plant_target(self, npc, kind):
        
        r0, c0 = npc.cell()
        busy = {n.intent["cell"] for n in self.npcs if n.intent and n.intent.get("plant")}
        busy |= {h.goal for h in self.horses if h.goal}
        rad = 6 if kind == "pick" else 5
        cand = [f for f in self.world.flowers if (f[0], f[1]) not in busy
                and max(abs(f[0] - r0), abs(f[1] - c0)) <= rad
                and (kind == "pick" or (f[0], f[1]) not in self.world.water)]
        if not cand:
            return None
        cand.sort(key=lambda f: max(abs(f[0] - r0), abs(f[1] - c0)))
        return random.choice(cand[:3])

    def _open_dialog(self, npc):
        pr, pc = self._player_cell()
        r, c = npc.cell()
        npc.face = ("left" if pc < c else "right") if pc != c else ("up" if pr < r else "down")
        self.dialog = dict(npc=npc, say=tourists.tourist_line(npc), options=tourists.dialog_options(npc, self.rng),
                           sel=0, result=None, t=0.0)
        self.moving = False
        self._play(self.snd_talk)

    def _dialog_key(self, key):
        d = self.dialog
        if d["result"]:
            if key in (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE, pygame.K_ESCAPE):
                self._close_dialog()
            return
        n = len(d["options"])
        if key in (pygame.K_UP, pygame.K_w):
            d["sel"] = (d["sel"] - 1) % n
            self._play(self.snd_click)
        elif key in (pygame.K_DOWN, pygame.K_s):
            d["sel"] = (d["sel"] + 1) % n
            self._play(self.snd_click)
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3) and key - pygame.K_1 < n:
            d["sel"] = key - pygame.K_1
            self._dialog_choose(d["sel"])
        elif key in (pygame.K_e, pygame.K_RETURN, pygame.K_SPACE):
            self._dialog_choose(d["sel"])
        elif key == pygame.K_ESCAPE:
            self._close_dialog()

    def _dialog_choose(self, i):
        
        d = self.dialog
        npc = d["npc"]
        if d["result"] or not npc.intent:
            self._close_dialog()
            return
        tone, _, chance = d["options"][i]
        it = npc.intent
        npc.tried.add(tone)
        if tourists.persuade(chance, self.rng):
            npc.persuaded(self)
            self.saved += 1
            d["result"] = (True, tourists.REPLY_OK[npc.mood], "Спасибо, что объяснили!")
            self._toast("Турист передумал · +1 SAVE")
            self._play(self.snd_ok)
            if it.get("plant"):  # вид узнан в разговоре
                t = next((tr for tr in self.world.triggers if (tr.r, tr.c) == it["cell"]), None)
                t = t or _PlantRef(it["cell"], it["plant"])
                self.pending_card = (it["plant"], t, XP["persuade"], "РАСТЕНИЕ СПАСЕНО")
            else:
                self.xp += XP["persuade"]
        else:
            npc.refused()
            again = npc.intent and npc.tries < tourists.MAX_TRIES
            note = ("Он ещё не сделал шаг — нажми E рядом и попробуй другой тон!" if again
                    else "Не вышло — сейчас нарушит. В другой раз подбери тон под характер.")
            d["result"] = (False, tourists.REPLY_FAIL[npc.mood], note)
            self._play(self.snd_fail)
        d["t"] = 0.0

    def _close_dialog(self):
        self.dialog = None
        self._dialog_rects = []

    def _update_horses(self, dt):
        self._horse_director(dt)
        self._dust_t -= dt
        for horse in self.horses:
            ev = horse.update(dt, self.world.flowers)
            if horse.state == "trample" and self._dust_t <= 0:
                r, c = horse.cell()
                self._burst_at_cell(r, c, 4, [assets.DIRT_LT, assets.DIRT_BASE, assets.GRASS_DK], (30, 90), (0.25, 0.5))
            if horse.escaped and horse.state != "ridden" and horse.out_t > HORSE_GIVE_UP:
                horse.go_home()
                self._toast("Фермер сам увёл лошадь домой — в другой раз успей раньше", bad=True)
                continue
            if not ev:
                continue
            kind, cell = ev
            if kind == "trample":
                self._play(self.snd_trample)
            elif kind == "trampled":
                self._destroy_plant(cell, "Лошадь вытоптала")
        if self._dust_t <= 0:
            self._dust_t = 0.15

    def _horse_director(self, dt):
        
        if self.escapes >= MAX_ESCAPES or any(h.escaped for h in self.horses):
            return
        self.escape_t -= dt
        if self.escape_t > 0:
            return
        if any(n.intent for n in self.npcs):
            self.escape_t = 5.0
            return
        horse = random.choice([h for h in self.horses if not h.escaped])
        horse.escape()
        self.escapes += 1
        self.escape_t = random.uniform(*ESCAPE_GAP)
        self._toast("Лошадь сбежала с фермы в заповедник! Верни её", bad=True)
        self._play(self.snd_neigh)
        self._play(self.snd_alert)

    def _mount(self, horse):
        nx, ny = horse.x - 5, horse.y - 12
        if not self._collide(nx, ny):
            self.px, self.py = nx, ny
        horse.mount()
        self.riding = horse
        self.near = None
        self._toast("Верхом! Вези лошадь к воротам фермы")
        self._play(self.snd_neigh)

    def _dismount(self):
        
        h, self.riding = self.riding, None
        h.dismount(self.px + 5, self.py + 12, self.face)
        for dx, dy in ((0, TILE), (-TILE, 0), (TILE, 0), (0, -TILE)):
            if not self._collide(self.px + dx, self.py + dy):
                self.px, self.py = self.px + dx, self.py + dy
                break
        self._toast("Лошадь успокоилась, но скоро снова уйдёт")

    def _return_horse(self):
        h, self.riding = self.riding, None
        h.go_home()
        gr, gc = self.world.gate_out
        self.px, self.py, self.face = gc*TILE + 3, gr*TILE + 2, "up"
        self.saved += 1
        self.horses_home += 1
        self.xp += XP["horse"]
        self._toast(f"Лошадь дома · +1 SAVE · +{XP['horse']} XP")
        self._play(self.snd_ok)
        self._play(self.snd_neigh)
        self._burst_at_cell(gr - 1, gc, 18, [assets.UI_GREEN, assets.UI_AMBER, (255, 246, 210)], (60, 180), (0.5, 1.0))

    def camera(self):
        cx = int((self.px+5)*SCALE - WIN_W/2)
        cy = int((self.py+6)*SCALE - WIN_H/2)
        if self.map_w > WIN_W:
            cx = max(0, min(self.map_w - WIN_W, cx))
        else:
            cx = -(WIN_W - self.map_w) // 2
        if self.map_h > WIN_H:
            cy = max(0, min(self.map_h - WIN_H, cy))
        else:
            cy = -(WIN_H - self.map_h) // 2
        return cx, cy

    def player_frame(self):
        frames = self.player_surf[self.face]
        if not self.moving:
            return frames[0]
        return frames[WALK_SEQ[int(self.walk_t / WALK_DT) % len(WALK_SEQ)]]

    def draw(self):
        if self.state == "menu":
            self._draw_menu()
        elif self.state == "settings":
            self._draw_settings()
        elif self.state == "book":
            self._draw_book()
        elif self.state in ("play", "quit"):
            self._draw_play()

    def _draw_book(self):
        
        if self.book.origin == "play":
            self._draw_play()
            ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA); ov.fill((5, 9, 7, 170)); self.screen.blit(ov, (0, 0))
        else:
            self._menu_backdrop(dim=225)
        self.book.draw(self.screen)

    def _visible(self, r, c, cx, cy):
        ts = TILE*SCALE
        return -ts <= c*ts - cx <= WIN_W and -ts <= r*ts - cy <= WIN_H + ts

    def _water(self, cx, cy):
        frame = self.water_surf[int(self.t / WATER_DT) % len(self.water_surf)]
        ts = TILE*SCALE
        for r in range(max(0, cy // ts), min(self.world.H, (cy + WIN_H) // ts + 1)):
            for c in range(max(0, cx // ts), min(self.world.W, (cx + WIN_W) // ts + 1)):
                if (r, c) in self.world.water:
                    self.screen.blit(frame[(r*7 + c*13) % len(frame)], (c*ts - cx, r*ts - cy))

    def _draw_flower(self, r, c, pl, cx, cy):
        ts = TILE*SCALE
        k = SWAY_SEQ[int(self.t / SWAY_DT - c*0.3 - r*0.12) % len(SWAY_SEQ)]
        fs = self.flower_surf[pl["name"]][k]
        x = c*ts - cx + (ts - fs.get_width())//2
        if pl.get("habitat") == "water":  # кувшинки — на воде
            self.screen.blit(fs, (x, r*ts - cy + (ts - fs.get_height())//2 + 3))
        else:
            self.screen.blit(fs, (x, (r+1)*ts - cy - fs.get_height()))

    def _draw_litter(self, r, c, cx, cy):
        ts = TILE*SCALE
        self.screen.blit(self.litter_surf, (c*ts - cx + 22, r*ts - cy + 24))

    def _draw_actor(self, actor, cx, cy):
        if actor is self:
            self._draw_player(cx, cy)
            return
        frame, x, y = actor.frame(self.npc_surf[actor.variant]), actor.px, actor.py
        if actor.crouch():                     # наклонился к растению
            y += 2 + int(self.t * 3) % 2
        self.screen.blit(frame, (int(x*SCALE - cx), int(y*SCALE - cy)))

    def _draw_player(self, cx, cy):
        if not self.riding:
            self.screen.blit(self.player_frame(), (int(self.px*SCALE - cx), int(self.py*SCALE - cy)))
            return
        frames = self.rider_surf[self.riding.variant][self.face]
        f = frames[WALK_SEQ[int(self.walk_t / RIDE_DT) % len(WALK_SEQ)]] if self.moving else frames[0]
        x = (self.px + 5)*SCALE - cx - f.get_width()//2
        y = (self.py + 14)*SCALE - cy - f.get_height()
        self.screen.blit(f, (int(x), int(y)))

    def _draw_scene(self, cx, cy):
        items = []
        ts = TILE*SCALE
        for (r, c) in self.trampled:
            if self._visible(r, c, cx, cy):
                self.screen.blit(self.trampled_surf, (c*ts - cx + (ts - self.trampled_surf.get_width())//2,
                                                      (r+1)*ts - cy - self.trampled_surf.get_height() - 3))
        for (r, c, pl) in self.world.flowers:
            if self._visible(r, c, cx, cy):
                items.append(((r+1)*TILE, "flower", (r, c, pl)))
        for t in self.world.triggers:
            if t.kind == "litter" and not t.resolved and self._visible(t.r, t.c, cx, cy):
                items.append((t.r*TILE + 18, "litter", (t.r, t.c)))
        for nl in self.npc_litters:
            if not nl.resolved and self._visible(nl.r, nl.c, cx, cy):
                items.append((nl.r*TILE + 14, "trash", nl))
        for npc in self.npcs:
            items.append((npc.py + 12, "actor", npc))
        for horse in self.horses:
            if horse.state != "ridden" and self._visible(int(horse.y) // TILE, int(horse.x) // TILE, cx, cy):
                items.append((horse.y, "horse", horse))
        for car in self.cars:
            if self._visible(int(car.y) // TILE, int(car.x + 12) // TILE, cx, cy):
                items.append((car.y + 11, "car", car))
        items.append((self.py + 12, "actor", self))
        items.sort(key=lambda it: it[0])
        for _, kind, data in items:
            if kind == "flower":
                self._draw_flower(*data, cx, cy)
            elif kind == "litter":
                self._draw_litter(data[0], data[1], cx, cy)
            elif kind == "trash":
                self._draw_trash(data, cx, cy)
            elif kind == "horse":
                s = self.horse_surf[data.variant][data.face][data.frame()]
                self.screen.blit(s, (int((data.x - 11)*SCALE - cx), int((data.y - 13 + data.hop())*SCALE - cy)))
            elif kind == "car":
                s = self.car_surf[data.color]["right" if data.dir > 0 else "left"][data.frame()]
                self.screen.blit(s, (int(data.x*SCALE - cx), int(data.y*SCALE - cy)))
            else:
                self._draw_actor(data, cx, cy)

    def _draw_trash(self, nl, cx, cy):
        if nl.left() < NPC_LITTER_WARN and int(self.t * 6) % 2:
            return
        s, ts = self.trash_surf[nl.variant], TILE*SCALE
        self.screen.blit(s, (nl.c*ts - cx + (ts - s.get_width())//2, (nl.r+1)*ts - cy - s.get_height() - 6))

    def _bubble(self, kind, x, y, frac=None):
        
        b = self.bubble_surf[kind]
        bx, by = int(x - b.get_width()//2), int(y - b.get_height())
        self.screen.blit(b, (bx, by))
        if frac is not None:
            w = b.get_width()
            col = assets.UI_AMBER if frac > 0.4 else assets.UI_RED
            pygame.draw.rect(self.screen, (20, 16, 10), (bx - 1, by - 9, w + 2, 7))
            pygame.draw.rect(self.screen, col, (bx, by - 8, int(w * max(0.0, frac)), 5))

    def _draw_overheads(self, cx, cy):
        
        bob = int(round(2*math.sin(self.t*6)))
        for npc in self.npcs:
            x, y = (npc.px + 5)*SCALE - cx, npc.py*SCALE - cy - 4 + bob
            if npc.intent:
                it = npc.intent
                frac = it["t"] / it["total"] if npc.state == "intent" else None
                self._bubble("intent", x, y, frac)
            elif npc.bubble:
                self._bubble(npc.bubble[0], x, y)
        for h in self.horses:
            if h.escaped and h.state != "ridden":
                self._bubble("alarm", h.x*SCALE - cx + 12, (h.y - 15)*SCALE - cy + bob)

    def _panel(self, rect, fill=assets.UI_PANEL, edge=assets.UI_EDGE, w=2, surf=None):
        surf = surf or self.screen
        pygame.draw.rect(surf, fill, rect)
        pygame.draw.rect(surf, edge, rect, w)

    def _callout_info(self, t):
        
        ts = TILE*SCALE
        if isinstance(t, NPC):
            it = t.intent
            if not it:
                return None
            frac = it["t"] / it["total"] if t.state == "intent" else None
            return (t.px + 5)*SCALE, t.py*SCALE - 106, "!  " + tourists.intent_title(it), frac, "E — поговорить"
        if isinstance(t, actors.Horse):
            if not t.escaped or t.state == "ridden":
                return None
            return t.x*SCALE, (t.y - 15)*SCALE - 92, "!  ЛОШАДЬ В ЗАПОВЕДНИКЕ", None, "E — сесть верхом"
        if t == "gate":
            r, c = self.world.gate
            return c*ts + ts//2, r*ts - 40, "ВОРОТА ФЕРМЫ", None, "E — вернуть лошадь"
        frac = max(0.0, t.left() / NPC_LITTER_LIFETIME) if isinstance(t, NpcLitter) else None
        return t.c*ts + ts//2, t.r*ts - 34, t.title, frac, "E — убрать"

    def _callout(self, t, cx, cy):
        info = self._callout_info(t)
        if not info:
            return
        ax, ay, title, frac, hint = info
        sx, sy = int(ax - cx), int(ay - cy)
        good = t == "gate"
        label = self.txt(self.f_sm, title, assets.UI_GREEN if good else assets.UI_RED)
        w = label.get_width() + 20
        x0 = max(6, min(WIN_W - w - 6, sx - w//2))
        sy = max(70, sy)
        self._panel((x0, sy, w, 26), fill=(20, 42, 28) if good else (42, 20, 15),
                    edge=assets.UI_GREEN if good else assets.UI_RED)
        self.screen.blit(label, (x0+10, sy+5))
        hy = sy + 28
        if frac is not None:
            col = assets.UI_AMBER if frac > 0.27 else assets.UI_RED
            pygame.draw.rect(self.screen, assets.UI_PANEL, (x0, sy+27, w, 5))
            pygame.draw.rect(self.screen, col, (x0, sy+27, int(w*frac), 5))
            hy += 6
        self.screen.blit(self.txt(self.f_xs, hint, assets.UI_INK), (x0+10, hy))

    def _icon_button(self, rect, icon, key, active):
        self._panel(rect, fill=assets.UI_PANEL2 if active else assets.UI_PANEL,
                    edge=assets.UI_GREEN if active else assets.UI_EDGE)
        self.screen.blit(icon, (rect.centerx - icon.get_width()//2, rect.y + 5))
        k = self.txt(self.f_key, key, assets.UI_FAINT)
        self.screen.blit(k, (rect.centerx - k.get_width()//2, rect.bottom - 19))

    def _threats(self):
        
        return (sum(1 for n in self.npcs if n.intent)
                + sum(1 for h in self.horses if h.escaped and h.state != "ridden"))

    def _draw_icons(self):
        r1 = pygame.Rect(10, 10, 46, 52)
        self._icon_button(r1, self.icon_map, "M", self.show_map)
        active = sum(1 for nl in self.npc_litters if not nl.resolved)
        if active:
            b = self.txt(self.f_xs, str(active), assets.UI_INK)
            br = pygame.Rect(r1.right - 10, r1.y - 4, b.get_width() + 8, 16)
            self._panel(br, fill=assets.UI_RED, edge=(42, 20, 15), w=1)
            self.screen.blit(b, (br.x + 4, br.y + 1))
        threats = self._threats()
        if threats and int(self.t * 3) % 3:  # значок угроз
            b = self.txt(self.f_xs, str(threats), (20, 16, 10))
            br = pygame.Rect(r1.right - 10, r1.bottom - 12, b.get_width() + 8, 16)
            self._panel(br, fill=THREAT_COL, edge=(42, 20, 15), w=1)
            self.screen.blit(b, (br.x + 4, br.y + 1))
        self.map_icon_rect = r1
        r2 = pygame.Rect(WIN_W-56, 10, 46, 52)
        self._icon_button(r2, self.icon_stats, "Tab", self.show_stats)
        self.stats_icon_rect = r2

    def _draw_minimap_panel(self):
        MM = 2
        mw, mh = self.minimap_surf.get_width()*MM, self.minimap_surf.get_height()*MM
        W, H = mw+32, mh+104
        x0, y0 = (WIN_W-W)//2, (WIN_H-H)//2
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA); ov.fill((5, 9, 7, 150)); self.screen.blit(ov, (0, 0))
        self._panel((x0, y0, W, H), fill=assets.UI_PANEL, edge=assets.UI_EDGE, w=3)
        self.screen.blit(self.txt(self.f_md, "КАРТА ЭКОТРОПЫ", assets.UI_GREEN), (x0+16, y0+12))
        mm_scaled = pygame.transform.scale(self.minimap_surf, (mw, mh))
        mx0, my0 = x0+16, y0+42
        self.screen.blit(mm_scaled, (mx0, my0))
        pygame.draw.rect(self.screen, assets.UI_EDGE, (mx0, my0, mw, mh), 1)
        cell = assets.MINI_CELL * MM
        cam_x, cam_y = self.camera()
        k = cell / (TILE*SCALE)
        pygame.draw.rect(self.screen, assets.UI_FAINT, (mx0 + cam_x*k, my0 + cam_y*k, WIN_W*k, WIN_H*k), 1)

        def dot(x, y, col, size=4):
            pygame.draw.rect(self.screen, (20, 16, 10), (int(x) - size//2 - 1, int(y) - size//2 - 1, size + 2, size + 2))
            pygame.draw.rect(self.screen, col, (int(x) - size//2, int(y) - size//2, size, size))

        blink = int(self.t * 4) % 2
        gr, gc = self.world.gate
        dot(mx0+gc*cell+cell//2, my0+gr*cell+cell//2, assets.WOOD_LT, 5)
        for t in self.world.triggers:
            if not t.resolved:
                dot(mx0+t.c*cell+cell//2, my0+t.r*cell+cell//2, assets.UI_RED)
        for nl in self.npc_litters:
            if not nl.resolved and not (nl.left() < NPC_LITTER_WARN and blink):
                dot(mx0+nl.c*cell+cell//2, my0+nl.r*cell+cell//2, assets.UI_AMBER)
        for r, c, left in self.flashes:  # вспышка погибшего растения
            if int(left * 6) % 2:
                pygame.draw.rect(self.screen, assets.UI_RED, (mx0 + c*cell - 3, my0 + r*cell - 3, cell + 6, cell + 6), 2)
        for npc in self.npcs:
            x, y = mx0 + (npc.px+5)/TILE*cell, my0 + (npc.py+10)/TILE*cell
            if npc.intent:
                pygame.draw.rect(self.screen, THREAT_COL, (int(x) - 6, int(y) - 6, 12, 12), 2 if blink else 1)
                dot(x, y, THREAT_COL, 5)
            else:
                dot(x, y, (170, 140, 220))
        for h in self.horses:
            if h.escaped and h.state != "ridden":
                x, y = mx0 + h.x/TILE*cell, my0 + h.y/TILE*cell
                pygame.draw.rect(self.screen, HORSE_COL, (int(x) - 6, int(y) - 6, 12, 12), 2 if blink else 1)
                dot(x, y, HORSE_COL, 5)
        dot(mx0 + (self.px+5)/TILE*cell, my0 + (self.py+10)/TILE*cell,
            assets.UI_INK if blink else assets.UI_GREEN, 6)
        lx, ly = x0+16, my0+mh+8
        for label, col in (("ты", assets.UI_GREEN), ("растение", assets.UI_RED), ("мусор", assets.UI_AMBER),
                           ("турист", (170, 140, 220)), ("нарушает", THREAT_COL), ("лошадь", HORSE_COL),
                           ("ферма", assets.WOOD_LT)):
            s = self.txt(self.f_xs, label, assets.UI_INK)
            if lx + s.get_width() + 12 > x0 + W - 12:
                lx, ly = x0 + 16, ly + 18
            dot(lx + 3, ly + 8, col)
            self.screen.blit(s, (lx + 10, ly + 1))
            lx += s.get_width() + 26
        self.screen.blit(self.txt(self.f_xs, "M / Esc — закрыть", assets.UI_FAINT), (x0+16, y0+H-22))

    def _draw_stats_panel(self):
        rows = max(1, math.ceil(len(SPECIES) / STAT_PER_ROW))
        W = 28 + STAT_PER_ROW*STAT_CELL
        parts = []
        for kind in KIND_ORDER:
            names = [sp["name"] for sp in SPECIES if sp["kind"] == kind]
            parts.append(f"{KINDS[kind]['plural']} {sum(n in self.species for n in names)}/{len(names)}")
        kinds = self._wrap_lines(" · ".join(parts), W-28, self.f_xs)
        note = ("последний: " + self.found[-1]) if self.found else "пока никого — ищи мусор у цветов"
        notes = self._wrap_lines(note, W-28, self.f_xs)[:2]
        lh = self.f_xs.get_height() + 2
        # высота по содержимому
        H = 162 + rows*STAT_CELL + 8 + len(kinds)*lh + 4 + lh + 8 + len(notes)*lh + 10 + 22
        x0, y0 = WIN_W-W-16, 70
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA); ov.fill((5, 9, 7, 90)); self.screen.blit(ov, (0, 0))
        self._panel((x0, y0, W, H), fill=assets.UI_PANEL, edge=assets.UI_EDGE, w=3)
        self.screen.blit(self.txt(self.f_md, "СТАТИСТИКА", assets.UI_GREEN), (x0+14, y0+10))
        chips = [("SAVE", str(self.saved), assets.UI_GREEN), ("LOST", str(self.lost), assets.UI_RED),
                 ("ВИДЫ", f"{len(self.species)}/{len(SPECIES)}", assets.UI_INK), ("XP", str(self.xp), assets.UI_AMBER)]
        cw = (W-28)//2
        for i, (k, v, col) in enumerate(chips):
            x = x0+14+(i % 2)*cw
            y = y0+40+(i//2)*48
            self._panel((x, y, cw-8, 40), fill=assets.UI_PANEL2)
            self.screen.blit(self.txt(self.f_xs, k, assets.UI_FAINT), (x+8, y+4))
            self.screen.blit(self.txt(self.f_md, v, col), (x+8, y+18))
        self.screen.blit(self.txt(self.f_sm, "Коллекция видов:", assets.UI_INK), (x0+14, y0+140))
        # иконки по типам, неоткрытые — серые; прямоугольники — для наведения и клика
        order = sorted(SPECIES, key=lambda sp: KIND_ORDER.index(sp["kind"]))
        gy = y0 + 162
        self.stat_icon_rects = {}
        for i, sp in enumerate(order):
            name = sp["name"]
            cell = pygame.Rect(x0 + 14 + (i % STAT_PER_ROW)*STAT_CELL, gy + (i // STAT_PER_ROW)*STAT_CELL,
                               STAT_CELL, STAT_CELL)
            self.stat_icon_rects[name] = cell
            if name == self.stat_hover:
                self._panel(cell, fill=assets.UI_PANEL2, edge=assets.UI_GREEN)
            col, grey = self.plant_icon[name]
            fs = col if name in self.species else grey
            self.screen.blit(fs, (cell.centerx - fs.get_width()//2, cell.bottom - 2 - fs.get_height()))
        y = gy + rows*STAT_CELL + 8
        for s in kinds:
            self.screen.blit(self.txt(self.f_xs, s, assets.UI_INK), (x0+14, y)); y += lh
        y += 4
        horses = f"лошадей вернул на ферму: {self.horses_home} · побегов: {self.escapes}"
        self.screen.blit(self.txt(self.f_xs, horses, assets.UI_INK), (x0+14, y)); y += lh + 8
        for s in notes:
            self.screen.blit(self.txt(self.f_xs, s, assets.UI_FAINT), (x0+14, y)); y += lh
        foot = "Tab / Esc — закрыть · клик по виду — подробнее" if self.species else "Tab / Esc — закрыть"
        self.screen.blit(self.txt(self.f_xs, foot, assets.UI_FAINT), (x0+14, y0+H-22))
        if self.stat_hover in self.stat_icon_rects:  # подпись над наведённым видом
            cell = self.stat_icon_rects[self.stat_hover]
            s = self.txt(self.f_xs, self.stat_hover, assets.UI_INK)
            tip = pygame.Rect(0, cell.y - 24, s.get_width() + 16, 22)
            tip.centerx = cell.centerx
            tip.x = max(4, min(WIN_W - tip.w - 4, tip.x))
            self._panel(tip, fill=assets.UI_PANEL2, edge=assets.UI_GREEN)
            self.screen.blit(s, (tip.x + 8, tip.y + (tip.h - s.get_height())//2))

    def _draw_toast(self):
        if not self.toast:
            return
        text, t, bad = self.toast
        alpha = 255 if t < 2.0 else max(0, int(255*(2.6-t)/0.6))
        col = assets.UI_RED if bad else assets.UI_GREEN
        surf = self.txt(self.f_sm, text, col)
        panel = pygame.Surface((surf.get_width()+24, 30), pygame.SRCALPHA)
        panel.fill((*assets.UI_PANEL, 230))
        pygame.draw.rect(panel, col, panel.get_rect(), 2)
        panel.blit(surf, (12, 6))
        panel.set_alpha(alpha)
        self.screen.blit(panel, (WIN_W//2-panel.get_width()//2, WIN_H-70))

    def _draw_zone_toast(self):
        if not self.zone_toast:
            return
        text, t = self.zone_toast
        alpha = 255 if t < 1.6 else max(0, int(255*(2.4-t)/0.8))
        surf = self.txt(self.f_sm, text, assets.UI_INK)
        panel = pygame.Surface((surf.get_width()+20, 28), pygame.SRCALPHA)
        panel.fill((*assets.UI_PANEL2, 210))
        panel.blit(surf, (10, 5))
        panel.set_alpha(alpha)
        self.screen.blit(panel, (14, WIN_H-46))

    def _draw_ride_hint(self):
        
        if not self.riding or self.near == "gate":
            return
        s = self.txt(self.f_xs, "Верхом · вези лошадь к воротам фермы у кордона · E — слезть", assets.UI_INK)
        rect = pygame.Rect(WIN_W//2 - s.get_width()//2 - 10, 72, s.get_width() + 20, 22)
        self._panel(rect, fill=(44, 34, 20), edge=HORSE_COL, w=1)
        self.screen.blit(s, (rect.x + 10, rect.y + 4))

    def _draw_play(self):
        cx, cy = self.camera()
        self.screen.fill((14, 24, 19))
        self.screen.blit(self.map_surf, (-cx, -cy))
        self._water(cx, cy)
        self._draw_scene(cx, cy)
        self._draw_overheads(cx, cy)
        if not self.card:
            self._draw_particles()  # искры под интерфейсом
        if self.near and not self.dialog:
            self._callout(self.near, cx, cy)
        self._draw_icons()
        self._draw_ride_hint()
        self._draw_zone_toast()
        self._draw_toast()
        if self.show_map:
            self._draw_minimap_panel()
        if self.show_stats:
            self._draw_stats_panel()
        if self.dialog:
            self._draw_dialog()
        if self.card:
            self._card(self.card)

    def _draw_dialog(self):
        
        d = self.dialog
        npc = d["npc"]
        mood = tourists.MOODS[npc.mood]
        W = min(WIN_W - 60, 780)
        x0 = (WIN_W - W) // 2
        tx = x0 + 16 + 104
        tw = x0 + W - 16 - tx
        say = self._wrap_lines(f"«{d['say']}»", tw, self.f_sm)
        opts = [self._wrap_lines(text, tw - 20, self.f_sm)[:3] for _, text, _ in d["options"]]
        lh = self.f_sm.get_height() + 2
        if d["result"]:
            body = 24 + 2*lh + 30
        else:
            body = sum(18 + len(o)*lh + 10 for o in opts)
        H = 16 + 22 + len(say)*lh + 10 + body + 26
        y0 = WIN_H - H - 12
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA); ov.fill((5, 9, 7, 110)); self.screen.blit(ov, (0, 0))
        self._panel((x0, y0, W, H), fill=assets.UI_PANEL, edge=THREAT_COL, w=3)
        frame = pygame.Rect(x0 + 16, y0 + 16, 96, 112)
        self._panel(frame, fill=(36, 64, 47))
        p = self.npc_portrait[npc.variant]
        self.screen.blit(p, (frame.centerx - p.get_width()//2, frame.centery - p.get_height()//2))
        mtag = self.txt(self.f_xs, mood["label"], assets.UI_AMBER)
        self.screen.blit(mtag, (frame.centerx - mtag.get_width()//2, frame.bottom + 6))
        y = y0 + 14
        self.screen.blit(self.txt(self.f_md, "ТУРИСТ", THREAT_COL), (tx, y))
        self.screen.blit(self.txt(self.f_xs, f"характер: {mood['label']} — {mood['hint']}", assets.UI_FAINT),
                         (tx + 80, y + 4))
        y += 24
        for s in say:
            self.screen.blit(self.txt(self.f_sm, s, assets.UI_INK), (tx, y)); y += lh
        y += 10
        self._dialog_rects = []
        if d["result"]:
            ok, text, note = d["result"]
            col = assets.UI_GREEN if ok else assets.UI_RED
            head = "Получилось!" if ok else "Не убедил…"
            self.screen.blit(self.txt(self.f_md, head, col), (tx, y)); y += 24
            y += self._wrap(f"Турист: «{text}»", tx, y, tw, self.f_sm, assets.UI_INK, max_lines=1) + 6
            self._wrap(note, tx, y, tw, self.f_xs, assets.UI_FAINT if ok else assets.UI_AMBER, max_lines=1)
            hint = "E — дальше"
        else:
            for i, ((tone, _, _), lines) in enumerate(zip(d["options"], opts)):
                h = 18 + len(lines)*lh + 4
                rect = pygame.Rect(tx - 6, y - 4, tw + 6, h + 2)
                sel = i == d["sel"]
                self._panel(rect, fill=assets.UI_PANEL2 if sel else assets.UI_PANEL,
                            edge=assets.UI_GREEN if sel else assets.UI_EDGE, w=2 if sel else 1)
                self._dialog_rects.append(rect)
                tag = f"{i + 1} · {tourists.TONE_LABEL[tone]}" + (" · уже пробовал" if tone in npc.tried else "")
                self.screen.blit(self.txt(self.f_xs, tag, assets.UI_GREEN if sel else assets.UI_FAINT), (tx + 4, y))
                for k, s in enumerate(lines):
                    self.screen.blit(self.txt(self.f_sm, s, assets.UI_INK), (tx + 14, y + 16 + k*lh))
                y += h + 8
            left = tourists.MAX_TRIES - npc.tries
            hint = f"W/S или 1–3 — выбор · E — сказать · Esc — отойти · попыток: {left}"
        self.screen.blit(self.txt(self.f_xs, hint, assets.UI_FAINT), (tx, y0 + H - 22))

    def _wrap_lines(self, text, maxw, font):
        
        lines, line = [], ""
        for w in text.split():
            test = (line + " " + w).strip()
            if font.size(test)[0] <= maxw:
                line = test
                continue
            if line:
                lines.append(line)
            while font.size(w)[0] > maxw:
                k = len(w)
                while k > 1 and font.size(w[:k])[0] > maxw:
                    k -= 1
                lines.append(w[:k]); w = w[k:]
            line = w
        if line:
            lines.append(line)
        return lines

    def _wrap(self, text, x, y, maxw, font, col, surf=None, max_lines=None):
        
        surf = surf or self.screen
        lines = self._wrap_lines(text, maxw, font)
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines]
            while lines[-1] and font.size(lines[-1] + "…")[0] > maxw:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "…"
        lh = font.get_height() + 2
        for i, s in enumerate(lines):
            surf.blit(self.txt(font, s, col), (x, y + i*lh))
        return len(lines) * lh - 2 if lines else 0

    def _card_layout(self, pl):
        
        tw = CARD_W - CARD_TX - CARD_PAD
        info = kind_info(pl)
        def block(kind, font, text, col, gap=CARD_GAP):
            lines = self._wrap_lines(text, tw - (16 if kind == "threat" else 0), font)
            h = len(lines) * (font.get_height() + 2) - 2 + (10 if kind == "threat" else 0)
            return dict(kind=kind, font=font, lines=lines, col=col, h=h, gap=gap)
        head = [block("text", self.f_md, pl["name"], assets.UI_GREEN, 3),
                block("text", self.f_it, pl["lat"], assets.UI_FAINT, 2 if pl.get("alt") else CARD_GAP)]
        if pl.get("alt"):
            head.append(block("text", self.f_xs, "в народе — " + pl["alt"], assets.UI_FAINT))
        head.append(dict(kind="badges", h=20, gap=CARD_GAP))
        head.append(block("text", self.f_sm, f"{info['season']}: {pl['season']} · зона: {', '.join(zones(pl))}", assets.UI_INK))
        head.append(block("threat", self.f_xs, "УГРОЗА · " + pl["threat"], assets.UI_AMBER))
        top = CARD_HEAD_H + 12
        for font in (self.f_sm, self.f_xs):
            blocks = head + [block("text", font, pl["fact"], assets.UI_INK, 0)]
            need = sum(b["h"] + b["gap"] for b in blocks)
            if top + need <= CARD_H - CARD_FOOT_H - 8:
                return CARD_H, blocks, True
        H = top + need + CARD_FOOT_H + 8
        return min(H, CARD_MAX_H), blocks, H <= CARD_MAX_H

    def _card_surface(self, pl, new, xp, head=None):
        
        H, blocks, _ = self._card_layout(pl)
        W = CARD_W
        card_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        self._panel((0, 0, W, H), fill=assets.UI_PANEL, edge=assets.UI_AMBER, w=3, surf=card_surf)
        pygame.draw.rect(card_surf, assets.UI_AMBER, (0, 0, W, CARD_HEAD_H))
        ink = (20, 16, 10)
        head = head or ("НОВЫЙ ВИД В КОЛЛЕКЦИИ!" if new else "НАРУШЕНИЕ ОСТАНОВЛЕНО")
        hs = self.txt(self.f_md, head, ink)
        card_surf.blit(hs, (CARD_PAD, (CARD_HEAD_H - hs.get_height()) // 2))
        xs = self.txt(self.f_sm, f"+{xp} XP", ink)
        card_surf.blit(xs, (W - CARD_PAD - xs.get_width(), (CARD_HEAD_H - xs.get_height()) // 2))

        frame = self._card_frame(H)
        self._panel(frame, fill=(36, 64, 47), surf=card_surf)
        cap = self.txt(self.f_xs, kind_info(pl)["label"], assets.UI_FAINT)
        card_surf.blit(cap, (frame.centerx - cap.get_width() // 2,
                             frame.bottom - CARD_CAPTION_H + (CARD_CAPTION_H - cap.get_height()) // 2 - 1))
        pygame.draw.line(card_surf, assets.UI_EDGE, (frame.x + 6, frame.bottom - CARD_CAPTION_H),
                         (frame.right - 7, frame.bottom - CARD_CAPTION_H))

        y = CARD_HEAD_H + 12
        for b in blocks:
            if b["kind"] == "badges":
                self._card_badges(card_surf, pl, y)
            elif b["kind"] == "threat":
                self._panel((CARD_TX, y, W - CARD_TX - CARD_PAD, b["h"]), fill=(44, 34, 20), edge=assets.UI_AMBER,
                            w=1, surf=card_surf)
                for i, s in enumerate(b["lines"]):
                    card_surf.blit(self.txt(b["font"], s, b["col"]), (CARD_TX + 8, y + 5 + i*(b["font"].get_height() + 2)))
            else:
                for i, s in enumerate(b["lines"]):
                    card_surf.blit(self.txt(b["font"], s, b["col"]), (CARD_TX, y + i*(b["font"].get_height() + 2)))
            y += b["h"] + b["gap"]

        fy = H - CARD_FOOT_H
        pygame.draw.line(card_surf, assets.UI_EDGE, (CARD_PAD, fy), (W - CARD_PAD, fy))
        cnt = self.txt(self.f_xs, f"ВИДЫ {len(self.species)}/{len(SPECIES)}", assets.UI_FAINT)
        card_surf.blit(cnt, (CARD_PAD, fy + (CARD_FOOT_H - cnt.get_height()) // 2))
        hint = self.txt(self.f_sm, "E / Esc — дальше", assets.UI_FAINT)
        card_surf.blit(hint, (W - CARD_PAD - hint.get_width(), fy + (CARD_FOOT_H - hint.get_height()) // 2))
        more = self.txt(self.f_xs, "B — подробнее в энциклопедии", assets.UI_FAINT)
        mx = (CARD_PAD + cnt.get_width() + W - CARD_PAD - hint.get_width() - more.get_width()) // 2
        card_surf.blit(more, (mx, fy + (CARD_FOOT_H - more.get_height()) // 2))
        return card_surf

    def _card_frame(self, H):
        top = CARD_HEAD_H + 12
        return pygame.Rect(CARD_PAD, top, CARD_PORTRAIT_W, H - CARD_FOOT_H - 8 - top)

    def _card_badges(self, surf, pl, y):
        bx = CARD_TX
        for tag in pl["rb"]:
            s = self.txt(self.f_xs, tag, assets.UI_RED)
            self._panel((bx, y, s.get_width()+12, 20), fill=(42, 20, 15), edge=assets.UI_RED, w=1, surf=surf)
            surf.blit(s, (bx + 6, y + (20 - s.get_height()) // 2))
            bx += s.get_width() + 18

    def _card_rect(self):
        W, H = self.card_bg.get_size()
        return pygame.Rect((WIN_W-W)//2, (WIN_H-H)//2, W, H)

    def _card(self, t):
        base = self._card_rect()
        W, H = base.size
        card_surf = self.card_bg.copy()
        bob = int(round(3*math.sin(self.card_t*3.2)))
        fimg, frame = self.card_flower, self._card_frame(H)
        art_h = frame.height - CARD_CAPTION_H
        card_surf.blit(fimg, (frame.centerx - fimg.get_width()//2, frame.y + (art_h - fimg.get_height())//2 + bob))

        ov_alpha = min(170, int(170 * min(1.0, self.card_t/0.18)))
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        ov.fill((5, 9, 7, ov_alpha))
        for i in range(2):
            p = (self.card_t - 0.1 - i*0.14) / 0.6
            if 0 < p < 1:
                grow = int(10 + 80*(1 - (1-p)**3))
                pygame.draw.rect(ov, (*assets.UI_AMBER, int(190*(1-p))), base.inflate(grow*2, grow*2), 3)
        self.screen.blit(ov, (0, 0))
        self._draw_particles()  # искры под карточкой

        dur = 0.32
        p = min(1.0, self.card_t/dur)
        ease = 1 - (1-p)**3
        overshoot = 1 + 0.12*math.sin(p*math.pi) if p < 1.0 else 1.0
        scale = max(0.05, ease*overshoot)
        alpha = int(255*min(1.0, self.card_t/0.16))
        if p >= 1.0:
            glow = 0.5 + 0.5*math.sin(self.card_t*4)
            pygame.draw.rect(self.screen, assets.blend(assets.UI_EDGE, assets.UI_AMBER, glow), base.inflate(8, 8), 3)
            self.screen.blit(card_surf, base)
            return
        sw, sh = max(1, int(W*scale)), max(1, int(H*scale))
        scaled_card = pygame.transform.smoothscale(card_surf, (sw, sh))
        scaled_card.set_alpha(alpha)
        self.screen.blit(scaled_card, ((WIN_W-sw)//2, (WIN_H-sh)//2))

    def _menu_backdrop(self, dim=210):
        self.screen.fill((14, 24, 19))
        self.screen.blit(self.menu_bg, (0, 0))
        ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA); ov.fill((8, 14, 10, dim)); self.screen.blit(ov, (0, 0))

    def _buttons_block(self, buttons):
        mx, my = self.display.to_logical(pygame.mouse.get_pos())
        for i, (rect, label, action) in enumerate(buttons):
            hover = rect.collidepoint(mx, my) or i == self.menu_sel
            self._panel(rect, fill=assets.UI_PANEL2 if hover else assets.UI_PANEL,
                        edge=assets.UI_GREEN if hover else assets.UI_EDGE, w=2)
            t = self.txt(self.f_md, label, assets.UI_INK)
            self.screen.blit(t, (rect.centerx-t.get_width()//2, rect.centery-t.get_height()//2))

    def _draw_menu(self):
        self._menu_backdrop()
        title = self.txt(self.f_big, "ХРАНИТЕЛИ СТОЛБОВ", assets.UI_GREEN)
        self.screen.blit(title, (WIN_W//2-title.get_width()//2, 46))
        sub = self.txt(self.f_sm, "экотропа «Столбы» · природный парк «Ленские столбы»", assets.UI_FAINT)
        self.screen.blit(sub, (WIN_W//2-sub.get_width()//2, 86))
        self.screen.blit(self.logo, (WIN_W//2-self.logo.get_width()//2, 114))
        self._buttons_block(self._menu_buttons())
        hint = self.txt(self.f_xs, "стрелки/мышь — выбор · Enter/E — подтвердить", assets.UI_FAINT)
        self.screen.blit(hint, (WIN_W//2-hint.get_width()//2, WIN_H-30))

    def _draw_settings(self):
        self._menu_backdrop(dim=225)
        title = self.txt(self.f_big, "НАСТРОЙКИ", assets.UI_GREEN)
        self.screen.blit(title, (WIN_W//2-title.get_width()//2, 80))
        mx, my = self.display.to_logical(pygame.mouse.get_pos())
        for i, row in enumerate(self._settings_items()):
            sel = i == self.menu_sel or row["rect"].collidepoint((mx, my))
            if row["kind"] == "slider":
                self._draw_slider(row, sel)
            else:
                rect = row["rect"]
                self._panel(rect, fill=assets.UI_PANEL2 if sel else assets.UI_PANEL,
                            edge=assets.UI_GREEN if sel else assets.UI_EDGE, w=2)
                t = self.txt(self.f_md, row["label"], assets.UI_INK)
                self.screen.blit(t, (rect.centerx-t.get_width()//2, rect.centery-t.get_height()//2))
        hint = self.txt(self.f_xs, "←/→ — громкость · Enter/E — выбор · F11 — фуллскрин", assets.UI_FAINT)
        self.screen.blit(hint, (WIN_W//2-hint.get_width()//2, WIN_H-30))

    def _draw_slider(self, row, sel):
        rect = row["rect"]
        on = self.sound_on
        val = getattr(self, row["key"])
        self._panel(rect, fill=assets.UI_PANEL2 if sel else assets.UI_PANEL,
                    edge=assets.UI_GREEN if sel else assets.UI_EDGE, w=2)
        lab = self.txt(self.f_md, row["label"], assets.UI_INK if on else assets.UI_FAINT)
        self.screen.blit(lab, (rect.x+14, rect.centery-lab.get_height()//2))
        track = self._slider_track(rect)
        pygame.draw.rect(self.screen, (14, 24, 19), track)
        pygame.draw.rect(self.screen, assets.UI_EDGE, track, 1)
        fw = int(track.width * val)
        if fw > 0:
            pygame.draw.rect(self.screen, assets.UI_GREEN if on else assets.UI_EDGE,
                             (track.x, track.y, fw, track.height))
        knob = pygame.Rect(track.x+fw-4, track.y-5, 8, track.height+10)
        pygame.draw.rect(self.screen, assets.UI_INK if on else assets.UI_FAINT, knob)
        pct = self.txt(self.f_sm, f"{int(round(val*100))}%", assets.UI_INK if on else assets.UI_FAINT)
        self.screen.blit(pct, (track.right+12, rect.centery-pct.get_height()//2))

    def run(self):
        print("Меню: стрелки/мышь — выбор, Enter/E — подтвердить")
        print("Игра: WASD/стрелки — ходьба · E — действие/поговорить/сесть верхом · M — карта · Tab — статистика · "
              "B — энциклопедия · F11 — фуллскрин · Esc — назад")
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.1)
            self.t += dt
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                elif e.type == pygame.VIDEORESIZE:
                    self.display.resized((e.w, e.h))
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_RETURN and e.mod & pygame.KMOD_ALT:
                        self._on_key(pygame.K_F11)
                    else:
                        self._on_key(e.key)
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self._on_click(e.pos)
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    self._drag_key = None
                elif e.type == pygame.MOUSEMOTION and self.state in ("menu", "settings", "play", "book"):
                    self._on_hover(e.pos)
                elif e.type == pygame.MOUSEWHEEL and self.state == "book":
                    self.book.on_wheel(e.y)
            if self.state == "quit":
                return
            self._sync_display()
            if self.state == "play":
                self.update(dt)
            self.draw()
            self.display.present()

    def _stand_near(self, t):
        for (dc, dr, face) in ((0, 1, "up"), (-1, 0, "right"), (1, 0, "left"), (0, -1, "down")):
            x, y = (t.c+dc)*TILE + 2, (t.r+dr)*TILE + 2
            if not self._collide(x, y):
                self.px, self.py, self.face = x, y, face
                return
        self.px, self.py, self.face = t.c*TILE + 2, (t.r+1)*TILE + 2, "up"

    def shot(self, path):
        self.state = "play"
        t = self.world.triggers[0]
        self._stand_near(t)
        self.update()
        self.draw()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        pygame.image.save(self.screen, path)
        print("saved", path)
        random.seed(3)
        self.near = t
        self.act()
        for _ in range(30):
            self.update(1/60)
        self.draw()
        cp = path.replace(".png", "_card.png")
        pygame.image.save(self.screen, cp)
        print("saved", cp)


class _PlantRef:
    
    def __init__(self, cell, plant):
        self.r, self.c = cell
        self.plant = plant
        self.resolved = True


def main():
    try:  # кириллица в консоли Windows
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    g = Game()
    if SHOT:
        g.shot(SHOT)
    else:
        g.run()
    pygame.quit()


if __name__ == "__main__":
    main()
