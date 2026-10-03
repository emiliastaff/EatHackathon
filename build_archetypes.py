"""
ShelfPulse - archetype master dataset + link to scraped Neutonic products/reviews.

1. archetypes_anchor.csv   the 3 hand-defined archetypes (from the whiteboard), titled
2. archetypes_master.csv   ALL 2^11 = 2048 combinations of the 11 drivers, each with a
                           generated title, its nearest anchor archetype and distance
3. product_signals.csv     (if neutonic_data/ exists) 0-1 score per product per driver,
                           from product text/price + share of reviews mentioning the driver
4. product_archetype_fit.csv  fit of every product to each anchor archetype + best-match
                              archetype among all 2048

Driver value 1 = "this matters to the shopper" (ok on the whiteboard), 0 = "doesn't" (No).
"""
import csv, itertools, os, re, statistics
from datetime import datetime, timezone

DRIVERS = ["cost", "medical", "dietary", "nutrition", "design", "curiosity",
           "coolness", "seasonal", "eco_friendly", "trendsetter", "mood"]

ANCHORS = {
    "A": {"title": "Value-Savvy Explorer",
          "description": "Price-aware but curious; buys on design, coolness, diet & nutrition and "
                         "eco credentials. Ignores medical claims, seasons, trends and mood.",
          "v": [1, 0, 1, 1, 1, 1, 1, 0, 1, 0, 0]},
    "B": {"title": "Premium Wellness Enthusiast",
          "description": "Not price-sensitive; every signal counts, especially medical/functional "
                         "claims, seasonality, trends and mood. High-engagement, high-basket.",
          "v": [0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]},
    "C": {"title": "Seasonal Mood Shopper",
          "description": "Price-aware and driven by moment and mood; follows trends, seasons and "
                         "eco cues. Not swayed by health claims, design or novelty.",
          "v": [1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1]},
}

# Title building blocks for generated archetypes (priority order matters)
MOTIVES = [("medical", "Wellness"), ("nutrition", "Nutrition"), ("dietary", "Diet-Led"),
           ("curiosity", "Explorer"), ("trendsetter", "Trend"), ("mood", "Mood"),
           ("eco_friendly", "Eco"), ("seasonal", "Seasonal"), ("coolness", "Cool-Seeker"),
           ("design", "Aesthetic")]
NOUN = {"Wellness": "Optimiser", "Nutrition": "Tracker", "Diet-Led": "Label Reader",
        "Explorer": "Explorer", "Trend": "Follower", "Mood": "Mood Buyer", "Eco": "Conscious Buyer",
        "Seasonal": "Occasion Buyer", "Cool-Seeker": "Image Buyer", "Aesthetic": "Design Buyer"}


def title_for(d):
    price = "Budget" if d["cost"] else "Premium"
    motives = [m for k, m in MOTIVES if d[k]]
    if not motives:
        return f"{price} Habitual Shopper"
    if len(motives) == 1:
        return f"{price} {NOUN[motives[0]]}"
    if len(motives) >= 8:
        return f"{price} Maximiser (cares about almost everything)"
    return f"{price} {motives[0]} {NOUN[motives[1]]}"


def hamming(a, b):
    return sum(x != y for x, y in zip(a, b))


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


def build_archetypes(out):
    anchors = [{"archetype_code": k, "title": a["title"], "description": a["description"],
                **dict(zip(DRIVERS, a["v"])), "drivers_that_matter": sum(a["v"])}
               for k, a in ANCHORS.items()]
    write(f"{out}/archetypes_anchor.csv", anchors)

    master = []
    for i, combo in enumerate(itertools.product([0, 1], repeat=len(DRIVERS)), 1):
        d = dict(zip(DRIVERS, combo))
        dist = {k: hamming(combo, a["v"]) for k, a in ANCHORS.items()}
        near = min(dist, key=dist.get)
        exact = [k for k, a in ANCHORS.items() if list(combo) == a["v"]]
        master.append({
            "archetype_id": f"ARC-{i:04d}",
            "title": ANCHORS[exact[0]]["title"] if exact else title_for(d),
            "is_anchor": bool(exact),
            "nearest_anchor": ANCHORS[near]["title"],
            "distance_to_anchor": dist[near],
            "similarity_to_anchor": round(1 - dist[near] / len(DRIVERS), 2),
            **d,
            "drivers_that_matter": sum(combo),
            "price_sensitive": bool(d["cost"]),
            "driver_profile": ", ".join(k for k in DRIVERS if d[k]) or "none",
        })
    # readable order: your 3 archetypes first, then each family from closest to furthest
    master.sort(key=lambda r: (not r["is_anchor"], r["nearest_anchor"], r["distance_to_anchor"],
                               -r["drivers_that_matter"]))
    write(f"{out}/archetypes_master.csv", master)
    return master


# ---------- link to scraped data (rule-based signals; documented assumptions) ----------
KW = {
    "medical":      r"nootropic|clinical|cognitive|brain|immun|theanine|creatine|focus|memory|health",
    "dietary":      r"vegan|sugar[- ]?free|zero sugar|no sugar|gluten|caffeine[- ]?free|keto|natural|plant",
    "nutrition":    r"vitamin|electrolyte|protein|creatine|calorie|nutrient|mineral|b12|magnesium",
    "design":       r"design|packag|can looks|aesthetic|beautiful|sleek|colou?r",
    "curiosity":    r"mushroom|lion'?s mane|rosemary|yuzu|matcha|watermelon mint|white peach|wild|pouch|"
                    r"unusual|unique|different|never tried|curious|intrigu",
    "coolness":     r"\bcool\b|trendy|stylish|vibe|everyone (asks|loves)|friends",
    "seasonal":     r"summer|winter|christmas|festive|limited|seasonal|edition|autumn|spring",
    "eco_friendly": r"recycl|aluminium|aluminum|plastic[- ]?free|sustainab|eco|compostable",
    "trendsetter":  r"\bnew\b|launch|tiktok|viral|trend|influencer",
    "mood":         r"mood|calm|relax|stress|anxi|happy|energ|productiv|motivat|chill",
}


def unit_price(p):
    n = re.search(r"(\d+)\s*(pack|cans?|count|sachets?|sticks?|pk|x)", f"{p['title']} {p['variant_titles']}", re.I)
    try:
        return float(p["price_min"]) / (int(n.group(1)) if n else 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def build_links(out, data_dir="neutonic_data", master=None):
    if not os.path.exists(f"{data_dir}/products.csv"):
        print(f"(skip product linking: {data_dir}/products.csv not found)")
        return
    products = list(csv.DictReader(open(f"{data_dir}/products.csv", encoding="utf-8")))
    reviews = list(csv.DictReader(open(f"{data_dir}/reviews.csv", encoding="utf-8"))) \
        if os.path.exists(f"{data_dir}/reviews.csv") else []
    by_prod = {}
    for r in reviews:
        by_prod.setdefault(r["product_shopify_id"], []).append(f"{r['title']} {r['content']}".lower())

    ups = [u for u in (unit_price(p) for p in products) if u]
    med_up = statistics.median(ups) if ups else None
    now = datetime.now(timezone.utc)

    signals = []
    for p in products:
        text = f"{p['title']} {p['tags']} {p['description']} {p['product_type']}".lower()
        revs = by_prod.get(p["product_id"], [])
        row = {"product_id": p["product_id"], "title": p["title"], "product_type": p["product_type"],
               "market": p["market_vendor"], "unit_price": round(unit_price(p) or 0, 2),
               "n_reviews": len(revs)}
        # cost: 1 = good value (unit price at/below median) -> appeals to price-sensitive archetypes
        up = unit_price(p)
        row["cost"] = 1.0 if (up and med_up and up <= med_up) else 0.0
        for d, pat in KW.items():
            listing = 1.0 if re.search(pat, text) else 0.0
            share = sum(bool(re.search(pat, t)) for t in revs) / len(revs) if revs else 0.0
            # 60% what the listing claims, 40% how often reviewers bring it up (capped at 1)
            row[d] = round(min(1.0, 0.6 * listing + 0.4 * min(1.0, share * 3)), 2)
        try:
            created = datetime.fromisoformat(p["created_at"].replace("Z", "+00:00"))
            if (now - created).days <= 180:
                row["trendsetter"] = max(row["trendsetter"], 1.0)
        except Exception:
            pass
        signals.append(row)
    write(f"{out}/product_signals.csv", signals)

    def fit(sig, vec):
        cared = [d for d, v in zip(DRIVERS, vec) if v]
        return round(sum(sig[d] for d in cared) / len(cared), 3) if cared else 0.0

    fits = []
    for s in signals:
        row = {"product_id": s["product_id"], "title": s["title"], "product_type": s["product_type"]}
        for k, a in ANCHORS.items():
            row[f"fit_{a['title']}"] = fit(s, a["v"])
        anchor_scores = {a["title"]: row[f"fit_{a['title']}"] for a in ANCHORS.values()}
        row["best_anchor_archetype"] = max(anchor_scores, key=anchor_scores.get)
        # best of all 2048 (ignore trivial 1-2 driver profiles)
        best = max((m for m in master if m["drivers_that_matter"] >= 3),
                   key=lambda m: fit(s, [m[d] for d in DRIVERS]))
        row["best_match_archetype_id"] = best["archetype_id"]
        row["best_match_title"] = best["title"]
        row["best_match_fit"] = fit(s, [best[d] for d in DRIVERS])
        fits.append(row)
    write(f"{out}/product_archetype_fit.csv", fits)
    print(f"linked {len(signals)} products and {len(reviews)} reviews")


if __name__ == "__main__":
    out = "shelfpulse_data"
    os.makedirs(out, exist_ok=True)
    m = build_archetypes(out)
    print(f"{len(m)} archetype combinations written")
    build_links(out, master=m)
