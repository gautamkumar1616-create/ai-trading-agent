
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="AI Trading Agent MVP", layout="wide")
st.title("📈 AI Trading Agent — NIFTY 15m MVP")
st.caption("Research/scanner prototype. Paper-trading only; not financial advice.")

uploaded = st.file_uploader("Upload NIFTY/stock 15-minute CSV", type=["csv"])

def normalize(df):
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    aliases = {
        "datetime":"timestamp", "date":"timestamp", "time":"timestamp",
        "open_price":"open", "high_price":"high", "low_price":"low",
        "close_price":"close", "vol":"volume"
    }
    df = df.rename(columns={k:v for k,v in aliases.items() if k in df.columns})
    required = {"open","high","low","close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.sort_values("timestamp")
    for c in ["open","high","low","close","volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["open","high","low","close"]).reset_index(drop=True)

def indicators(df, dc_len=20, rsi_len=14):
    d=df.copy()
    d["ema20"]=d["close"].ewm(span=20, adjust=False).mean()
    d["ema50"]=d["close"].ewm(span=50, adjust=False).mean()
    d["ema200"]=d["close"].ewm(span=200, adjust=False).mean()
    tr=pd.concat([
        d["high"]-d["low"],
        (d["high"]-d["close"].shift()).abs(),
        (d["low"]-d["close"].shift()).abs()
    ],axis=1).max(axis=1)
    d["atr14"]=tr.rolling(14).mean()
    delta=d["close"].diff()
    gain=delta.clip(lower=0).rolling(rsi_len).mean()
    loss=(-delta.clip(upper=0)).rolling(rsi_len).mean()
    rs=gain/loss.replace(0,np.nan)
    d["rsi"]=100-(100/(1+rs))
    if "volume" in d.columns:
        d["vol_sma20"]=d["volume"].rolling(20).mean()
    else:
        d["volume"]=np.nan
        d["vol_sma20"]=np.nan
    # Daily-session VWAP approximation: resets on date if timestamp exists.
    if "timestamp" in d.columns:
        day=d["timestamp"].dt.date
        tp=(d["high"]+d["low"]+d["close"])/3
        pv=tp*d["volume"].fillna(0)
        d["vwap"]=pv.groupby(day).cumsum()/d["volume"].fillna(0).groupby(day).cumsum().replace(0,np.nan)
    else:
        d["vwap"]=((d["high"]+d["low"]+d["close"])/3).expanding().mean()
    d["dc_high"]=d["high"].rolling(dc_len).max().shift(1)
    d["dc_low"]=d["low"].rolling(dc_len).min().shift(1)
    return d

def score_row(r):
    bull=0; bear=0; reasons=[]
    if r["close"]>r["ema20"]: bull+=15; reasons.append("Above EMA20")
    if r["ema20"]>r["ema50"]: bull+=15; reasons.append("EMA20 > EMA50")
    if r["close"]>r["ema200"]: bull+=10; reasons.append("Above EMA200")
    if r["close"]>r["vwap"]: bull+=15; reasons.append("Above VWAP")
    if 55<=r["rsi"]<=70: bull+=15; reasons.append("RSI momentum")
    if r["close"]>r["dc_high"]: bull+=20; reasons.append("DC20 breakout")
    if pd.notna(r["volume"]) and pd.notna(r["vol_sma20"]) and r["volume"]>1.5*r["vol_sma20"]:
        bull+=10; reasons.append("Volume expansion")
    if r["close"]<r["ema20"]: bear+=15
    if r["ema20"]<r["ema50"]: bear+=15
    if r["close"]<r["ema200"]: bear+=10
    if r["close"]<r["vwap"]: bear+=15
    if 30<=r["rsi"]<=45: bear+=15
    if r["close"]<r["dc_low"]: bear+=20
    if pd.notna(r["volume"]) and pd.notna(r["vol_sma20"]) and r["volume"]>1.5*r["vol_sma20"]:
        bear+=10
    return bull, bear, reasons

if uploaded:
    try:
        df=normalize(pd.read_csv(uploaded))
        d=indicators(df)
        scores=[]
        reasons=[]
        for _,r in d.iterrows():
            b,be,rs=score_row(r)
            scores.append(max(b,be)); reasons.append(", ".join(rs))
        d["score"]=scores
        d["reasons"]=reasons
        d["signal"]="NO TRADE"
        d.loc[(d["score"]>=70)&(d["close"]>d["vwap"])& (d["rsi"]>=55),"signal"]="WATCH LONG"
        d.loc[(d["score"]>=70)&(d["close"]<d["vwap"])& (d["rsi"]<=45),"signal"]="WATCH SHORT"

        latest=d.iloc[-1]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Latest Close", f'{latest["close"]:.2f}')
        c2.metric("Setup Score", f'{latest["score"]:.0f}/100')
        c3.metric("RSI", f'{latest["rsi"]:.1f}' if pd.notna(latest["rsi"]) else "—")
        c4.metric("Signal", latest["signal"])

        st.subheader("Latest analysis")
        st.write(latest["reasons"] if latest["reasons"] else "No qualifying conditions.")

        view_cols=[c for c in ["timestamp","close","ema20","ema50","ema200","vwap","rsi","dc_high","dc_low","score","signal"] if c in d.columns]
        st.dataframe(d[view_cols].tail(50), use_container_width=True)

        st.subheader("Top setups in the uploaded data")
        tops=d[d["signal"]!="NO TRADE"].sort_values("score", ascending=False).head(20)
        st.dataframe(tops[view_cols], use_container_width=True)

        csv=d.to_csv(index=False).encode()
        st.download_button("Download analysed CSV", csv, "trading_agent_analysis.csv", "text/csv")
    except Exception as e:
        st.error(str(e))
else:
    st.info("CSV upload karo. Expected columns: timestamp/date, open, high, low, close, optional volume.")
    st.markdown("""
### Current MVP logic
- EMA 20/50/200
- VWAP
- RSI 14
- Donchian Channel 20 (DC20)
- Volume expansion when volume is available
- 0–100 setup score
- WATCH LONG / WATCH SHORT / NO TRADE

**Next build:** historical backtest engine → risk/SL/target module → Angel One data connector → live scanner → AI explanation.
""")
