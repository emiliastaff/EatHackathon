"""
Neutonic scraper: full product catalogue + every customer review.

Sources (both public, the same ones the storefront itself loads):
  1. Shopify catalogue:   https://www.neutonic.com/products.json
  2. Klaviyo Reviews widget API (what renders the reviews on each product page)

Outputs (in ./neutonic_data/):
  products.csv       one row per product (price, pack size, tags, market, description...)
  reviews.csv        one row per review  (rating, title, text, review date, PURCHASE date,
                     days purchase->review, verified, variant, incentive, media, brand reply,
                     mentions_return flag ...). Reviewer names are deliberately NOT saved.
  review_groups.csv  one row per review group (star rating, review count, 1-5 star histogram)

Note: Neutonic pools reviews across related products (e.g. all canned drinks share one
group of ~1,100 reviews). Each review still records the exact product + variant it was for.

Run:
  Terminal:  pip install requests && python neutonic_scraper.py
  Colab:     !pip -q install requests   then   %run neutonic_scraper.py
"""
import argparse, csv, json, os, re, time, html as htmllib
from datetime import datetime
import requests

BASE = "https://www.neutonic.com"
KLAVIYO = "https://fast.a.klaviyo.com/reviews/api"
PAGE_SIZE = 50  # max the reviews API returns per call
RETURN_RE = re.compile(r"\b(return(ed|ing)?|refund(ed)?|sent (it )?back|money back|cancel(led)? (my )?subscription)\b", re.I)

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (hackathon research; polite scraper)",
                  "Accept": "application/json, text/html"})


def get(url, params=None, as_json=True, tries=4):
    for i in range(tries):
        try:
            r = S.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json() if as_json else r.text
            if r.status_code in (429, 503):
                time.sleep(10 * (i + 1)); continue
            print(f"  HTTP {r.status_code}: {url}"); return None
        except requests.RequestException as e:
            print(f"  error {e}"); time.sleep(5)
    return None


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def fetch_products():
    products, page = [], 1
    while True:
        data = get(f"{BASE}/products.json", {"limit": 250, "page": page})
        batch = (data or {}).get("products", [])
        if not batch:
            break
        products += batch; page += 1; time.sleep(1)
    return products


def product_row(p):
    v = p.get("variants") or []
    prices = [float(x["price"]) for x in v if x.get("price")]
    compare = [float(x["compare_at_price"]) for x in v if x.get("compare_at_price")]
    return {
        "product_id": p["id"], "handle": p["handle"], "title": p["title"],
        "product_type": p.get("product_type"), "market_vendor": p.get("vendor"),
        "tags": "; ".join(p.get("tags") or []),
        "variant_titles": "; ".join(x.get("title", "") for x in v),
        "variant_count": len(v),
        "price_min": min(prices) if prices else None, "price_max": max(prices) if prices else None,
        "compare_at_max": max(compare) if compare else None,
        "any_available": any(x.get("available") for x in v),
        "created_at": p.get("created_at"), "published_at": p.get("published_at"),
        "updated_at": p.get("updated_at"),
        "url": f"{BASE}/products/{p['handle']}",
        "description": strip_html(p.get("body_html")),
    }


def klaviyo_company_id():
    page = get(BASE, as_json=False) or ""
    m = re.search(r"company_id=([A-Za-z0-9]{6})", page)
    if not m:
        raise SystemExit("Could not find the Klaviyo site id on the homepage.")
    return m.group(1)


def days_between(a, b):
    try:
        fa = datetime.fromisoformat(a.replace("Z", "+00:00"))
        fb = datetime.fromisoformat(b.replace("Z", "+00:00"))
        return round((fb - fa).total_seconds() / 86400, 1)
    except Exception:
        return None


def review_row(r, group_id):
    prod = r.get("product") or {}
    var = r.get("product_variant") or {}
    text = f"{r.get('title') or ''} {r.get('content') or ''}"
    kws = [r.get(f"keyword_{i}") for i in range(1, 7)]
    return {
        "review_id": r.get("id"), "group_id": group_id,
        "product_shopify_id": prod.get("shopify_id"), "product_handle": prod.get("handle"),
        "product_name": prod.get("name"),
        "variant": var.get("title") if isinstance(var, dict) else var,
        "rating": r.get("rating"), "title": r.get("title"),
        "content": (r.get("content") or "").replace("\r", " ").replace("\n", " "),
        "created_at": r.get("created_at"), "updated_at": r.get("updated_at"),
        "order_purchase_date": r.get("order_purchase_date"),
        "days_purchase_to_review": days_between(r.get("order_purchase_date"), r.get("created_at"))
            if r.get("order_purchase_date") else None,
        "verified": r.get("verified"), "edited": r.get("edited"),
        "incentive_type": r.get("incentive_type"),
        "syndication_platform": r.get("syndication_platform"),
        "has_media": bool(r.get("image_uuid") or r.get("videos")),
        "keywords": "; ".join(k for k in kws if k),
        "custom_form": json.dumps(r["custom_form_json"]) if r.get("custom_form_json") else "",
        "brand_reply": (r.get("public_reply_content") or "").replace("\n", " "),
        "brand_reply_at": r.get("public_reply_updated_at"),
        "mentions_return": bool(RETURN_RE.search(text)),
    }


# The reviews API stops after 550 results for any single query (11 pages of 50).
# To get past that cap we union several sort orders and text searches ("filter" is
# a keyword search over review text) and de-duplicate by review id.
API_CAP = 550
SORTS = [3, 2, 0]  # 3 = default/recent, 2 = lowest rating first, 0 = newest
SEARCH_WORDS = ["the", "and", "i", "to", "it", "is", "for", "my", "a", "e", "o", "great",
                "love", "taste", "flavour", "flavor", "energy", "focus", "drink", "not",
                "but", "good", "this", "with", "day", "work", "crash", "caffeine", "product",
                "s", "t", "n", "r", "l", "u", "y", "d", "1", "2", "3", "4", "5"]


def _page(cid, group_id, offset, sort, word):
    return get(f"{KLAVIYO}/client_reviews/{group_id}/", {
        "product_id": group_id, "company_id": cid, "limit": PAGE_SIZE, "offset": offset,
        "sort": sort, "filter": word, "type": "reviews", "media": "false",
        "preferred_country": "GB", "tz": "Europe/London"})


def _sweep(cid, group_id, sort, word, found, delay):
    """Page through one (sort, search word) combination, up to the API cap."""
    offset, first = 0, None
    while offset < API_CAP:
        data = _page(cid, group_id, offset, sort, word)
        if not data:
            break
        first = first or data
        for r in data.get("reviews") or []:
            found.setdefault(r["id"], r)
        if not data.get("has_more") or not data.get("reviews"):
            break
        offset += PAGE_SIZE; time.sleep(delay)
    return first


def fetch_group_reviews(cid, group_id, delay):
    found = {}
    first = _sweep(cid, group_id, SORTS[0], "", found, delay)
    if not first:
        return [], None
    summary, total = first.get("summary"), first.get("filtered_count") or 0
    print(f"    {group_id}: {len(found)}/{total}")
    if total > API_CAP:
        for s in SORTS[1:]:
            _sweep(cid, group_id, s, "", found, delay)
        print(f"    {group_id}: {len(found)}/{total} after extra sort orders")
        for w in SEARCH_WORDS:
            if len(found) >= total:
                break
            probe = _page(cid, group_id, 0, SORTS[0], w)
            fc = (probe or {}).get("filtered_count") or 0
            if not fc:
                continue
            for s in (SORTS if fc > API_CAP else SORTS[:1]):
                _sweep(cid, group_id, s, w, found, delay)
            print(f"    {group_id}: {len(found)}/{total} after search '{w}'")
    if len(found) < total:
        print(f"    note: {total - len(found)} reviews in this group could not be reached")
    return [review_row(r, group_id) for r in found.values()], summary


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="neutonic_data")
    ap.add_argument("--delay", type=float, default=1.0)
    a, _ = ap.parse_known_args(argv)  # tolerate Jupyter's extra -f arg
    os.makedirs(a.out, exist_ok=True)

    print("1/3 Fetching product catalogue...")
    products = fetch_products()
    prows = [product_row(p) for p in products]
    write_csv(f"{a.out}/products.csv", prows)
    print(f"    {len(prows)} products")

    print("2/3 Finding review groups...")
    cid = klaviyo_company_id()
    groups = {}
    for p in products:
        g = get(f"{KLAVIYO}/client_reviews/{p['id']}/grouped_id/", {"company_id": cid})
        if g and g.get("grouped_id"):
            groups.setdefault(str(g["grouped_id"]), []).append(p["handle"])
        time.sleep(a.delay / 2)
    print(f"    {len(groups)} review groups across {len(products)} products")

    print("3/3 Downloading reviews...")
    all_reviews, seen, summaries = [], set(), []
    for gid, handles in groups.items():
        rows, summ = fetch_group_reviews(cid, gid, a.delay)
        for r in rows:
            if r["review_id"] not in seen:
                seen.add(r["review_id"]); all_reviews.append(r)
        if summ:
            hist = summ.get("rating_histogram") or [None] * 5
            summaries.append({"group_id": gid, "group_name": summ.get("name"),
                              "products_in_group": "; ".join(handles),
                              "star_rating": summ.get("star_rating"),
                              "review_count": summ.get("review_count"),
                              **{f"stars_{i+1}": hist[i] for i in range(5)}})

    write_csv(f"{a.out}/reviews.csv", all_reviews)
    write_csv(f"{a.out}/review_groups.csv", summaries)
    print(f"\nDone: {len(prows)} products, {len(all_reviews)} unique reviews -> {a.out}/")


main()
