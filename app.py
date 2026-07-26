import requests
import pandas as pd
import streamlit as st

BASE_URL = "https://api.india.delta.exchange/v2"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "streamlit-option-chain-app"
}

st.set_page_config(page_title="Delta BTC Option Chain", layout="wide")
st.title("Delta Exchange BTC Option Chain")

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

try:
    products = fetch_all_products()
    expiries = get_btc_expiries(products)

    if not expiries:
        st.error("No BTC option expiries found.")
        st.stop()

    selected_expiry = st.selectbox("Select expiry", expiries, index=0)
    option_rows = fetch_option_chain("BTC", selected_expiry)
    chain = build_chain_table(option_rows)

    st.caption(f"Rows fetched: {len(option_rows)}")

    if option_rows:
        spot_candidates = pd.to_numeric(
            pd.DataFrame(option_rows).get("spot_price"),
            errors="coerce"
        ).dropna()

        if not spot_candidates.empty:
            st.metric("Spot Price", f"{spot_candidates.iloc[0]:,.2f}")

    st.dataframe(chain, use_container_width=True, height=700)

    csv = chain.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download option chain CSV",
        data=csv,
        file_name=f"delta_btc_option_chain_{selected_expiry}.csv",
        mime="text/csv"
    )

except requests.HTTPError as e:
    st.error(f"HTTP error: {e}")
except Exception as e:
    st.error(f"Error: {e}")