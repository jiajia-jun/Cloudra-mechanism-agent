"""Explicit built-in tool manifest.

Keep this module dependency-free: the execution kernel imports
``cloudra.tools``, while tool implementations pull in optional extras
(chem/visual) and heavy modules that may legitimately be missing.  The registry
therefore stores import paths instead of importing tool classes at module
import time.

Optional semantic fields are the single source of truth for downstream policy
projections (DAG gate / runtime profiles / evidence derivation).  Downstream
modules must query :mod:`cloudra.tools.capabilities` instead of maintaining
their own per-tool name sets.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolRegistration:
    module: str
    class_name: str
    summary: str = ""
    skill_references: tuple[tuple[str, str], ...] = ()

    # Declared wire name. Only needed when the tool has non-default semantics
    # (or a tool_name that differs from class_name); capabilities only projects
    # entries that carry it.
    tool_name: str = ""

    # DAG semantics. All flags default to the conservative/plain behavior.
    dag_observe: bool = True
    evidence_deriver: str = ""  # "module:function(current, role, arguments, result)->dict"
    # 事实适配器（contract_version=2）："module:function(payload, source_ref)
    # -> list[EvidenceFact]"；从已登记证据中抽类型化事实（含反证）。
    dag_fact_adapter: str = ""
    # 证据产生工具：完成的调用产出计算证据（知识检索触发语义）。
    # §5 起不再有"自动入 CallReview 收件箱"的开关——送审只能显式
    # （dag_bind_evidence with claim）。
    dag_evidence_producer: bool = False
    # Phase 3 门槛：mechanism 未被接受前拦截的计算入口（开算/写计算输入）。
    dag_compute_entry: bool = False
    dag_compute_predicate: str = ""  # "module:function(arguments)->bool", overrides dag_compute_entry

    # Runtime availability. The default keeps the Android allow-list opt-in.
    runtime_profiles: frozenset[str] = frozenset({"desktop"})

    # Visual-mode gate: image-producing/consuming tools hidden unless the
    # agent's visual_mode setting is on.
    visual: bool = False

    # Supervisor capability: whether the scientific Supervisor may discover and
    # execute this tool. One of: "none" (default, hidden), "evidence_read"
    # (read-only evidence access), "skill_read", "hub" (AgentHub, action-gated),
    # "review_decision" (control-plane verdicts). Projected exclusively via
    # tools/capabilities.py; do not keep separate supervisor tool name sets.
    supervisor_access: str = "none"

    # Invocation routing. Direct controls stay top-level wire tools in the
    # javascript protocol (exposed next to js_exec) and are rejected inside a
    # guest program; ordinary business tools are the only guest-callable ones.
    invocation_direct_only: bool = False

    # Config gate: "<section>.<field>" naming a boolean on CloudraConfig.
    # When the flag is false the tool is hidden from the wire projection and
    # hard-fails at call time (the tool itself must check the flag too).
    config_gate: str = ""

    # Role allowlist: non-empty restricts the tool to the listed role_ids —
    # the wire projection hides it from other roles and PermissionStage
    # hard-fails their calls. Empty means every role may use it (default).
    # Never set on direct controls, dag_* or supervisor-surface tools: their
    # gates (invocation_direct_only / orchestration mode / supervisor_access)
    # are separate mechanisms.
    role_allowlist: frozenset[str] = frozenset()


# 化学/QM 工具的默认使用者：科学计算角色 + Coordinator（benchmark 题面
# agent 以 coordinator 角色运行，绝不能失去化学工具链）。supervisor 在列
# 仅为保住其 evidence_read 投影面（log_parser/reaction_mapping）——它的
# 实际可见面仍由 supervisor_access 收窄，allowlist 对它是只减不增。
_SCIENCE_ROLES = frozenset(
    {"coordinator", "small_mol", "md", "dft", "experiment", "supervisor"}
)

TOOL_REGISTRY: tuple[ToolRegistration, ...] = (
    ToolRegistration('cloudra.tools.Skilltool.get_tool_docs', 'GetToolDocs',
        tool_name='get_tool_docs', summary='Read complete current contracts for named tools without granting permissions.',
        dag_observe=False, supervisor_access='skill_read'),
    ToolRegistration(
        module='cloudra.tools.Bashtool.bash',
        class_name='Bash',
        tool_name='bash',
        dag_compute_predicate='cloudra.tools.core.bash_habit_guard:is_substantive_bash_command',
        summary='Execute an authorized shell command; compute submission remains gated.',
    ),
    ToolRegistration(
        module='cloudra.tools.Browsertool.browser',
        class_name='HeadlessBrowser',
        tool_name='browser',
        summary='Browse web pages and inspect online sources.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.conformer_search',
        class_name='ConformerSearch',
        tool_name='conformer_search',
        dag_compute_entry=True,
        role_allowlist=_SCIENCE_ROLES,
        summary='Generate conformer ensembles or constrained seeds; search success is not scientific qualification.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.electronic_analysis',
        class_name='ElectronicAnalysis',
        tool_name='electronic_analysis',
        dag_compute_entry=True,
        role_allowlist=_SCIENCE_ROLES,
        summary='Analyze electronic properties from declared structures and calculations.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.format_converter',
        class_name='FormatConverter',
        tool_name='format_converter',
        role_allowlist=_SCIENCE_ROLES,
        summary='Convert molecular file formats while preserving atom information.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.qm_input_writer',
        class_name='QmInputWriter',
        tool_name='qm_input_writer',
        dag_compute_entry=True,
        role_allowlist=_SCIENCE_ROLES,
        summary='Write native QM input using explicitly declared calculation settings.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.image_to_smiles',
        class_name='ImageToSmiles',
        tool_name='image_to_smiles',
        role_allowlist=_SCIENCE_ROLES,
        summary='Extract a molecular representation from a chemical image.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.cdxml_to_graph',
        class_name='CdxmlToGraph',
        tool_name='cdxml_to_graph',
        role_allowlist=_SCIENCE_ROLES,
        summary='Read molecular graphs from ChemDraw CDXML files.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.internal_coordinates',
        class_name='InternalCoordinates',
        tool_name='internal_coordinates',
        role_allowlist=_SCIENCE_ROLES,
        summary='Inspect or adjust molecular internal coordinates with explicit atom numbering.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.ir_processor',
        class_name='IRProcessor',
        tool_name='ir_processor',
        # 实验谱图处理：experiment 角色专属
        role_allowlist=frozenset({'experiment'}),
        summary='Process experimental infrared spectra.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.log_parser',
        class_name='LogParser',
        tool_name='log_parser',
        evidence_deriver='cloudra.tools.Chemtool.log_parser:derive_delivery_changes',
        dag_fact_adapter='cloudra.dag.fact_adapters:log_parser_facts',
        dag_evidence_producer=True,
        supervisor_access='evidence_read',
        role_allowlist=_SCIENCE_ROLES,
        summary='Extract numerical and termination evidence from actual QM logs.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.molecule_drawer',
        class_name='MoleculeDrawer',
        tool_name='molecule_drawer',
        role_allowlist=_SCIENCE_ROLES,
        summary='Draw a two-dimensional molecular structure.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.mechanism_predict',
        class_name='MechanismPredict',
        tool_name='mechanism_predict',
        # ML 机理假设生成器（FlowER 外部 conda env）：不是计算证据；
        # flower.enabled 默认开（未装环境时调用层引导 setup_flower.sh）。
        config_gate='flower.enabled',
        role_allowlist=_SCIENCE_ROLES | {'researcher'},
        summary='Generate ML mechanism hypotheses; predictions are not calculation evidence.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.name_to_structure',
        class_name='NameToStructure',
        tool_name='name_to_structure',
        role_allowlist=_SCIENCE_ROLES,
        summary='Resolve a chemical name to a molecular structure.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.nmr_processor',
        class_name='NMRProcessor',
        tool_name='nmr_processor',
        # 实验谱图处理：experiment 角色专属
        role_allowlist=frozenset({'experiment'}),
        summary='Process experimental NMR spectra.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.pymol_render',
        class_name='PymolRender',
        tool_name='pymol_render',
        visual=True,
        role_allowlist=_SCIENCE_ROLES,
        summary='Render molecular geometry images for visual inspection.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.query_compute_job',
        class_name='QueryComputeJob',
        tool_name='query_compute_job',
        role_allowlist=_SCIENCE_ROLES,
        summary='Read job states and output locations; completion does not imply scientific verification.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.query_compute_queue',
        class_name='QueryComputeQueue',
        tool_name='query_compute_queue',
        role_allowlist=_SCIENCE_ROLES,
        summary='Inspect compute-node capacity and queued or running jobs.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.mark_compute_job_failed',
        class_name='MarkComputeJobFailed',
        tool_name='mark_compute_job_failed',
        dag_observe=False,
        role_allowlist=_SCIENCE_ROLES,
        summary='Request guarded failure bookkeeping for a compute job; active locks protect running calculations.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.reaction_mapping',
        class_name='ReactionMapping',
        tool_name='reaction_mapping',
        evidence_deriver='cloudra.tools.Chemtool.reaction_mapping:derive_delivery_changes',
        dag_fact_adapter='cloudra.dag.fact_adapters:reaction_mapping_facts',
        dag_evidence_producer=True,
        supervisor_access='evidence_read',
        role_allowlist=_SCIENCE_ROLES,
        summary='Establish and inspect atom correspondence between reaction endpoints.',
    ),
    # TS writes and independent read-only inspection.
    ToolRegistration(
        'cloudra.tools.Chemtool.ts_search_process', 'TsPrepare', tool_name='ts_prepare',
        role_allowlist=_SCIENCE_ROLES,
        summary='Start one durable TS path from grouped explicit inputs; successful jobs advance automatically.',
    ),
    ToolRegistration(
        'cloudra.tools.Chemtool.ts_search_process', 'TsResume', tool_name='ts_resume',
        role_allowlist=_SCIENCE_ROLES,
        summary='Revise an existing TS path with input changes and a reason; queued jobs may be replaced.',
    ),
    ToolRegistration(
        'cloudra.tools.Chemtool.ts_search_process', 'TsStop', tool_name='ts_stop',
        role_allowlist=_SCIENCE_ROLES, dag_observe=False,
        summary='Stop TS advancement, withdraw queued jobs and request safe cancellation; retain results for inspection or resume.',
    ),
    ToolRegistration(
        'cloudra.tools.Chemtool.ts_search_process', 'TsInspect', tool_name='ts_inspect',
        supervisor_access='evidence_read', dag_observe=False,
        summary='Read authoritative TS state, current atom order, evidence and missing inputs without advancing.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.smiles_to_mol',
        class_name='SmilesToMol',
        tool_name='smiles_to_mol',
        role_allowlist=_SCIENCE_ROLES,
        summary='Build a molecular structure from SMILES with explicit molecular state.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.submit_compute_job',
        class_name='SubmitComputeJob',
        tool_name='submit_compute_job',
        dag_compute_entry=True,
        role_allowlist=_SCIENCE_ROLES,
        summary='Submit an authorized native QM job; formal TS and IRC use the TS workflow.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.thermo_analysis',
        class_name='ThermoAnalysis',
        tool_name='thermo_analysis',
        evidence_deriver='cloudra.tools.Chemtool.thermo_analysis:derive_delivery_changes',
        dag_evidence_producer=True,
        role_allowlist=_SCIENCE_ROLES,
        summary='Extract thermochemical quantities from declared calculation evidence.',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.ts_guess',
        class_name='TsGuess',
        tool_name='ts_guess',
        evidence_deriver='cloudra.tools.Chemtool.ts_guess:derive_delivery_changes',
        dag_fact_adapter='cloudra.dag.fact_adapters:ts_guess_facts',
        dag_evidence_producer=True,
        dag_compute_predicate='cloudra.tools.Chemtool.ts_guess:is_compute_entry_call',
        role_allowlist=_SCIENCE_ROLES,
        summary='Generate or inspect TS guesses and scans; a guess is not a verified saddle point.',
    ),
    ToolRegistration(
        module='cloudra.tools.Interactool.ask_user',
        class_name='AskUser',
        tool_name='ask_user',
        invocation_direct_only=True,
        summary='Ask the human for missing information or a required decision; direct control.',
    ),
    ToolRegistration(
        module='cloudra.tools.Interactool.email_reader',
        class_name='EmailReader',
        tool_name='email_reader',
        config_gate='email.enabled',
        summary='Read configured email messages.',
    ),
    ToolRegistration(
        module='cloudra.tools.Interactool.email_sender',
        class_name='EmailSender',
        tool_name='email_sender',
        config_gate='email.enabled',
        summary='Send email through the configured account with required authorization.',
    ),
    ToolRegistration(
        module='cloudra.tools.Managetool.agent_hub',
        class_name='AgentHub',
        tool_name='agent_hub',
        runtime_profiles=frozenset({'desktop', 'android'}),
        supervisor_access='hub',
        summary='Discover peers and exchange project-scoped tasks, messages or skills.',
    ),
    ToolRegistration(
        module='cloudra.tools.Managetool.get_subagent_report',
        class_name='GetSubAgentReport',
        tool_name='get_subagent_report',
        runtime_profiles=frozenset({'desktop', 'android'}),
        summary='Read the recorded report of a delegated agent.',
    ),
    ToolRegistration(
        module='cloudra.tools.Managetool.schedule',
        class_name='Schedule',
        tool_name='schedule',
        runtime_profiles=frozenset({'desktop', 'android'}),
        invocation_direct_only=True,
        summary='Schedule future work or wait for a wakeup; direct control.',
    ),
    ToolRegistration(
        module='cloudra.tools.Managetool.subagent_launcher',
        class_name='SubAgentLauncher',
        tool_name='subagent_launcher',
        runtime_profiles=frozenset({'desktop', 'android'}),
        role_allowlist=frozenset({'coordinator'}),
        summary='Launch an authorized specialist agent for a concrete task.',
    ),
    ToolRegistration(
        module='cloudra.tools.Managetool.subagent_swarm',
        class_name='SubAgentSwarm',
        tool_name='subagent_swarm',
        role_allowlist=frozenset({'coordinator'}),
        summary='Launch a coordinated group of authorized task agents.',
    ),
    ToolRegistration('cloudra.tools.Plantool.goal', 'GoalSet', summary='Set or update the current task goal.'),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_view',
        class_name='DagView',
        tool_name='dag_view',
        dag_observe=False,
        supervisor_access='evidence_read',
        summary='Read the mechanism graph and its current delivery state.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_delivery_report',
        class_name='DagDeliveryReport',
        tool_name='dag_delivery_report',
        dag_observe=False,
        supervisor_access='evidence_read',
        summary='Read delivery completeness, pending checks and review status.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_add_species',
        class_name='DagAddSpecies',
        tool_name='dag_add_species',
        dag_observe=False,
        summary='Add a molecular species to the mechanism graph.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_add_step',
        class_name='DagAddStep',
        tool_name='dag_add_step',
        dag_observe=False,
        summary='Add a reaction step between species in the mechanism graph.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_update_delivery_element',
        class_name='DagUpdateDeliveryElement',
        tool_name='dag_update_delivery_element',
        dag_observe=False,
        summary='Update declared fields of an existing delivery element.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_remove_edge',
        class_name='DagRemoveEdge',
        tool_name='dag_remove_edge',
        dag_observe=False,
        summary='Remove a graph edge with an explicit reason.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_remove_node',
        class_name='DagRemoveNode',
        tool_name='dag_remove_node',
        dag_observe=False,
        # 无 supervisor_access：删图是研究侧（Coordinator/子 agent）的修改
        # 权限；Supervisor 保留审查职责、不顺带获得直接删图能力。
        summary='Remove a graph node with an explicit reason.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_bind_evidence',
        class_name='DagBindEvidence',
        tool_name='dag_bind_evidence',
        dag_observe=False,
        summary='Bind actual evidence to a delivery claim for review.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_propose_mechanism',
        class_name='DagProposeMechanism',
        tool_name='dag_propose_mechanism',
        dag_observe=False,
        summary='Propose a mechanism graph for scientific review.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_submit_step_evidence',
        class_name='DagSubmitStepEvidence',
        tool_name='dag_submit_step_evidence',
        dag_observe=False,
        summary='Submit recorded evidence for a reaction step.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_submit_species_evidence',
        class_name='DagSubmitSpeciesEvidence',
        tool_name='dag_submit_species_evidence',
        dag_observe=False,
        summary='Submit recorded evidence for a molecular species.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_review_step',
        class_name='DagReviewStep',
        tool_name='dag_review_step',
        dag_observe=False,
        supervisor_access='review_decision',
        summary='Adjudicate a submitted reaction step as the scientific Supervisor.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_review_species',
        class_name='DagReviewSpecies',
        tool_name='dag_review_species',
        dag_observe=False,
        supervisor_access='review_decision',
        summary='Adjudicate submitted species evidence as the scientific Supervisor.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_accept_mechanism',
        class_name='DagAcceptMechanism',
        tool_name='dag_accept_mechanism',
        dag_observe=False,
        supervisor_access='review_decision',
        summary='Record the scientific Supervisor verdict on a proposed mechanism.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_review_call',
        class_name='DagReviewCall',
        tool_name='dag_review_call',
        dag_observe=False,
        supervisor_access='review_decision',
        summary='Review an evidence-producing call against a submitted claim.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_review_evidence',
        class_name='DagReviewEvidence',
        tool_name='dag_review_evidence',
        dag_observe=False,
        supervisor_access='review_decision',
        summary='Record a scientific verdict on submitted evidence.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_view_evidence',
        class_name='DagViewEvidence',
        tool_name='dag_view_evidence',
        dag_observe=False,
        supervisor_access='evidence_read',
        summary='Read registered evidence and source references.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_set_coverage_contract',
        class_name='DagSetCoverageContract',
        tool_name='dag_set_coverage_contract',
        dag_observe=False,
        supervisor_access='review_decision',
        summary='Set the Supervisor coverage contract for a reviewed mechanism.',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_message_supervisor',
        class_name='DagMessageSupervisor',
        tool_name='dag_message_supervisor',
        dag_observe=False,
        # 无 supervisor_access：这是研究 Agent/Coordinator → Supervisor 的
        # 请求入口，工具本身硬拒 Supervisor 调用；督导的回复路径是
        # dag_review_* 裁决工具与运行结束报告。
        summary='Submit a research-side request to the scientific Supervisor.',
    ),
    ToolRegistration('cloudra.tools.Plantool.todo', 'TodoWrite', summary='Maintain a concrete task checklist.'),
    ToolRegistration(
        module='cloudra.tools.Searchtool.read',
        class_name='Read',
        tool_name='read',
        runtime_profiles=frozenset({'desktop', 'android'}),
        supervisor_access='evidence_read',
        summary='Read selected workspace file content or supported media.',
    ),
    ToolRegistration(
        module='cloudra.tools.Searchtool.search',
        class_name='Search',
        tool_name='search',
        runtime_profiles=frozenset({'desktop', 'android'}),
        summary='Search online sources for task-relevant information.',
    ),
    ToolRegistration(
        module='cloudra.tools.Skilltool.get_skill',
        class_name='GetSkill',
        tool_name='get_skill',
        runtime_profiles=frozenset({'desktop', 'android'}),
        dag_observe=False,
        supervisor_access='skill_read',
        summary='Load a named skill SOP or its reference document.',
    ),
    ToolRegistration(
        module='cloudra.tools.Stoptool.stop_tool',
        class_name='StopTool',
        tool_name='stop',
        runtime_profiles=frozenset({'desktop', 'android'}),
        invocation_direct_only=True,
        summary='End the current agent turn with its result; direct control.',
    ),
    ToolRegistration(
        module='cloudra.tools.Writetool.edit',
        class_name='Edit',
        tool_name='edit',
        runtime_profiles=frozenset({'desktop', 'android'}),
        supervisor_access='process_write',
        summary='Apply a precise edit to an existing workspace file.',
    ),
    ToolRegistration(
        module='cloudra.tools.Writetool.write',
        class_name='Write',
        tool_name='write',
        runtime_profiles=frozenset({'desktop', 'android'}),
        supervisor_access='process_write',
        summary='Write a workspace artifact with explicit overwrite handling.',
    ),
    ToolRegistration(
        module='cloudra.tools.Writetool.update_memory',
        class_name='UpdateMemory',
        tool_name='update_memory',
        runtime_profiles=frozenset({'desktop', 'android'}),
        summary='Update the project memory through its authorized workflow.',
    ),
)
