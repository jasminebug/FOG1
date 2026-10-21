"""Fog overlay topology: ring + one forward chord + one random chord.

Every node i has the ordered out-neighbour list
    N_i = [i+1, i-1, i+ceil(sqrt(N)), r_i]   (indices mod N)
where r_i is drawn uniformly from the remaining nodes, so the one-hop
degree is four. The two-hop set N_i^(2) is the union of the neighbour lists
of i's neighbours, excluding i and N_i.
"""
from __future__ import annotations
import math
import numpy as np


def build_topology(N: int, rng: np.random.Generator):
    c = max(2, math.ceil(math.sqrt(N)))
    nbrs = []
    for i in range(N):
        base = []
        for j in ((i + 1) % N, (i - 1) % N, (i + c) % N):
            if j != i and j not in base:
                base.append(j)
        pool = [j for j in range(N) if j != i and j not in base]
        if pool:
            base.append(int(pool[rng.integers(len(pool))]))
        nbrs.append(base)
    two_hop = []
    for i in range(N):
        s1 = set(nbrs[i])
        s2 = set()
        for j in nbrs[i]:
            s2.update(nbrs[j])
        s2 -= s1
        s2.discard(i)
        two_hop.append(sorted(s2))
    # hop class: 0 self, 1 one-hop, 2 two-hop, 3 remote
    hop = np.full((N, N), 3, dtype=np.int8)
    for i in range(N):
        hop[i, i] = 0
        for j in two_hop[i]:
            hop[i, j] = 2
        for j in nbrs[i]:
            hop[i, j] = 1
    return nbrs, two_hop, hop


def regions_of(N: int, R: int):
    """Contiguous ring segments used by the hierarchical baseline (H-ORC)."""
    R = max(1, min(R, N))
    return np.array([min(R - 1, i * R // N) for i in range(N)], dtype=np.int32)
