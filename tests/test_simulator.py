"""Sanity and invariant tests: `python -m pytest -q`."""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fogzero import SimConfig, simulate, SCHEMES  # noqa: E402
from fogzero.topology import build_topology  # noqa: E402

FAST = SimConfig(horizon=3.0)


@pytest.mark.parametrize("scheme", SCHEMES)
def test_runs_and_is_deterministic(scheme):
    a = simulate(scheme, FAST.with_(seed=7))
    b = simulate(scheme, FAST.with_(seed=7))
    assert a == b
    assert 0 <= a["viol_pct"] <= 100
    assert a["mean_ms"] > 0


def test_same_workload_for_all_schemes():
    n = {simulate(s, FAST)["tasks"] for s in SCHEMES}
    assert len(n) == 1


def test_topology_degree_four():
    nb, th, hop = build_topology(50, np.random.default_rng(0))
    assert all(len(x) == 4 for x in nb)
    assert all(i not in nb[i] for i in range(50))
    assert all(hop[i, i] == 0 for i in range(50))


def test_czo_coordinator_load_formula():
    """Eq. (12): Gamma_CZO = 2*Lambda + N/T_s."""
    r = simulate("CZO", FAST)
    expected = 2 * r["lambda_real"] + FAST.N / FAST.T_s
    assert abs(r["coord_load"] - expected) / expected < 0.02


def test_hzs_coordinator_load_independent_of_lambda():
    """Eq. (14): Gamma_HZS = 2N/T_p, independent of the task rate."""
    lo = simulate("HZS", FAST.with_(rho=0.3))
    hi = simulate("HZS", FAST.with_(rho=0.9))
    expected = 2 * FAST.N / FAST.T_p * int(FAST.horizon / FAST.T_p) / FAST.horizon
    assert lo["coord_load"] == pytest.approx(expected)
    assert hi["coord_load"] == pytest.approx(expected)


def test_afs_probe_cost_is_2k_without_escalation():
    """Alg. 2 line 2: 2(|C_i|-1) messages, i.e. 2k when i is not re-probed."""
    r = simulate("AFS", FAST.with_(esc_max=0))
    assert r["msgs_per_task"] == pytest.approx(2 * FAST.k)
    assert r["coord_load"] == 0


def test_escalation_bounded():
    r0 = simulate("AFS", FAST.with_(rho=0.9, esc_max=0))
    r1 = simulate("AFS", FAST.with_(rho=0.9, esc_max=1))
    assert r0["esc_pct"] == 0
    extra = r1["msgs_per_task"] - 2 * FAST.k
    assert extra <= 2 * FAST.k_e * r1["esc_pct"] / 100 + 1e-9


def test_decision_latency_ordering():
    czo = simulate("CZO", FAST)
    afs = simulate("AFS", FAST)
    assert czo["dec_ms"] == pytest.approx(FAST.d_c * 1e3)
    assert afs["dec_ms"] < czo["dec_ms"]


def test_outage_hurts_czo_not_afs():
    base = simulate("CZO", FAST)
    out = simulate("CZO", FAST.with_(outages=((1.0, 2.0),)))
    assert out["viol_pct"] >= base["viol_pct"]
    a0 = simulate("AFS", FAST)
    a1 = simulate("AFS", FAST.with_(outages=((1.0, 2.0),)))
    assert a0 == a1


def test_trace_workload_loads():
    p = os.path.join(ROOT, "data", "azure2021", "azure2021_short.csv.gz")
    if not os.path.exists(p):
        pytest.skip("trace not present")
    r = simulate("HZS", FAST.with_(workload="azure2021", trace_path=p))
    assert r["tasks"] > 1000
