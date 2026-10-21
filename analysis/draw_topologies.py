#!/usr/bin/env python3
"""Fig. 1: control-plane topologies of CZO, AFS and HZS."""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
plt.rcParams.update({"font.family": "serif", "font.size": 7})
fig, axs = plt.subplots(1, 3, figsize=(3.5, 1.45))
n = 8
ang = np.linspace(0, 2 * np.pi, n, endpoint=False) + np.pi / 2
P = np.c_[np.cos(ang), np.sin(ang)]
ring = [(i, (i + 1) % n) for i in range(n)] + [(0, 3), (2, 6), (5, 1)]
cols = {"CZO": "#1f4e79", "AFS": "#c55a11", "HZS": "#2e7d32"}
titles = ["(a) CZO", "(b) AFS", "(c) HZS"]
for ax, key, t in zip(axs, ["CZO", "AFS", "HZS"], titles):
    c = cols[key]
    if key == "CZO":
        for p in P:
            ax.annotate("", p * 0.82, (0, 0), arrowprops=dict(arrowstyle="<->", color=c, lw=0.7))
        ax.add_patch(plt.Circle((0, 0), 0.22, color=c))
        ax.text(0, 0, "C", color="w", ha="center", va="center", fontsize=7, weight="bold")
    else:
        for a, b in ring:
            ax.plot(*P[[a, b]].T, color=c, lw=0.8)
        if key == "HZS":
            ax.add_patch(plt.Circle((0, 0), 0.22, color=c))
            ax.text(0, 0, "K", color="w", ha="center", va="center", fontsize=7, weight="bold")
            for i in (1, 4, 6):
                ax.annotate("", P[i] * 0.82, (0, 0), arrowprops=dict(arrowstyle="->", color="grey", lw=0.6, ls="--"))
            ax.annotate("", P[7] * 0.9, P[3] * 0.9, arrowprops=dict(arrowstyle="->", color=c, lw=0.8, ls=":"))
            ax.text(0.05, -1.55, "dashed: slow loop (T_p)\ndotted: partner", ha="center", fontsize=5.5)
    for p in P:
        ax.add_patch(plt.Circle(p, 0.13, facecolor="white", edgecolor=c, lw=0.9))
    ax.set_title(t, fontsize=7.5, color=c)
    ax.set_xlim(-1.35, 1.35); ax.set_ylim(-1.8, 1.3)
    ax.set_aspect("equal"); ax.axis("off")
fig.tight_layout(pad=0.2)
for ext in ("png", "pdf"):
    fig.savefig(os.path.join(ROOT, "results", "figures", f"fig1_topologies.{ext}"), dpi=300, bbox_inches="tight")
