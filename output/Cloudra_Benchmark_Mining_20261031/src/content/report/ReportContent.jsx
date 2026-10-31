import React, {useState} from 'react';
import {EvidenceChart, DataComponent, ReportSection, RichNarrative, useDataApp} from '../../data-app-public.jsx';
import sections from './report-sections.json';

const f = v => v == null ? '—' : Number(v).toFixed(3);
function SmallTable({id,queryId,title,columns,rows,caption}) {
 return <DataComponent id={id} queryId={queryId} kind="table" title={title} displayRows={rows} sourceRows={rows}>
  <div className="mining-table-wrap"><table className="mining-table" data-reviewed-rows><caption>{caption}</caption>
   <thead><tr>{columns.map(c=><th key={c.key} scope="col">{c.label}</th>)}</tr></thead>
   <tbody>{rows.map((r,i)=><tr key={i}>{columns.map(c=><td key={c.key} className={c.numeric?'num':''}>{c.render?c.render(r[c.key],r):r[c.key]}</td>)}</tr>)}</tbody>
  </table></div>
 </DataComponent>;
}
function Chart({id,queryId,title,spec,height=320}) {
 const {reviewedRows}=useDataApp();const rows=reviewedRows(queryId);
 return <EvidenceChart id={id} queryId={queryId} title={title} rows={rows} sourceRows={rows} spec={spec} height={height}/>;
}
export function ReportContent(){
 const {reviewedRows,appTitle,canEdit,mode,setAppTitle,visible}=useDataApp();
 const [search,setSearch]=useState('');
 const tasks=reviewedRows('tasks').filter(r=>`${r.task} ${r.name} ${r.tier}`.toLowerCase().includes(search.toLowerCase()));
 const pairs=reviewedRows('pairs').map(r=>({...r,comparison:`${r.arm_a} − ${r.arm_b}`,interval:`[${Number(r.ci_low).toFixed(3)}, ${Number(r.ci_high).toFixed(3)}]`,wins:`${r.a_wins} / ${r.b_wins} / ${r.ties}`}));
 return <article className="report-content" aria-label="Cloudra benchmark 深度挖掘">
 <header className="report-hero"><h1 data-data-app-title contentEditable={canEdit&&mode==='edit'} suppressContentEditableWarning onBlur={e=>setAppTitle(e.currentTarget.textContent.trim()||appTitle)}>{appTitle}</h1>
 <RichNarrative id="deck" value="P2 · 50个任务 × 4种研究模式 · 2026年10月31日归档" className="report-deck"/></header>
 {sections.map(s=>visible(s.id)&&<section key={s.id} className="report-section" id={s.id}>
  <ReportSection id={s.id} title={s.title} queryId={s.queryId} sourceRows={reviewedRows(s.queryId)} queryIds={s.queryIds} sourceRowsByQuery={s.queryIds?Object.fromEntries(s.queryIds.map(q=>[q,reviewedRows(q)])):undefined} showHeading={false}>
   <RichNarrative id={`${s.id}:body`} value={s.text} className="report-analysis"/>
  </ReportSection>
  {s.id==='ranking'&&<>
   <Chart id="tier-chart" queryId="baseline_tiers" title="Cloudra与同一backbone基线的分层对照" spec={{type:'bar',x:'题目',y:'得分',series:'组别',stackable:false,startAtZero:true,valueDecimals:3,showXAxisLabel:false,showYAxisLabel:false}} height={300}/>
   <SmallTable id="pair-table" queryId="baseline" title="Cloudra相对backbone的逐题配对差值" rows={reviewedRows('baseline')} columns={[{key:'比较',label:'范围'},{key:'mean_difference',label:'均差',numeric:true,render:f},{key:'interval',label:'任务配对95%区间'},{key:'wins',label:'胜 / 负 / 平'}]} caption="整理后轨道，50题配对；区间按任务整组bootstrap。"/>
  </>}
  {s.id==='closure'&&<Chart id="components-chart" queryId="components" title="Cloudra − backbone：各分量对最终得分的贡献" spec={{type:'horizontalBar',x:'比较',y:'得分贡献',series:'分量',stackable:false,startAtZero:true,valueDecimals:3}} height={360}/>}
  {s.id==='domain'&&<SmallTable id="domain-table" queryId="impossible" title="方法适用域任务的两个观察维度" rows={reviewedRows('impossible')} columns={[{key:'组别',label:'组别'},{key:'准确度满分数',label:'准确度满分',numeric:true,render:v=>`${v} / 10`},{key:'自洽满分且准确度为零',label:'自洽满分、准确度零',numeric:true}]} caption="P2最终40行，accuracy和selfc_all分开计数。"/>}
  {s.id==='effort'&&<>
   <Chart id="effort-chart" queryId="effort" title="同一15题：平均QM作业时长" spec={{type:'horizontalBar',x:'arm',y:'mean_job_hours',xLabel:'',yLabel:'job-hours / run',startAtZero:true,valueDecimals:2}} height={300}/>
   <SmallTable id="effort-table" queryId="effort" title="同题计算投入与整理后结果" rows={reviewedRows('effort')} columns={[{key:'arm',label:'组别'},{key:'mean_job_hours',label:'作业时长均值(h)',numeric:true,render:v=>Number(v).toFixed(2)},{key:'final_repaired',label:'得分均值',numeric:true,render:f},{key:'n',label:'题数',numeric:true}]} caption="投入来自flex快照，最终分来自200行表；job-hours为QM进程墙钟之和。"/>
  </>}
  {s.id==='delivery'&&<SmallTable id="tracks-table" queryId="arms" title="运行快照与整理后的成绩" rows={reviewedRows('arms')} columns={[{key:'arm',label:'组别'},{key:'raw',label:'运行快照',numeric:true,render:f},{key:'fair',label:'表内fair',numeric:true,render:f},{key:'adjudicated',label:'归档整理后',numeric:true,render:f},{key:'缺图',label:'原fair缺图',numeric:true}]} caption="全部200行；fair保留7个standard缺图−1，整理后用其重构结果覆盖。"/>}
  {s.id==='complement'&&<Chart id="oracle-chart" queryId="oracle" title="同题的结果互补：guided与四臂逐题最高值" spec={{type:'bar',x:'题目',y:'得分',series:'选择',stackable:false,startAtZero:true,valueDecimals:3}} height={320}/>}
  {s.id==='appendix'&&<>
   <label className="mining-search">按题号、名称或tier检索 <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="例如 NU3 / Diels / normal"/></label>
   <SmallTable id="task-table" queryId="tasks" title="50题逐题结果" rows={tasks} columns={[{key:'task',label:'题号'},{key:'tier',label:'分层'},{key:'guided',label:'guided',numeric:true,render:f},{key:'record',label:'record',numeric:true,render:f},{key:'standard',label:'standard',numeric:true,render:f},{key:'brief-errors',label:'brief',numeric:true,render:f}]} caption={`${tasks.length}题 · 归档整理后得分。完整名称和结构在来源数据中保留。`}/>
  </>}
 </section>)}
 </article>;
}
