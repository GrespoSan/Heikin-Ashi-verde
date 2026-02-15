import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(page_title="HA Trend Scanner", page_icon="🕯️", layout="wide")

st.title("📊 Scanner Inversione Heikin Ashi")
st.markdown("Analisi basata sulla tua logica HA originale.")

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.header("⚙️ Configurazione")
tf_choice = st.sidebar.selectbox("Timeframe", ["Daily", "Weekly"])
tf_map = {"Daily": "1d", "Weekly": "1wk"}

st.sidebar.divider()
analisi_mode = st.sidebar.radio(
    "Seleziona Periodo:",
    ["Classica ([-2] vs [-3])", "Live ([-1] vs [-2])"],
    help="Se è domenica e vuoi vedere Venerdì vs Giovedì, usa LIVE."
)

# CARICAMENTO FILE TXT
DEFAULT_SYMBOLS = ["NQ=F", "ES=F", "YM=F", "CL=F", "RB=F", "GC=F", "BTC=F"]
uploaded_file = st.sidebar.file_uploader("📁 Carica file TXT", type=["txt"])
if uploaded_file:
    content = uploaded_file.read().decode("utf-8")
    symbols = [s.strip().upper() for s in content.replace(",", "\n").split() if s.strip()]
else:
    symbols = DEFAULT_SYMBOLS

# --------------------------------------------------
# HEIKIN ASHI CALCULATION (LOGICA ORIGINALE)
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
# DATA FETCH - PULIZIA PROFONDA
# --------------------------------------------------
@st.cache_data
def fetch_data(symbol, interval):
    try:
        # Usiamo auto_adjust=True per pulire i dati alla fonte
        data = yf.download(symbol, period="1y", interval=interval, progress=False, auto_adjust=True)
        if data.empty: return None
        
        # FIX per le colonne se yfinance restituisce MultiIndex
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
        # Rimuoviamo candele sporche (senza volumi o senza movimento di prezzo)
        # Questo serve per RB la domenica, per eliminare la candela 'fake' di oggi
        data = data[(data['Volume'] > 0) & (data['High'] > data['Low'])].dropna()
        
        return data
    except:
        return None

# --------------------------------------------------
# ANALYSIS (LOGICA RIGIDA [-1] vs [-2])
# --------------------------------------------------
def analyze_stock(symbol):
    data = fetch_data(symbol, tf_map[tf_choice])
    if data is None or len(data) < 10:
        return None

    ha_data = get_heikin_ashi(data)
    
    if analisi_mode == "Classica ([-2] vs [-3])":
        idx_rec, idx_prev = -2, -3
    else:
        # LIVE: Questa deve essere Venerdì vs Giovedì se oggi è domenica
        idx_rec, idx_prev = -1, -2

    c_rec = ha_data.iloc[idx_rec]
    c_prev = ha_data.iloc[idx_prev]

    # CONDIZIONE: Verde (C>O) e precedente Rossa (C<O)
    is_verde = c_rec['Close'] > c_rec['Open']
    is_rossa = c_prev['Close'] < c_prev['Open']

    if is_verde and is_rossa:
        return {
            "Symbol": symbol,
            "Data Recente": c_rec.name.strftime("%d/%m/%Y"),
            "Data Precedente": c_prev.name.strftime("%d/%m/%Y"),
            "HA_Open_Rec": round(c_rec['Open'], 4),
            "HA_Close_Rec": round(c_rec['Close'], 4),
            "HA_DataFrame": ha_data
        }
    return None

# --------------------------------------------------
# RUN & DISPLAY
# --------------------------------------------------
results = []
for s in symbols:
    res = analyze_stock(s)
    if res: results.append(res)

if results:
    st.success(f"Trovati {len(results)} segnali in modalità {analisi_mode}")
    df_res = pd.DataFrame(results).drop(columns="HA_DataFrame")
    st.table(df_res)
    
    st.divider()
    sel = st.selectbox("Seleziona simbolo per il grafico:", [r["Symbol"] for r in results])
    sd = next(r for r in results if r["Symbol"] == sel)
    
    # Grafico
    d_plot = sd["HA_DataFrame"].tail(30)
    fig = go.Figure(data=[go.Candlestick(
        x=d_plot.index, open=d_plot['Open'], high=d_plot['High'], 
        low=d_plot['Low'], close=d_plot['Close']
    )])
    fig.update_layout(xaxis_rangeslider_visible=False, height=500, title=f"Dettaglio {sel}")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning(f"Nessun segnale trovato in modalità {analisi_mode}.")
    st.info("Nota: Se RB non appare, controlla che Venerdì sia effettivamente VERDE Heikin Ashi e Giovedì ROSSO.")