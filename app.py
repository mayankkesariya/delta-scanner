import requests
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

BASE_URL = "https://api.india.delta.exchange/v2"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "streamlit-option-chain-app"
}

st.set_page_config(page_title="Delta BTC Option Chain", layout="wide")
st.title("Delta Exchange BTC Option Chain")

refresh_options = [5, 10, 15, 30, 60]

bar1, bar2, bar3, bar4 = st.columns([1.2, 1.2, 1, 1])

with bar1:
    auto_refresh = st.toggle("Auto refresh", value=True)

with bar2:
    refresh_seconds = st.selectbox(
        "Refresh every (sec)",
        options=refresh_options,
        index=2
    )

with bar3:
    underlying = st.selectbox("Underlying", ["BTC"], index=0)

with bar4:
    manual_refresh = st.button("Refresh now", use_container_width=True)

if auto_refresh:
    st_autorefresh(
        interval=refresh_seconds * 1000,
        limit=None,
        debounce=True,
        key=f"option_chain_refresh_{refresh_seconds}"
    )

if manual_refresh:
    st.cache_data.clear()
    st.rerun()

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
    r.r