# Datasets used in this repository

Two workloads drive the simulator. Both are fully reproducible from this repository.

## 1. Synthetic workload (generated, no download)

| Item | Model |
|---|---|
| Arrivals | Homogeneous Poisson process, rate Λ = ρ·N·E[μ]/E[w] (≈ 1,750 tasks/s for N = 50, ρ = 0.7) |
| Work | Exponential, mean E[w] = 20 ms of nominal service time |
| Ingress node | Uniform over the N fog nodes |
| Node capability | μ_i ~ U(0.6, 1.4), drawn once per run, never revealed to any scheme |
| Service noise | Multiplicative Gaussian, σ = 0.20 (floored at 0.1) |
| Deadline | D = 100 ms |
| Randomness | `numpy.random.SeedSequence(seed)` spawned into 5 independent PCG64 streams (topology, workload, noise, decisions, message loss). Seeds 0–29 are evaluation seeds. |

Because the workload, topology and noise streams do not depend on the scheme, all four schemes run on the *same sample path* for a given seed, which is why paired statistical tests are used.

## 2. Azure Functions Invocation Trace 2021 and the trace-derived workload

| Field | Value |
|---|---|
| Publisher | Microsoft Azure — *Azure Public Dataset* |
| Source repository | https://github.com/Azure/AzurePublicDataset |
| Original file | `data/AzureFunctionsInvocationTraceForTwoWeeksJan2021.rar` (18.4 MB) |
| SHA-256 of the .rar | `8bb5d1c82e89e467062b6582996232df24edfebadbaf3287a8c985ca178ba92d` |
| Description page | `AzureFunctionsInvocationTrace2021.md` in the same repository |
| Content | 1,980,951 function invocations from 119 applications / 424 functions, two weeks starting 2021-01-31 |
| Schema | `app` (hashed), `func` (hashed), `end_timestamp` (s), `duration` (s) |
| Licence | Creative Commons Attribution 4.0 International (CC-BY 4.0) |
| Required citation | Y. Zhang, Í. Goiri, G. I. Chaudhry, R. Fonseca, S. Elnikety, C. Delimitrou, R. Bianchini, "Faster and cheaper serverless computing on harvested resources," *Proc. ACM SOSP*, 2021, doi:10.1145/3477132.3483580 |

### Preprocessing (`scripts/prepare_azure_trace.py`)

1. `arrival_s = end_timestamp − duration` (clipped at 0, rounded to 0.1 ms).
2. Keep invocations with `duration ≤ 1 s` (short-task regime, 87.4 % of invocations).
3. `func_key = CRC32("app:func")` (identifiers stay anonymous).
4. Result: `data/azure2021/azure2021_short.csv.gz` (9.8 MB), columns `arrival_s, duration_s, func_key`.
   SHA-256 of the derived file: `c8cb42679178872f3f5f3f0ddfd855799fb01f7787f8045082c87c0daf3dc617`.

Descriptive statistics (`python scripts/trace_stats.py`):

| Statistic | Value |
|---|---|
| Invocations kept | 1,731,643 |
| Distinct functions | 336 |
| Time span | 14.0 days (mean 1.43 invocations/s) |
| Duration mean / median | 125.8 ms / 15.0 ms |
| Duration CV | 1.70 (heavy-tailed; exponential would be 1.0) |
| Duration p90 / p99 | 398 ms / 920 ms |
| Traffic share of top-1 / top-10 functions | 30.9 % / 79.9 % |

### Replay model (`fogzero/workload.py::azure2021`)

The trace is far sparser (1.4 inv/s) than a loaded fog domain (≈1,750 tasks/s), so it is replayed as a
**multi-tenant superposition**:

* n = Λ·H invocations are split over S = 16 tenant streams; each stream is a contiguous trace segment cut at a
  seed-dependent offset, time-scaled onto [0, H) — its burstiness is preserved — and the streams are superposed.
* Durations are rescaled so that their mean equals 20 ms; the heavy-tailed shape is preserved.
* Spatial locality: each (tenant, app, function) is hashed to a home arc of ⌈0.2·N⌉ consecutive nodes; each
  invocation enters at a uniformly chosen node of that arc.
* Per-task deadline: max(100 ms, 3·w).

Because of time scaling, segment superposition, duration rescaling and the synthetic spatial mapping, the replay
preserves burstiness, heavy-tailed durations and concentration on a few functions, but **not** the exact production
arrival instants. The paper therefore calls it a *trace-derived* workload rather than a production workload.

Resulting replay properties (30 seeds): peak/mean arrivals in 100-ms bins = 2.07; index of dispersion = 9.78
(Poisson = 1); hottest ingress node receives 1.70× the average load.

### Rebuilding the file from scratch

```bash
git clone --depth 1 https://github.com/Azure/AzurePublicDataset
pip install unrar-cffi
python scripts/prepare_azure_trace.py --rar AzurePublicDataset/data/AzureFunctionsInvocationTraceForTwoWeeksJan2021.rar
```

## 3. Other public traces (not used, loader-compatible)

Any CSV with columns `arrival_s, duration_s, func_key` can be used via `SimConfig(workload="azure2021", trace_path=...)`.
Candidates: Azure Functions 2019 trace (Shahrad et al., USENIX ATC 2020, https://github.com/Azure/AzurePublicDataset),
Google cluster-usage traces (https://github.com/google/cluster-data), Alibaba cluster traces
(https://github.com/alibaba/clusterdata). They are **not** redistributed here.
