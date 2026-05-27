"""Renderer básico: PIL Image -> terminal pixel-art con rich-pixels.

Usa el carácter ▀ (half-block superior) con truecolor para meter 2 píxeles
verticales en cada celda de la terminal. Requiere terminal con truecolor
+ Unicode (Windows Terminal, WezTerm, iTerm2 OK; cmd.exe clásico NO).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from .sages import ALL_SAGES

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"

# Decompression-bomb defense — sprites/tiles in this project are <300px,
# so anything ≥1 megapixel is a malformed or hostile asset.
Image.MAX_IMAGE_PIXELS = 1_000_000

_VALID_SAGE_IDS = {s.id for s in ALL_SAGES}
_VALID_VIEWS = {"front", "back", "profile_l", "profile_r"}


class AssetError(Exception):
    """Asset failed to load (missing, invalid, or outside assets/)."""


def _resolve_under(base: Path, name: str) -> Path:
    """Resolve `name` under `base` and assert containment to block traversal."""
    path = (base / name).resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError as e:
        raise AssetError(f"path escapes assets dir: {name}") from e
    return path


def load_sage_sprite(sage_id: str, assets_dir: Path = ASSETS_DIR,
                     view: str = "front") -> Image.Image:
    """Carga el sprite de un sabio en la orientación pedida.

    view: 'front' | 'back' | 'profile_l' | 'profile_r'
    """
    if sage_id not in _VALID_SAGE_IDS:
        raise AssetError(f"unknown sage_id: {sage_id!r}")
    if view not in _VALID_VIEWS:
        raise AssetError(f"unknown view: {view!r}")
    suffix = "" if view == "front" else f"_{view}"
    p = _resolve_under(assets_dir / "sprites", f"sage_{sage_id}{suffix}.png")
    try:
        return Image.open(p).convert("RGBA")
    except FileNotFoundError as e:
        raise AssetError(f"sprite missing: {p.name}") from e


def load_tile(name: str, assets_dir: Path = ASSETS_DIR) -> Image.Image:
    p = _resolve_under(assets_dir / "tiles", f"{name}.png")
    try:
        return Image.open(p).convert("RGBA")
    except FileNotFoundError as e:
        raise AssetError(f"tile missing: {p.name}") from e


def upscale(img: Image.Image, factor: int) -> Image.Image:
    if factor <= 1:
        return img
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)
