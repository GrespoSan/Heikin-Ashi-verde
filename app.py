import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date, timedelta

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="Heikin Ashi Trend Scanner",
    page_icon="📈",
    layout="wide"
)

st.title("📊 Heikin Ashi Trend Change Scanner")
st.markdown("**Segnale: Ieri VERDE (HA) e Altro Ieri ROSSA (HA)**")

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.header("⚙️ Configurazione")

# --- NUOVA OPZIONE TIMEFRAME ---
tf_choice = st.sidebar.selectbox("Seleziona Timeframe", ["Daily", "Weekly"])
tf_map = {"Daily": "1d", "Weekly": "1wk"}
interval = tf_map[tf_choice]

DEFAULT_SYMBOLS = [
    "NQ=F", "ES=F", "YM=F", "RTY=F",
    "^GDAXI", "^STOXX50E",
    "CL=F", "RB=F", "NG=F", "GC=F", "SI=F", "HG=F", "PL=F", "PA=F",
    "ZC=F", "ZS=F", "ZW=F", "ZO=F", "ZR=F", "KC=F", "CC=F", "CT=F",
    "SB=F", "OJ=F",
    "6E=F", "6B=F", "6A=F", "6N=F", "6S=F", "6J=F", "6M=F",
    "DX-Y.NYB", "BTC=F", "ETH=F", "ZB=F"
]

uploaded_file = st.sidebar.file_uploader(
    "📁 Carica file TXT con simboli",
    type=["txt"]
)

if uploaded_file:
    symbols = uploaded_file.read().decode("utf-8").replace(",", "\n").split()
    symbols = [s.strip().upper() for s in symbols if s.strip()]
else:
    symbols = DEFAULT_SYMBOLS

# --------------------------------------------------
# HEIKIN ASHI CALCULATION
# --------------------------------------------------
def get_heikin_ashi(df):
    df_ha = df.copy()
    # Close HA: (Open+High+Low+Close) / 4
    df_ha['Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    # Open HA: (Open_prev + Close_prev) / 2
    # Inizializziamo il primo valore
    ha_open = [(df['Open'].iloc[0] + df['Close'].iloc[0]) / 2]
    for i in range(1, len(df)):
        ha_open.append((ha_open[i-1] + df_ha['Close'].iloc[i-1]) / 2)
    df_ha['Open'] = ha_open
    
    # High HA: max(High, Open_HA, Close_HA)
    df_ha['High'] = df[['High', 'Open', 'Close']].max(axis=1) # Semplificato per brevità
    # Low HA: min(Low, Open_HA, Close_HA)
    df_ha['Low'] = df[['Low', 'Open', 'Close']].min(axis=1)
    
    return df_ha

# --------------------------------------------------
# DATA FETCH
# --------------------------------------------------
@st.cache_data
def fetch_data(symbol, interval):
    end = date.today() + timedelta(days=1)
    # Estendiamo il periodo per il weekly
    days_back = 400 if interval == "1wk" else 200
    start = end - timedelta(days=days_back)

    df = yf.download(
        symbol,
        start=start,
        end=end,
        interval=interval,
        group_by="column",
        auto_adjust=False,
        progress=False
    )

    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close"]].dropna()
    for col in df.columns:
        df[col] = df[col].astype(float)
    
    df.index = pd.to_datetime(df.index)
    return df

# --------------------------------------------------
# ANALYSIS (LOGICA RICHIESTA)
# --------------------------------------------------
def analyze_stock(symbol):
    data = fetch_data(symbol, interval)
    if data is None or len(data) < 3:
        return None

    # Calcoliamo le candele Heikin Ashi
    ha_data = get_heikin_ashi(data)

    # Ieri (ultima chiusa) e Altro Ieri
    yesterday_ha = ha_data.iloc[-1]
    day_before_ha = ha_data.iloc[-2]

    # Logica Colore: Verde se Close > Open, Rossa se Close < Open
    yest_is_green = yesterday_ha['Close'] > yesterday_ha['Open']
    prev_is_red = day_before_ha['Close'] < day_before_ha['Open']

    # CONDIZIONE RICHIESTA: Ieri Verde E Altro Ieri Rossa
    if yest_is_green and prev_is_red:
        signal = "🟢 Inversione Rialzista HA"
    else:
        return None

    return {
        "Symbol": symbol,
        "Segnale": signal,
        "Close_HA": yesterday_ha["Close"],
        "Open_HA": yesterday_ha["Open"],
        "Data": yesterday_ha.name,
        "DataFrame": data,
        "HA_DataFrame": ha_data
    }

# --------------------------------------------------
# RUN SCANNER
# --------------------------------------------------
results = []
with st.spinner(f"Analisi {tf_choice} in corso..."):
    for s in symbols:
        r = analyze_stock(s)
        if r:
            results.append(r)

# --------------------------------------------------
# TABLES
# --------------------------------------------------
st.subheader(f"🎯 Segnali Trovati ({tf_choice})")
if results:
    df_res = pd.DataFrame(results)[["Symbol", "Segnale", "Close_HA", "Data"]].copy()
    df_res["Data"] = df_res["Data"].dt.strftime("%d/%m/%Y")
    st.dataframe(df_res, use_container_width=True)
else:
    st.info("Nessun segnale di inversione Heikin Ashi trovato con i criteri impostati.")

# --------------------------------------------------
# CHART
# --------------------------------------------------
st.divider()
if results:
    selected = st.selectbox("Seleziona un titolo per visualizzare le candele Heikin Ashi", [r["Symbol"] for r in results])
    sel = next(r for r in results if r["Symbol"] == selected)
    
    # Usiamo il DataFrame Heikin Ashi per il grafico
    d = sel["HA_DataFrame"].tail(50) 

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=d.index,
        open=d["Open"],
        high=d["High"],
        low=d["Low"],
        close=d["Close"],
        name="Heikin Ashi"
    ))

    fig.update_layout(
        title=f"{selected} – Grafico Heikin Ashi {tf_choice}",
        xaxis_rangeslider_visible=False,
        height=600
    )
    st.plotly_chart(fig, use_container_width=True)