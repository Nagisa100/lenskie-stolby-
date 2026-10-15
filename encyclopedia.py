import math
import pygame
import assets
import plants_art
from species import SPECIES, KIND_ORDER, KINDS, INFO_FIELDS, kind_info, zones, has_info

ORDER = sorted(SPECIES, key=lambda sp: KIND_ORDER.index(sp["kind"]))  # как в сетке статистики
MARGIN = 16             # от края кадра до панели
PAD = 14                # внутренний отступ панели
LIST_HEAD_H = 58
CARD_HEAD_H = 30
FOOT_H = 34
GROUP_H = 26
CELL_H, CELL_GAP, MIN_CELL_W = 46, 6, 280
ICON_W = 44
PORTRAIT_W, PORTRAIT_H, CAPTION_H = 150, 196, 22
ART_SCALE = 5
SCROLL_STEP = 40
BTN_H = 24
INK_DARK = (20, 16, 10)


class Encyclopedia:
    def __init__(self, game):
        self.g = game              # шрифты, панели, иконки и коллекция берём у игры
        self.view = "list"         # list / card
        self.origin = "menu"       # куда вернуться по Esc
        self.sel = 0               # вид в ORDER
        self.from_list = False     # карточку открыли из списка — Esc вернёт к нему
        self.list_scroll = 0
        self.scroll = 0
        self.hot = None            # под мышью: индекс вида или кнопка
        self.cells = []            # [(индекс, rect)] видимых ячеек с прошлого кадра
        self.buttons = []          # [(действие, rect)]
        self._pages = {}
        self._art = {}

    def found(self, sp):
        return sp["name"] in self.g.species

    def open(self, origin, name=None):
        
        self.origin = origin
        self.hot = None
        self.cells, self.buttons = [], []
        if name:
            self.sel = next(i for i, sp in enumerate(ORDER) if sp["name"] == name)
            self.view, self.from_list, self.scroll = "card", False, 0
        else:
            self.view = "list"
            self._reveal()

    

    def on_key(self, key):
        if key == pygame.K_b:
            return True
        if self.view == "list":
            if key == pygame.K_ESCAPE:
                return True
            if key in (pygame.K_LEFT, pygame.K_a):
                self._select(self.sel - 1)
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self._select(self.sel + 1)
            elif key in (pygame.K_UP, pygame.K_w):
                self._select_row(-1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self._select_row(1)
            elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                self._show_card(from_list=True)
            return False
        if key == pygame.K_ESCAPE:
            if not self.from_list:
                return True
            self._to_list()
        elif key == pygame.K_BACKSPACE:
            self._to_list()
        elif key in (pygame.K_LEFT, pygame.K_a):
            self._step(-1)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._step(1)
        elif key in (pygame.K_UP, pygame.K_w):
            self.scroll -= SCROLL_STEP
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.scroll += SCROLL_STEP
        elif key == pygame.K_PAGEUP:
            self.scroll -= self._card_view().h - SCROLL_STEP
        elif key == pygame.K_PAGEDOWN:
            self.scroll += self._card_view().h - SCROLL_STEP
        elif key == pygame.K_HOME:
            self.scroll = 0
        elif key == pygame.K_END:
            self.scroll = 10**6
        self.scroll = max(0, self.scroll)
        return False

    def on_click(self, pos):
        for action, rect in self.buttons:
            if rect.collidepoint(pos):
                return self._press(action)
        if self.view == "list":
            for i, rect in self.cells:
                if rect.collidepoint(pos):
                    self.sel = i
                    self._show_card(from_list=True)
                    return False
        return False

    def on_hover(self, pos):
        
        self.hot = None
        for action, rect in self.buttons:
            if rect.collidepoint(pos):
                self.hot = action
                return True
        if self.view == "list":
            for i, rect in self.cells:
                if rect.collidepoint(pos):
                    self.hot = i
                    return True
        return False

    def on_wheel(self, dy):
        if self.view == "list":
            self.list_scroll = max(0, self.list_scroll - dy * SCROLL_STEP)
        else:
            self.scroll = max(0, self.scroll - dy * SCROLL_STEP)

    def _press(self, action):
        self.g._play(self.g.snd_click)
        if action == "close":
            return True
        if action == "list":
            self._to_list()
        elif action in ("prev", "next"):
            self._step(-1 if action == "prev" else 1)
        return False

    def _select(self, i):
        self.sel = i % len(ORDER)
        self._reveal()
        self.g._play(self.g.snd_click)

    def _select_row(self, d):
        
        cells = self._list_layout()[1]
        cur = cells[self.sel]
        cand = [(abs(r.y - cur.y), abs(r.x - cur.x), i) for i, r in enumerate(cells) if (r.y - cur.y) * d > 0]
        if cand:
            self._select(min(cand)[2])

    def _show_card(self, from_list):
        self.view, self.from_list, self.scroll = "card", from_list, 0
        self.g._play(self.g.snd_page)

    def _to_list(self):
        self.view, self.from_list = "list", False
        self._reveal()
        self.g._play(self.g.snd_page)

    def _step(self, d):
        """соседний вид в карточке"""
        self.sel = (self.sel + d) % len(ORDER)
        self.scroll = 0
        self.g._play(self.g.snd_page)

    def _reveal(self):
        
        view, cells, _, content_h = self._list_layout()
        r = cells[self.sel]
        if r.top - GROUP_H < self.list_scroll:
            self.list_scroll = r.top - GROUP_H
        elif r.bottom + 4 > self.list_scroll + view.h:
            self.list_scroll = r.bottom + 4 - view.h
        self.list_scroll = max(0, min(self.list_scroll, content_h - view.h))

    # раскладка

    def _panel_rect(self):
        w, h = self.g.screen.get_size()
        return pygame.Rect(MARGIN, MARGIN, w - 2*MARGIN, h - 2*MARGIN)

    def _list_layout(self):
        
        panel = self._panel_rect()
        view = pygame.Rect(panel.x + PAD, panel.y + LIST_HEAD_H, panel.w - 2*PAD - 8, panel.h - LIST_HEAD_H - FOOT_H)
        cols = max(2, view.w // MIN_CELL_W)
        cw = (view.w - (cols - 1)*CELL_GAP) // cols
        cells, heads, y = [None] * len(ORDER), [], 0
        for kind in KIND_ORDER:
            idx = [i for i, sp in enumerate(ORDER) if sp["kind"] == kind]
            if not idx:
                continue
            heads.append((kind, y, sum(self.found(ORDER[i]) for i in idx), len(idx)))
            y += GROUP_H
            for k, i in enumerate(idx):
                r, c = divmod(k, cols)
                cells[i] = pygame.Rect(c*(cw + CELL_GAP), y + r*(CELL_H + CELL_GAP), cw, CELL_H)
            y += math.ceil(len(idx) / cols) * (CELL_H + CELL_GAP) + 4
        return view, cells, heads, y

    def _frame_rect(self):
        panel = self._panel_rect()
        return pygame.Rect(panel.x + PAD, panel.y + CARD_HEAD_H + 12, PORTRAIT_W, PORTRAIT_H)

    def _card_text_x(self):
        panel, frame = self._panel_rect(), self._frame_rect()
        return frame.right + 16, panel.right - PAD - 8 - (frame.right + 16)

    def _card_view(self, top=None):
        
        panel, frame = self._panel_rect(), self._frame_rect()
        x, w = self._card_text_x()
        top = frame.y + 50 if top is None else top
        return pygame.Rect(x, top, w, panel.bottom - FOOT_H - 6 - top)

    def _close_rect(self, panel, y, h):
        return pygame.Rect(panel.right - 8 - h, y, h, h)

    # отрисовка

    def draw(self, surf):
        self.buttons = []
        if self.view == "list":
            self._draw_list(surf)
        else:
            self._draw_card(surf)

    def _button(self, surf, action, rect, label, font=None):
        g = self.g
        hot = self.hot == action
        g._panel(rect, fill=assets.UI_PANEL2 if hot else assets.UI_PANEL,
                 edge=assets.UI_GREEN if hot else assets.UI_EDGE, w=2 if hot else 1, surf=surf)
        t = g.txt(font or g.f_sm, label, assets.UI_INK)
        surf.blit(t, (rect.centerx - t.get_width()//2, rect.centery - t.get_height()//2))
        self.buttons.append((action, rect))

    def _draw_list(self, surf):
        g = self.g
        panel = self._panel_rect()
        g._panel(panel, w=3, surf=surf)
        n = sum(self.found(sp) for sp in ORDER)
        surf.blit(g.txt(g.f_md, "ЭНЦИКЛОПЕДИЯ ВИДОВ", assets.UI_GREEN), (panel.x + PAD, panel.y + 10))
        sub = f"Красная книга Республики Саха (Якутия) · найдено {n}/{len(ORDER)}"
        surf.blit(g.txt(g.f_xs, sub, assets.UI_FAINT), (panel.x + PAD, panel.y + 34))
        self._button(surf, "close", self._close_rect(panel, panel.y + 10, 26), "✕")

        view, cells, heads, content_h = self._list_layout()
        self.list_scroll = max(0, min(self.list_scroll, content_h - view.h))
        surf.set_clip(view)
        for kind, y, found, total in heads:
            yy = view.y + y - self.list_scroll
            t = g.txt(g.f_sm, f"{KINDS[kind]['plural'].upper()} · {found}/{total}", assets.UI_AMBER)
            surf.blit(t, (view.x + 2, yy + 4))
            pygame.draw.line(surf, assets.UI_EDGE, (view.x + t.get_width() + 12, yy + 12), (view.right - 2, yy + 12))
        self.cells = []
        for i, r in enumerate(cells):
            rect = r.move(view.x, view.y - self.list_scroll)
            if rect.bottom > view.y and rect.top < view.bottom:
                self._draw_cell(surf, i, rect)
                self.cells.append((i, rect.clip(view)))
        surf.set_clip(None)
        self._scrollbar(surf, view, content_h, self.list_scroll)
        hint = "стрелки — выбор · Enter/E — открыть · колесо — прокрутка · Esc — назад"
        surf.blit(g.txt(g.f_xs, hint, assets.UI_FAINT), (panel.x + PAD, panel.bottom - FOOT_H + 10))

    def _draw_cell(self, surf, i, rect):
        g = self.g
        sp = ORDER[i]
        found = self.found(sp)
        sel, hot = i == self.sel, i == self.hot
        g._panel(rect, fill=assets.UI_PANEL2 if sel or hot else assets.UI_PANEL,
                 edge=assets.UI_GREEN if sel else (assets.UI_FAINT if hot else assets.UI_EDGE),
                 w=2 if sel else 1, surf=surf)
        icon = g.plant_icon[sp["name"]][0 if found else 1]
        surf.blit(icon, (rect.x + 4 + (ICON_W - icon.get_width())//2, rect.centery - icon.get_height()//2))
        tx = rect.x + 6 + ICON_W
        name = self._fit(g.f_sm, sp["name"], rect.right - 8 - tx)
        surf.blit(g.txt(g.f_sm, name, assets.UI_INK if found else assets.UI_FAINT), (tx, rect.y + 6))
        status, col = ("✓ найден", assets.UI_GREEN) if found else ("не найден", assets.UI_FAINT)
        surf.blit(g.txt(g.f_xs, status, col), (tx, rect.y + 26))

    def _draw_card(self, surf):
        g = self.g
        sp = ORDER[self.sel]
        found = self.found(sp)
        panel = self._panel_rect()
        accent = assets.UI_AMBER if found else assets.UI_EDGE
        g._panel(panel, edge=accent, w=3, surf=surf)
        pygame.draw.rect(surf, accent, (panel.x, panel.y, panel.w, CARD_HEAD_H))
        ink = INK_DARK if found else assets.UI_INK
        t = g.txt(g.f_sm, f"ЭНЦИКЛОПЕДИЯ · {kind_info(sp)['label'].upper()}", ink)
        surf.blit(t, (panel.x + PAD, panel.y + (CARD_HEAD_H - t.get_height())//2))
        close = self._close_rect(panel, panel.y + 3, CARD_HEAD_H - 6)
        num = g.txt(g.f_sm, f"{self.sel + 1} / {len(ORDER)}", ink)
        surf.blit(num, (close.x - 12 - num.get_width(), panel.y + (CARD_HEAD_H - num.get_height())//2))
        self._button(surf, "close", close, "✕")

        # слева: портрет, значки Красной книги, сезон и зона
        frame = self._frame_rect()
        g._panel(frame, fill=(36, 64, 47), surf=surf)
        art = self._art_surf(sp, found)
        bob = int(round(2*math.sin(g.t*3))) if found else 0
        art_h = frame.h - CAPTION_H
        surf.blit(art, (frame.centerx - art.get_width()//2, frame.y + (art_h - art.get_height())//2 + bob))
        cap, col = ("✓ найден", assets.UI_GREEN) if found else ("не найден", assets.UI_FAINT)
        cs = g.txt(g.f_xs, cap, col)
        surf.blit(cs, (frame.centerx - cs.get_width()//2, frame.bottom - CAPTION_H + (CAPTION_H - cs.get_height())//2 - 1))
        pygame.draw.line(surf, assets.UI_EDGE, (frame.x + 6, frame.bottom - CAPTION_H), (frame.right - 7, frame.bottom - CAPTION_H))
        y = frame.bottom + 10
        if found:
            for tag in sp["rb"]:
                s = g.txt(g.f_xs, tag, assets.UI_RED)
                g._panel((frame.x, y, s.get_width() + 12, 20), fill=(42, 20, 15), edge=assets.UI_RED, w=1, surf=surf)
                surf.blit(s, (frame.x + 6, y + (20 - s.get_height())//2))
                y += 26
            y += 2
            for line in (f"{kind_info(sp)['season']}: {sp['season']}", "зона: " + ", ".join(zones(sp))):
                y += g._wrap(line, frame.x, y, frame.w, g.f_xs, assets.UI_FAINT, surf=surf) + 6

        # справа: название и прокручиваемый текст
        x, w = self._card_text_x()
        y = frame.y - 2
        for s in g._wrap_lines(sp["name"], w, g.f_md):
            surf.blit(g.txt(g.f_md, s, assets.UI_GREEN if found else assets.UI_INK), (x, y))
            y += g.f_md.get_height() + 2
        if found:
            surf.blit(g.txt(g.f_it, sp["lat"], assets.UI_FAINT), (x, y))
            y += g.f_it.get_height() + 2
            names = [n for n in (sp.get("alt") and "в народе — " + sp["alt"],
                                 sp.get("other_names") and "также: " + sp["other_names"]) if n]
            for n in names:
                y += g._wrap(n, x, y, w, g.f_xs, assets.UI_FAINT, surf=surf) + 2
        y += 8
        pygame.draw.line(surf, assets.UI_EDGE, (x, y - 4), (x + w, y - 4))
        view = self._card_view(y)
        page = self._page(sp, found, w)
        self.scroll = max(0, min(self.scroll, page.get_height() - view.h))
        surf.blit(page, view.topleft, pygame.Rect(0, self.scroll, w, view.h))
        self._scrollbar(surf, view, page.get_height(), self.scroll)

        # низ: соседние виды и подсказка
        by = panel.bottom - FOOT_H + 5
        bx = panel.x + PAD
        for action, label, bw in (("prev", "◀", 36), ("list", "К списку", 96), ("next", "▶", 36)):
            self._button(surf, action, pygame.Rect(bx, by, bw, BTN_H), label)
            bx += bw + 6
        hint = g.txt(g.f_xs, "←/→ — соседний вид · ↑/↓, колесо — прокрутка · Esc — назад", assets.UI_FAINT)
        surf.blit(hint, (max(bx + 8, panel.right - PAD - hint.get_width()), by + (BTN_H - hint.get_height())//2))

    def _page(self, sp, found, w):
        
        key = (sp["name"], found, w)
        if key in self._pages:
            return self._pages[key]
        g = self.g
        items = []  # (шрифт, текст, цвет, отступ после)
        if found:
            for field, label in INFO_FIELDS:
                if has_info(sp[field]):
                    items.append((g.f_xs, (label or kind_info(sp)["timing"]).upper(), assets.UI_AMBER, 3))
                    items.append((g.f_sm, sp[field], assets.UI_INK, 12))
            items.append((g.f_xs, f"Источник: Красная книга РС(Я), т. 1, 2017, с. {sp['rb_page']}.", assets.UI_FAINT, 0))
        else:
            items.append((g.f_sm, "Вид ещё не найден. Ищи его на экотропе: убери мусор рядом с ним или "
                                  "останови туриста, который хочет его сорвать. После находки здесь "
                                  "откроется описание из Красной книги.", assets.UI_FAINT, 12))
            items.append((g.f_xs, "ГДЕ ИСКАТЬ", assets.UI_AMBER, 3))
            items.append((g.f_sm, "зона: " + ", ".join(zones(sp)), assets.UI_INK, 0))
        blocks = [(font, g._wrap_lines(text, w, font), col, gap) for font, text, col, gap in items]
        h = sum(len(lines) * (font.get_height() + 2) + gap for font, lines, col, gap in blocks)
        page = pygame.Surface((w, max(1, h)), pygame.SRCALPHA)
        y = 0
        for font, lines, col, gap in blocks:
            for s in lines:
                page.blit(g.txt(font, s, col), (0, y))
                y += font.get_height() + 2
            y += gap
        self._pages[key] = page
        return page

    def _art_surf(self, sp, found):
        
        key = (sp["name"], found)
        if key not in self._art:
            im = plants_art.plant_sprite(sp, big=True, grey=not found)
            k = max(1, min(ART_SCALE, (PORTRAIT_W - 10) // im.width, (PORTRAIT_H - CAPTION_H - 10) // im.height))
            s = pygame.image.frombytes(im.tobytes(), im.size, "RGBA").convert_alpha()
            self._art[key] = pygame.transform.scale(s, (im.width * k, im.height * k))
        return self._art[key]

    def _scrollbar(self, surf, view, content_h, scroll):
        if content_h <= view.h:
            return
        track = pygame.Rect(view.right + 4, view.y, 4, view.h)
        pygame.draw.rect(surf, assets.UI_PANEL2, track)
        th = max(24, view.h * view.h // content_h)
        ty = view.y + (view.h - th) * scroll // (content_h - view.h)
        pygame.draw.rect(surf, assets.UI_FAINT, (track.x, ty, track.w, th))

    @staticmethod
    def _fit(font, text, w):
       
        if font.size(text)[0] <= w:
            return text
        while text and font.size(text + "…")[0] > w:
            text = text[:-1]
        return text + "…"
