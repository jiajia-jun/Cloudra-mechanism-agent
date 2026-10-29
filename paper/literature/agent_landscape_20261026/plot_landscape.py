"""Publication exports from systems.json. No inferred negative capabilities."""
import csv
import json
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / 'figures'
rows = json.loads((HERE/'systems.json').read_text())
GROUPS = ['extended_materials_surfaces','finite_molecules_complexes','soft_biomolecular']
LABELS = ['Extended materials / surfaces','Finite molecules / complexes','Soft matter / biomolecular systems']
COLORS = dict(zip(GROUPS,['#658568','#587C92','#BD9950']))
TASKS = ['T','E','O','F','R','D']
TASK_LABELS = ['Build / edit\nstructures','Energy /\nproperties','Geometry\nrelaxation','Freq. /\nthermochem.','Transition\npaths / TS','MD / quantum\ndynamics']
counts = Counter(r['physical_target'] for r in rows)
task_counts = Counter(t for r in rows for t in r['demonstrated_tasks'])
ordered = sorted(rows,key=lambda r:(GROUPS.index(r['physical_target']),r['first_public_date'],r['name']))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':7.2,'text.color':'#263238',
 'axes.labelcolor':'#263238','xtick.color':'#536167','ytick.color':'#263238',
 'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','axes.linewidth':0.6})
fig = plt.figure(figsize=(180/25.4,270/25.4),facecolor='white')
fig.text(.065,.965,'Computational chemistry and atomistic simulation agents',fontsize=12,weight='bold')
fig.text(.065,.944,'Structured literature sample · 2023–26 October 2026 · 26 reported systems',fontsize=7,color='#5D696B')
ax = fig.add_axes([.345,.752,.31,.138])
ax.text(0,1.21,'a  Demonstrated physical targets',transform=ax.transAxes,fontsize=7.2,weight='bold')
for i,(group,label) in enumerate(zip(GROUPS,LABELS)):
    ax.barh(i,counts[group],height=.52,color=COLORS[group])
    ax.text(counts[group]+.22,i,f'{counts[group]} / {len(rows)}',va='center',fontsize=7,weight='bold')
ax.set_yticks(range(3),LABELS);ax.invert_yaxis();ax.set_xlim(0,16)
ax.set_xticks([0,5,10,15]);ax.tick_params(axis='y',length=0,pad=8)
ax.set_xlabel('Number of systems',labelpad=5)
ax.spines[['top','right','left']].set_visible(False)
ax.spines['bottom'].set_color('#B4BDBD')
ax.xaxis.grid(True,color='#E6EAE8',linewidth=.6);ax.set_axisbelow(True)
fig.text(.735,.874,'Physical target ≠\nboundary condition',fontsize=7,weight='bold')
fig.text(.735,.85,'A protein or polymer in a periodic\ncell remains a biomolecular or\npolymer target. Software support\nis not a demonstrated use case.',fontsize=7.2,linespacing=1.5,color='#556267',va='top')
axm = fig.add_axes([.345,.185,.58,.49])
n=len(ordered)
axm.set_xlim(-.5,5.5);axm.set_ylim(n-.5,-3.0)
for i,row in enumerate(ordered):
    c=COLORS[row['physical_target']]
    axm.add_patch(Rectangle((-.5,i-.5),6,1,facecolor=('#F4F6F4' if i%2==0 else 'white'),edgecolor='none'))
    for j,t in enumerate(TASKS):
        if t in row['demonstrated_tasks']:
            axm.scatter(j,i,s=27,marker='s',color=c,edgecolors='white',linewidths=.45)
    axm.text(-.76,i,row['name'],ha='right',va='center',fontsize=7.2)
    axm.add_patch(Rectangle((-.65,i-.33),.045,.66,facecolor=c,edgecolor='none',clip_on=False))
for j,(task,label) in enumerate(zip(TASKS,TASK_LABELS)):
    axm.text(j,-2.15,label,ha='center',va='center',fontsize=7.0,linespacing=1.25)
    axm.text(j,-1.05,f'n = {task_counts[task]}',ha='center',va='center',fontsize=7,color='#667376')
for g in GROUPS[1:]:
    k=next(i for i,r in enumerate(ordered) if r['physical_target']==g)
    axm.axhline(k-.5,color='#BDC8C1',linewidth=.85,xmin=0,xmax=1)
axm.axis('off')
fig.text(.065,.706,'b  Tasks demonstrated in the inspected primary reports',fontsize=7.2,weight='bold')
fig.text(.065,.686,'Filled squares: positive evidence. Blank cells: unencoded, not evidence of missing capability.\nCoverage is not task difficulty, end-to-end completion or scientific acceptance.',fontsize=7.2,color='#5D696B')
fig.text(.065,.142,'Cloudra · this work',fontsize=7.2,weight='bold',color='#3D6250')
fig.text(.065,.119,'Organic small-molecule mechanism exploration',fontsize=7,weight='bold')
fig.text(.065,.094,'Chemistry-aware perception + geometry operators support geometric reasoning; an evidence DAG carries scientific validation.\nRestraint and guided diagnosis connect these designs. Cloudra is shown as a design focus and is excluded from literature counts.',fontsize=7.2,linespacing=1.5)
fig.text(.065,.045,'Scope: task execution, planning, code modification or feedback decisions involving actual atomistic calculations.\nCounts describe this screened sample, not field prevalence; tasks overlap. Preprint and journal versions are deduplicated.\nSource-coded records, exclusions and sensitivity analyses accompany the figure.',fontsize=7.0,color='#667376',linespacing=1.45)
OUT.mkdir(exist_ok=True)
for ext in ('svg','pdf','png'):
    fig.savefig(OUT/f'agent_landscape.{ext}',dpi=400,facecolor='white')
plt.close(fig)
with (HERE/'source_index.csv').open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['system','physical_target','demonstrated_target','boundary_conditions','tasks','first_public_date','primary_url','locator','evidence_paraphrase','limitations'])
    for r in ordered:
        s=r['sources'][0];w.writerow([r['name'],r['physical_target'],r['demonstrated_target'],r['boundary_conditions'],','.join(r['demonstrated_tasks']),r['first_public_date'],s['url'],s['locator'],s['evidence_paraphrase'],r['limitations']])
print(f'Exported {len(rows)} rows to {OUT}; tasks={dict(task_counts)}')
