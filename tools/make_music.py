"""Generates assets/music/track1..6.m4a: original ~12s loops (synthesized here, so no licensing issues).
Each track differs in tempo, key, chord progression, lead sound and drum pattern."""
import subprocess, wave
from pathlib import Path
import numpy as np

SR, SECS = 44100, 12.5
ROOT = Path(__file__).resolve().parent.parent
note = lambda m: 440 * 2 ** ((m - 69) / 12)

TRACKS = [
    # name, bpm, key shift, progression (scale degrees as midi offsets from C), lead wave, drum style
    ("pop",      118, 0, [[0, 4, 7], [-5, -1, 2], [-3, 0, 4], [-7, -3, 0]], "sine",   "four"),
    ("funky",    108, 2, [[0, 3, 7], [5, 8, 12], [3, 7, 10], [7, 10, 14]],  "square", "funk"),
    ("house",    124, -3, [[0, 4, 7], [-3, 0, 4], [5, 9, 12], [7, 11, 14]], "saw",    "four"),
    ("chill",    92, 5, [[0, 4, 7, 11], [-3, 0, 4, 7], [2, 5, 9, 12], [-5, -1, 2, 5]], "sine", "half"),
    ("tropical", 112, 7, [[0, 4, 7], [-5, -1, 2], [-3, 0, 4], [5, 9, 12]],  "pluck",  "reggaeton"),
    ("bright",   128, -1, [[0, 4, 7], [5, 9, 12], [7, 11, 14], [5, 9, 12]], "square", "four"),
]


def env(n, a=0.005, d=0.25):
    x = np.arange(n) / SR
    return np.minimum(x / a, 1) * np.exp(-x / d)


def osc(kind, f, x):
    ph = 2 * np.pi * f * x
    if kind == "square":
        return np.sign(np.sin(ph)) * 0.5
    if kind == "saw":
        return 2 * ((f * x) % 1) - 1
    if kind == "pluck":
        return np.sin(ph) * np.exp(-x * 9) + 0.3 * np.sin(2 * ph) * np.exp(-x * 14)
    return np.sin(ph)


def make(name, bpm, key, prog, lead, drums, seed):
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    out = np.zeros(int(SR * SECS))

    def add(start, sig, gain=1.0):
        i = int(start * SR)
        n = min(len(sig), len(out) - i)
        if n > 0 and i >= 0:
            out[i:i + n] += gain * sig[:n]

    kick_beats = {"four": [0, 1, 2, 3], "funk": [0, 1.5, 2.75], "half": [0, 2.5], "reggaeton": [0, 1, 2, 3]}[drums]
    snare_beats = {"four": [1, 3], "funk": [1, 3], "half": [2], "reggaeton": [0.75, 1.5, 2.75, 3.5]}[drums]
    nbars = int(SECS / (4 * beat)) + 1
    for bar in range(nbars):
        chord = [m + 60 + key for m in prog[bar % 4]]
        b0 = bar * 4 * beat
        for k in kick_beats:
            n = int(0.25 * SR); x = np.arange(n) / SR
            add(b0 + k * beat, np.sin(2 * np.pi * (50 + 90 * np.exp(-x * 30)) * x) * env(n, 0.001, 0.12), 0.9)
        for sn in snare_beats:
            n = int(0.18 * SR)
            add(b0 + sn * beat, rng.standard_normal(n) * env(n, 0.001, 0.05), 0.22)
        for h in np.arange(0, 4, 0.5):
            n = int(0.04 * SR)
            add(b0 + (h + 0.25 if drums == "funk" else h + 0.5) * beat, rng.standard_normal(n) * env(n, 0.001, 0.012), 0.07)
        # bass on root, rhythm per style
        for bb in ([0, 1, 2, 3] if drums != "half" else [0, 2]):
            n = int(beat * SR * 0.8); x = np.arange(n) / SR
            add(b0 + bb * beat, np.sin(2 * np.pi * note(chord[0] - 24) * x) * env(n, 0.005, 0.35), 0.45)
        # chord stabs / pads
        for st in ([0.5, 1.5, 2.5, 3.5] if drums != "half" else [0]):
            n = int((0.3 if drums != "half" else 4 * beat) * SR); x = np.arange(n) / SR
            pad = sum(np.sin(2 * np.pi * note(m) * x) for m in chord) / len(chord)
            add(b0 + st * beat, pad * env(n, 0.003 if drums != "half" else 0.3, 0.15 if drums != "half" else 1.5), 0.25)
        # simple lead melody from chord tones
        for i, step in enumerate(rng.choice([0, 1, 2, 2, 1, 0, 2, 1], 4)):
            n = int(0.45 * beat * SR); x = np.arange(n) / SR
            m = chord[step % len(chord)] + 12
            add(b0 + i * beat + 0.25 * beat, osc(lead, note(m), x) * env(n, 0.005, 0.18), 0.12)
    fade = int(0.3 * SR)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade * 3:] *= np.linspace(1, 0, fade * 3)
    out = out / np.max(np.abs(out)) * 0.8
    return (out * 32767).astype(np.int16)


if __name__ == "__main__":
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    dst = ROOT / "assets" / "music"
    dst.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(TRACKS, 1):
        pcm = make(*t, seed=i)
        wav = dst / f"track{i}.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(wav), "-ac", "2", "-c:a", "aac", "-b:a", "160k",
                        str(dst / f"track{i}.m4a")], check=True)
        wav.unlink()
        print("track", i, t[0])
