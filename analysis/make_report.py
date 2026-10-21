#!/usr/bin/env python3
"""Turn results/raw/*.csv into the tables and figures used in the paper.

Outputs
  results/summary/<exp>_summary.csv   mean, std, 95% CI per configuration
  results/tables/*.csv + tables.md     every table in the paper
  results/figures/fig*.png|pdf         every data figure in the paper
  results/summary/key_numbers.json     numbers quoted in the text

Statistics: means over 30 paired seeds; 95% CI = t(0.975, n-1) * sd / sqrt(n);
paired two-sided Wilcoxon signed-rank tests with Holm-Bonferroni correction;
crossover delay from a least-squares line with a 2000-sample seed bootstrap.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "results", "raw")
SUM = os.path.join(ROOT, "results", "summary")
TAB = os.path.join(ROOT, "results", "tables")
FIG = os.path.join(ROOT, "results", "figures")
for d in (SUM, TAB, FIG):
    os.makedirs(d, exist_ok=True)

ORDER = ["CZO", "HORC", "AFS", "HZS"]
STYLE = {"CZO": dict(color="#1f4e79", marker="s", ls="-"),
         "HORC": dict(color="#7f6000", marker="D", ls="-."),
         "AFS": dict(color="#c55a11", marker="o", ls="--"),
         "HZS": dict(color="#2e7d32", marker="^", ls="-")}
METRICS = ["mean_ms", "p95_ms", "p99_ms", "viol_pct", "lost_pct", "dec_ms",
           "fwd_ms", "wait_ms", "serv_ms", "msgs_per_task", "coord_load",
           "coord_load_max", "esc_pct", "partner_pct", "lambda_real"]

plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.labelsize": 8,
                     "legend.fontsize": 7, "xtick.labelsize": 7, "ytick.labelsize": 7,
                     "axes.grid": True, "grid.alpha": 0.3, "savefig.dpi": 300,
                     "savefig.bbox": "tight"})
KEY = {}


def load(name):
    return pd.read_csv(os.path.join(RAW, f"{name}.csv"))


def ci(x):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return 0.0
    return float(stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x)))


def summarise(df, keys, name):
    g = df.groupby(keys)
    rows = []
    for k, sub in g:
        k = k if isinstance(k, tuple) else (k,)
        r = dict(zip(keys, k))
        r["n"] = len(sub)
        for m in METRICS:
            if m in sub:
                r[m] = sub[m].mean()
                r[m + "_sd"] = sub[m].std(ddof=1)
                r[m + "_ci"] = ci(sub[m])
        rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(SUM, f"{name}_summary.csv"), index=False)
    return out


def fmt(m, c, d=2):
    return f"{m:.{d}f} ± {c:.{d}f}"


def holm(pvals):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    m = len(p)
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p[idx]))
        adj[idx] = running
    return adj


def wilcoxon(a, b):
    d = np.asarray(a) - np.asarray(b)
    if np.allclose(d, 0):
        return 1.0
    try:
        return float(stats.wilcoxon(a, b, zero_method="zsplit").pvalue)
    except ValueError:
        return 1.0


def rank_biserial(a, b):
    """Matched-pairs rank-biserial correlation r = (W+ - W-) / (W+ + W-).

    Ranks of |a - b| over the non-zero differences (Kerby, 2014). r is in [-1, 1];
    negative values mean that `a` is lower; |r| = 1 means the same sign on every seed.
    """
    d = np.asarray(a, float) - np.asarray(b, float)
    d = d[d != 0]
    if len(d) == 0:
        return 0.0
    r = stats.rankdata(np.abs(d))
    wp, wm = r[d > 0].sum(), r[d < 0].sum()
    return float((wp - wm) / (wp + wm))


def paired(df, keys, s1, s2, metric):
    x = df[df.scheme == s1].sort_values("seed")[metric].to_numpy()
    y = df[df.scheme == s2].sort_values("seed")[metric].to_numpy()
    return x, y


def save(fig, name):
    fig.savefig(os.path.join(FIG, name + ".png"))
    fig.savefig(os.path.join(FIG, name + ".pdf"))
    plt.close(fig)


md = []


def table(df, name, title):
    df.to_csv(os.path.join(TAB, name + ".csv"), index=False)
    md.append(f"\n### {title}\n\n" + df.to_markdown(index=False) + "\n")


# ------------------------------------------------------------------ baseline
b = load("baseline")
sb = summarise(b, ["scheme"], "baseline").set_index("scheme").loc[ORDER]
rows = []
for s in ORDER:
    r = sb.loc[s]
    rows.append({"Metric": s,
                 "Mean completion (ms)": fmt(r.mean_ms, r.mean_ms_ci),
                 "P95 (ms)": f"{r.p95_ms:.2f}", "P99 (ms)": f"{r.p99_ms:.2f}",
                 "SLA violation (%)": fmt(r.viol_pct, r.viol_pct_ci),
                 "Decision latency (ms)": f"{r.dec_ms:.2f}",
                 "Msgs per task": f"{r.msgs_per_task:.2f}",
                 "Coordinator load, total (msg/s)": f"{r.coord_load:.0f}",
                 "Busiest controller (msg/s)": f"{r.coord_load_max:.0f}"})
t5 = pd.DataFrame(rows).set_index("Metric").T.reset_index().rename(columns={"index": "Metric"})
table(t5, "table_baseline", "Reference configuration (N=50, rho=0.7, d_c=20 ms, 30 seeds)")
KEY["baseline"] = sb[["mean_ms", "mean_ms_ci", "viol_pct", "viol_pct_ci", "p95_ms",
                      "p99_ms", "dec_ms", "msgs_per_task", "coord_load",
                      "coord_load_max", "lambda_real", "wait_ms", "serv_ms",
                      "fwd_ms", "esc_pct", "partner_pct"]].round(4).to_dict("index")

# pairwise tests on the baseline and on the trace workload at rho=0.7
tr = load("trace")
tests = []
for label, df in (("synthetic, rho=0.7", b), ("Azure trace, rho=0.7", tr[tr.rho == 0.7])):
    for other in ("CZO", "HORC", "AFS"):
        for m in ("mean_ms", "viol_pct"):
            x, y = paired(df, None, "HZS", other, m)
            tests.append({"Workload": label, "Comparison": f"HZS vs {other}", "Metric": m,
                          "Mean difference": float(np.mean(x - y)),
                          "95% CI of difference": ci(x - y),
                          "p (Wilcoxon)": wilcoxon(x, y),
                          "r (rank-biserial)": rank_biserial(x, y)})
tt = pd.DataFrame(tests)
tt["p (Holm)"] = holm(tt["p (Wilcoxon)"])
tt["Significant (0.05)"] = np.where(tt["p (Holm)"] < 0.05, "yes", "no")
tt = tt[["Workload", "Comparison", "Metric", "Mean difference", "95% CI of difference",
         "p (Wilcoxon)", "p (Holm)", "r (rank-biserial)", "Significant (0.05)"]]
for c in ("Mean difference", "95% CI of difference"):
    tt[c] = tt[c].round(3)
tt["r (rank-biserial)"] = tt["r (rank-biserial)"].round(2)
tt["p (Wilcoxon)"] = tt["p (Wilcoxon)"].map(lambda v: f"{v:.2e}")
tt["p (Holm)"] = tt["p (Holm)"].map(lambda v: f"{v:.2e}")
table(tt, "table_tests", "Paired Wilcoxon signed-rank tests (30 seeds, Holm-corrected)")
KEY["tests"] = tt.to_dict("records")

# ------------------------------------------------------------------ load
ld = load("load")
sl = summarise(ld, ["rho", "scheme"], "load")
fig, ax = plt.subplots(2, 1, figsize=(3.5, 4.2), sharex=True)
for s in ORDER:
    d = sl[sl.scheme == s].sort_values("rho")
    ax[0].errorbar(d.rho, d.mean_ms, d.mean_ms_ci, label=s, capsize=2, ms=3.5, lw=1.1, **STYLE[s])
    ax[1].errorbar(d.rho, d.viol_pct, d.viol_pct_ci, label=s, capsize=2, ms=3.5, lw=1.1, **STYLE[s])
ax[0].set_ylabel("Mean completion time (ms)")
ax[1].set_ylabel("SLA violation (%)")
ax[1].set_xlabel(r"Offered load $\rho$")
ax[0].set_title("(a)", loc="left", fontsize=8)
ax[1].set_title("(b)", loc="left", fontsize=8)
ax[0].legend(ncol=4, loc="upper left", frameon=False)
save(fig, "fig3_load")
KEY["load"] = {s: sl[sl.scheme == s].set_index("rho")[["mean_ms", "viol_pct", "mean_ms_ci", "viol_pct_ci"]].round(3).to_dict("index") for s in ORDER}

# ------------------------------------------------------------------ scale
sc = load("scale")
ss = summarise(sc, ["N", "scheme"], "scale")
fig, ax = plt.subplots(2, 1, figsize=(3.5, 4.2))
for s, col, lab in (("CZO", "coord_load", "CZO (single controller)"),
                    ("HORC", "coord_load_max", "HORC (busiest controller)"),
                    ("HZS", "coord_load", "HZS (coordinator)")):
    d = ss[ss.scheme == s].sort_values("N")
    ax[0].plot(d.N, d[col], label=lab, ms=3.5, lw=1.1, **STYLE[s])
d = ss[ss.scheme == "AFS"].sort_values("N")
ax[0].plot(d.N, np.full(len(d), 1.0), label="AFS (none; drawn at floor)", ms=3.5, lw=1.1, **STYLE["AFS"])
ax[0].set_xscale("log"); ax[0].set_yscale("log")
ax[0].set_ylabel("Coordinator-incident msgs/s")
ax[0].legend(frameon=False, fontsize=6.5)
ax[0].set_title("(a)", loc="left", fontsize=8)
for s in ORDER:
    d = ss[ss.scheme == s].sort_values("N")
    ax[1].errorbar(d.N, d.mean_ms, d.mean_ms_ci, label=s, capsize=2, ms=3.5, lw=1.1, **STYLE[s])
ax[1].set_xscale("log")
ax[1].set_xlabel("Number of fog nodes N")
ax[1].set_ylabel("Mean completion time (ms)")
ax[1].set_title("(b)", loc="left", fontsize=8)
ax[1].legend(ncol=4, frameon=False, loc="upper right")
save(fig, "fig4_scale")
KEY["scale"] = {s: ss[ss.scheme == s].set_index("N")[["mean_ms", "viol_pct", "coord_load", "coord_load_max", "msgs_per_task"]].round(3).to_dict("index") for s in ORDER}

# ------------------------------------------------------------------ delay / crossover
dl = load("delay")
sd = summarise(dl, ["d_c_ms"], "delay").sort_values("d_c_ms")
afs = b[b.scheme == "AFS"].sort_values("seed")
hzs = b[b.scheme == "HZS"].sort_values("seed")


def crossing(dfc, target_mean):
    g = dfc.groupby("d_c_ms").mean_ms.mean()
    slope, icpt = np.polyfit(g.index.to_numpy(float), g.to_numpy(), 1)
    return (target_mean - icpt) / slope, slope, icpt


x_afs, slope, icpt = crossing(dl, afs.mean_ms.mean())
x_hzs, _, _ = crossing(dl, hzs.mean_ms.mean())
rng = np.random.default_rng(12345)
seeds = np.sort(dl.seed.unique())
boot_a, boot_h = [], []
for _ in range(2000):
    sel = rng.choice(seeds, len(seeds), replace=True)
    sub = pd.concat([dl[dl.seed == s_] for s_ in sel])
    ma = np.mean([afs[afs.seed == s_].mean_ms.iloc[0] for s_ in sel])
    mh = np.mean([hzs[hzs.seed == s_].mean_ms.iloc[0] for s_ in sel])
    boot_a.append(crossing(sub, ma)[0])
    boot_h.append(crossing(sub, mh)[0])
ci_a = np.percentile(boot_a, [2.5, 97.5])
ci_h = np.percentile(boot_h, [2.5, 97.5])
# the same crossing measured on the SLA metric (interpolated)
gv = dl.groupby("d_c_ms").viol_pct.mean()
x_v = float(np.interp(afs.viol_pct.mean(), gv.to_numpy(), gv.index.to_numpy(float)))

# analytical prediction, Eq. (15): d_c* = d_dec^loc + dW + df + dS
czo_small = dl[dl.d_c_ms <= 5]
comp = {}
for nm, dfm in (("AFS", afs), ("HZS", hzs)):
    comp[nm] = dict(dec=dfm.dec_ms.mean(), dW=dfm.wait_ms.mean() - czo_small.wait_ms.mean(),
                    df=dfm.fwd_ms.mean() - czo_small.fwd_ms.mean(),
                    dS=dfm.serv_ms.mean() - czo_small.serv_ms.mean())
    comp[nm]["pred"] = sum(comp[nm].values())
rows = []
for nm, emp, cc in (("AFS", x_afs, ci_a), ("HZS", x_hzs, ci_h)):
    c = comp[nm]
    rows.append({"Decentralised scheme": nm,
                 "d_dec (ms)": round(c["dec"], 2), "ΔW (ms)": round(c["dW"], 2),
                 "Δf (ms)": round(c["df"], 2), "ΔS (ms)": round(c["dS"], 2),
                 "Predicted d_c* (ms), Eq. 15": round(c["pred"], 2),
                 "Empirical d_c* (ms)": round(emp, 2),
                 "Bootstrap 95% CI (ms)": f"[{cc[0]:.2f}, {cc[1]:.2f}]"})
table(pd.DataFrame(rows), "table_crossover", "Crossover controller delay: analytical vs. empirical")
KEY["crossover"] = dict(slope=slope, intercept=icpt, afs=x_afs, afs_ci=list(ci_a), hzs=x_hzs,
                        hzs_ci=list(ci_h), afs_viol_cross=x_v, comp=comp,
                        czo=sd.set_index("d_c_ms")[["mean_ms", "viol_pct"]].round(3).to_dict("index"))

fig, ax = plt.subplots(figsize=(3.5, 2.4))
ax.errorbar(sd.d_c_ms, sd.mean_ms, sd.mean_ms_ci, capsize=2, ms=3.5, lw=1.1, label="CZO (measured)", **STYLE["CZO"])
xx = np.linspace(0, 42, 50)
ax.plot(xx, icpt + slope * xx, color=STYLE["CZO"]["color"], lw=0.7, alpha=0.6,
        label=f"fit: {icpt:.1f} + {slope:.2f}·$d_c$")
for nm, m_, c_ in (("AFS", afs.mean_ms.mean(), ci(afs.mean_ms)), ("HZS", hzs.mean_ms.mean(), ci(hzs.mean_ms))):
    ax.axhspan(m_ - c_, m_ + c_, color=STYLE[nm]["color"], alpha=0.25)
    ax.axhline(m_, color=STYLE[nm]["color"], ls=STYLE[nm]["ls"], lw=1, label=f"{nm} ({m_:.2f} ms)")
ax.axvline(x_afs, color="grey", lw=0.8, ls=":")
ax.annotate(f"$d_c^*$ ≈ {x_afs:.2f} ms", (x_afs, afs.mean_ms.mean()), xytext=(8, 40),
            textcoords="offset points", fontsize=7, arrowprops=dict(arrowstyle="->", lw=0.6))
ax.set_xlabel("Controller round-trip delay $d_c$ (ms)")
ax.set_ylabel("Mean completion time (ms)")
ax.legend(frameon=False, fontsize=6.5, loc="upper left")
save(fig, "fig5_delay")

# ------------------------------------------------------------------ fan-out
fo = load("fanout")
sf = summarise(fo, ["k", "scheme"], "fanout")
fig, ax = plt.subplots(figsize=(3.5, 2.3))
for s in ("AFS", "HZS"):
    d = sf[sf.scheme == s].sort_values("k")
    ax.errorbar(d.k, d.viol_pct, d.viol_pct_ci, label=s, capsize=2, ms=3.5, lw=1.1, **STYLE[s])
ax.axhline(sb.loc["CZO"].viol_pct, color=STYLE["CZO"]["color"], lw=1, label="CZO ($d_c$ = 20 ms)")
ax.set_xlabel("Probe fan-out k")
ax.set_ylabel("SLA violation (%)")
ax.legend(frameon=False)
save(fig, "fig6_fanout")
rows = []
for kk in sorted(fo.k.unique()):
    r = {"k": int(kk)}
    for s in ("AFS", "HZS"):
        d = sf[(sf.k == kk) & (sf.scheme == s)].iloc[0]
        r[f"{s} mean (ms)"] = fmt(d.mean_ms, d.mean_ms_ci)
        r[f"{s} violation (%)"] = fmt(d.viol_pct, d.viol_pct_ci)
        r[f"{s} msgs/task"] = round(d.msgs_per_task, 2)
    rows.append(r)
table(pd.DataFrame(rows), "table_fanout", "Probe fan-out sweep")
KEY["fanout"] = {s: sf[sf.scheme == s].set_index("k")[["mean_ms", "viol_pct", "msgs_per_task"]].round(3).to_dict("index") for s in ("AFS", "HZS")}

# ------------------------------------------------------------------ failures
fl = load("failures")
sfl = summarise(fl, ["scenario", "scheme"], "failures")
scen = list(dict.fromkeys(fl.scenario))
rows = []
for f in scen:
    r = {"Scenario": f}
    for s in ORDER:
        d = sfl[(sfl.scenario == f) & (sfl.scheme == s)].iloc[0]
        r[f"{s} viol. (%)"] = fmt(d.viol_pct, d.viol_pct_ci)
        r[f"{s} mean (ms)"] = f"{d.mean_ms:.2f}"
    rows.append(r)
table(pd.DataFrame(rows), "table_failures", "Failure scenarios (30 seeds, 10 s horizon)")
KEY["failures"] = {f: {s: sfl[(sfl.scenario == f) & (sfl.scheme == s)][["mean_ms", "viol_pct", "lost_pct", "viol_pct_ci"]].iloc[0].round(3).to_dict() for s in ORDER} for f in scen}
fig, ax = plt.subplots(figsize=(3.5, 2.6))
w = 0.2
x = np.arange(len(scen))
for k_, s in enumerate(ORDER):
    d = sfl[sfl.scheme == s].set_index("scenario").loc[scen]
    ax.bar(x + (k_ - 1.5) * w, d.viol_pct, w, yerr=d.viol_pct_ci, capsize=1.5,
           color=STYLE[s]["color"], label=s, error_kw=dict(lw=0.6))
ax.set_xticks(x)
ax.set_xticklabels([f.split(" ")[0] for f in scen])
ax.set_ylabel("SLA violation (%)")
ax.legend(ncol=4, frameon=False, loc="upper left")
save(fig, "fig7_failures")

# ------------------------------------------------------------------ escalation
es = load("escalation")
ses = summarise(es, ["rho", "E_max", "scheme"], "escalation")
rows = []
for _, d in ses.sort_values(["rho", "scheme", "E_max"]).iterrows():
    rows.append({"rho": d.rho, "Scheme": d.scheme, "E_max": int(d.E_max),
                 "Escalated tasks (%)": round(d.esc_pct, 2),
                 "Mean (ms)": fmt(d.mean_ms, d.mean_ms_ci),
                 "P99 (ms)": round(d.p99_ms, 2),
                 "Violation (%)": fmt(d.viol_pct, d.viol_pct_ci),
                 "Decision latency (ms)": round(d.dec_ms, 3),
                 "Msgs/task": round(d.msgs_per_task, 3)})
table(pd.DataFrame(rows), "table_escalation", "Escalation-depth ablation")
KEY["escalation"] = rows

# ------------------------------------------------------------------ selection
se = load("selection")
sse = summarise(se, ["rho", "selection", "scheme"], "selection")
rows = []
for _, d in sse.sort_values(["rho", "scheme", "selection"]).iterrows():
    rows.append({"rho": d.rho, "Scheme": d.scheme, "first_k rule": d.selection,
                 "Mean (ms)": fmt(d.mean_ms, d.mean_ms_ci),
                 "Violation (%)": fmt(d.viol_pct, d.viol_pct_ci)})
table(pd.DataFrame(rows), "table_selection", "Neighbour-selection rule for first_k")
KEY["selection"] = rows

# ------------------------------------------------------------------ stigmergy
st = load("stigmergy")
sst = summarise(st, ["setting", "beta"], "stigmergy")
rows = [{"setting": d.setting, "beta": d.beta, "Mean (ms)": fmt(d.mean_ms, d.mean_ms_ci),
         "P95 (ms)": round(d.p95_ms, 2), "Violation (%)": fmt(d.viol_pct, d.viol_pct_ci)}
        for _, d in sst.sort_values(["setting", "beta"], ascending=[False, True]).iterrows()]
table(pd.DataFrame(rows), "table_stigmergy", "Stigmergic-bias ablation (AFS, rho=0.7)")
KEY["stigmergy"] = rows

# ------------------------------------------------------------------ HZS ablation
ha = load("hzs_ablation")
sha = summarise(ha, ["variant"], "hzs_ablation")
order_v = list(dict.fromkeys(ha.variant))
full = ha[ha.variant == "HZS (full)"].sort_values("seed")
rows = []
for v in order_v:
    d = sha[sha.variant == v].iloc[0]
    x = ha[ha.variant == v].sort_values("seed")
    p = wilcoxon(x.viol_pct.to_numpy(), full.viol_pct.to_numpy()) if v != "HZS (full)" else np.nan
    rows.append({"Variant": v, "Mean (ms)": fmt(d.mean_ms, d.mean_ms_ci),
                 "Violation (%)": fmt(d.viol_pct, d.viol_pct_ci),
                 "Partner dispatches (%)": round(d.partner_pct, 2),
                 "Coordinator load (msg/s)": round(d.coord_load, 1),
                 "p vs full (viol.)": "—" if np.isnan(p) else f"{p:.3f}"})
table(pd.DataFrame(rows), "table_hzs_ablation", "HZS design ablation (Azure trace, rho=0.7)")
KEY["hzs_ablation"] = rows

# ------------------------------------------------------------------ trace
strc = summarise(tr, ["rho", "scheme"], "trace")
fig, ax = plt.subplots(2, 1, figsize=(3.5, 4.2), sharex=True)
for s in ORDER:
    d = strc[strc.scheme == s].sort_values("rho")
    ax[0].errorbar(d.rho, d.mean_ms, d.mean_ms_ci, label=s, capsize=2, ms=3.5, lw=1.1, **STYLE[s])
    ax[1].errorbar(d.rho, d.viol_pct, d.viol_pct_ci, label=s, capsize=2, ms=3.5, lw=1.1, **STYLE[s])
ax[0].set_ylabel("Mean completion time (ms)")
ax[1].set_ylabel("SLA violation (%)")
ax[1].set_xlabel(r"Offered load $\rho$ (Azure Functions 2021 trace)")
ax[0].set_title("(a)", loc="left", fontsize=8)
ax[1].set_title("(b)", loc="left", fontsize=8)
ax[0].legend(ncol=4, frameon=False, loc="upper left")
save(fig, "fig8_trace")
rows = []
for rr in sorted(tr.rho.unique()):
    r = {"rho": rr}
    for s in ORDER:
        d = strc[(strc.rho == rr) & (strc.scheme == s)].iloc[0]
        r[f"{s} mean (ms)"] = fmt(d.mean_ms, d.mean_ms_ci)
        r[f"{s} viol. (%)"] = fmt(d.viol_pct, d.viol_pct_ci)
    rows.append(r)
table(pd.DataFrame(rows), "table_trace", "Azure Functions 2021 trace-driven results")
KEY["trace"] = {s: strc[strc.scheme == s].set_index("rho")[["mean_ms", "viol_pct", "mean_ms_ci", "viol_pct_ci", "p95_ms", "coord_load", "coord_load_max"]].round(3).to_dict("index") for s in ORDER}
td = load("trace_delay")
KEY["trace_delay"] = td.groupby("d_c_ms")[["mean_ms", "viol_pct"]].mean().round(3).to_dict("index")
# crossover on the trace-derived workload (Sec. VII-D/VII-H): CZO line vs HZS mean at rho = 0.7
g_t = td.groupby("d_c_ms").mean_ms.mean()
t_slope, t_icpt = np.polyfit(g_t.index.to_numpy(float), g_t.to_numpy(), 1)
hzs_tr = tr[(tr.rho == 0.7) & (tr.scheme == "HZS")].mean_ms.mean()
KEY["trace_crossover"] = dict(slope=float(t_slope), intercept=float(t_icpt),
                              hzs_mean_ms=float(hzs_tr),
                              d_c_star_ms=float((hzs_tr - t_icpt) / t_slope))

# ------------------------------------------------------------------ winner table (evidence for G1-G4)
def winners(df, keys, label, schemes=ORDER):
    out = []
    for k, sub in df.groupby(keys):
        k = k if isinstance(k, tuple) else (k,)
        present = [s for s in schemes if s in set(sub.scheme)]
        means = {s: sub[sub.scheme == s].viol_pct.mean() for s in present}
        mlat = {s: sub[sub.scheme == s].mean_ms.mean() for s in present}
        best = min(means, key=means.get)
        rest = sorted((s for s in present if s != best), key=means.get)
        runner = rest[0]
        x = sub[sub.scheme == best].sort_values("seed").viol_pct.to_numpy()
        y = sub[sub.scheme == runner].sort_values("seed").viol_pct.to_numpy()
        p = wilcoxon(x, y)
        bl = min(mlat, key=mlat.get)
        out.append({"Sweep": label, "Setting": ", ".join(f"{kk}={vv}" for kk, vv in zip(keys, k)),
                    "Lowest violation": best, "Runner-up": runner,
                    "Viol. best / runner-up (%)": f"{means[best]:.2f} / {means[runner]:.2f}",
                    "_p": p,
                    "Lowest mean latency": bl})
    return out


W = []
W += winners(ld, ["rho"], "Load (synthetic)")
W += winners(sc, ["N"], "Scale (synthetic)")
dlx = pd.concat([dl.assign(scheme="CZO"), b[b.scheme.isin(["AFS", "HZS"])].merge(
    pd.DataFrame({"d_c_ms": sorted(dl.d_c_ms.unique())}), how="cross")])
W += winners(dlx, ["d_c_ms"], "Controller delay", schemes=["CZO", "AFS", "HZS"])
W += winners(fo.assign(), ["k"], "Fan-out", schemes=["AFS", "HZS"])
W += winners(fl, ["scenario"], "Failures")
W += winners(tr, ["rho"], "Azure trace")
wt = pd.DataFrame(W)
# Holm-Bonferroni correction over all 40 simultaneous comparisons (Table XVI);
# unadjusted p-values are kept as an exploratory column.
wt["p_holm"] = holm(wt["_p"])
wt["p (Wilcoxon, unadjusted)"] = wt["_p"].map(lambda v: f"{v:.3g}")
wt["p (Holm, 40 tests)"] = wt["p_holm"].map(lambda v: f"{v:.3g}")
wt["Significant, unadjusted (p<0.05)"] = np.where(wt["_p"] < 0.05, "yes", "no")
wt["Significant, Holm (p<0.05)"] = np.where(wt["p_holm"] < 0.05, "yes", "no")
cnt = wt.groupby("Lowest violation").size().to_dict()
dec_unadj = wt[wt["_p"] < 0.05].groupby("Lowest violation").size().to_dict()
dec_holm = wt[wt["p_holm"] < 0.05].groupby("Lowest violation").size().to_dict()
KEY["winners"] = dict(total=len(wt), best_counts=cnt,
                      significant_holm=dec_holm, significant_unadjusted=dec_unadj,
                      not_significant_holm=int((wt["p_holm"] >= 0.05).sum()),
                      not_significant_unadjusted=int((wt["_p"] >= 0.05).sum()))
wt = wt.drop(columns=["_p", "p_holm"])
wt = wt[["Sweep", "Setting", "Lowest violation", "Runner-up", "Viol. best / runner-up (%)",
         "p (Wilcoxon, unadjusted)", "p (Holm, 40 tests)", "Significant, unadjusted (p<0.05)",
         "Significant, Holm (p<0.05)", "Lowest mean latency"]]
table(wt, "table_winners", "Evidence summary per configuration (Table XVI): lowest SLA violation, "
      "paired Wilcoxon vs runner-up, Holm-corrected over all 40 comparisons")

with open(os.path.join(TAB, "tables.md"), "w") as f:
    f.write("# Result tables (auto-generated by analysis/make_report.py)\n")
    f.write("\n".join(md))


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o


with open(os.path.join(SUM, "key_numbers.json"), "w") as f:
    json.dump(_clean(KEY), f, indent=1, default=str)
print("report written:", TAB, FIG)
