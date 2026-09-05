import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="NIFTY 500 AI Trading Agent V3", layout="wide")

st.title("🤖 NIFTY 500 AI Trading Agent V3")
st.caption("NIFTY 500 scanner • 15m strategy • Paper trading • Angel One data connector")

# -------------------------
# Credentials
# -------------------------
def secret(name):
    try:
        return st.secrets.get(name, os.getenv(name, ""))
    except Exception:
        return os.getenv(name, "")

API_KEY = secret("ANGEL_API_KEY")
CLIENT_CODE = secret("ANGEL_CLIENT_CODE")
TOTP_SECRET = secret("ANGEL_TOTP_SECRET")
MPIN = secret("ANGEL_MPIN")

# -------------------------
# Strategy
# -------------------------
def rsi(s, period=14):
    d = s.diff()
    gain = d.clip(lower=0).rolling(period).mean()
    loss = (-d.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def indicators(df):
    d = df.copy()
    d["ema20"] = d["close"].ewm(span=20, adjust=False).mean()
    d["ema50"] = d["close"].ewm(span=50, adjust=False).mean()
    d["ema200"] = d["close"].ewm(span=200, adjust=False).mean()
    d["rsi"] = rsi(d["close"])
    prev = d["close"].shift(1)
    tr = pd.concat([
        d["high"] - d["low"],
        (d["high"] - prev).abs(),
        (d["low"] - prev).abs()
    ], axis=1).max(axis=1)
    d["atr"] = tr.rolling(14).mean()
    d["vol_ma20"] = d["volume"].rolling(20).mean()
    d["dc20_high"] = d["high"].rolling(20).max().shift(1)
    d["dc20_low"] = d["low"].rolling(20).min().shift(1)
    return d

def signal(d, risk_reward=2.0):
    if len(d) < 210:
        return {"signal": "NO TRADE", "reason": "Need at least 210 candles"}

    x = d.iloc[-1]
    score_long = 0
    score_short = 0
    long_reasons, short_reasons = [], []

    if x.close > x.ema20:
        score_long += 15; long_reasons.append("Close > EMA20")
    if x.ema20 > x.ema50:
        score_long += 15; long_reasons.append("EMA20 > EMA50")
    if x.close > x.ema200:
        score_long += 15; long_reasons.append("Close > EMA200")
    if x.rsi >= 55:
        score_long += 15; long_reasons.append("RSI >= 55")
    if x.volume >= x.vol_ma20:
        score_long += 15; long_reasons.append("Volume expansion")
    if x.close > x.dc20_high:
        score_long += 25; long_reasons.append("DC20 breakout")

    if x.close < x.ema20:
        score_short += 15; short_reasons.append("Close < EMA20")
    if x.ema20 < x.ema50:
        score_short += 15; short_reasons.append("EMA20 < EMA50")
    if x.close < x.ema200:
        score_short += 15; short_reasons.append("Close < EMA200")
    if x.rsi <= 45:
        score_short += 15; short_reasons.append("RSI <= 45")
    if x.volume >= x.vol_ma20:
        score_short += 15; short_reasons.append("Volume expansion")
    if x.close < x.dc20_low:
        score_short += 25; short_reasons.append("DC20 breakdown")

    atr = float(x.atr) if pd.notna(x.atr) else 0
    entry = float(x.close)

    if score_long >= score_short and score_long >= 70 and atr > 0:
        sl = entry - atr
        target = entry + risk_reward * (entry - sl)
        return {
            "signal": "BUY", "entry": entry, "sl": sl, "target": target,
            "rr": risk_reward, "score": score_long,
            "reason": ", ".join(long_reasons)
        }

    if score_short > score_long and score_short >= 70 and atr > 0:
        sl = entry + atr
        target = entry - risk_reward * (sl - entry)
        return {
            "signal": "SELL", "entry": entry, "sl": sl, "target": target,
            "rr": risk_reward, "score": score_short,
            "reason": ", ".join(short_reasons)
        }

    return {
        "signal": "NO TRADE", "entry": entry, "sl": np.nan,
        "target": np.nan, "rr": np.nan,
        "score": max(score_long, score_short),
        "reason": "Setup score below threshold or conditions mixed"
    }

# -------------------------
# NIFTY 500 universe
# -------------------------
@st.cache_data(ttl=86400)
def get_nifty500():
    # Use short network timeouts so Streamlit never stays stuck indefinitely.
    urls = [
        "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
        "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
        "https://raw.githubusercontent.com/kprohith/nse-stock-analysis/main/ind_nifty500list.csv",
    ]
    last_error = None
    for url in urls:
        try:
            import requests
            r = requests.get(
                url,
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            r.raise_for_status()
            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
            df.columns = [str(c).strip() for c in df.columns]
            sym_col = next(
                (c for c in df.columns if c.upper() in ["SYMBOL", "SYMBOLS"]),
                None
            )
            if sym_col:
                out = pd.DataFrame({
                    "symbol": df[sym_col].astype(str).str.strip().str.upper()
                })
                out = out.drop_duplicates().sort_values("symbol").reset_index(drop=True)
                if len(out) >= 450:
                    return out
        except Exception as e:
            last_error = e
    raise RuntimeError(
        "NIFTY 500 list could not be loaded automatically. "
        "Network access may be temporarily blocked. "
        f"Last error: {last_error}"
    )

@st.cache_data(ttl=86400)
def get_angel_instruments():
    urls = [
        "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json",
        "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json",
    ]
    last_error = None
    for url in urls:
        try:
            df = pd.read_json(url)
            df["symbol"] = df["symbol"].astype(str).str.upper()
            df["exch_seg"] = df["exch_seg"].astype(str).str.upper()
            df["token"] = df["token"].astype(str)
            return df
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Could not download Angel One instrument master: {last_error}")

# -------------------------
# Angel historical connector
# -------------------------
def angel_login():
    if not (API_KEY and CLIENT_CODE and TOTP_SECRET and MPIN):
        raise RuntimeError("Angel One credentials are not configured in Streamlit Secrets.")
    import pyotp
    from SmartApi import SmartConnect
    obj = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    session = obj.generateSession(CLIENT_CODE, MPIN, totp)
    if not session or not session.get("status"):
        raise RuntimeError(f"Angel One login failed: {session}")
    return obj

def fetch_candles(obj, exchange, token, from_dt, to_dt, interval="FIFTEEN_MINUTE"):
    params = {
        "exchange": exchange,
        "symboltoken": str(token),
        "interval": interval,
        "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
        "todate": to_dt.strftime("%Y-%m-%d %H:%M"),
    }
    resp = obj.getCandleData(params)
    if not resp or not resp.get("status"):
        return None
    rows = resp.get("data", [])
    if not rows:
        return None
    d = pd.DataFrame(rows, columns=["timestamp","open","high","low","close","volume"])
    for c in ["open","high","low","close","volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["timestamp"] = pd.to_datetime(d["timestamp"], errors="coerce")
    return d.dropna(subset=["timestamp","close"]).sort_values("timestamp").reset_index(drop=True)

# -------------------------
# UI
# -------------------------
with st.sidebar:
    st.header("Trading Controls")
    mode = st.radio("Mode", ["Universe / Data Check", "Paper Scan"])
    min_score = st.slider("Minimum setup score", 50, 100, 70, 5)
    max_stocks = st.slider("Stocks to scan now", 5, 500, 20, 5)
    lookback_days = st.slider("Historical lookback (days)", 5, 30, 10)
    rr = st.selectbox("Risk / Reward", [1.5, 2.0, 2.5, 3.0], index=1)
    st.divider()
    st.write("Angel One:")
    st.write("🟢 Credentials configured" if API_KEY and CLIENT_CODE and TOTP_SECRET and MPIN else "⚪ Credentials not configured")
    st.warning("Live order execution is LOCKED in V3.")

tab1, tab2, tab3 = st.tabs(["NIFTY 500 Universe", "Paper Scan", "Next Build"])

with tab1:
    st.subheader("NIFTY 500 Universe")
    st.info("Universe loading is manual in V3.2 so the app does not get stuck on a slow external website.")

    if "universe" not in st.session_state:
        st.session_state.universe = pd.DataFrame(columns=["symbol"])
    if "mapped" not in st.session_state:
        st.session_state.mapped = pd.DataFrame()

    if st.button("Load NIFTY 500 Universe"):
        with st.spinner("Loading NIFTY 500 list..."):
            try:
                st.session_state.universe = get_nifty500()
                st.success(f"NIFTY 500 universe loaded: {len(st.session_state.universe)} symbols")
            except Exception as e:
                st.error(str(e))

    universe = st.session_state.universe
    if not universe.empty:
        st.dataframe(universe.head(50), use_container_width=True)

    if st.button("Load Angel One Instrument Master"):
        try:
            inst = get_angel_instruments()
            st.success(f"Angel instrument master loaded: {len(inst):,} instruments")
            nse_eq = inst[(inst["exch_seg"] == "NSE") & (inst["symbol"].str.endswith("-EQ"))].copy()
            if universe.empty:
                st.warning("First press 'Load NIFTY 500 Universe'.")
            else:
                u = universe.copy()
                u["angel_symbol"] = u["symbol"] + "-EQ"
                mapped = u.merge(
                    nse_eq[["symbol","token","name","exch_seg"]],
                    left_on="angel_symbol", right_on="symbol", how="left",
                    suffixes=("", "_angel")
                )
                st.session_state.mapped = mapped
                count = int(mapped["token"].notna().sum())
                st.success(f"Mapped NSE equity symbols: {count} / {len(mapped)}")
                st.dataframe(mapped[["symbol","token"]].head(100), use_container_width=True)
        except Exception as e:
            st.error(str(e))

with tab2:
    st.subheader("Paper Scan")
    try:
        universe = get_nifty500()
    except Exception:
        universe = pd.DataFrame(columns=["symbol"])

    if universe.empty:
        st.info("NIFTY 500 universe is not currently available. Use the Universe tab to test loading.")
    else:
        if not (API_KEY and CLIENT_CODE and TOTP_SECRET and MPIN):
            st.info("For automatic historical scanning, add Angel One credentials to Streamlit Secrets. Do not paste them into the chat.")
        else:
            if st.button("Scan NIFTY 500 (Paper Only)"):
                try:
                    obj = angel_login()
                    mapped = st.session_state.get("mapped", pd.DataFrame()).copy()
                    if mapped.empty:
                        inst = get_angel_instruments()
                        nse_eq = inst[(inst["exch_seg"] == "NSE") & (inst["symbol"].str.endswith("-EQ"))].copy()
                        symbols = universe.copy()
                        symbols["angel_symbol"] = symbols["symbol"] + "-EQ"
                        mapped = symbols.merge(nse_eq[["symbol","token"]], left_on="angel_symbol", right_on="symbol", how="inner")
                    mapped = mapped.drop_duplicates("symbol_x" if "symbol_x" in mapped.columns else "symbol").head(max_stocks)

                    end = datetime.now()
                    start = end - timedelta(days=lookback_days)
                    results = []
                    progress = st.progress(0)
                    for i, row in enumerate(mapped.itertuples(index=False), start=1):
                        try:
                            d = fetch_candles(obj, "NSE", row.token, start, end)
                            if d is not None and len(d) >= 210:
                                out = signal(indicators(d), rr)
                                out["symbol"] = row.symbol_x
                                if out["score"] >= min_score:
                                    results.append(out)
                        except Exception:
                            pass
                        progress.progress(i / max(1, len(mapped)))
                        time.sleep(0.35)

                    if results:
                        res = pd.DataFrame(results).sort_values(["score","symbol"], ascending=[False, True])
                        st.success(f"Found {len(res)} qualifying paper setups.")
                        st.dataframe(res, use_container_width=True)
                        st.download_button("Download scan CSV", res.to_csv(index=False), "nifty500_paper_scan.csv", "text/csv")
                    else:
                        st.warning("No qualifying setup found in the selected scan.")
                except Exception as e:
                    st.error(str(e))

with tab3:
    st.subheader("Roadmap")
    st.markdown("""
**V3 completed:** NIFTY 500 universe + Angel One instrument mapping + paper historical scan framework.

**Next:** persistent paper-trade journal → full historical backtest → live 15-minute WebSocket market scanner → risk engine → only after validation, controlled live execution.

**Important:** this version does not place live orders and does not promise profitable signals.
""")
