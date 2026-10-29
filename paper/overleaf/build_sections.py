"""Prepare the bilingual Overleaf body from the approved manuscript sources."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCES = (
    ("01_introduction", "01_introduction"),
    ("02_architecture_and_methods", "02_methods"),
    ("03_benchmarks_and_results", "03_results"),
)
MARKERS = {"targets": 1, "molecular-tasks-1": 2, "molecular-tasks-2": 3}
SINGLE_COLUMN = {1, 2, 3, 8, 10, 11, 15, 16}
WIDE_WIDTHS = {7: ".64", 9: ".9", 12: ".9", 13: ".9", 14: ".75", 17: ".96"}

# Line breaks retain every term of the approved equations at readable type size.
DISPLAY_EQUATIONS = {
    1: r"""\begin{aligned}
J(\pi)={}&2(N_{\mathrm{f}}+N_{\mathrm{b}})+N_{\mathrm{o}}\\
&+4\Delta_H+8\Delta_q+8\Delta_r+2N_{\mathrm{s}}.
\end{aligned}""",
    2: r"""\begin{aligned}
\mathbf{x}_i'&=\mathbf{a}+\mathbf{R}(\hat{\mathbf{u}},\theta)(\mathbf{x}_i-\mathbf{a}),\\
\mathbf{R}&=\cos\theta\,\mathbf{I}+(1-\cos\theta)\hat{\mathbf{u}}\hat{\mathbf{u}}^{\mathsf{T}}\\
&\quad+\sin\theta\,[\hat{\mathbf{u}}]_\times.
\end{aligned}""",
    5: r"""\begin{aligned}
\hat{\mathbf{u}}_s&=(a_s\cos s\gamma,\,y_s,\,a_s\sin s\gamma),\\
a_s&=\sqrt{1-y_s^2},\qquad y_s=1-\frac{2s}{K-1},\\
\gamma&=\pi(3-\sqrt{5}).
\end{aligned}""",
    6: r"""\begin{aligned}
S(\mathbf{X})=\max_{(i,j)\in W}\{&0,\,l_{ij}-d_{ij}(\mathbf{X}),\\
&d_{ij}(\mathbf{X})-u_{ij}\}.
\end{aligned}""",
    7: r"""\begin{gathered}
\min_{\mathbf{Q}^{\mathsf{T}}\mathbf{Q}=\mathbf{I},\det\mathbf{Q}=1}\|\mathbf{P}\mathbf{Q}-\mathbf{R}\|_{\mathrm{F}}^2,\\
\mathbf{P}^{\mathsf{T}}\mathbf{R}=\mathbf{U}\boldsymbol{\Sigma}\mathbf{V}^{\mathsf{T}},\\
\mathbf{Q}=\mathbf{U}\operatorname{diag}[1,1,\det(\mathbf{U}\mathbf{V}^{\mathsf{T}})]\mathbf{V}^{\mathsf{T}}.
\end{gathered}""",
    8: r"""\begin{aligned}
d_{ij,k}^*&=(1-\lambda_k)d_{ij}^{\mathrm{R}}+\lambda_k d_{ij}^{\mathrm{P}},\\
V_k&=\sum_{i<j}\frac{(d_{ij,k}-d_{ij,k}^*)^2}{d_{ij,k}^4}.
\end{aligned}""",
    9: r"""\begin{aligned}
S_t={}&\mathbf{1}[R\ne\emptyset]\\
&\wedge\bigwedge_{c\in R}\mathbf{1}[\exists f\in F_t:f.c=c,\,f.o=+]\\
&\wedge\mathbf{1}[\nexists f\in F_t:f.c\in R\cup O,\,f.o=-].
\end{aligned}""",
    10: r"""\begin{aligned}
\mathbf{H}_{\mathrm{mw}}&=\mathbf{M}^{-1/2}\nabla_{\mathbf{x}}^2 U\,\mathbf{M}^{-1/2},\\
\mathbf{H}_{\mathrm{mw}}\mathbf{v}_k&=\lambda_k\mathbf{v}_k.
\end{aligned}""",
    12: r"""\begin{aligned}
\frac{\mathrm{d}\mathbf{q}_{\pm}}{\mathrm{d}s}&=-\frac{\nabla_{\mathbf{q}}U}{\|\nabla_{\mathbf{q}}U\|},\\
\mathbf{q}_{\mathrm{init},\pm}&\approx\mathbf{q}_{\mathrm{TS}}\pm\epsilon\mathbf{v}_-.
\end{aligned}""",
}


def escape_text(text):
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
        "→": r"\(\to\)", "−": r"\( - \)",
    }
    subscripts = "₀₁₂₃₄₅₆₇₈₉"
    out = []
    for char in text:
        if char in subscripts:
            out.append(r"\textsubscript{" + str(subscripts.index(char)) + "}")
        else:
            out.append(replacements.get(char, char))
    return "".join(out)


def text_to_tex(text, chapter):
    """Keep math unchanged; convert prose citations, code spans, and figure refs."""
    pieces = text.split("$")
    for index in range(0, len(pieces), 2):
        text = pieces[index]
        out = []
        cursor = 0
        while cursor < len(text):
            if text[cursor] == "`":
                end = text.find("`", cursor + 1)
                if end != -1:
                    out.append(r"\texttt{" + escape_text(text[cursor + 1:end]) + "}")
                    cursor = end + 1
                    continue
            if text[cursor] == "[":
                end = text.find("]", cursor + 1)
                value = text[cursor + 1:end] if end != -1 else ""
                numbers = value.replace(" ", "").split(",")
                if numbers and all(x.isdecimal() and 1 <= int(x) <= 18 for x in numbers):
                    shift = 6 if chapter == 2 else 0
                    keys = [f"ref{int(x) + shift:02}" for x in numbers]
                    out.append(r"\citep{" + ",".join(keys) + "}")
                    cursor = end + 1
                    continue
            prefix = next((p for p in ("Figures ", "Figure ", "图 ", "图") if text.startswith(p, cursor)), None)
            if prefix:
                end = cursor + len(prefix)
                number_end = end
                while number_end < len(text) and text[number_end].isdecimal():
                    number_end += 1
                if number_end > end:
                    number = int(text[end:number_end])
                    if 1 <= number <= 17:
                        label = "图~" if prefix.startswith("图") else prefix.strip() + "~"
                        out.append(label + rf"\ref{{fig:{number:02}}}")
                        cursor = number_end
                        # The one plural phrase uses a second automatic reference.
                        if prefix == "Figures " and text.startswith(" and ", cursor):
                            second_start = cursor + 5
                            second_end = second_start
                            while second_end < len(text) and text[second_end].isdecimal():
                                second_end += 1
                            if second_end > second_start:
                                out.append(" and " + rf"\ref{{fig:{int(text[second_start:second_end]):02}}}")
                                cursor = second_end
                        continue
            out.append(escape_text(text[cursor]))
            cursor += 1
        pieces[index] = "".join(out)
    return "$".join(pieces)


def figure_captions(language):
    figures = json.loads((HERE / "figure_manifest.json").read_text())[language]
    captions = [item["caption"] for item in figures]
    if len(captions) != 17:
        raise ValueError(f"Expected 17 manuscript captions, received {len(captions)}")
    return captions


def figure_tex(number, captions, chapter):
    if number in (10, 15):
        output = [r"\begin{figure*}[tbp]", r"\centering"]
        for n in (number, number + 1):
            output.extend((
                r"\begin{minipage}[t]{.48\textwidth}",
                r"\vspace{0pt}\centering",
                rf"\includegraphics[width=\linewidth]{{figures/fig{n:02}.pdf}}",
                r"\caption{" + text_to_tex(captions[n - 1], chapter) + "}",
                rf"\label{{fig:{n:02}}}",
                r"\end{minipage}" + (r"\hfill" if n == number else ""),
            ))
        output.append(r"\end{figure*}")
        return "\n".join(output)
    single = number in SINGLE_COLUMN
    environment = "figure" if single else "figure*"
    width = r"\linewidth" if single else WIDE_WIDTHS.get(number, "") + r"\textwidth"
    return "\n".join((
        rf"\begin{{{environment}}}[tbp]",
        r"\centering",
        rf"\includegraphics[width={width}]{{figures/fig{number:02}.pdf}}",
        r"\caption{" + text_to_tex(captions[number - 1], chapter) + "}",
        rf"\label{{fig:{number:02}}}",
        rf"\end{{{environment}}}",
    ))


def convert(source, language, chapter, captions):
    output = []
    used_figures = set()
    equation = 0
    math_lines = None
    blank_lines = 0

    def add_figure(number):
        if number not in used_figures:
            output.extend((figure_tex(number, captions, chapter), ""))
            used_figures.add(number)
            if number in (10, 15):
                used_figures.add(number + 1)

    for line in source.splitlines():
        if not line:
            blank_lines += 1
            if blank_lines == 1:
                output.append("")
            continue
        if blank_lines >= 4:
            output.extend((r"\discussionSpace", ""))
        blank_lines = 0
        if line == "$$":
            if math_lines is None:
                math_lines = []
            else:
                equation += 1
                body = DISPLAY_EQUATIONS.get(equation, "\n".join(math_lines))
                output.extend((rf"\begin{{equation}}\label{{eq:methods-{equation:02}}}", body, r"\end{equation}"))
                math_lines = None
            continue
        if math_lines is not None:
            math_lines.append(line)
            continue
        if line.startswith(("### References", "### 参考文献", "### 本节参考文献")):
            break
        if line.startswith("<!-- figure:"):
            add_figure(MARKERS[line.removeprefix("<!-- figure:").removesuffix(" -->")])
            continue
        if line.startswith("!["):
            continue
        if line.startswith(("Figure ", "图 ")):
            lead = line.split(". ", 1)[0]
            number = lead.split(" ", 1)[1]
            if number.isdecimal():
                n = int(number)
                if n < 15:
                    add_figure(n)
                continue
        heading = next(((prefix, command) for prefix, command in (("#### ", "subsubsection"), ("### ", "subsection"), ("## ", "section")) if line.startswith(prefix)), None)
        if heading:
            prefix, command = heading
            title = line[len(prefix):]
            number, title = title.split(" ", 1)
            if number == "2.1.1":
                add_figure(4)
            if number == "2.6":
                add_figure(5)
            if number == "3.3.2":
                add_figure(15)
                add_figure(16)
            if number == ("3.3.2" if language == "zh" else "3.3.3"):
                add_figure(17)
            output.append("\\" + command + "{" + text_to_tex(title, chapter) + "}")
            if number == "3.2.1":
                add_figure(6)
            if number == "3.2.3":
                add_figure(9)
            continue
        output.append(text_to_tex(line, chapter))
        if chapter == 3 and any(value in line for value in ("Figure 17", "图 17", "图17")):
            add_figure(17)
    if math_lines is not None:
        raise ValueError("Unclosed display equation")
    if chapter == 2 and equation != 15:
        raise ValueError(f"Expected 15 methods equations, received {equation}")
    expected = {1, 2, 3} if chapter == 1 else ({4, 5} if chapter == 2 else set(range(6, 18)))
    if used_figures != expected:
        raise ValueError(f"Incorrect chapter {chapter} figure set: {used_figures}")
    return "\n".join(output).strip() + "\n"


def main():
    for language in ("en", "zh"):
        captions = figure_captions(language)
        folder = HERE / f"Cloudra_{language.upper()}" / "sections"
        folder.mkdir(exist_ok=True)
        for chapter, (source_name, target_name) in enumerate(SOURCES, 1):
            suffix = "_zh" if language == "zh" else ""
            source = ROOT / "paper/sections" / f"{source_name}{suffix}.md"
            target = folder / f"{target_name}.tex"
            target.write_text(convert(source.read_text(), language, chapter, captions))
            print(target.relative_to(ROOT))


if __name__ == "__main__":
    main()
