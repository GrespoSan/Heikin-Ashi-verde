import numpy as np
import pandas as pd
from portfolio_validation import portfolio_lump_sum
from research_presets import prepare_preset_features

def bars(n=410):
    d=pd.bdate_range("2021-01-04",periods=n)
    z=np.arange(n)
    c=60+z*.03+4*np.sin(z/11)
    o=c+.1*np.sin(z/7)
    return pd.DataFrame({"open":o,"high":np.maximum(o,c)+.4,"low":np.minimum(o,c)-.4,"close":c,"volume":1e6},index=d)

def test_zero_signals_conserves_capital_and_cash():
    d=pd.bdate_range("2021-01-04",periods=300)
    f=pd.DataFrame({"open":100.,"high":101.,"low":99.,"close":100.,"volume":1000.},index=d)
    r=portfolio_lump_sum({"X":f},d[220],d[-1],100000)
    assert r["metrics"]["Titoli ammessi"]==1
    assert r["fills"].empty
    assert np.allclose(r["curve"]["Patrimonio"],100000)
    assert np.allclose(r["curve"]["Esposizione %"],0)

def test_daily_accounting_and_no_margin():
    f=bars()
    r=portfolio_lump_sum({"X":f,"Y":f.copy()},f.index[220],f.index[-1],100000)
    curve=r["curve"]
    assert np.allclose(curve["Patrimonio"],curve["Liquidita"]+curve["Investito"])
    assert (curve["Liquidita"]>=-1e-7).all()
    assert (curve["Investito"]>=0).all()
    assert (curve["Esposizione %"].between(0,100.0000001)).all()
    assert np.isclose(r["holdings"]["Valore"].sum(),curve["Patrimonio"].iloc[-1])

def test_spy_and_holidays():
    f=bars()
    spy=f.drop(f.index[[230,250]])
    r=portfolio_lump_sum({"X":f},f.index[220],f.index[-1],100000,spy)
    assert r["spy_metrics"] is not None
    assert r["spy_curve"].shape[0]==r["curve"].shape[0]
    assert np.isfinite(r["spy_metrics"]["CAGR %"])

def test_no_changing_historical_prices():
    f=bars()
    before=f.copy(deep=True)
    portfolio_lump_sum({"X":f},f.index[220],f.index[-1],100000)
    pd.testing.assert_frame_equal(f,before)
