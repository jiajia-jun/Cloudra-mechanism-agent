"""事实适配器（contract_version=2）：从已登记的工具证据 payload 抽取
类型化 EvidenceFact（含反证）。

适配器是纯函数：(payload, source_ref) -> list[EvidenceFact]；不读文件、
不做二次计算——所有判断都来自工具结果里已解析的结构化字段。工具失败
（is_success=false）不产事实（失败本身已由 CallReview 记录，可送审）。
"""

from __future__ import annotations

import uuid
from typing import Any

from cloudra.dag.evidence_facts import EvidenceFact, FactSubject
from cloudra.dag.models import GraphRef


def _fact(
    check: str,
    outcome: str,
    source_ref: GraphRef,
    details: dict[str, Any],
    subject: FactSubject | None = None,
) -> EvidenceFact:
    return EvidenceFact(
        fact_id="fact_" + uuid.uuid4().hex,
        check=check,
        outcome=outcome,  # type: ignore[arg-type]
        subject=subject or FactSubject(),
        source_refs=[source_ref],
        details=details,
    )


def _result_of(payload: dict[str, Any]) -> dict[str, Any]:
    result = (payload or {}).get("result") or {}
    return result if isinstance(result, dict) else {}


def log_parser_facts(payload: dict[str, Any], source_ref: GraphRef) -> list[EvidenceFact]:
    """log_parser：驻点收敛、曲率（虚频计数）、能量、热化学修正分别记录。"""
    result = _result_of(payload)
    if not result.get("is_success"):
        return []
    facts: list[EvidenceFact] = []

    opt_converged = result.get("opt_converged")
    if opt_converged is True:
        facts.append(_fact("stationary_point", "supports", source_ref,
                           {"opt_converged": True}))
    elif opt_converged is False:
        facts.append(_fact("stationary_point", "refutes", source_ref,
                           {"opt_converged": False}))

    freqs = result.get("frequencies_cm")
    imag = result.get("imaginary_frequencies")
    if freqs is not None or imag is not None:
        n_imag = len(imag or [])
        facts.append(_fact(
            "curvature",
            "supports" if freqs is not None else "inconclusive",
            source_ref,
            {"n_imag": n_imag, "imaginary_frequencies": imag or []},
        ))

    # IRC path availability is a parser-observed fact.  Unknown does not pass;
    # if IRC fields are present but convergence is not confirmed we keep an
    # inconclusive path fact instead of pretending no path evidence was looked at.
    irc_converged = result.get("irc_both_directions_converged")
    irc_seen = any(
        key.startswith("irc_") and result.get(key) is not None
        for key in (
            "irc_num_points_forward",
            "irc_num_points_backward",
            "irc_endpoint_energies_hartree",
            "irc_both_directions_converged",
        )
    )
    if irc_converged is True:
        facts.append(_fact("path", "supports", source_ref, {
            "irc_both_directions_converged": True,
            "irc_num_points_forward": result.get("irc_num_points_forward"),
            "irc_num_points_backward": result.get("irc_num_points_backward"),
            "irc_endpoint_energies_hartree": result.get(
                "irc_endpoint_energies_hartree"
            ),
        }))
    elif irc_seen:
        facts.append(_fact("path", "inconclusive", source_ref, {
            "irc_both_directions_converged": result.get("irc_both_directions_converged"),
            "irc_num_points_forward": result.get("irc_num_points_forward"),
            "irc_num_points_backward": result.get("irc_num_points_backward"),
        }))

    if result.get("scf_energy_hartree") is not None:
        facts.append(_fact("energy", "supports", source_ref,
                           {"scf_energy_hartree": result["scf_energy_hartree"]}))

    if (
        result.get("thermal_gibbs_correction_hartree") is not None
        or result.get("total_gibbs_free_energy_hartree") is not None
    ):
        facts.append(_fact("thermochemistry", "supports", source_ref, {
            "thermal_gibbs_correction_hartree": result.get(
                "thermal_gibbs_correction_hartree"
            ),
            "total_gibbs_free_energy_hartree": result.get(
                "total_gibbs_free_energy_hartree"
            ),
        }))
    return facts


def ts_guess_facts(payload: dict[str, Any], source_ref: GraphRef) -> list[EvidenceFact]:
    """ts_guess：verify 的曲率/路径判断与 scan_parse 的能垒候选分别记录。"""
    result = _result_of(payload)
    if not result.get("is_success"):
        return []
    arguments = (payload or {}).get("arguments") or {}
    facts: list[EvidenceFact] = []

    n_imag = result.get("n_imag")
    if n_imag is not None:
        # verify 是对 TS 候选的判断：n_imag==1 支持曲率检查，否则反证。
        facts.append(_fact(
            "curvature",
            "supports" if n_imag == 1 else "refutes",
            source_ref,
            {"n_imag": n_imag, "imag_freqs": result.get("imag_freqs") or []},
        ))

    if result.get("irc_end_a_path") and result.get("irc_end_b_path"):
        facts.append(_fact("path", "supports", source_ref, {
            "irc_end_a_path": result["irc_end_a_path"],
            "irc_end_b_path": result["irc_end_b_path"],
        }))
    elif arguments.get("irc_log"):
        # 提供了 IRC 但端点不可得（含未收敛保持缺口）：不确定，不是支持。
        facts.append(_fact("path", "inconclusive", source_ref,
                           {"irc_log": arguments["irc_log"]}))

    candidate = result.get("candidate")
    if isinstance(candidate, dict) and candidate.get("geometry_ref"):
        facts.append(_fact("energy", "supports", source_ref, {
            "barrier_kcal": result.get("barrier_kcal"),
            "scan_index": candidate.get("scan_index"),
            "energy": candidate.get("energy"),
            "geometry_ref": candidate.get("geometry_ref"),
            "source": candidate.get("source"),
        }))
    elif result.get("candidate_unavailable"):
        facts.append(_fact("energy", "inconclusive", source_ref,
                           {"candidate_unavailable": True}))
    return facts


def _identity_fact_outcome(identity: str) -> str:
    if identity == "match":
        return "supports"
    if identity == "mismatch":
        return "refutes"
    # not_provided / inconclusive and unknown values never become support.
    return "inconclusive"


def reaction_mapping_facts(
    payload: dict[str, Any],
    source_ref: GraphRef,
) -> list[EvidenceFact]:
    """reaction_mapping：身份与原子映射分开记录，反证不隐藏。

    两端身份分别形成 identity 事实；只有 concrete binding 或唯一图级候选
    才支持 mapping。对称导致 mapping inconclusive 不自动变成身份反证。
    """
    result = _result_of(payload)
    if not result.get("is_success"):
        return []
    arguments = (payload or {}).get("arguments") or {}
    if not isinstance(arguments, dict):
        arguments = {}
    facts: list[EvidenceFact] = []

    reactant_identity = result.get("reactant_identity")
    product_identity = result.get("product_identity")
    reactant_details: dict[str, Any] = {"endpoint_role": "reactant"}
    product_details: dict[str, Any] = {"endpoint_role": "product"}

    # Pass through charge/spin/declared SMILES where the adapter can see it.
    if "reactant_charge" in arguments:
        reactant_details["charge"] = arguments["reactant_charge"]
    if "product_charge" in arguments:
        product_details["charge"] = arguments["product_charge"]
    if "reactant_smiles" in arguments:
        reactant_details["smiles"] = arguments["reactant_smiles"]
    if "product_smiles" in arguments:
        product_details["smiles"] = arguments["product_smiles"]

    if reactant_identity:
        reactant_details["identity"] = reactant_identity
        facts.append(_fact(
            "identity",
            _identity_fact_outcome(reactant_identity),
            source_ref,
            reactant_details,
        ))
    if product_identity:
        product_details["identity"] = product_identity
        facts.append(_fact(
            "identity",
            _identity_fact_outcome(product_identity),
            source_ref,
            product_details,
        ))

    binding_status = result.get("binding_status")
    mapping_status = result.get("mapping_status")
    mapping_details: dict[str, Any] = {
        "binding_status": binding_status,
        "mapping_status": mapping_status,
        "binding_source": result.get("binding_source"),
        "binding_diagnostics": result.get("binding_diagnostics") or [],
        "atom_map_complete": bool(result.get("atom_map")),
        "mapping_uncertainty": (
            None
            if mapping_status == "unique"
            else "symmetric_or_ambiguous"
            if mapping_status == "ambiguous"
            else "not_determined"
            if mapping_status == "inconclusive"
            else "unknown"
        ),
    }
    if binding_status == "complete":
        mapping_outcome: str = "supports"
    elif binding_status == "inconclusive" or mapping_status in (
        "ambiguous", "inconclusive",
    ):
        mapping_outcome = "inconclusive"
    elif binding_status == "not_requested" and mapping_status == "unique":
        # A unique graph-level mapping is still a useful mapping fact, but the
        # contract should say whether concrete atom correspondence is needed.
        mapping_outcome = "supports"
    elif mapping_status:
        mapping_outcome = "inconclusive"
    else:
        mapping_outcome = "inconclusive"
    facts.append(_fact("mapping", mapping_outcome, source_ref, mapping_details))
    return facts
