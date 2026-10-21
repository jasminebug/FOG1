#!/usr/bin/env python3
"""Check that the numbers quoted in the paper are reproduced by results/.

Run after `python analysis/make_report.py`. Every assertion below is a number that
appears in the paper text or tables, together with the place where it appears.
Exit code 0 means every quoted number is reproduced (to the printed precision).

    python analysis/check_paper_numbers.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
K = json.load(open(os.path.join(ROOT, "results", "summary", "key_numbers.json")))
RAW = os.path.join(ROOT, "results", "raw")
TAB = os.path.join(ROOT, "results", "tables")

ok = fail = 0


def check(where, got, expected, tol):
    global ok, fail
    # tolerance = half a unit of the printed precision; +1e-6 accepts exact half-way values
    # (e.g. 1.325 printed as 1.33), and Table XIV means were rounded from 2-dp values.
    good = abs(float(got) - float(expected)) <= tol + 1e-6
    ok += good
    fail += not good
    flag = "ok  " if good else "FAIL"
    print(f"[{flag}] {where:<58} paper {expected:>10}   repo {float(got):.4f}")


def eq(where, got, expected):
    global ok, fail
    good = got == expected
    ok += good
    fail += not good
    print(f"[{'ok  ' if good else 'FAIL'}] {where:<58} paper {expected!s:>10}   repo {got!s}")


# ---- experimental accounting (Sec. VII-A) -----------------------------------
runs = {os.path.basename(f)[:-4]: len(pd.read_csv(f)) for f in glob.glob(os.path.join(RAW, "*.csv"))}
expected_runs = dict(baseline=120, load=840, scale=600, delay=330, fanout=360, failures=840,
                     escalation=360, selection=240, stigmergy=150, trace=480, trace_delay=150,
                     hzs_ablation=270)
for k_, v in expected_runs.items():
    eq(f"Sec. VII-A runs, {k_}", runs.get(k_), v)
eq("Sec. VII-A total runs", sum(runs.values()), 4740)

# ---- Table VII --------------------------------------------------------------
B = K["baseline"]
for s, mean, ci_, viol, vci, p95, p99, dec, mpt, load, busiest in [
        ("CZO", 42.71, 0.31, 2.12, 0.07, 83.30, 114.66, 20.00, 2.29, 3993, 3993),
        ("HORC", 31.96, 0.35, 1.32, 0.07, 73.81, 105.00, 8.08, 2.30, 4014, 812),
        ("AFS", 26.34, 0.35, 1.37, 0.07, 70.81, 107.05, 2.02, 6.02, 0, 0),
        ("HZS", 26.36, 0.35, 1.35, 0.08, 70.88, 106.43, 2.05, 9.41, 100, 100)]:
    b = B[s]
    check(f"Table VII {s} mean completion (ms)", b["mean_ms"], mean, 0.005)
    check(f"Table VII {s} mean 95% CI", b["mean_ms_ci"], ci_, 0.005)
    check(f"Table VII {s} SLA violation (%)", b["viol_pct"], viol, 0.005)
    check(f"Table VII {s} violation 95% CI", b["viol_pct_ci"], vci, 0.005)
    check(f"Table VII {s} P95 (ms)", b["p95_ms"], p95, 0.005)
    check(f"Table VII {s} P99 (ms)", b["p99_ms"], p99, 0.005)
    check(f"Table VII {s} decision latency (ms)", b["dec_ms"], dec, 0.005)
    check(f"Table VII {s} messages per task", b["msgs_per_task"], mpt, 0.005)
    check(f"Table VII {s} coordinator load (msg/s)", b["coord_load"], load, 0.5)
    check(f"Table VII {s} busiest controller (msg/s)", b["coord_load_max"], busiest, 0.5)
check("Abstract: swarm vs CZO latency reduction (%)",
      100 * (1 - B["AFS"]["mean_ms"] / B["CZO"]["mean_ms"]), 38.3, 0.05)
check("Abstract: HZS coordinator traffic reduction (%)",
      100 * (1 - B["HZS"]["coord_load"] / B["CZO"]["coord_load"]), 97.5, 0.05)
check("Sec. VII-B realised task rate (tasks/s)", B["CZO"]["lambda_real"], 1746, 0.5)
check("Sec. VII-B CZO waiting (ms)", B["CZO"]["wait_ms"], 2.97, 0.005)
check("Sec. VII-B AFS waiting (ms)", B["AFS"]["wait_ms"], 4.87, 0.005)
check("Sec. VII-B CZO service (ms)", B["CZO"]["serv_ms"], 17.64, 0.005)
check("Sec. VII-B AFS service (ms)", B["AFS"]["serv_ms"], 18.75, 0.005)
check("Sec. VII-B CZO forwards farther (ms)", B["CZO"]["fwd_ms"] - B["AFS"]["fwd_ms"], 1.41, 0.005)

# ---- Table VIII -------------------------------------------------------------
T = pd.read_csv(os.path.join(TAB, "table_tests.csv"))
for wl, comp, met, diff, ci_, ph, r in [
        ("synthetic, rho=0.7", "HZS vs CZO", "mean_ms", -16.35, 0.08, 2.2e-8, -1.00),
        ("synthetic, rho=0.7", "HZS vs CZO", "viol_pct", -0.77, 0.04, 2.2e-8, -1.00),
        ("synthetic, rho=0.7", "HZS vs HORC", "mean_ms", -5.60, 0.07, 2.2e-8, -1.00),
        ("synthetic, rho=0.7", "HZS vs HORC", "viol_pct", 0.02, 0.04, 0.63, 0.27),
        ("synthetic, rho=0.7", "HZS vs AFS", "mean_ms", 0.02, 0.04, 0.63, 0.25),
        ("synthetic, rho=0.7", "HZS vs AFS", "viol_pct", -0.02, 0.03, 0.24, -0.42),
        ("Azure trace, rho=0.7", "HZS vs CZO", "mean_ms", -11.42, 1.01, 2.2e-8, -1.00),
        ("Azure trace, rho=0.7", "HZS vs CZO", "viol_pct", -0.30, 0.56, 0.63, -0.13),
        ("Azure trace, rho=0.7", "HZS vs HORC", "mean_ms", -10.25, 1.48, 2.2e-8, -1.00),
        ("Azure trace, rho=0.7", "HZS vs HORC", "viol_pct", -0.70, 0.48, 0.12, -0.50),
        ("Azure trace, rho=0.7", "HZS vs AFS", "mean_ms", -0.21, 0.33, 0.24, -0.41),
        ("Azure trace, rho=0.7", "HZS vs AFS", "viol_pct", -0.15, 0.16, 0.14, -0.47)]:
    row = T[(T.Workload == wl) & (T.Comparison == comp) & (T.Metric == met)].iloc[0]
    tag = f"Table VIII {wl.split(',')[0]} {comp} {met}"
    check(tag + " Δ", row["Mean difference"], diff, 0.005)
    check(tag + " CI", row["95% CI of difference"], ci_, 0.005)
    check(tag + " p (Holm)", row["p (Holm)"], ph, 0.005 if ph > 1e-3 else 0.05e-8)
    check(tag + " r", row["r (rank-biserial)"], r, 0.005)

# ---- Sec. VII-C load and scale ---------------------------------------------
L = K["load"]
check("Sec. VII-C CZO mean at rho=0.3 (ms)", L["CZO"]["0.3"]["mean_ms"], 38.66, 0.005)
check("Sec. VII-C CZO mean at rho=0.9 (ms)", L["CZO"]["0.9"]["mean_ms"], 47.71, 0.005)
check("Sec. VII-C CZO violations at rho=0.3 (%)", L["CZO"]["0.3"]["viol_pct"], 1.34, 0.005)
check("Sec. VII-C CZO violations at rho=0.9 (%)", L["CZO"]["0.9"]["viol_pct"], 3.21, 0.005)
check("Sec. VII-C AFS mean at rho=0.3 (ms)", L["AFS"]["0.3"]["mean_ms"], 21.42, 0.005)
check("Sec. VII-C AFS mean at rho=0.9 (ms)", L["AFS"]["0.9"]["mean_ms"], 34.44, 0.005)
check("Sec. VII-C AFS violations at rho=0.3 (%)", L["AFS"]["0.3"]["viol_pct"], 0.72, 0.005)
check("Sec. VII-C AFS violations at rho=0.9 (%)", L["AFS"]["0.9"]["viol_pct"], 2.48, 0.005)
check("Sec. VII-C HZS violations at rho=0.9 (%)", L["HZS"]["0.9"]["viol_pct"], 2.42, 0.005)
S = K["scale"]
check("Sec. VII-C HORC mean at N=10 (ms)", S["HORC"]["10"]["mean_ms"], 43.05, 0.005)
check("Sec. VII-C HORC mean at N=200 (ms)", S["HORC"]["200"]["mean_ms"], 31.39, 0.005)
check("Sec. VII-C CZO load at N=10 (msg/s)", S["CZO"]["10"]["coord_load"], 797, 0.5)
check("Sec. VII-C CZO load at N=200 (msg/s)", S["CZO"]["200"]["coord_load"], 15986, 0.5)
check("Sec. VII-C HORC busiest at N=10 (msg/s)", S["HORC"]["10"]["coord_load_max"], 166, 0.5)
check("Sec. VII-C HORC busiest at N=200 (msg/s)", S["HORC"]["200"]["coord_load_max"], 3226, 0.5)
check("Sec. VII-C HZS load at N=10 (msg/s)", S["HZS"]["10"]["coord_load"], 20, 0.01)
check("Sec. VII-C HZS load at N=200 (msg/s)", S["HZS"]["200"]["coord_load"], 400, 0.01)
check("Sec. VII-C HORC violations at N=100 (%)", S["HORC"]["100"]["viol_pct"], 1.30, 0.005)
check("Sec. VII-C HORC violations at N=200 (%)", S["HORC"]["200"]["viol_pct"], 1.24, 0.005)
check("Sec. VII-C HZS violations at N=100 (%)", S["HZS"]["100"]["viol_pct"], 1.43, 0.005)

# ---- Sec. VII-D / Table IX --------------------------------------------------
C = K["crossover"]
check("Sec. VII-D CZO fit intercept (ms)", C["intercept"], 22.43, 0.005)
check("Sec. VII-D CZO fit slope", C["slope"], 1.015, 0.0005)
check("Table IX AFS measured d_c* (ms)", C["afs"], 3.85, 0.005)
check("Table IX AFS CI low", C["afs_ci"][0], 3.77, 0.005)
check("Table IX AFS CI high", C["afs_ci"][1], 3.92, 0.005)
check("Table IX HZS measured d_c* (ms)", C["hzs"], 3.87, 0.005)
check("Table IX HZS CI low", C["hzs_ci"][0], 3.80, 0.005)
check("Table IX HZS CI high", C["hzs_ci"][1], 3.94, 0.005)
for s, dec, dW, df, dS, pred in [("AFS", 2.02, 2.13, -1.41, 1.11, 3.86), ("HZS", 2.05, 2.18, -1.40, 1.06, 3.88)]:
    c = C["comp"][s]
    check(f"Table IX {s} d_dec", c["dec"], dec, 0.005)
    check(f"Table IX {s} ΔW", c["dW"], dW, 0.005)
    check(f"Table IX {s} Δf", c["df"], df, 0.005)
    check(f"Table IX {s} ΔS", c["dS"], dS, 0.005)
    check(f"Table IX {s} predicted d_c*", c["pred"], pred, 0.005)
check("Sec. VII-D SLA crossover (ms, 'about 11.5')", C["afs_viol_cross"], 11.5, 0.05)
check("Sec. VII-D CZO at d_c=1 ms, mean (ms)", C["czo"]["1.0"]["mean_ms"], 23.46, 0.005)
check("Sec. VII-D CZO at d_c=1 ms, violations (%)", C["czo"]["1.0"]["viol_pct"], 0.77, 0.005)
check("Sec. VII-D CZO at d_c=40 ms, mean (ms)", C["czo"]["40.0"]["mean_ms"], 63.05, 0.005)
check("Sec. VII-D CZO at d_c=40 ms, violations (%)", C["czo"]["40.0"]["viol_pct"], 6.23, 0.005)
TC = K["trace_crossover"]
check("Sec. VII-D trace CZO fit intercept (ms)", TC["intercept"], 49.68, 0.005)
check("Sec. VII-D trace CZO fit slope", TC["slope"], 1.01, 0.005)
check("Sec. VII-D trace crossover (ms, 'about 8.7')", TC["d_c_star_ms"], 8.7, 0.05)
TD = K["trace_delay"]
check("Sec. VII-H trace CZO at d_c=1 ms, mean (ms)", TD["1"]["mean_ms"] if "1" in TD else TD["1.0"]["mean_ms"], 50.69, 0.005)
check("Sec. VII-H trace CZO at d_c=1 ms, violations (%)", TD["1"]["viol_pct"] if "1" in TD else TD["1.0"]["viol_pct"], 8.64, 0.005)

# ---- Table X ----------------------------------------------------------------
F = K["fanout"]
for k_, am, av, amsg, hm, hv, hmsg in [(1, 31.92, 1.98, 2.07, 31.61, 1.74, 5.51), (2, 27.64, 1.52, 4.03, 27.62, 1.43, 7.48),
                                        (3, 26.34, 1.37, 6.02, 26.36, 1.35, 9.41), (4, 25.99, 1.32, 8.02, 26.02, 1.32, 11.33),
                                        (6, 30.44, 2.14, 12.02, 30.90, 2.25, 15.18), (8, 30.98, 2.29, 16.02, 31.84, 2.59, 19.04)]:
    a, h = F["AFS"][str(k_)], F["HZS"][str(k_)]
    check(f"Table X k={k_} AFS mean", a["mean_ms"], am, 0.005)
    check(f"Table X k={k_} AFS violation", a["viol_pct"], av, 0.005)
    check(f"Table X k={k_} AFS msgs/task", a["msgs_per_task"], amsg, 0.005)
    check(f"Table X k={k_} HZS mean", h["mean_ms"], hm, 0.005)
    check(f"Table X k={k_} HZS violation", h["viol_pct"], hv, 0.005)
    check(f"Table X k={k_} HZS msgs/task", h["msgs_per_task"], hmsg, 0.005)

# ---- Table XI ---------------------------------------------------------------
FL = K["failures"]
tab11 = {"F0 none": (2.12, 42.7, 1.32, 32.0, 1.37, 26.3, 1.35, 26.4),
         "F1 outage 2s": (7.43, 53.3, 2.33, 34.2, 1.37, 26.3, 1.32, 26.3),
         "F2 outage 5s": (16.76, 86.0, 4.24, 39.8, 1.37, 26.3, 1.33, 26.3),
         "F3 intermittent 4x0.5s": (6.37, 48.5, 2.16, 33.4, 1.37, 26.3, 1.35, 26.4),
         "F4 delayed recovery (cold)": (10.47, 62.3, 2.96, 35.9, 1.37, 26.3, 1.33, 26.3),
         "F5 node crash 10%": (2.27, 43.2, 1.53, 33.1, 1.52, 27.4, 1.48, 27.4),
         "F6 msg loss 5%": (4.41, 47.2, 2.76, 36.3, 1.42, 26.7, 1.39, 26.7)}
for sc_, vals in tab11.items():
    for i, s in enumerate(("CZO", "HORC", "AFS", "HZS")):
        check(f"Table XI {sc_.split()[0]} {s} violation (%)", FL[sc_][s]["viol_pct"], vals[2 * i], 0.005)
        check(f"Table XI {sc_.split()[0]} {s} mean (ms)", FL[sc_][s]["mean_ms"], vals[2 * i + 1], 0.05)

# ---- Tables XII, XIII, XV, XVII and XIV (string tables) ---------------------
def tab(name):
    return pd.read_csv(os.path.join(TAB, name + ".csv"))


def num(s):
    return float(str(s).split("±")[0])


E = tab("table_escalation")
for rho, s, e, esc, mean, viol in [(0.7, "AFS", 1, 0.58, 26.34, 1.37), (0.7, "HZS", 1, 0.53, 26.36, 1.35),
                                   (0.9, "AFS", 0, 0.0, 34.48, 2.58), (0.9, "AFS", 1, 1.12, 34.44, 2.47),
                                   (0.9, "HZS", 1, 0.91, 34.36, 2.42), (0.7, "AFS", 2, 0.58, 26.36, 1.40)]:
    r = E[(E.rho == rho) & (E.Scheme == s) & (E.E_max == e)].iloc[0]
    check(f"Table XII rho={rho} {s} E_max={e} escalated (%)", r["Escalated tasks (%)"], esc, 0.005)
    check(f"Table XII rho={rho} {s} E_max={e} mean (ms)", num(r["Mean (ms)"]), mean, 0.005)
    check(f"Table XII rho={rho} {s} E_max={e} violation (%)", num(r["Violation (%)"]), viol, 0.005)
SE = tab("table_selection")
for rho, s, rule, mean, viol in [(0.7, "AFS", "fixed_id", 27.45, 1.51), (0.7, "HZS", "fixed_id", 27.34, 1.44),
                                 (0.9, "AFS", "fixed_id", 38.81, 3.21), (0.9, "HZS", "fixed_id", 37.80, 2.88),
                                 (0.9, "AFS", "random", 34.44, 2.47), (0.9, "HZS", "random", 34.36, 2.42)]:
    r = SE[(SE.rho == rho) & (SE.Scheme == s) & (SE["first_k rule"] == rule)].iloc[0]
    check(f"Table XIII rho={rho} {s} {rule} mean", num(r["Mean (ms)"]), mean, 0.005)
    check(f"Table XIII rho={rho} {s} {rule} violation", num(r["Violation (%)"]), viol, 0.005)
ST = tab("table_stigmergy")
for setting, beta, mean, p95, viol in [("default", 0.0, 26.31, 70.71, 1.35), ("default", 0.1, 26.34, 70.81, 1.37),
                                       ("default", 0.5, 26.33, 70.95, 1.37), ("default", 1.0, 26.34, 70.92, 1.37),
                                       ("aggressive", 1.0, 26.72, 72.05, 1.47)]:
    r = ST[(ST.setting == setting) & (ST.beta == beta)].iloc[0]
    check(f"Table XVII {setting} beta={beta} mean", num(r["Mean (ms)"]), mean, 0.005)
    check(f"Table XVII {setting} beta={beta} P95", r["P95 (ms)"], p95, 0.005)
    check(f"Table XVII {setting} beta={beta} violation", num(r["Violation (%)"]), viol, 0.005)
HA = tab("table_hzs_ablation")
for v, mean, viol, part, load, p in [("HZS (full)", 58.43, 9.16, 1.29, 100, None),
                                     ("no capacity lease", 58.41, 9.12, 1.83, 100, 0.043),
                                     ("load-averse score", 58.41, 9.19, 1.21, 100, 0.309),
                                     ("eager partners", 63.00, 10.26, 7.17, 100, 0.000),
                                     ("no partners (p=0)", 58.71, 9.34, 0.00, 100, 0.006),
                                     ("T_p = 0.25 s", 58.29, 9.12, 1.93, 400, 0.440),
                                     ("T_p = 0.5 s", 58.41, 9.14, 1.65, 200, 0.919),
                                     ("T_p = 2 s", 58.59, 9.26, 1.10, 50, 0.014),
                                     ("T_p = 5 s", 58.40, 9.18, 0.74, 20, 0.129)]:
    r = HA[HA.Variant == v].iloc[0]
    check(f"Table XV {v} mean", num(r["Mean (ms)"]), mean, 0.005)
    check(f"Table XV {v} violation", num(r["Violation (%)"]), viol, 0.005)
    check(f"Table XV {v} partner dispatches (%)", r["Partner dispatches (%)"], part, 0.005)
    check(f"Table XV {v} coordinator load", r["Coordinator load (msg/s)"], load, 0.05)
    if p is not None:
        check(f"Table XV {v} p vs full", float(r["p vs full (viol.)"]), p, 0.0005)
TR = K["trace"]
for rho, vals in {"0.3": (38.7, 0.19, 29.0, 0.31, 23.9, 0.73, 23.8, 0.74),
                  "0.5": (48.4, 2.95, 41.8, 3.23, 35.0, 3.32, 34.3, 3.16),
                  "0.7": (69.9, 9.46, 68.7, 9.86, 58.6, 9.31, 58.4, 9.16),
                  "0.9": (173.7, 31.3, 179.0, 32.6, 167.4, 31.5, 166.0, 31.2)}.items():
    for i, s in enumerate(("CZO", "HORC", "AFS", "HZS")):
        check(f"Table XIV rho={rho} {s} mean (ms)", TR[s][rho]["mean_ms"], vals[2 * i], 0.055)
        tol = 0.055 if rho == "0.9" else 0.005
        check(f"Table XIV rho={rho} {s} violation (%)", TR[s][rho]["viol_pct"], vals[2 * i + 1], tol)

# ---- Table XVI --------------------------------------------------------------
W = K["winners"]
eq("Table XVI configurations", W["total"], 40)
eq("Table XVI lowest violation counts", W["best_counts"], {"AFS": 3, "CZO": 9, "HORC": 6, "HZS": 22})
eq("Table XVI significant after Holm", W["significant_holm"], {"AFS": 2, "CZO": 7, "HORC": 2, "HZS": 3})
eq("Table XVI significant unadjusted", W["significant_unadjusted"], {"AFS": 2, "CZO": 8, "HORC": 2, "HZS": 14})
eq("Sec. VIII-A not significant after Holm", W["not_significant_holm"], 26)
eq("Sec. VIII-A not significant unadjusted", W["not_significant_unadjusted"], 14)
WT = tab("table_winners")
holm_hzs = sorted(WT[(WT["Lowest violation"] == "HZS") & (WT["Significant, Holm (p<0.05)"] == "yes")].Setting)
eq("Table XVI HZS Holm-significant settings", holm_hzs, ["k=1", "k=2", "scenario=F1 outage 2s"])

print(f"\n{ok} numbers reproduced, {fail} mismatches")
sys.exit(1 if fail else 0)
