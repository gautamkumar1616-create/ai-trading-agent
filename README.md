
# Trading Agent MVP

This is the first research/scanner prototype for a NIFTY 50 15-minute Trading Agent.

## Run

1. Install Python 3.10+.
2. Open terminal in this folder.
3. Run:
   pip install -r requirements.txt
   streamlit run app.py
4. Upload a 15-minute OHLC/volume CSV.

## Important
This prototype does NOT place orders. It is for research and paper trading.
The current scoring rules are a starting hypothesis, not a proven profitable strategy.

## Roadmap
1. Add proper entry/exit backtest
2. Add SL/target/position sizing
3. Measure win rate, expectancy, profit factor and max drawdown
4. Connect Angel One historical/live data
5. Add alerts
6. Add AI explanation layer
