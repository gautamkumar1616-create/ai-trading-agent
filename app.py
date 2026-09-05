import os
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Personal AI Trading Agent V2", layout="wide")
st.title("🤖 Personal AI Trading Agent V2")
st.caption("BUY / SELL / NO TRADE • Entry • SL • Target • R:R • Setup Score • Paper Trading")

def sec(name):
    try:
        return st.secrets.get(name, os.getenv(name, ""))
    except Exception:
        return os.getenv(name, "")

api_key = sec("ANGEL_API_KEY")
client_code = sec("ANGEL_CLIENT_CODE")
totp_secret = sec("ANGEL_TOTP_SECRET")

with st.sidebar:
    st.header("Trading Controls")
    mode = st.radio("Mode", ["Paper Trading", "Live Data (next)", "Live Orders (LOCKED)"])
    timeframe = st.selectbox("Timeframe", ["15m", "5m", "30m"], index=0)
    min_score = st.slider("Minimum setup score", 50, 95, 70, 5)
    risk_pct = st.slider("Risk per trade (%)", 0.1, 2.0, 0.5, 0.1)
    st.divider()
    st.write("Angel One:")
    st.write("🟢 Credentials configured" if api_key and client_code and totp_secret else "🟡 Not configured")
    if mode == "Live Orders (LOCKED)":
        st.warning("Live order execution is locked until backtest, paper validation and static-IP setup are complete.")

def rsi(s, period=14):
    d = s.diff()
    gain = d.clip(lower=0)
    loss = -d.clip(upper=0)
    ag = gain.ewm(alpha=1/period, adjust=False).mean()
    al = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - 100/(1+rs)

def indicators(df):
    df = df.copy()
    for c in ["Open","High","Low","Close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "Volume" not in df.columns:
        df["Volume"] = 0
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
    df = df.dropna(subset=["Open","High","Low","Close"])
    df["EMA20"] = df.Close.ewm(span=20, adjust=False).mean()
    df["EMA50"] = df.Close.ewm(span=50, adjust=False).mean()
    df["EMA200"] = df.Close.ewm(span=200, adjust=False).mean()
    df["RSI"] = rsi(df.Close)
    tr = pd.concat([(df.High-df.Low),
                    (df.High-df.Close.shift()).abs(),
                    (df.Low-df.Close.shift()).abs()], axis=1).max(axis=1)
    df["ATR14"] = tr.ewm(alpha=1/14, adjust=False).mean()
    df["VolMA20"] = df.Volume.rolling(20).mean()
    df["DC20High"] = df.High.rolling(20).max().shift(1)
    df["DC20Low"] = df.Low.rolling(20).min().shift(1)
    return df

def make_signal(df):
    df = indicators(df)
    if len(df) < 50:
        return {"Signal":"NO TRADE","Score":0,"Reason":"At least 50 candles required."}
    x = df.iloc[-1]
    L = S = 0
    lr, sr = [], []

    if x.Close > x.EMA20 > x.EMA50:
        L += 20; lr.append("Price > EMA20 > EMA50")
    if x.Close < x.EMA20 < x.EMA50:
        S += 20; sr.append("Price < EMA20 < EMA50")
    if x.Close > x.EMA200:
        L += 10; lr.append("Above EMA200")
    if x.Close < x.EMA200:
        S += 10; sr.append("Below EMA200")
    if pd.notna(x.DC20High) and x.Close > x.DC20High:
        L += 25; lr.append("DC20 breakout")
    if pd.notna(x.DC20Low) and x.Close < x.DC20Low:
        S += 25; sr.append("DC20 breakdown")
    if x.RSI >= 55:
        L += 15; lr.append(f"RSI {x.RSI:.1f}")
    elif x.RSI <= 45:
        S += 15; sr.append(f"RSI {x.RSI:.1f}")
    if pd.notna(x.VolMA20) and x.VolMA20 > 0 and x.Volume > 1.5*x.VolMA20:
        L += 10; S += 10
        lr.append("Volume expansion"); sr.append("Volume expansion")
    if x.Close > x.Open:
        L += 5; lr.append("Bullish candle")
    elif x.Close < x.Open:
        S += 5; sr.append("Bearish candle")

    direction = "BUY" if L >= S else "SELL"
    score = max(L,S)
    atr = float(x.ATR14)
    entry = float(x.Close)

    if direction == "BUY":
        sl, target = entry-1.2*atr, entry+2.4*atr
    else:
        sl, target = entry+1.2*atr, entry-2.4*atr

    rr = abs(target-entry)/abs(entry-sl) if entry != sl else 0
    if score < min_score or atr <= 0:
        direction = "NO TRADE"
        entry = sl = target = rr = np.nan

    return {"Signal":direction,"Score":int(score),"Entry":entry,
            "Stop Loss":sl,"Target":target,"Risk/Reward":rr,
            "RSI":float(x.RSI),"Reason":", ".join(lr if direction=="BUY" else sr)}

st.header("1️⃣ Data")
file = st.file_uploader("Upload 15-minute OHLCV CSV", type="csv")

if file:
    raw = pd.read_csv(file)
    lower = {c.lower().strip():c for c in raw.columns}
    rename = {lower[k.lower()]:k for k in ["Open","High","Low","Close","Volume"] if k.lower() in lower}
    df = raw.rename(columns=rename)

    missing = [c for c in ["Open","High","Low","Close"] if c not in df.columns]
    if missing:
        st.error("Missing columns: " + ", ".join(missing))
    else:
        r = make_signal(df)
        st.header("2️⃣ Current Signal")
        a,b,c,d = st.columns(4)
        a.metric("Signal", r["Signal"])
        b.metric("Setup Score", r["Score"])
        c.metric("R:R", "-" if pd.isna(r["Risk/Reward"]) else f"1:{r['Risk/Reward']:.2f}")
        d.metric("RSI", f"{r['RSI']:.1f}")

        if r["Signal"] != "NO TRADE":
            st.success(f'{r["Signal"]} | Entry ₹{r["Entry"]:.2f} | SL ₹{r["Stop Loss"]:.2f} | Target ₹{r["Target"]:.2f}')
        else:
            st.info("NO TRADE — setup conditions are not strong enough.")

        st.write("**Reason:**", r["Reason"])

        st.header("3️⃣ Paper Trading")
        capital = st.number_input("Paper capital (₹)", 1000.0, 10000000.0, 100000.0, 5000.0)
        if r["Signal"] != "NO TRADE":
            risk_money = capital*risk_pct/100
            unit_risk = abs(r["Entry"]-r["Stop Loss"])
            qty = int(risk_money/unit_risk) if unit_risk else 0
            st.write(f"Risk-based paper quantity: **{qty}**")
            st.write(f"Maximum planned loss at SL: approximately **₹{risk_money:,.0f}**")

        st.header("4️⃣ Latest Candles")
        st.dataframe(df.tail(20), use_container_width=True)
else:
    st.info("CSV upload se V2 signal engine test karo. Next stage mein Angel One live feed connect karenge.")

st.header("5️⃣ Build Roadmap")
st.markdown("CSV → Signal Engine → Paper Trading → Angel One Live WebSocket → Live Scanner → Risk Engine → Controlled Live Orders")
st.caption("Live orders are locked. Never put API keys, passwords, PINs or TOTP secrets in GitHub.")
