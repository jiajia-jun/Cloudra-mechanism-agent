# NA2 fresh run plan (2026-09-05, own run)

Task: acetaldehyde self-aldol -> 3-hydroxybutanal, base (OH-), water, 0-25 C.
Reactant [OH-].CC=O.CC=O (q=-1, m=1); Product [OH-].CC(O)CC=O.
Mapping (1-based): O1 = OH- O; A-aldehyde: C2(CH2-bearing H8), C3(CHO C), O4; B-aldehyde: C5(CH3), C6(CHO C), O7.
Hypothesis (textbook base-catalyzed aldol):
  rc ->[E1 deprotonation] i1 (enolate . H2O . aldehyde B)
  i1 ->[E2 C-C addition, RDS?] i2 (aldol alkoxide . H2O)
  i2 ->[E3 proton shuttle O1-H8 -> O7] p ([OH-].CC(O)CC=O)
Bond changes:
  E1 rc->i1: break (2,8),(3,4); form (1,8),(2,3)
  E2 i1->i2: break (2,3),(6,7); form (2,6),(3,4)
  E3 i2->p : break (1,8); form (7,8)
Methods allowed ONLY: GFN2-xTB (opt+freq+TS+IRC) and MACE-OMol25 (SP via ORCA ! ExtOpt external).
