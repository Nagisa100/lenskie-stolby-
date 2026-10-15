import array, math, random

RATE = 22050
CHANNELS = 1


def setup():
    
    global RATE, CHANNELS
    import pygame
    info = pygame.mixer.get_init()
    if not info or info[1] != -16:
        return False
    RATE, CHANNELS = info[0], info[2]
    return True


def _pack(samples, peak=28000):
    m = max(1e-6, max(abs(x) for x in samples))
    k = peak / m
    data = array.array('h', (int(max(-32000, min(32000, x * k))) for x in samples for _ in range(CHANNELS)))
    return data.tobytes()


def _sound(samples):
    import pygame
    return pygame.mixer.Sound(buffer=_pack(samples))


def _env(i, n, attack, release):
    a = max(1, int(n * attack)); r = max(1, int(n * release))
    if i < a:
        return i / a
    if i > n - r:
        return max(0.0, (n - i) / r)
    return 1.0


STEP_KINDS = {
    "path": (0.085, 1.0, 0.55, 0.6),
    "grass": (0.075, 0.22, 0.45, 0.75),
    "sand": (0.11, 0.38, 0.6, 0.3),
}


def footstep(seed=0, kind="path"):
    
    dur, bright, crunch_k, thud_k = STEP_KINDS.get(kind, STEP_KINDS["path"])
    rnd = random.Random(seed * 97 + 3)
    n = int(RATE * dur)
    pitch = 85 + rnd.uniform(-10, 10)
    out = []
    noise = 0.0
    for i in range(n):
        t = i / RATE
        env = _env(i, n, 0.015, 0.8)
        noise += bright * (rnd.uniform(-1, 1) - noise)
        crunch = noise * (1 - t / dur) * crunch_k / max(0.3, bright ** 0.5)
        thud = math.sin(2 * math.pi * pitch * t) * math.exp(-22 * t) * thud_k
        out.append((crunch + thud) * env)
    return _sound(out)


def jingle():
    
    notes = (523.25, 659.25, 783.99, 1046.5)
    step = 0.085
    n = int(RATE * (step * len(notes) + 0.45))
    out = []
    for i in range(n):
        t = i / RATE
        s = 0.0
        for k, f in enumerate(notes):
            local = t - k * step
            if local < 0:
                continue
            tail = 3.0 if k == len(notes) - 1 else 9.0
            tri = 2 * abs(2 * ((f * local) % 1.0) - 1) - 1
            s += (0.7 * tri + 0.3 * math.sin(2 * math.pi * f * 2 * local)) * math.exp(-tail * local) * 0.3
        out.append(s * _env(i, n, 0.005, 0.3))
    return _sound(out)


def lost():
    
    n = int(RATE * 0.4)
    out = []
    ph = 0.0
    for i in range(n):
        t = i / RATE
        ph += (330 - 190 * t / 0.4) / RATE
        tri = 2 * abs(2 * (ph % 1.0) - 1) - 1
        out.append(tri * math.exp(-4.5 * t) * _env(i, n, 0.02, 0.3))
    return _sound(out)


def horn():
    
    n = int(RATE * 0.36)
    out = []
    for i in range(n):
        t = i / RATE
        on = t < 0.13 or 0.19 < t < 0.34
        s = 0.0
        if on:
            for f in (392.0, 494.0):
                s += (1.0 if (f * t) % 1.0 < 0.5 else -1.0) * 0.5
        out.append(s * _env(i, n, 0.02, 0.1))
    return _sound(out)


def page():
    
    n = int(RATE * 0.12)
    rnd = random.Random(11)
    out = []
    prev = 0.0
    for i in range(n):
        prev += 0.35 * (rnd.uniform(-1, 1) - prev)
        out.append(prev * _env(i, n, 0.25, 0.6))
    return _sound(out)


def chime():
    
    n = int(RATE * 0.55)
    notes = (523.25, 659.25, 783.99)
    out = []
    for i in range(n):
        t = i / RATE
        env = _env(i, n, 0.03, 0.75)
        s = 0.0
        for k, f in enumerate(notes):
            local = max(0.0, t - k * 0.06)
            s += math.sin(2 * math.pi * f * local) * math.exp(-3.2 * local) * 0.33
        out.append(s * env)
    return _sound(out)


def crinkle():
    
    n = int(RATE * 0.22)
    rnd = random.Random(5)
    out = []
    prev = 0.0
    for i in range(n):
        env = _env(i, n, 0.01, 0.7)
        prev = prev * 0.55 + rnd.uniform(-1, 1) * 0.45
        out.append(prev * env * 0.8)
    return _sound(out)


def talk(seed=0):
    
    rnd = random.Random(seed * 31 + 7)
    syl = 0.065
    n = int(RATE * syl * 3)
    pitches = [rnd.uniform(360, 520) for _ in range(3)]
    out = []
    ph = 0.0
    for i in range(n):
        t = i / RATE
        k = min(2, int(t / syl))
        local = t - k * syl
        ph += pitches[k] * (1 + 0.15 * math.sin(2 * math.pi * 18 * local)) / RATE
        sq = 1.0 if ph % 1.0 < 0.4 else -1.0
        out.append(sq * _env(int(local * RATE), int(syl * RATE), 0.08, 0.5) * 0.4)
    return _sound(out)


def success():
    
    notes = ((659.25, 0.0), (987.77, 0.09))
    n = int(RATE * 0.42)
    out = []
    for i in range(n):
        t = i / RATE
        s = 0.0
        for f, t0 in notes:
            local = t - t0
            if local >= 0:
                tri = 2 * abs(2 * ((f * local) % 1.0) - 1) - 1
                s += tri * math.exp(-6 * local) * 0.5
        out.append(s * _env(i, n, 0.01, 0.4))
    return _sound(out)


def fail():
    
    n = int(RATE * 0.26)
    out = []
    ph = 0.0
    for i in range(n):
        t = i / RATE
        ph += (220 - 110 * t / 0.26) / RATE
        sq = 1.0 if ph % 1.0 < 0.5 else -1.0
        out.append(sq * 0.35 * _env(i, n, 0.02, 0.5))
    return _sound(out)


def neigh():
    
    n = int(RATE * 0.7)
    out = []
    ph = 0.0
    for i in range(n):
        t = i / RATE
        f = 820 - 420 * (t / 0.7) ** 0.7
        f *= 1 + 0.06 * math.sin(2 * math.pi * 23 * t)
        ph += f / RATE
        saw = 2 * (ph % 1.0) - 1
        s = 0.6 * saw + 0.4 * math.sin(2 * math.pi * ph * 2)
        out.append(s * _env(i, n, 0.05, 0.45) * (0.7 + 0.3 * math.sin(2 * math.pi * 7 * t)))
    return _sound(out)


def trample():
    
    rnd = random.Random(17)
    n = int(RATE * 0.5)
    hits = (0.0, 0.12, 0.27, 0.36)
    out = []
    prev = 0.0
    for i in range(n):
        t = i / RATE
        s = 0.0
        for h in hits:
            local = t - h
            if 0 <= local < 0.1:
                prev = prev * 0.7 + rnd.uniform(-1, 1) * 0.3
                s += (math.sin(2 * math.pi * 70 * local) * 0.8 + prev * 0.5) * math.exp(-30 * local)
        out.append(s)
    return _sound(out)


def alert():
    
    n = int(RATE * 0.34)
    out = []
    for i in range(n):
        t = i / RATE
        on = t < 0.12 or 0.17 < t < 0.29
        f = 988.0 if t < 0.15 else 784.0
        out.append((math.sin(2 * math.pi * f * t) * 0.5 + (0.2 if (f * t) % 1.0 < 0.5 else -0.2)) * on)
    return _sound(out)


def click():
    
    n = int(RATE * 0.05)
    out = []
    for i in range(n):
        t = i / RATE
        env = _env(i, n, 0.01, 0.8)
        out.append(math.sin(2 * math.pi * 880 * t) * env * 0.5)
    return _sound(out)


def ambient():
    
    total = 20.0       # длина лупа, с
    bar = 5.0          # один аккорд на такт
    f0 = 1.0 / total   # «частота лупа»: любая кратная ей синусоида сойдётся на стыке

    def q(f):          # притянуть ноту к ближайшей кратной f0 — ради бесшовности (сдвиг < 0.03 Гц)
        return max(1, round(f * total)) / total

    # Am - F - C - G: тёплая, чуть тоскливая прогрессия; общие ноты держат переходы мягкими
    chords = [
        [110.00, 164.81, 220.00, 261.63],
        [87.31, 130.81, 220.00, 261.63],
        [130.81, 196.00, 261.63, 329.63],
        [98.00, 146.83, 196.00, 246.94],
    ]
    chords = [[q(f) for f in ch] for ch in chords]
    # редкие ноты сверху — пентатоника Am, (время старта, частота)
    melody = [(t0, q(f)) for t0, f in (
        (1.2, 329.63), (4.2, 261.63), (6.4, 440.00), (9.2, 392.00),
        (11.6, 329.63), (14.0, 293.66), (16.4, 261.63),
    )]

    n = int(RATE * total)
    nb = len(chords)
    cfrac = 0.9 / bar  # доля такта под кросс-фейд аккордов
    out = []
    for i in range(n):
        t = i / RATE
        # пэд: внутри такта играет свой аккорд, в начале — плавный переход с предыдущего (по кругу)
        pos = t / bar
        k = int(pos) % nb
        frac = pos - int(pos)
        cur = sum(math.sin(2 * math.pi * f * t) for f in chords[k])
        if frac < cfrac:
            prev = sum(math.sin(2 * math.pi * f * t) for f in chords[(k - 1) % nb])
            s = frac / cfrac
            s = s * s * (3 - 2 * s)      # smoothstep
            pad = prev * (1 - s) + cur * s
        else:
            pad = cur
        pad *= 0.25
        pad *= 1 - 0.12 * (0.5 - 0.5 * math.cos(2 * math.pi * (2 * f0) * t))  # «дыхание» громкости
        # редкие ноты — мягкий треугольник с затуханием, стартуют и гаснут вдали от стыка
        mel = 0.0
        for t0, f in melody:
            local = t - t0
            if 0 <= local < 3.0:
                tri = 2 * abs(2 * ((f * local) % 1.0) - 1) - 1
                mel += (0.75 * tri + 0.25 * math.sin(2 * math.pi * f * local)) * math.exp(-1.6 * local) * 0.5
        out.append(pad + mel)
    return _sound(out)
