import math
import requests
import pandas as pd
import streamlit as st

BASE_URL = "https://api.india.delta.exchange/v2"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "streamlit-option-chain-app"
}

st.set_page_config(page_title="Delta BTC Ratio Spread Scanner", layout="wide")
st.title("Delta Exchange BTC Ratio Spread Opportunity Scanner")

# -----------------------------
# ORIGINAL OPTION CHAIN CODE
# kept intact in logic and structure
# -----------------------------
@st.cache_data(ttl=30)
def fetch_all_products():
    all_rows = []
    after = None

    while True:
        params = {
            "contract_types": "call_options,put_options",
            "states": "live",
            "page_size": 100
        }
        if after:
            params["after"] = after

        r = requests.get(
            f"{BASE_URL}/products",
            params=params,
            headers=HEADERS,
            timeout=20
        )
        r.raise_for_status()
        data = r.json()

        rows = data.get("result", [])
        all_rows.extend(rows)

        meta = data.get("meta", {}) or {}
        after = meta.get("after")

        if not after or not rows:
            break

    return all_rows

@st.cache_data(ttl=15)
def fetch_option_chain(underlying="BTC", expiry_date=None):
    params = {
        "contract_types": "call_options,put_options",
        "underlying_asset_symbols": underlying
    }
    if expiry_date:
        params["expiry_date"] = expiry_date

    r = requests.get(
        f"{BASE_URL}/tickers",
        params=params,
        headers=HEADERS,
        timeout=20
    )
    r.raise_for_status()
    data = r.json()
    return data.get("result", [])

def get_btc_expiries(products):
    expiries = set()

    for p in products:
        if p.get("contract_type") not in ["call_options", "put_options"]:
            continue

        symbol = p.get("symbol", "")
        if "-BTC-" not in symbol:
            continue

        settlement_time = p.get("settlement_time")
        if settlement_time:
            try:
                dt = pd.to_datetime(settlement_time, utc=True)
                expiries.add(dt.strftime("%d-%m-%Y"))
            except Exception:
                pass

    return sorted(expiries, key=lambda x: pd.to_datetime(x, format="%d-%m-%Y"))

def build_chain_table(option_rows):
    if not option_rows:
        return pd.DataFrame()

    df = pd.DataFrame(option_rows)

    df["strike_price"] = pd.to_numeric(df.get("strike_price"), errors="coerce")
    df["mark_price"] = pd.to_numeric(df.get("mark_price"), errors="coerce")
    df["spot_price"] = pd.to_numeric(df.get("spot_price"), errors="coerce")
    df["oi"] = pd.to_numeric(df.get("oi"), errors="coerce")
    df["volume"] = pd.to_numeric(df.get("volume"), errors="coerce")

    df["best_bid"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("best_bid")), errors="coerce")
    df["best_ask"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("best_ask")), errors="coerce")
    df["bid_iv"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("bid_iv")), errors="coerce")
    df["ask_iv"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("ask_iv")), errors="coerce")

    df["delta"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("delta")), errors="coerce")
    df["gamma"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("gamma")), errors="coerce")
    df["theta"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("theta")), errors="coerce")
    df["vega"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("vega")), errors="coerce")

    calls = df[df["contract_type"] == "call_options"].copy()
    puts = df[df["contract_type"] == "put_options"].copy()

    calls = calls.rename(columns={
        "symbol": "call_symbol",
        "best_bid": "call_bid",
        "best_ask": "call_ask",
        "mark_price": "call_mark",
        "oi": "call_oi",
        "volume": "call_volume",
        "delta": "call_delta",
        "gamma": "call_gamma",
        "theta": "call_theta",
        "vega": "call_vega",
        "bid_iv": "call_bid_iv",
        "ask_iv": "call_ask_iv"
    })

    puts = puts.rename(columns={
        "symbol": "put_symbol",
        "best_bid": "put_bid",
        "best_ask": "put_ask",
        "mark_price": "put_mark",
        "oi": "put_oi",
        "volume": "put_volume",
        "delta": "put_delta",
        "gamma": "put_gamma",
        "theta": "put_theta",
        "vega": "put_vega",
        "bid_iv": "put_bid_iv",
        "ask_iv": "put_ask_iv"
    })

    merged = pd.merge(
        calls[[
            "strike_price", "spot_price", "call_symbol", "call_bid", "call_ask",
            "call_mark", "call_oi", "call_volume", "call_delta", "call_gamma",
            "call_theta", "call_vega", "call_bid_iv", "call_ask_iv"
        ]],
        puts[[
            "strike_price", "put_symbol", "put_bid", "put_ask", "put_mark",
            "put_oi", "put_volume", "put_delta", "put_gamma", "put_theta",
            "put_vega", "put_bid_iv", "put_ask_iv"
        ]],
        on="strike_price",
        how="outer"
    ).sort_values("strike_price")

    col_order = [
        "call_symbol", "call_bid", "call_ask", "call_mark", "call_oi", "call_volume",
        "call_delta", "call_gamma", "call_theta", "call_vega", "call_bid_iv", "call_ask_iv",
        "strike_price",
        "put_bid", "put_ask", "put_mark", "put_oi", "put_volume",
        "put_delta", "put_gamma", "put_theta", "put_vega", "put_bid_iv", "put_ask_iv", "put_symbol"
    ]

    existing_cols = [c for c in col_order if c in merged.columns]
    merged = merged[existing_cols]

    return merged

# -----------------------------
# ADDED RATIO SPREAD SCANNER
# -----------------------------
def enrich_option_rows(option_rows):
    if not option_rows:
        return pd.DataFrame()

    df = pd.DataFrame(option_rows).copy()

    df["strike_price"] = pd.to_numeric(df.get("strike_price"), errors="coerce")
    df["mark_price"] = pd.to_numeric(df.get("mark_price"), errors="coerce")
    df["spot_price"] = pd.to_numeric(df.get("spot_price"), errors="coerce")
    df["oi"] = pd.to_numeric(df.get("oi"), errors="coerce")
    df["volume"] = pd.to_numeric(df.get("volume"), errors="coerce")

    if "quotes" in df.columns:
        df["best_bid"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("best_bid")), errors="coerce")
        df["best_ask"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("best_ask")), errors="coerce")
        df["bid_iv"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("bid_iv")), errors="coerce")
        df["ask_iv"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("ask_iv")), errors="coerce")
    else:
        df["best_bid"] = pd.NA
        df["best_ask"] = pd.NA
        df["bid_iv"] = pd.NA
        df["ask_iv"] = pd.NA

    if "greeks" in df.columns:
        df["delta"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("delta")), errors="coerce")
        df["gamma"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("gamma")), errors="coerce")
        df["theta"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("theta")), errors="coerce")
        df["vega"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("vega")), errors="coerce")
    else:
        df["delta"] = pd.NA
        df["gamma"] = pd.NA
        df["theta"] = pd.NA
        df["vega"] = pd.NA

    return df

def _premium_sell(row, price_mode="bid"):
    if price_mode == "mid":
        bid = row.get("best_bid")
        ask = row.get("best_ask")
        if pd.notna(bid) and pd.notna(ask):
            return (bid + ask) / 2
    bid = row.get("best_bid")
    mark = row.get("mark_price")
    return bid if pd.notna(bid) else mark

def _premium_buy(row, price_mode="ask"):
    if price_mode == "mid":
        bid = row.get("best_bid")
        ask = row.get("best_ask")
        if pd.notna(bid) and pd.notna(ask):
            return (bid + ask) / 2
    ask = row.get("best_ask")
    mark = row.get("mark_price")
    return ask if pd.notna(ask) else mark

def payoff_call_ratio(spot, long_strike, short_strike, long_qty, short_qty, net_credit):
    long_payoff = max(spot - long_strike, 0) * long_qty
    short_payoff = max(spot - short_strike, 0) * short_qty
    return net_credit + long_payoff - short_payoff

def payoff_put_ratio(spot, long_strike, short_strike, long_qty, short_qty, net_credit):
    long_payoff = max(long_strike - spot, 0) * long_qty
    short_payoff = max(short_strike - spot, 0) * short_qty
    return net_credit + long_payoff - short_payoff

def find_call_ratio_spreads(df, qty_long=1, qty_short=2, min_credit=0.0, min_oi=0, min_volume=0, width_min=1000, width_max=20000, price_mode="natural"):
    calls = df[df["contract_type"] == "call_options"].copy()
    calls = calls.sort_values("strike_price").reset_index(drop=True)

    rows = []
    if calls.empty:
        return pd.DataFrame()

    spot = pd.to_numeric(calls["spot_price"], errors="coerce").dropna()
    spot_value = float(spot.iloc[0]) if not spot.empty else math.nan

    for i in range(len(calls)):
        long_row = calls.iloc[i]
        if long_row.get("oi", 0) < min_oi or long_row.get("volume", 0) < min_volume:
            continue

        for j in range(i + 1, len(calls)):
            short_row = calls.iloc[j]
            if short_row.get("oi", 0) < min_oi or short_row.get("volume", 0) < min_volume:
                continue

            long_k = long_row["strike_price"]
            short_k = short_row["strike_price"]
            width = short_k - long_k

            if pd.isna(long_k) or pd.isna(short_k):
                continue
            if width < width_min or width > width_max:
                continue

            buy_price = _premium_buy(long_row, "ask" if price_mode == "natural" else "mid")
            sell_price = _premium_sell(short_row, "bid" if price_mode == "natural" else "mid")

            if pd.isna(buy_price) or pd.isna(sell_price):
                continue

            net_credit = qty_short * sell_price - qty_long * buy_price
            if net_credit < min_credit:
                continue

            max_profit = net_credit + (short_k - long_k) * qty_long
            upside_be = short_k + max_profit / max(qty_short - qty_long, 1)
            if qty_short > qty_long:
                theoretical_unbounded_loss = True
                worst_case_note = "Unlimited above upper breakeven"
            else:
                theoretical_unbounded_loss = False
                worst_case_note = "Bounded"

            spot_points = sorted(set([
                max(0, spot_value * 0.7) if pd.notna(spot_value) else 0,
                long_k,
                short_k,
                upside_be if pd.notna(upside_be) else short_k,
                (spot_value if pd.notna(spot_value) else short_k) * 1.4
            ]))
            sample_payoffs = [payoff_call_ratio(x, long_k, short_k, qty_long, qty_short, net_credit) for x in spot_points]
            min_sample_payoff = min(sample_payoffs) if sample_payoffs else None

            rows.append({
                "strategy": f"{qty_long}x{int(long_k)}C / -{qty_short}x{int(short_k)}C",
                "type": "Call Ratio Spread",
                "long_symbol": long_row.get("symbol"),
                "short_symbol": short_row.get("symbol"),
                "spot_price": spot_value,
                "long_strike": long_k,
                "short_strike": short_k,
                "width": width,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "net_credit": net_credit,
                "max_profit_at_short_strike": max_profit,
                "upper_breakeven": upside_be,
                "long_delta": long_row.get("delta"),
                "short_delta": short_row.get("delta"),
                "long_oi": long_row.get("oi"),
                "short_oi": short_row.get("oi"),
                "long_volume": long_row.get("volume"),
                "short_volume": short_row.get("volume"),
                "long_iv": long_row.get("ask_iv"),
                "short_iv": short_row.get("bid_iv"),
                "sample_min_payoff": min_sample_payoff,
                "risk_note": worst_case_note,
                "credit_per_width": net_credit / width if width else None,
                "distance_short_from_spot_pct": ((short_k - spot_value) / spot_value * 100) if pd.notna(spot_value) and spot_value else None
            })

    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values(["net_credit", "credit_per_width"], ascending=[False, False]).reset_index(drop=True)
    return res

def find_put_ratio_spreads(df, qty_long=1, qty_short=2, min_credit=0.0, min_oi=0, min_volume=0, width_min=1000, width_max=20000, price_mode="natural"):
    puts = df[df["contract_type"] == "put_options"].copy()
    puts = puts.sort_values("strike_price", ascending=False).reset_index(drop=True)

    rows = []
    if puts.empty:
        return pd.DataFrame()

    spot = pd.to_numeric(puts["spot_price"], errors="coerce").dropna()
    spot_value = float(spot.iloc[0]) if not spot.empty else math.nan

    for i in range(len(puts)):
        long_row = puts.iloc[i]
        if long_row.get("oi", 0) < min_oi or long_row.get("volume", 0) < min_volume:
            continue

        for j in range(i + 1, len(puts)):
            short_row = puts.iloc[j]
            if short_row.get("oi", 0) < min_oi or short_row.get("volume", 0) < min_volume:
                continue

            long_k = long_row["strike_price"]
            short_k = short_row["strike_price"]
            width = long_k - short_k

            if pd.isna(long_k) or pd.isna(short_k):
                continue
            if width < width_min or width > width_max:
                continue

            buy_price = _premium_buy(long_row, "ask" if price_mode == "natural" else "mid")
            sell_price = _premium_sell(short_row, "bid" if price_mode == "natural" else "mid")

            if pd.isna(buy_price) or pd.isna(sell_price):
                continue

            net_credit = qty_short * sell_price - qty_long * buy_price
            if net_credit < min_credit:
                continue

            max_profit = net_credit + (long_k - short_k) * qty_long
            lower_breakeven = short_k - max_profit / max(qty_short - qty_long, 1)
            if qty_short > qty_long:
                theoretical_unbounded_loss = True
                worst_case_note = "Unlimited below lower breakeven"
            else:
                theoretical_unbounded_loss = False
                worst_case_note = "Bounded"

            spot_points = sorted(set([
                0,
                lower_breakeven if pd.notna(lower_breakeven) else 0,
                short_k,
                long_k,
                spot_value if pd.notna(spot_value) else long_k
            ]))
            sample_payoffs = [payoff_put_ratio(x, long_k, short_k, qty_long, qty_short, net_credit) for x in spot_points]
            min_sample_payoff = min(sample_payoffs) if sample_payoffs else None

            rows.append({
                "strategy": f"{qty_long}x{int(long_k)}P / -{qty_short}x{int(short_k)}P",
                "type": "Put Ratio Spread",
                "long_symbol": long_row.get("symbol"),
                "short_symbol": short_row.get("symbol"),
                "spot_price": spot_value,
                "long_strike": long_k,
                "short_strike": short_k,
                "width": width,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "net_credit": net_credit,
                "max_profit_at_short_strike": max_profit,
                "lower_breakeven": lower_breakeven,
                "long_delta": long_row.get("delta"),
                "short_delta": short_row.get("delta"),
                "long_oi": long_row.get("oi"),
                "short_oi": short_row.get("oi"),
                "long_volume": long_row.get("volume"),
                "short_volume": short_row.get("volume"),
                "long_iv": long_row.get("ask_iv"),
                "short_iv": short_row.get("bid_iv"),
                "sample_min_payoff": min_sample_payoff,
                "risk_note": worst_case_note,
                "credit_per_width": net_credit / width if width else None,
                "distance_short_from_spot_pct": ((spot_value - short_k) / spot_value * 100) if pd.notna(spot_value) and spot_value else None
            })

    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values(["net_credit", "credit_per_width"], ascending=[False, False]).reset_index(drop=True)
    return res

def format_numeric_columns(df):
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].round(4)
    return out

# -----------------------------
# UI
# -----------------------------
with st.sidebar:
    st.header("Scanner Settings")
    refresh_seconds = st.slider("Auto refresh seconds", min_value=10, max_value=300, value=30, step=5)
    st.caption("Use the refresh button below to reload live data anytime.")

    strategy_side = st.selectbox("Scan side", ["Call Ratio Spread", "Put Ratio Spread"])
    qty_long = st.number_input("Long quantity", min_value=1, max_value=10, value=1, step=1)
    qty_short = st.number_input("Short quantity", min_value=1, max_value=10, value=2, step=1)
    price_mode = st.selectbox("Premium mode", ["natural", "mid"], index=0)

    min_credit = st.number_input("Minimum net credit", min_value=0.0, value=0.0, step=1.0)
    min_oi = st.number_input("Minimum OI per leg", min_value=0, value=0, step=1)
    min_volume = st.number_input("Minimum volume per leg", min_value=0, value=0, step=1)
    width_min = st.number_input("Minimum strike width", min_value=0, value=1000, step=500)
    width_max = st.number_input("Maximum strike width", min_value=0, value=20000, step=500)
    max_rows = st.slider("Top opportunities", min_value=5, max_value=200, value=30, step=5)

st.markdown(
    f"""
    <script>
        setTimeout(function() {{
            window.location.reload();
        }}, {refresh_seconds * 1000});
    </script>
    """,
    unsafe_allow_html=True,
)

refresh_now = st.button("Refresh now")
if refresh_now:
    st.cache_data.clear()

try:
    products = fetch_all_products()
    expiries = get_btc_expiries(products)

    if not expiries:
        st.error("No BTC option expiries found.")
        st.stop()

    selected_expiry = st.selectbox("Select expiry", expiries, index=0)
    option_rows = fetch_option_chain("BTC", selected_expiry)
    chain = build_chain_table(option_rows)
    option_df = enrich_option_rows(option_rows)

    c1, c2, c3 = st.columns(3)
    c1.metric("Contracts fetched", len(option_rows))

    spot_candidates = pd.to_numeric(
        pd.DataFrame(option_rows).get("spot_price"),
        errors="coerce"
    ).dropna()
    spot_value = float(spot_candidates.iloc[0]) if not spot_candidates.empty else None
    c2.metric("Spot Price", f"{spot_value:,.2f}" if spot_value is not None else "NA")
    c3.metric("Selected Expiry", selected_expiry)

    st.subheader("Opportunity Scanner")
    st.caption("Credit ratio spreads can carry unlimited tail risk on the naked short side. Use position sizing and margin checks.")

    if strategy_side == "Call Ratio Spread":
        opps = find_call_ratio_spreads(
            option_df,
            qty_long=qty_long,
            qty_short=qty_short,
            min_credit=min_credit,
            min_oi=min_oi,
            min_volume=min_volume,
            width_min=width_min,
            width_max=width_max,
            price_mode=price_mode,
        )
    else:
        opps = find_put_ratio_spreads(
            option_df,
            qty_long=qty_long,
            qty_short=qty_short,
            min_credit=min_credit,
            min_oi=min_oi,
      