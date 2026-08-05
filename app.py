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
    # BTC Option Chain — Put | Strike | Call layout, mirroring the NIFTY/SENSEX
    # Put-Strike-Call sheet style: strikes down the middle, Puts on the left,
    # Calls on the right, ATM row highlighted.
    # ==========================================================================
    st.markdown("---")
    st.subheader("BTC Option Chain — Put | Strike | Call Layout")

    if chain.empty:
        st.warning("No option chain data available to build the layout.")
    else:
        layout_df = chain.copy()
        layout_df["call_iv"] = layout_df["call_ask_iv"].where(layout_df["call_ask_iv"].notna(), layout_df["call_bid_iv"]) * 100
        layout_df["put_iv"] = layout_df["put_bid_iv"].where(layout_df["put_bid_iv"].notna(), layout_df["put_ask_iv"]) * 100

        layout_cols = [
            "put_oi", "put_volume", "put_delta", "put_iv", "put_bid", "put_ask", "put_mark",
            "strike_price",
            "call_mark", "call_bid", "call_ask", "call_iv", "call_delta", "call_volume", "call_oi",
        ]
        layout_names = [
            "Put OI", "Put Vol", "Put Delta", "Put IV%", "Put Bid", "Put Ask", "Put Mark",
            "STRIKE",
            "Call Mark", "Call Bid", "Call Ask", "Call IV%", "Call Delta", "Call Vol", "Call OI",
        ]
        present = [c for c in layout_cols if c in layout_df.columns]
        layout_df = layout_df[present].reset_index(drop=True)
        layout_df.columns = [n for c, n in zip(layout_cols, layout_names) if c in present]

        atm_idx = None
        if spot_value is not None and layout_df["STRIKE"].notna().any():
            atm_idx = (layout_df["STRIKE"] - spot_value).abs().idxmin()

        def highlight_layout(row):
            if atm_idx is not None and row.name == atm_idx:
                return ["background-color: #ffe680; font-weight: bold;"] * len(row)
            styles = [""] * len(row)
            strike = row["STRIKE"]
            if spot_value is not None and pd.notna(strike):
                shade_prefix = "Call" if strike < spot_value else "Put"
                for i, col in enumerate(row.index):
                    if col.startswith(shade_prefix):
                        styles[i] = "background-color: #eef1f5;"
            return styles

        styled_layout = layout_df.style.apply(highlight_layout, axis=1).format(precision=2)
        st.dataframe(styled_layout, use_container_width=True, height=520)
        st.caption(
            "Yellow row = strike nearest current spot (ATM). Shaded cells mark the ITM side. "
            "Columns mirror your Put | Strike | Call sheet; Delta Exchange doesn't expose the extra "
            "distance/Greek grid columns from your Excel file, so tell me the formula behind those if you want them added."
        )

    # ==========================================================================
    # NEW SECTION (added below scanner, does not modify anything above)
    # BTC IV Skew Curve: Call IV vs Put IV vs Strike, plus the Put/Call IV
    # skew ratio curve, with the scanner's current ratio-spread legs marked.
    # ==========================================================================
    st.markdown("---")
    st.subheader("BTC IV Skew Curve")

    if chain.empty:
        st.warning("No IV data available to build the skew curve.")
    else:
        skew_df = chain[["strike_price", "call_bid_iv", "call_ask_iv", "put_bid_iv", "put_ask_iv"]].copy()
        skew_df["Call IV"] = skew_df["call_ask_iv"].where(skew_df["call_ask_iv"].notna(), skew_df["call_bid_iv"]) * 100
        skew_df["Put IV"] = skew_df["put_bid_iv"].where(skew_df["put_bid_iv"].notna(), skew_df["put_ask_iv"]) * 100
        skew_df = skew_df.dropna(subset=["strike_price"]).sort_values("strike_price").reset_index(drop=True)
        skew_df["Put/Call IV Ratio"] = skew_df["Put IV"] / skew_df["Call IV"]

        if skew_df.empty:
            st.warning("No strikes with usable IV quotes for this expiry.")
        else:
            try:
                import matplotlib.pyplot as plt

                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [2, 1]})

                ax1.plot(skew_df["strike_price"], skew_df["Call IV"], marker="o", markersize=3, label="Call IV", color="#2ca02c")
                ax1.plot(skew_df["strike_price"], skew_df["Put IV"], marker="o", markersize=3, label="Put IV", color="#d62728")
                if spot_value is not None:
                    ax1.axvline(spot_value, color="black", linestyle="--", linewidth=1, label=f"Spot {spot_value:,.0f}")

                if not opps.empty:
                    top_legs = opps.head(max_rows)
                    iv_col = "Call IV" if option_type == "call_options" else "Put IV"
                    iv_lookup = skew_df.set_index("strike_price")[iv_col]
                    long_iv = iv_lookup.reindex(top_legs["long_strike"]).values
                    short_iv = iv_lookup.reindex(top_legs["short_strike"]).values
                    ax1.scatter(top_legs["long_strike"], long_iv, color="blue", marker="^", s=60, label="Long leg (scanner)", zorder=5)
                    ax1.scatter(top_legs["short_strike"], short_iv, color="orange", marker="v", s=60, label="Short leg (scanner)", zorder=5)

                ax1.set_ylabel("Implied Volatility (%)")
                ax1.set_title(f"BTC IV Skew — {selected_expiry}")
                ax1.legend(loc="upper right", fontsize=8)
                ax1.grid(alpha=0.3)

                ax2.plot(skew_df["strike_price"], skew_df["Put/Call IV Ratio"], color="#9467bd", marker="o", markersize=3)
                ax2.axhline(1.0, color="black", linestyle="--", linewidth=1)
                if spot_value is not None:
                    ax2.axvline(spot_value, color="black", linestyle="--", linewidth=1)
                ax2.set_ylabel("Put IV / Call IV")
                ax2.set_xlabel("Strike Price")
                ax2.grid(alpha=0.3)

                st.pyplot(fig)
            except ImportError:
                st.info("matplotlib isn't installed, so here's the built-in chart instead. Run `pip install matplotlib` for the full skew view with spot/ratio-leg markers.")
                st.line_chart(skew_df.set_index("strike_price")[["Call IV", "Put IV"]])
                st.line_chart(skew_df.set_index("strike_price")[["Put/Call IV Ratio"]])

            st.dataframe(
                format_numeric_columns(skew_df[["strike_price", "Call IV", "Put IV", "Put/Call IV Ratio"]]),
                use_container_width=True, height=300
            )
            st.download_button(
                "Download skew data CSV",
                skew_df.to_csv(index=False).encode("utf-8"),
                f"btc_iv_skew_{selected_expiry}.csv", "text/csv"
            )

except requests.HTTPError as e:
    st.error(f"HTTP error: {e}")
except Exception as e:
    st.error(f"Error: {e}")

