"""Prepare the two journal-layout LaTeX projects from the paired section drafts."""

from pathlib import Path
from shutil import copyfile

ROOT = Path(__file__).resolve().parents[2]
KEYS = {
    "1": "zou2025elagente",
    "2": "aitomia2026",
    "3": "perezsanchez2026quntur",
    "4": "choi2026estructural",
    "5": "li2026arche",
    "6": "bai2026grafico",
}

CAPTIONS = {
    "en": {
        "targets": "Physical targets in a structured literature sample of 85 chemical AI agent systems: 39 materials/surface, 23 finite-molecule/complex, 12 soft-matter/biomolecular, and 11 cross-class systems.",
        "molecular-tasks-1": "Documented tasks in the finite-molecule/complex class (panel 1 of 2; 23 chemical AI agent systems in total). T: structure construction/editing; E: static energy/properties; O: geometry optimization; F: vibrations/thermochemistry; R: explicit pathways/TS; D: molecular/quantum dynamics. Filled cells denote positive evidence; blanks are unencoded, not absent capabilities.",
        "molecular-tasks-2": "Chemical AI agent systems in the finite-molecule/complex class, continued (panel 2 of 2), using the codes in Figure 2. Cloudra (this work) is benchmarked at the bottom. Complete matrices for all 85 chemical AI agent systems and source-level qualifications accompany the draft.",
    },
    "zh": {
        "targets": "85个化学 AI Agent 系统的结构化文献样本：材料/表面39项、有限分子/配合物23项、软物质/生物分子12项、跨类系统11项。",
        "molecular-tasks-1": "有限分子/配合物类已记录的任务（第1/2面板，共23个化学 AI Agent 系统）。T：结构构建/编辑；E：静态能量/性质；O：几何优化；F：振动/热化学；R：显式路径/过渡态；D：分子/量子动力学。实心表示正面证据，空白表示未编码，不代表缺少能力。",
        "molecular-tasks-2": "有限分子/配合物类化学 AI Agent 系统任务续图（第2/2面板），代码同图2，底端展示 Cloudra（本工作）的能力覆盖。全部85个化学 AI Agent 系统的完整矩阵及逐项来源限制见配套材料。",
    },
}

FIGURE_FILES = {
    "targets": "agent_landscape_acid_20261027/targets",
    "molecular-tasks-1": "agent_landscape_acid_20261027/matrix_finite_molecules_complexes_01",
    "molecular-tasks-2": "agent_landscape_acid_20261027/matrix_finite_molecules_complexes_02",
}


def tex_text(text):
    result = []
    position = 0
    while position < len(text):
        if text[position] == "[":
            end = text.find("]", position)
            if end >= 0:
                numbers = [part.strip() for part in text[position + 1 : end].split(",")]
                if numbers and all(number in KEYS for number in numbers):
                    result.append("\\cite{" + ",".join(KEYS[number] for number in numbers) + "}")
                    position = end + 1
                    continue
        character = text[position]
        result.append({"&": "\\&", "%": "\\%", "#": "\\#", "_": "\\_"}.get(character, character))
        position += 1
    result = "".join(result)
    result = result.replace(
        "Figures 2 and 3", "Figures~\\ref{fig:agent-molecular-tasks-1} and~\\ref{fig:agent-molecular-tasks-2}"
    )
    result = result.replace("图2和图3", "图~\\ref{fig:agent-molecular-tasks-1}和图~\\ref{fig:agent-molecular-tasks-2}")
    for number, label in ((1, "targets"), (2, "molecular-tasks-1"), (3, "molecular-tasks-2")):
        result = result.replace(f"Figure {number}", "Figure~\\ref{fig:agent-" + label + "}")
        result = result.replace(f"图{number}", "图~\\ref{fig:agent-" + label + "}")
    return result


def section_to_tex(source):
    result = []
    for line in source.splitlines():
        if line.strip().startswith("<!-- figure:") and line.strip().endswith(" -->"):
            figure = line.strip()[12:-4]
            if figure not in FIGURE_FILES:
                raise ValueError(f"Unknown figure: {figure}")
            result.append("\\input{figure_" + figure.replace("-", "_") + ".tex}")
        elif line.startswith("### "):
            title = line[4:].split(" ", 1)[1]
            result.append("\\subsection{" + tex_text(title) + "}")
        elif line.startswith("## "):
            title = line[3:].split(" ", 1)[1]
            result.append("\\section{" + tex_text(title) + "}")
        else:
            result.append(tex_text(line))
    return "\n".join(result) + "\n"


def selected_bib(source):
    entries = []
    for key in KEYS.values():
        marker = "{" + key + ","
        start = source.find(marker)
        if start < 0:
            raise ValueError(f"Missing bibliography entry: {key}")
        start = source.rfind("@", 0, start)
        opening = source.find("{", start)
        depth = 0
        for end in range(opening, len(source)):
            if source[end] == "{":
                depth += 1
            elif source[end] == "}":
                depth -= 1
                if depth == 0:
                    entries.append(source[start : end + 1])
                    break
        else:
            raise ValueError(f"Incomplete bibliography entry: {key}")
    return "\n\n".join(entries) + "\n"


references = selected_bib((ROOT / "paper/references.bib").read_text())
for language, suffix in (("en", ""), ("zh", "_zh")):
    project = ROOT / "paper/latex" / f"introduction_{language}"
    source = (ROOT / "paper/sections" / f"01_introduction{suffix}.md").read_text()
    (project / "introduction.tex").write_text(section_to_tex(source))
    (project / "references.bib").write_text(references)
    images = project / "figures"
    images.mkdir(exist_ok=True)
    for label, filename in FIGURE_FILES.items():
        output_name = Path(filename).name
        for extension in ("pdf", "svg"):
            copyfile(
                ROOT / "paper/figures" / f"{filename}_{language}.{extension}",
                images / f"{output_name}.{extension}",
            )
        placement = "!htb" if label == "targets" else "t"
        figure = (
            "\\begin{figure}[" + placement + "]\n"
            "\\centering\n"
            "\\includegraphics[width=\\columnwidth]{figures/" + output_name + ".pdf}\n"
            "\\caption{" + tex_text(CAPTIONS[language][label]) + "}\n"
            "\\label{fig:agent-" + label + "}\n"
            "\\end{figure}\n"
        )
        (project / ("figure_" + label.replace("-", "_") + ".tex")).write_text(figure)
    for stale in (
        project / "landscape_figure.tex",
        project / "figure_material_tasks.tex",
        project / "figure_molecular_tasks.tex",
        images / "agent_landscape.pdf",
        images / "agent_landscape.svg",
    ):
        stale.unlink(missing_ok=True)
    for filename in ("agent_targets", "agent_material_tasks", "agent_molecular_tasks"):
        for extension in ("pdf", "svg"):
            (images / f"{filename}.{extension}").unlink(missing_ok=True)
    print(f"Prepared {project.name}")
