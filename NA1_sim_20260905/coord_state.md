# NA1_sim_20260905 coord_state (recreated ROUND5 2026-09-05)
State: DAG mechanism committed (delivery rev 1, Supervisor accepted draft_c7064f78); compute unlocked.
Campaign: re-dispatched fresh small_mol session (see below) -> workdir NA1_sim_20260905/campaign_xtb/.
History: ROUND1-3 pilots unreliable (pre-restart runtime); ROUND4 original campaign as_067bd4408b974a8d
orphaned 'queued' by runtime restart 07:02:53 UTC; ROUND4b liveness probe OK, fresh campaign
as_45f63e56d51d4c38 ran 07:36-07:39 UTC then killed by 'interrupted by process restart';
ROUND5 (this): gate timeout #2 -> campaign re-dispatched; full anomaly log in root HARNESS_NOTES.md.
ROUND6 2026-09-05: gate timeout #3; child as_8fd99e8a36c54f16 FAILED (runtime restart family).
Partial rc evidence on disk: campaign_xtb/rc/ (xtb opt E~-25.56285 Eh; soft -12.72 cm-1 imag to resolve; MACE SP missing).
Campaign re-dispatched fresh (RESUME) -> session recorded below; i1/i2/p/ts1-3/mace pending.

ROUND7 2026-09-05 22:43 (wake: MACE SP compute job task 103 done):
  rc evidence chain COMPLETE and VERIFIED by coordinator:
    - geometry: campaign_xtb/rc/rc_vtight/rc_vtight.xtb_opt.log  GEOMETRY OPTIMIZATION CONVERGED AFTER 207 ITERATIONS, E=-25.565796664932 Eh, gnorm=6.04e-05, .xtboptok present
    - frequency: campaign_xtb/rc/rc_vtight/rc_vtight.xtb_freq.log  n_imag=0 (mode7=+18.83 cm-1 lowest real; supersedes rc_v3 -12.72 soft imag diagnostic)
    - single_point (MACE-OMol25): campaign_xtb/rc/rc.mace_sp.out.log + scheduler copy mace/.cloudra/calc-103.out.log  FINAL SINGLE POINT ENERGY (From external program) = -383.505731694800 Eh, ORCA TERMINATED NORMALLY
    - smiles annotation present on inp and xyz headers: [OH-].CC=O.CC=O (16 atoms)
  campaign child as_12fcb6974dd045ac state=running (active writes 22:38-22:42; NOT blocked); i1/i2/p/ts1-3/ts2/ts3/scans

ROUND8 2026-09-05 23:39:34 +0800 (wake: campaign gate check_timeout; child as_12fcb6974dd045ac state=FAILED):
  Child died mid-campaign. Last message before death: reverse PT scan from i1 rises monotonically to
  -25.5705 Eh with NO maximum near rc -> deprotonation (rc->i1) is BARRIERLESS on the xtb PES (no saddle);
  child planned an O1...H9 approach scan (keeping C2-H9 intact) to characterize the approach barrier.
  Failure root cause: sub-agent run finished with HTTP 402 'Insufficient Balance' from api.deepseek.com
  (LLM-provider billing) - same infra-failure family as prior runtime-restart kills; NOT chemistry, NOT DAG policy.
  Verified on disk at death: rc evidence chain COMPLETE (xtb geom+ohess n_imag=0 + MACE SP -383.505731694800 Eh;
  energies.md row present). i1 partial only (i1_conf0.xyz / i1a_opt.xyz unverified; no freq/MACE). i2/p/ts1-3 EMPTY.
  mace/ holds only rc SP. CAMPAIGN_REPORT.md MISSING. scans/ts1_* present as diagnostics.
  Action: campaign re-dispatched ONCE to a fresh small_mol session (session id recorded below); gate re-armed +3600s.

ROUND8 dispatch session: see get_subagent_report on the session id returned by the launcher call below.

ROUND9 2026-09-05 23:47 (wake: MACE SP compute job task 110 done -> i1 evidence):
  i1 evidence chain on disk (child as_a59c5ae18e4244e7, state=running):
    - geometry: campaign_xtb/i1/i1_vtight.xtb_opt.log (xtb 6.7.1 GFN2/ALPB water, --opt vtight --chrg -1),
      E=-25.588255852854 Eh, gnorm=5.92e-05, .xtboptok PRESENT (vtight/), i1/i1_final.xyz annotates smiles: C=C[O-].O.CC=O
    - frequency: i1_vtight.xtb_freq.log + vtight/vibspectrum: n_imag=0 (modes1-6 ~0.00, mode7=+38.13 cm-1); g98.out all positive
    - single_point MACE-OMol25: mace/.cloudra/calc-110.out.log FINAL SINGLE POINT ENERGY (From external program) = -383.531676752600 Eh;
      ORCA TERMINATED NORMALLY (line 409); inp line 201 carries 'smiles: C=C[O-].O.CC=O'
  OPEN SCIENTIFIC QUESTION (hub post evt_a9dbaa8a85c74276 to a-4): i1/opt1/xtbopt.xyz (ROUND7 artifact, .xtboptok,
    smiles: [OH2].CC=O.C=C[O-]) E=-25.617450205380 is 18.3 kcal/mol BELOW chosen i1_vtight -> must adjudicate identity
    before i1 serves as barrier reference; if same species, lower conformer should be the i1 reference.
  Gate: still armed (CAMPAIGN_REPORT.md check). CAMPAIGN_REPORT.md MISSING at 23:47. energies.md not yet updated with i1 row.


