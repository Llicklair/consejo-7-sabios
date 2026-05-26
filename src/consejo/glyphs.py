"""Generador de glifos rúnicos para el idioma inventado del Consejo.

El debate real ocurre en lengua humana vía API. En pantalla, las burbujas
de los sabios muestran glifos rúnicos pixel-art generados de forma
determinista a partir del texto real (misma frase -> misma secuencia
rúnica). Ilegible a propósito: la atmósfera es la mazmorra, la verdad
queda en `consejo-report.md`.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from PIL import Image, ImageDraw

ALPHABET_SIZE = 24
GLYPH_SIZE = 8
GLYPH_SPACING = 2


def _stable_hash(s: str) -> int:
    return int.from_bytes(
        hashlib.blake2b(s.encode("utf-8"), digest_size=4).digest(), "big"
    )


def text_to_glyphs(text: str, length: int | None = None) -> list[int]:
    """Convierte texto humano en índices de glifo (0..ALPHABET_SIZE-1).

    Determinista: misma entrada -> misma salida. Trocea el texto en
    pseudo-sílabas de 2-3 caracteres y mapea cada una al alfabeto.
    """
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    i = 0
    while i < len(text):
        size = 2 + ((_stable_hash(text[: i + 1]) >> 4) & 1)
        chunks.append(text[i : i + size])
        i += size

    glyphs = [_stable_hash(c) % ALPHABET_SIZE for c in chunks]

    if length is not None and glyphs:
        if len(glyphs) >= length:
            glyphs = glyphs[:length]
        else:
            original = list(glyphs)
            while len(glyphs) < length:
                glyphs.append(original[len(glyphs) % len(original)])
    return glyphs


@dataclass(frozen=True)
class _Stroke:
    kind: str
    a: tuple[int, int]
    b: tuple[int, int] | None = None


def _strokes_for_index(idx: int) -> list[_Stroke]:
    rng = random.Random(idx * 7919 + 31)

    # Eje primario: vertical, horizontal o diagonal cruzando el centro.
    spines = [
        _Stroke("line", (3, 1), (3, 6)),
        _Stroke("line", (4, 1), (4, 6)),
        _Stroke("line", (1, 3), (6, 3)),
        _Stroke("line", (1, 4), (6, 4)),
        _Stroke("line", (1, 1), (6, 6)),
        _Stroke("line", (6, 1), (1, 6)),
    ]
    strokes: list[_Stroke] = [rng.choice(spines)]

    # 1-3 ramas decorativas
    pts = [(x, y) for x in range(1, 7) for y in range(1, 7)]
    for _ in range(rng.choice([1, 2, 2, 3])):
        a = rng.choice(pts)
        b = rng.choice(pts)
        if a == b:
            strokes.append(_Stroke("dot", a))
        else:
            strokes.append(_Stroke("line", a, b))
    return strokes


def generate_glyph_bitmaps(
    color: tuple[int, int, int] = (220, 220, 200),
) -> list[Image.Image]:
    """Devuelve los ALPHABET_SIZE glifos como imágenes RGBA 8x8.

    El color por defecto es pergamino claro; pasa otro para colorear
    por sabio (ej. el Mago/Simplificador en violeta).
    """
    rgba = color + (255,)
    images: list[Image.Image] = []
    for idx in range(ALPHABET_SIZE):
        img = Image.new("RGBA", (GLYPH_SIZE, GLYPH_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        for s in _strokes_for_index(idx):
            if s.kind == "dot":
                draw.point(s.a, fill=rgba)
            elif s.kind == "line" and s.b is not None:
                draw.line([s.a, s.b], fill=rgba, width=1)
        images.append(img)
    return images


def render_glyphs_to_strip(
    glyph_indices: list[int],
    color: tuple[int, int, int] = (220, 220, 200),
    glyphs: list[Image.Image] | None = None,
) -> Image.Image:
    """Compone una secuencia de glifos en una sola imagen horizontal."""
    if glyphs is None:
        glyphs = generate_glyph_bitmaps(color)
    if not glyph_indices:
        return Image.new("RGBA", (GLYPH_SIZE, GLYPH_SIZE), (0, 0, 0, 0))

    n = len(glyph_indices)
    w = n * GLYPH_SIZE + (n - 1) * GLYPH_SPACING
    strip = Image.new("RGBA", (w, GLYPH_SIZE), (0, 0, 0, 0))
    for i, idx in enumerate(glyph_indices):
        x = i * (GLYPH_SIZE + GLYPH_SPACING)
        g = glyphs[idx % ALPHABET_SIZE]
        strip.paste(g, (x, 0), g)
    return strip
