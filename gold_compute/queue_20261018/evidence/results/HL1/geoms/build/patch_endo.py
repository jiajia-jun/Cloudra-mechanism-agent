
import json, hashlib
base='/home/ly/Cloudra-mechanism-agent/gold_compute/queue_20261018/results/HL1'
def sha(p):
    return hashlib.sha256(open(p,'rb').read()).hexdigest()[:16]
p=base+'/mechanism_graph.json'
d=json.load(open(p))
d9='/home/ly/Cloudra-mechanism-agent/ts/ts_0036/jobs/declaration_0009/'
d6='/home/ly/Cloudra-mechanism-agent/ts/ts_0036/jobs/declaration_0006/'
for e in d['edges']:
    if e['id']!='e_endo': continue
    e['barrier_kcal_mol']=6.95
    pr=e['properties']
    pr['status']=('TS 已验（唯一虚频 -375.5525 + 成键对投影 (18,1)+0.2807/(20,2)+0.1438 + 最大单原子份额 0.3494 非转子）；'
                  '反应物端已 0 虚频（-441.019350272，57 模，declaration_0009/job 1322）；'
                  '产物端 Opt/Freq 待补（durable 流 product_opt/product_frequency 未排上，改以独立外框自由弛豫 job 1324 承担，仍在跑）')
    pr['barrier_definition']=('纯电子能 ΔE‡ = E(TS) - E_ref = -441.002183678 - (-441.013264959) = +0.011081281 Ha = +6.95 kcal/mol'
                              '（x627.509474；该数只由 TS 与分离参考决定，不依赖端点证明）')
    pr['ts']={'E':-441.002183678,'job':1230,'log':d6+'ts_opt/refine.log',
              'line':'L18090 SCF, L18331 Stationary, L18853 Normal termination','sha256_prefix':sha(d6+'ts_opt/refine.log')}
    pr['ts_frequency']={'imaginary_cm':-375.5525,'modes':57,'log':d6+'frequency/frequency.log','line':'L936',
                        'sha256_prefix':sha(d6+'frequency/frequency.log'),
                        'projections_A':{'1-18':0.2807,'2-20':0.1438,'4-5':-0.0389,'C-N':-0.0332,'N-O':-0.0198},
                        'max_single_atom_fraction':{'atom':18,'element':'C','fraction':0.3494}}
    pr['irc']={'job':1280,'log':d6+'irc/irc.log','sha256_prefix':sha(d6+'irc/irc.log'),
               'summary':'10 FORWARD（去产物侧，r(18,1) 2.211→1.741）+ 10 REVERSE（回反应物侧，2.314→2.752）；两臂均未闭合',
               'convention':'替代口径同上'}
    pr['reactant_opt']={'job':1316,'log':d9+'reactant_opt/reactant_opt.log',
                        'line':'L39497 SCF, L39756 Stationary, L40276 Normal termination','sha256_prefix':sha(d9+'reactant_opt/reactant_opt.log')}
    pr['reactant_frequency']={'E':-441.019350272,'modes':57,'imaginary':0,'lowest_real_cm':21.9369,
                        'log':d9+'reactant_frequency/reactant_frequency.log',
                        'line':'L552 SCF, L922 first Frequencies (21.9369), L1729 Stationary, L2206 Normal termination',
                        'sha256_prefix':sha(d9+'reactant_frequency/reactant_frequency.log'),
                        'note':'durable verdict 把该 attempt 标为 endpoint_unconfirmed（几何/频率源/频率日志三者被判不一致，实测 E 与关键距离完全相同，属工具侧绑定标志问题）；本行数值取自原生日志本身'}
    pr['product_opt']={'status':'pending','job':None,'log':None,
                       'note':'durable 流该 run 已 ended，未自动排 product_opt/product_frequency；改由独立外框自由弛豫 job 1324（产物侧臂末点 r(18,1)=1.741 的 opt+freq）承担，结果见 arm_end_relax'}
    pr['product_frequency']={'status':'pending','job':None,'log':None,'note':'同上，与 product_opt 同一作业同时出'}
    pr['arm_end_relax']={'status':'running','job':1324,
                         'log':base+'/jobs/HL1_armend_relax_ts0036.log',
                         'purpose':'ts_0036 IRC 产物侧臂末点（r(18,1)=1.741）外框自由 opt+freq，用于核验该臂通向哪个极小值'}
d['selectivity']['value_kcal_mol']=4.94
d['selectivity']['value_statement']='约 5 kcal/mol 量级（两位差值的算术结果 4.94 = 11.89 - 6.95，不作有效数字声明；B3LYP-D3BJ/def2-SVP 单点能本征不确定度 ±1–2 kcal/mol）'
d['selectivity']['caveat']='只与分离参考口径一起使用；不许用各面自己的络合物作分母。e_endo 端点为待补状态，选择性结论按「约 5 kcal/mol 量级、倾向 C10 同侧（endo）」表述'
json.dump(d,open(p,'w'),ensure_ascii=False,indent=1)
print('e_endo barrier', [e['barrier_kcal_mol'] for e in d['edges']])
print('sha', hashlib.sha256(open(p,'rb').read()).hexdigest()[:16])
