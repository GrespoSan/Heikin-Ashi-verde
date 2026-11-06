"""Cache per sessione: nessun ricalcolo degli indicatori per modifiche a costi o uscite."""
from dataclasses import asdict
import json
from engine import prepare_features

def cached_features(cache,revision,symbol,cfg,df,start=None,end=None,max_entries=96):
    key=(revision,symbol,json.dumps(asdict(cfg),sort_keys=True),str(start),str(end))
    if key in cache:
        value=cache.pop(key);cache[key]=value
        return value
    value=prepare_features(df,cfg,start,end)
    cache[key]=value
    while len(cache)>max_entries:cache.popitem(last=False)
    return value
