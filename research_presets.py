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

PRESET_VERSION = "AB-FIVE-EXITS-2026-11-07-v4"
EXIT_METHODS = ("Forces 10/4", "Supertrend 10x2", "Forces HA + HA rossa + trailing 5%", "Forces ↓2 o zero (E2)", "50% ↓2 + 50% zero (E5)")
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
        # TradingView: confronta il close con la banda FINALE CORRENTE,
        # non con quella precedente. Il ramo dipende dal precedente Supertrend.
        if bullish[i-1]==1.0:
            bullish[i]=0.0 if close[i]<lower[i] else 1.0
        else:
            bullish[i]=1.0 if close[i]>upper[i] else 0.0
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
    """Simulazione long full-allocation su una singola azione con costi 0,15% per lato.

    E2: due diminuzioni consecutive del Forces Standard 10/4, ancora positivo,
        oppure Forces <= 0 come uscita di sicurezza.
    E5: vende metà dopo lo stesso segnale di attenuazione, il resto quando
        Forces Standard 10/4 <=0; se Forces arriva a zero prima, chiude tutto.
    Decisioni al close confermato, fill next open. Le parziali sono contabilizzate
    nello stesso trade, senza capitalizzare separatamente il capitale già incassato.
    """
    if code not in PRESETS:
        raise ValueError("Preset sconosciuto")
    if exit_method not in EXIT_METHODS:
        raise ValueError("Uscita sconosciuta")
    in_source, _ = PRESETS[code]
    entry_force = features[(in_source,7,7)]
    std_force_exit = features[("Standard",10,4)]
    st_bull = features["supertrend_10x2"]
    ha_force_exit = features[("Heikin Ashi",10,4)]
    ha = features["ha_green"]
    ema200 = features["ema200"]
    closes = df.close.to_numpy(dtype=float)
    opens = df.open.to_numpy(dtype=float)
    n = len(df)
    beginning = pd.Timestamp(start) if start is not None else df.index[0]
    finish = pd.Timestamp(end) if end is not None else df.index[-1]
    if beginning > finish:
        raise ValueError("Periodo inverso")
    equity = 1.0
    peak = 1.0
    worst_dd = 0.0
    position = False
    entry_price = np.nan
    entry_idx = -1
    trade_capital = 0.0
    remaining = 0.0
    sold_value = 0.0
    partial_done = False
    high_close_since_entry = np.nan
    trades = []
    executions = []
    curve = []
    last_i = None
    exit_method_ha = "Forces HA + HA rossa + trailing 5%"
    exit_method_e2 = "Forces ↓2 o zero (E2)"
    exit_method_e5 = "50% ↓2 + 50% zero (E5)"
    for i in range(201,n):
        if df.index[i] < beginning or df.index[i] > finish:
            continue
        last_i = i
        prev = i-1
        exited = False
        forces_zero = (np.isfinite(std_force_exit[prev]) and
                       std_force_exit[prev] <= 0)
        fade_two = (prev>=2 and np.isfinite(std_force_exit[prev-2:prev+1]).all()
                    and std_force_exit[prev] > 0
                    and std_force_exit[prev-2] > std_force_exit[prev-1] >
                        std_force_exit[prev])
        if position:
            do_full = False
            do_half = False
            if exit_method == "Forces 10/4":
                do_full = forces_zero
            elif exit_method == "Supertrend 10x2":
                do_full = np.isfinite(st_bull[prev]) and st_bull[prev] == 0.0
            elif exit_method == exit_method_ha:
                ha_confirmation = (np.isfinite(ha_force_exit[prev])
                                   and ha_force_exit[prev] <= 0
                                   and not bool(ha[prev]))
                trail5 = (np.isfinite(high_close_since_entry)
                          and high_close_since_entry > entry_price
                          and (high_close_since_entry-closes[prev])/entry_price >= .05)
                do_full = ha_confirmation or trail5
            elif exit_method == exit_method_e2:
                do_full = forces_zero or fade_two
            else:
                do_full = forces_zero
                do_half = fade_two and not partial_done and not do_full

            if do_half:
                sell = opens[i]*(1-.0015)
                # Metà della QUANTITÀ iniziale e commissione proporzionale;
                # metà del capitale resta liquida e non viene reinvestita.
                sold_value += .5*sell/entry_price
                remaining = .5
                partial_done = True
                executions.append({"Ingresso":df.index[entry_idx],
                                   "Data":df.index[i], "Preset":code,
                                   "Uscita":exit_method, "Frazione venduta":.5,
                                   "Prezzo":sell, "Motivo":"Forces in calo 2 barre"})
            if do_full:
                sell = opens[i]*(1-.0015)
                fraction = remaining
                sold_value += fraction*sell/entry_price
                remaining = 0.0
                new_equity = trade_capital*sold_value
                trades.append({
                    "Ingresso": df.index[entry_idx], "Uscita":df.index[i],
                    "Prezzo ingresso":entry_price, "Prezzo uscita":sell,
                    "Rendimento netto %":(sold_value-1)*100,
                    "Sedute":i-entry_idx,
                    "Prelievo parziale":partial_done,
                })
                executions.append({"Ingresso":df.index[entry_idx],
                                   "Data":df.index[i], "Preset":code,
                                   "Uscita":exit_method, "Frazione venduta":fraction,
                                   "Prezzo":sell, "Motivo":"Chiusura finale"})
                equity = new_equity
                position = False
                exited = True

        entry_signal = (bool(ha[prev]) and np.isfinite(entry_force[prev])
                        and np.isfinite(entry_force[prev-1])
                        and entry_force[prev] > 0 and entry_force[prev-1] <= 0
                        and closes[prev] > ema200[prev])
        if not position and not exited and entry_signal:
            entry_price = opens[i]*(1+.0015)
            entry_idx = i
            trade_capital = equity
            sold_value = 0.0
            remaining = 1.0
            partial_done = False
            position = True
            high_close_since_entry = closes[i]
        if position:
            high_close_since_entry = max(high_close_since_entry,closes[i])
            marked = trade_capital*(sold_value+remaining*closes[i]*(1-.0015)/entry_price)
        else:
            marked = equity
        peak = max(peak,marked)
        worst_dd = min(worst_dd,marked/peak-1)
        curve.append({"Data":df.index[i],"Equity":marked})
    if last_i is None:
        raise ValueError("Nessuna barra utile nel periodo selezionato.")
    marked_last = (trade_capital*(sold_value+remaining*closes[last_i]*(1-.0015)/entry_price)
                   if position else equity)
    returns = [t["Rendimento netto %"] for t in trades]
    return {
        "Preset":code, "ID":preset_id(code,exit_method),
        "Descrizione":PRESET_DESCRIPTIONS[code]+"; uscita "+exit_method,
        "Uscita":exit_method,
        "Trade chiusi":len(trades),
        "Vincenti %":100*sum(v>0 for v in returns)/len(returns) if returns else np.nan,
        "Durata media":float(np.mean([t["Sedute"] for t in trades])) if trades else np.nan,
        "Rendimento realizzato %":100*(equity-1),
        "Rendimento con aperta %":100*(marked_last-1),
        "Drawdown massimo %":100*worst_dd,
        "Posizione aperta":position,
        "Posizione residua %":100*remaining if position else 0.0,
        "Operazioni":pd.DataFrame(trades),
        "Esecuzioni":pd.DataFrame(executions),
        "Equity":pd.DataFrame(curve),
    }
