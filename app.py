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
    page_title="HA Trend Scanner",
    page_icon="🕯️",
    layout="wide"
)

st.title("📊 Scanner Inversione Heikin Ashi")

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
st.sidebar.header("⚙️ Configurazione")
tf_choice = st.sidebar.selectbox("Timeframe", ["Daily", "Weekly"])
tf_map = {"Daily": "1d", "Weekly": "1wk"}

st.sidebar.divider()
analisys_mode = st.sidebar.radio(
    "Modalità di Confronto:",
    ("Classica (Ieri vs Altro Ieri)", "Live (Oggi vs Ieri)"),
    help="Se RB è sbagliato in 'Classica', assicurati che oggi non sia un giorno festivo o che i dati siano aggiornati."
)

st.sidebar.divider()
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
# DATA FETCH + STRICT CLEANING
# --------------------------------------------------
@st.cache_data
def fetch_data(symbol, interval):
    try:
        data = yf.download(symbol, period="1y", interval=interval, progress=False, auto_adjust=False)
        if data.empty: return None
        
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
            
        # Rimuoviamo righe con valori mancanti o Volume 0 (spesso candele errate)
        data = data.dropna(subset=['Open', 'High', 'Low', 'Close'])
        
        # 🔥 FIX CRUCIALE: Se l'ultima candela è di OGGI, la rimuoviamo per la modalità 'Classica'
        # in modo che iloc[-1] diventi effettivamente 'Ieri' e iloc[-2] 'Altro Ieri'
        today_date = date.today()
        if data.index[-1].date() >= today_date:
            data_yesterday_back = data.iloc[:-1] # Escludiamo la candela live
        else:
            data_yesterday_back = data
            
        return data, data_yesterday_back
    except:
        return None

# --------------------------------------------------
# ANALYSIS
# --------------------------------------------------
def analyze_stock(symbol):
    fetched = fetch_data(symbol, tf_map[tf_choice])
    if fetched is None: return None
    
    data_full, data_only_closed = fetched
    
    # Selezioniamo il dataset in base al toggle
    if analisys_mode == "Classica (Ieri vs Altro Ieri)":
        target_df = data_only_closed
        label_rec, label_prec = "Ieri", "Altro Ieri"
    else:
        target_df = data_full
        label_rec, label_prec = "Oggi/Live", "Ieri"

    if len(target_df) < 5: return None
    
    ha_data = get_heikin_ashi(target_df)
    
    # Ora iloc[-1] è SEMPRE la candela più recente della modalità scelta
    c_recente = ha_data.iloc[-1]
    c_precedente = ha_data.iloc[-2]

    recente_verde = c_recente['Close'] > c_recente['Open']
    precedente_rossa = c_precedente['Close'] < c_precedente['Open']

    if recente_verde and precedente_rossa:
        return {
            "Symbol": symbol,
            f"Data {label_prec}": c_precedente.name.strftime("%d/%m/%Y"),
            f"Colore {label_prec}": "🔴 ROSSA",
            f"Data {label_rec}": c_recente.name.strftime("%d/%m/%Y"),
            f"Colore {label_rec}": "🟢 VERDE",
            "HA_DataFrame": ha_data
        }
    return None

# --------------------------------------------------
# RUN & DISPLAY
# --------------------------------------------------
results = []
with st.spinner("Scansione..."):
    for s in symbols:
        res = analyze_stock(s)
        if res: results.append(res)

if results:
    st.success(f"Trovati {len(results)} segnali ({analisys_mode})")
    df_res = pd.DataFrame(results)
    cols = ["Symbol"] + [c for c in df_res.columns if "Data" in c or "Colore" in c]
    st.dataframe(df_res[cols], use_container_width=True)
    
    selected = st.selectbox("Grafico:", [r["Symbol"] for r in results])
    sel_data = next(r for r in results if r["Symbol"] == selected)
    d_plot = sel_data["HA_DataFrame"].tail(30)
    
    fig = go.Figure(data=[go.Candlestick(x=d_plot.index, open=d_plot['Open'], high=d_plot['High'], low=d_plot['Low'], close=d_plot['Close'])])
    fig.update_layout(xaxis_rangeslider_visible=False, height=500, title=f"Dettaglio HA: {selected}")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Nessun segnale trovato.")