from pathlib import Path

root = Path(__file__).resolve().parents[1] / "figures"
source = {
    "fig_p4_surface_vs_network.svg": "fig_p4_surface_vs_network_green_v2.svg",
    "fig_p5_3d_space_clean.svg": "fig_p5_3d_space_green_v2.svg",
    "fig_p3_blackbox_questions.svg": "fig_p3_blackbox_questions_green_v2.svg",
    "fig_p6_workflow_clean.svg": "fig_p6_workflow_green_v2.svg",
    "fig_p13_closed_loop.svg": "fig_p13_closed_loop_green_v2.svg",
}

colors = {
    "#1f4e79": "#194D36",
    "#2564a8": "#287B54",
    "#52718f": "#427E68",
    "#d7e1ec": "#D8E5D5",
    "#e8f0fa": "#EDF6E8",
    "#eef3f8": "#F4F9EF",
    "#f7fafd": "#F8FBF5",
    "#e07b00": "#D4A921",
    "#d69325": "#D4A921",
    "#d08c21": "#D4A921",
    "#925b0d": "#806511",
    "#8a5410": "#806511",
    "#9dbede": "#A9C9A5",
    "#a4b6c9": "#A9C9A5",
    "#cfe0f2": "#E6F3E3",
    "#b7c9d9": "#B7D4B2",
    "#8fa9bf": "#8AAB84",
    "#7b5ea7": "#9DBF62",
    "#5b3e77": "#536B2B",
    "#c0392b": "#B54B49",
    "#2e7d32": "#287B54",
    "#fff7ea": "#FFF9E8",
    "#fffaf0": "#FFF9E8",
    "#fdebd7": "#F8EAB9",
    "#ffe8cc": "#F8EAB9",
    "#fff2dd": "#F8EAB9",
    "#596b7a": "#5D6F62",
    "#6a8299": "#5D6F62",
    "#ebd5af": "#E8D997",
}

for original, updated in source.items():
    text = (root / original).read_text()
    for before, after in colors.items():
        text = text.replace(before, after)
    (root / updated).write_text(text)
    print(updated)
