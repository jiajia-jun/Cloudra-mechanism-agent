"""mechanism_predict：FlowER 机理假设生成器的外部进程封装。

形态照 crest_runner 先例：FlowER（torch 2.4 大模型）跑在独立 conda env
``flower`` 里，由 ``_flower_beam_driver.py`` 驱动；Cloudra 主进程从不 import
torch——子进程产物只有 network.json（清洁 SMILES 节点 + 带概率的基元步边）。

定位纪律：**ML 输出是假设，不是证据**。本工具不在 registry 里声明任何
dag_evidence_producer / dag_compute_entry 语义；生成的中间体/路径必须经
xtb/DFT 证据链（submit_compute_job）验证后才能进入机理主张。

开关：config ``flower.enabled`` 默认 false。关闭时 wire 投影隐藏本工具
（capabilities.config_disabled_tools），本文件 tool_call 再硬失败一次
（双保险，与 dag 工具"投影隐藏 + 执行层硬拒"的模式一致）。
"""

import asyncio
import json
import os
import subprocess
from typing import Any, Optional

from pydantic import Field

from cloudra.base.session_class import Session
from cloudra.base.tools_class import Tool, input_schema, output_schema
from cloudra.infra.config import get_config
from cloudra.persistence.fs_utils import atomic_write_text
from cloudra.persistence.workspace import resolve_tool_path
from cloudra.tools.core.crest_runner import _terminate_process_group

try:
    from rdkit import Chem
    _RDKIT_AVAILABLE = True
except Exception:
    Chem = None
    _RDKIT_AVAILABLE = False

RUNS_DIR_NAME = "flower_runs"
DRIVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_flower_beam_driver.py")
MAX_MESSAGE_PATHWAYS = 5
MAX_RETURNED_PATHWAYS = 10
PATH_EXPLORE_CAP = 5000

# stderr 失败分类的精确 token（无正则；未命中落 unknown_failure 并保留原文尾巴）
_TOKEN_MODULE_NOT_FOUND = "ModuleNotFoundError"
_TOKEN_OUT_OF_MEMORY = "OutOfMemoryError"
_TOKEN_NO_PICKLE = "no result_chunk_"

description = (
    "ML reaction-mechanism hypothesis generator (FlowER, electron flow matching, Nature 2025). "
    "Give reactant SMILES and it beam-searches a network of elementary steps in an external conda "
    "environment, returning ranked mechanistic pathways with per-step probabilities (electron-flow "
    "likelihoods, mass-conserving by construction). Optionally checks whether target products are reached. "
    "IMPORTANT: the output is a machine-learning HYPOTHESIS, never computational evidence — proposed "
    "intermediates and pathways must be verified with the xtb/DFT pipeline (submit_compute_job) before "
    "supporting any mechanistic claim. "
    "Use for: proposing candidate elementary steps/intermediates for organic polar reactions before "
    "committing QM resources. "
    "Do not use for: radical, surface, or organometallic mechanisms (outside its USPTO-FULL/RMechDB/"
    "PMechDB training distribution), or as a substitute for QM verification. "
    "Runs on CPU: expect minutes for small molecules; keep max_depth/sample_size modest."
)


class MechanismPredict_input_schema(input_schema):
    reactants: str = Field(
        description="Dot-separated reactant SMILES for the reacting complex "
                    "(e.g. 'CC(=O)CC(=O)C(F)(F)F.NNc1cccc(Br)c1'). Plain SMILES, no atom maps needed."
    )
    products: str = Field(
        default="",
        description="Optional target product SMILES; separate multiple targets with '|'. "
                    "Only used to annotate whether the search reaches them (stereo is ignored)."
    )
    beam_size: int = Field(
        default=5, ge=1, le=20,
        description="Beam width: how many frontier candidates are expanded per depth level. "
                    "Larger = more comprehensive but slower."
    )
    nbest: int = Field(default=3, ge=1, le=10, description="Top-k outcomes kept per expansion.")
    max_depth: int = Field(
        default=10, ge=1, le=20,
        description="Maximum elementary steps from reactants. CPU default is 10 (official default is 15)."
    )
    sample_size: int = Field(
        default=16, ge=1, le=64,
        description="Stochastic samples per expansion; edge probability = count/sample_size. "
                    "Official evaluation uses 64."
    )
    timeout_s: int = Field(default=1800, ge=60, le=7200, description="Subprocess timeout (seconds).")
    output_dir: Optional[str] = Field(
        default=None,
        description="Run directories go under <output_dir>/flower_runs/. Default: ./mechanism_output/. "
                    "Relative paths resolve against the agent process's current working directory."
    )


class MechanismPredict_output_schema(output_schema):
    is_success: bool = Field(description="Whether the search completed and produced a parsed network")
    message: str = Field(default="", description="Status summary (top pathways) or error message")
    pathways: list[dict] = Field(
        default_factory=list,
        description="Top pathways: ordered elementary steps "
                    "[{reactant, product, probability}] + cumulative_probability + reaches_target"
    )
    num_species: int = Field(default=0, description="Unique species nodes in the reaction network")
    num_steps: int = Field(default=0, description="Unique elementary-step edges in the network")
    network_json: str = Field(default="", description="Path to the full mechanism network JSON")
    run_dir: str = Field(default="", description="Persistent run directory (logs, inputs, pickle)")


def enumerate_pathways(
    network: dict,
    max_pathways: int = MAX_RETURNED_PATHWAYS,
    explore_cap: int = PATH_EXPLORE_CAP,
) -> list[dict]:
    """枚举 root 到终点的简单路径（环上回访即止），按累计概率降序截断。

    边概率是 FlowER 采样的频率估计（count/sample_size）；累计概率是各步
    概率之积——它是排序启发，不是动力学预测。
    """
    adjacency: dict[str, list[tuple[str, float]]] = {}
    for edge in network.get("edges", []):
        adjacency.setdefault(edge["reactant"], []).append(
            (edge["product"], float(edge["probability"]))
        )
    root = network.get("root", "")
    paths: list[tuple[float, list[dict]]] = []
    stack: list[tuple[str, list[dict], float, frozenset]] = [(root, [], 1.0, frozenset({root}))]
    explored = 0
    while stack and explored < explore_cap:
        node, steps, cum, visited = stack.pop()
        explored += 1
        children = [(p, prob) for p, prob in adjacency.get(node, []) if p not in visited]
        if not children:
            if steps:
                paths.append((cum, steps))
            continue
        for product, prob in children:
            stack.append((
                product,
                [*steps, {"reactant": node, "product": product, "probability": prob}],
                cum * prob,
                visited | {product},
            ))
    paths.sort(key=lambda item: item[0], reverse=True)
    return [
        {"cumulative_probability": cum, "steps": steps, "reaches_target": None}
        for cum, steps in paths[:max_pathways]
    ]


def _normalise_target_smiles(smiles: str):
    """目标产物的清洁形式：与 driver 的 clean 口径对齐（去立体、canonical、非立体）。

    返回 None 表示非法 SMILES。
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    Chem.RemoveStereochemistry(mol)
    return Chem.MolToSmiles(mol, isomericSmiles=False, canonical=True)


def _attach_target_flags(pathways: list[dict], targets: list[str]) -> None:
    """就地标注每条路径的终点是否覆盖全部目标组分（exact 组分匹配）。"""
    if not targets:
        return
    wanted = set(targets)
    for pathway in pathways:
        terminal = pathway["steps"][-1]["product"]
        components = {part for part in terminal.split(".") if part}
        pathway["reaches_target"] = wanted <= components


class MechanismPredict(Tool):
    tool_id: str = 't-61'
    tool_name: str = 'mechanism_predict'
    tool_description: str = description
    input_schema: Any = MechanismPredict_input_schema
    output_schema: Any = MechanismPredict_output_schema

    def is_write(self) -> bool:
        return True

    async def tool_call(
        self, user_input: MechanismPredict_input_schema, session: Session
    ) -> MechanismPredict_output_schema:
        cfg = get_config().flower
        if not cfg.enabled:
            return MechanismPredict_output_schema(
                is_success=False,
                message=(
                    "mechanism_predict is disabled (flower.enabled=false). Install the FlowER "
                    "environment with scripts/setup_flower.sh, then set flower.enabled=true."
                ),
            )
        if not _RDKIT_AVAILABLE:
            return MechanismPredict_output_schema(
                is_success=False,
                message="RDKit is not installed. Install it with: pip install 'cloudra[chem]'",
            )

        missing = [
            key for key, value in (
                ("flower.repo_dir", cfg.repo_dir),
                ("flower.env_python", cfg.env_python),
                ("flower.checkpoint", cfg.checkpoint),
            )
            if not value
        ]
        if missing:
            return MechanismPredict_output_schema(
                is_success=False,
                message=(
                    f"FlowER is not configured ({', '.join(missing)} unset). "
                    "Run scripts/setup_flower.sh to install the environment and write the config."
                ),
            )
        broken = [
            key for key, ok in (
                ("flower.repo_dir", os.path.isdir(cfg.repo_dir)),
                ("flower.env_python", os.path.isfile(cfg.env_python)),
                ("flower.checkpoint", os.path.isfile(cfg.checkpoint)),
            )
            if not ok
        ]
        if broken:
            return MechanismPredict_output_schema(
                is_success=False,
                message=(
                    f"FlowER paths do not exist on disk: {', '.join(broken)}. "
                    "Re-run scripts/setup_flower.sh or fix the config."
                ),
            )

        reactants = user_input.reactants.strip()
        if not reactants or ">>" in reactants or "|" in reactants:
            return MechanismPredict_output_schema(
                is_success=False,
                message="reactants must be plain dot-separated SMILES (no '>>' or '|').",
            )
        for component in reactants.split("."):
            if Chem.MolFromSmiles(component) is None:
                return MechanismPredict_output_schema(
                    is_success=False,
                    message=f"Invalid reactant SMILES component: {component!r}",
                )
        targets: list[str] = []
        if user_input.products.strip():
            for raw in user_input.products.split("|"):
                normalised = _normalise_target_smiles(raw.strip())
                if normalised is None:
                    return MechanismPredict_output_schema(
                        is_success=False,
                        message=f"Invalid target product SMILES: {raw!r}",
                    )
                targets.append(normalised)

        return await asyncio.to_thread(self._run, user_input, reactants, targets)

    # ---------- 同步段（子进程 + 文件 IO，经 asyncio.to_thread 卸载） ----------

    def _run(
        self, user_input: MechanismPredict_input_schema, reactants: str, targets: list[str]
    ) -> MechanismPredict_output_schema:
        cfg = get_config().flower
        if user_input.output_dir:
            out_dir = resolve_tool_path(self, user_input.output_dir)
        else:
            out_dir = resolve_tool_path(self, os.path.abspath("mechanism_output"))
        run_dir = self._next_run_dir(out_dir)

        input_path = os.path.join(run_dir, "beam.txt")
        result_dir = os.path.join(run_dir, "results")
        network_path = os.path.join(run_dir, "network.json")
        stdout_path = os.path.join(run_dir, "stdout.log")
        stderr_path = os.path.join(run_dir, "stderr.log")

        command = [
            cfg.env_python, DRIVER_PATH,
            "--repo", cfg.repo_dir,
            "--checkpoint", cfg.checkpoint,
            "--input", input_path,
            "--result-dir", result_dir,
            "--out", network_path,
            "--beam-size", str(user_input.beam_size),
            "--nbest", str(user_input.nbest),
            "--max-depth", str(user_input.max_depth),
            "--sample-size", str(user_input.sample_size),
        ]
        atomic_write_text(input_path, reactants + "\n")
        atomic_write_text(os.path.join(run_dir, "command.txt"), " ".join(command) + "\n")

        # 独立进程组：超时只回收本次运行自己的进程树（DataLoader worker 同属该组）。
        proc = subprocess.Popen(
            command, cwd=run_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=user_input.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_group(proc)
            stdout, stderr = proc.communicate()
        atomic_write_text(stdout_path, stdout or "")
        atomic_write_text(stderr_path, stderr or "")

        if timed_out:
            return MechanismPredict_output_schema(
                is_success=False,
                run_dir=run_dir,
                message=(
                    f"FlowER exceeded the {user_input.timeout_s}s timeout; this run's own process "
                    f"group was terminated (logs are kept). Reduce max_depth/sample_size or raise "
                    f"timeout_s. Full log: {stdout_path}"
                ),
            )
        if proc.returncode != 0:
            tail = "\n".join((stderr or "").splitlines()[-15:])
            if _TOKEN_MODULE_NOT_FOUND in (stderr or ""):
                reason = (
                    "the flower conda environment is incomplete (module import failed); "
                    "re-run scripts/setup_flower.sh"
                )
            elif _TOKEN_OUT_OF_MEMORY in (stderr or ""):
                reason = "the FlowER process ran out of memory; reduce sample_size/beam_size"
            elif _TOKEN_NO_PICKLE in (stderr or ""):
                reason = "FlowER exited without writing its result pickle"
            else:
                reason = "unrecognised failure; raw stderr tail follows (no cause is guessed)"
            return MechanismPredict_output_schema(
                is_success=False,
                run_dir=run_dir,
                message=(
                    f"FlowER subprocess failed (returncode={proc.returncode}): {reason}\n{tail}\n"
                    f"Full logs: {stdout_path}, {stderr_path}"
                ),
            )

        # returncode == 0 不构成成功：必须能读到并解析 network.json。
        if not os.path.isfile(network_path):
            return MechanismPredict_output_schema(
                is_success=False,
                run_dir=run_dir,
                message=(
                    "FlowER exited 0 but network.json is missing; refusing to treat the exit code "
                    f"alone as success. Full log: {stdout_path}"
                ),
            )
        try:
            with open(network_path, encoding="utf-8") as handle:
                network = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            return MechanismPredict_output_schema(
                is_success=False,
                run_dir=run_dir,
                message=f"network.json is unparsable ({exc}); the run directory is kept for inspection.",
            )

        pathways = enumerate_pathways(network)
        _attach_target_flags(pathways, targets)
        num_species = len(network.get("nodes", []))
        num_steps = len(network.get("edges", []))

        lines = [
            f"FlowER mechanism search completed: {num_species} species, {num_steps} "
            "elementary-step edges (ML hypotheses, NOT verified).",
        ]
        if num_steps == 0:
            lines.append(
                "No elementary steps were found within the search budget "
                f"(max_depth={user_input.max_depth}, beam_size={user_input.beam_size}). Consider "
                "raising them, or the reaction may lie outside FlowER's polar/organic training "
                "distribution."
            )
        else:
            lines.append("Top pathways by cumulative probability (sampling heuristic):")
            for idx, pathway in enumerate(pathways[:MAX_MESSAGE_PATHWAYS], start=1):
                chain = pathway["steps"][0]["reactant"]
                chain += "".join(
                    f" -> {step['product']} (p={step['probability']:.2f})"
                    for step in pathway["steps"]
                )
                lines.append(
                    f"{idx}. cum={pathway['cumulative_probability']:.3f} "
                    f"({len(pathway['steps'])} steps): {chain}"
                )
        if targets:
            reached = [p for p in pathways if p["reaches_target"]]
            lines.append(
                f"Target check: {len(reached)}/{len(pathways)} shown pathways reach all target "
                "product(s) exactly (stereo ignored)."
            )
        lines.append(f"Full network: {network_path} | run directory: {run_dir}")
        lines.append(
            "Reminder: these are ML-proposed hypotheses. Verify intermediates/TS with "
            "submit_compute_job (xtb/DFT) before making mechanistic claims."
        )

        return MechanismPredict_output_schema(
            is_success=True,
            message="\n".join(lines),
            pathways=pathways,
            num_species=num_species,
            num_steps=num_steps,
            network_json=network_path,
            run_dir=run_dir,
        )

    @staticmethod
    def _next_run_dir(output_dir: str) -> str:
        """``flower_runs/flower_NNNN``：编号单调递增，便于按运行次序复查。"""
        runs_root = os.path.join(output_dir, RUNS_DIR_NAME)
        os.makedirs(runs_root, exist_ok=True)
        used = set()
        for name in os.listdir(runs_root):
            head, _, tail = name.rpartition("_")
            if head == "flower" and tail.isdigit():
                used.add(int(tail))
        index = 1
        while index in used:
            index += 1
        run_dir = os.path.join(runs_root, f"flower_{index:04d}")
        os.makedirs(run_dir, exist_ok=False)
        return run_dir


def get_class():
    return MechanismPredict
