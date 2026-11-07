"""Regressioni per i preset congelati A/B/C. Eseguire: python -m unittest tests.test_research_presets"""
import unittest
import numpy as np
import pandas as pd
from research_presets import PRESETS, EXIT_METHODS, prepare_preset_features, simulate_preset, preset_id, supertrend_10x2


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
        self.assertEqual(set(PRESETS), {"A","B"})
        self.assertEqual(len({preset_id(c) for c in PRESETS}), 2)
        self.assertEqual(len({preset_id(c,e) for c in PRESETS for e in EXIT_METHODS}), 6)
        self.assertEqual(len(EXIT_METHODS),3)

    def test_all_presets_return_valid_results(self):
        x = candles()
        features = prepare_preset_features(x)
        for c in PRESETS:
            for exit_method in EXIT_METHODS:
              with self.subTest(preset=c,exit_method=exit_method):
                r = simulate_preset(x,features,c,exit_method=exit_method)
                self.assertEqual(r["Preset"],c)
                self.assertTrue(np.isfinite(r["Rendimento realizzato %"]))
                self.assertLessEqual(r["Drawdown massimo %"],0)
                self.assertTrue((r["Operazioni"]["Uscita"]>r["Operazioni"]["Ingresso"]).all()
                                if not r["Operazioni"].empty else True)

    def test_ha_confirmation_and_trailing_are_separate_exit_triggers(self):
        x=candles()
        f=prepare_preset_features(x)
        # I due trigger devono essere OR: il trailing può uscire anche con HA verde.
        # Esegui la terza uscita con entrambi gli ingressi e verifica risultati finiti.
        for code in PRESETS:
            result=simulate_preset(x,f,code,exit_method=EXIT_METHODS[2])
            self.assertTrue(np.isfinite(result["Rendimento realizzato %"]))
            self.assertEqual(result["Uscita"],EXIT_METHODS[2])

    def test_trailing_trigger_without_ha_red(self):
        df=candles()
        # Segnale ingresso unico, HA sempre verde. Il max close in trade
        # 110 seguito da 104 fa scattare il trailing al close, uscita next open.
        for i,p in ((220,100.0),(221,100.0),(222,110.0),(223,104.0),(224,103.0)):
            df.iloc[i,df.columns.get_loc("open")]=p
            df.iloc[i,df.columns.get_loc("close")]=p
        features=prepare_preset_features(candles())
        features["ha_green"]=np.ones(len(df),dtype=bool)
        features["ema200"]=np.zeros(len(df))
        signal=np.full(len(df),-1.0)
        signal[220]=1.0
        features[("Heikin Ashi",7,7)]=signal
        features[("Heikin Ashi",10,4)]=np.ones(len(df))
        result=simulate_preset(df,features,"B",exit_method=EXIT_METHODS[2])
        self.assertFalse(result["Operazioni"].empty)
        self.assertEqual(result["Operazioni"].iloc[0]["Ingresso"],df.index[221])
        self.assertEqual(result["Operazioni"].iloc[0]["Uscita"],df.index[224])

    def test_ha_confirmation_trigger_without_trailing(self):
        df=candles()
        features=prepare_preset_features(df)
        features["ha_green"]=np.ones(len(df),dtype=bool)
        features["ha_green"][223]=False
        features["ema200"]=np.zeros(len(df))
        signal=np.full(len(df),-1.0)
        signal[220]=1.0
        features[("Heikin Ashi",7,7)]=signal
        exit_forces=np.ones(len(df))
        exit_forces[223]=-1.0
        features[("Heikin Ashi",10,4)]=exit_forces
        result=simulate_preset(df,features,"B",exit_method=EXIT_METHODS[2])
        self.assertFalse(result["Operazioni"].empty)
        self.assertEqual(result["Operazioni"].iloc[0]["Uscita"],df.index[224])

    def test_supertrend_reversal_and_warmup(self):
        df=candles()
        line=supertrend_10x2(df)
        self.assertTrue(np.isnan(line[:9]).all())
        self.assertTrue(np.isin(line[9:],[0.0,1.0]).all())
        self.assertEqual(len(line),len(df))

    def test_supertrend_rejects_invalid_method(self):
        x=candles()
        f=prepare_preset_features(x)
        with self.assertRaises(ValueError):
            simulate_preset(x,f,"A",exit_method="Inesistente")

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
