"""Build paired methods TeX bodies without changing the approved introduction."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def text_to_tex(source):
    parts = source.split("$")
    for index in range(0, len(parts), 2):
        s = parts[index]
        for old, new in (("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_")):
            s = s.replace(old, new)
        for citation in ("[6,7]", "[3,4]", "[1]", "[2]", "[5]", "[7]"):
            s = s.replace(citation, r"\textsuperscript{" + citation[1:-1] + "}")
        parts[index] = s
    return "$".join(parts)


def convert(source, language):
    lines = source.splitlines()
    out = []
    in_math = False
    in_refs = False
    equation = 0
    for line in lines:
        if line == "$$":
            in_math = not in_math
            if in_math:
                equation += 1
                out.append(r"\begin{equation}\label{eq:methods-" + str(equation) + "}")
            else:
                out.append(r"\end{equation}")
            continue
        if in_math:
            out.append(line.replace(r"\varnothing", r"\emptyset").replace(r"\nexists", r"\not\exists"))
            continue
        if line in {"### 参考文献", "### References"}:
            in_refs = True
            heading = "参考文献" if language == "zh" else "References"
            out.extend([r"\section*{" + heading + "}", r"\begingroup\fontsize{8.5}{10.5}\selectfont"])
            continue
        if in_refs:
            if not line:
                continue
            number, content = line.split("] ", 1)
            number = number[1:]
            pieces = content.split("https://")
            text = text_to_tex(pieces[0])
            for piece in pieces[1:]:
                url, *remainder = piece.split(" ", 1)
                text += r"\url{https://" + url + "}"
                if remainder:
                    text += text_to_tex(remainder[0])
            out.append(r"\par\noindent\hangindent=1.5em\hangafter=1 [" + number + "] " + text + r"\par\smallskip")
            continue
        for prefix, command in (("#### ", "subsubsection"), ("### ", "subsection"), ("## ", "section")):
            if line.startswith(prefix):
                title = line[len(prefix) :].split(" ", 1)[1]
                out.append("\\" + command + "{" + text_to_tex(title) + "}")
                break
        else:
            out.append(text_to_tex(line))
    if in_refs:
        out.append(r"\endgroup")
    if in_math:
        raise ValueError("Unclosed display equation")
    if equation != 15:
        raise ValueError(f"Unexpected equation count: {equation}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    for language, suffix in (("zh", "_zh"), ("en", "")):
        source = ROOT / "paper/sections" / f"02_architecture_and_methods{suffix}.md"
        project = ROOT / "paper/latex" / f"methods_{language}"
        (project / "methods.tex").write_text(convert(source.read_text(), language))
        print(f"Prepared {project.name}: 15 equations")
