import numpy as np
import pandas as pd
from validation_benchmarks import strategy_metrics, passive_metrics, matched_benchmark

def synthetic():
    dates = pd.bdate_range("2024-01-02", periods=260)
    p = pd.DataFrame({"open": np.linspace(100, 120, len(dates)),
                      "close": np.linspace(100, 121, len(dates))}, index=dates)
    return p

def test_passive_does_not_change_ohlc():
    p = synthetic()
    before = p.copy(deep=True)
    m = passive_metrics(p, p.index)
    pd.testing.assert_frame_equal(p, before)
    assert m["Rendimento %"] > 0
    assert 0 <= m["Esposizione media %"] <= 100
    assert m["Prima barra effettiva"] == "2024-01-02"

def test_strategy_exposure_and_cagr():
    p = synthetic()
    curve = pd.DataFrame({"Data": p.index,
                          "Equity": np.linspace(1, 1.1, len(p)),
                          "Exposure": [1.0] * 130 + [0.0] * 130})
    result = strategy_metrics(curve)
    assert abs(result["Rendimento %"] - 10) < 1e-10
    assert abs(result["Esposizione media %"] - 50) < 1e-10
    assert result["CAGR %"] > 0

def test_spy_different_trading_holidays_no_interpolation():
    p = synthetic()
    dates = p.index.delete([5, 20])
    m = matched_benchmark(p, dates)
    assert m is not None
    assert m["Sedute"] == len(p)
    assert m["Prima barra effettiva"] == str(dates[0].date())
    assert matched_benchmark(None, dates) is None
