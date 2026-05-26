"""Sonido procedural para el Consejo — WAVs generados en Python puro.

Sin dependencias externas: usa `random`, `math`, `struct` y `wave` del
stdlib. Reproducción vía `winsound` (Windows). En otras plataformas el
SoundPlayer queda como no-op silencioso.

WAVs generados:
- fire_crackle.wav      — loop ambiente (brown noise + chispazos)
- palantir_hum.wav      — loop low ethereal (sine + harmonic + beating)
- page_turn.wav         — one-shot papel rasgándose
- magic_sparkle.wav     — one-shot campanada mágica
- seal_thump.wav        — one-shot golpe sordo (firma del consejo)
- footstep.wav          — one-shot pisada

Uso:
    python -m consejo.sound                # regenera WAVs en assets/sounds/
"""

from __future__ import annotations

import argparse
import math
import random
import struct
import threading
import wave
from array import array
from pathlib import Path
from typing import Callable

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
SOUNDS_DIR = ASSETS_DIR / "sounds"
SAMPLE_RATE = 22050


# ---------- helpers ----------

def _save_wav(samples: list[float], path: Path, sample_rate: int = SAMPLE_RATE) -> None:
    """Guarda lista de floats en [-1, 1] como WAV mono 16-bit."""
    # Clampea y normaliza si es necesario
    peak = max((abs(s) for s in samples), default=1.0)
    norm = 0.9 / max(peak, 1e-6)
    int_samples = array("h", (max(-32768, min(32767, int(s * norm * 32000))) for s in samples))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(int_samples.tobytes())


def _envelope_attack_decay(n: int, attack: float, decay: float) -> list[float]:
    """Devuelve una envolvente de longitud n: attack lineal + decay exponencial."""
    attack_n = max(1, int(attack * n))
    out = [0.0] * n
    for i in range(attack_n):
        out[i] = i / attack_n
    for i in range(attack_n, n):
        # Decay exponencial controlado por `decay` (factor de caída)
        out[i] = math.exp(-(i - attack_n) / max(1, n - attack_n) * decay)
    return out


# ---------- generadores ----------

def gen_fire_crackle(duration: float = 6.0) -> list[float]:
    """Brown noise + chispazos aleatorios (low-pass natural)."""
    n = int(duration * SAMPLE_RATE)
    rng = random.Random(42)  # determinista
    out = [0.0] * n
    # Brown noise (cumulative sum de gaussianas)
    prev = 0.0
    for i in range(n):
        prev += rng.gauss(0, 0.04)
        # Damping para que no diverja
        prev *= 0.999
        out[i] = prev
    # Suavizar con running mean (kernel de 8)
    smoothed = [0.0] * n
    k = 8
    rolling = 0.0
    for i in range(n):
        rolling += out[i]
        if i >= k:
            rolling -= out[i - k]
            smoothed[i] = rolling / k
        else:
            smoothed[i] = rolling / (i + 1)
    # Chispazos: ~5 por segundo
    n_cracks = int(duration * 5)
    for _ in range(n_cracks):
        pos = rng.randint(0, max(1, n - 300))
        amp = rng.uniform(0.4, 0.9)
        decay_len = 200
        for i in range(decay_len):
            if pos + i >= n:
                break
            smoothed[pos + i] += rng.gauss(0, 1) * amp * math.exp(-i / 25)
    # Normalizar
    peak = max((abs(s) for s in smoothed), default=1.0)
    return [s * 0.6 / max(peak, 1e-6) for s in smoothed]


def gen_palantir_hum(duration: float = 6.0) -> list[float]:
    """Hum etéreo: 2 sines cercanos (beating) + armónico + modulación lenta."""
    n = int(duration * SAMPLE_RATE)
    f1, f2 = 80.0, 81.7
    f_harm = 160.0
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Modulación lenta de amplitud (respira)
        mod = 0.5 + 0.5 * math.sin(2 * math.pi * 0.3 * t)
        # Mezcla de senos
        s = (math.sin(2 * math.pi * f1 * t) +
             math.sin(2 * math.pi * f2 * t) * 0.7 +
             math.sin(2 * math.pi * f_harm * t) * 0.3)
        out.append(s * mod * 0.3)
    return out


def gen_page_turn() -> list[float]:
    """Crujido breve de papel (~0.5s): noise blanco con envolvente rápida."""
    duration = 0.5
    n = int(duration * SAMPLE_RATE)
    rng = random.Random(7)
    raw = [rng.gauss(0, 1) for _ in range(n)]
    # High-pass simple (diferencia)
    out = [raw[i] - raw[i - 1] if i > 0 else 0 for i in range(n)]
    # Envolvente ADSR rápido
    env = _envelope_attack_decay(n, 0.02, 4.0)
    # Modulación con un seno bajo para simular el "swoosh" del papel
    for i in range(n):
        t = i / SAMPLE_RATE
        out[i] *= env[i] * (0.7 + 0.3 * math.sin(2 * math.pi * 6 * t))
    return [s * 0.5 for s in out]


def gen_magic_sparkle() -> list[float]:
    """Campanada mágica ascendente: 3 frecuencias armónicas con bell envelope."""
    duration = 0.9
    n = int(duration * SAMPLE_RATE)
    freqs = [880.0, 1318.5, 1760.0]  # A5, E6, A6
    out = [0.0] * n
    for freq in freqs:
        for i in range(n):
            t = i / SAMPLE_RATE
            env = math.exp(-t * 3.5)
            out[i] += math.sin(2 * math.pi * freq * t) * env / len(freqs)
    return [s * 0.55 for s in out]


def gen_seal_thump() -> list[float]:
    """Golpe sordo grave (sello): seno bajo + decay rápido."""
    duration = 0.45
    n = int(duration * SAMPLE_RATE)
    freq = 65.0
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-t * 8)
        # Frecuencia con leve sweep hacia abajo
        f = freq * (1.0 - t * 0.3)
        out.append(math.sin(2 * math.pi * f * t) * env)
    return [s * 0.75 for s in out]


def gen_footstep() -> list[float]:
    """Pisada blanda: seno bajo + ruido breve."""
    duration = 0.18
    n = int(duration * SAMPLE_RATE)
    rng = random.Random(3)
    freq = 100.0
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        env = math.exp(-t * 15)
        s = math.sin(2 * math.pi * freq * t) * 0.4 + rng.gauss(0, 1) * 0.15
        out.append(s * env)
    return [s * 0.55 for s in out]


def gen_chair_creak() -> list[float]:
    """Crujido de silla al sentarse: tono medio modulado + decay."""
    duration = 0.55
    n = int(duration * SAMPLE_RATE)
    rng = random.Random(11)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Frecuencia que baja (crujido de madera)
        f = 220 - 120 * t / duration
        # Modulación lenta para textura
        mod = 1.0 + 0.3 * math.sin(2 * math.pi * 8 * t)
        env = math.exp(-t * 4)
        noise = rng.gauss(0, 1) * 0.1
        out.append((math.sin(2 * math.pi * f * t) * mod + noise) * env * 0.5)
    return out


def gen_door_creak() -> list[float]:
    """Puerta vieja crujiendo: barrido grave largo + final con thud."""
    duration = 0.9
    n = int(duration * SAMPLE_RATE)
    rng = random.Random(13)
    out = []
    for i in range(n):
        t = i / SAMPLE_RATE
        # Frecuencia muy baja modulando con un seno lento
        f = 90 + 40 * math.sin(2 * math.pi * 1.5 * t)
        mod = 0.5 + 0.5 * math.sin(2 * math.pi * 12 * t)
        env_attack = min(1.0, t / 0.1)
        env_decay = math.exp(-max(0, t - 0.6) * 6)
        env = env_attack * env_decay
        noise = rng.gauss(0, 1) * 0.05
        out.append((math.sin(2 * math.pi * f * t) * mod + noise) * env * 0.6)
    return out


def gen_quill_writing() -> list[float]:
    """Pluma rasgando papel: ruido filtrado con envolvente irregular."""
    duration = 1.2
    n = int(duration * SAMPLE_RATE)
    rng = random.Random(17)
    raw = [rng.gauss(0, 1) for _ in range(n)]
    # Filtro paso-alto (diferencia)
    out = [raw[i] - raw[i-1] if i > 0 else 0 for i in range(n)]
    # Envolvente irregular (escritura intermitente)
    for i in range(n):
        t = i / SAMPLE_RATE
        # 3 trazos de pluma
        env = (math.exp(-(t-0.1)**2 * 80) +
               math.exp(-(t-0.5)**2 * 80) +
               math.exp(-(t-0.9)**2 * 80))
        out[i] *= env * 0.4
    return out


_GENERATORS: dict[str, Callable[[], list[float]]] = {
    "fire_crackle": lambda: gen_fire_crackle(duration=6.0),
    "palantir_hum": lambda: gen_palantir_hum(duration=6.0),
    "page_turn": gen_page_turn,
    "magic_sparkle": gen_magic_sparkle,
    "seal_thump": gen_seal_thump,
    "footstep": gen_footstep,
    "chair_creak": gen_chair_creak,
    "door_creak": gen_door_creak,
    "quill_writing": gen_quill_writing,
}


def regenerate_sounds(out_dir: Path = SOUNDS_DIR) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, gen in _GENERATORS.items():
        samples = gen()
        p = out_dir / f"{name}.wav"
        _save_wav(samples, p)
        paths[name] = p
    return paths


# ---------- playback ----------

class SoundPlayer:
    """Reproductor polifónico con backend pygame.mixer.

    - 2 canales de loops ambientales (chimenea + palantir hum durante DEBATE)
    - 2 canales reservados para one-shots (no se interrumpen entre sí)
    - Volúmenes ajustables por categoría
    - Fallback transparente a winsound si pygame no está disponible
    - No-op silencioso si está deshabilitado o no hay backend
    """

    # Canales asignados: 0,1 = ambient loops · 2,3 = one-shots
    CH_AMBIENT_FIRE = 0
    CH_AMBIENT_HUM = 1
    CH_ONESHOT_A = 2
    CH_ONESHOT_B = 3
    _next_oneshot_channel = CH_ONESHOT_A

    def __init__(self, sounds_dir: Path = SOUNDS_DIR, enabled: bool = True,
                 master_volume: float = 0.7):
        self.sounds_dir = sounds_dir
        self.master_volume = master_volume
        self._sounds: dict[str, object] = {}
        self._backend: str = "none"
        self._lock = threading.Lock()
        # Intenta pygame primero
        if enabled:
            self._init_pygame()
        if self._backend == "none" and enabled:
            self._init_winsound()
        self.enabled = self._backend != "none"

    def _init_pygame(self) -> None:
        try:
            import os
            # Suprime mensaje de bienvenida de pygame en stdout
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame
            pygame.mixer.pre_init(frequency=SAMPLE_RATE, size=-16,
                                  channels=1, buffer=1024)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(8)
            self._pygame = pygame
            self._backend = "pygame"
        except Exception:
            self._backend = "none"

    def _init_winsound(self) -> None:
        try:
            import winsound  # noqa
            self._backend = "winsound"
            self._current_loop_winsound: str | None = None
            self._resume_timer: threading.Timer | None = None
        except ImportError:
            self._backend = "none"

    def _load(self, name: str):
        """Carga lazy de Sound en pygame; cachea para evitar I/O."""
        if name in self._sounds:
            return self._sounds[name]
        path = self.sounds_dir / f"{name}.wav"
        if not path.exists():
            return None
        if self._backend == "pygame":
            try:
                snd = self._pygame.mixer.Sound(str(path))
                self._sounds[name] = snd
                return snd
            except Exception:
                return None
        return None

    def play_loop(self, name: str, slot: str = "fire",
                  volume: float = 1.0) -> None:
        """Reproduce un loop ambiente. slot='fire' o 'hum'."""
        if not self.enabled:
            return
        if self._backend == "pygame":
            snd = self._load(name)
            if snd is None:
                return
            ch_idx = self.CH_AMBIENT_FIRE if slot == "fire" else self.CH_AMBIENT_HUM
            ch = self._pygame.mixer.Channel(ch_idx)
            ch.set_volume(self.master_volume * volume)
            ch.play(snd, loops=-1, fade_ms=300)
        elif self._backend == "winsound":
            # Solo soporta un loop a la vez
            with self._lock:
                path = self.sounds_dir / f"{name}.wav"
                if path.exists():
                    self._current_loop_winsound = name
                    import winsound
                    winsound.PlaySound(str(path),
                                       winsound.SND_ASYNC | winsound.SND_FILENAME
                                       | winsound.SND_LOOP)

    def stop_loop(self, slot: str = "fire", fade_ms: int = 400) -> None:
        if not self.enabled:
            return
        if self._backend == "pygame":
            ch_idx = self.CH_AMBIENT_FIRE if slot == "fire" else self.CH_AMBIENT_HUM
            ch = self._pygame.mixer.Channel(ch_idx)
            ch.fadeout(fade_ms)
        elif self._backend == "winsound" and slot == "fire":
            with self._lock:
                self._current_loop_winsound = None
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)

    def play_oneshot(self, name: str, volume: float = 1.0,
                     resume_loop: bool = True) -> None:
        if not self.enabled:
            return
        if self._backend == "pygame":
            snd = self._load(name)
            if snd is None:
                return
            # Alterna entre los 2 canales de one-shots para permitir solape
            with self._lock:
                ch_idx = SoundPlayer._next_oneshot_channel
                SoundPlayer._next_oneshot_channel = (
                    self.CH_ONESHOT_B if ch_idx == self.CH_ONESHOT_A
                    else self.CH_ONESHOT_A
                )
            ch = self._pygame.mixer.Channel(ch_idx)
            ch.set_volume(self.master_volume * volume)
            ch.play(snd)
        elif self._backend == "winsound":
            path = self.sounds_dir / f"{name}.wav"
            if not path.exists():
                return
            with self._lock:
                import winsound
                winsound.PlaySound(str(path),
                                   winsound.SND_ASYNC | winsound.SND_FILENAME)
                if resume_loop and self._current_loop_winsound:
                    if self._resume_timer is not None:
                        self._resume_timer.cancel()
                    self._resume_timer = threading.Timer(
                        1.2, self._restart_loop_winsound)
                    self._resume_timer.daemon = True
                    self._resume_timer.start()

    def _restart_loop_winsound(self) -> None:
        with self._lock:
            if self._current_loop_winsound is None:
                return
            path = self.sounds_dir / f"{self._current_loop_winsound}.wav"
            if path.exists():
                import winsound
                winsound.PlaySound(str(path),
                                   winsound.SND_ASYNC | winsound.SND_FILENAME
                                   | winsound.SND_LOOP)

    def stop(self) -> None:
        if not self.enabled:
            return
        if self._backend == "pygame":
            self._pygame.mixer.fadeout(500)
        elif self._backend == "winsound":
            with self._lock:
                self._current_loop_winsound = None
                if getattr(self, "_resume_timer", None) is not None:
                    self._resume_timer.cancel()
                    self._resume_timer = None
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)

    @property
    def backend(self) -> str:
        return self._backend


# ---------- entry point ----------

def main() -> None:
    parser = argparse.ArgumentParser(description="Genera los WAVs procedurales del Consejo.")
    parser.add_argument("--out", type=Path, default=SOUNDS_DIR)
    args = parser.parse_args()
    paths = regenerate_sounds(args.out)
    print(f"Generados {len(paths)} sonidos en {args.out.resolve()}")
    for name, p in sorted(paths.items()):
        size_kb = p.stat().st_size // 1024
        print(f"  {name:18s} -> {p.name} ({size_kb} KB)")


if __name__ == "__main__":
    main()
