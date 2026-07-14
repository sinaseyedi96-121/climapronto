"""
Subscribers
===========
Paid subscribers land here via a different path than the rest of the
pipeline: when someone pays through Stripe Checkout, the
`stripe-webhook` Netlify function (netlify/functions/stripe-webhook.js)
verifies the payment and appends them directly to data/subscribers.json
IN THE GITHUB REPO, using the GitHub API.

So by the time the crawler runs, subscribers.json is already sitting in
its own working copy of the repo — no API call needed here, just a read.
(run_and_push.sh does `git pull` before every run, so it's always current.)
"""

import json
from pathlib import Path

SUBSCRIBERS_FILE = Path(__file__).parent / "data" / "subscribers.json"


def get_subscribers() -> list[dict]:
    """Return [{'email': ..., 'prodotto': ..., 'paid_at': ...}, ...]."""
    if not SUBSCRIBERS_FILE.exists():
        return []
    with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
