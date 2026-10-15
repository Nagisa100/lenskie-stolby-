"""
Smoke-тест без окна: меню, ~600 кадров с вводом, туристы, лошади, карточки всех видов.
Скрины — в preview/.

    python tools/smoke.py            # всё
    python tools/smoke.py cards      # только карточки
    python tools/smoke.py book       # только энциклопедия
"""
import os, sys, random
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HOME)
os.chdir(HOME)
sys.argv = [sys.argv[0], "--shot"] + sys.argv[1:]  # окно офскрин

import pygame
import main
import audio
import tourists
import plants_art
from species import SPECIES, INFO_FIELDS, has_info
from encyclopedia import ORDER
from world import Trigger, TILE

PREVIEW = os.path.join(HOME, "preview")
DT = 1 / 60


class Keys:
    """«зажатые» клавиши для Game.key_override"""
    def __init__(self, *keys):
        self.keys = set(keys)

    def __getitem__(self, k):
        return k in self.keys


def save(g, name):
    path = os.path.join(PREVIEW, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pygame.image.save(g.screen, path)
    print("saved", os.path.relpath(path, HOME))


def frames(g, n, draw=True):
    for _ in range(n):
        g.t += DT
        g.update(DT)
        if draw:
            g.draw()


def place_player(g, r, c):
    """поставить игрока на свободную клетку рядом с (r, c)"""
    for dr, dc in ((1, 0), (0, -1), (0, 1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1), (0, 0)):
        x, y = (c + dc)*TILE + 3, (r + dr)*TILE + 2
        if not g._collide(x, y):
            g.px, g.py = x, y
            return
    raise AssertionError(f"некуда встать рядом с {(r, c)}")


def check_menus(g):
    g.state = "menu"
    g.draw()
    save(g, "menu.png")
    g._on_key(pygame.K_DOWN); g._on_key(pygame.K_RETURN)        # энциклопедия
    assert g.state == "book" and g.book.view == "list" and g.book.origin == "menu", g.state
    g.draw()
    g._on_key(pygame.K_ESCAPE)
    assert g.state == "menu", g.state
    g._on_key(pygame.K_DOWN); g._on_key(pygame.K_RETURN)
    assert g.state == "settings", g.state
    g._on_key(pygame.K_RIGHT); g._on_key(pygame.K_LEFT)       # ползунок музыки
    g._on_key(pygame.K_DOWN); g._on_key(pygame.K_LEFT)        # ползунок эффектов
    g.draw()
    save(g, "settings.png")
    g._on_key(pygame.K_ESCAPE)
    assert g.state == "menu"
    g.menu_sel = 0
    g._on_key(pygame.K_RETURN)
    assert g.state == "play"
    print("меню/настройки: ок")


def check_wander(g, n=600):
    """~600 кадров: ходьба, E, карта, статистика"""
    rnd = random.Random(7)
    dirs = [(), (pygame.K_d,), (pygame.K_a,), (pygame.K_w,), (pygame.K_s,), (pygame.K_d, pygame.K_s), (pygame.K_a, pygame.K_w)]
    for i in range(n):
        if i % 40 == 0:
            g.key_override = Keys(*rnd.choice(dirs))
        if i % 97 == 50:
            g._on_key(pygame.K_e)
        if i == 200:
            g._on_key(pygame.K_m)
        if i == 260:
            save(g, "minimap.png")
            g._on_key(pygame.K_m)
        if i == 320:
            g._on_key(pygame.K_TAB)
        if i == 360:
            g._on_key(pygame.K_TAB)
        if g.card and i % 20 == 0:
            g._on_key(pygame.K_ESCAPE)
        if g.dialog:
            g._on_key(pygame.K_ESCAPE)
        g.t += DT
        g.update(DT)
        g.draw()
    g.key_override = Keys()
    print(f"блуждание {n} кадров: ок · SAVE {g.saved} LOST {g.lost} XP {g.xp} видов {len(g.species)}")


def pick_scene(g, want_ok):
    """турист хочет сорвать растение, рейнджер уговаривает"""
    w = g.world
    npc = g.npcs[0]
    for other in g.npcs[1:]:
        other.intent = None
    land = [f for f in w.flowers if (f[0], f[1]) not in w.water and f[2]["kind"] == "flower"]
    for f in land:
        r, c, sp = f
        path_cells = [p for p in w.path if max(abs(p[0] - r), abs(p[1] - c)) <= 4]
        if not path_cells:
            continue
        pr, pc = min(path_cells, key=lambda p: abs(p[0] - r) + abs(p[1] - c))
        npc.px, npc.py, npc.route, npc.state, npc.intent = pc*TILE + 3, pr*TILE + 2, [], "walk", None
        if npc.start_intent("pick", g, f):
            break
    else:
        raise AssertionError("нет растения для сцены с туристом")
    for _ in range(600):                       # дойти до растения
        if npc.state == "intent":
            break
        npc.update(DT, g)
    assert npc.state == "intent", npc.state
    nr, nc = npc.cell()
    place_player(g, nr, nc)
    g.key_override = Keys()
    frames(g, 2)
    assert g.near is npc, f"рядом не турист: {g.near}"
    save(g, "tourist_intent.png")
    g._on_key(pygame.K_e)
    assert g.dialog, "диалог не открылся"
    g.draw()
    save(g, "dialog.png")
    # лучший или худший ответ по шансу
    opts = g.dialog["options"]
    assert all(tourists.CHANCE_MIN <= ch <= tourists.CHANCE_MAX for _, _, ch in opts)
    pick = max if want_ok else min
    idx = pick(range(len(opts)), key=lambda k: opts[k][2])
    g.rng = random.Random(1 if want_ok else 0)
    g.rng.random = (lambda: 0.0) if want_ok else (lambda: 0.999)   # исход детерминирован
    g.dialog["sel"] = idx
    g._on_key(pygame.K_e)
    ok, text, note = g.dialog["result"]
    assert ok == want_ok, (ok, text)
    g.draw()
    save(g, "dialog_ok.png" if want_ok else "dialog_fail.png")
    g._on_key(pygame.K_e)
    assert g.dialog is None
    return npc, (r, c, sp)


def check_tourists(g):
    lost0, saved0 = g.lost, g.saved
    npc, plant = pick_scene(g, want_ok=True)
    assert g.saved == saved0 + 1 and npc.intent is None and npc.state in ("calm", "back")
    frames(g, 1)
    assert g.card, "после уговоров нет карточки растения"
    g.card_t = 2.0
    g.draw()
    save(g, "card_saved_by_talk.png")
    g._close_card(force=True)
    assert w_has(g, plant), "уговорённый турист всё же сорвал растение"
    # две неудачи — растение сорвано
    npc, plant = pick_scene(g, want_ok=False)
    assert npc.intent and npc.tries == 1
    frames(g, 2)
    g._on_key(pygame.K_e)
    assert g.dialog, "второй попытки нет"
    g.dialog["sel"] = 0
    g._on_key(pygame.K_e)
    g._on_key(pygame.K_e)
    frames(g, 30)
    assert not w_has(g, plant), "растение не сорвано после двух неудач"
    assert g.lost >= lost0 + 1
    assert (plant[0], plant[1]) in g.trampled or (plant[0], plant[1]) in g.world.water
    frames(g, 5)
    save(g, "plant_lost.png")
    print(f"туристы: уговоры и срыв — ок · LOST {g.lost}")


def w_has(g, plant):
    return any((f[0], f[1]) == (plant[0], plant[1]) for f in g.world.flowers)


def check_director(g):
    """режиссёр запускает события"""
    started = 0
    g.event_t = 0.5
    seen = set()
    for i in range(80 * 60):
        g.t += DT
        g.update(DT)
        for n in g.npcs:
            if n.intent and id(n.intent) not in seen:
                seen.add(id(n.intent))
                started += 1
        if g.card:
            g._close_card(force=True)
        if g.dialog:
            g._close_dialog()
    assert started >= 2, started
    print(f"режиссёр туристов: {started} событий за 80 с")


def check_horses(g):
    w = g.world
    horse = g.horses[0]
    for h in g.horses:
        if h.escaped:
            h.go_home()
    g.riding = None
    flowers0 = len(w.flowers)
    lost0 = g.lost
    horse.escape()
    g.escapes += 1
    tramples = 0
    for _ in range(60 * 60):  # лошадь выходит и топчет
        g.t += DT
        ev = horse.update(DT, w.flowers)
        if ev and ev[0] == "trampled":
            g._destroy_plant(ev[1], "Лошадь вытоптала")
            tramples += 1
            if tramples >= 1:
                break
    assert tramples >= 1, f"лошадь ничего не вытоптала, состояние {horse.state}"
    assert len(w.flowers) == flowers0 - 1 and g.lost == lost0 + 1
    hr, hc = horse.cell()
    place_player(g, hr, hc)
    frames(g, 2)
    save(g, "horse_escaped.png")
    assert g.near is horse, f"рядом не лошадь: {g.near}"
    g._on_key(pygame.K_e)
    assert g.riding is horse and horse.state == "ridden"
    g.key_override = Keys(pygame.K_d)
    frames(g, 30)
    g.key_override = Keys()
    save(g, "riding.png")
    for d in ("down", "up", "left"):
        g.face = d
        g.moving = True
        g.draw()
    g.moving = False
    # слезть в поле
    g._on_key(pygame.K_e)
    assert g.riding is None and horse.state == "calm"
    frames(g, 2)
    g._on_key(pygame.K_e) if g.near is horse else None
    if g.riding is None:
        hr, hc = horse.cell()
        place_player(g, hr, hc)
        frames(g, 1)
        g._on_key(pygame.K_e)
    assert g.riding is horse
    # к воротам и вернуть
    gr, gc = w.gate_out
    g.px, g.py = gc*TILE + 3, (gr - 1)*TILE + 2
    if g._collide(g.px, g.py):
        g.px, g.py = gc*TILE + 3, gr*TILE + 2
    frames(g, 2)
    assert g.near == "gate", g.near
    save(g, "farm_gate.png")
    saved0 = g.saved
    g._on_key(pygame.K_e)
    assert g.riding is None and not horse.escaped and g.saved == saved0 + 1
    frames(g, 40)
    save(g, "farm.png")
    print("лошади: побег, топтание, верхом, слезть, возврат — ок")


def check_stats(g):
    for sp in SPECIES[::3]:
        g.species.add(sp["name"])
    g.found.append(SPECIES[0]["name"])
    g.show_stats = True
    g.draw()
    save(g, "stats.png")
    g.show_stats = False
    g.show_map = True
    g.npcs[1].start_intent("litter", g)
    g.draw()
    save(g, "minimap_threats.png")
    g.show_map = False


def check_species_info():
    """у каждого вида заполнены поля энциклопедии; пропуски — только явные «TODO эколог»"""
    todo = []
    for sp in SPECIES:
        assert isinstance(sp.get("rb_page"), int), sp["name"]
        for key, _ in INFO_FIELDS:
            assert isinstance(sp.get(key), str) and sp[key].strip(), f"{sp['name']}: нет поля {key}"
            if not has_info(sp[key]):
                todo.append(f"{sp['name']}.{key}")
    print(f"данные видов: {len(INFO_FIELDS)} полей × {len(SPECIES)} видов, TODO эколог: {len(todo)}")
    for t in todo:
        print("  TODO", t)


def check_book(g):
    """энциклопедия: список, карточка, прокрутка, соседние виды, мышь, переход из статистики"""
    g.state, g.card, g.dialog = "play", None, None
    g.show_stats = g.show_map = False
    g.particles = []
    found = "Адонис сибирский"
    for name in (found, "Лилия пенсильванская", "Хвойник односемянный"):
        g.species.add(name)
    grey = next(sp["name"] for sp in ORDER if sp["name"] not in g.species)

    # B в игре — список; клавиши и мышь
    g._on_key(pygame.K_b)
    assert g.state == "book" and g.book.view == "list" and g.book.origin == "play"
    g.book.sel = 0
    g.draw()
    save(g, "book_list.png")
    g._on_key(pygame.K_DOWN); g._on_key(pygame.K_RIGHT)
    assert g.book.sel != 0
    g.book.on_wheel(-3)
    g.draw()
    assert g.book.list_scroll > 0, "список не прокручивается"
    i, rect = g.book.cells[-1]
    g._on_hover(rect.center)
    assert g.book.hot == i and g._hand
    g._on_click(rect.center)
    assert g.book.view == "card" and g.book.sel == i and g.book.from_list
    g._on_key(pygame.K_ESCAPE)
    assert g.state == "book" and g.book.view == "list", "Esc из карточки не вернул к списку"

    # все страницы рисуются и не вылезают за ширину
    for k, sp in enumerate(ORDER):
        g.book.sel, g.book.view, g.book.scroll = k, "card", 0
        g.draw()
        w = g.book._card_text_x()[1]
        page = g.book._page(sp, sp["name"] in g.species, w)
        assert page.get_width() == w
    # найденный вид: прокрутка и соседи
    g.book.sel = next(k for k, sp in enumerate(ORDER) if sp["name"] == found)
    g.book.scroll = 0
    g.draw()
    save(g, "book_card.png")
    for _ in range(4):
        g._on_key(pygame.K_DOWN)
    g.book.on_wheel(-2)
    g.draw()
    assert g.book.scroll > 0, "текст карточки не прокручивается"
    save(g, "book_card_scrolled.png")
    g._on_key(pygame.K_RIGHT)
    assert g.book.scroll == 0 and ORDER[g.book.sel]["name"] != found
    g.book.sel = next(k for k, sp in enumerate(ORDER) if sp["name"] == grey)
    g.draw()
    save(g, "book_locked.png")
    g.book.on_click(dict(g.book.buttons)["next"].center)
    assert ORDER[g.book.sel]["name"] != grey
    g.book.on_click(dict(g.book.buttons)["list"].center)
    assert g.book.view == "list"
    g._on_key(pygame.K_ESCAPE)
    assert g.state == "play"

    # статистика: наведение и клик только по найденным
    g.show_stats = True
    g.draw()
    assert set(g.stat_icon_rects) == {sp["name"] for sp in SPECIES}
    g._on_hover(g.stat_icon_rects[grey].center)
    assert g.stat_hover is None and not g._hand, "серая иконка реагирует на наведение"
    g._on_click(g.stat_icon_rects[grey].center)
    assert g.state == "play", "серая иконка открыла энциклопедию"
    g._on_hover(g.stat_icon_rects[found].center)
    assert g.stat_hover == found and g._hand
    g.draw()
    save(g, "stats_hover.png")
    g._on_click(g.stat_icon_rects[found].center)
    assert g.state == "book" and g.book.view == "card" and not g.book.from_list
    assert ORDER[g.book.sel]["name"] == found
    g.draw()
    save(g, "book_from_stats.png")
    g._on_key(pygame.K_ESCAPE)
    assert g.state == "play" and g.show_stats, "Esc не вернул в статистику"
    # кнопки карты и статистики работают как раньше
    g._on_hover(g.stats_icon_rect.center)
    assert g.stat_hover is None and not g._hand
    g._on_click(g.map_icon_rect.center)
    assert g.show_map
    g._on_click(g.map_icon_rect.center)
    assert not g.show_map
    g._on_click(g.stats_icon_rect.center)
    assert not g.show_stats

    # карточка «новый вид» с подсказкой → B → страница вида
    sp = next(s for s in SPECIES if s["name"] == grey)
    g._collect(sp, Trigger((0, 0), "litter", sp, "", ""), main.XP["trigger"])
    g.card_t = 2.0
    g.particles = []
    g.draw()
    save(g, "card_new_hint.png")
    g._on_key(pygame.K_b)
    assert g.state == "book" and g.card is None and ORDER[g.book.sel]["name"] == grey
    g._on_key(pygame.K_ESCAPE)
    assert g.state == "play"
    print("энциклопедия: список, карточки, прокрутка, мышь, статистика → карточка — ок")


def check_cards(g):
    """карточки всех видов влезают в рамку"""
    g.state = "play"
    bad = []
    for i, sp in enumerate(SPECIES):
        H, blocks, fits = g._card_layout(sp)
        if not fits:
            bad.append(sp["name"])
        t = Trigger((0, 0), "litter", sp, "", "")
        new = i % 2 == 0
        g._open_card(t, new, main.XP["trigger"] + (main.XP["new_bonus"] if new else 0))
        g.card_t = 2.0
        g.particles = []
        g.draw()
        save(g, f"cards/{i + 1:02d}.png")
        g.card = None
    probs = plants_art.check_art()
    assert not probs, probs
    assert not bad, f"не влезает текст карточки: {bad}"
    print(f"карточки: {len(SPECIES)} видов, всё влезает")


def check_no_sound():
    """звук недоступен — игра всё равно идёт"""
    real = audio.setup
    audio.setup = lambda: False
    try:
        g = main.Game()
    finally:
        audio.setup = real
    assert not g.sound_on
    g.state = "play"
    g.key_override = Keys(pygame.K_d)
    frames(g, 120)
    g._activate("toggle_sound")
    assert not g.sound_on
    print("без звука: ок")


def main_smoke():
    random.seed(5)
    g = main.Game()
    assert len(SPECIES) == 27, len(SPECIES)
    assert not g.world.missing, g.world.missing
    which = sys.argv[2:] or ["all"]
    check_species_info()
    if "cards" in which or "all" in which:
        check_cards(g)
    if "book" in which:
        g.state = "play"
        check_book(g)
    if "all" in which or "play" in which:
        check_menus(g)
        check_wander(g)
        check_tourists(g)
        check_horses(g)
        check_director(g)
        check_stats(g)
        check_book(g)
        check_no_sound()
    pygame.quit()
    print("OK")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main_smoke()
