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
st.markdown("Cerca: **Ieri VERDE** (HA Close > HA Open) e **Altro Ieri ROSSA** (HA Close < HA Open)")

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.header("⚙️ Configurazione")
tf_choice = st.sidebar.selectbox("Timeframe", ["Daily", "Weekly"])
tf_map = {"Daily": "1d", "Weekly": "1wk"}

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
# HEIKIN ASHI CALCULATION
# --------------------------------------------------
def get_heikin_ashi(df):
    ha_df = df.copy()
    
    # 1. HA Close
    ha_df['Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    # 2. HA Open
    ha_open = np.zeros(len(df))
    ha_open[0] = (df['Open'].iloc[0] + df['Close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i-1] + ha_df['Close'].iloc[i-1]) / 2
    ha_df['Open'] = ha_open
    
    # 3. HA High & Low
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
# ANALYSIS (LOGICA STRICT: -2 vs -3)
# --------------------------------------------------
def analyze_stock(symbol):
    data = fetch_data(symbol, tf_map[tf_choice])
    if data is None or len(data) < 5:
        return None

    # Calcolo HA
    ha_data = get_heikin_ashi(data)
    
    # Logica: Ieri (-2) vs Altro Ieri (-3)
    # Ignora sempre l'ultima candela (-1) che potrebbe essere live/oggi
    ieri = ha_data.iloc[-2]
    altro_ieri = ha_data.iloc[-3]

    # Condizioni Colore
    ieri_verde = ieri['Close'] > ieri['Open']
    altro_ieri_rossa = altro_ieri['Close'] < altro_ieri['Open']

    if ieri_verde and altro_ieri_rossa:
        return {
            "Symbol": symbol,
            
            # DATI ALTRO IERI (Rossa)
            "Data Altro Ieri": altro_ieri.name.strftime("%d/%m/%Y"),
            "HA Open (A.Ieri)": round(altro_ieri['Open'], 4),
            "HA Close (A.Ieri)": round(altro_ieri['Close'], 4),
            
            # DATI IERI (Verde)
            "Data Ieri": ieri.name.strftime("%d/%m/%Y"),
            "HA Open (Ieri)": round(ieri['Open'], 4),
            "HA Close (Ieri)": round(ieri['Close'], 4),
            
            "DataFrame": data,
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
    st.success(f"Trovati {len(results)} segnali di inversione!")
    
    # Creazione DataFrame per la tabella
    df_results = pd.DataFrame(results)
    
    # Seleziona e ordina le colonne da mostrare
    cols_to_show = [
        "Symbol", 
        "Data Altro Ieri", "HA Open (A.Ieri)", "HA Close (A.Ieri)", 
        "Data Ieri", "HA Open (Ieri)", "HA Close (Ieri)"
    ]
    
    st.dataframe(df_results[cols_to_show], use_container_width=True)
    
    st.divider()
    
    # Grafico
    selected = st.selectbox("Dettaglio Grafico:", [r["Symbol"] for r in results])
    sel_data = next(r for r in results if r["Symbol"] == selected)
    
    # Grafico Heikin Ashi
    d_plot = sel_data["HA_DataFrame"].tail(30)
    
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=d_plot.index,
        open=d_plot['Open'], high=d_plot['High'],
        low=d_plot['Low'], close=d_plot['Close'],
        name="Heikin Ashi"
    ))
    
    fig.update_layout(
        title=f"Analisi HA: {selected} (Daily/Weekly)", 
        xaxis_rangeslider_visible=False,
        height=600
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Nessun segnale trovato con i criteri: Altro Ieri ROSSA -> Ieri VERDE.")