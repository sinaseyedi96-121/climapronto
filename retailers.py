"""
Retailer checkers
=================
Two kinds of checker, set via one of these keys on a PRODUCTS entry:
  "checker"       -> function(product) -> "available" | "out_of_stock" | "unknown"
                     One status for the whole product. Used for retailers
                     that don't expose per-store stock.
  "store_checker" -> function(product) -> list of
                     {"store", "city", "lat", "lon", "status"} with a REAL,
                     independently-verified status per physical store. Used
                     for retailers whose stock API genuinely differs by
                     store (confirmed, not assumed — see EURONICS section:
                     Unieuro was tried first and rejected because it only
                     has one nationwide number, not per-store data).
                     crawler.py derives the product's overall status from
                     this list (available if any store has it).

HOW TO ADD A REAL RETAILER (the DevTools method):
  1. Open the product page (or the store-availability widget) in Chrome.
  2. DevTools -> Network tab -> filter "Fetch/XHR".
  3. Reload / type a postcode and watch which request returns the stock data.
  4. Right-click that request -> Copy -> Copy as cURL, and paste it to me:
     I'll convert it into a checker function here.
  5. If it looks like a per-store endpoint, verify it actually differs
     between two real stores for the same product before trusting it as
     a store_checker — some retailers echo one aggregate number under a
     misleadingly named "per-store" field.

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

    # ---- REAL ENTRIES: Euronics storefront API (see EURONICS section below).
    # Verified genuinely per-store: the same product's inventory.value came
    # back true at some real stores and false at others in the same query
    # (e.g. near Milano: true at Como/Tortona/Biella, false at 31 other
    # stores including the Milano city store itself) — not one number
    # copy-pasted everywhere. "store_checker": "euronics_stores" tells the
    # crawler to fetch that real per-store list (244 stores nationwide,
    # one API call, no auth) and derive the product's overall status from
    # it, instead of using a separate "checker".
    {
        "id": "euronics-argo-elite-plus",
        "name": "ARGO Condizionatore monoblocco Elite Plus Classe A",
        "retailer": "Euronics",
        "price": "424 €",
        "url": "https://www.euronics.it/elettrodomestici/trattamento-aria/condizionatori-portatili/argo---condizionatore-monoblocco-elite-plus-classe-a-bianco/242018027.html",
        "store_checker": "euronics_stores",
        "checker_args": {"pid": "242018027"},
    },
    {
        "id": "euronics-samsung-monosplit",
        "name": "SAMSUNG Kit F-AR 09M Climatizzatore monosplit",
        "retailer": "Euronics",
        "price": "299,99 €",
        "url": "https://www.euronics.it/elettrodomestici/trattamento-aria/condizionatori-fissi/samsung---kit-f-ar-09m-climatizzatore-monosplit/202002436.html",
        "store_checker": "euronics_stores",
        "checker_args": {"pid": "202002436"},
    },

    # ---- REAL ENTRY TEMPLATE (uncomment and fill after the DevTools check):
    # {
    #     "id": "retailer-product-slug",
    #     "name": "Product name",
    #     "retailer": "Retailer name",
    #     "price": "549 €",
    #     "url": "https://...product-page...",
    #     "checker": "json_endpoint",
    #     "checker_args": {
    #         "endpoint": "https://...the-XHR-url-you-found...",
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


# ----------------------------------------------------------------------
# EURONICS — real storefront API (the same one euronics.it's own frontend
# calls for its store locator). No auth needed. Genuinely per-store: the
# same "pid" query against this endpoint returns inventory.value=true for
# some stores and false for others (verified against two different real
# products, each with its own distinct pattern of which stores have it).
# ----------------------------------------------------------------------
EURONICS_STORES_URL = "https://www.euronics.it/on/demandware.store/Sites-euronics-Site/it_IT/Stores-Inventory"

# A center point + radius wide enough to cover all of Italy in one call
# (store count is stable from radius=500 through radius=5000 — i.e. this
# already returns every store nationwide, ~244 of them, not a partial
# radius-limited slice).
EURONICS_CENTER_LAT = 42.5
EURONICS_CENTER_LON = 12.5
EURONICS_RADIUS_KM = 1500


def euronics_stores(product: dict) -> list:
    """Real per-store checker for Euronics.it. One API call returns every
    physical store nationwide with a genuine in-stock boolean for this
    exact product — not an aggregate applied to every location."""
    args = product["checker_args"]
    resp = requests.get(
        EURONICS_STORES_URL,
        params={
            "lat": EURONICS_CENTER_LAT,
            "long": EURONICS_CENTER_LON,
            "radius": EURONICS_RADIUS_KM,
            "pid": args["pid"],
        },
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    stores = []
    for s in resp.json().get("stores", []):
        lat, lon = s.get("lat"), s.get("long")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        in_stock = (s.get("inventory") or {}).get("value")
        stores.append({
            "store": s.get("name") or "Euronics",
            "city": s.get("city") or "",
            "lat": lat,
            "lon": lon,
            "status": "available" if in_stock else "out_of_stock",
        })
    return stores


CHECKERS = {
    "demo_json": demo_json,
    "json_endpoint": json_endpoint,
    "html_marker": html_marker,
}

STORE_CHECKERS = {
    "euronics_stores": euronics_stores,
}


def check_product(product: dict) -> str:
    """Dispatch a product to its (single-status) checker. Products with a
    "store_checker" instead are handled directly in crawler.py, since
    their status is derived from the real per-store list, not a separate
    call."""
    checker = CHECKERS.get(product["checker"])
    if checker is None:
        raise ValueError(f"Unknown checker '{product['checker']}' for {product['id']}")
    return checker(product)
