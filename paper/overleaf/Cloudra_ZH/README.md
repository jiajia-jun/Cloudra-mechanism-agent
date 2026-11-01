# Cloudra ZH

Updated: 1 November 2026. Main file: main.tex. Compiler: XeLaTeX, TeX Live 2026.

Local architecture synchronization, 1 November 2026: Figure 4 uses `figures/Cloudra_Architecture_Stacked.pdf`, with its editable SVG alongside. The local PDF has 19 pages; architecture appears on page 3. Chengyi Yang is the first and corresponding author (`202509240114@csust.edu.cn`). These local files and source ZIPs include the final evaluation scores and current manuscript text. This local synchronization does not update the online Overleaf project.

Edit the chapter files in sections/, references in references.bib, and vector figures in figures/. LaTeX manages figure, equation, and citation numbering.

The manuscript contains the 48-run repeated-task study and the complete four-configuration, 50-task study (200 runs; 600 score components). Seven benchmark figure groups preserve the manuscript's existing visual style. The complete task matrix retains all 800 displayed values.

sections/03_figures.tex declares the wide result figures as native LaTeX floats. Results and discussion flow continuously in two columns; no manual page or column breaks separate their subsections. Existing diagnostic experiments remain in sections/03_results.tex.

The abstract and contributions foreground the correspondence between chemical intent, molecular identity, operations, and evidence. The benchmark evaluates research capabilities; the controlled local studies examine semantic correspondences in judgments and actions. Experimental facts and qualifications are retained. Previously stale scores, F4-related text, and shared benchmark figures now match the final English evaluation. The current local PDF was compiled with Tectonic 0.17.0 (19 pages).
