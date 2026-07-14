"""
ClimaPronto crawler
==================
Checks AC availability at Italian retailers, updates data/stock.json,
and emails subscribers when a product comes back in stock.

Runs every 10 minutes via cron on the Oracle VM (see README.md),
or on a schedule via GitHub Actions during testing.

Pipeline (same shape as Laplace Apply):
  fetch each product  ->  normalize  ->  diff vs previous state
  ->  on out_of_stock/unknown -> available transition: notify subscribers
  ->  save new state
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from retailers import check_product, PRODUCTS
from emailer import send_restock_email
from subscribers import get_subscribers

# ----------------------------------------------------------------------
# CONFIG — adjust here, nothing below should need editing
# ----------------------------------------------------------------------
DATA_DIR = Path(__file__).parent / "data"
STOCK_FILE = DATA_DIR / "stock.json"          # published state (the website reads this)
NOTIFY_LOG_FILE = DATA_DIR / "notify_log.json"  # who was emailed for what, to avoid duplicates

# Safety valve: never email the same subscriber about the same product
# more than once within this many hours (protects against flapping stock).
NOTIFY_COOLDOWN_HOURS = 12
# ----------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def hours_since(iso_ts: str) -> float:
    then = datetime.fromisoformat(iso_ts)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


def main() -> int:
    previous = load_json(STOCK_FILE, {"updated_at": None, "products": []})
    prev_status = {p["id"]: p.get("status", "unknown") for p in previous.get("products", [])}

    # ------------------------------------------------------------------
    # 1. Check every product
    # ------------------------------------------------------------------
    results = []
    for product in PRODUCTS:
        try:
            status = check_product(product)
        except Exception as e:  # one retailer failing must not kill the run
            print(f"[warn] check failed for {product['id']}: {e}")
            status = "unknown"
        results.append({**product, "status": status, "checked_at": now_iso()})
        print(f"[info] {product['id']}: {status}")

    # ------------------------------------------------------------------
    # 2. Find restocks (something that was NOT available is now available)
    # ------------------------------------------------------------------
    restocked = [
        p for p in results
        if p["status"] == "available" and prev_status.get(p["id"]) in ("out_of_stock", "unknown")
        # first run (product not in prev_status at all) does NOT count as a
        # restock — otherwise everyone gets emailed on day one.
        and p["id"] in prev_status
    ]

    # ------------------------------------------------------------------
    # 3. Notify subscribers
    # ------------------------------------------------------------------
    if restocked:
        notify_log = load_json(NOTIFY_LOG_FILE, {})
        try:
            subscribers = get_subscribers()
        except Exception as e:
            print(f"[error] could not fetch subscribers, skipping notifications: {e}")
            subscribers = []

        for product in restocked:
            for sub in subscribers:
                wants_it = sub["prodotto"] in ("qualsiasi", product["id"])
                if not wants_it:
                    continue
                log_key = f'{sub["email"]}::{product["id"]}'
                last = notify_log.get(log_key)
                if last and hours_since(last) < NOTIFY_COOLDOWN_HOURS:
                    continue
                try:
                    send_restock_email(sub["email"], product)
                    notify_log[log_key] = now_iso()
                    print(f"[info] emailed {sub['email']} about {product['id']}")
                except Exception as e:
                    print(f"[warn] email to {sub['email']} failed: {e}")

        save_json(NOTIFY_LOG_FILE, notify_log)

    # ------------------------------------------------------------------
    # 4. Publish new state (the website reads this file from GitHub raw)
    # ------------------------------------------------------------------
    save_json(STOCK_FILE, {"updated_at": now_iso(), "products": results})
    print(f"[info] wrote {STOCK_FILE} — {len(results)} products, {len(restocked)} restock(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
