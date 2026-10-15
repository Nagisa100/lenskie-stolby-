import math, random
from collections import deque
from species import SPECIES, zones

TILE = 16

ZONE_RIVER = "Берег Лены"
ZONE_DUNES = "Тукулан"
ZONE_CORDON = "Кордон"
ZONE_TAIGA = "Тайга"
ZONE_DROUGHT = "Засуха"
ZONE_MEADOW = "Луга"
ZONE_VILLAGE = "Посёлок"
SOUTH_ROWS = 14  # рядов за дорогой

TREE_P = {ZONE_RIVER: 0.12, ZONE_DUNES: 0.08, ZONE_CORDON: 0.11, ZONE_TAIGA: 0.32, ZONE_DROUGHT: 0.10,
          ZONE_MEADOW: 0.09, ZONE_VILLAGE: 0.05}
EDGE_TREE_P = 0.42
ORANGE_P = {ZONE_RIVER: 0.10, ZONE_DUNES: 0.85, ZONE_CORDON: 0.15, ZONE_TAIGA: 0.12, ZONE_DROUGHT: 0.0,
            ZONE_MEADOW: 0.2, ZONE_VILLAGE: 0.3}
FLOWER_P = {ZONE_RIVER: 0.08, ZONE_DUNES: 0.07, ZONE_CORDON: 0.08, ZONE_TAIGA: 0.09, ZONE_DROUGHT: 0.03,
            ZONE_MEADOW: 0.09, ZONE_VILLAGE: 0.0}
WATER_PLANT_P = 0.10
MAX_PER_SPECIES = 6
# где может расти вид с данным habitat
HABITAT_OK = {"grass": {"grass"}, "sand": {"sand", "grass"}, "rock": {"rock"}, "tree": {"tree"}, "water": {"water"}}
STEPS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
STEPS8 = STEPS4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))
BOULDERS = {ZONE_RIVER: 6, ZONE_DUNES: 6, ZONE_CORDON: 4, ZONE_TAIGA: 6, ZONE_DROUGHT: 4}
PEBBLE_P = 0.035
WILTED_P = 0.09
PILLARS = 6
CAR_COLORS = 5
EXTRA_TRIGGERS = 6


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t*t*(3 - 2*t)


class Trigger:
    
    def __init__(self, cell, kind, plant, title, task):
        self.r, self.c = cell
        self.kind = kind
        self.plant = plant
        self.title = title
        self.task = task
        self.resolved = False

    def rect_px(self):
        return (self.c*TILE, self.r*TILE, TILE, TILE)


class World:
    
    def __init__(self, w=48, h=36, south=SOUTH_ROWS):
        self.W, self.PH = w, h  # PH — высота парка с дорогой
        self.H = h + south
        self.name = "ЭКОТРОПА «СТОЛБЫ»"
        self.path = set()
        self.dune = set()
        self.water = set()
        self.drought = set()
        self.road = set()
        self.parking = set()
        self.house = {}
        self.house_door = None
        self.log = None
        self.trees = []
        self.deco_signs = []
        self.posts = []
        self.benches = []
        self.boulders = []
        self.pillars = []
        self.pebbles = []
        self.wilted = []
        self.parked_cars = []
        self.stalls = []
        self.p_sign = None
        self.reeds = []
        self.mushrooms = []
        self.flowers = []
        self.triggers = []
        self.pasture = (0, 0, 0)
        self.fence = set()
        self.pen = set()
        self.gate = None
        self.gate_out = None
        self.farm_props = []
        self.village = []
        self.crossing = set()
        self.missing = []
        self.player_start = (0, 0)
        self._solid = set()
        self.generate()

    def zone_at(self, r, c):
        
        if r >= self.PH:
            return ZONE_VILLAGE if c >= int(self.W * 0.62) else ZONE_MEADOW
        if (r, c) in self.drought:
            return ZONE_DROUGHT
        if r < self.PH // 2:
            return ZONE_RIVER if c < self.W // 2 else ZONE_DUNES
        return ZONE_CORDON if c < self.W // 2 else ZONE_TAIGA

    def ground_at(self, r, c):
        
        if (r, c) in self.dune:
            return "sand"
        if (r, c) in self.path or (r, c) in self.road or (r, c) in self.parking or (r, c) in self.drought:
            return "path"
        return "grass"

    def _center(self, r):
        c = self.W/2 + 2.6*math.sin(r*0.42) + 0.8*math.sin(r*0.19)
        return max(3, min(self.W-4, int(round(c))))

    def _middle(self, c):
        m = self.PH/2 + 1.3*math.sin(c*0.31)
        m += 5*_smooth((self.W*0.35 - c) / (self.W*0.2))
        m -= 4*_smooth((c - self.W*0.72) / (self.W*0.15))
        return max(3, min(self.PH-4, int(round(m))))

    def _river_depth(self, c):
        span = self.W*0.45
        bay = 3.4*math.sin(math.pi*(c-1)/span) if 1 <= c <= 1+span else 0.0
        return 2 + max(0, int(round(bay + 0.5*math.sin(c*0.9))))

    def _near_free(self, blocked, r, c, rad=3):
        for d in range(rad+1):
            for dr in range(-d, d+1):
                for dc in range(-d, d+1):
                    if max(abs(dr), abs(dc)) != d:
                        continue
                    rr, cc = r+dr, c+dc
                    if 1 <= rr < self.H-1 and 1 <= cc < self.W-1 and (rr, cc) not in blocked:
                        return (rr, cc)
        return None

    def _dilate(self, cells, rad):
        out = set()
        for (r, c) in cells:
            for dr in range(-rad, rad+1):
                for dc in range(-rad, rad+1):
                    out.add((r+dr, c+dc))
        return out

    def _reachable(self, start):
        seen = {start}
        q = deque([start])
        while q:
            r, c = q.popleft()
            for nr, nc in ((r+1, c), (r-1, c), (r, c+1), (r, c-1)):
                if (nr, nc) not in seen and not self.solid(nc, nr):
                    seen.add((nr, nc))
                    q.append((nr, nc))
        return seen

    def _make_farm(self, pc0, road_r):
        
        c0, c1 = 1, max(7, pc0 - 2)
        low = max([r for (r, c) in self.path if c0 <= c <= c1] or [self.PH // 2])
        r0, r1 = low + 2, road_r - 1
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if r in (r0, r1) or c in (c0, c1):
                    self.fence.add((r, c))
                else:
                    self.pen.add((r, c))
        gc = (c0 + c1) // 2 + 1
        self.gate, self.gate_out = (r0, gc), (r0 - 1, gc)
        self.fence.discard(self.gate)
        self.farm_props = [(r1 - 1, c0 + 1, "cart"), (r0 + 1, c1 - 1, "hay")]
        self.pen -= {(r, c) for (r, c, _) in self.farm_props}
        self.pasture = ((r0 + r1) // 2, (c0 + c1) // 2, max(1, (c1 - c0) // 2 - 1))

    def generate(self):
        random.seed(11)
        W, H = self.W, self.PH
        road_r = H - 2
        self.water = {(r, c) for c in range(W) for r in range(self._river_depth(c))}
        for r in range(road_r):
            cc = self._center(r)
            for dc in (-1, 0, 1):
                if r > self._river_depth(cc+dc):
                    self.path.add((r, cc+dc))
        base_c = max(2, W // 10)
        c_end = W - 5
        for c in range(base_c - 1, c_end + 1):
            m = self._middle(c)
            for dr in (-1, 0, 1):
                if (m+dr, c) not in self.water:
                    self.path.add((m+dr, c))
        blobs = [(H*0.27, W*0.78, W*0.17, H*0.15), (H*0.17, W*0.70, W*0.08, H*0.07),
                 (H*0.38, W*0.92, W*0.06, H*0.07)]
        for (cy, cx, rx, ry) in blobs:
            for r in range(H):
                for c in range(W):
                    d = ((c-cx)/rx)**2 + ((r-cy)/ry)**2
                    if d <= 1.0 + 0.18*math.sin(c*1.7 + r*0.9) and (r, c) not in self.water:
                        self.dune.add((r, c))
        self.road = {(r, c) for r in (road_r, road_r+1) for c in range(W)}
        pc1 = min(self._center(r) for r in range(road_r-4, road_r)) - 3
        pc0 = max(1, pc1 - 9)
        self.parking = {(r, c) for r in range(road_r-4, road_r) for c in range(pc0, pc1+1)}
        busy = self.water | self.path | self.dune | self.road | self.parking
        dcy, dcx, drx, dry = H*0.48, W*0.80, W*0.13, H*0.14
        for r in range(H):
            for c in range(W):
                d = ((c-dcx)/drx)**2 + ((r-dcy)/dry)**2
                if d <= 1.0 + 0.15*math.sin(c*1.3 + r*1.1) and (r, c) not in busy:
                    self.drought.add((r, c))
        for _ in range(2):
            self.drought -= {(r, c) for (r, c) in self.drought
                             if sum((r+dr, c+dc) in self.drought for dr in (-1, 0, 1) for dc in (-1, 0, 1)) < 5}
        wall_r = min(self._middle(c) for c in range(base_c, base_c+3)) - 2
        base_r = wall_r - 2
        roof = {(base_r, base_c):48, (base_r, base_c+1):49, (base_r, base_c+2):50,
                (base_r+1, base_c):60, (base_r+1, base_c+1):61, (base_r+1, base_c+2):62}
        walls = {(base_r+2, base_c):72, (base_r+2, base_c+1):73, (base_r+2, base_c+2):75}
        self.house = {**roof, **walls}
        self.house_door = (base_r+2, base_c+1)
        self.path -= set(self.house)
        lc = self._center(H-9)
        self.log = (lc-4, lc+3, H-9)
        self._make_farm(pc0, road_r)

        hard = set(self.path) | set(self.water) | set(self.house) | self.road | self.parking
        hard |= {(self.log[2], c) for c in range(self.log[0], self.log[1])}
        hard |= self.fence | self.pen | {self.gate, self.gate_out}
        colors = list(range(CAR_COLORS))
        random.shuffle(colors)
        for r in (road_r-4, road_r-1):
            for c in range(pc0+1, pc1-1, 3):
                self.stalls.append((r, c))
                if random.random() < 0.75:
                    self.parked_cars.append((r, c, colors[len(self.parked_cars) % CAR_COLORS]))
        start_r = road_r - 2
        self.deco_signs = [(start_r, self._center(start_r)+2)]
        farm_sign = self._near_free(hard, self.gate_out[0], self.gate_out[1] + 2, 2)
        if farm_sign:
            self.deco_signs.append(farm_sign)
        hard |= set(self.deco_signs)
        self.p_sign = self._near_free(hard, road_r-5, pc1)
        if self.p_sign:
            hard.add(self.p_sign)

        top_r = self._river_depth(self._center(0)) + 1
        trail_top = self._center(top_r)
        cols = [c for c in range(int(W*0.40), int(W*0.76), 2) if abs(c - trail_top) > 3]
        for c in sorted(random.sample(cols, min(PILLARS, len(cols)))):
            cell = (self._river_depth(c), c)
            if cell not in hard and cell not in self.dune:
                self.pillars.append((cell[0], cell[1], random.randrange(3)))
                hard.add(cell)

        cr = self._middle(W // 2)
        for (r, c) in ((cr-2, self._center(cr)+2), (top_r, trail_top+2)):
            cell = self._near_free(hard, r, c)
            if cell:
                self.posts.append(cell)
                hard.add(cell)
        bay_c = int(W*0.25)
        for (r, c) in ((wall_r, base_c+4), (self._middle(c_end), c_end+2),
                       (int(H*0.75), self._center(int(H*0.75))+2),
                       (self._river_depth(bay_c)+1, bay_c)):
            cell = self._near_free(hard, r, c)
            if cell:
                self.benches.append(cell)
                hard.add(cell)

        near_trail = self._dilate(self.path | self.water | self.dune | self.drought, 3)
        for zone, n in BOULDERS.items():
            cand = [(r, c) for r in range(1, H-1) for c in range(1, W-1)
                    if (r, c) in near_trail and self.zone_at(r, c) == zone
                    and not (self._dilate([(r, c)], 1) & hard)]
            for (r, c) in random.sample(cand, min(n, len(cand))):
                if not (self._dilate([(r, c)], 1) & hard):
                    self.boulders.append((r, c, zone == ZONE_TAIGA))
                    hard.add((r, c))

        occ = hard | set(self.dune)
        for (r, c) in sorted(self._dilate(self.water, 1) - self.water - occ):
            if not (0 <= r < H and 0 <= c < W):
                continue
            p = 0.6 if self.zone_at(r, c) == ZONE_RIVER else 0.2
            if random.random() < p:
                self.reeds.append((r, c))
                occ.add((r, c))
        cand = [(r, c) for r in range(H) for c in range(1, W-1)
                if (r, c) not in occ and self.zone_at(r, c) == ZONE_TAIGA]
        for cell in random.sample(cand, min(5, len(cand))):
            self.mushrooms.append(cell)
            occ.add(cell)
        for r in range(1, H-1):
            for c in range(1, W-1):
                if (r, c) not in occ and r > self._river_depth(c) and random.random() < PEBBLE_P:
                    self.pebbles.append((r, c))
                    occ.add((r, c))
        for (r, c) in sorted(self.drought):
            if (r, c) not in occ and random.random() < WILTED_P:
                self.wilted.append((r, c))
                occ.add((r, c))
        placed = set()
        for r in range(H):
            for c in range(1, W-1):
                if r <= self._river_depth(c):
                    continue
                if (r, c) in occ or (r, c) in placed or (r-1, c) in placed:
                    continue
                edge = c <= 2 or c >= W-3
                p = EDGE_TREE_P if edge else TREE_P[self.zone_at(r, c)]
                if random.random() < p:
                    placed.add((r, c))
        tops = set()
        for (r, c) in sorted(placed):
            if self.zone_at(r, c) == ZONE_DROUGHT:
                self.trees.append((r, c, "dead"))
                tops.add((r-1, c))
                continue
            orange = random.random() < ORANGE_P[self.zone_at(r, c)]
            room = (r-1 > self._river_depth(c) and (r-1, c) not in occ and (r-1, c) not in placed)
            if room and random.random() < 0.3:
                kind = "tallo" if orange else "tallg"
                tops.add((r-1, c))
            else:
                kind = "o" if orange else "g"
            self.trees.append((r, c, kind))

        self._make_south(occ, placed, tops)
        sc = self._center(start_r)
        self.player_start = (sc, start_r)
        self._solid = set(self.water) | set(self.house)
        self._solid |= {cell for house in self.village for cell in house}
        self._solid |= {(r, c) for (r, c, _) in self.trees}
        self._solid |= set(self.posts) | set(self.benches)
        self._solid |= {(r, c) for (r, c, _) in self.boulders}
        self._solid |= {(r, c) for (r, c, _) in self.pillars}
        self._solid |= {(r, c + dc) for (r, c, _) in self.parked_cars for dc in (0, 1)}
        self._solid |= self.fence | {(r, c) for (r, c, _) in self.farm_props}

        self._place_plants(occ - set(self.dune) - set(self.water), placed | tops, (start_r, sc))

    def _make_south(self, occ, placed, tops):
        
        W, PH, H = self.W, self.PH, self.H
        road_r = PH - 2
        cc = self._center(road_r - 1)
        self.crossing = {(r, cc + dc) for r in (road_r, road_r + 1) for dc in (-1, 0, 1)}
        mid = lambda c: PH + 6 + int(round(1.2 * math.sin(c * 0.33)))
        south = {(r, cc + dc) for r in range(PH, mid(cc)) for dc in (-1, 0, 1)}
        for c in range(3, W - 3):
            south |= {(mid(c) + dr, c) for dr in (-1, 0, 1)}
        self.path |= south
        occ |= south

        
        styles = (((52, 53, 54), (64, 65, 66), (76, 89, 79)), ((48, 49, 50), (60, 61, 62), (72, 85, 75)))
        for i, hc in enumerate((W - 17, W - 12, W - 7)):
            wall = min(mid(c) for c in range(hc, hc + 3)) - 2
            top, low, walls = styles[i % 2]
            house = {}
            for k in range(3):
                house[(wall - 2, hc + k)] = top[k]
                house[(wall - 1, hc + k)] = low[k]
                house[(wall, hc + k)] = walls[k]
            self.village.append(house)
            occ |= set(house)
            porch = wall + 1  
            while porch < H - 1 and (porch, hc + 1) not in south:
                self.path.add((porch, hc + 1))
                occ.add((porch, hc + 1))
                porch += 1

        
        pond = set()
        pr, pcx = PH + 10.5, W * 0.2
        for r in range(PH + 1, H - 1):
            for c in range(1, int(W * 0.5)):
                d = ((c + 0.5 - pcx) / 5.6) ** 2 + ((r + 0.5 - pr) / 2.1) ** 2
                if d <= 1.0 + 0.12 * math.sin(c * 1.9 + r) and (r, c) not in occ:
                    pond.add((r, c))
        self.water |= pond
        for cell in sorted(self._dilate(pond, 1) - pond - occ):
            if PH <= cell[0] < H and 0 < cell[1] < W - 1 and random.random() < 0.35:
                self.reeds.append(cell)
                occ.add(cell)

        blocked = occ | self.water | self.road | self.crossing
        for (r, c, what) in ((mid(cc) - 2, cc + 3, "post"), (mid(W - 19) - 2, W - 19, "sign"),
                             (PH + 8, int(pcx) + 7, "bench")):
            cell = self._near_free(blocked, r, c)
            if not cell or cell[0] < PH:
                continue
            {"post": self.posts, "sign": self.deco_signs, "bench": self.benches}[what].append(cell)
            blocked.add(cell)
            occ.add(cell)

        near = self._dilate(south | pond, 3)
        cand = [(r, c) for r in range(PH + 1, H - 1) for c in range(2, int(W * 0.62))
                if (r, c) in near and not (self._dilate([(r, c)], 1) & blocked)]
        for (r, c) in random.sample(cand, min(3, len(cand))):
            if not (self._dilate([(r, c)], 1) & blocked):
                self.boulders.append((r, c, False))
                blocked.add((r, c))
                occ.add((r, c))
        for r in range(PH + 1, H - 1):
            for c in range(1, W - 1):
                if (r, c) not in blocked and random.random() < PEBBLE_P:
                    self.pebbles.append((r, c))
                    blocked.add((r, c))
                    occ.add((r, c))

        new = set()
        for r in range(PH, H):
            for c in range(1, W - 1):
                if (r, c) in blocked or (r, c) in new or (r - 1, c) in new:
                    continue
                edge = c <= 2 or c >= W - 3 or r >= H - 1
                if random.random() < (EDGE_TREE_P if edge else TREE_P[self.zone_at(r, c)]):
                    new.add((r, c))
        for (r, c) in sorted(new):
            orange = random.random() < ORANGE_P[self.zone_at(r, c)]
            room = r - 1 >= PH and (r - 1, c) not in blocked and (r - 1, c) not in new
            if room and random.random() < 0.3:
                kind = "tallo" if orange else "tallg"
                tops.add((r - 1, c))
            else:
                kind = "o" if orange else "g"
            self.trees.append((r, c, kind))
        placed |= new

    def _habitats(self, r, c):
        
        if (r, c) in self.water:
            shore = any((r+dr, c+dc) not in self.water and not self.solid(c+dc, r+dr) for dr, dc in STEPS4)
            return {"water"} if shore else set()
        out = {"sand"} if (r, c) in self.dune else {"grass"}
        if any((r+dr, c+dc) in self._rocks for dr, dc in STEPS8):
            out.add("rock")
        if any((r+dr, c+dc) in self._tree_cells for dr, dc in STEPS4):
            out.add("tree")
        return out

    @staticmethod
    def _fits(sp, habitats):
        return bool(HABITAT_OK.get(sp.get("habitat", "grass"), {"grass"}) & habitats)

    def _place_plants(self, blocked, trees, start):
        
        W, H = self.W, self.H
        self._rocks = {(r, c) for (r, c, _) in self.boulders} | {(r, c) for (r, c, _) in self.pillars}
        self._tree_cells = {(r, c) for (r, c, k) in self.trees if k != "dead"}
        by_zone = {}
        for sp in SPECIES:
            for z in zones(sp):
                by_zone.setdefault(z, []).append(sp)
        taken = blocked | trees
        count = {sp["name"]: 0 for sp in SPECIES}
        for r in range(H):
            for c in range(1, W-1):
                if (r, c) in taken:
                    continue
                hab = self._habitats(r, c)
                zone = self.zone_at(r, c)
                p = WATER_PLANT_P if "water" in hab else FLOWER_P[zone]
                fit = [sp for sp in by_zone.get(zone, ()) if self._fits(sp, hab) and count[sp["name"]] < MAX_PER_SPECIES]
                if fit and random.random() < p:
                    # редкие виды — в приоритете
                    sp = random.choices(fit, [1 / (1 + count[s["name"]]) ** 2 for s in fit])[0]
                    count[sp["name"]] += 1
                    self.flowers.append((r, c, sp))
                    taken.add((r, c))

        reach = self._reachable(start)
        def reachable(r, c):
            # кувшинки — с берега
            return (r, c) in reach or ((r, c) in self.water and any((r+dr, c+dc) in reach for dr, dc in STEPS4))
        chosen = []
        def spaced(f):
            return all(max(abs(f[0]-g[0]), abs(f[1]-g[1])) >= 3 for g in chosen)
        cells = [(r, c) for r in range(H) for c in range(1, W-1) if (r, c) not in taken and reachable(r, c)]
        for sp in SPECIES:
            own = [f for f in self.flowers if f[2] is sp and reachable(f[0], f[1])]
            if not own:
                free = [cell for cell in cells if cell not in taken and self.zone_at(*cell) in zones(sp)
                        and self._fits(sp, self._habitats(*cell))]
                free = free or [cell for cell in cells if cell not in taken and self._fits(sp, self._habitats(*cell))]
                if not free:
                    self.missing.append(sp["name"])
                    continue
                r, c = random.choice(free)
                self.flowers.append((r, c, sp))
                taken.add((r, c))
                own = [(r, c, sp)]
            chosen.append(random.choice([f for f in own if spaced(f)] or own))
        if self.missing:
            print("! нет достижимой точки роста:", ", ".join(self.missing))
        rest = [f for f in self.flowers if reachable(f[0], f[1]) and f not in chosen]
        random.shuffle(rest)
        for f in rest:
            if len(chosen) >= len(SPECIES) + EXTRA_TRIGGERS:
                break
            if spaced(f):
                chosen.append(f)
        for (r, c, sp) in chosen:
            self.triggers.append(Trigger((r, c), "litter", sp,
                                         "!  НАРУШЕНИЕ · мусор у точки роста",
                                         "Убери мусор у точки роста (нажми E)"))

    def plant_at(self, cell):
        for f in self.flowers:
            if (f[0], f[1]) == cell:
                return f
        return None

    def remove_plant(self, cell):
        \
        gone = self.plant_at(cell)
        self.flowers = [f for f in self.flowers if (f[0], f[1]) != cell]
        self.triggers = [t for t in self.triggers if (t.r, t.c) != cell]
        return gone

    def walkable(self, r, c):
        \
        return not self.solid(c, r) and (r, c) not in self.road and (r, c) not in self.parking

    def route(self, start, goal, passable, limit=60):
        
        prev, dist = {start: None}, {start: 0}
        q = deque([start])
        while q:
            cur = q.popleft()
            if goal(cur) and cur != start:
                path = []
                while cur != start:
                    path.append(cur)
                    cur = prev[cur]
                return path[::-1]
            if dist[cur] >= limit:
                continue
            r, c = cur
            for dr, dc in STEPS8:
                n = (r+dr, c+dc)
                if n in prev or not passable(*n):
                    continue
                if dr and dc and not (passable(r+dr, c) and passable(r, c+dc)):
                    continue
                prev[n], dist[n] = cur, dist[cur] + 1
                q.append(n)
        return None

    def solid(self, c, r):
        if c < 0 or r < 0 or c >= self.W or r >= self.H:
            return True
        return (r, c) in self._solid

    def px_size(self):
        return self.W*TILE, self.H*TILE