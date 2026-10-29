"""Plot saved evidence-association responses and one original completion trace."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/cloudra-evidence-mpl")

# isort: off
from figure_style import (
    EDGE, GREEN, GRID, MUTED, OLIVE, PALE, WARM, WHITE,
    configure, panel, save,
)
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle
# isort: on


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "output/cloudra_model_study_20261028"
OUTPUT = ROOT / "paper/figures/model_semantics_20261028/evidence_panels"


def read_json(name: str) -> dict:
    return json.loads((SOURCE / name).read_text(encoding="utf-8"))


def box(ax, x, y, w, h, title, lines, *, accent=GREEN, fill=PALE):
    ax.add_patch(Rectangle((x, y), w, h, facecolor=fill,
                           edgecolor=EDGE, linewidth=0.65, zorder=2))
    ax.add_patch(Rectangle((x, y + h - 0.018), w, 0.018,
                           facecolor=accent, edgecolor="none", zorder=3))
    ax.text(x + 0.025, y + h - 0.052, title, fontsize=7.5,
            weight="bold", va="top", zorder=4)
    ax.text(x + 0.025, y + h - 0.13, "\n".join(lines),
            fontsize=7, va="top", linespacing=1.35, zorder=4)


def arrow(ax, start, end, *, color=GREEN, dashed=False, shrink=2):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>",
                                mutation_scale=7, linewidth=0.8,
                                color=color, shrinkA=shrink, shrinkB=shrink,
                                linestyle="--" if dashed else "-", zorder=1))


def evidence_panel(fig, coherent, altered):
    panel(fig, "a", "Evidence–geometry association", 0.045, 0.965)
    ax = fig.add_axes([0.045, 0.455, 0.445, 0.47])
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    opt, freq, irc = (coherent[k] for k in ("O", "F", "I"))
    box(ax, 0, 0.705, 0.435, 0.265, "TS optimization", [
        f"final geometry: {opt['final_geometry']}", "converged: true",
    ])
    box(ax, 0.545, 0.705, 0.455, 0.265, "TS frequency", [
        f"geometry: {freq['geometry']} → {altered['F']['geometry']}",
        f"1 imaginary: {freq['imaginary_frequencies_cm'][0]:.4f} " + r"cm$^{-1}$",
    ], accent=WARM)
    arrow(ax, (0.435, 0.835), (0.545, 0.835))
    ax.text(0.49, 0.89, "same", fontsize=6.5, ha="center", color=MUTED)
    ax.text(0.49, 0.855, "TS", fontsize=6.5, ha="center", color=MUTED)
    box(ax, 0.17, 0.365, 0.66, 0.255, "Bidirectional IRC", [
        f"start: {irc['start_geometry']}",
        "outer frames: " + " / ".join(irc["outer_geometries"]),
    ])
    arrow(ax, (0.215, 0.705), (0.37, 0.62))
    endpoints = [coherent[k] for k in ("R", "P")]
    for x, title, endpoint in zip((0, 0.545), ("Source Opt/Freq", "Target Opt/Freq"), endpoints):
        box(ax, x, 0.035, 0.455, 0.245, title, [
            f"{endpoint['input_geometry']} → {endpoint['final_geometry']}",
            "0 imaginary frequencies",
        ])
    arrow(ax, (0.36, 0.365), (0.225, 0.28))
    arrow(ax, (0.64, 0.365), (0.77, 0.28))


def response_panel(fig, records, sources):
    panel(fig, "b", "Association decisions", 0.535, 0.965)
    ax = fig.add_axes([0.635, 0.535, 0.335, 0.325])
    conditions = [(binding, presentation, order)
                  for binding in ("coherent", "altered")
                  for presentation in ("flat", "linked")
                  for order in ("forward", "swapped")]
    source_ids = [s["base_case_id"] for s in sources]
    short = {source_ids[0]: "E1", source_ids[1]: "NB1 · step 1",
             source_ids[2]: "NB1 · step 2", source_ids[3]: "HA1"}
    by_key = {(r["base_case_id"], r["binding"], r["presentation"], r["order"]): r
              for r in records}
    for row, base in enumerate(source_ids):
        for col, condition in enumerate(conditions):
            r = by_key[(base, *condition)]
            correct = r["prediction"] == r["expected"]
            ax.scatter(col, row, marker="o" if correct else "D", s=220,
                       facecolor=GREEN if correct else WHITE,
                       edgecolor=GREEN if correct else WARM, linewidth=1.1,
                       zorder=3)
            ax.text(col, row, r["prediction"], ha="center", va="center",
                    fontsize=6.8, weight="bold", color=WHITE if correct else WARM,
                    zorder=4)
    ax.set(xlim=(-0.6, 7.6), ylim=(3.6, -0.7),
           xticks=range(8), xticklabels=["F", "S"] * 4,
           yticks=range(4), yticklabels=[short[b] for b in source_ids])
    ax.tick_params(length=0, pad=5, labelsize=7)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for x in range(9):
        ax.axvline(x - 0.5, color=GRID, linewidth=0.5, zorder=0)
    for y in range(5):
        ax.axhline(y - 0.5, color=GRID, linewidth=0.5, zorder=0)
    ax.axvline(3.5, color=OLIVE, linewidth=1)
    for start, label in ((0, "Coherent"), (4, "Altered")):
        ax.text(start + 1.5, -1.12, label, ha="center", fontsize=7.5,
                weight="bold", clip_on=False)
    for middle, label in ((0.5, "Flat"), (2.5, "Linked"),
                          (4.5, "Flat"), (6.5, "Linked")):
        ax.text(middle, -0.67, label, ha="center", fontsize=7, clip_on=False)
    fig.text(0.635, 0.477, "F / S: forward / swapped answer options", fontsize=7,
             color=MUTED)
    legend = fig.add_axes([0.535, 0.427, 0.44, 0.038])
    legend.axis("off")
    legend.scatter([0.025], [0.5], s=48, c=GREEN, marker="o")
    legend.text(0.07, 0.5, "Correct association", va="center", fontsize=7)
    legend.scatter([0.55], [0.5], s=48, facecolors=WHITE, edgecolors=WARM,
                   marker="D", linewidth=1)
    legend.text(0.595, 0.5, "Incorrect", va="center", fontsize=7)
    legend.set(xlim=(0, 1), ylim=(0, 1))


def history_panel(fig, candidate, followup):
    panel(fig, "c", "Completion request and DAG response", 0.045, 0.39)
    ax = fig.add_axes([0.045, 0.045, 0.925, 0.29])
    ax.set(xlim=(0, 1), ylim=(0, 1))
    ax.axis("off")
    stages = [
        ("Structured report", ["complete: false", "unresolved evidence", "waived: []"],
         candidate["report_source"], GREEN),
        ("Completion request", ["stop", 'disposition: "complete"'],
         candidate["source"], WARM),
        ("DAG response", ['action: "continue_work"', "IRC proof still missing"],
         followup["gate_source"], GREEN),
        ("Model receives gap", ["missing short_irc", "bind supporting evidence", "or declare partial"],
         followup["feedback_event"]["source"], OLIVE),
        ("Revised request", ["stop", 'disposition: "partial"'],
         followup["next_stop_source"], GREEN),
    ]
    width = 0.181
    for i, (title, lines, source, accent) in enumerate(stages):
        x = i * 0.205
        box(ax, x, 0.05, width, 0.9, title, lines, accent=accent)
        if i < len(stages) - 1:
            arrow(ax, (x + width, 0.5), (x + 0.205, 0.5), color=OLIVE, shrink=0)


def main():
    configure()
    analysis = read_json("identity_binding_analysis.json")
    provenance = read_json("evidence_binding_provenance.json")
    history = read_json("historical_completion_audit.json")
    probes = [json.loads(line) for line in (SOURCE / "evidence_binding_probes.jsonl")
              .read_text(encoding="utf-8").splitlines() if line.strip()]
    responses = {}
    for pair in analysis["evidence_binding"]["option_order_pairs"]:
        for side in ("left", "right"):
            response = pair[side]
            responses[response["id"]] = response
    records = list(responses.values())
    assert len(records) == len(probes) == 32
    assert all(r["prediction"] in {"A", "B"} for r in records)
    probe_by_id = {p["id"]: p for p in probes}
    assert set(probe_by_id) == set(responses)
    wrong = [r for r in records if r["prediction"] != r["expected"]]
    assert len(wrong) == 2
    source_id = "brief-errors/r1/evt_8ed26719359e47e0"
    coherent = probe_by_id[f"evidence_binding/{source_id}/coherent/flat/forward"]["binding_records"]
    altered = probe_by_id[f"evidence_binding/{source_id}/altered/flat/forward"]["binding_records"]
    assert coherent["F"]["geometry"] == "g_63"
    assert altered["F"]["geometry"] == "g_42"
    before = json.loads(json.dumps(coherent))
    before["F"]["geometry"] = altered["F"]["geometry"]
    assert before == altered
    candidate = next(r for r in history["incomplete_report_then_first_action_stop"]
                     if r["source"]["event_id"] == "evt_6cc649e84ef041b2")
    followup = next(r for r in history["rejected_stop_followups"]
                    if r["stop_source"]["event_id"] == "evt_6cc649e84ef041b2")
    assert candidate["intervening_calls"] == []
    assert followup["calls_before_next_stop_or_run_end"] == []
    assert followup["explicit_evidence_submission_observed"] is False
    report = json.loads(candidate["actual_program_outputs"][1]["data"]["value"])
    assert report["complete"] is False and report["waived"] == []
    assert "short_irc" in followup["feedback_event"]["data"]["content"]
    fig = plt.figure(figsize=(178 / 25.4, 114 / 25.4))
    evidence_panel(fig, coherent, altered)
    response_panel(fig, records, provenance["source_chains"])
    history_panel(fig, candidate, followup)
    caption = """Evidence–geometry association and completion requests. (a) Controlled E1 inputs change the TS-frequency geometry reference from g_63 to g_42 while keeping local termination, convergence, energy and frequency values fixed. (b) All 32 local Qwen3.8:27b inputs: four source chains × coherent/altered association × flat/linked presentation × forward/swapped answer order. Four chains cover three tasks; the two NB1 chains share one original run. Letters show saved A/B responses. Green circles and open brown diamonds indicate correct and incorrect association decisions. Both errors occur with altered/flat/swapped inputs. (c) An original DeepSeek-v4-flash IA1 trajectory (brief-errors, r2): a report with unresolved evidence is followed by a complete stop request, a DAG response specifying the missing short_irc proof, feedback to the model and a partial stop request. Source sequence numbers, event identifiers and the following events are retained in the accompanying data file."""
    data = {
        "figure": "evidence_closure", "size_mm": [178, 114],
        "source_files": [str(SOURCE / name) for name in (
            "identity_binding_analysis.json", "evidence_binding_probes.jsonl",
            "evidence_binding_provenance.json", "historical_completion_audit.json")],
        "local_probe_model": "Qwen3.8:27b", "n_local_inputs": 32,
        "n_source_chains": 4, "n_source_tasks": 3,
        "association_responses": records, "wrong_responses": wrong,
        "source_chains": [{"base_case_id": s["base_case_id"], "task": s["task"],
                           "target_identity": s["target_identity"],
                           "runtime_event": s["runtime_event"]}
                          for s in provenance["source_chains"]],
        "illustrated_coherent_records": coherent, "illustrated_altered_records": altered,
        "historical_report_and_stop": candidate, "historical_rejected_stop_followup": followup,
        "historical_partial_request": next(r for r in history["stop_calls"]
            if r["source"]["event_id"] == "evt_2727815f4f0240ac"),
    }
    save(fig, OUTPUT, "evidence_closure", data, caption)


if __name__ == "__main__":
    main()
