from pathlib import Path
import os,json,sqlite3,hashlib,csv,subprocess,collections,datetime,re,base64,urllib.parse
os.umask(0o077)
PROJECT=Path('/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master')
RAW=PROJECT/'gold_compute/remote_backups'
BASE=RAW/'paratera_final_20261001_0830'
FINAL=BASE/'final_archive_20261001_1522'
OUT=PROJECT/'gold_compute/organized_data/hard_20261001'
REPO=Path('/private/tmp/cloudra-hl1-20260930')
COMMIT='3ec62c55c8e3433854246ea50f889668b2659cc4'
ACTIVE=['HA1','HA6','HA8','HB1','HB10','HD2','HF1','HH1','HI1','HL1']
CASE_DIR={'HE3':'HE3_gold_20260929','HG2':'HG2_gold_20260929','HI1':'HI1_gold_20260929','HL1':'HL1_gold_20260929','HA8':'hard_replacements_20261001/H6PI','HB10':'hard_replacements_20261001/HDA_CN'}
SECTIONS=['01_results','02_calculations','03_context_and_events','04_databases','05_snapshots','06_environment_and_private_config','07_restore','08_integrity']
for s in SECTIONS:(OUT/s).mkdir(parents=True,exist_ok=True)
OUT.chmod(0o700)

def write(p,s):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s);p.chmod(0o600)
def js(p,x):write(p,json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n')
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def link(p,target):
 p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists() and not p.is_symlink():p.symlink_to(os.path.relpath(target,p.parent),target_is_directory=target.is_dir())
def mdlink(p,target,label):return '['+label+']('+urllib.parse.quote(os.path.relpath(target,p.parent),safe='/._-')+')'
def conn(p):return sqlite3.connect('file:'+urllib.parse.quote(str(p),safe='/')+'?mode=ro&immutable=1',uri=True)
def csvwrite(p,rows,fields):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
 p.chmod(0o600)
def norm(x):
 if isinstance(x,bytes):return {'encoding':'base64','data':base64.b64encode(x).decode()}
 return x
catalog=OUT/'catalog.sqlite3'
assert not catalog.exists(), 'Existing organized catalog; do not overwrite without checking.'
c=sqlite3.connect(catalog)
c.executescript('''CREATE TABLE snapshots(id TEXT PRIMARY KEY, role TEXT,path TEXT);
CREATE TABLE files(source_path TEXT PRIMARY KEY,bytes INTEGER,sha256 TEXT,category TEXT,case_id TEXT,snapshot_id TEXT);
CREATE TABLE databases(id TEXT PRIMARY KEY,source_path TEXT,sha256 TEXT,bytes INTEGER,epoch TEXT,integrity TEXT);
CREATE TABLE database_tables(database_id TEXT,table_name TEXT,row_count INTEGER,PRIMARY KEY(database_id,table_name));
CREATE TABLE jobs(id INTEGER PRIMARY KEY,state TEXT,case_id TEXT,session_id TEXT,input_remote TEXT,input_local TEXT,log_local TEXT,interpretation TEXT,req_cpus INTEGER,req_memory_mb INTEGER);
CREATE TABLE agents(session_id TEXT PRIMARY KEY,display_name TEXT,role_id TEXT,stored_state TEXT,current_messages INTEGER,event_count INTEGER,context_path TEXT);
CREATE TABLE published_files(path TEXT PRIMARY KEY,git_commit TEXT,sha256 TEXT);
''')
# Retain original archives and give each a distinct epoch identity.
snaps=[('final','生产终态固定快照',FINAL),('migration','关机迁移期固定元数据快照',BASE/'migration_snapshot'),('migration_workspace','迁移工作区及此前预拷贝混合；固定清单覆盖范围见原说明',BASE/'workspace'),('increments','重启后逐作业终态增量',BASE/'post_recovery_20261001')]
for p in sorted(RAW.iterdir()):
 if p.is_dir() and p!=BASE:snaps.append((p.name,'此前服务器历史归档；不作本轮终态',p))
for sid,role,p in snaps:
 c.execute('insert into snapshots values(?,?,?)',(sid,role,str(p.relative_to(PROJECT))))
 link(OUT/'05_snapshots'/sid,p)
raw_items=[]
# All original files are cataloged, including auxiliary files outside existing manifests.
for sid,role,root in snaps:
 for p in sorted(root.rglob('*')):
  if not p.is_file() or p.is_symlink():continue
  rel=str(p.relative_to(PROJECT));lower=rel.lower();case='unassigned'
  for k,v in CASE_DIR.items():
   if v.lower() in lower:case=k;break
  if case=='unassigned':
   match=re.search(r'(?<![A-Za-z0-9])(HA1|HA6|HA8|HB1|HB10|HD2|HF1|HH1|HI1|HL1|HE3|HG2)(?![A-Za-z0-9])',rel)
   if match:case=match.group(1)
  if p.name in ('config.yaml','.api_token') or 'token' in p.name.lower():category='private_config'
  elif p.suffix in ('.db','.sqlite','.sqlite3') or p.name.endswith(('-wal','-shm')):category='database'
  elif '/rebuild/' in lower:category='source_environment'
  elif 'manifest' in p.name.lower() or 'verification' in p.name.lower() or p.name=='STATE.json':category='provenance_integrity'
  elif p.name.endswith(('.xyz','.hess','.gbw','.inp','.out','.out.log','.trj','.allxyz')) or 'calc-' in p.name:category='calculation_evidence'
  elif 'report' in p.name.lower() or 'handoff' in p.name.lower() or 'audit' in p.name.lower():category='report_handoff'
  elif '/runtime/' in lower or 'events' in p.name or 'message' in p.name or p.name=='agents.json':category='runtime_context'
  else:category='other_preserved'
  row=(rel,p.stat().st_size,digest(p),category,case,sid);c.execute('insert into files values(?,?,?,?,?,?)',row)
  raw_items.append({'path':rel,'bytes':row[1],'sha256':row[2],'category':category,'case_id':case,'snapshot_id':sid})
c.commit();print(json.dumps({'stage':'raw_inventory','files':len(raw_items),'bytes':sum(x['bytes'] for x in raw_items)}),flush=True)
js(OUT/'08_integrity/raw_inventory.json',raw_items)
csvwrite(OUT/'08_integrity/raw_inventory.csv',raw_items,['path','bytes','sha256','category','case_id','snapshot_id'])
# Published results are copied from the exact accepted commit, not a dirty working tree.
paths=subprocess.check_output(['git','-C',str(REPO),'ls-tree','-r','--name-only',COMMIT],text=True).splitlines()
selected=[p for p in paths if p.startswith('ideapool/tasks/hard/') or p in ('ideapool/reaction_candidates/hard.md','cloudra/benchmark/hard_registry/hi.py','cloudra/benchmark/hard_registry/replacements.py','cloudra/benchmark/gen_hard_tasks.py') or p.startswith('gold_compute/archive/retired_tasks_20261001/') or (p.startswith('gold_compute/') and ('2026-10-01.md' in p or p.startswith('gold_compute/hard_replacements_20261001/verified/') or p.endswith('FINAL_INDEPENDENT_AUDIT.json')))]
for rel in selected:
 b=subprocess.check_output(['git','-C',str(REPO),'show',COMMIT+':'+rel]);p=OUT/'01_results/published'/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);p.chmod(0o600)
 c.execute('insert into published_files values(?,?,?)',(rel,COMMIT,hashlib.sha256(b).hexdigest()))
results=[]
for case in ACTIVE:
 d=json.loads((OUT/'01_results/published/ideapool/tasks/hard'/f'{case}.json').read_text())
 for e in d['gold']['mechanism_graph']['edges']:
  results.append({'task_id':case,'edge_id':e.get('id'),'barrier_kcal_mol':e.get('barrier_kcal_mol'),'source':'published TaskSpec at '+COMMIT})
csvwrite(OUT/'01_results/edge_gold.csv',results,['task_id','edge_id','barrier_kcal_mol','source'])
js(OUT/'01_results/published_provenance.json',{'git_commit':COMMIT,'files':selected,'active_tasks':ACTIVE,'retired_tasks':['HE3','HG2'],'missing_barrier_count':sum(x['barrier_kcal_mol'] is None for x in results),'interpretation':'TaskSpec 快照，不把所有历史值声称为本轮新算；精确科学验收看各证据文档。'})
# Database identity, schema, and table statistics for every preserved SQLite file.
dbs=[]
for i in raw_items:
 p=PROJECT/i['path']
 if p.suffix not in ('.db','.sqlite','.sqlite3'):continue
 with p.open('rb') as f:
  if f.read(16)!=b'SQLite format 3\x00':continue
 dbid=f"db{len(dbs)+1:02d}";dbdir=OUT/'04_databases'/('current' if i['snapshot_id']=='final' else 'historical')/dbid;dbdir.mkdir(parents=True,exist_ok=True)
 link(dbdir/'snapshot.sqlite3',p)
 a=conn(p);a.row_factory=sqlite3.Row;integrity=[r[0] for r in a.execute('pragma integrity_check')]
 assert integrity==['ok'],(p,integrity)
 schema=[];stats=[]
 for r in a.execute("select type,name,sql from sqlite_master where sql is not null order by type,name"):
  schema.append(r['sql']+';')
 for r in a.execute("select name from sqlite_master where type='table' order by name"):
  table=r['name'];count=a.execute('select count(*) from "'+table.replace('"','""')+'"').fetchone()[0]
  cols=[dict(z) for z in a.execute('pragma table_info("'+table.replace('"','""')+'")')]
  stats.append({'table':table,'rows':count,'columns':cols});c.execute('insert into database_tables values(?,?,?)',(dbid,table,count))
  # JSONL export of logical tables from current databases; FTS internal indexes are recoverable in raw SQLite.
  if i['snapshot_id']=='final' and not table.startswith('kg_entities_fts') and table!='sqlite_sequence':
   export=dbdir/'tables'/f'{table}.jsonl';export.parent.mkdir(parents=True,exist_ok=True)
   with export.open('w') as f:
    for row in a.execute('select * from "'+table.replace('"','""')+'"'):
     f.write(json.dumps({k:norm(v) for k,v in dict(row).items()},ensure_ascii=False)+'\n')
   export.chmod(0o600)
  if table=='session' and i['snapshot_id']=='final':legacy_sessions=[dict(z) for z in a.execute('select session_id,state,agent_id,parent_session_id from session')]
 write(dbdir/'schema.sql','\n\n'.join(schema)+'\n');js(dbdir/'tables.json',stats)
 info={'id':dbid,'source_path':i['path'],'sha256':i['sha256'],'bytes':i['bytes'],'epoch':i['snapshot_id'],'integrity':'ok','tables':stats}
 dbs.append(info);c.execute('insert into databases values(?,?,?,?,?,?)',(dbid,i['path'],i['sha256'],i['bytes'],i['snapshot_id'],'ok'))
 js(dbdir/'metadata.json',{k:v for k,v in info.items() if k!='tables'});a.close()
js(OUT/'04_databases/database_inventory.json',dbs)
# v2 durable snapshot and events: full retained current contexts and separate event history.
v2=conn(FINAL/'runtime/recovery_20261001/runtime-v2.db');v2.row_factory=sqlite3.Row
snapshot=json.loads(v2.execute("select data from objects where kind='snapshot'").fetchone()[0]);js(OUT/'03_context_and_events/recovered_v2/runtime_snapshot.json',snapshot)
ctxcounts={};agents=[]
for sid,a in snapshot['agents'].items():
 d=OUT/'03_context_and_events/recovered_v2/agents'/sid;d.mkdir(parents=True,exist_ok=True);js(d/'agent.json',a)
 ctx=snapshot['session_contexts'].get(sid)
 if ctx is not None:
  js(d/'context.json',ctx);count=len(ctx.get('messages',[]));ctxcounts[sid]=count
  text=['# '+sid+' 当前 context','\n来自最终 runtime-v2 objects.snapshot；这是保存时的当前上下文，可能含压缩/注入，不等于重启前全部原始对话。\n']
  for n,msg in enumerate(ctx.get('messages',[])):
   text+=['## '+str(n)+' · '+str(msg.get('role','unknown')),'\n'+(msg.get('content') if isinstance(msg.get('content'),str) else json.dumps(msg,ensure_ascii=False,indent=2))+'\n']
  write(d/'context.md','\n'.join(text))
 else:write(d/'CONTEXT_NOT_PRESENT.md','# 当前 context 未保存\n\n最终 objects.snapshot 中没有本 session 的 session_contexts 条目。元数据和实际保存的事件仍在，不能凭空补为完整上下文。\n')
 agents.append({'session_id':sid,'display_name':a['display_name'],'role_id':a['role_id'],'stored_state':a['state'],'current_messages':ctxcounts.get(sid,0),'context_present':ctx is not None})
handles={};counts=collections.Counter();types=collections.Counter()
for row in v2.execute('select * from events order by seq,event_id'):
 d=dict(row);sid=d['session_id'] or '_project';target=OUT/'03_context_and_events/recovered_v2/agents'/sid/'events.jsonl'
 if sid not in handles:target.parent.mkdir(parents=True,exist_ok=True);handles[sid]=target.open('w')
 # Preserve original serialized data exactly; raw schema retains ordering and IDs.
 handles[sid].write(json.dumps(d,ensure_ascii=False)+'\n');counts[sid]+=1;types[d['type']]+=1
for f in handles.values():f.close()
for a in agents:
 a['event_count']=counts[a['session_id']];d=OUT/'03_context_and_events/recovered_v2/agents'/a['session_id']
 c.execute('insert into agents values(?,?,?,?,?,?,?)',(a['session_id'],a['display_name'],a['role_id'],a['stored_state'],a['current_messages'],a['event_count'],str((d/'context.json').relative_to(OUT)) if a['context_present'] else None))
js(OUT/'03_context_and_events/agents_index.json',agents)
csvwrite(OUT/'03_context_and_events/agents_index.csv',agents,['session_id','display_name','role_id','stored_state','context_present','current_messages','event_count'])
js(OUT/'03_context_and_events/event_types.json',dict(types));js(OUT/'03_context_and_events/legacy_session_states.json',legacy_sessions)
# Old bounded event excerpts and the metadata used during recovery remain distinct.
for p in (BASE/'migration_snapshot').glob('*.json'):
 if p.name=='agents.json' or p.name.startswith(('last-events-','migration-message-')):link(OUT/'03_context_and_events/pre_reboot_excerpts'/p.name,p)
link(OUT/'03_context_and_events/RECOVERY_PROVENANCE.json',FINAL/'runtime/recovery_20261001/RECOVERY_PROVENANCE.json')
# Job identity comes from actual job inputs, not owner labels or guessed scientific success.
ledger=conn(FINAL/'runtime/compute.db');ledger.row_factory=sqlite3.Row
jobs=[];missing_inputs=[];missing_logs=[]
notes={14:'wrong species / shutdown interruption; rejected',15:'wrong species; rejected',27:'noncovalent return; rejected',36:'invalid seed; failed',45:'wrong fragments; rejected',50:'cancelled before QM',58:'discontinuous scan; seed evidence only',64:'shutdown interruption; rejected',67:'accepted EM1 TS; working major directory is C29R/M1',70:'accepted E2 TS; working minor directory is C29S/I2',69:'duplicate saddle of 70; not a separate channel',68:'EM1 IRC backward native limit',73:'E2 IRC backward native limit',77:'accepted HA8 TS',78:'HB10 endo IRC both native limits',79:'HB10 exo IRC both native limits',81:'HA8 IRC both native limits',88:'soft imaginary rotor; rejected',90:'single repair of 88; accepted EZE reactant endpoint'}
for r in ledger.execute('select * from compute_jobs order by id'):
 d=dict(r);remote=d['path'] or '';local=FINAL/remote.removeprefix('/data/cloudra/')
 case=next((k for k,v in CASE_DIR.items() if v in remote),'unassigned');log=local.parent/'.cloudra'/f"calc-{d['id']}.out.log"
 row={'id':d['id'],'state':d['state'],'case_id':case,'session_id':d['session_id'],'input_remote':remote,'input_local':str(local.relative_to(PROJECT)) if local.is_file() else '', 'log_local':str(log.relative_to(PROJECT)) if log.is_file() else '', 'interpretation':notes.get(d['id'],'ledger terminal status alone does not establish chemical acceptance'),'req_cpus':d['req_cpus'],'req_memory_mb':d['req_memory_mb']}
 if not row['input_local']:missing_inputs.append(d['id'])
 if not row['log_local']:missing_logs.append(d['id'])
 jobs.append(row);c.execute('insert into jobs values(?,?,?,?,?,?,?,?,?,?)',tuple(row.values()))
 ddir=OUT/'02_calculations'/case/'jobs'/f"job{d['id']:03d}";js(ddir/'ledger.json',d)
 if local.is_file():link(ddir/'input.inp',local)
 if log.is_file():link(ddir/'raw_output.log',log)
 if local.parent.is_dir():link(ddir/'run_directory',local.parent)
for case,v in CASE_DIR.items():link(OUT/'02_calculations'/case/'raw_case',FINAL/'workspace/hard_resume_20260930'/v)
csvwrite(OUT/'02_calculations/jobs.csv',jobs,list(jobs[0]));js(OUT/'02_calculations/jobs.json',jobs)
js(OUT/'02_calculations/path_gaps.json',{'missing_inputs':missing_inputs,'missing_expected_logs':missing_logs,'meaning':'Expected path absent, not proof that all evidence is lost. Search catalog and legacy snapshots before making a claim.'})
ledger.close();v2.close()
# Environment and restore links are private and never printed.
link(OUT/'06_environment_and_private_config/source',FINAL/'rebuild/source');link(OUT/'06_environment_and_private_config/environment',FINAL/'rebuild')
for name in ('config.yaml','.api_token','nodes.json'):
 if (FINAL/'runtime'/name).exists():link(OUT/'06_environment_and_private_config/private'/name,FINAL/'runtime'/name)
for name in ('VERIFICATION.json','MANIFEST.json','CASE_SENSITIVE_PATH_MAP.json','STATE.json','BILLING_STOP_VERIFICATION.json','FINAL_README.md'):
 link(OUT/'08_integrity/final_snapshot'/name,FINAL/name)
c.commit();c.close()
# Human navigation documents.
readme=OUT/'README.md'
write(readme,'''# Hard 数据归档入口 · 2026-10-01

本目录是分类、可读导出与检索层。原始迁移快照、最终快照、逐作业增量及此前服务器归档各自保留，所有链接采用相对路径。原始数据库与文件是恢复依据；本目录的 JSONL/CSV/SQLite 索引是派生资料。

## 按目的查找

| 目录 | 内容 | 从哪里开始 |
|---|---|---|
| 01_results | 已发布 10 道题、归档 HE3/HG2、科学验收说明、映射坐标及题源/registry 快照 | [结果说明](01_results/README.md) |
| 02_calculations | 按题目→作业编号→输入/原始日志/运行目录组织，含失败与拒收证据 | [计算索引](02_calculations/README.md)、[jobs.csv](02_calculations/jobs.csv) |
| 03_context_and_events | 重启前片段、恢复来源、重启后的完整已保存事件和 9 份当前 context | [context 说明](03_context_and_events/README.md) |
| 04_databases | 当前与历史 SQLite 原库链接、schema、表/行数、当前逻辑表 JSONL | [数据库说明](04_databases/README.md) |
| 05_snapshots | 最终、迁移、增量、此前服务器快照入口，互不混淆 | [快照说明](05_snapshots/README.md) |
| 06_environment_and_private_config | 原服务器源码、软件/依赖清单、启动服务、私有配置 | [环境说明](06_environment_and_private_config/README.md) |
| 07_restore | 恢复顺序、大小写文件映射、只读检索示例 | [恢复手册](07_restore/README.md) |
| 08_integrity | 原始文件逐项 SHA 索引、最终核验与停费凭证、整理核验 | [核验说明](08_integrity/README.md) |

## 哪份记录优先

1. 题库已发布状态采用 `3ec62c55c8e3433854246ea50f889668b2659cc4` 的文件快照。
2. 本轮计算终态采用 `final_archive_20261001_1522` 的原始文件与 compute.db。
3. 重启后的 agent/context/events 采用最终 `runtime/recovery_20261001/runtime-v2.db`。
4. 迁移与此前服务器记录仅说明其自身时间段，不覆盖最终状态。

科学限制：HA8/HB10 两道替换已验收；HI1 本轮只验收加成 E2/EM1，E1/E3 保持缺测；HL1 与其它题按既有证据说明。正常结束、DONE、agent succeeded 都不能独立证明化学成功。IRC 原生步数上限、近简并、旧身份错误和工作目录面标签交换均保留。

目录与导出保留私有访问权限。context 可能含工具输出和配置，不应整目录提交 Git 或对外分享。服务器已关机，本次整理全在本地完成。
''')
write(OUT/'01_results/README.md',f'''# 已发布结果与科学验收

固定来源 commit：`{COMMIT}`。本层文件从 Git 对象读取，不含当前工作区未提交改动。

- 活跃题：{', '.join(ACTIVE)}。
- HE3/HG2 原 TaskSpec：`published/gold_compute/archive/retired_tasks_20261001/`，保留原文。
- [逐边数值表](edge_gold.csv)；空白表示 null，不能当零能垒。
- [HI1 独立结论](published/gold_compute/hard_hi1_2026-10-01.md)：E2 13.36、EM1 15.52；实际 C29S/I2 对应工作 minor 目录，C29R/M1 对应工作 major 目录。
- [两道替换验收](published/gold_compute/hard_replacements_verified_2026-10-01.md)：HA8 29.48；HB10 endo14.34/exo14.12，0.22 近简并不作为稳健 favored。
- [HL1 结论](published/gold_compute/hard_hl1_2026-10-01.md)、[HG2 退役证据](published/gold_compute/hard_hg2_2026-10-01.md)。
- 原子映射、最终几何与独立审查：`published/gold_compute/hard_replacements_20261001/`。

电子能垒、溶剂/气相、共同参考态与 IRC 原生上限均按各证据文件解释。这里的 published 只表示已入题库，不能推断每个值都来自本轮 QM，也不能推断整条反应图全边已验。
''')
write(OUT/'02_calculations/README.md',f'''# 计算证据：题目 → 作业 → 文件

`jobs.csv` / `jobs.json` 包含最终 compute.db 的 {len(jobs)} 个作业。每个 job 目录有原账本记录，并链接真实输入、原始日志及完整运行目录；Hessian、GBW、轨迹、临时文件、报告与拒收尝试均在原目录保留。

目录名不代替化学身份：HI1 的 working major/minor 面标签交换已在结果说明纠正。`HA8` 是原 `H6PI`，`HB10` 是原 `HDA_CN`。

所有活跃账本状态为零。尚未找到的预期路径在 `path_gaps.json` 明示，不能默默假装已找到；可从 catalog.sqlite3 的 files 表及历史快照继续追溯。未被本轮账本登记的 standalone xTB/初猜资料仍在 raw_case 与总文件索引中。

状态 DONE/failed/cancelled 是程序/调度状态；科学接受、拒收、重复鞍点、错误物种与诊断扫描需看独立结论。旧 HE3/HG2 的退出证据也保留。
''')
write(OUT/'03_context_and_events/README.md',f'''# Context、agent 与事件：按恢复时间段保留

## 重启前保存范围

`pre_reboot_excerpts/agents.json` 保存原 10 个 session 元数据；三份 `last-events-*.json` 每份仅 3 条事件，是有边界的片段。迁移时没有完整持久化原 v2 内存 context。后续恢复使用这些元数据和文件 HANDOFF；不能声称恢复了重启前全部旧对话。

## 重启后的持久资料

原库：`../04_databases/` 中最终 `runtime/recovery_20261001/runtime-v2.db`。

- `recovered_v2/runtime_snapshot.json`：完整 objects.snapshot，含 projects、agents、roles、runtime_defaults、session_contexts、pending_compactions、launch_groups。
- `recovered_v2/agents/<session_id>/agent.json`：保存的身份、父子关系、设置、权限、状态。
- `context.json`：当前已保存上下文完整结构；`context.md` 为可读展示，JSON 为无损依据。共有 {len(ctxcounts)} 份、{sum(ctxcounts.values())} 条消息。prefix_meta/压缩后消息及工具内容保留。
- `events.jsonl`：该 session 的全部已保存事件，按原 seq 排列；无 session 的事件放 `_project/`。共 {sum(counts.values())} 条，ID、run_id、seq、session_seq、created_at、type、原 data 字符串原样保留。
- `agents_index.csv/json`：{len(agents)} 个 agent 的状态、是否有 context、消息/事件数。

## 状态与覆盖限制

当前 context 不是“全历史 transcript”；压缩与注入可能改变消息覆盖范围。缺少 context 的两个 agent 以 CONTEXT_NOT_PRESENT.md 明示；不要从事件猜造缺失对话。

legacy `tasks/database.db` 的 session 表仍保存 running 状态；最终 v2 也有一个旧 owner 记录仍 running。这是保存时的状态字段，不表示机器仍在计算。实际 compute.db 无活跃作业、进程已结束、平台已关机；`legacy_session_states.json` 保留差异，不修改原库来抹平。

当前库、内嵌历史 backup/runtime-v2.db、迁移旧库独立存放；不会把跨库 seq 混为一条连续历史。event created_at 按源字符串保留；本轮报告时间使用 SGT(UTC+8)。
''')
roles={'compute.db':'作业状态、资源请求、实际输入路径、调度错误','database.db':'legacy sessions/session_events、DAG、证据绑定、artifacts；不是当前 v2 状态权威','runtime-v2.db':'v2 事件流、完整运行快照和保存的 context；backup 子目录为较早历史','chem_kg.db':'化学知识库实体、关系、标签及 FTS 索引'}
lines=['# SQLite 数据库目录','\n所有原库通过相对链接保留；读取采用 immutable 只读模式。每库附 schema.sql、tables.json、metadata.json；current 库额外导出逻辑表 JSONL。FTS 内部索引与 sqlite_sequence 仍在完整原库保留，不重复解释为业务记录。\n','| ID | 时间段 | 原文件 | 用途 |','|---|---|---|---|']
for d in dbs:lines.append('| '+d['id']+' | '+d['epoch']+' | `'+d['source_path'].removeprefix('gold_compute/remote_backups/')+'` | '+roles.get(Path(d['source_path']).name,'历史数据库')+' |')
lines+=['\n不要合并覆盖同名库；按 source_path、epoch、SHA 区分。最终固定快照中的 backup/runtime-v2.db 仍是较早记录，不因位于 final 目录就成为最新事件库。','\n所有 '+str(len(dbs))+' 个库 integrity_check 均为 ok。逻辑导出不是经过脱敏的共享数据；原表内敏感设置、路径、凭据哈希均仍按私有权限保存。','\n只读查询示例见 ../07_restore/README.md。']
write(OUT/'04_databases/README.md','\n'.join(lines)+'\n')
write(OUT/'05_snapshots/README.md','# 快照时间段与用途\n\n'+ '\n'.join('- `'+s+'`：'+r+' → `'+str(p.relative_to(PROJECT))+'`。' for s,r,p in snaps)+'\n\n迁移 workspace 含 253 项早期预拷贝额外文件：其固定覆盖清单和核验结论看原 MIGRATION_README/BACKUP_VERIFICATION，不把多余文件当作同一固定时间点。各 epoch 不替换彼此；去重信息只用于查找，未删除重复证据。\n')
write(OUT/'06_environment_and_private_config/README.md','''# 环境恢复与私有配置

- `source/`：远端部署源码固定快照，不等同于已发布科学回填 commit。
- `environment/`：REBUILD_MANIFEST、inventory、下载来源、pip/dpkg/MPI 版本、启动脚本、服务单元等。
- `private/`：config.yaml、API token 与节点配置，仅本地私有引用。
- 老部署、context 和数据库入口见 ../05_snapshots/ 与 ../04_databases/。

ORCA 6.1.1 / 完整 OpenMPI 4.1.8 与各题既定方法见环境清单。新 v2 恢复 API 使用 8422 与持久库 recovery_20261001/runtime-v2.db；旧 8420 的原项目上下文没有完整恢复。源码快照未包含虚拟环境或可执行软件整套二进制，重建时用清单和官方来源恢复，不把清单当作二进制副本。
''')
write(OUT/'07_restore/README.md','''# 恢复与检索顺序

1. 将 organized_data 与 remote_backups 一并保留在 gold_compute 下，相对链接即可随整个 gold_compute 迁移；单独拷贝索引目录不能替代原始资料。
2. 选择 `final_archive_20261001_1522` 恢复本轮生产终态：workspace → /data/cloudra/workspace，runtime → /data/cloudra/runtime；原迁移与增量另留历史。
3. Mac 大小写冲突：读取最终快照 CASE_SENSITIVE_PATH_MAP.json。在 Linux 先按原路径放小写 em1_ts_final.xyz，再将 em1_TS_final.xyz.__case_preserved 复制为大写原名。两份内容不同，都必须保留。
4. 数据库使用独立 SQLite backup 快照。检查 SHA 和 integrity_check 后部署；同名历史库不能覆盖最新库。-wal/-shm 是运行/只读打开时的辅助文件，未列入固定 manifest 的附件不能取代一致快照。
5. 用 rebuild/ 清单恢复程序与依赖、服务环境和私有配置，落实 8422 的持久 runtime store。先只读验证路径、数据库与 agent/context，再明确决定是否恢复执行；整理数据本身不授权开机或重交 QM。
6. 科学结果取 01_results/published 的已发布 commit；远端源码和旧报告里的过渡结论不覆盖独立验收。查证路径优先最终日志，再历史快照。

## 本地目录查询

在本目录用 Python/sqlite3 的只读连接打开 catalog.sqlite3：

```sql
SELECT id,state,case_id,input_local,log_local,interpretation FROM jobs WHERE case_id='HI1' ORDER BY id;
SELECT source_path,sha256,snapshot_id FROM files WHERE source_path LIKE '%calc-83.out.log';
SELECT id,epoch,source_path FROM databases;
SELECT session_id,current_messages,event_count FROM agents;
SELECT database_id,table_name,row_count FROM database_tables WHERE table_name IN ('events','session_events','compute_jobs');
```

catalog.sqlite3 是派生索引，不能替代原 runtime-v2、compute、DAG、知识数据库。schema.sql 说明原表；JSONL 保留原数据类型及记录，BLOB 如有则带 base64 编码标识。
''')
write(OUT/'08_integrity/README.md','''# 完整性与溯源

- raw_inventory.json/csv 与 catalog.sqlite3/files：本次整理前原始归档全部文件的路径、字节数、SHA、类别、题目、epoch。
- final_snapshot/：6776 个固定文件的原远端 manifest、大小写映射、全量 SHA/五库核验、平台停费凭证。
- ORGANIZATION_VERIFICATION.json：整理后重新核验原始文件、派生文件、链接、JSONL 记录数及全部原库。
- organized_manifest.json：本次新建文档、导出和目录索引的 SHA；验证器自身不包含其动态结果文件。

原始同名文件在不同 epoch 的 SHA 可不同，属历史变化，不能当成内容冲突后删掉。数据库结构完整性与化学验收是两个不同条件；可读并不表示某个鞍点、端点或能垒科学有效。
''')
# Convenient top-level user entry and regenerable organizer copy.
write(OUT/'organize_archive.py',Path(__file__).read_text())
write(PROJECT/'gold_compute/HARD_DATA_INDEX.md','# Hard 数据总入口\n\n[打开分类归档](organized_data/hard_20261001/README.md)。\n\n包括计算证据、已发布结果、context/事件、所有数据库、快照时间段、环境与私有配置、恢复说明及完整性核验。原始备份保持独立；当前服务器已关机，未重启任何计算。\n')
for p in OUT.rglob('*'):
 if not p.is_symlink():p.chmod(0o700 if p.is_dir() else 0o600)
print(json.dumps({'stage':'organized','databases':len(dbs),'jobs':len(jobs),'agents':len(agents),'contexts':len(ctxcounts),'context_messages':sum(ctxcounts.values()),'events':sum(counts.values()),'missing_inputs':missing_inputs,'missing_logs':missing_logs,'published_files':len(selected),'output':str(OUT)}),flush=True)
