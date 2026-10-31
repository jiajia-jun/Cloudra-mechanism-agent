"""Insert the P2 evidence figures and bilingual results into the current Overleaf sources."""
from pathlib import Path
import json,shutil,zipfile
ROOT=Path(__file__).resolve().parents[2]
DRAFT=Path('/private/tmp/cloudra_paper_update/manuscript_map')
FIG=ROOT/'paper/figures/benchmark_p2_20261031'
ARCH=ROOT/'paper/archive/20261031_pre_p2'
ARCH.mkdir(parents=True,exist_ok=True)
FIGURES=[('bench_overview','bench-overview'),('bench_components','bench-components'),('bench_delivery','bench-delivery'),('bench_speed','bench-speed'),('bench_tasks','bench-tasks'),('bench_tasks_hi','bench-tasks-hi'),('bench_cases','bench-cases'),('bench_imp','bench-imp')]
ZH={
'bench_overview':'P2 主比较与逐题差异。a，Cloudra Guided 与同一 backbone 的 Standard 基线在全部 50 题及各难度层的整理后复合分；Easy 为 20 题，其余各 10 题。b，保留全部 50 个同题配对。c，配对均差与 100,000 次按任务整组 bootstrap 的 95% 百分位区间。',
'bench_components':'CloudraBench 的三个评分层。a--c，各配置、难度层的 Graph、自洽性和 Accuracy 均值，单元格同时给出可用分项数。分项使用 187 条有对应科学分量的运行；重构总分和缺分项的回填行分别在逐题图中保留标记。d，Guided 相对 Backbone 的现有 0.1/0.3/0.6 加权贡献，全部、Normal、Hard 分别使用 39、8、7 个可复算配对。',
'bench_delivery':'交付图与分级科学支持。a，50 题中的原始 root graph 记录，Standard 的 7 份审计重构用斜线单列。b，每配置 40 道非 Impossible 题的自洽分布，满分、分级部分分、缺图及缺分项分别保留。c，7 个 Standard 运行从自身记录重构后的总分，按题逐项呈现。',
'bench_speed':'运行速度与计算投入。a，P1b 的 12 个真实批次，每配置 3 批，每批 4 题，并发为 2；点为观测批次，短线为均值。b，P2 四配置共同 15 题的逐运行累计 QM job-hours 及均值。c，同一任务集每运行的完成、失败和取消作业数量。d，Standard 与 Guided 同题的计算投入及整理后总分，箭头连接相同任务，菱形标记审计重构。',
'bench_tasks':'Easy 20 题与 Normal 10 题的逐题分层成绩。每块均按 Guided、Backbone、Record、Brief 展示，依次为整理后总分、Graph、自洽性和 Accuracy。色标统一为 0--1；数字保留两位小数，来源表保留完整精度。† 表示审计恢复或手工引用整理；* 表示离线超时后保留原分。灰格保留缺失分项，Standard 原缺图行不以原始零分替代重构科学分量。',
'bench_tasks_hi':'Hard 10 题与 Impossible 10 题的逐题分层成绩。配置顺序、四个评分块、色标和来源标记与前图一致。逐题展示同时保留相同答案的证据差异、通道与目标判断的反转，以及整理后总分与原分项之间的对应范围。',
'bench_cases':'计算结果的科学归属。a，HA8 分别采用稳定极小值与反应性构象作参照的声明能垒，与 campaign Gold 并列。b，HH1 两组均给出 23.48 kcal/mol 能垒且准确度接近，自洽证据分不同。c，NU6 两个已记录能量之差为 18.836772 kcal/mol；Guided 将其保留为 concerted 鞍点区域的代价，并将目标闭环鞍点留为未解决，Standard 则将 18.837 声明为第二步闭环能垒。计算细节与路径文字取自归档证据记录。',
'bench_imp':'Impossible 层的逐题对照与 Brief--Guided 差异。a--c，10 题、四配置的整理后总分、自洽性和 Accuracy；Standard/IA9 自洽分项以灰格保留缺图状态。d，Brief 相对 Guided 的逐题总分差，IA1、IA9 与 IG8 展示交叉优势。e，均分差按 Graph、自洽性、Accuracy 的现有权重分解，总差为 +0.03788。Brief/IC3 包含手工引用整理，Standard/IA9 总分采用审计图；分项记录及目标判断在正文与讨论中分别解释。',
}

def caption_en(stem):
 text=(FIG/f'{stem}.caption.txt').read_text().strip()
 return text.replace('%',r'\%').replace('&',r'\&').replace('mol−1',r'mol$^{-1}$').replace('−', '-').replace('–','--')

def float_tex(stem,label,lang):
 cap=caption_en(stem) if lang=='EN' else ZH[stem].replace('%',r'\%')
 return '\n'.join([r'\begin{figure*}[!tbp]',r'\centering',rf'\includegraphics[width=\textwidth]{{figures/{stem}.pdf}}',r'\caption{'+cap+'}',rf'\label{{fig:{label}}}',r'\end{figure*}'])+'\n'

manifest={}
for lang in ['EN','ZH']:
 project=ROOT/'paper/overleaf'/f'Cloudra_{lang}'
 for rel in ['main.tex','references.bib','sections/01_introduction.tex','sections/02_methods.tex','sections/03_results.tex']:
  src=project/rel;dest=ARCH/lang/rel;dest.parent.mkdir(parents=True,exist_ok=True)
  if not dest.exists():shutil.copy2(src,dest)
 results=(DRAFT/f'benchmark_results_{lang.lower()}.tex').read_text()
 # Remove process-facing comments and one defensive restatement in Results.
 results='\n'.join(line for line in results.splitlines() if not line.startswith('%'))+'\n'
 results=results.replace(' It does not require a corresponding improvement in every already available numerical barrier.','')
 results=results.replace('这并不要求每一个已有数值能垒都同步提高。','')
 chunks=results.split('\n\\subsubsection{')
 body=chunks[0]
 for i,ch in enumerate(chunks[1:],1):
  block='\n\\subsubsection{'+ch
  additions={2:[FIGURES[0]],3:[FIGURES[1]],4:[FIGURES[2]],5:[FIGURES[3]],6:FIGURES[4:7],8:[FIGURES[7]]}.get(i,[])
  # Place per-task matrices before the chemical-case discussion, then its case figure.
  if i==6:
   marker='Three archived comparisons' if lang=='EN' else '三个归档'
   if marker in block:
    pos=block.index(marker);block=block[:pos]+float_tex(*FIGURES[4],lang)+float_tex(*FIGURES[5],lang)+r'\FloatBarrier'+'\n\n'+block[pos:]
    additions=[FIGURES[6]]
  body+=block
  if additions:
   body+='\n'+'\n'.join(float_tex(stem,label,lang) for stem,label in additions)+'\n'+r'\FloatBarrier'+'\n'
 (project/'sections/03_benchmark_results.tex').write_text(body)
 old=(project/'sections/03_results.tex').read_text()
 start='\\subsection{From chemical intent to reliable geometric operations}' if lang=='EN' else '\\subsection{从化学意图到可靠的几何操作}'
 if start not in old:
  # The exact current Chinese heading is retained from the third subsection boundary.
  headings=[line for line in old.splitlines() if line.startswith('\\subsection{')]
  start=headings[1]
 tail_start='\\subsection{Workflow guidance, limitations, and outlook}' if lang=='EN' else '\\subsection{工作流引导、局限与展望}'
 end=old.index(tail_start)
 retained=old[old.index(start):end]
 head='\\section{Results and Discussion}\n\nThis chapter reports the repeated-task study and the completed 200-run CloudraBench comparison, then connects the observed configuration differences to the research trajectories and local diagnostic experiments.\n\n' if lang=='EN' else '\\section{结果与讨论}\n\n本章报告四题重复实验与完整 200 次 CloudraBench 对照，随后结合研究轨迹与局部诊断实验，分析不同研究配置产生差异的具体环节。\n\n'
 (project/'sections/03_results.tex').write_text(head+r'\input{sections/03_benchmark_results}'+'\n\\FloatBarrier\n\n'+retained+'\n'+r'\input{sections/03_benchmark_discussion}'+'\n')
 discussion=(DRAFT/f'benchmark_discussion_{lang.lower()}.tex').read_text();discussion='\n'.join(x for x in discussion.splitlines() if not x.startswith('%'))+'\n'
 if lang=='EN':
  discussion=discussion.replace('These are global relations among results accumulated at different times.','These are global relations among results accumulated at different times, consistent with the role of external planning and verification feedback in language-model workflows.\\citep{valmeekam2023planning}')
  discussion=discussion.replace('a chemically familiar description can remain coherent even when the numerical or path evidence has changed.','a chemically familiar description can remain coherent even when the numerical or path evidence has changed.\\citep{turpin2023unfaithful}')
  discussion=discussion.replace('The Brief-errors comparison further shows that the useful content of feedback depends on the decision being made.','The Brief-errors comparison further shows that the useful content of feedback depends on the decision being made, complementing evidence on the importance of external feedback for reasoning correction.\\citep{huang2024selfcorrect}')
 else:
  # Three source links belong to Discussion, alongside the relevant mechanism explanation.
  paragraphs=discussion.split('\n\n')
  if len(paragraphs)>3:
   paragraphs[2]+=r' 这一解释与语言模型研究中外部规划、检验及反馈的作用相呼应。\citep{valmeekam2023planning,huang2024selfcorrect}';paragraphs[3]+=r' 文本解释对既有判断的合理化也为这种语义与证据脱节提供了相关研究背景。\citep{turpin2023unfaithful}'
  discussion='\n\n'.join(paragraphs)
 (project/'sections/03_benchmark_discussion.tex').write_text(discussion)
 meth=project/'sections/02_methods.tex';text=meth.read_text();marker='\\subsubsection{Repeated-task experiment and full-benchmark ablation}' if lang=='EN' else '\\subsubsection{重复实验与全题库消融}'
 if marker not in text:
  headings=[x for x in text.splitlines() if x.startswith('\\subsubsection{')];marker=headings[-1]
 text=text[:text.index(marker)]+(DRAFT/f'experimental_design_{lang.lower()}.tex').read_text();meth.write_text(text)
 intro=project/'sections/01_introduction.tex';text=intro.read_text()
 if lang=='EN':
  oldp='Evaluation combines 48 independent runs with three repeats on four tasks and a full-benchmark, four-configuration experiment comprising 200 independent ablation sandboxes, examining repeatability and coverage across tasks, respectively.'
  newp='Evaluation combines 48 independent runs with three repeats on four tasks and a completed 200-run, four-configuration study across all 50 tasks. The primary comparison uses the same model backbone in Standard, while Record and Brief-errors locate the effects of evidence organization and diagnostic feedback.'
  text=text.replace(oldp,newp)
 else:
  # Keep the existing introduction and add the observed experiment hierarchy to its final paragraph.
  text=text.rstrip()+'\n\n本研究以同一 backbone 的 Standard 运行为主要基线，并以 Record 与 Brief-errors 拆解证据组织和诊断反馈的作用；全题库实验共 50 题、四配置、200 次独立运行。\n'
 intro.write_text(text)
 main=project/'main.tex';text=main.read_text().replace('29 October 2026','31 October 2026').replace('2026年10月29日','2026年10月31日').replace('2026 年 10 月 29 日','2026 年 10 月 31 日');main.write_text(text)
 bib=project/'references.bib';text=bib.read_text()
 extra='''
@inproceedings{valmeekam2023planning,
 title={On the Planning Abilities of Large Language Models: A Critical Investigation},
 author={Valmeekam, Karthik and Marquez, Matthew and Sreedharan, Sarath and Kambhampati, Subbarao},
 booktitle={Advances in Neural Information Processing Systems}, year={2023},
 url={https://arxiv.org/abs/2305.15771}
}
@inproceedings{huang2024selfcorrect,
 title={Large Language Models Cannot Self-Correct Reasoning Yet},
 author={Huang, Jie and Chen, Xinyun and Mishra, Swaroop and Zheng, Huaixiu Steven and Yu, Adams Wei and Song, Xinying and Zhou, Denny},
 booktitle={International Conference on Learning Representations}, year={2024},
 url={https://arxiv.org/abs/2310.01798}
}
@inproceedings{turpin2023unfaithful,
 title={Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting},
 author={Turpin, Miles and Michael, Julian and Perez, Ethan and Bowman, Samuel R.},
 booktitle={Advances in Neural Information Processing Systems}, year={2023},
 url={https://arxiv.org/abs/2305.04388}
}
'''
 if 'valmeekam2023planning' not in text:text+=extra
 bib.write_text(text)
 for stem,_ in FIGURES:shutil.copy2(FIG/f'{stem}.pdf',project/'figures'/f'{stem}.pdf')
 manifest[lang]=[{'file':f'figures/{stem}.pdf','label':f'fig:{label}','caption':caption_en(stem) if lang=='EN' else ZH[stem]} for stem,label in FIGURES]
 # Review files in the same project; avoids changing its online identity or class.
 (project/'README.md').write_text(f'Cloudra manuscript ({lang}), updated 31 October 2026.\n\nMain: main.tex; compiler: XeLaTeX, TeX Live 2026.\n\nThe completed P2 results are in sections/03_benchmark_results.tex; discussion is in sections/03_benchmark_discussion.tex. Eight new vector figures preserve the existing manuscript style. Existing local diagnostic experiments remain in sections/03_results.tex.\n')
(FIG/'overleaf_figure_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print('Integrated EN/ZH; existing 3.2 and 3.3 retained, eight new figures per project.')
