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
OWNER_TEST = os.getenv("OWNER_TEST", "").lower() in ("1", "true", "yes")  # send test posts to Matt only
if OWNER_TEST:
    TG_CHAT = str(CONFIG.get("owner_chat_id", ""))
ALI_ON = bool(os.getenv("ALIEXPRESS_APP_KEY") and os.getenv("ALIEXPRESS_APP_SECRET"))
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

COLOR_SIZE = re.compile(r"\b(black|white|blue|red|green|pink|purple|grey|gray|denim|cherry|navy|beige|brown|gold|silver|"
                        r"rose|yellow|orange|teal|clear|small|medium|large|xl|xxl|xs|mini|kids|adult|men'?s|women'?s|"
                        r"\d+(\.\d+)?\s*(oz|ml|l|ft|in|inch|cm|mm|pack|pcs|count|ct|piece|pieces|pk)?)\b", re.I)


def title_family(title):
    """Rough product-family key from a title: same brand + product words, ignoring color/size/pack details."""
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", (title or "").lower())
    t = re.split(r"[,|]| - ", t)[0]
    t = COLOR_SIZE.sub(" ", t)
    words = re.findall(r"[a-z][a-z'&+-]*", t)
    return " ".join(words[:4])


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


CACHE_DIR = ROOT / ".cache"
COOKIES_F = CACHE_DIR / "amazon_cookies.json"
PRODUCTS_F = CACHE_DIR / "products.json"


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


class Amazon:
    def save_cookies(self):
        CACHE_DIR.mkdir(exist_ok=True)
        jar = [{"name": c.name, "value": c.value, "domain": c.domain} for c in self.s.cookies.jar]
        COOKIES_F.write_text(json.dumps(jar))

    def load_cookies(self):
        for c in load_json(COOKIES_F, []):
            self.s.cookies.set(c["name"], c["value"], domain=c["domain"])

    def location_is_israel(self):
        """Check the delivery location using a Best Sellers page (one request)."""
        page = self.get(BASE + "/gp/bestsellers/").text
        el = BeautifulSoup(page, "html.parser").select_one("#glow-ingress-line2")
        where = clean(el.get_text()) if el else "?"
        log(f"  saved session delivers to: {where}")
        return "israel" in where.lower()

    def __init__(self, impersonate="safari"):
        self.s = cffi_requests.Session(impersonate=impersonate)
        self.s.headers.update({"Accept-Language": "en-US,en;q=0.9"})
        # show prices in USD even with an Israeli delivery address
        self.s.cookies.set("i18n-prefs", "USD", domain=".amazon.com")
        self.requests_made = 0
        self.cache_hits = 0

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
        cache = load_json(PRODUCTS_F, {})
        hit = cache.get(asin)
        if hit and is_recent(hit.get("_at", ""), CONFIG.get("product_cache_hours", 6) / 24):
            self.cache_hits += 1
            return {k: v for k, v in hit.items() if k != "_at"}
        info = self._product(asin)
        if info["shipping"] in ("free", "paid", "no"):
            cache[asin] = {**info, "_at": now().isoformat()}
            cache = {a: v for a, v in cache.items() if is_recent(v.get("_at", ""), 1)}
            CACHE_DIR.mkdir(exist_ok=True)
            PRODUCTS_F.write_text(json.dumps(cache))
        return info

    def _product(self, asin):
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

        m = re.search(r'"parentAsin"\s*:\s*"([A-Z0-9]{10})"', page)
        return {
            "parent_asin": m.group(1) if m else "",
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
    ali = item.get("store") == "aliexpress"
    head = pick(L["ali_head"] if ali else L["trending"] if item.get("source") == "movers-and-shakers" else L["rank"], v)
    intro = pick(L.get("intro", [""]), v // 3)
    lines = ([intro, ""] if intro else []) + [f"🔥 {esc(head.format(rank=item['rank'], category=category, sold=item.get('sold', '')))}", "",
                                              f"<b>{esc(short(title))}</b>", ""]
    if item.get("price"):
        p = f"💰 <b>{esc(shekels(item['price']))}</b>"
        if item.get("was"):
            p += f"  <s>{esc(shekels(item['was']))}</s>"
        if item.get("discount"):
            p += f"  ({esc(item['discount'])} {L['off']})"
        lines.append(p)
    if item.get("rating"):
        star = "👍" if ali else "⭐"
        lines.append(f"{star} {esc(item['rating'])}" + (f" ({item['reviews']})" if item.get("reviews") else ""))
    lines.append(f"🇮🇱 {pick(L['ali_shipping'] if ali else L['free_shipping'], v // 2)}")
    if extra:
        lines += ["", *extra]
    url = item.get("link") or product_link(item["asin"])
    lines.append(f'👉 <a href="{esc(url)}">{pick(L["ali_view"] if ali else L["view"], v // 4)}</a>')
    return "\n".join(lines)


XMAS = re.compile(r"\s*[-,|]?\s*\b(?:(?:great |perfect |cool |unique )?(?:christmas|xmas|holiday) (?:gifts?|presents?)(?: (?:for|ideas?)[^,|]*)?|stocking stuffers?(?: for [^,|]*)?|christmas|xmas)\b", re.I)


def drop_christmas(title):
    """Israeli audience: remove Christmas / stocking-stuffer wording from Amazon titles."""
    t = XMAS.sub("", title)
    return re.sub(r"\s{2,}", " ", re.sub(r"[\s,|-]+$", "", t)).strip() or title


def caption(item, category):
    L = CONFIG["labels"]
    title = drop_christmas(item["title"] or "Best seller")
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
    posts.append({k: item.get(k, "") for k in ("asin", "title", "title_he", "price", "was", "discount", "rating", "reviews", "rank", "source", "message_id", "image", "variant", "store", "link", "sold")}
                 | {"category_slug": category["slug"], "category_en": category["en"], "category_he": category["he"],
                    "posted_at": now().isoformat()})
    posts = posts[-40:]
    keep = {p["asin"] for p in posts}
    for f in img_dir.glob("*.jpg"):
        if f.stem not in keep:
            f.unlink()
    log_file.write_text(json.dumps(posts, indent=1, ensure_ascii=False))


def is_big_deal(item):
    off = int(re.sub(r"\D", "", item.get("discount") or "") or 0)
    top = item.get("source") != "movers-and-shakers" and (item.get("rank") or 99) <= CONFIG.get("notify_max_rank", 3)
    return off >= CONFIG.get("notify_min_discount", 30) or top


def square_photo(url):
    """Download the product photo and center it on a white square, so Telegram shows it uncropped."""
    from io import BytesIO
    from PIL import Image
    try:
        im = Image.open(BytesIO(requests.get(url, timeout=30).content)).convert("RGB")
    except Exception as e:
        log(f"  (photo download failed: {e})")
        return None
    side = 1080
    im.thumbnail((side - 80, side - 80), Image.LANCZOS)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    buf = BytesIO()
    canvas.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def send_telegram(item, category):
    """Post to the channel. Returns the Telegram message id (or True on a dry run), None on failure."""
    text = caption(item, category)
    if DRY_RUN:
        log("---- DRY RUN post ----\n" + text + f"\n[image] {item.get('image')}\n")
        return True
    api = f"https://api.telegram.org/bot{TG_TOKEN}"
    if item.get("image"):
        photo = square_photo(item["image"])
        data = {"chat_id": TG_CHAT, "caption": text, "parse_mode": "HTML",
                "disable_notification": "false" if is_big_deal(item) else "true"}
        if photo:
            r = requests.post(f"{api}/sendPhoto", data=data, files={"photo": ("deal.jpg", photo, "image/jpeg")}, timeout=60)
        else:
            r = requests.post(f"{api}/sendPhoto", data={**data, "photo": item["image"]}, timeout=30)
        if r.ok:
            return r.json()["result"]["message_id"]
        log(f"  photo post failed ({r.text[:150]}), sending as text")
    r = requests.post(f"{api}/sendMessage", data={
        "chat_id": TG_CHAT, "text": text, "parse_mode": "HTML",
        "disable_notification": "false" if is_big_deal(item) else "true"}, timeout=30)
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


def over_cap(info):
    """Israel: personal imports above $75 pay VAT/customs, so skip anything priced above the cap."""
    return money(info.get("price")) > CONFIG.get("max_price_usd", 75)


def arg(name, default=None):
    """--name value from the command line, else NAME env var, else default."""
    if f"--{name}" in sys.argv:
        return sys.argv[sys.argv.index(f"--{name}") + 1]
    return os.getenv(name.upper().replace("-", "_")) or default


POOL_F = ROOT / "data" / "pool.json"


def pool_add(it, info, category):
    pool = load_json(POOL_F, {})
    pool[it["asin"]] = {"it": it, "info": info, "category": category, "at": now().isoformat()}
    POOL_F.write_text(json.dumps(pool, ensure_ascii=False))


def pool_fresh(state):
    pool = load_json(POOL_F, {})
    fams = state.get("families", {})
    out = []
    for a, v in pool.items():
        if not is_recent(v["at"], CONFIG.get("reserve_hours", 12) / 24) or state["posted"].get(a) or over_cap(v["info"]):
            continue
        fs = [f for f in (v["info"].get("parent_asin"), title_family(v["info"].get("title"))) if f]
        if any(is_recent(fams.get(f, ""), CONFIG["repost_after_days"]) for f in fs):
            continue
        out.append(v)
    return out


def pool_take(state, keyfn=None):
    """Best still-fresh reserve deal that hasn't been posted (same product family rule applies)."""
    pool = {a: v for a, v in load_json(POOL_F, {}).items()
            if is_recent(v["at"], CONFIG.get("reserve_hours", 12) / 24) and not state["posted"].get(a) and not over_cap(v["info"])}
    def ok(v):
        fams = [f for f in (v["info"].get("parent_asin"), title_family(v["info"].get("title"))) if f]
        return not any(is_recent(state.get("families", {}).get(f, ""), CONFIG["repost_after_days"]) for f in fams)
    choices = [v for v in pool.values() if ok(v) and not clashes(state, v["info"].get("title"))]
    POOL_F.write_text(json.dumps(pool, ensure_ascii=False))
    if not choices:
        return None
    best = max(choices, key=keyfn or (lambda v: (discount_pct(v["info"]), -(v["it"].get("rank") or 99))))
    pool.pop(best["it"]["asin"], None)
    POOL_F.write_text(json.dumps(pool, ensure_ascii=False))
    return best


# ---------------------------------------------------------------- aliexpress

# Family-friendly channel: never post adult, weapon, smoking/vape, drug or gambling items from AliExpress
ALI_BLOCK = re.compile(
    r"\b(sex\w*|adult|erotic\w*|lingerie|thong|g-?string|bdsm|fetish|bondage|nipple|vibrat\w*|dildo\w*|"
    r"masturbat\w*|condom\w*|lubric\w*|porn\w*|nude|naked|strip(?:per|tease)|seductive|18\+|"
    r"knife|knives|blade|dagger|machete|sword|gun|pistol|rifle|airsoft|ammo|bullet|holster|taser|stun|"
    r"pepper spray|brass knuckles?|baton|crossbow|slingshot|weapon\w*|tactical vest|"
    r"vape\w*|e-?cig\w*|cigarette\w*|hookah|shisha|bong|grinder|rolling paper|tobacco|smok(?:e|ing) pipe|"
    r"cannabis|weed|marijuana|420|kratom|gambling|casino|poker chips?|alcohol|beer|wine|vodka|whiskey|"
    r"tattoo|piercing|hair removal|breast|butt lift|slimming|diet pills?|fat burn\w*|weight loss|"
    r"halloween mask|skull|devil|satan\w*|zombie|blood|horror|creepy|scary|"
    # licensed characters / brands: on AliExpress these are almost always unofficial knockoffs
    r"fnaf|five nights?|freddy|huggy|poppy playtime|pok[eé]mon|pikachu|disney|marvel|spider-?man|avengers|"
    r"frozen|elsa|stitch|minnie|mickey|barbie|hello kitty|sanrio|kuromi|cinnamoroll|my melody|sonic|mario|"
    r"nintendo|minecraft|roblox|paw patrol|peppa|bluey|cocomelon|harry potter|star wars|naruto|anime|"
    r"labubu|squishmallows?|lego|nike|adidas|airpods?|stanley|owala|jellycat)\b", re.I)
ALI_BLOCK_CATS = re.compile(r"sex|adult|intimate|lingerie|underwear|tobacco|smok|cigarette|weapon|knife|knives|"
                            r"hunting|tattoo|novelty & special use", re.I)


def ali_ok(p):
    """Age-appropriate, popular, well-rated, under the price cap."""
    text = " ".join(str(p.get(k) or "") for k in ("product_title", "first_level_category_name", "second_level_category_name"))
    if ALI_BLOCK.search(text):
        return False
    cats = f"{p.get('first_level_category_name') or ''} {p.get('second_level_category_name') or ''}"
    if ALI_BLOCK_CATS.search(cats):
        return False
    price = money(p.get("target_sale_price"))
    if not price or price > CONFIG.get("max_price_usd", 75):
        return False
    title = (p.get("product_title") or "").lower()
    if price < CONFIG.get("ali_min_price_usd", 0) and not any(k in title for k in CONFIG.get("ali_min_price_exempt", [])):
        return False
    if int(p.get("lastest_volume") or 0) < CONFIG.get("ali_min_sold", 500):
        return False
    return money(p.get("evaluate_rate")) >= CONFIG.get("ali_min_rating_pct", 90)


def ali_pick(state):
    """Find one AliExpress deal: a random family-friendly search, best-selling first, not posted recently."""
    sys.path.insert(0, str(ROOT / "tools"))
    import aliexpress
    queries = CONFIG.get("ali_queries", [])
    tried = 0
    for q in random.choices(queries, weights=[x.get("weight", 1) for x in queries], k=min(4, len(queries))):
        tried += 1
        try:
            prods = aliexpress.search(keywords=q["q"], page=random.randint(1, 3), page_size=50)
        except Exception as e:
            log(f"  (AliExpress search '{q['q']}' failed: {e})")
            continue
        good = [p for p in prods if ali_ok(p)]
        if q.get("require"):  # brand searches: only that brand's own products, not "compatible with" items
            good = [p for p in good if q["require"] in (p.get("product_title") or "").lower()[:40]
                    and not re.search(r"\b(for|compatible)\b[^,]{0,25}" + re.escape(q["require"]), (p.get("product_title") or "").lower())]
        # most of the time prefer higher-value items ($25+) when the search has any
        dear = [p for p in good if money(p.get("target_sale_price")) >= CONFIG.get("preferred_min_price_usd", 25)]
        if dear and random.random() < CONFIG.get("higher_value_share", 0.6):
            good = dear
        log(f"[AliExpress · {q['q']}] {len(prods)} results, {len(good)} pass the filters")
        random.shuffle(good)
        good.sort(key=lambda p: -int(p.get("lastest_volume") or 0) * (1 + min(money(p.get("discount")), 60) / 100))
        for p in good[:15]:
            pid = f"ali-{p['product_id']}"
            fam = title_family(p.get("product_title"))
            if state["posted"].get(pid) or (fam and is_recent(state.get("families", {}).get(fam, ""), CONFIG["repost_after_days"])):
                continue
            if not p.get("promotion_link"):
                continue
            if clashes(state, p.get("product_title")):
                continue
            sold = int(p.get("lastest_volume") or 0)
            was = p.get("target_original_price")
            info = {"title": clean(p.get("product_title")), "price": f"${money(p.get('target_sale_price')):.2f}",
                    "was": f"${money(was):.2f}" if money(was) > money(p.get("target_sale_price")) else "",
                    "discount": p.get("discount") if money(p.get("discount")) >= 5 else "",
                    "rating": p.get("evaluate_rate") or "", "image": p.get("product_main_image_url"),
                    "link": p["promotion_link"], "store": "aliexpress",
                    "sold": f"{sold // 1000},000" if sold >= 1000 else str(sold)}
            it = {"asin": pid, "rank": 0, "source": "aliexpress", "store": "aliexpress"}
            return it, info, {"slug": f"aliexpress/{q['q']}", "en": q["en"], "he": q["he"]}
    log(f"  no new AliExpress deal found in {tried} searches")
    return None


# ---------------------------------------------------------------- shekels

FX_F = ROOT / "data" / "fx.json"
_fx = {}


def usd_ils():
    """Today's USD->ILS rate (ECB via frankfurter, cached daily in data/fx.json). None if unknown."""
    if "rate" in _fx:
        return _fx["rate"]
    cached = load_json(FX_F, {})
    today = datetime.now(timezone.utc).date().isoformat()
    rate = cached.get("rate") if cached.get("date") == today else None
    if not rate:
        for url in ("https://api.frankfurter.app/latest?from=USD&to=ILS", "https://open.er-api.com/v6/latest/USD"):
            try:
                j = requests.get(url, timeout=15).json()
                rate = float((j.get("rates") or {}).get("ILS") or 0) or None
                if rate:
                    FX_F.write_text(json.dumps({"date": today, "rate": rate}))
                    break
            except Exception as e:
                log(f"  (exchange rate from {url.split('/')[2]} failed: {e})")
        if not rate and is_recent(cached.get("date", "") + "T00:00:00+00:00" if cached.get("date") else "", 7):
            rate = cached.get("rate")
    _fx["rate"] = rate
    return rate


def shekels(text):
    """'$12.99' -> '~₪47'. Leaves the text as is if it isn't dollars or the rate is unknown."""
    if not text or "$" not in text:
        return text
    usd, rate = money(text), usd_ils()
    if not usd or not rate:
        return text
    return f"~₪{round(usd * rate):,}"


# ---------------------------------------------------------------- variety

def product_type(title):
    t = f" {(title or '').lower()} "
    for k in CONFIG.get("product_types", []):  # list order matters: specific before generic
        if re.search(r"[\s\W]" + re.escape(k), t):
            return k
    return None


def brand_of(title):
    t = (title or "").lower()
    for b in CONFIG.get("brands", []):
        if t.startswith(b.lower() + " ") or f" {b.lower()} " in f" {t[:40]} ":
            return b.lower()
    return None


def clashes(state, title):
    """Variety across BOTH stores: no same product type in the last few posts, no same brand back to back."""
    if "recent_titles" not in state:  # first run with this rule: start from the posts log
        state["recent_titles"] = [x.get("title", "") for x in load_json(ROOT / "data" / "posts.json", [])][-12:]
    recent = state["recent_titles"]
    typ, brand = product_type(title), brand_of(title)
    if typ and typ in [product_type(x) for x in recent[-CONFIG.get("diversity_posts", 6):]]:
        return f"another {typ} was posted recently"
    if brand and brand in [brand_of(x) for x in recent[-CONFIG.get("brand_gap_posts", 4):]]:
        return f"{brand} was posted recently"
    return None


def israel_now():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Jerusalem"))


def post_due(state):
    """Spread ~posts_per_day posts evenly across the posting window. The trigger fires every 15 minutes."""
    if arg("category") or arg("force") or DRY_RUN or OWNER_TEST:
        return True
    local = israel_now()
    start, end = CONFIG.get("post_window", [7, 23])
    if not (start <= local.hour < end):
        log(f"Outside posting hours ({start}:00-{end}:00 Israel), nothing to do")
        return False
    per_day = CONFIG.get("posts_per_day", 20)
    today = local.date().isoformat()
    if state.get("day_counts", {}).get(today, 0) >= per_day:
        log("Daily post limit reached")
        return False
    gap = (end - start) * 60 / per_day
    last = state.get("last_post_at")
    if last and (now() - datetime.fromisoformat(last)).total_seconds() / 60 < gap - 8:
        log(f"Last post was less than {gap:.0f} minutes ago, waiting")
        return False
    if state.get("blocked_until", "") > now().isoformat():
        log(f"Amazon cooldown until {state['blocked_until'][11:16]} UTC: posting from the reserve instead")
        return "reserve"
    return True


def main():
    if "--test-telegram" in sys.argv:
        ok = send_telegram({"asin": "B0BSHF7WHW", "rank": 1, "title": "Test post from your deals bot",
                            "price": "$0.00", "image": ""}, {"slug": "test", "en": "Setup", "he": "בדיקה"})
        sys.exit(0 if ok else 1)

    if not DRY_RUN and not (TG_TOKEN and TG_CHAT):
        sys.exit("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (or set DRY_RUN=1)")

    state = load_state()
    due = post_due(state)
    if not due:
        return
    cats = CONFIG["categories"]
    only = arg("category")              # e.g. --category toys-and-games for a one-off targeted post
    keyword = (arg("keyword") or "").lower()  # e.g. --keyword lego: only items whose title contains it
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

    amz = None
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
        boost = sum(v for k, v in CONFIG.get("boost_keywords", {}).items() if k in title)
        pr = money(info.get("price"))
        value = CONFIG.get("higher_value_bonus", 25) if pr >= CONFIG.get("preferred_min_price_usd", 25) else \
            CONFIG.get("higher_value_bonus", 25) // 2 if pr >= 15 else 0
        return popularity + trending + min(discount_pct(info), 50) * discount_weight + (15 if branded else 0) + boost + value

    def post(it, info, category):
        nonlocal posted_now
        merged = {**it, **{k: v for k, v in info.items() if v}}
        if not merged.get("discount") and discount_pct(info):
            merged["discount"] = f"{discount_pct(info)}%"
        msg_id = send_telegram(merged, category)
        if msg_id:
            if not DRY_RUN and not OWNER_TEST:  # dry/test runs shouldn't stop the item being posted for real later
                state["posted"][it["asin"]] = now().isoformat()
                merged["message_id"] = msg_id
                remember_post(merged, category)
                state["last_post_at"] = now().isoformat()
                pool = load_json(POOL_F, {})
                if pool.pop(it["asin"], None):
                    POOL_F.write_text(json.dumps(pool, ensure_ascii=False))
                for f in (info.get("parent_asin"), title_family(info.get("title"))):
                    if f:
                        state.setdefault("families", {})[f] = now().isoformat()
                today = israel_now().date().isoformat()
                state["day_counts"] = {today: state.get("day_counts", {}).get(today, 0) + 1}
                state["recent_categories"] = (state.get("recent_categories", []) + [category["slug"]])[-4:]
                state["recent_titles"] = (state.get("recent_titles", []) + [merged.get("title") or ""])[-12:]
                if it.get("store") != "aliexpress":
                    state["since_ali"] = state.get("since_ali", 0) + 1
            posted_now += 1
            time.sleep(3)

    def post_ali(reason):
        if not ALI_ON:
            return False
        try:
            found = ali_pick(state)
        except Exception as e:
            log(f"  (AliExpress failed: {e})")
            return False
        if not found:
            return False
        it, info, category = found
        log(f"{reason}: posting AliExpress deal {info['price']} sold {info['sold']} {info['title'][:50]}")
        before = posted_now
        post(it, info, category)
        if OWNER_TEST:
            state["posted"][it["asin"]] = now().isoformat()  # in memory only, so the 2nd test is a different item
        if posted_now > before and not DRY_RUN and not OWNER_TEST:
            state["since_ali"] = 0
        return posted_now > before

    def post_reserve(reason):
        v = pool_take(state, lambda v: score(v["it"], v["info"]))
        if v:
            log(f"{reason}: posting reserve deal {v['it']['asin']} {v['info']['title'][:50]}")
            post(v["it"], v["info"], v["category"])
        else:
            log(f"{reason}: reserve is empty")
            post_ali(f"{reason} (Amazon stock empty)")

    if OWNER_TEST:
        for i in range(int(arg("max-posts", 2) or 2)):
            post_ali(f"Owner test {i + 1}")
        return

    # Mix: every Nth post comes from AliExpress (falls back to Amazon if nothing suitable is found)
    every = CONFIG.get("aliexpress_every", 3)
    if not targeted and ALI_ON and (arg("store") == "aliexpress" or state.get("since_ali", 0) >= every - 1):
        if post_ali("AliExpress turn"):
            save_state(state)
            return

    if due == "reserve":
        post_reserve("Amazon cooldown")
        save_state(state)
        return

    # Collect-then-post: check Amazon only every few hours (a bigger batch), post from the stock in between
    harvest = targeted
    if not targeted:
        stock = len(pool_fresh(state))
        last_h = state.get("last_harvest_at", "")
        if stock >= CONFIG.get("reserve_min", 3) and is_recent(last_h, CONFIG.get("harvest_every_hours", 4) / 24):
            log(f"{stock} deals in stock (last Amazon check {last_h[11:16]} UTC): posting from stock")
            post_reserve("Stock")
            save_state(state)
            return
        harvest = True
        budget = int(arg("check", CONFIG.get("harvest_checks", 30)))
        log(f"Stock is {stock}: checking Amazon for new deals (up to {budget} products)")
        lists = lists + [(c, random.choice(["bestsellers", "movers-and-shakers"]), 1)
                         for c in random.choices(cats, weights=[c.get("weight", 1) for c in cats],
                                                 k=CONFIG.get("harvest_extra_lists", 3))]

    try:
        log("Setting delivery location to Israel…")
        amz = Amazon("safari")
        amz.load_cookies()
        reused = COOKIES_F.exists() and amz.location_is_israel()
        for attempt, profile in enumerate([] if reused else ["safari", "chrome", "safari"], 1):
            amz = Amazon(profile)
            if amz.set_location_israel():
                break
            log(f"  attempt {attempt}: location not set to Israel yet")
            time.sleep(5)
        else:
            if not reused:
                log("! Couldn't set delivery to Israel this run")
                post_reserve("No Israel location")
                save_state(state)
                return
        amz.save_cookies()

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
                if keyword and keyword not in (it.get("title") or "").lower():
                    continue
                asin = it["asin"]
                low_t = (it.get("title") or "").lower()
                days = min([d for k, d in CONFIG.get("repost_days_override", {}).items() if k in low_t] or [CONFIG["repost_after_days"]])
                if is_recent(state["posted"].get(asin, ""), days):
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
                if over_cap(info):
                    log(f"     {info['price']} is over the ${CONFIG.get('max_price_usd', 75)} cap, skipping")
                    continue
                fams = [f for f in (info.get("parent_asin"), title_family(info.get("title"))) if f]
                low = (info.get("title") or "").lower()
                days = min([d for k, d in CONFIG.get("repost_days_override", {}).items() if k in low] or [CONFIG["repost_after_days"]])
                if any(is_recent(state.get("families", {}).get(f, ""), days) for f in fams):
                    log("     same product (other color/size) was posted recently, skipping")
                    continue
                if discount_pct(info) < min_discount:
                    continue
                if targeted and discount_pct(info) >= preferred:
                    post(it, info, category)          # targeted run: first match wins
                else:
                    candidates.append((score(it, info), it, info, category))
                    pool_add(it, info, category)
                    if len(candidates) >= CONFIG.get("harvest_target", 25):
                        break
            if len(candidates) >= CONFIG.get("harvest_target", 25):
                break
        if not targeted:
            state["last_harvest_at"] = now().isoformat()
            log(f"\nStocked {len(candidates)} deal(s); {len(pool_fresh(state))} in stock")

        # scheduled runs: post the highest-scoring free-shipping item (popularity, trending, discount, brand)
        if posted_now < max_posts and candidates and not targeted:
            candidates.sort(key=lambda c: -c[0])
            for sc, it, info, category in candidates[:3]:
                log(f"  candidate score={sc} #{it['rank']} {it.get('source')} off={discount_pct(info)}% {info['title'][:50]}")
            varied = [c for c in candidates if not clashes(state, c[2].get("title"))]
            if varied:
                _, it, info, category = varied[0]
                post(it, info, category)
            else:
                log("  every candidate repeats a recent product type/brand; posting from stock instead")
                post_reserve("Variety")
    except Blocked as e:
        mins = CONFIG.get("block_cooldown_minutes", 60)
        log(f"\n! Amazon showed a robot check ({e}). Pausing Amazon requests for {mins} minutes.")
        state["blocked_until"] = (now() + timedelta(minutes=mins)).isoformat()
        if posted_now == 0 and not targeted:
            post_reserve("Blocked")
        save_state(state)
        return
    finally:
        # forget very old entries so the state file stays small
        for key, days in (("posted", 60), ("not_free", 30), ("families", 30)):
            state[key] = {a: t for a, t in state.get(key, {}).items() if is_recent(t, days)}
        save_state(state)

    if amz:
        amz.save_cookies()
    log(f"\nDone. Posted {posted_now} item(s). {amz.requests_made if amz else 0} Amazon requests"
        f" ({amz.cache_hits if amz else 0} products from cache).")


if __name__ == "__main__":
    main()
