#!/usr/bin/env python3
"""Descriptive statistics of the preprocessed Azure trace (Table in DATASET.md)."""
import os
import sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fogzero import SimConfig  # noqa: E402
from fogzero.workload import azure2021  # noqa: E402

p = os.path.join(ROOT, "data", "azure2021", "azure2021_short.csv.gz")
df = pd.read_csv(p)
d = df.duration_s.clip(lower=1e-3)
span = df.arrival_s.max() - df.arrival_s.min()
print(f"invocations           : {len(df)}")
print(f"distinct functions    : {df.func_key.nunique()}")
print(f"time span             : {span/86400:.2f} days")
print(f"mean rate             : {len(df)/span:.3f} inv/s")
print(f"duration mean / median: {d.mean()*1e3:.1f} ms / {d.median()*1e3:.1f} ms")
print(f"duration CV           : {d.std()/d.mean():.3f}")
print(f"duration p90 / p99    : {d.quantile(.9)*1e3:.0f} ms / {d.quantile(.99)*1e3:.0f} ms")
share = df.func_key.value_counts(normalize=True)
print(f"top-1 / top-10 share  : {share.iloc[0]*100:.1f} % / {share.iloc[:10].sum()*100:.1f} %")
cfg = SimConfig(workload="azure2021", trace_path=p)
pm, idc, sk = [], [], []
for s in range(30):
    a, w, src, dl = azure2021(cfg, np.random.default_rng(s))
    c = np.bincount((a / 0.1).astype(int))
    pm.append(c.max() / c.mean()); idc.append(c.var() / c.mean())
    sk.append(np.bincount(src, minlength=cfg.N).max() / len(src) * cfg.N)
print(f"replay peak/mean (100 ms bins): {np.mean(pm):.2f}")
print(f"replay index of dispersion    : {np.mean(idc):.2f}  (Poisson = 1)")
print(f"replay hottest-node load ratio: {np.mean(sk):.2f}  (uniform = 1)")
