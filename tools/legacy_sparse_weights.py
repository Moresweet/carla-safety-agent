"""Compatibility entry point for standalone dependency probes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from carla_safety_agent.legacy_sparse_weights import convert_rsck_state
