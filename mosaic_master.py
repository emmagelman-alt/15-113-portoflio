#!/usr/bin/env python3
"""Mosaic Master: a pixel-art mosaic game for 15-114.

Single player: customers line up at your shop counter and ask for a picture.
Accept a request, build it out of shape tiles, and the customer scores it.
Scoring is an offline placeholder for now (see placeholder_score); the plan is
to swap in an image-similarity API later. Multiplayer is coming next.

Run:   .venv/bin/python mosaic_master.py
"""

import math
import random
import time

import pygame

# The game draws at this small size and pygame scales it up, so every
# pixel shows up as a chunky block.
W, H = 640, 360
FPS = 60
JUDGE_SECONDS = 2.5           # how long the customer "thinks" before scoring
TRANSITION_SECONDS = 0.45
DOUBLE_CLICK_SECONDS = 0.35

# ---------------------------------------------------------------- colors

INK = (28, 24, 32)
WHITE = (250, 248, 240)
CREAM = (244, 236, 216)
GREEN_BTN = (96, 186, 96)
RED_BTN = (222, 96, 84)
BLUE_BTN = (98, 150, 226)
YELLOW_BTN = (246, 204, 76)
WOOD = (150, 98, 58)
WOOD_DARK = (112, 72, 42)
WOOD_LIGHT = (190, 130, 78)

# Every tile shape comes in all of these colors.
PALETTE = [
    (22, 22, 26), (74, 74, 84), (140, 140, 150), (200, 200, 206), (250, 250, 246),
    (92, 56, 30), (150, 96, 50), (214, 174, 120), (242, 204, 168),
    (130, 22, 32), (212, 42, 42), (242, 132, 32), (250, 214, 40), (255, 240, 150),
    (200, 160, 40), (120, 120, 40), (150, 212, 60), (52, 152, 62), (26, 92, 46),
    (40, 162, 150), (92, 220, 230), (122, 190, 240), (42, 92, 200), (26, 36, 102),
    (122, 62, 172), (182, 150, 222), (242, 142, 182), (222, 52, 132),
]

SHAPES = ["square", "rectangle", "circle", "triangle", "oval", "star"]
PILE_SIZES = [30, 20, 13, 8]   # biggest first, so small tiles land on top

PROMPTS = [
    "black dog", "sunflower", "sunset on beach", "red apple", "house with a red roof",
    "snowman", "rainbow", "full moon at night", "green tree", "orange cat",
    "pizza slice", "rubber duck", "sailboat on the ocean", "ice cream cone",
    "birthday cake", "strawberry", "fish in a bowl", "hot air balloon",
    "snowy mountain", "ladybug", "rocket ship", "watermelon slice", "banana",
    "pumpkin", "christmas tree", "butterfly", "cactus in the desert", "lighthouse",
    "smiley face", "coffee mug", "red rose", "blue car", "penguin", "turtle",
    "umbrella in the rain", "campfire", "cupcake", "palm tree", "frog on a lily pad",
    "volcano", "starry night sky", "flower pot", "traffic light", "pink pig",
    "snail", "bumblebee", "heart", "cherries", "lollipop", "owl", "whale",
    "carrot", "mushroom", "beach ball", "red barn", "fireworks", "igloo", "robot",
]

# ---------------------------------------------------------------- layout

# Shop (first-person view)
DESK_Y = 258
SLOTS = [  # (x, feet y, scale): slot 0 is the counter, the rest is the line
    (300, 300, 2.6), (410, 236, 1.3), (452, 232, 1.18),
    (492, 228, 1.08), (530, 225, 1.0), (566, 222, 0.93),
]
DOOR = (604, 214, 0.85)
EXIT = (-70, 300, 2.6)
BUBBLE = pygame.Rect(352, 36, 270, 116)
PIECE_RECT = pygame.Rect(0, 0, 146, 90)
PIECE_RECT.center = (320, 310)

# Workspace (zoomed in on the table), following Desktop - 1.png
PILE = pygame.Rect(12, 12, 196, 336)
PILE_AREA = pygame.Rect(20, 20, 180, 278)
CANVAS = pygame.Rect(222, 48, 406, 250)
FINISH = pygame.Rect(552, 8, 76, 30)
SHAPE_BUTTONS = [pygame.Rect(222 + i * 69, 306, 61, 44) for i in range(len(SHAPES))]


# ---------------------------------------------------------------- helpers

_fonts = {}


def font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def draw_text(surf, msg, size, color, pos, anchor="topleft", shadow=None):
    img = font(size).render(msg, False, color)
    rect = img.get_rect(**{anchor: pos})
    if shadow:
        surf.blit(font(size).render(msg, False, shadow), rect.move(1, 1))
    surf.blit(img, rect)
    return rect


def wrap_text(msg, size, width):
    lines, line = [], ""
    for word in msg.split():
        test = (line + " " + word).strip()
        if font(size).size(test)[0] <= width or not line:
            line = test
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def shade(color, f):
    return tuple(max(0, min(255, int(c * f))) for c in color)


def lighten(color, f):
    return tuple(int(c + (255 - c) * f) for c in color)


def score_color(score):
    if score >= 70:
        return (70, 176, 84)
    if score >= 40:
        return (230, 170, 40)
    return (214, 64, 52)


class Button:
    def __init__(self, rect, label, color, size=18, text_color=INK):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.color = color
        self.size = size
        self.text_color = text_color

    def hit(self, pos):
        return self.rect.collidepoint(pos)

    def draw(self, surf, mouse, selected=False):
        r = self.rect
        base = self.color
        if selected:
            base = YELLOW_BTN
        elif r.collidepoint(mouse):
            base = lighten(base, 0.2)
        pygame.draw.rect(surf, INK, r.move(0, 3), border_radius=3)
        pygame.draw.rect(surf, base, r, border_radius=3)
        pygame.draw.rect(surf, INK, r, 2, border_radius=3)
        pygame.draw.line(surf, lighten(base, 0.4), (r.left + 3, r.top + 2), (r.right - 4, r.top + 2))
        if self.label:
            draw_text(surf, self.label, self.size, self.text_color, r.center, "center")


# ---------------------------------------------------------------- tiles

def tile_dims(shape, size):
    if shape == "rectangle":
        return size * 2, size
    if shape == "oval":
        return max(4, int(size * 0.6)), size
    return size, size


def star_points(cx, cy, outer, inner):
    pts = []
    for i in range(10):
        r = outer if i % 2 == 0 else inner
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def make_tile_surface(shape, size, color, edge=None):
    w, h = tile_dims(shape, size)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    r = surf.get_rect()
    if edge is None and size >= 10:
        edge = shade(color, 0.7)
    if shape in ("square", "rectangle"):
        pygame.draw.rect(surf, color, r)
        if edge:
            pygame.draw.rect(surf, edge, r, 1)
    elif shape in ("circle", "oval"):
        pygame.draw.ellipse(surf, color, r)
        if edge:
            pygame.draw.ellipse(surf, edge, r, 1)
    else:
        if shape == "triangle":
            pts = [(w // 2, 0), (w - 1, h - 1), (0, h - 1)]
        else:
            pts = star_points((w - 1) / 2, (h - 1) / 2 + h * 0.04, w / 2, w * 0.21)
        pygame.draw.polygon(surf, color, pts)
        if edge:
            pygame.draw.polygon(surf, edge, pts, 1)
    return surf


_tile_cache = {}


def tile_graphics(shape, size, color, rot):
    key = (shape, size, color, rot)
    if key not in _tile_cache:
        img = make_tile_surface(shape, size, color)
        if rot:
            img = pygame.transform.rotate(img, rot)   # nearest-neighbour: stays pixelly
        _tile_cache[key] = (img, pygame.mask.from_surface(img))
    return _tile_cache[key]


class Tile:
    def __init__(self, shape, color, size, x=0, y=0, rot=0, overlap=False):
        self.shape, self.color, self.size = shape, color, size
        self.x, self.y = x, y      # center, in screen pixels
        self.overlap = overlap     # double-clicked tiles may sit on top of others
        self.set_rot(rot)

    def set_rot(self, rot):
        self.rot = rot % 360
        self.image, self.mask = tile_graphics(self.shape, self.size, self.color, self.rot)

    @property
    def rect(self):
        return self.image.get_rect(center=(int(round(self.x)), int(round(self.y))))

    def contains(self, pos):
        r = self.rect
        return r.collidepoint(pos) and bool(self.mask.get_at((pos[0] - r.x, pos[1] - r.y)))

    def overlaps(self, other):
        a, b = self.rect, other.rect
        if not a.colliderect(b):
            return False
        return self.mask.overlap(other.mask, (b.x - a.x, b.y - a.y)) is not None

    def copy(self):
        return Tile(self.shape, self.color, self.size, self.x, self.y, self.rot, self.overlap)


def make_pile(shape):
    """Scatter every color and size of one shape into the pile tray."""
    tiles, rects = [], []
    for size in PILE_SIZES:
        for color in PALETTE:
            tile = Tile(shape, color, size)
            w, h = tile.image.get_size()
            best = None
            for _ in range(15):   # try a few spots, keep the least covered one
                r = pygame.Rect(0, 0, w, h)
                r.left = random.randint(PILE_AREA.left, PILE_AREA.right - w)
                r.top = random.randint(PILE_AREA.top, PILE_AREA.bottom - h)
                cost = 0
                for o in rects:
                    c = r.clip(o)
                    cost += c.w * c.h
                if best is None or cost < best[0]:
                    best = (cost, r)
            tile.x, tile.y = best[1].center
            rects.append(best[1])
            tiles.append(tile)
    return tiles


def draw_order(tiles):
    """Normal tiles first, overlap tiles on top."""
    return [t for t in tiles if not t.overlap] + [t for t in tiles if t.overlap]


def render_mosaic(tiles):
    surf = pygame.Surface(CANVAS.size)
    surf.fill(CREAM)
    for t in draw_order(tiles):
        r = t.rect
        surf.blit(t.image, (r.x - CANVAS.x, r.y - CANVAS.y))
    return surf


# ---------------------------------------------------------------- scoring

COMMENTS = [
    (80, ["Wow, I love it!", "That's perfect, thank you!", "Exactly what I pictured!"]),
    (60, ["Nice! I can see it.", "Pretty good, thanks!", "I like the colors!"]),
    (40, ["Hmm, it's... interesting.", "Not quite what I imagined.", "I guess that works?"]),
    (0, ["Is this finished?", "I'm not sure what this is.", "Maybe a few more tiles?"]),
]


def placeholder_score(tiles):
    """Score a finished mosaic from 0 to 100.

    PLACEHOLDER: this doesn't look at what the picture shows. It rewards
    covering the canvas, using several colors and using enough tiles. Replace
    it with a real image-vs-request similarity check (e.g. a vision API call)
    that returns (score, comment).
    """
    covered = pygame.mask.Mask(CANVAS.size)
    for t in tiles:
        r = t.rect
        covered.draw(t.mask, (r.x - CANVAS.x, r.y - CANVAS.y))
    coverage = covered.count() / float(CANVAS.w * CANVAS.h)
    colors = len({t.color for t in tiles})
    score = (min(1.0, coverage / 0.45) * 55
             + min(1.0, colors / 5.0) * 25
             + min(1.0, len(tiles) / 25.0) * 20)
    score = max(0, min(100, int(round(score))))
    comment = next(random.choice(lines) for floor, lines in COMMENTS if score >= floor)
    return score, comment


# ---------------------------------------------------------------- customers

SKINS = [(255, 222, 188), (240, 196, 152), (206, 150, 106), (160, 106, 70), (112, 72, 46)]
HAIRS = [(32, 26, 22), (92, 56, 30), (202, 160, 80), (232, 212, 150), (162, 62, 32),
         (124, 124, 128), (70, 44, 96)]
SHIRTS = [(212, 60, 60), (60, 120, 212), (70, 170, 90), (240, 180, 50), (160, 80, 190),
          (240, 130, 170), (40, 160, 160), (240, 240, 236), (60, 60, 70)]
PANTS = [(46, 64, 120), (70, 70, 80), (110, 80, 50), (30, 30, 36), (90, 110, 150)]
HAIR_STYLES = ["short", "long", "bun", "bald", "cap", "spiky"]


class Customer:
    def __init__(self, pos):
        self.x, self.feet, self.scale = pos
        self.target = pos
        self.skin = random.choice(SKINS)
        self.hair = random.choice(HAIRS)
        self.shirt = random.choice(SHIRTS)
        self.pants = random.choice(PANTS)
        self.hat = random.choice(SHIRTS)
        self.style = random.choice(HAIR_STYLES)
        self.blink_period = random.uniform(2.5, 4.5)
        self.mood = "neutral"
        self.moving = False
        self.walk_t = 0.0

    def at_target(self):
        return math.hypot(self.target[0] - self.x, self.target[1] - self.feet) <= 0.5

    def update(self, dt):
        tx, tf, ts = self.target
        dx, df = tx - self.x, tf - self.feet
        dist = math.hypot(dx, df)
        if dist > 0.5:
            f = min(1.0, 95 * dt / dist)
            self.x += dx * f
            self.feet += df * f
            self.scale += (ts - self.scale) * f
            self.moving = True
            self.walk_t += dt
        else:
            self.x, self.feet, self.scale = tx, tf, ts
            self.moving = False

    def sprite(self, now):
        s = pygame.Surface((30, 60), pygame.SRCALPHA)
        step = 1 + int(self.walk_t * 6) % 2 if self.moving else 0
        l_up = 2 if step == 1 else 0
        r_up = 2 if step == 2 else 0
        shoe = (46, 34, 34)
        # legs and shoes
        pygame.draw.rect(s, self.pants, (9, 44 - l_up, 5, 13))
        pygame.draw.rect(s, self.pants, (16, 44 - r_up, 5, 13))
        pygame.draw.rect(s, shoe, (8, 56 - l_up, 7, 3))
        pygame.draw.rect(s, shoe, (15, 56 - r_up, 7, 3))
        # body and arms
        pygame.draw.rect(s, self.shirt, (7, 24, 16, 22))
        pygame.draw.rect(s, shade(self.shirt, 0.8), (7, 42, 16, 4))
        arm = shade(self.shirt, 0.85)
        pygame.draw.rect(s, arm, (4, 25 + r_up, 3, 15))
        pygame.draw.rect(s, arm, (23, 25 + l_up, 3, 15))
        pygame.draw.rect(s, self.skin, (4, 40 + r_up, 3, 3))
        pygame.draw.rect(s, self.skin, (23, 40 + l_up, 3, 3))
        # neck and head
        pygame.draw.rect(s, self.skin, (13, 21, 4, 4))
        pygame.draw.rect(s, self.skin, (9, 5, 12, 18))
        pygame.draw.rect(s, self.skin, (8, 7, 14, 14))
        # eyes
        if now % self.blink_period < 0.12:
            pygame.draw.rect(s, INK, (11, 14, 2, 1))
            pygame.draw.rect(s, INK, (17, 14, 2, 1))
        else:
            pygame.draw.rect(s, INK, (11, 13, 2, 2))
            pygame.draw.rect(s, INK, (17, 13, 2, 2))
        # mouth
        mouth = (120, 40, 40)
        pygame.draw.rect(s, mouth, (13, 19, 4, 1))
        if self.mood == "happy":
            pygame.draw.rect(s, mouth, (12, 18, 1, 1))
            pygame.draw.rect(s, mouth, (17, 18, 1, 1))
            pygame.draw.rect(s, (240, 150, 150), (9, 16, 2, 1))
            pygame.draw.rect(s, (240, 150, 150), (19, 16, 2, 1))
        elif self.mood == "sad":
            pygame.draw.rect(s, mouth, (12, 20, 1, 1))
            pygame.draw.rect(s, mouth, (17, 20, 1, 1))
        # hair
        hair = self.hair
        if self.style in ("short", "long", "bun"):
            pygame.draw.rect(s, hair, (8, 3, 14, 5))
            pygame.draw.rect(s, hair, (8, 6, 2, 6))
            pygame.draw.rect(s, hair, (20, 6, 2, 6))
            if self.style == "long":
                pygame.draw.rect(s, hair, (6, 6, 3, 18))
                pygame.draw.rect(s, hair, (21, 6, 3, 18))
            if self.style == "bun":
                pygame.draw.rect(s, hair, (12, 0, 6, 4))
        elif self.style == "spiky":
            pygame.draw.rect(s, hair, (8, 4, 14, 4))
            for x in range(8, 22, 3):
                pygame.draw.rect(s, hair, (x, 1, 2, 4))
        elif self.style == "cap":
            pygame.draw.rect(s, self.hat, (8, 2, 14, 6))
            pygame.draw.rect(s, shade(self.hat, 0.8), (4, 7, 14, 2))
        elif self.style == "bald":
            pygame.draw.rect(s, hair, (8, 9, 1, 5))
            pygame.draw.rect(s, hair, (21, 9, 1, 5))
        return s

    def draw(self, surf, now, hop=0.0):
        w, h = max(1, int(30 * self.scale)), max(1, int(60 * self.scale))
        if self.feet < DESK_Y:
            shadow = pygame.Rect(0, 0, int(w * 0.8), max(2, int(4 * self.scale)))
            shadow.center = (int(self.x), int(self.feet))
            pygame.draw.ellipse(surf, (120, 108, 100), shadow)
        img = pygame.transform.scale(self.sprite(now), (w, h))
        surf.blit(img, img.get_rect(midbottom=(int(self.x), int(self.feet - hop))))

    def head_side(self):
        """Point next to the customer's face, where a speech bubble tail goes."""
        return int(self.x + 8 * self.scale), int(self.feet - 46 * self.scale)


# ---------------------------------------------------------------- backgrounds

def build_title_background():
    s = pygame.Surface((W, H))
    sky = [(52, 62, 150), (70, 90, 180), (96, 124, 210), (130, 160, 228),
           (170, 190, 236), (214, 200, 220), (250, 196, 160), (252, 170, 120)]
    band = 236 / len(sky)
    for i, col in enumerate(sky):
        y0, y1 = int(i * band), int((i + 1) * band)
        s.fill(col, (0, y0, W, y1 - y0))
        if i + 1 < len(sky):   # checkerboard dither into the next band
            for y in range(y1 - 4, y1):
                for x in range(y % 2, W, 2):
                    s.set_at((x, y), sky[i + 1])
    pygame.draw.circle(s, (255, 214, 110), (476, 206), 36)
    pygame.draw.circle(s, (255, 240, 180), (476, 206), 27)

    rng = random.Random(7)
    # far mountains with snowcaps
    for cx, peak, half in [(40, 140, 110), (170, 112, 120), (300, 150, 100),
                           (420, 118, 140), (580, 128, 120)]:
        pygame.draw.polygon(s, (112, 100, 170), [(cx - half, 250), (cx, peak), (cx + half, 250)])
        pygame.draw.polygon(s, (88, 78, 146), [(cx, peak), (cx + half, 250), (cx + half // 3, 250)])
        snow = 22
        f = snow / (250 - peak)
        pygame.draw.polygon(s, WHITE, [
            (cx - half * f, peak + snow), (cx - half * f / 3, peak + snow - 5),
            (cx, peak + snow), (cx + half * f / 2, peak + snow - 4),
            (cx + half * f, peak + snow), (cx, peak)])

    def ridge(base, amp, color, step):
        pts, y = [(0, H)], base
        for x in range(0, W + step, step):
            y = max(base - 26, min(base + 14, y + rng.randint(-amp, amp)))
            pts.append((x, y))
        pts.append((W, H))
        pygame.draw.polygon(s, color, pts)
        return pts[1:-1]

    ridge(246, 5, (84, 132, 110), 16)
    near = ridge(282, 4, (70, 156, 82), 20)
    s.fill((92, 178, 88), (0, 322, W, 38))
    # trees along the near hills
    for x, y in near[1:-1:2]:
        tx = x + rng.randint(-6, 6)
        pygame.draw.rect(s, (92, 60, 36), (tx - 1, y - 4, 3, 6))
        pygame.draw.polygon(s, (34, 110, 60), [(tx - 7, y - 3), (tx, y - 20), (tx + 7, y - 3)])
        pygame.draw.polygon(s, (46, 132, 70), [(tx - 5, y - 11), (tx, y - 24), (tx + 5, y - 11)])
    # flowers in the meadow
    for _ in range(70):
        x, y = rng.randint(0, W - 2), rng.randint(326, H - 3)
        s.fill(rng.choice([(250, 240, 120), (250, 140, 170), WHITE, (180, 150, 230)]), (x, y, 2, 2))
    return s


def draw_cloud(surf, x, y, size):
    for dx, dy, w, h in [(0, 6, 34, 10), (6, 0, 16, 10), (16, 2, 14, 8), (-6, 10, 46, 6)]:
        pygame.draw.rect(surf, WHITE, (x + dx * size, y + dy * size, w * size, h * size))


def build_shop_background():
    room = pygame.Surface((W, H))
    room.fill((226, 204, 168))
    for x in range(0, W, 24):
        room.fill((214, 190, 152), (x, 0, 12, 170))
    # wainscot
    room.fill((150, 98, 60), (0, 170, W, 36))
    room.fill((118, 76, 46), (0, 170, W, 3))
    for x in range(0, W, 32):
        room.fill((132, 86, 52), (x, 173, 2, 33))
    # checker floor
    for row, y in enumerate(range(206, DESK_Y, 8)):
        for col, x in enumerate(range(-8 * (row % 2), W, 16)):
            room.fill((196, 186, 176) if col % 2 == 0 else (164, 152, 146), (x, y, 16, 8))
    # window with a little landscape
    win = pygame.Rect(30, 40, 132, 96)
    room.fill((140, 190, 240), win)
    room.fill((180, 214, 246), (win.x, win.y + 40, win.w, 30))
    pygame.draw.circle(room, (255, 230, 130), (win.x + 100, win.y + 30), 11)
    pygame.draw.polygon(room, (80, 160, 90), [(win.x, win.bottom), (win.x + 40, win.y + 62),
                                              (win.x + 90, win.y + 74), (win.right, win.y + 60),
                                              (win.right, win.bottom)])
    pygame.draw.rect(room, WOOD_DARK, win, 5)
    room.fill(WOOD_DARK, (win.centerx - 2, win.y, 4, win.h))
    room.fill(WOOD_DARK, (win.x, win.centery - 2, win.w, 4))
    # framed mosaic on the wall
    frame = pygame.Rect(196, 56, 64, 50)
    room.fill(WOOD_LIGHT, frame)
    rng = random.Random(3)
    for gx in range(frame.x + 4, frame.right - 4, 7):
        for gy in range(frame.y + 4, frame.bottom - 4, 7):
            room.fill(rng.choice(PALETTE[9:26]), (gx, gy, 6, 6))
    pygame.draw.rect(room, WOOD_DARK, frame, 2)
    # door with an OPEN sign
    door = pygame.Rect(578, 92, 52, 114)
    room.fill((132, 86, 52), door)
    room.fill((116, 74, 44), (door.x + 6, door.y + 8, 40, 44))
    room.fill((116, 74, 44), (door.x + 6, door.y + 60, 40, 46))
    pygame.draw.rect(room, WOOD_DARK, door, 3)
    pygame.draw.circle(room, (236, 200, 90), (door.x + 42, door.y + 60), 3)
    sign = pygame.Rect(584, 70, 40, 16)
    room.fill((200, 60, 60), sign)
    pygame.draw.rect(room, INK, sign, 1)
    draw_text(room, "OPEN", 14, WHITE, sign.center, "center")
    # shop banner
    banner = pygame.Rect(244, 6, 152, 22)
    room.fill((60, 52, 92), banner)
    pygame.draw.rect(room, INK, banner, 2)
    draw_text(room, "MOSAIC SHOP", 18, (250, 220, 120), banner.center, "center")

    # desk, drawn over the customers
    desk = pygame.Surface((W, H - DESK_Y))
    desk.fill(WOOD)
    desk.fill(WOOD_LIGHT, (0, 0, W, 8))
    desk.fill(WOOD_DARK, (0, 8, W, 2))
    for y in range(32, H - DESK_Y, 24):
        desk.fill(shade(WOOD, 0.85), (0, y, W, 2))
    for _ in range(60):
        x, y = rng.randint(0, W - 12), rng.randint(12, H - DESK_Y - 2)
        desk.fill(shade(WOOD, 0.9), (x, y, rng.randint(4, 14), 1))
    # box of assorted tiles
    box = pygame.Rect(22, 18, 150, 72)
    desk.fill((110, 78, 44), (box.x, box.y, box.w, 12))
    for _ in range(46):
        shape = rng.choice(SHAPES)
        img = make_tile_surface(shape, rng.choice([7, 8, 9, 10]), rng.choice(PALETTE))
        desk.blit(img, (rng.randint(box.x + 2, box.right - 22), rng.randint(box.y - 6, box.y + 4)))
    desk.fill((198, 152, 94), (box.x, box.y + 10, box.w, box.h - 10))
    pygame.draw.rect(desk, (150, 108, 62), (box.x, box.y + 10, box.w, box.h - 10), 2)
    desk.fill((176, 132, 80), (box.x, box.y + 10, box.w, 3))
    draw_text(desk, "TILES", 22, (120, 82, 46), (box.centerx, box.y + 44), "center")
    return room, desk


def build_table_background():
    s = pygame.Surface((W, H))
    s.fill((124, 82, 50))
    rng = random.Random(11)
    for y in range(0, H, 40):
        s.fill((104, 68, 40), (0, y, W, 2))
    for _ in range(140):
        x, y = rng.randint(0, W - 20), rng.randint(0, H - 1)
        s.fill((114, 76, 46), (x, y, rng.randint(6, 26), 1))
    return s


# ---------------------------------------------------------------- the game

class Game:
    def __init__(self, screen):
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.now = time.time()
        self.mouse = (0, 0)
        self.state = "title"
        self.toast = None
        self.trans = None

        self.title_bg = build_title_background()
        self.room_bg, self.desk_bg = build_shop_background()
        self.table_bg = build_table_background()
        self.title_text = self.build_title_text()
        self.clouds = [(random.uniform(0, W), random.uniform(20, 120), random.choice([1, 2]))
                       for _ in range(6)]
        self.shape_icons = [make_tile_surface(s, 20, WHITE, edge=INK) for s in SHAPES]

        self.btn_single = Button((220, 236, 200, 30), "SINGLE PLAYER", GREEN_BTN, 20)
        self.btn_multi = Button((220, 276, 200, 30), "MULTIPLAYER", BLUE_BTN, 20)
        self.btn_home = Button((572, 8, 60, 22), "HOME", (210, 200, 190), 16)
        self.btn_accept = Button((BUBBLE.x + 14, BUBBLE.bottom - 34, 116, 24), "ACCEPT", GREEN_BTN, 18)
        self.btn_skip = Button((BUBBLE.right - 130, BUBBLE.bottom - 34, 116, 24), "SKIP", RED_BTN, 18)
        self.btn_finish = Button(FINISH, "FINISH", GREEN_BTN, 20)
        self.btn_shapes = [Button(r, "", (226, 216, 200)) for r in SHAPE_BUTTONS]

        self.served = 0
        self.score_total = 0
        self.recent_prompts = []

        self.shape = "square"
        self.pile = make_pile(self.shape)
        self.tiles = []
        self.drag = None
        self.last_click = (None, 0.0)
        self.reset_shop()

    # ---- setup

    def build_title_text(self):
        letters = []
        colors = [(240, 80, 80), (250, 170, 50), (250, 220, 70), (110, 200, 90),
                  (80, 170, 240), (170, 110, 230), (240, 120, 180)]
        for i, ch in enumerate("MOSAIC MASTER"):
            letters.append((font(26).render(ch, False, colors[i % len(colors)]),
                            font(26).render(ch, False, INK)))
        w = sum(img.get_width() for img, _ in letters) + 2
        h = letters[0][0].get_height() + 2
        small = pygame.Surface((w, h), pygame.SRCALPHA)
        x = 0
        for img, shadow in letters:
            small.blit(shadow, (x + 1, 1))
            small.blit(img, (x, 0))
            x += img.get_width()
        return pygame.transform.scale(small, (w * 3, h * 3))

    def reset_shop(self):
        """Fresh line of customers; the first one walks up to the counter."""
        self.line = []
        for i in range(len(SLOTS) - 1):
            c = Customer(SLOTS[i + 1])
            c.target = SLOTS[i]
            self.line.append(c)
        self.leaving = []
        self.shop_state = "arriving"
        self.request = None
        self.piece = None
        self.verdict = None

    def pick_prompt(self):
        choices = [p for p in PROMPTS if p not in self.recent_prompts] or PROMPTS
        prompt = random.choice(choices)
        self.recent_prompts = (self.recent_prompts + [prompt])[-12:]
        return prompt

    def show_toast(self, text, seconds=2.2):
        self.toast = (text, self.now + seconds)

    def begin_transition(self, kind, focus):
        self.trans = {"snap": self.screen.copy(), "t": 0.0, "kind": kind, "focus": focus}

    # ---- main loop

    def run(self):
        while True:
            dt = min(0.05, self.clock.tick(FPS) / 1000.0)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                self.handle_event(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def handle_event(self, event):
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.mouse = event.pos
        if self.trans and event.type == pygame.MOUSEBUTTONDOWN:
            return
        if self.state == "title":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.btn_single.hit(event.pos):
                    self.begin_transition("fade", (W // 2, H // 2))
                    self.reset_shop()
                    self.state = "shop"
                elif self.btn_multi.hit(event.pos):
                    self.show_toast("Multiplayer is coming soon!")
        elif self.state == "shop":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.shop_click(event.pos)
        elif self.state == "work":
            self.work_event(event)

    def update(self, dt):
        self.now = time.time()
        if self.trans:
            self.trans["t"] += dt
            if self.trans["t"] >= TRANSITION_SECONDS:
                self.trans = None
        if self.toast and self.now > self.toast[1]:
            self.toast = None
        if self.state == "title":
            self.clouds = [((x + 8 * dt * s) % (W + 120), y, s) for x, y, s in self.clouds]
        if self.state in ("shop", "work"):
            self.update_shop(dt)   # the line keeps moving while you work

    def draw(self):
        if self.state == "title":
            self.draw_title()
        elif self.state == "shop":
            self.draw_shop()
        else:
            self.draw_work()
        if self.toast:
            pos = (CANVAS.centerx, CANVAS.bottom - 16) if self.state == "work" else (W // 2, 336)
            img = font(18).render(self.toast[0], False, WHITE)
            box = img.get_rect(center=pos).inflate(16, 10)
            pygame.draw.rect(self.screen, INK, box, border_radius=4)
            self.screen.blit(img, img.get_rect(center=pos))
        if self.trans:
            self.draw_transition()

    def draw_transition(self):
        tr = self.trans
        t = min(1.0, tr["t"] / TRANSITION_SECONDS)
        fx, fy = tr["focus"]
        if tr["kind"] == "in":
            s = 1 + 2.2 * t * t
        elif tr["kind"] == "out":
            s = 1 - 0.75 * t
        else:
            s = 1.0
        img = tr["snap"] if s == 1 else pygame.transform.scale(
            tr["snap"], (max(1, int(W * s)), max(1, int(H * s))))
        img = img.copy()
        img.set_alpha(int(255 * (1 - t)))
        self.screen.blit(img, (int(fx - fx * s), int(fy - fy * s)))

    # ---- title screen

    def draw_title(self):
        scr = self.screen
        scr.blit(self.title_bg, (0, 0))
        for x, y, size in self.clouds:
            draw_cloud(scr, int(x) - 120, int(y), size)
        rect = self.title_text.get_rect(center=(W // 2, 92))
        scr.blit(self.title_text, rect)
        draw_text(scr, "build what your customers ask for, one tile at a time", 18,
                  WHITE, (W // 2, rect.bottom + 14), "center", shadow=INK)
        self.btn_single.draw(scr, self.mouse)
        self.btn_multi.draw(scr, self.mouse)

    # ---- shop (first-person counter view)

    def shop_click(self, pos):
        if self.btn_home.hit(pos):
            self.begin_transition("fade", (W // 2, H // 2))
            self.reset_shop()
            self.state = "title"
            return
        if self.shop_state == "request":
            if self.btn_accept.hit(pos):
                self.begin_transition("in", (320, 300))
                self.tiles = []
                self.drag = None
                self.state = "work"
            elif self.btn_skip.hit(pos):
                self.line[0].mood = "sad"
                self.next_customer()
        elif self.shop_state == "verdict":
            self.next_customer()

    def next_customer(self):
        front = self.line.pop(0)
        front.target = EXIT
        self.leaving.append(front)
        self.line.append(Customer(DOOR))
        for i, c in enumerate(self.line):
            c.target = SLOTS[i]
        self.shop_state = "arriving"
        self.request = None
        self.piece = None
        self.verdict = None

    def start_judging(self, tiles):
        self.judge_started = self.now
        self.verdict = placeholder_score(tiles)   # revealed after JUDGE_SECONDS

    def update_shop(self, dt):
        for c in self.line + self.leaving:
            c.update(dt)
        self.leaving = [c for c in self.leaving if not c.at_target()]
        front = self.line[0]
        if self.shop_state == "arriving" and front.target == SLOTS[0] and front.at_target():
            self.shop_state = "request"
            self.request = self.pick_prompt()
        elif self.shop_state == "judging":
            if self.now - self.judge_started >= JUDGE_SECONDS:
                score = self.verdict[0]
                self.served += 1
                self.score_total += score
                front.mood = "happy" if score >= 60 else ("sad" if score < 35 else "neutral")
                self.shop_state = "verdict"
                self.verdict_until = self.now + 6.0
        elif self.shop_state == "verdict" and self.now >= self.verdict_until:
            self.next_customer()

    def draw_shop(self):
        scr = self.screen
        scr.blit(self.room_bg, (0, 0))
        front = self.line[0]
        for c in sorted(self.line + self.leaving, key=lambda c: c.feet):
            hop = 0.0
            if c is front and self.shop_state == "verdict" and c.mood == "happy":
                hop = abs(math.sin(self.now * 9)) * 5 * c.scale
            c.draw(scr, self.now, hop)
        scr.blit(self.desk_bg, (0, DESK_Y))

        # the finished piece lies on the desk while the customer looks at it
        if self.piece is not None:
            frame = PIECE_RECT.inflate(8, 8)
            pygame.draw.rect(scr, INK, frame.move(0, 3))
            pygame.draw.rect(scr, WOOD_LIGHT, frame)
            pygame.draw.rect(scr, INK, frame, 1)
            scr.blit(self.piece, PIECE_RECT)
            if self.shop_state == "verdict":
                score = self.verdict[0]
                draw_text(scr, "%d%%" % score, 40, score_color(score),
                          (frame.right + 8, frame.centery), "midleft", shadow=INK)

        if self.shop_state == "request":
            self.draw_bubble(front)
            draw_text(scr, "Hi! Could you make me...", 18, INK, (BUBBLE.x + 14, BUBBLE.y + 10))
            y = BUBBLE.y + 30
            for line in wrap_text(self.request.upper(), 28, BUBBLE.w - 28)[:2]:
                draw_text(scr, line, 28, (60, 52, 140), (BUBBLE.x + 14, y))
                y += 22
            self.btn_accept.draw(scr, self.mouse)
            self.btn_skip.draw(scr, self.mouse)
        elif self.shop_state == "judging":
            self.draw_bubble(front)
            dots = "." * (1 + int(self.now * 3) % 3)
            draw_text(scr, "Hmm" + dots, 32, INK, (BUBBLE.x + 14, BUBBLE.y + 22))
            draw_text(scr, "Is this a %s?" % self.request, 18, (90, 84, 100),
                      (BUBBLE.x + 14, BUBBLE.y + 60))
        elif self.shop_state == "verdict":
            score, comment = self.verdict
            self.draw_bubble(front)
            y = BUBBLE.y + 10
            for line in wrap_text(comment or "...", 20, BUBBLE.w - 28)[:4]:
                draw_text(scr, line, 20, INK, (BUBBLE.x + 14, y))
                y += 16
            draw_text(scr, "SCORE %d%%" % score, 30, score_color(score),
                      (BUBBLE.x + 14, BUBBLE.bottom - 32), shadow=INK)
            draw_text(scr, "click to continue", 14, WHITE, (BUBBLE.right, BUBBLE.bottom + 6),
                      "topright", shadow=INK)

        # score so far
        hud = pygame.Rect(8, 8, 172, 22)
        pygame.draw.rect(scr, INK, hud, border_radius=3)
        avg = "--" if not self.served else "%d%%" % round(self.score_total / self.served)
        draw_text(scr, "SERVED %d   AVG %s" % (self.served, avg), 16, WHITE, hud.center, "center")
        self.btn_home.draw(scr, self.mouse)

    def draw_bubble(self, customer):
        scr = self.screen
        tip = customer.head_side()
        base = [(BUBBLE.x + 18, BUBBLE.bottom - 3), (BUBBLE.x + 40, BUBBLE.bottom - 3)]
        pygame.draw.rect(scr, INK, BUBBLE.move(0, 3), border_radius=8)
        pygame.draw.polygon(scr, WHITE, base + [tip])
        pygame.draw.line(scr, INK, base[0], tip, 2)
        pygame.draw.line(scr, INK, base[1], tip, 2)
        pygame.draw.rect(scr, WHITE, BUBBLE, border_radius=8)
        pygame.draw.rect(scr, INK, BUBBLE, 2, border_radius=8)
        pygame.draw.polygon(scr, WHITE, [(base[0][0] + 2, base[0][1] - 1),
                                         (base[1][0] - 2, base[1][1] - 1),
                                         (base[0][0] + 6, base[0][1] + 3)])

    # ---- workspace (zoomed in on the table)

    def canvas_tile_at(self, pos):
        for t in reversed(draw_order(self.tiles)):
            if t.contains(pos):
                return t
        return None

    def fits(self, tile, others):
        return CANVAS.contains(tile.rect) and not any(tile.overlaps(o) for o in others)

    def settle(self, tile, others):
        """Keep the tile on the canvas. Normal tiles slide to the nearest open spot."""
        r = tile.rect.clamp(CANVAS)
        tile.x, tile.y = r.center
        if tile.overlap or self.fits(tile, others):
            return True
        ox, oy = tile.x, tile.y
        for radius in range(2, 100, 2):
            n = max(8, int(2 * math.pi * radius / 4))
            for i in range(n):
                a = 2 * math.pi * i / n
                r = tile.rect
                r.center = (int(ox + math.cos(a) * radius), int(oy + math.sin(a) * radius))
                r = r.clamp(CANVAS)
                tile.x, tile.y = r.center
                if self.fits(tile, others):
                    return True
        tile.x, tile.y = ox, oy
        return False

    def work_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.work_mouse_down(event.pos)
        elif event.type == pygame.MOUSEMOTION and self.drag:
            t = self.drag["tile"]
            t.x, t.y = event.pos[0] + self.drag["dx"], event.pos[1] + self.drag["dy"]
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag:
            self.drop()
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            step = -15 if event.mod & pygame.KMOD_SHIFT else 15
            self.rotate_tile(step)

    def work_mouse_down(self, pos):
        if self.btn_finish.hit(pos):
            self.finish_piece()
            return
        for shape, btn in zip(SHAPES, self.btn_shapes):
            if btn.hit(pos):
                if shape != self.shape:
                    self.shape = shape
                    self.pile = make_pile(shape)
                return
        tile = self.canvas_tile_at(pos)
        if tile:
            last_tile, last_time = self.last_click
            if tile is last_tile and self.now - last_time < DOUBLE_CLICK_SECONDS:
                self.last_click = (None, 0.0)
                self.toggle_overlap(tile)
                return
            self.last_click = (tile, self.now)
            self.tiles.remove(tile)
            self.start_drag(tile, pos, from_canvas=True)
            return
        for t in reversed(self.pile):
            if t.contains(pos):
                self.start_drag(t.copy(), pos, from_canvas=False)
                return

    def start_drag(self, tile, pos, from_canvas):
        self.drag = {"tile": tile, "dx": tile.x - pos[0], "dy": tile.y - pos[1],
                     "from_canvas": from_canvas, "home": (tile.x, tile.y, tile.rot)}

    def drop(self):
        d, self.drag = self.drag, None
        tile = d["tile"]
        if not CANVAS.collidepoint(tile.rect.center):
            return   # dropped off the canvas: the tile is gone
        if self.settle(tile, self.tiles):
            self.tiles.append(tile)
        elif d["from_canvas"]:
            tile.x, tile.y = d["home"][:2]
            tile.set_rot(d["home"][2])
            self.tiles.append(tile)
            self.show_toast("No room there")
        else:
            self.show_toast("No room! Double-click a tile to let it overlap")

    def toggle_overlap(self, tile):
        if tile.overlap:
            tile.overlap = False
            if self.settle(tile, [o for o in self.tiles if o is not tile]):
                self.show_toast("Overlap off")
            else:
                tile.overlap = True
                self.show_toast("No free spot nearby, so it stays overlapping")
        else:
            tile.overlap = True
            self.tiles.remove(tile)
            self.tiles.append(tile)
            self.show_toast("Overlap on: this tile can sit on top of others")

    def rotate_tile(self, step):
        if self.drag:
            t = self.drag["tile"]
            t.set_rot(t.rot + step)
            return
        tile = self.canvas_tile_at(self.mouse)
        if not tile:
            return
        old = (tile.x, tile.y, tile.rot)
        tile.set_rot(tile.rot + step)
        if not self.settle(tile, [o for o in self.tiles if o is not tile]):
            tile.x, tile.y = old[:2]
            tile.set_rot(old[2])
            self.show_toast("No room to rotate")

    def finish_piece(self):
        if not self.tiles:
            self.show_toast("Add some tiles first!")
            return
        mosaic = render_mosaic(self.tiles)
        self.piece = pygame.transform.scale(mosaic, PIECE_RECT.size)
        self.start_judging(self.tiles)
        self.begin_transition("out", PIECE_RECT.center)
        self.drag = None
        self.toast = None
        self.state = "shop"
        self.shop_state = "judging"

    def draw_work(self):
        scr = self.screen
        scr.blit(self.table_bg, (0, 0))

        # tile pile
        pygame.draw.rect(scr, INK, PILE.move(0, 3), border_radius=4)
        pygame.draw.rect(scr, (86, 56, 34), PILE, border_radius=4)
        pygame.draw.rect(scr, (66, 42, 26), PILE.inflate(-8, -8), border_radius=3)
        pygame.draw.rect(scr, INK, PILE, 2, border_radius=4)
        for t in self.pile:
            scr.blit(t.image, t.rect)
        hint_y = PILE.bottom - 42
        for line in ["Drag tiles onto the canvas", "Double-click a tile: overlap",
                     "R: rotate    Drag off: remove"]:
            draw_text(scr, line, 15, (236, 214, 176), (PILE.centerx, hint_y), "midtop")
            hint_y += 12

        # request and finish button
        draw_text(scr, "REQUEST:", 18, (240, 220, 180), (CANVAS.x, 16))
        size = 30
        while size > 18 and font(size).size(self.request.upper())[0] > FINISH.x - CANVAS.x - 90:
            size -= 2
        draw_text(scr, self.request.upper(), size, WHITE, (CANVAS.x + 74, 24), "midleft", shadow=INK)
        self.btn_finish.draw(scr, self.mouse)

        # canvas
        frame = CANVAS.inflate(8, 8)
        pygame.draw.rect(scr, INK, frame.move(0, 3))
        pygame.draw.rect(scr, WOOD_LIGHT, frame)
        pygame.draw.rect(scr, INK, frame, 1)
        scr.fill(CREAM, CANVAS)
        blink = int(self.now * 4) % 2 == 0
        for t in draw_order(self.tiles):
            if t.overlap:   # glowing outline marks tiles that may overlap
                glow = t.mask.to_surface(setcolor=(255, 240, 110) if blink else WHITE,
                                         unsetcolor=(0, 0, 0, 0))
                r = t.rect
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    scr.blit(glow, r.move(dx, dy))
            scr.blit(t.image, t.rect)

        # shape buttons
        for shape, btn, icon in zip(SHAPES, self.btn_shapes, self.shape_icons):
            btn.draw(scr, self.mouse, selected=(shape == self.shape))
            scr.blit(icon, icon.get_rect(center=btn.rect.center))

        # the tile being dragged floats above everything
        if self.drag:
            t = self.drag["tile"]
            r = t.rect
            shadow = t.mask.to_surface(setcolor=(0, 0, 0, 90), unsetcolor=(0, 0, 0, 0))
            scr.blit(shadow, r.move(3, 4))
            scr.blit(t.image, r)


def main():
    pygame.init()
    pygame.display.set_caption("Mosaic Master")
    try:
        screen = pygame.display.set_mode((W, H), pygame.SCALED)
    except pygame.error:
        screen = pygame.display.set_mode((W, H))
    Game(screen).run()
    pygame.quit()


if __name__ == "__main__":
    main()
