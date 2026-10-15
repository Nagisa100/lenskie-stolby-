import math
from world import TILE

HORSE_SPEED = 14.0
HORSE_RUN_SPEED = 21.0
HORSE_STEP_DT = 0.22
TRAMPLE_TIME = 2.6
CALM_TIME = 10.0
GRAZE_AFTER = (10.0, 16.0)
ESCAPED = ("leave", "escape", "trample", "roam", "calm", "ridden")
CAR_W, CAR_H = 24, 12
CAR_ACCEL, CAR_BRAKE = 60.0, 180.0
CAR_LOOK = 26
HONK_COOLDOWN = 3.5


class Horse:
    
    def __init__(self, world, variant, rnd):
        self.world, self.variant, self.rnd = world, variant, rnd
        r, c = self._pick(None) or world.gate
        self.x, self.y = c*TILE + 8.0, r*TILE + 12.0
        self.face = rnd.choice(("left", "right"))
        self.state = "graze"
        self.timer = rnd.uniform(1.0, 5.0)
        self.target = None
        self.walk_t = 0.0
        self.route = []
        self.goal = None  # куда идёт сбежавшая лошадь
        self.out_t = 0.0

    @property
    def escaped(self):
        return self.state in ESCAPED

    def cell(self):
        return int(self.y) // TILE, int(self.x) // TILE

    def _free(self, r, c):
        return self.world.walkable(r, c) and (r, c) not in self.world.water

    def _clear(self, tx, ty):
        steps = max(1, int(math.hypot(tx - self.x, ty - self.y) / 3))
        for i in range(1, steps + 1):
            x = self.x + (tx - self.x) * i / steps
            y = self.y + (ty - self.y) * i / steps
            if not self._free(int(y) // TILE, int(x) // TILE) or (int(y) // TILE, int(x) // TILE) not in self.world.pen:
                return False
        return True

    def _pick(self, here):
        
        pen = sorted(self.world.pen)
        for _ in range(24):
            if here is None:
                r, c = self.rnd.choice(pen)
            else:
                r = int(self.y) // TILE + self.rnd.randint(-3, 3)
                c = int(self.x) // TILE + self.rnd.randint(-3, 3)
                if (r, c) not in self.world.pen:
                    continue
            if self._free(r, c) and (here is None or self._clear(c*TILE + 8, r*TILE + 12)):
                return r, c
        return None

    def _move(self, tx, ty, speed, dt):
        
        dx, dy = tx - self.x, ty - self.y
        dist = math.hypot(dx, dy)
        step = speed * dt
        self.walk_t += dt
        if abs(dx) > 0.3:
            self.face = "right" if dx > 0 else "left"
        if dist <= step:
            self.x, self.y = tx, ty
            return True
        self.x += dx / dist * step
        self.y += dy / dist * step
        return False

    def escape(self):
        
        w = self.world
        path = w.route(self.cell(), lambda p: p == w.gate_out, lambda r, c: self._free(r, c), 40)
        self.route = path or [w.gate_out]
        self.state, self.goal, self.out_t = "leave", None, 0.0

    def _seek(self, plants):
        
        w = self.world
        cells = {(r, c) for (r, c, _) in plants if (r, c) not in w.water}
        path = w.route(self.cell(), lambda p: p in cells, self._free, 60)
        if path:
            self.route, self.goal, self.state = path, path[-1], "escape"
        else:
            self.state, self.timer, self.goal = "roam", self.rnd.uniform(2.0, 4.0), None

    def update(self, dt, plants=()):
        
        if self.state == "ridden":
            return None
        if self.escaped:
            self.out_t += dt
        if self.state in ("leave", "escape", "roam") and self.route:
            r, c = self.route[0]
            if self._move(c*TILE + 8, r*TILE + 12, HORSE_RUN_SPEED, dt):
                self.route.pop(0)
            if self.route:
                return None
            if self.state == "leave":
                self._seek(plants)
                return ("left", None)
            if self.state == "escape":
                if any((r, c) == self.goal for (r, c, _) in plants):
                    self.state, self.timer = "trample", TRAMPLE_TIME
                    return ("trample", self.goal)
                self._seek(plants)  # растения нет — ищем следующее
            return None
        if self.state == "trample":
            self.walk_t += dt
            self.timer -= dt
            if self.timer <= 0:
                # вытоптала — пасётся, потом к следующему
                cell, self.goal = self.goal, None
                self.state, self.timer, self.route = "roam", self.rnd.uniform(*GRAZE_AFTER), []
                return ("trampled", cell)
            return None
        if self.state in ("roam", "calm"):
            self.walk_t = 0.0
            self.timer -= dt
            if self.timer <= 0:
                self._seek(plants)
                if self.state == "roam":  # растений нет — бродит
                    r, c = self.cell()
                    step = self.rnd.choice(((0, 1), (0, -1), (1, 0), (-1, 0)))
                    if self._free(r + step[0], c + step[1]):
                        self.route = [(r + step[0], c + step[1])]
            return None
        self._update_pen(dt)
        return None

    def _update_pen(self, dt):
        if self.state == "walk":
            if self._move(*self.target, HORSE_SPEED, dt):
                self.state = self.rnd.choice(("graze", "graze", "stand"))
                self.timer = self.rnd.uniform(4.0, 10.0)
            return
        self.walk_t = 0.0
        self.timer -= dt
        if self.timer <= 0:
            cell = self._pick(True)
            if cell:
                self.target = (cell[1]*TILE + 8 + self.rnd.uniform(-3, 3), cell[0]*TILE + 12)
                self.state = "walk"
            else:
                self.timer = 2.0

    def mount(self):
        self.state, self.route, self.goal = "ridden", [], None

    def dismount(self, x, y, face):
        
        self.x, self.y = x, y
        self.face = face if face in ("left", "right") else self.face
        self.state, self.timer, self.route = "calm", CALM_TIME, []

    def go_home(self):
        
        w = self.world
        inside = min(w.pen, key=lambda p: abs(p[0] - w.gate[0]) + abs(p[1] - w.gate[1]))
        self.x, self.y = inside[1]*TILE + 8.0, inside[0]*TILE + 12.0
        self.state, self.timer, self.route, self.goal = "stand", 3.0, [], None

    def hop(self):
        
        return -1 if self.state == "trample" and int(self.walk_t / 0.12) % 2 else 0

    def frame(self):
        
        if self.state == "trample":
            return 1 + int(self.walk_t / 0.12) % 2
        if self.state == "walk" or (self.state in ("leave", "escape", "roam") and self.route):
            return 1 + int(self.walk_t / HORSE_STEP_DT) % 2
        if self.state == "graze" or (self.state == "roam" and not self.route):
            return 0 if int(self.timer * 0.7) % 5 == 0 else 3
        return 0


class Car:
    
    def __init__(self, lane_r, direction, x, color, speed):
        self.dir = direction
        self.x = float(x)
        self.y = lane_r*TILE + 2.0
        self.color = color
        self.cruise = speed
        self.speed = speed
        self.wheel_t = 0.0
        self.honk_cd = 0.0

    def rect(self):
        return (self.x + 3, self.y + 2, CAR_W - 6, CAR_H - 3)

    def _ahead(self, box):
        bx, by, bw, bh = box
        if by + bh <= self.y or by >= self.y + CAR_H:
            return False
        if self.dir > 0:
            front = self.x + CAR_W
            return bx + bw > front - 2 and bx < front + CAR_LOOK
        return bx < self.x + 2 and bx + bw > self.x - CAR_LOOK

    def update(self, dt, player_box, cars, map_w):
        
        by_player = self._ahead(player_box)
        blocked = by_player or any(o is not self and o.dir == self.dir and self._ahead(o.rect()) for o in cars)
        target = 0.0 if blocked else self.cruise
        if self.speed > target:
            self.speed = max(target, self.speed - CAR_BRAKE * dt)
        else:
            self.speed = min(target, self.speed + CAR_ACCEL * dt)
        self.x += self.dir * self.speed * dt
        if self.dir > 0 and self.x > map_w + 30:
            self.x = -CAR_W - 30
        elif self.dir < 0 and self.x < -CAR_W - 30:
            self.x = map_w + 30
        self.wheel_t += self.speed * dt
        self.honk_cd = max(0.0, self.honk_cd - dt)
        if by_player and self.speed < 5 and self.honk_cd <= 0:
            self.honk_cd = HONK_COOLDOWN
            return True
        return False

    def frame(self):
        return int(self.wheel_t / 3) % 2
