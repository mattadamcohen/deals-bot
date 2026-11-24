"""New-format Instagram reels: full-screen product video, beat-synced cuts, big sharp captions.
  python tools/reel_v2.py under35   -> out/reel_under35.mp4   ("3 things under ₪35")
  python tools/reel_v2.py guess     -> out/reel_guess.mp4     ("Guess the price")
Audio is an original beat generated here (no licensing issues). For more reach, swap in a trending sound in the app.
"""
import json, subprocess, sys, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from ad import F, size
import dealcity as D
import reel

W, H, FPS = 1080, 1920, 30
BPM = 128
BEAT = 60 / BPM
OUT = REPO / "out"
TMP = OUT / "reel_v2_tmp"
VOPT = REPO / "data/ad/vopt"
RATE = json.loads((REPO / "data/fx.json").read_text()).get("rate", 3.34) if (REPO / "data/fx.json").exists() else 3.34
YEL, PINK, NAVY, WHITE, BLACK = (255, 214, 0), (255, 46, 136), (12, 20, 60), (255, 255, 255), (0, 0, 0)


def ils(usd):
    return f"₪{round(usd * RATE)}"


# ---------- audio: a punchy original beat ----------
def beat_wav(path, seconds, sr=44100):
    n = int(seconds * sr)
    out = np.zeros(n)
    t = np.arange(int(0.35 * sr)) / sr
    kick = np.sin(2 * np.pi * (55 + 90 * np.exp(-t * 30)) * t) * np.exp(-t * 9)
    st = np.arange(int(0.18 * sr)) / sr
    snare = (np.random.default_rng(1).uniform(-1, 1, st.size) * .7 + np.sin(2 * np.pi * 190 * st) * .4) * np.exp(-st * 22)
    ht = np.arange(int(0.05 * sr)) / sr
    hat = np.random.default_rng(2).uniform(-1, 1, ht.size) * np.exp(-ht * 90) * .35
    bass_notes = [55, 55, 65.4, 49]
    b = 0
    while b * BEAT < seconds:
        i = int(b * BEAT * sr)

        def add(s, at, g=1.0):
            e = min(n, at + s.size)
            if at < n:
                out[at:e] += s[:e - at] * g
        add(kick, i, 1.0)
        if b % 2 == 1:
            add(snare, i, .8)
        add(hat, i + int(BEAT / 2 * sr), 1)
        add(hat, i, .6)
        f = bass_notes[(b // 4) % 4]
        bt = np.arange(int(BEAT * .9 * sr)) / sr
        add(np.sign(np.sin(2 * np.pi * f * bt)) * .18 * np.exp(-bt * 3), i, 1)
        b += 1
    out /= np.max(np.abs(out)) + 1e-9
    fade = int(.4 * sr)
    out[-fade:] *= np.linspace(1, 0, fade)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((out * 0.85 * 32767).astype(np.int16).tobytes())


# ---------- overlay helpers ----------
def canvas():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def shadow_text(im, xy, text, font, fill, anchor="mm", stroke=10, sfill=BLACK):
    d = ImageDraw.Draw(im)
    d.text(xy, text, font=font, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=sfill)


def pill(im, cx, cy, text, font, bg, fg, pad=(46, 24), angle=0):
    tmp = Image.new("RGBA", (1, 1))
    tw, th, _ = size(ImageDraw.Draw(tmp), text, font)
    w, h = tw + pad[0] * 2, th + pad[1] * 2
    p = Image.new("RGBA", (w + 24, h + 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(p)
    d.rounded_rectangle([12, 18, w + 12, h + 18], radius=h // 2, fill=(0, 0, 0, 170))
    d.rounded_rectangle([0, 0, w, h], radius=h // 2, fill=bg + (255,))
    d.text((w / 2, h / 2), text, font=font, fill=fg, anchor="mm")
    if angle:
        p = p.rotate(angle, expand=True, resample=Image.BICUBIC)
    im.alpha_composite(p, (int(cx - p.width / 2), int(cy - p.height / 2)))


def top_scrim(im, h=520):
    g = Image.new("L", (1, h))
    for y in range(h):
        g.putpixel((0, y), int(190 * (1 - y / h) ** 1.6))
    im.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, h), 0)] * 3 + [g.resize((W, h))]), (0, 0))


def bottom_scrim(im, h=640):
    g = Image.new("L", (1, h))
    for y in range(h):
        g.putpixel((0, y), int(210 * (y / h) ** 1.4))
    im.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, h), 0)] * 3 + [g.resize((W, h))]), (0, H - h))


def number_badge(im, n):
    d = ImageDraw.Draw(im)
    d.ellipse([60, 150, 280, 370], fill=YEL + (255,), outline=BLACK, width=8)
    d.text((170, 262), f"#{n}", font=D.ANTON(120), fill=BLACK, anchor="mm")


def handle_tag(im):
    d = ImageDraw.Draw(im)
    d.text((W - 40, H - 60), "@ilamazondeals", font=F(800, 38), fill=(255, 255, 255, 230), anchor="rs",
           stroke_width=4, stroke_fill=BLACK)


def end_card(lines):
    im = Image.new("RGBA", (W, H), NAVY + (255,))
    d = ImageDraw.Draw(im)
    for i in range(0, W + H, 90):
        d.line([(i, 0), (i - H, H)], fill=(25, 40, 100), width=26)
    logo = Image.open(REPO / "assets/ilamazondeals-logo.png").convert("RGBA")
    logo.thumbnail((380, 380))
    im.alpha_composite(logo, ((W - logo.width) // 2, 330))
    y = 830
    for text, font, fill in lines:
        shadow_text(im, (W / 2, y), text, font, fill, stroke=6)
        y += font.size + 70
    return im


# ---------- video segments ----------
def segment(i, src, start, dur, overlay, zoom=True, crop_bottom=0.0):
    ov = TMP / f"ov{i}.png"
    overlay.save(ov)
    out = TMP / f"seg{i}.mp4"
    z = f",zoompan=z='min(1+0.0009*on,1.06)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS}" if zoom else ""
    pre = f"crop=iw:ih*{1 - crop_bottom:.3f}:0:0," if crop_bottom else ""
    vf = (f"[0:v]{pre}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}{z},"
          f"eq=contrast=1.08:saturation=1.25,unsharp=5:5:0.8[v];[v][1:v]overlay=0:0,format=yuv420p[o]")
    args = [reel.FFMPEG, "-y", "-loglevel", "error"]
    args += (["-ss", str(start), "-t", str(dur), "-i", str(src)] if src else
             ["-f", "lavfi", "-t", str(dur), "-i", f"color=c=black:s={W}x{H}:r={FPS}"])
    args += ["-loop", "1", "-t", str(dur), "-i", str(ov), "-filter_complex", vf, "-map", "[o]", "-an",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), str(out)]
    subprocess.run(args, check=True)
    return out


def still(i, img, dur):
    p = TMP / f"still{i}.png"
    img.convert("RGB").save(p)
    out = TMP / f"seg{i}.mp4"
    subprocess.run([reel.FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-t", str(dur), "-i", str(p),
                    "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out)], check=True)
    return out


def assemble(segs, name, total):
    lst = TMP / "list.txt"
    lst.write_text("".join(f"file '{s.name}'\n" for s in segs))
    joined = TMP / "joined.mp4"
    subprocess.run([reel.FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], check=True)
    wav = TMP / "beat.wav"
    beat_wav(wav, total + 0.5)
    out = OUT / name
    subprocess.run([reel.FFMPEG, "-y", "-loglevel", "error", "-i", str(joined), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    return out


# ---------- formats ----------
def under35():
    items = [  # (video, start, Hebrew name, usd)
        ("v04.mp4", 1.0, "מנורת לילה ארנב שמשנה צבע במגע", 8.35),
        ("v07.mp4", 2.0, "קוביות בנייה מגנטיות", 7.31),
        ("v03.mp4", 1.0, "ענן גשם לאמבטיה", 9.99),
    ]
    segs, seg_len = [], 6 * BEAT
    hook = canvas()
    top_scrim(hook, 900)
    shadow_text(hook, (W / 2, 330), "3 דברים מאליאקספרס", F(900, 92), WHITE)
    pill(hook, W / 2, 500, "מתחת ל-₪35", D.ANTON(118) if False else F(900, 110), YEL, BLACK, angle=-3)
    shadow_text(hook, (W / 2, 680), "שלא ידעתם שאתם צריכים", F(900, 70), WHITE)
    handle_tag(hook)
    segs.append(segment(0, VOPT / items[0][0], 0.2, 4 * BEAT, hook))
    for k, (v, st, he, usd) in enumerate(items, 1):
        ov = canvas()
        top_scrim(ov, 460)
        bottom_scrim(ov)
        number_badge(ov, k)
        shadow_text(ov, (W / 2, H - 470), he, F(900, 64), WHITE, stroke=8)
        pill(ov, W / 2, H - 300, ils(usd), F(900, 150), PINK, WHITE, pad=(60, 18), angle=-4)
        shadow_text(ov, (W / 2, H - 150), "משלוח לארץ · לינק בביו", F(800, 44), YEL, stroke=6)
        handle_tag(ov)
        segs.append(segment(k, VOPT / v, st, seg_len, ov))
    card = end_card([("כל הדילים במקום אחד", F(900, 84), WHITE), ("israelideals.com", D.ANTON(120), YEL),
                     ("לינק בביו", F(900, 70), WHITE)])
    segs.append(still(9, card, 4 * BEAT))
    return assemble(segs, "reel_under35.mp4", 4 * BEAT + 3 * seg_len + 4 * BEAT)


def guess():
    items = [
        ("v13.mp4", 1.0, "מנורת פלזמה", 9.55, 0),
        ("magtrack.mp4", 2.0, "מסלול מגנטי שמטפס על הקיר", 36.39, .24),
        ("v02.mp4", 22.0, "כלב רובוט חכם", 50.89, 0),
    ]
    segs, ask, reveal = [], 5 * BEAT, 3 * BEAT
    for k, (v, st, he, usd, cb) in enumerate(items, 1):
        q = canvas()
        top_scrim(q, 620)
        bottom_scrim(q, 520)
        shadow_text(q, (W / 2, 250), "תנחשו כמה זה עולה?" if k == 1 else f"ומה עם זה? ({k}/3)", F(900, 92), WHITE)
        pill(q, W / 2, 440, "₪ ?", F(900, 160), YEL, BLACK, pad=(70, 10), angle=4)
        shadow_text(q, (W / 2, H - 230), he, F(900, 66), WHITE, stroke=8)
        handle_tag(q)
        segs.append(segment(2 * k, VOPT / v, st, ask, q, crop_bottom=cb))
        r = canvas()
        top_scrim(r, 620)
        bottom_scrim(r, 520)
        shadow_text(r, (W / 2, 250), "רק", F(900, 92), WHITE)
        pill(r, W / 2, 470, ils(usd), F(900, 190), PINK, WHITE, pad=(70, 16), angle=-5)
        shadow_text(r, (W / 2, H - 230), he, F(900, 66), WHITE, stroke=8)
        handle_tag(r)
        segs.append(segment(2 * k + 1, VOPT / v, st + ask, reveal, r, zoom=False, crop_bottom=cb))
    card = end_card([("כמה ניחשתם?", F(900, 96), YEL), ("כתבו בתגובות", F(900, 80), WHITE),
                     ("כל הדילים: israelideals.com", F(900, 62), WHITE), ("לינק בביו", F(900, 62), YEL)])
    segs.append(still(9, card, 5 * BEAT))
    return assemble(segs, "reel_guess.mp4", 3 * (ask + reveal) + 5 * BEAT)


if __name__ == "__main__":
    TMP.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(exist_ok=True)
    print({"under35": under35, "guess": guess}[sys.argv[1]]())
