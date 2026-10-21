"""Simulation parameters (values: Table VI of the paper; notation: Table IV).

All times are in SECONDS inside the code; the paper reports milliseconds.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
from typing import Optional, Tuple


@dataclass(frozen=True)
class SimConfig:
    # --- substrate -------------------------------------------------------
    N: int = 50                    # number of fog nodes
    mu_low: float = 0.6            # node capability mu_i ~ U(mu_low, mu_high)
    mu_high: float = 1.4
    sigma: float = 0.20            # multiplicative service-time noise (std)

    # --- workload --------------------------------------------------------
    rho: float = 0.7               # offered load (utilisation target)
    mean_work: float = 0.020       # E[w]: mean nominal service time (s)
    deadline: float = 0.100        # SLA deadline D (s)
    horizon: float = 10.0          # simulated horizon H (s)
    workload: str = "synthetic"    # "synthetic" | "azure2021"
    trace_path: Optional[str] = None

    # --- latency model ---------------------------------------------------
    d_c: float = 0.020             # controller round-trip time (s)
    d_h: float = 0.002             # one-hop probe round-trip time (s)
    d_r: float = 0.006             # remote (non-neighbour) probe RTT / forwarding (s)
    d_rc: float = 0.008            # regional-controller RTT for H-ORC (s)
    regions: int = 5               # number of regions for H-ORC

    # --- control-plane periods -------------------------------------------
    T_s: float = 0.100             # CZO / H-ORC state-synchronisation period (s)
    T_p: float = 1.000             # HZS policy period (s)

    # --- swarm parameters ------------------------------------------------
    k: int = 3                     # probe fan-out
    p: int = 2                     # partners per node (HZS)
    alpha: float = 0.20            # EWMA learning rate for service-rate estimates
    eta: float = 0.10              # pheromone (stigmergy) learning rate
    beta: float = 0.10             # stigmergic exponent
    theta_min: float = 0.33        # lower clip of the pheromone value
    kappa: float = 2.0             # load-aversion constant (psi_rule="load_averse")
    psi_rule: str = "residual"     # partner score: residual | load_averse
    lease: bool = True             # capacity-leased partners (token buckets)
    lease_gamma: float = 0.8       # safety factor on leased residual capacity
    lease_burst: float = 2.0       # token-bucket depth
    selection: str = "random"      # first_k rule: random | fixed_id
    lazy_partner: bool = True      # wait for partner replies only when at risk
    risk: float = 1.0              # risk threshold r: consult partners if C_loc > r*D
    esc_max: int = 1               # maximum escalation depth E_max
    k_e: int = 2                   # extra second-hop probes per escalation

    # --- failure injection ------------------------------------------------
    outages: Tuple[Tuple[float, float], ...] = ()   # coordinator unreachable
    cold_restart: bool = False     # coordinator loses its state after an outage
    node_crash_frac: float = 0.0   # fraction of fog nodes that crash
    node_crash_window: Tuple[float, float] = (4.0, 7.0)
    msg_loss: float = 0.0          # independent control-message loss probability
    detect_timeout: float = 0.040  # failure-detection / retransmission timeout (s)

    seed: int = 0

    def with_(self, **kw) -> "SimConfig":
        return replace(self, **kw)

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def arrival_rate(self) -> float:
        """Lambda = rho * N * E[mu] / E[w]."""
        mean_mu = 0.5 * (self.mu_low + self.mu_high)
        return self.rho * self.N * mean_mu / self.mean_work
