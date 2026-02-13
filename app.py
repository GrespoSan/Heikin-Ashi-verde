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
    page_title="HA Scanner Pro",
    page_icon="🕯️",
    layout="wide"
)

st.title("📊 Heikin Ashi Trend Scanner")
st.markdown("**Logica:** Altro Ieri ROSSA 🔴 → Ieri VERDE 🟢 (Candele Heikin Ashi)")

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.header("⚙️ Configurazione")

tf_choice = st.sidebar.selectbox("Seleziona Timeframe", ["Daily", "Weekly"])
tf_map = {"Daily": "1d", "Weekly": "1wk"}

# CARICAMENTO FILE TXT
DEFAULT_SYMBOLS = ["NQ=F", "ES=F", "YM=F", "CL=F", "RB=F", "GC=F", "BTC=F", "EURUSD=X"]
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
    ha_df = pd.DataFrame(index=df.index)
    ha_df['Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    ha_open = np.zeros(len(df))
    ha_open[0] = (df['Open'].iloc[0] + df['Close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i-1] + ha_df['Close'].iloc[i-1]) / 2
    ha_df['Open'] = ha_open
    
    ha_df['High'] = pd.concat([df['High'], ha_df['Open'], ha_df['Close']], axis=1).max(axis=1)
    ha_df['Low'] = pd.concat([df['Low'], ha_df['Open'], ha_df['Close']], axis=1).min(axis=1)
    return ha_df

# --------------------------------------------------
# DATA FETCH
# --------------------------------------------------
@st.cache_data
def fetch_data(symbol, interval):
    try:
        # Scarichiamo un po' di dati in più per calcolare bene la HA iniziale
        df = yf.download(symbol, period="1y", interval=interval, progress=False, auto_adjust=False)
        if df is None or df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except:
        return None

# --------------------------------------------------
# ANALYSIS
# --------------------------------------------------
def analyze_stock(symbol):
    data = fetch_data(symbol, tf_map[tf_choice])
    if data is None or len(data) < 10:
        return None

    # Calcolo Heikin Ashi
    ha_data = get_heikin_ashi(data)
    
    # --- GESTIONE CANDELA LIVE ---
    # Se il mercato è aperto, l'ultima riga è "Oggi". 
    # Noi vogliamo le ultime due candele COMPLETAMENTE CHIUSE.
    # Escludiamo l'ultima riga se la data è uguale a oggi
    last_date = ha_data.index[-1].date()
    if last_date >= date.today():
        # L'ultima riga è oggi, quindi "Ieri" è la penultima (-2)
        # e "Altro Ieri" è la terzultima (-3)
        ieri = ha_data.iloc[-2]
        altro_ieri = ha_data.iloc[-3]
    else:
        # L'ultima riga è già una candela chiusa (es. weekend o mercato chiuso)
        ieri = ha_data.iloc[-1]
        altro_ieri = ha_data.iloc[-2]

    # Condizione richiesta
    ieri_verde = ieri['Close'] > ieri['Open']
    altro_ieri_rossa = altro_ieri['Close'] < altro_ieri['Open']

    if ieri_verde and altro_ieri_rossa:
        return {
            "Symbol": symbol,
            "Segnale": "🟢 Inversione Bullish",
            "Data Segnale": ieri.name.strftime("%d/%m/%Y"),
            "HA_Data": ha_data
        }
    return None

# --------------------------------------------------
# RUN SCANNER
# --------------------------------------------------
results = []
with st.spinner("Analisi tecnica in corso..."):
    for s in symbols:
        res = analyze_stock(s)
        if res:
            results.append(res)

# --------------------------------------------------
# OUTPUT
# --------------------------------------------------
if results:
    st.success(f"Trovati {len(results)} segnali validi")
    st.table(pd.DataFrame(results)[["Symbol", "Segnale", "Data Segnale"]])
    
    st.divider()
    selected = st.selectbox("Seleziona simbolo per visualizzare il grafico HA:", [r["Symbol"] for r in results])
    sel = next(r for r in results if r["Symbol"] == selected)
    
    # Grafico HA
    d_plot = sel["HA_Data"].tail(40)
    fig = go.Figure(data=[go.Candlestick(
        x=d_plot.index,
        open=d_plot['Open'], high=d_plot['High'],
        low=d_plot['Low'], close=d_plot['Close']
    )])
    fig.update_layout(title=f"Candele Heikin Ashi: {selected}", xaxis_rangeslider_visible=False, height=600)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Nessun segnale trovato. La condizione HA Ieri Verde / Altro Ieri Rossa non è soddisfatta al momento.")