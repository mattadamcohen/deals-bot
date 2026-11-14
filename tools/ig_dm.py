"""Reply to Instagram comments with the product link by private message (DM).

For every bot post/reel from the last 7 days, new comments get:
  1. a private reply (DM) with the product link(s) - links in DMs are clickable
  2. a short public reply under the comment ("📩 שלחנו לך בפרטי")
Each comment is handled once (data/ig_replied.json).
  python tools/ig_dm.py          # handle new comments
  python tools/ig_dm.py --check  # just list recent comments, send nothing
"""
import json, os, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

REPO = Path(__file__).resolve().parent.parent
CONFIG = json.loads((REPO / "config.json").read_text())
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
IG = str(CONFIG.get("ig_user_id") or "")
API = "https://graph.facebook.com/v23.0"
TAG = CONFIG.get("amazon_tag", "")
REPLIED = REPO / "data" / "ig_replied.json"


def link(asin):
    return f"https://www.amazon.com/dp/{asin}" + (f"?tag={TAG}" if TAG else "")


def media_map():
    """media id -> list of (asin, hebrew title) for bot posts and reels from the last 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    posts = json.loads((REPO / "data" / "posts.json").read_text())
    by_asin = {p["asin"]: p for p in posts}
    out = {}
    for p in posts:
        m = p.get("ig_media")
        if m and m != "failed" and datetime.fromisoformat(p["posted_at"]) > cutoff:
            out[m] = [p["asin"]]
    st_f = REPO / "data" / "reels.json"
    st = json.loads(st_f.read_text()) if st_f.exists() else {}
    for r in st.get("media", []):
        if datetime.fromisoformat(r["at"]) > cutoff:
            out[r["id"]] = r["asins"]
    return {m: [(a, (by_asin.get(a, {}).get("title_he") or by_asin.get(a, {}).get("title") or "")[:60]) for a in asins]
            for m, asins in out.items()}


def dm_text(items):
    if len(items) == 1:
        a, t = items[0]
        body = f"הנה הקישור ל{t}:\n{link(a)}"
    else:
        body = "הנה הקישורים למוצרים מהסרטון:\n\n" + "\n\n".join(f"{i}. {t}\n{link(a)}" for i, (a, t) in enumerate(items, 1))
    return ("היי! 👋 " + body + "\n\n📦 משלוח חינם לישראל בהזמנה מעל $49 (אפשר לשלב כמה מוצרים)"
            "\n🔥 עוד דילים כל יום בערוץ הטלגרם שלנו: t.me/ilamazondeals")


def main():
    if not (TOKEN and IG):
        sys.exit("IG_ACCESS_TOKEN / ig_user_id missing")
    done = json.loads(REPLIED.read_text()) if REPLIED.exists() else {}
    me = requests.get(f"{API}/{IG}", params={"fields": "username", "access_token": TOKEN}, timeout=30).json().get("username")
    sent = 0
    for media, items in media_map().items():
        r = requests.get(f"{API}/{media}/comments", params={"fields": "id,text,username,timestamp",
                                                             "limit": 50, "access_token": TOKEN}, timeout=30)
        if not r.ok:
            print("comments error", media, r.text[:200])
            continue
        for c in r.json().get("data", []):
            if c["id"] in done or c.get("username") == me:
                continue
            print(f"comment on {media} by {c.get('username')}: {c.get('text', '')[:60]}")
            if "--check" in sys.argv:
                continue
            dm = requests.post(f"{API}/{IG}/messages", json={"recipient": {"comment_id": c["id"]},
                                                            "message": {"text": dm_text(items)}},
                               params={"access_token": TOKEN}, timeout=30)
            print("  DM:", dm.status_code, dm.text[:200])
            if dm.ok:
                requests.post(f"{API}/{c['id']}/replies", data={"message": "📩 שלחנו לך את הקישור בהודעה פרטית!",
                                                                 "access_token": TOKEN}, timeout=30)
                sent += 1
            done[c["id"]] = {"ok": dm.ok, "at": datetime.now(timezone.utc).isoformat()}
            time.sleep(2)
    # forget entries older than 30 days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    done = {k: v for k, v in done.items() if v.get("at", "") > cutoff}
    REPLIED.write_text(json.dumps(done, indent=1))
    print(f"done, {sent} DM(s) sent")


if __name__ == "__main__":
    main()
