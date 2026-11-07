"""Audit OHLC riproducibile: legge le barre e non modifica MAI i prezzi."""
from hashlib import sha256
import numpy as np
import pandas as pd

COLUMNS = ["Ticker","Data","Open","High","Low","Close","Volume",
           "Problema","Scarto massimo %","Origine"]


def audit_ohlc_bars(frame, ticker, origin=""):
    """Restituisce solo anomalie con il valore originale di ogni colonna.

    Stessa tolleranza assoluta 1e-9 di engine.invalid_ohlc.
    Dettagli su tutti i motivi, anche simultanei, senza interventi sui dati.
    """
    records=[]
    for date, row in frame.iterrows():
        o,h,l,c=(float(row[x]) for x in ("open","high","low","close"))
        reason=[]
        values=np.asarray([o,h,l,c],dtype=float)
        if not np.isfinite(values).all():
            reason.append("OHLC non finiti")
        if np.isfinite(values).all() and np.any(values <= 0):
            reason.append("OHLC non positivi")
        if np.isfinite(values).all():
            if h < max(o,c,l)-1e-9:
                reason.append("High inferiore a Open/Close/Low")
            if l > min(o,c,h)+1e-9:
                reason.append("Low superiore a Open/Close/High")
        if "ohlc_valid" in frame and not bool(row["ohlc_valid"]):
            reason.append("Flag origine: OHLC non valido")
        if not reason:
            continue
        ref=max(abs(o),abs(c),1e-12)
        deviation=max(max(o,c,l)-h,l-min(o,c,h),0.)/ref*100 if np.isfinite(values).all() else np.nan
        records.append({
            "Ticker":ticker,"Data":str(pd.Timestamp(date).date()),
            "Open":o,"High":h,"Low":l,"Close":c,
            "Volume":float(row["volume"]) if "volume" in frame else np.nan,
            "Problema":" | ".join(reason),
            "Scarto massimo %":deviation,
            "Origine":origin,
        })
    return records


def quality_overview(data, origin="", minimum_warmup=220):
    """Riepilogo e dettaglio scaricabili, senza scartare o correggere barre."""
    overview=[]
    details=[]
    for ticker, df in data.items():
        anomalies=audit_ohlc_bars(df,ticker,origin)
        details.extend(anomalies)
        last_bad=pd.Timestamp(anomalies[-1]["Data"]) if anomalies else None
        after_last=int((df.index>last_bad).sum()) if last_bad is not None else len(df)
        if anomalies:
            status="ESCLUSO — OHLC da verificare"
        elif len(df)<minimum_warmup:
            status="ESCLUSO — storico insufficiente"
        else:
            status="IDONEO — OHLC"
        digest=sha256(pd.util.hash_pandas_object(
            df[["open","high","low","close"]],index=True).values.tobytes()).hexdigest()[:16]
        overview.append({
            "Ticker":ticker,"Stato":status,"Barre disponibili":len(df),
            "Anomalie":len(anomalies),
            "Prima anomalia":anomalies[0]["Data"] if anomalies else "",
            "Ultima anomalia":anomalies[-1]["Data"] if anomalies else "",
            "Barre dopo ultima anomalia":after_last,
            "Prima seduta":str(df.index[0].date()) if len(df) else "",
            "Ultima seduta":str(df.index[-1].date()) if len(df) else "",
            "Impronta OHLC":digest,
            "Origine":origin,
        })
    return pd.DataFrame(overview),pd.DataFrame(details,columns=COLUMNS)
