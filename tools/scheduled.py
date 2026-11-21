"""One-off scheduled posts from config 'scheduled' (Israel time). Each runs once; done ids are kept in data/scheduled.json.
  kinds: tg_giveaway (rules + pinned announcement in the channel), ig_image (single Instagram image post)."""
import json, os, subprocess, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
CONFIG = json.loads((REPO / "config.json").read_text())
ST = REPO / "data" / "scheduled.json"


LINK_COMMENT = ("📲 הצטרפו לערוץ הטלגרם שלנו ואתם בהגרלה על $50 לאמזון 🎁\n👉 t.me/ilamazondeals\n"
                "(הקישור הלחיץ נמצא בביו)\n\n🇬🇧 Join our Telegram channel: t.me/ilamazondeals")


def item_links(asins):
    import reel
    posts = json.loads((REPO / "data" / "posts.json").read_text())
    posts = posts if isinstance(posts, list) else list(posts.values())
    by = {p["asin"]: p for p in posts}
    return reel.links_text([by[a] for a in asins if a in by]) + "\n\n📲 עוד דילים בטלגרם: t.me/ilamazondeals"


def comment(media, text=None):
    import requests
    r = requests.post(f"https://graph.facebook.com/v23.0/{media}/comments",
                      data={"message": text or LINK_COMMENT, "access_token": os.getenv("IG_ACCESS_TOKEN", "").strip()}, timeout=30)
    print("link comment", media, r.status_code, r.text[:150])
    return r.ok


def main():
    done = json.loads(ST.read_text()) if ST.exists() else []
    now = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%dT%H:%M")
    for job in CONFIG.get("scheduled", []):
        if job["id"] in done or job["at"] > now:
            continue
        ok = False
        if job["kind"] == "tg_giveaway":
            r = subprocess.run([sys.executable, str(REPO / "tools" / "channel.py"), "giveaway"], capture_output=True, text=True)
            print(r.stdout[-400:], r.stderr[-400:])
            ok = "giveaway post True" in r.stdout
        elif job["kind"] == "ig_image":
            import ig_post
            img = Image.open(REPO / job["image"]).convert("RGB")
            urls = ig_post.host({job["id"]: img})
            media = ig_post.publish(list(urls.values()), (REPO / job["caption_file"]).read_text().strip())
            print("instagram", job["id"], media)
            ok = bool(media)
            if ok:
                comment(media, item_links(job["link_asins"]) if job.get("link_asins") else None)
        elif job["kind"] == "ig_comment":
            ok = comment(job["media"], item_links(job["link_asins"]) if job.get("link_asins") else None)
        print(job["id"], "OK" if ok else "FAILED")
        if ok:
            done.append(job["id"])
            ST.write_text(json.dumps(done))


if __name__ == "__main__":
    main()
