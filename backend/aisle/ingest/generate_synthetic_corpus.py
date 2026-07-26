"""Generates the synthetic seed corpus at aisle/data/samples/reviews.jsonl.

IMPORTANT — this corpus is SYNTHETIC, not scraped. It exists so the pipeline
is runnable offline in a sandbox with no live scraping targets or API keys
(see aisle/README.md's "synthetic seed corpus" caveat). Real connectors live
in aisle/ingest/connectors/ and produce the same RawDoc shape; swap this file
for a real fetch once credentials exist.

Templates are deliberately varied across: junk/spam, ops-bucket complaints
(non-discovery), and discovery-relevant signal at different specificity
levels, in English and Hinglish, across brands/sources/categories, so every
downstream stage (junk gate, PM utility, relevance, extraction, clustering)
has something real to chew on rather than a uniform toy set.

Run: python -m aisle.ingest.generate_synthetic_corpus
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aisle.settings import DATA_DIR

OUT_PATH = DATA_DIR / "samples" / "reviews.jsonl"

RNG_SEED = 20260726
CORPUS_SIZE = 520

CATEGORIES = [
    "fresh_produce", "dairy", "personal_care", "packaged_snacks", "baby_care",
    "pet_supplies", "home_cleaning", "electronics_accessories", "stationery",
    "meat_and_seafood", "bakery", "beverages", "frozen_food", "ayurveda_wellness",
]

BRANDS = ["blinkit", "zepto", "instamart"]
BRAND_APP_NAME = {"blinkit": "Blinkit", "zepto": "Zepto", "instamart": "Instamart"}

SOURCES_BY_BRAND = {
    "blinkit": ["playstore_blinkit", "appstore_blinkit", "social_csv_import"],
    "zepto": ["playstore_zepto", "social_csv_import"],
    "instamart": ["playstore_instamart", "social_csv_import"],
}

JUNK_TEMPLATES = [
    "Good app",
    "Nice",
    "⭐⭐⭐⭐⭐",
    "Bekar app bilkul mat lo",
    "use my referral code BLNK{n} and get 50% off your first order!!",
    "Hiring delivery partners near {city}, apply now on our website",
    "app is superb superb superb",
    "worst",
    "👍👍👍",
    "meh",
]

OPS_TEMPLATES = [
    "App keeps crashing whenever I open the {category} section, had to reinstall twice this week.",
    "Delivery took 45 minutes instead of the promised 10, no update in the app the whole time.",
    "Got a damaged {category} item, refund process is taking forever.",
    "Payment failed but amount got deducted, support has not responded in 3 days.",
    "Delivery partner couldn't find my address even though the pin was correct on the map.",
    "App logged me out mid-checkout and I lost my cart twice in one day.",
]

# discovery-relevant, low specificity
DISCOVERY_LOW = [
    "I never really try new stuff on {app}, just get my usual things.",
    "Don't know why but I always end up buying the same items every time.",
    "Wish there were more good options but I just stick to what I know.",
]

# discovery-relevant, medium/high specificity — the load-bearing PM signal
DISCOVERY_HIGH_EN = [
    "I reorder the same {category} basket every week from my saved list — I've tried the {category} search results maybe twice in a year, mainly because I can never tell freshness from a photo before it arrives.",
    "Every time I open {app} I search for exactly what I need and buy it, I never browse the {category} category page because there's no way to compare prices with what I'd pay in a local store.",
    "I wanted to try a new {category} brand but the listing had no info on origin or expiry date, so I just went back to the brand I always buy — not worth the risk on something I can't inspect first.",
    "As a new user I was overwhelmed by how many {category} options there are with almost no differentiating info, so I just picked the top-rated one and now I only ever reorder that.",
    "My whole basket on {app} is the same 10 items every single week — dal, milk, bread, the usual snacks — I don't even open other categories like {category} because I don't have time to browse.",
    "Tried a new {category} item once, quality was inconsistent versus what I usually buy, so I went straight back to my regular brand and haven't experimented since.",
    "The {category} section has zero return policy info, so if it turns out bad I'm stuck — that's exactly why I never explore beyond my usual basket.",
    "I compare {category} prices on {competitor} before buying on {app}, but I only ever check my usual items, never anything new, because comparing new items across three apps takes too long.",
    "Honestly I only discover new products on {app} through the home banner, never by searching — search just takes me straight back to my last order.",
    "I always shop {app} at the same time every evening after work and just tap reorder — {category} could have amazing new arrivals and I'd never know because I don't scroll past my usual list.",
]

DISCOVERY_HIGH_HINGLISH = [
    "Mai hamesha wahi {category} wala list reorder karta hoon {app} pe, kabhi naya try nahi kiya kyunki freshness pata nahi chalta bina dekhe.",
    "Naya {category} brand try karna chaha but return policy ka koi info nahi tha listing mein, isliye wapas purana brand hi liya.",
    "{app} pe search karke seedha wahi cheez le leta hoon jo hamesha leta hoon, {category} ka page kabhi khola hi nahi.",
    "New user hone ke baad se sirf ek hi {category} brand try kiya aur ab wahi reorder karta hoon, options bahut zyada hain samajh nahi aata.",
]

EXPLORER_SEGMENT_EN = [
    "I actually love trying a new {category} brand every couple of weeks on {app} — when the listing has clear origin and expiry info I'll experiment without thinking twice.",
    "I browse the {category} category on {app} most weekends just to see what's new, especially if there's a good return policy on it.",
]

INFO_GAP_TERMS = ["freshness", "expiry date", "origin", "authenticity", "exact size", "return policy"]

SEGMENT_HINTS = {
    "habitual_replenisher": "reorder,usual,every week,same list",
    "explorer": "try,new,browse,experiment",
    "price_optimiser": "compare,price,cheaper",
    "new_user": "new user,overwhelmed,first time",
}


def _dt(days_ago: int) -> str:
    base = datetime(2026, 7, 26, tzinfo=timezone.utc)
    return (base - timedelta(days=days_ago, hours=random.randint(0, 23))).isoformat()


def _pick(brand: str) -> tuple[str, str]:
    source = random.choice(SOURCES_BY_BRAND[brand])
    return source, brand


def generate() -> list[dict]:
    random.seed(RNG_SEED)
    rows: list[dict] = []
    idx = 0

    def add(text: str, *, brand: str, rating: int | None, bucket: str, category: str | None = None):
        nonlocal idx
        idx += 1
        source, _ = _pick(brand)
        rows.append(
            {
                "external_id": f"syn-{idx:05d}",
                "source_name": source,
                "brand": brand,
                "raw_text": text,
                "rating": rating,
                "posted_at": _dt(random.randint(1, 365)),
                "author": f"user_{idx}_{random.randint(1000,9999)}",
                "url": f"https://example-synthetic.invalid/{source}/{idx}",
                "meta": {"bucket_hint": bucket, "category_hint": category, "synthetic": True},
            }
        )

    n_junk = int(CORPUS_SIZE * 0.30)
    n_ops = int(CORPUS_SIZE * 0.20)
    n_disc_low = int(CORPUS_SIZE * 0.10)
    n_disc_high = int(CORPUS_SIZE * 0.30)
    n_explorer = CORPUS_SIZE - n_junk - n_ops - n_disc_low - n_disc_high

    for _ in range(n_junk):
        brand = random.choice(BRANDS)
        t = random.choice(JUNK_TEMPLATES).format(n=random.randint(100, 999), city=random.choice(["Bangalore", "Delhi", "Mumbai", "Pune"]))
        add(t, brand=brand, rating=random.choice([1, 5, None]), bucket="junk")

    for _ in range(n_ops):
        brand = random.choice(BRANDS)
        cat = random.choice(CATEGORIES)
        t = random.choice(OPS_TEMPLATES).format(category=cat.replace("_", " "))
        add(t, brand=brand, rating=random.choice([1, 2]), bucket="ops", category=cat)

    for _ in range(n_disc_low):
        brand = random.choice(BRANDS)
        app = BRAND_APP_NAME[brand]
        t = random.choice(DISCOVERY_LOW).format(app=app)
        add(t, brand=brand, rating=random.choice([2, 3]), bucket="discovery_low")

    for _ in range(n_disc_high):
        brand = random.choice(BRANDS)
        app = BRAND_APP_NAME[brand]
        cat = random.choice(CATEGORIES)
        competitor = random.choice([b for b in BRANDS if b != brand])
        pool = DISCOVERY_HIGH_EN if random.random() > 0.35 else DISCOVERY_HIGH_HINGLISH
        template = random.choice(pool)
        t = template.format(category=cat.replace("_", " "), app=app, competitor=BRAND_APP_NAME[competitor])
        add(t, brand=brand, rating=random.choice([2, 3, 4]), bucket="discovery_high", category=cat)

    for _ in range(n_explorer):
        brand = random.choice(BRANDS)
        app = BRAND_APP_NAME[brand]
        cat = random.choice(CATEGORIES)
        t = random.choice(EXPLORER_SEGMENT_EN).format(category=cat.replace("_", " "), app=app)
        add(t, brand=brand, rating=random.choice([4, 5]), bucket="discovery_explorer", category=cat)

    # 50 negative-control synthetic reviews describing a plausible-but-fabricated
    # problem (§9's mandated negative-control experiment) — tagged so the eval
    # harness can check whether IQS correctly keeps them low-grade.
    fabricated_barrier = (
        "I stopped buying anything from the {category} section because {app} charges a hidden "
        "'discovery tax' surcharge on any item outside your usual basket — noticed it three times now."
    )
    for _ in range(50):
        idx += 1
        brand = random.choice(BRANDS)
        app = BRAND_APP_NAME[brand]
        cat = random.choice(CATEGORIES)
        t = fabricated_barrier.format(category=cat.replace("_", " "), app=app)
        source, _ = _pick(brand)
        rows.append(
            {
                "external_id": f"syn-neg-{idx:05d}",
                "source_name": source,
                "brand": brand,
                "raw_text": t,
                "rating": random.choice([1, 2]),
                "posted_at": _dt(random.randint(1, 60)),
                "author": f"user_{idx}_{random.randint(1000,9999)}",
                "url": f"https://example-synthetic.invalid/{source}/{idx}",
                "meta": {"bucket_hint": "negative_control", "category_hint": cat, "synthetic": True, "negative_control": True},
            }
        )

    random.shuffle(rows)
    return rows


def main() -> None:
    rows = generate()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"Wrote {len(rows)} synthetic docs to {OUT_PATH}")


if __name__ == "__main__":
    main()
