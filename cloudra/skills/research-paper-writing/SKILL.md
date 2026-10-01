---
name: research-paper-writing
description: Guide academic paper writing from draft to publication-ready format. Covers storytelling structure, Markdown/LaTeX typesetting for journal templates, command-line formatting tools, and section-level refinement. Use when drafting, revising, or formatting any academic paper section.
license: MIT
---

# Research Paper Writing

## Overview

This skill covers drafting and typesetting papers. The Writer can read and write source files but cannot execute commands. For Pandoc conversion, LaTeX compilation, or package installation, the Writer sends the source path and requested output to the Coordinator or an agent with command execution access.

**Core workflow:**
1. Clarify the paper story (what, why, how, evidence)
2. Draft content in Markdown for rapid iteration
3. Convert and typeset to LaTeX journal template with an agent that can run commands
4. Align formatting
5. Run adversarial self-review before submission

## How to Tell a Story (Critical)

Every paper tells a story. Before writing, answer these questions:

### The Four-Act Structure

1. **Setup**: What problem exists and why does it matter?
   - Define the task clearly
   - Establish real-world importance
   
2. **Conflict**: Why is this problem hard? What have others tried?
   - Previous approaches and their limitations
   - The technical challenge that remains
   
3. **Resolution**: What did you do differently?
   - Your key insight or innovation
   - Why this approach works in principle
   
4. **Proof**: Does it actually work?
   - Experimental evidence
   - Comparison with alternatives

### Story Checklist

- [ ] Can you explain your paper in one sentence?
- [ ] Can you explain it in 30 seconds (elevator pitch)?
- [ ] Does each section advance the narrative?
- [ ] Is the logical flow: problem → challenge → solution → proof?
- [ ] Would a non-expert understand why this matters?

### Common Story Patterns

**Pattern A: Incremental improvement**
- "X works well but fails in case Y. We fix this by Z."

**Pattern B: New capability**
- "Nobody has done X. We show it's possible and useful."

**Pattern C: Unifying framework**
- "Methods A, B, C seem different but share insight X. We exploit this."

**Pattern D: Contrarian insight**
- "Everyone assumes X. We show Y works better because Z."

## Markdown Drafting Workflow

Write in Markdown first for rapid iteration. Use this structure:

### Basic Document Structure

```markdown
# Title

## Abstract
[150-250 words summarizing problem, approach, key results]

## 1. Introduction
[Story setup, problem importance, your contribution]

## 2. Related Work
[Position against existing work]

## 3. Method
[Your approach in detail]

## 4. Experiments
[Results, ablations, analysis]

## 5. Conclusion
[Summary, limitations, future work]

## References
```

### Writing Rules

1. **One paragraph, one message**: First sentence states the message
2. **Paragraph order**: Topic sentence → evidence → explanation → transition
3. **Sentence flow**: Each sentence connects to previous (cause/contrast/consequence/refinement)
4. **Term consistency**: Define once, use consistently

### Markdown-to-LaTeX Conversion Preparation

When your draft is ready for typesetting:

1. Ensure all sections use consistent heading levels
2. Mark figures/tables with clear placeholders
3. Use standard citation format: `[@author2024]` or `\cite{author2024}`
4. Add LaTeX math delimiters: `$inline$` and `$$display$$`

## LaTeX Journal Template Formatting

### Step 1: Obtain the Template

```bash
# Download journal template (example: IEEE)
wget https://template-selector.ieee.org/secure/templates
unzip IEEE-conference-template.zip

# Or use CTAN packages for common formats
# For article class (most journals):
texdoc article  # View documentation
```

### Step 2: Identify Template Requirements

Check these files in the template:
- `*.cls` or `*.sty`: Style definitions
- `sample.tex` or `main.tex`: Example structure
- `README` or `instructions.pdf`: Author guidelines

Key things to note:
- Document class and required packages
- Section numbering style
- Reference format (numeric vs author-year)
- Figure/table placement rules
- Page/column layout

### Step 3: Convert Markdown to LaTeX

Use **Pandoc** for conversion:

```bash
# Basic conversion
pandoc paper.md -o paper.tex --standalone

# With bibliography
pandoc paper.md -o paper.tex --bibliography=refs.bib --citeproc

# Specify output format for two-column
pandoc paper.md -o paper.tex --template=ieeetran.latex

# Preserve math
pandoc paper.md -o paper.tex --mathjax
```

### Step 4: Align with Template

After conversion, manually adjust:

1. **Document class**: Replace with journal's class
   ```latex
   % Change from:
   \documentclass{article}
   % To (example IEEE):
   \documentclass[conference]{IEEEtran}
   ```

2. **Required packages**: Add journal-specific packages
   ```latex
   \usepackage{cite}           % IEEE
   \usepackage{amsmath}        % Math
   \usepackage{graphicx}       % Figures
   \usepackage{booktabs}       % Professional tables
   ```

3. **Title/Author format**: Follow journal style
   ```latex
   % IEEE example:
   \title{Your Paper Title}
   \author{
   \IEEEauthorblockN{Author One}
   \IEEEauthorblockA{Department\\University\\email}
   }
   ```

4. **Bibliography style**: Match journal requirements
   ```latex
   % Numeric style (Nature, Science)
   \bibliographystyle{naturemag}
   
   % Author-year (APA journals)
   \bibliographystyle{apalike}
   
   % IEEE style
   \bibliographystyle{IEEEtran}
   ```

## Command-Line Formatting Tools

### Pandoc: The Universal Document Converter

```bash
# Install pandoc
# Ubuntu/Debian:
sudo apt install pandoc

# macOS:
brew install pandoc

# Convert Markdown to LaTeX
pandoc input.md -o output.tex

# Convert with custom template
pandoc input.md -o output.tex --template=my-template.latex

# Convert LaTeX to PDF (requires LaTeX installed)
pandoc input.tex -o output.pdf

# Batch convert multiple files
for f in *.md; do pandoc "$f" -o "${f%.md}.tex"; done
```

### LaTeX Compilation

```bash
# Standard compilation (handles references)
pdflatex paper.tex
bibtex paper
pdflatex paper.tex
pdflatex paper.tex

# Or use latexmk for automatic handling
latexmk -pdf paper.tex

# Watch mode (recompile on changes)
latexmk -pdf -pvc paper.tex

# Clean auxiliary files
latexmk -C
```

### Reference Management

```bash
# Convert BibTeX formats
# From DOI:
curl -LH "Accept: application/x-bibtex" https://doi.org/10.xxxx/xxxxx > ref.bib

# From Zotero/BibTeX to journal format
# Use bibtool
bibtool -i input.bib -o output.bib -s  # Sort

# Check for duplicate keys
bibtool -i refs.bib -d
```

### Table Formatting

```bash
# CSV to LaTeX table
# Using csv2latex (install: pip install csv2latex)
csv2latex data.csv > table.tex

# Or using Miller + manual formatting
mlr --csv cut -f col1,col2 data.csv | \
  awk -F, 'BEGIN{print "\\begin{tabular}{ll}"} 
  {print $1 " & " $2 " \\\\"} 
  END{print "\\end{tabular}"}'
```

### Figure Preparation

```bash
# Convert figures to appropriate format
# PDF to EPS (for older LaTeX)
pdftops -eps figure.pdf figure.eps

# PNG to PDF (better for LaTeX)
convert figure.png figure.pdf

# Resize and crop
convert input.png -resize 800x600 -trim output.png

# Batch conversion
for f in *.png; do convert "$f" "${f%.png}.pdf"; done
```

### Word Count

```bash
# Count words in LaTeX (excluding commands)
detex paper.tex | wc -w

# Using texcount (more accurate)
texcount paper.tex

# Count only main text (no references)
texcount -inc -incbib paper.tex
```

## Section-Specific Writing Guides

Load only the section you're working on:

| Section | Guide File |
|---------|------------|
| Abstract | `references/abstract.md` |
| Introduction | `references/introduction.md` |
| Related Work | `references/related-work.md` |
| Method | `references/method.md` |
| Experiments | `references/experiments.md` |
| Conclusion | `references/conclusion.md` |
| Storytelling | `references/storytelling.md` |
| LaTeX Templates | `references/latex-templating.md` |
| Command-Line Tools | `references/command-line-tools.md` |

## Paragraph Clarity Check

Use this test for any paragraph:

1. **Read as external reader**:
   - Does this paragraph have one explicit message?
   - Does the first sentence state what this paragraph will do?
   - Are all key terms readable without hidden context?
   - Does each sentence connect to previous one?

2. **Reverse outlining**:
   - Write down thesis/main claim
   - Write down each paragraph's topic sentence
   - Check: topic sentence → thesis, evidence → topic sentence
   - Revise or remove unmappable paragraphs

## Execution Rules

1. Build a mini-outline before drafting prose
2. For each subsection, include: motivation, design, technical advantage
3. Keep terminology stable across the full paper
4. If a claim lacks evidence, weaken or remove it
5. Use consistent formatting throughout
6. Load only the section guide needed for current work

## Output Contract

When revising or drafting sections, return:

1. A compact section outline (3-7 bullets)
2. Revised paragraphs with explicit roles
3. Self-review checklist (clarity, flow, terminology, claims)
4. Claim-evidence map: `Claim: ... | Evidence: ... | Status: supported/needs evidence`

## Paper Review

Use `references/paper-review.md` for adversarial review checklist.

Core review dimensions:
1. **Contribution**: Is the novelty clear and significant?
2. **Writing**: Is it reproducible and clear?
3. **Experiments**: Are gains meaningful and consistent?
4. **Evaluation**: Are ablations and baselines complete?
5. **Method**: Is the design sound and robust?

## Quick Commands Reference

```bash
# Full workflow example
pandoc draft.md -o draft.tex                    # Convert to LaTeX
# Edit draft.tex to match journal template
pdflatex draft.tex && bibtex draft && pdflatex draft.tex  # Compile
latexmk -pvc draft.tex                          # Watch mode
detex draft.tex | wc -w                         # Word count
```

## File Organization

```
paper/
├── main.tex              # Main LaTeX file
├── references.bib        # Bibliography
├── figures/              # Figure files
│   ├── method.pdf
│   └── results.png
├── sections/             # Section files (if using \input)
│   ├── introduction.tex
│   ├── method.tex
│   └── experiments.tex
├── draft.md              # Markdown draft
└── Makefile              # Build automation
```

## Makefile Template

```makefile
PAPER = main
LATEX = pdflatex
BIBTEX = bibtex

all: $(PAPER).pdf

$(PAPER).pdf: $(PAPER).tex references.bib
	$(LATEX) $(PAPER)
	$(BIBTEX) $(PAPER)
	$(LATEX) $(PAPER)
	$(LATEX) $(PAPER)

clean:
	rm -f *.aux *.log *.bbl *.blg *.toc *.out *.fls *.fdb_latexmk

watch:
	latexmk -pdf -pvc $(PAPER)

.PHONY: all clean watch
```
