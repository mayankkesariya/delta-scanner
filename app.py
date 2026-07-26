import requests
import time

# --- Configuration ---
# Update your API key here if needed
API_KEY = "YOUR_API_KEY_HERE" 
BASE_URL = "https://api.delta.exchange"

# --- Robust API Handling ---
def get_market_data(symbol):
    """
    Fetches market data with error handling to prevent 
    'NoneType' crashes during maintenance or connection issues.
    """
    try:
        url = f"{BASE_URL}/v2/products?symbol={symbol}"
        response = requests.get(url, timeout=10)
        
        # 1. Status Code Check
        if response.status_code != 200:
            print(f"API Error: Received status code {response.status_code}")
            return None
        
        data = response.json()
        
        # 2. Key Validation
        if 'result' not in data:
            print("API Error: 'result' key missing in response.")
            return None
            
        return data['result']
        
    except Exception as e:
        print(f"Connection Error: {e}")
        return None

# --- Main Logic ---
def analyze_parity(ratio):
    """
    Analyzes specific market spread based on the provided ratio.
    """
    # Placeholder: Replace this with your specific Delta Exchange symbol/logic
    # For demonstration, we check a mock calculation
    ticker_data = get_market_data("BTC")
    
    if ticker_data is None:
        print(f"Skipping ratio {ratio} due to failed data fetch.")
        return

    # --- Your Strategy Logic Here ---
    # Example logic placeholders:
    atm_net = -10 # Example calculation
    otm_credit = 5 # Example calculation
    
    # Check conditions:
    # ATM spread target: -20 to 0
    # OTM credit target: > 0
    if -20 <= atm_net <= 0 and otm_credit > 0:
        print(f"MATCH FOUND for Ratio 1:{ratio}")
        print(f"ATM Net: {atm_net}, OTM Credit: {otm_credit}")
    else:
        # Diagnostic print for debugging - remove if you want less noise
        # print(f"Checked 1:{ratio} -> No match (ATM: {atm_net}, OTM: {otm_credit})")
        pass

# --- Execution ---
def main():
    print("Starting Scanner...")
    # Loop ratios from 1:2 to 1:10
    for ratio in range(2, 11):
        try:
            analyze_parity(ratio)
        except Exception as e:
            print(f"Error scanning ratio 1:{ratio} -> {e}")
            
    print("Scan complete.")

if __name__ == "__main__":
    main()
