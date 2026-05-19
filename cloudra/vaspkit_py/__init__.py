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

from . import constants
from . import core
from . import bandstructure
from . import dos
from . import chargedensity
from . import workfunction
from . import stm
from . import utils
