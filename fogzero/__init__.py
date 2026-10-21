"""FogZero-HZS: centralised orchestration vs. agentic swarm vs. hybrid
zero-touch swarm (HZS) for deadline-constrained fog task dispatching.

Reference implementation accompanying the paper
"Centralized Orchestration versus Decentralized Agentic Swarms for
Zero-Touch Fog Computing: A Formal Analysis, Empirical Evaluation, and
Hybrid Architecture".
"""
from .config import SimConfig
from .simulator import simulate, SCHEMES

__all__ = ["SimConfig", "simulate", "SCHEMES"]
__version__ = "1.0.0"
