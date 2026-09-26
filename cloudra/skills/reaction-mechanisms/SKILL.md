---
name: reaction-mechanisms
description: Organic reaction mechanism encyclopedia and competing pathway playbook. Use when proposing mechanism graphs (dag_propose_mechanism), identifying competing pathways (regiochemical, stereochemical, concerted vs. stepwise, elimination vs. substitution), formulating reaction center seeds, or reviewing mechanism drafts across 9 major organic reaction classes.
---

# Organic Reaction Mechanisms & Competing Pathways Playbook

**Competition is the foundational core of organic reactions.**
Chemical transformations rarely proceed through an isolated, solitary pathway. A credible reaction mechanism must capture the kinetic and thermodynamic competition between parallel channels: regioselectivity, stereoselectivity, concerted versus stepwise paths, and side reactions.

Use this skill when formulating mechanism hypotheses, identifying competing branches for `dag_propose_mechanism`, evaluating transition-state starting geometries, or conducting Supervisor reviews.

---

## The 9 Major Organic Reaction Classes

This skill organizes organic transformations into 9 foundational classes. Load detailed reference playbooks via `get_skill(skill_name="reaction-mechanisms", reference="<filename>")`:

| Reaction Class | Reference File | Key Characteristics & Competing Channels |
| :--- | :--- | :--- |
| **Pericyclic Reactions** | `pericyclic.md` | Cycloadditions (Diels-Alder, 1,3-dipolar), sigmatropic shifts (Cope, Claisen), electrocyclizations. **Competitions**: *endo* vs. *exo*, concerted pericyclic vs. stepwise diradical/zwitterionic paths. |
| **Polar Carbonyl Additions** | `carbonyl.md` | Nucleophilic additions to aldehydes/ketones/esters, enolization, aldol/Claisen condensations. **Competitions**: 1,2-addition vs. 1,4-conjugate addition; kinetic vs. thermodynamic enolate. |
| **Nucleophilic Substitutions** | `substitution.md` | Aliphatic $S_N1$, $S_N2$, neighboring group participation (NGP), aromatic $S_N\text{Ar}$, benzyne paths. **Competitions**: Substitution ($S_N$) vs. Elimination ($E$); direct attack vs. ion-pair formation. |
| **Elimination Reactions** | `elimination.md` | $E1$, $E2$, $E1\text{cB}$, syn-eliminations (Chugaev, Cope elimination). **Competitions**: Zaitsev (more substituted alkene) vs. Hofmann (less substituted alkene); $E2$ stereospecific anti-periplanar requirements. |
| **Electrophilic & Radical Additions** | `addition.md` | Halogenation, hydrohalogenation, hydration across alkenes/alkynes. **Competitions**: Markovnikov vs. anti-Markovnikov regioselectivity; syn- vs. anti-stereospecific additions. |
| **Rearrangements** | `rearrangement.md` | Wagner-Meerwein carbocation shifts, Beckmann, Baeyer-Villiger, Pinacol, Favorskii rearrangements. **Competitions**: Migratory aptitude (H vs. aryl vs. alkyl); concerted migration vs. fragmented intermediates. |
| **Radical Pathways** | `radical.md` | Radical additions (ATRA), atom-transfer, polymerizations, homolytic cleavages. **Competitions**: Radical addition vs. hydrogen atom abstraction; cage escape vs. recombination. |
| **Oxidation & Reduction (Redox)** | `redox.md` | Epoxidations (Prilezhaev, Sharpless), dihydroxylations, hydrides, single-electron transfers (SET). **Competitions**: Outer-sphere single-electron transfer (SET) vs. inner-sphere two-electron hydride transfer. |
| **Transition-Metal Catalytic Coupling** | `coupling.md` | Suzuki-Miyaura, Heck, Sonogashira, Buchwald-Hartwig, Negishi cross-couplings. **Competitions**: Oxidative addition regioselectivity; $\beta$-hydride elimination vs. reductive elimination. |

---

## Competing Pathway Audit Checklist ("宁可多写不算，也不要少写")

When drawing a mechanism graph or proposing a hypothesis to the Supervisor, systematically audit these four competition axes:

1. **Regiochemical Competition**:
   - Are there multiple nucleophilic/electrophilic sites?
   - Did you consider Markovnikov vs. anti-Markovnikov, ortho/para vs. meta, or 1,2- vs. 1,4-addition?
2. **Stereochemical Competition**:
   - Did you consider diastereomeric faces (*Re* vs. *Si* face attack, *endo* vs. *exo* approaches)?
   - Are chiral centers inverted or retained?
3. **Concerted vs. Stepwise Alternatives**:
   - For cycloadditions or rearrangements, is a stepwise zwitterionic or diradical intermediate energetically accessible?
4. **Side Reactions & Decomposition**:
   - Will strong bases induce $E2$ elimination instead of $S_N2$ substitution?
   - Can active carbocations undergo hydride/alkyl shifts before trapping?

---

## How to Load In-Depth References

Load specific reference chapters for detailed reaction coordinate diagrams, expected transition-state bond lengths, and troubleshooting guides:

```python
# Example: Load the pericyclic reactions guide
get_skill(skill_name="reaction-mechanisms", reference="pericyclic.md")

# Example: Load transition-metal coupling pathways
get_skill(skill_name="reaction-mechanisms", reference="coupling.md")
```
