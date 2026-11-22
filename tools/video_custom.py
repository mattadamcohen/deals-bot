"""Hand-picked product video for Instagram: our title/price banners + a Telegram @ badge on the video.
  python tools/video_custom.py SPEC.json [--no-instagram]
SPEC: {"id", "title_he", "price", "video" (url or repo path), "start", "dur", "link", "store", "discount"}
"""
import json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import video_post as vp
from ad import F, size, text_c, TG

reel, W, H = vp.reel, vp.W, vp.H
HANDLE = "@ilamazondeals"


def plane(d, cx, cy, r):
    """Telegram-style paper plane in a white circle."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255))
    s = r / 50
    pts = [(-26, -2), (24, -20), (14, 22), (2, 10), (-6, 18), (-6, 6)]
    d.polygon([(cx + x * s, cy + y * s) for x, y in pts], fill=TG)
    d.line([(cx - 6 * s, cy + 6 * s), (cx + 18 * s, cy - 14 * s)], fill=(255, 255, 255), width=max(2, int(3 * s)))


def tg_badge(im):
    """Pill with the plane + @handle, just under the top banner, plus a 'join' line."""
    d = ImageDraw.Draw(im)
    f = F(900, 58)
    tw, th, _ = size(d, HANDLE, f)
    pw, ph = tw + 170, 104
    x0, y0 = (W - pw) // 2, 360
    d.rounded_rectangle([x0 + 6, y0 + 8, x0 + pw + 6, y0 + ph + 8], radius=ph // 2, fill=(0, 0, 0, 90))
    d.rounded_rectangle([x0, y0, x0 + pw, y0 + ph], radius=ph // 2, fill=TG + (255,), outline=(255, 255, 255), width=5)
    plane(d, x0 + 62, y0 + ph // 2, 38)
    d.text((x0 + 118, y0 + ph // 2), HANDLE, font=f, fill=(255, 255, 255), anchor="lm")
    j = "הצטרפו לערוץ הדילים בטלגרם"
    jf = F(800, 40)
    jw, jh, _ = size(d, j, jf)
    d.rounded_rectangle([(W - jw) / 2 - 24, y0 + ph + 20, (W + jw) / 2 + 24, y0 + ph + 20 + jh + 30], radius=20, fill=(0, 0, 0, 150))
    text_c(d, W / 2, y0 + ph + 34, j, jf, (255, 255, 255))
    return im


def render(p, src_bytes, start=0, dur=30, crop_bottom=0.0):
    vp.OUT.mkdir(exist_ok=True)
    raw = vp.OUT / "src.mp4"
    raw.write_bytes(src_bytes)
    ov = vp.OUT / "overlay.png"
    tg_badge(vp.banner(p)).save(ov)
    final = vp.OUT / "product-video.mp4"
    pre = f"[0:v]crop=iw:ih*{1 - crop_bottom:.3f}:0:0[src];[src]split[s1][s2];" if crop_bottom else "[0:v]split[s1][s2];"
    vf = (pre + "[s1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5[bg];"
          "[s2]scale=1080:1170:force_original_aspect_ratio=decrease[fg];"
          "[bg][fg]overlay=(W-w)/2:330+(1170-h)/2[v1];[v1][1:v]overlay=0:0,format=yuv420p[v]")
    r = subprocess.run([reel.FFMPEG, "-y", "-loglevel", "error", "-ss", str(start), "-t", str(dur), "-i", str(raw), "-i", str(ov),
                        "-filter_complex", vf, "-map", "[v]", "-map", "0:a?", "-r", "30", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(final)],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit("ffmpeg failed: " + r.stderr[-400:])
    return final


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    v = spec["video"]
    src = (REPO / v).read_bytes() if not v.startswith("http") else requests.get(v, timeout=60).content
    p = {"asin": spec["id"], "title_he": spec["title_he"], "title": spec.get("title", ""), "price": spec["price"],
         "discount": spec.get("discount", ""), "store": spec.get("store", "aliexpress"), "link": spec.get("link", "")}
    if p["store"] == "aliexpress" and "--no-instagram" not in sys.argv:
        import aliexpress  # IG rejects long comments: use the short s.click.aliexpress.com/e/_xxx link
        short = aliexpress.link(f"https://www.aliexpress.com/item/{p['asin'].removeprefix('ali-')}.html")
        print("short link:", short)
        if not short or len(short) > 80:
            sys.exit("no short AliExpress link; not posting")
        p["link"] = short
    final = render(p, src, spec.get("start", 0), spec.get("dur", 30), spec.get("crop_bottom", 0.0))
    print("rendered", final, final.stat().st_size // 1024, "KB")
    if "--no-instagram" in sys.argv:
        return
    st = json.loads(vp.ST.read_text()) if vp.ST.exists() else {}
    media = reel.publish_instagram(final, [p], cap=spec.get("caption") or vp.caption(p), thumb_ms=spec.get("thumb_ms", 1500))
    print("IG media", media)
    if media:
        reel.add_links(media, [p], st)
        st.setdefault("media", []).append({"id": media, "asins": [p["asin"]], "at": datetime.now(timezone.utc).isoformat(),
                                           "items": {p["asin"]: {"link": p["link"], "title_he": p["title_he"]}}})
        st["media"] = st["media"][-30:]
        st["video_used"] = (st.get("video_used", []) + [p["asin"]])[-200:]
        vp.ST.write_text(json.dumps(st))


if __name__ == "__main__":
    main()
