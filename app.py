import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# --- CONFIGURATION ---
BASE_URL = "https://api.delta.exchange"
SYMBOL = "BTC"

st.set_page_config(page_title="Delta Ratio Scanner", layout="wide")
st.title("🚀 Delta Exchange Daily OTM Scanner")

def get_market_data():
    """Fetches BTC price and Options data from Delta Exchange."""
    try:
        # Get BTC Price
        tickers = requests.get(f"{BASE_URL}/v2/tickers", timeout=10).json()['result']
        btc_data = next(t for t in tickers if t['symbol'] == 'BTCUSD')
        btc_price = float(btc_data['mark_price'])
        
        # Get All Products
        products = requests.get(f"{BASE_URL}/v2/products", timeout=10).json()['result']
        
        # Get Ticker Data for options to get Bid/Ask
        ticker_data = requests.get(f"{BASE_URL}/v2/tickers", timeout=10).json()['result']
        ticker_map = {t['symbol']: t for t in ticker_data}
        
        return btc_price, products, ticker_map
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None, None, None

if st.button("Scan Daily Market"):
    btc_price, products, ticker_map = get_market_data()
    
    if btc_price:
        now = datetime.utcnow()
        # Filter: Only Call Options, Active, Expiring within 48 hours
        calls = [p for p in products if p.get('symbol', '').startswith(SYMBOL) 
                 and p.get('type') == 'call_option' 
                 and p.get('status') == 'active']

        # Group by expiry
        expiries = {}
        for c in calls:
            try:
                settlement = datetime.fromisoformat(c['settlement_time'].replace('Z', ''))
                if now < settlement < (now + timedelta(hours=48)):
                    exp = c['settlement_time']
                    if exp not in expiries: expiries[exp] = []
                    expiries[exp].append({'symbol': c['symbol'], 'strike': float(c['strike_price'])})
            except: continue

        results = []
        for exp, opts in expiries.items():
            # Get unique strikes and find ATM
            strikes = sorted(list(set([o['strike'] for o in opts])))
            atm_strike = min(strikes, key=lambda x: abs(x - btc_price))
            atm_index = strikes.index(atm_strike)
            
            # Ensure index safety: 1st OTM is index+1, 3rd OTM is index+3
            if atm_index + 3 >= len(strikes): continue
            
            # Select Legs
            long_strike = strikes[atm_index + 1] # 1st OTM
            short_strike = strikes[atm_index + 3] # 3rd OTM (Further OTM)
            
            long_sym = next(o['symbol'] for o in opts if o['strike'] == long_strike)
            short_sym = next(o['symbol'] for o in opts if o['strike'] == short_strike)
            
            # Get Bid/Ask
            l_data = ticker_map.get(long_sym)
            s_data = ticker_map.get(short_sym)
            
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
                            "Long (Buy) Strike": long_strike,
                            "Short (Sell) Strike": short_strike,
                            "Net Credit": round(net_credit, 2)
                        })

        if results:
            df = pd.DataFrame(results)
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("No OTM spreads found offering a net credit at this time.")
