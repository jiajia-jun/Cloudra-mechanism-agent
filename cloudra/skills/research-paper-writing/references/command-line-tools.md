# Command-Line Tools for Paper Writing

## Overview

This guide covers essential command-line tools for academic paper writing, from document conversion to formatting and automation.

## Installation

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install pandoc texlive-full latexmk biber
```

### macOS

```bash
brew install pandoc mactex-no-gui latexmk
```

### Windows (WSL)

```bash
sudo apt update
sudo apt install pandoc texlive-full latexmk
```

## Pandoc: Universal Document Converter

### Basic Conversions

```bash
# Markdown to LaTeX
pandoc paper.md -o paper.tex

# Markdown to PDF (requires LaTeX)
pandoc paper.md -o paper.pdf

# Markdown to HTML
pandoc paper.md -o paper.html

# LaTeX to Markdown
pandoc paper.tex -o paper.md

# Word to Markdown
pandoc paper.docx -o paper.md
```

### With Options

```bash
# Standalone document (with preamble)
pandoc paper.md -o paper.tex --standalone

# With bibliography
pandoc paper.md -o paper.tex --bibliography=refs.bib --citeproc

# With custom template
pandoc paper.md -o paper.tex --template=IEEEtran.latex

# Specify metadata
pandoc paper.md -o paper.tex \
  --metadata title="Paper Title" \
  --metadata author="Author Name"

# Number sections
pandoc paper.md -o paper.tex --number-sections

# Table of contents
pandoc paper.md -o paper.tex --toc
```

### Pandoc Templates

Create custom template `ieee.latex`:
```latex
\documentclass[conference]{IEEEtran}
\usepackage{cite}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}

$if(title)$
\title{$title$
$endif$

$if(author)$
\author{
$for(author)$
\IEEEauthorblockN{$author.name$}
\IEEEauthorblockA{$author.affiliation$}
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
pandoc paper.md -o paper.tex --template=ieee.latex --bibliography=refs.bib
```

### Batch Conversion

```bash
#!/bin/bash
# convert_all.sh

for file in *.md; do
    base=$(basename "$file" .md)
    pandoc "$file" -o "${base}.tex" \
        --template=IEEEtran.latex \
        --bibliography=refs.bib \
        --citeproc
    echo "Converted: $file"
done
```

## LaTeX Compilation

### Basic Compilation

```bash
# Standard sequence (handles cross-references)
pdflatex paper.tex
bibtex paper
pdflatex paper.tex
pdflatex paper.tex

# With biber (for biblatex)
pdflatex paper.tex
biber paper
pdflatex paper.tex
pdflatex paper.tex
```

### Latexmk: Automatic Compilation

```bash
# Compile to PDF
latexmk -pdf paper.tex

# Watch for changes and recompile
latexmk -pdf -pvc paper.tex

# Clean auxiliary files
latexmk -C

# Specify output directory
latexmk -pdf -outdir=build paper.tex
```

### Latexmk Configuration

Create `.latexmkrc`:
```perl
# Use pdflatex
$pdf_mode = 1;

# Custom pdflatex command (with shell-escape if needed)
$pdflatex = 'pdflatex -interaction=nonstopmode -shell-escape %O %S';

# Bibtex command
$bibtex_use = 2;

# Clean extensions
$clean_ext = 'bbl blg aux log out toc lot lof fls fdb_latexmk';
```

### Watch Mode Script

```bash
#!/bin/bash
# watch_and_compile.sh

FILE=${1:-paper.tex}

echo "Watching $FILE for changes..."
echo "Press Ctrl+C to stop"

while true; do
    inotifywait -e modify "$FILE" *.bib 2>/dev/null
    latexmk -pdf "$FILE" 2>&1 | tail -5
    echo "---"
done
```

## Bibliography Management

### BibTeX Tools

```bash
# Sort bibliography
bibtool -i refs.bib -o refs_sorted.bib -s

# Find duplicate keys
bibtool -i refs.bib -d

# Extract cited references
bibtool -x paper.aux -o cited_refs.bib

# Convert DOI to BibTeX
curl -LH "Accept: application/x-bibtex" \
  "https://doi.org/10.1234/example" > ref.bib

# Batch DOI to BibTeX
while read doi; do
    curl -sLH "Accept: application/x-bibtex" \
      "https://doi.org/$doi" >> refs.bib
    echo "" >> refs.bib
    sleep 1  # Rate limiting
done < dois.txt
```

### Zotero Integration

```bash
# Export from Zotero (requires Zotero running)
# Use Better BibTeX plugin for auto-export

# Or use command line (if Zotero CLI installed)
zotero-cli export --format bibtex --output refs.bib
```

### CrossRef API

```bash
# Search by title
curl -s "https://api.crossref.org/works?query=paper+title&rows=5" | \
  jq '.message.items[0].DOI'

# Get BibTeX from DOI
curl -sLH "Accept: application/x-bibtex" \
  "https://doi.org/10.1234/example"
```

## Table Processing

### CSV to LaTeX

```bash
# Using csv2latex (pip install csv2latex)
csv2latex data.csv > table.tex

# Using csvsimple package
# Add to preamble: \usepackage{csvsimple}
# Then use: \csvautotabular{data.csv}

# Custom conversion with awk
awk -F, 'BEGIN{
    print "\\begin{tabular}{|l|l|l|}"
    print "\\hline"
}
NR==1{
    for(i=1;i<=NF;i++) printf "%s%s", $i, (i<NF?" & ":" \\\\\\hline\\n")
}
NR>1{
    for(i=1;i<=NF;i++) printf "%s%s", $i, (i<NF?" & ":" \\\\\\hline\\n")
}
END{print "\\end{tabular}"}' data.csv
```

### LaTeX Table Formatting

```bash
# Convert vertical lines to booktabs
sed -i 's/\\hline/\\midrule/g; s/|//g' table.tex

# Add booktabs package
sed -i 's/\\begin{document}/\\usepackage{booktabs}\n\\begin{document}/' table.tex
```

## Figure Processing

### Image Conversion

```bash
# PNG to PDF (better for LaTeX)
convert figure.png figure.pdf

# PDF to EPS (for older systems)
pdftops -eps figure.pdf figure.eps

# Resize images
convert input.png -resize 800x600 output.png

# Crop whitespace
convert input.png -trim output.png

# Batch conversion
for f in *.png; do
    convert "$f" "${f%.png}.pdf"
done
```

### Figure Optimization

```bash
# Compress PDF
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.4 \
   -dPDFSETTINGS=/screen -dNOPAUSE -dQUIET -dBATCH \
   -sOutputFile=output.pdf input.pdf

# Optimize PNG
optipng -o5 figure.png

# Convert to grayscale
convert input.png -colorspace Gray output.png
```

## Word Count and Analysis

### LaTeX Word Count

```bash
# Count words (excluding LaTeX commands)
detex paper.tex | wc -w

# Using texcount (more accurate)
texcount paper.tex

# Count only main text
texcount -inc -incbib paper.tex

# Summary only
texcount -inc -sum paper.tex

# Output in different formats
texcount -inc -sum -q paper.tex
```

### Pandoc Word Count

```bash
# Count words in markdown
wc -w paper.md

# Using pandoc
pandoc paper.md -t plain | wc -w
```

## Diff and Version Control

### LaTeX Diff

```bash
# Install latexdiff
sudo apt install latexdiff  # or brew install latexdiff

# Compare two versions
latexdiff old.tex new.tex > diff.tex

# Compile diff
pdflatex diff.tex

# With bibliography
latexdiff --bibtex old.tex new.tex > diff.tex
pdflatex diff.tex
bibtex diff
pdflatex diff.tex
pdflatex diff.tex
```

### Git for Papers

```bash
# Initialize repository
git init
git add *.tex *.bib *.pdf figures/
git commit -m "Initial draft"

# Track changes
git add -p  # Stage specific changes
git diff --word-diff  # Word-level diff

# Create branches for revisions
git checkout -b reviewer-response
# Make changes
git commit -m "Address reviewer comments"
git checkout main
git merge reviewer-response
```

## Automation with Makefile

### Basic Makefile

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

wordcount:
	texcount -inc -sum $(PAPER).tex

diff:
	latexdiff old.tex new.tex > diff.tex
	$(LATEX) diff.tex

.PHONY: all clean watch wordcount diff
```

### Advanced Makefile

```makefile
PAPER = main
LATEX = pdflatex
BIBTEX = bibtex
BIBER = biber

# Source files
TEX_FILES = $(wildcard sections/*.tex)
BIB_FILE = references.bib
FIGURES = $(wildcard figures/*)

# Output directory
BUILD_DIR = build

all: $(BUILD_DIR)/$(PAPER).pdf

$(BUILD_DIR)/$(PAPER).pdf: $(PAPER).tex $(TEX_FILES) $(BIB_FILE) $(FIGURES)
	@mkdir -p $(BUILD_DIR)
	$(LATEX) -output-directory=$(BUILD_DIR) $(PAPER)
	cd $(BUILD_DIR) && $(BIBTEX) $(PAPER)
	$(LATEX) -output-directory=$(BUILD_DIR) $(PAPER)
	$(LATEX) -output-directory=$(BUILD_DIR) $(PAPER)

clean:
	rm -rf $(BUILD_DIR)
	rm -f *.aux *.log *.bbl *.blg *.toc *.out

watch:
	latexmk -pdf -pvc -outdir=$(BUILD_DIR) $(PAPER)

wordcount:
	@texcount -inc -sum -q $(PAPER).tex

diff:
	@if [ -f old.tex ]; then \
		latexdiff old.tex new.tex > diff.tex; \
		$(LATEX) diff.tex; \
	else \
		echo "old.tex not found"; \
	fi

.PHONY: all clean watch wordcount diff
```

## Shell Scripts for Common Tasks

### Create New Paper

```bash
#!/bin/bash
# new_paper.sh

PAPER_NAME=${1:-paper}
TEMPLATE=${2:-IEEE}

mkdir -p "$PAPER_NAME"/{sections,figures}
cd "$PAPER_NAME"

# Create main.tex
cat > main.tex << 'EOF'
\documentclass[conference]{IEEEtran}
\usepackage{cite}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage{booktabs}

\title{Paper Title}

\author{
\IEEEauthorblockN{Author Name}
\IEEEauthorblockA{Department\\University\\email}
}

\begin{document}
\maketitle

\begin{abstract}
Your abstract here.
\end{abstract}

\input{sections/introduction}
\input{sections/related_work}
\input{sections/method}
\input{sections/experiments}
\input{sections/conclusion}

\bibliographystyle{IEEEtran}
\bibliography{references}

\end{document}
EOF

# Create section files
for section in introduction related_work method experiments conclusion; do
    echo "\\section{${section^}}" > "sections/$section.tex"
    echo "" >> "sections/$section.tex"
done

# Create references.bib
touch references.bib

# Create Makefile
cat > Makefile << 'EOF'
PAPER = main
all: $(PAPER).pdf
$(PAPER).pdf: $(PAPER).tex
	pdflatex $(PAPER)
	bibtex $(PAPER)
	pdflatex $(PAPER)
	pdflatex $(PAPER)
clean:
	rm -f *.aux *.log *.bbl *.blg
EOF

echo "Created paper structure in $PAPER_NAME/"
```

### Batch Process Papers

```bash
#!/bin/bash
# batch_compile.sh

for dir in */; do
    if [ -f "$dir/main.tex" ]; then
        echo "Compiling: $dir"
        cd "$dir"
        latexmk -pdf main.tex 2>&1 | tail -3
        cd ..
    fi
done
```

## Common Issues and Solutions

### Missing Packages

```bash
# Find package location
kpsewhich package.sty

# Install missing package (TeX Live)
tlmgr install package-name

# List installed packages
tlmgr list --only-installed
```

### Font Issues

```bash
# List available fonts
fc-list | grep -i "font name"

# Update font cache
fc-cache -fv
```

### Encoding Issues

```bash
# Convert encoding
iconv -f ISO-8859-1 -t UTF-8 input.tex > output.tex

# Check encoding
file -i paper.tex
```

## Quick Reference

### Essential Commands

```bash
# Document conversion
pandoc input.md -o output.tex          # MD to LaTeX
pandoc input.md -o output.pdf          # MD to PDF
pandoc input.md -o output.html         # MD to HTML

# LaTeX compilation
pdflatex paper.tex                     # Compile
bibtex paper                           # Bibliography
latexmk -pdf paper.tex                 # Auto-compile
latexmk -pdf -pvc paper.tex            # Watch mode

# Bibliography
bibtool -i refs.bib -o sorted.bib -s  # Sort
curl -LH "Accept: application/x-bibtex" "https://doi.org/..." > ref.bib

# Word count
detex paper.tex | wc -w               # Quick count
texcount -inc paper.tex               # Detailed count

# Diff
latexdiff old.tex new.tex > diff.tex  # Compare versions
```

### Environment Variables

```bash
# Set TEXINPUTS for custom packages
export TEXINPUTS="./styles//:$TEXINPUTS"

# Set BIBINPUTS for bibliography
export BIBINPUTS="./refs//:$BIBINPUTS"
```
