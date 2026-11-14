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
AMAZON_TAG = (os.getenv("AMAZON_TAG") or CONFIG.get("amazon_tag", "")).strip()


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

def price_text(el):
    """Text of an .a-price element: the hidden full price, or symbol + whole + fraction."""
    if el is None:
        return ""
    off = el.select_one(".a-offscreen")
    t = clean(off.get_text()) if off else ""
    if re.search(r"\d", t):
        return t
    whole = el.select_one(".a-price-whole")
    if whole:
        frac = el.select_one(".a-price-fraction")
        sym = el.select_one(".a-price-symbol")
        w = re.sub(r"[^\d,]", "", whole.get_text())
        return f"{clean(sym.get_text()) if sym else '$'}{w}.{clean(frac.get_text()) if frac else '00'}"
    t = clean(el.get_text())
    return t if re.search(r"\$\s*\d", t) else ""


def find_prices(soup, page):
    """(price, was) from a product page, trying the places Amazon puts prices for simple and multi-variant items."""
    price = was = ""
    for box_sel in ("#corePriceDisplay_desktop_feature_div", "#corePrice_feature_div", "#corePrice_desktop",
                    "#apex_desktop", "#apex_offerDisplay_desktop", "#desktop_buybox", "#buybox"):
        box = soup.select_one(box_sel)
        if not box:
            continue
        price = price or price_text(box.select_one(".priceToPay")) or price_text(
            next((e for e in box.select(".a-price") if "a-text-price" not in (e.get("class") or [])), None))
        was = was or price_text(box.select_one(".basisPrice .a-price, .a-price.a-text-price"))
        if price:
            break
    if not price:
        for sel in ("#priceblock_dealprice", "#priceblock_ourprice", "#priceblock_saleprice", "#price_inside_buybox",
                    "#tp_price_block_total_price_ww", "#sns-base-price", "#price"):
            el = soup.select_one(sel)
            if el:
                price = price_text(el) if el.select_one(".a-price, .a-offscreen") else clean(el.get_text())
                if re.search(r"\d", price):
                    break
                price = ""
    if not price:
        el = soup.select_one("#twister-plus-price-data-price")
        if el and el.get("value"):
            price = f"${float(el['value']):.2f}"
    if not price:
        m = re.search(r'"priceAmount"\s*:\s*([\d.]+)', page) or re.search(r'"displayPrice"\s*:\s*"\$([\d.,]+)"', page)
        if m:
            price = f"${float(m.group(1).replace(',', '')):.2f}"
    m = re.search(r"\$\s*[\d,]+(?:\.\d{2})?", price or "")
    price = m.group(0).replace(" ", "") if m else ""
    m = re.search(r"\$\s*[\d,]+(?:\.\d{2})?", was or "")
    was = m.group(0).replace(" ", "") if m else ""
    return price, was


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

    def best_sellers(self, slug, page=1, kind="bestsellers"):
        url = f"{BASE}/gp/{kind}/{slug}/" + (f"?pg={page}" if page > 1 else "")
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

        if not items:
            save_debug(f"bestsellers_{slug}.html", page)
        return sorted(items, key=lambda x: x["rank"])  # rank as shown on that list

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

        price, was = find_prices(soup, page)
        if not price:
            save_debug(f"noprice_{asin}.html", page)
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


_he_cache = {}


def to_hebrew(text):
    """Machine-translate a short English string to Hebrew; falls back to the original."""
    if not text:
        return text
    if text in _he_cache:
        return _he_cache[text]
    try:
        r = requests.get("https://translate.googleapis.com/translate_a/single",
                         params={"client": "gtx", "sl": "en", "tl": "iw", "dt": "t", "q": text}, timeout=15)
        out = "".join(part[0] for part in r.json()[0] if part and part[0]).strip()
    except Exception as e:
        log(f"  (translation failed: {e})")
        out = ""
    _he_cache[text] = out or text
    return _he_cache[text]


def esc(text):
    return html.escape(text, quote=False)


def short(title, limit=140):
    return title if len(title) <= limit else title[:limit - 3].rsplit(" ", 1)[0] + "…"


def seasonal_lines(category_slug, lang):
    today = datetime.now(timezone(timedelta(hours=2))).date().isoformat()
    out = [x[lang] for x in CONFIG.get("seasons", []) if x["from"] <= today <= x["to"]]
    g = CONFIG.get("gift_season")
    if g and g["from"] <= today <= g["to"] and any(category_slug.startswith(c) for c in g["categories"]):
        out.append(g[lang])
        if today <= g.get("early_until", ""):
            out.append(g["early_" + lang])
    return out


def pick(options, v):
    """Pick variant v of a label (labels can be a single string or a list of variants)."""
    return options[v % len(options)] if isinstance(options, list) else options


def block(item, category, title, L, extra=(), v=0):
    head = pick(L["trending"] if item.get("source") == "movers-and-shakers" else L["rank"], v)
    intro = pick(L.get("intro", [""]), v // 3)
    lines = ([intro, ""] if intro else []) + [f"🔥 {esc(head.format(rank=item['rank'], category=category))}", "",
                                              f"<b>{esc(short(title))}</b>", ""]
    if item.get("price"):
        p = f"💲 <b>{esc(item['price'])}</b>"
        if item.get("was"):
            p += f"  <s>{esc(item['was'])}</s>"
        if item.get("discount"):
            p += f"  ({esc(item['discount'])} {L['off']})"
        lines.append(p)
    if item.get("rating"):
        lines.append(f"⭐ {esc(item['rating'])}" + (f" ({item['reviews']})" if item.get("reviews") else ""))
    lines.append(f"🇮🇱 {pick(L['free_shipping'], v // 2)}")
    if extra:
        lines += ["", *extra]
    lines.append(f'👉 <a href="{product_link(item["asin"])}">{pick(L["view"], v // 4)}</a>')
    return "\n".join(lines)


XMAS = re.compile(r"\s*[-,|]?\s*\b(?:(?:great |perfect |cool |unique )?(?:christmas|xmas|holiday) (?:gifts?|presents?)(?: (?:for|ideas?)[^,|]*)?|stocking stuffers?(?: for [^,|]*)?|christmas|xmas)\b", re.I)


def drop_christmas(title):
    """Israeli audience: remove Christmas / stocking-stuffer wording from Amazon titles."""
    t = XMAS.sub("", title)
    return re.sub(r"\s{2,}", " ", re.sub(r"[\s,|-]+$", "", t)).strip() or title


def caption(item, category):
    L = CONFIG["labels"]
    title = drop_christmas(item["title"] or "Amazon best seller")
    title_he = to_hebrew(short(title))
    item["title_he"] = title_he
    v = item.setdefault("variant", random.randrange(1000))  # same variant for both languages; stable on re-edits
    he = block(item, category["he"], title_he, L["he"], seasonal_lines(category["slug"], "he"), v)
    en = block(item, category["en"], title, L["en"], seasonal_lines(category["slug"], "en"), v)
    sep = pick(["〰️〰️〰️〰️〰️", "• • • • •", "➖➖➖➖➖", "✨✨✨"], v // 5)
    return he + f"\n\n{sep}\n\n" + en


def remember_post(item, category):
    """Save the post's details and product photo under data/ (used to make social videos)."""
    img_dir = ROOT / "data" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    try:
        if item.get("image"):
            r = requests.get(item["image"], timeout=30)
            if r.ok:
                (img_dir / f"{item['asin']}.jpg").write_bytes(r.content)
    except Exception as e:
        log(f"  (image save failed: {e})")
    log_file = ROOT / "data" / "posts.json"
    posts = json.loads(log_file.read_text()) if log_file.exists() else []
    posts.append({k: item.get(k, "") for k in ("asin", "title", "title_he", "price", "was", "discount", "rating", "reviews", "rank", "source", "message_id", "image", "variant")}
                 | {"category_slug": category["slug"], "category_en": category["en"], "category_he": category["he"],
                    "posted_at": now().isoformat()})
    posts = posts[-40:]
    keep = {p["asin"] for p in posts}
    for f in img_dir.glob("*.jpg"):
        if f.stem not in keep:
            f.unlink()
    log_file.write_text(json.dumps(posts, indent=1, ensure_ascii=False))


def send_telegram(item, category):
    """Post to the channel. Returns the Telegram message id (or True on a dry run), None on failure."""
    text = caption(item, category)
    if DRY_RUN:
        log("---- DRY RUN post ----\n" + text + f"\n[image] {item.get('image')}\n")
        return True
    api = f"https://api.telegram.org/bot{TG_TOKEN}"
    if item.get("image"):
        r = requests.post(f"{api}/sendPhoto", data={
            "chat_id": TG_CHAT, "photo": item["image"], "caption": text, "parse_mode": "HTML"}, timeout=30)
        if r.ok:
            return r.json()["result"]["message_id"]
        log(f"  photo post failed ({r.text[:150]}), sending as text")
    r = requests.post(f"{api}/sendMessage", data={
        "chat_id": TG_CHAT, "text": text, "parse_mode": "HTML"}, timeout=30)
    if not r.ok:
        log(f"  ! telegram error: {r.text[:300]}")
        return None
    return r.json()["result"]["message_id"]


# ---------------------------------------------------------------- main

def discount_pct(info):
    m = re.search(r"\d+", info.get("discount") or "")
    if m:
        return int(m.group())
    was, price = money(info.get("was")), money(info.get("price"))
    return round((1 - price / was) * 100) if was > price > 0 else 0


def arg(name, default=None):
    """--name value from the command line, else NAME env var, else default."""
    if f"--{name}" in sys.argv:
        return sys.argv[sys.argv.index(f"--{name}") + 1]
    return os.getenv(name.upper().replace("-", "_")) or default


def main():
    if "--test-telegram" in sys.argv:
        ok = send_telegram({"asin": "B0BSHF7WHW", "rank": 1, "title": "Test post from your deals bot",
                            "price": "$0.00", "image": ""}, {"slug": "test", "en": "Setup", "he": "בדיקה"})
        sys.exit(0 if ok else 1)

    if not DRY_RUN and not (TG_TOKEN and TG_CHAT):
        sys.exit("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (or set DRY_RUN=1)")

    state = load_state()
    cats = CONFIG["categories"]
    only = arg("category")              # e.g. --category toys-and-games for a one-off targeted post
    targeted = bool(only)
    min_discount = int(arg("min-discount", 0) or 0)
    max_posts = int(arg("max-posts", CONFIG["max_posts_per_run"]))
    budget = int(arg("check", 60 if targeted else CONFIG["checks_per_run"]))
    preferred = min_discount or CONFIG["preferred_discount"]

    if targeted:
        lists = [(c, "bestsellers", 1) for c in cats if c["slug"] == only] or \
                [({"slug": only, "en": only.replace("-", " ").title(), "he": only}, "bestsellers", 1)]
        c0 = lists[0][0]
        lists += [(c0, "bestsellers", 2), (c0, "movers-and-shakers", 1), (c0, "movers-and-shakers", 2)]
    else:
        # weighted random pick of lists; avoid the categories used in the last few runs
        recent = state.get("recent_categories", [])
        pool = [c for c in cats if c["slug"] not in recent] or cats
        order = []
        while pool and len(order) < CONFIG["max_lists_per_run"]:
            pick = random.choices(pool, weights=[c.get("weight", 1) for c in pool])[0]
            pool.remove(pick)
            order.append(pick)
        # half the time look at what's trending (Movers & Shakers) rather than plain best sellers
        lists = [(c, random.choice(["bestsellers", "bestsellers", "movers-and-shakers"]), 1) for c in order]

    amz = Amazon()
    posted_now = 0
    candidates = []
    brands = [b.lower() for b in CONFIG.get("brands", [])]

    today = datetime.now(timezone(timedelta(hours=2))).date().isoformat()
    discount_weight = max([p.get("discount_weight", 1) for p in CONFIG.get("promo_periods", [])
                           if p["from"] <= today <= p["to"]] or [1])

    def score(it, info):
        """Popularity first (best-seller rank, trending), then discount and known brands as bonuses."""
        title = (info.get("title") or it.get("title") or "").lower()
        branded = any(title.startswith(b) or f" {b} " in f" {title[:40]} " for b in brands)
        r = it.get("rank") or 99
        popularity = 40 if r <= 3 else 30 if r <= 10 else 20 if r <= 20 else 10
        trending = 15 if it.get("source") == "movers-and-shakers" else 0
        return popularity + trending + min(discount_pct(info), 50) * discount_weight + (15 if branded else 0)

    def post(it, info, category):
        nonlocal posted_now
        merged = {**it, **{k: v for k, v in info.items() if v}}
        if not merged.get("discount") and discount_pct(info):
            merged["discount"] = f"{discount_pct(info)}%"
        msg_id = send_telegram(merged, category)
        if msg_id:
            if not DRY_RUN:  # dry runs shouldn't stop the item being posted for real later
                state["posted"][it["asin"]] = now().isoformat()
                merged["message_id"] = msg_id
                remember_post(merged, category)
                state["recent_categories"] = (state.get("recent_categories", []) + [category["slug"]])[-4:]
            posted_now += 1
            time.sleep(3)

    try:
        log("Setting delivery location to Israel…")
        if not amz.set_location_israel():
            log("! Location not confirmed as Israel; items will only be posted if their page says FREE … Israel")

        for asin in filter(None, (arg("backfill", "") or "").split(",")):
            info = amz.product(asin.strip())
            item = {"asin": asin.strip(), "rank": 0, **{k: v for k, v in info.items() if v}}
            item["title_he"] = to_hebrew(short(item.get("title", "")))
            if not item.get("discount") and discount_pct(info):
                item["discount"] = f"{discount_pct(info)}%"
            remember_post(item, {"slug": "", "en": arg("backfill-category", ""), "he": arg("backfill-category-he", "")})
            log(f"  backfilled {asin}")
        if arg("backfill"):
            return

        checked = 0
        for category, kind, page in lists:
            if posted_now >= max_posts or checked >= budget:
                break
            try:
                items = amz.best_sellers(category["slug"], page, kind)
            except Blocked:
                raise
            except Exception as e:
                log(f"  ({category['slug']} {kind} p{page} failed: {e})")
                continue
            for i in items:
                i["source"] = kind
            log(f"\n[{category['en']} · {kind} p{page}] {len(items)} items")
            for it in items:
                if checked >= budget or posted_now >= max_posts:
                    break
                asin = it["asin"]
                if is_recent(state["posted"].get(asin, ""), CONFIG["repost_after_days"]):
                    continue
                if is_recent(state["not_free"].get(asin, ""), CONFIG["recheck_not_free_after_days"]):
                    continue
                checked += 1
                info = amz.product(asin)
                log(f"  #{it['rank']} {asin} shipping={info['shipping']} off={discount_pct(info)}%  {info['title'][:55]}")
                if info["shipping"] != "free":
                    if info["shipping"] in ("paid", "no"):
                        state["not_free"][asin] = now().isoformat()
                    continue
                if not info.get("price"):
                    log("     no price found, skipping")
                    continue
                if discount_pct(info) < min_discount:
                    continue
                if targeted and discount_pct(info) >= preferred:
                    post(it, info, category)          # targeted run: first match wins
                else:
                    candidates.append((score(it, info), it, info, category))
                    if len(candidates) >= CONFIG.get("candidates_per_run", 6):
                        break
            if len(candidates) >= CONFIG.get("candidates_per_run", 6):
                break

        # scheduled runs: post the highest-scoring free-shipping item (popularity, trending, discount, brand)
        if posted_now < max_posts and candidates and not targeted:
            candidates.sort(key=lambda c: -c[0])
            for sc, it, info, category in candidates[:3]:
                log(f"  candidate score={sc} #{it['rank']} {it.get('source')} off={discount_pct(info)}% {info['title'][:50]}")
            _, it, info, category = candidates[0]
            post(it, info, category)
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
