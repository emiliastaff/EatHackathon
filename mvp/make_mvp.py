"""
Builds the self-contained ShelfPulse MVP page (mvp/shelfpulse.html) from the scraped data.
Run from the project root after neutonic_scraper.py:   python mvp/make_mvp.py
"""
import csv, json, os, re, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from build_archetypes import DRIVERS, ANCHORS, KW, build_archetypes, build_links  # noqa: E402
from archetype_api import STORE_MIXES, DRIVER_LABEL, FIX  # noqa: E402

DATA_DIR = os.path.join(ROOT, "neutonic_data")
OUT_DIR = os.path.join(ROOT, "shelfpulse_data")
STORE_LABELS = {"urban_trendy": "Urban trendy", "suburban_family": "Suburban family", "online_dtc": "Online DTC"}


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cwd = os.getcwd(); os.chdir(ROOT)
    master = build_archetypes("shelfpulse_data")
    build_links("shelfpulse_data", data_dir="neutonic_data", master=master)
    os.chdir(cwd)

    signals = list(csv.DictReader(open(os.path.join(OUT_DIR, "product_signals.csv"), encoding="utf-8")))
    reviews = list(csv.DictReader(open(os.path.join(DATA_DIR, "reviews.csv"), encoding="utf-8")))
    by_prod = {}
    for r in reviews:
        by_prod.setdefault(r["product_shopify_id"], []).append(r)

    def qrow(r):
        text = f"{(r.get('title') or '').strip()}. {(r.get('content') or '').strip()}".strip(". ")
        return {"quote": text[:260] + ("…" if len(text) > 260 else ""), "rating": int(f(r.get("rating"))),
                "verified": r.get("verified") == "True", "date": (r.get("created_at") or "")[:10]}

    products, seen_titles = [], {}
    for s in signals:
        revs = by_prod.get(s["product_id"], [])
        # prefer informative, verified reviews as evidence
        revs_sorted = sorted(revs, key=lambda r: (r.get("verified") != "True", -len(r.get("content") or "")))
        quotes = {}
        for d in DRIVERS:
            pat = KW.get(d)
            if not pat:
                continue
            for r in revs_sorted:
                if re.search(pat, f"{r.get('title','')} {r.get('content','')}", re.I) and len(r.get("content") or "") >= 25:
                    quotes[d] = qrow(r); break
        low = sorted((r for r in revs if f(r.get("rating")) <= 3 and len(r.get("content") or "") >= 15),
                     key=lambda r: f(r.get("rating")))
        ratings = [f(r["rating"]) for r in revs if r.get("rating")]
        p = {"id": s["product_id"], "title": s["title"], "type": s["product_type"] or "Other",
             "unit_price": f(s["unit_price"]) or None, "n_reviews": len(revs),
             "avg_rating": round(statistics.mean(ratings), 2) if ratings else None,
             "signals": {d: f(s[d]) for d in DRIVERS}, "quotes": quotes,
             "low_quote": qrow(low[0]) if low else None}
        # one row per product across UK/US/AU listings: keep the listing with most reviews
        key = re.sub(r"\s*\[(us|uk|au)\]\s*|\s*-\s*(us|uk|aus?)$", "", s["title"].lower()).strip()
        if key in seen_titles:
            if p["n_reviews"] > products[seen_titles[key]]["n_reviews"]:
                products[seen_titles[key]] = p
            continue
        seen_titles[key] = len(products); products.append(p)

    rated = [f(r["rating"]) for r in reviews if r.get("rating")]
    days = [f(r["days_purchase_to_review"]) for r in reviews if r.get("days_purchase_to_review")]
    data = {
        "drivers": DRIVERS, "driver_labels": DRIVER_LABEL, "fixes": FIX,
        "archetypes": [{"code": k, "title": a["title"], "description": a["description"], "v": a["v"]} for k, a in ANCHORS.items()],
        "store_mixes": {k: {"label": STORE_LABELS.get(k, k), "mix": m} for k, m in STORE_MIXES.items()},
        "products": products,
        "stats": {"products": len(products), "reviews": len(reviews),
                  "avg_rating": round(statistics.mean(rated), 2) if rated else 0,
                  "pct_five": round(100 * sum(r == 5 for r in rated) / len(rated)) if rated else 0,
                  "low_reviews": sum(r <= 3 for r in rated),
                  "median_days": round(statistics.median(days)) if days else None},
        "sources": [f"Neutonic storefront catalogue: {len(products)} products (Shopify)",
                    f"{len(reviews):,} customer reviews with ratings, review dates and purchase dates (Klaviyo Reviews)",
                    "Archetypes and drivers from an interview with a product head",
                    "No reviewer names or personal data stored"],
    }
    tpl = open(os.path.join(ROOT, "mvp", "template.html"), encoding="utf-8").read()
    out = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    path = os.path.join(ROOT, "mvp", "shelfpulse.html")
    open(path, "w", encoding="utf-8").write(out)
    print(f"wrote {path}: {len(products)} products, {len(reviews)} reviews, {len(out)//1024} KB")


if __name__ == "__main__":
    main()
