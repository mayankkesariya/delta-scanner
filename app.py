import streamlit as st
import requests
import pandas as pd

# --- CONFIGURATION ---
BASE_URL = "https://api.delta.exchange"
SYMBOL = "BTC"
PRICE_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
# Hardcoded offsets have been removed in favor of dynamic strike indexing.

# --- UI SETUP ---
st.set_page_config(page_title="Delta Parity Scanner", page_icon="📊", layout="centered")
st.title("📊 Delta Ratio Scanner")
st.markdown("Scanning all expiries for ATM Debits & **$1-$5 OTM Credits** (Ratios 1:5 to 1:10)")

# --- HELPER FUNCTIONS ---
def get_btc_price():
    try:
        return float(requests.get(PRICE_URL, timeout=5).json()['price'])
    except:
        return 65000.0

def get_bulk_data(endpoint):
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json().get('result', [])
        return []
    except:
        return []

def get_prices(symbol, ticker_dict):
    data = ticker_dict.get(symbol)
    if data and data.get('bid') and data.get('ask'):
        try:
            return float(data['bid']), float(data['ask'])
        except (ValueError, TypeError):
            pass
    return None, None

# --- MAIN SCANNER LOGIC ---
if st.button("🚀 Scan Market Now"):
    with st.spinner("Fetching live order books from Delta Exchange..."):
        products = get_bulk_data("/v2/products")
        tickers_list = get_bulk_data("/v2/tickers")
        
        if not products or not tickers_list:
            st.error("API Connection Failed. Please try again.")
        else:
            ticker_dict = {t.get('symbol'): t for t in tickers_list if t.get('symbol')}
            
            # Safe parsing using .get() to avoid KeyErrors
            calls = [p for p in products if p.get('symbol', '').startswith(SYMBOL) 
                     and p.get('type') == 'call_option' 
                     and p.get('status') == 'active']
            
            expiries = {}
            for c in calls:
                exp = c.get('settlement_time', 'Unknown')
                if exp not in expiries: expiries[exp] = []
                expiries[exp].append(c)

            btc_price = get_btc_price()
            st.info(f"**Current BTC Spot Price:** ${btc_price:,.0f}")
            
            opportunities = []

            for expiry, opts in expiries.items():
                if expiry == 'Unknown': continue
                
                parsed_opts = []
                for p in opts:
                    try:
                        parsed_opts.append({'symbol': p['symbol'], 'strike': float(p.get('strike_price', 0))})
                    except:
                        continue
                
                if not parsed_opts: continue
                strikes = sorted(list(set([p['strike'] for p in parsed_opts if p['strike'] > 0])))
                if not strikes: continue
                
                # --- DYNAMIC STRIKE INDEXING ---
                atm_strike = min
