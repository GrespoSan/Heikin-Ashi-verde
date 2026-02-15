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
st.info("💡 DI DOMENICA: Usa la modalità 'Live (Oggi vs Ieri)' per analizzare il Venerdì.")

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.header("⚙️ Configurazione")
tf_choice = st.sidebar.selectbox("Timeframe", ["Daily", "Weekly"])
tf_map = {"Daily": "1d", "Weekly": "1wk"}

# TOGGLE PER GLI INDICI
st.sidebar.divider()
analisi_mode = st.sidebar.radio(
    "Seleziona Periodo:",
    ["Classica ([-2] vs [-3])", "Live ([-1] vs [-2])"],
    help="Usa Classica nei giorni feriali. Usa Live nel weekend o se vuoi il segnale di oggi."
)

# CARICAMENTO FILE TXT
DEFAULT_SYMBOLS = ["NQ=F", "ES=F", "YM=F", "CL=F", "RB=F", "GC=F", "BTC=F"]
uploaded_file = st.sidebar.file_uploader("📁 Carica file TXT", type=["txt"])
if uploaded_file:
    content = uploaded_file.read().decode("utf-8")
    symbols = content.replace(",", "\n").split()
    symbols = [s.strip().upper() for s in symbols if s.strip()]
else:
    symbols = DEFAULT_SYMBOLS

# --------------------------------------------------
# HEIKIN ASHI (LA TUA LOGICA ORIGINALE)
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
    except: return None

# --------------------------------------------------
# ANALYSIS (ADATTATA COL TOGGLE)
# --------------------------------------------------
def analyze_stock(symbol):
    data = fetch_data(symbol, tf_map[tf_choice])
    if data is None or len(data) < 10: return None
    ha_data = get_heikin_ashi(data)
    
    # SELEZIONE INDICI
    if analisi_mode == "Classica ([-2] vs [-3])":
        idx_rec, idx_prev = -2, -3
    else:
        idx_rec, idx_prev = -1, -2

    c_rec, c_prev = ha_data.iloc[idx_rec], ha_data.iloc[idx_prev]

    # CONDIZIONE: VERDE dopo ROSSA
    if (c_rec['Close'] > c_rec['Open']) and (c_prev['Close'] < c_prev['Open']):
        return {
            "Symbol": symbol,
            "Data Prec (Rossa)": c_prev.name.strftime("%d/%m/%Y"),
            "Data Rec (Verde)": c_rec.name.strftime("%d/%m/%Y"),
            "HA_Open_Rec": round(c_rec['Open'], 4),
            "HA_Close_Rec": round(c_rec['Close'], 4),
            "HA_DataFrame": ha_data
        }
    return None

# --------------------------------------------------
# RUN
# --------------------------------------------------
results = []
for s in symbols:
    res = analyze_stock(s)
    if res: results.append(res)

if results:
    st.success(f"Trovati {len(results)} segnali.")
    st.table(pd.DataFrame(results).drop(columns="HA_DataFrame"))
    
    sel = st.selectbox("Grafico:", [r["Symbol"] for r in results])
    sd = next(r for r in results if r["Symbol"] == sel)
    d_plot = sd["HA_DataFrame"].tail(30)
    
    fig = go.Figure(data=[go.Candlestick(x=d_plot.index, open=d_plot['Open'], high=d_plot['High'], low=d_plot['Low'], close=d_plot['Close'])])
    fig.update_layout(xaxis_rangeslider_visible=False, height=600, title=f"Dettaglio HA: {sel}")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Nessun segnale trovato.")