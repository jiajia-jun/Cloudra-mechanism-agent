# gold_compute — 文献调研结果汇总

> 每份报告到齐后追加。字段：task | value | type | frame | source | verification | proposed_md_cell

## C3 (easy) — F- + CH3Cl double inversion (retention)
- value=16.4 (CONFIRMED) | type=ΔE‡ (classical/electronic) | frame=reactants (F-+CH3Cl(eq) asymptote) | verification=verified
- source: Szabó & Czakó 2015 Nat. Commun. 6, 5972, DOI 10.1038/ncomms6972 (front-side 31.3)
- note: ZPE-corrected adiabatic value 12.6; default central_complex frame does NOT apply.
- cell: ΔE‡ 16.4 kcal/mol（理论，TS 相对反应物渐近线 F⁻+CH3Cl(eq)；复合 FPA，AE-CCSD(T)/CBS + CCSDT(Q) + DK 标量相对论，Szabó & Czakó 2015 Nat. Commun. 6, 5972, DOI 10.1038/ncomms6972；正面进攻 31.3）[已核实]

## D1 (easy) — butadiene + ethylene Diels-Alder
- value=27.5 (CONFIRMED) | type=Ea | frame=experiment_kinetics (separated reactants; no pre-complex) | verification=verified
- source: Rowley & Steiner 1951 Discuss. Faraday Soc. 10, 198, DOI 10.1039/df9511000198 (via Huang, Tsai & Hu 2001 JPCA 105, 9945, DOI 10.1021/jp012740f)
- note: ±2 uncertainty is NOT sourced (remove); computed companion 21.9 kcal/mol classical barrier.
- cell: Ea 27.5 kcal/mol（实验，Rowley & Steiner 1951 Discuss. Faraday Soc. 10, 198, DOI 10.1039/df9511000198；经 Huang, Tsai & Hu 2001 J. Phys. Chem. A 105, 9945, DOI 10.1021/jp012740f 引用；同文献另报计算经典能垒 21.9）[已核实]

## NI1 (normal) — imine formation formaldehyde + methylamine
- value=26.7 (ΔE‡, G2(MP2,SVP)) | frame=central_complex (microsolvated: carbinolamine·(H2O)2 pre-complex) | verification=partial
- alt (acid-catalysed protonated carbinolamine): 16.2 kcal/mol (67.9 kJ/mol)
- source: Hall & Smith 1998 J. Phys. Chem. A 102, 4930, DOI 10.1021/jp9810825 (closed access; abstract-level)
- note: reference state inferred from abstract; RDS=carbinolamine dehydration confirmed.
- cell: 决速步=羟胺脱水；ΔE‡ ≈ 26.7 kcal/mol（G2(MP2,SVP)，Hall & Smith 1998 J. Phys. Chem. A 102, 4930, DOI 10.1021/jp9810825；两水辅助中性羟胺脱水；酸性O-质子化路径 16.2）[部分核实]

## NO3 (normal) — Baeyer-Villiger, acid-catalysed addition
- **NO RELIABLE ABSOLUTE VALUE** — target paper Álvarez-Idaboy 2006 Org. Lett. 8, 1763 (DOI 10.1021/ol060261z) reports only a barrier LOWERING ΔΔG‡=12.7 kcal/mol, not an absolute barrier.
- analogues: uncatalysed addition Ea 38-41 (Bach 2012 JOC DOI 10.1021/jo300727w); BF3-catalysed migration-RDS ΔG‡=17.7 (Carlqvist/Brinck 2001 JOC DOI 10.1021/jo001278c). frame ≠ central_complex.
- proposed cell: 决速步=加成步（酸催化加成新 TS…Álvarez-Idaboy 2006 Org. Lett. 8, 1763, DOI 10.1021/ol060261z）；绝对垒值未核——原文仅给出较前报道低 12.7 kcal/mol（ΔΔG‡）[部分核实]

## D4 (easy) — cyclopentadiene + acrolein DA  → CORRECTED VALUE
- value=13.6 (endo) / 14.1 (exo) kcal/mol | type=ΔE‡ | frame=reactants | verification=verified
- source: Domingo, Pérez, Ríos-Gutiérrez, Aurell 2024 Tetrahedron Chem 10, 100064, DOI 10.1016/j.tchem.2024.100064 (ωB97X-D/6-311G(d,p), gas phase; water 12.9/13.5)
- note: existing 17-20 was NOT a separated-reagents barrier; 19.2 is relative to loose pre-complex S1 (non-standard frame). Correct to 13.6/14.1.
- cell: ΔE‡ 13.6（endo）/14.1（exo）kcal/mol（理论 ωB97X-D/6-311G(d,p)，气相，相对分离反应物；Domingo et al. 2024 Tetrahedron Chem 10, 100064, DOI 10.1016/j.tchem.2024.100064）[已核实]

## NA2 (normal) — acetone self-aldol condensation
- **NO RELIABLE VALUE** for the gas-phase OH--catalysed elementary RDS. Best analogue: apparent Ea 27.8 kcal/mol (116.3 kJ/mol) acetone->isobutene over Hf/SiO2 (Lewis-acid, heterogeneous; Zhang 2021 JACS DOI 10.1021/jacs.1c01315) — wrong frame/step type.
- other leads (wrong step/frame): Boekfa 2010 JPCC DOI 10.1021/jp1058947 (acetone tautomerisation H-ZSM-5 20.5); Migues 2014 JPCC DOI 10.1021/jp504131y (HZSM-5/HY ~20); Pratt 2005 JOC DOI 10.1021/jo0503409 (Li-enolate, number not in abstract).
- proposed cell: 能垒数值未核（决速步=加成/脱水；无可靠气相/OH⁻催化DFT数值…）[未核实]

## G2 (easy) — diimide cis reduction of ethylene
- value=18.8 (CONFIRMED) | type=ΔE‡ | frame=reactants | verification=verified
- source (primary): Flood & Skancke, Chem. Phys. Lett. 1978, 54(1), 53-56, DOI 10.1016/0009-2614(78)85662-0 (ab initio FORCE method, low-level)
- correction: re-attribute 18.8 to the primary 1978 study (existing cell cited the Organic Reactions review 10.1002/0471264180.or040.02 as origin). Related: Pasto & Chipman 1979 JACS 101, 2290 ≈19.3 (cis); MNDO/AM1 ~25.8.
- cell: 同步双 H 转移 ΔE‡ 18.8 kcal/mol（cis-diimide，理论；相对分离反应物；Flood & Skancke Chem. Phys. Lett. 1978, 54, 53-56, DOI 10.1016/0009-2614(78)85662-0）[已核实]

## NA5 (normal) — Mannich C-C formation
- value=8.9 (37.2 kJ/mol) ANALOGUE (acetophenone enol + iminium, not formaldehyde/methylamine/acetaldehyde) | type=ΔE‡ | frame=central_complex (enol+iminium pre-complex) | verification=verified (source real, number read in full text) but analogue substrate
- source: Petrović et al. 2018 R. Soc. Open Sci. 5, 181232, DOI 10.1098/rsos.181232; corroborating proline-Mannich C-C 8.5 kcal/mol (Parasuk 2008 JOC 73, 9388, DOI 10.1021/jo801872w)
- tension: literature says for acid-catalysed (protonated iminium) Mannich the C-C step is barrierless/very low (Chem. Rev. 2011); the real RDS may be iminium dehydration — benchmark RDS assignment (C-C) questionable.
- cell: ΔE‡ ≈ 8.9 kcal/mol（37.2 kJ/mol，苯乙酮 enol 进攻亚铵 C–C 成键步，DFT/CPCM，Petrović et al. R. Soc. Open Sci. 2018, 5, 181232, DOI 10.1098/rsos.181232；类似体系非同一底物；脯氨酸催化 8.5 kcal/mol, Parasuk 2008 JOC 73, 9388）[已核实]

## D3 (easy) — cyclopentadiene dimerization (endo)
- value=16.6 NOT CONFIRMED (couldn't read Table 1); existing range cell "Ea 14.9-16.6" → parser takes 14.9. | type: source standardises to ΔH‡(0 K), so Ea label likely wrong → ΔH‡ | frame=reactants (gas kinetics) | verification=partial (source real, number unchecked)
- source: Güner, Khuong, Leach, Lee, Bartberger & Houk 2003 J. Phys. Chem. A 107, 11445, DOI 10.1021/jp035501w
- recommendation: downgrade [已核实]→[部分核实], correct Ea→ΔH‡.
- cell: ΔH‡ 16.6 kcal/mol（实验，Güner et al. 2003 J. Phys. Chem. A 107, 11445–11459, DOI 10.1021/jp035501w；分离反应物渐近线口径，实验数据标准化至 ΔH‡(0 K)；具体数值未获全文复核）[部分核实]

## F1 (easy, re-run) — BH4- + formaldehyde
- CANNOT CONFIRM; DOI 10.1139/v88-406 is a MISATTRIBUTION (paper = FT-ICR reduction of substituted maleic anhydrides, no formaldehyde, no barrier). No alternative source found.
- existing cell's ~30 kcal/mol (127 kJ/mol) value is unsupported by the cited DOI; value unconfirmed.
- recommendation: mark 能垒数值未核 / unverified, remove the false citation.

## M8 (easy) — cyclohexane chair flip
- value=10.3 (CONFIRMED/best single) | type=ΔG‡ | frame=experiment_kinetics (VT-NMR, chair ground state → half-chair TS) | verification=verified (via OA review citing Anet & Bourn; 1967 full text paywalled)
- source: Anet & Bourn 1967 JACS 89, 760-768, DOI 10.1021/ja00980a006
- note: existing "~10" correct; 10.3 is best single (others quote ~10.8-11).
- cell: ΔG‡ 10.3 kcal/mol（实验，VT-1H NMR 线形分析；Anet & Bourn 1967 J. Am. Chem. Soc. 89, 760-768, DOI 10.1021/ja00980a006；half-chair TS）[已核实]

## NU3 (normal) — Wittig (parent ylide)
- value=19.1 ANALOGUE (Me3P=CH2, not parent H3P=CH2) for the rate-determining cycloreversion/ring-opening; addition step is near barrierless (<1 kcal/mol, Robiette 2006 via Bofill 2024). | type=ΔE‡ | frame=reactants | verification=verified (analogue)
- source: Bofill et al. 2024 Chem. Eur. J. 30, e202400173, DOI 10.1002/chem.202400173 (B3LYP/6-31G*+D3BJ, ORCA, gas phase); <1 kcal/mol addition: Robiette 2006 JACS 128, 2394 (closed)
- note: benchmark premise (addition = RDS) likely inverted for non-stabilised ylides: addition ~barrierless, cycloreversion RDS.
- cell: 速决步（环氧膦开环/环回复）ΔE‡ ≈ 19.1 kcal/mol（B3LYP/6-31G*+D3BJ，气相，相对分离反应物，模型叶立德 Me3P=CH2 类似物；Bofill et al. 2024 Chem. Eur. J. 30, e202400173, DOI 10.1002/chem.202400173）；加成步近乎无能垒（<1 kcal/mol，Robiette 2006 JACS 128, 2394）[已核实]

## M1 (easy) — 2,2'-dimethylbiphenyl atropisomer rotation  -> CORRECTED
- existing ~13 NOT confirmed (likely mis-recollection). value=18.1 | type=ΔG‡ | frame=experiment_kinetics (ground-state atropisomer, unimolecular) | verification=partial (primary 1967 closed, number via OA secondary)
- sources: Theilacker & Böhm 1967 Angew. Chem. Int. Ed. Engl. 6, 251, DOI 10.1002/anie.196702511 (ΔG‡=18.1 @25C); number read in Bednářová 2018 Adv. Synth. Catal. 360, 2869, DOI 10.1002/adsc.201800452; corroborating DFT 16.7 (same) / 20.0 (Karton 2020 JPCA 124, 6977, DOI 10.1021/acs.jpca.0c05386). Cited OBC 2013, 11, 2859 (Masson) is closed, could not read its value.
- cell: ΔG‡ 18.1 kcal/mol（实验，25 °C 溶液消旋动力学，Theilacker & Böhm 1967 Angew. Chem. Int. Ed. Engl. 6, 251, DOI 10.1002/anie.196702511；经 Bednářová et al. 2018 Adv. Synth. Catal. 360, 2869 转引核对；计算佐证 Karton 2020 JPCA 124, 6977 ≈20）[部分核实]

## NY3 (normal) — ester saponification BAC2
- value=15.5 | type=ΔG‡ (298.15 K) | frame=solution_free_energy (aqueous; NOT central_complex) | verification=verified
- source: Pliego & Riveros 2002 Chem. Eur. J. 8(8), 1945, DOI 10.1002/1521-3765(20020415)8:8<1945::aid-chem1945>3.0.co;2-t (experimental 15.3, excellent agreement); RDS=OH- addition.
- note: existing cell's Zhan DOI is wrong: actual Zhan/Landry/Ornstein 2000 JACS DOI 10.1021/ja9937932 (not ja993311m).
- cell: ΔG‡ ≈ 15.5 kcal/mol（水相簇-连续介质自由能剖面，BAC2 OH⁻ 加成 RDS；Pliego & Riveros 2002 Chem. Eur. J. 8, 1945, DOI 10.1002/1521-3765(20020415)8:8<1945::aid-chem1945>3.0.co;2-t；实验 15.3）[已核实；frame=solution_free_energy]

## M16 (easy, re-run) — formic acid dehydrogenation  -> corrected
- value=71 (dehydrogenation HCOOH->CO2+H2); competing dehydration ~68; 1,2-H shift TS ~79 | type=ΔE‡ | frame=gas-phase static 0 K PES | verification=verified
- source: Goddard, Yamaguchi & Schaefer 1992 J. Chem. Phys. 96, 1158, DOI 10.1063/1.462203 (existing cell's "Scuseria & Schaefer" attribution imprecise; existing 65-68 matches the DEHYDRATION channel, not dehydrogenation)
- cell: ΔE‡ ≈ 71 kcal/mol（气相静态 PES，CCSD(TZ2P)/CCSDT-1//DZP，Goddard, Yamaguchi & Schaefer, J. Chem. Phys. 1992, 96, 1158, DOI 10.1063/1.462203；HCOOH→CO2+H2 通道；竞争脱水≈68、1,2-H 迁移 TS≈79）[已核实]

## NU5 (normal) — Passerini (formaldehyde + formic acid + methyl isocyanide)
- For the R=H (formaldehyde) minimal system: alpha-addition (nitrilium) ΔG = 44.1 (3-comp) / 13.9 (4-comp) kJ/mol = 10.5 / 3.3 kcal/mol; Mumm rearrangement ΔG = 160.1 (3-comp) / 51.8 (4-comp) kJ/mol = 38.3 / 12.4 kcal/mol. With the 2nd-acid (4-component) channel, Mumm rearrangement is rate-limiting at 12.4 kcal/mol. For a real ketone substrate, alpha-addition RDS = 22.0 kcal/mol.
- source: Staub, Harabuchi, Seraphim, Varnek & Maeda 2026 JCTC, DOI 10.1021/acs.jctc.5c01293 (PMC12805569), reproducing Maeda 2011 Angew 50, 644 (DOI 10.1002/anie.201005336). Level RwB97X-D/6-31+G(d,p)/CPCM(CCl4), 300 K. Maeda 2011 & Ramozzi&Morkumma 2015 JOC 80,5652 closed.
- proposed: RDS=Mumm rearrangement (4-comp, formaldehyde system) ΔG‡ ≈ 12.4 kcal/mol; frame=solution_free_energy (CCl4).
- cell: 决速步=Mumm 重排（第二羧酸协助的 4 组分通道）ΔG‡ ≈ 12.4 kcal/mol（RwB97X-D/6-31+G(d,p)/CPCM(CCl4)，300 K；甲醛体系，α-加成仅 ~3.3；Staub et al. 2026 J. Chem. Theory Comput., DOI 10.1021/acs.jctc.5c01293；原始 Maeda 2011 Angew 50, 644, DOI 10.1002/anie.201005336）[已核实]

## G3 (easy) — propylene + ethylene ene (Alder-ene)
- value=33.0 (138 kJ/mol, existing ~33 retained) | type=ΔE‡ | frame=reactants | verification=partial (138 read from a secondary attribution; primary Wiley closed)
- sources: Fernández & Bickelhaupt 2012 J. Comput. Chem. 33(5), 509-516, DOI 10.1002/jcc.22877 (M06-2X/def2-TZVPP); Sakai 2006 J. Phys. Chem. A 110(47), 12891-12899, DOI 10.1021/jp064588t (CASSCF/CiLC: stepwise ~4 kcal/mol lower than concerted — confirmed).
- cell: ΔE‡ ≈ 33 kcal/mol（138 kJ/mol，气相，相对分离反应物；M06-2X/def2-TZVPP，Fernández & Bickelhaupt 2012 J. Comput. Chem. 33(5), 509-516, DOI 10.1002/jcc.22877；CASSCF 显示分步路径低约 4 kcal/mol：Sakai 2006 J. Phys. Chem. A 110(47), 12891-12899, DOI 10.1021/jp064588t）[部分核实]

## HD2 (hard) — cyclohexene oxide + OH- trans-diaxial SN2 opening
- value=14.3 ANALOGUE (ethylene oxide, not cyclohexene oxide) | type=Ea | frame=microsolvated (NOT central_complex) | verification=verified (source real, number in abstract) but analogue substrate
- source: Lundin, Panas & Ahlberg 2007 J. Phys. Chem. A 111(37), 9087-9092, DOI 10.1021/jp073285b (B3LYP/6-311+G(d,p), microsolvated alkaline)
- no cyclohexene-oxide-specific hydroxide barrier found; best hydroxide-specific analogue Hansen 2023 Chem. Eur. J. 29, e202301308 (numeric not extractable).
- cell: ΔE‡ ≈ 14.3 kcal/mol（B3LYP/6-311+G(d,p) 微溶剂化；环氧乙烷类似物，非环己烯氧化物；Lundin, Panas & Ahlberg 2007 J. Phys. Chem. A 111, 9087-9092, DOI 10.1021/jp073285b）[已核实；frame=microsolvated]

## HL1 (hard) — Beckmann rearrangement of (E)-butanone oxime
- candidate 31.2 (acetone oxime, RDS 1,2-H shift, H-Faujasite embedded cluster Brønsted acid) | type=Ea | frame=solid acid zeolite (NOT solution H3O+) | verification=partial (abstract-level, closed full text)
- alt: concerted anti-migration for protonated formaldehyde oxime 44 kJ/mol ≈ 10.5 kcal/mol, gas phase (Nguyen & Vanquickenborne 1993 Perkin Trans 2, 1969, DOI 10.1039/p29930001969)
- source: Sirijaraensre & Limtrakul 2006 ChemPhysChem 7(11), 2424-2432, DOI 10.1002/cphc.200600403
- no butanone/acetone-oxime solution H3O+ concerted-migration barrier found.
- cell: 能垒数值：丙酮肟 DFT 决速步 31.2 kcal/mol（Sirijaraensre & Limtrakul 2006 ChemPhysChem 7, 2424, DOI 10.1002/cphc.200600403；B3LYP/6-31G(d,p)+MP2//，H-Faujasite 固相酸，非 H3O+ 溶液）；形式甲醛肟气相共轭步 44 kJ/mol≈10.5 kcal/mol（Nguyen 1993, DOI 10.1039/p29930001969）[部分核实]

## HL1 (hard) — UPDATE (better source, SI-verified)  [supersedes the 31.2 zeolite value]
- value=39.9 (PRIMARY, H3O+(H2O)6 acid model) / 19.2 (molecular-acid model) | type=ΔE‡ (relative RB3LYP) | frame=**central_complex** (TS relative to pre-reaction oxime+acid complex, 0.0) | verification=**verified** (read directly from retrieved ACS SI)
- source: Yamabe, Tsuchida & Yamazaki 2005 J. Org. Chem. 70(26), 10638-10644, DOI 10.1021/jo0508346, SI Fig. S4 (acetone-oxime analogue; TS1 427.1i cm^-1). Stepwise σ-complex path (benchmark gold assumes concerted — flag).
- cell: ΔE‡ ≈ 39.9 kcal/mol（丙酮肟类似物，B3LYP，H₃O⁺(H₂O)₆ 酸模型，TS1/决速步；Yamabe, Tsuchida & Yamazaki 2005 J. Org. Chem. 70, 10638-10644, DOI 10.1021/jo0508346, SI Fig. S4；分子酸模型另给 ΔE‡ ≈ 19.2）[已核实；frame=central_complex]

## NU6 (normal, re-run) — Staudinger beta-lactam (ketene + methanimine)
- value=60.8 (TS1C, RDS, stepwise) but ANOMALOUSLY HIGH vs mainstream literature; ΔH‡ 59.98, ΔG‡ 69.91; second step 63.5 | type=ΔE‡ | frame=reactants (separated) | verification=partial (OA full text, but value conflicts with Domingo 2015: ΔE‡ 11.9 / ΔG‡ 31.8)
- source: Mohammad-Salim 2021 ZANCO J. Pure Appl. Sci. 33(4), 1-10, DOI 10.21271/zjpas.33.4.1 (B3LYP/6-311++G(d,p), gas); conflict: Domingo et al. 2015 RSC Adv. 5, 37119, DOI 10.1039/c5ra03438h
- recommendation: value unreliable; keep 能垒数值未核 or use Domingo substituted-system (analogue) with clear flag.
- cell: 机理锚点（Cossío 2008 Acc. Chem. Res. 41, 925；Domingo 2015 RSC Adv. 5, 37119）；母体 ketene+formaldimine DFT（Mohammad-Salim 2021 ZJPAS 33(4), 1, DOI 10.21271/zjpas.33.4.1）ΔE‡(TS1C)≈60.8（ΔH‡ 59.98, ΔG‡ 69.91）；与取代体系主流值（ΔE‡ 11.9/ΔG‡ 31.8）冲突，待复核 [部分核实]

## NR1 (normal) — pinacol rearrangement  -> NO RELIABLE VALUE
- NO RELIABLE VALUE FOUND for the rate-determining concerted 1,2-methyl migration. Primary computational works all closed-access (no number in any abstract): Yamabe, Tsuchida & Yamazaki 2007 J. Comput. Chem. 28, 1561, DOI 10.1002/jcc.20690; Itoh & Yamataka 2010 J. Phys. Org. Chem. 23, 789, DOI 10.1002/poc.1664; Nakamura & Osamura 1993 JACS 115, 9112, DOI 10.1021/ja00073a029. Yamabe 2007 abstract confirms "completely concerted" H3O+(H2O)2 path but gives no number.
- decision: leave barrier = null; keep cell "能垒数值未核（...）" (no edit applied).

## NR1 (normal) — pinacol rearrangement  -> FILLED (partial)
- value=26.2 | type=ΔE‡ | frame=microsolvated (H3O+·12H2O) | verification=unverified (frame-set override) / source partial
- source: Yamabe, Tsuchida & Yamazaki 2007 J. Comput. Chem. 28(9), 1561-1571, DOI 10.1002/jcc.20690 (closed; number via Google Scholar full-text snippets; F5-2 ΔE=26.20 vs experiment 26.2-27.1; competing path ≈32.65; substrate ambiguity parent pinacol vs diphenyl analogue). Do NOT use 24.82 (neopentyl SN TS).
- applied cell + added R1 to gen_normal frame set.


## NI1 per-edge (from edge-swarm) — reconciliation
- NI1_E1 (addition) = 3.5 kcal/mol (14.7 kJ/mol, Hall & Smith 1998); NI1_E2 (dehydration, RDS) = 26.7 (111.9 kJ/mol). The later sub-agent mis-mapped 26.7 to E1; correct mapping per Hall & Smith: addition low (3.5), dehydration is RDS (26.7).

## F1 (easy) — BH4- + formaldehyde 调研终结论（两轮调研汇总）
- 维持 null（诚实缺测）。两轮文献调研结论：无开放数据库值（GMTKN55/BH9/RDB7 均无该反应；原 Can. J. Chem. 1988 引用系误引——该文为取代马来酸酐 FT-ICR 研究）。
- central-complex 口径下该反应很可能是沉没垒（barrierless），不适合做锚点；同反应类无可换题。建议保持诚实缺测。

## NA2 (normal) — acetone self-aldol 补充
- 维持 null。类似物值存在但不采用：乙醛锂烯醇盐 QCISD ΔU‡=5.01 kcal/mol（Pratt 2005 JOC 70, 4279, DOI 10.1021/jo0503409）——非本体系（Li 烯醇盐 vs OH- 催化丙酮），不转录。

## NO3 (normal) — Baeyer-Villiger 酸催化加成 补充
- 维持 null。Grein 2006 J. Org. Chem. 71, 861（DOI 10.1021/jo0513966）的酸催化加成 TS 表格需机构权限阅读；拿到前保持 null。

## NU6 (normal) — Staudinger 补充机理备注
- 维持 null。母体有 Zhou/Birney 2004 博士论文 CCSD(T)//B3LYP ΔE‡ 24.9 kcal/mol（分离反应物口径；且气相 IRC 显示协同、无两性离子中间体）——仅作机理备注，不入锚点。
