# app.py
import streamlit as st
import datetime as dt
import json
import os
from typing import List, Dict

DATA_FILE = "product_history.json"
VAT_RATE = 0.20  # 20% VAT for UK, change if needed

# ---------- Utility: load / save history ----------

def load_history() -> Dict:
    if not os.path.exists(DATA_FILE):
        return {"days": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_history(history: Dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

def get_last_7_days(history: Dict) -> List[Dict]:
    today = dt.date.today()
    cutoff = today - dt.timedelta(days=7)
    return [d for d in history["days"] if dt.date.fromisoformat(d["date"]) >= cutoff]

# ---------- VAT / profit helpers ----------

def add_vat(price_ex_vat: float, vat_rate: float = VAT_RATE) -> float:
    return round(price_ex_vat * (1 + vat_rate), 2)

def remove_vat(price_inc_vat: float, vat_rate: float = VAT_RATE) -> float:
    return round(price_inc_vat / (1 + vat_rate), 2)

def compute_profit(sell_price_inc_vat: float, cost_price_inc_vat: float, vat_rate: float = VAT_RATE) -> Dict[str, float]:
    sell_ex = remove_vat(sell_price_inc_vat, vat_rate)
    cost_ex = remove_vat(cost_price_inc_vat, vat_rate)
    profit_ex = round(sell_ex - cost_ex, 2)
    margin = round(profit_ex / sell_ex * 100, 2) if sell_ex > 0 else 0.0
    return {
        "sell_ex_vat": sell_ex,
        "cost_ex_vat": cost_ex,
        "profit_ex_vat": profit_ex,
        "margin_percent": margin,
    }

# ---------- AGENT: placeholder web‑scraper ----------

def fetch_best_selling_niches_last_month(
    min_price: float = 15.0,
    max_price: float = 40.0,
    limit: int = 20,
) -> List[Dict]:
    """
    TODO: Replace this dummy function with real scraping/API calls.
    For example, you could query an Amazon Best Sellers API and filter by:
        - price between min_price and max_price
        - last 30 days best sellers / trending categories.[web:2]

    Return format:
        [
          {
            "id": "unique-product-id",
            "name": "Product Name",
            "niche": "Category/Niche",
            "price_inc_vat": 19.99,
            "estimated_cost_inc_vat": 10.00
          },
          ...
        ]
    """
    # Dummy data to keep the app runnable
    demo = []
    for i in range(limit):
        price = min_price + (max_price - min_price) * (i / max(1, limit - 1))
        demo.append(
            {
                "id": f"demo-{i}",
                "name": f"Demo Product {i+1}",
                "niche": f"Niche {(i % 5) + 1}",
                "price_inc_vat": round(price, 2),
                "estimated_cost_inc_vat": round(price * 0.6, 2),
            }
        )
    return demo

# ---------- Filtering: avoid 70% repetition over 1 week ----------

def filter_new_products(
    candidates: List[Dict],
    history: Dict,
    max_size: int = 5,
    max_overlap_ratio: float = 0.7,
) -> List[Dict]:
    last_7 = get_last_7_days(history)
    seen_ids = set()
    for day in last_7:
        for p in day["products"]:
            seen_ids.add(p["id"])

    # First pass: prefer unseen products
    unseen = [p for p in candidates if p["id"] not in seen_ids]
    selected = unseen[:max_size]

    # If not enough unseen, allow some repeats but control overlap
    if len(selected) < max_size:
        remaining_slots = max_size - len(selected)
        repeats = [p for p in candidates if p["id"] in seen_ids and p not in selected]
        for p in repeats:
            # Check overlap if we include this product
            temp_selected_ids = {x["id"] for x in selected} | {p["id"]}
            overlap_count = len(temp_selected_ids & seen_ids)
            overlap_ratio = overlap_count / max_size
            if overlap_ratio <= max_overlap_ratio:
                selected.append(p)
                if len(selected) >= max_size:
                    break

    return selected

# ---------- Daily update logic ----------

def run_daily_agent() -> List[Dict]:
    history = load_history()
    today = dt.date.today().isoformat()

    # If today's products already exist, just return them
    for day in history["days"]:
        if day["date"] == today:
            return day["products"]

    # Fetch candidates
    candidates = fetch_best_selling_niches_last_month()

    # Filter to 5 products with low repetition vs last 7 days
    todays_products = filter_new_products(candidates, history, max_size=5)

    # Attach profit info
    for p in todays_products:
        profit = compute_profit(
            sell_price_inc_vat=p["price_inc_vat"],
            cost_price_inc_vat=p["estimated_cost_inc_vat"],
        )
        p["profit_ex_vat"] = profit["profit_ex_vat"]
        p["margin_percent"] = profit["margin_percent"]
        p["sell_ex_vat"] = profit["sell_ex_vat"]
        p["cost_ex_vat"] = profit["cost_ex_vat"]

    # Save to history
    history["days"].append(
        {
            "date": today,
            "products": todays_products,
        }
    )
    save_history(history)
    return todays_products

# ---------- Streamlit UI ----------

def main():
    st.set_page_config(page_title="Best‑Selling Niches Agent", layout="wide")
    st.title("Best‑Selling Niches Agent (15–40 £)")

    st.markdown(
        "This app shows 5 niches/products in the £15–40 range, "
        "with estimated profit and VAT breakdown, and keeps a 7‑day history."
    )

    # Manual run button
    if st.button("Run Agent Now"):
        products = run_daily_agent()
        st.success("Agent run completed.")
    else:
        history = load_history()
        today = dt.date.today().isoformat()
        today_entry = next((d for d in history["days"] if d["date"] == today), None)
        products = today_entry["products"] if today_entry else []

    if products:
        st.subheader("Today's picks")
        for p in products:
            with st.expander(f"{p['name']} ({p['niche']})"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Price inc VAT (£)", p["price_inc_vat"])
                    st.metric("Price ex VAT (£)", p["sell_ex_vat"])
                with col2:
                    st.metric("Cost inc VAT (£)", p["estimated_cost_inc_vat"])
                    st.metric("Cost ex VAT (£)", p["cost_ex_vat"])
                with col3:
                    st.metric("Profit ex VAT (£)", p["profit_ex_vat"])
                    st.metric("Margin (%)", p["margin_percent"])
    else:
        st.info("No products for today yet. Click 'Run Agent Now' to generate.")

    st.markdown("---")
    st.subheader("History (last 7 days)")
    history = load_history()
    last_7 = get_last_7_days(history)
    for day in sorted(last_7, key=lambda d: d["date"], reverse=True):
        st.markdown(f"**{day['date']}**")
        for p in day["products"]:
            st.write(
                f"- {p['name']} ({p['niche']}) – £{p['price_inc_vat']} inc VAT, "
                f"profit ex VAT £{p['profit_ex_vat']} (margin {p['margin_percent']}%)"
            )

if __name__ == "__main__":
    main()
