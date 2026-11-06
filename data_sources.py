"""Dati con provenienza esplicita; nessun fallback silenzioso fra provider/feed."""
from datetime import datetime, timedelta, timezone
import io
import json
import pandas as pd
from engine import normalize_bars, resample_weekly, invalid_ohlc

def read_import(payload,name,repair=False):
    if name.lower().endswith('.json'):
        obj=json.loads(payload.decode('utf-8-sig'))
        bars=obj.get('bars') if isinstance(obj,dict) else obj
        if not isinstance(bars,list):raise ValueError('JSON: atteso array di barre o oggetto con bars[].')
        return normalize_bars(pd.DataFrame(bars),validate=False)
    return normalize_bars(pd.read_csv(io.BytesIO(payload),sep=None,engine='python'),validate=False)
def yahoo(symbol,start,end,adjusted,repair=False):
    import yfinance as yf
    df=yf.download(symbol,start=start,end=end,interval='1d',auto_adjust=adjusted,progress=False,threads=False,timeout=20)
    if df is None or df.empty:raise ValueError(f'{symbol}: Yahoo non ha restituito dati.')
    if isinstance(df.columns,pd.MultiIndex):df.columns=df.columns.get_level_values(0)
    return normalize_bars(df,validate=False)
def alpaca(symbol,start,end,key,secret,feed='sip',adjustment='split',repair=False):
    if not key or not secret:raise ValueError('Configurare ALPACA_API_KEY e ALPACA_SECRET_KEY nei Secrets Streamlit.')
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed,Adjustment
    now=datetime.now(timezone.utc)-timedelta(minutes=20)
    until=min(datetime.fromisoformat(end).replace(tzinfo=timezone.utc),now)
    req=StockBarsRequest(symbol_or_symbols=symbol,timeframe=TimeFrame.Day,start=datetime.fromisoformat(start).replace(tzinfo=timezone.utc),end=until,feed=DataFeed(feed),adjustment=Adjustment(adjustment))
    bars=StockHistoricalDataClient(key,secret).get_stock_bars(req).df
    if bars.empty:raise ValueError(f'{symbol}: Alpaca non ha restituito dati.')
    bars=bars.xs(symbol,level='symbol').copy()
    bars.index=bars.index.tz_convert('America/New_York').tz_localize(None).normalize()
    return normalize_bars(bars,validate=False)
def completed_bars(df,symbol,market,timeframe='Daily',now=None,repair=False):
    """Equity: calendario della borsa. Futures/24h: esclusa prudentemente tutta la data UTC corrente."""
    now=pd.Timestamp.now(tz='UTC') if now is None else pd.Timestamp(now)
    if now.tzinfo is None:now=now.tz_localize('UTC')
    italy=symbol.endswith('.MI') or market=='Italia'
    other=('=F' in symbol or market=='Commodity / altri' or symbol.endswith('-USD'))
    if other:
        x=df[df.index<now.tz_convert('UTC').tz_localize(None).normalize()].copy()
        note='Chiusura prudente: esclusa la data UTC corrente; calendario futures non ricostruito.'
    else:
        import exchange_calendars as xcals
        code='XMIL' if italy else 'XNYS'
        cal=xcals.get_calendar(code,start=df.index.min()-pd.Timedelta(days=10),end=max(df.index.max(),now.tz_localize(None).normalize())+pd.Timedelta(days=10))
        schedule=cal.schedule
        closes=schedule['close'] if 'close' in schedule else schedule['market_close']
        closes=pd.to_datetime(closes,utc=True)
        sessions=pd.DatetimeIndex(schedule.index)
        if sessions.tz is not None:sessions=sessions.tz_localize(None)
        keep=sessions[(closes+pd.Timedelta(minutes=15)<=now).to_numpy()]
        x=df[df.index.isin(keep)].copy()
        note=f'Calendario {code}; barre ammesse 15 minuti dopo la chiusura ufficiale.'
    # Validazione/rettifica dopo l'esclusione delle candele aperte, prima del Weekly.
    x=normalize_bars(x,repair=repair,validate=repair)
    x['ohlc_valid']=~invalid_ohlc(x)
    if timeframe=='Weekly':
        x=resample_weekly(x)
        # La settimana resta provvisoria fino a sabato UTC, anche venerdì dopo la chiusura.
        days_since_monday=now.weekday()
        if days_since_monday<5:
            monday=now.tz_localize(None).normalize()-pd.Timedelta(days=days_since_monday)
            x=x[x.index<monday]
        note+=' Weekly: settimana corrente esclusa fino a sabato UTC.'
    if x.empty:raise ValueError('Nessuna candela chiusa disponibile nel periodo.')
    return x,note

