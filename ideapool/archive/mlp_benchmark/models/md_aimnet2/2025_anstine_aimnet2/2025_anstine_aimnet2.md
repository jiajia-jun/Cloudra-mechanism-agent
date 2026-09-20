
## 第 1 页

Volume 16 Number 23 21 June 2025 Pages 10067–10624

Chemical   Science

rsc.li/chemical-science

ISSN 2041-6539

EDGE ARTICLE Olexandr Isayev et al. AIMNet2: a neural network potential to meet your neutral,  charged, organic, and elemental-organic needs


![image_1](images/image_0001.jpeg)


## 第 2 页

Chemical Science

EDGE ARTICLE

AIMNet2: a neural network potential to meet your neutral, charged, organic, and elemental-organic needs†

Cite this: Chem. Sci., 2025, 16, 10228

All publication charges for this article have been paid for by the Royal Society of Chemistry

Dylan M. Anstine,‡ Roman Zubatyuk‡ and Olexandr Isayev *

Machine learned interatomic potentials (MLIPs) are reshaping computational chemistry practices because

of their ability to drastically exceed the accuracy-length/time scale tradeoﬀ. Despite this attraction, the

beneﬁts of such eﬃciency are only impactful when an MLIP uniquely enables insight into a target system

or is broadly transferable outside of the training dataset. In this work, we present the 2nd generation of our atoms-in-molecules neural network potential (AIMNet2), which is applicable to species composed of

up to 14 chemical elements in both neutral and charged states, making it a valuable method for

modeling the majority of non-metallic compounds. Using an exhaustive dataset of 2 × 107 hybrid DFT

level of theory quantum chemical calculations, AIMNet2 combines ML-parameterized short-range and

physics-based long-range terms to attain generalizability that reaches from simple organics to diverse

molecules with “exotic” element-organic bonding. We show that AIMNet2 outperforms semi-empirical

GFN2-xTB and is on par with reference density functional theory for interaction energy contributions,

Received 19th December 2024 Accepted 21st April 2025

conformer search tasks, torsion rotation proﬁles, and molecular-to-macromolecular geometry optimization. Overall, the demonstrated chemical coverage and computational eﬃciency of AIMNet2 is

DOI: 10.1039/d4sc08572h

a signiﬁcant step toward providing access to MLIPs that avoid the crucial limitation of curating additional

quantum chemical data and retraining with each new application.

rsc.li/chemical-science

computing hardware. As a result, MLIPs exist as promising tools for addressing diverse challenges faced across the chemical sciences,7–9 especially if they are robust enough to be coupled with high-throughput experimentation, autonomous synthesis platforms, and robotic chemistry laboratories.10–13

Introduction

The accessibility of quantum mechanical (QM) calculations and the continuous improvement of data-driven techniques, such as machine learning, have unlocked chemistry research directions that would be otherwise too expensive or impractical to pursue.1–3 Machine learned interatomic potentials (MLIPs)4–6— which are models that aim to reproduce QM potential energy surfaces given suﬃcient training data—have a notable presence in this emerging style of chemical research. One of the main attractions of these models is that quantum chemical calcula- tion workloads that require hours or days can be approximated within seconds. Using MLIPs, it is now possible to examine large batches of molecular systems or materials consisting of >105 atoms with minimal sacrices compared to QM accuracy using relatively modest computational resources, if pretrained models are made available. Computational chemistry research has accelerated to a point where evaluating millions of systems is trending toward becoming a routine step in the design-of- experiments, albeit with access to the proper accelerated

Avoiding the cost of QM calculations is a primary MLIP benet; however, most reported models are either specic to one system or a small number of compounds. This slows the ability of MLIP-driven simulations to address chemical chal- lenges, particularly when QM data is not available and needs to be generated. The time required to curate a dataset, train an MLIP, and properly validate its chemical space coverage can signicantly oﬀset the low computational cost of applying the model. An alternative is to collect a large amount of training data with broad chemical space coverage and train a general MLIP, ideally with a workow that minimizes unnecessary QM calculations and maximizes the contribution each system has for rening a model.14–16

With this motivation, there is a need to develop MLIPs that are transferable to a wide range of compounds with diverse chemical compositions and charge spin states. The accurate neural network engine for molecular energies (ANI)17,18 family of MLIPs were some of the earliest models to achieve reliable predictions for millions of molecular systems composed of H, C, N, O, F, Cl, and S.19 The ANI MLIPs are eﬀective for cases where physical and chemical characteristics can reasonably be

Department of Chemistry, Mellon College of Science, Carnegie Mellon University, Pittsburgh, Pennsylvania 15213, USA. E-mail: olexandr@olexandrisayev.com

† Electronic supplementary information (ESI) available. See DOI:

https://doi.org/10.1039/d4sc08572h

‡ Equal contributions.

10228 | Chem. Sci., 2025, 16, 10228–10244 © 2025 The Author(s). Published by the Royal Society of Chemistry


![image_2](images/image_0002.jpeg)


## 第 3 页

Edge Article Chemical Science

and coworkers.29,30 All source code and pretrained models used in this work are provided in the open-source repository https:// github.com/isayevlab/aimnetcentral on GitHub. In AIMNet2, the AIM layer is a learned atomic representation that is determined using a message-passing architecture. First, the interatomic distances are expanded into a set of radial symmetry basis functions of the form:

approximated using only short-range truncated chemical envi- ronments; however, diﬀerent model architectures are required for systems with many elements, non-local behavior, open- shells, and charged species. Recent model developments have overcome the poor scaling with respect to the number of parametrized chemical elements, provided mechanisms to incorporate contributions from long-range interactions,20–23 and introduced methods for considering spin states.24–26 Herein, we report an advancement to the atom-in-molecules neural network potential model suite, AIMNet2, which expands our previous model to include 14 chemical elements and long-range electrostatic and dispersion interactions for compounds with varied charges and valency. In addition to making these pre- trained models available, we also provide access to the AIMNet2 architecture, allowing the computational chemistry community interested in developing MLIPs to train their own models and fully utilize the eﬃciency and scalability for targeted applications.

gijs ¼ e  hðrijrsÞ 2 fc  rij  (2)

where the local atomic environment of atom i is described as a collection of Gaussian functions with a set of center positions rs and widths h. The subscript dimension s denes the number of Gaussian functions composing the basis (16). The symmetry functions are damped with a cosine cutoﬀfunction (fc) that smoothly reduces these descriptors to 0 at the local distance cutoﬀof 5.0 Å. It should be noted that this cutoﬀis used only in evaluation of ULocal, while long-range interactions, such as UCoul and UDisp, are calculated for the entire system, or with a suitable cutoﬀ, e.g. 15 Å. The strategy of augmenting short-range inter- actions with long-range contributions is one of several approaches to overcome the nearsightedness of MLIPs, where methodological trade-oﬀs have recently been discussed in detail.23 Regardless, the atomic environment vectors are combined with atomic embeddings (eqn (3)–(5)) to provide a feature vector representation that is rich in chemical details.

Results and discussions

Model design

A schematic overview of the key components of the AIMNet2 architecture is shown in Fig. 1. AIMNet2 calculates the total energy of a chemical system according to

UTotal = ULocal + UDisp + UCoul (1)

ads(z) ˛ Rds (3)

visd ðr;aÞ ¼ X

j gijsajds (4)

where ULocal, UDisp, and UCoul refer to the local congurational interaction energy, explicit dispersion correction, and electro- statics between atom-centered partial point charges, respectively. Similar to the previous version of AIMNet,27 multi-task predic- tions can be constructed on-top of the learned representation, i.e., the so-called AIM vector, but we chose to omit them for clarity. However, this feature supports the exibility of AIMNet2 to be applied to diverse molecular and material systems because the functional form can be readily tailored to meet the demands of the modeling task by including additional output heads. We include explicit dispersion interactions using a PyTorch28

vihd ðv;aÞ ¼ k X

js gijs~uijajdswdshk (5)

Atomic embeddings (a) are dened using a 16 × 16-matrix (d,s) that initially depends on each atom's atomic number (z), where d is a hyperparameter controlling the embedding size. The design of this 2D-embedding was motivated by a desire to enhance AIMNet2's exibility by introducing a message-passing convolution that depends on which radials shells dominate the

implementation of the DFT-D3 correction model from Grimme

Fig. 1 Operations and unrolled message passing workﬂow of the AIMNet2 architecture. Atomic coordinates (R), atomic numbers (Z), and net charge of the system (Q) are model inputs. AIMNet2 uses a message passing approach, where atomic feature vectors (v(*)) are calculated via a convolution and concatenation of atomic and geometric descriptors. The local conﬁgurational energy is obtained using the atoms-in- molecule vector (AIM), which is summed with dispersion and electrostatic contributions in the calculation of the total energy.

© 2025 The Author(s). Published by the Royal Society of Chemistry Chem. Sci., 2025, 16, 10228–10244 | 10229


![image_3](images/image_0003.jpeg)


## 第 4 页

Chemical Science Edge Article

training can quickly grow to an impractical scale. As a result, it is necessary to carry out data curation and model training practices that limit dataset redundancy and maximize the value that each data point will contribute to rening the MLIP model. The overall aim is to achieve a manageable collection of infor- mative quantum chemical data that can be used to train an AIMNet2 model that displays similar accuracy to a model that is laboriously trained on the full set of labeled data. In this report, we compact our dataset by implementing a strategy that we refer to as data distillation. The process of data distillation involves sequentially growing a training set that is a subset of the master set of all the accu- mulated quantum chemical calculation results, i.e., ∼120 million samples (molecular systems) labeled with low-delity B97-3c32 DFT method. Specically, we began by randomly selecting 1 × 105 reference data and trained an initial AIMNet2 potential. Following training, we performed inference on the master set, with molecules sorted from smallest to largest, until we found an additional 1 × 105 reference data that are predicted above a threshold of 3× the current training error. Candidate structures from the master set were evaluated using both force and energy criteria, where samples falling above either error threshold, dened using the most recent training run, were selected. These structures are added to the training set, and training continues starting from the previous model weights. This process repeats until the nal AIMNet2 model can accu- rately describe the entire master set, which occurred for our pretrained AIMNet2 models when we reached ∼2 × 107 refer- ence data points. We then retrained the nal ensemble AIM- Net2 models (4 members) from scratch. An overview of the preparation and use of our pretrained AIMNet2 models is presented in Fig. 2. We used ChEMBL33 and PubChem34 as key sources of the molecular structures. We performed non-equilibrium conformational sampling with molecular dynamics and metadynamics using GFN2-xTB35 and torsional scans with preliminary models. Additional structures were added from ANI-2x18 and OrbNet36 datasets. Altogether, this formed the master set of ∼1.2 × 108 molecular conformers for data distillation. The entire pool of structures was initially labeled with computationally eﬃcient B97-3c32 calculations. Aer reducing the master dataset to ∼2 × 107 samples, all structures were computed with more expensive and accurate uB97M-D3/def2-TZVPP.37 All reference DFT data were used in training without any dispersion correction. In the nal models, 2-body DFT-D3 [https://doi.org/10.1002/jcc.21759] dispersion correction was added with damping function parameters for B97-3c and uB97M. respectively. Additional details and statis- tics regarding the dataset can be found in the Methods section and ESI.†

composition of gijs. With each message pass, the atomic embed- ding is updated to provide a rened description of the chemical environment of neighboring atoms, thus, obfuscating the need for multiple element-specic networks, which are required, for instance, in MLIP models such as ANI.17,18 This exibility provides the AIMNet2 architecture an ability to eﬃciently generalize to arbitrary number of chemical elements without species-specic networks. During the rst message passing iteration, the atomic feature vectors are constructed via a concatenation of so-called ‘scalar’ (visd (r,a)) and ‘vector’ (vihd (r,a)) embedding components, which collect information of the atomic environment using harmonics with angular momentum l = 0 and l = 1. The vihd (r,a)

calculation is similar to that of visd (r,a); however, a combination of the embedding features is carried out using linear transformation with the weight matrix, wdsh, before performing a vector-norm of the resultant matrix multiplication sum. A set of initial atom- centered partial point charges (q) are predicted during the rst message pass. In subsequent iterations, the input description of each atom is expanded to include charge components. Partial charges undergo a similar convolution to that described in eqn (4) and (5); however, ads is replaced with each atom's partial point charge. Thus, the atomic feature vectors aer the rst message pass are modied to be a concatenation of visd (r,a), vis (r,q), vihd (r,a), and vihd (r,q). It is worth highlighting that other models have been re- ported that include electronic structure information, e.g., partial charges, as a component in their input representation. As an example, one could use partial charges from charge equilibration procedures (QEq),31 as is done in the 4GNNP model of Ko et al.,21 which requires dening environment- dependent electronegativities and solving a system of linear equations either iteratively or through matrix inversion. In contrast, AIMNet2 infers partial charges from the feature vector representation and iteratively renes them as part of the message passing procedure. Every partial charge update is fol- lowed by an application of Neural Charge Equilibration (NQE), which is a methodology adapted from the work of Zubatyuk et al. for simulating open-shell or ionic species with AIMNet- NSE:25

!

Q  X N

qi ¼ ~qi þ fi P N

(6)

j¼1 ~qj

j¼1 fi

where ~q and q are partial atomic charges before and aer equilibration, f is a non-negative atomic weigh factor which is predicted alongside the partial charges, and Q is total molecular charge. This normalization procedure re-distributes any surplus or decit partial charge along the atoms of the molecule according to predicted weights. The nal message passing iteration yields the AIM repre- sentation, which serves as the input for a feed-forward neural network block that ultimately is used to infer ULocal.

Case study of uncommon bonding

In this section, we report two test cases using our pretrained AIMNet2 models to demonstrate transferability. In the rst case we consider the ability of the AIMNet2 models for reproducing experimentally observed geometries of molecules with unusual bonding. For the second test case, we assess performance in

Data distillation

A major challenge to training an MLIP that covers wide ranges of chemical space is that the reference dataset used during

10230 | Chem. Sci., 2025, 16, 10228–10244 © 2025 The Author(s). Published by the Royal Society of Chemistry


## 第 5 页

Edge Article Chemical Science

Fig. 2 Overview of AIMNet2 model development and application usage. Diverse sampling techniques were used to curate a dataset of 120 million chemical systems that were labeled with B97-3c DFT. Following data distillation, the remaining 20 million systems were labeled with uB97M-D3/def2-TZVPP and used to train the application ready AIMNet2 models.

For each structure, geometries were optimized with the pretrained AIMNet2 models in the gas phase and compared to a ground truth conformer extracted from experimentally resolved crystal structures. For these 113 selected molecules (see the ESI† for geometries and reference codes) our models displayed an average root-mean-squared deviation (RMSD) of 0.38 Å. Six examples from the 113 total cases evaluated are presented in Fig. 3. Considering some discrepancy is expected when comparing gas phase calculations and crystal structure geometries, the low RMSD value shows our model is robust even for fringe cases like a six-coordinated Cl ion or a selenium- doped boron cluster. In addition to assessing the AIMNet2 models trained on the results of uB97M-D3 calculations, we compared with GFN2-xTB and AIMNet2 trained to B97-3c reference data. Geometry optimization was carried out with reasonably tight convergence criteria (fmax < 5 × 10−3 eV Å−1)

conformer search tasks for species with an extended set of chemical elements with veried experimental crystal structures. The aim of the rst benchmark is to highlight that the potential energy surface learned by the pretrained models can be used to accurately identify molecular geometry minima for organic and element-organic structures, particularly those with diverse covalent bonding. To emphasize this robustness, we selected 113 molecular structures that have rare bonding patterns from a larger extracted set from the Cambridge Structural Database (CSD).38 For details on the criteria and procedure used to down select these structures from an initial set of ∼2.5 × 105 diverse compounds, see the Methods section and ESI Note 1.† While AIMNet2 models were trained on samples broadly containing the covalent bonding possible in our element set, these testing molecules show rare chemical bonding patterns and therefore are borderline and challenging cases for an atomistic potential.

Fig. 3 Alignment of molecular geometries optimized with AIMNet2 in the gas phase compared to conformers extracted from the experimental crystal structure. 2D molecular sketches are depicted along their corresponding 3D geometries. Experimental conformers are colored with the SMARTS color scheme, and AIMNet2 optimized structures are colored in light blue regardless of atom type.

© 2025 The Author(s). Published by the Royal Society of Chemistry Chem. Sci., 2025, 16, 10228–10244 | 10231


![image_4](images/image_0004.jpeg)


![image_5](images/image_0005.jpeg)


## 第 6 页

Chemical Science Edge Article

a chemically varied set of 676 molecules that have 10–40 non-H atoms and 1–3 rotatable bonds. From each molecule's SMILES representation, an initial pool of molecular structures was produced using torsion driving with OpenEye Omega's Dense conformer ensemble generator. On average, 86 distinct conformers were generated for each molecule. Aer optimizing all conformers within the ensemble, we selected only those within 6 kcal mol−1 from the lowest energy conformer, which is a typical energy cutoﬀused in a conformation search task. Then within the pool of low-energy conformers, we searched for the conformation that is the closest to the experimental structure and recorded its RMSD and relative energy within the ensemble. In Fig. 4, we compare the success rate in locating approxi- mate experimental geometries within the set of low-energy conformers in the optimized pool of structures for low-cost DFT, semi-empirical GFN2-xTB, and AIMNet2. We dene a broad metric of success using two criteria: (1) the number of structures that have a low (<0.5 Å) RMSD to the ground truth and (2) the lowest RMSD structure also displaying low-relatively energy (<2.0 kcal mol−1) in the optimized pool. In other words, these criteria (displayed as red boxes in Fig. 4) reect the like- lihood of nding a high-quality molecular geometry if one were to conduct conformer search without knowing the ground truth. It is worth acknowledging that the bounds of this success window are somewhat arbitrary, and they can be tailored for the application or molecule(s) of interest. To limit ambiguity in our denition of success, the distribution of closest matches for each method are provided along the external bounds of Fig. 4. The pretrained AIMNet2 models display the lowest average RMSD and most compact distribution for identifying the experimental geometry among the three methods. Interestingly, GFN2-xTB optimizations result in better, on average, energy predictions than AIMNet2; however, this should be balanced against the signicantly larger breadth of the distribution in the geometric comparison. In other words, many of these low energy predictions experience large geometric deviations that can hinder their practical use. Conformer search using DFT

starting from experimental geometry, which was followed by computing the RMSD of heavy atom positions between the experimental and optimized geometries (see ESI Table 2 and Fig. 1†). Both AIMNet2 models were observed to yield lower RMSDs (0.32 and 0.35 Å) compared to those from semi- empirical GFN2-xTB (0.37 A). We also examined the lengths of bonds containing non-hydrogen atoms and at least one species from our so-called “extended element” set (B, Si, P, As, Se, Br, I) to provide further insight into the ability of AIMNet2 to accu- rately describe diverse chemical geometries. The mean absolute deviation in these bond lengths from our 113 molecules is 2.4% and 2.1% for AIMNet2-B973c and AIMNet2-uB97M-D3, respec- tively, indicating that, despite their uncommon nature, AIM- Net2 captures extended element covalent bonding within an accuracy of a few picometers. It should be noted that two structures, [As3Br12]3−and [As3I12]3−(Refcodes VUFRIX and GEHVIY), decomposed into two fragments during optimization with GFN2-xTB, and the latter also with AIMNet2-uB97M-D3. These entries were excluded from the RMSD statistics. More- over, four structures failed to converge during the self- consistent charge procedure of GFN2-xTB. Regardless, these results show that AIMNet2 can reliably reproduce molecular geometries even in unusual, arguably exotic, bonding situations. In the second step of our benchmark study, we measured the performance of pretrained AIMNet2 models in a conforma- tional search task (see ESI Note 2†). We dene success in this task as the ability to identify conformers that agree with those resolved experimentally by starting from a consistent pool of structures that were generated from molecular graphs without bias toward the ground truths, i.e., the geometries extracted from the CSD. For an interatomic potential to be used in conformer search, it must describe interactions between parti- cles in near and oﬀ-equilibrium molecular geometries accu- rately, thus, success in this benchmark supports the broad chemical space coverage of AIMNet2. Beginning with the same subset of ∼2.5 × 105 extracted molecules, we selected

Fig. 4 Success rate (red squares) of matching experimental geometries in a conformer search task of extended element structures. Success can be judged by the criteria of being low-energy (<2.0 kcal mol−1) and having low root-mean-squared-deviation (RMSD < 0.5 Å). Each data point represents the single closest match to the experimental structure extracted from CSD for each of the 676 targets. A consistent set of structures is evaluated for (a) AIMNet2, (b) B97-3c, and (c) GFN2-xTB.

10232 | Chem. Sci., 2025, 16, 10228–10244 © 2025 The Author(s). Published by the Royal Society of Chemistry


![image_6](images/image_0006.jpeg)


## 第 7 页

Edge Article Chemical Science

aggregated scores known as WTMAD1 or WTMAD2. These scores are derived by weighing the mean absolute deviation of the calculated results against the reference values. The distinction between WTMAD1 and WTMAD2 lies in the relative weighting assigned to the diﬀerent subsets within GMTKN55. Consistent with the OrbNet Denali report46 and to enable a fair comparison between models with varying coverage of elements, charge and spin states, we calculated WTMAD scores over the GMTKN55 subsets that are supported for each model and set the weight to 0 for the mean absolute deviation (MAD) for unsupported subsets. Fig. 5a lists WTMAD2 scores of AIM- Net2 models trained to two DFT references B97-3c and uB97M- D3/def2-TZVPP levels. Both models achieve substantial accuracy improvements compared to low-cost semi-empirical GFN2-xTB and are approximately equal to the proprietary OrbNet Denali model. The only subset of the GMTKN55 dataset where the accuracy of AIMNet2 models does not outperform GFN2-xTB is for intermolecular interactions, which provides motivation to pursue additional detailed assessment for various types of noncovalent interactions to better understand the performance of AIMNet2. We further investigated the intermolecular inter- action performance using NCI Atlas, where noncovalent inter- actions are partitioned into diﬀerent types in a dened chemical space. For this benchmark, the AIMNet2 models signicantly outperform for the subsets of ionic hydrogen bonds (IHB100×10) and sigma–hole interactions (SH250×10), whereas GFN2-xTB displays higher accuracy for the subset dispersion-bound molecular complexes (D442×10) by ∼0.3 kcal mol−1. These results are well aligned with the inter- molecular interaction ndings for GMTKN-55, whose subset consists of many dispersion bound systems such as p-stacked and nonpolar complexes. The overall performance of AIMNet2 is, on average, 1–2 kcal mol−1 RMSE for the various subsets of NCI Atlas (See Fig. 5b), which demonstrates notable accuracy improvements for electrostatics and directional intermolecular bonding. This is nearly twice as large as the typical errors re- ported for DFT methods; however, it represents a 25–50% improvement in accuracy for ionic hydrogen bonds and sigma– hole interactions over GFN2-xTB. It is important to place the prediction accuracy of interaction energies in the context of separation distance. In Fig. 5c and d, it is shown that the aggregate RMSE metrics are mainly dominated by diﬀerences occurring at separations less than the equilibrium or reference spacing, depending on the subset. The most signicant diﬀer- ence is found for short-range sigma–hole interactions, which we regard as challenging physicochemical behavior to accurately predict for an atom-centered point charge model, especially one relying on local environment descriptors. A similar plot for GFN2-xTB accuracy as a function of distance is provided in Fig. S5.† The same trends observed for our pretrained AIMNet2 models are displayed, albeit with GFN2-xTB producing signi- cantly larger errors for most distances and subsets. It is worth commenting on the robustness of the pretrained AIMNet2 model errors with respect to predicting interaction energies of systems with varied total molecular charge (see ESI Fig. 4†). By comparing diﬀerent subsets of our training data,

(B97-3c) optimizations can be regarded as a reliable, albeit more computationally demanding, measure of the typical success rate for this benchmark. Since performing optimization with the hybrid DFT method is computationally demanding, the DFT results are reported using B97-3c32 which serves as a reasonable reference point. Overall, this method32 identies conformer geometries that are close to experimentally observed structures in 83% of the cases (see ESI†). It should be noted that this reects not only the accuracy of the method but also the quality of conformational ensembles produced by OpenEye Omega, which is out of scope of our benchmark. The small percentage of geometries that are outside the RMSD window should not necessarily be labeled as a failure of the DFT or AIMNet2 potential energy surface representations, but instead they reect a population of higher deviation minima. Considering both energy and geometry criteria, B97-3c conformer search was found to achieve success in 75% of the 676 cases (see Fig. 4b). The success rate for neutral molecules is observed to be ∼15% higher compared to charged ones. GFN-FF39 (see ESI†) and GFN2-xTB methods displayed noticeably lower success rates, especially for conformer geometry (see ESI Table 3†), with values of 42.1% and 45.2%, respectively. In contrast, AIMNet2 models trained on uB97M DFT data achieved a 77% success rate and is within 2% of direct B97-3c calculations for both criteria.

General interaction energy benchmarks

To evaluate the performance of AIMNet2, we examined two of the most extensive and chemically diverse validation data sets avail- able for discerning accuracy in quantum chemical calculations, namely GMTKN55 (ref. 40) (General Main-group Thermochem- istry, Kinetics, and Noncovalent interactions) and NCI Atlas (Non- Covalent Interactions Atlas).41–44 Both benchmarks are designed for targeted assement of the accuracy of electronic structure calculation methods for describing various chemical behavior. The GMTKN55 (ref. 40) validation set of Goerigk, Grimme, and co-workers is divided into 55 sub-datasets, where each focuses on specic phenomena underpinning molecular properties. In particular, there are seven datasets that address reaction barrier heights, 18 datasets dedicated to basis properties and smaller molecular systems—where nine of these primarily investigate noncovalent intramolecular interactions, 12 datasets consist of diverse intermolecular interactions, and the remaining nine are concentrated on reaction energies and isomerization energies for larger systems. The NCI Atlas is a curated collection of interaction energies and dissociation curves for complexes where intermo- lecular interactions are dominated by contributions such as London dispersion, sigma–hole interactions, and hydrogen bonding in charged and neutral molecules (including extended species: B, S, Se, P, halogens). Compared to earlier datasets like S66,45 the NCI Atlas datasets are larger, more accurate, and they also oﬀer additional advantages such as a systematic construc- tion, increased diversity of the model systems, and high-quality molecular geometries, to name a few.44

Typically, when evaluating the performance of QM methods using the GMTKN55 benchmark, results are reported using

© 2025 The Author(s). Published by the Royal Society of Chemistry Chem. Sci., 2025, 16, 10228–10244 | 10233


## 第 8 页

Chemical Science Edge Article

Fig. 5 Performance of AIMNet2 models, GFN2-xTB and DFT methods on the (a) GMNTK55 benchmark and (b) the Non-Covalent Interaction (NCI) Atlas benchmark. Performance as a function of separation distance is reported for AIMNet2 models trained to uB97M-D3 (c) and B97-3c (d) for the NCI Atlas benchmark. HB300SPX×10 – hydrogen bonding extended to S, P and halogens; HB375×10 – hydrogen bonding in organic molecules; IHB100×10 – ionic hydrogen bonds in organic molecules; R739×5 – repulsive contacts in an extended chemical space; SH250×10 – sigma–hole interactions; D442×10 – London dispersion in an extended chemical space.

ANI-2x model, resulting in 3-5x error reduction and improve- ment in coverage while maintaining eﬀectively the same computational performance. Torsion proles calculated using OrbNet Denali and B97-3c are also considered, where the AIMNet2 model displays performance that is consistent with B97-3c and ∼0.25 kcal mol−1 less accurate than OrbNet Denali.

including neutral (Q = 0), charged (jQj # 2), and strongly charged (jQj from 3 to 9), we observe a consistently low ∼1.5 kcal mol−1 RMSE. In other words, there is not a clear discernible bias of the model error as a function of the total molecular charge. To enable a comparison with models trained to a common set of chemical elements (CHNOSFCl) we also benchmarked the AIMNet2 model on the TorsionNet500 (ref. 47) dataset of torsion energy proles for typical drug-like fragments. Following the outline of the original TorsionNet500 report, we compared several diﬀerent metrics of accuracy (See Table 1). The AIMNet2 model shows a substantial improvement from the

Eﬃcient optimization of molecules to macrostructures

An attractive feature of broadly transferable MLIPs is their ability to enable fast and accurate optimization of an enormous number of molecular and material structures. To highlight this performance for the AIMNet2 architecture, we conducted

Table 1 Performance comparison on the TorsionNet500 benchmark set. The reference energies are recalculated at their corresponding levels of theory. Metrics evaluated include the percentage of the torsion proﬁles for which the Pearson correlation coeﬃcient (R) is greater than 0.9, the average Pearson R over the torsion proﬁles, the MAE and RMSE of the relative energies of the torsion proﬁles, and minima accuracy, which is deﬁned as the percentage of torsion proﬁles where the global minimum of the proﬁle is correct to within 20° and 1 kcal mol−1

Method Pearson R > 0.9 (% proles) Average prole Pearson R MAE (kcal mol−1) RMSE (kcal mol−1) Minima accuracy (%)

AIMNet2 96.6 0.99 0.32 0.47 98.2 OrbNet denali 99.4 0.99 0.12 0.18 100.0 GFN2-xTB 76.4 0.88 0.73 1.00 94.0 B97-3c 97.4 0.99 0.29 0.43 100.0 ANI-2x 73.2 0.90 1.30 1.90 91.8

10234 | Chem. Sci., 2025, 16, 10228–10244 © 2025 The Author(s). Published by the Royal Society of Chemistry


![image_7](images/image_0007.png)


## 第 9 页

Edge Article Chemical Science

Fig. 6 Benchmarking molecular and macrostructure optimization performance of the AIMNet2 architecture. (a) Small molecule optimization performance, deﬁned as the total average time to reach convergence, comparison for GFN2-xTB (red), GFN-FF (green), AIMNet2 using CPU (orange) and GPU (blue) resources. CPU optimizations were performed on a single core of an i7-9700K system, and GPU optimizations on an NVIDIA L40S. (b) Macrostructure time (b) and peak memory (c) for force evaluations. Model systems are random polymer coils (red) and condensed phase methane (blue), where light colors (dashed lines) are for short-range models, dark colors (solid lines) are for models with long- range Coulomb + D3 dispersion, and standard colors (dotted) are for models with long-range Coulomb.

emphasize that these large systems are selected as model cases to demonstrate the scalability of optimization eﬃciency aﬀor- ded by the AIMNet2 architecture, and validating our pretrained models' ability to simulate polymer systems or condensed phase methane is outside the scope of this report. Eﬃciency is presented in terms of time per force evaluation to remove ambiguity that may arise from arbitrary diﬀerences between the initial geometry and converged structures. Moreover, only the performance of AIMNet2 is reported due to the computational limitations of performing semi-empirical optimization for systems of these sizes. O(N) scaling per optimization step is observed for both computational time and required memory for polymer systems for systems up to 105 atoms. A single optimi- zation step requires no more than three quarters of a second on a modern GPU, which is largely enabled by memory and thread eﬃcient operations used in constructing the AIMNet2 archi- tecture. For the periodic methane models, the time required for force evaluations scale quadratically with the systems size, which is a consequence of the neighbor list construction as opposed to the AIMNet2 inference (scales linearly). As much as 65% of the inference time is spent on neighbor list operations. For example, carrying out a force evaluation on 9 × 104 atoms methane simulation cell with a model using both short range (5 Å) and long-range (15 Å) components, requires 2.16 s to build the neighbor list but only 0.75 s for AIMNet2 evaluation. To reduce this disparity, high-performing GPU kernels for eﬃcient construction of AIMNet2 neighbor lists is an ongoing research eﬀort. In Fig. 6b and c optimization performance is also re- ported as a function of long-range interaction types. While the inclusion of Coulomb interactions requires little additional computational eﬀort (both scaling and memory), our pytorch D3 dispersion model is found to produce a signicant memory footprint. This presents yet another opportunity for optimized kernel development, which conceivably benets any MLIP developer seeking to include post hoc D3 corrections. It is worth noting that we used a limited memory Broyden–Fletcher– Goldfarb–Shanno (LBFGS) optimizer to measure

geometry optimization of varying system sizes, measured computational eﬃciency and scalability metrics, and compared them with regularly used low-cost methods: GFN-FF and the semi-empirical GFN2-xTB. The eﬃciency of the AIMNet2 architecture for optimizing small molecule conformer ensem- bles, i.e., batches of same sized molecules with diﬀerent initial geometries, is shown in Fig. 6a. GFN-FF, GFN2-xTB, and AIM- Net2 (CPU and GPU implementations) exhibit optimization eﬃciency, dened as the total time to reach convergence, that scales as O(N2), where N is the number of total atoms in the conformer structures. The performance of our GPU PyTorch implementation is particularly notable, where the AIMNet2 architecture yields ∼5× faster optimization in comparison to GFN-FF for systems consisting of up to 80 atoms. This supports an ability to drastically accelerate high-throughput optimiza- tion tasks and opens avenues to readily scale to millions of structures with modest resources. Carrying out AIMNet2 geometry optimization on a CPU results in a slower time-to- converge by approximately 2 orders of magnitude, being slightly faster than GFN2-xTB. It is worth commenting that direct benchmarking between the semi-empirical methods and AIMNet2 is challenging due to the underlying details of the optimizer implementations. Our AIMNet2 small molecule conformer ensemble benchmark uses an in-house batched PyTorch implementation of the FIRE optimizer, which we found to require ∼1.5–2.0× more steps to converge than the approximate normal coordinate rational function optimizer (ANCopt) implemented within the xTB soware suite. Despite requiring more gradient calls, we still observe improved performance for AIMNet on both CPU and GPU. Thus, the 5× speed-up can be viewed as a solower bound, and renement of the optimization strategy can lead to even better performance. For large structure optimization, we examine two classes of systems in diﬀerent density regimes consisting of up to 105

atoms: polymer random coils of polyethylene oxide (PEO) and condensed phase methane (0.425 g cm−3), see Fig. 6b and c. We

© 2025 The Author(s). Published by the Royal Society of Chemistry Chem. Sci., 2025, 16, 10228–10244 | 10235


![image_8](images/image_0008.jpeg)


## 第 10 页

Chemical Science Edge Article

displacement (MSD) over the simulation trajectory and applying the Einstein approach.51

macrostructure optimization performance using a custom AIMNet2 calculator plugin to the Atomic Simulation Environ- ment (ASE) soware, which imposes a small 5% overhead on top of the MLIP energy and force inference. Regardless, the overall eﬃciency aﬀorded by the AIMNet2 architecture combined with the robust accuracy of our provided pretrained models can be leveraged for high-throughput, chemically diverse, scalable geometry optimization.

In Fig. 7b and c, the potential and kinetic energy throughout the 2.5 ns simulation with data collected every 10 fs are shown. The traces of these energy functions are absent of any aberra- tions and display uctuations with magnitudes typical of molecular dynamics simulations performed with classical empirical potentials, indicting no signs of instability. Moreover, we applied molecular geometry-based postprocessing criteria to conrm that all CO2 molecules stayed intact and maintain approximately linear geometry, i.e., we did not nd any so-called “exploding molecules” that are typical of unstable simulations. In Fig. 7d, we report the calculated MSD, averaging over all 1000 CO2 molecules, which exhibits the expected linear relationship in the long-time scale. This results in a self-diﬀusion coeﬃcient of 2.82 × 10−9 m2 s−1 where the approximate experimental value, interpolated from the work of Groß et al., is 7.09 × 10−9

Molecular dynamics

While the pretrained models provide widespread chemical space coverage, eﬃcient inference, and accurate explicit treat- ment of nonbonded interactions, it is worthwhile to examine the AIMNet2 architecture's capability for performing molecular dynamics simulations. A recent report by Fu et al.48 remarked that standard energy and force error metrics used by MLIP model builders are not necessarily reective of an ability to perform stable molecular dynamics simulations. Explicitly demonstrating such a capability, particularly without equivar- iant message passing, provides important validation for potential use cases of the AIMNet2 architecture. With this motivation, we assessed the behavior of condensed phase carbon dioxide at 298 K with molecular dynamics simulations, see Fig. 7a. Our decision to examine this model system is twofold: (1) simulating CO2 in a dense uid state with periodic boundary conditions is a clear extrapolatory task as AIMNet2 was trained on small-to-moderately sized gas phase systems and (2) the work of Mathur et al.49 provides precedent for the ex- pected level of accuracy that CO2-specic MLIPs (in their case Deep Potential models50) can obtain. It should be noted that the AIMNet2 training dataset does not contain exhaustive sampling of CO2 molecule clusters. Therefore, performing stable and reasonably accurate molecular dynamics simulation of the CO2 model system serves as an additional measure of the AIMNet2 architecture's generalizability. A complete description of simu- lation specic details is provided in the Methods section. In addition to demonstrating stability, we calculated the average self-diﬀusion coeﬃcient by tracking the mean-squared

m2 s−1.52 Depending on the DFT functional used for generating reference data and the temperature evaluated, the DeePMD models of Mathur et al.49 displayed similar disagreement factors of up to 2.5× (also as underpredictions) with respect to the experimental measurements. The error in the AIMNet2 derived self-diﬀusion coeﬃcient originates from the underlying DFT functional, the model architecture, and the chemical informa- tion available in the training dataset. A signicant DFT func- tional dependence for CO2 uid properties has been previously discussed by Goel et al.,53 which is also observed by Mathur et al.49 Deconvoluting the degree to which each of these factors contributes to the prediction accuracy is a topic for future study. Regardless, our observations that our MLIP architecture can achieve relatively long timescales (for MLIPs) without notice- able aberrations and display accuracy comparable to previous work, despite any system-specic training, suggesting that AIMNet2 can eﬀectively drive stable molecular dynamics simulations. It is worth commenting that the development of ML potentials to accurately capture a wide range of non-local intermolecular interactions and related properties in a condensed phase system is a non-trivial task,23 and the

Fig. 7 Demonstration of stable molecular dynamics simulations performed with AIMNet2. (a) molecular dynamics snapshot of condensed phase CO2 at 298 K. (b) and (c) traces of the AIMNet2 calculated potential energy and the systems kinetic energy over the molecular dynamics simulation, respectively. The potential energy is shifted by the mean values calculated over the last half of the production run to allow for the magnitude of ﬂuctuations to be easily observed. (d) Average mean squared displacement (MSD) of the 1000 CO2 over time used to calculate the self-diﬀusion coeﬃcient.

10236 | Chem. Sci., 2025, 16, 10228–10244 © 2025 The Author(s). Published by the Royal Society of Chemistry


![image_9](images/image_0009.jpeg)


## 第 11 页

Edge Article Chemical Science

that are akin to the performance trade-oﬀs found in traditional molecular simulations, albeit on a diﬀerent scale. We refer to model objective as the models intended use, which is crucial to interpret in the context of the trade-oﬀs described by model balance. By our assessment, many modern MLIP models tend to favor improvements in accuracy over computational eﬃciency, e.g., NEQUIP,55 Allegro,56 TensorNet,57 or MACE.58 That is not to say eﬃciency is not a focus of these models. For example, Allegro is a creative solution to oﬀer better computational eﬃciency than NEQUIP with only modest diﬀerences in accuracy. Instead, we emphasize that these architectures have an overall greater computational expense. A recent demonstration from Gao et al.59 emphasizes this point, where DP-MP models, a message passing variant of the Deep Potential architecture, show ∼2 orders of magnitude faster inference than those equivariant models listed above at the cost of ∼10 meV Å−1 force accuracy. AIMNet2 achieves similar computational performance, depending on the use of sparse or dense operations and neighbor list construction, while being slightly less accurate than MACE or NEQUIP when more computationally demanding yet informative higher body-order terms are included. The optimization of the SNAP potential by Wood and Thompson is another example.60 Although this was reported prior to the models mentioned above, their thorough discussion about the performance of MLIPs for pragmatic molecular simulations maintains its relevance. The objective of the pretrained AIMNet2 models is to provide reliable accuracy for general molecular modeling at an aﬀord- able computational cost, ultimately meeting the varied needs of high-throughput computational chemistry. Other MLIP models have prioritized stable and/or scalable molecular simulations as a main objective, for instance, sGDML,61 SNAP,62 or DP.63

robustness of pretrained AIMNet2 models trained on gas phase calculations translating to condensed phase simulations is under ongoing investigation. For example, the GEMS model of Unke et al.,54 which uses a divide-and-conquer strategy of training on DFT calculations of molecular fragments, supports the viability of gas phase-to-larger scale MLIP-driven simula- tions. They describe the necessity to include sizeable molecular systems to accurately learn long-range interaction behavior in heterogenous systems, which is particularly relevant to large- scale molecular simulations such as those aimed at studying protein dynamics. Examples of large noncovalent complexes compose only a small fraction of the AIMNet2 training set in the interest of training eﬃciency. Consequently, we have demon- strated molecular simulations for homogenous condensed phase CO2, but such performance is unlikely to extend to bio- macromolecules for example. We emphasize this is a deciency that is inherited from the aim of the training set, and the AIMNet2 architecture can drive such heterogenous simulations given a suﬃcient set of targeted training data. In general, the AIMNet2 architecture provides a reliable and eﬃcient method for training models capable of dense periodic boundary simu- lations; however, we stress that users of our pretrained models should not expect that the molecular and intermolecular complex training set used in this work will yield accuracy in condensed phases. The complete set of scripts needed to train AIMNet2 models can be found in the Code availability section.

AIMNet2 in the landscape of MLIPs

Reective of the evolving molecular modeling capabilities enabled by MLIPs, the introduction of new models with diverse use cases has grown in recent years. From a high-level perspective, these interatomic potentials can be classied according to model balance and model objective, which are the main inuencers dictating algorithmic design and training dataset construction. In this section, we aim to formally state the balance and objective targets of our pretrained models and provide an overview of the AIMNet2 architecture's capabilities in comparison to other modern MLIPs. Model balance can be regarded as management of MLIP accuracy, eﬃciency, and transferability, which are dened by intertwined relationships

sGDML is particularly interesting for performing molecular simulations because of its scalability and inherent smoothness. However, kernel methods typically suﬀer from poor trans- ferability, and, as a result, it remains unclear if the sGDML approach can be used for general chemistry without system- specic or domain-specic retraining, which is a key benet of AIMNet2. It is worth reiterating that the comparisons pre- sented in this section can only be stated for neutral systems,

Fig. 8 Performance of pretrained AIMNet2 models for dipole inference. (a) QM7b couple-cluster (CCSD) benchmark for dipole norm (blue) and dipole components (orange). (b) Parity between the AIMNet2 model trained to uB97M data and the same level of reference DFT on QM7b structures.

© 2025 The Author(s). Published by the Royal Society of Chemistry Chem. Sci., 2025, 16, 10228–10244 | 10237


![image_10](images/image_0010.jpeg)


## 第 12 页

Chemical Science Edge Article

contributions to the performance of AIMNet2 are the imposi- tion of net charge, an ML-assisted charge redistribution scheme (Neural Charge Equilibration or NQE25), and convolutions for partial charge updating, all of which incorporate rich electronic structure information to enhance the learning process. It is worth commenting that work by Ko et al.21 also experienced signicant gains in performance by including electronic struc- ture information, albeit using a diﬀerent strategy of predicting partial charges with an ML-parameterized charge equilibration technique that served as inputs alongside Behler–Parinello symmetry functions. In contrast to QEq, the NQE scheme scales linearly and introduces negligible computational overhead. In this work, we report an improved atoms-in-molecules neural network potential, AIMNet2, which yielded a set of pre- trained models for diverse organic and elemental-organic compounds. The AIMNet2 architecture overcomes many of the limitations intrinsic to the original model. In particular, AIMNet2 explicitly includes long-range interactions so that it is not bound by the locality of message passing, it is applicable to neutral and charged states, and covers compounds composed of twice as many (14) diﬀerent chemical elements. Although it was not highlighted in this report, the multi-task predictions of the 1st AIMNet model can easily be incorporated into AIMNet2 by, for example, including additional predictive neural networks that operate on the learned AIM representation. The result is a exible MLIP model that can be readily tailored to predict additional chemical properties without having to retrain the entire model for each task. As a nal note, it is worth commenting on the challenge of achieving full chemical space coverage. Setting aside issues with the transferability of the underlying reference data, it remains uncertain what is required, or if it is even possible or necessary, to train a single universal neural network potential with suﬃ- cient accuracy and eﬃciency for any task. Considering the surprising, at least in our opinion, generalizability of AIMNet2, it is clear that including information derived from electronic structure and interfacing with known physics-based functional forms are crucial steps in the right direction. While there are some physical phenomena that still need to be addressed, e.g., reactions or open-shelled species, our validation checks, benchmarking, and eﬃciency tests support the idea that AIM- Net2 is a suitable drop-in replacement for DFT in many computational chemistry practices without needing to be retrained.

while AIMNet2 takes a step further and includes explicit treat- ment of molecular charge. Conceivably, the 4GNNP architecture of Ko et al.21 could be used to train a comparable general MLIP model; however, to achieve this for 14 elements would be a demanding task considering the poor scaling of Behler–Par- inello symmetry functions and charge equilibration (QEq) scheme. An extension of DP models capable of predicting Wannier centroid positions for charged compounds is also possible;22 however, the algorithmic imposition of net charge would need to be developed and a dataset rivaling AIMNet2 is not available. AIMNet2 occupies a unique space in the MLIP landscape, being broadly applicable across compounds con- taining common non-metals/halogens, regardless of charge state, while maintaining a high-level of computational eﬃ- ciency, scalability, and practical accuracy. As an example, the dissociation of charged complexes is one limiting case. This is a consequence of charge redistribution via NQE occurring as a function of learned short-range descriptors. As non-neutral species move beyond the message passing cutoﬀ, without intermediary molecules, the lack of communication between system components can yield systematic misprediction. This is an inherent limitation of any MLIP potential that relies on short-range learned descriptors, such as those used in message passing. Regardless, for molecules and molecular complexes, the pretrained AIMNet2 models are observed to produce distributions of atom-centered point charges with accuracy near that of DFT. In Fig. 8a, a comparison of predicted dipoles with respect to coupled cluster calculations for AIMNet2 (calculated from the distribution of point charges) and reference DFT (using the electron density) is presented for the QM7b dataset.64

AIMNet2 models trained to uB97M-D3 data are found to be ∼0.04 D less accurate than the same underlying DFT and provide a similar quality of predictions as B97-3c. A direct comparison between the AIMNet2 and uB97M dipole compo- nents is provided In Fig. 8b, which shows strong correlation, R2

= 0.99, and modest RMSE, 0.09 D. Similar results are found for the dipoles AlphaML dataset,64 see the parity plot in Fig. S6,† which contains slightly larger organic molecules than QM7b.

Conclusion

Simulation methods and molecular modeling tasks using MLIPs are becoming increasingly mature and will, likely, continue their growth as emergent core components in computational chemistry research. By our assessment, the eld of MLIP development is beginning to split into several distinct focus areas, such as being exceptionally accurate for specic systems or being eﬃcient and broadly generalizable with prac- tical accuracy for many applications. Regarding the rst area, advances are mainly being achieved by the development of increasingly complex and/or expressive model architectures, for example, the recent embrace of equivariant models.55,65,66 For the second area, which is the primary focus of our pretrained AIMNet2 models, we show that systematically curating an expansive dataset, allowing our model to learn its own exible representations, and including physics-based functional forms into the MLIP architecture yields signicant progress. Notable

Methods

Dataset preparation

To create the overall pool of training data we selected neutral and charged molecules under 20 heavy atoms from PubChem34

and ChEMBL33 databases that contained species in our dened set of elements {H, B, C, N, O, F, Si, P, S, Cl, As, Se, Br, I}. All realistic tautomeric forms and protonation states across the pH range (1–14) were generated with Chemaxon JChem soware.67

We utilized geometry optimization, torsional prole scans, and molecular dynamics (MD) as primary methods to explore molecular PESs around their minima. Thermal uctuations of

10238 | Chem. Sci., 2025, 16, 10228–10244 © 2025 The Author(s). Published by the Royal Society of Chemistry


## 第 13 页

Edge Article Chemical Science

atoms in MD simulations allow for the near-equilibrium sampling of molecular conformational space. MD simulations of small molecular clusters were used for expanded sampling of noncovalent interactions. The set of structures was supple- mented with systems from ANI-1x,17 ANI-2x18 and OrbNet36

The loss functions include the weighted contributions from total energy prediction error L E (scaled by the square root of number of atoms within molecule), partial charges prediction error L Q, and errors of prediction of the components of atomic forces L F, total dipole L D and total quadrupole L Q. The sum of the weights was normalized to unity, where values of w were selected via an empirically guided hyperparameter search. The nal AIMNet2 loss contribution weights were 1.0, 0.2, 0.05, and 0.02 for wE, wF, wD, and wQ, respectively using units based on eV, Å, and electron charge. The partial charges inferred by AIMNet2 are learned such that they reproduce the molecular dipole and quadrupoles extracted from the DFT reference calculations.

datasets to provide broader chemical space coverage in the AIMNet2 training set. Additional details, such as dataset statistics, are provided in the SI. 3Similar to our previous work,25

we used quantum mechanically derived force eld (QMDFF)68 as an eﬃcient method to construct system-specic and charge- specic potential for a molecule. We also applied the GFN2- xTB35 tight-binding model to obtain relaxed conformations, force constants, charges, and bond orders that are needed for the QMDFF model. Molecular clusters were created by constructing a rectangular periodic cell within the range of 20 to 30 Å. N = 2–5 molecules from dataset are then selected randomly, with a probability that is skewed toward choosing molecules with less non-hydrogen atoms. The selected molecules are then embedded within the periodic cell with random positions and orientations under the condition that no two atoms in diﬀerent molecules are within 1.5 Å. The atom density of the box is also randomly determined within reasonable bounds. Preliminary AIMNet2 models are used to run an MD simulation on the constructed box of molecules. MD is carried out at a random temperature between 50 K and 600 K using the Langevin thermostat. Aer 100 timesteps, the box is decomposed into a complete set of N-mer structures {xi}, where i indexes the molecules. Only N-mer structures with at least two atoms, one from each monomer, within a distance cutoﬀof 6.0 Å are selected. For torsion sampling component of the AIMNet2 dataset construction, SMILES strings are selected from a subset of molecules with rotatable dihedrals. Consistent with the diver- sity selection algorithm (see below), we selected all possible conformers with unique torsion angles. RDKit is used to embed the molecules in 3D space and select rotatable dihedrals.69 The preliminary AIMNet2 models are used to optimize the starting geometry, and carry out a relaxed scan, incremented by 10° over the entire torsion prole. All DFT calculations were performed with the ORCA 5 (ref. 70) package using B97-3c32 and uB97M- D3/def2-TZVPP37 levels of theory.

Data distillation

The main purpose of the AIMNet2 model is to predict the energy, atomic forces, and charge distribution of organic and element-organic molecules in equilibrium and non-equilibrium congurations. The amount of required data could be drasti- cally reduced with active learning techniques, such as the selection of the most important samples (molecular congura- tions) to label (compute reference DFT properties) and include in the training dataset. For example, the original 2.0 × 107 ANI- 1 dataset for neutral CHNO organic molecules was reduced to 4.5 × 106 active learning. Extension to just three extra chemical elements S, F and Cl required additional 4 × 106 samples. Therefore, a comparable extension of that dataset to 7 extra elements (B, Si, P, Br, As, Se, I), and charged molecules could be expected to require an order of ∼108 new DFT data points, which is approaching practical limits. Therefore, to reduce the dataset even further, we combined our standard active learning query-by-committee approach14,15,72 with data distillation.73,74

The process of data distillation involves two main compo- nents: a teacher (T) dataset and student (S) training. The teacher dataset is composed of all available labeled data. One could train an MLIP to the full teacher set to achieve a potential that captures the underlying physical and chemical relationships dened in the data. However, labeling the full teacher dataset with higher level of theory DFT calculations is impractical, even with supercomputing resources, and therefore, data distillation can be applied to limit redundant chemical information such that a tractably sized training set can be obtained. If D repre- sents a general dataset, fq represents an MLIP model with parameters q, and fq(x) is the model's prediction for data point x, then the expected loss for dataset D in relation to q is

Model training

AIMNet2 models were trained using minibatch gradient descent with the AdamW71 optimizer. To improve training performance, all minibatches were composed of molecules with the same number of atoms to avoid padding operations. Proper data feed shuﬄing was achieved within the multi-GPU distrib- uted data-parallel (DDP) approach: gradients on model weights were averaged aer 8 random batches were evaluated in parallel, thus the eﬀective combined batch size was 2048. Training was performed on 8 Nvidia V100 GPUs. We employ a reduce-on-plateau learning rate schedule, which leads to training convergence within 400–500 epochs. The training objective was minimization of weighted multi-target mean squared error (MSE) loss function:

LDðqÞ ¼ Eðx; yÞPD½lðfqðxÞ; yÞ

where x and y are the input data and label pair from D, lðfqðxÞ; yÞ is the given loss value between the prediction and ground truth. Dataset distillation aims to reduce the size of large-scale training input and label pairs T = {(xi, yi)} by creating smaller student pairs S = {(xi, yi)}, so that models trained on both T and S can achieve similar performance, which can be formulated as:

L  qT  L  qS ;

where qT and qS are the parameters of the models trained on S and T respectively. In our case, we focus on so-called distilling

L ¼ wEL E þ wFL F þ wDL D þ wQL Q

© 2025 The Author(s). Published by the Royal Society of Chemistry Chem. Sci., 2025, 16, 10228–10244 | 10239


## 第 14 页

Chemical Science Edge Article

molecular dynamics, an LBFGS minimization for 103 steps and a max displacement of 0.02 Å per step was performed using the AIMNet2 pretrained model to limit any unfavorable initial geometries that may result from diﬀerences between the empirical potential and our MLIP. To compare diﬀusion coef- cients, the external pressure was calculated using the equa- tions described by Thompson, Plimpton, and Mattson,80 which was then matched to the corresponding state point (∼135 MPa and 298 K) through simple interpolation of the experimental results.

in instead of distilling out. In the distilling process, the student dataset is built up iteratively as a subset of the teacher (master) dataset.

Diversity selection

Molecular species used in our benchmark Section were collected via diversity selection using the local environment of each non-hydrogen atom composing the CSD-extracted mole- cules. Specically, for each atom, we utilized a hashing function operating on atomic number, number of connected hydrogen atoms, the total number of neighbors, and the same set of properties for all neighboring atoms. This hash uniquely encodes the local environment for each atom in a molecule, and comparing hash values was our strategy for discerning mole- cules with diverse chemical structures. For each of the 14 atomic species types covered by the pretrained AIMNet2 models, we selected 10 molecules that contain the least frequent atomic hashes. Some of these top-10 molecules were duplicated. As a result, the nal number of benchmark struc- tures was reduced to 113 molecules instead of 140 aer enforcing uniqueness. These 113 molecules exemplify a selec- tion of the most unusual chemical bonding present in CSD, and thus serve as challenging test cases for demonstrating MLIP applicability. The full list of molecules and reference codes are supplied in the ESI.†

Code availability

The trained AIMNet2 models, training scripts, and the code to reproduce this study is available in GitHub at https:// github.com/isayevlab/aimnetcentral.

Data availability

The molecular structures in the training datasets used in this study are publicly available at https://doi.org/10.1184/R1/ 27629937.v2.

Author contributions

D. M. A., R. Z., and O. I. designed the study. D. M. A. and R. Z. developed and implemented the method. R. Z. prepared all QM data. D. M. A. and R. Z. ran calculations and created all display items. All authors contributed to the writing of the paper and analysis of the results.

MD simulations

The molecular dynamics simulation for the condensed phase CO2 system was performed using the atomic simulation envi- ronment (ASE)75 with a custom calculator (see the AIMNet2 repository). The simulation was performed under constant number of particles, volume, and temperature (NVT) conditions via the application of a stochastic velocity rescaling thermostat developed by Bussi, Donadio, and Parrinello.76 This thermostat has been veried to correctly sample the canonical ensemble, provides proper conserved quantities, and produces accurate self-diﬀusion coeﬃcients in uid phase water. The NVT simu- lations were carried out with a reference temperature of 298 K, 0.5 fs timestep, and a characteristic thermostat time constant of 100 fs. Initial velocities were assigned by sampling a Maxwell– Boltzmann distribution at 298 K, which were then adjusted to set the total translation and rotational momenta of the system to zero. We veried that these net momenta were conserved during postprocessing of the simulation results. Long-range dispersion and electrostatic interactions were applied using a neighbor list built over a 15 Å cutoﬀat every timestep. We elected to account for electrostatic interactions using the damped shied force method,77 which our initial testing showed to be a suitable choice for the CO2 system to achieve computationally eﬃcient (O(N)) scaling without incurring diﬀerences to the dynamics compared to common long-range solvers, for example, Ewald summation.78 The initial system was prepared using the enhanced Monte Carlo (EMC) soware developed by In't Veld and Rutledge,79 where 1000 CO2 mole- cules were packed into a simulation cell at a density of ∼0.95 g cm−3 and relaxed using an empirical potential. Prior to

Conﬂicts of interest

There are no conicts to declare.

Acknowledgements

The authors acknowledge Dr Adrian Roitberg, Dr Sergei Tretiak, Dr Sebastian Spicher, and Dr Brett Savoie for their invaluable insights and discussions. O. I. acknowledges Dr Ganna (Anya) Gryn'ova for stimulating discussions and hospitality while staying at HITS. This work was made possible by the Oﬃce of Naval Research (ONR) through support provided by the Ener- getic Materials Program (MURI grant no. N00014-21-1-2476). This research is part of the Frontera computing project at the Texas Advanced Computing Center. Frontera is made possible by the National Science Foundation award OAC-1818253. This research, in part, was done using resources provided by the Open Science Grid which is supported by the award 1148698 and the U.S. DOE Oﬃce of Science. This work was performed, in part, at the Center for Integrated Nanotechnologies, an Oﬃce of Science User Facility operated for the U.S. Department of Energy (DOE) Oﬃce of Science by Los Alamos National Laboratory (contract 89233218CNA000001) and Sandia National Laborato- ries (contract DE-NA-0003525). We gratefully acknowledge the support and hardware donation from NVIDIA Corporation and express our special gratitude to Dr Justin Smith. We would also

10240 | Chem. Sci., 2025, 16, 10228–10244 © 2025 The Author(s). Published by the Royal Society of Chemistry


## 第 15 页

Edge Article Chemical Science

throughput experimentation to discover photocatalytically active organic molecules, Chem. Sci., 2021, 12, 10742– 10754, DOI: 10.1039/D1SC02150H. 14 J. S. Smith, B. Nebgen, N. Lubbers, O. Isayev and A. E. Roitberg, Less is more: Sampling chemical space with active learning, J. Chem. Phys., 2018, 148, 241733, DOI: 10.1063/1.5023802. 15 E. V. Podryabinkin and A. V. Shapeev, Active learning of linearly parametrized interatomic potentials, Comput. Mater. Sci., 2017, 140, 171–180, DOI: 10.1016/ j.commatsci.2017.08.031. 16 S. J. Ang, W. Wang, D. Schwalbe-Koda, S. Axelrod and R. G´omez-Bombarelli, Active learning accelerates ab initio molecular dynamics on reactive energy surfaces, Chem, 2021, 7, 738–751, DOI: 10.1016/j.chempr.2020.12.009. 17 J. S. Smith, O. Isayev and A. E. Roitberg, ANI-1: an extensible neural network potential with DFT accuracy at force eld computational cost, Chem. Sci., 2017, 8, 3192–3203, DOI: 10.1039/C6SC05720A. 18 C. Devereux, J. S. Smith, K. K. Huddleston, K. Barros, R. Zubatyuk, O. Isayev and A. E. Roitberg, Extending the Applicability of the ANI Deep Learning Molecular Potential to Sulfur and Halogens, J. Chem. Theory Comput., 2020, 16, 4192–4202, DOI: 10.1021/acs.jctc.0c00121. 19 J. S. Smith, R. Zubatyuk, B. Nebgen, N. Lubbers, K. Barros, A. E. Roitberg, O. I. Isayev and S. Tretiak, The ANI-1ccx and ANI-1x data sets, coupled-cluster and density functional theory properties for molecules, Sci. Data, 2020, 7, 134, DOI: 10.1038/s41597-020-0473-z. 20 O. T. Unke and M. Meuwly, PhysNet: A Neural Network for Predicting Energies, Forces, Dipole Moments, and Partial Charges, J. Chem. Theory Comput., 2019, 15, 3678–3693, DOI: 10.1021/acs.jctc.9b00181. 21 T. W. Ko, J. A. Finkler, S. Goedecker and J. Behler, A fourth- generation high-dimensional neural network potential with accurate electrostatics including non-local charge transfer, Nat. Commun., 2021, 12, 398, DOI: 10.1038/s41467-020- 20427-2. 22 L. Zhang, H. Wang, M. C. Muniz, A. Z. Panagiotopoulos, R. Car and W. E, A deep potential model with long-range electrostatic interactions, J. Chem. Phys., 2022, 156, 124107, DOI: 10.1063/5.0083669. 23 D. M. Anstine and O. Isayev, Machine Learning Interatomic Potentials and Long-Range Physics, J. Phys. Chem. A, 2023, 127, 2417–2431, DOI: 10.1021/acs.jpca.2c06778. 24 O. T. Unke, S. Chmiela, M. Gastegger, K. T. Schütt, H. E. Sauceda and K. R. Müller SpookyNet, Learning force elds with electronic degrees of freedom and nonlocal eﬀects, Nat. Commun., 2021, 12, 7273, DOI: 10.1038/ s41467-021-27504-0. 25 R. Zubatyuk, J. S. Smith, B. T. Nebgen, S. Tretiak and O. Isayev, Teaching a neural network to attach and detach electrons from molecules, Nat. Commun., 2021, 12, 4870, DOI: 10.1038/s41467-021-24904-0. 26 S. Nikolov, M. A. Wood, A. Cangi, J. B. Maillet, M. C. Marinica, A. P. Thompson, M. P. Desjarlais and J. Tranchida, Data-driven magneto-elastic predictions with

like to acknowledge the Armed Forces of Ukraine and dedicate this paper and our gratitude to all the brave Ukrainian defenders.

References

1 S. Curtarolo, G. L. W. Hart, M. B. Nardelli, N. Mingo, S. Sanvito and O. Levy, The high-throughput highway to computational materials design, Nat. Mater., 2013, 12, 191– 201, DOI: 10.1038/nmat3568. 2 K. T. Butler, D. W. Davies, H. Cartwright, O. Isayev and A. Walsh, Machine learning for molecular and materials science, Nature, 2018, 559, 547–555, DOI: 10.1038/s41586- 018-0337-2. 3 B. Huang and O. A. von Lilienfeld, Ab Initio Machine Learning in Chemical Compound Space, Chem. Rev., 2021, 121, 10001–10036, DOI: 10.1021/acs.chemrev.0c01303. 4 J. Behler, Four Generations of High-Dimensional Neural Network Potentials, Chem. Rev., 2021, 121, 10037–10072, DOI: 10.1021/acs.chemrev.0c00868. 5 N. Fedik, R. Zubatyuk, M. Kulichenko, N. Lubbers, J. S. Smith, B. Nebgen, R. Messerly, Y. W. Li, A. I. Boldyrev, K. Barros, O. Isayev and S. Tretiak, Extending machine learning beyond interatomic potentials for predicting molecular properties, Nat. Rev. Chem., 2022, 6, 653–672, DOI: 10.1038/s41570-022-00416-3. 6 J. Westermayr and P. Marquetand, Machine Learning for Electronically Excited States of Molecules, Chem. Rev., 2021, 121, 9873–9926, DOI: 10.1021/acs.chemrev.0c00749. 7 R. Ramakrishnan, P. O. Dral, M. Rupp and O. A. von Lilienfeld, Big Data Meets Quantum Chemistry Approximations: The D-Machine Learning Approach, J. Chem. Theory Comput., 2015, 11, 2087–2096, DOI: 10.1021/ acs.jctc.5b00099. 8 P. Zheng, R. Zubatyuk, W. Wu, O. Isayev and P. O. Dral, Articial intelligence-enhanced quantum chemical method with broad applicability, Nat. Commun., 2021, 12, 7022, DOI: 10.1038/s41467-021-27340-2. 9 O. A. von Lilienfeld and K. Burke, Retrospective on a decade of machine learning for chemical discovery, Nat. Commun., 2020, 11, 4895, DOI: 10.1038/s41467-020-18556-9. 10 F. H¨ase, L. M. Roch and A. Aspuru-Guzik, Next-Generation Experimentation with Self-Driving Laboratories, Trends Chem., 2019, 1, 282–291, DOI: 10.1016/j.trechm.2019.02.007. 11 C. W. Coley, W. H. Green and K. F. Jensen, Machine Learning in Computer-Aided Synthesis Planning, Acc. Chem. Res., 2018, 51, 1281–1289, DOI: 10.1021/acs.accounts.8b00087. 12 C. W. Coley, D. A. Thomas III, J. A. M. Lummiss, J. N. Jaworski, C. P. Breen, V. Shultz, T. Hart, J. S. Fishman, L. Rogers, H. Gao, R. W. Hicklin, P. P. Plehiers, J. Byington, J. S. Piotti, W. H. Green, A. J. Hart, T. F. Jamison and K. F. Jensen, A robotic platform for ow synthesis of organic compounds informed by AI planning, Science, 2019, 365, eaax1566, DOI: 10.1126/science.aax1566. 13 X. Li, P. M. Maﬀettone, Y. Che, T. Liu, L. Chen and A. I. Cooper, Combining machine learning and high-

© 2025 The Author(s). Published by the Royal Society of Chemistry Chem. Sci., 2025, 16, 10228–10244 | 10241


## 第 16 页

Chemical Science Edge Article

38 C. R. Groom, I. J. Bruno, M. P. Lightfoot and S. C. Ward, The Cambridge Structural Database, Acta Crystallogr. B, 2016, 72, 171–179, DOI: 10.1107/S2052520616003954. 39 S. Spicher and S. Grimme, Robust Atomistic Modeling of Materials, Organometallic, and Biochemical Systems, Angew. Chem., Int. Ed., 2020, 59, 15665–15673, DOI:

scalable classical spin-lattice dynamics, npj Comput. Mater., 2021, 7, 153, DOI: 10.1038/s41524-021-00617-2. 27 R. Zubatyuk, J. S. Smith, J. Leszczynski and O. Isayev, Accurate and transferable multitask prediction of chemical properties with an atoms-in-molecules neural network, Sci. Adv., 2024, 5, eaav6490, DOI: 10.1126/sciadv.aav6490. 28 A. Paszke, S. Gross, F. Massa, A. Lerer, J. Bradbury, G. Chanan, T. Killeen, Z. Lin, N. Gimelshein, L. Antiga, A. Desmaison, A. Köpf, E. Yang, Z. DeVito, M. Raison, A. Tejani, S. Chilamkurthy, B. Steiner, L. Fang, J. Bai and S. Chintala, Pytorch: An imperative style, high-performance deep learning library, Adv. Neural Inf. Process. Syst., 2019, 32, DOI: 10.48550/arXiv.1912.01703. 29 S. Grimme, J. Antony, S. Ehrlich and H. Krieg, A consistent and accurate ab initio parametrization of density functional dispersion correction (DFT-D) for the 94 elements H-Pu, J. Chem. Phys., 2010, 132, 154104, DOI: 10.1063/1.3382344. 30 S. Grimme, A. Hansen, J. G. Brandenburg and C. Bannwarth, Dispersion-Corrected Mean-Field Electronic Structure Methods, Chem. Rev., 2016, 116, 5105–5154, DOI: 10.1021/ acs.chemrev.5b00533. 31 A. K. Rappe and W. A. Goddard III, Charge equilibration for molecular dynamics simulations, J. Phys. Chem., 1991, 95, 3358–3363, DOI: 10.1021/j100161a070. 32 J. G. Brandenburg, C. Bannwarth, A. Hansen and S. Grimme, B97-3c: A revised low-cost variant of the B97-D density functional method, J. Chem. Phys., 2018, 148, 064104, DOI: 10.1063/1.5012601. 33 D. Mendez, A. Gaulton, A. P. Bento, J. Chambers, M. De Veij, E. F´elix, M. P. Magariños, J. F. Mosquera, P. Mutowo, M. Nowotka, M. Gordillo-Marañ´on, F. Hunter, L. Junco, G. Mugumbate, M. Rodriguez-Lopez, F. Atkinson, N. Bosc, C. J. Radoux, A. Segura-Cabrera, A. Hersey and A. R. Leach, ChEMBL: towards direct deposition of bioassay data, Nucleic Acids Res., 2019, 47, D930–D940, DOI: 10.1093/nar/ gky1075. 34 S. Kim, J. Chen, T. Cheng, A. Gindulyte, J. He, S. He, Q. Li, B. A. Shoemaker, P. A. Thiessen, B. Yu, L. Zaslavsky, J. Zhang and E. E. Bolton, PubChem 2023 update, Nucleic Acids Res., 2023, 51, D1373–D1380, DOI: 10.1093/nar/ gkac956. 35 C. Bannwarth, S. Ehlert and S. Grimme, GFN2-xTB—An Accurate and Broadly Parametrized Self-Consistent Tight- Binding Quantum Chemical Method with Multipole Electrostatics and Density-Dependent Dispersion Contributions, J. Chem. Theory Comput., 2019, 15, 1652– 1671, DOI: 10.1021/acs.jctc.8b01176. 36 Z. Qiao, M. Welborn, A. Anandkumar, F. R. Manby and T. F. Miller III, OrbNet: Deep learning for quantum chemistry using symmetry-adapted atomic-orbital features, J. Chem. Phys., 2020, 153, 124111, DOI: 10.1063/5.0021955. 37 N. Mardirossian and M. Head-Gordon, uB97M-V: A combinatorially optimized, range-separated hybrid, meta- GGA density functional with VV10 nonlocal correlation, J. Chem. Phys., 2016, 144, 214110, DOI: 10.1063/1.4952647.

10.1002/ange.202004239. 40 L. Goerigk, A. Hansen, C. Bauer, S. Enrlich, A. Najibi and S. Grimme, A look at the density functional theory zoo with the advanced GMTKN55 database for general main group thermochemistry, kinetics and noncovalent interactions, Phys. Chem. Chem. Phys., 2017, 19, 32184– 32215, DOI: 10.1039/C7CP04913G. 41 J. ˇRez´aˇc, Non-Covalent Interactions Atlas Benchmark Data Sets: Hydrogen Bonding, J. Chem. Theory Comput., 2020, 16, 2355–2368, DOI: 10.1021/acs.jctc.9b01265. 42 J. ˇRez´aˇc, Non-Covalent Interactions Atlas Benchmark Data Sets 2: Hydrogen Bonding in an Extended Chemical Space, J. Chem. Theory Comput., 2020, 16, 6305–6316, DOI:

10.1021/acs.jctc.0c00715. 43 K. Kˇr´ıˇz and J. ˇRez´aˇc, Non-covalent interactions atlas benchmark data sets 4: s-hole interactions, Phys. Chem. Chem. Phys., 2022, 24, 14794–14804, DOI: 10.1039/ D2CP01600A. 44 J. ˇRez´aˇc, Non-Covalent Interactions Atlas benchmark data sets 5: London dispersion in an extended chemical space, Phys. Chem. Chem. Phys., 2022, 24, 14780–14793, DOI: 10.1039/D2CP01602H. 45 B. Brauer, M. K. Kesharwani, S. Kozuch and J. M. L. Martin, The S66x8 benchmark for noncovalent interactions revisited: explicitly correlated ab initio methods and density functional theory, Phys. Chem. Chem. Phys., 2016, 18, 20905–20925, DOI: 10.1039/C6CP00688D. 46 A. S. Christensen, S. K. Sirumalla, Z. Qiao, M. B. O'Connor, D. G. A. Smith, F. Ding, P. J. Bygrave, A. Anandkumar, M. Welborn, F. R. Manby and T. F. Miller III, OrbNet Denali: A machine learning potential for biological and organic chemistry with semi-empirical cost and DFT accuracy, J. Chem. Phys., 2021, 155, 204103, DOI: 10.1063/ 5.0061990. 47 B. K. Rai, V. Sresht, Q. Yang, R. Unwalla, M. Tu, A. M. Mathiowetz and G. A. Bakken, TorsionNet: A Deep Neural Network to Rapidly Predict Small-Molecule Torsional Energy Proles with the Accuracy of Quantum Mechanics, J. Chem. Inf. Model., 2022, 62, 785–800, DOI: 10.1021/acs.jcim.1c01346. 48 X. Fu, Z. Wu, W. Wang, T. Xie, S. Keten, R. Gomez- Bombarelli and T. Jaakkola, Forces are not enough: Benchmark and critical evaluation for machine learning force elds with molecular simulations, arXiv, 2022, preprint, arXiv:2210.07237, DOI: 10.48550/arXiv.2210.07237. 49 R. Mathur, M. C. Muniz, S. Yue, R. Car and A. Z. Panagiotopoulos, First-Principles-Based Machine Learning Models for Phase Behavior and Transport Properties of CO2, J. Phys. Chem. B, 2023, 127, 4562–4569, DOI: 10.1021/acs.jpcb.3c00610.

10242 | Chem. Sci., 2025, 16, 10228–10244 © 2025 The Author(s). Published by the Royal Society of Chemistry


## 第 17 页

Edge Article Chemical Science

potentials, J. Comput. Phys., 2015, 285, 316–330, DOI: 10.1016/j.jcp.2014.12.018. 63 L. Zhang, J. Han, H. Wang, R. Car and W. E, Deep Potential Molecular Dynamics: A Scalable Model with the Accuracy of Quantum Mechanics, Phys. Rev. Lett., 2018, 120, 143001, DOI: 10.1103/PhysRevLett.120.143001. 64 Y. Yang, K. U. Lao, D. M Wilkins, A. Grisa, M. Ceriotti and R. A. DiStasio Jr, Quantum mechanical static dipole polarizabilities in the QM7b and AlphaML showcase databases, Sci. Data, 2019, 6, 152, DOI: 10.1038/s41597- 019-0157-8. 65 N. Thomas, T. Smidt, S. Kearnes, L. Yang, L. Li, K. Kohlhoﬀ and P. Riley, Tensor eld networks: Rotation-and translation-equivariant neural networks for 3d point clouds, arXiv, 2018, preprint, arXiv:1802.08219, DOI:

50 L. Zhang, J. Han, H. Wang, R. Car and W. E, Deep Potential Molecular Dynamics: A Scalable Model with the Accuracy of Quantum Mechanics, Phys. Rev. Lett., 2018, 120, 143001, DOI: 10.1103/PhysRevLett.120.143001. 51 E. J. Maginn, R. A. Messerly, D. J. Carlson, D. R. Roe and J. R. Elliot, Best Practices for Computing Transport Properties 1. Self-Diﬀusivity and Viscosity from Equilibrium Molecular Dynamics [Article v1.0], J. Comp. Mol. Sci., 2018, 1, 6324, DOI: 10.33011/livecoms.1.1.6324. 52 T. Groß, J. Buchhauser and H.-D. Lüdemann, Self-diﬀusion in uid carbon dioxide at high pressures, J. Chem. Phys., 1998, 109, 4518–4522, DOI: 10.1063/1.477055. 53 H. Goel, Z. W. Windom, A. A. Jackson and N. Rai, Performance of density functionals for modeling vapor liquid equilibria of CO2 and SO2, J. Comput. Chem., 2018, 39, 397–406, DOI: 10.1002/jcc.25123. 54 O. T. Unke, M. Stöhr, S. Ganscha, T. Unterthiner, H. Maennel, S. Kashubin, D. Ahlin, M. Gastegger, L. M. Sandonas, J. T. Berryman, A. Tkatchenko and K. R. Müller, Biomolecular dynamics with machine-learned quantum-mechanical force elds trained on diverse chemical fragments, Sci. Adv., 2014, 10, eadn4397, DOI: 10.1126/sciadv.adn4397. 55 S. Batzner, A. Musaelian, L. Sun, M. Geiger, J. P. Mailoa, M. Kornbluth, N. Molinari, T. E. Smidt and B. Kozinsky, E(3)-equivariant graph neural networks for data-eﬃcient and accurate interatomic potentials, Nat. Commun., 2022, 13, 2453, DOI: 10.1038/s41467-022-29939-5. 56 A. Musaelian, S. Batzner, A. Johansson, L. Sun, C. J. Owen, M. Kornbluth and B. Kozinsky, Learning local equivariant representations for large-scale atomistic dynamics, Nat. Commun., 2023, 14, 579, DOI: 10.1038/s41467-023-36329-y. 57 G. Simeon and G. De Fabritiis, Tensornet: Cartesian tensor representations for eﬃcient learning of molecular potentials, Adv. Neural Inf. Process. Syst., 2024, 36, DOI: 10.48550/arXiv.2306.06482. 58 I. Batatia, D. P. Kovacs, G. Simm, C. Ortner and G. Cs´anyi, MACE: Higher order equivariant message passing neural networks for fast and accurate force elds, Adv. Neural Inf. Process. Syst., 2022, 35, 11423–11436, DOI: 10.48550/ arXiv.2206.07697. 59 R. Gao, Y. Li and R. Car, Enhanced deep potential model for fast and accurate molecular dynamics: application to the hydrated electron, Phys. Chem. Chem. Phys., 2024, 26, 23080–23088, DOI: 10.1039/D4CP01483A. 60 M. A. Wood and A. P. Thompson, Extending the accuracy of the SNAP interatomic potential form, J. Chem. Phys., 2018, 148, 241721, DOI: 10.1063/1.5017641. 61 S. Chmiela, H. E. Sauceda, I. Poltavsky, K. R. Müller and A. Tkatchenko, sGDML: Constructing accurate and data eﬃcient molecular force elds using machine learning, Comput. Phys. Commun., 2019, 240, 38–45, DOI: 10.1016/ j.cpc.2019.02.007. 62 A. P. Thompson, L. P. Swiler, C. R. Trott, S. M. Foiles and G. J. Tucker, Spectral neighbor analysis method for automated generation of quantum-accurate interatomic

10.48550/arXiv.1802.08219. 66 J. Nigam, M. J. Willatt and M. Ceriotti, Equivariant representations for molecular Hamiltonians and N-center atomic-scale properties, J. Chem. Phys., 2022, 156, 014115, DOI: 10.1063/5.0072784. 67 ChemAxon. JChem, 2010, https://www.chemaxon.com. 68 S. Grimme, A General Quantum Mechanically Derived Force Field (QMDFF) for Molecules and Condensed Phase Simulations, J. Chem. Theory Comput., 2014, 10, 4497–4514, DOI: 10.1021/ct500573f. 69 G. Landrum, RDKit, 2010, https://www.rdkit.org. 70 F. Neese, Soware update: The ORCA program system— Version 5.0, Wiley Interdiscip. Rev. Comput. Mol. Sci., 2022, 12, e1606, DOI: 10.1002/wcms.1606. 71 I. Loshchilov, Decoupled weight decay regularization, arXiv, 2017, preprint, arXiv:1711.05101, DOI: 10.48550/ arXiv.1711.05101. 72 B. Settles, Active Learning, Synthesis Lectures on Articial Intelligence and Machine Learning, 2012, vol. 6, pp. 1–114, DOI: 10.1007/978-3-031-01560-1. 73 T. Wang, J. Y. Zhu, A. Torralba and A. A. Efros, Dataset Distillation, arXiv, 2018, preprint, arXiv:1811.10959, DOI: 10.48550/arXiv.1811.10959. 74 N. Sachdeva and J. McAuley, Data Distillation: A Survey, arXiv, 2023, preprint, arXiv:2301.04272, DOI: 10.48550/ arXiv.2301.04272. 75 A. H. Larsen, J. J. Mortensen, J. Blomqvist, I. E. Castelli, R. Christensen, M. Dułak, J. Friis, M. N. Groves, B. Hammer, C. Hargus, E. D. Hermes, P. C. Jennings, P. B. Jensen, J. Kermode, J. R. Kitchin, E. L. Kolsbjerg, J. Kubal, K. Kaasbjerg, S. Lysgaard, J. B. Maronsson, T. Maxson, T. Olsen, L. Pastewka, A. Peterson, C. Rostgaard, J. Schiøtz, O. Schütt, M. Strange, K. S. Thygesen, T. Vegge, L. Vilhelmsen, M. Walter, Z. Zeng and K. W. Jacobsen, The atomic simulation environment— a Python library for working with atoms, J. Phys.: Condens. Matter, 2017, 29, 273002, DOI: 10.1088/1361-648X/aa680e. 76 G. Bussi, D. Donadio and M. Parrinello, Canonical sampling through velocity rescaling, J. Chem. Phys., 2007, 126, 014101, DOI: 10.1063/1.2408420. 77 C. J. Fennell and J. D. Gezelter, Is the Ewald summation still necessary? Pairwise alternatives to the accepted standard for

© 2025 The Author(s). Published by the Royal Society of Chemistry Chem. Sci., 2025, 16, 10228–10244 | 10243


## 第 18 页

Chemical Science Edge Article

Freely Rotating Chains, Macromolecules, 2003, 36, 7358– 7365, DOI: 10.1021/ma0346658. 80 A. P. Thompson, S. J. Plimpton and W. Mattson, General formulation of pressure and stress tensor for arbitrary many-body interaction potentials under periodic boundary conditions, J. Chem. Phys., 2009, 131, 154107, DOI:

long-range electrostatics, J. Chem. Phys., 2006, 124, 234104, DOI: 10.1063/1.2206581. 78 P. P. Ewald, Die Berechnung optischer und elektrostatischer Gitterpotentiale, Ann. Phys., 1921, 369, 253–287, DOI: 10.1002/andp.1921369030. 79 P. J. In't Veld and G. C. Rutledge, Temperature-Dependent Elasticity of a Semicrystalline Interphase Composed of

10.1063/1.3245303.

10244 | Chem. Sci., 2025, 16, 10228–10244 © 2025 The Author(s). Published by the Royal Society of Chemistry
