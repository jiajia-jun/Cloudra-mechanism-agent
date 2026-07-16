"""
VASPKIT-Py: A Python-based VASP post-processing toolkit.

Provides:
  - Band structure calculation & plotting
  - Density of states (DOS) analysis
  - Charge density processing
  - Work function extraction
  - STM image simulation (Tersoff-Hamann)
"""

__version__ = "0.1.0"
__author__ = "VASPKIT-Py Team"

from . import bandstructure, chargedensity, constants, core, dos, stm, utils, workfunction

__all__ = [
    "bandstructure",
    "chargedensity",
    "constants",
    "core",
    "dos",
    "stm",
    "utils",
    "workfunction",
]
