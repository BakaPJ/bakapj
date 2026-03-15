# app.py
import streamlit as st
import pandas as pd
import datetime as dt
import threading
import time
import json
from pathlib import Path

# ========== CONFIGURATION ==========
DATA_FILE = Path("products_history.json")  # stored history (for 1 week de-dup logic)
VAT_RATE = 0.20  # 20% VAT example; adjust as needed
TARGET_MARGIN = 0.30  # assumed profit margin percentage for demo

# ========== HELPER: LOAD / SAVE HISTORY ==========

def load_history():
    if DATA_FILE.exists():
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return []  # list of records

def save_history(history):
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# ========== HELPER: VAT & PROFIT CALCS ==========

def calculate_vat(price, vat_rate=VAT_RATE):
    """Return VAT amount and price including VAT."""
    vat_amount = price * vat_rate
    price_with_vat = price + vat_amount
    return vat_amount, price_with_vat

def estimate_profit(price, target_margin=TARGET_MARGIN):
    """Very simple profit estimation: assume a flat margin on selling price."""
    profit = price * target_margin
    return profit

# ========== AGENT: FETCH & FILTER PRODUCTS ==========

def fetch_best_sellers():
    """
    Placeholder agent that 'scans the net'.
    Replace this with your own API calls or data-pull logic.
    It must return a list of dicts with:
        name, niche, price, url, sold_last_30_days
    """

    # DEMO DATA ONLY – replace with real source
    demo_products = [
        {"name": "Yoga Mat Pro", "niche": "Fitness", "price": 19.99, "url": "https://example.com/yoga-mat", "sold_last_30_days": 500},
        {"name": "Adjustable Dumbbells", "niche": "Fitness", "price": 39.99, "url": "https://example.com/dumbbells", "sold_last_30_days": 420},
        {"name": "Resistance Bands Set", "niche": "Fitness", "price": 15.50, "url": "https://example.com/bands", "sold_last_30_days": 380},
        {"name": "Ceramic Coffee Grinder", "niche": "Kitchen", "price": 24.99, "url": "https://example.com/grinder", "sold_last_30_days": 280},
        {"name": "Stainless Steel French Press", "niche": "Kitchen", "price": 29.99, "url": "https://example.com/french-press", "sold_last_30_days": 260},
        {"name": "Ergonomic Mouse", "niche": "Office", "price": 25.00, "url": "https://example.com/mouse", "sold_last_30_days": 310},
        {"name": "Mechanical Keyboard", "niche": "Office", "price": 40.00, "url": "https://example.com/keyboard", "sold_last_30_days": 450},
        {"name": "Noise Cancelling Earbuds", "niche": "Electronics", "price": 34.99, "url": "https://example.com/earbuds", "sold_last_30_days": 600},
        {"name": "LED Desk Lamp", "niche": "Home Decor", "price": 18.99, "url": "https://example.com/lamp", "sold_last_30_days": 230},
        {"name": "Minimalist Wall Clock", "niche": "Home Decor", "price": 22.50, "url": "https://example.com/clock", "sold_last_30_days": 210},
    ]
    return demo_products

def filter_and_rank_products(products, min_price=15, max_price=40, top_niches=5, products_per_niche=5):
    """
    Filter by price and select top-selling products grouped by niche.
    Returns a list of dicts enriched with VAT and profit data.
    """
    # Filter by price range
    filtered = [p for p in products if min_price <= p["price"] <= max_price]

    # Group by niche and sort by sold_last_30_days
    by_niche = {}
    for p in filtered:
        niche = p["niche"]
        by_niche.setdefault(niche, [])
        by_niche[niche].append(p)

    result_rows = []
    for niche, items in by_niche.items():
        # sort descending by sold_last_30_days
        items_sorted = sorted(items, key=lambda x: x["sold_last_30_days"], reverse=True)
        for item in items_sorted[:products_per_niche]:
            vat_amount, price_with_vat = calculate_vat(item["price"])
            profit = estimate_profit(item["price"])
            result_rows.append({
                "run_date": dt.datetime.utcnow().isoformat(),
                "niche": niche,
                "product_name": item["name"],
                "price": round(item["price"], 2),
                "vat_amount": round(vat_amount, 2),
                "price_with_vat": round(price_with_vat, 2),
                "estimated_profit": round(profit, 2),
                "sold_last_30_days": item["sold_last_30_days"],
                "url": item["url"],
            })

    # Sort all products by sold_last_30_days and pick niches with best sellers first
    result_rows = sorted(result_rows, key=lambda x: x["sold_last_30_days"], reverse=True)

    # Limit to 5 niches (top_niches) if there are more
    seen_niches = set()
    final_rows = []
    for row in result_rows:
        if row["niche"] not in seen_niches:
            if len(seen_niches) >= top_niches:
                continue
            seen_niches.add(row["niche"])
        final_rows.append(row)

    return final_rows

# ========== DE-DUP LOGIC (NO 70% REPEAT IN 1 WEEK) ==========

def filter_by_weekly_uniqueness(new_rows, history, max_repeat_ratio=0.7, days_window=7):
    """
    Ensure that in any 7-day window, at least 30% of products are new
    by limiting repeated products if needed.
    """
    now = dt.datetime.utcnow()
    week_ago = now - dt.timedelta(days=days_window)

    recent = [
        h for h in history
        if dt.datetime.fromisoformat(h["run_date"]) >= week_ago
    ]
    recent_names = {h["product_name"] for h in recent}

    # Quick check: if we repeat too many products, drop some of them
    new_unique = []
    repeated = []
    for row in new_rows:
        if row["product_name"] in recent_names:
            repeated.append(row)
        else:
            new_unique.append(row)

    total_new = len(new_rows)
    max_repeats_allowed = int(total_new * max_repeat_ratio)

    # We can include at most max_repeats_allowed of the repeated ones
    allowed_repeats = repeated[:max_repeats_allowed]

    # Result: all new_unique + some repeated
    final = new_unique + allowed_repeats
    return final

# ========== SCHEDULER THREAD ==========

def daily_job():
    """Job that runs once and stores the results."""
    history = load_history()
    products = fetch_best_sellers()
    ranked = filter_and_rank_products(products)
    filtered = filter_by_weekly_uniqueness(ranked, history)
    # Append to history and save
    history.extend(filtered)
    save_history(history)

def scheduler_loop():
    """Background loop to run daily_job every day at 12:00 (server time)."""
    while True:
        now = dt.datetime.now()
        run_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
        if run_time <= now:
            run_time += dt.timedelta(days=1)
        sleep_seconds = (run_time - now).total_seconds()
        time.sleep(sleep_seconds)
        daily_job()

def start_scheduler_once():
    """Start the scheduler in a background thread (idempotent)."""
    if "scheduler_started" not in st.session_state:
        t = threading.Thread(target=scheduler_loop, daemon=True)
        t.start()
        st.session_state["scheduler_started"] = True

# ========== STREAMLIT UI ==========

def main():
    st.title("Best-Selling Niche Product Agent")
    st.write(
        "This app runs a daily agent that pulls best-selling products, "
        "applies a price filter £15–£40, calculates VAT and estimated profit, "
        "and avoids repeating more than 70% of products in any 7-day window."
    )

    start_scheduler_once()

    # Manual run button
    if st.button("Run agent now"):
        daily_job()
        st.success("Agent run completed and saved to history.")

    history = load_history()
    if not history:
        st.info("No data yet. Wait for the daily run at 12:00 or click 'Run agent now'.")
        return

    df = pd.DataFrame(history)

    # Filters in UI
    st.subheader("History viewer")
    min_date = df["run_date"].min()
    max_date = df["run_date"].max()

    start_date = st.date_input("Start date", value=dt.date.fromisoformat(min_date[:10]))
    end_date = st.date_input("End date", value=dt.date.fromisoformat(max_date[:10]))

    mask = (pd.to_datetime(df["run_date"]).dt.date >= start_date) & (
        pd.to_datetime(df["run_date"]).dt.date <= end_date
    )
    df_filtered = df[mask].copy()

    selected_niches = st.multiselect(
        "Filter by niche", options=sorted(df_filtered["niche"].unique())
    )
    if selected_niches:
        df_filtered = df_filtered[df_filtered["niche"].isin(selected_niches)]

    st.write("Results:")
    st.dataframe(df_filtered.sort_values("run_date", ascending=False))

    # Option to download as CSV
    csv = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download current view as CSV",
        data=csv,
        file_name="products_history_filtered.csv",
        mime="text/csv",
    )

DATA_FILE = Path("products_history.json")
VAT_RATE = 0.20
TARGET_MARGIN = 0.30

def load_history():
    if DATA_FILE.exists():
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(history):
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def calculate_vat(price, vat_rate=VAT_RATE):
    vat_amount = price * vat_rate
    price_with_vat = price + vat_amount
    return vat_amount, price_with_vat

def estimate_profit(price, target_margin=TARGET_MARGIN):
    return price * target_margin

# ---------- UPDATED: include sales_rank & review_count ----------
def fetch_best_sellers():
    """
    Replace this stub with real data source.
    Must return list of dicts:
    name, niche, price, url, sold_last_30_days, sales_rank, review_count
    """

    demo_products = [
        {
            "name": "Yoga Mat Pro",
            "niche": "Fitness",
            "price": 19.99,
            "url": "https://example.com/yoga-mat",
            "sold_last_30_days": 500,
            "sales_rank": 1200,         # lower = better
            "review_count": 850,
        },
        {
            "name": "Adjustable Dumbbells",
            "niche": "Fitness",
            "price": 39.99,
            "url": "https://example.com/dumbbells",
            "sold_last_30_days": 420,
            "sales_rank": 2500,
            "review_count": 620,
        },
        {
            "name": "Resistance Bands Set",
            "niche": "Fitness",
            "price": 15.50,
            "url": "https://example.com/bands",
            "sold_last_30_days": 380,
            "sales_rank": 3100,
            "review_count": 410,
        },
        {
            "name": "Ceramic Coffee Grinder",
            "niche": "Kitchen",
            "price": 24.99,
            "url": "https://example.com/grinder",
            "sold_last_30_days": 280,
            "sales_rank": 5200,
            "review_count": 190,
        },
        {
            "name": "Stainless Steel French Press",
            "niche": "Kitchen",
            "price": 29.99,
            "url": "https://example.com/french-press",
            "sold_last_30_days": 260,
            "sales_rank": 6100,
            "review_count": 230,
        },
        {
            "name": "Ergonomic Mouse",
            "niche": "Office",
            "price": 25.00,
            "url": "https://example.com/mouse",
            "sold_last_30_days": 310,
            "sales_rank": 4300,
            "review_count": 340,
        },
        {
            "name": "Mechanical Keyboard",
            "niche": "Office",
            "price": 40.00,
            "url": "https://example.com/keyboard",
            "sold_last_30_days": 450,
            "sales_rank": 2100,
            "review_count": 900,
        },
        {
            "name": "Noise Cancelling Earbuds",
            "niche": "Electronics",
            "price": 34.99,
            "url": "https://example.com/earbuds",
            "sold_last_30_days": 600,
            "sales_rank": 800,
            "review_count": 1500,
        },
        {
            "name": "LED Desk Lamp",
            "niche": "Home Decor",
            "price": 18.99,
            "url": "https://example.com/lamp",
            "sold_last_30_days": 230,
            "sales_rank": 7200,
            "review_count": 260,
        },
        {
            "name": "Minimalist Wall Clock",
            "niche": "Home Decor",
            "price": 22.50,
            "url": "https://example.com/clock",
            "sold_last_30_days": 210,
            "sales_rank": 7900,
            "review_count": 140,
        },
    ]
    return demo_products

def filter_and_rank_products(
    products, min_price=15, max_price=40, top_niches=5, products_per_niche=5
):
    filtered = [p for p in products if min_price <= p["price"] <= max_price]

    by_niche = {}
    for p in filtered:
        by_niche.setdefault(p["niche"], [])
        by_niche[p["niche"]].append(p)

    result_rows = []
    for niche, items in by_niche.items():
        # Example ranking: by sold_last_30_days first, then by sales_rank
        items_sorted = sorted(
            items,
            key=lambda x: (-x["sold_last_30_days"], x["sales_rank"])
        )
        for item in items_sorted[:products_per_niche]:
            vat_amount, price_with_vat = calculate_vat(item["price"])
            profit = estimate_profit(item["price"])
            result_rows.append(
                {
                    "run_date": dt.datetime.utcnow().isoformat(),
                    "niche": niche,
                    "product_name": item["name"],
                    "price": round(item["price"], 2),
                    "vat_amount": round(vat_amount, 2),
                    "price_with_vat": round(price_with_vat, 2),
                    "estimated_profit": round(profit, 2),
                    "sold_last_30_days": item["sold_last_30_days"],
                    "sales_rank": item["sales_rank"],
                    "review_count": item["review_count"],
                    "url": item["url"],
                }
            )

    result_rows = sorted(
        result_rows,
        key=lambda x: (-x["sold_last_30_days"], x["sales_rank"])
    )

    seen_niches = set()
    final_rows = []
    for row in result_rows:
        if row["niche"] not in seen_niches:
            if len(seen_niches) >= top_niches:
                continue
            seen_niches.add(row["niche"])
        final_rows.append(row)

    return final_rows

def filter_by_weekly_uniqueness(new_rows, history, max_repeat_ratio=0.7, days_window=7):
    now = dt.datetime.utcnow()
    week_ago = now - dt.timedelta(days=days_window)

    recent = [
        h for h in history
        if dt.datetime.fromisoformat(h["run_date"]) >= week_ago
    ]
    recent_names = {h["product_name"] for h in recent}

    new_unique = []
    repeated = []
    for row in new_rows:
        if row["product_name"] in recent_names:
            repeated.append(row)
        else:
            new_unique.append(row)

    total_new = len(new_rows)
    max_repeats_allowed = int(total_new * max_repeat_ratio)
    allowed_repeats = repeated[:max_repeats_allowed]
    final = new_unique + allowed_repeats
    return final

def daily_job():
    history = load_history()
    products = fetch_best_sellers()
    ranked = filter_and_rank_products(products)
    filtered = filter_by_weekly_uniqueness(ranked, history)
    history.extend(filtered)
    save_history(history)

def scheduler_loop():
    while True:
        now = dt.datetime.now()
        run_time = now.replace(hour=12, minute=0, second=0, microsecond=0)
        if run_time <= now:
            run_time += dt.timedelta(days=1)
        sleep_seconds = (run_time - now).total_seconds()
        time.sleep(sleep_seconds)
        daily_job()

def start_scheduler_once():
    if "scheduler_started" not in st.session_state:
        t = threading.Thread(target=scheduler_loop, daemon=True)
        t.start()
        st.session_state["scheduler_started"] = True

def main():
    st.title("Best-Selling Niche Product Agent")
    st.write(
        "Daily agent with price filter, VAT & profit, sales rank and review count, "
        "avoiding >70% repeated products over 7 days."
    )

    start_scheduler_once()

    if st.button("Run agent now"):
        daily_job()
        st.success("Agent run completed and saved to history.")

    history = load_history()
    if not history:
        st.info("No data yet. Wait for the daily run at 12:00 or use 'Run agent now'.")
        return

    df = pd.DataFrame(history)

    st.subheader("History viewer")
    min_date = df["run_date"].min()
    max_date = df["run_date"].max()

    start_date = st.date_input("Start date", value=dt.date.fromisoformat(min_date[:10]))
    end_date = st.date_input("End date", value=dt.date.fromisoformat(max_date[:10]))

    mask = (pd.to_datetime(df["run_date"]).dt.date >= start_date) & (
        pd.to_datetime(df["run_date"]).dt.date <= end_date
    )
    df_filtered = df[mask].copy()

    selected_niches = st.multiselect(
        "Filter by niche", options=sorted(df_filtered["niche"].unique())
    )
    if selected_niches:
        df_filtered = df_filtered[df_filtered["niche"].isin(selected_niches)]

    # You now see sales_rank and review_count in the table too
    st.write("Results (includes sales rank and review count):")
    st.dataframe(
        df_filtered.sort_values("run_date", ascending=False)[
            [
                "run_date",
                "niche",
                "product_name",
                "price",
                "vat_amount",
                "price_with_vat",
                "estimated_profit",
                "sold_last_30_days",
                "sales_rank",
                "review_count",
                "url",
            ]
        ]
    )

    csv = df_filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download current view as CSV",
        data=csv,
        file_name="products_history_filtered.csv",
        mime="text/csv",
    )

if __name__ == "__main__":
    main()
