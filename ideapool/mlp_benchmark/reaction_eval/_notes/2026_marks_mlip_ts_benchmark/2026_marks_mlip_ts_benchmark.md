
## 第 1 页

Journal Name

Reliable and Efficient Automated Transition-State Searches with Machine-Learned Interatomic Potentials

Jonah Marks ,a Jonathon Vandezande ,b and Joseph Gomes a,∗

arXiv:2604.00405v1  [physics.chem-ph]  1 Apr 2026

Transition-state searches are central to understanding reaction mechanisms, but the high compu- tational cost of density-functional theory (DFT) limits their application in high-throughput catalyst and materials discovery. Machine-learned interatomic potentials (MLIPs) offer near-DFT accuracy at orders-of-magnitude lower cost, yet their reliability for transition-state searches remains under- explored. Here, we systematically benchmark hybrid transition-state-search workflows combining six freely available potentials (MACE-OMol25, UMA-Small, UMA-Medium, eSEN-S, AIMNet2, and GFN2-xTB) with two reaction-path-finding algorithms (the freezing-string method and climbing- image nudged elastic band) across 58 diverse reactions spanning small organics, polymerization chemistry, and transition-metal catalysis. We find that models trained on the Open Molecules 2025 dataset exhibit markedly superior performance, with MACE-OMol25 achieving a 96.6% success rate while requiring fewer than four DFT-gradient evaluations per reaction on organic systems—a 94–96% reduction compared to conventional DFT-based searches. Low-level refinement on the MLIP sur- face before high-level DFT optimization reduces computational cost three-fold with minimal loss in reliability. For transition-metal systems, UMA-Medium demonstrates promising transferability to in-distribution transition metal complex reactions and out-of-distribution organometallic C–H acti- vation. These results establish MLIP-accelerated workflows as practical tools for automated reaction discovery, enabling near–DFT accuracy at a fraction of traditional expense.

1 Introduction

functional theory (DFT), which can accurately describe complex chemical phenomena including bond formation and dissociation. However, despite favorable scaling relative to post-Hartree–Fock methods, DFT-based searches quickly become prohibitively ex- pensive in large systems or when multiple reactions are under investigation due to the non-linear scaling of DFT and large num- ber of in-series PES evaluations required by TS-search algorithms. Consequently, there is a growing need for workflows that can gen- erate high-quality TS guesses with minimal computational cost. To address this issue, many algorithms have been developed to automate TS searches, including machine-learning algorithms that attempt to directly predict reaction parameters or TSs1–7 and methods based on a chain-of-states reaction-path representation that explore the PES. The latter group includes two functional classes: methods that optimize the MEP (such as the nudged elastic band and growing-string method), which provide approxi- mate transition-state geometries, and local refinement techniques that take such geometries as starting points and converge them to true first-order saddle points, often using Hessian informa- tion. A widely used and effective strategy is to combine these approaches—first by employing a reaction-path locating method to generate a candidate transition state, followed by local refine- ment with a local surface-walking algorithm.8–12 A hybrid two- stage workflow can be used wherein the reaction-path-locating

Determining reaction mechanisms is central to the design of new materials, catalysts, and synthetic routes. Experimental elucida- tion of mechanisms and reaction parameters is often challeng- ing and resource intensive due to the rarity of barrier-crossing events and the fleeting nature of activated complexes such as transition states. Theoretical approaches therefore play an es- sential complementary role, providing mechanistic insight and, once validated, may enable high-throughput screening of reac- tive systems. Many theoretical methods center on identifying the transition state, whose relative energy and geometry determine the rate and selectivity of a reaction. The transition state is the highest energy point along the minimum-energy path (MEP) con- necting reactant and product states, corresponding to a first-order saddle point on the Born–Oppenheimer potential-energy surface (PES). The energy of the transition state relative to the reac- tant and product states defines the activation barrier and thereby the reaction kinetics. Accurately capturing these energetics re- quires PESs from electronic-structure methods such as density-

a Department of Chemical and Biochemical Engineering, University of Iowa, Iowa City, IA, United States

b Rowan Scientific, Boston, MA, United States

∗Email: joe-gomes@uiowa.edu

Journal Name, [year], [vol.], 1–20 | 1


![image_1](images/image_0001.jpeg)


![image_2](images/image_0002.jpeg)


![image_3](images/image_0003.jpeg)


![image_4](images/image_0004.jpeg)


![image_5](images/image_0005.jpeg)


![image_6](images/image_0006.jpeg)


![image_7](images/image_0007.jpeg)


## 第 2 页

algorithm is performed at a lower level of theory, and the local refinement at a higher level of theory. Among the various reaction-path-locating methods,8,9,11,13–16

ever, their generalization to out-of-distribution reaction types remains limited. Development of workflows that integrate conventional search algorithms with MLIPs in a standardized framework enables researchers to rapidly incorporate emerging state-of-the-art models or train models for specific phenomena of interest, providing broader chemical coverage at the cost of higher per-reaction expense. In this work, we develop and evaluate a hybrid machine- learned-DFT workflow for automated transition-state searches. MLIPs or semi-empirical DFT are first used to generate TS guess geometries using either the FSM or the CI-NEB method. Each potential–algorithm pair produces a candidate geometry that can optionally be refined on the same surface, hereafter referred to as low-level refinement. These native and low-level-refined guesses are then used as initial structures for high-level (DFT) refinement. This hybrid strategy allows the inexpensive low-level potential to bear the majority of the search cost, while the high- level refinement provides the accuracy and validation necessary for reliable thermochemical and kinetic predictions.27,28

the nudged elastic band (NEB)13–15 and freezing-string method (FSM)9,10,17 are two of the most widely used approaches. The NEB method constructs a discretized reaction path between reac- tant and product via interpolation. The path is then converged to an approximate MEP through optimization of the spring- coupled images in the discretized path. The spring coupling ensures equidistant distribution of the images in the path. In the climbing-image nudged elastic band (CI-NEB) method, the highest-energy image is driven uphill along the reaction coor- dinate to converge to the saddle point, improving the accuracy of the transition state. In contrast to the NEB method, the FSM incrementally extends strings from the reactant and product states until two branches meet, offering improved convergence for complex pathways that deviate significantly from interpolated paths. FSM "freezes" earlier images in the path as new images are added, reducing the cost of the search at the expense of not finding the minimum energy pathway. Both techniques have been shown to perform well with ab-initio PESs, but the substantial computational cost of repeated electronic-structure evaluations limits their practicality for large systems or high-throughput applications. Reducing the number of high-level evaluations required during transition-state searches is therefore key to improving the scalability of these methods. Machine-learned interatomic potentials (MLIPs) have emerged as a compelling alternative to DFT, delivering near-DFT accuracy at significantly reduced computational cost. These models use neural networks or other machine-learning architec- tures to approximate the PES by learning from large datasets of quantum-chemical energies and forces, enabling rapid energy and gradient evaluations once trained. Recent model archi- tectures such as AIMNet2,18 MACE-OMol25,19 eSEN-S,20 and UMA21 offer orders-of-magnitude speedup relative to DFT while maintaining near-DFT accuracy across respective validation sets. With new quantum-chemical datasets like the Open Molecules 2025 (OMol25) dataset, pre-trained forms of MACE, eSEN-S, and UMA architectures are able to reliably simulate charged and open-shell systems with chemically diverse atomic species, enabling simulation of many classes of industrially-relevant molecules.22 While these MLIPs have been trained and tested extensively for thermochemical and structural properties, their performance in transition-state searches, where accurate descrip- tion of the PES near the activated regions is critical, remains less explored. Prior applications of MLIPs in TS searches, often employing custom-trained models with narrow chemical do- mains, have shown promise but were typically limited to small benchmarks or specialized implementations of the reaction-path locating algorithms.23–26

We then systematically benchmark all combinations of the FSM and CI-NEB with six freely available potentials-MACE- OMol25, UMA-Small, UMA-Medium, eSEN-Small, AIMNet2 and GFN2-xTB- yielding 24 potential–algorithm workflows per reaction. Performance is assessed across two established reaction sets, followed by application of best-performing combinations to a new benchmark of polymerization reactions and four organometallic test cases. Two primary metrics are considered: the success rate of the high-level refinement to the reference saddle point as validated by frequency analysis, and the number of DFT gradient evaluations required to do so. Collectively these results reveal clear trends in which algorithm-potential combinations most effectively reproduce DFT-level transition states while minimizing high-level computational cost. Models trained on the OMol25 dataset exhibit markedly higher reliability and lower search costs than those trained on other datasets. Among these, MACE-OMol25 consistently achieves 96% success rates across benchmark sets with an average of fewer than five DFT evaluations per reaction on small organic systems. The UMA-Medium model displays comparable efficiency, with slightly lower reliability on small molecules but improved performance for larger, more complex systems, including organometallic and transition-metal catalysis.

2 Methods

2.1 Transition-State Searches Transition-state-search workflows involve multiple stages, pro- gressing from initial molecular structures to fully validated transi- tion states. The key steps used in this study are outlined in Figure 1. The reactant and product geometries provided by benchmark datasets and prior literature case studies were used as starting points for one of two reaction-path-finding algorithms: the ML- FSM Python package or the CI-NEB implementation in ASE29. The details and parameters of ML-FSM are described in section 2.2.1; the CI-NEB implementation and parameters are described

Additionally, many machine-learning methods that directly predict transition states from reactant and product structures have been proposed.1,6 These methods are extremely promising, as they offer orders-of-magnitude cost reductions relative to the hybrid workflows presented here and often achieve high accuracy for reactions within their training distributions. How-

Journal Name, [year], [vol.], 1–20 | 2


## 第 3 页

dramatically reducing the total number of gradient evaluations required at the cost of locating the MEP. The FSM algorithm proceeds through iterative growth cycles consisting of two primary steps. First, interpolation is performed between the current innermost (frontier) nodes to generate a dense chain of intermediate states from which an intermediate geometry Rinterp at fixed arc-length distance s along the approx- imate reaction coordinate is selected. Second, this interpolated structure undergoes constrained optimization using a local quadratic approximation of the PES:

E(R) = E(Rinterp)+(R−Rinterp)T g⊥+ 1

2(R−Rinterp)T H(R−Rinterp)

(1) where g⊥denotes the component of the gradient perpendicu- lar to the local tangent direction and H is an approximate Hessian matrix. The perpendicular gradient is computed through the pro- jection:

g⊥= (I−ˆtˆtT )g (2)

where ˆt is the normalized tangent vector at the current node and I is the identity matrix. The optimization is performed using the L-BFGS-B algorithm with backtracking line searches and user-specified limits on both the maximum number of line search steps and the maximum number of optimization steps that can be taken.17 Once opti- mized, each node is permanently frozen and excluded from fur- ther refinement, ensuring linear scaling with respect to the num- ber of nodes added. Growth cycles continue until string unification is achieved. The unification criterion examines the distance d between frontier nodes: if 2s > d > s, a single node is added and the calculation ter- minates; if d < s due to the optimization of frontier nodes, termi- nation occurs without additional node placement. Upon comple- tion, the highest energy image serves as the transition-state guess for subsequent refinement using local surface-walking methods. The key efficiency advantage of the FSM lies in the truncation of node optimization and absence of global chain optimization. While this approach sacrifices detailed minimum energy pathway information, it enables rapid identification transition-state region with computational costs typically 5–10 times lower than con- ventional GSM and NEB methods.9,17 However, unlike CI-NEB or GSM methods, the highest energy node cannot be considered the exact transition state. In this work, we use the ML-FSM Python package. FSM cal- culations used linear interpolation in redundant internal coor- dinates combined with Cartesian-space optimization using the L-BFGS-B implementation in SciPy.17,32–34 Each calculation em- ployed 18 nodes, a maximum of three line search steps, and two optimization steps per node.

Fig. 1 Transition-state-search workflows, green boxes denote steps per- formed with low-level potentials, while the blue box denotes use of the ωB97X-V/def2-TZVP level of theory.

in Appendix A.1. Both ML-FSM and CI-NEB are chain-of-states methods that produce a discrete string of optimized intermedi- ate geometries connecting the reactant and product. The highest energy intermediate geometry, as computed on the low-level po- tential, is designated as the native transition-state guess. Two workflow variants were evaluated. In the native work- flow, this TS guess was passed directly to high-level refinement and validation using partitioned rational-function optimization in Q-Chem at the ωB97X-V/def2-TZVP level of theory. In the low-level-refined workflow, the same TS guess was first refined on the low-level potential (MLIP or semi-empirical DFT) prior to the high-level refinement and validation (vide infra for com- parative analysis of both workflows). Low-level refinement was carried out using a restricted-step P-RFO optimization in redun- dant internal coordinates, as implemented in the Sella Python package.30,31 This additional refinement stage was intended to improve the proximity of the native guess to a first-order saddle point while retaining the efficiency of the low-level potential.

2.2 Non-local Path Finding Algorithms

2.2.1 ML-FSM

The Freezing-String Method (FSM) provides transition-state guesses at significantly reduced computational cost by employ- ing a "freeze-and-grow" strategy that eliminates the need for global chain optimization.9 Unlike the GSM and NEB method, which iteratively optimize the entire chain of states, the FSM permanently "freezes" each node after its initial optimization,

2.3 Potential-Energy Surfaces Computationally inexpensive PESs that maintain accuracy along reaction coordinates are essential for enabling high-throughput transition-state searches. Five freely available machine-learned

Journal Name, [year], [vol.], 1–20 | 3


![image_8](images/image_0008.jpeg)


## 第 4 页

interatomic potentials and one semi-empirical DFT (SE-DFT) models were used in this work for both reaction path finding and low-level refinement of the TS guesses. Each model is summarized below; full details can be found in the respective cited references.

Refinement of native TS guesses on the low-level PES—either a MLIP or SE-DFT—was carried out using a restricted-step partitioned-rational-function optimization (RS-P-RFO) in redun- dant internal coordinates, as implemented in the Sella Python package.31 The RS-P-RFO employs iterative Hessian diagonaliza- tion enabling efficient convergence to nearby first-order saddle points without full Hessian evaluations.30 Further details of the optimization algorithm are provided in the original works Hermes et al. 31,45. Convergence was achieved when the max- imum Cartesian gradient component was below 0.05 eV·Å−1

• GFN2-xTB:35 An extended-tight-binding SE-DFT model with self-consistent multipole electrostatics and D4 dispersion. GFN2-xTB is parameterized up to Z=86.

• AIMNet2:18 A second-generation atoms-in-molecules neural-network potential incorporating iterative charge equilibration and explicit long-range electrostatics. Trained on 20 ωB97M-D3/def2-TZVPP structures distilled from a 120M B97-3c conformer master set of molecules with elements (C,H,N,O,S,F,Cl,Br,I,P,Si,B,As,Se).

(approximately 3×10−3 Ha·Bohr−1). Transition-state geometries refined at the low-level were subsequently used as initial guesses for the high-level (ωB97X-V/def2-TZVP) P-RFO refinement and validation. High-level transition-state refinement optimizations per- formed in Q-Chem 6.0 are initialized with an analytical Hessian that is updated at each cycle using the Murtagh–Sargent–Powell formula.46 The maximum number of self-consistent-field (SCF) iterations and geometry-optimization steps were limited to 250. SCF energies and gradients were converged to 10−6 Ha and 3×10−4 Ha·Bohr−1, respectively. In cases where frequency anal- ysis revealed low-magnitude (< 30 cm−1) or spurious imaginary modes, tighter convergence criteria was employed to eliminate minor imaginary modes.

• oMOL25’s eSEN Conserving small:22 (hereafter eSEN-S): an equivariant graph transformer with spherical convolu- tions instead of attention trained on the OMol25 dataset.

• UMA Small 1.1:21 (hereafter UMA-S): mixture-of-experts variants of eSEN-S with 150M total parameters (≈6M ac- tive) trained on approximately 500M structures.22,36–38

• UMA Medium 1.1:21 (hereafter UMA-M): mixture-of- experts variants of eSEN-S with 1.4B parameters (≈150M active) trained on approximately 500M structures.22,36–38

3 Results

3.1 Organic Reaction Benchmarking To evaluate the reliability and efficiency of the MLIPs introduced in Section 2.3 for the transition-state searches, we applied four workflow variants (FSM native, FSM low-level refined, CI-NEB native, and CI-NEB low-level refined) with all six potentials to two established benchmark sets of organic reactions. The CI- NEB results are discussed in detail in Appendix A.3; here we focus on the FSM-based searches, which achieved higher suc- cess rates at lower computational cost. The Baker set, intro- duced by Baker and Chan 47, consists of 24 gas-phase reactions of small organic molecules. The reactions include chemical phe- nomena such as insertion reactions, cationic and anionic mech- anisms, open-shell systems, and rotation reactions, providing a rigorous test of algorithm robustness across diverse organic re- action types. The second set, introduced by Sharada et al. 10, comprises nine elementary organic reactions encompassing di- verse reaction phenomena including bond formation, dissocia- tion, ring-opening, and isomerization. Despite its modest size, the set includes both prototypical and challenging cases–for example the Alanine Dipeptide, parent Diels–Alder, and Ireland–Claisen reactions, as well as a classically-hard test case, ethane dehydro- genation (CH3CH3 →CH2CH2 + H2). Collectively, the Baker and Sharada benchmarks span a broad range of chemical transforma- tions and charge-spin states while remaining tractable for high- level electronic-structure methods, making them ideal benchmark sets for evaluating transition-state-search methods.10,17,26,48–50

• MACE-OMol25:19 An E(3)-equivariant message-passing neural network with explicit higher-body terms (up to 4-body) and bilinear radial mixing. The OMol25 variant introduces charges and spin awareness, trained on ∼100M DFT data points (ωB97M-V/def2-TZVPD) spanning diverse charged and open-shell molecules.

2.4 Computational Details All DFT calculations were performed with Q-Chem 6.0,39 using the range-separated-hybrid density functional ωB97X-V40 with the triple-ζ def2-TZVP41 basis set. The SG-2 quadrature grid was employed for all energy and gradient evaluations.42 In several cases across benchmark sets, TS searches converged to the correct saddle point with a secondary imaginary frequency, often below 20i. To eliminate these secondary imaginary frequencies the op- timization was continued with the SG-3 quadrature grid, tighter SCF convergence criteria, and tighter convergence thresholds. DFT calculations were primarily used for two tasks: (1) harmonic-frequency calculation to verify the nature of saddle points, where a first-order saddle point must have exactly one imaginary frequency, and (2) the high-level refinement of guess geometries to first-order saddle points using the eigenvector following partitioned rational-function optimization (P-RFO)43

method as implemented in Q-Chem. The P-RFO algorithm operates in delocalized internal coordinates by default. In instances where P-RFO converged to an off-target saddle point, the connected minima were confirmed by intrinsic reaction coordinate (IRC) calculations performed in Sella using the predictor–corrector geodesic algorithm.31,44

3.1.1 FSM

Across the Baker benchmark, the FSM showed consistently high success rates and low computational cost in identifying reference

Journal Name, [year], [vol.], 1–20 | 4


## 第 5 页

Table 1 Comparison of performance of GFN2-xTB, AIMNet2, eSEN-S, UMA-S, UMA-M, MACE-OMol25 for native and low-level-refined guess generation via the FSM on the Baker set. Performance is measured by successful convergence to the reference transition state, and the number of DFT gradient evaluations required. Italicized values denote failed runs, with superscripts denoting the failure mode.

GFN2-xTB AIMNet2 eSEN-S UMA-S UMA-M MACE-OMol25 Native Low-level Native Low-level Native Low-level Native Low-level Native Low-level Native Low-level Reaction refined refined refined refined refined refined

(a) Converges to an alternate first-order saddle point. (b) Converges to local-minimum structure. (c) Converges to correct TS with spurious imaginary frequency additional cost to eliminate frequency via tighter P-RFO convergence parameters was added. (d) Fails to converge P-RFO within 250 optimization cycles. (e) SCF convergence error. (f) Converges to structure with multiple strong (> 200 cm−1) imaginary frequencies.

Success Rate 83.3% 87.5% 87.5% 79.2% 95.8% 91.7% 91.7% 83.3% 95.8% 87.5% 87.5% 95.8% Mean Success Cost 14.5 7.4 16.2 10.3 16.7 4.0 14.0 3.3 13.8 2.9 12.8 2.9

1. HCN →HNC 3 4 3 4 4 2 3 3 4 2 4 2 2. HCCH →CCH2 16 5 6 3 8 2 9 2 9 2 9 3 3. H2CO →H2 + CO 10 5 21 36b 17 2 16 3 16 2 18 2 4. CH3O →CH2OH 6 4 23 14 6 3 6 3 6 3 6 3 5. cyclopropyl ring opening 13 5 47a 7a 13 3 12 3 9 3 23a 3 6. bicyclo[1.1.0]butane →trans-butadiene 147a 14 43 28 59 4 181a 4 43 3 92a 4 7. formyloxyethyl 1,2-migration 14 8 18 33b 14 4 15 5 11 4 16 3 8. parent Diels–Alder cycloaddition 31 7 29 4 42 2 26 3 19 3 23 3 9. s-tetrazine →2HCN + N2 14 10b 7 4 24 5 36 4 24 3 9 3 10. trans-butadiene →cis-butadiene 5 4 4 4 3 3 3 2 3 2 3 2 11. CH3CH3 →CH2CH2 + H2 20 9 33 34 23 250d 20 156a 17 64a 21 3 12. CH3CH2F →CH2CH2 + HF 11 7 9 4 11 2 11 2 11 2 11 2 13. acetaldehyde keto-enol tautomerism 6 5 4 4 4 2 4 2 4 2 4 2 14. HCOCl →HCl + CO 8 6 8 4 7 2 6 2 7 2 7 2 15. H2O + PO− 3 →H2PO− 4 23 6 27 250d 23 3 27 2 21 2 23 2 16. CH2CHCH2CH2CHO Claisen rearrangement 30 7 34 6 27 22 24 250d 27 233a 25 3 17. SiH2 + CH3CH3 →SiH3CH2CH3 19 22 7 8 6 4 7 5 7 4 6 4 18. HNCCS →HNC + CS 144a 36b 8 4 21 3 12 3 15 3 10 2 19. HCONH+ 3 →NH+ 4 + CO 42c 9 250d 21 14c 10c 25c 9c 17c 9c 21 7 20. acrolein rotational TS 4 4 3 3 4 2 4 3 4 2 4 3 21. HCONHOH →HCOHNHO 6 10 9 7 9 3 9 3 10 3 10 3 22. HNC + H2 →H2CNH 45a 8 0e 17a 250d 2 250d 40a 41a 2 234b 3 23. H2CNH →HCNH2 9 7 7 10 6 2 5 2 6 3 5 3 24. HCNH2 →HCN + H2 38a 3a 37 29 40 18f 29 19 f 28 18 f 33 27 f

Journal Name, [year], [vol.], 1–20 | 5


## 第 6 页

Table 2 Comparison of performance of GFN2-xTB, AIMNet2, eSEN-S, UMA-S, UMA-M, MACE-OMol25 for native and low-level-refined guess generation via the FSM on the Sharada set. Performance is measured by successful convergence to the reference transition state, and the number of DFT gradient evaluations required. Italicized values denote failed runs, with superscripts denoting the failure mode.

saddle points. Averaged across all workflows and potentials, the FSM achieves a success rate of 88.9%; successful searches re- quired an average of 9.9 gradient evaluations. Native workflows, in which the FSM guess was submitted directly to the Q-Chem P-RFO, yielded the highest success rate at 90.3% but required 14.7 gradient evaluations per successful search. The low-level refinement yielded a success rate of 87.5% across all six models and the cost reduced by approximately 3-fold, with an average of 5.0 gradient evaluations per successful search—a 66% reduc- tion in cost. Under the assumption that the low-level potentials produce qualitatively correct Hessians, such a reduction in cost is expected. The modest decline in success rate, however, sug- gests that the low-level models do not yield uniformly accurate Hessians and in some cases introduce systematic failure. For ex- ample, in reaction 11 (CH3CH3 →CH2CH2 + H2), searches using eSEN-S, UMA-S, and UMA-M all succeed with the native guess, but all fail after the low-level refinement. Likewise, for reaction 24 (HCNH2 →HCN + H2), eSEN-S, UMA-S, UMA-M, and MACE- OMol25 searches succeed natively yet fail in identical fashion fol- lowing refinement. These two reactions represent characteristic failure modes and are analyzed in greater detail vide infra in Sec- tion 4.1.2. Performance on the Sharada benchmark set mirrored that of the Baker set. Across the 9 reactions, 4 of which are shared with the Baker set, the FSM achieved an overall success rate of 89.8% with an average cost of 22.4 gradient evaluations per successful search. The native and low-level-refined workflows achieved suc- cess rates of 90.7% and 88.9% respectively, with average costs of 36.4 and 8.0 gradient evaluations, respectively. Notably, the Sharada set includes larger systems like the alanine dipeptide iso- merization (reaction 8) and the Ireland–Claisen rearrangement (reaction 9). The continued high performance on these 20–50+ atom systems demonstrates the FSM’s scalability to reactions with many orthogonal degrees of freedom. The more pronounced cost reduction in this set underscores the efficiency of coupling the FSM with a local refinement algorithm prior to high-level refine- ment and validation. For larger systems, where the non-linear scaling of DFT renders gradient evaluations significantly more ex- pensive, this reduction in the number of required evaluations be- comes increasingly impactful.

GFN2-xTB AIMNet2 eSEN-S UMA-S UMA-M MACE-OMol25 Native Low-level Native Low-level Native Low-level Native Low-level Native Low-level Native Low-level Reaction refined refined refined refined refined refined

Success Rate 77.8% 88.9% 100.0% 88.9% 100.0% 88.9% 77.8% 88.9% 100.0% 77.8% 88.9% 100.0% Mean Success Cost 37.6 11.0 40.2 15.9 36.1 5.4 21.7 5.9 44.0 4.1 35.8 5.7

(a) Converges to an alternate first-order saddle point. (b) Converges to local-minimum structure. (c) Converges to correct TS with spurious imaginary frequency additional cost to eliminate frequency via tighter P-RFO convergence parameters was added. (e) SCF convergence error. (f) Converges to structure with multiple strong (> 200 cm−1) imaginary frequencies. (g) P-RFO optimization step failure.

1. H2CO →H2 + CO 10 5 21 36b 17 2 16 3 16 2 18 2 2. SiH2 + H2 →SiH4 25 20 6 8 7 4 5 5 7 4 6 4 3. CH2CHOH ↔CH3CHO 6 5 4 4 4 2 4 2 4 2 4 2 4. CH3CH3 →CH2CH2 + H2 20 9 33 34 23 250d 20 156a 17 64a 21 3 5. bicyclo[1.1.0]butane →trans-butadiene 147a 14 43 28 59 4 181a 4 43 3 92a 4 6. parent Diels–Alder cycloaddition 31 7 29 4 42 2 26 3 19 3 23 3 7. cis,cis-2,4-hexadiene ↔3,4-dimethylcyclobutene 18 5 19 5 16 3 16 3 16 3 17 3 8. C5 ↔C7AX 153 23 100c 25 108 12 65 12 199 12 117 16 9. silyl ketene acetal →silyl ester Ireland–Claisen rearrangement 250d 53b 107 19 49 14 96g 15 75 250d 80 14

3.1.2 Summary of MLIP performance on organic bench- marks

When comparing machine-learned potentials, a strong and sys- tematic performance advantage was observed for models trained on the OMol25 dataset. Evaluated over 29 unique reactions (24 from the Baker set and 5 from the Sharada set) using the FSM with low-level refinement, MACE-OMol25 achieved the highest success rate of 96.6% with a mean cost of 3.8 gradient evalua- tions per successful search. eSEN-S followed closely (93.1%, 4.5 gradients), while UMA-M achieved the lowest computational cost (3.3 gradients) at a moderate success rate of 86.2%. UMA-S and GFN2-xTB showed comparable reliability (86-88%) and AIMNet2 had the lowest success rate at 82.8% with a mean cost of 10.7 gradient evaluations per successful search. The OMol25 trained models appear to have a systematic ad-

Journal Name, [year], [vol.], 1–20 | 6


## 第 7 页

vantage. Aggregated across the full benchmark with both work- flows, the four OMol25 models achieved a mean success rate of 91.8% with an average cost of 11.7 gradient evaluations, com- pared to 84.5% success and 15.5 gradient evaluations for non- OMol25 models. While training strategies, model architecture, and model hyperparameters influence the end model’s accuracy, this difference likely arises from the richer representation of reac- tive configurations and transition-state geometries in the OMol25 dataset. Based on these results, the MACE-OMol25 and UMA-M combined with the FSM were selected for all subsequent evalua- tions of benchmark sets and case studies.

respectively, while MACE-OMol25 requires 12 and 4 gradient evaluations. This failure mode can therefore be attributed to the ML-FSM implementation rather than deficiencies in the underlying potentials. While incorporation of fallback routines for common failure modes represents a good practices in high throughput workflow development, for the present analysis, this reaction is classified as a failure of the ML-FSM algorithm. The UMA-M low-level-refined workflow exhibits one additional failure on reaction 8, methylamine and F3-acetic acid, reaching the 250 optimization step limit, whereas the MACE-OMol25 low-level-refined structure successfully converges in 4 steps.

3.2 Closed-Shell Polymerization Reactions (Poly25) The Poly25 dataset consists of 25 closed-shell gas phase reactions important in polymer chemistry. The reactions are further sub- divided into five classes: amide formation, epoxy polymerization, ester formation, isocyanate-containing reactions, and polyurea formation. The utility of this set of reactions is that it offers an assessment of the performance of current models and methods on an industrially relevant class of chemical reactions, that im- portantly has not been used in previous studies benchmarking reaction path and TS-finding methods. We apply the FSM-based native optimization and low-level refinement workflows using the MACE-OMol25 and UMA-M models to the problem of identify- ing the reference TS structures for each reaction contained in the Poly25 dataset. Both MACE-OMol25 and UMA-M demonstrate excellent per- formance on the closed-shell-polymerization benchmark, achiev- ing 96.0% success rates–comparable or better than their respec- tive performance on the combined Baker and Sharada sets, in- dicating that closed-shell polymerization reactions are an area of chemical space well represented in the OMol25 dataset. The mean computational cost for successful searches differs substan- tially between native workflows, with MACE-OMol25 averaging 22.0 gradient evaluations while UMA-M averages 31.5 gradient evaluations. The low-level refinement reduces both models to nearly identical costs of approximately 5 gradient evaluations. One notable outlier is reaction 1, methylamine and benzoic acid, where the UMA-M direct search requires 205 gradient evaluations compared to only 46 for MACE-OMol25. However, low-level re- finement mitigates this disparity entirely, reducing both searches to 6 and 5 gradient evaluations respectively. For three of the four workflow combinations, UMA-M native, and both MACE-OMol25 native and low-level-refined searches, the sole failure occurs on reaction 19, the isocyanate and methanol reaction. Closer inspection of the FSM output reveals a discontinuous arc length along the internal coordinates interpolation path arising from failures in the back transfor- mation from internal coordinates to Cartesian coordinates that occurs during the FSM growth phase. Manually re-running this reaction with linear synchronous transit (LST) interpola- tion,51 a well-established alternative to internal coordinates interpolation for chain-of-states methods, circumvents this issue entirely. UMA-M direct and Sella-refined searches converge to the reference saddle point in 17 and 3 gradient evaluations

3.3 Organometallic Case Studies Transition-metal-catalyzed reactions represent a critical test for MLIP-accelerated transition-state searches. These systems typi- cally contain 30–200+ atoms, involve diverse metal-ligand coor- dination environments, and exhibit multiple competing reaction pathways, making conventional DFT-based mechanistic studies computationally demanding and well suited candidates for MLIP acceleration. To evaluate the UMA-M and MACE-OMol25 mod- els on transition-metal-containing systems, we selected four case studies spanning different metals, coordination geometries, and mechanistic classes (Figure 2). The first three reactions are drawn from the Metal-Organic Barrier Heights (MOBH35) benchmark database, which provides DLPNO-CCSD(T)/CBS reference energies for 35 transition-metal- catalyzed transformations.27 The OMol25 training set includes reactive configurations generated from the MOBH35 structures via metal and ligand substitution and reaction path sampling with the Artificial-Force-Induced Reaction (AFIR) scheme.22,52

The three selected MOBH35 reactions (scandium-catalyzed olefin insertion, iron-catalyzed transfer hydrogenation, and platinum- mediated metallabenzene rearrangement) therefore represent near-in-distribution test cases, assessing whether coverage of structurally related reactive configurations in the training data translates to reliable transition-state search performance. The three selected reactions span early and late transition metals, diverse coordination geometries, and distinct mechanistic classes. Following the MOBH35 test cases, we examine the rhodium(III)-catalyzed oxidative carbonylation of toluene, a well-characterized example of transition-metal-mediated C–H activation.53 This system provides an out-of-distribution test case, as it is not derived from any of the reaction datasets used to generate OMol25 training configurations, probing MLIP transferability beyond the training data distribution. For all organometallic test cases, we applied the FSM na- tive and low-level-refined workflows using the UMA-M and MACE-OMol25 models. Where experimental or high-level (DLPNO-CCSD(T)/CBS) data was available we additionally evaluated the accuracy of MLIP predicted reaction and activation energies.

3.3.1 Scandium-Catalyzed Olefin Insertion

The first case study examines the elementary olefin-insertion step in the scandium-catalyzed hydroaminoalkylation of N- methylpiperidine with n-hexene, as investigated by Liu et al. 54

Journal Name, [year], [vol.], 1–20 | 7


## 第 8 页

Fig. 2 Reactant, transition state, and product geometries of (A) Scandium-Catalyzed Olefin Insertion (B) Iron-Catalyzed Transfer Hydrogenation (C) Platinum-Mediated Metallabenzene Re-arrangement case studies.

Journal Name, [year], [vol.], 1–20 | 8


![image_9](images/image_0009.png)


## 第 9 页

Table 3 Comparison of performance of UMA-M and MACE-OMol25 for native and low-level-refined guess generation via the FSM on the Poly25 benchmark. Performance is measured by successful convergence to the reference transition state and the number of DFT gradient evaluations required.

Reaction UMA-M MACE-OMol25

Native Low-level Refined Native Low-level Refined

Amide Formation

1. Methylamine + Benzoic acid 205 6 46 5 2. F3-methylamine + F3-acetic acid 18 3 14 3 3. Methylamine + F3-acetic acid 54 250 55 4 4. Methylamine + Acetic acid 29 6 24 6 5. F3-methylamine + Acetic acid 37 4 32 4 6. Phenylamine + Acetic acid 16 4 11 5

Epoxy

7. Ethylene oxide + tert-butoxide 9 6 6 5 8. Ethylene oxide + Methoxide 8 5 6 4 9. Fluoroethylene oxide + Methoxide 27 5 37 5 10. Propylene oxide + Methoxide 7 5 7 8

Ester Formation

11. F3-methanol + F3-acetic acid 25 3 19 2 12. Phenol + Acetic acid 20 6 20 6 13. Methanol + Acetic acid 32 10 41 9 14. Methanol + F3-acetic acid 30 4 11 5 15. F3-methanol + Acetic acid 45 4 33 5 16. Methanol + Benzoic acid 46 9 35 8

Isocyanate Containing

17. Isocyanate + Methanol 136 250 83 250 18. Isocyanate + Water 8 2 7 3 19. Methyl isocyanate + Water 11 4 12 4 20. Isocyanate + Phenol 14 5 21 5 21. Phenyl isocyanate + Water 46 3 30 4

Polyurea Formation

22. Isocyanate + Ammonia 12 2 8 2 23. Isocyanate + N-phenylaniline 14 6 14 8 24. Ethylene oxide + Phenoxide 11 8 11 10 25. Isocyanate + Aniline 32 5 28 5

Success Rate 96.0 % 92.0 % 96.0 % 96.0 % Mean Success Cost 31.5 5.0 22.0 5.2

and Iron and Janes 27. In the full catalytic cycle, the amine- coordinated η2-azametallacyclic complex serves as the active species, which undergoes ligand exchange with n-hexene to form a weakly bound π-complex. The subsequent insertion of the C=C bond into the Sc–C bond proceeds via a four-center transition state, yielding a ring-expanded azametallacyclic intermediate. This transformation constitutes the key C–C bond-forming step preceding C–H activation and regeneration of the catalyst. This reaction provides a stringent benchmark because it features a single, well-defined four-center transition state on a shallow potential surface. Application of the native and low-level FSM workflows with UMA-M model to this system led to different outcomes. The native FSM TS guess failed to converge to a saddle point within 250 optimization cycles. In contrast, the low-level-refined guess

converged to the correct transition state after only 22 optimiza- tion cycles. The initial ωB97X-V/def2-TZVP frequency calculation based on the native guess revealed five imaginary modes, with the largest at 308i cm−1, approximately 18 kcal·mol−1 above the reference TS, and a root-mean-square deviation (RMSD) of 0.75 Å. In contrast, the low-level-refined guess displayed a largest imaginary mode of (243i cm−1), consistent with the reference value (228i cm−1), and was approximately 3 kcal · mol−1 higher in energy and RMSD of 0.63 Årelative to the reference structure. Both MACE-OMol25 workflows successfully located the reference transition state, though with different computational costs. The native MACE-OMol25 guess exhibited a largest imaginary mode of 282i cm−1, an error of 19 kcal · mol−1, and RMSD of 0.76 Å, converging to the reference TS after 201 optimization steps. The corresponding low-level-refined guess improved these metrics

Journal Name, [year], [vol.], 1–20 | 9


## 第 10 页

(231i cm−1, 3 kcal · mol−1, and 0.66 Å) and converged to the correct transition state in 20 optimization steps. As expected, the native guesses from the FSM initially over- estimated the barrier due to the truncated path optimization. The UMA-M model predicted a barrier height of 10.9 kcal·mol−1

the error that might be observed from changes in level of theory between ωB97X-V/def2-TZVP and ωB97M-V/def2-TZVPD (OMol25). The accuracy of the UMA-M refined barrier on the MLIP-surface alone is notable and suggests that for this reaction, reliable barrier estimates can be obtained directly from the MLIP without recourse to DFT single point correction.

and a reaction energy of −14.9 kcal · mol−1 when evaluated on the low-level-refined TS geometry, overestimating the barrier by by 5.4 kcal · mol−1 relative to the DLPNO-CCSD(T)/CBS reference (5.5 and −16.9 kcal · mol−1) while reproducing the reaction energy within 2.0 kcal · mol−1. The MACE-OMol25 model showed larger barrier errors (13.9 kcal · mol−1, an overestimation of 8.4 kcal · mol−1) but predicted the reaction energy within 0.4 kcal · mol−1 of the DLPNO-CCSD(T)/CBS value (−17.3 vs −16.9 kcal · mol−1). Both models overestimate the barrier relative to ωB97X-V/def2-TZVP as well, indicating systematic errors in the MLIP energetics near the saddle point region. Importantly, despite these energetic discrepancies, the low-level-refined geometries were of sufficient quality for the high-level P-RFO to converge to the correct transition state in 20–22 optimization steps.

3.3.3 Platinum-Mediated Metallabenzene Re-arrangement

The platinum-mediated metallabenzene rearrangement is an in- tramolecular C–C coupling step that converts a metallabenzene complex to its cyclopentadienyl (Cp) analogue, as investigated by Iron et al. 56 and included in the MOBH35 benchmark set.27

In this transformation, the aromatic metallabenzene precursor undergoes direct C–C bond formation through a three-centered transition state characterized by an asymmetric M=C-C=C-C=C bonding motif. The reaction proceeds via carbene migratory- insertion-type mechanism, yielding an η5–Cp product. This sys- tem represents a demanding benchmark as it involves contrac- tion of an aromatic six-membered metallacyclic ring to a five- membered Cp ligand through direct C–C coupling. Application of the FSM with UMA-M produced guess struc- tures characterized by largest initial imaginary modes of 706i and 405i cm−1 for the native and low-level-refined workflows, respec- tively, compared to the reference transition-state frequency of 379i cm−1. The native guess structure was approximately 30 kcal· mol−1 higher in energy than the reference TS and had an RMSD of 0.65 Å, while the low-level-refined guess was only 0.2 kcal · mol−1 higher in energy and had an RMSD of 0.39 Å. Both guesses converged to the reference saddle point, requiring 91 and 22 op- timization steps, respectively. The MACE-OMol25 model showed larger initial deviations. The native guess exhibited an imaginary frequency of 1305i cm−1, lay 37 kcal·mol−1 above the reference, and an RMSD of 0.66 Å. This converged to the reference saddle point in 97 optimization steps, though the converged structure retained a second spu- rious imaginary frequency of 24i cm−1. The low-level-refined guess, when evaluated with ωB97X-V/def2-TZVP, exhibited a largest imaginary frequency of 429i cm−1, was approximately 1 kcal · mol−1 higher in energy than the reference transition state, and had an RMSD of 0.39 Å. Despite these initial metrics, the subsequent high-level P-RFO optimization failed to converge within 250 steps, with the final frequency analysis revealing no imaginary modes indicating that the optimization converged to a local minimum. Single-point ωB97X-V/def2-TZVP energy calculations on the refined UMA-M and MACE-OMol25 geometries predicted barrier heights of 21.9 and 23.2 kcal · mol−1, respectively, in close agreement with the DLPNO-CCSD(T)/CBS reference (19.0 kcal · mol−1) and ωB97X-V/def2-TZVP optimized value (21.2 kcal · mol−1). The predicted reaction energies (−40.5 and −43.2 kcal · mol−1) are similarly consistent with the DLPNO- CCSD(T)/CBS (−45.9 kcal · mol−1) and ωB97X-V/def2-TZVP (−42.4 kcal · mol−1) references. Similar to prior sections, the results on this test case show that MLIP-refined geometries are of high accuracy.

3.3.2 Iron-Catalyzed Transfer Hydrogenation

The iron-catalyzed transfer hydrogenation of acetophenone with isopropanol, mediated by Fe(II) PNNP eneamido complexes,55

is a prototypical example of base-metal catalysis. The key el- ementary step involves inner-sphere proton-transfer, which has been extensively characterized theoretically and included in the MOBH35 dataset, providing high accuracy DLPNO-CCSD(T)/CBS calculations of the activation and reaction energy.27

Application of the FSM workflows with the UMA-M and MACE-OMol25 successfully located the reference TS in all four cases. The native guesses converged in 30 and 28 gradient evaluations, respectively, while the low-level refinement reduced those to 11 and 14 gradient evaluations. As expected, the native FSM guesses substantially over- estimate the activation barrier due to the truncated path optimization, predicting barriers of 53.0 and 52.2 kcal · mol−1

for UMA-M and MACE-OMol25 respectively, while the reference DLPNO-CCSD(T)/CBS value is 16.4 kcal · mol−1. Low-level refinement dramatically improves these estimates: the UMA-M refined barrier of 15.3 kcal · mol−1 is within 1.1 kcal · mol−1

of the DLPNO-CCSD(T)/CBS value and 0.3 kcal · mol−1 of the ωB97X-V/def2-TZVP result (15.0 kcal · mol−1), while the MACE-OMol25 refined barrier of 13.1 kcal · mol−1 underesti- mates the reference by 3.3 kcal · mol−1. For the reaction energy, UMA-M predicts 1.9 kcal · mol−1, in exact agreement with the DLPNO-CCSD(T)/CBS value and within 0.5 kcal · mol−1 of the ωB97X-V/def2-TZVP (1.4 kcal · mol−1). MACE-OMol25 predicts −0.4 kcal · mol−1, incorrectly reversing the sign of the reaction energy. The UMA-M and MACE-OMol25 refined structures exhibit ωB97X-V/def2-TZVP imaginary frequencies of 1352i/64i cm−1

(RMSD = 0.395 Å) and 1382i/64i cm−1 (RMSD of 0.388 Å), respectively, compared to a single mode at 1387i cm−1 for the reference transition state, confirming that both models closely reproduce the saddle-point topology of the DFT surface. The error of the UMA-M model on this system is consistent with

Journal Name, [year], [vol.],1–20 | 10


## 第 11 页

3.3.4 Rhodium-Catalyzed Oxidative Carbonylation of Toluene

show substantially elongated C–H bonds (1.55-1.56 Å vs 1.28 Å reference) and Rh–H distances (2.71–2.72Å vs. 2.31 Å), reflect- ing the incomplete optimization of the breaking C–H bond at the FSM guess stage. The H–O1 distance is similarly overestimated at 1.47 Å compared to 1.37 Å. In contrast, the metal–carbon (Rh–C) and metal–oxygen (Rh–O2) distances are well reproduced even in the native guesses (within 0.01-0.02 Å of reference), indicating that the FSM and UMA-M/MACEOMol potentials capture the metal coordination geometry of the transition state prior to any refinement. Following low-level refinement, both UMA-M and MACE- OMol25 yield reactive core geometries in excellent agreement with ωB97X-V/def2-TZVP reference. The C–H distances (1.30 and 1.31 Å) and Rh–H distances (both 2.33 Å) are within 0.03 Å of the reference values, while the H–O1 bond lengths (both 1.36 Å) are within 0.01 Å. The Rh–C and Rh–O2 distances are similarly well reproduced, deviating by at most 0.04 Å across both models. This level of agreement demonstrates that the MLIP PESs themselves accurately minimize transition-state geometries without recourse to DFT. Notably, the Rh–H dis- tances remain above 2.3 Å in all refined structures, consistent with the electrophilic substitution mechanism characterized by Zakzeski et al. 53 and confirming the MLIPs correctly reproduce the non-agostic nature of this transition state. Collectively, these geometric comparisons confirm that both MLIPs faithfully reproduce geometries of the reactive core consistent with DFT PESs, and that the remaining energetic discrepancies originate from the conformational degrees of freedom peripheral to the reaction center.

The Rh(III)-catalyzed oxidative carbonylation of toluene to p- tolouic acid in trifluoroacetic acid represents a well-characterized example of transition metal-mediated aromatic C–H activa- tion. Combined experimental and theoretical investigations by Zakzeski et al. 53 established that the catalytically active species is Rh(CO)2(TFA)3, where TFA−denotes triflouroacetate anions. The proposed mechanism proceeds through reversible coordination of toluene via the para position, followed by rate limiting electrophilic C–H bond activation at the para carbon. Theoretical analysis at B3LYP/6-311G**//B3LYP/6-31G* level of theory confirmed that C–H activation proceeds through an electrophilic substitution mechanism rather than via agostic C–H interactions, as evidenced by Rh–H distances exceeding 2.4 Å in both the coordinated complex and transition state.53 We select the rate-limiting C–H activation elementary step as our test case, using the Rh(CO)2(TFA)3(C6H5CH3) complex as the reactant and the corresponding Rh(CO)2(TFA)2(TFAH)(C6H4CH3) species as the product. This system provides a demanding benchmark because it requires accurate treatment of an octahedral d6 Rh(III) center with multiple carboxylate ligands. Application of the FSM with UMA-M and MACE-OMol25 po- tentials successfully located the C–H activation transition state in all four workflow combinations, though the converged structures corresponded to two distinct conformers distinguished by the ori- entation of the trifluoroacetate ligands shown in Figure 3. The native work flows for both models converged in 82 optimization steps each, yielding transition-state structures with largest imag- inary frequencies of 885i (Figure 3B) and 890i cm−1 for UMA- M and MACE-OMol25 respectively, compared to the reference value of 831i cm−1 (Figure 3A. The low-level-refined workflows converged to a second conformer characterized by larger imagi- nary frequencies of 937i and 938i cm−1 for UMA-M and MACE- OMol25, respectively, requiring 55 and 76 optimization steps. Both conformers correspond to the same electrophilic C–H acti- vation mechanism and differ only in the rotational orientation of the side groups. This distinction does not affect the mechanistic interpretation, as the reaction does not involve stereo selectivity at this elementary step. The energetic analysis reveals modest deviations between the converged conformers. Single-point energies of TS con- formers resulting from the native-workflow lie approximately 1.6 kcal · mol−1 above the reference saddle point at the ωB97X- V/def2-TZVP level of theory, while low-level-refined structures are approximately 1.4 kcal · mol−1 higher than the reference saddle point. These small energy differences fall within the range expected for ligand rotational isomers on a relatively flat PES. To assess the structural quality of the converged transition states, we compare key geometric parameters of the reactive core defined by five atoms directly involved in the bond breaking and formation (H, C, O1, O2, and Rh; see Figure 3A across all work- flows and against both the ωB97X-V/def2-TZVP reference and B3LYP/6-311G**//B3LYP/6-31G* values reported by Zakzeski et al. 53 (Table 4). The native FSM guesses from both models

Table 4 Geometric parameters of the reactive core at the transition state as calculated by various potentials.

Method H–O1 C–H Rh–H Rh–C Rh–O2

Literature53 1.38 1.28 2.40 2.17 2.11 ωB97X-V/def2-TZVP 1.37 1.28 2.31 2.18 2.05 UMA-M Native 1.47 1.55 2.71 2.17 2.06 UMA-M Refined 1.36 1.30 2.33 2.14 2.06 MACE-OMol25 Native 1.47 1.56 2.72 2.19 2.06 MACE-OMol25 Refined 1.36 1.31 2.33 2.16 2.07

The near-identical reactive-core geometries across both con- formers and both models further clarify the origin of modest en- ergetic deviations (∼1.4–1.6 kcal · mol−1) observed between the converged transition states and the reference saddle point. Be- cause the bond-breaking and bond-forming geometric parameters are closely reproduced, the energetic differences can be attributed to differing orientations of the peripheral TFA ligands rather than errors in description of the reaction mechanism. These confor- mational differences arise from a combination of the initial guess geometry provided to the P-RFO optimizer and the optimizers tra- jectory across the saddle point region; on a relatively flat sur- face with respect to ligand rotation, small differences in the start- ing geometry can direct convergence toward distinct but mech- anistically equivalent conformers. This underscores an impor- tant practical consideration for transition-state searches on large

Journal Name, [year], [vol.],1–20 | 11


## 第 12 页

Fig. 3 Transition-state structures for the Rh(III)-catalyzed C–H activation step in oxidative carbonylation of toluene. (A) Reference transition state optimized at the ωB97X-V/def2-TZVP level of theory. (B) Transition state obtained from the UMA-M low-level-refined workflow after DFT refinement. Key atoms defining the reactive core are labeled in panel (A).

organometallic systems: peripheral-ligand flexibility can produce multiple valid saddle points with nearly degenerate energies, and the lowest-energy conformer is not guaranteed to be found with- out systematic conformational sampling.

to an 84.5% success rate and 15.5 gradient evaluations for non-OMol25 potentials. Aside from neural-network architec- tural differences, an advantage arises from the quantity and composition of the training data, the OMol25 dataset contains approximately 100M structures, including reactive snapshots, transition-state region configurations, and systematically diverse conformers calculated at the ωB97M-V/def2-TZVPD level of theory. Models such as UMA-M and UMA-S further benefit from inclusion of additional data sources22,36,37,57,58 spanning broader chemical domains, which appeared to enhance their transferability to transition metal complexes and supported catalytic systems. The value of low-level refinement on the MLIP surface is evident across all chemical regimes studied. For the organic benchmarks, low-level refinement reduced the average number of DFT gradient evaluations from 14.7 to 5.0 on the Baker set and from 36.4 to 8.0 on the Sharada set, with reductions of roughly 50% in RMSD between native and refined guess struc- tures. On the Poly25 closed-shell-polymerization benchmark, refinement reduced UMA-M and MACE-OMol25 costs from 31.5 and 22.0 to 5.0 and 5.2 gradient evaluations, respectively. For transition-metal systems, similar cost reductions were observed alongside substantial improvements in guess quality. This demonstrates that inexpensive local optimization on the MLIP surface provides geometries that are significantly closer to the target saddle point and should be a routine component of hybrid transition-state-search workflows. Comparing model performance across chemical regimes, MACE-OMol25 performed best for small organic systems, re- quiring an average of only 3.8 gradient evaluations across the Baker and Sharada sets with only a single failure, achieving a comparable cost of 5.2 gradient evaluations on the Poly25 set where the sole failure was attributable to the FSM interpolation

4 Discussion

The systematic benchmarking of algorithm–MLIP combinations across organic and organometallic reactions reveals several key insights into the design of efficient hybrid workflows for auto- mated TS searches. Most fundamentally, the choice of reaction- path algorithm has a more profound impact on search reliabil- ity than the choice of MLIP. The FSM achieved success rates of 88.9% and 90.3% on the Baker and Sharada sets, respectively, compared to 70.8% and 62.0% for the CI-NEB method on the Baker and Sharada sets, respectively (Appendix A), when aver- aged over all six potentials. This performance gap persisted even after low-level refinement, indicating that the algorithmic differ- ences in how initial guesses are generated, rather than their sub- sequent local optimization, largely determines whether the down- stream DFT P-RFO converges to the correct saddle point. In cases where the CI-NEB method successfully located a viable path, the resulting TS search converged quickly and yielded TS geometries and barrier heights comparable in accuracy to those obtained via FSM. The relative performance of the CI-NEB method may be strongly implementation dependent, and improved interpolation or optimization heuristics could reduce the observed gap in per- formance. Among the MLIPs evaluated, the systematic advantage of OMol25-trained models (MACE-OMol25, UMA-M, UMA-S, eSEN-S) over alternative potentials (GFN2-xTB, AIMNet2) is striking. Across 29 unique reactions from the Baker and Sharada sets, the OMol25 models were successful in 91.8% of searches with an average cost of 11.7 DFT gradient evaluations compared

Journal Name, [year], [vol.],1–20 | 12


![image_10](images/image_0010.jpeg)


## 第 13 页

rather than the potential. In contrast, UMA-M showed superior performance for transition-metal reactions, including both the near-in-distribution MOBH35 systems and the out-of-distribution rhodium-catalyzed C–H activation case. This improvement reflects UMA-M’s broader training data, which includes metal- surface and metal-adsorbate configurations from the OC2036

points found correspond to chemically-distinct transformations. For a native search to succeed, the FSM must generate a geom- etry whose largest imaginary mode corresponds to the transfor- mation of interest. Low-level refinement on the MLIP or SE-DFT potential introduces additional error to this process in two ways. First, Sella constructs an approximate Hessian that deviates from the exact one, even when derived from DFT gradient evaluations. Second, when that approximate Hessian is computed from an MLIP, model specific curvature errors can distort the relative or- dering of the imaginary modes. In test cases such as reaction 11 of the Baker set (ethane dehydrogenation), where several first-order saddle points are geometrically similar, this misranking redirects the optimizer toward an incorrect transition state. To isolate the source of error, refinement using the Sella Python package was repeated using ωB97X-V/def2-TZVP gradients on the same FSM UMA-M native guess. The subsequent high-level refinement in Q-Chem successfully located the reference saddle point in two optimization cycles, confirming that the failure arises from Hes- sian inaccuracy in the UMA-M model rather than from the re- finement algorithm itself. Diagonalization of the UMA-M finite- difference Hessian for the native guess yielded imaginary frequen- cies of 3969i, 949i, and 762i cm−1, compared to 2343i, 843i, and 598i cm−1 at ωB97X-V/def2-TZVP level of theory demonstrating substantial curvature distortion at the guess geometry that drives convergence toward an alternate saddle point. A second systematic failure was observed for reaction 24 of the Baker set, (HCNH2 →HCN + H2). All native searches with OMol25 trained models located the reference saddle point (Fig- ure 4H, whereas low-level-refined guesses (4F) converged to the same higher-energy second-order saddle point (Figure 4A). Be- cause eSEN-S, UMA-M, UMA-S, MACE-OMol25 all produced iden- tical outcomes, the MACE-OMol25 run serves as a representa- tive search. At the ωB97X-V/def2-TZVP level of theory, the na- tive guess (4E) exhibited a single imaginary mode of 2075i cm−1, while the MACE-OMol25 model predicted two modes of 1995i and 500i cm−1. The presence of this secondary imaginary mode indi- cates significant Hessian error: the RS-P-RFO procedure attempts to maximize the largest mode while minimizing all others, and the secondary mode skews the step direction, leading to conver- gence on a higher-energy second-order saddle point (Figure 4G). This failure also arises due to the use of approximate Hessian up- date heuristics. The P-RFO optimizer as implemented in Q-Chem employs the Powell–Murtagh–Sargent update scheme to approx- imate the Cartesian Hessian at new geometries as optimization proceeds.46,59 In this approximate Hessian, the secondary mode is eliminated during optimization and once the optimization con- vergence criteria are satisfied, the optimization terminates. A fi- nal full Hessian calculation at the optimized geometry restores the missing mode and reveals the error in the approximate Hessian. This behavior underscores the sensitivity of the P-RFO algorithm to inaccuracies in the Hessian due to either approximation or un- derlying model error.

and OC2258 in addition to the OMol25 molecular dataset, ex- posing the model to a wider range of metal-ligand coordination environments and oxidation states. Taken together, these results indicate that MLIP-accelerated transition-state searches based on algorithms such as the FSM with low-level refinement workflow are already suitable for high throughput studies. For small organic reactions, these models achieve near-DFT reliability at a fraction of the cost. For more complex transition-metal systems, UMA-M demonstrated promis- ing transferability, but it should still be applied with caution, as capturing the complexities of spin or charge re-organization along reaction coordinates remains a difficult task for current algorithms and models. For well-covered areas of chemical space such as small organic and closed-shell polymerization reactions, the demonstrated reliability and low cost of these workflows made them suitable for high-throughput screening, where approximate barrier heights can be obtained rapidly from MLIP-refined geometries with DFT single-point corrections ap- plied as needed. For transition metal systems, MLIP-optimization substantially reduces the initial cost of mechanistic exploration, but DFT validation of the final saddle point remains essential given the higher error observed in select cases.

4.1 Current limitations/Failure Mode analysis

4.1.1 Failure Modes Introduced by Low-Level Refinement

Several of the observed failures represent near-miss cases, such as the low-level-refined UMA-S and UMA-M searches on reaction 11, (ethane dehydrogenation). The native guesses from UMA- S and UMA-M (Shown in Figure 4A) converge to the reference saddle point (Figure 4D) which has an imaginary frequency of 2267i cm−1. Low-level refinement on the UMA-S and UMA-M sur- faces results in the structure shown in Figure 4B, which when in- put to the high-level DFT refinement, results in convergence to a saddle point that lies approximately 8 kcal · mol−1 higher in en- ergy, and has an imaginary frequency of 2130i cm−1 shown in 4C. IRC calculations at the ωB97X-V/def2-TZVP level of theory vali- dated that this higher energy saddle point corresponds to correct transformation via an alternate mechanism; symmetric dissocia- tion of the Hydrogen atoms. In contrast, the lower energy, ref- erence saddle point undergoes an asymmetric dissociation of the Hydrogen atoms. A similar near-miss occurred for the UMA-M refined search on reaction 16 (Claisen rearrangement). The located saddle-point had an imaginary frequency of 532i cm−1 and was 43 kcal·mol−1

higher in energy than the reference saddle point, which had an imaginary frequency of 633i cm−1. IRC calculations reveal the higher energy saddle point corresponds to a similar transforma- tion wherein both reactant and product states are in a higher- energy cis configuration. In many other cases the off-target saddle

4.1.2 General failure modes

Beyond the refinement-specific failures analyzed above, sev- eral additional failure mechanisms were observed that are

Journal Name, [year], [vol.],1–20 | 13


## 第 14 页

Fig. 4 Native guesses, low-level refined structures, and corresponding converged ωB97X-V/def2-TZVP transition states for reactions 11 (CH3CH3 → CH2CH2 + H2) and 24 (HCNH2 →HCN + H2) of the Baker set using FSM with UMA-M. (A) Native MLIP guess for reaction 11. (B) Low-level-refined MLIP structure for reaction 11. (C) Higher-energy saddle point obtained from (B) after DFT refinement. (D) Reference transition state for reaction 11 at the ωB97X-V/def2-TZVP level. (E) Native MLIP guess for reaction 24. (F) Low-level-refined MLIP structure for reaction 24. (G) Higher-energy second-order saddle point obtained from (F) after DFT refinement. (H) Reference transition state for reaction 24 at the ωB97X-V/def2-TZVP level.

not attributable to the low-level refinement step. The most common involved convergence to a local minimum rather than the intended first-order saddle point, typically occurring when the initial guess lay outside the basin of attraction of the target transition state. A related behavior was convergence to alternate first-order saddle points corresponding to different chemical transformations, as observed in reaction 5 (cyclopropyl ring-opening) and reaction 6 (bicyclo[1.1.0]butane rearrange- ment) of the Baker set. A smaller subset of failures originated from numerical issues during Q-Chem P-RFO refinement itself. These included self-consistent field (SCF) convergence failures, internal-coordinate breakdowns when the delocalized coordinate system became ill-defined (as observed for reaction 22 of the Baker set with CI-NEB and MACE-OMol25), and fatal optimiza- tion errors in the P-RFO step, typically failure to determine appropriate step size.

also with a 100% success rate. The key distinction in the present work is that the MLIP bears the entire computational burden of the reaction path finding step, with DFT only employed only for the final P-RFO refinement. Incorporation of low-level refinement on the MLIP surface dramatically reduced the overall DFT cost of the search. MACE- OMol25-refined searches achieved a 95.8% success rate and re- quired only 2.9 gradient evaluations on Baker, a 96% reduction relative to the full DFT search and a 79% reduction in required DFT gradient calls during high-level TS refinement alone. Sim- ilar improvements were observed on the Sharada set; MACE- OMol25 maintains a 100% success rate while averaging 5.7 gra- dient evaluations, a 94% and 81% reduction relative to the full DFT searches and DFT high-level TS refinement step respectively. Notably, the DFT costs of native workflows are comparable to the P-RFO refinement step alone in the all-DFT searches, demonstrat- ing that replacing DFT FSM calculations with MLIP evaluations eliminates the majority of the computational expense while in- curring only a minor loss in reliability. Recent work by Hait et al. 50 proposed an alternative MLIP- based approach using geodesic path construction on the eSEN-S- sm-cons MLIP surface.50 Their method globally optimizes densely discretized paths (typically ∼40 nodes), requiring hundreds of MLIP gradient evaluations before final P-RFO refinement in Q- Chem. Applied to the Sharada benchmark, this approach suc- cessfully generated viable transition-state guesses for all nine re- actions, all of which converged to reference transition states in ∼30% fewer P-RFO iterations than those from DFT-FSM calcu- lations run natively in Q-Chem. In comparison, we find that the MACE-OMol25 model outperforms UMA and eSEN-S models on small organic systems, achieving a 100% success rate on the

4.2 Literature comparison To contextualize the efficiency gains afforded by the MLIP- accelerated workflow, we compared our results directly to previous benchmarks of the FSM with redundant-internal- coordinate interpolation that used DFT for both the reaction-path finding and the subsequent TS refinement.17 This comparison is particularly informative because both studies employ identical reactant and product geometries for the Baker and Sharada benchmark sets and use the same ωB97X-V/def2-TZVP level of theory for P-RFO TS refinement. In the all-DFT FSM workflow, transition-state searches on the Baker set required an average of 73 total gradient evaluations (59 for the FSM and 14 for the P-RFO) with 100% success rate, while the Sharada set required 90 gradient evaluations (60 for the FSM and 30 for the P-RFO),

Journal Name, [year], [vol.],1–20 | 14


![image_11](images/image_0011.png)


## 第 15 页

Sharada set when performing local refinement with the MACE- OMol25 surface, at an average cost of 5.7 gradient evaluations, compared to the average of 16.7 for the geodesic method. The geodesic framework would likely benefit from integration with MACE-OMol25, as the model’s improved accuracy across organic systems could further reduce computational cost. A practical consideration concerns the assumption that MLIP gradients are computationally negligible. While reasonable for small systems and moderate-scale studies, this assumption weak- ens for larger systems or high-throughput campaigns. The more computationally intensive geodesic optimization appears to pro- vide improved reliability for challenging cases, where truncated path optimization of the FSM approaches may lead to failed TS searches. Both frameworks clearly demonstrate that well-trained MLIPs can produce transition-state guesses of sufficient accuracy to reduce DFT cost by one to two orders of magnitude relative to conventional ab initio workflows.

non-OMol25 potentials. For small organic systems, MACE-OMol25 combined with low- level refinement provides optimal performance, locating refer- ence transition states in 96.6% of attempts while requiring an average of only 3.8 DFT gradient evaluations, a 94–96% reduc- tion compared to conventional all-DFT workflows. For transition metal containing systems, UMA-M demonstrated superior trans- ferability, successfully handling both near-distribution test cases drawn from the MOBH35 benchmarks and the out-of-distribution rhodium-catalyzed C–H activation system. Low-level refinement on the MLIP surface before high-level DFT optimization emerged as a critical workflow component, reducing average DFT costs by approximately three fold, while maintaining success rates. For organic systems, the modest reliability decrease observed with low-level refinement arose from MLIP curvature errors that can redirect optimization toward alternate saddle points, particularly when multiple geometrically similar saddle points exist. For transition-metal systems, the primary challenges were convergence during high-level refine- ment and sensitivity to the quality of the initial-guess geometry, reflecting the greater complexity of these systems. These results demonstrate that MLIP-accelerated transition- state searches have matured to the point of practical deployment for high-throughput mechanistic studies. The workflows achieve near-DFT reliability for organic and closed-shell polymeriza- tion reactions while enabling orders-of-magnitude speedups. For transition-metal systems, current models show promise but require continued development. Given the demonstrated reliability and negligible computational cost of MLIP-based reaction-path finding relative to DFT, we recommend that MLIP pre-optimization with models such as MACE-OMol25 and UMA- M be adopted as the default first stage in transition-state-search workflows, replacing semi-empirical or low-level DFT methods for this purpose. The demonstrated efficiency and scalability of these hybrid workflows opens new possibilities for computational exploration of complex reaction networks in catalysis, materials synthesis, and synthetic chemistry.

4.3 Future Directions for Improvement Several of the observed error modes originated from errors in the local curvature information. Improved Hessian information offers a direct path forward. The computational efficiency of MLIPs makes it practical to evaluate full Hessians at each optimization step for methods such as RS-P-RFO and P-RFO, which has been shown to improve convergence reliability and efficiency.60 Emerging techniques for rapid Hessian evalua- tion through automatic differentiation promise to make these approaches model-agnostic and inexpensive.61 Their success, however, depends on the underlying MLIP producing physically meaningful second derivatives. A complementary direction is the development of reaction path-finding algorithms and MLIPs capable of handling variable spin and charge states along the reaction coordinate. Many catalytic and redox processes such as the catalyzed oxidation of methanol on titania-supported oxide catalysts62,63 involve transitions between electronic states that require multi-reference treatment and cannot be described on a single PES. Extending MLIP-based workflows to such systems will require both models accurate across electronic states and reaction-path methods capable of switching between electronic states.

Author contributions

Jonah Marks: Conceptualization, methodology, software, inves- tigation, formal analysis, data curation, writing – original draft, visualization, editing. Jonathon Vandezande: Methodology, resources (Poly25 dataset) writing – review & editing. Joseph Gomes: Conceptualization, methodology, supervision, funding acquisition, resources, writing – review & editing.

5 Conclusions

This work provides a systematic benchmarking of modern MLIPs and demonstrates that, when coupled with appropriate reaction-path and refinement algorithms, these models enable reliable and efficient automated TS searches across broad areas of chemical space at a fraction of the computational cost of DFT. Through systematic benchmarking of 24 algorithm–potential combinations across 58 diverse reactions, we demonstrate that the choice of reaction-path algorithm fundamentally determines search reliability: the FSM achieved 88–90% success rates compared to 63–71% for the CI-NEB implementation tested here. Among MLIPs, models trained on the OMol25 dataset (MACE- OMol25, UMA-M, UMA-S, eSEN-S) systematically outperformed alternatives, achieving 91.8% success compared to 84.5% for

Conflicts of interest

J.E.V. is an employee of the Rowan Scientific Corporation, which is commercializing the ML-FSM code used in this paper. All other authors declare no competing interests.

Data availability

The data supporting this study, including input geometries and scripts used to perform the transition state benchmarking calcu- lations, will be made publicly available in a GitHub repository upon publication of this work and archived with a DOI.

Journal Name, [year], [vol.],1–20 | 15


## 第 16 页

Acknowledgements

M. R. Hasyim, K. Michel, I. Batatia, G. Csányi, M. Dzamba, P. Eastman, N. C. Frey, X. Fu, V. Gharakhanyan, A. S. Krish- napriyan, J. A. Rackers, S. Raja, A. Rizvi, A. S. Rosen, Z. Ulissi, S. Vargas, C. L. Zitnick, S. M. Blau and B. M. Wood, arXiv preprint arXiv:2505.08762, 2025.

J.G acknowledges start up funding from The University of Iowa. This research was supported in part through computational re- sources provided by The University of Iowa.

References

23 M. Schreiner, A. Bhowmik, T. Vegge, P. B. Jørgensen and O. Winther, Mach. Learn.: Sci. Technol., 2022, 3, 045022.

1 C. A. Grambow, L. Pattanaik and W. H. Green, J. Phys. Chem. Lett., 2020, 11, 2992–2997.

24 B. Wander, M. Shuaibi, J. R. Kitchin, Z. W. Ulissi and C. L. Zitnick, ACS Catal., 2025, 15, 5283–5294.

2 M. Z. Makos, N. Verma and E. C. Larson, J. Chem. Phys., 2021, 024116.

25 Q. Zhao, Y. Han, D. Zhang, J. Wang, P. Zhong, T. Cui, B. Yin, Y. Cao, H. Jia and C. Duan, Adv. Sci., 2025.

3 S. Heinen, G. F. von Rudorff and O. A. von Lilienfeld, J. Chem. Phys., 2021, 155, 064105.

26 J. Marks and J. Gomes, arXiv preprint arXiv:2501.06159, 2025.

4 K. A. Spiekermann, L. Pattanaik and W. H. Green, J. Phys. Chem., 2022, 126, 3976–3986.

27 M. A. Iron and T. Janes, J. Phys. Chem. A, 2019, 123, 3761– 3781.

5 P. van Gerwen, K. R. Briling, C. Bunne, V. R. Somnath, R. Laplaza, A. Krause and C. Corminboeuf, J. Chem. Inf. Model., 2024, 64, 5771–5785.

28 M. Bursch, J.-M. Mewes, A. Hansen and S. Grimme, Angew. Chem., 2022, 134, e202205735.

29 A. H. Larsen, J. J. Mortensen, J. Blomqvist, I. E. Castelli, R. Christensen, M. Dułak, J. Friis, M. N. Groves, B. Hammer, C. Hargus et al., J. Phys.:Condens. Matter, 2017, 29, 273002.

6 C. Duan, G. H. Liu, Y. Du, T. Chen, Q. Zhao, H. Jia, C. P. Gomes, E. A. Theodorou and H. J. Kulik, Nat. Mach. Intell., 2025, 7, 615–626.

30 E. D. Hermes, K. Sargsyan, H. N. Najm and J. Zádor, J. Chem. Theory Comput., 2019, 15, 6536–6549.

7 H. C. Chang, M. H. Tsai and Y. P. Li, J. Chem. Inf. Model., 2025, 65, 1367–1377.

31 E. D. Hermes, K. Sargsyan, H. N. Najm and J. Zádor, J. Chem. Theory Comput., 2022, 18, 6974–6988.

8 B. Peters, A. Heyden, A. T. Bell and A. Chakraborty, J. Chem. Phys, 2004, 120, 7877–7886.

32 D. C. Liu and J. Nocedal, Math. Program., 1989, 45, 503–528. 33 R. H. Byrd, P. Lu, J. Nocedal and C. Zhu, SIAM J. Sci. Comput., 1995, 16, 1190–1208.

9 A. Behn, P. M. Zimmerman, A. T. Bell and M. Head-Gordon, J. Chem. Phys., 2011, 135, 224108.

10 S. M. Sharada, P. M. Zimmerman, A. T. Bell and M. Head- Gordon, J. Chem. Theory Comput., 2012, 8, 5166–5174.

34 P. Virtanen, R. Gommers, T. E. Oliphant, M. Haber- land, T. Reddy, D. Cournapeau, E. Burovski, P. Peterson, W. Weckesser, J. Bright et al., Nat. Methods, 2020, 17, 261– 272.

11 P. M. Zimmerman, J. Chem. Phys., 2013, 138, 184102. 12 M. Jafari and P. M. Zimmerman, J. Comput. Chem., 2017, 38, 645–658.

35 C. Bannwarth, S. Ehlert and S. Grimme, J. Chem. Theory Com- put., 2019, 15, 1652–1671.

13 G. Mills and H. Jónsson, Phys. Rev. Lett., 1994, 72, 1124. 14 G. Henkelman and H. Jónsson, J. Chem. Phys., 2000, 113, 9978–9985.

36 L. Chanussot, A. Das, S. Goyal, T. Lavril, M. Shuaibi, M. Riv- iere, K. Tran, J. Heras-Domingo, C. Ho, W. Hu et al., ACS Catal., 2021, 11, 6059–6072.

15 G. Henkelman, B. P. Uberuaga and H. Jonsson, J. Chem. Phys., 2000, 113, 9901–9904.

37 L. Barroso-Luque, M. Shuaibi, X. Fu, B. M. Wood, M. Dzamba, M. Gao, A. Rizvi, C. L. Zitnick and Z. W. Ulissi, arXiv preprint arXiv:2410.12771, 2024.

16 D. Sheppard, R. Terrell and G. Henkelman, J. Chem. Phys, 2008, 128, 134106.

17 J. Marks and J. Gomes, J. Chem. Theory Comput., 2025, 21, 12110–12120.

38 A. Sriram, S. Choi, X. Yu, L. M. Brabson, A. Das, Z. Ulissi, M. Uyttendaele, A. J. Medford and D. S. Sholl, ACS Cent. Sci., 2024, 10, 923–941.

18 D. M. Anstine, R. Zubatyuk and O. Isayev, Chem. Sci., 2025, 16, 10228–10244.

39 E. Epifanovsky, A. T. Gilbert, X. Feng, J. Lee, Y. Mao, N. Mardirossian, P. Pokhilko, A. F. White, M. P. Coons, A. L. Dempwolff et al., J. Chem. Phys., 2021, 155, 084801.

19 I. Batatia, D. P. Kovács, G. Simm, C. Ortner and G. Csányi, Adv. Neural Inf. Process. Syst., 2022, 35, 11423–11436.

20 X. Fu, B. M. Wood, L. Barroso-Luque, D. S. Levine, M. Gao, M. Dzamba and C. L. Zitnick, Proc. Mach. Learn. Res., 2025, 267, 17875–17893.

40 N. Mardirossian and M. Head-Gordon, Phys. Chem. Chem. Phys., 2014, 16, 9904–9924.

41 F. Weigend and R. Ahlrichs, Phys. Chem. Chem. Phys., 2005, 3297–3305.

21 B. M. Wood, M. Dzamba, X. Fu, M. Gao, M. Shuaibi, L. Barroso-Luque, K. Abdelmaqsoud, V. Gharakhanyan, J. R. Kitchin, D. S. Levine, K. Michel, A. Sriram, T. Cohen, A. Das, S. J. Sahoo, A. Rizvi, Z. W. Ulissi and C. L. Zitnick, Adv. Neural Inf. Process. Syst., 2025.

42 S. Dasgupta and J. M. Herbert, J. Comput. Chem., 2017, 38, 869–882.

43 J. Baker, J. Comput. Chem., 1986, 7, 385–395. 44 M. W. Schmidt, M. S. Gordon and M. Dupuis, J. Am. Chem. Soc., 1985, 107, 2585–2589.

22 D. S. Levine, M. Shuaibi, E. W. C. Spotte-Smith, M. G. Taylor,

Journal Name, [year], [vol.],1–20 | 16


## 第 17 页

45 E. D. Hermes, K. Sargsyan, H. N. Najm and J. Zádor, J. Chem. Phys., 2021, 155, 094105.

reaction coordinate as a series of intermediate geometries or images {Ri}, connecting reactant and product structures.13,14,16

In contrast to more common IDPP-based interpolation schemes, the initial reaction path in this work was constructed using internal coordinates, which better preserve realistic bonding en- vironments for molecular systems.17 Adjacent images are linked by spring constants of magnitude k enforcing approximately equal spacing along the path, while interatomic forces from the potential-energy function optimize each node perpendicular to the path tangent. For each image i the total force

46 B. A. Murtagh and R. W. Sargent, Comput. J., 1970, 13, 185– 194.

47 J. Baker and F. Chan, J. Comput. Chem., 1996, 17, 888–904. 48 A. Heyden, A. T. Bell and F. J. Keil, J. Chem. Phys., 2005, 123, 224101.

49 J. Kästner and P. Sherwood, J. Chem. Phys., 2008, 128, 014106.

50 D. Hait, J. D. Estrada Pabon, M. Stohr and T. J. Martínez, J. Chem. Theory Comput., 2025, 21, 11632–11644.

Fi = F⊥ i +F∥ i (3)

51 T. A. Halgren and W. N. Lipscomb, Chem. Phys. Lett., 1977, 49, 225–232.

is decomposed into perpendicular and parallel components:

52 S. Maeda, Y. Harabuchi, M. Takagi, T. Taketsugu and K. Mo- rokuma, Chem. Rec., 2016, 16, 2232–2248.

F⊥ i = −∇V(Ri)+[∇V(Ri)· ˆτi]ˆτi (4)

53 J. Zakzeski, A. Behn, M. Head-Gordon and A. T. Bell, J. Am. Chem. Soc., 2009, 131, 11098–11105.

F∥ i = k(|Ri+1 −Ri|−|Ri −Ri−1|)· ˆτi (5)

54 F. Liu, G. Luo, Z. Hou and Y. Luo, Organometallics, 2017, 36, 1557–1565.

where ∇V denotes the gradient of the potential energy and ˆτi is the normalized local tangent at image i. The climbing-image nudged elastic band (CI-NEB) variant was employed to determine saddle-point geometries, avoiding the computational cost associated with Hessian calculations required for local surface-walking algorithms.15 In this approach, once the NEB method converges to a specified force threshold, the highest energy image j is identified and optimized along the reaction coordinate to ascend directly to the transition state. The spring force is removed for this image, and its parallel force component is inverted, yielding:

55 D. E. Prokopchuk and R. H. Morris, Organometallics, 2012, 31, 7375–7385.

56 M. A. Iron, J. M. Martin and M. E. V. der Boom, J. Am. Chem. Soc., 2003, 125, 13020–13021.

57 A. Sriram, A. Das, B. M. Wood, S. Goyal and C. L. Zitnick, Proc. Int. Conf. Learn. Represent., 2022.

58 R. Tran, J. Lan, M. Shuaibi, B. M. Wood, S. Goyal, A. Das, J. Heras-Domingo, A. Kolluru, A. Rizvi, N. Shoghi et al., ACS Catal., 2023, 13, 3066–3084.

59 M. J. Powell, Math. Program., 1971, 1, 26–57. 60 E. C.-Y. Yuan, A. Kumar, X. Guan, E. D. Hermes, A. S. Rosen, J. Zádor, T. Head-Gordon and S. M. Blau, Nat. Commun., 2024, 15, 8865.

FCI j = −∇V(Rj)+2[∇V(Rj)· ˆτj]ˆτ (6)

This drives the image uphill along the path while continuing to relax in the perpendicular direction. To ensure robust convergence CI-NEB calculations were per- formed in two sequential steps. First, the path was optimized using the standard NEB method until the maximal perpendicu- lar force to the MEP fell below 0.5 eV·Å−1. Subsequently, start- ing from this relaxed path, the CI-NEB method was then applied until full convergence was achieved with maximal perpendicular forces below 0.05 eV Å−1 (approximately 3 × 10−3 Ha·Bohr−1). All calculations employed seven nodes along each reaction path with spring constants of 0.1 eV·Å−1, using the adaptive step-size- preconditioned NEB optimizer64 as implemented in ASE.29

61 A. Burger, L. Thiede, N. Rønne, V. Bernales, N. Vijaykumar, T. Vegge, A. Bhowmik and A. Aspuru-Guzik, arXiv preprint arXiv:2509.21624, 2025.

62 J. L. Bronkema, D. C. Leo and A. T. Bell, J. Phys. Chem. C, 2007, 111, 14530–14540.

63 A. Goodrow and A. T. Bell, J. Phys. Chem. C, 2008, 112, 13204–13214.

64 S. Makri, C. Ortner and J. R. Kermode, J. Chem. Phys., 2019, 150, 094109.

A Appendix A: Nudged Elastic Band Experiments

A.1 Methods The Nudged Elastic Band (NEB) method locates minimum-energy pathways and approximate transition states by representing the

Journal Name, [year], [vol.],1–20 | 17


## 第 18 页

systems suggest this implementation of CI-NEB is intrinsically less robust for generating transition-state guesses suitable for high- level DFT optimization. Nevertheless, the low computational cost is noteworthy: when the CI-NEB method does succeed the result- ing geometry is often nearly identical to the reference transition state, effectively precluding the need for additional low-level re- finement.

A.2 Experiments The CI-NEB method exhibited substantially lower success rates than the FSM (Section 3.1.1) across both native and low-level- refined workflows. On the Baker benchmark, the CI-NEB method succeeded on only 70.8% of reactions across both workflows. The corresponding average gradient evaluations were 5.6 for native searches and 4.3 for low-level-refined searches, indicating that pre-optimization on the low-level surface does not appreciably lower the downstream high-level refinement cost. This is due to the climbing-image formulation itself, which explicitly maxi- mizes the energy of the highest node in the path. On the Sharada benchmark, the CI-NEB method again showed reduced reliability: across nine reactions, it succeeded on 63% of native searches and 61.1% of low-level-refined searches. The average cost of the suc- cessful runs was 12.6 and 8.0 gradient evaluations, respectively. CI-NEB guesses frequently converged to local minima rather than the target transition state, or failed to converge within 250 optimization cycles of the high-level P-RFO. These failure modes are examined in greater detail in 4. Representative examples include reactions 7 (formyloxyethyl migration), 8 (Diels–Alder cycloaddition), and 15 (H2O + PO− 3 →H2PO− 4 ) of the Baker set. Although the overall performance reflects both the algorith- mic strategy, underlying PES, and P-RFO performance, the con- sistently higher success rates achieved by the FSM on these same

A.3 Comparison to the ML-FSM Across both benchmark sets a clear algorithmic difference emerges: the FSM consistently outperformed the CI-NEB method in success rate, while achieving a comparable or lower cost when using the low-level refinement. The FSM maintained a high success rate across all reactions and potentials, with no reactions failing for all potentials and workflows attempted. In contrast, the CI-NEB method exhibited lower success rates, with more frequent convergence to local minima or off-target saddle points. The CI-NEB searches fail to produce a transition-state guess that converges to the reference saddle point for reactions 8 (Diels–Alder cycloaddition) and 22 (HNC + H2 →H2CNH) of the Baker set. These results demonstrate that the FSM provides a more reliable and computationally efficient framework for generating transition-state guesses. Consequently, the FSM is exclusively used in subsequent benchmark sets and case studies.

Journal Name, [year], [vol.],1–20 | 18


## 第 19 页

Table 5 Comparison of performance of GFN2-xTB, AIMNet2, eSEN-S, UMA-S, UMA-M, MACE-OMol25 for native and low-level-refined guess generation via the CI-NEB method on the Baker set. Performance is measured by successful convergence to the reference transition state, and the number of DFT gradient evaluations required. Italicized values denote failed runs, with superscripts denoting the failure mode.

(a) Converges to an alternate first-order saddle point. (b) Converges to local-minimum structure. (c) Converges to correct TS with spurious imaginary frequency additional cost to eliminate frequency via tighter P-RFO convergence parameters was added. (d) Fails to converge P-RFO within 250 optimization cycles. (e) SCF Convergence error. (f) Converges to structure with multiple strong (> 200 cm−1) imaginary frequencies. (g) P-RFO optimization step failure. (h) Q-Chem internal coordinates back transformation failure.

GFN2-xTB AIMNet2 eSEN-S UMA-S UMA-M MACE-OMol25 Native Low-level Native Low-level Native Low-level Native Low-level Native Low-level Native Low-level Reaction refined refined refined refined refined refined

Success Rate 70.8% 75.0% 70.8% 66.7% 75.0% 75.0% 66.7% 70.8% 70.8% 70.8% 70.8% 66.7% Mean Success Cost 7.2 7.2 10.9 6.5 3.8 3.0 3.7 3.3 4.0 3.3 3.9 2.8

10. trans-butadiene →cis-butadiene 4 4 4 4 4 3 4 2 4 2 4 2 11. CH3CH3 →CH2CH2 + H2 213a 250d 35 175a 3 3 154a 39a 3 3 250d 138a

1. HCN →HNC 4 4 4 4 2 2 3 3 2 2 2 2 2. HCCH →CCH2 4 5 3 3 2 2 2 2 2 2 2 3 3. H2CO →H2 + CO 5 5 12 14 2 2 11b 12b 38a 37a 2 2 4. CH3O →CH2OH 4 4 15 14 3 3 3 3 3 3 3 3 5. cyclopropyl ring opening 4 5 11a 7a 3 3 4 3 3 3 12 3 6. bicyclo[1.1.0]butane →trans-butadiene 19 14 27b 4a 4 4 4 4 4 3 3 4 7. formyloxyethyl 1,2-migration 8 8 24b 4b 107b 154b 250d 188b 81e 241b 166b 250d

9. s-tetrazine →2HCN + N2 12 12 4 4 74 f 49a 101 f 4 74 f 139a 108 f 177 f

12. CH3CH2F →CH2CH2 + HF 9 8 4 4 3 2 3 2 2 2 3 2 13. acetaldehyde keto-enol tautomerism 5 5 4 4 3 2 3 2 3 2 3 2 14. HCOCl →HCl + CO 6 6 4 4 2 2 2 2 2 2 2 2 15. H2O + PO− 3 →H2PO− 4 250d 250d 250d 1g 250d 37b 250d 250d 250d 250d 157b 20b

8. parent Diels–Alder cycloaddition 17b 167b 250d 250d 250d 250d 250d 250d 71b 62b 79b 5b

16. CH2CHCH2CH2CHO Claisen rearrangement 8 7 4 6 3 3 3 3 3 2 3 3 17. SiH2 + CH3CH3 →SiH3CH2CH3 16 15 10 8 5 4 5 5 8 4 5 4 18. HNCCS →HNC + CS 5g 107b 2 2 3 3 3 3 3 3 3 2 19. HCONH+ 3 →NH+ 4 + CO 3g 9 61c 14b 10 9 10 10 10 9 9 1g

23. H2CNH →HCNH2 3 f 3f 5f 13 9 2 3 2 9 9 2 f 2f

20. acrolein rotational TS 4 4 3 3 3 2 3 3 3 2 3 3 21. HCONHOH →HCOHNHO 6 10 7 7 4 3 4 3 4 3 4 3 22. HNC + H2 →H2CNH 7a 7a 76b 57b 2a 2a 3a 3a 2a 2a -h -h

24. HCNH2 →HCN + H2 4 4 9 10 17a 3a 17a 2a 21 f 250d 4 4

Journal Name, [year], [vol.],1–20 | 19


## 第 20 页

Table 6 Comparison of performance of GFN2-xTB, AIMNet2, eSEN-S, UMA-S, UMA-M, MACE-OMol25 for native and low-level-refined guess generation via the CI-NEB method on the Sharada set. Performance is measured by successful convergence to the reference transition state, and the number of DFT gradient evaluations required. Italicized values denote failed runs, with superscripts denoting the failure mode.

GFN2-xTB AIMNet2 eSEN-S UMA-S UMA-M MACE-OMol25 Native Low-level Native Low-level Native Low-level Native Low-level Native Low-level Native Low-level Reaction refined refined refined refined refined refined

(a) Converges to an alternate first-order saddle point. (b) Converges to local-minimum structure. (c) Converges to correct TS with spurious imaginary frequency additional cost to eliminate frequency via tighter P-RFO convergence parameters was added. (d) Fails to converge P-RFO within 250 optimization cycles. (e) SCF Convergence error. (f) Converges to structure with multiple strong (> 200 cm−1) imaginary frequencies. (g) P-RFO optimization step failure.

Success Rate 55.6% 55.6% 44.4% 33.3% 77.8% 77.8% 55.6% 66.7% 77.8% 66.7% 66.7% 66.7% Mean Success Cost 16.2 12.8 23.3 11.3 4.9 3.7 7.2 14.8 21.0 4.2 6.0 4.3

1. H2CO →H2 + CO 5 5 12 14 2 2 11b 12b 38a 37a 2 2 2. SiH2 + H2 →SiH4 22 27 26b 22b 5 4 5 5 5 4 5 4 3. CH2CHOH ↔CH3CHO 5 5 4 4 3 2 3 2 3 2 3 2 4. CH3CH3 →CH2CH2 + H2 213a 250b 35 175a 3 3 154a 39a 3 3 250d 138a

7. cis,cis-2,4-hexadiene ↔3,4-dimethylcyclobutene 15b 12b 250d 250d 3 3 3 3 3 3 3 3 8. C5 ↔C7AX 30 13 42 16c 14 8 21 10 14 10 20 11 9. silyl ketene acetal →silyl ester Ireland–Claisen rearrangement 62b 51b 57b 54b 53b 54b 250d 65 115 250d 58b 59b

5. bicyclo[1.1.0]butane →trans-butadiene 19 14 27b 4a 4 4 4 4 4 3 3 4 6. parent Diels–Alder cycloaddition 17b 167b 250d 250d 250d 250d 250d 250d 71b 62b 79b 5b

Journal Name, [year], [vol.],1–20 | 20
