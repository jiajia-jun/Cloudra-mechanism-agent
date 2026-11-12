# Heterogeneous Catalysis, CHE Electrocatalysis & Surface Transition States

---

## 1. Heterogeneous Surface Reaction Mechanism Archetypes

Surface catalytic reactions proceed via three foundational kinetic/thermodynamic paradigms:

```
1. Langmuir-Hinshelwood (LH)      2. Eley-Rideal (ER)           3. Mars-van Krevelen (MvK)
   A(g) + * <-> A*                   A* + B(g) -> AB* + *          A(g) + O_lat -> AO(g) + V_O
   B(g) + * <-> B*                                                 V_O + 1/2 O2(g) -> O_lat
   A* + B* -> AB* + * -> AB(g) + 2*
```

### 1.1 Langmuir-Hinshelwood (LH) Mechanism (Co-Adsorption Model)
*   **Physical Picture**: All reacting species adsorb onto adjacent surface active sites ($A^*$ and $B^*$). They diffuse on the surface, cross a transition state to form an adsorbed product complex $AB^*$, and subsequently desorb.
*   **Elementary Steps**:
    $$\begin{aligned}
    A(\text{g}) + * &\xrightleftharpoons[k_{-1}]{k_1} A^* \quad (K_A = k_1 / k_{-1}) \\
    B(\text{g}) + * &\xrightleftharpoons[k_{-2}]{k_2} B^* \quad (K_B = k_2 / k_{-2}) \\
    A^* + B^* &\xrightarrow{k_3} AB^* + * \quad (\text{Rate-Determining Step, RDS}) \\
    AB^* &\xrightleftharpoons[k_{-4}]{k_4} AB(\text{g}) + *
    \end{aligned}$$
*   **Rate Law (under quasi-equilibrium adsorption)**:
    $$r_{\text{LH}} = k_3 \theta_A \theta_B = \frac{k_3 K_A K_B P_A P_B}{(1 + K_A P_A + K_B P_B + K_{AB} P_{AB})^2}$$
*   **Signature**: At very high $P_A$, site poisoning occurs ($\theta_A \to 1, \theta_B \to 0$), causing the reaction rate to decrease with increasing $P_A$ (self-inhibition). Examples: CO oxidation on transition metals at low $O_2$ pressure, alkene hydrogenation.

---

### 1.2 Eley-Rideal (ER) Mechanism (Direct Collision Model)
*   **Physical Picture**: One reactant $A$ adsorbs onto a site ($A^*$), while a second gas-phase reactant $B(\text{g})$ collides directly with $A^*$ from the gas phase (or a physisorbed precursor state) to form product $AB$ without requiring chemical adsorption of $B$.
*   **Elementary Steps**:
    $$\begin{aligned}
    A(\text{g}) + * &\xrightleftharpoons[k_{-1}]{k_1} A^* \\
    A^* + B(\text{g}) &\xrightarrow{k_{\text{ER}}} AB(\text{g}) + *
    \end{aligned}$$
*   **Rate Law**:
    $$r_{\text{ER}} = k_{\text{ER}} \theta_A P_B = \frac{k_{\text{ER}} K_A P_A P_B}{1 + K_A P_A + K_{AB} P_{AB}}$$
*   **Signature**: Strictly first-order in $P_B$; does not suffer from dual-site competitive poisoning at high coverage. Examples: radical surface recombination, plasma-assisted catalysis, selective hydrogenation of adsorbed species.

---

### 1.3 Mars-van Krevelen (MvK) Mechanism (Lattice Oxygen / Redox Model)
*   **Physical Picture**: The reducible metal oxide catalyst ($CeO_2, TiO_2, V_2O_5, RuO_2$) acts as a chemical reactant: its **lattice oxygen ($O_{\text{lat}}$)** directly oxidizes the substrate, leaving a **surface oxygen vacancy ($V_O^*$)**. Gaseous oxidant ($O_2$ or $H_2O$) then dissociatively refills the vacancy.
*   **Elementary Steps**:
    $$\begin{aligned}
    \text{Reduction:} \quad & R(\text{g}) + O_{\text{lat}}^* \xrightarrow{k_{\text{red}}} RO(\text{g}) + V_O^* \\
    \text{Reoxidation:} \quad & V_O^* + \frac{1}{2} O_2(\text{g}) \xrightarrow{k_{\text{ox}}} O_{\text{lat}}^*
    \end{aligned}$$
*   **Key DFT Metric**:
    *   **Oxygen Vacancy Formation Energy ($E_{\text{vac}}$)**:
        $$E_{\text{vac}} = E(\text{Slab}_{V_O}) + \frac{1}{2} E(O_2) - E(\text{Slab}_{\text{pristine}})$$
        Lower $E_{\text{vac}}$ facilitates substrate oxidation, but excessively low $E_{\text{vac}}$ hinders surface reoxidation. Examples: CO oxidation and WGS on $CeO_2$, selective alkane oxidation on $V_2O_5$, lattice oxygen mechanism (LOM) in OER.

---

## 2. Computational Hydrogen Electrode (CHE) Model & Electrocatalysis

### 2.1 CHE Theory & Free Energy Components

Developed by Nørskov and co-workers, the Computational Hydrogen Electrode (CHE) defines the Standard Hydrogen Electrode (SHE) at standard conditions ($T = 298.15\text{ K}, P_{\text{H}_2} = 101.325\text{ kPa}, a_{\text{H}^+} = 1, U_{\text{SHE}} = 0\text{ V}$):
$$\frac{1}{2} \text{H}_2(\text{g}) \xrightleftharpoons{} \text{H}^+ + \text{e}^-, \quad \mu(\text{H}^+ + \text{e}^-) = \frac{1}{2} \mu(\text{H}_2(\text{g}))$$

For an electrochemical elementary step $A^* + \text{H}^+ + \text{e}^- \to AH^*$, the Gibbs free energy change as a function of potential $U$ (vs. RHE/SHE) and pH is:
$$\Delta G(U, \text{pH}) = \Delta E_{\text{DFT}} + \Delta \text{ZPE} - T \Delta S - n e U + \Delta G_{\text{pH}} + \Delta G_{\text{field}} + \Delta G_{\text{solv}}$$

where:
1.  $\Delta E_{\text{DFT}} = E_{\text{DFT}}(AH^*) - E_{\text{DFT}}(A^*) - \frac{1}{2} E_{\text{DFT}}(\text{H}_2(\text{g}))$.
2.  $\Delta \text{ZPE} = \sum_i \frac{1}{2} h \nu_i$ (calculated via partial Hessian vibrational analysis on adsorbate modes).
3.  $T \Delta S$: gas molecules retain full translational, rotational, and vibrational entropy (NIST-JANAF tables). Adsorbates lose translation/rotation, modeled as harmonic oscillators ($S_{\text{vib}}$).
4.  $- n e U$: shifts the chemical potential of transferred electrons by $-neU$.
5.  $\Delta G_{\text{pH}} = - k_B T \ln a_{\text{H}^+} = k_B T \ln 10 \times \text{pH} \approx 0.0592 \times \text{pH}\text{ eV}$ (if potential is referenced to RHE, $U_{\text{RHE}} = U_{\text{SHE}} - 0.0592 \times \text{pH}$, the pH correction is implicitly absorbed).
6.  $\Delta G_{\text{solv}}$: explicit or implicit solvation stabilization (e.g. $*OH$ stabilized by $\sim 0.25 \sim 0.30\text{ eV}$, $*OOH$ by $\sim 0.15 \sim 0.25\text{ eV}$, $*O$ by $< 0.05\text{ eV}$).

---

### 2.2 Standard Thermodynamic Reference Corrections (PBE Level, 298.15 K)

| Molecule | $\text{ZPE}\text{ (eV)}$ | $\int C_p dT\text{ (eV)}$ | $-TS\text{ (eV)}$ | $G_{\text{corr}} = G - E_{\text{DFT}}\text{ (eV)}$ | Exp. $\Delta G_f^\circ\text{ (eV)}$ |
| :--- | :--- | :--- | :--- | :--- | :--- |
| $\text{H}_2(\text{g})$ | 0.27 | 0.09 | -0.41 | **-0.05** | 0.00 |
| $\text{H}_2\text{O}(\text{g})$ | 0.56 | 0.10 | -0.67 | **-0.01** | -2.37 (liquid: -2.46) |
| $\text{CO}(\text{g})$ | 0.14 | 0.09 | -0.61 | **-0.38** | -1.42 |
| $\text{CO}_2(\text{g})$ | 0.31 | 0.10 | -0.66 | **-0.25** | -4.09 |
| $\text{CH}_4(\text{g})$ | 1.19 | 0.10 | -0.58 | **+0.71** | -0.53 |
| $\text{N}_2(\text{g})$ | 0.15 | 0.09 | -0.59 | **-0.35** | 0.00 |
| $\text{O}_2(\text{g})$* | 0.10 | 0.09 | -0.63 | **-0.44** | 0.00 |

> **Critical Gas-Phase DFT Error Corrections**:
> 1. **$\text{O}_2$ Triplet Ground State Artifact**:
>    Standard GGA (PBE/RPBE) severely overbinds triplet $\text{O}_2$ by $\sim 0.4 \sim 0.5\text{ eV}$. **Never use computed gas-phase $\text{O}_2$ DFT energy directly.** Derive $G(\text{O}_2)$ from liquid water splitting ($\Delta G = 4.92\text{ eV}$ for $2\text{H}_2\text{O}(\text{l}) \to 2\text{H}_2(\text{g}) + \text{O}_2(\text{g})$):
>    $$G(\text{O}_2(\text{g})) = 2 G(\text{H}_2\text{O}(\text{l})) - 2 G(\text{H}_2(\text{g})) + 4.92\text{ eV}$$
>    where $G(\text{H}_2\text{O}(\text{l})) = G(\text{H}_2\text{O}(\text{g})) - 0.09\text{ eV}$ (accounting for vapor pressure at 298 K).
> 2. **$\text{CO}$ and $\text{CO}_2$ Gas-Phase Corrections**:
>    GGA functionals underestimate $C\equiv O$ triple bond strength and overestimate $\text{CO}$ binding. In CO2RR studies, standard empirical corrections are: $E(\text{CO}(\text{g})) \leftarrow E_{\text{DFT}}(\text{CO}) - 0.33\text{ eV}$; $E(\text{CO}_2(\text{g})) \leftarrow E_{\text{DFT}}(\text{CO}_2) + 0.45\text{ eV}$.

---

### 2.3 Reaction Pathways, Scaling Relations & Overpotentials

#### A. Hydrogen Evolution Reaction (HER)
*   **Overall Reaction**: $2\text{H}^+ + 2\text{e}^- \to \text{H}_2(\text{g})$ ($U^\circ = 0.00\text{ V vs. RHE}$)
*   **Elementary Steps**:
    1.  **Volmer Step**: $* + \text{H}^+ + \text{e}^- \to \text{H}^* \quad (\Delta G_1 = \Delta G_{\text{H}^*})$
    2.  **Heyrovsky Step**: $\text{H}^* + \text{H}^+ + \text{e}^- \to * + \text{H}_2(\text{g}) \quad (\Delta G_2 = -\Delta G_{\text{H}^*})$
    3.  **Tafel Step**: $2\text{H}^* \to 2* + \text{H}_2(\text{g}) \quad (\Delta G_3 = -2\Delta G_{\text{H}^*})$
*   **Descriptor & Volcano Optimum**: Single descriptor $\Delta G_{\text{H}^*}$.
    *   $\Delta G_{\text{H}^*} > 0$ (weak binding, e.g. Au, Ag, Cu): Volmer step is rate-limiting, $\eta = \Delta G_{\text{H}^*} / e$.
    *   $\Delta G_{\text{H}^*} < 0$ (strong binding, e.g. Ni, Co, W, Mo): Heyrovsky/Tafel desorption is rate-limiting, $\eta = -\Delta G_{\text{H}^*} / e$.
    *   **Volcano Apex**: $\Delta G_{\text{H}^*} \approx 0\text{ eV}$ (Pt has $\Delta G_{\text{H}^*} \approx -0.09\text{ eV}$, near optimal).

---

#### B. Oxygen Evolution Reaction (OER) & Oxygen Reduction Reaction (ORR)
*   **Overall Reaction**: $2\text{H}_2\text{O} \xrightleftharpoons{} \text{O}_2 + 4\text{H}^+ + 4\text{e}^-$ ($U^\circ = 1.23\text{ V vs. RHE}$)
*   **4-Electron Associative Mechanism (OER)**:
    $$\begin{aligned}
    \text{Step 1: } & * + \text{H}_2\text{O}(\text{l}) \to *\text{OH} + \text{H}^+ + \text{e}^- & \Delta G_1 = G(*\text{OH}) - G(*) - G(\text{H}_2\text{O}) + \frac{1}{2} G(\text{H}_2) - eU \\
    \text{Step 2: } & *\text{OH} \to *\text{O} + \text{H}^+ + \text{e}^- & \Delta G_2 = G(*\text{O}) - G(*\text{OH}) + \frac{1}{2} G(\text{H}_2) - eU \\
    \text{Step 3: } & *\text{O} + \text{H}_2\text{O}(\text{l}) \to *\text{OOH} + \text{H}^+ + \text{e}^- & \Delta G_3 = G(*\text{OOH}) - G(*\text{O}) - G(\text{H}_2\text{O}) + \frac{1}{2} G(\text{H}_2) - eU \\
    \text{Step 4: } & *\text{OOH} \to * + \text{O}_2(\text{g}) + \text{H}^+ + \text{e}^- & \Delta G_4 = 4.92\text{ eV} - (\Delta G_1 + \Delta G_2 + \Delta G_3) - eU
    \end{aligned}$$
*   **Universal Scaling Relation**:
    Because both $*\text{OH}$ and $*\text{OOH}$ bind to the catalyst through a single oxygen atom, their adsorption free energies are linearly correlated across metals, oxides, and single-atom catalysts:
    $$\Delta G_{*\text{OOH}} = \Delta G_{*\text{OH}} + 3.20\ (\pm 0.20)\text{ eV}$$
*   **Theoretical Minimum Overpotential Limit**:
    In an ideal catalyst, all steps share $\Delta G_i = 1.23\text{ eV}$. However, due to the scaling relation:
    $$\Delta G_2 + \Delta G_3 = \Delta G_{*\text{OOH}} - \Delta G_{*\text{OH}} = 3.20\text{ eV} \implies \Delta G_2 = \Delta G_3 = 1.60\text{ eV}$$
    The minimum required potential is $U_{\text{min}} = 1.60\text{ V}$, imposing a theoretical minimum overpotential:
    $$\eta_{\text{theor}}^{\text{min}} = 1.60\text{ V} - 1.23\text{ V} = 0.37\text{ V}$$
    *   **OER Theoretical Overpotential**: $\eta_{\text{OER}} = \max\{\Delta G_1, \Delta G_2, \Delta G_3, \Delta G_4\} / e - 1.23\text{ V}$.
    *   **Primary Descriptor**: $(\Delta G_{*\text{O}} - \Delta G_{*\text{OH}})$.

---

#### C. Carbon Dioxide Reduction Reaction (CO2RR)
```
                    CO2(g) + H+ + e-
                      /          \
            (C-bound)/            \(O-bound)
                    v              v
                 *COOH           *OCHO
                  /                \
        (+H+ + e-)                 (+H+ + e-)
                v                    v
         *CO + H2O                  HCOOH(l) (Formate pathway)
         /        \
(desorption) /     \ (+H+ + e- protonation)
       v            v
     CO(g)       *CHO / *COH (Deep reduction branch)
                    |
                 ... v
               CH4 / C2H4
```
*   **Branching Points**:
    1.  **Initial Protonation**: C-bound $*\text{COOH}$ (leads to CO and hydrocarbons) vs. O-bound $*\text{OCHO}$ (leads to $\text{HCOOH}/\text{HCOO}^-$).
    2.  **$*\text{CO}$ Selectivity**:
        *   Weak binding ($\Delta G_{\text{des}} < 0$, e.g. Au, Ag, Zn): Desorbs as $\text{CO}(\text{g})$ with high Faradaic efficiency.
        *   Moderate binding (e.g. Cu): Retains $*\text{CO}$ for subsequent PCET to $*\text{CHO}$, enabling deep reduction to hydrocarbons ($\text{CH}_4, \text{C}_2\text{H}_4$).
        *   Strong binding (e.g. Pt, Ni, Fe): $*\text{CO}$ poisons surface; HER dominates.

---

#### D. Nitrogen Reduction Reaction (NRR)
*   **Overall Reaction**: $\text{N}_2(\text{g}) + 6\text{H}^+ + 6\text{e}^- \to 2\text{NH}_3(\text{g})$ ($U^\circ = +0.06\text{ V vs. RHE}$)
*   **Pathways**:
    1.  **Distal Pathway**: Sequential protonation of distal N atom to yield 1st $\text{NH}_3$, followed by protonation of remaining $*\text{N}$.
    2.  **Alternating Pathway**: Alternating protonation of both N atoms until N–N bond cleaves.
*   **Key Selectivity Metric**: Compare $\Delta G_{\text{selectivity}} = \Delta G_{\text{H}^*} - \Delta G_{*\text{NNH}}$. On most metals $\Delta G_{\text{H}^*} \ll \Delta G_{*\text{NNH}}$, causing surface coverage by $\text{H}^*$ and severe HER selectivity dominance.

---

## 3. Surface transition states

For an elementary reaction between two relaxed surface states, follow the [periodic TS workflow](periodic-ts.md). Use one fixed cell, an explicit atom correspondence and consistent electronic settings. If NEB identifies an interior minimum, verify that structure and examine the steps on either side. Refine the candidate where needed and verify its reaction-relevant imaginary mode and both downhill connections before assigning an elementary activation barrier.
