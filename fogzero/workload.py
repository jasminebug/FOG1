"""Workload generators.

synthetic : homogeneous Poisson arrivals, exponential work, uniform ingress.
azure2021 : arrival instants, relative durations and function identity taken
            from the Azure Functions Invocation Trace 2021 (CC-BY 4.0);
            see DATASET.md for provenance and preprocessing.
"""
from __future__ import annotations
import zlib
import numpy as np
import pandas as pd

_TRACE_CACHE = {}


def synthetic(cfg, rng):
    lam = cfg.arrival_rate
    n = rng.poisson(lam * cfg.horizon)
    arr = np.sort(rng.uniform(0.0, cfg.horizon, n))
    work = rng.exponential(cfg.mean_work, n)
    src = rng.integers(0, cfg.N, n)
    dl = np.full(n, cfg.deadline)
    return arr, work, src, dl


def _load_trace(path):
    if path not in _TRACE_CACHE:
        df = pd.read_csv(path)
        df = df.sort_values("arrival_s", kind="stable").reset_index(drop=True)
        _TRACE_CACHE[path] = (df["arrival_s"].to_numpy(),
                              df["duration_s"].to_numpy(),
                              df["func_key"].to_numpy(dtype=np.int64))
    return _TRACE_CACHE[path]


def azure2021(cfg, rng, tenants: int = 16, footprint: float = 0.2):
    """Trace-driven workload (multi-tenant superposition replay).

    1. n = Lambda*H invocations are split evenly over S = `tenants` streams.
    2. Each stream is a contiguous segment of the preprocessed trace cut at a
       seed-dependent offset; its inter-arrival pattern (burstiness) is kept
       and linearly time-scaled onto [0, H). The S streams are superposed,
       which models a fog domain that serves several independent tenants.
    3. Durations are rescaled so that their overall mean equals E[w]; the
       shape and heavy tail (CV ~ 1.7) of the production trace are kept.
    4. Spatial locality: every (tenant, app, func) triple is assigned a home
       arc of ceil(footprint*N) consecutive ring nodes via a stable hash, and
       each invocation enters at a node drawn uniformly from that arc.
    5. The per-task relative deadline is max(D, 3 w).
    """
    if not cfg.trace_path:
        raise ValueError("azure2021 workload needs cfg.trace_path")
    a, d, key = _load_trace(cfg.trace_path)
    n_tot = int(round(cfg.arrival_rate * cfg.horizon))
    per = max(2, n_tot // tenants)
    arrs, durs, srcs = [], [], []
    arc = max(1, int(np.ceil(footprint * cfg.N)))
    for s_ in range(tenants):
        off = int(rng.integers(0, len(a) - per))
        seg_a = a[off:off + per].astype(float)
        seg_d = d[off:off + per].astype(float)
        seg_k = key[off:off + per]
        span = seg_a[-1] - seg_a[0]
        t = (seg_a - seg_a[0]) / max(span, 1e-9) * cfg.horizon * (per - 1) / per
        t = t + rng.uniform(0, cfg.horizon / per)          # de-align streams
        salt = int(rng.integers(0, 2**31 - 1))
        home = np.array([((int(x) ^ salt) * 2654435761) % cfg.N for x in seg_k])
        src = (home + rng.integers(0, arc, per)) % cfg.N
        arrs.append(t); durs.append(seg_d); srcs.append(src)
    arr = np.concatenate(arrs)
    dur = np.maximum(np.concatenate(durs), 1e-3)
    src = np.concatenate(srcs).astype(np.int64)
    order = np.argsort(arr, kind="stable")
    arr, dur, src = arr[order], dur[order], src[order]
    work = dur / dur.mean() * cfg.mean_work
    dl = np.maximum(cfg.deadline, 3.0 * work)
    return arr, work, src, dl


def stable_key(app: str, func: str) -> int:
    return zlib.crc32(f"{app}:{func}".encode()) & 0x7FFFFFFF


GENERATORS = {"synthetic": synthetic, "azure2021": azure2021}
