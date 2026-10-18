
import json, hashlib
base='/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1'
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()[:16]
p=base+'/mechanism_graph.json'
d=json.load(open(p))
log=base+'/jobs/HL1_armend_relax_ts0036.log'
for e in d['edges']:
    if e['id']!='e_endo': continue
    pr=e['properties']
    pr['status']=('TS 已验（唯一虚频 -375.5525 + 成键对投影 (18,1)+0.2807/(20,2)+0.1438 + 最大单原子份额 0.3494 非转子）；'
                  '反应物端 0 虚频（-441.019350272，57 模，declaration_0009/job 1322）；'
                  '产物端 0 虚频（-441.098273730，57 模，job 1324 独立外框弛豫，与 #1228 同一极小值）')
    pr['product_opt']={'status':'done','job':1324,'log':log,'mode':'独立外框自由 opt+freq（durable 流该 run 已 ended，未自动排 product_opt）',
                       'E':-441.098273730,'line':'L9642 SCF / L9889 Stationary / L10414 Normal termination',
                       'sha256_prefix':sha(log),'smiles_in_input':'C1=NO[C@@H]2[C@@H]3CC[C@@H](C3)[C@H]12（gjf 第 6 行 smiles: 注释）'}
    pr['product_frequency']={'status':'done','job':1324,'log':log,'modes':57,'imaginary':0,'lowest_real_cm':130.0548,
                       'line':'L10852 freq 单点 SCF / L11222 首条 Frequencies 130.0548 / L12093 Stationary / L12719 Normal termination',
                       'sha256_prefix':sha(log),'note':'L11212 "Low frequencies --- -6.5091 0.0008 0.0011 0.0014 8.7287 13.1609" 为平动/转动投影残差，不计入 3N-6'}
    pr['arm_end_relax']={'status':'done','job':1324,'log':log,'sha256_prefix':sha(log),
                       'start':'ts_0036 IRC 产物侧臂末点（r(18,1)=1.741）',
                       'E':-441.098273730,'imaginary':0,'modes':57,
                       'rmsd_vs_1228_endo':0.0005,'max_atom_dev':{'atom':20,'element':'O','dev_A':0.0012},
                       'rmsd_vs_1229_exo':1.2506,'sdist_18':1.2768,'d_working7_18':3.0466,
                       'conclusion':'该臂收敛到 C10 同侧（endo）产物极小值 #1228，身份由 RMSD 0.0005 Å 与 sdist/d 双重确认'}
json.dump(d,open(p,'w'),ensure_ascii=False,indent=1)
print('sha', hashlib.sha256(open(p,'rb').read()).hexdigest())
