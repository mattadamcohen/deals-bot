# Amazon → Telegram deals bot (free shipping to Israel)

Every hour (about 07:00–22:00 Israel time) this bot does the following:
- goes through Amazon.com Best Sellers, 3 categories per run, covering all 25 every ~8 hours
- opens the top items with the delivery location set to **Israel**
- keeps only items whose page shows **FREE delivery to Israel** (orders over $49)
- posts them to your Telegram channel with photo, price, discount, rating and link
- never posts the same item twice within 14 days

## Setup (about 10 minutes)

1. **Create the bot:** in Telegram, message **@BotFather** → `/newbot` → copy the token.
2. **Create the channel:** make it public (e.g. `@il_amazon_deals`), then add your bot as an **admin** with permission to post.
3. **Add this code to a GitHub repo.** Private works fine: a run takes about 2 minutes, which keeps you within the free Actions minutes.
4. In the repo, go to **Settings → Secrets and variables → Actions** and add:
   - Secret `TELEGRAM_BOT_TOKEN` = the BotFather token
   - Secret `TELEGRAM_CHAT_ID` = `@your_channel_name`
   - *(optional)* Variable `AMAZON_TAG` = your Amazon Associates tag (e.g. `matt-20`)
5. Go to **Actions → Amazon deals bot → Run workflow**:
   - first tick **test_telegram**, which sends a test post
   - then tick **dry_run**, which shows what it would post in the run log
   - then run it normally. After that it runs every hour by itself.

## Tuning (`config.json`)
| Setting | What it does |
|---|---|
| `categories` | Amazon Best Sellers category slugs (from `amazon.com/gp/bestsellers/<slug>`) |
| `categories_per_run` / `items_to_check_per_category` | How much it reads per hour. Higher means more posts, but Amazon is more likely to block it |
| `max_posts_per_run` | Cap on posts per hour, so the channel isn't spammed |
| `labels` | Post wording. You can change these to Hebrew |

## If something breaks
- **Run log says "Amazon blocked this run":** Amazon showed a robot check. One-off blocks are normal, and the next hour usually works. If it happens every time, lower `categories_per_run`.
- **0 items found or shipping=unknown:** Amazon changed its page layout. Download the run's **debug-pages** artifact and share it so the parsing can be fixed.

## Notes
- Free shipping to Israel needs a cart of **$49+ of eligible items**, and eligibility can differ by size or color.
- If you use an Amazon Associates tag, Amazon requires a disclosure. Put "As an Amazon Associate I earn from qualifying purchases" in the channel description.
- Amazon's official product API (Creators API) is only for Associates accounts that already have sales. Once you qualify, the bot can switch to it for more reliable data.
