"""
ShelfPulse - archetype + evidence API (drop-in FastAPI router).

Add to your existing FastAPI app:
    from archetype_api import router as archetype_router
    app.include_router(archetype_router)

Expects next to this file:
    build_archetypes.py                 (drivers, archetypes, keyword rules)
    shelfpulse_data/product_signals.csv
    shelfpulse_data/product_archetype_fit.csv   (not required, recomputed live)
    neutonic_data/reviews.csv           (for evidence quotes)

Endpoints
    GET /api/archetypes                        3 archetypes + what drives them
    GET /api/store-mixes                       assumed archetype mix per store type
    GET /api/products                          products with their 11 driver signals
    GET /api/archetype-fit/{product_id}?store=urban_trendy
         -> fit per archetype, store-weighted demand fit, strong/weak drivers,
            recommendations, real review quotes, and the assumptions behind it
"""
import csv, os, re
from typing import Optional
from functools import lru_cache
from fastapi import APIRouter, HTTPException, Query

from build_archetypes import DRIVERS, ANCHORS, KW

BASE = os.path.dirname(os.path.abspath(__file__))
SIGNALS_CSV = os.path.join(BASE, "shelfpulse_data", "product_signals.csv")
REVIEWS_CSV = os.path.join(BASE, "neutonic_data", "reviews.csv")

router = APIRouter(prefix="/api", tags=["archetypes"])

# ASSUMPTION: share of shoppers of each archetype per store type (editable via query params)
STORE_MIXES = {
    "urban_trendy":     {"A": 0.45, "B": 0.40, "C": 0.15},
    "suburban_family":  {"A": 0.30, "B": 0.15, "C": 0.55},
    "online_dtc":       {"A": 0.40, "B": 0.35, "C": 0.25},
}

DRIVER_LABEL = {
    "cost": "Value for money", "medical": "Functional / health claims", "dietary": "Dietary claims",
    "nutrition": "Nutrition", "design": "Design & packaging", "curiosity": "Curiosity / novelty",
    "coolness": "Coolness / social image", "seasonal": "Seasonal relevance",
    "eco_friendly": "Eco credentials", "trendsetter": "Trend / newness", "mood": "Mood & occasion",
}
FIX = {
    "cost": "Show cost-per-serving vs the mainstream alternative; offer a smaller trial pack.",
    "medical": "State the functional benefit plainly (what it does, how fast, for how long).",
    "dietary": "Put dietary badges (sugar-free, vegan, gluten-free) on the front of pack and listing title.",
    "nutrition": "Add a simple nutrition panel highlight (e.g. key vitamins, calories) near the price.",
    "design": "Refresh hero imagery; test a bolder shelf-standout pack in this store format.",
    "curiosity": "Lead with the unusual flavour or ingredient to spark trial; use sampling.",
    "coolness": "Add social proof: creator content, 'as seen on', or community reviews.",
    "seasonal": "Add a seasonal moment (summer serve, winter edition, gifting bundle).",
    "eco_friendly": "Call out recyclable / low-plastic packaging at shelf and online.",
    "trendsetter": "Badge it as new, and tie it to a current trend or launch moment.",
    "mood": "Frame it around a mood or occasion (deep work, afternoon slump, calm focus).",
}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


@lru_cache(maxsize=1)
def load_signals():
    if not os.path.exists(SIGNALS_CSV):
        raise HTTPException(500, f"Missing {SIGNALS_CSV}. Run build_archetypes.py first.")
    rows = list(csv.DictReader(open(SIGNALS_CSV, encoding="utf-8")))
    for r in rows:
        for d in DRIVERS:
            r[d] = _f(r.get(d))
    return {r["product_id"]: r for r in rows}


@lru_cache(maxsize=1)
def load_reviews():
    if not os.path.exists(REVIEWS_CSV):
        return {}
    out = {}
    for r in csv.DictReader(open(REVIEWS_CSV, encoding="utf-8")):
        out.setdefault(r["product_shopify_id"], []).append(r)
    return out


def fit(sig, vec):
    cared = [d for d, v in zip(DRIVERS, vec) if v]
    return round(sum(sig[d] for d in cared) / len(cared), 3) if cared else 0.0


def quotes_for(product_id, drivers, k=3):
    revs = load_reviews().get(product_id, [])
    picked, seen = [], set()
    for d in drivers:
        pat = KW.get(d)
        if not pat:
            continue
        for r in revs:
            text = f"{r.get('title', '')}. {r.get('content', '')}".strip()
            if r["review_id"] in seen or not re.search(pat, text, re.I):
                continue
            picked.append({"driver": DRIVER_LABEL[d], "rating": r.get("rating"),
                           "verified": r.get("verified"), "date": (r.get("created_at") or "")[:10],
                           "quote": text[:280]})
            seen.add(r["review_id"])
            break
        if len(picked) >= k:
            break
    # always surface the most critical review as counter-evidence
    low = sorted((r for r in revs if r["review_id"] not in seen and _f(r.get("rating")) <= 3),
                 key=lambda r: _f(r.get("rating")))
    if low:
        r = low[0]
        picked.append({"driver": "Rejection signal", "rating": r.get("rating"),
                       "verified": r.get("verified"), "date": (r.get("created_at") or "")[:10],
                       "quote": f"{r.get('title', '')}. {r.get('content', '')}"[:280]})
    return picked


@router.get("/archetypes")
def archetypes():
    return [{"code": k, "title": a["title"], "description": a["description"],
             "drivers": {d: v for d, v in zip(DRIVERS, a["v"])}} for k, a in ANCHORS.items()]


@router.get("/store-mixes")
def store_mixes():
    return {s: {ANCHORS[k]["title"]: w for k, w in m.items()} for s, m in STORE_MIXES.items()}


@router.get("/products")
def products():
    return [{"product_id": p["product_id"], "title": p["title"], "product_type": p["product_type"],
             "unit_price": _f(p.get("unit_price")), "n_reviews": int(_f(p.get("n_reviews"))),
             "signals": {d: p[d] for d in DRIVERS}} for p in load_signals().values()]


@router.get("/archetype-fit/{product_id}")
def archetype_fit(product_id: str,
                  store: str = Query("urban_trendy", enum=list(STORE_MIXES)),
                  mix_a: Optional[float] = None, mix_b: Optional[float] = None, mix_c: Optional[float] = None):
    sig = load_signals().get(product_id)
    if not sig:
        raise HTTPException(404, "Unknown product_id")

    mix = dict(STORE_MIXES[store])
    if None not in (mix_a, mix_b, mix_c) and (mix_a + mix_b + mix_c) > 0:
        t = mix_a + mix_b + mix_c
        mix = {"A": mix_a / t, "B": mix_b / t, "C": mix_c / t}

    per = {k: fit(sig, a["v"]) for k, a in ANCHORS.items()}
    store_fit = round(sum(mix[k] * per[k] for k in ANCHORS), 3)

    # how much the store's shoppers care about each driver (mix-weighted), vs how well the product delivers
    importance = {d: sum(mix[k] * ANCHORS[k]["v"][i] for k in ANCHORS) for i, d in enumerate(DRIVERS)}
    gaps = sorted(DRIVERS, key=lambda d: importance[d] * (1 - sig[d]), reverse=True)
    strengths = sorted(DRIVERS, key=lambda d: importance[d] * sig[d], reverse=True)

    return {
        "product": {"product_id": product_id, "title": sig["title"], "product_type": sig["product_type"],
                    "unit_price": _f(sig.get("unit_price")), "n_reviews": int(_f(sig.get("n_reviews")))},
        "store": store,
        "store_mix": {ANCHORS[k]["title"]: round(w, 2) for k, w in mix.items()},
        "fit_by_archetype": {ANCHORS[k]["title"]: v for k, v in per.items()},
        "best_archetype": ANCHORS[max(per, key=per.get)]["title"],
        "store_weighted_fit": store_fit,
        "signals": {DRIVER_LABEL[d]: sig[d] for d in DRIVERS},
        "top_strengths": [{"driver": DRIVER_LABEL[d], "signal": sig[d], "importance": round(importance[d], 2)}
                          for d in strengths[:3]],
        "biggest_gaps": [{"driver": DRIVER_LABEL[d], "signal": sig[d], "importance": round(importance[d], 2),
                          "recommendation": FIX[d]} for d in gaps[:3]],
        "evidence_quotes": quotes_for(product_id, strengths[:3] + gaps[:3]),
        "method": "fit(archetype) = mean of the product's 0-1 signals over the drivers that archetype cares about; "
                  "store fit = archetype fits weighted by the store's archetype mix; "
                  "gap = driver importance in this store x (1 - product signal).",
        "assumptions": [
            "The 3 archetypes and their drivers come from a product-head interview, not measured segments.",
            "Store archetype mixes are assumed starting values (override with mix_a/mix_b/mix_c).",
            "Signals combine listing claims (60%) and review mentions (40%) via keyword rules.",
            "Reviews skew positive (~93% five-star for canned drinks); rejection signals are under-represented.",
        ],
    }
