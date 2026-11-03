# Nifty 500 Oversold-at-Support Scanner

Finds Nifty 500 stocks whose RSI is oversold on a lower timeframe (5m, 15m, 30m, 1h) while price is at, or just under, a daily or weekly support zone. Shows how far price is from the zone.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Get the full Nifty 500 list (important)
`data/nifty500.csv` ships with a short fallback list (about 110 large caps). The app first tries to load the full list from NSE; if NSE blocks the request you will see a warning in the sidebar. To fix that permanently, download
https://archives.nseindia.com/content/indices/ind_nifty500list.csv in your browser and save it over `data/nifty500.csv` (keep the `Symbol` column).

## Deploy on Streamlit Community Cloud
1. Create a GitHub repository and push this folder (`app.py` at the repo root).
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Choose New app, select the repository and branch, set the main file to `app.py`, then Deploy.
4. Later changes: push to GitHub and the app redeploys itself.

After your first successful run, run `pip freeze | grep -iE "streamlit|yfinance|pandas|numpy|scipy|plotly|requests"` and copy the exact versions into `requirements.txt` to pin them.

## Layout
- `app.py` is the UI only.
- `scanner/config.py` holds every default and constant.
- `scanner/data.py` loads the stock list and cached yfinance downloads.
- `scanner/indicators.py` has RSI and the weekly resample.
- `scanner/support.py` finds and classifies support zones.
- `scanner/engine.py` runs the scan pipeline.

## Known limits
- yfinance is unofficial and can be delayed or rate limited, more so on shared cloud hosts. A broker API (Angel One SmartAPI, Zerodha Kite, Upstox) is the reliable upgrade for intraday data.
- Yahoo only keeps about 60 days of 5m, 15m and 30m candles and about 2 years of 1h candles. That is enough for RSI.
- Exchange holidays are not modelled in the "NSE open" indicator.
- Support zones are a mechanical estimate. Always check the chart.
- For education only, not investment advice.
