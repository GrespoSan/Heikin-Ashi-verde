import numpy as np
import pandas as pd
from research_presets import prepare_preset_features, simulate_preset
from rotation_reserved import rotate_reserved, compare_capacities, RANKING_METHODS

def synthetic(n=520, shift=0):
    dates=pd.bdate_range("2021-01-04",periods=n)
    x=np.arange(n)
    close=100 + .1*x + 9*np.sin((x+shift)/12) + 2*np.sin(x/4)
    op=close + .3*np.sin(x/6)
    return pd.DataFrame({
        "open":op,"close":close,
        "high":np.maximum(op,close)+.8,
        "low":np.minimum(op,close)-.8,
        "volume":1_000_000
    },index=dates)

def test_one_slot_matches_frozen_b_equity_each_day():
    df=synthetic()
    start,end=df.index[225],df.index[-1]
    features=prepare_preset_features(df)
    reference=simulate_preset(df,features,"B",start,end,exit_method="Supertrend 10x2")
    result=rotate_reserved({"ONLY":df},start,end,10000,1,RANKING_METHODS[0])
    actual=result["curve"]["Patrimonio"].to_numpy()/10000
    expected=reference["Equity"]["Equity"].to_numpy()
    np.testing.assert_allclose(actual,expected,atol=1e-9,rtol=1e-9)
    assert result["metrics"]["Acquisti"] in (
        reference["Trade chiusi"],reference["Trade chiusi"]+1)

def test_reserved_slots_capital_ownership_and_max_positions():
    data={"AAA":synthetic(shift=3),"BBB":synthetic(shift=8),
          "CCC":synthetic(shift=18),"DDD":synthetic(shift=29)}
    start,end=list(data.values())[0].index[[230,-1]]
    for capacity in (1,2,3):
        r=rotate_reserved(data,start,end,10000.,capacity,RANKING_METHODS[0])
        c=r["curve"]
        assert c["Posizioni aperte"].max()<=capacity
        assert c["Liquidita"].min()>-1e-8
        np.testing.assert_allclose(c["Patrimonio"],c["Liquidita"]+c["Investito"],atol=1e-7)
        assert r["holdings"]["Slot"].nunique()==capacity
        assert np.isclose(r["holdings"]["Valore"].sum(),c["Patrimonio"].iloc[-1])
        assert r["metrics"]["Capitale iniziale"]==10000

def test_ranking_uses_only_previous_bars():
    df=synthetic()
    a=rotate_reserved({"AAA":df,"BBB":df.copy()},
        df.index[230],df.index[390],10000,1,RANKING_METHODS[1])
    changed=df.copy()
    changed.loc[changed.index[410]:,"close"] *= 3
    changed["high"]=np.maximum(changed.open,changed.close)+.8
    changed["low"]=np.minimum(changed.open,changed.close)-.8
    b=rotate_reserved({"AAA":df,"BBB":changed},
        df.index[230],df.index[390],10000,1,RANKING_METHODS[1])
    pd.testing.assert_frame_equal(a["curve"],b["curve"])
    pd.testing.assert_frame_equal(a["fills"],b["fills"])

def test_six_runs_and_no_extra_capital():
    df=synthetic()
    summary,results=compare_capacities({"A":df,"B":synthetic(shift=10)},
        df.index[220],df.index[-1],10000.,spy=df)
    assert len(summary)==6
    assert len(results)==6
    for m in RANKING_METHODS:
        for cap in (1,2,3):
            r=results[(cap,m)]
            assert r["metrics"]["Capacita"]==cap
            assert r["spy_metrics"] is not None
