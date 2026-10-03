

# ShelfPulse

**"What happens to my category if I say yes?"**

ShelfPulse helps a retail buyer decide what to stock by showing **who** chooses a product, **why**, and **what to change**, using real shopper reviews instead of last year's sales data.

Built for **Track 1: Human Truth** (Really Good Culture hackathon).

---

## The problem
Buyers make range decisions with other people's evidence: supplier decks built to win the meeting, and sales data describing a shelf that has already traded. Sales show *what* sold, never *why*, or what nearly won instead. And shoppers ≠ consumers: the person buying on budget is often not the person consuming for flavour or curiosity.

## What ShelfPulse does
1. **Range review:** ranks every product for a store format (urban trendy, suburban family, online DTC) with a verdict: *Stock*, *Stock with fixes* or *Review listing*.
2. **Product deep-dive:** fit by shopper archetype, how the same product performs in different stores, the biggest gaps with concrete fixes, and real shopper quotes (including rejection signals).
3. **Adjustable shopper mix:** sliders to test a different customer base live.
4. **Transparent method:** every score, formula and assumption is visible.

## Shopper archetypes
Built from an interview with a product head, across 11 purchase drivers: cost, medical/functional claims, dietary claims, nutrition, design, curiosity, coolness, seasonal, eco-friendly, trendsetter, mood.

| Archetype | Driven by |
|---|---|
| **Value-Savvy Explorer** | Cost, diet, nutrition, design, curiosity, coolness, eco |
| **Premium Wellness Enthusiast** | Everything except price |
| **Seasonal Mood Shopper** | Cost, seasonal, eco, trends, mood |

All 2,048 (2^11) driver combinations are generated and mapped to their nearest archetype (`archetypes_master.csv`).

## Data
- **Neutonic** (UK functional drinks brand): 59 products from the Shopify catalogue
- **1,080+ customer reviews** with rating, review date, purchase date and verified flag (Klaviyo Reviews widget API)
- The reviews API caps each query at 550 results, so the scraper combines several sort orders and keyword searches, then de-duplicates, to recover ~98% of reviews
- No reviewer names or personal data are stored

## The maths

Verdicts rank products against the rest of the range in each store format (top third / middle / bottom).

Verdicts rank products against the rest of the range in each store format (top third / middle / bottom).

## Run it
```bash
pip install -r requirements.txt
python3 neutonic_scraper.py        # products + reviews  -> neutonic_data/
python3 mvp/make_mvp.py            # builds mvp/shelfpulse.html (open in any browser)

# optional: live API + dashboard
python3 -m uvicorn main:app --reload   # http://127.0.0.1:8000  (API docs at /docs)
```

## Project structure
| File | Purpose |
|---|---|
| `neutonic_scraper.py` | Scrapes products and all reviews |
| `build_archetypes.py` | Archetypes, 2,048 combinations, product driver signals |
| `archetype_api.py` | FastAPI routes: archetypes, store mixes, products, archetype fit |
| `main.py` | Runs the API and serves the dashboard |
| `mvp/make_mvp.py` | Builds the self-contained MVP page from the data |
| `mvp/shelfpulse.html` | **The MVP**: opens offline, no server needed |
| `static/index.html` | Dashboard for the live API version |

## Assumptions and limits
- The 3 archetypes are hypotheses from a product-head interview, not measured segments.
- Store shopper mixes are starting values (adjustable in the UI).
- Signals use keyword rules; design and coolness are only partly visible in text.
- Reviews skew positive (~93% five-star for canned drinks), so rejection signals are under-represented. Low ratings are surfaced on purpose.
- Reviews show who bought, not always who consumed.

## Making it real
- **Data ownership:** replace scraped reviews with consented Watch Humans video reviews, which capture what nearly won and why.
- **Calibration:** fit archetype weights and store mixes to a retailer's sell-through and loyalty data, then test predictions on the next range review.
- **Privacy:** aggregates and anonymised quotes only.
- **Cost and scale:** pennies per thousand reviews; the pipeline works for any category with reviews.

## Team
[Add team names]
