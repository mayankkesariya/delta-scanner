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
OFFSET_OTM_LONG = 1000   
OFFSET_OTM_SHORT = 3000  

# --- UI SETUP ---
st.set_page_config(page_title="Delta Parity Scanner", page_icon="📊", layout="centered")
st.title("📊 Delta Ratio Scanner")
st.markdown("Scanning for ATM Debits & OTM Credits (Ratios 1:5 to 1:10)")

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
                
                atm_strike = min(strikes, key=lambda x: abs(x - btc_price))
atm_index = strikes.index(atm_strike)

# Ensure there are enough strikes above the ATM price to scan
if atm_index + 3 >= len(strikes):
    continue

# Dynamically pick the 1st and 3rd strikes Out-Of-The-Money
long_strike = strikes[atm_index + 1] 
short_strike = strikes[atm_index + 3] 

                
                atm_sym = next((p['symbol'] for p in parsed_opts if p['strike'] == atm_strike), None)
                long_sym = next((p['symbol'] for p in parsed_opts if p['strike'] == long_strike), None)
                short_sym = next((p['symbol'] for p in parsed_opts if p['strike'] == short_strike), None)

                if not (atm_sym and long_sym and short_sym): continue

                atm_bid, atm_ask = get_prices(atm_sym, ticker_dict)
                long_bid, long_ask = get_prices(long_sym, ticker_dict)
                short_bid, short_ask = get_prices(short_sym, ticker_dict)

                if None in [atm_bid, atm_ask, long_bid, long_ask, short_bid, short_ask]: continue

                atm_debit_cost = atm_ask - long_bid 
                
                # Check ATM Debit Condition
                if atm_debit_cost > 0: 
                    # Check OTM Ratios
                    for ratio in range(5, 11):
                        otm_net_credit = (ratio * short_bid) - long_ask
                        
                        if otm_net_credit > 0: 
                            opportunities.append({
                                "Expiry": str(expiry)[:10],
                                "Ratio": f"1:{ratio}",
                                "Long Strike": long_strike,
                                "Short Strike": short_strike,
                                "ATM Debit ($)": round(atm_debit_cost, 2),
                                "OTM Credit ($)": round(otm_net_credit, 2)
                            })

            # --- DISPLAY RESULTS ---
            if opportunities:
                st.success(f"Found {len(opportunities)} valid skew opportunities!")
                df = pd.DataFrame(opportunities)
                # Display as an interactive table that looks great on mobile
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("No ratios met the exact criteria. The market is not currently skewed in your favor.")
              
