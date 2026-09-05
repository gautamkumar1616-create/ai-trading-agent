# NIFTY 500 AI Trading Agent V3.2

This version upgrades the personal trading agent from CSV-only testing to a NIFTY 500 universe and Angel One historical-data connector.

## Current
- NIFTY 500 constituent loading
- Angel One instrument-master mapping
- 15-minute historical candle connector
- BUY / SELL / NO TRADE scoring
- Entry / SL / Target / R:R
- Paper-only scan
- Live order execution locked

## Angel One Secrets
Add these to Streamlit Secrets (never commit them to GitHub):
- ANGEL_API_KEY
- ANGEL_CLIENT_CODE
- ANGEL_TOTP_SECRET
- ANGEL_MPIN

Do not send these values in chat.

## Important
The scanner is a rule-based research tool, not a guarantee of returns. Validate with historical backtesting and paper trading before any live execution.

## V3.2 fix
The NIFTY 500 universe is loaded only when the user presses the button, with short network timeouts and multiple sources, so the app does not hang indefinitely during startup.

## V3.2 fix
Streamlit session state now persists the loaded NIFTY 500 universe and Angel One mapping across button clicks/reruns.
