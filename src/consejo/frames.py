"""Pure per-state frame rendering — `render_frame(state, t, total, ...) -> PIL.Image`.

This module is the public **frames API** of the animator. The asyncio
Live loop, sound side-effects, and Rich console handling live in
`consejo.animator`; the actual pixel composition is what's exposed here.

Phase D architecture: this split lets the frame builder be unit-tested
without spinning up a terminal or asyncio loop — call `render_frame()`
with any `(state, t, total, ...)` tuple and get back a PIL image.
"""

from __future__ import annotations

from .animator import (
    render_frame,
    _walk_view as walk_view,
    _walk_bob as walk_bob,
    _lerp_xy as lerp_xy,
    _ease_out as ease_out,
)

__all__ = ["render_frame", "walk_view", "walk_bob", "lerp_xy", "ease_out"]
