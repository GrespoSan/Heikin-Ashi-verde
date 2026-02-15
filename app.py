import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(page_title="HA Trend Scanner - DEBUG MODE", page_icon="🕯️", layout="wide")

st.title("📊 Scanner Heikin Ashi + Debug Monitor")

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
    index=1 # Default su Live per testare RB oggi
)

DEFAULT_SYMBOLS = ["NQ=F", "ES=F", "YM=F", "CL=F", "RB=F", "GC=F", "BTC=F"]
uploaded_file = st.sidebar.file_uploader("📁 Carica file TXT", type=["txt"])
symbols = [s.strip().upper() for s in uploaded_file.read().decode("utf-8").replace(",", "\n").split() if s.strip()] if uploaded_file else DEFAULT_SYMBOLS

# --------------------------------------------------
# HEIKIN ASHI (LOGICA ORIGINALE)
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
        data = yf.download(symbol, period="1y", interval=interval, progress=False, auto_adjust=True)
        if data.empty: return None
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        
        # Pulizia base: eliminiamo solo i weekend vuoti assoluti
        data = data[data['Volume'] > 0].dropna()
        return data
    except: return None

# --------------------------------------------------
# LOGICA DI ANALISI E RACCOLTA DEBUG
# --------------------------------------------------
results = []
debug_info = []

with st.spinner("Analisi in corso..."):
    for s in symbols:
        data = fetch_data(s, tf_map[tf_choice])
        if data is None or len(data) < 5: continue
        
        ha_data = get_heikin_ashi(data)
        
        # Salviamo i dati per il Debug (Ultime 3 date reali nel DB)
        debug_info.append({
            "Simbolo": s,
            "[-3] Date": ha_data.index[-3].strftime("%d/%m"),
            "[-2] Date": ha_data.index[-2].strftime("%d/%m"),
            "[-1] Date": ha_data.index[-1].strftime("%d/%m")
        })

        # Selezione Indici
        idx_rec, idx_prev = (-1, -2) if analisi_mode == "Live ([-1] vs [-2])" else (-2, -3)
        
        c_rec = ha_data.iloc[idx_rec]
        c_prev = ha_data.iloc[idx_prev]
        
        # Test Colore
        if (c_rec['Close'] > c_rec['Open']) and (c_prev['Close'] < c_prev['Open']):
            results.append({
                "Symbol": s,
                "Data Prec": c_prev.name.strftime("%d/%m"),
                "Data Rec": c_rec.name.strftime("%d/%m"),
                "HA_Open_Rec": round(c_rec['Open'], 4),
                "HA_Close_Rec": round(c_rec['Close'], 4),
                "ha_df": ha_data
            })

# --------------------------------------------------
# DISPLAY RISULTATI
# --------------------------------------------------
if results:
    st.success(f"Segnali trovati: {len(results)}")
    st.table(pd.DataFrame(results).drop(columns="ha_df"))
else:
    st.warning("Nessun segnale trovato con la logica selezionata.")

# --------------------------------------------------
# SEZIONE DEBUG (FONDAMENTALE)
# --------------------------------------------------
st.divider()
with st.expander("🔍 MONITOR DEBUG (Controlla le date qui sotto per RB)"):
    st.write("Queste sono le date che lo script sta effettivamente assegnando agli indici:")
    st.table(pd.DataFrame(debug_info))

if results:
    sel = st.selectbox("Grafico:", [r["Symbol"] for r in results])
    sd = next(r for r in results if r["Symbol"] == sel)
    d_p = sd["ha_df"].tail(20)
    fig = go.Figure(data=[go.Candlestick(x=d_p.index, open=d_p['Open'], high=d_p['High'], low=d_p['Low'], close=d_p['Close'])])
    fig.update_layout(xaxis_rangeslider_visible=False, title=f"Dettaglio {sel}")
    st.plotly_chart(fig, use_container_width=True)