"""Generates the versioned DEMO fixtures in fixtures/serpapi/v1/.

These are SYNTHETIC responses that follow SerpApi's documented JSON shapes for each engine.
All brands are fictional and all brand/news URLs use the reserved `.example` domain.
They exist so the full multi-agent workflow can be demonstrated offline. They are NOT
market data. To capture genuine responses, run scripts/record_fixtures.py with a key.

    python scripts/build_demo_fixtures.py
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.planner import build_plan  # noqa: E402
from app.schemas.profile import demo_profile  # noqa: E402
from app.serpapi.gateway import canonical_params  # noqa: E402

OUT = ROOT / "fixtures" / "serpapi" / "v1"
CREATED = "2026-09-28 06:40:12 UTC"
NOTE = "SYNTHETIC DEMO FIXTURE – fictional brands, illustrative values. Not real market data."


def meta(engine: str, slug: str, extra: dict | None = None) -> dict:
    return {"id": f"fixture-{slug}", "status": "Success", "created_at": CREATED, "processed_at": CREATED,
            "total_time_taken": 1.31, "fixture_note": NOTE, **(extra or {})}


def shop_item(pos, title, source, price, rating, reviews, pid=None, old=None, delivery="Free delivery", ext=None, raw_price=None):
    item = {"position": pos, "title": title, "source": source,
            "price": raw_price if raw_price is not None else f"₹{price:,.2f}",
            "extracted_price": float(price), "rating": rating, "reviews": reviews, "delivery": delivery,
            "product_link": f"https://{source.lower().replace(' ', '').replace('.', '').replace('&', 'and')}.example/p/{pos}",
            "thumbnail": "https://images.example/thumb.png"}
    if raw_price is not None and not raw_price.startswith("₹"):
        item["extracted_price"] = float(price)
    if pid:
        item["product_id"] = pid
    if old:
        item["old_price"] = f"₹{old:,.2f}"
        item["extracted_old_price"] = float(old)
    if ext:
        item["extensions"] = ext
    return item


SNACKS = [
    shop_item(1, "Crunch Theory Roasted Makhana Peri Peri 4 x 30g", "Crunch Theory", 199, 4.4, 2310, pid="7400100000000000101"),
    shop_item(2, "Makhana Mill Himalayan Salt Makhana 80g", "Makhana Mill", 149, 4.2, 860, pid="7400100000000000102"),
    shop_item(3, "GoodGrain Co. Baked Ragi Chips 150g", "GoodGrain Co.", 175, 4.3, 540),
    shop_item(4, "Trailblaze Foods Trail Mix Pack of 3 (200g each)", "Trailblaze Foods", 549, 4.5, 1210),
    shop_item(5, "Snackwise Protein Bars Peanut Butter 6 Bars", "Snackwise", 360, 4.1, 330),
    shop_item(6, "Little Millet Co. Jowar Puffs 100g", "Little Millet Co.", 120, 4.0, 150),
    shop_item(7, "Peppy Pulses Roasted Chana Mix 200g", "BigBasket", 140, 4.3, 410),
    shop_item(8, "Crunch Theory Makhana Combo 80g & 120g", "Crunch Theory", 299, 4.4, 95, old=349, ext=["14% off"]),
    shop_item(9, "Makhana Mill Assorted Snack Box", "Makhana Mill", 449, 4.6, 120),
    shop_item(10, "NutriWorld Global Healthy Snack Variety Pack 30 Count", "NutriWorld Global", 24.99, 4.5, 3100,
              raw_price="$24.99", delivery="International shipping"),
    shop_item(11, "GoodGrain Co. Multigrain Chips 2 x 150g", "Amazon.in", 320, 4.3, 210),
    shop_item(12, "Trailblaze Foods Seed Mix 250g", "Trailblaze Foods", 299, 4.5, 640),
]
COFFEE = [
    shop_item(1, "Kaapi Trail Attikan Estate Medium Roast Coffee Beans 250g", "Kaapi Trail", 649, 4.6, 1840,
              pid="7400200000000000201", old=749, ext=["SALE"]),
    shop_item(2, "Blue Hills Roasters Single Origin Arabica Whole Beans 250g", "Blue Hills Roasters", 720, 4.7, 960, pid="7400200000000000202"),
    shop_item(3, "Monsoon Bean Co. Monsooned Malabar Whole Beans 250g", "Monsoon Bean Co.", 560, 4.4, 520),
    shop_item(4, "Third Crack Coffee Dark Roast Espresso Blend 500g", "Third Crack Coffee", 1099, 4.5, 610),
    shop_item(5, "Estate Brew Classic Filter Coffee Beans 1kg", "Flipkart", 1450, 4.2, 1320),
    shop_item(6, "Roast Republic Cold Brew Coffee Beans 250g", "Roast Republic", 590, 4.3, 210),
    shop_item(7, "Chikmagalur Craft Peaberry Coffee Beans 250g", "Chikmagalur Craft", 840, 4.8, 140),
    shop_item(8, "Kaapi Trail Coffee Beans Pack of 2 x 250g", "Kaapi Trail", 1199, 4.6, 300),
    shop_item(9, "Blue Hills Roasters Coffee Sampler 4 x 100g", "Blue Hills Roasters", 899, 4.7, 75),
    shop_item(10, "Monsoon Bean Co. Medium Roast Coffee Beans 250g", "Amazon.in", 499, 4.3, 890),
    shop_item(11, "Third Crack Coffee Swiss Water Decaf 250 g", "Third Crack Coffee", 780, 4.4, 60),
    shop_item(12, "Estate Brew House Blend Coffee Beans 200g", "Estate Brew", 380, 4.0, 45),
]
HONEY = [
    shop_item(1, "Wildbloom Honey Raw Forest Honey 500g", "Wildbloom Honey", 549, 4.5, 760, pid="7400300000000000301"),
    shop_item(2, "Himalayan Hive Multiflora Honey 1kg", "BigBasket", 699, 4.3, 1430),
    shop_item(3, "Pantry Atelier Wild Thyme Honey 250g", "Pantry Atelier", 650, 4.7, 88),
    shop_item(4, "Forest Gold Organic Honey 500g", "Forest Gold", 299, 4.1, 2210, old=399, ext=["25% off"]),
    shop_item(5, "Nectar & Co. Acacia Honey 500 g", "Nectar & Co.", 799, 4.6, 240),
    shop_item(6, "BeeKind Organics Raw Honey 500g", "BeeKind Organics", 475, 4.4, 530),
    shop_item(7, "Himalayan Hive Honey Combo 500g + 250g", "Himalayan Hive", 599, 4.2, 60),
    shop_item(8, "Wildbloom Honey Gift Box 3 x 250g", "Wildbloom Honey", 1250, 4.8, 45),
    shop_item(9, "Forest Gold Honey 1 kg", "JioMart", 1050, 4.0, 300, raw_price="1,050"),
    shop_item(10, "Pantry Atelier Single Estate Honey 350g", "Pantry Atelier", 1190, 4.6, 70),
    shop_item(11, "Nectar & Co. Rare Jamun Honey 250g", "Nectar & Co.", 1390, 4.7, 52),
]


def shopping(q, items, slug):
    return {"search_metadata": meta("google_shopping", slug, {"google_shopping_url": "https://www.google.co.in/search?tbm=shop"}),
            "search_parameters": {"engine": "google_shopping", "q": q, "gl": "in", "hl": "en"},
            "shopping_results": items}


def product(pid, title, brand, price, rating, reviews, sellers, desc):
    return {"search_metadata": meta("google_product", f"product-{pid}"),
            "search_parameters": {"engine": "google_product", "product_id": pid, "offer_view": "true", "gl": "in", "hl": "en"},
            "product_results": {"product_id": pid, "title": title, "brand": brand, "prices": [f"₹{price:,}"],
                                "typical_prices": {"low": f"₹{int(price * 0.9):,}", "high": f"₹{int(price * 1.12):,}",
                                                   "shown_price": f"₹{price:,} at {sellers[0][0]}"},
                                "rating": rating, "reviews": reviews, "description": desc,
                                "extensions": ["Vegetarian", "Shelf life: 6 months"]},
            "sellers_results": {"online_sellers": [
                {"position": i + 1, "name": n, "link": f"https://{n.lower().replace(' ', '').replace('.', '')}.example/item",
                 "base_price": f"₹{p:,.2f}", "total_price": f"₹{p + s:,.2f}",
                 "additional_price": {"shipping": "Free" if s == 0 else f"₹{s:,.2f}"}}
                for i, (n, p, s) in enumerate(sellers)]},
            "specs_results": {"Brand": brand, "Form": "Whole", "Diet type": "Vegetarian"},
            "reviews_results": {"ratings": [{"stars": 5, "amount": int(reviews * 0.62)}, {"stars": 4, "amount": int(reviews * 0.24)}],
                                "reviews": [{"title": "Fresh and well packed", "rating": 5, "source": "Demo reviewer"},
                                            {"title": "Good but pricey", "rating": 4, "source": "Demo reviewer"}]}}


def organic(q, rows, slug):
    return {"search_metadata": meta("google", slug), "search_parameters": {"engine": "google", "q": q, "gl": "in", "hl": "en"},
            "organic_results": [{"position": i + 1, "title": t, "link": l, "displayed_link": l.split("/")[2],
                                 "snippet": sn, "source": src} for i, (t, l, sn, src) in enumerate(rows)]}


def trends_series():
    rnd = random.Random(7)
    start = datetime(2025, 9, 28, tzinfo=timezone.utc)
    raw = {"healthy snacks": [], "coffee beans": [], "organic honey": []}
    for i in range(53):
        season = math.sin(2 * math.pi * (i - 10) / 52)
        raw["healthy snacks"].append(60 + 3 * season + rnd.uniform(-4, 4))
        raw["coffee beans"].append(42 + 24 * i / 52 + 5 * season + rnd.uniform(-3, 3))
        raw["organic honey"].append(41 - 7 * i / 52 + 6 * season + rnd.uniform(-3, 3))
    top = max(max(v) for v in raw.values())
    timeline = []
    for i in range(53):
        d0 = start + timedelta(weeks=i)
        d1 = d0 + timedelta(days=6)
        label = f"{d0:%b} {d0.day} – {d1.day}, {d1.year}" if d0.month == d1.month else f"{d0:%b} {d0.day} – {d1:%b} {d1.day}, {d1.year}"
        row = {"date": label, "timestamp": str(int(d0.timestamp())),
               "values": [{"query": q, "value": str(round(v[i] / top * 100)), "extracted_value": round(v[i] / top * 100)}
                          for q, v in raw.items()]}
        if i == 52:
            row["partial_data"] = True
        timeline.append(row)
    return timeline


def news_item(i, title, source, date, snippet):
    return {"position": i, "title": title, "source": {"name": source, "icon": "https://icons.example/x.png"},
            "link": f"https://{source.lower().replace(' ', '')}.example/article/{i}", "date": date, "snippet": snippet}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.json"):
        f.unlink()
    plan = build_plan(demo_profile(), budget=30)  # build every task the demo could ever request
    entries: list[dict] = []

    def save(name: str, engine: str, params: dict, payload: dict) -> None:
        (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        entries.append({"engine": engine, "params": canonical_params(engine, params), "file": name})

    shop_map = {"packaged_snacks": (SNACKS, "snacks"), "coffee_tea": (COFFEE, "coffee"), "premium_pantry": (HONEY, "honey")}
    for t in plan.planned + plan.skipped:
        if t.engine == "google_shopping":
            items, slug = shop_map[t.focus]
            save(f"google_shopping__{slug}_in.json", t.engine, t.params, shopping(t.params["q"], items, f"shop-{slug}"))
        elif t.engine == "google":
            rows = {
                "packaged_snacks": [
                    ("Crunch Theory – Roasted Makhana & Healthy Snacks", "https://crunchtheory.example/", "Shop roasted makhana and healthy snack packs, baked not fried.", "Crunch Theory"),
                    ("Makhana Mill | Healthy Snack Brand from Bihar", "https://makhanamill.example/", "Fox-nut snacks in four flavours. Free shipping over ₹499.", "Makhana Mill"),
                    ("Top 12 Healthy Snack Brands in India (2026)", "https://foodjournal.example/healthy-snack-brands", "A roundup of popular healthy snack brands and what they sell.", "Food Journal"),
                    ("GoodGrain Co. – Millet Chips & Healthy Snacks", "https://goodgrain.example/", "Ragi and multigrain chips made with millets.", "GoodGrain Co."),
                    ("Buy Healthy Snacks Online", "https://www.amazon.in/s?k=healthy+snacks", "Shop healthy snacks on Amazon.in.", "Amazon.in"),
                    ("Trailblaze Foods – Trail Mix, Seeds & Healthy Snacks", "https://trailblazefoods.example/", "Trail mixes and seed blends for snacking.", "Trailblaze Foods"),
                    ("Healthy snacking: industry report summary", "https://dailycommercewire.example/healthy-snacking-report", "Commentary on the packaged healthy snacks segment.", "Daily Commerce Wire"),
                ],
                "coffee_tea": [
                    ("Kaapi Trail | Specialty Coffee Roasters – Fresh Coffee Beans", "https://kaapitrail.example/", "Estate coffee beans roasted to order and shipped across India.", "Kaapi Trail"),
                    ("Blue Hills Roasters – Single Origin Coffee from Indian Estates", "https://bluehillsroasters.example/", "Single origin specialty coffee, whole bean or ground.", "Blue Hills Roasters"),
                    ("Top 15 Specialty Coffee Brands in India (2026 Guide)", "https://foodjournal.example/specialty-coffee-brands", "Our guide to specialty coffee brands worth trying.", "Food Journal"),
                    ("Monsoon Bean Co. – Shop Coffee", "https://monsoonbean.example/shop", "Monsooned Malabar and estate coffee beans.", "Monsoon Bean Co."),
                    ("Third Crack Coffee — Roastery & Coffee Subscriptions", "https://thirdcrackcoffee.example/", "Coffee subscriptions delivered every month.", "Third Crack Coffee"),
                    ("Buy Coffee Beans Online", "https://www.amazon.in/s?k=coffee+beans", "Shop coffee beans on Amazon.in.", "Amazon.in"),
                    ("Specialty coffee in India: market overview", "https://dailycommercewire.example/coffee-market-overview", "How the coffee segment is evolving.", "Daily Commerce Wire"),
                    ("Estate Brew Coffee Co. – Filter Coffee Beans", "https://estatebrew.example/", "Filter coffee beans and blends.", "Estate Brew"),
                ],
                "premium_pantry": [
                    ("Pantry Atelier – Gourmet Honey, Preserves & Pantry", "https://pantryatelier.example/", "Single-estate honey and small-batch preserves.", "Pantry Atelier"),
                    ("Wildbloom Honey | Raw Forest Honey", "https://wildbloomhoney.example/", "Raw, unprocessed forest honey in glass jars.", "Wildbloom Honey"),
                    ("Best Gourmet Pantry Brands in India", "https://foodjournal.example/gourmet-pantry", "Our pick of gourmet pantry brands.", "Food Journal"),
                    ("Nectar & Co. – Rare Honeys", "https://nectar.example/", "Acacia, jamun and other rare honey varieties.", "Nectar & Co."),
                    ("Buy Honey Online at BigBasket", "https://www.bigbasket.com/ps/?q=honey", "Shop honey brands on BigBasket.", "BigBasket"),
                    ("BeeKind Organics – Organic Honey & Spreads", "https://beekindorganics.example/", "Certified organic raw honey.", "BeeKind Organics"),
                ],
            }[t.focus]
            save(f"google__{t.focus}_in.json", t.engine, t.params, organic(t.params["q"], rows, f"web-{t.focus}"))
        elif t.engine == "google_news":
            items = [
                news_item(1, "Crunch Theory launches baked makhana range in 40 cities", "Daily Commerce Wire", "09/22/2026, 07:00 AM, +0000 UTC",
                          "The snack brand introduced three new flavours for quick-commerce channels."),
                news_item(2, "Coffee bean prices climb as harvest shortfall tightens supply", "Agri Markets Today", "09/15/2026, 09:30 AM, +0000 UTC",
                          "Exporters report higher green coffee costs after an uneven monsoon."),
                news_item(3, "Kaapi Trail raises seed funding to expand roasting capacity", "Startup Ledger", "09/03/2026, 11:00 AM, +0000 UTC",
                          "The specialty roaster will add a second roasting unit."),
                news_item(4, "Regulator proposes stricter front-of-pack labelling for packaged foods", "Policy Desk Daily", "08/27/2026, 06:15 AM, +0000 UTC",
                          "Draft rules would require clearer nutrition labels on packaged snacks."),
                news_item(5, "D2C food brands could see higher ad costs this festive season, analysts say", "Daily Commerce Wire", "08/18/2026, 08:00 AM, +0000 UTC",
                          "Analysts expect competition for festive-season advertising."),
                news_item(6, "Wildbloom Honey introduces glass-jar gift boxes", "Retail Pulse", "08/02/2026, 10:00 AM, +0000 UTC",
                          "The honey brand unveiled gift packaging for corporate orders."),
                news_item(7, "Honey adulteration tests: what buyers should know", "Consumer Watch", "01/12/2026, 05:00 AM, +0000 UTC",
                          "An explainer on purity testing for honey."),
            ]
            items[1]["stories"] = [news_item(8, "Green coffee import duty review under discussion", "Policy Desk Daily",
                                             "09/10/2026, 07:45 AM, +0000 UTC", "Industry groups seek a review of duties.")]
            save("google_news__packaged_food_in.json", t.engine, t.params,
                 {"search_metadata": meta("google_news", "news-food-in"),
                  "search_parameters": {"engine": "google_news", **t.params}, "news_results": items})
        elif t.engine == "amazon":
            def az(i, title, brand, price, rating, reviews, sponsored=False, old=None):
                r = {"position": i, "asin": f"B0DEMO{i:04d}", "title": title, "brand": brand,
                     "link_clean": f"https://amazon-in.example/dp/B0DEMO{i:04d}", "price": f"₹{price:,}",
                     "extracted_price": float(price), "rating": rating, "reviews": reviews, "sponsored": sponsored,
                     "delivery": ["FREE delivery Tue, 6 Oct"]}
                if old:
                    r["old_price"], r["extracted_old_price"] = f"₹{old:,}", float(old)
                return r
            save("amazon__snacks_in.json", t.engine, t.params,
                 {"search_metadata": meta("amazon", "amazon-snacks"), "search_parameters": {"engine": "amazon", **t.params},
                  "organic_results": [
                      az(1, "Crunch Theory Roasted Makhana Cream & Onion 4 x 30g", "Crunch Theory", 189, 4.3, 5120, sponsored=True),
                      az(2, "Makhana Mill Pudina Makhana 80g", "Makhana Mill", 139, 4.1, 1840),
                      az(3, "Healthy Snack Combo Pack of 5 Assorted", None, 499, 3.9, 260, old=649),
                      az(4, "Trailblaze Foods Cranberry Trail Mix 200g", "Trailblaze Foods", 225, 4.4, 980),
                      az(5, "Peppy Pulses Masala Chana 150g", "Peppy Pulses", 99, 4.0, 720),
                      az(6, "Little Millet Co. Ragi Puffs 100g", None, 125, 4.0, 95),
                  ]})
        elif t.engine == "google_trends" and t.params.get("data_type") == "TIMESERIES":
            save("google_trends__timeseries_in.json", t.engine, t.params,
                 {"search_metadata": meta("google_trends", "trends-ts-in", {"google_trends_url": "https://trends.google.com/trends/explore?geo=IN"}),
                  "search_parameters": {"engine": "google_trends", **t.params},
                  "interest_over_time": {"timeline_data": trends_series()}})
        elif t.engine == "google_autocomplete":
            save("google_autocomplete__healthy_snacks_in.json", t.engine, t.params,
                 {"search_metadata": meta("google_autocomplete", "ac-snacks"), "search_parameters": {"engine": "google_autocomplete", **t.params},
                  "suggestions": [{"value": v, "relevance": 600 - 10 * i, "type": "QUERY"} for i, v in enumerate(
                      ["healthy snacks for weight loss", "healthy snacks online", "healthy snacks for kids",
                       "healthy snacks brands in india", "healthy snacks for office"])]})

    # Dependent requests: product details (top-reviewed listing per focus) and related queries (top mean term)
    for pid, title, brand, price, rating, reviews, sellers, desc in [
        ("7400100000000000101", "Crunch Theory Roasted Makhana Peri Peri 4 x 30g", "Crunch Theory", 199, 4.4, 2310,
         [("Crunch Theory", 199, 0), ("Amazon.in", 189, 0), ("BigBasket", 205, 30)], "Roasted fox nuts, 4 single-serve packs."),
        ("7400200000000000201", "Kaapi Trail Attikan Estate Medium Roast Coffee Beans 250g", "Kaapi Trail", 649, 4.6, 1840,
         [("Kaapi Trail", 649, 0), ("Amazon.in", 699, 0), ("Flipkart", 675, 40)], "Medium roast arabica whole beans."),
        ("7400300000000000301", "Wildbloom Honey Raw Forest Honey 500g", "Wildbloom Honey", 549, 4.5, 760,
         [("Wildbloom Honey", 549, 0), ("BigBasket", 565, 0)], "Raw forest honey in a glass jar."),
    ]:
        params = {"product_id": pid, "offer_view": "true", "gl": "in", "hl": "en"}
        save(f"google_product__{pid}.json", "google_product", params, product(pid, title, brand, price, rating, reviews, sellers, desc))

    from app.intelligence.trends import summarize_series
    timeline = trends_series()
    points = [{"date": r["date"], "partial": r.get("partial_data", False),
               **{v["query"]: v["extracted_value"] for v in r["values"]}} for r in timeline]
    top_term = max(["healthy snacks", "coffee beans", "organic honey"], key=lambda q: summarize_series(q, points).mean)
    related = {
        "healthy snacks": (["healthy snacks for weight loss", "healthy snacks online", "makhana", "protein snacks", "millet snacks"],
                           ["makhana snacks", "millet chips", "protein chips"]),
        "coffee beans": (["coffee beans price", "arabica coffee beans", "coffee beans online", "filter coffee", "cold brew coffee"],
                         ["cold brew coffee beans", "single origin coffee", "coffee subscription"]),
        "organic honey": (["raw honey", "organic honey price", "honey 1kg", "forest honey", "manuka honey"],
                          ["raw forest honey", "jamun honey", "honey gift box"]),
    }[top_term]
    params = {"q": top_term, "geo": "IN", "date": "today 12-m", "data_type": "RELATED_QUERIES"}
    save("google_trends__related_in.json", "google_trends", params, {
        "search_metadata": meta("google_trends", "trends-related-in"), "search_parameters": {"engine": "google_trends", **params},
        "related_queries": {
            "top": [{"query": q, "value": str(100 - i * 13), "extracted_value": 100 - i * 13} for i, q in enumerate(related[0])],
            "rising": [{"query": q, "value": f"+{350 - i * 90}%", "extracted_value": 350 - i * 90} for i, q in enumerate(related[1])],
        }})

    manifest = {"version": "v1", "synthetic": True, "created_at": CREATED, "note": NOTE,
                "generator": "scripts/build_demo_fixtures.py", "profile": "demo_profile() – section 14 of the brief",
                "entries": sorted(entries, key=lambda e: e["file"])}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} fixtures to {OUT} (top trend term: {top_term})")


if __name__ == "__main__":
    main()
