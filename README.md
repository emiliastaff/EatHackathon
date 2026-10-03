# ShelfPulse

**What happens to my category if I say yes?** ShelfPulse shows a retail buyer which shopper
archetypes a product wins or loses, why, and what to change, using real shopper reviews.

## Run it (about 5 minutes)

```bash
pip install -r requirements.txt
python neutonic_scraper.py        # 1. products + all reviews  -> neutonic_data/
python build_archetypes.py        # 2. archetypes + product signals -> shelfpulse_data/
uvicorn main:app --reload         # 3. open http://127.0.0.1:8000   (API docs: /docs)
```

Already scraped in Colab? Copy `neutonic_data/` (products.csv, reviews.csv) into this folder
and skip step 1.

## Files

| File | What it does |
|---|---|
| `neutonic_scraper.py` | Pulls the Shopify catalogue and every Klaviyo review (rating, text, purchase date, verified...). No reviewer names stored. |
| `build_archetypes.py` | 3 archetypes from the product-head interview, all 2,048 driver combinations, and each product's 0–1 signal on 11 drivers. |
| `archetype_api.py` | FastAPI routes: `/api/archetypes`, `/api/store-mixes`, `/api/products`, `/api/archetype-fit/{id}?store=` |
| `main.py` | Runs the API and serves the dashboard. |
| `static/index.html` | The buyer dashboard. |

## The maths

- **Signal** (per product, per driver) = 0.6 × listing claims it + 0.4 × share of reviews mentioning it
- **Fit** (product × archetype) = mean signal over the drivers that archetype cares about
- **Store fit** = Σ store archetype mix × archetype fit
- **Gap** = driver importance in that store × (1 − product signal) → ranked recommendations

## Assumptions

- The 3 archetypes and their drivers come from a product-head interview, not measured segments.
- Store mixes are starting values; adjust them with the sliders.
- Signals use keyword rules; reviews skew positive (~93% five-star for canned drinks).
- In production, RGC's consented Watch Humans data would calibrate the archetypes and weights.
