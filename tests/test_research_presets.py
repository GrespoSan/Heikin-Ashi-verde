"""Regressioni per i preset congelati A/B/C. Eseguire: python -m unittest tests.test_research_presets"""
import unittest
import numpy as np
import pandas as pd
from research_presets import PRESETS, prepare_preset_features, simulate_preset, preset_id


def candles(n=320):
    date = pd.bdate_range("2024-01-01", periods=n)
    z = np.arange(n)
    base = 25 + z*0.025 + 0.55*np.sin(z/4)
    op = base - 0.22*np.cos(z/3)
    cl = base + 0.22*np.cos(z/3)
    return pd.DataFrame({
        "open": op, "high": np.maximum(op,cl)+0.2,
        "low": np.minimum(op,cl)-0.2, "close": cl,
        "volume": 1000,
    },index=date)


class ResearchPresetsTest(unittest.TestCase):
    def test_three_stable_distinct_ids(self):
        self.assertEqual(set(PRESETS), {"A","B","C"})
        self.assertEqual(len({preset_id(c) for c in PRESETS}), 3)

    def test_all_presets_return_valid_results(self):
        x = candles()
        features = prepare_preset_features(x)
        for c in PRESETS:
            with self.subTest(preset=c):
                r = simulate_preset(x,features,c)
                self.assertEqual(r["Preset"],c)
                self.assertTrue(np.isfinite(r["Rendimento realizzato %"]))
                self.assertLessEqual(r["Drawdown massimo %"],0)
                self.assertTrue((r["Operazioni"]["Uscita"]>r["Operazioni"]["Ingresso"]).all()
                                if not r["Operazioni"].empty else True)

    def test_forces_sources_not_identical(self):
        f = prepare_preset_features(candles())
        standard = f[("Standard",7,7)]
        ha = f[("Heikin Ashi",7,7)]
        self.assertFalse(np.allclose(standard[10:],ha[10:],equal_nan=True))

    def test_invalid_ohlc_rejected(self):
        df=candles()
        df.iloc[2,df.columns.get_loc("high")]=0.1
        with self.assertRaises(ValueError):
            prepare_preset_features(df)


if __name__=="__main__":
    unittest.main()
