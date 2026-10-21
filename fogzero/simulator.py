"""Event-driven simulator for zero-touch fog task dispatching.

Four control planes share every line of code except the decision logic:

  CZO   centralised zero-touch orchestration   (Sec. IV-B, Sec. VI, Listing 3)
  HORC  hierarchical (regional) orchestration  (Sec. VI; simulator-level baseline
                                                inspired by Oakestra, not an implementation of it)
  AFS   agentic fog swarm                      (Sec. IV-C, Eqs. (9)-(11), Listing 1;
                                                Algorithm 2 with P_i = empty)
  HZS   hybrid zero-touch swarm                (Sec. V, Eqs. (17)-(21), Algorithms 1-2)

Workload, topology, node capabilities and per-task service-time noise are
drawn from seed-specific generators that do NOT depend on the scheme, so all
schemes are compared on exactly the same sample path (paired design).

Units: seconds. Nodes are non-preemptive FIFO single servers represented by
their busy-until time B_j.
"""
from __future__ import annotations

import heapq
import math
from bisect import bisect_right

import numpy as np

from .config import SimConfig
from .topology import build_topology, regions_of
from .workload import GENERATORS

SCHEMES = ("CZO", "HORC", "AFS", "HZS")

_ARR, _DEC, _DSP, _CMP, _SYNC, _POL, _CRASH, _RECOV = range(8)


class _Outage:
    """Coordinator availability model."""

    def __init__(self, cfg: SimConfig):
        self.iv = sorted(cfg.outages)
        self.starts = [s for s, _ in self.iv]

    def down(self, t: float):
        """Return the (start, end) outage containing t, or None."""
        k = bisect_right(self.starts, t) - 1
        if k >= 0 and self.iv[k][0] <= t < self.iv[k][1]:
            return self.iv[k]
        return None


def simulate(scheme: str, cfg: SimConfig) -> dict:
    if scheme not in SCHEMES:
        raise ValueError(f"unknown scheme {scheme}")
    ss = np.random.SeedSequence(cfg.seed)
    r_topo, r_work, r_noise, r_dec, r_loss = [np.random.default_rng(s) for s in ss.spawn(5)]

    N = cfg.N
    nbrs, two_hop, hop = build_topology(N, r_topo)
    mu = r_topo.uniform(cfg.mu_low, cfg.mu_high, N)
    crash_set = []
    if cfg.node_crash_frac > 0:
        m = max(1, int(round(cfg.node_crash_frac * N)))
        crash_set = sorted(int(x) for x in r_topo.choice(N, m, replace=False))

    arr, work, src0, dl = GENERATORS[cfg.workload](cfg, r_work)
    n = len(arr)
    noise = np.maximum(0.1, 1.0 + cfg.sigma * r_noise.standard_normal(n))

    fwd_by_hop = np.array([0.0, cfg.d_h / 2, cfg.d_h, cfg.d_r])
    rtt_by_hop = (0.0, cfg.d_h, 2 * cfg.d_h, cfg.d_r)
    FWD = fwd_by_hop[hop]                          # N x N forwarding delay
    hop_l = hop.tolist()
    FWD_l = FWD.tolist()

    outage = _Outage(cfg)
    loss = cfg.msg_loss
    H = cfg.horizon

    # ------------------------------------------------------------------ state
    B = [0.0] * N                                  # true busy-until
    alive = [True] * N
    pending = [[] for _ in range(N)]               # (completion, task) per node
    lost = np.zeros(n, dtype=bool)
    C = np.full(n, np.nan)                          # completion time (rel. arrival)
    dec_delay = np.zeros(n)
    fwd_d = np.zeros(n)
    wait_d = np.zeros(n)
    serv_d = np.zeros(n)
    escalated = np.zeros(n, dtype=np.int8)
    used_partner = np.zeros(n, dtype=bool)
    task_src = src0.copy()

    msgs = 0            # all control messages
    coord_msgs = 0      # messages sent to / from a coordinator
    coord_msgs_max = 0  # for HORC: busiest regional controller

    heap = []
    seq = 0

    def push(t, kind, data):
        nonlocal seq
        heapq.heappush(heap, (t, seq, kind, data))
        seq += 1

    if crash_set:
        push(cfg.node_crash_window[0], _CRASH, None)
        push(cfg.node_crash_window[1], _RECOV, None)

    # ------------------------------------------------- scheme-specific state
    central = scheme in ("CZO", "HORC")
    swarm = scheme in ("AFS", "HZS")

    if central:
        if scheme == "CZO":
            region = np.zeros(N, dtype=np.int32)
            R = 1
            d_ctrl = cfg.d_c
        else:
            R = max(1, min(cfg.regions, N))
            region = regions_of(N, R)
            d_ctrl = cfg.d_rc
        members = [np.where(region == r)[0] for r in range(R)]
        view = np.zeros(N)
        mu_g = np.ones(N)
        inv_mu_g = np.ones(N)
        known_dead = np.zeros(N, dtype=bool)
        comp_buffer = []            # completions not yet reported (j, w, s)
        inflight = {}               # decided but not yet dispatched: tau -> (i, j, t_ready)
        per_ctrl_msgs = [0] * (R + 1)   # last slot: HORC root controller
        all_nodes = np.arange(N)
        # outage affects controller of region 0 only (single-controller failure)
        t = cfg.T_s
        while t < H + 1e-9:
            push(t, _SYNC, None)
            t += cfg.T_s
        ctrl_epoch_reset = []       # restart times for cold restarts
        if cfg.cold_restart:
            ctrl_epoch_reset = [e for _, e in outage.iv]

    if swarm:
        mu_hat = np.ones((N, N))    # agent-local estimates  mu_hat[i][j]
        theta = np.ones((N, N))     # pheromone              theta[i][j]
        use_theta = cfg.beta > 0
        partners = [[] for _ in range(N)]
        if scheme == "HZS":
            mu_g = np.ones(N)
            tele = [[] for _ in range(N)]   # node-side telemetry buffers (w, s)
            lease_rate = [dict() for _ in range(N)]
            lease_tok = [dict() for _ in range(N)]
            lease_t = [dict() for _ in range(N)]
            busy_acc = np.zeros(N)
            last_pol = 0.0
            t = cfg.T_p
            while t < H + 1e-9:
                push(t, _POL, None)
                t += cfg.T_p
        if cfg.selection == "fixed_id":
            ord_nbrs = [sorted(x) for x in nbrs]
        else:
            ord_nbrs = nbrs

    D_rel = dl  # per-task relative deadline

    # --------------------------------------------------------------- helpers
    def reserve(tau, j, t_disp, i):
        """Dispatch task tau (ingress i) to node j at time t_disp."""
        f = FWD_l[i][j]
        t_at = t_disp + f
        dec_delay[tau] = t_disp - arr[tau]
        fwd_d[tau] = f
        if not alive[j]:
            lost[tau] = True
            return
        st = B[j] if B[j] > t_at else t_at
        s = work[tau] / mu[j] * noise[tau]
        fin = st + s
        B[j] = fin
        wait_d[tau] = st - t_at
        serv_d[tau] = s
        C[tau] = fin - arr[tau]
        pending[j].append((fin, tau))
        push(fin, _CMP, (tau, j, i, s))

    def first_k(i, k):
        nb = ord_nbrs[i]
        if cfg.selection == "random":
            if k <= len(nb):
                idx = r_dec.choice(len(nb), k, replace=False)
                out = [nb[x] for x in idx]
            else:
                out = list(nb)
                th = two_hop[i]
                extra = min(k - len(nb), len(th))
                if extra > 0:
                    idx = r_dec.choice(len(th), extra, replace=False)
                    out += [th[x] for x in idx]
            return out
        out = list(nb[:k])
        if k > len(nb):
            out += two_hop[i][: k - len(nb)]
        return out

    def probe(i, cands, t):
        """Send probes; return list of (j, B_j snapshot, rtt, is_partner)."""
        nonlocal msgs
        res = []
        for j, is_p in cands:
            if j == i:
                res.append((j, B[j], 0.0, False))
                continue
            msgs += 2
            if not alive[j]:
                continue
            if loss > 0 and r_loss.random() > (1 - loss) ** 2:
                continue
            res.append((j, B[j], rtt_by_hop[hop_l[i][j]], is_p))
        return res

    def evaluate(tau, i, snap, t_dec):
        """Eq. (9)-(10): return (best j, raw estimate of best, raw min)."""
        a = arr[tau]
        w = work[tau]
        mh = mu_hat[i]
        th = theta[i]
        fr = FWD_l[i]
        beta = cfg.beta
        best, best_cost, best_raw, raw_min = i, math.inf, math.inf, math.inf
        for j, bj, _, _ in snap:
            ta = t_dec + fr[j]
            est = (bj if bj > ta else ta) - a + w / mh[j]
            if est < raw_min:
                raw_min = est
            cost = est / (th[j] ** beta) if use_theta else est
            if cost < best_cost:
                best, best_cost, best_raw = j, cost, est
        return best, best_raw, raw_min

    # --------------------------------------------------------------- events
    ai = 0
    INF = math.inf
    while True:
        t_next_arr = arr[ai] if ai < n else INF
        t_next_ev = heap[0][0] if heap else INF
        if t_next_arr == INF and t_next_ev == INF:
            break
        if t_next_arr <= t_next_ev:
            tau = ai
            ai += 1
            now = t_next_arr
            kind = _ARR
            data = tau
        else:
            now, _, kind, data = heapq.heappop(heap)

        # ---------------------------------------------------------- arrival
        if kind == _ARR:
            i = int(task_src[tau])
            if not alive[i]:                       # ingress fail-over
                live = [j for j in nbrs[i] if alive[j]]
                if live:
                    i = live[0]
                    task_src[tau] = i
                else:
                    lost[tau] = True
                    continue

            if central:
                r = int(region[i])
                t_proc = now + d_ctrl / 2
                o = outage.down(t_proc) if r == 0 else None
                if o is not None:
                    # degraded mode: execute locally after failure detection
                    msgs += 1
                    per_ctrl_msgs[r] += 0
                    t_loc = max(now, o[0] + cfg.detect_timeout)
                    push(t_loc, _DSP, (tau, i, i, 0))
                    continue
                extra = 0.0
                sent = 0
                while True:
                    sent += 1
                    if loss > 0 and r_loss.random() > (1 - loss) ** 2:
                        extra += cfg.detect_timeout
                        if sent > 20:
                            break
                        continue
                    break
                msgs += 2 * sent
                per_ctrl_msgs[r] += 2 * sent
                push(t_proc + extra, _DEC, (tau, i, extra))
                continue

            # ---- swarm schemes: build candidate set C_i (Alg. 2, line 1)
            cands = [(i, False)]
            seen = {i}
            for j in first_k(i, cfg.k):
                if j not in seen:
                    seen.add(j)
                    cands.append((j, False))
            if scheme == "HZS":
                for j in partners[i]:
                    if cfg.lease:
                        # refill token bucket, skip partner if no token left
                        rt = lease_rate[i].get(j, 0.0)
                        tk = lease_tok[i].get(j, 0.0) + rt * (now - lease_t[i].get(j, now))
                        tk = min(tk, cfg.lease_burst)
                        lease_tok[i][j] = tk
                        lease_t[i][j] = now
                        if tk < 1.0:
                            continue
                    if j not in seen:
                        seen.add(j)
                        cands.append((j, True))
            snap = probe(i, cands, now)
            local = [x for x in snap if not x[3]]
            part = [x for x in snap if x[3]]
            t_loc = now + max((x[2] for x in local), default=0.0)
            if part:
                t_all = now + max(max((x[2] for x in part)), t_loc - now)
                use_all = True
                if cfg.lazy_partner and t_all > t_loc:
                    # deadline-aware partner consultation: wait for the
                    # (remote) partner replies only if the best local
                    # candidate puts the task at risk of missing its deadline
                    a = now
                    w = work[tau]
                    mh = mu_hat[i]
                    cmin = INF
                    fr = FWD_l[i]
                    for j, bj, _, _ in local:
                        ta = t_loc + fr[j]
                        est = (bj if bj > ta else ta) - a + w / mh[j]
                        if est < cmin:
                            cmin = est
                    use_all = cmin + (t_all - t_loc) > cfg.risk * D_rel[tau]   # Eq. (20)
                if use_all:
                    push(t_all, _DEC, (tau, i, snap, 0, True))
                else:
                    push(t_loc, _DEC, (tau, i, local, 0, False))
            else:
                push(t_loc, _DEC, (tau, i, snap, 0, False))
            continue

        # ---------------------------------------------------------- decision
        if kind == _DEC:
            if central:
                tau, i, extra = data
                r = int(region[i])
                cand = members[r]
                a = arr[tau]
                t_ready = a + d_ctrl + extra
                fw = FWD[i, cand]
                vv = view[cand]
                est = np.maximum(vv, t_ready + fw) + work[tau] * inv_mu_g[cand]
                if known_dead.any():
                    est = np.where(known_dead[cand], INF, est)
                k_ = int(np.argmin(est))
                j = int(cand[k_])
                if (scheme == "HORC" and R > 1 and est[k_] - a > cfg.risk * D_rel[tau]):
                    # regional controller escalates an at-risk task to the root
                    msgs += 2
                    per_ctrl_msgs[R] += 2
                    t_root = t_ready + cfg.d_c
                    est2 = np.maximum(view, t_root + FWD[i]) + work[tau] * inv_mu_g
                    if known_dead.any():
                        est2 = np.where(known_dead, INF, est2)
                    j2 = int(np.argmin(est2))
                    if est2[j2] < est[k_]:
                        view[j2] = est2[j2]
                        escalated[tau] = 1
                        inflight[tau] = (i, j2, t_root)
                        push(t_root, _DSP, (tau, i, j2, 0))
                        continue
                view[j] = est[k_]
                inflight[tau] = (i, j, t_ready)
                push(t_ready, _DSP, (tau, i, j, 0))
                continue

            tau, i, snap, depth, used_p = data
            j, best_raw, raw_min = evaluate(tau, i, snap, now)
            if (raw_min > D_rel[tau] and depth < cfg.esc_max):   # Eq. (21): bounded escalation
                seen = {x[0] for x in snap}
                pool = [x for x in two_hop[i] if x not in seen]
                if pool:
                    kk = min(cfg.k_e, len(pool))
                    idx = r_dec.choice(len(pool), kk, replace=False)
                    extra_c = [(pool[x], False) for x in idx]
                    new = probe(i, extra_c, now)
                    escalated[tau] = depth + 1
                    push(now + 2 * cfg.d_h, _DEC, (tau, i, snap + new, depth + 1, used_p))
                    continue
            if used_p and j in partners[i] and j != i:
                used_partner[tau] = True
                if cfg.lease and j in lease_tok[i]:
                    lease_tok[i][j] -= 1.0
            reserve(tau, j, now, i)
            continue

        # ---------------------------------------------------------- dispatch
        if kind == _DSP:
            tau, i, j, _ = data
            if central:
                inflight.pop(tau, None)
            reserve(tau, j, now, i)
            continue

        # ---------------------------------------------------------- completion
        if kind == _CMP:
            tau, j, i, s = data
            if lost[tau]:
                continue
            w = work[tau]
            if swarm:
                mh = mu_hat[i]
                mh[j] = (1 - cfg.alpha) * mh[j] + cfg.alpha * (w / s)
                if use_theta:
                    ok = 1.0 if C[tau] <= D_rel[tau] else 0.0
                    v = (1 - cfg.eta) * theta[i, j] + cfg.eta * ok
                    theta[i, j] = min(1.0, max(cfg.theta_min, v))
                if scheme == "HZS":
                    tele[j].append((w, s))
                    busy_acc[j] += s
            else:
                comp_buffer.append((j, w, s))
            continue

        # ---------------------------------------------------------- sync
        if kind == _SYNC:
            # region-0 controller may be down; others always up
            o = outage.down(now)
            for r in range(R):
                if r == 0 and o is not None:
                    continue
                mem = members[r]
                msgs += len(mem)
                per_ctrl_msgs[r] += len(mem)
            if ctrl_epoch_reset:
                for te in ctrl_epoch_reset:
                    if now - cfg.T_s < te <= now:
                        # cold restart of controller 0: lose view and estimates
                        m0 = members[0]
                        view[m0] = 0.0
                        mu_g[m0] = 1.0
                        inv_mu_g[m0] = 1.0
                        known_dead[m0] = False
                        comp_buffer = [x for x in comp_buffer if region[x[0]] != 0]
            keep = []
            a_ = cfg.alpha
            for (j, w, s) in comp_buffer:
                if o is not None and region[j] == 0:
                    keep.append((j, w, s))
                    continue
                if loss > 0 and r_loss.random() < loss:
                    continue
                mu_g[j] = (1 - a_) * mu_g[j] + a_ * (w / s)
            comp_buffer = keep
            upd = np.ones(N, dtype=bool)
            if o is not None:
                upd[members[0]] = False
            if loss > 0:
                upd &= r_loss.random(N) >= loss
            Barr = np.fromiter(B, float, N)
            view[upd] = np.maximum(Barr[upd], now)
            # re-apply the controller's own in-flight assignments (bookkeeping)
            for tq, (iq, jq, trq) in inflight.items():
                if upd[jq]:
                    ta = trq + FWD_l[iq][jq]
                    view[jq] = (view[jq] if view[jq] > ta else ta) + work[tq] * inv_mu_g[jq]
            inv_mu_g[:] = 1.0 / np.maximum(mu_g, 1e-3)
            al = np.fromiter(alive, bool, N)
            known_dead[upd] = ~al[upd]
            continue

        # ---------------------------------------------------------- policy
        if kind == _POL:
            o = outage.down(now)
            if o is not None:
                last_pol = now
                continue
            if cfg.cold_restart:
                for te in [e for _, e in outage.iv]:
                    if now - cfg.T_p < te <= now:
                        mu_g[:] = 1.0
            win = max(now - last_pol, 1e-6)
            a_ = cfg.alpha
            reported = np.zeros(N, dtype=bool)
            busy_rep = np.zeros(N)
            for j in range(N):
                msgs += 1
                coord_msgs += 1
                if not alive[j]:
                    continue
                if loss > 0 and r_loss.random() < loss:
                    continue                      # batch lost; buffer kept
                reported[j] = True
                g = mu_g[j]
                for (w, s) in tele[j]:
                    g = (1 - a_) * g + a_ * (w / s)
                mu_g[j] = g
                tele[j] = []
                busy_rep[j] = busy_acc[j]
                busy_acc[j] = 0.0
            u = busy_rep / win
            u = np.minimum(u, 1.0)
            if cfg.psi_rule == "residual":
                psi = mu_g * (1.0 - u)                  # Eq. (17): residual capacity
            else:
                psi = mu_g / (1.0 + cfg.kappa * u)      # load-averse score (v1)
            psi[~reported] = -INF                       # silent nodes excluded
            q = max(2, N // 4)
            top = np.argsort(-psi, kind="stable")[:q]
            top = [int(x) for x in top if psi[x] > -INF]
            qq = len(top)
            for i in range(N):
                msgs += 1
                coord_msgs += 1
                if loss > 0 and r_loss.random() < loss:
                    continue                      # broadcast lost: keep old
                if qq >= 1 and cfg.p > 0:
                    P = []
                    for m in range(cfg.p):
                        c_ = top[(2 * i + m) % qq]  # Eq. (18): P_i = {top[2i mod q], top[(2i+1) mod q]}
                        if c_ != i and c_ not in P:
                            P.append(c_)
                    partners[i] = P
                else:
                    partners[i] = []
                mu_hat[i, :] = mu_g
            if cfg.lease:
                # Eq. (19) capacity leases: residual capacity of partner j (tasks/s)
                # is split evenly among the agents that hold j as a partner
                holders = {}
                for i in range(N):
                    for j in partners[i]:
                        holders[j] = holders.get(j, 0) + 1
                for i in range(N):
                    for j in partners[i]:
                        cap = cfg.lease_gamma * mu_g[j] * max(0.0, 1.0 - u[j]) / cfg.mean_work
                        lease_rate[i][j] = cap / holders[j]
                        lease_tok[i][j] = min(lease_tok[i].get(j, cfg.lease_burst), cfg.lease_burst)
                        lease_t[i][j] = now
            last_pol = now
            continue

        # ---------------------------------------------------------- crashes
        if kind == _CRASH:
            for j in crash_set:
                alive[j] = False
                for (fin, tau) in pending[j]:
                    if fin > now:
                        lost[tau] = True
                pending[j] = []
                B[j] = now
            continue
        if kind == _RECOV:
            for j in crash_set:
                alive[j] = True
                B[j] = max(B[j], now)
            continue

    # ------------------------------------------------------------- metrics
    done = ~lost & ~np.isnan(C)
    viol = lost | np.isnan(C) | (np.nan_to_num(C, nan=np.inf) > D_rel)
    Cd = C[done]
    lam_real = n / H
    if central:
        coord_msgs = sum(per_ctrl_msgs)
        coord_msgs_max = max(per_ctrl_msgs)
    else:
        coord_msgs_max = coord_msgs
    out = dict(
        scheme=scheme, seed=cfg.seed, tasks=int(n),
        mean_ms=float(Cd.mean() * 1e3) if Cd.size else float("nan"),
        p95_ms=float(np.percentile(Cd, 95) * 1e3) if Cd.size else float("nan"),
        p99_ms=float(np.percentile(Cd, 99) * 1e3) if Cd.size else float("nan"),
        viol_pct=float(viol.mean() * 100),
        lost_pct=float(lost.mean() * 100),
        dec_ms=float(dec_delay[done].mean() * 1e3) if Cd.size else float("nan"),
        fwd_ms=float(fwd_d[done].mean() * 1e3) if Cd.size else float("nan"),
        wait_ms=float(wait_d[done].mean() * 1e3) if Cd.size else float("nan"),
        serv_ms=float(serv_d[done].mean() * 1e3) if Cd.size else float("nan"),
        msgs_per_task=msgs / max(n, 1),
        coord_load=coord_msgs / H,
        coord_load_max=coord_msgs_max / H,
        lambda_real=lam_real,
        esc_pct=float((escalated > 0).mean() * 100),
        partner_pct=float(used_partner.mean() * 100),
    )
    return out
