#!/usr/bin/env python3
"""
Computational Hydrogen Electrode (CHE) Free Energy Profile Calculator

This script demonstrates calculating standard electrochemical free energy profiles
for HER (Hydrogen Evolution Reaction) and 4-electron OER (Oxygen Evolution Reaction)
using Nørskov's CHE framework with zero-point energy and vibrational entropy corrections.
"""

import numpy as np

# Standard gas-phase free energy corrections at 298.15 K, 1 atm (PBE level)
# G_corr = ZPE + \int C_p dT - TS (eV)
GAS_CORRECTIONS = {
    "H2": -0.05,
    "H2O_gas": -0.01,
    "H2O_liq": -0.01 - 0.09,  # Account for liquid vapor pressure (0.035 bar)
    "CO": -0.38,
    "CO2": -0.25,
    "CH4": 0.71,
    "N2": -0.35,
}

# Derived standard Gibbs energy of liquid water splitting (2 H2O -> 2 H2 + O2)
# Delta G = 4.92 eV at 298.15 K. Avoids the 0.4-0.5 eV overbinding error of GGA O2.
DELTA_G_H2O_SPLIT = 4.92


def compute_gas_gibbs(e_dft_dict):
    """
    Calculate corrected Gibbs free energies for gas/liquid reference molecules.

    Parameters
    ----------
    e_dft_dict : dict
        Raw DFT total energies: {'H2': ..., 'H2O': ..., ...}

    Returns
    -------
    dict
        Corrected Gibbs free energies G (eV).
    """
    g_dict = {}
    g_dict["H2"] = e_dft_dict["H2"] + GAS_CORRECTIONS["H2"]
    g_dict["H2O_liq"] = e_dft_dict["H2O"] + GAS_CORRECTIONS["H2O_liq"]

    # Derive G(O2) from liquid water splitting
    g_dict["O2"] = 2.0 * g_dict["H2O_liq"] - 2.0 * g_dict["H2"] + DELTA_G_H2O_SPLIT
    return g_dict


def compute_adsorbate_gibbs(e_dft, zpe, ts_vib, e_solv=0.0):
    """
    Calculate Gibbs free energy of an adsorbed surface state.

    G = E_DFT + ZPE - TS_vib + E_solv
    """
    return e_dft + zpe - ts_vib + e_solv


def calculate_her_profile(e_slab, e_slab_h, g_ref, u_pot=0.0, ph=0.0,
                          zpe_h=0.17, ts_vib_h=0.01):
    """
    Calculate HER free energy profile (Volmer-Heyrovsky / Volmer-Tafel).

    Reaction: * + H+ + e- -> *H -> 1/2 H2 + *
    """
    # Proton-electron pair chemical potential at potential U vs. RHE
    g_h_e = 0.5 * g_ref["H2"] - u_pot

    g_clean = e_slab
    g_h_star = compute_adsorbate_gibbs(e_slab_h, zpe_h, ts_vib_h)

    # Delta G for * -> *H
    delta_g_h = g_h_star - (g_clean + g_h_e)

    # Step free energy changes
    delta_g_volmer = delta_g_h
    delta_g_heyrovsky = -delta_g_h

    # Theoretical overpotential
    eta = max(delta_g_volmer, delta_g_heyrovsky) / 1.0

    return {
        "Delta_G_H*": delta_g_h,
        "Delta_G_Volmer": delta_g_volmer,
        "Delta_G_Heyrovsky": delta_g_heyrovsky,
        "Overpotential_eta": max(0.0, eta),
    }


def calculate_oer_profile(e_slab, e_slab_oh, e_slab_o, e_slab_ooh, g_ref,
                          u_pot=0.0,
                          corrections=None):
    """
    Calculate 4-electron associative OER free energy profile.

    Steps:
      1: * + H2O(l) -> *OH + H+ + e-
      2: *OH -> *O + H+ + e-
      3: *O + H2O(l) -> *OOH + H+ + e-
      4: *OOH -> * + O2(g) + H+ + e-
    """
    if corrections is None:
        # Default ZPE - TS corrections (eV) for standard adsorbates
        corrections = {
            "OH": {"zpe": 0.35, "ts": 0.05, "solv": -0.25},
            "O": {"zpe": 0.07, "ts": 0.03, "solv": 0.0},
            "OOH": {"zpe": 0.40, "ts": 0.08, "solv": -0.15},
        }

    g_clean = e_slab
    g_oh = compute_adsorbate_gibbs(e_slab_oh, corrections["OH"]["zpe"],
                                  corrections["OH"]["ts"], corrections["OH"]["solv"])
    g_o = compute_adsorbate_gibbs(e_slab_o, corrections["O"]["zpe"],
                                 corrections["O"]["ts"], corrections["O"]["solv"])
    g_ooh = compute_adsorbate_gibbs(e_slab_ooh, corrections["OOH"]["zpe"],
                                   corrections["OOH"]["ts"], corrections["OOH"]["solv"])

    g_h2o = g_ref["H2O_liq"]
    g_h_e = 0.5 * g_ref["H2"] - u_pot
    g_o2 = g_ref["O2"]

    # 4 elementary steps Delta G (eV)
    dg1 = (g_oh + g_h_e) - (g_clean + g_h2o)
    dg2 = (g_o + g_h_e) - g_oh
    dg3 = (g_ooh + g_h_e) - (g_o + g_h2o)
    dg4 = (g_clean + g_o2 + g_h_e) - g_ooh

    steps = [dg1, dg2, dg3, dg4]
    limiting_step_idx = int(np.argmax(steps)) + 1
    limiting_potential = max(steps)  # U_L in V
    overpotential = max(0.0, limiting_potential - 1.23)

    # Check scaling relation Delta G(*OOH) - Delta G(*OH)
    dg_oh_relative = g_oh - g_clean - (g_h2o - 0.5 * g_ref["H2"])
    dg_ooh_relative = g_ooh - g_clean - (2.0 * g_h2o - 1.5 * g_ref["H2"])
    scaling_diff = dg_ooh_relative - dg_oh_relative

    return {
        "Delta_G_1 (*OH)": dg1,
        "Delta_G_2 (*O)": dg2,
        "Delta_G_3 (*OOH)": dg3,
        "Delta_G_4 (O2)": dg4,
        "RDS_Step": limiting_step_idx,
        "Limiting_Potential_UL": limiting_potential,
        "Overpotential_eta": overpotential,
        "Scaling_Difference_OOH_OH": scaling_diff,
    }


if __name__ == "__main__":
    # Example Pt(111) mock data (eV)
    e_dft_gas = {"H2": -6.77, "H2O": -14.22}
    g_ref = compute_gas_gibbs(e_dft_gas)

    # Mock slab energies (eV)
    e_clean = -200.00
    e_h = -203.45
    e_oh = -210.80
    e_o = -205.10
    e_ooh = -215.10

    print("=" * 60)
    print("CHE Electrocatalysis Free Energy Profile Analysis")
    print("=" * 60)

    # HER Calculation at U = 0 V
    her_res = calculate_her_profile(e_clean, e_h, g_ref, u_pot=0.0)
    print("\n--- HER Profile (U = 0.0 V vs RHE) ---")
    print(f"Delta G(*H)       : {her_res['Delta_G_H*']:.3f} eV")
    print(f"Theoretical eta   : {her_res['Overpotential_eta']:.3f} V")

    # OER Calculation at U = 0 V and U = 1.23 V
    oer_res_0 = calculate_oer_profile(e_clean, e_oh, e_o, e_ooh, g_ref, u_pot=0.0)
    oer_res_eq = calculate_oer_profile(e_clean, e_oh, e_o, e_ooh, g_ref, u_pot=1.23)

    print("\n--- OER Profile (U = 0.0 V vs RHE) ---")
    print(f"Step 1 (* -> *OH)   : {oer_res_0['Delta_G_1 (*OH)']:.3f} eV")
    print(f"Step 2 (*OH -> *O)  : {oer_res_0['Delta_G_2 (*O)']:.3f} eV")
    print(f"Step 3 (*O -> *OOH) : {oer_res_0['Delta_G_3 (*OOH)']:.3f} eV")
    print(f"Step 4 (*OOH -> O2) : {oer_res_0['Delta_G_4 (O2)']:.3f} eV")
    print(f"RDS Step            : Step {oer_res_0['RDS_Step']}")
    print(f"Theoretical eta_OER : {oer_res_0['Overpotential_eta']:.3f} V")
    print(f"Scaling (OOH - OH)  : {oer_res_0['Scaling_Difference_OOH_OH']:.3f} eV (Ideal ~3.20 eV)")
