"""Composición de la escena dungeon — v7 mística.

Cambios:
- 4 librerías grandes (24×40) contra muros laterales (2 cada lado)
- Palantir (esfera de cristal morada) en el centro de la mesa
- Planta brillante mágica a su lado
- Runa mágica grabada en el suelo
- Halos cyan/verde alrededor de los detalles mágicos
- Sombra de la mesa corregida (ya no corta las patas)
"""

from __future__ import annotations

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw
from rich.console import Console

from .renderer import ASSETS_DIR, load_sage_sprite, load_tile, render_image
from .sages import SAGES


def random_seat_indices(seed: int | None = None) -> list[int]:
    """Genera una permutación aleatoria de [0..len(SAGES)-1].
    Si seed se pasa, es determinista (útil para tests)."""
    rng = random.Random(seed)
    order = list(range(len(SAGES)))
    rng.shuffle(order)
    return order

CANVAS_W = 352
CANVAS_H = 224
BG_COLOR = (12, 10, 16, 255)

NORTH_WALL_ROWS = 2
NORTH_WALL_H = NORTH_WALL_ROWS * 16

FIREPLACE_W = 64
FIREPLACE_H = 72
FIREPLACE_XY = ((CANVAS_W - FIREPLACE_W) // 2, 0)

TABLE_W = 144
TABLE_H = 80
TABLE_X = (CANVAS_W - TABLE_W) // 2
TABLE_Y = (CANVAS_H - TABLE_H) // 2 + 12

# SEATS con orientación: (chair_xy, sage_xy, view)
#   view ∈ {"front", "back", "profile_l", "profile_r"}
#   La silla se selecciona automáticamente: front→chair, back→chair_back,
#   profile_r→chair_side, profile_l→chair_side (flipped horizontal)
# Posiciones acercadas a la mesa.
# SEATS: ((chair_xy), (sage_xy), view)
# Cada silla está colocada en EL LADO CORRECTO del sabio según su orientación:
#   - N sages miran sur → silla detrás (norte), centrada en X
#   - W sage mira este → silla a su oeste (chair_x menor)
#   - E sage mira oeste → silla a su este (chair_x mayor)
#   - S sages miran norte (espalda al usuario) → silla "detrás" = arriba en
#     pantalla, respaldo visible sobre la cabeza
SEATS: list[tuple[tuple[int, int], tuple[int, int], str]] = [
    ((104, 52),  (88, 66),   "front"),      # 0 — NW (sage+silla -8 south, hacia mesa)
    ((232, 52),  (216, 66),  "front"),      # 1 — NE (mismo)
    ((68, 92),   (84, 100),  "profile_r"),  # 2 — W head (sage+silla +12 east)
    ((248, 92),  (220, 100), "profile_l"),  # 3 — E head (sage+silla -12 west)
    ((236, 134), (220, 148), "back"),       # 4 — S-right (sage+silla -8 north)
    ((168, 134), (152, 148), "back"),       # 5 — S-mid
    ((100, 134), (84, 148),  "back"),       # 6 — S-left
]

DOOR_X = 16
DOOR_Y = CANVAS_H - 44
DOOR_SPRITE_XY = (10, CANVAS_H - 60)


def _floor_variant(x, y, plain, cracked, mossy, dirt):
    h = (x * 73 + y * 131) & 0xFF
    if h < 180:
        return plain
    elif h < 215:
        return cracked
    elif h < 240:
        return mossy
    return dirt


def _wall_variant(x, y, plain, cracked, mossy, deco):
    h = (x * 91 + y * 67) & 0xFF
    if h < 190:
        return plain
    elif h < 220:
        return cracked
    elif h < 245:
        return mossy
    return deco


def _radial_glow(radius, color, alpha_max=70):
    size = radius * 2 + 1
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for r in range(radius, 0, -1):
        falloff = (1 - r / radius) ** 1.6
        alpha = int(alpha_max * falloff)
        if alpha > 0:
            box = (radius - r, radius - r, radius + r, radius + r)
            d.ellipse(box, fill=color + (alpha,))
    return img


def _paste_glow(canvas, glow, center):
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    cx, cy = center
    overlay.paste(glow, (cx - glow.width // 2, cy - glow.height // 2), glow)
    return Image.alpha_composite(canvas, overlay)


def _warm_wash(canvas):
    overlay = Image.new("RGBA", canvas.size, (255, 130, 40, 18))
    return Image.alpha_composite(canvas, overlay)


def _corner_vignette(canvas):
    w, h = canvas.size
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    corner_radius = 120
    for cx, cy in [(0, 0), (w, 0), (0, h), (w, h)]:
        for r in range(corner_radius, 0, -4):
            alpha = int(75 * ((1 - r / corner_radius) ** 1.4))
            if alpha > 0:
                od.ellipse((cx - r, cy - r, cx + r, cy + r),
                           fill=(0, 0, 6, alpha))
    return Image.alpha_composite(canvas, overlay)


def compose_room(assets_dir: Path = ASSETS_DIR,
                 include_lighting: bool = True,
                 include_table_decor: bool = True) -> Image.Image:
    """Sala dungeon completa. Flags para que el animator desactive lighting
    estático (lo aplica por frame con pulse) y el decor de mesa (lo gestiona
    según el estado: book en ANALIZANDO, HUD en DEBATE)."""
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), BG_COLOR)

    floor_p = load_tile("floor", assets_dir)
    floor_c = load_tile("floor_cracked", assets_dir)
    floor_m = load_tile("floor_mossy", assets_dir)
    floor_d = load_tile("floor_dirt", assets_dir)
    floor_wood = load_tile("floor_wood", assets_dir)

    # --- SUELO ---
    wood_zone_x = (FIREPLACE_XY[0] - 32, FIREPLACE_XY[0] + FIREPLACE_W + 32)
    wood_zone_y = (NORTH_WALL_H, NORTH_WALL_H + 64)
    for y in range(0, CANVAS_H, 16):
        for x in range(0, CANVAS_W, 16):
            if wood_zone_x[0] <= x < wood_zone_x[1] and wood_zone_y[0] <= y < wood_zone_y[1]:
                canvas.paste(floor_wood, (x, y))
            else:
                canvas.paste(_floor_variant(x, y, floor_p, floor_c, floor_m, floor_d), (x, y))

    # --- MUROS ---
    wall_p = load_tile("wall", assets_dir)
    wall_c = load_tile("wall_cracked", assets_dir)
    wall_m = load_tile("wall_mossy", assets_dir)
    wall_deco = load_tile("wall_decorative", assets_dir)
    wall_top = load_tile("wall_top", assets_dir)

    for x in range(0, CANVAS_W, 16):
        for row_y in range(0, NORTH_WALL_H, 16):
            canvas.paste(_wall_variant(x, row_y, wall_p, wall_c, wall_m, wall_deco), (x, row_y))
    for x in range(0, CANVAS_W, 16):
        canvas.paste(_wall_variant(x, CANVAS_H - 16, wall_p, wall_c, wall_m, wall_deco),
                     (x, CANVAS_H - 16))
    for y in range(NORTH_WALL_H, CANVAS_H - 16, 16):
        canvas.paste(_wall_variant(0, y, wall_p, wall_c, wall_m, wall_deco), (0, y))
        canvas.paste(_wall_variant(CANVAS_W - 16, y, wall_p, wall_c, wall_m, wall_deco),
                     (CANVAS_W - 16, y))
    for x in range(0, CANVAS_W, 16):
        canvas.paste(wall_top, (x, 0), wall_top)

    # --- CHIMENEA ---
    fireplace = load_tile("fireplace", assets_dir)
    canvas.paste(fireplace, FIREPLACE_XY, fireplace)

    # --- PUERTA ---
    door = load_tile("door", assets_dir)
    canvas.paste(door, (DOOR_X, DOOR_Y), door)

    # --- ANTORCHAS ---
    torch = load_tile("torch", assets_dir)
    torch_positions = [
        (4, 80), (4, 132),
        (CANVAS_W - 12, 80), (CANVAS_W - 12, 132),
    ]
    for tx, ty in torch_positions:
        canvas.paste(torch, (tx, ty), torch)

    # --- ALFOMBRA ---
    rug = load_tile("rug", assets_dir)
    rug_x = (CANVAS_W - rug.width) // 2
    rug_y = (CANVAS_H - rug.height) // 2 + 18
    canvas.paste(rug, (rug_x, rug_y), rug)

    # --- 3 LIBRERÍAS GRANDES contra muros laterales ---
    # (la W lower se eliminó porque colisionaba con la puerta SW)
    bookshelf_lg = load_tile("bookshelf_large", assets_dir)
    canvas.paste(bookshelf_lg, (16, 36), bookshelf_lg)     # W upper
    canvas.paste(bookshelf_lg, (312, 36), bookshelf_lg)    # E upper
    canvas.paste(bookshelf_lg, (312, 156), bookshelf_lg)   # E lower

    # --- DECORACIÓN MENOR ---
    brazier = load_tile("brazier", assets_dir)
    chest = load_tile("chest", assets_dir)
    barrel = load_tile("barrel", assets_dir)
    anvil = load_tile("anvil", assets_dir)
    stones = load_tile("stones", assets_dir)
    crate = load_tile("crate", assets_dir)
    skull = load_tile("skull_pile", assets_dir)
    banner = load_tile("banner", assets_dir)
    weapon_rack = load_tile("weapon_rack", assets_dir)

    # Banners colgados en muro norte alto (2 a cada lado de la chimenea)
    canvas.paste(banner, (60, 16), banner)
    canvas.paste(banner, (280, 16), banner)

    # NW / NE entre librerías y chimenea
    canvas.paste(chest, (124, 56), chest)
    canvas.paste(weapon_rack, (216, 50), weapon_rack)
    canvas.paste(skull, (138, 100), skull)
    canvas.paste(skull, (202, 100), skull)

    # SW corner: barril + brazier
    canvas.paste(barrel, (48, 168), barrel)
    canvas.paste(crate, (62, 172), crate)
    canvas.paste(brazier, (74, 158), brazier)

    # SE corner: yunque + brazier + crate
    canvas.paste(anvil, (296, 188), anvil)
    canvas.paste(crate, (280, 188), crate)
    canvas.paste(brazier, (290, 158), brazier)

    # Stones esparcidas
    canvas.paste(stones, (140, 200), stones)
    canvas.paste(stones, (200, 200), stones)
    canvas.paste(stones, (48, 132), stones)
    canvas.paste(stones, (304, 132), stones)

    # --- RUNA MÁGICA EN EL SUELO (a la izquierda del SL sage, cerca de la puerta) ---
    rune = load_tile("magic_rune", assets_dir)
    rune_xy = (50, 194)
    canvas.paste(rune, rune_xy, rune)

    # --- MESA GRANDE ---
    table = load_tile("table", assets_dir)
    t_x = (CANVAS_W - table.width) // 2
    t_y = (CANVAS_H - table.height) // 2 + 12
    canvas.paste(table, (t_x, t_y), table)

    # --- DETALLES MÁGICOS ENCIMA DE LA MESA (decor estático) ---
    if include_table_decor:
        apply_table_decor(canvas, assets_dir, t_x, t_y, table.width)

    # --- SILLAS (orientación correcta según posición) ---
    chair_front = load_tile("chair", assets_dir)
    chair_back = load_tile("chair_back", assets_dir)
    chair_side = load_tile("chair_side", assets_dir)
    chair_side_flipped = chair_side.transpose(Image.FLIP_LEFT_RIGHT)
    for chair_xy, _, view in SEATS:
        if view == "back":
            canvas.paste(chair_back, chair_xy, chair_back)
        elif view == "profile_r":
            canvas.paste(chair_side, chair_xy, chair_side)
        elif view == "profile_l":
            canvas.paste(chair_side_flipped, chair_xy, chair_side_flipped)
        else:
            canvas.paste(chair_front, chair_xy, chair_front)

    if include_lighting:
        canvas = apply_lighting(canvas, torch_positions,
                                include_table_decor_halos=include_table_decor)

    return canvas


def apply_table_decor(canvas: Image.Image, assets_dir: Path,
                      t_x: int, t_y: int, table_w: int) -> None:
    """Pinta el decor estático de la mesa (palantir, planta, vela, scrolls).
    El animator lo OMITE durante ANALIZANDO/DEBATE (el book/HUD ocupan la
    posición central) y lo incluye en estados estáticos."""
    palantir = load_tile("palantir", assets_dir)
    plant = load_tile("glowing_plant", assets_dir)
    candle = load_tile("candle", assets_dir)
    scroll = load_tile("scroll", assets_dir)
    palantir_x = t_x + table_w // 2 - 6
    palantir_y = t_y + 26
    canvas.paste(palantir, (palantir_x, palantir_y), palantir)
    plant_x = palantir_x - 22
    plant_y = palantir_y - 6
    canvas.paste(plant, (plant_x, plant_y), plant)
    candle_x = palantir_x + 18
    candle_y = palantir_y + 6
    canvas.paste(candle, (candle_x, candle_y), candle)
    canvas.paste(scroll, (t_x + 30, t_y + 56), scroll)
    canvas.paste(scroll, (t_x + table_w - 38, t_y + 56), scroll)


# Posiciones fijas usadas por apply_lighting (referencia de halos mágicos)
_TABLE_CENTER_X = (CANVAS_W) // 2
_PALANTIR_GLOW_CENTER = (_TABLE_CENTER_X, (CANVAS_H - 80) // 2 + 12 + 36)
_PLANT_GLOW_CENTER = (_TABLE_CENTER_X - 18, (CANVAS_H - 80) // 2 + 12 + 22)
_CANDLE_GLOW_CENTER = (_TABLE_CENTER_X + 22, (CANVAS_H - 80) // 2 + 12 + 38)
_RUNE_XY = (50, 194)


def apply_lighting(canvas: Image.Image,
                   torch_positions: list[tuple[int, int]] | None = None,
                   pulse: float = 1.0,
                   include_table_decor_halos: bool = True) -> Image.Image:
    """Aplica todos los halos de luz + warm wash + vignette de esquina.
    `pulse` (0.5..1.5) multiplica intensidad de los halos cálidos para que
    el animator pueda hacer 'breathing'. Los halos mágicos (palantir/planta/
    runa) sólo se aplican si include_table_decor_halos=True."""
    if torch_positions is None:
        torch_positions = [
            (4, 80), (4, 132),
            (CANVAS_W - 12, 80), (CANVAS_W - 12, 132),
        ]
    p = max(0.3, pulse)
    # Halo chimenea (gigante, principal fuente de luz)
    glow_fire = _radial_glow(int(112 * (0.95 + 0.1 * p)),
                             (255, 150, 40), alpha_max=int(140 * p))
    fp_center = (FIREPLACE_XY[0] + FIREPLACE_W // 2, FIREPLACE_XY[1] + 42)
    canvas = _paste_glow(canvas, glow_fire, fp_center)
    # Antorchas
    glow_torch = _radial_glow(28, (255, 160, 50), alpha_max=int(80 * p))
    for tx, ty in torch_positions:
        canvas = _paste_glow(canvas, glow_torch, (tx + 4, ty + 4))
    # Braziers
    glow_brazier = _radial_glow(40, (255, 145, 30), alpha_max=int(85 * p))
    canvas = _paste_glow(canvas, glow_brazier, (81, 165))
    canvas = _paste_glow(canvas, glow_brazier, (297, 165))
    if include_table_decor_halos:
        # Vela sobre la mesa
        glow_candle = _radial_glow(18, (255, 200, 80), alpha_max=int(70 * p))
        canvas = _paste_glow(canvas, glow_candle, _CANDLE_GLOW_CENTER)
        # Palantir (cyan/morado)
        glow_palantir = _radial_glow(34, (130, 130, 240), alpha_max=95)
        canvas = _paste_glow(canvas, glow_palantir, _PALANTIR_GLOW_CENTER)
        # Planta brillante (verde-amarillo)
        glow_plant = _radial_glow(20, (180, 240, 120), alpha_max=80)
        canvas = _paste_glow(canvas, glow_plant, _PLANT_GLOW_CENTER)
    # Runa (siempre, está en el suelo)
    glow_rune = _radial_glow(22, (130, 220, 255), alpha_max=100)
    canvas = _paste_glow(canvas, glow_rune, (_RUNE_XY[0] + 7, _RUNE_XY[1] + 7))
    # Cozy effects
    canvas = _warm_wash(canvas)
    canvas = _corner_vignette(canvas)
    return canvas


def compose_scene(assets_dir: Path = ASSETS_DIR,
                  seat_indices: list[int] | None = None) -> Image.Image:
    """Sala con los 7 sabios sentados. Si `seat_indices` es None, se
    genera una asignación aleatoria sabio→asiento (consejo distinto cada vez).
    Pasa una lista [0..6] permutada para reproducibilidad."""
    if seat_indices is None:
        seat_indices = random_seat_indices()
    canvas = compose_room(assets_dir)
    for seat_idx, sage_idx in enumerate(seat_indices):
        sage = SAGES[sage_idx]
        _, sage_xy, view = SEATS[seat_idx]
        sprite = load_sage_sprite(sage.id, assets_dir, view=view)
        canvas.paste(sprite, sage_xy, sprite)
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser(description="Compone la escena dungeon mística del Consejo.")
    parser.add_argument("--out", type=Path, default=ASSETS_DIR / "scene_static.png")
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--scale", type=int, default=2)
    args = parser.parse_args()

    img = compose_scene()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.out)
    print(f"Escena guardada en {args.out.resolve()} ({img.width}x{img.height})")

    if not args.no_render:
        render_image(img, scale=args.scale, console=Console())


if __name__ == "__main__":
    main()
