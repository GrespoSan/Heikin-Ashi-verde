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
    page_title="HA Trend Scanner",
    page_icon="🕯️",
    layout="wide"
)

st.title("📊 Scanner Inversione Heikin Ashi")
st.markdown("Cerca: **Inversione Colore** (Verde preceduta da Rossa)")

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.header("⚙️ Configurazione")
tf_choice = st.sidebar.selectbox("Timeframe", ["Daily", "Weekly"])
tf_map = {"Daily": "1d", "Weekly": "1wk"}

# --- TOGGLE AGGIUNTO ---
st.sidebar.divider()
analisi_mode = st.sidebar.radio(
    "Seleziona Periodo:",
    ["Ieri vs Altro Ieri", "Oggi vs Ieri"],
    help="Ieri vs Altro Ieri usa gli indici [-2] e [-3]. Oggi vs Ieri usa [-1] e [-2]."
)

# --- CARICAMENTO FILE TXT ---
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
# HEIKIN ASHI CALCULATION (LA TUA LOGICA)
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
# DATA FETCH (LA TUA LOGICA)
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
# ANALYSIS (ADATTATA COL TOGGLE)
# --------------------------------------------------
def analyze_stock(symbol):
    data = fetch_data(symbol, tf_map[tf_choice])
    if data is None or len(data) < 5:
        return None

    ha_data = get_heikin_ashi(data)
    
    # Selezione indici in base al toggle
    if analisi_mode == "Ieri vs Altro Ieri":
        idx_rec = -2
        idx_prev = -3
        label_rec = "Ieri"
        label_prev = "Altro Ieri"
    else:
        idx_rec = -1
        idx_prev = -2
        label_rec = "Oggi"
        label_prev = "Ieri"

    candela_rec = ha_data.iloc[idx_rec]
    candela_prev = ha_data.iloc[idx_prev]

    # Condizioni Colore
    verde = candela_rec['Close'] > candela_rec['Open']
    rossa = candela_prev['Close'] < candela_prev['Open']

    if verde and rossa:
        return {
            "Symbol": symbol,
            f"Data {label_prev}": candela_prev.name.strftime("%d/%m/%Y"),
            f"HA Open ({label_prev})": round(candela_prev['Open'], 4),
            f"HA Close ({label_prev})": round(candela_prev['Close'], 4),
            f"Data {label_rec}": candela_rec.name.strftime("%d/%m/%Y"),
            f"HA Open ({label_rec})": round(candela_rec['Open'], 4),
            f"HA Close ({label_rec})": round(candela_rec['Close'], 4),
            "HA_DataFrame": ha_data
        }
    return None

# --------------------------------------------------
# RUN & DISPLAY
# --------------------------------------------------
results = []
with st.spinner(f"Scansione {analisi_mode}..."):
    for s in symbols:
        res = analyze_stock(s)
        if res:
            results.append(res)

if results:
    st.success(f"Trovati {len(results)} segnali ({analisi_mode})")
    df_results = pd.DataFrame(results)
    
    # Colonne dinamiche per la tabella
    cols = ["Symbol"] + [c for c in df_results.columns if "Data" in c or "HA" in c and "DataFrame" not in c]
    st.dataframe(df_results[cols], use_container_width=True)
    
    st.divider()
    selected = st.selectbox("Dettaglio Grafico:", [r["Symbol"] for r in results])
    sel_data = next(r for r in results if r["Symbol"] == selected)
    
    d_plot = sel_data["HA_DataFrame"].tail(30)
    fig = go.Figure(data=[go.Candlestick(
        x=d_plot.index,
        open=d_plot['Open'], high=d_plot['High'],
        low=d_plot['Low'], close=d_plot['Close'],
        name="Heikin Ashi"
    )])
    
    fig.update_layout(title=f"Analisi HA: {selected}", xaxis_rangeslider_visible=False, height=600)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning(f"Nessun segnale trovato in modalità: {analisi_mode}")