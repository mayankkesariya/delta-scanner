import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- CONFIGURATION ---
BASE_URL = "https://api.delta.exchange"
SYMBOL = "BTC"
PRICE_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
HEADERS = {"User-Agent": "Mozilla/5.0"}

st.set_page_config(page_title="OTM Daily Scanner", layout="centered")
st.title("📊 OTM Daily Ratio Scanner")
st.markdown("Scanning **Daily/Near-term** expiries. Both legs OTM. Showing all net credits > 0.")

def get_btc_price():
    try: return float(requests.get(PRICE_URL, timeout=5).json()['price'])
    except: return 65000.0

def get_bulk_data(endpoint):
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, timeout=10)
        return response.json().get('result', []) if response.status_code == 200 else []
    except: return []

if st.button("🚀 Scan Daily OTM Market"):
    with st.spinner("Analyzing short-term options..."):
        products = get_bulk_data("/v2/products")
        tickers_list = get_bulk_data("/v2/tickers")
        ticker_dict = {t['symbol']: t for t in tickers_list if 'symbol' in t}
        btc_price = get_btc_price()
        
        now = datetime.utcnow()
        # Filter: Only options expiring within 48 hours (Daily/Short-term)
        calls = [p for p in products if p.get('symbol', '').startswith(SYMBOL) 
                 and p.get('type') == 'call_option' 
                 and p.get('status') == 'active']

        expiries = {}
        for c in calls:
            # Convert ISO time string to datetime
            try:
                settlement = datetime.fromisoformat(c['settlement_time'].replace('Z', ''))
                if now < settlement < (now + timedelta(hours=48)):
                    exp = c['settlement_time']
                    if exp not in expiries: expiries[exp] = []
                    expiries[exp].append({'symbol': c['symbol'], 'strike': float(c['strike_price'])})
            except: continue

        results = []
        for exp, opts in expiries.items():
            strikes = sorted(list(set([o['strike'] for o in opts])))
            atm_strike = min(strikes, key=lambda x: abs(x - btc_price))
            atm_index = strikes.index(atm_strike)
            
            # Ensure index safety (1st OTM is index+1, 3rd OTM is index+3)
            if atm_index + 3 >= len(strikes): continue
            
            long_strike = strikes[atm_index + 1]
            short_strike = strikes[atm_index + 3]
            
            long_sym = next(o['symbol'] for o in opts if o['strike'] == long_strike)
            short_sym = next(o['symbol'] for o in opts if o['strike'] == short_strike)
            
            l_data = ticker_dict.get(long_sym)
            s_data = ticker_dict.get(short_sym)
            
            if l_data and s_data:
                long_ask = float(l_data['ask'])
                short_bid = float(s_data['bid'])
                
                # Check Ratios 1:2 to 1:10
                for ratio in range(2, 11):
                    net_credit = (ratio * short_bid) - long_ask
                    if net_credit > 0:
                        results.append({
                            "Expiry": exp[5:16],
                            "Ratio": f"1:{ratio}",
                            "Long Strike": long_strike,
                            "Short Strike": short_strike,
                            "Net Credit": f"${round(net_credit, 2)}"
                        })

        if results:
            st.dataframe(pd.DataFrame(results), use_container_width=True)
        else:
            st.warning("No OTM spreads found offering a net credit at this time.")
