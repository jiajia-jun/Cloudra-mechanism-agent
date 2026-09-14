"""Benchmark module: benchmark task schema, task generators, and the scoring pipeline.

Public surface:
- `schema`: TaskSpec / GoldSpec / RubricSpec / mechanism-graph models.
- `gen_easy_tasks`: generator turning ideapool/reaction_candidates/easy.md
  into ideapool/tasks/easy/*.json.
- `graph_similarity`: chemical-parameterized GED between two mechanism graphs.
- `integrity`: sandbox forensic scan + evidence binding (Layer 1).
- `selfconsistency`: physical self-consistency checks (Layer 2).
- `accuracy`: Gaussian-tolerance barrier scoring (Layer 3).
- `method_policy`: method-whitelist interception.
- `runner`: independent benchmark runner with its own data directory.
"""

from cloudra.benchmark.schema import (  # noqa: F401
    AccuracyRubric,
    BondChangeSet,
    ExpectedOutcome,
    GoldMechanismGraph,
    GoldSpec,
    GraphSimilarityRubric,
    ImpossibleCaseRubric,
    IntegrityRubric,
    MechanismEdge,
    MechanismNode,
    MethodPolicy,
    NodeRole,
    PromptSpec,
    RubricSpec,
    SelfConsistencyRubric,
    SystemSpec,
    TaskSpec,
    Tier,
)
