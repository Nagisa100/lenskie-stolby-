"""
Скриншоты для презентации: стартовый экран, вход на карту, тропа, растение и карточка вида,
уборка мусора, миникарта, энциклопедия, название игры → screens/ (1920x1080).

    python tools/screens.py
"""
import os, sys
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOME)
os.chdir(HOME)
sys.argv = [sys.argv[0]]

import pygame
import main
import assets
from main import NpcLitter
from world import TILE

OUT = os.path.join(HOME, "screens")
SIZE = (1920, 1080)
DT = 1 / 60


class Keys:
    def __init__(self, *keys):
        self.keys = set(keys)

    def __getitem__(self, k):
        return k in self.keys


def snap(g, name, draw=True):
    if draw:
        g.draw()
    g.display.present()
    pygame.image.save(pygame.display.get_surface(), os.path.join(OUT, name))
    print("saved", name)


def frames(g, n, *keys):
    g.key_override = Keys(*keys)
    for _ in range(n):
        g.t += DT
        g.update(DT)
    g.key_override = Keys()


def put(g, r, c):
    g.px, g.py = c * TILE + 3, r * TILE + 2


def free_near(g, r, c):
    """свободная клетка рядом — для мусора"""
    for dr, dc in ((0, 2), (0, -2), (1, 2), (-1, 2), (2, 0), (0, 3)):
        cell = (r + dr, c + dc)
        if g.world.walkable(*cell) and cell not in g.world.water and not g.world.plant_at(cell):
            return cell
    return r, c + 1


def title(g):
    """название игры: логотип крупно на фоне карты"""
    g._menu_backdrop(dim=200)
    W, H = main.WIN_W, main.WIN_H
    big = pygame.font.Font(assets.FONT_PATH, 52)
    t = g.txt(big, "ХРАНИТЕЛИ СТОЛБОВ", assets.UI_GREEN)
    g.screen.blit(t, (W // 2 - t.get_width() // 2, 34))
    logo = pygame.transform.scale_by(g.logo, 2)
    g.screen.blit(logo, (W // 2 - logo.get_width() // 2, 104))
    sub = g.txt(g.f_md, "природный парк «Ленские столбы» · Якутия", assets.UI_INK)
    g.screen.blit(sub, (W // 2 - sub.get_width() // 2, 390))
    tag = g.txt(g.f_sm, "27 краснокнижных видов · туристы · сбежавшие лошади", assets.UI_FAINT)
    g.screen.blit(tag, (W // 2 - tag.get_width() // 2, 422))


def run():
    sys.stdout.reconfigure(encoding="utf-8")
    os.makedirs(OUT, exist_ok=True)
    g = main.Game()
    pygame.display.set_mode(SIZE)
    g._sync_display()
    g.event_t = g.escape_t = 1e9                   # без случайных событий
    w = g.world

    # 0–5 с: стартовый экран и вход на карту
    g.state = "menu"
    snap(g, "01_menu.png")
    g.state, g.started = "play", True
    frames(g, 30)
    snap(g, "02_start.png")

    # 5–13 с: движение по тропе — вверх, к реке со столбами
    top = min(r for (r, c) in w.path if r < w.PH)
    put(g, top + 3, w._center(top + 3))
    n = g.npcs[0]
    n.px, n.py, n.route, n.wait_t, n.face = w._center(top + 7) * TILE + 3, (top + 7) * TILE + 2, [], 99, "up"
    frames(g, 3)
    g.face, g.moving, g.walk_t = "up", True, 0.05      # кадр шага
    n.moving, n.walk_t = True, 0.3
    snap(g, "03_trail.png")

    # 13–22 с: находка растения и карточка вида
    t = next(tr for tr in w.triggers if tr.plant["name"] == "Лилия пенсильванская")
    g._stand_near(t)
    frames(g, 40)
    assert g.near is t, g.near
    snap(g, "04_plant.png")
    g.act()
    frames(g, 90)
    snap(g, "05_card.png")
    g._close_card(force=True)
    g.particles = []

    # 22–30 с: уборка мусора и миникарта
    r, c = min((p for p in w.path if p[0] > w.PH // 2 and p[0] < w.PH - 4), key=lambda p: (p[0], p[1]))
    put(g, r, c)
    lr, lc = free_near(g, r, c)
    litter = NpcLitter(lr, lc, 0)
    litter.age = 9.0
    g.npc_litters = [litter]
    put(g, lr, lc - 1)
    frames(g, 160)
    assert g.near is litter, g.near
    n.px, n.py, n.route, n.wait_t, n.face = (lc + 3) * TILE + 3, (lr + 1) * TILE + 2, [], 99, "right"
    n.moving, n.walk_t = True, 0.0                     # мусорщик уходит по тропе
    snap(g, "06_litter.png")
    g.act()
    frames(g, 8)
    snap(g, "07_litter_done.png")
    g.npc_litters = [NpcLitter(*free_near(g, p[0], p[1]), 1) for p in ((12, 20), (28, 30))]
    g.npcs[1].start_intent("litter", g)
    g.show_map = True
    snap(g, "08_minimap.png")
    g.show_map = False

    # энциклопедия: список, страница вида, наведение в статистике
    for name in ("Адонис сибирский", "Башмачок крупноцветковый", "Калипсо луковичная", "Кувшинка четырёхгранная"):
        g.species.add(name)
    g._open_book()
    snap(g, "10_book_list.png")
    g._close_book()
    g._open_book("Лилия пенсильванская")
    snap(g, "11_book_card.png")
    g._close_book()
    g.show_stats = True
    g.draw()                                           # прямоугольники иконок статистики
    g.stat_hover = "Лилия пенсильванская"
    snap(g, "12_stats_hover.png")
    g.show_stats, g.stat_hover = False, None

    # 30–35 с: название игры
    title(g)
    snap(g, "09_title.png", draw=False)
    pygame.quit()


if __name__ == "__main__":
    run()
