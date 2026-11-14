"""Generates assets/music.wav: an original, upbeat 12-second loop (synthesized here, so no licensing issues)."""
import numpy as np, wave
from pathlib import Path
SR, BPM, SECS = 44100, 118, 12.0
beat = 60 / BPM
t = np.arange(int(SR * SECS)) / SR
out = np.zeros_like(t)

def env(n, a=0.005, d=0.25):
    x = np.arange(n) / SR
    return np.minimum(x / a, 1) * np.exp(-x / d)

def add(start, sig):
    i = int(start * SR)
    n = min(len(sig), len(out) - i)
    if n > 0:
        out[i:i + n] += sig[:n]

note = lambda m: 440 * 2 ** ((m - 69) / 12)
# I-V-vi-IV in C (C, G, Am, F), one chord per bar
chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
bass = [36, 43, 45, 41]
nbeats = int(SECS / beat)
for b in range(nbeats):
    bar = (b // 4) % 4
    s = b * beat
    # kick on every beat
    n = int(0.25 * SR); x = np.arange(n) / SR
    add(s, 0.9 * np.sin(2 * np.pi * (50 + 90 * np.exp(-x * 30)) * x) * env(n, 0.001, 0.12))
    # clap/snare on 2 and 4
    if b % 2 == 1:
        n = int(0.18 * SR)
        add(s, 0.25 * np.random.default_rng(b).standard_normal(n) * env(n, 0.001, 0.05))
    # off-beat hats
    n = int(0.05 * SR)
    add(s + beat / 2, 0.08 * np.random.default_rng(1000 + b).standard_normal(n) * env(n, 0.001, 0.015))
    # bass
    n = int(beat * SR * 0.9); x = np.arange(n) / SR
    add(s, 0.35 * np.sign(np.sin(2 * np.pi * note(bass[bar]) * x)) * 0.5 * env(n, 0.005, 0.3))
    # plucky chord stabs on the off-beat
    n = int(0.3 * SR); x = np.arange(n) / SR
    add(s + beat / 2, sum(0.12 * np.sin(2 * np.pi * note(m + 12) * x) for m in chords[bar]) * env(n, 0.003, 0.12))
# fade in/out and normalize
fade = int(0.3 * SR)
out[:fade] *= np.linspace(0, 1, fade); out[-fade * 3:] *= np.linspace(1, 0, fade * 3)
out = out / np.max(np.abs(out)) * 0.8
pcm = (out * 32767).astype(np.int16)
stereo = np.repeat(pcm[:, None], 2, axis=1)
dst = Path(__file__).resolve().parent.parent / "assets" / "music.wav"
with wave.open(str(dst), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(stereo.tobytes())
print("wrote", dst)
