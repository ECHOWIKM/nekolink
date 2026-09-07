# -*- coding: utf-8 -*-
"""Generate short notification wavs for NekoLink (stdlib only)."""
from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parent
SR = 44100
RNG = random.Random(20260907)


def clamp16(x: float) -> int:
    return max(-32768, min(32767, int(x)))


def write_mono(path: Path, samples: list[float], sr: int = SR) -> None:
    peak = max(1e-9, max(abs(s) for s in samples))
    g = 0.72 * 32767.0 / peak
    frames = bytearray()
    for s in samples:
        frames += struct.pack("<h", clamp16(s * g))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(frames))
    print(f"wrote {path.name} ({len(samples) / sr:.3f}s)")


def env_adsr(i: int, n: int, a=0.01, d=0.05, s=0.55, r=0.12) -> float:
    t = i / max(1, n - 1)
    if t < a:
        return t / a
    if t < a + d:
        return 1.0 - (1.0 - s) * ((t - a) / d)
    if t > 1.0 - r:
        return s * max(0.0, (1.0 - t) / r)
    return s


def noise() -> float:
    return RNG.uniform(-1.0, 1.0)


def lowpass_state():
    return {"y": 0.0}


def lowpass(x: float, st: dict, alpha: float) -> float:
    st["y"] = st["y"] + alpha * (x - st["y"])
    return st["y"]


def bandish(x: float, st_hp: dict, st_lp: dict, a_hp=0.15, a_lp=0.25) -> float:
    hp = x - lowpass(x, st_hp, a_hp)
    return lowpass(hp, st_lp, a_lp)


def cough_burst(n: int, bright: float = 1.0, pitch: float = 1.0) -> list[float]:
    """Dry throat-clear burst (synthetic QQ-style homage)."""
    out = []
    st_hp, st_lp, st_lp2 = lowpass_state(), lowpass_state(), lowpass_state()
    for i in range(n):
        # 更快的爆发感
        e = env_adsr(i, n, a=0.008, d=0.28, s=0.15, r=0.48)
        t = i / SR
        f1 = 175.0 * pitch
        f2 = 520.0 * pitch
        glot = 0.16 * math.sin(2 * math.pi * f1 * t)
        glot += 0.09 * math.sin(2 * math.pi * f2 * t)
        # 前几毫秒更像清嗓爆破
        plosive = 1.35 if i < int(0.012 * SR) else (0.95 if i < int(0.04 * SR) else 0.55)
        raw = noise() * plosive + glot
        y = bandish(raw, st_hp, st_lp, a_hp=0.12 + 0.06 * bright, a_lp=0.32)
        y = lowpass(y, st_lp2, 0.48)
        y = math.tanh(y * 1.85) * 0.92
        out.append(y * e)
    return out


def make_qq_cough() -> list[float]:
    """两声短促「咳咳」——致敬 QQ 经典提示音（原创合成，非提取版权资源）。"""
    gap = int(0.055 * SR)
    first = cough_burst(int(0.095 * SR), bright=0.95, pitch=1.05)
    second = [
        s * 1.22 for s in cough_burst(int(0.125 * SR), bright=1.2, pitch=0.94)
    ]
    pad = [0.0] * int(0.015 * SR)
    tail = [0.0] * int(0.05 * SR)
    return pad + first + [0.0] * gap + second + tail


def make_soft_chime() -> list[float]:
    n = int(0.55 * SR)
    out = []
    freqs = [784.0, 1175.0]
    for i in range(n):
        t = i / SR
        e1 = math.exp(-t * 5.5)
        e2 = math.exp(-t * 4.2)
        s = 0.55 * math.sin(2 * math.pi * freqs[0] * t) * e1
        s += 0.40 * math.sin(2 * math.pi * freqs[1] * t) * e2
        s += 0.12 * math.sin(2 * math.pi * freqs[0] * 2 * t) * e1
        out.append(s)
    return out


def make_gentle_ping() -> list[float]:
    n = int(0.35 * SR)
    out = []
    f0 = 1046.5
    for i in range(n):
        t = i / SR
        e = math.exp(-t * 9.0)
        s = math.sin(2 * math.pi * f0 * t) * e
        s += 0.35 * math.sin(2 * math.pi * f0 * 2 * t) * math.exp(-t * 14)
        s += 0.12 * math.sin(2 * math.pi * f0 * 3 * t) * math.exp(-t * 18)
        out.append(s)
    return out


def make_crystal_bell() -> list[float]:
    n = int(0.70 * SR)
    out = []
    partials = [
        (880, 1.0, 4.0),
        (1760, 0.35, 7.0),
        (2630, 0.18, 10.0),
        (3520, 0.08, 14.0),
    ]
    for i in range(n):
        t = i / SR
        s = 0.0
        for f, a, d in partials:
            s += a * math.sin(2 * math.pi * f * t) * math.exp(-t * d)
        out.append(s)
    return out


def make_bubble() -> list[float]:
    n = int(0.28 * SR)
    out = []
    for i in range(n):
        t = i / SR
        f = 420 + 980 * (t / 0.28) ** 0.7
        e = math.exp(-t * 16) * (1 - math.exp(-t * 80))
        out.append(math.sin(2 * math.pi * f * t) * e)
    return out


def make_wood_knock() -> list[float]:
    n = int(0.22 * SR)
    out = []
    st = lowpass_state()
    for i in range(n):
        t = i / SR
        e = math.exp(-t * 28)
        click = noise() if i < int(0.004 * SR) else 0.0
        body = 0.7 * math.sin(2 * math.pi * 190 * t) + 0.35 * math.sin(
            2 * math.pi * 310 * t
        )
        y = lowpass(click * 2.2 + body, st, 0.45)
        out.append(y * e)
    gap = int(0.07 * SR)
    return out + [0.0] * gap + [x * 0.85 for x in out]


def make_soft_marimba() -> list[float]:
    n = int(0.45 * SR)
    out = []
    notes = [523.25, 659.25]
    for i in range(n):
        t = i / SR
        s = 0.0
        for j, f in enumerate(notes):
            td = t - j * 0.09
            if td < 0:
                continue
            e = math.exp(-td * 6.5)
            s += (0.7 if j == 0 else 0.55) * math.sin(2 * math.pi * f * td) * e
            s += 0.15 * math.sin(2 * math.pi * f * 2 * td) * math.exp(-td * 10)
        out.append(s)
    return out


def main() -> None:
    files = {
        "qq_cough.wav": make_qq_cough,
        "咳嗽_qq.wav": make_qq_cough,
        "soft_chime.wav": make_soft_chime,
        "gentle_ping.wav": make_gentle_ping,
        "crystal_bell.wav": make_crystal_bell,
        "bubble_pop.wav": make_bubble,
        "wood_knock.wav": make_wood_knock,
        "soft_marimba.wav": make_soft_marimba,
    }
    for name, fn in files.items():
        write_mono(OUT / name, fn())
    print("done")


if __name__ == "__main__":
    main()
