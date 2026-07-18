# ClimaPronto

Monitors AC availability at Italian retailers every 10 minutes, shows it on a
live website with a map, sells time-boxed restock alerts via Stripe (1 week
2,90 €, 1 month 5,90 €, 2 months 8,90 €), and emails buyers when their
product comes back in stock.

```
Oracle VM (or GitHub Actions)          GitHub repo                Netlify (site + functions)
┌──────────────────────────┐    ┌─────────────────────┐    ┌─────────────────────────┐
│ crawler.py every 10 min  │───▶│ data/stock.json     │───▶│ index.html reads it     │
│  · checks retailers      │    │ data/subscribers.json│◀──┼─ stripe-webhook.js      │
│  · diffs vs last state   │    │ (both committed back,│   │   writes new paid       │
│  · emails on restock ────┼─┐  │  same pattern as     │   │   subscribers here      │
└──────────────────────────┘ │  │  Laplace Apply)      │   │                         │
                             │  └─────────────────────┘    │ create-checkout-        │
                        Resend API                          │   session.js starts    │
                     (restock emails)                        │   Stripe Checkout      │
                                                              └──────────┬──────────────┘
                                                                         │
                                                                    Stripe Checkout
                                                          (buyer picks a plan and pays)
```

## Files

| File | What it does |
|---|---|
| `site/index.html` | The website: map, live board, link to the alert page |
| `site/avvisi.html` | Alert signup: pick a product + plan, starts Stripe Checkout |
| `site/grazie.html` | Thank-you page Stripe redirects to after payment |
| `netlify/functions/create-checkout-session.js` | Starts a Stripe Checkout session (called by the form) |
| `netlify/functions/stripe-webhook.js` | Confirms payment, writes the subscriber to GitHub |
| `netlify.toml` | Tells Netlify where the site and functions live |
| `crawler.py` | Main loop: check → diff → notify → save state |
| `retailers.py` | Product list + one checker function per retailer |
| `emailer.py` | Sends restock emails via Resend |
| `subscribers.py` | Reads `data/subscribers.json` (written by the webhook) |
| `run_and_push.sh` | Oracle VM cron entrypoint (pull, crawl, push) |
| `.github/workflows/crawl.yml` | Testing-phase runner (every 30 min) |
| `data/stock.json` | Published state — the website reads this |
| `data/subscribers.json` | Paid alert signups — written by the webhook, read by the crawler |
| `data/notify_log.json` | Who was emailed about what (dedup) |

## Go-live checklist, in order

### 1. Create the GitHub repo
Push everything (drag the whole `climapronto` folder onto
github.com → your repo → "Add file → Upload files" works fine, it accepts
nested folders in Chrome). Must be **public** — the website reads
`stock.json` from the raw GitHub URL, which requires public access.

### 2. Connect Netlify to that repo (not drag-and-drop this time)
Functions need a Git-connected deploy to work:
1. app.netlify.com → **Add new site → Import an existing project → GitHub**
   → pick the `climapronto` repo.
2. Build settings: leave build command empty, publish directory `site`
   (Netlify also auto-reads `netlify.toml`, which sets this already).
3. Deploy. You now get auto-deploys on every push, for free.
4. Note your site's URL (e.g. `https://climapronto.netlify.app`) — you'll
   need it in the next steps.

### 3. Stripe (payments)
1. Create a free account at stripe.com. Stay in **test mode** at first
   (toggle top-right) — test payments use fake card `4242 4242 4242 4242`,
   any future date, any CVC, no real money moves.
2. Developers → API keys → copy the **Secret key** (`sk_test_...`).
3. Netlify → Site settings → Environment variables → add:
   - `STRIPE_SECRET_KEY` = that secret key
   - `SITE_URL` = your Netlify URL from step 2.4
4. Developers → Webhooks → **Add endpoint**:
   - URL: `https://<your-site>.netlify.app/.netlify/functions/stripe-webhook`
   - Event: `checkout.session.completed`
   - Copy the **Signing secret** it gives you (`whsec_...`) →
     add as `STRIPE_WEBHOOK_SECRET` in Netlify env vars.
5. Trigger a redeploy (Netlify → Deploys → Trigger deploy) so the
   functions pick up the new env vars.

Test the whole payment loop: open your site → pick a product → pay with
the test card above → you should land on `grazie.html`, and a commit
called "alert paid: ..." should appear in `data/subscribers.json` in
your GitHub repo within a few seconds.

When ready for real money: flip Stripe out of test mode, replace
`STRIPE_SECRET_KEY` with the live key (`sk_live_...`), and repeat step 4
for a **live-mode** webhook (test and live webhooks are separate).

### 4. GitHub token (lets the webhook write to your repo)
1. GitHub → Settings → Developer settings → **Fine-grained tokens** →
   Generate new token.
2. Repository access: **Only** `climapronto`. Permissions: **Contents:
   Read and write**. Nothing else.
3. Netlify env vars → add:
   - `GITHUB_TOKEN` = the token
   - `GITHUB_REPO` = `sinaseyedi96-121/climapronto`
4. Trigger a redeploy again.

**This token is sensitive — never paste it back into a chat.** If it
ever ends up in a conversation or a public commit, revoke it immediately
from that same GitHub settings page and issue a new one.

### 5. Resend (restock emails)
1. Free account at resend.com → API Keys → create → copy.
2. While testing (no domain yet): emails can only go **from**
   `onboarding@resend.dev` **to your own account email** — sign up on
   Resend with the email you'll use to test.
3. Later, once you own a domain: Resend → Domains → add → set the DNS
   records shown → update `FROM_ADDRESS` in `emailer.py`.

### 6. Wire up the crawler → website connection
This is already built, just needs the right names:
1. In `site/index.html`, `DATA_URL` must point at your repo's raw
   `stock.json`. If your repo is `sinaseyedi96-121/climapronto` on the
   `main` branch, it's already correct.
2. In `emailer.py`, update `SITE_URL` to your real Netlify URL.

### 7a. Testing phase: GitHub Actions runs the crawler
Repo → Settings → Secrets and variables → Actions → add secret
`RESEND_API_KEY`. The included workflow runs every 30 minutes and commits
`data/stock.json` (and `data/notify_log.json`) back automatically.
**Reminder from Laplace: secret names must match exactly.**

### 7b. Production: move the crawler to the Oracle VM (real 10-min checks)
```bash
git clone https://github.com/sinaseyedi96-121/climapronto.git
cd climapronto
pip3 install -r requirements.txt --break-system-packages
cp .env.example .env && nano .env      # paste RESEND_API_KEY
chmod +x run_and_push.sh
git config credential.helper store     # first push asks for user + PAT once
crontab -e
# add:
# */10 * * * * /home/ubuntu/climapronto/run_and_push.sh >> /home/ubuntu/climapronto/cron.log 2>&1
```
Then disable the GitHub Actions workflow (Actions tab → Check stock → ⋯ →
Disable workflow) so the two runners don't both push at once.

### 8. Add real products
Ships with two DEMO products so the whole loop — including payment — is
testable today. To add a real one: DevTools → Network → Fetch/XHR on the
retailer's product page, find the stock request, plug it into the
`json_endpoint` checker in `retailers.py` (or send me the request as cURL
and I'll write the checker).

**Euronics is already wired up** as a real example (`euronics_stores` in
`retailers.py`): one API call to their store locator returns every
physical store nationwide (~244) with a genuinely independent in-stock
flag per store for the given product — verified by checking the same
product against multiple real stores and confirming the flag actually
differs between them (some true, some false), not one number echoed
everywhere.

Unieuro was tried first and rejected: their API only exposes a single
nationwide stock number per product, no per-store breakdown, which would
have meant painting the same status on every store pin — technically
real data, but not the "is it at the store near me" signal subscribers
are actually paying for. MediaWorld also has a genuine per-store
pickup-availability endpoint, but it's behind bot protection that blocks
plain server-side requests (would need real headless-browser automation
to use, not just `requests` calls) — skipped for now as not worth the
added fragility.

To add another retailer with genuine per-store data: write a function
that returns `[{"store", "city", "lat", "lon", "status"}, ...]` with a
REAL status per store (confirm it actually varies between stores before
trusting it!), register it in `STORE_CHECKERS` in `retailers.py`, and
set `"store_checker": "<name>"` on the product instead of `"checker"`.

## Testing the full loop end to end
1. Run the crawler once (baseline — never emails on the first run).
2. Pay for a demo product on your live site with the Stripe test card →
   confirm the commit lands in `data/subscribers.json`.
3. In `retailers.py`, flip that demo product's `simulate` to `"available"`.
4. Run the crawler again → restock detected → email sent to that subscriber.

## Current limits (fine for launch, revisit at scale)
- Resend free tier: 3,000 emails/month, 100/day.
- Netlify Functions free tier: 125,000 requests/month — effectively
  unlimited at this stage.
- The crawler and the webhook both commit to the same repo independently;
  at very high signup volume a rare git conflict is possible. Not a
  concern until you're seeing many purchases per minute.
- No refund automation — Stripe Dashboard → Payments handles refunds
  manually for now.
- No unsubscribe link in the restock email yet — worth adding before
  real volume (a `mailto:` link or a tiny Netlify function both work).
