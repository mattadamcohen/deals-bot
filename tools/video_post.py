"""Instagram product-video post: the item's own video (from Amazon/AliExpress) framed with our title + price banner.
Runs in the video slots (config video_slots, Israel hours). Skips the slot if a carousel went out today or no
recent deal has a usable video. At most one per slot; the same item is never used twice.
  python tools/video_post.py [--force] [--no-instagram]
"""
import json, os, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import reel  # fonts, helpers, publish
bot = reel.bot
CONFIG = reel.CONFIG
ST = REPO / "data" / "reels.json"
OUT = REPO / "reel-out"
W, H = 1080, 1920


def banner(p):
    """Top title + bottom price/CTA overlay (transparent PNG)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 330], fill=(20, 80, 230, 235))
    d.rectangle([0, H - 420, W, H], fill=(255, 214, 0, 240))
    title = reel.short_he(p.get("title_he") or p.get("title"))
    from ad import F, text_c
    text_c(d, W / 2, 70, "דיל שווה", F(900, 70), (255, 214, 0))
    text_c(d, W / 2, 175, title[:34], F(800, 54), (255, 255, 255))
    price = bot.shekels(p.get("price") or "")
    text_c(d, W / 2, H - 390, price, F(900, 120), (20, 20, 30))
    off = (p.get("discount") or "").strip()
    if off:
        text_c(d, W / 2, H - 250, f"{off} הנחה", F(900, 56), (235, 30, 60))
    text_c(d, W / 2, H - 165, "כתבו \"לינק\" ונשלח לכם בפרטי", F(800, 48), (20, 20, 30))
    text_c(d, W / 2, H - 95, "t.me/ilamazondeals", F(800, 36), (8, 30, 110))
    return im


def make_video(p, src):
    OUT.mkdir(exist_ok=True)
    raw = OUT / "src.mp4"
    raw.write_bytes(src)
    ov = OUT / "overlay.png"
    banner(p).save(ov)
    final = OUT / "product-video.mp4"
    ff = reel.FFMPEG
    # product video centred between the banners, blurred copy as background, max 30 s, keep original audio if any
    vf = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5[bg];"
          "[0:v]scale=1080:1170:force_original_aspect_ratio=decrease[fg];"
          "[bg][fg]overlay=(W-w)/2:330+(1170-h)/2[v1];[v1][1:v]overlay=0:0,format=yuv420p[v]")
    r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(raw), "-i", str(ov), "-filter_complex", vf,
                        "-map", "[v]", "-map", "0:a?", "-t", "30", "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "21", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(final)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("ffmpeg failed:", r.stderr[-400:])
        return None
    return final


def caption(p):
    store = "אליאקספרס" if p.get("store") == "aliexpress" else "אמזון"
    title = reel.short_he(p.get("title_he") or p.get("title"))
    price = bot.shekels(p.get("price") or "")
    off = f" ({p['discount']} הנחה)" if p.get("discount") else ""
    lines = [f"🔥 {title}", f"💰 {price}{off} ב{store}", "",
             "💬 כתבו \"לינק\" בתגובות ונשלח לכם את הקישור בפרטי",
             "🔗 הקישור גם בתגובה הראשונה",
             "👈 עוד דילים כל יום בערוץ הטלגרם, הקישור בביו", "",
             "#דילים #" + ("אליאקספרס" if store == "אליאקספרס" else "אמזון") + " #קניותאונליין #מבצעים"]
    return "\n".join(lines)


def main():
    st = json.loads(ST.read_text()) if ST.exists() else {}
    force = "--force" in sys.argv
    slot = None if force else reel.due_slot(st, "video_slots", "video_slots_done")
    if not force and not slot:
        print("No video slot due now")
        return
    today = datetime.now(ZoneInfo("Asia/Jerusalem")).date().isoformat()
    if not force and (st.get("last_carousel_at", "") and
                      datetime.fromisoformat(st["last_carousel_at"]).astimezone(ZoneInfo("Asia/Jerusalem")).date().isoformat() == today
                      and slot.endswith("-14")):
        print("Carousel went out today; skipping the 14:00 video slot")
        st["video_slots_done"] = (st.get("video_slots_done", []) + [slot])[-10:]
        ST.write_text(json.dumps(st))
        return
    posts = json.loads((REPO / "data" / "posts.json").read_text())
    used = set(st.get("video_used", []))
    since = (datetime.now(timezone.utc) - timedelta(hours=CONFIG.get("video_lookback_hours", 36))).isoformat()
    cands = [p for p in posts if p.get("video") and p["posted_at"] > since and p["asin"] not in used
             and not reel.is_battery(p)]
    cands.sort(key=reel.deal_score, reverse=True)
    media, chosen = None, None
    for p in cands[:5]:
        try:
            r = requests.get(p["video"], timeout=60)
            if not r.ok or len(r.content) < 50_000 or len(r.content) > 60 * (1 << 20):
                continue
        except Exception as e:
            print("video download failed:", e)
            continue
        final = make_video(p, r.content)
        if not final:
            continue
        chosen = p
        print("rendered", final, final.stat().st_size // 1024, "KB for", p["asin"])
        if "--no-instagram" not in sys.argv:
            media = reel.publish_instagram(final, [p], cap=caption(p), thumb_ms=1500)
            if media:
                reel.add_links(media, [p], st)
                st.setdefault("media", []).append({"id": media, "asins": [p["asin"]], "at": datetime.now(timezone.utc).isoformat()})
                st["media"] = st["media"][-30:]
        reel.send(final, [p], media, 0)
        break
    if not chosen:
        print("No recent deal with a usable video; skipping this slot")
    else:
        st["video_used"] = (st.get("video_used", []) + [chosen["asin"]])[-200:]
    if slot:
        st["video_slots_done"] = (st.get("video_slots_done", []) + [slot])[-10:]
    ST.write_text(json.dumps(st))


if __name__ == "__main__":
    main()
