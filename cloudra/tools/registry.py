"""Explicit built-in tool manifest.

Keep this module dependency-free: :mod:`cloudra.core.agent` imports
``cloudra.tools`` while several tool implementations import ``cloudra.core.agent``.
The registry therefore stores import paths instead of importing tool classes at
module import time.

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
    # D5：工具结束是否入 CallReview 收件箱（并唤醒 Supervisor 复核）。
    dag_review: bool = False
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


TOOL_REGISTRY: tuple[ToolRegistration, ...] = (
    ToolRegistration(
        module='cloudra.tools.Bashtool.bash',
        class_name='Bash',
        tool_name='bash',
        dag_compute_predicate='cloudra.tools.core.bash_habit_guard:is_substantive_bash_command',
    ),
    ToolRegistration(
        module='cloudra.tools.Browsertool.browser',
        class_name='HeadlessBrowser',
        tool_name='browser',
    ),
    ToolRegistration(
        module='cloudra.tools.Browsertool.web_fetch',
        class_name='WebFetcher',
        tool_name='web_fetch',
        runtime_profiles=frozenset({'desktop', 'android'}),
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.conformer_search',
        class_name='ConformerSearch',
        tool_name='conformer_search',
        dag_compute_entry=True,
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.electronic_analysis',
        class_name='ElectronicAnalysis',
        tool_name='electronic_analysis',
        dag_compute_entry=True,
    ),
    ToolRegistration('cloudra.tools.Chemtool.format_converter', 'FormatConverter'),
    ToolRegistration(
        module='cloudra.tools.Chemtool.qm_input_writer',
        class_name='QmInputWriter',
        tool_name='qm_input_writer',
        dag_compute_entry=True,
    ),
    ToolRegistration('cloudra.tools.Chemtool.image_to_smiles', 'ImageToSmiles'),
    ToolRegistration(
        module='cloudra.tools.Chemtool.cdxml_to_graph',
        class_name='CdxmlToGraph',
        tool_name='cdxml_to_graph',
    ),
    ToolRegistration('cloudra.tools.Chemtool.internal_coordinates', 'InternalCoordinates'),
    ToolRegistration(
        module='cloudra.tools.Chemtool.ir_processor',
        class_name='IRProcessor',
        tool_name='ir_processor',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.log_parser',
        class_name='LogParser',
        tool_name='log_parser',
        evidence_deriver='cloudra.tools.Chemtool.log_parser:derive_delivery_changes',
        dag_fact_adapter='cloudra.dag.fact_adapters:log_parser_facts',
        dag_review=True,
        supervisor_access='evidence_read',
    ),
    ToolRegistration('cloudra.tools.Chemtool.molecule_drawer', 'MoleculeDrawer'),
    ToolRegistration('cloudra.tools.Chemtool.name_to_structure', 'NameToStructure'),
    ToolRegistration(
        module='cloudra.tools.Chemtool.nmr_processor',
        class_name='NMRProcessor',
        tool_name='nmr_processor',
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.pymol_render',
        class_name='PymolRender',
        tool_name='pymol_render',
        visual=True,
    ),
    ToolRegistration('cloudra.tools.Chemtool.query_compute_job', 'QueryComputeJob'),
    ToolRegistration('cloudra.tools.Chemtool.query_compute_queue', 'QueryComputeQueue'),
    ToolRegistration(
        module='cloudra.tools.Chemtool.mark_compute_job_failed',
        class_name='MarkComputeJobFailed',
        tool_name='mark_compute_job_failed',
        dag_observe=False,
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.reaction_mapping',
        class_name='ReactionMapping',
        tool_name='reaction_mapping',
        evidence_deriver='cloudra.tools.Chemtool.reaction_mapping:derive_delivery_changes',
        dag_fact_adapter='cloudra.dag.fact_adapters:reaction_mapping_facts',
        dag_review=True,
        supervisor_access='evidence_read',
    ),
    ToolRegistration('cloudra.tools.Chemtool.smiles_to_mol', 'SmilesToMol'),
    ToolRegistration(
        module='cloudra.tools.Chemtool.submit_compute_job',
        class_name='SubmitComputeJob',
        tool_name='submit_compute_job',
        dag_compute_entry=True,
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.thermo_analysis',
        class_name='ThermoAnalysis',
        tool_name='thermo_analysis',
        evidence_deriver='cloudra.tools.Chemtool.thermo_analysis:derive_delivery_changes',
        dag_review=True,
    ),
    ToolRegistration(
        module='cloudra.tools.Chemtool.ts_guess',
        class_name='TsGuess',
        tool_name='ts_guess',
        evidence_deriver='cloudra.tools.Chemtool.ts_guess:derive_delivery_changes',
        dag_fact_adapter='cloudra.dag.fact_adapters:ts_guess_facts',
        dag_review=True,
        dag_compute_predicate='cloudra.tools.Chemtool.ts_guess:is_compute_entry_call',
    ),
    ToolRegistration('cloudra.tools.Interactool.ask_user', 'AskUser'),
    ToolRegistration('cloudra.tools.Interactool.email_reader', 'EmailReader'),
    ToolRegistration('cloudra.tools.Interactool.email_sender', 'EmailSender'),
    ToolRegistration(
        module='cloudra.tools.Managetool.agent_hub',
        class_name='AgentHub',
        tool_name='agent_hub',
        runtime_profiles=frozenset({'desktop', 'android'}),
        supervisor_access='hub',
    ),
    ToolRegistration(
        module='cloudra.tools.Managetool.get_subagent_report',
        class_name='GetSubAgentReport',
        tool_name='get_subagent_report',
        runtime_profiles=frozenset({'desktop', 'android'}),
    ),
    ToolRegistration(
        module='cloudra.tools.Managetool.schedule',
        class_name='Schedule',
        tool_name='schedule',
        runtime_profiles=frozenset({'desktop', 'android'}),
    ),
    ToolRegistration(
        module='cloudra.tools.Managetool.subagent_launcher',
        class_name='SubAgentLauncher',
        tool_name='subagent_launcher',
        runtime_profiles=frozenset({'desktop', 'android'}),
    ),
    ToolRegistration(
        module='cloudra.tools.Managetool.subagent_swarm',
        class_name='SubAgentSwarm',
        tool_name='subagent_swarm',
    ),
    ToolRegistration('cloudra.tools.Plantool.goal', 'GoalSet'),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_view',
        class_name='DagView',
        tool_name='dag_view',
        dag_observe=False,
        supervisor_access='evidence_read',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_delivery_report',
        class_name='DagDeliveryReport',
        tool_name='dag_delivery_report',
        dag_observe=False,
        supervisor_access='evidence_read',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_add_species',
        class_name='DagAddSpecies',
        tool_name='dag_add_species',
        dag_observe=False,
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_add_step',
        class_name='DagAddStep',
        tool_name='dag_add_step',
        dag_observe=False,
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_update_delivery_element',
        class_name='DagUpdateDeliveryElement',
        tool_name='dag_update_delivery_element',
        dag_observe=False,
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_remove_edge',
        class_name='DagRemoveEdge',
        tool_name='dag_remove_edge',
        dag_observe=False,
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_bind_evidence',
        class_name='DagBindEvidence',
        tool_name='dag_bind_evidence',
        dag_observe=False,
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_propose_mechanism',
        class_name='DagProposeMechanism',
        tool_name='dag_propose_mechanism',
        dag_observe=False,
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_accept_mechanism',
        class_name='DagAcceptMechanism',
        tool_name='dag_accept_mechanism',
        dag_observe=False,
        supervisor_access='review_decision',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_review_call',
        class_name='DagReviewCall',
        tool_name='dag_review_call',
        dag_observe=False,
        supervisor_access='review_decision',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_review_evidence',
        class_name='DagReviewEvidence',
        tool_name='dag_review_evidence',
        dag_observe=False,
        supervisor_access='review_decision',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_view_evidence',
        class_name='DagViewEvidence',
        tool_name='dag_view_evidence',
        dag_observe=False,
        supervisor_access='evidence_read',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_set_coverage_contract',
        class_name='DagSetCoverageContract',
        tool_name='dag_set_coverage_contract',
        dag_observe=False,
        supervisor_access='review_decision',
    ),
    ToolRegistration(
        module='cloudra.tools.Plantool.dag_tools.dag_message_supervisor',
        class_name='DagMessageSupervisor',
        tool_name='dag_message_supervisor',
        dag_observe=False,
        supervisor_access='review_decision',
    ),
    ToolRegistration('cloudra.tools.Plantool.todo', 'TodoWrite'),
    ToolRegistration('cloudra.tools.Plantool.todo_read', 'TodoRead'),
    ToolRegistration(
        module='cloudra.tools.Searchtool.read',
        class_name='Read',
        tool_name='read',
        runtime_profiles=frozenset({'desktop', 'android'}),
        supervisor_access='evidence_read',
    ),
    ToolRegistration(
        module='cloudra.tools.Searchtool.search',
        class_name='Search',
        tool_name='search',
        runtime_profiles=frozenset({'desktop', 'android'}),
    ),
    ToolRegistration(
        module='cloudra.tools.Skilltool.get_skill',
        class_name='GetSkill',
        tool_name='get_skill',
        runtime_profiles=frozenset({'desktop', 'android'}),
        dag_observe=False,
        supervisor_access='skill_read',
    ),
    ToolRegistration(
        module='cloudra.tools.Stoptool.stop_tool',
        class_name='StopTool',
        tool_name='stop',
        runtime_profiles=frozenset({'desktop', 'android'}),
    ),
    ToolRegistration(
        module='cloudra.tools.Writetool.edit',
        class_name='Edit',
        tool_name='edit',
        runtime_profiles=frozenset({'desktop', 'android'}),
    ),
    ToolRegistration(
        module='cloudra.tools.Writetool.write',
        class_name='Write',
        tool_name='write',
        runtime_profiles=frozenset({'desktop', 'android'}),
    ),
    ToolRegistration(
        module='cloudra.tools.Writetool.update_memory',
        class_name='UpdateMemory',
        tool_name='update_memory',
        runtime_profiles=frozenset({'desktop', 'android'}),
    ),
)
