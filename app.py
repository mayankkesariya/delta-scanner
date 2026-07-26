import time
import hmac
import json
import hashlib
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st

BASE_URL = "https://api.india.delta.exchange"
PUBLIC_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "streamlit-delta-btc-options-scanner",
}

st.set_page_config(page_title="Delta BTCUSDT Spot + Options", layout="wide")
st.title("Delta Exchange BTCUSDT Spot and BTC Options")


def get_secret(name, default=""):
    try:
        return st.secrets[name]
    except Exception:
        return default


API_KEY = get_secret("lHzi4h8CH4kEt5J3TQ0V752Wl34KvW")
API_SECRET = get_secret("g5ibKtcTEMelWS4UScjyoCW1RVDj9Z5bXEzvTZseT6l1eIlEUZKaLsyXoFJ4")


def generate_signature(secret: str, message: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()



def delta_request(method, path, params=None, payload=None, auth=False):
    params = params or {}
    payload = payload or ""
    headers = dict(PUBLIC_HEADERS)
    query_string = f"?{urlencode(params)}" if params else ""

    if auth:
        if not API_KEY or not API_SECRET:
            raise ValueError("Missing DELTA_API_KEY or DELTA_API_SECRET in Streamlit secrets.")
        timestamp = str(int(time.time()))
        signature_data = method + timestamp + path + query_string + payload
        signature = generate_signature(API_SECRET, signature_data)
        headers.update(
            {
                "api-key": API_KEY,
                "timestamp": timestamp,
                "signature": signature,
                "Content-Type": "application/json",
            }
        )

    response = requests.request(
        method=method,
        url=f"{BASE_URL}{path}",
        params=params,
        data=payload,
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("success", False):
        raise RuntimeError(str(data.get("error", "Unknown Delta API error")))
    return data.get("result")


@st.cache_data(ttl=20)
def fetch_btcusdt_ticker():
    return delta_request("GET", "/v2/tickers/BTCUSDT", auth=False)


@st.cache_data(ttl=60)
def fetch_all_option_products():
    all_rows = []
    after = None
    while True:
        params = {
            "contract_types": "call_options,put_options",
            "states": "live",
            "page_size": 100,
        }
        if after:
            params["after"] = after
        page = delta_request("GET", "/v2/products", params=params, auth=False)

        if isinstance(page, list):
            rows = page
            after = None
        else:
            rows = page.get("result", [])
            after = (page.get("meta") or {}).get("after")

        all_rows.extend(rows)
        if not after or not rows:
            break
    return all_rows


@st.cache_data(ttl=20)
def fetch_option_chain(expiry_date):
    return delta_request(
        "GET",
        "/v2/tickers",
        params={
            "contract_types": "call_options,put_options",
            "underlying_asset_symbols": "BTC",
            "expiry_date": expiry_date,
        },
        auth=False,
    )


@st.cache_data(ttl=20)
def fetch_wallet_balances():
    return delta_request("GET", "/v2/wallet/balances", auth=True)



def get_btc_expiries(products):
    expiries = set()
    for p in products:
        symbol = str(p.get("symbol", ""))
        ctype = p.get("contract_type")
        if ctype not in ["call_options", "put_options"]:
            continue
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



def normalize_option_chain(rows, btcusdt_spot=None):
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).copy()

    for col in ["strike_price", "spot_price", "mark_price", "oi", "volume", "turnover_usd"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["best_bid"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("best_bid")), errors="coerce")
    df["best_ask"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("best_ask")), errors="coerce")
    df["bid_iv"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("bid_iv")), errors="coerce")
    df["ask_iv"] = pd.to_numeric(df["quotes"].apply(lambda x: (x or {}).get("ask_iv")), errors="coerce")
    df["delta"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("delta")), errors="coerce")
    df["gamma"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("gamma")), errors="coerce")
    df["theta"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("theta")), errors="coerce")
    df["vega"] = pd.to_numeric(df["greeks"].apply(lambda x: (x or {}).get("vega")), errors="coerce")

    if btcusdt_spot is not None:
        df["spot_price"] = btcusdt_spot

    df["option_side"] = df["contract_type"].map(
        {"call_options": "CALL", "put_options": "PUT"}
    )
    df["mid_price"] = (df["best_bid"].fillna(0) + df["best_ask"].fillna(0)) / 2
    df.loc[df["best_bid"].isna() | df["best_ask"].isna(), "mid_price"] = pd.NA

    cols = [
        "symbol",
        "option_side",
        "strike_price",
        "spot_price",
        "best_bid",
        "best_ask",
        "mid_price",
        "mark_price",
        "bid_iv",
        "ask_iv",
        "delta",
        "gamma",
        "theta",
        "vega",
        "oi",
        "volume",
        "timestamp",
    ]
    cols = [c for c in cols if c in df.columns]
    return df[cols].sort_values(["strike_price", "option_side"]).reset_index(drop=True)



def build_option_chain_table(df):
    if df.empty:
        return df

    calls = df[df["option_side"] == "CALL"].copy().rename(
        columns={
            "symbol": "call_symbol",
            "best_bid": "call_bid",
            "best_ask": "call_ask",
            "mid_price": "call_mid",
            "mark_price": "call_mark",
            "bid_iv": "call_bid_iv",
            "ask_iv": "call_ask_iv",
            "delta": "call_delta",
            "gamma": "call_gamma",
            "theta": "call_theta",
            "vega": "call_vega",
            "oi": "call_oi",
            "volume": "call_volume",
        }
    )
    puts = df[df["option_side"] == "PUT"].copy().rename(
        columns={
            "symbol": "put_symbol",
            "best_bid": "put_bid",
            "best_ask": "put_ask",
            "mid_price": "put_mid",
            "mark_price": "put_mark",
            "bid_iv": "put_bid_iv",
            "ask_iv": "put_ask_iv",
            "delta": "put_delta",
            "gamma": "put_gamma",
            "theta": "put_theta",
            "vega": "put_vega",
            "oi": "put_oi",
            "volume": "put_volume",
        }
    )

    merged = pd.merge(
        calls[
            [
                "strike_price",
                "spot_price",
                "call_symbol",
                "call_bid",
                "call_ask",
                "call_mid",
                "call_mark",
                "call_bid_iv",
                "call_ask_iv",
                "call_delta",
                "call_gamma",
                "call_theta",
                "call_vega",
                "call_oi",
                "call_volume",
            ]
        ],
        puts[
            [
                "strike_price",
                "put_symbol",
                "put_bid",
                "put_ask",
                "put_mid",
                "put_mark",
                "put_bid_iv",
                "put_ask_iv",
                "put_delta",
                "put_gamma",
                "put_theta",
                "put_vega",
                "put_oi",
                "put_volume",
            ]
        ],
        on="strike_price",
        how="outer",
    ).sort_values("strike_price")

    ordered_cols = [
        "call_symbol",
        "call_bid",
        "call_ask",
        "call_mid",
        "call_mark",
        "call_bid_iv",
        "call_ask_iv",
        "call_delta",
        "call_gamma",
        "call_theta",
        "call_vega",
        "call_oi",
        "call_volume",
        "strike_price",
        "put_bid",
        "put_ask",
        "put_mid",
        "put_mark",
        "put_bid_iv",
        "put_ask_iv",
        "put_delta",
        "put_gamma",
        "put_theta",
        "put_vega",
        "put_oi",
        "put_volume",
        "put_symbol",
    ]
    merged = merged[[c for c in ordered_cols if c in merged.columns]]
    return merged.reset_index(drop=True)



def prettify(df):
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].round(4)
    return out


with st.sidebar:
    st.header("Settings")
    refresh_ttl = st.slider("Refresh every seconds", min_value=10, max_value=300, value=20, step=5)
    show_private = st.toggle("Use my API for balances check", value=False)

st.markdown(
    f"<script>setTimeout(function(){{window.location.reload();}}, {refresh_ttl * 1000});</script>",
    unsafe_allow_html=True,
)

try:
    ticker = fetch_btcusdt_ticker()
    products = fetch_all_option_products()
    expiries = get_btc_expiries(products)

    if not expiries:
        st.error("No BTC option expiries found from Delta Exchange.")
        st.stop()

    selected_expiry = st.selectbox("Select BTC option expiry", expiries, index=0)
    option_rows = fetch_option_chain(selected_expiry)

    spot_price = pd.to_numeric(pd.Series([ticker.get("spot_price")]), errors="coerce").iloc[0]
    mark_price = pd.to_numeric(pd.Series([ticker.get("mark_price")]), errors="coerce").iloc[0]
    volume = pd.to_numeric(pd.Series([ticker.get("volume")]), errors="coerce").iloc[0]

    option_df = normalize_option_chain(option_rows, btcusdt_spot=spot_price)
    chain_table = build_option_chain_table(option_df)

    a, b, c, d = st.columns(4)
    a.metric("BTCUSDT Spot", f"{spot_price:,.2f}" if pd.notna(spot_price) else "NA")
    b.metric("BTCUSDT Mark", f"{mark_price:,.2f}" if pd.notna(mark_price) else "NA")
    c.metric("BTCUSDT Volume", f"{volume:,.2f}" if pd.notna(volume) else "NA")
    d.metric("Option Rows", f"{len(option_df):,}")

    st.caption("Option table spot reference is forced to BTCUSDT perpetual ticker spot_price.")

    st.subheader("BTCUSDT Ticker")
    ticker_df = pd.DataFrame([ticker])
    for col in ["spot_price", "mark_price", "close", "open", "high", "low", "volume", "turnover_usd", "oi"]:
        if col in ticker_df.columns:
            ticker_df[col] = pd.to_numeric(ticker_df[col], errors="coerce")
    st.dataframe(prettify(ticker_df), use_container_width=True, height=220)

    st.subheader("BTC Option Prices")
    st.caption("Calls and puts for the selected expiry, using live Delta ticker data.")
    st.dataframe(prettify(chain_table), use_container_width=True, height=700)

    st.download_button(
        "Download option chain CSV",
        data=chain_table.to_csv(index=False).encode("utf-8"),
        file_name=f"delta_btc_option_chain_{selected_expiry}.csv",
        mime="text/csv",
    )

    with st.expander("Raw option rows"):
        st.dataframe(prettify(option_df), use_container_width=True, height=500)

    if show_private:
        st.subheader("Authenticated check")
        balances = fetch_wallet_balances()
        balances_df = pd.DataFrame(balances)
        if balances_df.empty:
            st.info("Authenticated request worked, but no balances were returned.")
        else:
            st.dataframe(balances_df, use_container_width=True, height=250)

except requests.HTTPError as e:
    st.error(f"HTTP error: {e}")
except Exception as e:
    st.error(f"Error: {e}")