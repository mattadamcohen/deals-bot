"""
Amazon best-seller -> Telegram channel bot.

Every run it:
  1. sets the Amazon.com delivery location to Israel,
  2. reads the Best Sellers list of a few categories (rotating through all of them),
  3. opens each top item and keeps only those showing FREE delivery to Israel,
  4. posts new ones to your Telegram channel (no repeats within REPOST_AFTER_DAYS).

Settings live in config.json. Secrets come from environment variables:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (e.g. @mychannel), optional AMAZON_TAG.
Set DRY_RUN=1 to print posts instead of sending them.
"""

import html
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / "config.json").read_text())
STATE_FILE = ROOT / "data" / "state.json"
DEBUG_DIR = ROOT / "debug"
BASE = "https://www.amazon.com"

DRY_RUN = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
AMAZON_TAG = os.getenv("AMAZON_TAG", "").strip()


class Blocked(Exception):
    """Amazon served a captcha / robot check."""


# ---------------------------------------------------------------- utilities

def log(*a):
    print(*a, flush=True)


def save_debug(name, text):
    DEBUG_DIR.mkdir(exist_ok=True)
    (DEBUG_DIR / name).write_text(text or "", encoding="utf-8")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"next_category": 0, "posted": {}, "not_free": {}}


def save_state(state):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True))


def now():
    return datetime.now(timezone.utc)


def is_recent(iso, days):
    try:
        return now() - datetime.fromisoformat(iso) < timedelta(days=days)
    except Exception:
        return False


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def money(text):
    m = re.search(r"[\d,]+(?:\.\d+)?", text or "")
    return float(m.group().replace(",", "")) if m else 0.0


def big_image(url):
    # Amazon image URLs carry a size token like ._AC_UL300_SR300,200_. ; removing it gives the full image
    return re.sub(r"\._[^/]*?_\.(jpg|jpeg|png|webp)$", r".\1", url or "", flags=re.I)


# ---------------------------------------------------------------- amazon

class Amazon:
    def __init__(self):
        self.s = cffi_requests.Session(impersonate="safari")
        self.s.headers.update({"Accept-Language": "en-US,en;q=0.9"})
        # show prices in USD even with an Israeli delivery address
        self.s.cookies.set("i18n-prefs", "USD", domain=".amazon.com")
        self.requests_made = 0

    def get(self, url, **kw):
        if self.requests_made:
            time.sleep(random.uniform(*CONFIG["delay_seconds"]))
        self.requests_made += 1
        kw.setdefault("headers", {}).setdefault("referer", BASE + "/gp/bestsellers/")
        r = self.s.get(url, timeout=30, **kw)
        body = r.text
        if "validateCaptcha" in body or "Enter the characters you see below" in body or r.status_code == 503:
            save_debug("captcha.html", body)
            raise Blocked(f"robot check on {url} (HTTP {r.status_code})")
        return r

    def set_location_israel(self):
        # Amazon blocks the homepage for bots but serves Best Sellers pages, so start there
        home = self.get(BASE + "/gp/bestsellers/").text
        m = re.search(r'anti-csrftoken-a2z(?:&quot;|")\s*:\s*(?:&quot;|")(.*?)(?:&quot;|")', home)
        token1 = m.group(1) if m else ""
        sel = self.get(
            BASE + "/portal-migration/hz/glow/get-rendered-address-selections"
            "?deviceType=desktop&pageType=Gateway&storeContext=NoStoreName&actionSource=desktop-modal",
            headers={"anti-csrftoken-a2z": token1, "x-requested-with": "XMLHttpRequest"},
        ).text
        m2 = re.search(r'CSRF_TOKEN\s*:\s*"(.*?)"', sel)
        if not m2:
            save_debug("location_selector.html", sel)
            log("! could not find location token")
            return False
        self.requests_made += 1
        r = self.s.post(
            BASE + "/portal-migration/hz/glow/address-change?actionSource=glow",
            json={"locationType": "COUNTRY", "district": "IL", "countryCode": "IL",
                  "storeContext": "generic", "deviceType": "web", "pageType": "Gateway",
                  "actionSource": "glow"},
            headers={"anti-csrftoken-a2z": m2.group(1), "x-requested-with": "XMLHttpRequest"},
            timeout=30,
        )
        log(f"  location change -> HTTP {r.status_code}")
        check = BeautifulSoup(self.get(BASE + "/gp/bestsellers/").text, "html.parser").select_one("#glow-ingress-line2")
        where = clean(check.get_text()) if check else "?"
        log(f"  delivering to: {where}")
        return "israel" in where.lower()

    def best_sellers(self, slug):
        url = f"{BASE}/gp/bestsellers/{slug}/"
        page = self.get(url).text
        soup = BeautifulSoup(page, "html.parser")
        items, seen = [], set()

        # 1) the grid cards (rank badge + asin)
        for card in soup.select("#gridItemRoot, div.zg-grid-general-faceout, li.zg-item-immersion"):
            asin_el = card.select_one("[data-asin]") or card.select_one("div[id]")
            asin = asin_el.get("data-asin") or asin_el.get("id") if asin_el else None
            if not asin or not re.fullmatch(r"[A-Z0-9]{10}", asin or ""):
                link = card.select_one("a[href*='/dp/']")
                m = re.search(r"/dp/([A-Z0-9]{10})", link["href"]) if link else None
                asin = m.group(1) if m else None
            if not asin or asin in seen:
                continue
            seen.add(asin)
            rank = card.select_one(".zg-bdg-text")
            img = card.select_one("img")
            items.append({
                "asin": asin,
                "rank": int(re.sub(r"\D", "", rank.get_text()) or 0) if rank else len(items) + 1,
                "title": clean(img.get("alt")) if img else "",
                "image": big_image(img.get("src")) if img else "",
            })

        # 2) fallback: any product links in page order
        if not items:
            for m in re.finditer(r"/dp/([A-Z0-9]{10})", page):
                if m.group(1) not in seen:
                    seen.add(m.group(1))
                    items.append({"asin": m.group(1), "rank": len(items) + 1, "title": "", "image": ""})

        title = clean(soup.title.get_text()) if soup.title else ""
        m = re.search(r"popular items in (.+)$", title) or re.search(r"Best Sellers in (.+?)(?: - |$)", title)
        cat_name = m.group(1) if m else slug.replace("-", " ").title()
        if not items:
            save_debug(f"bestsellers_{slug}.html", page)
        return cat_name, sorted(items, key=lambda x: x["rank"])

    def product(self, asin):
        page = self.get(f"{BASE}/dp/{asin}").text
        soup = BeautifulSoup(page, "html.parser")

        def text(sel):
            el = soup.select_one(sel)
            return clean(el.get_text(" ")) if el else ""

        delivery = " ".join(filter(None, [
            text("#mir-layout-DELIVERY_BLOCK"),
            text("#deliveryBlockMessage"),
            text("#amazonGlobal_feature_div"),
            text("#exports_desktop_qualifiedBuybox_tlc_feature_div"),
        ]))
        if "israel" not in delivery.lower():
            # fallback: look for an Israel delivery message anywhere in the buy box area
            m = re.search(r"(FREE (?:delivery|Shipping)[^<]{0,120}Israel[^<]{0,80}|[^<>]{0,80}cannot be shipped to your selected delivery location)", page, re.I)
            if m:
                delivery += " " + clean(m.group(1))
        low = delivery.lower()
        if "cannot be shipped" in low or "currently unavailable" in text("#availability").lower():
            shipping = "no"
        elif "free" in low and "israel" in low:
            shipping = "free"
        elif "israel" in low:
            shipping = "paid"
        else:
            shipping = "unknown"
            save_debug(f"product_{asin}.html", page)

        price_box = soup.select_one("#corePriceDisplay_desktop_feature_div, #corePrice_feature_div, #apex_desktop")
        price = was = ""
        if price_box:
            p = price_box.select_one(".priceToPay .a-offscreen, .a-price .a-offscreen")
            w = price_box.select_one(".a-price.a-text-price .a-offscreen, .basisPrice .a-offscreen")
            price = clean(p.get_text()) if p else ""
            was = clean(w.get_text()) if w else ""
        discount = text("#corePriceDisplay_desktop_feature_div .savingsPercentage").lstrip("-")

        img = soup.select_one("#landingImage, #imgBlkFront")
        image = ""
        if img:
            image = img.get("data-old-hires") or ""
            if not image and img.get("data-a-dynamic-image"):
                try:
                    image = max(json.loads(img["data-a-dynamic-image"]).items(), key=lambda kv: kv[1][0])[0]
                except Exception:
                    pass
            image = image or img.get("src", "")

        rating = text("#acrPopover .a-icon-alt").split(" out")[0]
        reviews = re.sub(r"[^\d,]", "", text("#acrCustomerReviewText"))

        return {
            "title": text("#productTitle"),
            "price": price, "was": was if money(was) > money(price) > 0 else "", "discount": discount,
            "rating": rating, "reviews": reviews, "image": image,
            "shipping": shipping, "delivery_text": delivery[:200],
        }


# ---------------------------------------------------------------- telegram

def product_link(asin):
    return f"{BASE}/dp/{asin}" + (f"?tag={AMAZON_TAG}" if AMAZON_TAG else "")


def caption(item, category):
    L = CONFIG["labels"]
    title = item["title"] or "Amazon best seller"
    if len(title) > 140:
        title = title[:137].rsplit(" ", 1)[0] + "…"
    lines = [f"🔥 #{item['rank']} {L['in']} {html.escape(category)}", "", f"<b>{html.escape(title)}</b>", ""]
    if item.get("price"):
        p = f"💲 <b>{html.escape(item['price'])}</b>"
        if item.get("was"):
            p += f"  <s>{html.escape(item['was'])}</s>"
        if item.get("discount"):
            p += f"  ({html.escape(item['discount'])} {L['off']})"
        lines.append(p)
    if item.get("rating"):
        lines.append(f"⭐ {html.escape(item['rating'])}" + (f" ({item['reviews']})" if item.get("reviews") else ""))
    lines.append(f"🇮🇱 {L['free_shipping']}")
    lines += ["", f'👉 <a href="{product_link(item["asin"])}">{L["view"]}</a>']
    return "\n".join(lines)


def send_telegram(item, category):
    text = caption(item, category)
    if DRY_RUN:
        log("---- DRY RUN post ----\n" + text + f"\n[image] {item.get('image')}\n")
        return True
    api = f"https://api.telegram.org/bot{TG_TOKEN}"
    if item.get("image"):
        r = requests.post(f"{api}/sendPhoto", data={
            "chat_id": TG_CHAT, "photo": item["image"], "caption": text, "parse_mode": "HTML"}, timeout=30)
        if r.ok:
            return True
        log(f"  photo post failed ({r.text[:150]}), sending as text")
    r = requests.post(f"{api}/sendMessage", data={
        "chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}, timeout=30)
    if not r.ok:
        log(f"  ! telegram error: {r.text[:300]}")
    return r.ok


# ---------------------------------------------------------------- main

def main():
    if "--test-telegram" in sys.argv:
        ok = send_telegram({"asin": "B0BSHF7WHW", "rank": 1, "title": "Test post from your deals bot ✅",
                            "price": "$0.00", "image": ""}, "Setup")
        sys.exit(0 if ok else 1)

    if not DRY_RUN and not (TG_TOKEN and TG_CHAT):
        sys.exit("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (or set DRY_RUN=1)")

    state = load_state()
    cats = CONFIG["categories"]
    start = state.get("next_category", 0) % len(cats)
    todo = [cats[(start + i) % len(cats)] for i in range(min(CONFIG["categories_per_run"], len(cats)))]
    state["next_category"] = (start + len(todo)) % len(cats)

    amz = Amazon()
    posted_now = 0
    try:
        log("Setting delivery location to Israel…")
        if not amz.set_location_israel():
            log("! Location not confirmed as Israel; items will only be posted if their page says FREE … Israel")

        for slug in todo:
            if posted_now >= CONFIG["max_posts_per_run"]:
                break
            category, items = amz.best_sellers(slug)
            log(f"\n[{category}] {len(items)} items found")
            checked = 0
            for it in items:
                if checked >= CONFIG["items_to_check_per_category"] or posted_now >= CONFIG["max_posts_per_run"]:
                    break
                asin = it["asin"]
                if is_recent(state["posted"].get(asin, ""), CONFIG["repost_after_days"]):
                    continue
                if is_recent(state["not_free"].get(asin, ""), CONFIG["recheck_not_free_after_days"]):
                    continue
                checked += 1
                info = amz.product(asin)
                log(f"  #{it['rank']} {asin} shipping={info['shipping']}  {info['title'][:60]}")
                if info["shipping"] != "free":
                    if info["shipping"] in ("paid", "no"):
                        state["not_free"][asin] = now().isoformat()
                    continue
                merged = {**it, **{k: v for k, v in info.items() if v}}
                if send_telegram(merged, category):
                    if not DRY_RUN:  # dry runs shouldn't stop the item being posted for real later
                        state["posted"][asin] = now().isoformat()
                    posted_now += 1
                    time.sleep(3)
    except Blocked as e:
        log(f"\n! Amazon blocked this run: {e}")
        save_state(state)
        sys.exit(2 if posted_now == 0 else 0)
    finally:
        # forget very old entries so the state file stays small
        for key, days in (("posted", 60), ("not_free", 30)):
            state[key] = {a: t for a, t in state[key].items() if is_recent(t, days)}
        save_state(state)

    log(f"\nDone. Posted {posted_now} item(s). {amz.requests_made} Amazon requests.")


if __name__ == "__main__":
    main()
