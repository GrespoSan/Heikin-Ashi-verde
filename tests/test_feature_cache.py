from collections import OrderedDict
from dataclasses import replace
from unittest.mock import patch
import pandas as pd
from engine import Indicators,prepare_features
from feature_cache import cached_features

def fixture():
    return pd.DataFrame({'open':10.,'high':11.,'low':9.,'close':10.5,'volume':1.},index=pd.bdate_range('2024-01-01',periods=300))

def test_feature_cache_reuse_and_invalidation():
    cache=OrderedDict();df=fixture();cfg=Indicators()
    with patch('feature_cache.prepare_features',wraps=prepare_features) as calc:
        a=cached_features(cache,'data1','A2A',cfg,df)
        b=cached_features(cache,'data1','A2A',cfg,df)
        assert a is b and calc.call_count==1
        cached_features(cache,'data1','A2A',replace(cfg,trend_ema=55),df)
        cached_features(cache,'data2','A2A',cfg,df)
        cached_features(cache,'data2','AMP',cfg,df)
        assert calc.call_count==4
        cached_features(cache,'data2','AMP',cfg,df,start='2024-07-01')
        assert calc.call_count==5

def test_feature_cache_lru_is_bounded():
    cache=OrderedDict();df=fixture();cfg=Indicators()
    for symbol in ('A','B','C'):cached_features(cache,'r',symbol,cfg,df,max_entries=2)
    assert len(cache)==2 and all(key[1]!='A' for key in cache)
