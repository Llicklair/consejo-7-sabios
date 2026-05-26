"""Generador de sprites y tiles v4 — 48×48 con detalle JRPG-ish.

Bumpeo de tamaño respecto a v3 (era 32×32). Más pixeles → más detalle:
- Caras con cejas, ojos, nariz y boca/barba.
- Sombreado en 4 tonos: outline + sombra fuerte + base + highlight.
- Accesorios con grano (báculo con vetas, escudo con relieves, etc.).
- Sigue siendo placeholder respecto al arte hand-drawn final, pero
  apreciablemente más rico que v3.

Tiles 16×16 con detalle (brick pattern, llamas multi-capa, grano).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

from .sages import SAGES, RGB, Sage

SPRITE_SIZE = 48
TILE_SIZE = 16

OUTLINE = (15, 12, 18, 255)
SHADOW_HARD = (8, 6, 12, 255)


def _rgba(c: RGB, a: int = 255) -> tuple[int, int, int, int]:
    return (c[0], c[1], c[2], a)


def darker(c: RGB, f: float = 0.6) -> RGB:
    return (max(0, int(c[0] * f)), max(0, int(c[1] * f)), max(0, int(c[2] * f)))


def lighter(c: RGB, f: float = 1.3) -> RGB:
    return (min(255, int(c[0] * f)), min(255, int(c[1] * f)), min(255, int(c[2] * f)))


def _new(size: tuple[int, int]) -> Image.Image:
    return Image.new("RGBA", size, (0, 0, 0, 0))


# ---------- silueta base (48×48) ----------

def _silhouette(draw: ImageDraw.ImageDraw, sage: Sage) -> None:
    """Cuerpo humano genérico con outline + 4 tonos + cara expresiva.
    La zona y=0..13 queda libre para el sombrero/capucha/cuernos del
    arquetipo. La zona x=0..7 y x=40..47 queda libre para accesorios."""
    body = sage.sprite_color
    body_d = darker(body, 0.55)
    body_l = lighter(body, 1.25)
    skin = (255, 218, 175)
    if sage.id == "embajador":
        skin = (240, 195, 150)
    elif sage.id == "optimizador":
        skin = (255, 235, 210)
    skin_d = darker(skin, 0.78)
    skin_dd = darker(skin, 0.6)
    pants = (40, 32, 24)
    pants_d = darker(pants, 0.55)

    # --- CABEZA (10×12 aprox) ---
    # Outline (rectángulo redondeado simulado)
    draw.rectangle((16, 14, 31, 26), fill=OUTLINE)
    draw.point((16, 14), fill=(0, 0, 0, 0))  # esquina cortada
    draw.point((31, 14), fill=(0, 0, 0, 0))
    draw.point((16, 26), fill=(0, 0, 0, 0))
    draw.point((31, 26), fill=(0, 0, 0, 0))
    # Piel
    draw.rectangle((17, 15, 30, 25), fill=_rgba(skin))
    # Sombra derecha + barbilla
    draw.line((30, 16, 30, 25), fill=_rgba(skin_d))
    draw.line((17, 25, 30, 25), fill=_rgba(skin_d))
    # Brillo izquierda
    draw.line((17, 15, 17, 22), fill=_rgba(lighter(skin, 1.06)))

    # Cejas (2 px cada una)
    draw.line((19, 18, 21, 18), fill=SHADOW_HARD)
    draw.line((26, 18, 28, 18), fill=SHADOW_HARD)

    # Ojos
    draw.point((20, 20), fill=SHADOW_HARD)
    draw.point((21, 20), fill=SHADOW_HARD)
    draw.point((26, 20), fill=SHADOW_HARD)
    draw.point((27, 20), fill=SHADOW_HARD)
    # Brillo en los ojos
    draw.point((20, 19), fill=(255, 255, 255, 200))
    draw.point((26, 19), fill=(255, 255, 255, 200))

    # Nariz (sombra suave)
    draw.point((23, 22), fill=_rgba(skin_dd))
    draw.point((24, 22), fill=_rgba(skin_dd))
    draw.point((24, 23), fill=_rgba(skin_d))

    # Mejillas rosadas
    draw.point((19, 23), fill=(220, 150, 130, 220))
    draw.point((28, 23), fill=(220, 150, 130, 220))

    # Boca (línea sutil)
    draw.line((22, 24, 25, 24), fill=_rgba(skin_dd))

    # --- CUELLO ---
    draw.rectangle((21, 26, 26, 28), fill=_rgba(skin_d))

    # --- TORSO ---
    draw.rectangle((13, 28, 34, 38), fill=OUTLINE)
    draw.rectangle((14, 29, 33, 37), fill=_rgba(body))
    # Sombra der + inferior
    draw.line((33, 29, 33, 37), fill=_rgba(body_d))
    draw.line((14, 37, 33, 37), fill=_rgba(body_d))
    # Highlight izq
    draw.line((14, 29, 14, 35), fill=_rgba(body_l))

    # Cinturón
    draw.rectangle((14, 35, 33, 36), fill=(75, 50, 28, 255))
    # Hebilla dorada
    draw.rectangle((22, 35, 25, 36), fill=(230, 190, 70, 255))
    draw.point((22, 35), fill=(255, 230, 100, 255))

    # --- BRAZOS ---
    # Outline brazos
    draw.rectangle((10, 28, 13, 36), fill=OUTLINE)
    draw.rectangle((34, 28, 37, 36), fill=OUTLINE)
    # Relleno
    draw.rectangle((11, 29, 13, 35), fill=_rgba(body))
    draw.rectangle((34, 29, 36, 35), fill=_rgba(body))
    draw.line((13, 29, 13, 35), fill=_rgba(body_d))
    draw.line((34, 29, 34, 35), fill=_rgba(body_d))

    # --- MANOS ---
    draw.rectangle((10, 36, 13, 38), fill=_rgba(skin))
    draw.rectangle((34, 36, 37, 38), fill=_rgba(skin))
    draw.line((10, 38, 13, 38), fill=_rgba(skin_d))
    draw.line((34, 38, 37, 38), fill=_rgba(skin_d))

    # --- PIERNAS ---
    draw.rectangle((15, 38, 22, 44), fill=_rgba(pants))
    draw.rectangle((25, 38, 32, 44), fill=_rgba(pants))
    # Sombras laterales
    draw.line((22, 38, 22, 44), fill=_rgba(pants_d))
    draw.line((32, 38, 32, 44), fill=_rgba(pants_d))
    # Sombra interior (entre las piernas)
    draw.line((23, 38, 23, 44), fill=(25, 20, 15, 255))
    draw.line((24, 38, 24, 44), fill=(25, 20, 15, 255))

    # --- BOTAS ---
    boots = (28, 20, 14)
    boots_l = (65, 48, 30)
    draw.rectangle((14, 44, 22, 47), fill=boots + (255,))
    draw.rectangle((25, 44, 33, 47), fill=boots + (255,))
    # Suela
    draw.line((14, 47, 22, 47), fill=boots_l + (255,))
    draw.line((25, 47, 33, 47), fill=boots_l + (255,))
    # Highlight punta
    draw.point((15, 45), fill=boots_l + (255,))
    draw.point((26, 45), fill=boots_l + (255,))


# ---------- gear por arquetipo (48×48) ----------

def _gear_mago(draw: ImageDraw.ImageDraw, sage: Sage) -> None:
    body = sage.sprite_color
    body_d = darker(body, 0.55)
    body_l = lighter(body, 1.25)
    accent = sage.accent_color
    gold = (230, 190, 70)
    gold_d = (160, 125, 35)
    gem = (200, 80, 200)

    # Cono puntiagudo (apex en y=0)
    cone_widths = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]  # 12 filas
    for y, w in enumerate(cone_widths):
        x0, x1 = 23 - w, 24 + w
        # outline
        draw.point((x0 - 1, y), fill=OUTLINE)
        draw.point((x1 + 1, y), fill=OUTLINE)
        # fill
        draw.line((x0, y, x1, y), fill=_rgba(body))
        if w > 0:
            draw.point((x1, y), fill=_rgba(body_d))  # sombra derecha
            draw.point((x0, y), fill=_rgba(body_l))  # highlight izq

    # Banda dorada (y=10..11)
    draw.line((18, 10, 29, 10), fill=_rgba(gold))
    draw.line((18, 11, 29, 11), fill=_rgba(gold_d))
    draw.point((17, 10), fill=OUTLINE)
    draw.point((17, 11), fill=OUTLINE)
    draw.point((30, 10), fill=OUTLINE)
    draw.point((30, 11), fill=OUTLINE)
    # Gema central
    draw.rectangle((22, 10, 25, 11), fill=_rgba(gem))
    draw.point((22, 10), fill=(255, 180, 255, 255))

    # Ala ancha (y=12..13)
    draw.rectangle((13, 12, 34, 13), fill=_rgba(body))
    draw.line((13, 12, 34, 12), fill=OUTLINE)
    draw.line((13, 13, 34, 13), fill=_rgba(body_d))
    draw.point((12, 12), fill=OUTLINE)
    draw.point((35, 12), fill=OUTLINE)
    draw.point((12, 13), fill=OUTLINE)
    draw.point((35, 13), fill=OUTLINE)
    # Estrellas en el ala
    for sx in (17, 24, 31):
        draw.point((sx, 13), fill=_rgba(gold))

    # Barba blanca (cubre boca + mentón)
    beard = (240, 240, 230)
    beard_d = (180, 180, 170)
    # Bigote (cubre la boca)
    draw.line((19, 23, 28, 23), fill=_rgba(beard))
    draw.line((19, 24, 28, 24), fill=_rgba(beard_d))
    # Barba (de mejillas a mentón)
    draw.line((18, 25, 29, 25), fill=_rgba(beard))
    draw.line((19, 26, 28, 26), fill=_rgba(beard))
    # Pico de la barba (sale por debajo del rostro)
    draw.line((20, 27, 27, 27), fill=_rgba(beard))
    draw.point((23, 28), fill=_rgba(beard))
    draw.point((24, 28), fill=_rgba(beard))

    # Túnica con borde dorado (cuello + bajo)
    draw.line((15, 29, 32, 29), fill=_rgba(gold))
    draw.line((15, 36, 32, 36), fill=_rgba(gold))

    # Báculo (lado derecho)
    wood = (110, 70, 35)
    wood_d = (70, 45, 20)
    # Vara
    draw.line((40, 16, 40, 46), fill=_rgba(wood))
    draw.line((41, 16, 41, 46), fill=_rgba(wood_d))
    # Vetas
    draw.point((40, 22), fill=_rgba(wood_d))
    draw.point((41, 30), fill=_rgba(wood))
    draw.point((40, 38), fill=_rgba(wood_d))
    # Espiral arriba
    draw.point((42, 14), fill=_rgba(wood))
    draw.point((43, 13), fill=_rgba(wood))
    draw.point((44, 14), fill=_rgba(wood))
    draw.point((45, 15), fill=_rgba(wood))
    # Orbe en la curva
    draw.ellipse((41, 10, 46, 15), fill=OUTLINE)
    draw.ellipse((42, 11, 45, 14), fill=_rgba(accent))
    draw.point((43, 12), fill=(255, 255, 255, 230))


def _gear_caballero(draw: ImageDraw.ImageDraw, sage: Sage) -> None:
    body = sage.sprite_color
    body_d = darker(body, 0.55)
    body_l = lighter(body, 1.3)
    accent = sage.accent_color
    accent_l = lighter(accent, 1.2)
    gold = (230, 190, 70)

    # Yelmo entero (cubre cabeza y=4..16)
    draw.rectangle((14, 4, 33, 16), fill=OUTLINE)
    draw.rectangle((15, 5, 32, 15), fill=_rgba(body))
    # Highlight izq + sombra der
    draw.line((15, 5, 15, 15), fill=_rgba(body_l))
    draw.line((32, 5, 32, 15), fill=_rgba(body_d))
    # Visera con rejilla
    draw.rectangle((17, 11, 30, 13), fill=(30, 30, 38, 255))
    for vx in (19, 22, 25, 28):
        draw.point((vx, 12), fill=(80, 80, 100, 255))
    # Remaches dorados
    for rx in (16, 31):
        draw.point((rx, 8), fill=_rgba(gold))
        draw.point((rx, 13), fill=_rgba(gold))

    # Cresta vertical (penacho alto)
    draw.rectangle((22, 0, 25, 4), fill=OUTLINE)
    draw.line((23, 0, 23, 4), fill=_rgba(accent))
    draw.line((24, 0, 24, 4), fill=_rgba(accent_l))
    # Pluma del penacho (más alta)
    draw.point((23, 0), fill=_rgba(accent_l))
    draw.point((24, 0), fill=_rgba(accent_l))

    # Hombreras
    draw.rectangle((11, 27, 14, 31), fill=OUTLINE)
    draw.rectangle((33, 27, 36, 31), fill=OUTLINE)
    draw.line((12, 28, 12, 30), fill=_rgba(body_l))
    draw.line((34, 28, 34, 30), fill=_rgba(body_l))

    # Escudo grande a la izquierda (sustituye el brazo izq)
    sh_body = body
    sh_l = lighter(body, 1.2)
    sh_d = darker(body, 0.55)
    # Outline del escudo
    draw.rectangle((1, 26, 9, 41), fill=OUTLINE)
    # Cuerpo
    draw.rectangle((2, 27, 8, 40), fill=_rgba(sh_body))
    # Sombras
    draw.line((2, 27, 2, 40), fill=_rgba(sh_l))
    draw.line((8, 27, 8, 40), fill=_rgba(sh_d))
    # Cruz heráldica
    draw.line((2, 32, 8, 32), fill=_rgba(accent))
    draw.line((2, 33, 8, 33), fill=_rgba(accent))
    draw.line((4, 28, 4, 39), fill=_rgba(accent))
    draw.line((5, 28, 5, 39), fill=_rgba(accent))
    # Centro dorado
    draw.point((4, 32), fill=_rgba(gold))
    draw.point((5, 33), fill=_rgba(gold))

    # Espada en la mano derecha
    iron = (200, 200, 215)
    iron_l = (240, 240, 250)
    iron_d = (130, 130, 145)
    # Pomo
    draw.rectangle((39, 28, 41, 30), fill=_rgba(gold))
    # Guarda
    draw.rectangle((37, 30, 43, 31), fill=_rgba(gold))
    # Hoja
    draw.line((40, 32, 40, 46), fill=_rgba(iron))
    draw.line((41, 32, 41, 46), fill=_rgba(iron_d))
    draw.point((40, 33), fill=_rgba(iron_l))
    # Punta
    draw.point((40, 47), fill=OUTLINE)


def _gear_berserker(draw: ImageDraw.ImageDraw, sage: Sage) -> None:
    body = sage.sprite_color
    body_d = darker(body, 0.55)
    hair = sage.accent_color  # pelo pelirrojo
    hair_d = darker(hair, 0.6)
    hair_l = lighter(hair, 1.3)
    fur = (90, 70, 50)
    fur_l = (130, 100, 70)

    # Cuernos curvos saliendo de la cabeza
    # Izquierdo
    for (x, y) in [(16, 8), (15, 7), (14, 6), (13, 4), (12, 2)]:
        draw.point((x, y), fill=OUTLINE)
    draw.point((15, 8), fill=(220, 210, 190, 255))
    draw.point((14, 7), fill=(180, 170, 150, 255))
    draw.point((13, 5), fill=(220, 210, 190, 255))
    # Derecho
    for (x, y) in [(31, 8), (32, 7), (33, 6), (34, 4), (35, 2)]:
        draw.point((x, y), fill=OUTLINE)
    draw.point((32, 8), fill=(220, 210, 190, 255))
    draw.point((33, 7), fill=(180, 170, 150, 255))
    draw.point((34, 5), fill=(220, 210, 190, 255))

    # Pelo pelirrojo voluminoso encima
    draw.rectangle((16, 9, 31, 14), fill=OUTLINE)
    draw.rectangle((17, 10, 30, 13), fill=_rgba(hair))
    draw.line((17, 10, 30, 10), fill=_rgba(hair_l))
    # Mechones sobre la frente
    draw.point((19, 14), fill=_rgba(hair))
    draw.point((22, 14), fill=_rgba(hair))
    draw.point((25, 14), fill=_rgba(hair))
    draw.point((28, 14), fill=_rgba(hair))

    # Barba pelirroja larga
    draw.rectangle((16, 22, 31, 28), fill=OUTLINE)
    draw.rectangle((17, 23, 30, 27), fill=_rgba(hair))
    draw.line((17, 23, 30, 23), fill=_rgba(hair_l))
    # Pico de la barba (sale por debajo)
    draw.line((20, 28, 27, 28), fill=_rgba(hair))
    draw.point((22, 29), fill=_rgba(hair))
    draw.point((25, 29), fill=_rgba(hair_d))
    draw.point((23, 30), fill=_rgba(hair))
    draw.point((24, 30), fill=_rgba(hair))

    # Pintura tribal bajo los ojos
    draw.line((19, 22, 21, 22), fill=_rgba(hair_d))
    draw.line((26, 22, 28, 22), fill=_rgba(hair_d))

    # Hombreras de piel
    draw.rectangle((10, 27, 14, 32), fill=OUTLINE)
    draw.rectangle((34, 27, 38, 32), fill=OUTLINE)
    draw.rectangle((11, 28, 13, 31), fill=_rgba(fur))
    draw.rectangle((35, 28, 37, 31), fill=_rgba(fur))
    draw.line((11, 28, 13, 28), fill=_rgba(fur_l))
    draw.line((35, 28, 37, 28), fill=_rgba(fur_l))

    # Hacha doble filo al hombro derecho
    wood = (110, 70, 35)
    wood_d = (70, 45, 20)
    blade = (200, 205, 215)
    blade_d = (130, 135, 150)
    # Mango diagonal
    draw.line((36, 30, 47, 14), fill=_rgba(wood))
    draw.line((37, 30, 47, 15), fill=_rgba(wood_d))
    # Cabeza del hacha (doble filo)
    draw.polygon([(40, 8), (47, 9), (47, 16), (40, 17), (38, 12)], fill=OUTLINE)
    draw.polygon([(41, 10), (46, 11), (46, 15), (41, 16), (40, 13)],
                 fill=_rgba(blade))
    # Brillo en el filo
    draw.line((44, 11, 46, 13), fill=(255, 255, 255, 220))
    draw.point((42, 14), fill=_rgba(blade_d))


def _gear_bardo(draw: ImageDraw.ImageDraw, sage: Sage) -> None:
    body = sage.sprite_color
    body_d = darker(body, 0.55)
    body_l = lighter(body, 1.3)
    accent = sage.accent_color  # pluma naranja
    accent_l = lighter(accent, 1.25)
    gold = (230, 190, 70)
    leather = (140, 90, 45)
    leather_d = (90, 55, 25)
    string = (240, 230, 200)

    # Sombrero (boina ancha redondeada)
    draw.ellipse((13, 4, 34, 13), fill=OUTLINE)
    draw.ellipse((14, 5, 33, 12), fill=_rgba(body))
    # Highlight superior
    draw.ellipse((16, 6, 28, 9), fill=_rgba(body_l))
    # Sombra inferior
    draw.line((15, 11, 32, 11), fill=_rgba(body_d))
    # Banda dorada
    draw.line((14, 12, 33, 12), fill=_rgba(gold))

    # Pluma vertical alta
    draw.line((30, 0, 30, 6), fill=OUTLINE)
    draw.line((30, 1, 30, 5), fill=_rgba(accent))
    # Barbas de la pluma
    for py in range(1, 5):
        draw.point((29, py), fill=_rgba(accent_l))
        draw.point((31, py), fill=_rgba(accent))

    # Cabello castaño visible bajo el sombrero
    hair = (130, 85, 45)
    draw.line((17, 13, 30, 13), fill=_rgba(hair))

    # Capa visible (banda accent al cuello)
    draw.line((15, 29, 32, 29), fill=_rgba(accent))
    draw.line((15, 30, 32, 30), fill=_rgba(darker(accent, 0.7)))

    # Camisa con bordado
    draw.point((23, 32), fill=_rgba(gold))
    draw.point((24, 32), fill=_rgba(gold))
    draw.point((23, 33), fill=_rgba(gold))
    draw.point((24, 33), fill=_rgba(gold))

    # Laúd grande al frente (mango + caja)
    # Caja redondeada
    draw.ellipse((11, 32, 23, 44), fill=OUTLINE)
    draw.ellipse((12, 33, 22, 43), fill=_rgba(leather))
    draw.ellipse((13, 34, 19, 38), fill=_rgba(lighter(leather, 1.3)))
    # Hoyo central
    draw.ellipse((15, 37, 19, 41), fill=_rgba(leather_d))
    draw.ellipse((16, 38, 18, 40), fill=OUTLINE)
    # Cuerdas
    for cy in (35, 36, 37):
        draw.line((17, cy, 21, cy), fill=_rgba(string))
    # Mástil
    draw.rectangle((20, 27, 21, 33), fill=OUTLINE)
    draw.line((20, 28, 20, 32), fill=_rgba(leather))
    draw.line((21, 28, 21, 32), fill=_rgba(leather_d))
    # Clavijero
    draw.rectangle((19, 25, 22, 27), fill=_rgba(leather_d))
    draw.point((20, 26), fill=_rgba(gold))
    draw.point((21, 26), fill=_rgba(gold))

    # Bolsa de cuero al cinturón
    draw.rectangle((6, 33, 11, 38), fill=OUTLINE)
    draw.rectangle((7, 34, 10, 37), fill=_rgba(leather))
    draw.line((7, 34, 10, 34), fill=_rgba(lighter(leather, 1.3)))
    draw.point((8, 36), fill=_rgba(gold))
    draw.point((9, 36), fill=_rgba(gold))


def _gear_picaro(draw: ImageDraw.ImageDraw, sage: Sage) -> None:
    body = sage.sprite_color
    body_d = darker(body, 0.55)
    body_l = lighter(body, 1.2)
    accent = sage.accent_color  # verde brillante
    accent_l = lighter(accent, 1.3)
    leather = (90, 60, 35)
    leather_d = (60, 38, 20)
    blade = (200, 205, 215)
    blade_d = (130, 135, 150)

    # Capucha grande (cubre la frente)
    # Outline polígono
    draw.polygon([(13, 6), (34, 6), (37, 18), (10, 18)], fill=OUTLINE)
    # Relleno
    draw.polygon([(14, 7), (33, 7), (36, 17), (11, 17)], fill=_rgba(body))
    # Sombra der + highlight izq
    draw.line((34, 8, 35, 16), fill=_rgba(body_d))
    draw.line((13, 8, 12, 16), fill=_rgba(body_l))
    # Pliegues
    draw.point((20, 10), fill=_rgba(body_d))
    draw.point((27, 10), fill=_rgba(body_d))

    # Sombra dentro de la capucha (rostro oculto)
    draw.rectangle((17, 16, 30, 22), fill=(15, 12, 22, 255))

    # Pañuelo sobre la boca (cubre boca + mentón)
    draw.rectangle((17, 22, 30, 27), fill=OUTLINE)
    draw.rectangle((18, 23, 29, 26), fill=_rgba(body))
    draw.line((18, 23, 29, 23), fill=_rgba(body_l))
    draw.line((18, 26, 29, 26), fill=_rgba(body_d))
    # Pliegue en el pañuelo
    draw.point((23, 24), fill=_rgba(body_d))
    draw.point((24, 24), fill=_rgba(body_d))

    # Solo se ven los ojos brillantes verdes (sobreescribe en zona sombra)
    draw.point((20, 19), fill=_rgba(accent_l))
    draw.point((21, 19), fill=_rgba(accent))
    draw.point((26, 19), fill=_rgba(accent_l))
    draw.point((27, 19), fill=_rgba(accent))
    # Halo verde alrededor
    draw.point((20, 20), fill=(60, 180, 60, 120))
    draw.point((27, 20), fill=(60, 180, 60, 120))

    # Capa corta sobre hombros
    draw.rectangle((10, 28, 37, 30), fill=OUTLINE)
    draw.line((11, 29, 36, 29), fill=_rgba(body))
    draw.line((11, 30, 36, 30), fill=_rgba(body_d))

    # 2 dagas cruzadas en cinturón
    # Daga izq
    draw.line((9, 32, 9, 38), fill=OUTLINE)
    draw.line((10, 33, 10, 37), fill=_rgba(blade))
    draw.point((10, 37), fill=_rgba(blade_d))
    draw.rectangle((9, 38, 11, 39), fill=_rgba(leather))
    # Daga der
    draw.line((38, 32, 38, 38), fill=OUTLINE)
    draw.line((37, 33, 37, 37), fill=_rgba(blade))
    draw.point((37, 37), fill=_rgba(blade_d))
    draw.rectangle((36, 38, 38, 39), fill=_rgba(leather))

    # Bolsa de monedas al cinturón
    draw.ellipse((6, 33, 12, 39), fill=OUTLINE)
    draw.ellipse((7, 34, 11, 38), fill=_rgba(leather))
    # Brillo de moneda
    draw.point((8, 35), fill=(230, 190, 70, 255))
    draw.point((10, 36), fill=(230, 190, 70, 255))


def _gear_clerigo(draw: ImageDraw.ImageDraw, sage: Sage) -> None:
    body = sage.sprite_color
    body_d = darker(body, 0.7)
    body_l = lighter(body, 1.05)
    accent = sage.accent_color  # amarillo símbolo
    gold = (230, 190, 70)
    gold_l = (255, 230, 110)

    # Capucha clara amplia
    draw.polygon([(13, 6), (34, 6), (37, 18), (10, 18)], fill=OUTLINE)
    draw.polygon([(14, 7), (33, 7), (36, 17), (11, 17)], fill=_rgba(body))
    draw.line((34, 8, 35, 16), fill=_rgba(body_d))
    draw.line((13, 8, 12, 16), fill=_rgba(body_l))
    # Borde dorado de la capucha (línea decorativa)
    draw.line((14, 17, 33, 17), fill=_rgba(gold))

    # Sombra suave dentro de la capucha
    draw.rectangle((17, 16, 30, 22), fill=(105, 90, 70, 255))

    # Ojos serenos (negros con brillo)
    draw.point((20, 20), fill=SHADOW_HARD)
    draw.point((21, 20), fill=SHADOW_HARD)
    draw.point((26, 20), fill=SHADOW_HARD)
    draw.point((27, 20), fill=SHADOW_HARD)
    draw.point((20, 19), fill=(255, 255, 255, 220))
    draw.point((26, 19), fill=(255, 255, 255, 220))

    # Símbolo sagrado en el pecho (sol radial dorado)
    cx, cy = 23, 32
    # Centro
    draw.rectangle((cx, cy, cx + 1, cy + 1), fill=_rgba(accent))
    # Rayos
    for (dx, dy) in [(-2, 0), (3, 0), (0, -2), (0, 3),
                     (-2, -2), (3, -2), (-2, 3), (3, 3)]:
        draw.point((cx + dx, cy + dy), fill=_rgba(gold))
    # Anillo intermedio
    draw.rectangle((cx - 1, cy - 1, cx + 2, cy + 2), fill=_rgba(gold_l))
    draw.rectangle((cx, cy, cx + 1, cy + 1), fill=_rgba(accent))

    # Borde dorado de la túnica
    draw.line((15, 36, 32, 36), fill=_rgba(gold))

    # Maza con cabeza dorada en la mano derecha
    wood = (95, 60, 25)
    # Mango
    draw.line((42, 28, 42, 46), fill=_rgba(wood))
    draw.line((43, 28, 43, 46), fill=_rgba(darker(wood, 0.7)))
    # Cabeza de la maza (esférica)
    draw.ellipse((39, 24, 46, 31), fill=OUTLINE)
    draw.ellipse((40, 25, 45, 30), fill=_rgba(gold))
    draw.point((41, 26), fill=_rgba(gold_l))
    # Pinchos
    draw.point((39, 24), fill=_rgba(gold))
    draw.point((46, 24), fill=_rgba(gold))
    draw.point((39, 30), fill=_rgba(gold))
    draw.point((46, 30), fill=_rgba(gold))
    draw.point((42, 22), fill=_rgba(gold))
    draw.point((43, 22), fill=_rgba(gold))


def _gear_druida(draw: ImageDraw.ImageDraw, sage: Sage) -> None:
    body = sage.sprite_color
    body_l = lighter(body, 1.4)
    accent = sage.accent_color  # marrón bastón
    leaf = (60, 160, 70)
    leaf_l = (130, 220, 100)
    leaf_d = (30, 100, 40)
    hair = (110, 70, 30)
    hair_l = (160, 105, 50)

    # Corona de hojas (7 hojas distribuidas)
    leaves = [
        (24, 2), (20, 3), (28, 3), (17, 6), (31, 6), (22, 5), (26, 5),
    ]
    for (lx, ly) in leaves:
        draw.point((lx, ly - 1), fill=OUTLINE)
        draw.point((lx, ly), fill=_rgba(leaf))
        draw.point((lx + 1, ly), fill=_rgba(leaf_d))
        draw.point((lx, ly + 1), fill=_rgba(leaf_l))
    # Tallo conectando (sutil)
    draw.line((18, 8, 30, 8), fill=_rgba(leaf_d))

    # Cabello castaño largo cubriendo orejas
    draw.rectangle((15, 10, 33, 16), fill=OUTLINE)
    draw.rectangle((16, 11, 32, 15), fill=_rgba(hair))
    draw.line((16, 11, 32, 11), fill=_rgba(hair_l))
    # Mechones cayendo
    draw.line((15, 16, 16, 18), fill=_rgba(hair))
    draw.line((32, 16, 33, 18), fill=_rgba(hair))
    draw.point((14, 19), fill=_rgba(hair))
    draw.point((34, 19), fill=_rgba(hair))

    # Barba castaña corta
    draw.line((19, 25, 28, 25), fill=_rgba(hair))
    draw.line((20, 26, 27, 26), fill=_rgba(hair))
    draw.point((23, 27), fill=_rgba(hair_l))
    draw.point((24, 27), fill=_rgba(hair_l))
    # Hojas enredadas en la barba
    draw.point((20, 27), fill=_rgba(leaf))
    draw.point((27, 27), fill=_rgba(leaf))

    # Túnica con detalle vegetal en el pecho
    draw.point((22, 32), fill=_rgba(leaf))
    draw.point((23, 32), fill=_rgba(leaf_l))
    draw.point((24, 32), fill=_rgba(leaf_l))
    draw.point((25, 32), fill=_rgba(leaf))
    draw.line((23, 33, 24, 33), fill=_rgba(leaf_d))

    # Bastón largo a la izquierda
    wood = (110, 70, 35)
    wood_d = (70, 45, 20)
    draw.line((6, 14, 6, 47), fill=_rgba(wood))
    draw.line((7, 14, 7, 47), fill=_rgba(wood_d))
    # Vetas
    for vy in (22, 30, 38):
        draw.point((6, vy), fill=_rgba(wood_d))
    # Cristal-rama arriba del bastón
    draw.point((5, 13), fill=_rgba(leaf))
    draw.point((6, 12), fill=_rgba(leaf))
    draw.point((7, 12), fill=_rgba(leaf_l))
    draw.point((8, 13), fill=_rgba(leaf))
    draw.point((6, 11), fill=_rgba(leaf_l))
    draw.point((7, 11), fill=_rgba(leaf))

    # Búho posado al hombro derecho
    owl = (145, 110, 65)
    owl_d = (95, 70, 35)
    owl_l = (190, 150, 95)
    draw.rectangle((37, 24, 43, 32), fill=OUTLINE)
    draw.rectangle((38, 25, 42, 31), fill=_rgba(owl))
    draw.line((38, 25, 42, 25), fill=_rgba(owl_l))
    # Ojos del búho
    draw.point((39, 27), fill=(255, 220, 50, 255))
    draw.point((41, 27), fill=(255, 220, 50, 255))
    draw.point((39, 28), fill=OUTLINE)
    draw.point((41, 28), fill=OUTLINE)
    # Pico
    draw.point((40, 29), fill=_rgba(owl_d))
    # Alas plegadas
    draw.point((38, 30), fill=_rgba(owl_d))
    draw.point((42, 30), fill=_rgba(owl_d))


_GEAR: dict[str, Callable[[ImageDraw.ImageDraw, Sage], None]] = {
    "Mago": _gear_mago,
    "Caballero": _gear_caballero,
    "Berserker": _gear_berserker,
    "Bardo": _gear_bardo,
    "Pícaro": _gear_picaro,
    "Clérigo": _gear_clerigo,
    "Druida": _gear_druida,
}


def generate_sage_sprite(sage: Sage) -> Image.Image:
    img = _new((SPRITE_SIZE, SPRITE_SIZE))
    draw = ImageDraw.Draw(img)
    _silhouette(draw, sage)
    gear = _GEAR.get(sage.archetype)
    if gear is None:
        raise ValueError(f"Sin adorno para arquetipo {sage.archetype!r}")
    gear(draw, sage)
    return img


def generate_sage_sprite_back(sage: Sage) -> Image.Image:
    """Vista de espalda — silueta encapuchada sin cara visible, con
    indicador del arquetipo arriba (cono, cresta, cuernos, pluma, etc.)."""
    img = _new((SPRITE_SIZE, SPRITE_SIZE))
    d = ImageDraw.Draw(img)
    body = sage.sprite_color
    body_d = darker(body, 0.55)
    body_l = lighter(body, 1.25)
    accent = sage.accent_color
    pants = (40, 32, 24)
    pants_d = darker(pants, 0.55)
    hair = (110, 70, 35) if sage.id in ("conservador", "embajador") else (50, 40, 30)

    # Capucha/cabeza desde atrás (no se ve cara)
    d.rectangle((14, 12, 33, 27), fill=OUTLINE)
    d.rectangle((15, 13, 32, 26), fill=_rgba(body))
    d.line((32, 14, 32, 26), fill=_rgba(body_d))
    d.line((15, 13, 15, 26), fill=_rgba(body_l))
    # Cabello visible bajo el sombrero (mecha de pelo en la nuca)
    d.line((18, 20, 29, 20), fill=_rgba(hair))
    d.line((18, 21, 29, 21), fill=_rgba(hair))

    # Capa/torso desde atrás
    d.rectangle((13, 27, 34, 41), fill=OUTLINE)
    d.rectangle((14, 28, 33, 40), fill=_rgba(body))
    d.line((33, 28, 33, 40), fill=_rgba(body_d))
    d.line((14, 28, 14, 39), fill=_rgba(body_l))
    # Pliegues centrales (la espalda muestra el pliegue de la capa)
    d.line((23, 28, 23, 40), fill=_rgba(body_d))
    d.line((24, 28, 24, 40), fill=_rgba(body_l))

    # Brazos (visibles a los lados)
    d.rectangle((10, 28, 13, 36), fill=OUTLINE)
    d.rectangle((34, 28, 37, 36), fill=OUTLINE)
    d.rectangle((11, 29, 13, 35), fill=_rgba(body))
    d.rectangle((34, 29, 36, 35), fill=_rgba(body))

    # Piernas + botas (mismas que de frente)
    d.rectangle((15, 41, 22, 46), fill=_rgba(pants))
    d.rectangle((25, 41, 32, 46), fill=_rgba(pants))
    d.line((22, 41, 22, 46), fill=_rgba(pants_d))
    d.line((32, 41, 32, 46), fill=_rgba(pants_d))
    d.rectangle((14, 46, 22, 47), fill=(28, 20, 14, 255))
    d.rectangle((25, 46, 33, 47), fill=(28, 20, 14, 255))

    # --- INDICADOR DEL ARQUETIPO (visible desde atrás) ---
    if sage.archetype == "Mago":
        # Punta del sombrero cónico
        for y in range(0, 12):
            w = max(0, y - 2) // 2
            d.line((24 - w, y, 23 + w, y), fill=_rgba(body))
        d.point((23, 11), fill=_rgba(accent))
        d.point((24, 11), fill=_rgba(accent))
    elif sage.archetype == "Caballero":
        # Yelmo + cresta vertical
        d.rectangle((13, 4, 34, 13), fill=OUTLINE)
        d.rectangle((14, 5, 33, 12), fill=_rgba(body))
        d.line((14, 5, 14, 12), fill=_rgba(body_l))
        d.rectangle((22, 0, 25, 4), fill=OUTLINE)
        d.line((23, 0, 23, 4), fill=_rgba(accent))
        d.line((24, 0, 24, 4), fill=lighter(accent, 1.2) + (255,))
    elif sage.archetype == "Berserker":
        # Pelo largo (back) + cuernos saliendo a los lados
        d.rectangle((15, 6, 32, 14), fill=_rgba(accent))
        d.line((15, 6, 32, 6), fill=lighter(accent, 1.3) + (255,))
        # Cuernos
        for (x, y) in [(14, 8), (13, 6), (12, 4), (11, 2)]:
            d.point((x, y), fill=OUTLINE)
            d.point((x, y - 1), fill=(220, 210, 190, 255))
        for (x, y) in [(33, 8), (34, 6), (35, 4), (36, 2)]:
            d.point((x, y), fill=OUTLINE)
            d.point((x, y - 1), fill=(220, 210, 190, 255))
    elif sage.archetype == "Bardo":
        # Sombrero redondeado (back) + pluma
        d.ellipse((13, 6, 34, 13), fill=OUTLINE)
        d.ellipse((14, 7, 33, 12), fill=_rgba(body))
        d.line((30, 0, 30, 6), fill=OUTLINE)
        d.line((30, 1, 30, 6), fill=_rgba(accent))
    elif sage.archetype == "Pícaro":
        # Capucha picuda
        d.polygon([(15, 8), (32, 8), (33, 12), (14, 12)], fill=OUTLINE)
        d.polygon([(16, 9), (31, 9), (32, 11), (15, 11)], fill=_rgba(body))
        d.point((24, 6), fill=_rgba(body))
        d.point((25, 6), fill=_rgba(body))
    elif sage.archetype == "Clérigo":
        # Capucha más clara + borde dorado
        d.polygon([(15, 8), (32, 8), (33, 12), (14, 12)], fill=OUTLINE)
        d.polygon([(16, 9), (31, 9), (32, 11), (15, 11)], fill=_rgba(body))
        d.line((14, 12, 33, 12), fill=(220, 175, 60, 255))
    elif sage.archetype == "Druida":
        # Corona de hojas
        for (lx, ly) in [(20, 6), (24, 4), (28, 6), (18, 9), (30, 9)]:
            d.point((lx, ly), fill=(60, 160, 70, 255))
            d.point((lx + 1, ly + 1), fill=(30, 100, 40, 255))
    return img


def generate_sage_sprite_profile(sage: Sage, facing: str = "right") -> Image.Image:
    """Vista de perfil — silueta lateral con un solo ojo + nariz pronunciada.
    Por defecto mira a la derecha; pasa facing='left' para espejar."""
    img = _new((SPRITE_SIZE, SPRITE_SIZE))
    d = ImageDraw.Draw(img)
    body = sage.sprite_color
    body_d = darker(body, 0.55)
    body_l = lighter(body, 1.25)
    accent = sage.accent_color
    skin = (255, 218, 175) if sage.id != "embajador" else (240, 195, 150)
    skin_d = darker(skin, 0.78)
    pants = (40, 32, 24)
    pants_d = darker(pants, 0.55)

    # Cabeza de perfil (ligeramente narrower)
    d.rectangle((16, 14, 30, 26), fill=OUTLINE)
    d.rectangle((17, 15, 29, 25), fill=_rgba(skin))
    # Sombra detrás (zona occipital)
    d.line((17, 15, 17, 25), fill=_rgba(skin_d))

    # Nariz pronunciada (apunta a la derecha)
    d.point((30, 19), fill=_rgba(skin))
    d.point((30, 20), fill=_rgba(skin))
    d.point((31, 19), fill=_rgba(skin_d))

    # Ojo (un solo ojo visible)
    d.point((26, 19), fill=SHADOW_HARD)
    d.point((26, 18), fill=(255, 255, 255, 200))

    # Boca
    d.point((28, 22), fill=_rgba(skin_d))

    # Oreja
    d.point((20, 20), fill=_rgba(skin_d))

    # Cuello
    d.rectangle((20, 26, 26, 28), fill=_rgba(skin_d))

    # Torso de perfil (más estrecho)
    d.rectangle((15, 28, 30, 41), fill=OUTLINE)
    d.rectangle((16, 29, 29, 40), fill=_rgba(body))
    d.line((29, 29, 29, 40), fill=_rgba(body_d))
    d.line((16, 29, 16, 40), fill=_rgba(body_l))
    # Cinturón
    d.line((16, 36, 29, 36), fill=(75, 50, 28, 255))

    # Un solo brazo visible (en el lado posterior)
    d.rectangle((12, 29, 15, 37), fill=OUTLINE)
    d.rectangle((13, 30, 14, 36), fill=_rgba(body))
    # Mano
    d.rectangle((13, 37, 14, 39), fill=_rgba(skin))

    # Piernas de perfil (una delante de la otra)
    d.rectangle((18, 41, 24, 46), fill=_rgba(pants))
    d.rectangle((22, 41, 28, 46), fill=_rgba(pants))
    d.line((24, 41, 24, 46), fill=_rgba(pants_d))
    d.line((28, 41, 28, 46), fill=_rgba(pants_d))

    # Botas
    d.rectangle((17, 46, 24, 47), fill=(28, 20, 14, 255))
    d.rectangle((22, 46, 29, 47), fill=(28, 20, 14, 255))

    # --- HEADGEAR/GEAR del arquetipo ---
    if sage.archetype == "Mago":
        # Cono lateral
        for y in range(0, 14):
            w = max(0, y - 2) // 2
            d.line((22 - w, y, 24 + w, y), fill=_rgba(body))
        d.line((14, 12, 30, 12), fill=_rgba(body))
        d.point((24, 11), fill=_rgba(accent))
        # Barba blanca visible de perfil
        beard = (240, 240, 230)
        d.line((23, 24, 29, 24), fill=_rgba(beard))
        d.line((24, 25, 28, 25), fill=_rgba(beard))
        d.point((26, 26), fill=_rgba(beard))
        # Báculo
        d.line((10, 18, 10, 47), fill=(100, 65, 30, 255))
        d.ellipse((8, 14, 12, 18), fill=_rgba(accent))
    elif sage.archetype == "Caballero":
        d.rectangle((15, 6, 30, 14), fill=OUTLINE)
        d.rectangle((16, 7, 29, 13), fill=_rgba(body))
        d.rectangle((22, 0, 25, 6), fill=OUTLINE)
        d.line((23, 1, 23, 5), fill=_rgba(accent))
        d.line((24, 1, 24, 5), fill=lighter(accent, 1.2) + (255,))
        # Visor (cubre el ojo)
        d.line((17, 11, 28, 11), fill=SHADOW_HARD)
    elif sage.archetype == "Berserker":
        # Cuernos: uno hacia atrás (más visible), uno cubierto
        d.rectangle((16, 8, 29, 14), fill=_rgba(accent))
        d.line((16, 7, 12, 3), fill=OUTLINE)
        d.point((14, 5), fill=(220, 210, 190, 255))
        # Barba pelirroja
        d.line((23, 24, 29, 24), fill=_rgba(accent))
        d.line((24, 25, 28, 25), fill=_rgba(accent))
        # Hacha al hombro
        d.line((12, 22, 6, 14), fill=(100, 65, 30, 255))
        d.polygon([(2, 10), (8, 12), (7, 16), (3, 14)], fill=_rgba(body))
    elif sage.archetype == "Bardo":
        d.ellipse((15, 6, 30, 13), fill=_rgba(body))
        d.line((28, 0, 28, 6), fill=_rgba(accent))
        # Laúd colgando al frente del torso
        d.ellipse((28, 31, 34, 37), fill=(140, 90, 45, 255))
        d.line((30, 28, 30, 31), fill=(80, 50, 25, 255))
    elif sage.archetype == "Pícaro":
        d.polygon([(14, 8), (30, 8), (31, 14), (13, 14)], fill=OUTLINE)
        d.polygon([(15, 9), (29, 9), (30, 13), (14, 13)], fill=_rgba(body))
        # Capucha cubre el ojo
        d.rectangle((20, 16, 28, 21), fill=(15, 12, 22, 255))
        # Ojo verde brillante
        d.point((26, 19), fill=_rgba(accent))
        d.point((26, 18), fill=(255, 255, 255, 180))
        # Daga
        d.line((10, 33, 10, 38), fill=(170, 175, 185, 255))
    elif sage.archetype == "Clérigo":
        d.polygon([(14, 8), (30, 8), (31, 14), (13, 14)], fill=OUTLINE)
        d.polygon([(15, 9), (29, 9), (30, 13), (14, 13)], fill=_rgba(body))
        d.line((15, 13, 29, 13), fill=(220, 175, 60, 255))
        # Maza
        d.line((10, 28, 10, 38), fill=(100, 65, 30, 255))
        d.ellipse((7, 24, 13, 30), fill=(220, 175, 60, 255))
    elif sage.archetype == "Druida":
        # Hojas
        for (lx, ly) in [(20, 4), (24, 3), (28, 4)]:
            d.point((lx, ly), fill=(60, 160, 70, 255))
            d.point((lx + 1, ly + 1), fill=(130, 220, 100, 255))
        # Bastón al lado
        d.line((10, 14, 10, 47), fill=(100, 65, 30, 255))
        d.point((10, 12), fill=(60, 160, 70, 255))

    if facing == "left":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img


# ---------- tiles ----------

def generate_floor() -> Image.Image:
    img = _new((TILE_SIZE, TILE_SIZE))
    d = ImageDraw.Draw(img)
    base = (78, 72, 65)
    base_d = (52, 48, 44)
    base_l = (98, 90, 80)
    d.rectangle((0, 0, 15, 15), fill=base + (255,))
    d.line((0, 7, 15, 7), fill=base_d + (255,))
    d.line((0, 8, 15, 8), fill=(30, 28, 25, 255))
    d.line((7, 0, 7, 15), fill=base_d + (255,))
    d.line((8, 0, 8, 15), fill=(30, 28, 25, 255))
    d.point((3, 3), fill=base_l + (255,))
    d.point((11, 4), fill=base_l + (255,))
    d.point((4, 12), fill=base_l + (255,))
    d.point((12, 11), fill=base_d + (255,))
    d.point((13, 12), fill=base_d + (255,))
    return img


def generate_floor_cracked() -> Image.Image:
    img = generate_floor()
    d = ImageDraw.Draw(img)
    d.line((2, 5, 6, 10), fill=(25, 22, 20, 255))
    d.point((3, 6), fill=(20, 18, 16, 255))
    d.point((4, 7), fill=(20, 18, 16, 255))
    d.point((5, 8), fill=(20, 18, 16, 255))
    d.line((10, 2, 13, 6), fill=(25, 22, 20, 255))
    return img


def generate_floor_mossy() -> Image.Image:
    img = generate_floor()
    d = ImageDraw.Draw(img)
    moss = (60, 110, 50, 255)
    moss_d = (40, 80, 35, 255)
    d.point((3, 8), fill=moss)
    d.point((5, 8), fill=moss_d)
    d.point((10, 8), fill=moss)
    d.point((12, 8), fill=moss_d)
    d.point((8, 4), fill=moss)
    d.point((8, 12), fill=moss_d)
    return img


def generate_floor_wood() -> Image.Image:
    img = _new((TILE_SIZE, TILE_SIZE))
    d = ImageDraw.Draw(img)
    wood = (110, 70, 35)
    wood_l = (150, 100, 55)
    wood_d = (70, 40, 18)
    wood_dd = (45, 25, 10)
    d.rectangle((0, 0, 15, 4), fill=wood + (255,))
    d.rectangle((0, 5, 15, 9), fill=wood + (255,))
    d.rectangle((0, 10, 15, 15), fill=wood + (255,))
    d.line((0, 4, 15, 4), fill=wood_dd + (255,))
    d.line((0, 9, 15, 9), fill=wood_dd + (255,))
    d.line((0, 0, 15, 0), fill=wood_l + (255,))
    d.line((0, 5, 15, 5), fill=wood_l + (255,))
    d.line((0, 10, 15, 10), fill=wood_l + (255,))
    d.point((4, 2), fill=wood_d + (255,))
    d.point((10, 7), fill=wood_d + (255,))
    d.point((6, 13), fill=wood_d + (255,))
    d.point((12, 12), fill=wood_d + (255,))
    return img


def generate_wall() -> Image.Image:
    img = _new((TILE_SIZE, TILE_SIZE))
    d = ImageDraw.Draw(img)
    stone = (62, 58, 70)
    stone_l = (88, 82, 95)
    stone_d = (38, 36, 45)
    mortar = (22, 20, 28)
    d.rectangle((0, 0, 15, 15), fill=stone + (255,))
    d.line((0, 4, 15, 4), fill=mortar + (255,))
    d.line((0, 11, 15, 11), fill=mortar + (255,))
    d.line((6, 0, 6, 4), fill=mortar + (255,))
    d.line((2, 5, 2, 10), fill=mortar + (255,))
    d.line((11, 5, 11, 10), fill=mortar + (255,))
    d.line((9, 12, 9, 15), fill=mortar + (255,))
    d.line((1, 0, 5, 0), fill=stone_l + (255,))
    d.line((7, 0, 14, 0), fill=stone_l + (255,))
    d.line((0, 5, 1, 5), fill=stone_l + (255,))
    d.line((3, 5, 10, 5), fill=stone_l + (255,))
    d.line((12, 5, 15, 5), fill=stone_l + (255,))
    d.line((0, 12, 8, 12), fill=stone_l + (255,))
    d.line((10, 12, 15, 12), fill=stone_l + (255,))
    d.line((1, 3, 5, 3), fill=stone_d + (255,))
    d.line((7, 3, 14, 3), fill=stone_d + (255,))
    d.line((0, 10, 1, 10), fill=stone_d + (255,))
    d.line((3, 10, 10, 10), fill=stone_d + (255,))
    return img


def generate_wall_cracked() -> Image.Image:
    """Variante de muro con grieta diagonal."""
    img = generate_wall()
    d = ImageDraw.Draw(img)
    crack = (20, 18, 25, 255)
    crack_l = (40, 38, 50, 255)
    # Grieta principal diagonal
    d.line((3, 2, 8, 9), fill=crack)
    d.point((4, 3), fill=crack)
    d.point((5, 5), fill=crack)
    d.point((7, 8), fill=crack)
    # Grieta secundaria
    d.line((10, 12, 13, 15), fill=crack)
    d.point((11, 13), fill=crack_l)
    return img


def generate_wall_mossy() -> Image.Image:
    """Variante con musgo en bloques inferiores."""
    img = generate_wall()
    d = ImageDraw.Draw(img)
    moss = (55, 100, 45, 255)
    moss_l = (90, 140, 65, 255)
    moss_d = (30, 65, 25, 255)
    # Parche grande de musgo
    d.point((1, 13), fill=moss_l)
    d.point((2, 13), fill=moss)
    d.point((3, 13), fill=moss)
    d.point((4, 14), fill=moss)
    d.point((5, 13), fill=moss_l)
    d.point((6, 14), fill=moss)
    d.point((4, 15), fill=moss_d)
    d.point((5, 15), fill=moss_d)
    # Parche pequeño superior
    d.point((12, 2), fill=moss)
    d.point((13, 2), fill=moss_l)
    d.point((12, 3), fill=moss_d)
    return img


def generate_wall_decorative() -> Image.Image:
    """Variante con piedra tallada / nicho con gema."""
    img = generate_wall()
    d = ImageDraw.Draw(img)
    gem = (180, 50, 80, 255)
    gem_l = (240, 110, 130, 255)
    iron = (60, 60, 70, 255)
    iron_l = (140, 140, 155, 255)
    # Nicho rectangular tallado
    d.rectangle((6, 6, 9, 10), fill=(15, 12, 18, 255))
    d.rectangle((7, 7, 8, 9), fill=iron)
    # Gema en el nicho
    d.point((7, 8), fill=gem_l)
    d.point((8, 8), fill=gem)
    # Marco
    d.line((6, 6, 9, 6), fill=iron_l)
    d.line((6, 10, 9, 10), fill=iron_l)
    return img


def generate_floor_dirt() -> Image.Image:
    """Variante de suelo con parche de tierra/arena."""
    img = generate_floor()
    d = ImageDraw.Draw(img)
    dirt = (120, 95, 65, 255)
    dirt_d = (85, 65, 40, 255)
    dirt_l = (155, 125, 85, 255)
    # Parche irregular
    d.point((3, 4), fill=dirt)
    d.point((4, 4), fill=dirt_l)
    d.point((5, 5), fill=dirt)
    d.point((4, 5), fill=dirt)
    d.point((3, 5), fill=dirt_d)
    d.point((5, 6), fill=dirt_l)
    d.point((10, 9), fill=dirt)
    d.point((11, 10), fill=dirt_l)
    d.point((10, 10), fill=dirt)
    d.point((12, 9), fill=dirt_d)
    return img


def generate_wall_top() -> Image.Image:
    img = _new((16, 6))
    d = ImageDraw.Draw(img)
    top_light = (135, 128, 142)
    top_mid = (105, 98, 112)
    top_dark = (75, 70, 85)
    d.rectangle((0, 0, 15, 1), fill=top_light + (255,))
    d.rectangle((0, 2, 15, 3), fill=top_mid + (255,))
    d.rectangle((0, 4, 15, 5), fill=top_dark + (255,))
    d.point((7, 1), fill=top_dark + (255,))
    d.point((7, 3), fill=top_dark + (255,))
    return img


def generate_table() -> Image.Image:
    """Mesa grande con tapa elíptica + 2 patas frontales visibles (144×80)."""
    img = _new((144, 80))
    d = ImageDraw.Draw(img)
    wood = (140, 85, 45)
    wood_l = (190, 135, 75)
    wood_ll = (220, 170, 100)
    wood_d = (90, 50, 22)
    wood_dd = (55, 28, 12)
    leg = (95, 55, 25)
    leg_l = (135, 85, 40)
    leg_d = (60, 30, 12)

    # Sombra del conjunto sobre el suelo (PRIMERO para que patas/tapa la cubran)
    d.ellipse((4, 68, 140, 79), fill=(0, 0, 0, 110))

    # --- 2 PATAS FRONTALES ---
    # Pata izquierda
    d.rectangle((30, 48, 38, 78), fill=OUTLINE)
    d.rectangle((31, 49, 37, 77), fill=leg + (255,))
    d.line((31, 49, 31, 77), fill=leg_l + (255,))
    d.line((37, 49, 37, 77), fill=leg_d + (255,))
    # Detalle tallado en la pata (anillos)
    d.line((31, 56, 37, 56), fill=leg_d + (255,))
    d.line((31, 57, 37, 57), fill=leg + (255,))
    d.line((31, 68, 37, 68), fill=leg_d + (255,))
    d.line((31, 69, 37, 69), fill=leg + (255,))
    # Pie de la pata izq (más ancho)
    d.rectangle((28, 75, 40, 79), fill=OUTLINE)
    d.rectangle((29, 76, 39, 78), fill=leg + (255,))
    d.line((29, 76, 39, 76), fill=leg_l + (255,))

    # Pata derecha (espejo)
    d.rectangle((106, 48, 114, 78), fill=OUTLINE)
    d.rectangle((107, 49, 113, 77), fill=leg + (255,))
    d.line((107, 49, 107, 77), fill=leg_l + (255,))
    d.line((113, 49, 113, 77), fill=leg_d + (255,))
    d.line((107, 56, 113, 56), fill=leg_d + (255,))
    d.line((107, 57, 113, 57), fill=leg + (255,))
    d.line((107, 68, 113, 68), fill=leg_d + (255,))
    d.line((107, 69, 113, 69), fill=leg + (255,))
    d.rectangle((104, 75, 116, 79), fill=OUTLINE)
    d.rectangle((105, 76, 115, 78), fill=leg + (255,))
    d.line((105, 76, 115, 76), fill=leg_l + (255,))

    # --- TAPA ELÍPTICA GRANDE ---
    # Sombra exterior
    d.ellipse((1, 10, 142, 60), fill=wood_dd + (255,))
    # Borde grueso
    d.ellipse((2, 8, 141, 58), fill=wood_dd + (255,))
    # Borde intermedio
    d.ellipse((4, 9, 139, 57), fill=wood_d + (255,))
    # Tapa principal
    d.ellipse((5, 10, 138, 56), fill=wood + (255,))
    # Banda decorativa inferior
    d.arc((5, 10, 138, 56), 200, 340, fill=wood_d + (255,))

    # Highlights amplios arriba
    d.ellipse((14, 12, 129, 28), fill=wood_l + (255,))
    # Highlight más fuerte (reflejo de luz)
    d.ellipse((22, 13, 110, 21), fill=wood_ll + (255,))

    # Veteado del grano
    d.line((16, 26, 127, 26), fill=wood_d + (255,))
    d.line((14, 34, 129, 34), fill=wood_d + (255,))
    d.line((18, 42, 125, 42), fill=wood_dd + (255,))
    d.line((16, 48, 127, 48), fill=wood_dd + (255,))

    # Nudos del grano
    d.ellipse((38, 30, 42, 34), fill=wood_dd + (255,))
    d.ellipse((90, 38, 95, 43), fill=wood_dd + (255,))
    d.ellipse((68, 46, 71, 49), fill=wood_dd + (255,))
    d.ellipse((25, 38, 28, 41), fill=wood_dd + (255,))
    d.ellipse((115, 32, 118, 35), fill=wood_dd + (255,))
    return img


def generate_chair() -> Image.Image:
    """Silla frontal (back rest visible above sage's head)."""
    img = _new((16, 24))
    d = ImageDraw.Draw(img)
    wood = (110, 65, 30)
    wood_l = (155, 100, 55)
    wood_d = (70, 38, 15)
    d.rectangle((3, 0, 12, 14), fill=OUTLINE)
    d.rectangle((4, 1, 11, 13), fill=wood + (255,))
    d.line((4, 4, 11, 4), fill=wood_d + (255,))
    d.line((4, 10, 11, 10), fill=wood_d + (255,))
    d.point((7, 7), fill=wood_l + (255,))
    d.point((8, 7), fill=wood_l + (255,))
    d.point((7, 8), fill=wood_d + (255,))
    d.point((8, 8), fill=wood_d + (255,))
    d.rectangle((1, 14, 14, 18), fill=OUTLINE)
    d.rectangle((2, 15, 13, 17), fill=wood + (255,))
    d.line((2, 15, 13, 15), fill=wood_l + (255,))
    d.rectangle((2, 18, 4, 23), fill=wood_d + (255,))
    d.rectangle((11, 18, 13, 23), fill=wood_d + (255,))
    return img


def generate_chair_back() -> Image.Image:
    """Silla vista DESDE ATRÁS (para sabios sur con la espalda al usuario).
    Se ve el reverso del respaldo + asiento parcial."""
    img = _new((16, 24))
    d = ImageDraw.Draw(img)
    wood = (110, 65, 30)
    wood_l = (155, 100, 55)
    wood_d = (70, 38, 15)
    # Respaldo desde atrás (sin tallado central, más liso)
    d.rectangle((3, 0, 12, 14), fill=OUTLINE)
    d.rectangle((4, 1, 11, 13), fill=wood + (255,))
    d.line((4, 1, 11, 1), fill=wood_l + (255,))
    # Veta vertical en el dorso
    d.line((7, 2, 7, 12), fill=wood_d + (255,))
    d.line((8, 2, 8, 12), fill=wood_d + (255,))
    # Asiento (asoma por debajo del respaldo)
    d.rectangle((1, 14, 14, 18), fill=OUTLINE)
    d.rectangle((2, 15, 13, 17), fill=wood + (255,))
    d.line((2, 17, 13, 17), fill=wood_d + (255,))
    # Patas
    d.rectangle((2, 18, 4, 23), fill=wood_d + (255,))
    d.rectangle((11, 18, 13, 23), fill=wood_d + (255,))
    return img


def generate_chair_side() -> Image.Image:
    """Silla de perfil (lado izquierdo del respaldo visible).
    Para flip horizontal usar img.transpose(Image.FLIP_LEFT_RIGHT)."""
    img = _new((16, 24))
    d = ImageDraw.Draw(img)
    wood = (110, 65, 30)
    wood_l = (155, 100, 55)
    wood_d = (70, 38, 15)
    # Respaldo en el lado izquierdo (vertical)
    d.rectangle((2, 0, 5, 15), fill=OUTLINE)
    d.rectangle((3, 1, 4, 14), fill=wood + (255,))
    d.line((3, 1, 4, 1), fill=wood_l + (255,))
    # Detalles del respaldo
    d.point((3, 4), fill=wood_d + (255,))
    d.point((4, 4), fill=wood_d + (255,))
    d.point((3, 10), fill=wood_d + (255,))
    d.point((4, 10), fill=wood_d + (255,))
    # Asiento horizontal (de respaldo a frente)
    d.rectangle((2, 14, 13, 17), fill=OUTLINE)
    d.rectangle((3, 15, 12, 16), fill=wood + (255,))
    d.line((3, 15, 12, 15), fill=wood_l + (255,))
    # Pata trasera (debajo del respaldo)
    d.rectangle((3, 17, 5, 23), fill=wood_d + (255,))
    # Pata frontal (debajo del frente del asiento)
    d.rectangle((10, 17, 12, 23), fill=wood_d + (255,))
    return img


def generate_torch() -> Image.Image:
    img = _new((8, 16))
    d = ImageDraw.Draw(img)
    d.rectangle((3, 6, 4, 15), fill=(70, 40, 18, 255))
    d.point((3, 6), fill=(120, 75, 35, 255))
    d.rectangle((2, 4, 5, 6), fill=(100, 60, 25, 255))
    d.line((2, 4, 5, 4), fill=(150, 95, 45, 255))
    d.polygon([(1, 4), (3, 0), (6, 4), (5, 5), (2, 5)], fill=(220, 80, 20, 255))
    d.polygon([(2, 3), (3, 1), (5, 3), (4, 4), (3, 4)], fill=(255, 150, 30, 255))
    d.point((3, 2), fill=(255, 230, 100, 255))
    d.point((4, 2), fill=(255, 230, 100, 255))
    return img


def generate_fireplace() -> Image.Image:
    """Chimenea grande con mantelpiece tallado, 3 leños, llama 4-capas,
    rejilla de hierro abajo, humo arriba (64×72)."""
    img = _new((64, 72))
    d = ImageDraw.Draw(img)
    stone = (72, 68, 76)
    stone_l = (105, 100, 112)
    stone_ll = (145, 138, 152)
    stone_d = (44, 42, 50)
    stone_dd = (24, 22, 30)
    iron = (50, 48, 58)
    iron_l = (110, 108, 122)
    gold = (220, 175, 60)

    # Outline general
    d.rectangle((1, 0, 62, 71), fill=OUTLINE)

    # --- CUERPO DE PIEDRA ---
    d.rectangle((2, 1, 61, 70), fill=stone + (255,))

    # --- MANTELPIECE (repisa superior tallada) ---
    # Base de la repisa (sobresale)
    d.rectangle((0, 12, 63, 18), fill=OUTLINE)
    d.rectangle((1, 13, 62, 17), fill=stone + (255,))
    d.line((1, 13, 62, 13), fill=stone_ll + (255,))
    d.line((1, 14, 62, 14), fill=stone_l + (255,))
    d.line((1, 17, 62, 17), fill=stone_dd + (255,))
    # Tallado decorativo en la repisa (rombos)
    for cx in (12, 22, 32, 42, 52):
        d.point((cx, 15), fill=gold + (255,))
        d.point((cx - 1, 16), fill=stone_d + (255,))
        d.point((cx + 1, 16), fill=stone_d + (255,))

    # --- BLOQUES DE PIEDRA EN LA PARTE ALTA (arriba del mantel) ---
    # Bloques irregulares con vetas
    for y in (4, 8):
        d.line((2, y, 61, y), fill=stone_d + (255,))
    for x in (10, 22, 32, 42, 54):
        d.line((x, 0, x, 11), fill=stone_d + (255,))
    # Highlights selectos
    d.point((6, 3), fill=stone_ll + (255,))
    d.point((28, 6), fill=stone_l + (255,))
    d.point((48, 9), fill=stone_l + (255,))
    # Símbolo central (sol grabado)
    d.ellipse((28, 4, 35, 11), fill=stone_d + (255,))
    d.ellipse((29, 5, 34, 10), fill=gold + (255,))
    for (dx, dy) in [(-2, 0), (3, 0), (0, -2), (0, 3), (-1, -1), (2, -1), (-1, 2), (2, 2)]:
        d.point((31 + dx, 7 + dy), fill=stone_d + (255,))

    # --- BLOQUES INTERMEDIOS (entre mantel y hueco) ---
    for y in (22, 28):
        d.line((2, y, 61, y), fill=stone_d + (255,))
    for x in (10, 20, 44, 54):
        d.line((x, 18, x, 21), fill=stone_d + (255,))
        d.line((x, 23, x, 27), fill=stone_d + (255,))
    # Highlights
    d.point((6, 20), fill=stone_l + (255,))
    d.point((50, 25), fill=stone_l + (255,))

    # --- HUECO DEL FUEGO (arqueado) ---
    # Arco superior
    d.pieslice((10, 26, 53, 44), 180, 360, fill=OUTLINE)
    d.pieslice((11, 27, 52, 43), 180, 360, fill=(15, 12, 18, 255))
    # Cuerpo del hueco
    d.rectangle((10, 35, 53, 64), fill=OUTLINE)
    d.rectangle((11, 36, 52, 63), fill=(15, 12, 18, 255))

    # --- LEÑOS (3 apilados) ---
    log = (110, 70, 30)
    log_l = (155, 105, 50)
    log_d = (70, 40, 12)
    log_dd = (45, 22, 6)
    # Tronco grande inferior
    d.rectangle((14, 56, 49, 62), fill=OUTLINE)
    d.rectangle((15, 57, 48, 61), fill=log + (255,))
    d.line((15, 57, 48, 57), fill=log_l + (255,))
    d.line((15, 61, 48, 61), fill=log_d + (255,))
    # Anillos del tronco grande
    d.ellipse((17, 58, 19, 60), fill=log_d + (255,))
    d.ellipse((40, 58, 42, 60), fill=log_d + (255,))
    d.point((18, 59), fill=log_l + (255,))
    d.point((41, 59), fill=log_l + (255,))
    # Tronco medio (encima, ligeramente atrás)
    d.rectangle((18, 51, 45, 56), fill=OUTLINE)
    d.rectangle((19, 52, 44, 55), fill=log + (255,))
    d.line((19, 52, 44, 52), fill=log_l + (255,))
    # Tronco pequeño superior
    d.rectangle((26, 48, 38, 51), fill=OUTLINE)
    d.rectangle((27, 49, 37, 50), fill=log + (255,))

    # --- BRASAS bajo los leños ---
    for x in range(15, 49):
        h = (x * 7) % 5
        if h == 0:
            d.point((x, 62), fill=(255, 110, 20, 255))
        elif h == 1:
            d.point((x, 62), fill=(220, 60, 10, 255))
        elif h == 2:
            d.point((x, 63), fill=(180, 40, 5, 255))

    # --- LLAMA 4 CAPAS ---
    # Capa 0: rojo profundo (más amplia)
    d.polygon([
        (14, 56), (17, 48), (20, 52), (23, 42), (27, 48),
        (31, 38), (35, 46), (39, 40), (43, 50), (46, 46), (49, 56),
    ], fill=(190, 40, 10, 255))
    # Capa 1: rojo-naranja
    d.polygon([
        (17, 52), (19, 46), (22, 50), (25, 40), (29, 46),
        (32, 36), (35, 44), (39, 38), (43, 48), (45, 52),
    ], fill=(230, 80, 20, 255))
    # Capa 2: naranja vivo
    d.polygon([
        (20, 48), (22, 42), (25, 46), (28, 38), (31, 42),
        (34, 36), (37, 42), (40, 38), (42, 46),
    ], fill=(255, 140, 30, 255))
    # Capa 3: amarillo (cerca de blanco)
    d.polygon([
        (23, 44), (25, 38), (28, 42), (31, 36), (34, 40), (37, 38),
    ], fill=(255, 220, 90, 255))
    # Núcleos blancos
    d.point((26, 40), fill=(255, 250, 200, 255))
    d.point((31, 38), fill=(255, 250, 200, 255))

    # --- CHISPAS volando arriba ---
    d.point((22, 32), fill=(255, 180, 40, 255))
    d.point((28, 28), fill=(255, 200, 60, 255))
    d.point((34, 30), fill=(255, 180, 40, 255))
    d.point((40, 26), fill=(255, 200, 60, 255))

    # --- HUMO subiendo (gris muy claro, semi-transparente) ---
    smoke = (180, 180, 190)
    for (sx, sy, a) in [(28, 22, 100), (32, 19, 80), (30, 16, 60), (33, 13, 40)]:
        d.ellipse((sx - 2, sy - 1, sx + 2, sy + 1), fill=smoke + (a,))

    # --- REJILLA DE HIERRO (barras verticales delante del fuego, abajo) ---
    d.rectangle((10, 63, 53, 65), fill=OUTLINE)
    for bx in (14, 20, 26, 32, 38, 44, 50):
        d.line((bx, 56, bx, 64), fill=iron + (255,))
        d.point((bx, 56), fill=iron_l + (255,))

    # --- BASE INFERIOR (cenizas + repisa) ---
    d.rectangle((0, 65, 63, 71), fill=OUTLINE)
    d.rectangle((1, 66, 62, 70), fill=stone_d + (255,))
    d.line((1, 66, 62, 66), fill=stone_l + (255,))
    # Cenizas que sobresalen
    d.point((20, 67), fill=(160, 150, 140, 255))
    d.point((38, 67), fill=(160, 150, 140, 255))
    return img


def generate_door() -> Image.Image:
    img = _new((28, 44))
    d = ImageDraw.Draw(img)
    wood = (110, 65, 30)
    wood_d = (70, 38, 15)
    d.rectangle((0, 8, 27, 43), fill=(18, 14, 12, 255))
    d.pieslice((0, 0, 27, 16), 180, 360, fill=(18, 14, 12, 255))
    d.rectangle((2, 10, 25, 42), fill=wood + (255,))
    d.pieslice((2, 2, 25, 18), 180, 360, fill=wood + (255,))
    d.line((9, 10, 9, 42), fill=wood_d + (255,))
    d.line((18, 10, 18, 42), fill=wood_d + (255,))
    d.line((10, 11, 10, 42), fill=(155, 95, 50, 255))
    d.line((19, 11, 19, 42), fill=(155, 95, 50, 255))
    d.line((2, 10, 2, 42), fill=OUTLINE)
    d.line((25, 10, 25, 42), fill=OUTLINE)
    d.arc((2, 2, 25, 18), 180, 360, fill=OUTLINE)
    iron = (60, 60, 70, 255)
    iron_l = (110, 110, 125, 255)
    d.rectangle((2, 17, 25, 19), fill=iron)
    d.rectangle((2, 32, 25, 34), fill=iron)
    d.line((2, 17, 25, 17), fill=iron_l)
    d.line((2, 32, 25, 32), fill=iron_l)
    for y in (18, 33):
        for x in (5, 13, 22):
            d.point((x, y), fill=(180, 170, 150, 255))
    d.ellipse((11, 24, 16, 29), fill=OUTLINE)
    d.ellipse((12, 25, 15, 28), fill=iron_l)
    d.point((13, 26), fill=(220, 210, 190, 255))
    return img


def generate_rug() -> Image.Image:
    img = _new((136, 74))
    d = ImageDraw.Draw(img)
    rug_base = (140, 30, 35)
    rug_l = (185, 55, 60)
    rug_d = (90, 18, 20)
    rug_dd = (55, 10, 12)
    border = (220, 180, 80)
    border_d = (160, 130, 50)
    border_dd = (110, 90, 35)
    d.ellipse((0, 4, 135, 73), fill=(0, 0, 0, 110))
    d.ellipse((1, 1, 134, 72), fill=border_dd + (255,))
    d.ellipse((3, 3, 132, 70), fill=border_d + (255,))
    d.ellipse((5, 5, 130, 68), fill=border + (255,))
    d.ellipse((8, 8, 127, 65), fill=rug_d + (255,))
    d.ellipse((10, 10, 125, 63), fill=rug_base + (255,))
    d.ellipse((20, 12, 116, 28), fill=rug_l + (255,))
    cx, cy = 68, 37
    d.polygon([(cx, cy - 8), (cx + 10, cy), (cx, cy + 8), (cx - 10, cy)],
              fill=border + (255,), outline=border_dd + (255,))
    d.polygon([(cx, cy - 5), (cx + 6, cy), (cx, cy + 5), (cx - 6, cy)],
              fill=rug_dd + (255,))
    for x in (28, 108):
        d.point((x, 37), fill=border + (255,))
        d.point((x - 1, 37), fill=border + (255,))
        d.point((x + 1, 37), fill=border + (255,))
        d.point((x, 36), fill=border + (255,))
        d.point((x, 38), fill=border + (255,))
    d.line((38, 37, 50, 37), fill=border_d + (255,))
    d.line((86, 37, 98, 37), fill=border_d + (255,))
    for sx in (12, 28, 44, 60, 76, 92, 108, 122):
        d.point((sx, 6), fill=border + (255,))
        d.point((sx, 67), fill=border + (255,))
    return img


def generate_candle() -> Image.Image:
    img = _new((6, 10))
    d = ImageDraw.Draw(img)
    wax = (235, 220, 180)
    wax_d = (180, 165, 130)
    d.rectangle((1, 4, 4, 9), fill=OUTLINE)
    d.rectangle((2, 4, 3, 8), fill=wax + (255,))
    d.line((2, 4, 3, 4), fill=(255, 245, 215, 255))
    d.point((3, 8), fill=wax_d + (255,))
    d.point((1, 9), fill=wax_d + (255,))
    d.point((4, 9), fill=wax_d + (255,))
    d.point((2, 3), fill=(40, 30, 25, 255))
    d.point((3, 3), fill=(40, 30, 25, 255))
    d.polygon([(2, 0), (3, 0), (4, 2), (3, 3), (2, 3), (1, 2)], fill=(255, 150, 30, 255))
    d.point((2, 1), fill=(255, 220, 80, 255))
    d.point((3, 1), fill=(255, 220, 80, 255))
    return img


def generate_scroll() -> Image.Image:
    img = _new((8, 4))
    d = ImageDraw.Draw(img)
    paper = (235, 215, 165)
    paper_d = (180, 160, 110)
    seal = (180, 30, 30)
    d.rectangle((0, 1, 7, 2), fill=OUTLINE)
    d.line((0, 1, 7, 1), fill=paper + (255,))
    d.line((0, 2, 7, 2), fill=paper_d + (255,))
    d.point((0, 0), fill=paper + (255,))
    d.point((7, 0), fill=paper + (255,))
    d.point((0, 3), fill=paper_d + (255,))
    d.point((7, 3), fill=paper_d + (255,))
    d.point((3, 2), fill=seal + (255,))
    return img


def generate_banner() -> Image.Image:
    img = _new((8, 16))
    d = ImageDraw.Draw(img)
    cloth = (60, 40, 100)
    cloth_l = (100, 75, 150)
    cloth_d = (40, 28, 70)
    gold = (225, 180, 60)
    d.line((0, 0, 7, 0), fill=(60, 60, 70, 255))
    d.line((0, 1, 7, 1), fill=(110, 110, 125, 255))
    d.rectangle((1, 2, 6, 13), fill=OUTLINE)
    d.rectangle((2, 2, 5, 13), fill=cloth + (255,))
    d.line((2, 2, 5, 2), fill=cloth_l + (255,))
    d.line((5, 2, 5, 13), fill=cloth_d + (255,))
    d.point((3, 6), fill=gold + (255,))
    d.point((4, 6), fill=gold + (255,))
    d.point((3, 7), fill=gold + (255,))
    d.point((4, 7), fill=gold + (255,))
    d.point((2, 14), fill=cloth_d + (255,))
    d.point((3, 15), fill=cloth + (255,))
    d.point((4, 15), fill=cloth + (255,))
    d.point((5, 14), fill=cloth_d + (255,))
    return img


def generate_barrel() -> Image.Image:
    img = _new((12, 14))
    d = ImageDraw.Draw(img)
    wood = (130, 80, 35)
    wood_l = (175, 115, 55)
    wood_d = (85, 50, 22)
    iron = (60, 60, 70)
    iron_l = (110, 110, 125)
    d.rectangle((1, 1, 10, 12), fill=OUTLINE)
    d.point((0, 3), fill=OUTLINE)
    d.point((0, 9), fill=OUTLINE)
    d.point((11, 3), fill=OUTLINE)
    d.point((11, 9), fill=OUTLINE)
    d.rectangle((2, 2, 9, 11), fill=wood + (255,))
    d.line((1, 4, 1, 8), fill=wood + (255,))
    d.line((10, 4, 10, 8), fill=wood + (255,))
    d.line((4, 2, 4, 11), fill=wood_d + (255,))
    d.line((7, 2, 7, 11), fill=wood_d + (255,))
    d.line((2, 2, 2, 11), fill=wood_l + (255,))
    d.line((1, 4, 10, 4), fill=iron + (255,))
    d.line((1, 9, 10, 9), fill=iron + (255,))
    d.line((1, 5, 10, 5), fill=iron_l + (255,))
    d.ellipse((2, 0, 9, 2), fill=wood_d + (255,))
    d.line((3, 1, 8, 1), fill=wood + (255,))
    return img


def generate_crate() -> Image.Image:
    img = _new((14, 12))
    d = ImageDraw.Draw(img)
    wood = (135, 90, 45)
    wood_l = (175, 125, 70)
    wood_d = (85, 55, 25)
    d.rectangle((0, 0, 13, 11), fill=OUTLINE)
    d.rectangle((1, 1, 12, 10), fill=wood + (255,))
    d.line((1, 4, 12, 4), fill=wood_d + (255,))
    d.line((1, 7, 12, 7), fill=wood_d + (255,))
    d.line((2, 2, 11, 9), fill=wood_d + (255,))
    d.line((11, 2, 2, 9), fill=wood_d + (255,))
    d.line((1, 1, 12, 1), fill=wood_l + (255,))
    d.line((1, 1, 1, 9), fill=wood_l + (255,))
    d.point((2, 2), fill=(180, 170, 150, 255))
    d.point((11, 2), fill=(180, 170, 150, 255))
    d.point((2, 9), fill=(180, 170, 150, 255))
    d.point((11, 9), fill=(180, 170, 150, 255))
    return img


def generate_anvil() -> Image.Image:
    img = _new((16, 14))
    d = ImageDraw.Draw(img)
    iron = (55, 55, 65)
    iron_l = (110, 110, 125)
    wood = (95, 60, 28)
    wood_l = (135, 90, 45)
    wood_d = (60, 35, 15)
    d.rectangle((3, 9, 12, 13), fill=OUTLINE)
    d.rectangle((4, 10, 11, 13), fill=wood + (255,))
    d.line((4, 10, 11, 10), fill=wood_l + (255,))
    d.line((4, 13, 11, 13), fill=wood_d + (255,))
    d.point((6, 11), fill=wood_d + (255,))
    d.point((9, 12), fill=wood_d + (255,))
    d.rectangle((5, 7, 10, 9), fill=OUTLINE)
    d.line((5, 8, 10, 8), fill=iron + (255,))
    d.rectangle((4, 4, 11, 7), fill=OUTLINE)
    d.rectangle((5, 5, 10, 6), fill=iron + (255,))
    d.rectangle((1, 4, 4, 6), fill=OUTLINE)
    d.line((2, 5, 3, 5), fill=iron + (255,))
    d.rectangle((4, 2, 12, 4), fill=OUTLINE)
    d.rectangle((5, 3, 11, 3), fill=iron + (255,))
    d.line((5, 2, 11, 2), fill=iron_l + (255,))
    return img


def generate_stones() -> Image.Image:
    img = _new((14, 8))
    d = ImageDraw.Draw(img)
    stone = (95, 92, 100)
    stone_l = (135, 130, 145)
    stone_d = (55, 52, 60)
    d.ellipse((4, 3, 9, 7), fill=OUTLINE)
    d.ellipse((5, 4, 8, 6), fill=stone + (255,))
    d.point((6, 4), fill=stone_l + (255,))
    d.ellipse((0, 4, 4, 7), fill=OUTLINE)
    d.point((2, 5), fill=stone + (255,))
    d.point((1, 6), fill=stone + (255,))
    d.point((3, 6), fill=stone + (255,))
    d.ellipse((9, 4, 13, 7), fill=OUTLINE)
    d.point((10, 5), fill=stone + (255,))
    d.point((11, 6), fill=stone + (255,))
    d.point((12, 6), fill=stone_l + (255,))
    d.ellipse((6, 0, 9, 3), fill=OUTLINE)
    d.point((7, 1), fill=stone + (255,))
    d.point((8, 1), fill=stone_l + (255,))
    d.point((7, 2), fill=stone_d + (255,))
    return img


def generate_chest() -> Image.Image:
    img = _new((16, 12))
    d = ImageDraw.Draw(img)
    wood = (110, 70, 30)
    wood_l = (155, 105, 55)
    wood_d = (70, 40, 15)
    gold = (225, 180, 60)
    gold_l = (255, 225, 110)
    d.rectangle((1, 1, 14, 11), fill=OUTLINE)
    d.rectangle((2, 5, 13, 10), fill=wood + (255,))
    d.line((2, 5, 13, 5), fill=wood_l + (255,))
    d.line((2, 10, 13, 10), fill=wood_d + (255,))
    d.rectangle((2, 2, 13, 4), fill=wood + (255,))
    d.line((2, 2, 13, 2), fill=wood_l + (255,))
    d.line((4, 2, 4, 10), fill=gold + (255,))
    d.line((11, 2, 11, 10), fill=gold + (255,))
    d.rectangle((7, 5, 9, 8), fill=gold + (255,))
    d.point((8, 6), fill=OUTLINE)
    d.point((8, 7), fill=gold_l + (255,))
    return img


def generate_bookshelf_large() -> Image.Image:
    """Librería grande de pared con 4 estantes llenos de libros (24×40)."""
    img = _new((24, 40))
    d = ImageDraw.Draw(img)
    wood = (90, 55, 25)
    wood_l = (135, 90, 45)
    wood_d = (55, 32, 12)
    wood_dd = (35, 20, 8)
    # Marco exterior
    d.rectangle((0, 0, 23, 39), fill=OUTLINE)
    d.rectangle((1, 1, 22, 38), fill=wood + (255,))
    # Cornisa superior
    d.rectangle((1, 1, 22, 2), fill=wood_l + (255,))
    d.line((0, 0, 23, 0), fill=OUTLINE)
    # Base inferior
    d.rectangle((1, 36, 22, 38), fill=wood_d + (255,))
    # Laterales con sombreado
    d.line((1, 3, 1, 36), fill=wood_l + (255,))
    d.line((22, 3, 22, 36), fill=wood_d + (255,))
    # 3 separadores horizontales = 4 estantes
    for sy in (11, 19, 27):
        d.line((2, sy, 21, sy), fill=wood_dd + (255,))
        d.line((2, sy + 1, 21, sy + 1), fill=wood_d + (255,))
    # Tablones del fondo (vetas sutiles)
    d.line((11, 3, 11, 10), fill=wood_d + (255,))
    d.line((11, 12, 11, 18), fill=wood_d + (255,))
    # Libros: 4 niveles × 5 libros
    book_palette = [
        (160, 30, 30), (40, 80, 160), (50, 120, 50), (180, 130, 40),
        (140, 80, 30), (110, 50, 130), (220, 180, 50), (60, 60, 70),
        (30, 50, 110), (200, 100, 30), (80, 130, 70), (140, 60, 60),
        (180, 70, 80), (50, 100, 130), (120, 60, 30), (90, 30, 100),
        (180, 130, 100), (60, 100, 80), (140, 50, 50), (100, 80, 130),
    ]
    levels = [(3, 7), (12, 6), (20, 6), (28, 8)]
    idx = 0
    for level_top, h in levels:
        for i in range(5):
            x0 = 2 + i * 4
            x1 = x0 + 2
            color = book_palette[idx % len(book_palette)]
            idx += 1
            y0 = level_top + (idx % 2)
            y1 = level_top + h - 1
            d.rectangle((x0, y0, x1, y1), fill=color + (255,))
            d.line((x0, y0, x1, y0), fill=lighter(color, 1.3) + (255,))
            d.line((x1, y0, x1, y1), fill=darker(color, 0.55) + (255,))
            # Detalle dorado del lomo (1 px aleatorio)
            if idx % 3 == 0:
                d.point((x0 + 1, y0 + 2), fill=(255, 220, 90, 200))
    return img


# --- Dígitos pixel-art 3×5 (renderizar números dentro del palantir) ---
_DIGITS_3x5: dict[str, list[str]] = {
    "0": ["###", "# #", "# #", "# #", "###"],
    "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["###", "  #", "###", "#  ", "###"],
    "3": ["###", "  #", "###", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"],
    "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"],
    "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"],
    "9": ["###", "# #", "###", "  #", "###"],
}


def _draw_digit(d: ImageDraw.ImageDraw, x: int, y: int, ch: str,
                color: tuple[int, int, int, int]) -> None:
    pat = _DIGITS_3x5.get(ch)
    if pat is None:
        return
    for dy, row in enumerate(pat):
        for dx, c in enumerate(row):
            if c == "#":
                d.point((x + dx, y + dy), fill=color)


def _draw_number(d: ImageDraw.ImageDraw, x: int, y: int, n: int,
                 color: tuple[int, int, int, int]) -> None:
    """Dibuja un número 1-30. 1 dígito en 3×5, 2 dígitos en 7×5 (con gap)."""
    s = str(n)
    cur_x = x
    for ch in s:
        _draw_digit(d, cur_x, y, ch, color)
        cur_x += 4  # 3 wide + 1 px gap


def _palantir_colors_for_round(round_n: int) -> dict[str, tuple]:
    """Paleta del palantir según la ronda (1-30+). Sube intensidad con rondas."""
    if round_n <= 5:
        # Morado tranquilo
        return dict(crystal=(120, 80, 200), light=(180, 130, 230),
                    bright=(220, 180, 255), dark=(60, 30, 120))
    elif round_n <= 15:
        # Morado intenso
        return dict(crystal=(150, 60, 220), light=(210, 130, 240),
                    bright=(240, 200, 255), dark=(80, 25, 140))
    elif round_n <= 25:
        # Rojo-magenta
        return dict(crystal=(200, 50, 130), light=(240, 110, 170),
                    bright=(255, 180, 210), dark=(120, 20, 60))
    else:
        # Rojo crítico
        return dict(crystal=(230, 40, 50), light=(255, 100, 80),
                    bright=(255, 200, 160), dark=(140, 10, 10))


def generate_palantir(round_n: int = 0) -> Image.Image:
    """Esfera de cristal (palantir) sobre soporte (20×28). Si round_n > 0,
    pinta el número dentro del orbe. Color escala con la ronda."""
    img = _new((20, 28))
    d = ImageDraw.Draw(img)
    stand = (65, 38, 18)
    stand_l = (110, 75, 35)
    stand_d = (35, 18, 8)
    gold = (220, 175, 60)
    gold_l = (255, 220, 110)

    pal = _palantir_colors_for_round(round_n)

    # --- BASE / PEDESTAL ---
    d.rectangle((2, 24, 17, 27), fill=OUTLINE)
    d.rectangle((3, 25, 16, 26), fill=stand + (255,))
    d.line((3, 25, 16, 25), fill=stand_l + (255,))
    d.line((3, 26, 16, 26), fill=stand_d + (255,))
    # Pie central
    d.rectangle((8, 20, 11, 24), fill=OUTLINE)
    d.rectangle((9, 21, 10, 23), fill=stand_l + (255,))

    # --- GARRAS sosteniendo la esfera ---
    # 4 garras (esquinas del soporte)
    for (gx, gy) in [(2, 19), (17, 19), (4, 17), (15, 17)]:
        d.point((gx, gy), fill=OUTLINE)
        d.point((gx, gy - 1), fill=stand + (255,))

    # --- ANILLO DORADO bajo la esfera ---
    d.line((3, 19, 16, 19), fill=gold + (255,))
    d.line((4, 18, 15, 18), fill=gold_l + (255,))
    # Engastes pequeños
    d.point((6, 18), fill=stand_d + (255,))
    d.point((13, 18), fill=stand_d + (255,))

    # --- ESFERA DE CRISTAL (16×16) ---
    d.ellipse((1, 1, 18, 18), fill=OUTLINE)
    d.ellipse((2, 2, 17, 17), fill=pal["dark"] + (255,))
    d.ellipse((3, 3, 16, 16), fill=pal["crystal"] + (255,))
    d.ellipse((4, 4, 15, 15), fill=pal["crystal"] + (255,))

    # Reflejo superior izquierdo (highlight grande)
    d.ellipse((4, 4, 9, 8), fill=pal["light"] + (255,))
    d.ellipse((5, 5, 7, 7), fill=pal["bright"] + (255,))

    # --- NÚMERO DE RONDA dentro del orbe ---
    if round_n > 0:
        # Posición centrada en el orbe (centro aprox (9, 9))
        s = str(round_n)
        total_w = len(s) * 3 + (len(s) - 1)  # 3*N + gaps
        cx = 9 - total_w // 2
        cy = 8
        _draw_number(d, cx, cy, round_n, (255, 250, 230, 255))

    # Estrellas/destellos sutiles dentro del orbe (no tapan número)
    if round_n == 0:
        d.point((12, 11), fill=(255, 255, 255, 230))
        d.point((6, 13), fill=pal["bright"] + (255,))

    return img


def generate_book_closed() -> Image.Image:
    """Libro cerrado flotando — frame 0 del ciclo (20×14)."""
    img = _new((20, 14))
    d = ImageDraw.Draw(img)
    leather = (140, 50, 50)
    leather_d = (85, 28, 28)
    leather_l = (190, 80, 80)
    gold = (230, 190, 70)
    page = (240, 225, 180)
    # Outline + cuerpo
    d.rectangle((1, 2, 18, 12), fill=OUTLINE)
    d.rectangle((2, 3, 17, 11), fill=leather + (255,))
    # Highlight superior
    d.line((2, 3, 17, 3), fill=leather_l + (255,))
    # Sombra inferior
    d.line((2, 11, 17, 11), fill=leather_d + (255,))
    # Lomo central
    d.rectangle((9, 3, 10, 11), fill=leather_d + (255,))
    # Páginas (líneas blancas en el canto)
    d.line((2, 4, 17, 4), fill=page + (255,))
    d.line((2, 10, 17, 10), fill=page + (255,))
    # Detalle dorado central
    d.point((6, 7), fill=gold + (255,))
    d.point((7, 7), fill=gold + (255,))
    d.point((12, 7), fill=gold + (255,))
    d.point((13, 7), fill=gold + (255,))
    return img


def generate_book_half_open() -> Image.Image:
    """Libro entreabierto — frame 1 (20×14)."""
    img = _new((20, 14))
    d = ImageDraw.Draw(img)
    leather = (140, 50, 50)
    leather_d = (85, 28, 28)
    page = (240, 225, 180)
    page_d = (190, 170, 130)
    ink = (60, 35, 20)
    # Tapas (V abierto suave)
    d.polygon([(2, 4), (9, 3), (10, 12), (1, 12)], fill=OUTLINE)
    d.polygon([(11, 3), (18, 4), (19, 12), (10, 12)], fill=OUTLINE)
    d.polygon([(3, 5), (9, 4), (9, 11), (2, 11)], fill=leather + (255,))
    d.polygon([(11, 4), (17, 5), (18, 11), (11, 11)], fill=leather + (255,))
    # Páginas interiores
    d.polygon([(4, 5), (9, 5), (9, 10), (4, 10)], fill=page + (255,))
    d.polygon([(11, 5), (16, 5), (16, 10), (11, 10)], fill=page + (255,))
    # Líneas de texto/runas
    d.line((5, 7, 8, 7), fill=ink + (255,))
    d.line((12, 7, 15, 7), fill=ink + (255,))
    d.line((5, 9, 7, 9), fill=ink + (255,))
    d.line((12, 9, 14, 9), fill=ink + (255,))
    # Sombras inferiores
    d.line((4, 10, 9, 10), fill=page_d + (255,))
    d.line((11, 10, 16, 10), fill=page_d + (255,))
    return img


def generate_book_open() -> Image.Image:
    """Libro totalmente abierto — frame 2 (20×14)."""
    img = _new((20, 14))
    d = ImageDraw.Draw(img)
    leather = (140, 50, 50)
    leather_d = (85, 28, 28)
    page = (240, 225, 180)
    page_d = (190, 170, 130)
    ink = (60, 35, 20)
    gold = (230, 190, 70)
    # Tapa abierta totalmente (plana)
    d.rectangle((0, 4, 19, 13), fill=OUTLINE)
    d.rectangle((1, 5, 18, 12), fill=leather + (255,))
    # Páginas
    d.rectangle((2, 6, 9, 11), fill=page + (255,))
    d.rectangle((10, 6, 17, 11), fill=page + (255,))
    # Lomo en el centro
    d.line((9, 5, 9, 12), fill=leather_d + (255,))
    d.line((10, 5, 10, 12), fill=leather_d + (255,))
    # Texto en las páginas
    d.line((3, 7, 8, 7), fill=ink + (255,))
    d.line((11, 7, 16, 7), fill=ink + (255,))
    d.line((3, 8, 7, 8), fill=ink + (255,))
    d.line((11, 8, 15, 8), fill=ink + (255,))
    d.line((3, 9, 8, 9), fill=ink + (255,))
    d.line((11, 9, 16, 9), fill=ink + (255,))
    d.line((3, 10, 6, 10), fill=ink + (255,))
    d.line((11, 10, 14, 10), fill=ink + (255,))
    # Letra dorada inicial
    d.point((3, 7), fill=gold + (255,))
    d.point((11, 7), fill=gold + (255,))
    # Página suelta arriba (vuela)
    d.line((6, 0, 13, 0), fill=page_d + (255,))
    d.line((5, 1, 14, 1), fill=page + (255,))
    d.line((4, 2, 15, 2), fill=page + (255,))
    d.line((4, 3, 15, 3), fill=page_d + (255,))
    return img


def generate_fire_frame_a() -> Image.Image:
    """Variante de chimenea con llama 'larga' (animación frame A) — 64×72."""
    return _fireplace_with_flame_pattern("a")


def generate_fire_frame_b() -> Image.Image:
    """Variante 'media' (frame B)."""
    return _fireplace_with_flame_pattern("b")


def generate_fire_frame_c() -> Image.Image:
    """Variante 'corta + chispas' (frame C)."""
    return _fireplace_with_flame_pattern("c")


def _fireplace_with_flame_pattern(pattern: str) -> Image.Image:
    """Mismo cuerpo de chimenea base pero distinta forma de llama
    (para cycling de animación). Mantiene el mantelpiece + bloques."""
    img = generate_fireplace()
    d = ImageDraw.Draw(img)
    # Limpiar zona de llama (sobreescribir con negro del hueco)
    d.rectangle((11, 25, 52, 55), fill=(15, 12, 18, 255))
    # Re-pintar leños (estaban en y=56..62)
    log = (110, 70, 30)
    log_l = (155, 105, 50)
    log_d = (70, 40, 12)
    d.rectangle((14, 56, 49, 62), fill=OUTLINE)
    d.rectangle((15, 57, 48, 61), fill=log + (255,))
    d.line((15, 57, 48, 57), fill=log_l + (255,))
    d.line((15, 61, 48, 61), fill=log_d + (255,))
    d.ellipse((17, 58, 19, 60), fill=log_d + (255,))
    d.ellipse((40, 58, 42, 60), fill=log_d + (255,))
    # Brasas (siempre)
    for x in range(15, 49):
        h = (x * 7) % 5
        if h == 0:
            d.point((x, 62), fill=(255, 110, 20, 255))
        elif h == 1:
            d.point((x, 62), fill=(220, 60, 10, 255))
    # Llamas según pattern
    if pattern == "a":
        # Larga
        d.polygon([(14, 56), (17, 46), (20, 52), (23, 38), (27, 48),
                   (31, 34), (35, 46), (39, 38), (43, 50), (46, 46), (49, 56)],
                  fill=(190, 40, 10, 255))
        d.polygon([(17, 52), (19, 44), (22, 50), (25, 36), (29, 44),
                   (32, 32), (35, 42), (39, 36), (43, 48), (45, 52)],
                  fill=(230, 80, 20, 255))
        d.polygon([(20, 48), (22, 40), (25, 44), (28, 34), (31, 40),
                   (34, 32), (37, 40), (40, 36), (42, 46)],
                  fill=(255, 140, 30, 255))
        d.polygon([(23, 42), (25, 36), (28, 40), (31, 32), (34, 38), (37, 36)],
                  fill=(255, 220, 90, 255))
        d.point((26, 38), fill=(255, 250, 200, 255))
        d.point((31, 34), fill=(255, 250, 200, 255))
    elif pattern == "b":
        # Media
        d.polygon([(13, 56), (16, 30), (19, 33), (22, 25), (25, 32),
                   (28, 28), (32, 33), (34, 56)],
                  fill=(220, 60, 20, 255))
        d.polygon([(15, 54), (17, 28), (20, 31), (23, 24), (26, 30), (29, 27), (31, 52)],
                  fill=(255, 130, 30, 255))
        d.polygon([(18, 50), (20, 27), (22, 30), (24, 26), (26, 29), (28, 46)],
                  fill=(255, 220, 80, 255))
        d.point((22, 26), fill=(255, 250, 200, 255))
        d.point((28, 24), fill=(255, 200, 60, 255))
    else:  # "c"
        # Corta + más chispas
        d.polygon([(15, 56), (18, 44), (22, 48), (26, 42), (30, 46),
                   (34, 42), (38, 48), (42, 44), (46, 56)],
                  fill=(220, 60, 20, 255))
        d.polygon([(18, 54), (21, 46), (25, 44), (28, 46), (32, 42), (36, 44), (40, 50)],
                  fill=(255, 130, 30, 255))
        d.polygon([(22, 48), (25, 42), (28, 44), (31, 40), (34, 44)],
                  fill=(255, 220, 80, 255))
        # Más chispas
        d.point((20, 35), fill=(255, 200, 60, 255))
        d.point((28, 30), fill=(255, 180, 50, 255))
        d.point((34, 32), fill=(255, 200, 60, 255))
        d.point((40, 36), fill=(255, 180, 50, 255))
        d.point((24, 28), fill=(255, 220, 80, 255))
    return img


def generate_glowing_plant() -> Image.Image:
    """Planta mágica en maceta con flores brillantes (12×18)."""
    img = _new((12, 18))
    d = ImageDraw.Draw(img)
    clay = (140, 80, 50)
    clay_l = (180, 110, 70)
    clay_d = (90, 50, 25)
    stem = (60, 130, 50)
    stem_l = (90, 170, 70)
    leaf = (80, 160, 60)
    leaf_l = (130, 220, 90)
    leaf_d = (40, 90, 30)
    glow_y = (255, 230, 100)
    glow_c = (130, 220, 255)
    glow_cl = (200, 245, 255)
    # Maceta (forma trapezoidal)
    d.polygon([(1, 11), (10, 11), (9, 17), (2, 17)], fill=OUTLINE)
    d.polygon([(2, 12), (9, 12), (8, 16), (3, 16)], fill=clay + (255,))
    d.line((2, 12, 9, 12), fill=clay_l + (255,))
    d.line((3, 16, 8, 16), fill=clay_d + (255,))
    # Reborde de la maceta
    d.rectangle((0, 10, 11, 11), fill=OUTLINE)
    d.line((1, 10, 10, 10), fill=clay + (255,))
    # Tierra
    d.line((1, 11, 10, 11), fill=(50, 35, 25, 255))
    # Tallo principal central
    d.line((5, 4, 5, 10), fill=stem + (255,))
    d.line((6, 4, 6, 10), fill=stem_l + (255,))
    # Hojas inferiores
    d.point((3, 6), fill=leaf + (255,))
    d.point((2, 7), fill=leaf_l + (255,))
    d.point((3, 7), fill=leaf + (255,))
    d.point((4, 7), fill=leaf_d + (255,))
    d.point((8, 7), fill=leaf + (255,))
    d.point((9, 8), fill=leaf_l + (255,))
    d.point((8, 8), fill=leaf + (255,))
    d.point((7, 8), fill=leaf_d + (255,))
    # Flor central grande (5×3)
    d.rectangle((4, 1, 7, 3), fill=OUTLINE)
    d.point((4, 1), fill=glow_y + (255,))
    d.point((5, 1), fill=glow_y + (255,))
    d.point((6, 1), fill=glow_y + (255,))
    d.point((7, 1), fill=glow_y + (255,))
    d.point((5, 2), fill=glow_cl + (255,))
    d.point((6, 2), fill=glow_cl + (255,))
    # Pequeñas flores adicionales
    d.point((2, 3), fill=glow_c + (255,))
    d.point((9, 3), fill=glow_c + (255,))
    d.point((3, 4), fill=glow_y + (255,))
    d.point((8, 4), fill=glow_y + (255,))
    return img


def generate_sign_seal() -> Image.Image:
    """Sello dorado de firma del consejo (12×12). Aparece encima de cada
    sabio que ha firmado la premisa."""
    img = _new((12, 12))
    d = ImageDraw.Draw(img)
    gold = (230, 190, 70)
    gold_l = (255, 230, 110)
    gold_d = (160, 125, 35)
    wax = (180, 30, 30)
    # Lacre rojo de fondo (sombra)
    d.ellipse((1, 2, 11, 11), fill=wax + (255,))
    # Cuerpo dorado del sello
    d.ellipse((0, 0, 10, 10), fill=OUTLINE)
    d.ellipse((1, 1, 9, 9), fill=gold + (255,))
    # Highlight superior izquierdo
    d.ellipse((2, 2, 5, 5), fill=gold_l + (255,))
    # Símbolo grabado (estrella de 4 puntas — sello del consejo)
    d.line((5, 2, 5, 8), fill=gold_d + (255,))
    d.line((2, 5, 8, 5), fill=gold_d + (255,))
    d.point((4, 4), fill=gold_d + (255,))
    d.point((6, 4), fill=gold_d + (255,))
    d.point((4, 6), fill=gold_d + (255,))
    d.point((6, 6), fill=gold_d + (255,))
    # Destellos
    d.point((11, 1), fill=(255, 255, 230, 255))
    d.point((1, 11), fill=(255, 255, 230, 255))
    return img


def generate_magic_rune() -> Image.Image:
    """Runa mágica brillante para grabar en el suelo (14×14)."""
    img = _new((14, 14))
    d = ImageDraw.Draw(img)
    rune = (130, 220, 255)
    rune_l = (200, 245, 255)
    rune_d = (60, 140, 200)
    # Anillo exterior
    d.ellipse((0, 0, 13, 13), outline=rune_d + (255,))
    d.ellipse((1, 1, 12, 12), outline=rune + (220,))
    # Anillo interior
    d.ellipse((3, 3, 10, 10), outline=rune_l + (200,))
    # Cruz mágica central
    d.line((6, 4, 6, 9), fill=rune_l + (220,))
    d.line((7, 4, 7, 9), fill=rune_l + (220,))
    d.line((4, 6, 9, 6), fill=rune_l + (220,))
    d.line((4, 7, 9, 7), fill=rune_l + (220,))
    # Punto central brillante
    d.point((6, 6), fill=(255, 255, 255, 255))
    d.point((7, 6), fill=(255, 255, 255, 255))
    d.point((6, 7), fill=(255, 255, 255, 255))
    d.point((7, 7), fill=(255, 255, 255, 255))
    # Estrellas en los 4 puntos cardinales
    d.point((6, 0), fill=rune_l + (255,))
    d.point((7, 0), fill=rune_l + (255,))
    d.point((6, 13), fill=rune_l + (255,))
    d.point((7, 13), fill=rune_l + (255,))
    d.point((0, 6), fill=rune_l + (255,))
    d.point((0, 7), fill=rune_l + (255,))
    d.point((13, 6), fill=rune_l + (255,))
    d.point((13, 7), fill=rune_l + (255,))
    return img


def generate_bookshelf() -> Image.Image:
    img = _new((16, 24))
    d = ImageDraw.Draw(img)
    wood = (95, 60, 30)
    wood_l = (135, 90, 45)
    wood_d = (60, 35, 15)
    d.rectangle((0, 0, 15, 23), fill=OUTLINE)
    d.rectangle((1, 1, 14, 22), fill=wood + (255,))
    d.line((1, 1, 14, 1), fill=wood_l + (255,))
    d.line((1, 22, 14, 22), fill=wood_d + (255,))
    for shelf_y in (8, 15):
        d.line((1, shelf_y, 14, shelf_y), fill=wood_d + (255,))
        d.line((1, shelf_y + 1, 14, shelf_y + 1), fill=wood + (255,))
    books = [
        [(2, 2, 4, 7, (160, 30, 30)), (5, 3, 7, 7, (40, 80, 160)),
         (8, 2, 10, 7, (50, 120, 50)), (11, 3, 13, 7, (180, 130, 40))],
        [(2, 9, 4, 14, (140, 80, 30)), (5, 10, 8, 14, (110, 50, 130)),
         (9, 9, 11, 14, (220, 180, 50)), (12, 10, 14, 14, (60, 60, 70))],
        [(2, 16, 5, 21, (30, 50, 110)), (6, 17, 8, 21, (200, 100, 30)),
         (9, 16, 11, 21, (80, 130, 70)), (12, 17, 14, 21, (140, 60, 60))],
    ]
    for shelf in books:
        for x0, y0, x1, y1, color in shelf:
            d.rectangle((x0, y0, x1, y1), fill=color + (255,))
            d.line((x0, y0, x1, y0), fill=lighter(color, 1.3) + (255,))
            d.line((x1, y0, x1, y1), fill=darker(color, 0.6) + (255,))
    return img


def generate_weapon_rack() -> Image.Image:
    img = _new((14, 22))
    d = ImageDraw.Draw(img)
    wood = (100, 65, 30)
    wood_l = (140, 95, 50)
    wood_d = (65, 38, 16)
    iron = (170, 175, 185)
    iron_l = (220, 225, 235)
    iron_d = (95, 100, 115)
    d.rectangle((6, 1, 7, 20), fill=OUTLINE)
    d.line((6, 1, 6, 20), fill=wood + (255,))
    d.line((7, 1, 7, 20), fill=wood_d + (255,))
    d.rectangle((1, 2, 12, 3), fill=OUTLINE)
    d.line((1, 2, 12, 2), fill=wood_l + (255,))
    d.line((1, 3, 12, 3), fill=wood + (255,))
    d.rectangle((2, 3, 4, 4), fill=iron + (255,))
    d.point((2, 3), fill=iron_l + (255,))
    d.rectangle((1, 5, 5, 6), fill=(180, 140, 40, 255))
    d.line((3, 7, 3, 18), fill=iron + (255,))
    d.point((2, 9), fill=iron_l + (255,))
    d.point((3, 18), fill=iron_d + (255,))
    d.point((3, 19), fill=OUTLINE)
    d.line((10, 4, 10, 19), fill=wood + (255,))
    d.line((11, 4, 11, 19), fill=wood_d + (255,))
    d.polygon([(8, 6), (12, 5), (13, 9), (12, 11), (8, 10)], fill=OUTLINE)
    d.polygon([(9, 7), (11, 7), (12, 9), (11, 10), (9, 9)], fill=iron + (255,))
    d.point((10, 7), fill=iron_l + (255,))
    return img


def generate_brazier() -> Image.Image:
    img = _new((14, 18))
    d = ImageDraw.Draw(img)
    iron = (60, 60, 70)
    iron_l = (110, 110, 125)
    iron_d = (30, 30, 40)
    d.line((2, 17, 6, 14), fill=iron + (255,))
    d.line((11, 17, 7, 14), fill=iron + (255,))
    d.line((6, 17, 7, 14), fill=iron + (255,))
    d.point((2, 17), fill=OUTLINE)
    d.point((11, 17), fill=OUTLINE)
    d.point((6, 17), fill=OUTLINE)
    d.rectangle((6, 9, 7, 14), fill=iron + (255,))
    d.ellipse((1, 8, 12, 13), fill=OUTLINE)
    d.ellipse((2, 9, 11, 12), fill=iron + (255,))
    d.line((2, 9, 11, 9), fill=iron_l + (255,))
    d.line((2, 12, 11, 12), fill=iron_d + (255,))
    d.point((4, 10), fill=(220, 60, 10, 255))
    d.point((9, 10), fill=(220, 60, 10, 255))
    d.point((6, 11), fill=(255, 100, 30, 255))
    d.polygon([(2, 8), (4, 3), (6, 6), (7, 2), (9, 5), (11, 8)],
              fill=(220, 80, 20, 255))
    d.polygon([(3, 7), (5, 4), (6, 6), (8, 3), (10, 7)],
              fill=(255, 140, 30, 255))
    d.point((5, 5), fill=(255, 220, 80, 255))
    d.point((7, 4), fill=(255, 220, 80, 255))
    return img


def generate_skull_pile() -> Image.Image:
    img = _new((12, 8))
    d = ImageDraw.Draw(img)
    bone = (230, 220, 195)
    bone_d = (160, 150, 130)
    d.ellipse((2, 1, 8, 6), fill=OUTLINE)
    d.ellipse((3, 2, 7, 5), fill=bone + (255,))
    d.point((3, 5), fill=bone_d + (255,))
    d.point((4, 3), fill=OUTLINE)
    d.point((6, 3), fill=OUTLINE)
    d.point((5, 5), fill=bone_d + (255,))
    d.line((8, 6, 11, 7), fill=bone_d + (255,))
    d.point((9, 5), fill=bone + (255,))
    d.point((11, 6), fill=bone + (255,))
    return img


# ---------- bubble ----------

def generate_bubble(width: int, height: int, color: RGB = (255, 220, 60)) -> Image.Image:
    """Burbuja estilo cómic: amarilla con outline negro grueso + cola.
    color default = amarillo cómic. width/height son del cuerpo (sin la cola)."""
    img = _new((width, height + 6))
    d = ImageDraw.Draw(img)
    fill = _rgba(color)
    outline = (15, 12, 18, 255)
    highlight = (255, 250, 200, 220)
    # Cuerpo con esquinas redondeadas + outline grueso
    d.rounded_rectangle((0, 0, width - 1, height - 1), radius=3, fill=outline)
    d.rounded_rectangle((1, 1, width - 2, height - 2), radius=2, fill=outline)
    d.rounded_rectangle((2, 2, width - 3, height - 3), radius=2, fill=fill)
    # Brillo interior (línea pequeña arriba a la izquierda)
    d.line((4, 3, width // 3, 3), fill=highlight)
    d.point((4, 4), fill=highlight)
    # Cola triangular tipo cómic apuntando hacia abajo
    cx = width // 2
    d.polygon([(cx - 3, height - 3), (cx + 3, height - 3), (cx, height + 5)],
              fill=outline)
    d.polygon([(cx - 2, height - 2), (cx + 2, height - 2), (cx, height + 3)],
              fill=fill)
    return img


# ---------- entry point ----------

def regenerate_all(out_dir: Path) -> dict[str, Path]:
    sprites_dir = out_dir / "sprites"
    tiles_dir = out_dir / "tiles"
    sprites_dir.mkdir(parents=True, exist_ok=True)
    tiles_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    for sage in SAGES:
        # Frontal (used by animator and N sages)
        img = generate_sage_sprite(sage)
        p = sprites_dir / f"sage_{sage.id}.png"
        img.save(p)
        paths[f"sage_{sage.id}"] = p
        # Vista de espalda (para sabios sur)
        img_back = generate_sage_sprite_back(sage)
        pb = sprites_dir / f"sage_{sage.id}_back.png"
        img_back.save(pb)
        paths[f"sage_{sage.id}_back"] = pb
        # Perfil izquierdo y derecho (para sabios W y E)
        img_pl = generate_sage_sprite_profile(sage, "left")
        ppl = sprites_dir / f"sage_{sage.id}_profile_l.png"
        img_pl.save(ppl)
        paths[f"sage_{sage.id}_profile_l"] = ppl
        img_pr = generate_sage_sprite_profile(sage, "right")
        ppr = sprites_dir / f"sage_{sage.id}_profile_r.png"
        img_pr.save(ppr)
        paths[f"sage_{sage.id}_profile_r"] = ppr

    tiles: dict[str, Callable[[], Image.Image]] = {
        "floor": generate_floor,
        "floor_cracked": generate_floor_cracked,
        "floor_mossy": generate_floor_mossy,
        "floor_wood": generate_floor_wood,
        "wall": generate_wall,
        "wall_cracked": generate_wall_cracked,
        "wall_mossy": generate_wall_mossy,
        "wall_decorative": generate_wall_decorative,
        "floor_dirt": generate_floor_dirt,
        "wall_top": generate_wall_top,
        "table": generate_table,
        "chair": generate_chair,
        "chair_back": generate_chair_back,
        "chair_side": generate_chair_side,
        "torch": generate_torch,
        "fireplace": generate_fireplace,
        "door": generate_door,
        "rug": generate_rug,
        "candle": generate_candle,
        "scroll": generate_scroll,
        "banner": generate_banner,
        "barrel": generate_barrel,
        "crate": generate_crate,
        "anvil": generate_anvil,
        "stones": generate_stones,
        "chest": generate_chest,
        "bookshelf": generate_bookshelf,
        "bookshelf_large": generate_bookshelf_large,
        "palantir": generate_palantir,
        "book_closed": generate_book_closed,
        "book_half_open": generate_book_half_open,
        "book_open": generate_book_open,
        "fire_frame_a": generate_fire_frame_a,
        "fire_frame_b": generate_fire_frame_b,
        "fire_frame_c": generate_fire_frame_c,
        "glowing_plant": generate_glowing_plant,
        "magic_rune": generate_magic_rune,
        "sign_seal": generate_sign_seal,
        "weapon_rack": generate_weapon_rack,
        "brazier": generate_brazier,
        "skull_pile": generate_skull_pile,
    }
    for name, gen in tiles.items():
        p = tiles_dir / f"{name}.png"
        gen().save(p)
        paths[name] = p
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenera assets placeholder v4 (48×48 sprites).")
    parser.add_argument("--out", type=Path, default=Path("assets"))
    args = parser.parse_args()
    paths = regenerate_all(args.out)
    print(f"Generados {len(paths)} assets v4 en {args.out.resolve()}")


if __name__ == "__main__":
    main()
