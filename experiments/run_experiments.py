#!/usr/bin/env python3
"""Run every experiment reported in the paper.

Usage
-----
    python experiments/run_experiments.py                 # all, 30 seeds
    python experiments/run_experiments.py --exp baseline load
    python experiments/run_experiments.py --quick         # smoke test (3 seeds, 5 s)
    python experiments/run_experiments.py --workers 8     # parallel

Raw per-run results are written to results/raw/<experiment>.csv
(one row per scheme x configuration x seed). Existing files are skipped
unless --force is given.

Seeds 0..29 are the evaluation seeds. Seeds 100..109 were used only while
choosing design constants (risk threshold, partner score) and are never
reported.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fogzero import SimConfig, simulate  # noqa: E402

TRACE = os.path.join(ROOT, "data", "azure2021", "azure2021_short.csv.gz")
ALL4 = ("CZO", "HORC", "AFS", "HZS")
SWARM = ("AFS", "HZS")

FAILURES = {
    "F0 none": dict(),
    "F1 outage 2s": dict(outages=((4.0, 6.0),)),
    "F2 outage 5s": dict(outages=((2.5, 7.5),)),
    "F3 intermittent 4x0.5s": dict(outages=((2.0, 2.5), (4.0, 4.5), (6.0, 6.5), (8.0, 8.5))),
    "F4 delayed recovery (cold)": dict(outages=((4.0, 7.0),), cold_restart=True),
    "F5 node crash 10%": dict(node_crash_frac=0.10, node_crash_window=(4.0, 7.0)),
    "F6 msg loss 5%": dict(msg_loss=0.05),
}

HZS_VARIANTS = {
    "HZS (full)": dict(),
    "no capacity lease": dict(lease=False),
    "load-averse score": dict(psi_rule="load_averse"),
    "eager partners": dict(lazy_partner=False),
    "no partners (p=0)": dict(p=0),
    "T_p = 0.25 s": dict(T_p=0.25),
    "T_p = 0.5 s": dict(T_p=0.5),
    "T_p = 2 s": dict(T_p=2.0),
    "T_p = 5 s": dict(T_p=5.0),
}


def experiments():
    """Yield (experiment, label_dict, scheme, overrides)."""
    E = {}
    E["baseline"] = [({}, s, {}) for s in ALL4]
    E["load"] = [({"rho": r}, s, {"rho": r})
                 for r in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9) for s in ALL4]
    E["scale"] = [({"N": n}, s, {"N": n}) for n in (10, 25, 50, 100, 200) for s in ALL4]
    E["delay"] = [({"d_c_ms": d}, "CZO", {"d_c": d / 1e3})
                  for d in (1, 2, 3, 4, 5, 7.5, 10, 15, 20, 30, 40)]
    E["fanout"] = [({"k": k}, s, {"k": k}) for k in (1, 2, 3, 4, 6, 8) for s in SWARM]
    E["failures"] = [({"scenario": f}, s, kw) for f, kw in FAILURES.items() for s in ALL4]
    E["escalation"] = [({"E_max": e, "rho": r}, s, {"esc_max": e, "rho": r})
                       for r in (0.7, 0.9) for e in (0, 1, 2) for s in SWARM]
    E["selection"] = [({"selection": m, "rho": r}, s, {"selection": m, "rho": r})
                      for r in (0.7, 0.9) for m in ("random", "fixed_id") for s in SWARM]
    E["stigmergy"] = ([({"beta": b, "setting": "default"}, "AFS", {"beta": b}) for b in (0.0, 0.1, 0.5, 1.0)]
                      + [({"beta": 1.0, "setting": "aggressive"}, "AFS",
                          {"beta": 1.0, "eta": 0.5, "theta_min": 0.1})])
    tr = {"workload": "azure2021", "trace_path": TRACE}
    E["hzs_ablation"] = [({"variant": v}, "HZS", {**tr, "rho": 0.7, **kw})
                         for v, kw in HZS_VARIANTS.items()]
    E["trace"] = [({"rho": r}, s, {**tr, "rho": r}) for r in (0.3, 0.5, 0.7, 0.9) for s in ALL4]
    E["trace_delay"] = [({"d_c_ms": d}, "CZO", {**tr, "d_c": d / 1e3})
                        for d in (1, 2, 5, 10, 20)]
    return E


def _one(args):
    exp, label, scheme, kw, seed, quick = args
    cfg = SimConfig(seed=seed, **kw)
    if quick:
        cfg = cfg.with_(horizon=5.0)
    r = simulate(scheme, cfg)
    r.update(label)
    r["experiment"] = exp
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", nargs="*", default=None)
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "raw"))
    ap.add_argument("--budget", type=float, default=0,
                    help="stop after this many seconds (resumable; 0 = no limit)")
    a = ap.parse_args()
    if a.quick:
        a.seeds = min(a.seeds, 3)
        a.out = os.path.join(ROOT, "results", "quick")
    os.makedirs(a.out, exist_ok=True)
    E = experiments()
    names = a.exp or list(E)
    for name in names:
        path = os.path.join(a.out, f"{name}.csv")
        if os.path.exists(path) and not a.force:
            print(f"[skip] {name} (exists)")
            continue
        jobs = [(name, lab, sc, kw, seed, a.quick)
                for (lab, sc, kw) in E[name] for seed in range(a.seeds)]
        part = path + ".partial"
        done = 0
        if os.path.exists(part):
            done = sum(1 for _ in open(part)) - 1
        t0 = time.time()
        todo = jobs[max(done, 0):]
        if a.workers > 1:
            with ProcessPoolExecutor(a.workers) as ex:
                it = ex.map(_one, todo, chunksize=4)
                _drain(it, part, t0, a.budget)
        else:
            _drain(map(_one, todo), part, t0, a.budget)
        n_now = sum(1 for _ in open(part)) - 1 if os.path.exists(part) else 0
        if n_now >= len(jobs):
            os.replace(part, path)
            print(f"[done] {name}: {len(jobs)} runs", flush=True)
        else:
            print(f"[partial] {name}: {n_now}/{len(jobs)}", flush=True)
            return


def _drain(it, part, t0, budget):
    import csv
    new = not os.path.exists(part)
    with open(part, "a", newline="") as f:
        w = None
        for r in it:
            if w is None:
                w = csv.DictWriter(f, fieldnames=list(r.keys()))
                if new:
                    w.writeheader()
            w.writerow(r)
            f.flush()
            if budget and time.time() - t0 > budget:
                break


if __name__ == "__main__":
    main()
