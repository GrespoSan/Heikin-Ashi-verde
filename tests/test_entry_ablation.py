import numpy as np
import pandas as pd
from entry_ablation import (
    VARIANTS, ABLATION_VERSION, simulate_entry_ablation,
    audit_reference_match, evaluate_ablation_universe
)
from research_presets import prepare_preset_features

def sample(n=500):
    dates = pd.bdate_range('2022-01-03',periods=n)
    x = np.arange(n)
    close = 100 + x*.06 + 12*np.sin(x/15) + 3*np.sin(x/4)
    op = close + .4*np.sin(x/5)
    return pd.DataFrame({
        'open':op, 'close':close,
        'high':np.maximum(op,close)+1,
        'low':np.minimum(op,close)-1,
        'volume':100000 + x*10
    },index=dates)

def test_reference_b_equals_frozen_engine():
    bars=sample()
    feat=prepare_preset_features(bars)
    assert audit_reference_match(bars,feat,bars.index[220],bars.index[-1])
    assert audit_reference_match(bars,feat,bars.index[240],bars.index[370])

def test_all_ablation_rules_without_tuning():
    bars=sample()
    feat=prepare_preset_features(bars)
    for variant in VARIANTS:
        stats, curve=simulate_entry_ablation(bars,feat,variant,bars.index[220],bars.index[-1])
        assert len(curve)>0
        assert (curve.Exposure.isin([0.,1.])).all()
        assert stats['Trade chiusi']<=stats['Ingressi']
        assert stats['Ingressi']-stats['Trade chiusi'] in (0,1)
        assert np.isfinite(stats['CAGR %'])
        assert np.isfinite(stats['Drawdown %'])

def test_reconciliation_is_mandatory():
    bars=sample()
    results,excluded=evaluate_ablation_universe({'TEST':bars},bars.index[220],bars.index[-1],bars)
    assert excluded.empty
    assert set(results['Variante'])==set(VARIANTS)
    assert len(results)==5
