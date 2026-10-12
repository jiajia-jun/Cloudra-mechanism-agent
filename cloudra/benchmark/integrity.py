"""Layer 1 — delivery integrity: forensic sandbox scan and evidence binding.

The scorer never trusts the agent's self-declared mechanism. It recursively
walks the agent's sandbox, extracts the delivered `mechanism_graph.json`, and
binds each graph element to concrete computational evidence files found on
disk. Binding uses the `smiles:` annotation line that the delivery contract
(the task query) requires in every evidence file — the annotation propagates
into QM logs because Gaussian/ORCA echo their input title/comment lines.
The report carries graph parseability plus per-node binding quality (no
pass/fail verdict — Layer 1 不再判过不过，只产出事实): fingerprint/hash-level
matches give quality 1.0, protonation/charge-state-only variants give partial
credit (the rubric's `protonation_partial_quality`). runner 把逐节点质量图
并入图分（graph_similarity 的证据加权代价），零证据整体倒扣也在 runner。
`accessible=false` 的节点是"允许方法下不可达"的显式声明，不参与绑定、
不产出 NodeBinding。

Pure filesystem + parsing; no LLM, no DB.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

from pydantic import ConfigDict, model_validator

from cloudra.benchmark.graph_similarity import (
    GedConfig,
    protonation_variant_quality,
    species_substitution_cost,
)
from cloudra.benchmark.schema import (
    GoldMechanismGraph,
    IntegrityRubric,
    MechanismEdge,
    MechanismNode,
    NodeRole,
)
from cloudra.tools.core.irc_evidence import normal_log

# 交付侧识别的常规图论 type 别名 → 系统 NodeRole。未知 type 不做猜测映射：
# 留原样让校验 fail-loud（无法识别的声明不该被静默吞成另一个角色）。
_NODE_TYPE_ALIASES = {
    "reactant": NodeRole.REACTANT.value,
    "product": NodeRole.PRODUCT.value,
    "intermediate": NodeRole.INTERMEDIATE.value,
    "transition_state": NodeRole.TRANSITION_STATE.value,
    "ts": NodeRole.TRANSITION_STATE.value,
}


class _DeliveredNode(MechanismNode):
    """交付侧节点：Postel 宽松加载（GH #29）。

    常规图节点字段（``type``、字符串 ``smiles``）在字段校验前规范化到本系统
    的 schema（``role``、``smiles: list[str]``）；多写的键忽略。组分列表形态
    （``["C=O","CN"]``）由 schema 校验器折叠成点连接络合物单条，无需在此
    特判。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _normalize_delivery_fields(cls, data):
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # role 缺失，或 role 是自由文本（不是合法 NodeRole 枚举值）而 type 能映射
        # 时，以 type 的映射值为 role；自由文本并进 label，不丢信息。role 本身
        # 是合法枚举值时不动；type 也映射不了则留原样，让校验 fail-loud。
        alias = _NODE_TYPE_ALIASES.get(str(data.get("type") or "").strip().lower())
        if alias is not None and data.get("role") not in {r.value for r in NodeRole}:
            free_text = str(data["role"]).strip() if data.get("role") is not None else ""
            if free_text:
                label = str(data.get("label") or "").strip()
                data["label"] = f"{label} | {free_text}" if label else free_text
            data["role"] = alias
        smiles = data.get("smiles")
        if isinstance(smiles, str):
            data["smiles"] = [smiles]
        elif smiles is None:
            data["smiles"] = []
        return data


class _DeliveredEdge(MechanismEdge):
    """交付侧边：忽略多写的键，id 可缺省（加载时补）。

    Postel 规范化：常规图论字段 ``source``/``target`` 映射到 ``from``/``to``。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_delivery_fields(cls, data):
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "from" not in data and "source" in data:
            data["from"] = data["source"]
        if "to" not in data and "target" in data:
            data["to"] = data["target"]
        return data

# file extensions we treat as computational evidence worth parsing for SMILES
_EVIDENCE_SUFFIXES = {".gjf", ".com", ".inp", ".xyz", ".log", ".out", ".sdf", ".mol", ".json"}

# 超过该大小的文件只做类型分类、不整读扫 SMILES，也不进 Layer 2 的帧解析
# （两层共享同一上限：超大文件在 Layer 1 没贡献绑定，cclib 整读只会拖住评分器）
MAX_SCAN_BYTES = 20 * 1024 * 1024

# `smiles:` 注释行是交付协议的一部分（query 明确要求证据文件携带）。
# 容忍 JSON/YAML 引号与注释前缀："smiles": "X"、smiles: 'X'、# smiles: X。
# 注意不能把 [ ] 排除在捕获集外——离子/ bracket SMILES（[F-]、[OH3+]）依赖它们。
@dataclass
class EvidenceFile:
    path: str
    smiles_found: list[str] = field(default_factory=list)
    kind: str = ""  # 'gaussian'|'orca'|'xyz'|'json'|'unknown'
    size: int = 0   # 字节数；Layer 2 据此跳过超过 MAX_SCAN_BYTES 的文件


@dataclass
class NodeBinding:
    node_id: str
    bound_files: list[str] = field(default_factory=list)
    matched: bool = False
    # 绑定质量：1.0 = 指纹/哈希级全绑；(0, 1) = 仅质子化/电荷态不同的骨架
    # 匹配（partial credit，扣分不判零）；0 = 未绑定。
    quality: float = 0.0


@dataclass
class IntegrityReport:
    graph_found: bool
    graph_parseable: bool
    graph_path: Optional[str] = None
    delivered_graph: Optional[GoldMechanismGraph] = None
    evidence_files: list[EvidenceFile] = field(default_factory=list)
    # 只含参与绑定评估的节点（accessible=true；TS 节点经边间接绑定）——
    # accessible=false 的节点不要求证据，不在此列
    node_bindings: list[NodeBinding] = field(default_factory=list)
    # 平均绑定质量（含 partial credit；分母只含参与绑定的节点）
    binding_quality: float = 1.0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# sandbox scan
# ---------------------------------------------------------------------------


def find_graph_json(sandbox: Path) -> Optional[Path]:
    """Locate the agent-maintained mechanism_graph.json at the sandbox root,
    falling back to any *.json that parses to a mechanism graph shape."""
    direct = sandbox / "mechanism_graph.json"
    if direct.is_file():
        return direct
    for p in sorted(sandbox.rglob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(data, dict) and "nodes" in data and "edges" in data:
            return p
    return None


def load_delivered_graph(path: Path) -> Optional[GoldMechanismGraph]:
    """Parse a delivered graph JSON into GoldMechanismGraph.

    交付侧宽松加载（Postel）：agent 多写的键（energy/metadata 等）忽略、
    边缺 id 自动补；gold 侧仍由 strict schema 约束。端点引用完整性由
    GoldMechanismGraph 的 validator 把关：悬空 from/to/via → 校验失败、
    返回 None（不可解析），不再静默造幽灵节点进图比较。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        nodes = [_DeliveredNode.model_validate(n) for n in data.get("nodes", [])]
        edges = [_DeliveredEdge.model_validate(e) for e in data.get("edges", [])]
        return GoldMechanismGraph(
            nodes=[MechanismNode(**n.model_dump()) for n in nodes],
            edges=[
                MechanismEdge(**(e.model_dump() | {"id": e.id or f"e{i}"}))
                for i, e in enumerate(edges)
            ],
        )
    except Exception:
        return None


def _smiles_in_json(obj) -> list[str]:
    """结构化收集 JSON 里 smiles 键的值（含数组）。"""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() == "smiles":
                if isinstance(v, str):
                    found.append(v)
                elif isinstance(v, list):
                    found.extend(s for s in v if isinstance(s, str))
            else:
                found.extend(_smiles_in_json(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_smiles_in_json(item))
    return found


def _smiles_in_text(text: str) -> list[str]:
    # Structured files are read as JSON; annotation parsing is for raw text.
    try:
        data = json.loads(text)
    except Exception:
        data = None
    if isinstance(data, (dict, list)):
        return _smiles_in_json(data)
    found = []
    for line in text.splitlines():
        offset = 0
        while (index := line.lower().find('smiles', offset)) >= 0:
            offset = index + len('smiles')
            if index and (line[index - 1].isalnum() or line[index - 1] == '_'):
                continue
            suffix = line[offset:].lstrip("'\" \t")
            if not suffix or suffix[0] not in ':=':
                continue
            value = suffix[1:].lstrip().lstrip("'\"")
            end = next((i for i, char in enumerate(value) if char.isspace() or char in ",;\"'}"), len(value))
            if end:
                found.append(value[:end])
    return found


def scan_evidence_files(sandbox: Path, exclude: Optional[Path] = None) -> list[EvidenceFile]:
    files: list[EvidenceFile] = []
    for p in sorted(sandbox.rglob("*")):
        if not p.is_file():
            continue
        try:
            p.resolve().relative_to(sandbox.resolve())
        except ValueError:
            continue
        if p.suffix.lower() not in _EVIDENCE_SUFFIXES:
            continue
        if p.name == "mechanism_graph.json":
            continue
        # 兜底发现加载的交付图（如 sub/my_graph.json）同样不得计入证据——
        # 否则图文件内嵌的 SMILES 会自绑，零计算证据也能过 Layer 1
        if exclude is not None and p == exclude:
            continue
        kind = _classify(p)
        try:
            size = p.stat().st_size
            if size > MAX_SCAN_BYTES:
                text = ""  # 超大日志不整读；保留分类结果，SMILES 扫描跳过
            else:
                text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # 机理图形状的 JSON（顶层 nodes+edges）一律不是证据：交付图的多份改名
        # 拷贝若算证据，其内嵌 SMILES 会让图节点绑定到自己，零计算证据过 Layer 1
        if p.suffix.lower() == ".json" and text:
            try:
                data = json.loads(text)
            except Exception:
                data = None
            if isinstance(data, dict) and "nodes" in data and "edges" in data:
                continue
        files.append(EvidenceFile(
            path=str(p.relative_to(sandbox)),
            smiles_found=_smiles_in_text(text),
            kind=kind,
            size=size,
        ))
    return files


def _classify(p: Path) -> str:
    s = p.suffix.lower()
    if s in (".gjf", ".com"):
        return "gaussian"
    if s == ".inp":
        return "orca"
    if s == ".xyz":
        return "xyz"
    if s == ".json":
        return "json"
    if s in (".log", ".out"):
        # sniff engine by content header（只读头部，不整读）
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(2000)
        except Exception:
            return "unknown"
        if "Entering Gaussian System" in head or "Gaussian" in head:
            return "gaussian"
        if "O   R   C   A" in head or "ORCA" in head:
            return "orca"
        return "log"
    return "unknown"


# ---------------------------------------------------------------------------
# binding
# ---------------------------------------------------------------------------


def _species_file_qualities(
    species_smiles: str,
    files: list[EvidenceFile],
    cfg: GedConfig,
    match_threshold: float,
    partial_quality: float,
) -> tuple[float, list[str]]:
    """逐证据文件评估该物种（一条 SMILES；络合物为点连接单条）的绑定质量，
    返回 (best_quality, [path, ...])。

    三档：指纹/哈希 cost ≤ match_threshold → 1.0；否则查质子化骨架——仅电荷
    态/质子化形式不同 → `protonation_variant_quality`（质量 = 1-(1-partial)·w，
    w = 指纹相对误差 1-Tanimoto：指纹退化的小分子离子对扣满到 partial_quality，
    大分子小扰动扣得少）；其余 → 0（不绑）。指纹对单重原子物种会退化
    （O vs [OH-] 的 Tanimoto=0），所以质子化通道必须在指纹之后独立兜底。"""
    best = 0.0
    paths: list[str] = []
    for f in files:
        if not f.smiles_found:
            continue
        q = 0.0
        for fs in f.smiles_found:
            # A similar fingerprint cannot replace missing molecular components.
            # Separate component evidence is handled by _component_union_coverage.
            if len(fs.split(".")) != len(species_smiles.split(".")):
                continue
            if species_substitution_cost([species_smiles], [fs], cfg) <= match_threshold:
                q = 1.0
                break
            if partial_quality > 0.0:
                vq = protonation_variant_quality(species_smiles, fs, cfg, partial_quality)
                q = max(q, vq)
        if q > 0.0:
            paths.append(f.path)
            best = max(best, q)
    return best, paths


def _component_union_coverage(
    species_smiles: str,
    files: list[EvidenceFile],
    cfg: GedConfig,
    match_threshold: float,
    partial_quality: float,
) -> tuple[float, list[str]]:
    """逐组分联合覆盖兜底（用户裁决：络合物优化不干净时允许拆开交付）。

    仅在整络合物标注绑不上时启用：把络合物 SMILES 按 "." 拆成单组分，每个
    组分走与整绑相同的结构比对（指纹/哈希 + protonation variant，不走字符串
    相等）——每个组分都至少被一个证据文件标注则联合覆盖成立，返回
    (最弱组分质量, 覆盖文件并集)；任一组分无覆盖返回 (0.0, [])。单组分物种
    无此通道（与整绑同义）。"""
    components = species_smiles.split(".")
    if len(components) <= 1:
        return 0.0, []
    quality = 1.0
    paths: list[str] = []
    for comp in components:
        q, qpaths = _species_file_qualities(
            comp, files, cfg, match_threshold, partial_quality
        )
        if not qpaths:
            return 0.0, []
        quality = min(quality, q)
        paths.extend(qpaths)
    return quality, sorted(set(paths))


def bind_graph_to_evidence(
    graph: GoldMechanismGraph,
    files: list[EvidenceFile],
    cfg: Optional[GedConfig] = None,
    match_threshold: float = 0.2,
    partial_quality: float = 0.7,
    *,
    sandbox: Path,
) -> list[NodeBinding]:
    """Bind each accessible non-TS node to evidence files whose parsed SMILES
    match the node's claimed SMILES. A node's SMILES list holds whole species:
    a multi-molecule complex is ONE dot-joined complex SMILES (``C=O.CN``) —
    the schema folds component lists into that form at parse time
    (``MechanismNode._fold_complex_components``). Binding is two-layered:

    1. 整络合物优先：evidence ``smiles:`` annotations are matched against the
       whole dot-joined complex (the delivery contract's primary form);
    2. 逐组分联合覆盖兜底（用户裁决：络合物在允许方法下优化不干净时允许拆开
       交付）：整络合物绑不上时拆成单组分，每个组分都至少被一个证据文件标注
       （同一结构比对/protonation 通道）则该物种也算覆盖——图拓扑不受影响，
       节点仍是单个络合物。

    The node binds when every listed species is matched (either layer) by at
    least one evidence file. Binding is graded: fingerprint/hash-level matches
    give quality 1.0; protonation/charge-state-only variants give
    `partial_quality` (the node's quality is its weakest species — 兜底通道下
    即最弱组分). TS nodes carry no SMILES and are bound indirectly via their
    edge's endpoints: a TS counts as evidenced only when at least one edge
    routes through it (`via`) and both endpoint species of that edge are
    themselves bound to evidence; its quality inherits the weaker endpoint.

    `accessible=false` 的节点（含 TS）是"允许方法下不可达"的显式声明：不参与
    绑定、不产出 NodeBinding；via 边任一端点不可达时该 TS 随之绑不上
    （端点不在绑定集合里）。"""
    cfg = cfg or GedConfig()
    sandbox = Path(sandbox)
    available = files
    from cloudra.dag.file_science import _geometry_species
    verified = []
    for evidence in files:
        identities = []
        if evidence.size <= MAX_SCAN_BYTES and (evidence.kind == 'xyz' or normal_log(sandbox / evidence.path, max_scan_bytes=MAX_SCAN_BYTES)):
            for identity in evidence.smiles_found:
                try:
                    if _geometry_species(str(sandbox / evidence.path), identity):
                        identities.append(identity)
                except (ValueError, RuntimeError):
                    continue
        verified.append(replace(evidence, smiles_found=identities))
    files = verified
    bindings: list[NodeBinding] = []
    by_id: dict[str, NodeBinding] = {}
    ts_ids = {n.id for n in graph.nodes if n.role == NodeRole.TRANSITION_STATE}

    # pass 1: accessible 物种节点（TS 节点第二趟按边端点判定）
    for node in graph.nodes:
        if not node.accessible:
            continue  # 不可达声明不要求证据
        nb = NodeBinding(node_id=node.id)
        by_id[node.id] = nb
        bindings.append(nb)
        if node.id in ts_ids:
            continue
        if 'evidence_log' in node.properties:
            raw = node.properties['evidence_log']
            try:
                path = (sandbox / raw).resolve() if isinstance(raw, str) else None
                relative = str(path.relative_to(sandbox.resolve())) if path is not None else None
                evidence = next((item for item in available if item.path == relative
                                 and item.kind in {'gaussian', 'orca'} and item.size <= MAX_SCAN_BYTES), None)
                if evidence and node.smiles and normal_log(path, max_scan_bytes=MAX_SCAN_BYTES):
                    identities = next(item.smiles_found for item in files if item.path == relative)
                    identities = list(identities)
                    identities.extend(identity for identity in node.smiles if _geometry_species(str(path), identity))
                    candidate = replace(evidence, smiles_found=list(dict.fromkeys(identities)))
                    qualities = [_species_file_qualities(identity, [candidate], cfg, match_threshold, partial_quality)[0]
                                 for identity in node.smiles]
                    if all(quality > 0 for quality in qualities):
                        nb.bound_files, nb.matched, nb.quality = [relative], True, min(qualities)
            except (ValueError, RuntimeError, OSError):
                pass
            continue  # A bad explicit reference must never select other history.
        if not node.smiles:
            # 物种节点不带 SMILES = 只有声明没有可取证内容，不予绑定；
            # 否则 agent 把 SMILES 全留空即可零证据通过本层。
            continue
        all_species_matched = True
        node_quality = 1.0
        for species_smiles in node.smiles:
            q, qpaths = _species_file_qualities(
                species_smiles, files, cfg, match_threshold, partial_quality
            )
            if not qpaths:
                # 整络合物标注绑不上 → 逐组分联合覆盖兜底（两层语义见 docstring）
                q, qpaths = _component_union_coverage(
                    species_smiles, files, cfg, match_threshold, partial_quality
                )
            if qpaths:
                nb.bound_files.extend(qpaths)
            else:
                all_species_matched = False
            node_quality = min(node_quality, q)
        nb.bound_files = sorted(set(nb.bound_files))
        nb.matched = all_species_matched and bool(nb.bound_files)
        nb.quality = node_quality if nb.matched else 0.0

    # pass 2: TS nodes — 仅当某条边经由它且两端物种都已绑定证据；
    # accessible=false 的 TS 不在 by_id 里，自然跳过
    for ts_id in ts_ids:
        nb = by_id.get(ts_id)
        if nb is None:
            continue
        node = next(n for n in graph.nodes if n.id == ts_id)
        if 'evidence_log' in node.properties:
            raw = node.properties['evidence_log']
            try:
                path = (sandbox / raw).resolve() if isinstance(raw, str) else None
                relative = str(path.relative_to(sandbox.resolve())) if path is not None else None
                if any(f.path == relative and f.kind in {'gaussian', 'orca'} and f.size <= MAX_SCAN_BYTES for f in available) and normal_log(path, max_scan_bytes=MAX_SCAN_BYTES):
                    endpoint_quality = max((min(by_id[e.from_node].quality, by_id[e.to_node].quality)
                                            for e in graph.edges if e.via == ts_id and e.from_node in by_id and e.to_node in by_id), default=0.0)
                    nb.bound_files, nb.matched, nb.quality = [relative], True, endpoint_quality
            except (ValueError, OSError):
                pass
            continue
        for e in graph.edges:
            if e.via != ts_id:
                continue
            a, b = by_id.get(e.from_node), by_id.get(e.to_node)
            if a is not None and b is not None and a.matched and b.matched:
                nb.matched = True
                nb.quality = min(a.quality, b.quality)
                from cloudra.benchmark.barrier_evidence import (
                    _declared_node_energy_hartree,
                    _identify_by_declared_energy,
                )
                declared = _declared_node_energy_hartree(node)
                candidates = [f.path for f in available if f.kind in {'gaussian', 'orca'}
                              and f.size <= MAX_SCAN_BYTES]
                selected = _identify_by_declared_energy(sandbox, candidates, declared) if declared is not None else None
                nb.bound_files = [selected] if selected else []
                break
    return bindings


# ---------------------------------------------------------------------------
# public entry
# ---------------------------------------------------------------------------


def audit_integrity(
    sandbox: Path,
    rubric: Optional[IntegrityRubric] = None,
    cfg: Optional[GedConfig] = None,
) -> IntegrityReport:
    """审计入口：只产出报告（图可解析性 + 逐节点绑定质量），不判通过与否。
    零证据倒扣与证据加权扣分都在 runner/graph_similarity 侧按报告事实计算。"""
    rubric = rubric or IntegrityRubric()
    report = IntegrityReport(graph_found=False, graph_parseable=False)

    graph_path = find_graph_json(sandbox)
    if graph_path is None:
        report.notes.append("mechanism_graph.json not found in sandbox")
        return report
    report.graph_found = True
    report.graph_path = str(graph_path.relative_to(sandbox))

    graph = load_delivered_graph(graph_path)
    if graph is None:
        report.notes.append("mechanism_graph.json present but not parseable")
        return report
    report.graph_parseable = True
    report.delivered_graph = graph

    # 兜底发现的交付图文件自身排除出证据扫描：其内嵌 SMILES 不构成计算证据
    report.evidence_files = scan_evidence_files(sandbox, exclude=graph_path)
    report.node_bindings = bind_graph_to_evidence(
        graph,
        report.evidence_files,
        cfg,
        match_threshold=rubric.match_threshold,
        partial_quality=rubric.protonation_partial_quality,
        sandbox=sandbox,
    )

    report.binding_quality = (
        sum(b.quality for b in report.node_bindings) / len(report.node_bindings)
    ) if report.node_bindings else 0.0
    bound = [b for b in report.node_bindings if b.matched]
    partial = [b.node_id for b in bound if b.quality < 1.0]
    if partial:
        report.notes.append(
            f"partial-credit binds (protonation/charge-state variants): {partial}"
        )
    unbound = [b.node_id for b in report.node_bindings if not b.matched]
    if unbound:
        report.notes.append(f"unbound nodes (no matching evidence file): {unbound}")
    return report
