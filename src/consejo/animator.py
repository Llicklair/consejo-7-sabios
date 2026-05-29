"""Animador: traduce StateEvents en frames pixel-art renderizados a terminal.

Cambios v2:
- Nuevo estado ANALIZANDO con libro flotante (3 frames) + partículas
- DEBATE con número de ronda dinámico (1..N)
- Palantir convertido en HUD: muestra la ronda dentro del orbe + partículas
- Fuego animado: cicla 3 frames de chimenea para chisporroteo visual
- Burbujas amarillas estilo cómic
- Asignación aleatoria sabio→asiento por sesión

Uso:
    python -m consejo.animator             # demo a velocidad 1x
    python -m consejo.animator --speed 3   # 3x más rápido
    python -m consejo.animator --rounds 7  # más rondas de debate
"""

from __future__ import annotations

import argparse
import asyncio
import math
import time
from typing import Optional

from PIL import Image, ImageDraw
from rich.console import Console, Group
from rich.live import Live
from rich.text import Text
from rich_pixels import Pixels

from .glyphs import (
    GLYPH_SIZE,
    generate_glyph_bitmaps,
    render_glyphs_to_strip,
    text_to_glyphs,
)
from .renderer import ASSETS_DIR, load_sage_sprite, load_tile, upscale
from .report import generate_fake_report
from .sages import SAGES, RGB
from .scene import (
    DOOR_SPRITE_XY, FIREPLACE_XY, SEATS,
    TABLE_X, TABLE_Y, TABLE_W,
    apply_lighting, apply_table_decor, compose_room, random_seat_indices,
)
from .sound import SoundPlayer
from .sprites import _draw_number as _sprite_draw_number, generate_bubble, generate_palantir
from .states import (
    DEFAULT_DEBATE_ROUNDS,
    DEFAULT_TIMINGS,
    EventBus,
    State,
    mock_driver,
)

FPS = 10  # bajar a 10 reduce flicker en terminals lentos + render más estable
FRAME_DT = 1.0 / FPS

COMIC_YELLOW: RGB = (255, 220, 60)

STATE_SUBTITLES: dict[State, str] = {
    State.ENTRANDO:     "Los siete sabios cruzan el corredor hacia tu cámara...",
    State.SENTANDOSE:   "Toman asiento. El Mago levanta la mirada hacia ti.",
    State.ANALIZANDO:   "🔮 «Bienvenido, fundador. Analizamos tu proyecto y pronto debatiremos.»",
    State.DEBATE:       "Ronda {round} · turno {turn} · habla {speaker} · plan: {plan_size} ítems · ✦ {n_signed}/6 firmas",
    State.JUEZ:         "El juez sopesa las voces y sintetiza el veredicto...",
    State.ACUERDO:      "Acuerdo alcanzado. Las seis firmas brillan sobre la mesa.",
    State.LEVANTANDOSE: "Los sabios se levantan, satisfechos.",
    State.SALIENDO:     "Salen al corredor para llevar el plan a tu mundo.",
    State.REPORTE:      "📜 Reporte generado. Revisa el plan en tu consejo-report.md",
}


# ---------- caches ----------

_ROOM_CACHE: Optional[Image.Image] = None
_SPRITE_CACHE: dict[tuple[str, str], Image.Image] = {}
_GLYPHS_BY_COLOR: dict[RGB, list[Image.Image]] = {}
_FIRE_FRAMES: list[Image.Image] = []
_BOOK_FRAMES: list[Image.Image] = []


def _room() -> Image.Image:
    """Devuelve el room base sin lighting ni decor de mesa. El animator
    aplica ambos por frame para tener pulse + decor condicional."""
    global _ROOM_CACHE
    if _ROOM_CACHE is None:
        _ROOM_CACHE = compose_room(include_lighting=False,
                                    include_table_decor=False)
    return _ROOM_CACHE.copy()


_SEATED_CACHE: dict[tuple, Image.Image] = {}


def _scene_seated(seat_indices: list[int]) -> Image.Image:
    """Compose room + 7 seated sage sprites. Cached per seat permutation —
    seat_indices is constant for a session (set once via random_seat_indices),
    so this builds the static base scene exactly once per (session, decor)."""
    key = tuple(seat_indices)
    cached = _SEATED_CACHE.get(key)
    if cached is None:
        canvas = _room()
        for seat_idx, sage_idx in enumerate(seat_indices):
            sage = SAGES[sage_idx]
            _, sage_xy, view = SEATS[seat_idx]
            sp = _sprite(sage.id, view)
            canvas.paste(sp, sage_xy, sp)
        _SEATED_CACHE[key] = canvas
        cached = canvas
    return cached.copy()


def _add_static_table_decor(canvas: Image.Image) -> None:
    """Pinta el decor estático en la mesa (palantir/planta/vela/scrolls)."""
    apply_table_decor(canvas, ASSETS_DIR, TABLE_X, TABLE_Y, TABLE_W)


def _seal_tile() -> Image.Image:
    return load_tile("sign_seal")


def _draw_signatures(canvas: Image.Image, seat_indices: list[int],
                     signed: set, t_total: float,
                     new_signs_age: float) -> None:
    """Pinta un sello dorado encima de cada sabio que ha firmado.
    Los sellos recién aparecidos hacen pop-in (scale up rápido)."""
    if not signed:
        return
    seal = _seal_tile()
    for seat_idx, sage_idx in enumerate(seat_indices):
        if sage_idx not in signed:
            continue
        _, sage_xy, _view = SEATS[seat_idx]
        # Posición encima de la cabeza
        seal_x = sage_xy[0] + 24 - seal.width // 2
        seal_y = sage_xy[1] - seal.height - 1
        # Pop-in para firmas recién hechas (< 0.5s)
        # Buscar si ESTE sage firmó hace poco — sólo afecta visual
        # Aplicamos un pequeño bob senoidal y un fade-in
        bob = int(math.sin(t_total * 3 + sage_idx) * 1)
        seal_y_b = max(0, seal_y + bob)
        canvas.paste(seal, (seal_x, seal_y_b), seal)
        # Brillo extra alrededor del sello si es muy reciente
        if new_signs_age < 0.6:
            cx, cy = seal_x + seal.width // 2, seal_y_b + seal.height // 2
            r = 7 + int(new_signs_age * 6)
            alpha = max(0, int(180 * (1 - new_signs_age / 0.6)))
            # Pequeño anillo de chispa
            overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            od.ellipse((cx - r, cy - r, cx + r, cy + r),
                       outline=(255, 240, 180, alpha), width=1)
            canvas.alpha_composite(overlay)


def _sprite(sage_id: str, view: str = "front") -> Image.Image:
    key = (sage_id, view)
    if key not in _SPRITE_CACHE:
        _SPRITE_CACHE[key] = load_sage_sprite(sage_id, view=view)
    return _SPRITE_CACHE[key]


def _glyphs(color: RGB) -> list[Image.Image]:
    if color not in _GLYPHS_BY_COLOR:
        _GLYPHS_BY_COLOR[color] = generate_glyph_bitmaps(color)
    return _GLYPHS_BY_COLOR[color]


def _fire_frames() -> list[Image.Image]:
    global _FIRE_FRAMES
    if not _FIRE_FRAMES:
        _FIRE_FRAMES = [
            load_tile("fire_frame_a"),
            load_tile("fire_frame_b"),
            load_tile("fire_frame_c"),
        ]
    return _FIRE_FRAMES


def _book_frames() -> list[Image.Image]:
    global _BOOK_FRAMES
    if not _BOOK_FRAMES:
        _BOOK_FRAMES = [
            load_tile("book_closed"),
            load_tile("book_half_open"),
            load_tile("book_open"),
        ]
    return _BOOK_FRAMES


# ---------- helpers ----------

def _lerp_xy(a: tuple[int, int], b: tuple[int, int], t: float) -> tuple[int, int]:
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t))


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _walk_view(dx: int, dy: int) -> str:
    """Pick sprite view from a displacement vector. Horizontal dominates."""
    if abs(dx) >= abs(dy):
        return "profile_r" if dx > 0 else "profile_l"
    return "front" if dy > 0 else "back"


def _walk_bob(t: float) -> int:
    """Vertical pixels-up offset for the walking gait at ~2 steps/sec."""
    return int(abs(math.sin(t * 6.0)) * 2)


_CONSOLE_SIZE_CACHE: dict = {"t": 0.0, "size": (0, 0)}


def _cached_console_size(console, ttl: float = 0.5) -> tuple[int, int]:
    """Memoize console.size for `ttl` seconds. Rich's console.size probes the
    terminal on each access, which is wasteful at FPS=10 — and the user does
    not resize their terminal 10×/sec."""
    now = time.monotonic()
    if now - _CONSOLE_SIZE_CACHE["t"] > ttl:
        _CONSOLE_SIZE_CACHE["t"] = now
        _CONSOLE_SIZE_CACHE["size"] = (console.size.width, console.size.height)
    return _CONSOLE_SIZE_CACHE["size"]


def _apply_fire_frame(canvas: Image.Image, t_total: float) -> None:
    """Sobreescribe la chimenea con el frame actual de fuego."""
    frames = _fire_frames()
    idx = int(t_total * 4) % len(frames)   # 4 cambios por segundo
    canvas.paste(frames[idx], FIREPLACE_XY, frames[idx])


def _radial_glow_overlay(radius: int, color: tuple[int, int, int],
                         alpha_max: int) -> Image.Image:
    """Pequeño halo radial para overlay (cacheado por simplicidad sería ideal)."""
    size = radius * 2 + 1
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for r in range(radius, 0, -2):
        falloff = (1 - r / radius) ** 1.5
        alpha = int(alpha_max * falloff)
        if alpha > 0:
            d.ellipse((radius - r, radius - r, radius + r, radius + r),
                      fill=color + (alpha,))
    return img


def _apply_breathing_light(canvas: Image.Image, t_total: float) -> Image.Image:
    """Halo cálido extra sobre la chimenea que pulsa con el tiempo.
    Le da a la sala la sensación de que la luz 'respira'."""
    # Pulse rápido (fuego): 1.8 rad/s ≈ 0.28 Hz
    pulse_fire = 0.55 + 0.45 * math.sin(t_total * 1.8)
    radius_fire = 44 + int(10 * pulse_fire)
    alpha_fire = int(35 + 30 * pulse_fire)
    glow_fire = _radial_glow_overlay(radius_fire, (255, 150, 30), alpha_fire)
    fp_center = (FIREPLACE_XY[0] + 32, FIREPLACE_XY[1] + 30)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay.paste(glow_fire,
                  (fp_center[0] - glow_fire.width // 2,
                   fp_center[1] - glow_fire.height // 2), glow_fire)
    # Pulse lento global (warm wash extra): respira más despacio
    pulse_global = 0.5 + 0.5 * math.sin(t_total * 0.7)
    global_alpha = int(6 * pulse_global)
    if global_alpha > 0:
        wash = Image.new("RGBA", canvas.size, (255, 130, 40, global_alpha))
        overlay = Image.alpha_composite(overlay, wash)
    return Image.alpha_composite(canvas, overlay)


def _draw_orbit_particles(canvas: Image.Image, center: tuple[int, int],
                          radius_x: int, radius_y: int, t: float,
                          n_particles: int = 8,
                          color: tuple[int, int, int] = (200, 180, 255),
                          phase: float = 0.0) -> None:
    """Partículas orbitando elípticamente alrededor de `center`."""
    d = ImageDraw.Draw(canvas)
    cx, cy = center
    speed = 1.5
    for i in range(n_particles):
        angle = t * speed + i * (2 * math.pi / n_particles) + phase
        x = cx + radius_x * math.cos(angle)
        y = cy + radius_y * math.sin(angle)
        # Brillo central
        d.point((int(x), int(y)), fill=color + (255,))
        # Halo (alpha más bajo)
        d.point((int(x) + 1, int(y)), fill=color + (140,))
        d.point((int(x) - 1, int(y)), fill=color + (140,))
        d.point((int(x), int(y) + 1), fill=color + (140,))
        d.point((int(x), int(y) - 1), fill=color + (140,))


def _draw_book_floating(canvas: Image.Image, t: float) -> tuple[int, int]:
    """Libro flotante con frames de páginas pasando, sobre la mesa.
    Devuelve el centro del libro (para usarlo de pivote de partículas)."""
    frames = _book_frames()
    idx = int(t * 1.5) % len(frames)        # 1.5 cambios/seg
    book = frames[idx]
    # Flotación senoidal: el libro sube y baja sutilmente
    float_y = int(math.sin(t * 1.8) * 2)
    bx = TABLE_X + TABLE_W // 2 - book.width // 2
    by = TABLE_Y + 10 + float_y
    canvas.paste(book, (bx, by), book)
    return (bx + book.width // 2, by + book.height // 2)


def _draw_palantir_hud(canvas: Image.Image, round_num: int,
                       t: float) -> tuple[int, int]:
    """Pega un palantir grande con el número de ronda en el centro de la mesa.
    Devuelve el centro del palantir."""
    palantir = generate_palantir(round_n=round_num)
    float_y = int(math.sin(t * 2.2) * 1)
    px = TABLE_X + TABLE_W // 2 - palantir.width // 2
    py = TABLE_Y + 14 + float_y
    canvas.paste(palantir, (px, py), palantir)

    if round_num > 0:
        # Banner "ROUND N" sobre el palantir, escala 4x — el más visible
        # del HUD para que sea siempre legible aunque el terminal sea pequeño.
        n_digits = len(str(round_num))
        inner_w = n_digits * 3 + (n_digits - 1)
        pad = 2
        label_w = inner_w + pad * 2
        label_h = 5 + pad * 2
        label = Image.new("RGBA", (label_w, label_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(label)
        d.rectangle((0, 0, label_w - 1, label_h - 1),
                    outline=(255, 230, 90, 255), fill=(25, 8, 40, 240))
        _sprite_draw_number(d, pad, pad, round_num, (255, 250, 220, 255))
        scale_factor = 4
        label = label.resize(
            (label.width * scale_factor, label.height * scale_factor),
            Image.NEAREST,
        )
        bx = px + palantir.width // 2 - label.width // 2
        by = max(2, py - label.height - 2 + float_y)
        canvas.paste(label, (bx, by), label)

    return (px + palantir.width // 2, py + palantir.height // 2 - 4)


def _draw_bubbles(canvas: Image.Image, round_state: State,
                  round_num: int, seat_indices: list[int],
                  t_in_state: float = 0.0,
                  active_speaker_idx: int | None = None) -> None:
    """Burbujas multi-línea (2-3 líneas) que cambian cada ~1.5s — simulan
    la conversación en curso.

    `active_speaker_idx`: si se pasa (modo consensus turn-by-turn), SOLO
    se dibuja la burbuja del sabio activo. None = todas las burbujas
    visibles (modo paralelo clásico).
    """
    tic = int(t_in_state / 1.5)           # nuevo contenido cada 1.5s
    line_h = GLYPH_SIZE + 2               # altura por línea con gap

    for seat_idx, sage_idx in enumerate(seat_indices):
        if active_speaker_idx is not None and sage_idx != active_speaker_idx:
            continue
        sage = SAGES[sage_idx]
        _, sage_xy, _view = SEATS[seat_idx]
        # 2 o 3 líneas, fluctúa con sage + tic
        num_lines = 2 + ((sage_idx + tic) % 2)

        line_strips = []
        for li in range(num_lines):
            seed = f"{sage.id}-r{round_num}-t{tic}-l{li}"
            length = 3 + ((li + sage_idx + tic) % 3)
            glyphs = text_to_glyphs(seed, length=length)
            strip = render_glyphs_to_strip(glyphs, glyphs=_glyphs(sage.glyph_color))
            line_strips.append(strip)

        max_w = max(s.width for s in line_strips)
        bw = max_w + 8
        bh = line_h * num_lines + 4

        bubble = generate_bubble(bw, bh, color=COMIC_YELLOW)
        for i, strip in enumerate(line_strips):
            x_off = (bw - strip.width) // 2
            y_off = 3 + i * line_h
            bubble.paste(strip, (x_off, y_off), strip)

        bx = sage_xy[0] + 24 - bubble.width // 2
        by = sage_xy[1] - bubble.height - 2
        bx = max(2, min(canvas.width - bubble.width - 2, bx))
        by = max(1, by)
        canvas.paste(bubble, (bx, by), bubble)


def _fireplace_glow(canvas: Image.Image, intensity: float = 0.6) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow = Image.new("RGBA", (80, 60), (255, 140, 30, int(85 * intensity)))
    fp_x = FIREPLACE_XY[0] - 8
    overlay.paste(glow, (fp_x, 4), glow)
    return Image.alpha_composite(canvas, overlay)


# ---------- render por estado ----------

def render_frame(state: State, t_in_state: float, total_dur: float,
                 t_total: float = 0.0,
                 round_num: int = 0,
                 seat_indices: list[int] | None = None,
                 signed: set | None = None,
                 new_signs_age: float = 999.0,
                 active_speaker_idx: int | None = None) -> Image.Image:
    """Compone el frame correspondiente a (state, t).
    t_total: tiempo desde el inicio de la sesión (para animaciones cíclicas).
    round_num: número de ronda (sólo significativo en DEBATE).
    signed: set de índices de sabios que ya firmaron.
    new_signs_age: segundos desde las últimas firmas (para pop-in)."""
    if seat_indices is None:
        seat_indices = list(range(len(SAGES)))
    if signed is None:
        signed = set()
    progress = _ease_out(t_in_state / max(0.001, total_dur))

    # Estados donde NO se pinta el decor estático de mesa (el book/HUD ocupan esa zona)
    HIDE_TABLE_DECOR_STATES = {State.ANALIZANDO, State.DEBATE, State.JUEZ}

    # ENTRANDO: sabios cruzan corredor a sus asientos
    if state == State.ENTRANDO:
        canvas = _room()
        _add_static_table_decor(canvas)
        _apply_fire_frame(canvas, t_total)
        for seat_idx, sage_idx in enumerate(seat_indices):
            sage = SAGES[sage_idx]
            stagger = seat_idx / len(SAGES) * 0.5
            local = max(0.0, (progress - stagger) / max(0.001, 1 - stagger))
            if local <= 0:
                continue
            start_xy = DOOR_SPRITE_XY
            end_xy = SEATS[seat_idx][1]
            xy = _lerp_xy(start_xy, end_xy, local)
            view = _walk_view(end_xy[0] - start_xy[0], end_xy[1] - start_xy[1])
            bob = _walk_bob(t_total) if local < 0.98 else 0
            sp = _sprite(sage.id, view=view)
            canvas.paste(sp, (xy[0], xy[1] - bob), sp)
        return _apply_pulsing_lights(canvas, t_total, include_decor=True)

    # SALIENDO: sabios caminan hacia la puerta
    if state == State.SALIENDO:
        canvas = _room()
        _add_static_table_decor(canvas)
        _apply_fire_frame(canvas, t_total)
        for seat_idx, sage_idx in enumerate(seat_indices):
            sage = SAGES[sage_idx]
            stagger = seat_idx / len(SAGES) * 0.4
            local = max(0.0, (progress - stagger) / max(0.001, 1 - stagger))
            start_xy = SEATS[seat_idx][1]
            end_xy = DOOR_SPRITE_XY
            xy = _lerp_xy(start_xy, end_xy, local)
            view = _walk_view(end_xy[0] - start_xy[0], end_xy[1] - start_xy[1])
            bob = _walk_bob(t_total) if 0.02 < local < 0.98 else 0
            sp = _sprite(sage.id, view=view)
            canvas.paste(sp, (xy[0], xy[1] - bob), sp)
        return _apply_pulsing_lights(canvas, t_total, include_decor=True)

    # REPORTE: fade-out + chimenea agonizando
    if state == State.REPORTE:
        canvas = _room()
        _add_static_table_decor(canvas)
        _apply_fire_frame(canvas, t_total)
        canvas = _apply_pulsing_lights(canvas, t_total, include_decor=True)
        fade_alpha = int(220 * progress)
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, fade_alpha))
        return Image.alpha_composite(canvas, overlay)

    # === Estados con sabios sentados ===
    show_decor = state not in HIDE_TABLE_DECOR_STATES
    canvas = _scene_seated(seat_indices)
    if show_decor:
        _add_static_table_decor(canvas)
    _apply_fire_frame(canvas, t_total)

    if state == State.ANALIZANDO:
        book_center = _draw_book_floating(canvas, t_total)
        _draw_orbit_particles(canvas, book_center, 18, 8, t_total,
                              n_particles=10, color=(140, 220, 200))
        _draw_orbit_particles(canvas, book_center, 24, 12, t_total,
                              n_particles=6, color=(200, 240, 180), phase=math.pi)

    elif state == State.DEBATE:
        pal_center = _draw_palantir_hud(canvas, round_num, t_total)
        if round_num <= 5:
            p_color = (200, 180, 255)
        elif round_num <= 15:
            p_color = (220, 170, 255)
        elif round_num <= 25:
            p_color = (255, 150, 200)
        else:
            p_color = (255, 130, 130)
        _draw_orbit_particles(canvas, pal_center, 18, 9, t_total,
                              n_particles=10, color=p_color)
        _draw_bubbles(canvas, state, round_num, seat_indices, t_in_state,
                      active_speaker_idx=active_speaker_idx)
        _draw_signatures(canvas, seat_indices, signed, t_total, new_signs_age)

    elif state == State.JUEZ:
        pal_center = _draw_palantir_hud(canvas, 0, t_total)
        _draw_orbit_particles(canvas, pal_center, 22, 11, t_total,
                              n_particles=14, color=(255, 240, 200))
        _draw_signatures(canvas, seat_indices, signed, t_total, 999.0)

    elif state == State.ACUERDO:
        _draw_signatures(canvas, seat_indices, signed, t_total, 999.0)
        flash_alpha = int(180 * max(0.0, 1 - progress * 1.5))
        overlay = Image.new("RGBA", canvas.size, (255, 250, 220, flash_alpha))
        canvas = Image.alpha_composite(canvas, overlay)

    return _apply_pulsing_lights(canvas, t_total, include_decor=show_decor)


def _apply_pulsing_lights(canvas: Image.Image, t_total: float,
                          include_decor: bool) -> Image.Image:
    """Aplica todos los halos + warm wash + vignette con pulse temporal.
    El pulse modula intensidad de halos cálidos (sin afectar los mágicos)."""
    pulse = 0.85 + 0.18 * math.sin(t_total * 1.5)
    canvas = apply_lighting(canvas, pulse=pulse,
                            include_table_decor_halos=include_decor)
    return canvas


# ---------- bucle principal ----------

async def animate(speed: float = 1.0, scale: int = 1,
                  seed: int | None = None,
                  rounds: int = DEFAULT_DEBATE_ROUNDS,
                  sound: bool = True,
                  driver: callable | None = None) -> None:
    """Ejecuta la animación.

    `driver`: corutina opcional `(bus) -> None` que emite eventos. Si None,
    usa el `mock_driver` por defecto (animación de demo). El CLI pasa aquí
    `orchestrator.run_council` para que el consejo real conduzca la escena.
    """
    bus = EventBus()
    console = Console()
    player = SoundPlayer(enabled=sound)

    seat_indices = random_seat_indices(seed)
    session_t0 = time.monotonic()

    current: dict = {
        "state": State.ENTRANDO,
        "t0": session_t0,
        "round_num": 0,
        "signed": set(),       # set de sage_idx que han firmado
        "new_signs_t": 0.0,    # timestamp última firma (para anim. pop-in)
        "new_signs": [],       # sage_idx que firmaron en la ronda actual
        "turn": 0,             # turno actual (consensus mode)
        "speaker": "",         # sage_id hablando ahora (consensus mode)
        "speaker_idx": None,   # idx en SAGES del speaker (None=todos hablan)
        "plan_size": 0,        # items en el plan (consensus mode)
    }

    def renderable() -> Group:
        now = time.monotonic()
        t = now - current["t0"]
        t_total = now - session_t0
        state = current["state"]
        total = DEFAULT_TIMINGS[state] / speed
        new_signs_age = now - current["new_signs_t"] if current["new_signs"] else 999.0
        img = render_frame(state, t, total,
                           t_total=t_total,
                           round_num=current["round_num"],
                           seat_indices=seat_indices,
                           signed=current["signed"],
                           new_signs_age=new_signs_age,
                           active_speaker_idx=current.get("speaker_idx"))
        if scale > 1:
            img = upscale(img, scale)
        cw, ch = _cached_console_size(console)
        target_h_px = max(2, (ch - 2) * 2)
        if img.width > cw or img.height > target_h_px:
            factor = min(cw / img.width, target_h_px / img.height)
            img = img.resize((max(1, int(img.width * factor)),
                              max(1, int(img.height * factor))),
                             Image.NEAREST)
        pixels = Pixels.from_image(img)
        sub_template = STATE_SUBTITLES[state]
        if "{round}" in sub_template:
            sub = sub_template.format(
                round=current["round_num"],
                turn=current.get("turn", 0),
                speaker=current.get("speaker", "—"),
                plan_size=current.get("plan_size", 0),
                n_signed=len(current["signed"]),
            )
        else:
            sub = sub_template
        if state == State.REPORTE and current.get("report_path"):
            sub = f"Reporte generado: {current['report_path']}"
        subtitle = Text(f"  {sub}", style="bold yellow")
        return Group(pixels, subtitle)

    async def consume() -> None:
        async for event in bus.consume():
            # Solo en modo demo (mock_driver) fabricamos un reporte fake. En
            # modo real (driver = run_council) el CLI escribe el reporte de
            # verdad tras converger; un fake aquí lo duplicaba y confundía.
            if (event.state == State.REPORTE and "report_path" not in current
                    and driver is None):
                current["report_path"] = generate_fake_report()
            current["state"] = event.state
            current["t0"] = time.monotonic()
            if event.state == State.DEBATE:
                current["round_num"] = event.round_num
                new_signs = event.payload.get("signed_this_round", [])
                current["new_signs"] = list(new_signs)
                current["new_signs_t"] = time.monotonic()
                # Consensus mode emits the *current* vote state in
                # total_signed (a sage that flips block→sign→block needs
                # their seal removed). Use it as the source of truth.
                tot = event.payload.get("total_signed")
                if tot is not None:
                    current["signed"] = set(tot)
                else:
                    current["signed"].update(new_signs)
                current["turn"] = event.payload.get("turn", 0)
                current["speaker"] = event.payload.get("speaker", "")
                current["plan_size"] = event.payload.get("plan_size", 0)
                # speaker_idx: None = classic mode (no per-turn speaker
                # → show all bubbles). -1 = voice-only sage speaking
                # (Designer/Strategist, no seat → no bubble). >=0 =
                # restrict bubble to that seated sage.
                current["speaker_idx"] = event.payload.get("speaker_idx")

            # --- SOUND TRIGGERS (polifónicos con pygame.mixer) ---
            if event.state == State.ENTRANDO:
                player.play_loop("fire_crackle", slot="fire", volume=0.6)
                player.play_oneshot("door_creak", volume=0.7)
            elif event.state == State.SENTANDOSE:
                player.play_oneshot("chair_creak", volume=0.8)
            elif event.state == State.ANALIZANDO:
                player.play_oneshot("page_turn", volume=0.9)
                # Loop sutil de pluma mientras analizan (en canal hum)
                player.play_loop("quill_writing", slot="hum", volume=0.4)
            elif event.state == State.DEBATE:
                # Magic sparkle al iniciar cada ronda; el hum etéreo se
                # mantiene durante todo el debate
                if event.round_num == 1:
                    player.stop_loop(slot="hum", fade_ms=200)
                    player.play_loop("palantir_hum", slot="hum", volume=0.45)
                player.play_oneshot("magic_sparkle", volume=0.7)
                # Si hay nuevas firmas, golpe sordo suave por cada una
                new_signs = event.payload.get("signed_this_round", [])
                if new_signs:
                    player.play_oneshot("seal_thump", volume=0.4)
            elif event.state == State.JUEZ:
                player.play_oneshot("magic_sparkle", volume=0.9)
            elif event.state == State.ACUERDO:
                player.stop_loop(slot="hum", fade_ms=300)
                player.play_oneshot("seal_thump", volume=1.0)
            elif event.state == State.LEVANTANDOSE:
                player.play_oneshot("chair_creak", volume=0.6)
            elif event.state == State.SALIENDO:
                player.play_oneshot("door_creak", volume=0.7)
            elif event.state == State.REPORTE:
                player.stop()

    # Producer: mock_driver por defecto, o el driver custom pasado por el CLI
    if driver is None:
        driver_task = asyncio.create_task(
            mock_driver(bus, speed=speed, debate_rounds=rounds)
        )
    else:
        driver_task = asyncio.create_task(driver(bus))
    consumer = asyncio.create_task(consume())

    with Live(renderable(), console=console, refresh_per_second=FPS,
              auto_refresh=False, transient=False) as live:
        while not consumer.done():
            live.update(renderable(), refresh=True)
            await asyncio.sleep(FRAME_DT)
        live.update(renderable(), refresh=True)

    await driver_task
    await consumer


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo animada del Consejo en terminal.")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None,
                        help="Semilla para asignar sabios a asientos")
    parser.add_argument("--rounds", type=int, default=DEFAULT_DEBATE_ROUNDS,
                        help="Número de rondas de debate")
    parser.add_argument("--no-sound", action="store_true",
                        help="Desactiva el sonido (default: activado en Windows)")
    args = parser.parse_args()

    asyncio.run(animate(speed=args.speed, scale=args.scale,
                        seed=args.seed, rounds=args.rounds,
                        sound=not args.no_sound))


if __name__ == "__main__":
    main()
