#!/usr/bin/env python3
"""重新生成软著源程序清单（txt + LaTeX），从当前 cloudra/ 代码库。

输出：
  01_源代码/源代码_前30页.txt / 源代码_后30页.txt          （旧版兼容格式）
  05_完整申请文件包/02_源程序_前30页_排版.txt / 03_...     （同上内容）
  06_LaTeX排版/01_源程序前30页.tex / 02_源程序后30页.tex   （tectonic 可直接编译）

规则：源程序按路径排序拼接，每页 52 行，前 30 页 + 最后 30 页（真实尾部）。
用法：python scripts/gen_copyright_source.py
"""

import os
import re
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATERIALS = ROOT / "软著申请材料"
VERSION = "V2.0"
LINES_PER_PAGE = 52
PAGES_PER_FILE = 30
SEP = "-" * 70

TECTONIC = Path.home() / "anaconda3/envs/tectonic/bin/tectonic"


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "FW" else 1 for c in text)


def collect_lines() -> list[tuple[str, int, str]]:
    files: list[str] = []
    for root, dirs, names in os.walk(ROOT / "cloudra"):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in names:
            if name.endswith(".py"):
                files.append(os.path.relpath(os.path.join(root, name), ROOT))
    files.sort()
    lines: list[tuple[str, int, str]] = []
    for path in files:
        with open(ROOT / path, encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh, 1):
                lines.append((path, lineno, raw.rstrip("\n")))
    return lines


def page_header(page_no: int) -> str:
    label = f"第 {page_no} 页"
    pad = 69 - len(f"Cloudra {VERSION}".encode("utf-8")) - len(label.encode("utf-8"))
    return f"Cloudra {VERSION}{' ' * max(pad, 1)}{label}"


def write_legacy_txt(path: Path, pages: list[list[tuple[str, int, str]]], start_page: int) -> None:
    out: list[str] = []
    for idx, page in enumerate(pages):
        out.append(page_header(start_page + idx))
        out.append(SEP)
        for rel, lineno, content in page:
            out.append(f"{rel}:{lineno}\t{content}")
    data = "\n".join(out) + "\n\n\f"
    path.write_text(data, encoding="utf-8")


def latex_escape_line(line: str) -> str:
    return line


def write_latex(path: Path, pages: list[list[tuple[str, int, str]]], start_page: int) -> None:
    parts: list[str] = []
    parts.append(
        r"""% Cloudra 源程序清单（软著申请用），tectonic 直接编译
\documentclass[10pt,a4paper]{article}
\usepackage{ctex}
\usepackage[top=16mm,bottom=16mm,left=20mm,right=20mm]{geometry}
\usepackage{listings}
\usepackage{fancyhdr}
\usepackage{fontspec}
\setmonofont{DejaVu Sans Mono}
\setCJKmonofont{WenQuanYi Zen Hei}
\lstset{
  basicstyle=\ttfamily\fontsize{6.5}{8.3}\selectfont,
  columns=fullflexible,
  keepspaces=true,
  breaklines=true,
  breakatwhitespace=false,
  breakindent=0pt,
  postbreak=,
  tabsize=4,
  frame=none,
  xleftmargin=0pt,
  xrightmargin=0pt,
  aboveskip=0pt,
  belowskip=0pt,
}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\ttfamily Cloudra V2.0 源程序}
\fancyhead[R]{\small\ttfamily 第 \thepage{} 页}
\renewcommand{\headrulewidth}{0.4pt}
\setlength{\headheight}{14pt}
\begin{document}
\setcounter{page}{"""
        + str(start_page)
        + """}
"""
    )
    for page in pages:
        first = page[0][1]
        parts.append(f"\\begin{{lstlisting}}[firstnumber={first},numbers=left,numberstyle=\\tiny\\ttfamily,numbersep=5pt]\n")
        for rel, lineno, content in page:
            parts.append(f"{rel}:{lineno}\t{content}\n")
        parts.append("\\end{lstlisting}\n")
        parts.append("\\clearpage\n")
    parts.append("\\end{document}\n")
    path.write_text("".join(parts), encoding="utf-8")


def compile_tex(tex: Path) -> None:
    if not TECTONIC.exists():
        print(f"skip compile: {TECTONIC} not found")
        return
    subprocess.run([str(TECTONIC), tex.name], cwd=tex.parent, check=True)


def main() -> None:
    lines = collect_lines()
    pages = [lines[i : i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)]
    print(f"files total lines={len(lines)} pages={len(pages)}")
    first = pages[:PAGES_PER_FILE]
    last = pages[-PAGES_PER_FILE:]
    last_start = len(pages) - PAGES_PER_FILE + 1

    src_dir = MATERIALS / "01_源代码"
    src_dir.mkdir(parents=True, exist_ok=True)
    write_legacy_txt(src_dir / "源代码_前30页.txt", first, 1)
    write_legacy_txt(src_dir / "源代码_后30页.txt", last, last_start)

    pkg_dir = MATERIALS / "05_完整申请文件包"
    write_legacy_txt(pkg_dir / "02_源程序_前30页_排版.txt", first, 1)
    write_legacy_txt(pkg_dir / "03_源程序_后30页_排版.txt", last, last_start)

    tex_dir = MATERIALS / "06_LaTeX排版"
    tex_dir.mkdir(parents=True, exist_ok=True)
    write_latex(tex_dir / "01_源程序_前30页.tex", first, 1)
    write_latex(tex_dir / "02_源程序_后30页.tex", last, last_start)
    compile_tex(tex_dir / "01_源程序_前30页.tex")
    compile_tex(tex_dir / "02_源程序_后30页.tex")

    manual_md = MATERIALS / "02_操作手册" / "Cloudra软件使用说明书.md"
    manual_lines = manual_md.read_text(encoding="utf-8").splitlines()
    manual_pages = [
        manual_lines[i : i + LINES_PER_PAGE] for i in range(0, len(manual_lines), LINES_PER_PAGE)
    ]
    write_manual_paginated(pkg_dir / "04_操作手册_排版.txt", manual_pages)
    print(f"manual pages={len(manual_pages)}")
    print("done")


def write_manual_paginated(path: Path, pages: list[list[str]]) -> None:
    out: list[str] = []
    for idx, page in enumerate(pages):
        out.append(page_header(idx + 1))
        out.append(SEP)
        out.extend(page)
    path.write_text("\n".join(out) + "\n\n\f", encoding="utf-8")


if __name__ == "__main__":
    main()
