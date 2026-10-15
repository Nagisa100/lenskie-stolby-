import math, random
from collections import deque
from world import TILE
from species import noun

NPC_SPEED = 33.0
NPC_STEP_DT = 0.15
INTENT_TIME = 3.0  # сколько висит «!» перед нарушением, с
FAIL_GRACE = 1.6  # время на вторую попытку
MAX_TRIES = 2
CALM_TIME = (45.0, 70.0)  # уговорённый турист не нарушает, с
PICK_REACH = 9  # как далеко турист отходит от тропы
NPC_LITTER_LIFETIME = 30.0

MOODS = {
    "friendly": dict(label="дружелюбный", hint="любит интересные факты"),
    "stubborn": dict(label="упрямый", hint="уважает только правила"),
    "hurry": dict(label="спешит", hint="лекции слушать некогда"),
}
TONES = ("info", "joke", "strict")
TONE_LABEL = {"info": "рассказать", "joke": "пошутить", "strict": "строго"}
# шанс убедить: характер × тон
CHANCE = {
    "friendly": {"info": 0.75, "joke": 0.6, "strict": 0.3},
    "stubborn": {"info": 0.35, "joke": 0.25, "strict": 0.7},
    "hurry": {"info": 0.25, "joke": 0.65, "strict": 0.45},
}
# поправка по виду нарушения
KIND_BONUS = {
    "pick": {"info": 0.10, "joke": 0.0, "strict": -0.05},
    "litter": {"info": -0.05, "joke": 0.0, "strict": 0.10},
    "offroad": {"info": 0.0, "joke": 0.10, "strict": 0.0},
}
TASTE = 0.15  # личные склонности туриста
LUCK = 0.12  # удача разговора
REPEAT = 0.5  # повтор тона слабее
CHANCE_MIN, CHANCE_MAX = 0.08, 0.9

INTENT_TITLE = {
    "litter": "ТУРИСТ ХОЧЕТ ВЫБРОСИТЬ ФАНТИК",
    "pick": "ТУРИСТ ХОЧЕТ СОРВАТЬ {noun}",
    "offroad": "ТУРИСТ ХОЧЕТ ПОЙТИ НАПРОЛОМ",
}
SAYS = {
    "litter": {"friendly": "Урны нигде нет — оставлю фантик тут, ладно?",
               "stubborn": "Все бросают — и я брошу.",
               "hurry": "Некогда искать урну, брошу тут!"},
    "pick": {"friendly": "Ой, красота! Возьму {noun} на память.",
             "stubborn": "Сорву {noun} — от одного не убудет.",
             "hurry": "Сорву {noun} по-быстрому и побегу."},
    "offroad": {"friendly": "Срежу через полянку — там так красиво!",
                "stubborn": "Тропа петляет, пойду напрямик.",
                "hurry": "Опаздываю — пойду напролом!"},
}
JOKE_PICK = {
    "flower": "Сорванный цветок завянет к вечеру, а фото с ним — навсегда. Давайте сфотографирую!",
    "shrub": "Красные «ягодки» хвойника — для фото, а не для кармана. Улыбочку!",
    "mushroom": "Этот гриб из Красной книги, а не из кулинарной. Суп из него — только в моём отчёте!",
    "moss": "Мох в кармане не приживётся — ему нужен свой камень. Пусть живёт дома!",
    "травку": "Эта травка живёт только на сырых скалах — в кармане ей конец. Давайте лучше фото!",
}
REPLY_OK = {"friendly": "Ой, не знал! Спасибо, не буду.",
            "stubborn": "Ладно-ладно, правила есть правила.",
            "hurry": "Ха, убедили! Бегу дальше по тропе."}
REPLY_FAIL = {"friendly": "Да ну, один разочек можно…",
              "stubborn": "Мне никто не указ!",
              "hurry": "Некогда мне слушать!"}


def intent_title(intent):
    t = INTENT_TITLE[intent["kind"]]
    return t.format(noun=noun(intent["plant"]).upper()) if intent.get("plant") else t


def tourist_line(npc):
    it = npc.intent
    line = SAYS[it["kind"]][npc.mood]
    return line.format(noun=noun(it["plant"])) if it.get("plant") else line


def ranger_options(npc, rng=random):
    """три ответа рейнджера: рассказать, пошутить, строго"""
    it = npc.intent
    sp = it.get("plant")
    if it["kind"] == "pick":
        info = f"Это {sp['name']} из Красной книги Якутии. {sp['fact']}"
        joke = JOKE_PICK.get(noun(sp)) or JOKE_PICK.get(sp["kind"], JOKE_PICK["flower"])
        what = "грибов" if sp["kind"] == "mushroom" else ("мхов" if sp["kind"] == "moss" else "растений")
        strict = rng.choice((f"Сбор краснокнижных {what} в парке запрещён — за это штраф. Оставьте, пожалуйста.",
                             "Стоп! Это охраняемый вид, трогать нельзя — это нарушение режима парка."))
    elif it["kind"] == "offroad":
        info = (f"За тропой растёт {sp['name']} — вид из Красной книги. "
                f"Угроза для него — {sp['threat'].lower()}." if sp else
                "За тропой растут краснокнижные виды — один шаг может погубить точку роста.")
        joke = rng.choice(("Напролом через луг ходят только лоси. Вы же не лось? Тропа ведёт туда же!",
                           "Короткий путь через цветы — самый долгий: объясняться со мной дольше!"))
        strict = rng.choice(("Сходить с экотропы запрещено правилами парка. Вернитесь, пожалуйста.",
                             "Дальше нельзя: за тропой — охраняемые растения. Назад на тропу!"))
    else:
        info = "На холоде мусор разлагается очень медленно и годами лежит у тропы. Заберите с собой, пожалуйста."
        joke = rng.choice(("Столбам полмиллиарда лет — фантик им совсем не к лицу!",
                           "Белки здесь фантики не собирают — проверено. Придётся вам!"))
        strict = rng.choice(("Мусорить в парке запрещено — за это штраф. Уберите, пожалуйста.",
                             "Фантик — в карман, а не в траву. Таковы правила парка."))
    return [("info", info), ("joke", joke), ("strict", strict)]


def option_chance(npc, tone, luck=0.0):
    
    p = CHANCE[npc.mood][tone] + KIND_BONUS[npc.intent["kind"]][tone] + npc.taste[tone] + luck
    if tone in npc.tried:
        p *= REPEAT
    return max(CHANCE_MIN, min(CHANCE_MAX, p))


def dialog_options(npc, rng):
    
    opts = [(tone, text, option_chance(npc, tone, rng.uniform(-LUCK, LUCK)))
            for tone, text in ranger_options(npc, rng)]
    rng.shuffle(opts)
    return opts


def persuade(chance, rng):
    
    return rng.random() < chance


class NpcLitter:
    
    def __init__(self, r, c, variant=0):
        self.r, self.c = r, c
        self.title = "!  ТУРИСТ ОСТАВИЛ МУСОР"
        self.resolved = False
        self.age = 0.0
        self.variant = variant

    def left(self):
        return NPC_LITTER_LIFETIME - self.age


class NPC:
    
    def __init__(self, c, r, variant, mood):
        self.px = c*TILE + 3
        self.py = r*TILE + 2
        self.face = random.choice(("down", "up", "left", "right"))
        self.moving = False
        self.walk_t = 0.0
        self.variant = variant
        self.mood = mood
        # свои склонности поверх характера
        self.taste = {t: random.uniform(-TASTE, TASTE) for t in TONES}
        self.tried = set()  # тоны, уже испробованные в разговоре
        self.route = []
        self.wait_t = random.uniform(0.4, 2.2)
        self.state = "walk"
        self.intent = None
        self.tries = 0
        self.calm_t = 0.0
        self.bubble = None           # ("heart" | "no", сколько ещё висит)
        self.cleanup = None  # мусор, который идёт подобрать

    def cell(self):
        return int(self.py + 10) // TILE, int(self.px + 5) // TILE

    @property
    def busy(self):
        return self.intent is not None or self.state in ("trample", "back") or self.cleanup is not None

    def update(self, dt, game):
        """событие для игры: act, trample или cleaned"""
        if self.bubble:
            self.bubble = (self.bubble[0], self.bubble[1] - dt) if self.bubble[1] > dt else None
        if self.calm_t > 0:
            self.calm_t -= dt
            if self.calm_t <= 0 and self.state == "calm":
                self.state = "walk"
        event = None
        if self.route:
            self._step(dt)
            if not self.route:
                event = self._arrived(game)
        else:
            self.moving = False
            if self.state == "intent" and not self.intent:
                self._go_back(game.world)
            elif self.state == "intent":
                self.intent["t"] -= dt
                if self.intent["t"] <= 0:
                    event = self._commit(game)
            elif self.state in ("walk", "calm"):
                self.wait_t -= dt
                if self.wait_t <= 0:
                    self._plan(game.world)
        self.walk_t = self.walk_t + dt if self.moving else 0.0
        return event

    def _step(self, dt):
        r, c = self.route[0]
        dx, dy = c*TILE + 3 - self.px, r*TILE + 2 - self.py
        dist = math.hypot(dx, dy)
        step = NPC_SPEED * dt
        if dist <= step:
            self.px, self.py = c*TILE + 3, r*TILE + 2
            self.route.pop(0)
            if not self.route:
                self.wait_t = random.uniform(1.2, 3.5)
        else:
            self.px += dx / dist * step
            self.py += dy / dist * step
        if dist > 0.01:
            self.face = ("left" if dx < 0 else "right") if abs(dx) > abs(dy) else ("up" if dy < 0 else "down")
        self.moving = True

    def _arrived(self, game):
        if self.state == "approach":  # дошёл до растения
            if not self.intent:
                self._go_back(game.world)
                return None
            self.state = "intent"
            pr, pc = self.intent["cell"]
            r, c = self.cell()
            self.face = ("left" if pc < c else "right") if pc != c else ("up" if pr < r else "down")
            return None
        if self.state == "trample":
            self._go_back(game.world)
            return ("trample", self.intent_cell_done)
        if self.cleanup is not None:
            litter, self.cleanup = self.cleanup, None
            self._go_back(game.world)
            return ("cleaned", litter)
        if self.state == "back":
            self.state = "calm" if self.calm_t > 0 else "walk"
        return None

    def _commit(self, game):
        
        it, self.intent = self.intent, None
        self.tries = 0
        if it["kind"] == "offroad":
            path = game.world.route(self.cell(), lambda p: p == it["cell"], game.world.walkable, PICK_REACH + 4)
            if path:
                self.state, self.route, self.intent_cell_done = "trample", path, it["cell"]
                return ("act", dict(it, kind="offroad_go"))
        self._go_back(game.world)
        return ("act", it)

    def start_intent(self, kind, game, target=None):
        
        self.route = []
        self.tries = 0
        self.tried = set()
        if kind == "litter" or target is None:
            self.intent = dict(kind="litter", t=INTENT_TIME, total=INTENT_TIME, cell=self.cell(), plant=None)
            self.state = "intent"
            return True
        r, c, sp = target
        self.intent = dict(kind=kind, t=INTENT_TIME, total=INTENT_TIME, cell=(r, c), plant=sp)
        if kind == "offroad":
            self.state = "intent"
            return True
        w = game.world
        near = lambda p: max(abs(p[0] - r), abs(p[1] - c)) == 1 and w.walkable(*p)
        path = w.route(self.cell(), near, w.walkable, PICK_REACH)
        if path is None:
            self.intent = None
            return False
        self.state, self.route = ("approach", path) if path else ("intent", [])
        return True

    def persuaded(self, game):
        
        self.intent = None
        self.tries = 0
        self.bubble = ("heart", 2.2)
        self.calm_t = random.uniform(*CALM_TIME)
        near = [l for l in game.npc_litters if not l.resolved
                and max(abs(l.r - self.cell()[0]), abs(l.c - self.cell()[1])) <= 6]
        if near:
            litter = min(near, key=lambda l: abs(l.r - self.cell()[0]) + abs(l.c - self.cell()[1]))
            path = game.world.route(self.cell(), lambda p: p == (litter.r, litter.c), game.world.walkable, 14)
            if path is not None:
                self.cleanup, self.route, self.state = litter, path, "calm"
                if not path:
                    self.route = [(litter.r, litter.c)]
                return
        self._go_back(game.world)

    def refused(self):
        
        self.tries += 1
        self.bubble = ("no", 1.6)
        if self.intent:
            self.intent["t"] = 0.0 if self.tries >= MAX_TRIES else min(self.intent["t"], FAIL_GRACE)
            if self.state == "approach":
                self.route, self.state = [], "intent"

    def _go_back(self, world):
        
        here = self.cell()
        if here in world.path:
            self.state = "calm" if self.calm_t > 0 else "walk"
            self.wait_t = random.uniform(0.8, 2.0)
            return
        path = world.route(here, lambda p: p in world.path, world.walkable, 40)
        self.route = path or []
        self.state = "back" if path else ("calm" if self.calm_t > 0 else "walk")

    def _plan(self, world):
        
        path = world.path
        start = self.cell()
        if start not in path:
            self._go_back(world)
            return
        prev, dist = {start: None}, {start: 0}
        q = deque([start])
        while q:
            cur = q.popleft()
            if dist[cur] >= 14:
                continue
            r, c = cur
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                n = (r+dr, c+dc)
                if n in prev or n not in path:
                    continue
                if dr and dc and ((r+dr, c) not in path or (r, c+dc) not in path):
                    continue
                prev[n], dist[n] = cur, dist[cur] + 1
                q.append(n)
        goals = [p for p, d in dist.items() if d >= 6]
        if not goals:
            self.wait_t = 1.0
            return
        goal, route = random.choice(goals), []
        while goal is not None:
            route.append(goal)
            goal = prev[goal]
        self.route = route[::-1][1:]

    def crouch(self):
        
        return self.state == "intent" and self.intent and self.intent["kind"] == "pick"

    def frame(self, surf):
        frames = surf[self.face]
        if not self.moving:
            return frames[0]
        return frames[(1, 0, 2, 0)[int(self.walk_t / NPC_STEP_DT) % 4]]
