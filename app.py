import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date, datetime, timedelta

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="HA Scanner Pro",
    page_icon="🕯️",
    layout="wide"
)

st.title("📊 Scanner Inversione Heikin Ashi")
st.markdown("Cerca: **VERDE** (HA C > O) preceduta da **ROSSA** (HA C < O)")

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.header("⚙️ Configurazione")
tf_choice = st.sidebar.selectbox("Timeframe", ["Daily", "Weekly"])
tf_map = {"Daily": "1d", "Weekly": "1wk"}

# --- TOGGLE PER SELEZIONE PERIODO ---
st.sidebar.divider()
st.sidebar.subheader("Periodo di Analisi")
mode = st.sidebar.radio(
    "Scegli quali candele analizzare:",
    ["Sempre Chiuse (Ieri vs Altro Ieri)", "Ultima disponibile vs Precedente"],
    help="La prima opzione ignora sempre oggi. La seconda usa oggi se il mercato è chiuso o nell'ultima ora."
)

# --- CARICAMENTO FILE TXT ---
st.sidebar.divider()
DEFAULT_SYMBOLS = [
    "NQ=F", "ES=F", "YM=F", "RTY=F", "CL=F", "RB=F", "NG=F", "GC=F", 
    "SI=F", "HG=F", "BTC=F", "ETH=F", "DX-Y.NYB", "6E=F", "6B=F"
]

uploaded_file = st.sidebar.file_uploader("📁 Carica file TXT con simboli", type=["txt"])

if uploaded_file:
    content = uploaded_file.read().decode("utf-8")
    symbols = content.replace(",", "\n").split()
    symbols = [s.strip().upper() for s in symbols if s.strip()]
else:
    symbols = DEFAULT_SYMBOLS

# --------------------------------------------------
# HEIKIN ASHI CALCULATION
# --------------------------------------------------
def get_heikin_ashi(df):
    ha_df = df.copy()
    ha_df['Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    ha_open = np.zeros(len(df))
    ha_open[0] = (df['Open'].iloc[0] + df['Close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i-1] + ha_df['Close'].iloc[i-1]) / 2
    ha_df['Open'] = ha_open
    
    ha_df['High'] = ha_df[['High', 'Open', 'Close']].max(axis=1)
    ha_df['Low'] = ha_df[['Low', 'Open', 'Close']].min(axis=1)
    return ha_df

# --------------------------------------------------
# DATA FETCH
# --------------------------------------------------
@st.cache_data
def fetch_data(symbol, interval):
    try:
        data = yf.download(symbol, period="1y", interval=interval, progress=False, auto_adjust=False)
        if data.empty: return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data.dropna()
    except:
        return None

# --------------------------------------------------
# ANALYSIS
# --------------------------------------------------
def analyze_stock(symbol):
    data = fetch_data(symbol, tf_map[tf_choice])
    if data is None or len(data) < 5:
        return None

    ha_data = get_heikin_ashi(data)
    
    # LOGICA DI SELEZIONE CANDELA
    if mode == "Sempre Chiuse (Ieri vs Altro Ieri)":
        # Escludiamo l'ultima riga se è la data odierna
        last_idx = -2 if ha_data.index[-1].date() >= date.today() else -1
        idx_attuale = last_idx
        idx_precedente = last_idx - 1
    else:
        # Ultima disponibile (anche se live) vs precedente
        idx_attuale = -1
        idx_precedente = -2

    attuale = ha_data.iloc[idx_attuale]
    precedente = ha_data.iloc[idx_precedente]

    # Condizioni Colore
    attuale_verde = attuale['Close'] > attuale['Open']
    precedente_rossa = precedente['Close'] < precedente['Open']

    if attuale_verde and precedente_rossa:
        return {
            "Symbol": symbol,
            "Data Analizzata": attuale.name.strftime("%d/%m/%Y"),
            "Status": "LIVE/OGGI" if attuale.name.date() == date.today() else "CHIUSA",
            "HA_Open": round(attuale['Open'], 4),
            "HA_Close": round(attuale['Close'], 4),
            "HA_DataFrame": ha_data
        }
    return None

# --------------------------------------------------
# RUN & DISPLAY
# --------------------------------------------------
results = []
with st.spinner("Scansione in corso..."):
    for s in symbols:
        res = analyze_stock(s)
        if res:
            results.append(res)

if results:
    st.success(f"Trovati {len(results)} segnali con modalità: {mode}")
    df_res = pd.DataFrame(results)[["Symbol", "Data Analizzata", "Status", "HA_Open", "HA_Close"]]
    st.table(df_res)
    
    selected = st.selectbox("Dettaglio Grafico:", [r["Symbol"] for r in results])
    sel_data = next(r for r in results if r["Symbol"] == selected)
    
    d_plot = sel_data["HA_DataFrame"].tail(30)
    fig = go.Figure(data=[go.Candlestick(
        x=d_plot.index,
        open=d_plot['Open'], high=d_plot['High'],
        low=d_plot['Low'], close=d_plot['Close'],
        name="Heikin Ashi"
    )])
    fig.update_layout(xaxis_rangeslider_visible=False, height=600, title=f"Analisi {selected}")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning(f"Nessun segnale trovato in modalità: {mode}")