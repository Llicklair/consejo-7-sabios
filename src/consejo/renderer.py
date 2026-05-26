"""Renderer básico: PIL Image -> terminal pixel-art con rich-pixels.

Usa el carácter ▀ (half-block superior) con truecolor para meter 2 píxeles
verticales en cada celda de la terminal. Requiere terminal con truecolor
+ Unicode (Windows Terminal, WezTerm, iTerm2 OK; cmd.exe clásico NO).

Smoke test:
    python -m consejo.renderer arquitecto       # un solo sabio
    python -m consejo.renderer all              # los 7, etiquetados
    python -m consejo.renderer tile fireplace   # un tile de mazmorra
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image
from rich.console import Console
from rich_pixels import Pixels

from .sages import SAGES, by_id

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"


def load_sage_sprite(sage_id: str, assets_dir: Path = ASSETS_DIR,
                     view: str = "front") -> Image.Image:
    """Carga el sprite de un sabio en la orientación pedida.

    view: 'front' | 'back' | 'profile_l' | 'profile_r'
    """
    suffix = "" if view == "front" else f"_{view}"
    p = assets_dir / "sprites" / f"sage_{sage_id}{suffix}.png"
    return Image.open(p).convert("RGBA")


def load_tile(name: str, assets_dir: Path = ASSETS_DIR) -> Image.Image:
    p = assets_dir / "tiles" / f"{name}.png"
    return Image.open(p).convert("RGBA")


def upscale(img: Image.Image, factor: int) -> Image.Image:
    if factor <= 1:
        return img
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


def render_image(img: Image.Image, scale: int = 2, console: Console | None = None) -> None:
    """Imprime `img` a la terminal con rich-pixels."""
    console = console or Console()
    console.print(Pixels.from_image(upscale(img, scale)))


def render_all_sages(scale: int = 2) -> None:
    console = Console()
    for sage in SAGES:
        console.rule(f"[bold cyan]{sage.archetype}[/]  ·  [yellow]{sage.role}[/]")
        render_image(load_sage_sprite(sage.id), scale=scale, console=console)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "all":
        render_all_sages()
        return

    if args[0] == "tile" and len(args) >= 2:
        render_image(load_tile(args[1]))
        return

    # sage por id
    sage = by_id(args[0])
    console = Console()
    console.print(f"[bold]{sage.archetype}[/]  ·  [dim]{sage.role}[/]")
    render_image(load_sage_sprite(sage.id), console=console)


if __name__ == "__main__":
    main()
