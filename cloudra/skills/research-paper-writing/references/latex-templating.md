# LaTeX Journal Template Guide

## Overview

This guide helps you format your paper for specific journal templates. The workflow:
1. Obtain the journal template
2. Understand template structure
3. Convert your content to match
4. Compile and verify

## Common Journal Templates

### IEEE (Transactions, Conferences)

**Template source**: https://template-selector.ieee.org/

**Document class**:
```latex
\documentclass[conference]{IEEEtran}  % Conference
\documentclass[journal]{IEEEtran}     % Journal
```

**Required packages**:
```latex
\usepackage{cite}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage{textcomp}
\usepackage{xcolor}
\usepackage{booktabs}
```

**Title/Author format**:
```latex
\title{Paper Title}

\author{
\IEEEauthorblockN{Author One\IEEEauthorrefmark{1},
Author Two\IEEEauthorrefmark{2},
Author Three\IEEEauthorrefmark{1}}
\IEEEauthorblockA{\IEEEauthorrefmark{1}Department of Computer Science\\
University Name\\
Email: \{one, three\}@university.edu}
\IEEEauthorblockA{\IEEEauthorrefmark{2}Research Institute\\
Organization Name\\
Email: two@institute.org}
}
```

**Bibliography**:
```latex
\bibliographystyle{IEEEtran}
\bibliography{references}
```

**Key rules**:
- Two-column format
- Numbered references [1], [2], etc.
- Figures/tables span one column unless specified
- Use `\cite{}` for citations

### Springer (Nature, Scientific Reports)

**Template source**: https://www.nature.com/documents/nature-summary-paragraph.pdf

**Document class**:
```latex
\documentclass[fleqn,10pt]{wlscirep}  % Scientific Reports
\documentclass{article}               % Generic Springer
```

**Required packages**:
```latex
\usepackage{graphicx}
\usepackage{color}
\usepackage{booktabs}
\usepackage{multirow}
\usepackage{supertabular}
\usepackage{algorithm}
```

**Title/Author format**:
```latex
\title{Paper Title}

\author[1]{Author One}
\author[2]{Author Two}
\author[1,2,*]{Author Three}

\affil[1]{Department of X, University Y}
\affil[2]{Institute Z}
\affil[*]{Corresponding author: email@university.edu}
```

**Bibliography**:
```latex
\bibliographystyle{naturemag}
\bibliography{references}
```

**Key rules**:
- Single-column format
- Author-year citations (Author et al., Year)
- Extended data figures/tables separate from main text
- Methods section at end (for some journals)

### Elsevier (Various Journals)

**Template source**: https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions

**Document class**:
```latex
\documentclass[preprint,12pt]{elsarticle}  % Preprint
\documentclass[final,5p]{elsarticle}      % Final (5 pages)
\documentclass[final,3p]{elsarticle}      % Final (3 pages)
```

**Required packages**:
```latex
\usepackage{lineno}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{multirow}
```

**Title/Author format**:
```latex
\title{Paper Title}

\author[1]{Author One\corref{cor1}}
\author[2]{Author Two}
\cortext[cor1]{Corresponding author}
\ead{email@university.edu}

\affiliation[1]{organization={Department of X, University Y},
                city={City},
                country={Country}}
\affiliation[2]{organization={Institute Z},
                city={City},
                country={Country}}
```

**Bibliography**:
```latex
\bibliographystyle{elsarticle-num}  % Numeric
\bibliographystyle{elsarticle-harv} % Author-year
\bibliography{references}
```

**Key rules**:
- Line numbers in review mode
- Highlights for review (optional)
- Graphical abstract (optional)
- CRediT author statement required

### ACM (Conference Proceedings)

**Template source**: https://www.acm.org/publications/proceedings-template

**Document class**:
```latex
\documentclass[sigconf,review]{acmart}  % Conference
\documentclass[sigplan]{acmart}         % SIGPLAN
\documentclass[acmsmall]{acmart}        % Journal
```

**Required packages**:
```latex
% ACM template includes most packages
\usepackage{booktabs}
\usepackage{multirow}
```

**Title/Author format**:
```latex
\title{Paper Title}

\author{Author One}
\affiliation{%
  \institution{University Y}
  \city{City}
  \country{Country}
}
\email{one@university.edu}

\author{Author Two}
\affiliation{%
  \institution{Institute Z}
  \city{City}
  \country{Country}
}
\email{two@institute.org}
```

**Bibliography**:
```latex
\bibliographystyle{ACM-Reference-Format}
\bibliography{references}
```

**Key rules**:
- CCS concepts required
- ACM reference format
- Author rights management
- Badges for reproducibility (optional)

### APA (Psychology, Social Sciences)

**Document class**:
```latex
\documentclass[man,12pt]{apa7}  % Manuscript
\documentclass[doc,12pt]{apa7}  % Document
\documentclass[jou,12pt]{apa7}  % Journal
```

**Required packages**:
```latex
\usepackage{apacite}
\usepackage{graphicx}
\usepackage{booktabs}
```

**Title/Author format**:
```latex
\title{Paper Title}
\shorttitle{Short Title}

\author{Author One}
\affiliation{Department of X, University Y}

\author{Author Two}
\affiliation{Institute Z}

\leftheader{One, Two}
```

**Bibliography**:
```latex
\bibliographystyle{apacite}
\bibliography{references}
```

**Key rules**:
- Author-year citations
- Running head
- Abstract 150-250 words
- Keywords after abstract

## Template Conversion Checklist

### Step 1: Obtain Template

```bash
# Download from journal website
# Or use CTAN:
texdoc <package-name>  # View documentation
```

### Step 2: Identify Requirements

Check these in the template:
- [ ] Document class and options
- [ ] Required packages
- [ ] Title/author format
- [ ] Section numbering style
- [ ] Reference format
- [ ] Figure/table format
- [ ] Page layout (single/double column)
- [ ] Word/page limits

### Step 3: Convert Content

**Document class**:
```latex
% Change from generic:
\documentclass{article}

% To journal-specific:
\documentclass[conference]{IEEEtran}
```

**Packages**:
```latex
% Add journal-specific packages
\usepackage{cite}           % IEEE
\usepackage{natbib}         % Author-year styles
\usepackage{lineno}         % For review mode
```

**Title/Author**:
```latex
% Follow journal format exactly
% Check sample/template files
```

**Sections**:
```latex
% Some templates use different section commands
\section{}      % Standard
\chapter{}      % Book-style
\paragraph{}    % No numbering
```

**References**:
```latex
% Match journal style
\bibliographystyle{IEEEtran}    % IEEE numeric
\bibliographystyle{apalike}     % Author-year
\bibliographystyle{naturemag}   % Nature style
```

### Step 4: Compile

```bash
# Standard compilation
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex

# Or use latexmk
latexmk -pdf main.tex

# For Elsevier (requires multiple passes)
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
pdflatex main.tex  # Extra pass for line numbers
```

## Pandoc Conversion

### Basic Conversion

```bash
# Markdown to LaTeX
pandoc paper.md -o paper.tex --standalone

# With bibliography
pandoc paper.md -o paper.tex --bibliography=refs.bib --citeproc

# With template
pandoc paper.md -o paper.tex --template=IEEEtran.latex
```

### Custom Template

Create `IEEEtran.latex`:
```latex
\documentclass[conference]{IEEEtran}
\usepackage{cite}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage{textcomp}
\usepackage{xcolor}

$if(title)$
\title{$title$
$endif$

$if(author)$
\author{
$for(author)$
$author.name$\\$author.affiliation$\\$author.email$
$endfor$
}
$endif$

\begin{document}

$if(title)$
\maketitle
$endif$

$if(abstract)$
\begin{abstract}
$abstract$
\end{abstract}
$endif$

$body$

\bibliographystyle{IEEEtran}
\bibliography{$bibliography$}

\end{document}
```

Use with:
```bash
pandoc paper.md -o paper.tex --template=IEEEtran.latex --bibliography=refs.bib
```

### Batch Conversion

```bash
#!/bin/bash
# convert.sh - Convert markdown files to LaTeX

for file in *.md; do
    base=$(basename "$file" .md)
    pandoc "$file" -o "${base}.tex" \
        --template=IEEEtran.latex \
        --bibliography=refs.bib \
        --citeproc
    echo "Converted: $file -> ${base}.tex"
done
```

## Common Adjustments

### Single-Column vs Double-Column Layout

**Common double-column templates**: IEEE, ACM, Elsevier (some), Springer (some)

**Document class options**:
```latex
% IEEE - single column for review, double column for final
\documentclass[review]{IEEEtran}     % Single column + line numbers
\documentclass[conference]{IEEEtran} % Double column
\documentclass[journal]{IEEEtran}    % Double column

% ACM
\documentclass[sigconf]{acmart}      % Double column
\documentclass[acmsmall]{acmart}     % Single column
```

### Figures in Double-Column Papers

```latex
% Single column figure (fits in one column)
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{figures/method.pdf}
\caption{Method overview.}
\label{fig:method}
\end{figure}

% Double column figure (spans both columns)
\begin{figure*}[t]
\centering
\includegraphics[width=\textwidth]{figures/results.pdf}
\caption{Results across all datasets.}
\label{fig:results}
\end{figure*}

% Double column figure with specific width
\begin{figure*}[t]
\centering
\includegraphics[width=0.85\textwidth]{figures/pipeline.pdf}
\caption{Overall pipeline.}
\label{fig:pipeline}
\end{figure*}
```

**Placement rules**:
- `[t]` = top of page (preferred)
- `[b]` = bottom of page
- `[h]` = here (use sparingly)
- `[!]` = override float restrictions
- `figure*`/`table*` only work with `[t]` or `[b]` in double-column

### Tables in Double-Column Papers

```latex
% Single column table
\begin{table}[t]
\centering
\caption{Comparison with baselines.}
\label{tab:results}
\begin{tabular}{lccc}
\toprule
Method & Metric1 & Metric2 & Metric3 \\
\midrule
Baseline1 & 0.85 & 0.72 & 0.91 \\
Baseline2 & 0.87 & 0.74 & 0.93 \\
Ours & \textbf{0.92} & \textbf{0.81} & \textbf{0.96} \\
\bottomrule
\end{tabular}
\end{table}

% Double column table (spans both columns)
\begin{table*}[t]
\centering
\caption{Comprehensive comparison across multiple datasets.}
\label{tab:results-full}
\begin{tabular}{lcccccc}
\toprule
 & \multicolumn{2}{c}{Dataset A} & \multicolumn{2}{c}{Dataset B} & \multicolumn{2}{c}{Dataset C} \\
\cmidrule(lr){2-3} \cmidrule(lr){4-5} \cmidrule(lr){6-7}
Method & PSNR $\uparrow$ & SSIM $\uparrow$ & PSNR $\uparrow$ & SSIM $\uparrow$ & PSNR $\uparrow$ & SSIM $\uparrow$ \\
\midrule
Baseline1 & 28.5 & 0.85 & 30.2 & 0.88 & 27.1 & 0.82 \\
Baseline2 & 29.1 & 0.87 & 30.8 & 0.89 & 27.5 & 0.84 \\
Ours & \textbf{30.2} & \textbf{0.91} & \textbf{31.5} & \textbf{0.92} & \textbf{28.3} & \textbf{0.87} \\
\bottomrule
\end{tabular}
\end{table*}
```

### When to Use Double-Column Figures/Tables

Use `figure*`/`table*` when:
- Content is too wide for single column
- Need to show many columns (multiple datasets/metrics)
- Pipeline/overview figures that benefit from full width
- Detailed comparison tables

Use `figure`/`table` when:
- Simple figures (single image)
- Small tables (2-4 columns)
- Content fits comfortably in one column

### Width Reference

```latex
% Useful width values
\columnwidth     % Width of one column
\textwidth       % Full page width (both columns + gap)
\linewidth       % Width of current line environment

% For double-column papers:
% \textwidth ≈ 2 * \columnwidth + column_gap

% Common usage
\includegraphics[width=\columnwidth]{...}      % Full single column
\includegraphics[width=\textwidth]{...}         % Full double column
\includegraphics[width=0.45\columnwidth]{...}   % Half column
\includegraphics[width=0.48\textwidth]{...}     % Side-by-side in double column
```

### Side-by-Side Figures in Double Column

```latex
% Two figures side by side (single column)
\begin{figure}[t]
\centering
\begin{subfigure}[b]{0.45\columnwidth}
    \includegraphics[width=\textwidth]{fig1.pdf}
    \caption{Input}
    \label{fig:input}
\end{subfigure}
\hfill
\begin{subfigure}[b]{0.45\columnwidth}
    \includegraphics[width=\textwidth]{fig2.pdf}
    \caption{Output}
    \label{fig:output}
\end{subfigure}
\caption{Comparison of input and output.}
\label{fig:comparison}
\end{figure}

% Two figures side by side (double column)
\begin{figure*}[t]
\centering
\begin{subfigure}[b]{0.48\textwidth}
    \includegraphics[width=\textwidth]{fig1.pdf}
    \caption{Method A}
    \label{fig:method-a}
\end{subfigure}
\hfill
\begin{subfigure}[b]{0.48\textwidth}
    \includegraphics[width=\textwidth]{fig2.pdf}
    \caption{Method B}
    \label{fig:method-b}
\end{subfigure}
\caption{Comparison of methods.}
\label{fig:methods}
\end{figure*}
```

**Note**: For `subfigure`, add `\usepackage{subcaption}` to preamble.

### Equations

```latex
% Inline
$E = mc^2$

% Display
\begin{equation}
\mathcal{L} = \sum_{i=1}^{N} \ell(f(x_i), y_i)
\label{eq:loss}
\end{equation}

% Multi-line (IEEE)
\begin{align}
\frac{\partial L}{\partial w} &= \frac{\partial L}{\partial z} \cdot \frac{\partial z}{\partial w} \\
&= \delta \cdot x
\end{align}
```

### Algorithms

```latex
% Using algorithm2e
\usepackage[ruled,vlined]{algorithm2e}

\begin{algorithm}[t]
\caption{Training procedure}
\label{alg:training}
\KwIn{Dataset $\mathcal{D}$, learning rate $\eta$}
\KwOut{Trained model $f_\theta$}
Initialize $\theta$\;
\For{epoch $= 1$ to $T$}{
    \For{batch $(x,y) \in \mathcal{D}$}{
        Compute loss $\ell = \mathcal{L}(f_\theta(x), y)$\;
        Update $\theta \leftarrow \theta - \eta \nabla_\theta \ell$\;
    }
}
\Return $f_\theta$\;
\end{algorithm}
```

## Verification Checklist

Before submission, verify:

- [ ] Document class matches journal requirements
- [ ] All required packages are included
- [ ] Title/author format is correct
- [ ] Citations use correct format
- [ ] References match journal style
- [ ] Figures/tables are properly formatted
- [ ] Page limits are respected
- [ ] Line numbers enabled (if required)
- [ ] Supplementary material formatted correctly
- [ ] Acknowledgments section included
- [ ] Data availability statement (if required)
- [ ] Author contributions (if required)

## Quick Reference: Journal Commands

| Journal | Document Class | Bibliography Style |
|---------|---------------|-------------------|
| IEEE | `\documentclass{IEEEtran}` | `\bibliographystyle{IEEEtran}` |
| Nature | `\documentclass{article}` | `\bibliographystyle{naturemag}` |
| Elsevier | `\documentclass{elsarticle}` | `\bibliographystyle{elsarticle-num}` |
| ACM | `\documentclass{acmart}` | `\bibliographystyle{ACM-Reference-Format}` |
| APA | `\documentclass{apa7}` | `\bibliographystyle{apacite}` |
| Springer | `\documentclass{svjour3}` | `\bibliographystyle{spbasic}` |
