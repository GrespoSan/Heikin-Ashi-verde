"""Preset di ricerca A/B: segnali LONG Daily, separati dal motore operativo.

Non contiene ottimizzatori; non modifica screener e backtest esistenti.
Esegue segnali su chiusure confermate, ordini all'open successivo.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import numpy as np
import pandas as pd
from engine import Indicators, calculate

PRESET_VERSION = "AB-THREE-EXITS-2026-11-07-v3"
EXIT_METHODS = ("Forces 10/4", "Supertrend 10x2", "Forces HA + HA rossa + trailing 5%")
PRESETS = {
    "A": ("Standard", "Standard"),
    "B": ("Heikin Ashi", "Standard"),
}
PRESET_DESCRIPTIONS = {
    "A": "Ingresso Forces 7/7 Standard",
    "B": "Ingresso Forces 7/7 Heikin Ashi",
}


def preset_id(code, exit_method="Forces 10/4"):
    """ID stabile che descrive anche i costi e la regola di entrata."""
    if code not in PRESETS:
        raise ValueError("Preset sconosciuto")
    if exit_method not in EXIT_METHODS:
        raise ValueError("Uscita sconosciuta")
    obj = {"version": PRESET_VERSION, "code": code, "sources": PRESETS[code],
           "entry": "HA verde + Forces 7/7 crossing up zero + close > EMA200",
           "exit": exit_method, "fees_per_side": 0.0015,
           "trailing": "peak close from position entry; (peak_close-current_close)/entry_fill >= 5%; confirm next open" if exit_method.endswith("trailing 5%") else None,
           "fill": "next session open", "one_position": True}
    return sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]



def supertrend_10x2(df):
    """Supertrend con ATR Wilder(10), fattore 2, su OHLC Standard.

    Bande finali e inversioni basate sulle bande della barra precedente,
    coerentemente con la ricorrenza TradingView; primo ATR inizializzato
    alla SMA dei true ranges. I risultati richiedono confronto con TV.
    True = regime rialzista; False = ribassista; NaN prima del warmup.
    """
    n = len(df)
    high=df.high.to_numpy(dtype=float)
    low=df.low.to_numpy(dtype=float)
    close=df.close.to_numpy(dtype=float)
    tr=np.empty(n)
    tr[0]=high[0]-low[0]
    for i in range(1,n):
        tr[i]=max(high[i]-low[i],abs(high[i]-close[i-1]),abs(low[i]-close[i-1]))
    atr=np.full(n,np.nan)
    if n<10:
        return np.full(n,np.nan)
    atr[9]=float(np.mean(tr[:10]))
    for i in range(10,n):
        atr[i]=(atr[i-1]*9+tr[i])/10
    upper=np.full(n,np.nan)
    lower=np.full(n,np.nan)
    bullish=np.full(n,np.nan)
    for i in range(9,n):
        mid=(high[i]+low[i])/2
        basic_upper=mid+2*atr[i]
        basic_lower=mid-2*atr[i]
        if i==9:
            upper[i]=basic_upper
            lower[i]=basic_lower
            bullish[i]=0.0  # TradingView inizializza in regime ribassista alla prima ATR valida
            continue
        upper[i]=(basic_upper if basic_upper<upper[i-1] or close[i-1]>upper[i-1]
                  else upper[i-1])
        lower[i]=(basic_lower if basic_lower>lower[i-1] or close[i-1]<lower[i-1]
                  else lower[i-1])
        if bullish[i-1]==1.0:
            bullish[i]=0.0 if close[i]<lower[i-1] else 1.0
        else:
            bullish[i]=1.0 if close[i]>upper[i-1] else 0.0
    return bullish

def prepare_preset_features(df):
    """Le serie devono contenere OHLC STANDARD, mai prezzi HA importati.

    Usa esattamente il calcolo Forces dell'engine applicato alle due sorgenti.
    La media 200 è calcolata su close standard. Richiede storico di warmup.
    """
    if len(df) < 220:
        raise ValueError("Servono almeno 220 sedute con OHLC standard per EMA200 e warmup.")
    required = {"open", "high", "low", "close"}
    if not required.issubset(df):
        raise ValueError("Mancano colonne OHLC standard")
    if (df[list(required)] <= 0).any().any():
        raise ValueError("OHLC non positivi")
    if ((df.high < df[["open","close","low"]].max(axis=1)) |
        (df.low > df[["open","close","high"]].min(axis=1))).any():
        raise ValueError("Barre OHLC incoerenti; dati da verificare")
    result = {}
    for source in ("Standard", "Heikin Ashi"):
        for sma, ema in ((7,7),(10,4)):
            cfg = Indicators(sma=sma,ema=ema,forces_source=source,trend_ema=200)
            x = calculate(df,cfg)
            result[(source,sma,ema)] = x.forces.to_numpy(dtype=float)
            if source == "Standard" and sma == 7:
                result["ha_green"] = x.ha.to_numpy(dtype=bool)
                result["ema200"] = x.price_ema.to_numpy(dtype=float)
    result["supertrend_10x2"] = supertrend_10x2(df)
    return result


def simulate_preset(df, features, code, start=None, end=None, exit_method="Forces 10/4"):
    """Costo 0,15% lato acquisto e vendita, composto, capitale teorico intero.

    La posizione aperta è riportata separatamente (mark-to-market), non come trade
    realizzato. Nessun nuovo ingresso all'open di un'uscita. Nessun intraday stop.
    """
    if code not in PRESETS:
        raise ValueError("Preset sconosciuto")
    if exit_method not in EXIT_METHODS:
        raise ValueError("Uscita sconosciuta")
    in_source, out_source = PRESETS[code]
    entry_force = features[(in_source,7,7)]
    exit_force = features[(out_source,10,4)]
    st_bull = features["supertrend_10x2"]
    ha_force_exit = features[("Heikin Ashi",10,4)]
    ha = features["ha_green"]
    ema200 = features["ema200"]
    closes = df.close.to_numpy(dtype=float)
    opens = df.open.to_numpy(dtype=float)
    n = len(df)
    beginning = pd.Timestamp(start) if start is not None else df.index[0]
    finish = pd.Timestamp(end) if end is not None else df.index[-1]
    # Il calcolo usa dati precedenti anche a start (warmup); le esecuzioni no.
    equity = 1.0
    top = 1.0
    worst_dd = 0.0
    position = False
    entry_price = np.nan
    entry_idx = -1
    high_close_since_entry = np.nan
    trades = []
    curve = []
    for i in range(201,n):
        if df.index[i] < beginning or df.index[i] > finish:
            continue
        previous = i - 1
        exited = False
        forces_exit = np.isfinite(exit_force[previous]) and exit_force[previous] <= 0
        supertrend_exit = np.isfinite(st_bull[previous]) and st_bull[previous] == 0.0
        ha_confirmation = (np.isfinite(ha_force_exit[previous])
                           and ha_force_exit[previous] <= 0 and not ha[previous])
        # Trailing sul massimo CLOSE del trade, NON sugli high e NON stop intraday.
        trail5 = (np.isfinite(high_close_since_entry) and position
                  and high_close_since_entry > entry_price
                  and (high_close_since_entry - closes[previous]) / entry_price >= 0.05)
        if exit_method == "Forces 10/4":
            should_exit = forces_exit
        elif exit_method == "Supertrend 10x2":
            should_exit = supertrend_exit
        else:
            should_exit = ha_confirmation or trail5
        if position and should_exit:
            sell = opens[i] * (1 - 0.0015)
            ret = sell / entry_price - 1
            equity *= 1 + ret
            trades.append({
                "Ingresso": df.index[entry_idx],
                "Uscita": df.index[i],
                "Prezzo ingresso": entry_price,
                "Prezzo uscita": sell,
                "Rendimento netto %": ret*100,
                "Sedute": i - entry_idx,
            })
            position = False
            exited = True
        entry_signal = (ha[previous] and np.isfinite(entry_force[previous])
                        and np.isfinite(entry_force[previous-1])
                        and entry_force[previous] > 0 and entry_force[previous-1] <= 0
                        and closes[previous] > ema200[previous])
        if not position and not exited and entry_signal:
            entry_price = opens[i] * (1 + 0.0015)
            entry_idx = i
            position = True
            high_close_since_entry = closes[i]
        if position:
            high_close_since_entry = max(high_close_since_entry, closes[i])
        marked = equity * (closes[i] * (1-0.0015) / entry_price) if position else equity
        top = max(top, marked)
        worst_dd = min(worst_dd, marked/top-1)
        curve.append({"Data":df.index[i], "Equity":marked})
    result_equity = equity
    last_index = next((i for i in range(n-1,200,-1)
                       if beginning <= df.index[i] <= finish), None)
    if last_index is None:
        raise ValueError("Il periodo selezionato non ha sedute sufficienti.")
    marked_last = (result_equity * closes[last_index] * (1-0.0015) / entry_price
                   if position else result_equity)
    ret = [t["Rendimento netto %"] for t in trades]
    return {
        "Preset": code, "ID": preset_id(code, exit_method), "Descrizione": PRESET_DESCRIPTIONS[code]+"; uscita "+exit_method,
        "Uscita": exit_method,
        "Trade chiusi": len(trades),
        "Vincenti %": 100*sum(x>0 for x in ret)/len(ret) if ret else np.nan,
        "Durata media": float(np.mean([t["Sedute"] for t in trades])) if trades else np.nan,
        "Rendimento realizzato %": 100*(result_equity-1),
        "Rendimento con aperta %": 100*(marked_last-1),
        "Drawdown massimo %": 100*worst_dd,
        "Posizione aperta": position,
        "Operazioni": pd.DataFrame(trades),
        "Equity": pd.DataFrame(curve),
    }
