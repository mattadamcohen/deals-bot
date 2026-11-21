# IL Deals bot: handoff for a new chat (as of 21 Nov 2026)

Paste or attach this file at the start of a new chat. It covers what exists, how it runs, Matt's rules and what is still open.

## 1. What this is
Matt (Ra'anana, Israel) runs a fully automated deals business called **IL Deals**.
- **Telegram channel:** @ilamazondeals (t.me/ilamazondeals), titled "Top Amazon & AliExpress". Posts go out through the bot **@ILAmazonbot**. About 11 subscribers so far.
- **Instagram:** @ilamazondeals (IG user id 17841425400607402, Graph API v23.0).
- **Amazon Associates tag:** `ilamazondeals-20`. **AliExpress affiliate tracking ID:** `ilamazondeals` (AliExpress Open Platform app is approved; product.query, productdetail, featuredpromo, link.generate and order.list all work. hotproduct needs separate approval).
- **Post language:** Hebrew first, then English. Prices are shown in shekels (~₪, from a daily FX rate cached in data/fx.json; it was 3.3428 on Nov 21).
- **Code:** public GitHub repo **mattadamcohen/deals-bot** (Python). It runs on GitHub Actions, triggered by cron-job.org (deals runs, plus an ig-dm job every 15 minutes that also kicks off deals.yml).
- **Restore points:** listed in docs/RESTORE_POINTS.md. `d2950c7` is from before the 11 new categories; `4ead040` is from before the Nov 20 category broadening.

## 2. Security rules (always)
- Never paste tokens or secrets in chat. Secrets live only in GitHub secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, IG_ACCESS_TOKEN, ALIEXPRESS_APP_KEY, ALIEXPRESS_APP_SECRET. The tracking ID can be shared.
- Never use Matt's full name in public materials. The giveaway rules say "מפעיל ערוץ IL Deals".
- Show Matt a draft before posting new ad or promo creatives. Ask before deleting anything that wasn't explicitly requested.

## 3. Matt's content rules
- **Volume:** about 30 Telegram posts a day, 07:00 to 23:00 Israel time, including Shabbat. About half from AliExpress (aliexpress_every 2).
- **Price cap:** $75 max (max_price_usd). Matt can approve specific items over the cap (for example SVBONY binoculars, a go-kart). He said he does NOT want the cap raised.
- **AliExpress:** $5 minimum (squishies, fidgets and stress balls are exempt). Min 500 sold (200 for squishies), rating at least 90%. Age-appropriate only. **No knockoffs** of licensed characters or brands (Disney, Pokémon, LEGO, Labubu, UNO, Hot Wheels, Nike and so on); those are allowed only from that brand's official store, and only for its own characters.
- **Value and quality:** prefer higher-value items ($25 and up) and quality brands (brand_bonus 35). **No** niche parts, filters (fridge water filters were blocked twice) or device-specific accessories (bands, cases, refills).
- **Variety:**
  - Never post two similar items in a row. Rotate themes: kids, fashion, tech, home, kitchen, beauty, sport.
  - No product type repeats within 48 hours. Theme gap of 2 posts, store-group gap of 2, brand gap of 4.
  - Weekly caps: bras/underwear 1 a week, batteries 1 a week, cables/chargers 1 a day, power banks 1 every 2 days.
  - Less bedding and linen. **No ties.** Never use "dropshipping" or other seller junk words in posts (strip_junk handles this).
- **Format:** posts are 3-photo albums, plus the product video when one exists. Use the wording "משלוח לארץ".
- **Coupons:** at most one coupon post a day. Matt said to skip AliExpress Black Friday codes for now.
- **Bundle post:** every 3 days at about 16:00, 3 cheap top-rated Amazon add-ons ($6–18) pitched as "cart fillers to reach $49 for free shipping".
- **Matt's own picks:** he sends them to the bot. They are queued ONLY if the message includes "פרסם" or "post". Forwarded messages are ignored, and nothing is reposted within 7 days. A screenshot is never treated as a pick unless he says so explicitly. Scheduled picks live in config `scheduled_picks`.
- **Steam cleaner (110V, US plug) was posted.** It doesn't work on Israel's 230V power. I suggested deleting it; Matt hasn't decided yet.

## 4. Instagram rules
- At most 4 posts a day.
- **Reels** at 10:30 and 18:00, 6 items each, alternating the gift-box style (box shakes, lid pops, items fly out) with the classic style. Covers are chosen through thumb_offset.
- **Product-video posts** at 14:00 and 21:00 (title banner and price overlay, from deals posted with a video in the last 36 hours).
- **Carousel** every 3 days in the 14:00 slot (it replaces the video post that day).
- IG pickers exclude AliExpress items for reels and carousels.
- **Every IG post gets a links comment.** Comments must be short: **use short AliExpress links** (aliexpress.link() gives s.click.aliexpress.com/e/_xxx) and **one comment per product**, because IG rejects long comments. Fallback: links in the caption (ig_links_in_caption). Captions also send people to t.me/ilamazondeals and the bio link. The "comment לינק" DM flow runs in ig_dm.py.
- The API can't pin posts; Matt pins manually.
- **Posted Nov 21:**
  - A 3-tile "WELCOME TO THE HOTTEST DEALS" grid banner (grid_3, grid_2, grid_1; 4:5 with a 34px overlap so the 3:4 grid crop lines up). Matt needs to unpin the 2 giveaway posts and pin right, middle, left. He may wait until the giveaway ends.
  - The "DEAL CITY: בית וטק" post (instagram.com/p/DgANM0XklkF).
  - The "DEAL CITY: מתנות לחנוכה" post (out/dealcity_gifts.jpg) is ready, but Matt hasn't asked for it to be posted.

## 5. Giveaway
$50 Amazon gift card. Runs Nov 18 to 30, drawn automatically Dec 1 at 12:00. Entry is by joining the channel (chat_member) or tapping the pinned button (t.me/ILAmazonbot?start=giveaway); the bot checks membership. Pinned announcement is message 207. Rules are in data/giveaway/. There were 3 entries as of Nov 18.

## 6. Affiliate results (as of Nov 21)
- **AliExpress:** 1 order, 2 items (squishy $5.11 + Needoh $4.60), Nov 18, about $0.67 commission. Probably Matt's own order.
- **Amazon:** there's no API. Matt checks Associates Central → Reports. He doesn't want a daily report yet.

## 7. How to operate (from the sandbox)
- Clone the repo; Claude works in /home/claude/deals-bot-repo. Commit with `git pull --rebase -X theirs` and then push.
- `gh workflow run` doesn't work here. Dispatch with:
  `gh api -X POST repos/mattadamcohen/deals-bot/actions/workflows/<wf>.yml/dispatches -f ref=main -f 'inputs[x]=y'`
- Logs: `gh run view <id> -R mattadamcohen/deals-bot --log`.
- All workflows check out `ref: main`.
- The sandbox can't reach the Amazon or AliExpress CDNs, so images are downloaded through **fetch-urls.yml** (inputs `pairs` = "name=url …", saved into data/ad/).
- **Workflows:**
  - deals.yml: the main run. Its steps are posting, scheduled one-offs, reels, video posts and the carousel.
  - ig-dm.yml: DMs, every 15 minutes.
  - channel.yml: description, title, photo, pin, repin, delete IDs, giveaway.
  - aliexpress-test.yml: keywords=sale runs tools/sale_probe.py, which reports orders.
  - ig-check.yml: lists recent IG media and comments.
  - tg-scrape.yml: reads a public channel's recent posts via t.me/s/.
  - probe.yml: tests Amazon best-seller lists.
  - ad-assets.yml: AliExpress images by query.
  - fetch-urls.yml: images by URL.
- **One-off scheduled jobs:** config `scheduled` → tools/scheduled.py, with done IDs in data/scheduled.json. Kinds:
  - tg_giveaway
  - ig_image: image, caption_file, optional link_asins for per-item short-link comments
  - ig_comment: media, optional link_asins
  - ig_delete_comments
- **Key files:**
  - bot.py: picking, filters, captions, inbox, giveaway, coupon and bundle posts.
  - config.json: 65 Amazon best-seller lists, 164 AliExpress queries, caps, blocks, slots.
  - data/posts.json: the last 40 posts with title_he, price, link, image, message_id and album_ids.
  - data/state.json, data/pool.json (reserve pool).
  - tools/reel.py, tools/giftbox.py, tools/video_post.py, tools/ig_post.py, tools/aliexpress.py.

## 8. Design styles Matt likes
- **Party/balloons** (Keflipo-style): sky-to-orange gradient, string lights, balloons, confetti, bubbly gradient titles.
- **Blue confetti** (Israir-style): deep blue, orange border, streamers, chrome "CRAZY Deals!".
- **Neon** (BUG-style).
  - Helpers for these three: tools/promo2.py (fancy_text, neon, gradient, confetti, circle_photo, logo).
- **"DEAL CITY"** (GTA-6 *vibe*, but no GTA logo, name or characters): sunset gradient, striped retro sun, skyline, palm silhouettes, Anton and Bebas Neue fonts (assets/fonts), black-gutter panel collage, pink ₪ price stickers, Hebrew name tags, and a "JOIN THE CREW" CTA bar. Code: tools/dealcity.py (`--posts` builds the home and gifts posts; functions title_panel, product_post, photo_contain, price_sticker). Matt likes it with **fewer items (4–5) so it isn't busy**.
- **Grid banner:** tools/grid_banner.py.
- **Gift-box reel:** tools/giftbox.py.
- **Classic reel:** tools/reel.py.
- **Fonts:** Heebo for Hebrew (raqm RTL). Use the logo at assets/ilamazondeals-logo.png. Brand colors are blue and yellow, with pink and orange accents.
- **Print:**
  - tools/flyer.py: black-and-white A4 tear-off poster and sticker sheet, using Matt's exact QR (cropped from his image) that points to t.me/ilamazondeals.
  - tools/flyer_color.py: color party and blue-confetti flyers, A4 and A5.
  - Text on both: "Hottest Amazon & AliExpress Deals" / "Free shipping deals to Israel" / "Join our Telegram community now!".
  - Verify QR codes with the OpenCV WeChat decoder.
- **Matt's preferences:** honest assessments, light edits that keep his voice, no AI-style dashes in his copy.

## 9. Website (draft only, ON HOLD)
- A private preview artifact "IL Deals: website draft" (claude.ai/artifact/Fc4WQweTfbpL3zheF7sXme). Template in site/template.html.
- Hebrew RTL, mobile-first. Search, category chips with counts, an All / Amazon / AliExpress toggle and sorting. Cards show a store badge, discount, "חדש היום", ₪ price and was-price, rating and sold count, "משלוח לארץ" and an orange "לצפייה בדיל" affiliate button. A Telegram banner sits after 8 cards; the footer has the affiliate disclosure (the Amazon Associates line is required).
- **Plan when Matt says go:** GitHub Pages first (or a custom domain later). The bot writes each Telegram post to the site data in the same run, using the same affiliate links. Deleted Telegram posts are removed from the site. Deals expire after about 14 days, with an optional daily price check. **Don't build until Matt asks.**

## 10. Open items and ideas waiting on Matt
- iHerb affiliate program through Awin ("iHerb ROW"). Matt would sign up and add an Awin token secret; then add iHerb as a third store at about 1 in 6–8 posts, with no health claims and Israeli customs limits in mind (15 supplement items per order).
- Facebook Page and TikTok setup: Matt needs to provide the Page name and create a TikTok business account. He wants to approve before anything goes live.
- Which Black Friday promo style to post (party, confetti or neon); a Hanukkah gift-box version; a gift-angle line in captions.
- Pin the grid banner (see section 4).
- Decide on the 110V steam cleaner post.
- Instagram unfollowing: only possible through the browser, not the API.
