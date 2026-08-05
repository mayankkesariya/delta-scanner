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
st.title("BTCUSD Parity")

@st.cache_data(ttl=30)
def fetch_all_products():
    all_rows = []
    after = None
    while True:
        params = {"contract_types": "call_options,put_options", "states": "live", "page_size": 100}
        if after:
            params["after"] = after
        r = requests.get(f"{BASE_URL}/products", params=params, headers=HEADERS, timeout=20)
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
    params = {"contract_types": "call_options,put_options", "underlying_asset_symbols": underlying}
    if expiry_date:
        params["expiry_date"] = expiry_date
    r = requests.get(f"{BASE_URL}/tickers", params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json().get("result", [])

def get_btc_expiries(products):
    expiries = set()
    for p in products:
        if p.get("contract_type") not in ["call_options", "put_options"]:
            continue
        if "-BTC-" not in p.get("symbol", ""):
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
        "symbol": "call_symbol", "best_bid": "call_bid", "best_ask": "call_ask", "mark_price": "call_mark",
        "oi": "call_oi", "volume": "call_volume", "delta": "call_delta", "gamma": "call_gamma",
        "theta": "call_theta", "vega": "call_vega", "bid_iv": "call_bid_iv", "ask_iv": "call_ask_iv"
    })
    puts = puts.rename(columns={
        "symbol": "put_symbol", "best_bid": "put_bid", "best_ask": "put_ask", "mark_price": "put_mark",
        "oi": "put_oi", "volume": "put_volume", "delta": "put_delta", "gamma": "put_gamma",
        "theta": "put_theta", "vega": "put_vega", "bid_iv": "put_bid_iv", "ask_iv": "put_ask_iv"
    })
    merged = pd.merge(
        calls[["strike_price", "spot_price", "call_symbol", "call_bid", "call_ask", "call_mark", "call_oi", "call_volume", "call_delta", "call_gamma", "call_theta", "call_vega", "call_bid_iv", "call_ask_iv"]],
        puts[["strike_price", "put_symbol", "put_bid", "put_ask", "put_mark", "put_oi", "put_volume", "put_delta", "put_gamma", "put_theta", "put_vega", "put_bid_iv", "put_ask_iv"]],
        on="strike_price", how="outer"
    ).sort_values("strike_price")
    col_order = [
        "call_symbol", "call_bid", "call_ask", "call_mark", "call_oi", "call_volume", "call_delta", "call_gamma",
        "call_theta", "call_vega", "call_bid_iv", "call_ask_iv", "strike_price", "put_bid", "put_ask", "put_mark",
        "put_oi", "put_volume", "put_delta", "put_gamma", "put_theta", "put_vega", "put_bid_iv", "put_ask_iv", "put_symbol"
    ]
    return merged[[c for c in col_order if c in merged.columns]]

def enrich_option_rows(option_rows):
    if not option_rows:
        return pd.DataFrame()
    df = pd.DataFrame(option_rows).copy()
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
    return df

def premium_buy(row, mode):
    if mode == "mid" and pd.notna(row.get("best_bid")) and pd.notna(row.get("best_ask")):
        return (row.get("best_bid") + row.get("best_ask")) / 2
    return row.get("best_ask") if pd.notna(row.get("best_ask")) else row.get("mark_price")

def premium_sell(row, mode):
    if mode == "mid" and pd.notna(row.get("best_bid")) and pd.notna(row.get("best_ask")):
        return (row.get("best_bid") + row.get("best_ask")) / 2
    return row.get("best_bid") if pd.notna(row.get("best_bid")) else row.get("mark_price")

def find_ratio_spreads(df, option_type, qty_long, qty_short, min_credit, min_oi, min_volume, width_min, width_max, price_mode):
    sub = df[df["contract_type"] == option_type].copy()
    ascending = True if option_type == "call_options" else False
    sub = sub.sort_values("strike_price", ascending=ascending).reset_index(drop=True)
    if sub.empty:
        return pd.DataFrame()
    spot = pd.to_numeric(sub["spot_price"], errors="coerce").dropna()
    spot_value = float(spot.iloc[0]) if not spot.empty else math.nan
    rows = []
    for i in range(len(sub)):
        long_row = sub.iloc[i]
        if long_row.get("oi", 0) < min_oi or long_row.get("volume", 0) < min_volume:
            continue
        for j in range(i + 1, len(sub)):
            short_row = sub.iloc[j]
            if short_row.get("oi", 0) < min_oi or short_row.get("volume", 0) < min_volume:
                continue
            long_k = long_row["strike_price"]
            short_k = short_row["strike_price"]
            if option_type == "call_options":
                if pd.notna(spot_value) and not (long_k > spot_value and short_k > spot_value):
                    continue
                width = short_k - long_k
            else:
                if pd.notna(spot_value) and not (long_k < spot_value and short_k < spot_value):
                    continue
                width = long_k - short_k
            if pd.isna(long_k) or pd.isna(short_k) or width < width_min or width > width_max:
                continue
            buy_price = premium_buy(long_row, price_mode)
            sell_price = premium_sell(short_row, price_mode)
            if pd.isna(buy_price) or pd.isna(sell_price):
                continue
            net_credit = qty_short * sell_price - qty_long * buy_price
            if net_credit < min_credit:
                continue
            max_profit = net_credit + width * qty_long
            breakeven = short_k + max_profit / max(qty_short - qty_long, 1) if option_type == "call_options" else short_k - max_profit / max(qty_short - qty_long, 1)
            rows.append({
                "strategy": f"{qty_long}:{qty_short} | {qty_long}x{int(long_k)}{'C' if option_type == 'call_options' else 'P'} / -{qty_short}x{int(short_k)}{'C' if option_type == 'call_options' else 'P'}",
                "type": "Call Ratio Spread" if option_type == "call_options" else "Put Ratio Spread",
                "spot_price": spot_value,
                "long_symbol": long_row.get("symbol"),
                "short_symbol": short_row.get("symbol"),
                "long_strike": long_k,
                "short_strike": short_k,
                "width": width,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "net_credit": net_credit,
                "max_profit_at_short_strike": max_profit,
                "breakeven": breakeven,
                "long_oi": long_row.get("oi"),
                "short_oi": short_row.get("oi"),
                "long_volume": long_row.get("volume"),
                "short_volume": short_row.get("volume"),
                "long_delta": long_row.get("delta"),
                "short_delta": short_row.get("delta"),
                "long_strike_iv": ((long_row.get("ask_iv") if pd.notna(long_row.get("ask_iv")) else long_row.get("bid_iv")) * 100),
                "short_strike_iv": ((short_row.get("bid_iv") if pd.notna(short_row.get("bid_iv")) else short_row.get("ask_iv")) * 100),
                "iv_difference": (((long_row.get("ask_iv") if pd.notna(long_row.get("ask_iv")) else long_row.get("bid_iv")) - (short_row.get("bid_iv") if pd.notna(short_row.get("bid_iv")) else short_row.get("ask_iv"))) * 100),
                "risk_note": "Unlimited tail risk" if qty_short > qty_long else "Bounded",
            })
    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values(["net_credit", "width"], ascending=[False, False]).reset_index(drop=True)
    return res

def find_atm_width_ratios(df, option_type, atm_strike, qty_long, qty_short, widths, price_mode):
    """
    Anchors the long leg at atm_strike (qty_long) and, for each requested width,
    finds the nearest available short strike (qty_short) at that distance from ATM.
    Returns one row per width. New function, does not alter find_ratio_spreads.
    """
    sub = df[df["contract_type"] == option_type].copy()
    sub["strike_price"] = pd.to_numeric(sub["strike_price"], errors="coerce")
    sub = sub.dropna(subset=["strike_price"]).sort_values("strike_price").reset_index(drop=True)
    if sub.empty or atm_strike is None:
        return pd.DataFrame()

    long_matches = sub[sub["strike_price"] == atm_strike]
    long_row = long_matches.iloc[0] if not long_matches.empty else sub.iloc[(sub["strike_price"] - atm_strike).abs().idxmin()]
    long_strike = long_row["strike_price"]
    buy_price = premium_buy(long_row, price_mode)

    available_strikes = sub["strike_price"]
    rows = []
    for w in widths:
        target = long_strike + w if option_type == "call_options" else long_strike - w
        short_strike = available_strikes.iloc[(available_strikes - target).abs().idxmin()]
        if short_strike == long_strike:
            continue
        short_row = sub[sub["strike_price"] == short_strike].iloc[0]
        sell_price = premium_sell(short_row, price_mode)
        if pd.isna(buy_price) or pd.isna(sell_price):
            continue
        actual_width = (short_strike - long_strike) if option_type == "call_options" else (long_strike - short_strike)
        net_credit = qty_short * sell_price - qty_long * buy_price
        max_profit = net_credit + actual_width * qty_long
        denom = max(qty_short - qty_long, 1)
        breakeven = short_strike + max_profit / denom if option_type == "call_options" else short_strike - max_profit / denom
        long_iv = long_row.get("ask_iv") if pd.notna(long_row.get("ask_iv")) else long_row.get("bid_iv")
        short_iv = short_row.get("bid_iv") if pd.notna(short_row.get("bid_iv")) else short_row.get("ask_iv")
        rows.append({
            "Requested Width": w,
            "Actual Width": actual_width,
            "Long Strike": long_strike,
            "Short Strike": short_strike,
            "Buy Price": buy_price,
            "Sell Price": sell_price,
            "Net Credit": net_credit,
            "Max Profit": max_profit,
            "Breakeven": breakeven,
            "Long IV%": long_iv * 100 if pd.notna(long_iv) else None,
            "Short IV%": short_iv * 100 if pd.notna(short_iv) else None,
            "IV Diff": (long_iv - short_iv) * 100 if pd.notna(long_iv) and pd.notna(short_iv) else None,
            "Long OI": long_row.get("oi"),
            "Short OI": short_row.get("oi"),
            "Long Vol": long_row.get("volume"),
            "Short Vol": short_row.get("volume"),
        })
    return pd.DataFrame(rows)

def format_numeric_columns(df):
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].round(4)
    return out

with st.sidebar:
    refresh_seconds = st.slider("Auto refresh seconds", 5, 10, 5, 1)
    strategy_side = st.selectbox("Scan side", ["Call Ratio Spread", "Put Ratio Spread"])
    ratio_start = st.number_input("Short ratio start", min_value=2, max_value=20, value=5, step=1)
    ratio_end = st.number_input("Short ratio end", min_value=2, max_value=20, value=10, step=1)
    price_mode = st.selectbox("Premium mode", ["natural", "mid"], index=0)
    min_credit = st.number_input("Minimum net credit", min_value=0.0, value=0.0, step=1.0)
    width_min = st.number_input("Minimum strike width", min_value=0, value=1000, step=500)
    width_max = st.number_input("Maximum strike width", min_value=0, value=20000, step=500)
    max_rows = st.slider("Top opportunities", 5, 200, 30, 5)

st.markdown(f"<script>setTimeout(function(){{window.location.reload();}}, {refresh_seconds * 1000});</script>", unsafe_allow_html=True)

if st.button("Refresh now"):
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
    spot_candidates = pd.to_numeric(pd.DataFrame(option_rows).get("spot_price"), errors="coerce").dropna()
    spot_value = float(spot_candidates.iloc[0]) if not spot_candidates.empty else None
    c2.metric("Spot Price", f"{spot_value:,.2f}" if spot_value is not None else "NA")
    c3.metric("Selected Expiry", selected_expiry)

    option_type = "call_options" if strategy_side == "Call Ratio Spread" else "put_options"
    start_ratio = min(ratio_start, ratio_end)
    end_ratio = max(ratio_start, ratio_end)
    frames = []
    for short_ratio in range(start_ratio, end_ratio + 1):
        frame = find_ratio_spreads(option_df, option_type, 1, short_ratio, min_credit, 0, 0, width_min, width_max, price_mode)
        if not frame.empty:
            frame["ratio"] = f"1:{short_ratio}"
            frames.append(frame)
    opps = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not opps.empty:
        opps = opps.sort_values(["net_credit", "width"], ascending=[False, False]).reset_index(drop=True)

    st.subheader("Opportunity Scanner")
    st.caption(f"Scanning ratios from 1:{start_ratio} to 1:{end_ratio}")
    if opps.empty:
        st.warning("No opportunities found for the current filters.")
    else:
        show_df = format_numeric_columns(opps.head(max_rows))
        show_df = show_df[[
            "ratio","long_strike","short_strike","width","buy_price","sell_price","net_credit","long_strike_iv","short_strike_iv","iv_difference"
        ]]
        show_df.columns = [
            "Ratio","Long Strike","Short Strike","Farak","Buy Price","Sell Price","Net Credit","Long Strike IV","Short Strike IV","IV Difference"
        ]
        st.dataframe(show_df, use_container_width=True, height=420)
        st.download_button("Download opportunities CSV", opps.to_csv(index=False).encode("utf-8"), f"delta_ratio_spreads_{selected_expiry}.csv", "text/csv")

    # ==========================================================================
    # NEW SECTION (added below scanner, does not modify anything above)
    # ATM-anchored ratio table, Call side only: Buy 1 ATM call, sell N calls
    # (default 1:10) across as many widths/differences from ATM as you enter.
    # ==========================================================================
    st.markdown("---")
    st.subheader("ATM 1:10 Call Ratio — Multi-Width Table")

    call_sub = option_df[option_df["contract_type"] == "call_options"].copy()
    call_sub["strike_price"] = pd.to_numeric(call_sub["strike_price"], errors="coerce")
    call_sub = call_sub.dropna(subset=["strike_price"])

    if call_sub.empty or spot_value is None:
        st.warning("No call strikes available to anchor an ATM ratio table.")
    else:
        atm_strike = float(call_sub.loc[(call_sub["strike_price"] - spot_value).abs().idxmin(), "strike_price"])

        wc1, wc2, wc3, wc4 = st.columns([1, 1, 1, 1])
        atm_long_qty = wc1.number_input("Long qty (ATM)", min_value=1, value=1, step=1, key="atm_long_qty")
        atm_short_qty = wc2.number_input("Short qty per leg", min_value=1, value=10, step=1, key="atm_short_qty")
        start_diff = wc3.number_input("Start difference", min_value=0, value=600, step=100, key="atm_start_diff")
        end_diff = wc4.number_input("End difference", min_value=0, value=1400, step=100, key="atm_end_diff")

        lo_diff, hi_diff = (start_diff, end_diff) if start_diff <= end_diff else (end_diff, start_diff)
        strikes_in_band = call_sub.loc[
            (call_sub["strike_price"] >= atm_strike + lo_diff) & (call_sub["strike_price"] <= atm_strike + hi_diff),
            "strike_price"
        ].sort_values().unique()
        widths = [float(s - atm_strike) for s in strikes_in_band]

        st.caption(
            f"ATM Call strike (nearest to spot {spot_value:,.2f}): **{atm_strike:,.0f}**  |  "
            f"Ratio {int(atm_long_qty)}:{int(atm_short_qty)}  |  "
            f"Scanning {len(widths)} strike(s) between +{lo_diff:.0f} and +{hi_diff:.0f} from ATM"
        )

        if widths:
            atm_table = find_atm_width_ratios(option_df, "call_options", atm_strike, int(atm_long_qty), int(atm_short_qty), widths, price_mode)
            if atm_table.empty:
                st.warning("No valid strikes found in that difference range.")
            else:
                st.dataframe(format_numeric_columns(atm_table), use_container_width=True, height=380)
                st.download_button(
                    "Download ATM ratio table CSV",
                    atm_table.to_csv(index=False).encode("utf-8"),
                    f"btc_atm_ratio_{int(atm_long_qty)}_{int(atm_short_qty)}_{selected_expiry}.csv",
                    "text/csv"
                )
        else:
            st.info("No call strikes fall inside the start/end difference range — try widening it.")

except requests.HTTPError as e:
    st.error(f"HTTP error: {e}")
except Exception as e:
    st.error(f"Error: {e}")
