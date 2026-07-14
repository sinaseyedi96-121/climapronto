"""
Retailer checkers
=================
One small function per retailer. Each returns one of:
  "available" | "out_of_stock" | "unknown"

HOW TO ADD A REAL RETAILER (the DevTools method):
  1. Open the product page (or the store-availability widget) in Chrome.
  2. DevTools -> Network tab -> filter "Fetch/XHR".
  3. Reload / type a postcode and watch which request returns the stock data.
  4. Right-click that request -> Copy -> Copy as cURL, and paste it to me:
     I'll convert it into a checker function here.
Most retailers fall into one of the two templates below (JSON endpoint,
or HTML page with a recognizable "add to cart" / "esaurito" marker).

PRODUCTS is the single list to edit when you add/remove monitored items.
"""

import re

import requests

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
REQUEST_TIMEOUT = 20  # seconds

# A realistic browser user-agent; many retailers reject the default
# python-requests one outright.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
}

# ----------------------------------------------------------------------
# THE PRODUCT LIST — this is what the crawler monitors.
#   id       : stable slug, used in state files and the signup form
#   name     : shown on the website
#   retailer : shown on the website
#   price    : optional, shown on the website (update manually or via checker)
#   url      : public product page (used in the email + website link)
#   checker  : which function below knows how to check it
#   checker_args : passed to the checker
# ----------------------------------------------------------------------
PRODUCTS = [
    # ---- DEMO ENTRIES: replace with real products once you have endpoints.
    # These use httpbin to simulate a JSON stock endpoint so you can test
    # the whole pipeline (crawl -> diff -> email) end to end today.
    {
        "id": "demo-pinguino",
        "name": "De'Longhi Pinguino PAC EL92 (DEMO)",
        "retailer": "Demo Store",
        "price": "499 €",
        "url": "https://example.com/pinguino",
        "checker": "demo_json",
        "checker_args": {"simulate": "available"},
        # Per-store availability shown on the website map.
        # For retailers with a store-availability endpoint, the checker can
        # fill/refresh these statuses; for online-only retailers, omit
        # "stores" and only the product-level status is shown.
        "stores": [
            {"store": "Demo Store Milano Centrale", "city": "Milano", "lat": 45.4642, "lon": 9.1900, "status": "available"},
            {"store": "Demo Store Torino Lingotto", "city": "Torino", "lat": 45.0703, "lon": 7.6869, "status": "available"},
            {"store": "Demo Store Roma Tiburtina", "city": "Roma", "lat": 41.9028, "lon": 12.4964, "status": "out_of_stock"},
            {"store": "Demo Store Bologna Fiera", "city": "Bologna", "lat": 44.4949, "lon": 11.3426, "status": "available"},
            {"store": "Demo Store Trento Nord", "city": "Trento", "lat": 46.0748, "lon": 11.1217, "status": "out_of_stock"},
        ],
    },
    {
        "id": "demo-comfee",
        "name": "Comfee CP12 Pro 12000 BTU (DEMO)",
        "retailer": "Demo Store",
        "price": "329 €",
        "url": "https://example.com/comfee",
        "checker": "demo_json",
        "checker_args": {"simulate": "out_of_stock"},
        "stores": [
            {"store": "Demo Store Napoli Centro", "city": "Napoli", "lat": 40.8518, "lon": 14.2681, "status": "out_of_stock"},
            {"store": "Demo Store Firenze Novoli", "city": "Firenze", "lat": 43.7696, "lon": 11.2558, "status": "out_of_stock"},
            {"store": "Demo Store Palermo Forum", "city": "Palermo", "lat": 38.1157, "lon": 13.3615, "status": "unknown"},
            {"store": "Demo Store Bari Santa Caterina", "city": "Bari", "lat": 41.1171, "lon": 16.8719, "status": "out_of_stock"},
            {"store": "Demo Store Verona Adigeo", "city": "Verona", "lat": 45.4384, "lon": 10.9916, "status": "available"},
        ],
    },

    # ---- REAL ENTRY TEMPLATE (uncomment and fill after the DevTools check):
    # {
    #     "id": "unieuro-pinguino-el92",
    #     "name": "De'Longhi Pinguino PAC EL92 Silent",
    #     "retailer": "Unieuro",
    #     "price": "549 €",
    #     "url": "https://www.unieuro.it/online/...product-page...",
    #     "checker": "json_endpoint",
    #     "checker_args": {
    #         "endpoint": "https://www.unieuro.it/...the-XHR-url-you-found...",
    #         # path into the JSON where availability lives, e.g. ["stock", "status"]
    #         "json_path": ["available"],
    #         # value(s) that mean "in stock"
    #         "available_values": [True, "AVAILABLE", "IN_STOCK"],
    #     },
    # },
]


# ----------------------------------------------------------------------
# CHECKER IMPLEMENTATIONS
# ----------------------------------------------------------------------

def demo_json(product: dict) -> str:
    """Test checker: returns the simulated status from checker_args, no
    network needed. Lets you exercise the full pipeline (crawl -> diff ->
    email) without any real retailer endpoint. To test the restock email:
    run once with simulate="out_of_stock", flip it to "available", run again."""
    return product["checker_args"]["simulate"]


def json_endpoint(product: dict) -> str:
    """Generic checker for retailers with a clean JSON stock endpoint
    (the thing you find in DevTools -> Network -> XHR)."""
    args = product["checker_args"]
    resp = requests.get(args["endpoint"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    # walk down the json_path, e.g. ["stock", "status"] -> data["stock"]["status"]
    value = data
    for key in args["json_path"]:
        if isinstance(value, list):
            value = value[int(key)]
        else:
            value = value.get(key)
        if value is None:
            return "unknown"

    return "available" if value in args["available_values"] else "out_of_stock"


def html_marker(product: dict) -> str:
    """Generic checker for retailers where the plain product page HTML
    (no JS needed) contains a recognizable marker string.
    Works surprisingly often: many sites render 'Aggiungi al carrello'
    vs 'Non disponibile' server-side even if the rest is a SPA."""
    args = product["checker_args"]
    resp = requests.get(product["url"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    html = resp.text

    if re.search(args["available_pattern"], html, re.IGNORECASE):
        return "available"
    if re.search(args["out_of_stock_pattern"], html, re.IGNORECASE):
        return "out_of_stock"
    return "unknown"


CHECKERS = {
    "demo_json": demo_json,
    "json_endpoint": json_endpoint,
    "html_marker": html_marker,
}


def check_product(product: dict) -> str:
    """Dispatch a product to its checker."""
    checker = CHECKERS.get(product["checker"])
    if checker is None:
        raise ValueError(f"Unknown checker '{product['checker']}' for {product['id']}")
    return checker(product)
