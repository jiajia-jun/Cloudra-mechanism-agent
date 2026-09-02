# Benchmark Construction Narrative: How the 100-Reaction Set Is Defined, Scored, and What Question It Answers

> 说明：本文是论文 §3.2 的科学叙事改写稿（替代当前"技术实施说明"式写法——只讲机制怎么搭、字段是什么，不讲"为什么这样设计、答什么科学问题"）。目标：把 benchmark 的**反应集分类学（taxonomy）**、**打分机制（scoring）**、**背后的科学故事（scientific rationale）**讲成一段可读的叙事，而非技术文档。英文正文可直接入论文；中文分段落在"科学故事"小标题下，保留给作者审校语义。

---

## 3.2 What the Reaction Set Is, and What It Is Designed to Test

Cloudra is evaluated on a deliberately **tiered** reaction set rather than a flat collection of examples. The four tiers are not ordered by "how hard the question is to look up," but by the **kind of scientific judgment** the agent must exercise in order to answer correctly. Each tier therefore targets a distinct failure mode of an autonomous chemistry agent, and the four together compose a single question: *can an agent correctly decide what to compute, rather than merely execute a computation it was told to perform?*

**Easy (30).** The baseline. These are textbook single-step elementary transformations of small, closed-shell, singlet molecules (a canonical Diels–Alder, a Claisen or Cope rearrangement, a 4π/6π electrocyclization, an $S_N2$, an $E2$, a carbonyl addition, a hydrogen transfer) plus a set of intramolecular processes (atropisomeric rotation, ammonia umbrella inversion, conformational rotation, proton-cluster transfer). They are deliberately drawn from the high-density region where the underlying interatomic potential is well behaved, so that a correct answer requires only that the agent be able to *produce a self-consistent mechanistic closure*: a valid saddle, a bidirectional IRC that actually connects the two endpoints, and a physically consistent frequency. The tier answers the baseline question: **does the agent compute a mechanism the way a careful researcher would, or does it merely narrate one?**

**Normal (30).** This tier raises the demand to **mechanistic complexity**. It is deliberately scaffolded in three ascending bands: (i) *route discrimination* — a single substrate that can react through competing channels such as $S_N2$ vs. $E2$, Zaitsev vs. Hofmann elimination, or a 1,2- vs. 1,4-addition, where the correct answer depends on which pathway is actually kinetically favored; (ii) *simple multi-step networks* (two to three elementary steps); and (iii) *complex named-reaction cascades* (three to four steps, e.g. a Fischer indole synthesis or a Paal–Knorr heterocyclization). What is being tested is the agent's ability to **generate and prune a mechanism hypothesis**: to propose intermediates, capture them, rank competing barrier heights, and decide which branch of a reaction network is physically operative. The set is drawn from textbook classics whose mechanisms and free-energy orderings are established, and the pool is de-duplicated at the level of *mechanistic essence* (a scripted chemical-difference analysis finds the 48 candidates collapse to ≈32 distinct mechanistic types; the redundancy that remains is deliberate, e.g. acid/base or O/N "contrast pairs" that exist specifically to test whether an agent can tell two superficially similar mechanisms apart).

**Hard (20).** This tier raises the demand to **stereochemical 3-D selectivity**. It tests three things: (i) *stereospecificity* — whether a given substrate geometry *deterministically* maps to a single product configuration (Woodward–Hoffmann rules, syn/anti addition and elimination, $S_N2$ inversion); (ii) *stereoselectivity competition* — whether the agent can resolve the free-energy difference between two *diastereomeric* transition states (endo:exo, face selectivity, torquoselectivity), which is a genuinely quantitative, geometry-dependent question; and (iii) *configurational stability* — barriers to atropisomer racemization. The tier exists because this is precisely where a string- or rule-level "chemical intuition" fails: the answer lives in three-dimensional electronic structure, not in the connectivity of the SMILES. The agent must not only find the transition states but compare competing ones, and the gold reference carries the *difference* between competing channels rather than a single absolute barrier.

**Impossible (20).** The most novel tier, and the one that defines the benchmark's central claim. These are **strong-static-correlation / near-degenerate diradical systems** — reaction geometries where a single-reference description (RHF-CCSD(T), closed-shell RKS-DFT, or an MLIP whose training labels come from single-reference DFT) returns *non-physical* results: wrong electronic-state ordering, artificial symmetry breaking, or barriers off by tens of kilocalories per mole. Here the correct behavior is **not** to compute a number. It is for the agent to recognize, during its spin/electronic-state diagnosis, that the requested quantity lies outside the validity of its allowed methods, and to **issue a justified scientific refusal** — explaining *why* the result is untrustworthy and what level of theory (CASSCF/CASPT2/MRCI) would be required. Each impossible case is paired with a **sibling control**: a mechanistically related reaction from the same family that *is* single-reference amenable. The intended signal is a conjunction — the agent must refuse the impossible case *and* solve its sibling — because only that pairing proves the refusal arose from a genuine electronic-structure diagnosis rather than from the difficulty or unfamiliarity of the problem.

Taken together, the tiers are a graded probe of the scientific judgment that matters most for an autonomous quantum-chemistry agent: **correct single-step execution, mechanistic hypothesis generation and pruning, stereochemical 3-D perception, and finally an honest assessment of the boundaries of the method itself.** It is the last of these — reliable abstention when the method is invalid — that we believe is the most consequential and least-well-served capability in current computational-chemistry agents, and it is the axis on which the benchmark is most clearly novel.

---

## Scoring: A Forensic Audit, Not a Self-Report

The benchmark is engineered around a single premise: **an agent's self-declared success is not evidence.** Rather than trusting a narrative summary, every run is scored by an independent, deterministic forensic pass over the agent's sandbox. This mirrors how a human supervisor would audit a computational study — by asking whether the claimed results are actually backed by reproducible artifacts, and whether those artifacts are physically sound.

Scoring is composed of three nested layers plus a structural comparison:

1. **Evidence integrity (Layer 1).** The scorer recursively scans the sandbox, locates the delivered mechanism graph, and binds every graph element to a concrete computational evidence file. Binding is mediated by the `smiles:` annotation that the delivery contract requires in every evidence file (which propagates into quantum-chemistry logs via the input title/comment). A matching fingerprint or molecular-hash earns full credit; a species that differs only by protonation/charge state earns partial credit; a claim with no backing evidence earns none. A mechanism graph that is missing, unparseable, or bound to zero evidence is *penalized* — an unsupported mechanistic claim is judged worse than no claim at all. This layer answers: **does the agent deliver what it claims to deliver, or is it asserting a result?**

2. **Physical self-consistency (Layer 2).** Independent of any gold reference, every transition state is checked to be a first-order saddle (exactly one imaginary frequency, excluding spurious low-frequency conformer modes below 100 cm⁻¹), its IRC is checked to connect both endpoints, and every species is checked to be a genuine minimum. This layer answers: **is the computed mechanism internally physically valid, rather than a numerically plausible but saddle-free narrative?**

3. **Barrier accuracy (Layer 3).** Where a reference barrier exists, the agent's reported barrier is scored with a Gaussian tolerance — the score decays exponentially with the squared deviation, calibrated per task, and capped so that legitimate method-level differences are not over-penalized. This layer answers: **is the magnitude right, not just the topology?**

4. **Mechanism-graph comparison.** The delivered graph is compared to the gold mechanism graph with a chemistry-parameterized graph edit distance. Default scoring is *subgraph coverage*: the gold mechanism must be found within the delivered graph, while any extra delivered nodes or edges are free. This encodes the scientific stance that *investigating more than necessary is never penalized* — the penalty is reserved for a wrong step, a missing intermediate, or a chemically mismatched species. Node substitution is priced by a molecular-hash shortcut and, in the general case, by a sigmoid over Morgan-fingerprint similarity; edge substitution is priced by the symmetric difference of the atom-mapped bond-change sets, so that a concerted-versus-stepwise divergence is explicitly priced. Stereochemistry is treated layer-appropriately: ignored for Easy/Normal, but costly for Hard.

The four are combined as a weighted composite, then multiplied by a binding-quality factor derived from the integrity layer:

```
final = (0.5 · graph_score + 0.2 · self_consistency_pass + 0.3 · accuracy_score) × binding_quality
```

The weights are a deliberate statement about what matters. **Graph topology dominates (0.5)** — getting the mechanism right is the primary goal. **Physical validity (0.2)** is a gate that must be passed but is binary. **Barrier magnitude (0.3)** is the quantitative check. The **binding-quality multiplier** drives the anti-fabrication point home: even a topologically perfect mechanism earns nothing if it is not backed by actual computational evidence. Refusal behavior is tracked *orthogonally* to this score (every tier can end answered / refused / failed), because the Impossible tier's headline metric is not a per-tier score but a **cross-tier refusal calibration** — how precisely the agent refuses where it should and answers where it should — which is precisely the metric that a "refuse everything" agent cannot inflate.

---

## 科学故事（写给作者：为什么这样分层，答什么科学问题）

**一句话：这个 benchmark 考的不是"能不能把量子化学跑起来"，而是"能不能正确地决定该算什么"。**

四档是同一根轴上的四档科学判断力，每档对准一个独立的失效模式：

- **Easy = 「你算的是不是一个自洽的机理」**。小分子、闭壳、单重态、方法舒适区。这里只要求 agent 给出"TS+双向 IRC+频率"的自洽闭环，而不是讲一个机理故事。锚点能垒只作 $\pm2$ kcal/mol 的参考，不作 pass/fail 硬线——Easy 考的是**闭环能力**，不追绝对真值。

- **Normal = 「你能不能生成并剪枝一个机理假设」**。从"单底物多通道判别"到"2–3 步简单网络"再到"3–4 步人名反应级联"，层层递进。考点是**机理假设生成、中间体捕获、竞争路径能垒排序、反应网络 DAG 剪枝**。选入优先级：MACE 可算性 > 机理判别价值 > 文献锚点完整度；池子按"化学本质"去重（48 条收敛到约 32 个本质，剩下的冗余是刻意的对照题）。锚点缺失/口径偏差**不构成剔除理由**——因为最终参考值会由我们自算标定，而不是把文献二手数字当 ground truth。

- **Hard = 「你能不能感知三维**立体选择性**」**。这是 string/规则级"化学直觉"会失效的地方：答案在三维电子结构里，不在 SMILES 的连接性里。考点是立体专一（构型→产物确定映射）、立体选择性竞争（两个非对映 TS 的能垒差 → dr/ee/endo:exo/面选择性）、构型稳定性阻垒（轴手性消旋）。gold 带竞争立体通道，要求两条 TS 都交付；锚点是**能垒差 ΔΔG‡/ΔΔE‡**（进 `gold.selectivity`，绝不塞进绝对能垒），立体失配在打分里是**昂贵**的。

- **Impossible = 「你能不能诚实面对方法的边界」**。强静态关联/近简并双自由基体系，单参考（RHF-CCSD(T)、闭壳 RKS-DFT、用单参考 DFT 标签训练的 MLIP）在这些区域的单线态势能面**输出非物理结果**（错误态序、虚假对称破缺、能垒偏差数十 kcal/mol）。这里的"正确答案"是**拒答**——识别多参考特征后主动说明为何不可信、需要 CASSCF/CASPT2/MRCI。每个 impossible 题配一个**兄弟题**（同反应族、单参考可算），信号 = 本题拒答 × 兄弟题正常作答——**只有这个合取才能证明拒答源于电子结构诊断，而不是"题目难/不会做"**。

**为什么这是科学故事里的核心亮点**：现有计算化学 agent 或用 MLIP 跑断连 QM 脚本，或做一个"自宣成功"的机理叙事；几乎没有一个系统能在算力/方法受限时**主动、可信地拒答**。而"在方法无效时做可靠的拒答"本身就是**正确的科研决策行为**，也恰恰是现有多数大模型系统做不到的指标。这是 benchmark 最清晰的差异化轴——我们调研确认学术界对"计算化学 agent 的多参考识别与合理拒答"尚无成熟基准。

**方法底座与物理天花板**：全档统一以 MACE-OMol25 为唯一物理计算金标准（单引擎锁定，2026-08-25 决策，不再引入 AIMNet2/MACE-OFF 作交叉验证）。这个选择本身就是要**探 MLIP 的训练分布偏向与物理边界**：OMol25 全量标注基于单参考 DFT（开壳层用 UKS），对强静态关联/近简并/多参考双自由基体系，底层 DFT 数据本身失真，MACE 在该区域输出非物理能垒。所以 Impossible 档对 MACE 是**物理死穴**——这正是我们想测的：一个"用 MLIP 当计算引擎"的 agent，能否诚实报告它的引擎在哪些体系上根本不可信。

**打分哲学**：**永远不信任 agent 的自宣成功**（completion by assertion）。跑完后对沙箱做事后取证——交付图是否存在、每个节点/步是否有真实计算证据支撑、TS 是不是一阶鞍点且被 IRC 连通、能垒是否落在参考容差内。这是对抗"编造/自圆其说"的核心设计。composite 里 **图拓扑占 0.5**（机理对不对是首要）、**物理自洽占 0.2**（门槛，二元）、**能垒大小占 0.3**（定量核对），再乘上**证据绑定质量**（乘法因子）——把"无证据支撑的机理声明比没交付更糟"这层意思落地。

**能垒口径纪律**：energy-barrier 的参考系本身会影响打分——"TS 相对预反应络合物（central_complex）"与"TS 相对分离反应物渐近线（reactants）"差一个络合物阱深（约 10 kcal/mol）。Easy 档统一记 central_complex；凡文献锚点属分离渐近线口径的题，数值保留、`verification` 一律降 `unverified` 待核，**不按新口径编造数值**。这是诚实测度的一部分。

**构造可复现性（一句话，不进正文细节）**：每档由一个策展候选池（`easy.md`/`normal.md`/`hard.md`/`impossible.md`）作为唯一事实源，生成器确定性产出 `TaskSpec` JSON；`bond_changes` 对多步档**由相邻步原子映射 SMILES 差集推导（禁止手填）**，且逐题 fail-loud 校验（原子映射/形式电荷守恒、去映射后等于池内 SMILES、每步有键级变化）；参考能垒的 `verification`/`computed_by_us` 明确区分文献锚点与自算值。这些是让 benchmark 可审计、可复现、且不被"泄露答案"的工程保证，但论文只须一句带过，不必展开。
