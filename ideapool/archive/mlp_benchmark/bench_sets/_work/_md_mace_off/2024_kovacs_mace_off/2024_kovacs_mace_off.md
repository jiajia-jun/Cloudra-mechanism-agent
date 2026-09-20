
## 第 1 页

MACE-OFF: Short Range Transferable Machine Learning Force Fields for Organic Molecules

D´avid P´eter Kov´acs†,1 J. Harry Moore†*,1, 2 Nicholas J. Browning,3 Ilyes Batatia,1 Joshua T. Horton,4 Yixuan Pu,5 Venkat Kapil,6, 5, 7 William C. Witt,8 Ioan-Bogdan Magd˘au,4 Daniel J. Cole,4 and G´abor Cs´anyi1, 2

1Engineering Laboratory, University of Cambridge, Cambridge, CB2 1PZ, UK 2˚ Angstr¨om AI, 2325 3rd Street, San Francisco, CA 94107, USA 3Swiss National Supercomputing Centre (CSCS), 6900, Lugano, Switzerland 4School of Natural and Environmental Sciences, Newcastle University, Newcastle upon Tyne NE1 7RU, UK 5Department of Physics and Astronomy, University College, London WC1E 6BT, UK 6Yusuf Hamied Department of Chemistry, University of Cambridge, Lensﬁeld Road, Cambridge, CB2 1EW,UK 7Thomas Young Centre and London Centre for Nanotechnology, London WC1E 6BT, UK 8Department of Materials Science and Metallurgy, University of Cambridge, 27 Charles Babbage Road, CB3 0FS, Cambridge, United Kingdom (Dated: August 25, 2025)

arXiv:2312.15211v5  [physics.chem-ph]  22 Aug 2025

Abstract

Classical empirical force ﬁelds have dominated biomolecular simulation for over 50 years. Al- though widely used in drug discovery, crystal structure prediction, and biomolecular dynamics, they generally lack the accuracy and transferability required for ﬁrst-principles predictive modeling. In this paper, we introduce MACE-OFF, a series of short range transferable force ﬁelds for organic molecules created using state-of-the-art machine learning technology and ﬁrst-principles reference data computed with a high level of quantum mechanical theory. MACE-OFF demonstrates the remarkable capabilities of short range models by accurately predicting a wide variety of gas and condensed phase properties of molecular systems. It produces accurate, easy-to-converge dihedral torsion scans of unseen molecules, as well as reliable descriptions of molecular crystals and liquids, including quantum nuclear eﬀects. We further demonstrate the capabilities of MACE-OFF by de- termining free energy surfaces in explicit solvent, as well as the folding dynamics of peptides and nanosecond simulation of a fully solvated protein. These developments enable ﬁrst-principles simu- lations of molecular systems for the broader chemistry community at high accuracy and relatively low computational cost.

that empirical force ﬁelds, which sacriﬁce accuracy for computational speed, continue to be used routinely to study molecular liquids, crystals, biological systems, and drug-like molecules [19–22]. Two alternatives to empirical force ﬁelds are avail- able. The ﬁrst is semi-empirical quantum mechanics, such as the series of extended tight-binding models [23], which represents a low-cost solution for small molecules. The method is limited by its moderate accuracy com- pared to quantum chemistry methods, its restriction to modelling non-periodic systems (if not in principle, but in widely used implementations), and its cubic scaling with system size. More recently, a number of transferable machine learning force ﬁelds have also been developed for or- ganic chemistry. By “transferable”, here we mean that these potentials are capable of generalising in system size and both chemical and conformation space suﬃ- ciently well to perform stable molecular dynamics and accurate property prediction for a wide range of molec- ular systems beyond those on which the model was trained. The most notable are the series of ANI [24–27] and AIMNet potentials [8, 28, 29]. ANI potentials pi-

I. Introduction

Machine learning (ML) force ﬁelds have recently un- dergone major improvements in accuracy, robustness, and computational speed [1–13]. They are now rou- tinely used in materials chemistry contexts where den- sity functional theory was previously the method of choice. In these applications, available empirical force ﬁelds, such as the embedded-atom method [14], do not provide suﬃcient accuracy and transferability to describe many scientiﬁcally interesting and challeng- ing phenomena. Successful applications of ML poten- tials include simulation of quenching of amorphous sil- icon [15], determination of the phase diagrams of inor- ganic perovskites [16] and alloys [17], and device-scale simulation of phase-change memory materials [18]. In contrast, simulating bio-organic systems entails a diﬀerent set of trade-oﬀs, with greater emphasis on sim- ulating large systems over long timescales. This means

† These authors contributed equally. ∗Corresponding author: jhm72@cam.ac.uk


## 第 2 页

2

MACE-OFF. The force ﬁelds are parameterized for the ten most important chemical elements for organic chem- istry: H, C, N, O, F, P, S, Cl, Br, and I. They are capable of accurately describing intra- and intermolec- ular interactions of neutral closed-shell systems. This enables the simulation of a wide range of chemical sys- tems, from molecular liquids and crystals to drug-like molecules and biopolymers. The models were validated on a number of tasks, in- cluding the prediction of small molecule torsion barriers, geometry optimizations, calculations of lattice parame- ters and enthalpies of formation of molecular crystals, and the calculation of the Raman spectra of molecular crystals, including nuclear quantum eﬀects. We have also validated the models for predicting the densities and heats of vaporization of a range of molecular liq- uids. In particular, we study how well MACE-OFF re- produces the fundamental properties of water, includ- ing density and radial distribution functions. To further showcase the capabilities of the model, we computed the free energy surface and J-coupling parameters of alanine tripeptide (Ala3) in vacuum and explicit water, simu- lated the folding of Ala15 at diﬀerent temperatures, and carried out an all-atom simulation of the protein cram- bin in explicit water (18 000 atoms). Finally, we tested the computational speed of the current implementation in the LAMMPS and OpenMM simulation packages, demonstrating both strong and weak scaling. While truly general purpose force ﬁelds for biomolec- ular modeling require explicit treatment of long-range Coulomb interactions, the purpose of this paper is to push the capabilities of short-range potentials as far as they can go, in part as preparation for inclusion of ex- plicit polarizable electrostatic interactions in the future.

oneered the use of local symmetry function-based feed- forward neural networks [30] trained on a large dataset of organic molecular geometries [31, 32] to create trans- ferable ML force ﬁelds. The ANI-2x model became the most widely adopted ML force ﬁeld and therefore serves as one of the primary points of comparison in this pa- per. The ANI-2x model was recently combined with a polarizable electrostatic model [33] in a hybrid ML/MM simulation setting, and also with a neural network based dispersion correction [34]. The AIMNet models apply a message passing architecture [35], where the initial em- beddings are the ANI symmetry functions. They have also extended the applicability of the models to a larger set of chemical elements, as well as to charged species. These models relax the locality assumptions by incor- porating electrostatic and dispersion interactions. The PhysNet model uses a message passing architecture [35] and in addition to the semi-local terms also includes long-range electrostatic and dispersion interactions [36]. Other recent bio-organic force ﬁelds include the FEN- NIX model, which combines a local equivariant machine learning model with a physical long-range functional form for electrostatics and dispersion [37]. The model was trained to reproduce the CCSD(T)/CBS energies of small molecules and molecular dimers. It was shown that FENNIX can be used to run stable dynamics of liquid water, solvated alanine dipeptides, and an entire protein in the gas phase. However, further benchmark- ing of this model is required to assess the accuracy of the intramolecular potential outside the training set and of condensed phase molecular dynamics simulations. Similarly, the ANA2B potential employs a short- ranged ML potential, with long-ranged, classical mul- tipolar electrostatics, polarization and dispersion inter- actions [38]. Although this long-ranged model shows promising accuracy for condensed phase properties and crystal structure ranking, its accuracy and computa- tional performance has not yet been demonstrated for larger biomolecules. The GEMS model [39], built on the SpookyNet ar- chitecture [40], is another recent ML force ﬁeld for biomolecular simulations. Whilst a transferable ver- sion of this potential is capable of producing stable dynamics for challenging biomolecular systems, certain properties, for example the folding dynamics of small peptides, require the addition of system-speciﬁc train- ing conﬁgurations in order to accurately reproduce ex- perimental properties. More recently, the transferable SO3LR potential was introduced by the same group of researchers [41]. This is based on the equivari- ant SO3krates architecture and also includes analytic dispersion and electrostatic long range contributions. Whilst this potential is capable of fast and stable simu- lations of biomolecular systems, we are not yet aware of more extensive quantitative benchmarking on oﬀ- equilibrium energetics or thermodynamic properties. In this paper, we introduce a family of purely lo- cal (i.e. short range), transferable bio-organic machine learning force ﬁelds which we refer to collectively as

II. Methods

A. The MACE architecture

The MACE model [2] is a force ﬁeld that maps the positions and chemical elements of atoms to the sys- tem’s potential energy. Linear scaling with system size is achieved by decomposing the total energy into atomic site energies. First, a graph is deﬁned by connecting two nodes (atoms) by an edge if they are in each other’s lo- cal environment. The local environment N(i) is the set of all atoms j around the central atom i for which ∥rij∥f rcut, where rij is the vector from atom i to atom j and rcut is the cutoﬀhyperparameter. The array of features of node i is denoted by h(t) i and is expressed in the spherical harmonic basis, with its elements indexed by l and m. The superscript in t indicates the iteration steps (corresponding to “layers” of message passing in the language of graph neural networks). All MACE- OFF models are made up of two layers. The h(t) i fea- tures depend on the chemical environment of the atoms for t > 0.


## 第 3 页

3

The node features h(0) i are initialized as a (learnable) embedding of the chemical elements with atomic num- bers zi into k channels:

The recursive update of the node features (t : 0 →2) is obtained by adding the message to the atoms’ features from the previous iteration, with weights that depend on the chemical element (zi):

h(0) i,k00 = X

z Wkzδzzi (1)

h(t+1) i,kLM = X

˜k W (t) kL,˜km(t) i,˜kLM + X

˜k W (t) kziL,˜kh(t) i,˜kLM (6)

The superscript (0) in this case indicates the initial (0- th) layer. This type of mapping has been widely applied to graph neural networks [42–44] and other models [45, 46]. Next, for each atom, the features of its neighbours are combined with the interatomic displacement vec- tors, rij, to form the one-particle basis φ(t) ij,kη1l3m3. The radial distance is used as an input into a learnable radial function R(rij) with several outputs that correspond to the diﬀerent ways in which the displacement vector and the node features can be combined while preserving equivariance [47]:

Since the initial node features h(0) are only dependent on the chemical element of the atom, the second term of Eq. (6) is not included in the ﬁrst layer. This makes it possible to set the energy of the isolated atoms (that is, those with no neighbours) exactly [49], which is often desirable [37, 50]. The MACE models in this work have an eﬀective receptive ﬁeld of 2 × rcut due to the two layers of message passing. The site energy is a sum of read-out functions ap- plied to node features from the ﬁrst and second layers. The read-out function is deﬁned as a linear combina- tion of rotationally invariant node features for the ﬁrst layer, and as multi-layer perceptron (MLP) for the sec- ond layer.

l1l2m1m2 Cl3m3 η1,l1m1l2m2R(t) kη1l1l2l3(rij) ×

φ(t) ij,kη1l3m3 = X

× Y m1 l1 (ˆrij)h(t) j,kl2m2 (2)

2 X

2 X

t=1 R(t)  h(t) i  , (7)

t=1 E(t) i =

where Y m l are the spherical harmonics, and Cl3m3 η1,l1m1l2m2 denotes the Clebsch-Gordan coeﬃcients. There are multiple ways of constructing an equivariant combina- tion with a given symmetry (l3, m3), and these multi- plicities are enumerated by the index η1 [48]. The one-particle basis φ is summed over the neighbor- hood and the k channels are mixed together with learn- able weights to form the permutation invariant atomic basis Ai:

Ei =

k W (t) k h(t) i,k00 for t = 1

  

P

R(t)  h(t) i  =

 for t = 2 (8)

MLP n h(t) i,k00 o

 

k

The forces and stresses on the atoms are calculated by taking analytical derivatives of the total potential en- ergy with respect to the positions of the atoms and the components of the deformation tensor in the periodic setting, as is usual.

A(t) i,kl3m3 = X

˜k,η1 W (t) k˜kη1l3

j∈N (i) φ(t) ij,˜kη1l3m3 (3)

X

Higher-order (many-body) symmetric features are created on each atom i by taking tensor products of the atomic basis, Ai, with itself ν times, resulting in the “product basis”. The product basis is then contracted with the generalized Clebsch-Gordan coef- ﬁcients, CLM ηνlm, to obtain the equivariant many-body basis, Bi [48],

B. Training data

The core of the training set is version 1 of the SPICE dataset [51] with 95% of the data used for training and validation, and 5% set aside for testing. Test/train splitting was performed at the molecule level, ensur- ing conformers of the same molecule do not appear in both train/validation and test sets. Table 1 summarizes the training and test sets. The MACE-OFF models are trained to reproduce the energies and forces computed at the ωB97M-D3(BJ)/def2-TZVPPD level of quantum mechanics [52–56], as implemented in the PSI4 software package [57]. We have used a subset of SPICE that con- tains the ten chemical elements H, C, N, O, F, P, S, Cl, Br, and I, and has a neutral formal charge (see Table 2 in Ref. [51] for element coverage in the dataset). We have also removed the ion pairs subset. Overall, we used about 85% of the full SPICE dataset. The ge- ometries in the SPICE dataset have been generated by running molecular dynamics simulations using classi- cal force ﬁelds [58], performed at both 300K and 500K,

ν Y

B(t),ν i,ηνkLM = X

ξ=1 A(t) i,klξmξ (4)

lm CLM ηνlm

where bold lm denotes the ν-tuple of l and m values and similarly to Eq. (2), ην enumerates the number of possible couplings to create the features with equivari- ance LM. The maximum body-order is controlled by the parameter ν and is ﬁxed at 3 (corresponding to 4- body terms, which includes the central atom) for all MACE-OFF models in this work. Finally, a “message” mi is created on each atom as a learnable linear combination of the equivariant many- body features:

m(t) i,kLM = X

ην W (t),ν ziηνkLB(t),ν i,ηνkLM (5)

X

ν


## 第 4 页

4

formation about the training is provided in Section S1.

and sampling maximally diﬀerent conformations from the resulting trajectories [51]. The SPICE dataset only contains small molecules of up to 50 atoms. To facilitate the learning of in- tramolecular non-bonded interactions, we augmented SPICE with larger 50–90 atom molecules randomly se- lected from the QMugs dataset [60]. The geometries were generated by running molecular dynamics simu- lations using GFN2-xTB [23] similarly to the protocol described in Ref. [61]. The energies and forces were re- evaluated at the level of QM theory used in SPICE. Finally, to obtain a better description of water, the dataset was further augmented with a number of wa- ter clusters carved out of molecular dynamics simula- tions of liquid water [62], with sizes of up to 50 water molecules. In addition to the 5% of each subset, part of the COMP6 tripeptide dataset [25] was also recom- puted at the SPICE level of theory and used as part of the test evaluation, but not for training. In order to understand the role additional data plays in the performance of the model, we also investigated the diﬀerence in performance due to inclusion of ad- ditional conﬁgurations released as part of the second version of SPICE [63]. The updated dataset, which we incorporate into the MACE-OFF24(M) model (see Sec- tion II C), contains among others, an additional 208,000 conﬁgurations comprising solvated PubChem molecules and amino acid-ligand pairs. The former were sampled from molecular dynamics using the same protocol as in the original dataset, whilst the amino acid-ligand pairs were extracted from structures in the PDB. This re- lease also included 1000 water clusters, containing up to 90 atoms. These were also added and used to com- plement the set of water clusters already included in the extended dataset.

III. Results

A. Extended SPICE Test Set

First, we look at the pointwise errors of the en- ergy and force predictions on a held-out test set for each of the three baseline MACE-OFF23 models. Fig- ure 1 shows the per-atom energy, force and intermolec- ular force root-mean-square errors (full statistics are provided in Section S2). As the size of the model increases, the models gradually become more accu- rate, with the large model generally achieving errors of around 0.5–1.0 meV/atom and 15–20 meV/˚A, well below the 1 kcal/mol (43 meV) chemical accuracy limit for the drug-like organic molecules studied here. The last column represents an extrapolation task, the training set contains only dipeptides, and this test set looks at tripeptides, indicating that the models are able to extrapolate to larger fragments with more complex interactions, with no loss of accuracy. The bottom panel of Figure 1 shows speciﬁcally the intermolecular force errors, which were obtained by sep- arating the force contributions to molecular translations and rotations (see Section S2 and Ref. [65] for de- tails). These interactions are crucial as they underpin the thermodynamics and transport properties in the or- ganic condensed phase. MACE-OFF23(M) and MACE- OFF23(L) both yield similar errors of around 5–15 meV/˚A, which are about 1.5–3 times smaller than total force errors, and about 5–10% of the typical DFT inter- molecular force magnitude (RMS). For context, relative intramolecular force errors, which are roughly equiva- lent to total force errors, are around 1–2%. The latter are routinely used across the literature to benchmark ML models, however, we advocate that intermolecular RMSE errors are a more appropriate metric to assess model accuracy for organic condensed phase applica- tions. The results here demonstrate the remarkable accuracy of MACE models in predicting these subtle but crucial interactions. We will investigate how these energy and force errors translate into condensed phase physical property predictions in later Sections.

C. Model details

The MACE model has parameters that enable sys- tematic control of model expressivity (and subsequent accuracy) against computational cost. In this paper, we present three variants of the MACE-OFF23 model, a small, a medium, and a large one, denoted in the text as MACE-OFF23(S), MACE-OFF23(M) and MACE- OFF23(L) respectively. The models get more accurate with size, but also have an increasing computational cost. The small model is well suited for large-scale sim- ulations, the medium model oﬀers a good balance of speed and accuracy, and the large model is best used for small systems or when the highest possible accu- racy is desirable. MACE-OFF24(M) is an update to the medium model that uses an extended 6 ˚A cutoﬀand includes additional conﬁgurations from version 2 of the SPICE dataset [63]. The hyperparameters of the mod- els are displayed in Table 2. All models were trained using the PyTorch [64] implementation of MACE, avail- able at https://github.com/ACEsuit/mace. More in-

B. Dihedral scans

Next, we evaluate the performance of the MACE- OFF23 models on dihedral scans of drug-like molecules. This task is routinely carried out using quantum me- chanical methods to create reference data for pa- rameterizing classical empirical force ﬁeld dihedral terms [66]. The task is particularly challenging, as con- strained geometry optimizations can be diﬃcult to con- verge if the potential energy surface is not smooth, as


## 第 5 页

5

Table 1. Summary of training and test sets. The columns ‘PubChem’ to ‘Solvated Amino Acids’ correspond to the original SPICE dataset [51].

Water QMugs [60] Tripeptides

PubChem DES370K Monomers DES370K Dimers [59] Dipeptides Solvated Amino Acids

H, C, N, O

H, C, N, O, S H, C, N, O, S H, O H, C, N, O, F, P, S, Cl, Br, I

H, C, N, O, F, P, S, Cl, Br, I

H, C, N, O, F, P, S, Cl, Br, I

Chemical elements H, C, N, O, F, P, S, Cl, Br, I

System size 3-50 3-22 4-34 26-60 79-96 3-150 51-90 30-69 # Train 646821 16861 263065 19773 948 1597 2748 0 # Test 33884 889 13896 1025 52 84 144 898

that MACE-optimized geometries have a deviation of about 0.025 ˚A, meaning they are almost indistinguish- able from DFT-optimized structures. It is important to note that the other models were trained to diﬀerent lev- els of DFT, which might also contribute to the observed diﬀerences [70].

Table 2. Hyperparameters of the MACE-OFF models

23(S) 23(M) 23(L) 24(M)

Cutoﬀradius (˚A) 4.5 5.0 5.0 6.0 Chemical channels 96 128 192 128 k (see Eq. (1)) max L (see Eq. (5)) 0 1 2 1 SPICE version 1 1 1 2

2. Biaryl fragments

has been observed for example for the ANI-1x poten- tial [67].

The biaryl torsion benchmark investigates the tor- sional proﬁles of about 100 diﬀerent biaryl fragments computed at the coupled cluster level of theory [68]. In these molecules, the rotatable bond is between two aro- matic rings. Such chemistry frequently occurs in drug- like molecules, and the proﬁles are typically challeng- ing to model accurately using empirical classical force ﬁelds. Following previous studies, we used a subset of 78 molecules to facilitate comparisons with the ANI-1ccx model, which is only parameterized for H, C, N, and O chemical elements [68]. In the bottom panel of Figure 2, we compare the re- sults of torsion drives of empirical force ﬁelds, semi- empirical QM methods, and the ANI-1ccx machine learning force ﬁeld [26] with the MACE-OFF23 models. We also compare the DFT potential energy surfaces (us- ing the SPICE level of theory) with the published gold standard coupled cluster data. The DFT torsion drives achieve a mean barrier height error of 0.2 kcal/mol with respect to coupled cluster data, and is therefore the best result theoretically pos- sible for MACE-OFF23 models which were trained on the same DFT level of theory. We ﬁnd that the large model comes close to this, with a mean absolute error of 0.3 kcal/mol. The medium and small MACE models have barrier height errors of 0.4 and 0.5 kcal/mol, re- spectively. Remarkably, the small MACE model is sig- niﬁcantly more accurate than the next-best non-DFT methods, ANI-1ccx and GFN2-xTB, as illustrated in the bottom-center plot of Figure 2. In particular, unlike MACE-OFF23, coupled cluster reference calculations were used to parameterize the ANI-1ccx and GFN2 models. In the bottom right, we also show the cumula- tive error distributions to verify that the MACE-OFF23

1. TorsionNet-500

The top panel of Figure 2 summarizes the results for the TorsionNet-500 dataset [69]. This dataset contains torsion drives of 500 diﬀerent molecules, selected to cover a wide range of pharmaceutically relevant chem- ical space. The original dataset was reported at the B3LYP/6-31G(d) level of DFT theory. For consistency with the SPICE dataset, we recreated the torsion pro- ﬁles using the DFT setting of SPICE, which uses a higher level of theory and basis set (Section S3). The ﬁrst panel shows an example of a torsion drive, indicating the complex energy proﬁle that the MACE models are able to capture closely, including geome- tries far from equilibrium. The center panel shows the mean barrier height error of a number of representative models, comparing the Sage classical empirical force ﬁeld [21], a semi-empirical quantum mechanical method GFN2-xTB [23], a recent transferable machine learning force ﬁeld AIMNet2 [8], and the three MACE-OFF23 models. Again, systematic improvements in accuracy with MACE model size are observed, with medium and large models, in particular, achieving errors of around 0.25 kcal/mol compared to the reference method. The AIMNet2 model achieves comparable accuracy to the small MACE-OFF23 model. A similar conclusion can be drawn from the comparison of the molecular geome- tries by looking at the root mean squared deviation of the atomic positions averaged over the full torsion scans, as indicated by the top right panel of Figure 2. It shows


## 第 6 页

6

trained on the SPICE dataset, and quantum nuce- lear eﬀects are incorporated using path-integral coarse- grained simulations (PIGS) [71]. Full details are pro- vided in Section S8. This is a stringent test, as repro- ducing the line positions and their relative intensities re- quires an accurate treatment of both intramolecular in- teractions and the dipole moment in out-of-equilibrium conﬁgurations. As shown in Figure 3, we estimate the classical and approximate quantum IR spectra [71], and compare them directly with experimental data at 293 K [72]. For low and intermediate frequencies (up to around 2000 cm−1), the classical and quantum spectra agree with each other and with the experimental data, allowing identiﬁcation of all collective modes. For the high-frequency O–H and N–H modes, we observe that the classical spectra are blue-shifted due to the absence of anharmonic zero-point ﬂuctuations, which typically soften these bonds. A quantum treatment of nuclear dynamics results in good agreement with the experi- mental data, with the exception of a net blue shift and a slight discrepancy in the relative intensities of the high- frequency stretching with respect to the lower-frequency modes, likely due to the limitations of the reference den- sity functional.

C. Molecular crystals and organic liquids

In the following, we demonstrate the ability of the MACE-OFF force ﬁelds to simulate the vibrational and thermal properties of molecular crystals. Based on relative accuracy and computational expense, in what follows we present data only for the medium MACE- OFF models. Additional experiments, where either the higher throughput of the small model or the additional accuracy of the large model are desired, are reported in the Supporting Information.

Figure 1. Test set root mean square errors (RMSE). Errors in the MACE-OFF23 models compared to the un- derlying DFT reference data, highlighting the relative ac- curacy of the three models. Bottom panels show specif- ically inter-molecular force errors compared to overall DFT inter-molecular force magnitudes (RMS). Note that for subsets comprising only single molecule conﬁgurations (DES370K Monomers, Dipeptides, QMugs, Tripeptides) inter-molecular contributions are expected to be zero. The slight deviation from zero arises because DFT forces do not obey translational and rotational symmetries with suﬃcient accuracy, while MACE models do.

1. Lattice enthalphies

We assess the ability of the MACE-OFF23(M) model to describe the stability of molecular crystals. We com- puted the enthalpies of sublimation of a range of 23 rep- resentative small molecular crystals [73] following the protocol of Ref. [74] (Section S4). Figure 4 compares the predicted sublimation en- thalpies with the experimentally measured ones. This task is often used to test various DFT functionals [73], as well as beyond-DFT methods [75] and tuned ma- chine learning potentials [76]. Since the ωB97M-D3(BJ) functional used to parameterize MACE-OFF23 does not have a periodic implementation, an estimate of the highest achievable accuracy is not available. The ﬁg- ure shows that the MACE-OFF23(M) model is able to capture trends and improve signiﬁcantly compared to the ANI-2x model. The mean absolute error of 1.8 kcal/mol is comparable to the errors of several diﬀer- ent dispersion-corrected density functionals for a frac-

barrier height errors are not only accurate on average but are also robust, with essentially no outliers.

3. Infrared spectroscopy of a drug molecule

To assess the accuracy of the MACE-OFF23(M) model for ﬁnite temperature properties of molecules, we study the infrared spectrum of an isolated paraceta- mol molecule at room temperature. Molecular dipole moments are predicted using the MACE architecture,


![image_1](images/image_0001.png)


![image_2](images/image_0002.png)


## 第 7 页

7

Figure 2. Dihedral benchmark scans. The top panel shows torsion drive data for the TorsionNet-500 dataset, which has a wide chemical diversity (ﬁve example molecules are shown). The bottom panel focuses on the torsion angle between two aromatic rings in the biaryl torsion benchmark [68] which contains 78 molecules (ﬁve examples are shown).

QM reference data for isolated molecules and molecu- lar dimers. From these ab initio data, the models must learn the long-range interactions necessary to reproduce bulk properties without ever ﬁtting to them.

tion of the computational cost [73]. The sublimation enthalpies for all MACE-OFF models are tabulated in Section S4, and we observe that the small model is intermediate in accuracy between the medium model and ANI-2x, while the large model does not give any signiﬁcant performance improvement. Additional analyses of the relaxed unit cell vectors using the MACE-OFF23(L) model, and the powder Ra- man spectrum of crystalline paracetamol are presented in Sections S5 and S8.

To investigate the performance of the MACE-OFF23 models in the condensed phase, we selected a bench- mark set of 109 molecules from Ref. [78], contain- ing a representative set of functional groups relevant to medicinal chemistry and biology. For the liquid boxes containing approximately 600 atoms, MACE- OFF23(S) achieved a throughput of 2.1×106 steps/day via OpenMM on a single 80GB NVIDIA A100 GPU, whilst the medium model achieved a throughput of 1.1× 106 steps/day. Meanwhile MACE-OFF23(L) achieved a throughput of 2.8 × 105 steps/day on the same sys- tem, highlighting the signiﬁcant overhead compared to the other two models. See section III E for further dis- cussion of the computational performance.

2. Condensed phase properties of organic liquids

Small molecule empirical force ﬁelds are ﬁtted to re- produce experimental condensed phase properties in- cluding densities and heats of vaporization. As such, errors on small molecular systems are expected to be well within chemical accuracy [21, 77]. For machine learning force ﬁelds, this task represents a greater chal- lenge, since the potential is typically trained only using

First, we investigate the predictions of molecular liquid densities under ambient conditions using the medium MACE model shown on the top panel of


![image_3](images/image_0003.png)


![image_4](images/image_0004.jpeg)


## 第 8 页

8

MACE-OFF23(M) MD (classical) MACE-OFF23(M) PIGS (quantum) Experiment

IR Absorbance [arb. units]

500 1000 1500 2000 2500 3000 3500 4000

[cm 1]

Figure 3. Infrared (IR) spectrum of a paracetamol molecule. The classical (blue dashed) and quantum (blue solid) IR spectrum at 293 K using the MACE-OFF23(M) model is computed by propagating the system and estimat- ing the time correlation function of the time derivative of the total dipole moment. The experimental data are taken from Ref. 72.

X23 Molecular Crystal Sublimation Enthalpies

40

30

20

Predicted H (kcal/mol)

Figure 5. Molecular liquids. Comparison between MACE-OFF23(M) and ANI-2x with experiment for densi- ties (top) and heats of vaporization (bottom) of condensed phase organic liquids.

10

0

10

and RMSE errors twice as large as MACE-OFF23(M) (Section S6). The vast majority of the outliers in the density predic- tions can be assigned as either low boiling-point ether- containing compounds, polychlorinated hydrocarbons or dibromo-containing compounds. In the ﬁrst case, this may be due to a marginal under-prediction of the boiling point, since these compounds were simulated at 10 K below their tabulated boiling points. In the latter two cases, this functional group dependence suggests these nonbonded interactions are insuﬃciently repre- sented in the present training set, which contains, for ex- ample, only 84 examples of dibromo-containing dimers. This highlights the need for additional coverage of spe- ciﬁc functional groups within SPICE (for example, the recent AIMNet2 dataset includes 20 million conﬁgura- tions to cover 14 chemical elements [8]). We further investigated the performance of MACE-

ANI-2x MAE=4.9 kcal/mol MACE-OFF23(M) MAE=1.8 kcal/mol

20

30

5 10 15 20 25 30 35 40

Experimental H (kcal/mol)

Figure 4. Sublimation enthalphies of molecular crys- tals. Comparison between predicted sublimation enthal- phies of the MACE-OFF23(M) and ANI models and exper- iment.

Figure 5. MACE-OFF23(M) achieves a MAE of 0.09 g/cm3, indicating that it can generalize from the intermolecular interactions between molecular dimers in the training set to the condensed phase, retaining a good correlation with experiment. In contrast, the ANI- 2x potential has signiﬁcantly higher errors, with MAE


## 第 9 页

9

rectly predicts the radial distribution function (RDF) of water, performing comparably with both TIP3P and the highly accurate MB-pol water model, whose RDF is indistinguishable from experiment [80]. These inter- actions are modelled in a purely local way by MACE, having been trained on small water clusters containing up to 50 water molecules. This result further empha- sizes the ability of the model to generalize to bulk sim- ulations, even though the training data only contained non-periodic clusters. In contrast, ANI-2X shows a sig- niﬁcant over-structuring of the RDF, however this is likely driven primarily by the lack of dispersion cor- rection in the underlying quantum mechanical method used to label the training set. Additional tests of the vi- brational density of states of liquid water are presented in Section S8 and show good agreement with experi- ment. We further calculated the temperature dependence of the water density using NPT molecular dynamics simulations, as shown in Figure 7. This is a highly sensitive test of the accuracy of intermolecular interac- tions [65]. The MACE-OFF23(M) model over-estimates the density of liquid water by approximately 20%. Since there is extensive coverage of water clusters in the train- ing set, we hypothesized that this results from a miss- ing long-range contribution beyond the receptive ﬁeld. To investigate this hypothesis, we ﬁtted an additional model, which has an increased 6 ˚A layerwise cutoﬀ compared to 5 ˚A. The larger receptive ﬁeld leads to a predicted water density within 2% of the experimental value at room temperature, and within 5% across the full temperature range (Figure 7). We note that simi- lar errors are reported using many dispersion-corrected DFT exchange-correlation functionals [81]. At this point in the model development, the second version of SPICE had been released, which included Solvated Pubchem and Amino Acid Ligand Pairs datasets [63]. Given the direct applicability of these training data and the importance of modelling water to biomolec- ular simulations, the remainder of this section uses the MACE-OFF24(M) model, which includes the ad- ditional training data and extended 6 ˚A cutoﬀ(Ta- ble 2). To conﬁrm no loss of performance on incor- poration of the additional training data, we conﬁrmed that the test set errors are in agreement with MACE- OFF23(M) (Section S2.1).

OFF23(M) on heats of vaporization. The predictions correlate strongly with the experimental data; however, there is a systematic oﬀset of approximately 2 kcal/mol (Figure 5). We hypothesized that this may result from an under-prediction of the total intermolecular interac- tions originating from two sources: those that appear in molecular dynamics simulations outside the eﬀective cutoﬀof the MACE model (compare classical simula- tions, which typically employ long-range corrections to the total energy [79]), and those that the model has not learned from the limited set of intermolecular interac- tions in the training set. The eﬀect of the choice of MACE-OFF model on con- densed phase properties is further investigated in Sec- tion S6. In general, we observe that the small model systematically over-predicts the experimental density (MAE 0.23 g/cm3), which is consistent with its larger intermolecular force errors (Table S1). We did not observe any signiﬁcant improvements in accuracy, over the medium model, using either the large model or a model trained with an extended cutoﬀof 6 ˚A. This further reinforces the hypothesis that the poorly pre- dicted densities are a result of under-representation of the functional groups in the training set. Nevertheless, these data indicate that, given a reasonable receptive ﬁeld and a suﬃciently expressive model, it is possible to ﬁt a local force ﬁeld that captures the interactions required to recover experimental properties. Further improvements in accuracy are possible without resort- ing to ﬁtting to experiment by increasing further the size of the training dataset and the explicit addition of long-range Coulomb interactions into the model, which we leave for future work.

D. Biomolecular simulations

In the following section, we benchmark the per- formance of the MACE-OFF models on several well- studied large-scale biomolecular systems. This particu- lar application area is of key interest, and state-of-the- art classical protein force ﬁelds have been carefully pa- rameterized over many decades to reproduce key quan- tum mechanical and thermodynamic properties. How- ever, this extensive parameterization process makes it diﬃcult to extend classical force ﬁelds, and overall accu- racy and transferability remain fundamentally limited by their functional form. This typically becomes appar- ent only when each generation of advancing hardware enables suﬃciently long simulations to identify issues.

2. Ala3 Free Energy Surface

We ﬁrst investigated the ability of MACE-OFF24(M) to reproduce the free energy surface of the Ala3 tripep- tide. We observed computational performance of 9.6 × 106 steps/day for the vacuum system, and 2.2 × 106

1. Water structure and dynamics

steps/day for the solvated system on an NVIDIA 80GB A100 GPU via the OpenMM interface. Although this remains signiﬁcantly more expensive than the MM sim- ulation (around 150 × 106 steps/day), it nevertheless enables suﬃcient sampling of the free energy surface.

A key requirement for bio-organic force ﬁelds is an accurate description of water. Several empirical wa- ter models have been developed for this purpose, the most common for all-atom biomolecular simulations be- ing TIP3P. Figure 6 shows that MACE-OFF23(M) cor-


## 第 10 页

10

Figure 6. Water structure. Radial distribution functions of MACE, ANI and TIP3P models. MB-pol traces are reproduced from Ref. [80].

forceﬁeld.

The corresponding MACE simulations show a similar free energy surface to AMBER14SB/TIP3P, with the same four local minima identiﬁed. Whilst the relative depths of the α-helical conformations are in agreement, AMBER predicts the free energy of the anti-parallel β- sheet to be 1 kcal/mol higher than the PPII minimum, compared to 0.1 kcal/mol for MACE.

We also compare the unbiased conformational ensem- ble from 20 ns of NPT dynamics sampled with MACE- OFF24(M) directly to experiment by calculating 3J coupling constants from the Ramachandran distribu- tion. Computed values are shown in Table 3 in addi- tion to literature values for AMBER14SB, ANI-2x and experiment [82–84]. MACE-OFF24(M) accurately pre- dicts coupling constants, and is comparable with AM- BER14SB. In agreement with our previous ﬁndings, both methods signiﬁcantly outperform ANI-2x, high- lighting the diﬃculties in computing accurate dynamics in the solution phase with MLPs.

Figure 7. Water density as a function of temperature. Comparison between MACE-OFF23(M), and the extended cutoﬀMACE-OFF24(M) model.

Figure 8 shows the free energy surface of Ala3 in water, modelled by AMBER14SB/TIP3P and MACE- OFF24(M), respectively. Well-tempered metadynamics was used to enhance sampling along the central φ and ψ backbone angles (Section S7.1). The AMBER14SB simulation identiﬁes four local minima, corresponding to the anti-parallel β-sheet (φ < −120◦, ψ > 120◦), a right-handed α-helix (φ = −60◦, ψ > −60◦), the corre- sponding left-handed α-helix (φ = 60◦, ψ > 60◦), and a polyproline II (PPII)-type structure (φ = −60◦, ψ > 120◦). Comparing the dihedral angle distribution with NMR J-coupling constants, the AMBER14SB simula- tion is generally in good agreement, with a slight over- population of both α-helical structures and underpopu- lation of the PPII mesostate [82]. We therefore use this to enable visual comparison with a well-tuned classical

3J(HN,Hα) 3J(HN,Cβ) 3J(HN,C′)

MACE-OFF24(M) 5.70(0.43) 1.64(0.18) 1.37(0.30) ANI-2x 7.5 1.2 1.8 AMBER14SB 6.07 1.87 1.13

EXP 5.68(0.11) 2.39(0.09) 1.13(0.08)

Table 3. Summary of 3J couplings computed from dihedral distributions. AMBER14SB and experimen- tal values are taken from Ref. [82], and ANI-2x data from Ref. [83]. Standard errors in the mean from block averaging are shown in parentheses for MACE-OFF, and experimental uncertainties are reproduced from Ref. [82]


## 第 11 页

11

Figure 9. Ala15 folding dynamics. Secondary struc- ture assignment during a 500 ps trajectory generated with MACE-OFF24(M). The structure proceeds via a “wavy” in- termediate and oscillates between the α- and 310 helices. Secondary structure assignment was performed with the STRIDE algorithm [86].

Figure 8. Free energy surfaces of Ala3 in explicit sol- vent. AMBER14SB/TIP3P (top) and MACE-OFF24(M) (bottom).

Figure 10. Ala15 Temperature dependence. Secondary structure assignment with increasing temperature.

3. Folding dynamics of Ala15

GEMS. The oscillatory behavior has also been observed experimentally in alanine-rich polypeptides [85]. We also measured the secondary structure of the pep- tide as the temperature was increased. Starting from the folded structure at 300 K, the temperature was in- creased in steps from 300 K to 900 K over the course of 3 ns (Figure 10). The folded structure remains stable up to around 500 K, after which point the helix unfolds and the structure is primarily a random coil.

Having conﬁrmed that MACE-OFF24(M) is capable of recovering a good approximation to the free energy surface of a small peptide, we next investigated the fold- ing of the longer helical peptide Ala15. Because this is a signiﬁcantly larger system size than the dipeptide con- ﬁgurations on which the model was trained, this repre- sents a nontrivial test of the extrapolation capability of the potential, including its ability to capture complex hydrogen bonding interactions required to stabilize the secondary structure. Such simulations are believed to be particularly diﬃcult with purely local models such as those in the MACE-OFF family. As an initial test, the fully extended Ala15 struc- ture was simulated in vacuo. Figure 9 shows the as- signment of the secondary structure during the simula- tion. The peptide folded within 200 ps, adopting ini- tially a “wavy” intermediate structure, before ﬁrst fold- ing into a 310 helix. The secondary structure oscillates between the α-helix and the 310 helix for the remainder of the simulation, with the α-helix being the predomi- nant motif. These results are in agreement with other works [9, 39], in which polyalanine peptides are observed to fold through a “wavy intermediate” and oscillate be- tween 310 and α-helices. Although, MACE-OFF24(M) predicts the 310 helix in lower ratio than SO3LR and

4. Protein simulation in explicit solvent

Finally, we investigated the simulation of a fully sol- vated protein with MACE-OFF. As a test case, we chose Crambin, a 42-residue threonin storage protein that contains four charged residues. This test goes sig- niﬁcantly beyond what can typically be expected from a local force ﬁeld trained on neutral species only. Using the MACE-OFF24(M) model, we ﬁrst con- ﬁrmed that the force ﬁeld was indeed capable of sim- ulating a large biomolecular system containing charged residues. In particular, it has recently been shown that the FENNIX potential fails to simulate a solvated 28 residue peptide due to unphysical proton transfers in- volving charged residues [37]. We conﬁrmed that the root mean square ﬂuctuations of the protein backbone


![image_5](images/image_0005.png)


![image_6](images/image_0006.jpeg)


![image_7](images/image_0007.png)


![image_8](images/image_0008.jpeg)


![image_9](images/image_0009.png)


![image_10](images/image_0010.jpeg)


![image_11](images/image_0011.jpeg)


## 第 12 页

12

relative to the minimized structure remained below 1 ˚A for the duration of a 1 ns simulation, no bond break- ing occurred and the secondary structure motifs re- mained intact (Figure S2). We obtained a throughput of 3×105 steps per day on a single NVIDIA A100 80GB GPU. We then investigated the ability of MACE-OFF24(M) to capture the key vibrational modes of the system. To this end, we prepared a simulation box containing cram- bin in the high-hydration state, that is, fully solvated in explicit water, for a total system size of approximately 18,000 atoms. The power spectrum was calculated from the ﬁnal 125 ps of a 1.6 ns simulation recorded at 2 fs resolution, to match the simulation length and sam- pling frequency employed in Ref [41]. This system has also been investigated with the AMBER classical force ﬁeld and several machine learned potentials, including GEMS and, more recently, SO3LR [9, 39, 40]. All three MLPs produce spectra in qualitative agreement with each other. The water peaks at 1640 cm-1 and 3200- 3600 cm-1 are reproduced reasonably accurately, espe- cially considering that no nuclear quantum eﬀects are taken into account (Figure 11). Furthermore, in the low frequency region, two peaks are identiﬁed in the power spectrum by GEMS, SO3LR and MACE-OFF24(M). The most obvious of these occurs at 60 cm-1 and cor- responds to localized internal side chain ﬂuctuations, while a peak at 220 cm-1 is due to speciﬁc conﬁgura- tions of water at the protein surface. We note that, whilst a 125 ps trajectory is suﬃcient to qualitatively identify the spectral features, a much longer simulation of at least several nanoseconds would be required to fully converge the THz region of the spectrum and enable full quantitative comparison with experiment, as demonstrated for the GEMS model in Ref. [39]. We note that the power spectrum computed on the ﬁnal 1.3 ns simulation (discarding the initial 300 ps to equilibration) does not yield a signiﬁcantly diﬀerent spectrum to that of the 125 ps simulation used in Figure 11, indicating that signiﬁcantly more sam- pling would be required to resolve the THz lineshapes suﬃciently to enable experimental comparison [87]. It is also noteworthy that whilst the three MLPs com- pared in this section give a qualitatively similar result, their modelling choices are signiﬁcantly diﬀerent. Most notably, GEMS and SO3LR explicitly include long- range interactions, whilst MACE is local. Additionally, of these models, both MACE and SO3LR are universal potentials, whilst GEMS is ﬁtted in a system-speciﬁc fashion. We mention that, in addition to the GEMS model, the authors benchmarked a variant which was trained only on small fragments, denoted GEMS*, in- stead of the large system-speciﬁc conﬁgurations used to ﬁt GEMS [39]. The power spectrum produced by this model is also in qualitative agreement with the other ML potentials, however, the RMSD is reduced, indicat- ing the protein structure is conﬁned to small ﬂuctua- tions around local minima. This model also fails to re- produce experimental observables of other biomolecular

24(M)

Figure 11. Protein in explicit solvent. Power spec- trum of the high hydration state of crambin computed from the ﬁnal 125 ps of a 1.6 ns simulation with MACE- OFF24(M). GEMS, AMBER and SO3LR spectra are repro- duced from Ref. [41]. Black lines denote experimental peaks at 1640 cm-1 and the range 3200-3600 cm-1.

systems, for example Ala15 is not predicted to fold un- der the GEMS* potential, suggesting the top-down frag- ments are required to accurately reproduce nonbonded interactions within the GEMS family of models. The results of sections III C and III D highlight the most signiﬁcant diﬀerences between previous transfer- able organic ML potentials and the MACE-OFF mod- els. Whilst there is still signiﬁcant work to be done to comprehensively show improvement over classical forceﬁelds for large biomolecular systems, these re- sults demonstrate the capabilities of models ﬁt ‘bottom up’ from quantum mechanical data to learn subtle in- termolecular interactions and correctly predict macro- scopic properties.

E. Computational performance

To evaluate the computational performance of the MACE-OFF models, we performed NVT molecular dy- namics for water using both OpenMM and LAMMPS, with simulation boxes ranging from 102 to 105 atoms. The OpenMM results shown in Figure 12 were collected with a single NVIDIA A100 80GB GPU. The LAMMPS results shown in Section S9 highlight both CPU and GPU evaluation. In addition to the native PyTorch implementations of the MACE-OFF23 models, we also report results for optimized implementations leveraging custom C++, CUDA, and/or Kokkos code. One optimized variant in- corporates custom CUDA kernels which are packaged as a standalone, inference-only library, cuda mace [88]. Another pure-C++ implementation, as well as a Kokkos implementation, will be made available as part of the symmetrix library [89]. In these optimized variants, the learnable radial func- tion R(t) kη1l1l2l3(rij) is evaluated with cubic splines, which eﬃciently map rij to each of the outputs of the radial MLP. Furthermore, eqs. 2 and 3 are implemented in uniﬁed kernels that simultaneously compute the one- particle basis and perform the summation over neigh- bors to generate the invariant atomic basis Ai. The computation of spherical harmonics, as detailed in equa- tion 2 is accelerated using the sphericart [90] library,


![image_12](images/image_0012.png)


## 第 13 页

13

tigated the accuracy of the medium models against a range of crystalline, liquid and biomolecular condensed phase data, as we found them to provide a good com- promise between accuracy and computational expense. We have made all force ﬁelds available to the commu- nity, so that users can choose the model most suited to their application. The lack of explicit long-range interactions limits the domain of applicability of the present model to neutral, non-radical and non-reactive systems. This is some- thing that the recently published AIMNet2 model aims to address by extending the ANI models to include charged species and long-range interactions [8]. We are currently working on a next-generation MACE-OFF model that will similarly include an explicit description of charges, enabling the description of amino acids with diﬀerent protonation states, charged nucleic acids, and counter-ions. This will pave the way towards obtaining an accurate quantum mechanical transferable machine learning force ﬁeld for simulating the full range of bio- logically relevant systems.

Figure 12. Performance in OpenMM. Performance of MACE-OFF models in OpenMM for liquid water in the NVT ensemble at 1 g/cm3 at 300 K with a 1 fs timestep on a single NVIDIA 80GB A100 GPU. The cuda mace imple- mentation is labeled ‘OPT’. Forces were evaluated in double precision, and integrated in single precision.

Acknowledgements

which oﬀers a highly optimized implementation for real spherical harmonics. All linear and equivariant lin- ear operations have been substituted with custom ker- nels, and the cuda mace implementation further lever- ages tensor core acceleration while incorporating error- correction techniques to ensure numerical accuracy. Ad- ditionally, the computation of the product basis Bi in eq 4 is optimized using the sparsity of the generalized Clebsch-Gordon coeﬃcients CLM ηνlm, signiﬁcantly acceler- ating the product calculations over both the body order v and the coupling terms.

DPK acknowledges support from AstraZeneca and the EPSRC. DJC and JH acknowledge support from a UKRI Future Leaders Fellowship (grant MR/T019654/1). V.K. acknowledges support from the Ernest Oppenheimer Early Career Fellowship, the Sydney Harvey Junior Research Fellowship, Churchill College, University of Cambridge, and UCL’s startup funds. W.C.W. acknowledges support from the EPSRC (Grant EP/V062654/1), as well as an engagement from the Virtual Institute for Scientiﬁc Software at Geor- gia Tech, funded by Schmidt Sciences. In particular, Ketan Bhardwaj and Dave Brownwell of the Georgia Tech Scientiﬁc Software Engineering Center contributed to the Kokkos-based MACE evaluator. JHM acknowl- edges support from an AstraZeneca Non-Clinical PhD studentship, and thanks Prof. Ola Engkvist, Dr Marco Kl¨ahn and Dr Graeme Robb from AstraZeneca for their helpful discussions and supervision. The authors also thank Christoph Schran for providing the carved water cluster geometries. We also thank Dr Peter Eastman and Dr Stephen Farr for their help implementing the MACE-OpenMM interface. We are grateful for computational support from the Swiss National Supercomputing Centre under project s1209, UCL Myriad High Performance Computing Fa- cility, the Rocket High Performance Computing ser- vice at Newcastle University, the UK national high- performance computing service, ARCHER2, for which access was obtained via the UKCP consortium and EPSRC grant EP/P022561/1, the Cambridge Service for Data Driven Discovery (CSD3), obtained through a University of Cambridge EPSRC Core Equipment Award (EP/X034712/1), and ˚Angstr¨om AI. Elements of this work are adapted from a PhD thesis.

IV. Outlook

In this paper, we presented the series of MACE-OFF force ﬁeld models, demonstrating the broad applicabil- ity, transferability and capability of purely short-range machine learning potentials for organic (bio)molecular simulations. We have shown that the models, based on the MACE higher order equivariant message pass- ing architecture, can improve on the pioneering ANI models [27] that served as the only widely applicable machine learning force ﬁelds for molecules for a number of years. While a full ablation study between diﬀer- ent ML models is not possible due to a wide range of design choices made in their construction, the MACE- OFF model architecture, training data and loss func- tion all contribute to signiﬁcant improvements in both accuracy and extrapolation, combined with high com- putational speed. We trained here so-called small, medium and large versions of the MACE-OFF models, with systemati- cally improving accuracy when benchmarked against gas phase quantum mechanical data. We further inves-


## 第 14 页

14

Data Availability

[6] M. Haghighatlari, J. Li, X. Guan, O. Zhang, A. Das, C. J. Stein, F. Heidar-Zadeh, M. Liu, M. Head-Gordon, L. Bertels, et al., Newtonnet: A newtonian message passing network for deep learning of interatomic po- tentials and forces, Digital Discovery 1, 333 (2022). [7] A. V. Shapeev, Moment tensor potentials: A class of systematically improvable interatomic potentials, Mul- tiscale Modeling & Simulation 14, 1153 (2016). [8] D. Anstine, R. Zubatyuk, and O. Isayev, Aimnet2: A neural network potential to meet your neutral, charged, organic, and elemental-organic needs, Chem- Rxiv Sumbitted 20-12-2024, accessed 2025-04-15, 10. 26434/chemrxiv-2023-296ch-v3. [9] A. Kabylda, V. Vassilev-Galindo, S. Chmiela, I. Poltavsky, and A. Tkatchenko, Eﬃcient inter- atomic descriptors for accurate machine learning force ﬁelds of extended molecules, Nature Communications 14, 3562 (2023). [10] J. Behler, Four generations of high-dimensional neu- ral network potentials, Chemical Reviews 121, 10037 (2021). [11] F. Musil, A. Grisaﬁ, A. P. Bart´ok, C. Ortner, G. Cs´anyi, and M. Ceriotti, Physics-inspired structural represen- tations for molecules and materials, Chemical Reviews 121, 9759 (2021). [12] V. L. Deringer, A. P. Bart´ok, N. Bernstein, D. M. Wilkins, M. Ceriotti, and G. Cs´anyi, Gaussian process regression for materials and molecules, Chemical Re- views 121, 10073 (2021). [13] B. Huang and O. A. Von Lilienfeld, Ab initio machine learning in chemical compound space, Chemical reviews 121, 10001 (2021). [14] M. S. Daw and M. I. Baskes, Embedded-atom method: Derivation and application to impurities, surfaces, and other defects in metals, Physical Review B 29, 6443 (1984). [15] V. L. Deringer, N. Bernstein, G. Cs´anyi, C. Ben Mah- moud, M. Ceriotti, M. Wilson, D. A. Drabold, and S. R. Elliott, Origins of structural and electronic transitions in disordered silicon, Nature 589, 59 (2021). [16] W. J. Baldwin, X. Liang, J. Klarbring, M. Dubajic, D. Dell’Angelo, C. Sutton, C. Caddeo, S. D. Stranks, A. Mattoni, A. Walsh, et al., Dynamic local structure in caesium lead iodide: Spatial correlation and transient domains, Small , 2303565 (2023). [17] C. W. Rosenbrock, K. Gubaev, A. V. Shapeev, L. B. P´artay, N. Bernstein, G. Cs´anyi, and G. L. Hart, Machine-learned interatomic potentials for alloys and alloy phase diagrams, npj Computational Materials 7, 24 (2021). [18] Y. Zhou, W. Zhang, E. Ma, and V. L. Deringer, Device- scale atomistic modelling of phase-change memory ma- terials, Nature Electronics , 1 (2023). [19] P. Dauber-Osguthorpe and A. T. Hagler, Biomolecular force ﬁelds: where have we been, where are we now, where do we need to go and how do we get there?, J Comput Aided Mol Des 33, 133–203 (2019). [20] A. T. Hagler, Force ﬁeld development phase ii: Relax- ation of physics-based criteria... or inclusion of more rigorous physics into the representation of molecular en- ergetics, J Comput Aided Mol Des 33, 205–264 (2019). [21] S. Boothroyd, P. K. Behara, O. C. Madin, D. F. Hahn, H. Jang, V. Gapsys, J. R. Wagner, J. T. Horton, D. L. Dotson, M. W. Thompson, J. Maat, T. Gokey, L.-P.

The data used to train the models are pub- licly available at: https://doi.org/10.17863/CAM. 107498. The torsion drive dataset is also available at: https://zenodo.org/records/11385284. The MACE-OFF series of models is available at: https: //github.com/ACEsuit/mace-off/tree/main.

Supplementary Information

The supplementary information contains the follow- ing sections:

• Training details for the MACE-OFF models, in- cluding ﬁltering of the SPICE dataset

• Detailed breakdown of test set errors, including intramolecular force errors

• Details of the torsion scans

• Details of lattice enthalpy calculations

• Crystal structure geometries

• Details of condensed phase simulations, including error tables

• Details of biological simulations

• Simulation details and results for dipole models

• Computational performance in LAMMPS

References

[1] Y. Lysogorskiy, C. v. d. Oord, A. Bochkarev, S. Menon, M. Rinaldi, T. Hammerschmidt, M. Mrovec, A. Thomp- son, G. Cs´anyi, C. Ortner, et al., Performant imple- mentation of the atomic cluster expansion (pace) and application to copper and silicon, npj computational materials 7, 97 (2021). [2] I. Batatia, D. P. Kovacs, G. Simm, C. Ortner, and G. Cs´anyi, Mace: Higher order equivariant message passing neural networks for fast and accurate force ﬁelds, Advances in Neural Information Processing Sys- tems 35, 11423 (2022). [3] D. P. Kov´acs, I. Batatia, E. S. Arany, and G. Cs´anyi, Evaluation of the MACE force ﬁeld architecture: From medicinal chemistry to materials science, The Journal of Chemical Physics 159, 044118 (2023). [4] S. Batzner, A. Musaelian, L. Sun, M. Geiger, J. P. Mailoa, M. Kornbluth, N. Molinari, T. E. Smidt, and B. Kozinsky, E (3)-equivariant graph neural networks for data-eﬃcient and accurate interatomic potentials, Nature communications 13, 2453 (2022). [5] V. Zaverkin, D. Holzm¨uller, L. Bonﬁrraro, and J. K¨astner, Transfer learning for chemically accurate interatomic neural network potentials, Physical Chem- istry Chemical Physics 25, 5383 (2023).


## 第 15 页

15

[35] J. Gilmer, S. S. Schoenholz, P. F. Riley, O. Vinyals, and G. E. Dahl, Neural message passing for quantum chem- istry, in International conference on machine learning (PMLR, 2017) pp. 1263–1272. [36] O. T. Unke and M. Meuwly, Physnet: A neural network for predicting energies, forces, dipole moments, and par- tial charges, Journal of chemical theory and computa- tion 15, 3678 (2019). [37] T. Pl´e , L. Lagard`ere, and J.-P. Piquemal, Force- ﬁeld-enhanced neural network interactions: from local equivariant embedding to atom-in-molecule properties and long-range eﬀects, Chemical Science 10.1039/d3sc02581k (2023). [38] M. Th¨urlemann and S. Riniker, Hybrid classical/machine-learning force ﬁelds for the ac- curate description of molecular condensed-phase systems, Chemical Science 14, 12661 (2023). [39] O. T. Unke, M. St¨ohr, S. Ganscha, T. Unterthiner, H. Maennel, S. Kashubin, D. Ahlin, M. Gastegger, L. M. Sandonas, J. T. Berryman, A. Tkatchenko, and K.-R. M¨uller, Biomolecular dynamics with machine- learned quantum-mechanical force ﬁelds trained on diverse chemical fragments, Science Advances 10, eadn4397 (2024). [40] O. T. Unke, S. Chmiela, M. Gastegger, K. T. Sch¨utt, H. E. Sauceda, and K.-R. M¨uller, Spookynet: Learning force ﬁelds with electronic degrees of freedom and non- local eﬀects, Nature communications 12, 7273 (2021). [41] A. Kabylda, J. T. Frank, S. S. Dou, A. Khabibrakhmanov, L. M. Sandonas, O. T. Unke, S. Chmiela, K.-R. Muller, and A. Tkatchenko, Molecu- lar Simulations with a Pretrained Neural Network and Universal Pairwise Force Fields (2024). [42] K. Sch¨utt, P.-J. Kindermans, H. E. Sauceda Felix, S. Chmiela, A. Tkatchenko, and K.-R. M¨uller, Schnet: A continuous-ﬁlter convolutional neural network for modeling quantum interactions, Advances in neural in- formation processing systems 30 (2017). [43] K. Sch¨utt, O. Unke, and M. Gastegger, Equivariant message passing for the prediction of tensorial proper- ties and molecular spectra, in International Conference on Machine Learning (PMLR, 2021) pp. 9377–9388. [44] J. Gasteiger, F. Becker, and S. G¨unnemann, Gem- net: Universal directional graph neural networks for molecules, Advances in Neural Information Processing Systems 34, 6790 (2021). [45] M. J. Willatt, F. Musil, and M. Ceriotti, Feature opti- mization for atomistic machine learning yields a data- driven construction of the periodic table of the elements, Physical Chemistry Chemical Physics 20, 29661 (2018). [46] J. P. Darby, D. P. Kov´acs, I. Batatia, M. A. Caro, G. L. Hart, C. Ortner, and G. Cs´anyi, Tensor-reduced atomic density representations, Physical Review Letters 131, 028001 (2023). [47] E. Wigner, Group theory: and its application to the quantum mechanics of atomic spectra, Vol. 5 (Elsevier, 2012). [48] G. Dusson, M. Bachmayr, G. Cs´anyi, R. Drautz, S. Et- ter, C. van der Oord, and C. Ortner, Atomic cluster ex- pansion: Completeness, eﬃciency and stability, Journal of Computational Physics 454, 110946 (2022). [49] I. Batatia, S. Batzner, D. P. Kov´acs, A. Musaelian, G. N. C. Simm, R. Drautz, C. Ortner, B. Kozinsky, and G. Cs´anyi, The design space of E(3)-equivariant atom-

Wang, D. J. Cole, M. K. Gilson, J. D. Chodera, C. I. Bayly, M. R. Shirts, and D. L. Mobley, Development and benchmarking of open force ﬁeld 2.0.0: The sage small molecule force ﬁeld, J. Chem. Theory Comput. 0, null (2023), pMID: 37167319. [22] V. Gapsys, L. P´erez-Benito, M. Aldeghi, D. Seeliger, H. Van Vlijmen, G. Tresadern, and B. L. De Groot, Large scale relative protein ligand binding aﬃnities using non-equilibrium alchemy, Chem. Sci. 11, 1140 (2020). [23] C. Bannwarth, S. Ehlert, and S. Grimme, Gfn2-xtb—an accurate and broadly parametrized self-consistent tight- binding quantum chemical method with multipole elec- trostatics and density-dependent dispersion contribu- tions, Journal of chemical theory and computation 15, 1652 (2019). [24] J. S. Smith, O. Isayev, and A. E. Roitberg, Ani-1: an extensible neural network potential with dft accuracy at force ﬁeld computational cost, Chemical science 8, 3192 (2017). [25] J. S. Smith, B. Nebgen, N. Lubbers, O. Isayev, and A. E. Roitberg, Less is more: Sampling chemical space with active learning, The Journal of chemical physics 148, 241733 (2018). [26] J. S. Smith, B. T. Nebgen, R. Zubatyuk, N. Lub- bers, C. Devereux, K. Barros, S. Tretiak, O. Isayev, and A. E. Roitberg, Approaching coupled cluster accu- racy with a general-purpose neural network potential through transfer learning, Nature communications 10, 1 (2019). [27] C. Devereux, J. S. Smith, K. K. Huddleston, K. Barros, R. Zubatyuk, O. Isayev, and A. E. Roitberg, Extend- ing the applicability of the ani deep learning molecular potential to sulfur and halogens, Journal of Chemical Theory and Computation 16, 4192 (2020). [28] R. Zubatyuk, J. S. Smith, J. Leszczynski, and O. Isayev, Accurate and transferable multitask prediction of chem- ical properties with an atoms-in-molecules neural net- work, Science advances 5, eaav6490 (2019). [29] R. Zubatyuk, J. S. Smith, B. T. Nebgen, S. Tretiak, and O. Isayev, Teaching a neural network to attach and de- tach electrons from molecules, Nature Communications 12, 4870 (2021). [30] J. Behler and M. Parrinello, Generalized neural- network representation of high-dimensional potential- energy surfaces, Physical review letters 98, 146401 (2007). [31] J. S. Smith, O. Isayev, and A. E. Roitberg, Ani-1, a data set of 20 million calculated oﬀ-equilibrium con- formations for organic molecules, Scientiﬁc data 4, 1 (2017). [32] J. S. Smith, R. Zubatyuk, B. Nebgen, N. Lubbers, K. Barros, A. E. Roitberg, O. Isayev, and S. Tretiak, The ani-1ccx and ani-1x data sets, coupled-cluster and density functional theory properties for molecules, Sci- entiﬁc data 7, 134 (2020). [33] T. J. Inizan, T. Pl´e, O. Adjoua, P. Ren, H. G¨okcan, O. Isayev, L. Lagard`ere, and J.-P. Piquemal, Scal- able hybrid deep neural networks/polarizable potentials biomolecular simulations including long-range eﬀects, Chemical Science 14, 5438 (2023). [34] N. T. P. Tu, N. Rezajooei, E. R. Johnson, and C. Row- ley, A neural network potential with rigorous treatment of long-range dispersion, Digital Discovery (2023).


## 第 16 页

16

[64] A. Paszke, S. Gross, F. Massa, A. Lerer, J. Brad- bury, G. Chanan, T. Killeen, Z. Lin, N. Gimelshein, L. Antiga, A. Desmaison, A. K¨opf, E. Yang, Z. De- Vito, M. Raison, A. Tejani, S. Chilamkurthy, B. Steiner, L. Fang, J. Bai, and S. Chintala, Pytorch: An imper- ative style, high-performance deep learning library, in Neural Information Processing Systems (2019). [65] I.-B. Magd˘au, D. J. Arismendi-Arrieta, H. E. Smith, C. P. Grey, K. Hermansson, and G. Cs´anyi, Machine learning force ﬁelds for molecular liquids: Ethylene carbonate/ethyl methyl carbonate binary solvent, npj Computational Materials 9, 146 (2023). [66] J. T. Horton, S. Boothroyd, J. Wagner, J. A. Mitchell, T. Gokey, D. L. Dotson, P. K. Behara, V. K. Ra- maswamy, M. Mackey, J. D. Chodera, et al., Open force ﬁeld bespokeﬁt: Automating bespoke torsion parametrization at scale, Journal of Chemical Informa- tion and Modeling 62, 5622 (2022). [67] D. Hao, X. He, A. E. Roitberg, S. Zhang, and J. Wang, Development and evaluation of geometry optimization algorithms in conjunction with ani potentials, Journal of Chemical Theory and Computation 18, 978 (2022). [68] S.-L. J. Lahey, T. N. Thien Phuc, and C. N. Rowley, Benchmarking force ﬁeld and the ani neural network potentials for the torsional potential energy surface of biaryl drug fragments, Journal of Chemical Information and Modeling 60, 6258 (2020). [69] B. K. Rai, V. Sresht, Q. Yang, R. Unwalla, M. Tu, A. M. Mathiowetz, and G. A. Bakken, Torsionnet: A deep neural network to rapidly predict small-molecule torsional energy proﬁles with the accuracy of quantum mechanics, Journal of Chemical Information and Mod- eling 62, 785 (2022). [70] P. K. Behara, H. Jang, J. T. Horton, T. Gokey, D. L. Dotson, S. Boothroyd, C. I. Bayly, D. J. Cole, L.-P. Wang, and D. L. Mobley, Benchmarking quantum me- chanical levels of theory for valence parametrization in force ﬁelds, The Journal of Physical Chemistry B 128, 7888 (2024). [71] F. Musil, I. Zaporozhets, F. No´e, C. Clementi, and V. Kapil, Quantum dynamics using path integral coarse-graining, The Journal of Chemical Physics 157, 10.1063/5.0120386 (2022). [72] d. NIST Mass Spectrometry Data Center, William E. Wallace, Infrared spectra (2025), retrieved January 20, 2025. [73] A. M. Reilly and A. Tkatchenko, Understanding the role of vibrations, exact exchange, and many-body van der waals interactions in the cohesive properties of molec- ular crystals, The Journal of chemical physics 139, 024705 (2013). [74] G. A. Dolgonos, J. Hoja, and A. D. Boese, Revised val- ues for the x23 benchmark set of molecular crystals, Physical Chemistry Chemical Physics 21, 24333 (2019). [75] F. Della Pia, A. Zen, D. Alf`e, and A. Michaelides, How accurate are simulations and experiments for the lattice energies of molecular crystals?, Phys. Rev. Lett. 133, 046401 (2024). [76] H. Kaur, F. Della Pia, I. Batatia, X. R. Advincula, B. X. Shi, J. Lan, G. Cs´anyi, A. Michaelides, and V. Kapil, Data-eﬃcient ﬁne-tuning of foundational models for ﬁrst-principles quality sublimation enthalpies, Faraday Discuss. 256, 120 (2025). [77] C. Caleman, P. J. van Maaren, M. Hong, J. S. Hub,

centred interatomic potentials, Nature Machine Intelli- gence 7, 56 (2025). [50] D. P. Kov´acs, C. v. d. Oord, J. Kucera, A. E. Allen, D. J. Cole, C. Ortner, and G. Cs´anyi, Linear atomic cluster expansion force ﬁelds for organic molecules: be- yond rmse, Journal of chemical theory and computation 17, 7696 (2021). [51] P. Eastman, P. K. Behara, D. L. Dotson, R. Galvelis, J. E. Herr, J. T. Horton, Y. Mao, J. D. Chodera, B. P. Pritchard, Y. Wang, et al., Spice, a dataset of drug-like molecules and peptides for training machine learning potentials, Scientiﬁc Data 10, 11 (2023). [52] A. Najibi and L. Goerigk, The nonlocal kernel in van der waals density functionals as an additive correction: An extensive analysis with special emphasis on the b97m-v and ωb97m-v approaches, Journal of Chemical Theory and Computation 14, 5725 (2018). [53] F. Weigend and R. Ahlrichs, Balanced basis sets of split valence, triple zeta valence and quadruple zeta valence quality for h to rn: Design and assessment of accuracy, Physical Chemistry Chemical Physics 7, 3297 (2005). [54] D. Rappoport and F. Furche, Property-optimized gaus- sian basis sets for molecular response calculations, The Journal of chemical physics 133 (2010). [55] S. Grimme, S. Ehrlich, and L. Goerigk, Eﬀect of the damping function in dispersion corrected density func- tional theory, Journal of computational chemistry 32, 1456 (2011). [56] S. Grimme, J. Antony, S. Ehrlich, and H. Krieg, A con- sistent and accurate ab initio parametrization of den- sity functional dispersion correction (dft-d) for the 94 elements h-pu, The Journal of chemical physics 132 (2010). [57] D. G. Smith, L. A. Burns, A. C. Simmonett, R. M. Par- rish, M. C. Schieber, R. Galvelis, P. Kraus, H. Kruse, R. Di Remigio, A. Alenaizan, et al., Psi4 1.4: Open- source software for high-throughput quantum chem- istry, The Journal of chemical physics 152 (2020). [58] J. A. Maier, C. Martinez, K. Kasavajhala, L. Wick- strom, K. E. Hauser, and C. Simmerling, ﬀ14sb: im- proving the accuracy of protein side chain and backbone parameters from ﬀ99sb, Journal of chemical theory and computation 11, 3696 (2015). [59] A. G. Donchev, A. G. Taube, E. Decolvenaere, C. Har- gus, R. T. McGibbon, K.-H. Law, B. A. Gregersen, J.-L. Li, K. Palmo, K. Siva, et al., Quantum chemical bench- mark databases of gold-standard dimer interaction en- ergies, Scientiﬁc data 8, 55 (2021). [60] C. Isert, K. Atz, J. Jim´enez-Luna, and G. Schneider, Qmugs, quantum mechanical properties of drug-like molecules, Scientiﬁc Data 9, 273 (2022). [61] J. P. Darby, D. P. Kov´acs, I. Batatia, M. A. Caro, G. L. Hart, C. Ortner, and G. Cs´anyi, Tensor-reduced atomic density representations, Physical Review Letters 131, 028001 (2023). [62] C. Schran, F. L. Thiemann, P. Rowe, E. A. M¨uller, O. Marsalek, and A. Michaelides, Machine learning po- tentials for complex aqueous systems made simple, Pro- ceedings of the National Academy of Sciences 118, e2110077118 (2021). [63] P. Eastman, P. K. Behara, D. Dotson, R. Galvelis, J. Herr, J. Horton, Y. Mao, J. Chodera, B. Pritchard, Y. Wang, G. De Fabritiis, and T. Markland, Spice 2.0.1, 10.5281/zenodo.10975225 (2024).


## 第 17 页

17

ing of peptides with classical and novel machine learn- ing force ﬁelds: A comparison, The Journal of Physical Chemistry B 125, 3598 (2021). [84] J.-S. Hu and A. Bax, Determination of ϕ and X1 An- gles in Proteins from 13C-13C Three-Bond J Couplings Measured by Three-Dimensional Heteronuclear NMR. How Planar Is the Peptide Bond?, Journal of the Amer- ican Chemical Society 119, 6360 (1997). [85] K. A. Bolin and G. L. Millhauser, α and 310: The Split Personality of Polypeptide Helices, Accounts of Chemical Research 32, 1027 (1999). [86] M. Heinig and D. Frishman, STRIDE: A web server for secondary structure assignment from known atomic co- ordinates of proteins, Nucleic Acids Research 32, W500 (2004). [87] K. N. Woods, The glassy state of crambin and the THz time scale protein-solvent ﬂuctuations possibly related to protein function, BMC Biophysics 7, 8 (2014). [88] N. J. Browining, Cuda mace, https://github.com/ nickjbrowning/cuda_mace (2024), accessed 2025-04- 15. [89] W. C. Witt, symmetrix, https://github.com/wcwitt/ symmetrix (2025), accessed 2025-04-15. [90] F. Bigi, G. Fraux, N. J. Browning, and M. Ceriotti, Fast evaluation of spherical harmonics with sphericart, J. Chem. Phys. , 064802 (2023).

L. T. Costa, and D. van der Spoel, Force ﬁeld bench- mark of organic liquids: Density, enthalpy of vaporiza- tion, heat capacities, surface tension, isothermal com- pressibility, volumetric expansion coeﬃcient, and di- electric constant, Journal of Chemical Theory and Com- putation 8, 61 (2012). [78] J. T. Horton, A. E. Allen, L. S. Dodda, and D. J. Cole, Qubekit: Automating the derivation of force ﬁeld pa- rameters from quantum mechanics, Journal of chemical information and modeling 59, 1366 (2019). [79] M. R. Shirts, D. L. Mobley, J. D. Chodera, and V. S. Pande, Accurate and eﬃcient corrections for missing dispersion interactions in molecular simulations, The Journal of Physical Chemistry B 111, 13052 (2007). [80] G. R. Medders, V. Babin, and F. Paesani, Develop- ment of a “First-Principles” Water Potential with Flex- ible Monomers. III. Liquid Phase Properties, Journal of Chemical Theory and Computation 10, 2906 (2014). [81] M. J. Gillan, D. Alf`e, and A. Michaelides, Perspective: How good is dft for water?, The Journal of Chemical Physics 144, 130901 (2016). [82] S. Zhang, R. Schweitzer-Stenner, and B. Urbanc, Do Molecular Dynamics Force Fields Capture Conforma- tional Dynamics of Alanine in Water?, Journal of Chem- ical Theory and Computation 16, 510 (2020). [83] D. Rosenberger, J. S. Smith, and A. E. Garcia, Model-


## 第 18 页

Supporting Information for:

MACE-OFF: Short Range Transferable Machine

Learning Force Fields for Organic Molecules

D´avid P´eter Kov´acs*, J. Harry Moore*, Nicholas J. Browning,¶ Ilyes Batatia,

Joshua T. Horton,§ Yixuan Pu,∥Venkat Kapil,§ William C. Witt,@ Ioan-Bogdan

Magd˘au,§ Daniel J. Cole,§ and G´abor Cs´anyi∗,

Engineering Laboratory, University of Cambridge, Cambridge, CB2 1PZ, UK

!˚ Angstr¨om AI, 2325 3rd Street, San Francisco, CA 94107, USA

¶Swiss National Supercomputing Centre (CSCS), 6900, Lugano, Switzerland

§School of Natural and Environmental Sciences, Newcastle University, Newcastle upon

Tyne NE1 7RU, UK

∥Department of Physics and Astronomy, University College, London WC1E 6BT, UK

§Yusuf Hamied Department of Chemistry, University of Cambridge, Lensﬁeld Road,

Cambridge, CB2 1EW,UK

#Thomas Young Centre and London Centre for Nanotechnology, London WC1E 6BT, UK

@Department of Materials Science and Metallurgy, University of Cambridge, 27 Charles

Babbage Road, CB3 0FS, Cambridge, United Kingdom

E-mail: jhm72@cam.ac.uk

1


## 第 19 页

S1 MACE-OFF Training Details

Initially, the force weight in the loss was set to 1000 and the energy weight to 40. The learning

rate was 0.01 and Adam optimizer with Amsgrad was used. The exponential moving average

of the weights was taken in each training step. When the force error converged, the second

phase of the training was started with force weight 10 and energy weight 1000 and the

learning rate was reduced to 0.00025. Finally, the training was terminated when the energy

error also stopped decreasing signiﬁcantly. All models were trained on a single Nvidia A100

GPU. Training the small model took about 6 days, the medium about 10 days and the large

model 14 days.

After ﬁtting the small MACE model and observing the training errors, we noticed the

presence of outliers in the dataset. This is probably caused by errors in the underlying

electronic structure calculations, some of which have been documented on the SPICE GitHub

repository.1 To conﬁrm this, we also re-evaluated a selection of the conﬁgurations that had

the highest error, using the level of DFT used in SPICE, and found that for about a third of

the conﬁgurations, the recomputed energies and forces agreed well with the MACE prediction

and not with the original DFT labels. To purify the dataset, we removed from the training

set the conﬁgurations that had a maximum force error greater than 2 eV/˚A. This meant the

removal of just 808 conﬁgurations, many of which contained heavy elements, in particular

phosphorus and iodine, that might have a more challenging electronic structure.

In common with the ﬁrst version of SPICE, close inspection of the SPICE version

2 dataset revealed several nonphysical geometries with correspondingly high DFT forces.

These conﬁgurations were removed by applying a maximum force ﬁlter of 15 eV/˚A. We also

observed that many phosphorous-containing compounds were present among the outliers, as

well as conﬁgurations with highly distorted geometries, which suggest challenging electronic

structure. We found that many conﬁgurations had forces that do not sum to zero. To avoid

1https://github.com/openmm/spice-dataset

2


## 第 20 页

the possibility of these conﬁgurations poisoning the dataset, we applied a total force ﬁlter of

0.1 eV/˚A. In total this removed 10,372 conﬁgurations from the SPICE version 2 subsets.

3


## 第 21 页

S2 Test set errors

The numerical values of the test set errors are displayed in Table S1. Intermolecular force

errors were obtained as RMSEs between DFT intermolecular forces and MACE predictions.

The intermolecular forces were computed by summing over the translational and rotational

components for each atom as shown in Ref.1. The algorithm can be summarized as follows:

1. identify molecules (labeled j)

2. within each molecule j sum over all atomic forces (labeled k) to obtain the translational

component:

F trans j = X

k∈j fk (1)

3. redistribute the molecular translational force onto individual atoms (labeled i) to obtain

the atomic translational contributions:

f trans i = mi

Mj F trans j (2)

where mi are atomic masses and Mj are molecular masses

4. similarly, compute the torque on the entire molecule:

Tj = X

k∈j fk ×   rk −Rcom j  (3)

5. compute the rotational atomic force contributions that give rise to the given molecular

torque:

f rot i = mi   ri −Rcom j  × (Iαβ j )−1Tj (4)

where Iαβ j are the molecular moments of inertia

4


## 第 22 页

Table S1: Summary of test set errors including inter-molecular force errors

PubChem DES370K Monomers DES370K Dimers Dipeptides Solvated Amino Acids Water QMugs Tripeptide

23S 1.41 1.04 0.98 0.84 1.60 1.67 1.03 1.05

E (meV/at)

23M 0.91 0.63 0.58 0.52 1.21 0.76 0.69 0.57

23L 0.88 0.59 0.54 0.42 0.98 0.83 0.45 0.38

23S 35.68 17.63 16.31 25.07 38.56 28.53 41.45 32.88

MAE

Ftotal (meV/˚A)

23M 20.57 9.36 9.02 14.27 23.26 15.27 23.58 18.74

23L 14.75 6.58 6.62 10.19 19.43 13.57 16.93 13.20

23S 0.13 0.18 3.01 0.07 16.98 19.03 0.09 0.07

Finter (meV/˚A)

23M 0.13 0.18 1.79 0.07 10.30 10.03 0.09 0.07

23L 0.13 0.18 1.44 0.07 8.85 8.97 0.09 0.07

23S 0.00 0.00 0.00 0.00 0.01 8.44 0.00 0.00

E (%)

23M 0.00 0.00 0.00 0.00 0.00 3.84 0.00 0.00

Relative MAE

23L 0.00 0.00 0.00 0.00 0.00 4.18 0.00 0.00

23S 4.65 2.72 3.46 3.55 3.16 4.50 4.12 3.66

Ftotal (%)

23M 2.68 1.45 1.91 2.02 1.90 2.41 2.35 2.09

23L 1.92 1.02 1.40 1.44 1.59 2.14 1.68 1.47

23S nan nan 15.52 nan 21.66 21.19 nan nan

Finter (%)

23M nan nan 9.25 nan 13.14 11.17 nan nan

23L nan nan 7.44 nan 11.29 9.99 nan nan

23S 2.74 1.47 1.51 1.26 1.98 2.07 1.28 1.40

E (meV/at)

23M 2.02 0.90 0.91 0.85 1.55 0.99 0.89 0.75

23L 2.48 0.84 0.87 0.70 1.32 0.99 0.58 0.49

23S 61.83 26.15 28.48 36.97 53.55 39.33 62.46 71.41

RMSE

Ftotal (meV/˚A)

23M 40.51 14.31 16.81 22.25 32.19 21.40 36.73 33.94

23L 33.34 10.27 12.81 16.19 26.91 18.78 27.17 22.46

23S 0.78 0.44 8.70 0.13 27.11 27.59 0.17 0.12

Finter (meV/˚A)

23M 0.79 0.44 5.54 0.13 16.46 15.05 0.17 0.12

23L 0.76 0.44 4.34 0.13 14.24 13.39 0.17 0.12

23S 0.00 0.00 0.00 0.00 0.01 8.30 0.00 0.00

E (%)

23M 0.00 0.00 0.00 0.00 0.00 3.96 0.00 0.00

Relative RMSE

23L 0.00 0.00 0.00 0.00 0.00 3.98 0.00 0.00

23S 5.56 2.79 4.13 3.63 3.47 4.58 4.66 5.45

Ftotal (%)

23M 3.64 1.52 2.44 2.19 2.09 2.49 2.74 2.59

23L 3.00 1.09 1.86 1.59 1.74 2.19 2.03 1.71

23S nan nan 8.95 nan 20.17 20.18 nan nan

Finter (%)

23M nan nan 5.70 nan 12.25 11.00 nan nan

23L nan nan 4.46 nan 10.60 9.79 nan nan

5


## 第 23 页

6. compute the vibrational contribution as the diﬀerence:

f vib i = fi −f trans i −f rot i (5)

7. the intermolecular force is calculated as the sum of the translational and rotational

contributions.

Relative errors were obtained by dividing the absolute errors by the typical DFT force

magnitudes:

i |f DFT i −f MACE i | P

Rel MAE = P

i |f DFT i −¯f DFT| (6)

sP

i(f DFT i −f MACE i )2

i(f DFT i −¯f DFT)2 (7)

Rel RMSE =

P

where ¯f DFT = P

i f DFT i /N is the average DFT force (often zero).

Table S1 shows these errors computed for all three MACE models on each category of

atomic conﬁgurations found in the test set. Interestingly, even though PubChem, DES370K

Monomers, Dipeptides, QMugs and Tripeptides comprise only isolated molecule conﬁgura-

tions, we ﬁnd a small error that is incorrectly attributed to intermolecular interactions. This

issue arises because DFT forces in these test data to not obey translational and rotational

symmetry, i.e. total molecular force and torque do not sum to zero, even though a single

molecule is present in each simulation box. Meanwhile, MACE forces do obey these symme-

tries, and therefore the diﬀerence shows up as an intermolecular error which is identical for

all three MACE models.

The code used for this analysis is available at https://github.com/imagdau/aseMolec.

git.

6


## 第 24 页

S2.1 MACE-OFF24(M) Test Errors

Table S2: Test set errors for MACE-OFF24(M)

MAE Energy (meV/atom) MAE Force (meV/˚A)

PubChem 1.0 22.1 DES370K Monomers 0.6 9.6 DES370K Dimers 0.6 9.3 Dipeptides 0.5 14.4 QMugs 0.8 23.8 Solvated Amino Acids 1.3 23.2 Amino Acid-Ligand 1.5 24.2 Solvated PubChem 1.2 22.8

7


## 第 25 页

S3 Torsion angle scanning calculations

The TorsionNet-5002 and biaryl torsion3 benchmark datasets were recomputed at the SPICE4

level of QM theory (ωB97M-D3(BJ)/def2-TZVPPD5–9) to assess the accuracy of the MACE

models in predicting the potential energy surfaces of rotatable bonds commonly found in

drug-like molecules. Starting from the published optimized geometries, a torsion scan was

performed using TorsionDrive10 via its interface with QCEngine11. The dihedral angles

were scanned in 15◦increments and each constrained geometry optimization was carried out

with geomeTRIC12, using PSI413 to calculate the DFT energies and forces. For each of

the assessed force ﬁeld models, a separate constrained geometry optimization was performed

starting from the DFT reference geometries and holding the target torsion ﬁxed at each grid

point value. The ﬁnal RMSD between the optimized and reference geometry was recorded,

along with the energy to calculate the potential energy surfaces.

8


## 第 26 页

S4 Lattice enthalpies

First, the internal energy of the crystalline form was computed under the harmonic approx-

imation:

∂ln Z

!

U(T) =

(8)

∂ 1

kBT

= EMACE + Z ∞

 Ã(ϵ)dϵ

 ϵ

kBT −1 + ϵ

ϵ

2

e

0

where Z denotes the partition function of the system, and Ã(ϵ) represents the degeneracy or

phonon density of states as a function of vibrational energy. The above expression contains

an electronic contribution, computed using MACE, a zero point energy contribution, and a

contribution from ﬁnite-temperature vibrational energy. To compute the vibrational contri-

bution, we used a 3 × 3 × 3 supercell for all the molecules considered. For the gaseous form

of the molecules, we employed the ideal gas approximation to compute the enthalpies of the

gas as:

U(T) = eMACE + EZPE + Z T

0 CpdT (9)

where we used the ideal gas value to evaluate the last term, giving 4RT for all system except

for the linear carbon-dioxide, where the value is 3.5RT.

Combining the above two expressions, we can compute the sublimation enthalpies as:

∆Hsubm = Ugas(T) −Ucryst(T) (10)

= Elatt + ∆Evib + 4RT

To assess the accuracy of the MACE model we used the X23 set of molecular crystals14.

We ﬁrst relaxed the cells, followed by phonon and normal mode calculations to obtain the

ﬁnite temperature vibrational as well as zero point contributions to the enthalpies, following

the protocol above. It is important to note that for the ANI-2x force ﬁeld it was not possible

9


## 第 27 页

to fully relax the crystal geometries, because the model cannot predict stresses. Hence, we

kept the cell ﬁxed at the DFT equilibrium values from Ref.14. The results are summarized

in Table S3.

Table S3: Sublimation enthalphy in kJ/mol

System ∆H0 sub exp. ∆H0 sub MACE-OFF23(S) ∆H0 sub MACE-OFF23(M) ∆H0 sub MACE-OFF23(L) ∆H0 sub ANI-2x

1,4- Cyclohexanedione 81.1 85.1 77.7 85.1 59.7

Acetic acid 67.7 77.2 71.4 70.3 90.7 Adamantane 61.6 88.7 65.6 69.2 67.1 Ammonia 31.2 24.4 30.9 26.8 23.0 Anthracene 101.9 118.8 95.7 106.3 98.9 Benzene 44.9 49.4 48.1 58.4 48.3 Carbon dioxide 26.1 -35.2 -1.44 4.1 -117.9 Cyanamide 75.5 85.8 94.5 87.3 36.9 Cytosine 156.4 159.8 142.8 143.2 118.6 Ethyl carbamate 78.8 88.7 90.9 91.4 77.0 Formamide 71.7 82.2 75.0 80.1 67.3 Hexamine 75.8 58.4 89.5 62.3 83.5 Imidazole 81.4 88.7 91.6 86.3 86.6 Naphthalene 72.6 88.9 80.1 83.6 72.4 Oxalic acid α 93.7 98.5 89.5 89.7 44.1 Oxalic acid β 93.6 90.0 95.2 93.5 45.4 Pyrazine 56.3 86.4 70.0 69.7 53.7 Pyrazole 72.4 67.5 78.6 73.0 75.4 s-Triazine 55.7 58.4 64.9 75.6 112.1 s-Trioxane 56.3 75.8 59.9 53.9 51.7 Succinic acid 123.1 132.5 119.7 123.5 141.7 Uracil 129.2 139.7 127.2 131.8 98.9 Urea 93.8 121.5 114.0 112.5 78.2

10


## 第 28 页

S5 Crystal structure geometries

In Table S4 we compare the MACE-OFF23(L) relaxed crystal structure lattice parameters

with the experimental ones reported in Ref.15. We conﬁrm that MACE is able to accurately

reproduce the lattice constant of molecular crystals purely trained on molecular dimers.

Additional trimer training data, or a higher level of reference theory, such as coupled cluster,

could probably further improve the agreement with experiments.

Table S4: Crystal structure geometries

Molecule Texp Experiment MACE-OFF23(L)

Acetic acid 40 a 13.151 13.359 b 3.923 3.809 c 5.762 5.542 V 297.27 282.01 Ammonia 2 a 5.048 4.946 V 128.63 120.98 Benzene 4 a 7.351 6.59 b 9.364 9.303 c 6.695 6.851 V 460.84 420.51 Naphthalene 10 a 8.0846 7.821 b 5.9375 5.836 c 8.6335 8.430 ´ 124.67 125.26 V 340.83 314.23 Pyrazine 184 a 9.325 9.351 b 5.850 5.508 c 3.733 3.545 V 203.64 182.57 Urea 40 a 5.565 5.330 c 4.684 4.670 V 145.06 123.68

11


## 第 29 页

S6 Condensed phase simulations

Water density simulations were seeded using OpenMM’s Modeller functionality, with a

padding of 12.5 ˚A from the central water molecule to the box edge, resulting in box edge

of 25 ˚A. Simulations were run for 500 000 steps with a 1 fs timestep, resulting in a 500 ps

trajectory. The density was recorded every 100 steps. After an initial 100 ps period of equi-

libration, the density was calculated by averaging over the remaining 400 ps of trajectory.

Initial PDB ﬁles for the remaining organic liquid simulations were taken from Ref.16

and periodic boxes were generated using packmol17. Boxes were prepared containing 64

molecules, with box vectors determined such that the initial density was 80% of the ex-

perimental density. Structures were minimized with the L-BFGS algorithm prior to MD.

Molecular dynamics was performed with OpenMM, using a custom fork of the openmm-ml

package to interface MACE models to the MD code.2 Simulations were performed in the

NPT ensemble. The Langevin equations of motion were integrated with a timestep of 1 fs

and a Monte Carlo barostat was used to maintain pressure at 1 atm. Temperatures were

maintained at 298 K except for those compounds whose boiling point was below this value,

for which a value of 10 K below the experimental boiling point was used. Dynamics were

propagated for 300 ps, and the ﬁnal density was calculated by averaging over the ﬁnal 100 ps

of the simulation.

Heat of vaporization calculations additionally required simulation of the isolated molecule

in the vacuum phase, which were carried out on a nonperiodic molecule. Final energies for

both condensed and vacuum phases were calculated by averaging over the ﬁnal 100 ps of

each trajectory.

Tables S5 and S6 summarize the overall density and heat of vaporization errors for the

MACE-OFF23(S) and MACE-OFF23(M) models. Although the computational expense of

the MACE-OFF23(L) is prohibitive for these condensed phase simulations, we nonetheless

2https://github.com/jharrymoore/openmm-ml/tree/main

12


## 第 30 页

benchmarked the large model on a small selection of condensed phase systems. We saw

comparable performance to the medium model, and in particular observed that compounds

that had a high prediction error under the medium model had a similar error under the large

model. This indicates that this error is driven primarily by the dataset rather than by the

size of the model, as previously hypothesized.

To investigate this further, Tables S5 and S6 additionally show statistics for MACE-

OFF24(M), which employs an extended cutoﬀof 6 ˚A and has also been trained on additional

nonbonded data. We observe a modest decrease in MAE for the heat of vaporization from

2.18 to 1.75 kcal/mol, as well as a small decrease in the accuracy of liquid density predictions.

This further reinforces the hypothesis that the poorly predicted densities are a result of

under-representation of the functional groups, since the additional SPICE training sets do

little to increase sampling of these problematic functional groups.

Table S5: Summary of density errors

MAE / g/cm3 RMSE / g/cm3 r

MACE-OFF23(S) 0.23 0.38 0.20 MACE-OFF23(M) 0.09 0.15 0.89 MACE-OFF24(M) 0.14 0.34 0.26 ANI-2x 0.21 0.36 0.26

Table S6: Summary of ∆Hvap errors

MAE / kcal/mol RMSE / kcal/mol r

MACE-OFF23(S) 1.48 2.19 0.86 MACE-OFF23(M) 2.18 2.53 0.87 MACE-OFF24(M) 1.75 2.81 0.78 ANI-2x 2.75 3.45 0.66

13


## 第 31 页

S7 Biological Simulations

S7.1 Ala3 Free Energy Surface

Molecular dynamics simulations were performed with OpenMM, as in the previous section.

Enhanced sampling simulations were performed with metadynamics. Two collective variables

were deﬁned by the two torsion angles on the backbone of the central alanine residue. A 1 ns

simulation was performed with a temperature bias factor of 10, a barrier height of 1 kJ/mol

and a frequency of 100 steps.

S7.2 Ala15 peptide folding

The initial extended structure was generated using PyMOL. The system was propagated with

Langevin dybamics using a 1 fs timestep for 500 ps in vacuo via the OpenMM interface.

S7.2.1 Secondary structure prediction with MACE-OFF23(M)

Compared to MACE-OFF24(M) (see main text), the previous 5 ˚A model failed to repro-

duce the experimentally observed oscillation between the α-helix and the 310 helix, instead

predicting only the α-helical structure

14


## 第 32 页

Figure S1: Secondary structure (and temperature dependence) of Ala15 predicted by MACE- OFF23(M). Single letter codes correspond to standard STRIDE secondary structure labels, where H=α-helix, E=extended and C=random coil

S7.3 Crambin in explicit solvent

Crambin was prepared from the PDB structure 1EJG. The initial structure was prepared

using pdbﬁxer18 and solvated in an orthorombic box with padding between solute and the

box edge set to 1.2 nm. Dynamics were performed in the NPT emsemble, with pressure

15


![image_13](images/image_0013.png)


![image_14](images/image_0014.jpeg)


## 第 33 页

maintained at 1 atm with a Monte Carlo barostat, as implemented in OpenMM. A 1 fs

timestep was used both for integrating the Langevin equations of motion and for writing the

trajectory to disk for post processing. The power spectrum was calculated as the Fourier

transform of the velocity autocorrelation function using the Travis program with default

settings19–22.

Figure S2: Crambin RMSD. RMSD calculated by averaging two halves of a 1 ns trajectory, relative to the ﬁrst frame and computed on Cα atoms.

16


## 第 34 页

S8 Dipole models

S8.1 MACE-OFF23-µ

In addition to the series of MACE-OFF force ﬁeld models, we also developed MACE-OFF23-

µ, which predicts the total dipole moment of molecules and can be used, in combination with

a regular MACE-OFF model for energies and forces, to estimate vibrational spectra based on

the autocorrelation of the dipole moment. The model architecture is identical to the MACE

architecture described in the Methods in the main text, with the only diﬀerence being the

readout function, which produces an L = 1 tensor for each atom instead of the atomic site

energies. Given the equivariant order of the readout, the smallest possible model corresponds

to the ‘medium’ architecture, which is the one considered in this work. Other than the read-

out’s equivariant order, all hyperparameters match those of the MACE-OFF23(M) model.

MACE-OFF23-µ was trained on the subset of SPICE4 for which a total dipole moment was

available, resulting in the exclusion of the QMugs and water subsets.

We assess the accuracy of the MACE-OFF23-µ model on the held-out SPICE test sets,

evaluating its eﬀectiveness for predicting dipole moments and infrared spectra of organic

molecules. Figure S3 summarizes this performance by examining the alignment between the

violin distributions of the reference and predicted total dipole moment values, as well as the

RMSEs. The small RMSEs and strong alignment of the distributions indicate high ﬁdelity

across the test datasets for which reference dipole moment values were available. These

results suggest promising performance for zero-shot predictions of the dipole moments (and

infrared spectra) of unseen organic molecules, as demonstrated in a recent benchmark on

out-of-distribution drug-like molecules from the NIST database23. The MACE-OFF23-µ

model is available at: https://github.com/venkatkapil24/MACE-OFF-mu-models.

17


## 第 35 页

10

RMSE:   0.11

RMSE:   0.02

RMSE:   0.13

RMSE:   0.01

RMSE:   0.21

8

Reference

Prediction

Total dipole moment [e Å]

6

4

2

0

DES   370 K  Dimers

DES   370 K  Monomers

Solvated   Amino  Acids

PubChem

Dipeptides

2

Figure S3: Test set prediction and root mean square errors (RMSE). Violin plots of the reference (blue) and predicted (red) distributions of the dipole moment predicted using MACE-OFF23-µ. The RMSEs are reported above the violin plots for the individual test sets.

18


## 第 36 页

S8.2 Computational details

To compute the vibrational spectrum for the paracetamol form II polymorph, we ﬁrst per-

formed a 20 ps path-integral MD simulation using the MACE-OFF23(S) model at 500 K,

following the prescriptions of the Path Integral coarse-Grained Simulations (PIGS) ap-

proach24,25. The path-integral MD simulations are performed with a 0.50 fs timestep us-

ing the BAOAB integration scheme extended to path-integral MD26 using the path-integral

Langevin equation thermostats27 with a time constant of 100 fs.

To generate a potential energy surface that eﬀectively encodes quantum nuclear eﬀects,

we followed the PIGS technique. We used the positions and forces on the centroid of the

path-integral to ﬁt a MACE model that represents the diﬀerence between the potential

energy surface and the potential of mean force on the centroid at an elevated temperature

of 500 K. The sum of MACE-OFF23(S) and the PIGS model gives a transferable eﬀective

potential energy surface that encodes quantum nuclear eﬀects.

To generate a trajectory with quantum nuclear motion, we run MD with the sum of

MACE-OFF23(S) and the PIGS model using the i-PI28 software to propagate the equations

of motion and the ASE calculator as the force-provider. The MD simulations were performed

with a 0.50 fs timestep using a weak global stochastic velocity rescaling thermostat. To

generate classical trajectories we perform MD with the same setup but without the PIGS

potential.

We predicted the L = 0 and L = 2 spherical harmonic components of polarizability

tensors on the trajectories and computed their time correlation functions to obtain the

isotropic and anisotropic Raman spectra24. We estimate the powder Raman spectrum as a

linear combination of the isotropic and the anisotropic Raman spectra29.

The model architecture was identical to the MACE architecture used for the energy

models, with the only diﬀerence being the readout function producing a vector and a tensor

(dipole and polarisability) for each atom, instead of the atomic site energies. A relatively

19


## 第 37 页

small MACE model is already capable of achieving high accuracy predictions, and the se-

lected models used the hyperparameters displayed in Table S7.

Table S7: Hyperparameters of the MACE models for dipoles and polarizabilities

Paracetamol Water

Cutoﬀradius (˚A) 5.0 6.0

Chemical channels 16 32 k (Eq. 1) max L (Eq. 5) 2 2

S8.3 Vibrational spectroscopy of paracetamol

Raman spectroscopy is one of the most widely used techniques for characterizing molecular

crystals. Unlike IR spectroscopy, which only detects vibrational modes that distort dipoles,

Raman spectroscopy is more sensitive to collective modes governed by weak, non-bonded in-

teractions in a broad range of molecular materials. The low-frequency region of the Raman

spectrum (e.g., the THz regime) gives a vibrational ﬁngerprint of the intermolecular inter-

actions. Thus, it is widely used to diﬀerentiate between polymorphs of molecular crystals.

Meanwhile, the high-frequency Raman spectrum probes intramolecular modes and their cou-

pling to low-frequency modes.

Here, we test the ability of the MACE-OFF23(S) model to predict the Raman spec-

trum of the “Form II” polymorph of paracetamol. To compare MACE-OFF23(S) directly

with experiments, we rigorously incorporate quantum nuclear and non-Condon eﬀects using

our ML-aided framework24. We incorporate quantum nuclear eﬀects by ﬁtting an eﬀective

potential energy surface25 (using MACE) to calculate quantum nuclear corrections to the

MACE-OFF23(S) model within the path-integral coarse-grained simulations (PIGS) method.

To incorporate non-Condon eﬀects, we ﬁt a separate equivariant MACE model to the ﬁrst-

principles polarizability of paracetamol polymorphs (data taken from Refs. 30,31). The

20


## 第 38 页

remaining steps of our quantum nuclear simulations mimic an entirely classical calculation

involving a NV E molecular dynamics simulation, prediction of the isotropic and anisotropic

components of the polarizability tensor, and calculation of their time correlation functions.

For further details we refer the reader to Ref. 24.

As shown in Figure S4, we predict both the high- and low-frequency regions of the Ra-

man spectrum of paracetamol form II with an overall good agreement with the experimental

band positions32. Since the experiment captures the Raman spectra along diﬀerent crystal

directions while we estimate the “powder” Raman spectrum31, we do not compare band

intensities. We ﬁnd that the classical predictions (based on MACE classical MD) are consis-

tently shifted with respect to the experiment. At the same time, quantum nuclear predictions

(encoded by the PIGS method) play an essential role in improving the agreement between

theory and experiments. Moreover, we note that a broad band at around 3300 cm−1 is

only captured at the level incorporating quantum nuclear eﬀects. The low-frequency modes

also agree semi-quantitatively with the experiments and do not require a quantum nuclear

description. The 2–3 % overall shift in the vibrational frequencies notwithstanding, the

MACE-OFF23(S) combined with quantum nuclear eﬀects and non-Condon eﬀects shows

promising capabilities for the characterization of molecular crystals.

S8.4 Vibrational spectroscopy of liquid water

Next, we characterize the dynamical properties of water by computing the vibrational den-

sity of states, including the IR and Raman spectra selection rules, using MACE models

of dipoles and polarizabilities24. Given the signiﬁcant impact of quantum nuclear motion

on the dynamics of water25, we incorporate quantum nuclear eﬀects using the PIGS ap-

proach25 (discussed in Section S8.3), which has a classical cost and has recently been shown

to describe quantum nuclear eﬀects in water accurately34. As shown in Figure S5, after

incorporating quantum nuclear eﬀects, the MACE-OFF23(S) predictions agree with the ex-

21


## 第 39 页

Paracetamol Form II Raman Spectrum

MACE-OFF23(S) MD MACE-OFF23(S) PIMD Experiment

Raman intensity [arb.]

300 400 500 600 700

3000 3100 3200 3300 3400 3500 3600 3700

[cm 1]

[cm 1]

Figure S4: Powder Raman spectrum of paracetamol form II33. Spectrum computed at ambient conditions using the MACE-OFF23(S) model for the potential energy surface, a MACE model of the polarizability, and a MACE model that incorporates quantum nuclear eﬀects on the potential energy surface using the PIGS approach25. The black lines represent experimentally determined band positions32, scaled by 3% to aid visual comparison with the predicted spectra. We focus on high and low frequency features of the spectrum where experimental peaks are well separated.

periments across the entire frequency range. We note the presence of an overall 2-3 % blue

shift with respect to the experiments, consistent with the spectra for paracetamol form II

(see Section S8.3). MACE-OFF23(S) even qualitatively captures subtle features of the spec-

tra, including the 0 – 1000 cm−1 hydrogen bonding ﬁngerprints in the anisotropic Raman

spectrum, and the bimodal nature of the isotropic Raman stretching band arising from the

presence of hydrogen-bonded defects in room temperature water.

22


## 第 40 页

Figure S5: IR, isotropic Raman and anisotropic Raman spectra of water at ambient temper- ature and density using the MACE-OFF23(S) model for the potential energy surface and a single MACE model of water’s dipole and polarizability24. The black curve represents the experiment35. The dashed blue curve is obtained from classical MD, while the solid curve incorporates quantum eﬀects using the PIGS method25.

23


## 第 41 页

S9 Computational performance in LAMMPS

MACE-OFF23(S) in LAMMPS (CPU)

MACE-OFF23(S) in LAMMPS (GPU)

128 CPUs (1 node) 432 atoms/node 3600 atoms/node

1 GPU, OPT* 1 GPU, Kokkos 1 GPU, Torch 432 atoms/GPU 3600 atoms/GPU

10

10

Throughput (Million steps/day)

Throughput (Million steps/day)

8

8

30 nodes

6

6

4

4

30 GPUs

2

2

0

0

102 103 104 105

102 103 104 105

Number of atoms

Number of atoms

Figure S6: Throughput in LAMMPS. Performance of molecular dynamics in LAMMPS for water in the NVT ensemble at 1 g/cm3 and 300 K with a 1 fs timestep. All simulations used variants of the MACE-OFF23(S) model.

The left panel highlights CPU performance achievable on the UK-based Archer2 CPU supercomputer, using the new pure-C++ MACE implementation. The solid black curve demonstrates the throughput of a single 128-core node as a function of the number of atoms. The two dotted curves demonstrate weak scaling with 432 atoms/node or 3600 atoms/node. All calculations used double precision ﬂoating point numbers.

The right panel demonstrates the performance of the GPU evaluators. The three solid curves provide single-GPU results (determined with NVIDIA A100 80GB GPUs) for the native Torch-based MACE-OFF23(S), a custom Kokkos-based MACE implementation, and the cuda mace implementation marked as OPT*. The asterisk indicates that these latter simulations used single precision ﬂoating point numbers, with error correction for the most numerically sensitive terms, in contrast to the remaining calculations which were performed with double precision. Finally, the two dashed curves demonstrate the performance when multiple GPUs are employed, using the pure-Kokkos implementation, to access larger systems with domain decomposition. More work is needed to improve this weak scaling.

24


## 第 42 页

MACE-OFF23(S) in LAMMPS (CPU)

MACE-OFF23(S) in LAMMPS (GPU)

150

150

128 CPUs (1 node)

1 GPU, OPT* 1 GPU, Kokkos 1 GPU, Torch

Time per step (ms)

Time per step (ms)

100

100

50

50

0

0

0 1000 2000 3000 4000 5000 Number of atoms

0 1000 2000 3000 4000 5000 Number of atoms

Figure S7: Evaluation speed in LAMMPS. Data from Figure S6, replotted to show the average duration of each timestep.

25


## 第 43 页

References

(1) Magd˘au, I.-B.; Arismendi-Arrieta, D. J.; Smith, H. E.; Grey, C. P.; Hermansson, K.;

Cs´anyi, G. Machine learning force ﬁelds for molecular liquids: Ethylene Carbon-

ate/Ethyl Methyl Carbonate binary solvent. npj Computational Materials 2023, 9,

146.

(2) Rai, B. K.; Sresht, V.; Yang, Q.; Unwalla, R.; Tu, M.; Mathiowetz, A. M.; Bakken, G. A.

Torsionnet: A deep neural network to rapidly predict small-molecule torsional energy

proﬁles with the accuracy of quantum mechanics. Journal of Chemical Information and

Modeling 2022, 62, 785–800.

(3) Lahey, S.-L. J.; Thien Phuc, T. N.; Rowley, C. N. Benchmarking force ﬁeld and the

ani neural network potentials for the torsional potential energy surface of biaryl drug

fragments. Journal of Chemical Information and Modeling 2020, 60, 6258–6268.

(4) Eastman, P.; Behara, P. K.; Dotson, D. L.; Galvelis, R.; Herr, J. E.; Horton, J. T.;

Mao, Y.; Chodera, J. D.; Pritchard, B. P.; Wang, Y.; others Spice, a dataset of drug-

like molecules and peptides for training machine learning potentials. Scientiﬁc Data

2023, 10, 11.

(5) Najibi, A.; Goerigk, L. The nonlocal kernel in van der Waals density functionals as

an additive correction: An extensive analysis with special emphasis on the B97M-V

and ωB97M-V approaches. Journal of Chemical Theory and Computation 2018, 14,

5725–5738.

(6) Weigend, F.; Ahlrichs, R. Balanced basis sets of split valence, triple zeta valence and

quadruple zeta valence quality for H to Rn: Design and assessment of accuracy. Physical

Chemistry Chemical Physics 2005, 7, 3297–3305.

(7) Rappoport, D.; Furche, F. Property-optimized Gaussian basis sets for molecular re-

sponse calculations. The Journal of chemical physics 2010, 133.

26


## 第 44 页

(8) Grimme, S.; Ehrlich, S.; Goerigk, L. Eﬀect of the damping function in dispersion cor-

rected density functional theory. Journal of computational chemistry 2011, 32, 1456–

1465.

(9) Grimme, S.; Antony, J.; Ehrlich, S.; Krieg, H. A consistent and accurate ab initio

parametrization of density functional dispersion correction (DFT-D) for the 94 elements

H-Pu. The Journal of chemical physics 2010, 132.

(10) Qiu, Y.; Smith, D. G.; Stern, C. D.; Feng, M.; Jang, H.; Wang, L.-P. Driving torsion

scans with wavefront propagation. The Journal of chemical physics 2020, 152.

(11) Smith, D. G.; Lolinco, A. T.; Glick, Z. L.; Lee, J.; Alenaizan, A.; Barnes, T. A.;

Borca, C. H.; Di Remigio, R.; Dotson, D. L.; Ehlert, S.; others Quantum chemistry

common driver and databases (QCDB) and quantum chemistry engine (QCEngine):

Automation and interoperability among computational chemistry programs. The Jour-

nal of chemical physics 2021, 155.

(12) Wang, L.-P.; Song, C. Geometry optimization made simple with translation and rota-

tion coordinates. The Journal of chemical physics 2016, 144.

(13) Smith, D. G.; Burns, L. A.; Simmonett, A. C.; Parrish, R. M.; Schieber, M. C.;

Galvelis, R.; Kraus, P.; Kruse, H.; Di Remigio, R.; Alenaizan, A.; others PSI4 1.4:

Open-source software for high-throughput quantum chemistry. The Journal of chemi-

cal physics 2020, 152.

(14) Reilly, A. M.; Tkatchenko, A. Understanding the role of vibrations, exact exchange, and

many-body van der Waals interactions in the cohesive properties of molecular crystals.

The Journal of chemical physics 2013, 139, 024705.

(15) Dolgonos, G. A.; Hoja, J.; Boese, A. D. Revised values for the X23 benchmark set of

molecular crystals. Physical Chemistry Chemical Physics 2019, 21, 24333–24344.

27


## 第 45 页

(16) Horton, J. T.; Allen, A. E.; Dodda, L. S.; Cole, D. J. QUBEKit: Automating the deriva-

tion of force ﬁeld parameters from quantum mechanics. Journal of chemical information

and modeling 2019, 59, 1366–1381.

(17) Mart´ınez, L.; Andrade, R.; Birgin, E. G.; Mart´ınez, J. M. PACKMOL: A package for

building initial conﬁgurations for molecular dynamics simulations. Journal of Compu-

tational Chemistry 2009, 30, 2157–2164.

(18) Eastman, P.; Swails, J.; Chodera, J. D.; McGibbon, R. T.; Zhao, Y.; Beauchamp, K. A.;

Wang, L.-P.; Simmonett, A. C.; Harrigan, M. P.; Stern, C. D.; Wiewiora, R. P.;

Brooks, B. R.; Pande, V. S. OpenMM 7: Rapid Development of High Performance

Algorithms for Molecular Dynamics. PLOS Computational Biology 2017, 13, e1005659.

(19) Brehm, M.; Kirchner, B. TRAVIS - A Free Analyzer and Visualizer for Monte Carlo

and Molecular Dynamics Trajectories. Journal of Chemical Information and Modeling

2011, 51, 2007–2023.

(20) Brehm, M.; Thomas, M.; Gehrke, S.; Kirchner, B. TRAVIS—A Free Analyzer for

Trajectories from Molecular Simulation. The Journal of Chemical Physics 2020, 152,

164105.

(21) Thomas, M.; Brehm, M.; Fligg, R.; V¨ohringer, P.; Kirchner, B. Computing Vibrational

Spectra from Ab Initio Molecular Dynamics. Physical Chemistry Chemical Physics

2013, 15, 6608–6622.

(22) Thomas, M.; Brehm, M.; Kirchner, B. Voronoi Dipole Moments for the Simulation

of Bulk Phase Vibrational Spectra. Physical Chemistry Chemical Physics 2015, 17,

3207–3213.

(23) Pracht, P.; Pillai, Y.; Kapil, V.; Cs´anyi, G.; G¨onnheimer, N.; Vondr´ak, M.; Mar-

graf, J. T.; Wales, D. J. Eﬃcient Composite Infrared Spectroscopy: Combining the

28


## 第 46 页

Double-Harmonic Approximation with Machine Learning Potentials. Journal of Chem-

ical Theory and Computation 2024, 20, 10986–11004.

(24) Kapil, V.; Kov´acs, D. P.; Cs´anyi, G.; Michaelides, A. First-principles spectroscopy

of aqueous interfaces using machine-learned electronic and quantum nuclear eﬀects.

Faraday Discussions 2023,

(25) Musil, F.; Zaporozhets, I.; No´e, F.; Clementi, C.; Kapil, V. Quantum dynamics using

path integral coarse-graining. The Journal of Chemical Physics 2022, 157.

(26) Kapil, V.; Wieme, J.; Vandenbrande, S.; Lamaire, A.; Van Speybroeck, V.; Ceriotti, M.

Modeling the Structural and Thermal Properties of Loaded Metal–Organic Frameworks.

An Interplay of Quantum and Anharmonic Fluctuations. Journal of Chemical Theory

and Computation 2019, 15, 3237–3249.

(27) Ceriotti, M.; Parrinello, M.; Markland, T. E.; Manolopoulos, D. E. Eﬃcient stochastic

thermostatting of path integral molecular dynamics. The Journal of Chemical Physics

2010, 133.

(28) Kapil, V. et al. i-PI 2.0: A universal force engine for advanced molecular simulations.

Computer Physics Communications 2019, 236, 214–223.

(29) Raimbault, N.; Athavale, V.; Rossi, M. Anharmonic eﬀects in the low-frequency vibra-

tional modes of aspirin and paracetamol crystals. Physical Review Materials 2019, 3,

053605.

(30) Raimbault, N.; Grisaﬁ, A.; Ceriotti, M.; Rossi, M. Using Gaussian process regression to

simulate the vibrational Raman spectra of molecular crystals. New Journal of Physics

2019, 21, 105001.

(31) Raimbault, N.; Grisaﬁ, A.; Ceriotti, M.; Rossi, M. Using Gaussian process regression to

29


## 第 47 页

simulate the vibrational Raman spectra of molecular crystals. New Journal of Physics

2019, 21, 105001.

(32) Kolesov, B. A.; Mikhailenko, M. A.; Boldyreva, E. V. Dynamics of the intermolecu-

lar hydrogen bonds in the polymorphs of paracetamol in relation to crystal packing

and conformational transitions: a variable-temperature polarized Raman spectroscopy

study. Physical Chemistry Chemical Physics 2011, 13, 14243.

(33) Raimbault, N.; Athavale, V.; Rossi, M. Anharmonic eﬀects in the low-frequency vi-

brational modes of aspirin and paracetamol crystals. Physical Review Materials 2019,

3.

(34) Ceriotti, M.; Fang, W.; Kusalik, P. G.; McKenzie, R. H.; Michaelides, A.;

Morales, M. A.; Markland, T. E. Nuclear Quantum Eﬀects in Water and Aqueous

Systems: Experiment, Theory, and Current Challenges. Chemical Reviews 2016, 116,

7529–7550.

(35) Morawietz, T.; Marsalek, O.; Pattenaude, S. R.; Streacker, L. M.; Ben-Amotz, D.;

Markland, T. E. The Interplay of Structure and Dynamics in the Raman Spectrum of

Liquid Water over the Full Frequency and Temperature Range. The Journal of Physical

Chemistry Letters 2018, 9, 851–857.

30
