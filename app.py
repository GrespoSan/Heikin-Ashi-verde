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
    page_title="HA Scanner",
    page_icon="🕯️",
    layout="wide"
)

st.title("📊 Heikin Ashi Trend Scanner")
st.markdown("**Segnale:** Ieri VERDE (HA) e Altro Ieri ROSSA (HA)")

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.header("⚙️ Configurazione")

# Selezione Timeframe
tf_choice = st.sidebar.selectbox("Seleziona Timeframe", ["Daily", "Weekly"])
tf_map = {"Daily": "1d", "Weekly": "1wk"}

# Ripristino caricamento file TXT
DEFAULT_SYMBOLS = [
    "NQ=F", "ES=F", "YM=F", "RTY=F", "^GDAXI", "CL=F", "RB=F", "GC=F", "BTC=F"
]

uploaded_file = st.sidebar.file_uploader("📁 Carica file TXT con simboli", type=["txt"])

if uploaded_file:
    symbols = uploaded_file.read().decode("utf-8").replace(",", "\n").split()
    symbols = [s.strip().upper() for s in symbols if s.strip()]
else:
    symbols = DEFAULT_SYMBOLS

# --------------------------------------------------
# HEIKIN ASHI CALCULATION
# --------------------------------------------------
def get_heikin_ashi(df):
    ha_df = pd.DataFrame(index=df.index)
    
    # HA Close = (O + H + L + C) / 4
    ha_df['Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    # HA Open = (Open_prev + Close_prev) / 2
    ha_open = np.zeros(len(df))
    ha_open[0] = (df['Open'].iloc[0] + df['Close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i-1] + ha_df['Close'].iloc[i-1]) / 2
    ha_df['Open'] = ha_open
    
    # HA High = max(High, HA_Open, HA_Close)
    ha_df['High'] = pd.concat([df['High'], ha_df['Open'], ha_df['Close']], axis=1).max(axis=1)
    
    # HA Low = min(Low, HA_Open, HA_Close)
    ha_df['Low'] = pd.concat([df['Low'], ha_df['Open'], ha_df['Close']], axis=1).min(axis=1)
    
    return ha_df

# --------------------------------------------------
# DATA FETCH
# --------------------------------------------------
@st.cache_data
def fetch_data(symbol, interval):
    end = date.today() + timedelta(days=1)
    days_back = 400 if interval == "1wk" else 200
    start = end - timedelta(days=days_back)
    
    df = yf.download(symbol, start=start, end=end, interval=interval, progress=False, auto_adjust=False)
    
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    return df.dropna()

# --------------------------------------------------
# ANALYSIS
# --------------------------------------------------
def analyze_stock(symbol):
    data = fetch_data(symbol, tf_map[tf_choice])
    if data is None or len(data) < 10:
        return None

    # Calcolo candele Heikin Ashi
    ha_data = get_heikin_ashi(data)
    
    # Candela di IERI (ultima riga) e ALTRO IERI (penultima)
    ieri = ha_data.iloc[-1]
    altro_ieri = ha_data.iloc[-2]

    # Condizione: Ieri Verde (C > O) e Altro Ieri Rossa (C < O)
    ieri_verde = ieri['Close'] > ieri['Open']
    altro_ieri_rossa = altro_ieri['Close'] < altro_ieri['Open']

    if ieri_verde and altro_ieri_rossa:
        return {
            "Symbol": symbol,
            "Segnale": "🟢 Inversione Bullish HA",
            "Data": ieri.name,
            "HA_Data": ha_data
        }
    return None

# --------------------------------------------------
# EXECUTION
# --------------------------------------------------
results = []
with st.spinner(f"Scansione {tf_choice} in corso..."):
    for s in symbols:
        r = analyze_stock(s)
        if r:
            results.append(r)

# --------------------------------------------------
# DISPLAY
# --------------------------------------------------
if results:
    df_results = pd.DataFrame(results)[["Symbol", "Segnale", "Data"]]
    df_results["Data"] = df_results["Data"].dt.strftime("%d/%m/%Y")
    st.table(df_results)
    
    st.divider()
    selected = st.selectbox("Seleziona simbolo per il grafico HA:", [r["Symbol"] for r in results])
    sel = next(r for r in results if r["Symbol"] == selected)
    
    # Grafico con Candele Heikin Ashi
    d_plot = sel["HA_Data"].tail(40) # Ultime 40 candele HA
    
    fig = go.Figure(data=[go.Candlestick(
        x=d_plot.index,
        open=d_plot['Open'],
        high=d_plot['High'],
        low=d_plot['Low'],
        close=d_plot['Close'],
        name="Candele Heikin Ashi"
    )])

    fig.update_layout(
        title=f"Grafico HEIKIN ASHI - {selected}",
        xaxis_rangeslider_visible=False,
        height=600,
        yaxis_title="Prezzo HA"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Nessun segnale trovato con i criteri Heikin Ashi.")