import math, os, sys
import pygame


def dpi_aware():
    
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class Display:
    def __init__(self, w, h, offscreen=False):
        self.base = (w, h)
        self.w, self.h = w, h
        self.offscreen = offscreen
        self.fullscreen = False
        self.rect = pygame.Rect(0, 0, w, h)
        self._bufs = {}
        self._win_size = None
        if offscreen:
            self.window_size = (w, h)
            pygame.display.set_mode(self.window_size)
        else:
            try:
                dw, dh = pygame.display.get_desktop_sizes()[0]
            except Exception:
                dw, dh = w, h
            # окно в пропорциях экрана
            self.window_size = (max(w, int(dw * 0.85)), max(h, int(dh * 0.85)))
            os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
            pygame.display.set_mode(self.window_size, pygame.RESIZABLE)
        self.frame = pygame.Surface((w, h)).convert()

    def set_fullscreen(self, on):
        if on == self.fullscreen:
            return
        self.fullscreen = on
        if on:
            pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            pygame.display.set_mode(self.window_size, pygame.RESIZABLE)

    def resized(self, size):
        if not self.fullscreen and size[0] > 0 and size[1] > 0:
            self.window_size = size

    def logical_for(self, size):
        
        bw, bh = self.base
        ww, wh = size
        if ww <= 0 or wh <= 0:
            return bw, bh
        if ww * bh >= wh * bw:
            return max(bw, round(bh * ww / wh)), bh
        return bw, max(bh, round(bw * wh / ww))

    def sync(self):
        
        win = pygame.display.get_surface()
        if self.offscreen or win is None or win.get_size() == self._win_size:
            return False
        self._win_size = win.get_size()
        size = self.logical_for(self._win_size)
        if size == (self.w, self.h):
            return False
        self.w, self.h = size
        self.frame = pygame.Surface(size).convert()
        self._bufs = {}
        return True

    def _buf(self, key, size):
        b = self._bufs.get(key)
        if b is None or b.get_size() != size:
            b = pygame.Surface(size, 0, self.frame)
            self._bufs[key] = b
        return b

    def present(self):
        win = pygame.display.get_surface()
        ww, wh = win.get_size()
        s = min(ww / self.w, wh / self.h)
        w, h = max(1, int(self.w * s)), max(1, int(self.h * s))
        if ww - w <= 2 and wh - h <= 2:  # почти совпало — на всё окно
            w, h = ww, wh
        self.rect = pygame.Rect((ww - w) // 2, (wh - h) // 2, w, h)
        if (w, h) == (self.w, self.h):
            img = self.frame
        elif s >= 1:
            k = max(1, math.ceil(s - 1e-6))
            img = self._buf("big", (self.w * k, self.h * k))
            pygame.transform.scale(self.frame, img.get_size(), img)
            if img.get_size() != (w, h):
                fit = self._buf("fit", (w, h))
                pygame.transform.smoothscale(img, (w, h), fit)
                img = fit
        else:
            img = self._buf("fit", (w, h))
            pygame.transform.smoothscale(self.frame, (w, h), img)
        win.fill((0, 0, 0))
        win.blit(img, self.rect)
        pygame.display.flip()

    def to_logical(self, pos):
        
        r = self.rect
        return int((pos[0] - r.x) * self.w / r.w), int((pos[1] - r.y) * self.h / r.h)
