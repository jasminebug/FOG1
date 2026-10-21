# FOG1 — Orchestration vs. Agentic Swarms vs. HZS for Zero-Touch Fog Computing

Code, data and raw results for the paper

> **Centralized Orchestration versus Decentralized Agentic Swarms for Zero-Touch Fog Computing:
> Comparative Analysis and Hybrid Architecture**
> Bashar Aswad, Jasmine Kaur and Anurag Rana —
> Yogananda School of AI, Computers and Data Sciences, Shoolini University, Solan, Himachal Pradesh, India

Repository: <https://github.com/jasminebug/FOG1>

This repository contains:

- the event-driven simulator in which all four control planes are evaluated on identical workloads, topologies and noise realisations;
- the definitions of all 12 experiments (4,740 runs);
- the raw result of every run;
- the scripts that produce every table and figure in Section VII;
- a checker that confirms every number quoted in the paper against those results.

No agent in this study uses a language model. "Agentic" means autonomous, distributed decision-making by software agents (Sec. II-C).

| Scheme | Paper name | Who decides each task | Coordinator-incident load Γ |
|---|---|---|---|
| `CZO`  | Centralized zero-touch orchestration | one global controller (RTT d_c) | 2Λ + N/T_s — Eq. (12) |
| `HORC` | Hierarchical orchestration (simulator-level baseline inspired by Oakestra; not an implementation of it) | regional controllers (RTT d_rc), root on escalation | ≈ (2Λ + N/T_s)/R per region |
| `AFS`  | Agentic fog swarm | ingress agent, k one-hop probes | 0 — Eq. (13) |
| `HZS`  | Hybrid zero-touch swarm (proposed) | ingress agent + globally assigned partners | **2N/T_p**, independent of Λ — Eq. (14) |

---

## 1. Quick start

Requires Python ≥ 3.10. The paper's runs used Python 3.12.

```bash
git clone https://github.com/jasminebug/FOG1.git
cd FOG1
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q tests                               # 13 tests, ~10 s
python analysis/check_paper_numbers.py                  # 377 paper numbers vs. results/, ~1 s
```

A single simulation:

```python
from fogzero import SimConfig, simulate
cfg = SimConfig(N=50, rho=0.7, d_c=0.020, seed=0)      # all times in seconds
for s in ("CZO", "HORC", "AFS", "HZS"):
    r = simulate(s, cfg)
    print(s, round(r["mean_ms"], 2), "ms", round(r["viol_pct"], 2), "% SLA violations")
```

## 2. Reproducing the paper

```bash
python experiments/run_experiments.py --workers 8   # 12 experiments, seeds 0-29, 4,740 runs
python analysis/make_report.py                      # Tables VII-XVII, Fig. 3-8, key_numbers.json
python analysis/check_paper_numbers.py              # verifies every quoted number
python analysis/draw_topologies.py                  # Fig. 1
dot -Tpng -Gdpi=300 docs/diagrams/fig2_hzs_flow.dot -o results/figures/fig2_hzs_flow.png   # Fig. 2
```

Or simply `make all`.

**Determinism.** The simulator is fully deterministic given the seed. Re-running the campaign reproduces `results/raw/*.csv` exactly, row for row. The full campaign takes about 30 min on two cores (measured: 27 min). Re-running it reproduced all 4,740 rows with zero difference. With `--budget <seconds>`, runs are appended to `results/raw/<exp>.csv.partial` and resumed on the next call.

**Experimental accounting (Sec. VII-A).** 158 distinct (scheme, configuration) cells × 30 evaluation seeds = 4,740 runs.

| Experiment | Paper | Swept variable | Schemes | Runs |
|---|---|---|---|---|
| `baseline` | Tables VII, VIII | — | all 4 | 120 |
| `load` | Fig. 3, Sec. VII-C | ρ ∈ {0.3 … 0.9} | all 4 | 840 |
| `scale` | Fig. 4, Sec. VII-C | N ∈ {10, 25, 50, 100, 200} | all 4 | 600 |
| `delay` | Fig. 5, Table IX | d_c ∈ {1 … 40} ms | CZO only¹ | 330 |
| `fanout` | Fig. 6, Table X | k ∈ {1, 2, 3, 4, 6, 8} | AFS, HZS | 360 |
| `failures` | Fig. 7, Table XI | F0–F6 | all 4 | 840 |
| `escalation` | Table XII | E_max ∈ {0, 1, 2}, ρ ∈ {0.7, 0.9} | AFS, HZS | 360 |
| `selection` | Table XIII | first_k random / fixed lowest-ID | AFS, HZS | 240 |
| `stigmergy` | Table XVII | β, aggressive pheromone | AFS | 150 |
| `trace` | Fig. 8, Tables VIII, XIV | Azure-trace-derived workload, ρ ∈ {0.3, 0.5, 0.7, 0.9} | all 4 | 480 |
| `trace_delay` | Sec. VII-D, VII-H | trace-derived workload, d_c ∈ {1, 2, 5, 10, 20} ms | CZO | 150 |
| `hzs_ablation` | Table XV | HZS components and T_p | HZS variants | 270 |
| **Total** | | | | **4,740** |

¹ AFS and HZS do not depend on d_c; their reference runs are reused.

Seeds 0–29 are evaluation seeds. Seeds 100–109 were used only to fix two design constants: the risk threshold r = 1.0 and the residual-capacity partner score. They are never reported.

## 3. Statistics (Sec. VII-A)

- **Means and intervals:** mean ± 95 % CI, x̄ ± t₀.₉₇₅,ₙ₋₁·s/√n with n = 30 (Eq. 23).
- **Tests:** paired two-sided Wilcoxon signed-rank tests, since runs are paired by seed.
- **Effect size:** matched-pairs rank-biserial correlation r ∈ [−1, 1], where negative means HZS is lower.
- **Multiple comparisons:** Holm–Bonferroni correction within each family of simultaneous comparisons:
  - the 12 tests of Table VIII → `results/tables/table_tests.csv`;
  - the 40 sweep comparisons of Table XVI → `results/tables/table_winners.csv` (the full per-configuration table referred to in Sec. VIII-A).
- **Exploratory p-values:** unadjusted p-values are reported alongside and should be read as exploratory.
- **Crossover:** least-squares line through the CZO delay sweep, with a 2,000-sample seed bootstrap for the 95 % CI (Table IX).

## 4. Where each paper item comes from

| Paper item | File |
|---|---|
| Table VII | `results/tables/table_baseline.csv` |
| Table VIII | `results/tables/table_tests.csv` |
| Table IX | `results/tables/table_crossover.csv` |
| Table X | `results/tables/table_fanout.csv` |
| Table XI | `results/tables/table_failures.csv` |
| Table XII | `results/tables/table_escalation.csv` |
| Table XIII | `results/tables/table_selection.csv` |
| Table XIV | `results/tables/table_trace.csv` |
| Table XV | `results/tables/table_hzs_ablation.csv` |
| Table XVI | `results/tables/table_winners.csv` |
| Table XVII | `results/tables/table_stigmergy.csv` |
| Fig. 1, Fig. 2 | `results/figures/fig1_topologies.*`, `fig2_hzs_flow.png` (source in `docs/diagrams/`) |
| Fig. 3–8 | `results/figures/fig3_load.*` … `fig8_trace.*` |
| Numbers quoted in the text | `results/summary/key_numbers.json` |
| Listings 1–3 | `fogzero/simulator.py` (agent evaluation, coordinator slow loop, CZO greedy MCT) |
| Algorithms 1–2 | `fogzero/simulator.py` (slow global loop, fast local loop) |
| Eqs. (12)–(14) | checked by `tests/test_simulator.py` |

All tables are also collected in [`results/tables/tables.md`](results/tables/tables.md).

## 5. Repository layout

```
fogzero/            simulator package
  config.py         SimConfig: every parameter of Table VI (seconds)
  topology.py       ring + forward chord + random chord overlay (one-hop degree 4)
  workload.py       synthetic generator and trace-derived replay
  simulator.py      event-driven engine and the four control planes
experiments/        run_experiments.py: all 12 experiment definitions
analysis/           make_report.py: statistics, tables, figures
                    check_paper_numbers.py: paper numbers vs. results
                    draw_topologies.py: Fig. 1
scripts/            prepare_azure_trace.py, trace_stats.py
data/azure2021/     azure2021_short.csv.gz  (derived from the Azure Functions 2021 trace, CC-BY 4.0)
results/raw/        one CSV row per (experiment, configuration, scheme, seed): 4,740 rows
results/summary/    mean / sd / 95 % CI per configuration, key_numbers.json
results/tables/     every table as CSV plus tables.md
results/figures/    Fig. 1-8 (PNG 300 dpi and PDF)
docs/diagrams/      Graphviz sources of Fig. 1 and Fig. 2
tests/              13 pytest invariants (message formulas, determinism, paired workloads, ...)
```

## 6. Model summary (Sections IV–VI, Table VI)

**Nodes**
- Non-preemptive FIFO servers, each represented by its busy-until time B_j.
- Each node has an unknown capability μ_j ~ U(0.6, 1.4).
- Service times carry multiplicative noise with σ = 0.20.

**Latency**
- One-hop probe RTT d_h = 2 ms. Forwarding costs d_h/2 to a neighbor and d_h to a two-hop node.
- Remote probe RTT and forwarding delay d_r = 6 ms.
- Controller RTT d_c = 20 ms. Regional-controller RTT d_rc = 8 ms, with R = 5 regions.

**CZO**
- Greedy minimum-completion-time assignment over all N nodes, using a book-kept view of the busy-until times.
- The view is resynchronized to ground truth every T_s = 100 ms, and in-flight assignments are re-applied (Sec. VI).

**HORC**
- Regional greedy-MCT controllers.
- A task estimated to finish later than r·D is escalated to the root controller at an extra d_c.

**AFS** — Eqs. (9)–(11); Algorithm 2 with P_i = ∅
- Candidate set C_i = {i} ∪ first_k(N_i). first_k draws k one-hop neighbors uniformly without replacement, topped up from the two-hop set when k > 4.
- Each task costs 2(|C_i| − 1) probe messages.
- EWMA capability estimates (α = 0.2), plus a weak stigmergic bias (β = 0.1, η = 0.1, θ_min = 0.33).
- Bounded escalation, Eq. (21): E_max = 1 round adding k_e = 2 random two-hop nodes.

**HZS** — Eqs. (17)–(21), Algorithms 1–2
- Every T_p = 1 s, each node sends one batched telemetry report, and the coordinator sends one policy message per node. Hence Γ = 2N/T_p.
- Partners: the top q = max(2, ⌊N/4⌋) nodes by residual capacity ψ_j = μ̂_j(1 − û_j), assigned round-robin (Eq. 18).
- Capacity leases (Eq. 19): token buckets with γ_ℓ = 0.8 and depth 2.
- Partner replies are awaited only under deadline risk (Eq. 20, r = 1).

**Failures F1–F6** (Sec. VII-F)
- F1–F3: coordinator outages (2 s, 5 s, and 4 × 0.5 s).
- F4: delayed recovery with a cold restart.
- F5: crash of 10 % of the nodes for 3 s.
- F6: independent 5 % loss of every control message of every scheme.
- A 40 ms timeout is used for failure detection and retransmission.

**Message vs. byte rate.** The simulator counts messages, not bytes. An HZS batched report grows with the number of tasks served in the period (Sec. IV-D).

## 7. Output columns (`results/raw/*.csv`)

| Column | Meaning |
|---|---|
| `mean_ms`, `p95_ms`, `p99_ms` | completion-time statistics of completed tasks |
| `viol_pct` | SLA violations (%); tasks lost to node crashes count as violations |
| `lost_pct` | tasks lost to node crashes (%) |
| `dec_ms`, `fwd_ms`, `wait_ms`, `serv_ms` | decomposition of completion time used in Eq. (15) and Table IX |
| `msgs_per_task` | all control messages divided by the number of tasks |
| `coord_load` | coordinator-incident messages per second, summed over all controllers |
| `coord_load_max` | the same, for the busiest single controller |
| `lambda_real` | realised task rate of the finite-horizon run |
| `esc_pct` | share of tasks that escalated |
| `partner_pct` | share of tasks dispatched to an HZS partner |

## 8. Data

See **[DATASET.md](DATASET.md)**. It covers:
- the synthetic generator;
- the Azure Functions Invocation Trace 2021: source, CC-BY 4.0 licence, SHA-256 of the original archive, preprocessing, and the replay model that produces the trace-derived workload.

The derived workload preserves burstiness, heavy-tailed durations and concentration on a few functions. It does not reproduce the production arrival instants exactly, so the paper calls it trace-derived.

## 9. Licence and citation

The code is released under the MIT licence (`LICENSE`). The derived trace file is released under CC-BY 4.0 and remains © Microsoft.

If you use this repository, please cite the paper (see `CITATION.cff`) and the trace publication: Y. Zhang et al., "Faster and cheaper serverless computing on harvested resources," Proc. ACM SOSP 2021, doi:10.1145/3477132.3483580.
