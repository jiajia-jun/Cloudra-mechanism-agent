import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
import sharp from 'sharp';

const root='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/申请材料/省自科答辩';
const fig=path.join(root,'figures');
const work=path.join(root,'.build');
const out=path.join(root,'修订版','Cloudra_省自科答辩_故事重构版_v24.pptx');
const skill='/Users/cloudrayyy/.codex/plugins/cache/openai-primary-runtime/presentations/26.921.11914/skills/presentations';
const py='/Users/cloudrayyy/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const P=Presentation.create({slideSize:{width:1280,height:720}});
const C={navy:'#194D36',blue:'#287B54',light:'#EDF6E8',gold:'#D4A921',ink:'#24372D',muted:'#5D6F62',line:'#D8E5D5',white:'#FFFFFF',soft:'#F8FBF5',red:'#B54B49',green:'#427E68'};
const font='Arial Unicode MS',pending=[];
function esc(v){return String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');}
function unit(ch){return /[\u2E80-\u9FFF\uF900-\uFAFF]/u.test(ch)?1:/[A-Z0-9]/u.test(ch)?0.63:ch===' '?0.31:0.57;}
function wrapLine(line,max){let out=[],cur='',n=0;for(const ch of [...line]){let u=unit(ch);if(cur&&n+u>max){out.push(cur);cur='';n=0;}cur+=ch;n+=u;}out.push(cur);return out;}
function raster(t,w,h,size,color,bold,align){let lines=[],z=size;for(;z>=12;z--){lines=String(t).split('\n').flatMap(a=>wrapLine(a,Math.max(1,(w-4)/z)));if(lines.length*z*1.26<=h-2)break;}let sc=2,W=Math.ceil(w*sc),H=Math.ceil(h*sc),lh=z*1.26*sc,top=(H-lines.length*lh)/2+z*sc,anchor=align==='center'?'middle':align==='right'?'end':'start',x=align==='center'?W/2:align==='right'?W-2:2;let spans=lines.map((a,i)=>`<text x="${x}" y="${top+i*lh}" fill="${color}" font-family="Arial Unicode MS" font-size="${z*sc}" font-weight="${bold?'bold':'normal'}" text-anchor="${anchor}">${esc(a)}</text>`).join('');return sharp(Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">${spans}</svg>`)).png().toBuffer();}
function rect(s,x,y,w,h,fill=C.white,stroke='none',radius=0){return s.shapes.add({geometry:radius?'roundRect':'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:stroke,width:stroke==='none'?0:1},borderRadius:radius||undefined});}
function txt(s,t,x,y,w,h,size=24,color=C.ink,bold=false,align='left'){pending.push(raster(t,w,h,size,color,bold,align).then(buf=>s.images.add({blob:new Uint8Array(buf),contentType:'image/png',alt:String(t),fit:'contain',position:{left:x,top:y,width:w,height:h}})));}
function base(title,kicker='问题与证据'){let s=P.slides.add();s.background.fill=C.white;rect(s,0,0,1280,12,C.navy);txt(s,kicker,60,30,450,28,16,C.gold,true);txt(s,title,60,62,1160,69,34,C.navy,true);rect(s,60,140,1160,2,C.gold);return s;}
function foot(s,source,num,tag='依据'){rect(s,0,665,1280,55,C.soft);rect(s,60,665,1160,1,C.line);txt(s,tag+'｜'+source,60,674,1090,28,14,C.muted);txt(s,String(num).padStart(2,'0'),1160,674,60,28,14,C.muted,false,'right');}
function note(s,body,refs=[]){s.speakerNotes.textFrame.setText(body+'\n\n参考文献／数据来源：\n'+refs.join('\n'));}
function box(s,head,body,x,y,w,h=105,accent=C.blue){rect(s,x,y,w,h,C.soft,C.line,10);rect(s,x,y,6,h,accent);txt(s,head,x+22,y+10,w-36,34,22,C.navy,true);txt(s,body,x+22,y+47,w-36,h-54,18,C.ink);}
function pill(s,t,x,y,w,fill=C.light,color=C.navy){rect(s,x,y,w,39,fill,C.line,9);txt(s,t,x+7,y+5,w-14,29,17,color,true,'center');}
async function addImg(s,file,x,y,w,h,alt){let b=await fs.readFile(path.join(fig,file));if(file.endsWith('.svg'))b=await sharp(b,{density:180}).png().toBuffer();s.images.add({blob:new Uint8Array(b),contentType:file.endsWith('.jpg')?'image/jpeg':'image/png',alt,fit:'contain',position:{left:x,top:y,width:w,height:h}});}
const U={
review:'https://doi.org/10.1021/acscatal.5c01202',cat:'https://arxiv.org/abs/2606.05050',arche:'https://arxiv.org/abs/2609.11147',
auto:'https://doi.org/10.1002/anie.202011941',automekin:'https://doi.org/10.1002/jcc.26734',afir:'https://doi.org/10.1021/acs.accounts.6b00023',
network:'https://doi.org/10.1146/annurev-physchem-071119-040123',steiner:'https://doi.org/10.1007/s11244-021-01543-9',
fukui:'https://doi.org/10.1021/j100717a029',q2mm:'https://doi.org/10.1021/acs.accounts.6b00037',
rdkit:'https://www.rdkit.org/docs/RDKit_Book.html#atropisomeric-bonds',cjc:'https://doi.org/10.1002/cjoc.70691',
atropo:'https://doi.org/10.1038/s41929-024-01138-z',bioactive:'https://pubmed.ncbi.nlm.nih.gov/38515232/',
el:'https://arxiv.org/abs/2505.02484'
};
// 01 封面
{
let s=P.slides.add();s.background.fill=C.white;rect(s,0,0,1280,15,C.navy);rect(s,72,168,10,356,C.gold);
txt(s,'基于智能代理的轴手性体系\n过渡态自动化搜索与催化模型研究',108,170,1080,188,48,C.navy,true);
txt(s,'Cloudra：面向复杂有机反应机理计算的自主科学智能体',110,397,1055,60,27,C.gold,true);
txt(s,'杨程驿  ｜  长沙理工大学 化学与医药工程学院',109,553,970,42,22,C.muted);
note(s,'面向评委汇报：针对复杂有机反应中过渡态难找、微观路径难证伪的瓶颈，介绍自主科学智能体 Cloudra 的研究方案与进展。',['项目申请材料（内部）']);}
// 03 领域分布
{
let s=base('自动化研究已经很多，但研究对象分布并不均衡','现有工作');
rect(s,65,179,1145,400,C.soft,C.line,12);
txt(s,'AI 与自动化计算正在进入催化研究',93,200,1080,50,27,C.navy,true,'center');
const a=[['异相催化','固体表面上的反应','已有专门的智能体综述与完整系统实例'],['均相催化','分子在溶液等同一相中反应','相关 AI 研究存在，但复杂机理闭环仍需深入'],['本报告聚焦','复杂有机均相机理','尤其关注三维建模与过渡态验证']];
a.forEach((v,i)=>{let x=91+i*371;rect(s,x,275,346,231,i===2?'#FFF8EB':C.white,C.line,10);txt(s,v[0],x+18,291,310,40,25,i===2?C.gold:C.navy,true);txt(s,v[1],x+18,347,310,46,21,C.ink);txt(s,v[2],x+18,416,310,60,18,C.muted);});
txt(s,'现有自动化在均相反应中仍面临独特瓶颈：复杂有机机理的三维建模与过渡态搜索难度更高。',82,584,1118,49,20,C.ink,true,'center');
foot(s,'Morán-González et al., ACS Catal. 2025, Fig. 1；Steiner & Reiher 2022；CatDT 2026',2);
note(s,'介绍 AI 催化研究的领域分布：异相催化已有较多自动化系统，而均相反应因涉及复杂三维构象和过渡态微观路径，具有独特的挑战。',[U.review,U.steiner,U.cat]);}
// 04 CatDT 实例
{
let s=base('CatDT：把反应机理当作一张可以探索的路径网','对照实例');
await addImg(s,'figref_catdt_fig3_unimech_benchmark.png',59,180,718,429,'CatDT论文图3：候选反应网络、筛选与搜索');
box(s,'节点是什么？','一种可能的物质或表面状态。',799,183,409,104,C.blue);
box(s,'边是什么？','从一种状态走到另一种状态的反应步骤。',799,307,409,104,C.blue);
box(s,'怎样避免全算？','规则生成候选，智能筛选，再按能量剪枝。',799,431,409,104,C.gold);
foot(s,'Song et al., CatDT 2026, Fig. 3；论文中的 UniMech 采用候选生成、筛选和图搜索',3);
note(s,'介绍 CatDT 的路径网思路：将机理探索解构为网络拓扑搜索，通过规则生成与能量筛选保留有希望的路径。',[U.cat]);}
// 05 CatDT 的方法为何不能直接搬用
{
let s=base('把“路径网”搬到复杂有机反应，还缺少三维这一层','第一个转折');
await addImg(s,'fig_p4_network_to_poses_green_v3.svg',60,180,690,401,'表面反应网络与复杂有机反应空间对照示意');
box(s,'网络可描述“变了哪些键”','但同一键连关系，分子可以摆出许多不同形状。',777,189,438,105,C.blue);
box(s,'三维空间更自由','有机分子具有丰富的构象变化与空间取向，自由度显著增加。',777,314,438,105,C.gold);
box(s,'有机机理还要问','哪些分子姿态真的能够靠近并发生目标反应？',777,439,438,105,C.red);
foot(s,'CatDT 2026；Steiner & Reiher 2022；Young et al. 2021',4);
note(s,'对比 CatDT 的表面反应网络：均相有机反应具有更高的三维构象与取向自由度，因此需要深入到三维姿态层面的候选生成与核验。',[U.cat,U.steiner,U.auto]);}
// 06 组合爆炸
{
let s=base('同一条化学路径，可能对应大量不同的三维尝试','为什么难');
await addImg(s,'fig_p5_3d_space_green_v2.svg',54,179,678,420,'原创SVG：同一路径对应多种三维反应姿态');
box(s,'选哪条路线？','可能有多种成键、断键或竞争反应。',760,184,455,103,C.blue);
box(s,'分子怎样摆？','催化剂与底物有多种相对位置和构象。',760,310,455,103,C.blue);
box(s,'从哪里开始找？','计算需要一个接近目标的三维初始结构。',760,436,455,103,C.gold);
foot(s,'Young et al. 2021；Hansen et al. 2016；Steiner & Reiher 2022',5);
note(s,'说明多步机理在路径选择、构象姿态与初始结构搜索上的组合空间，引出从“盲目尝试”转向“在候选中选择”的必要性。',[U.auto,U.q2mm,U.steiner]);}
// 07 用户提供势能面
{
let s=P.slides.add();s.background.fill=C.white;await addImg(s,'fig_pes_user_supplied.jpg',100,0,1080,720,'申请人提供的势能面与反应路径图');
note(s,'向评委直观阐释：反应物和产物像地形图中的两个位置，机理计算的核心在于找到连接两侧的最高山口——过渡态。在多维复杂势能面上，寻找这个一阶鞍点需要高质量的初始猜测与可靠物理校核。',[U.fukui,'图源：申请人提供']);}
// 08 传统人工计算
{
let s=base('传统机理计算：程序会算，研究者反复决定算什么','人工循环');
await addImg(s,'fig_p3_computation_vs_questions_green_v3.svg',60,183,686,414,'计算程序黑箱与计算前后人工判断示意');
box(s,'计算之前','研究者提出路径、选构象、构建起始结构。',774,183,438,105,C.blue);
box(s,'计算运行','软件优化结构并求取能量等物理量。',774,309,438,105,C.blue);
box(s,'计算之后','研究者辨认结果、否定错误假设、决定下一步。',774,435,438,105,C.gold);
foot(s,'Young et al. 2021；ARCHE 2026；CatDT 2026',7);
note(s,'指出传统计算化学的痛点：底层量化软件具备高精度计算能力，但计算前后的假设提出与结果判断高度依赖人工反复介入。',[U.auto,U.arche,U.cat]);}
// 09 传统工作流
{
let s=base('固定工作流解决了大量重复劳动','自动化的基础');
await addImg(s,'fig_p6_workflow_green_v2.svg',77,177,1125,438,'原创SVG：固定工作流与开放机理探索对照');
rect(s,95,614,1090,42,C.light,C.line,10);txt(s,'autodE、AutoMeKin、AFIR 等证明：许多路径搜索与重复计算可以自动化。',119,619,1042,31,20,C.navy,true,'center');
foot(s,'Young et al. 2021；Martínez-Núñez et al. 2021；Maeda & Morokuma 2016',8);
note(s,'肯定 autodE、AutoMeKin 等工作流对重复计算自动化的贡献，同时指出：当探索开放机理遭遇非预期结果时，系统需要更高层次的科学判断。',[U.auto,U.automekin,U.afir]);}
// 10 从固定流程过渡到开放决策
{
let s=base('工作流按步骤完成后，仍可能出现预设之外的结果','从自动执行到科学判断');
const q=[['预定任务','优化目标结构，再检查计算是否正常结束。'],['计算结果','程序成功结束，但结构沿另一条通道变化。'],['新问题','要重建原目标，还是把这条通道作为新假设？']];
q.forEach((v,i)=>{let x=62+i*399;rect(s,x,191,373,307,i===2?'#FFF8EB':C.soft,C.line,12);rect(s,x,191,373,8,i===2?C.gold:C.blue);txt(s,v[0],x+22,220,329,55,27,C.navy,true,'center');txt(s,v[1],x+27,306,319,112,23,C.ink,false,'center');});
rect(s,74,530,1132,101,C.light,C.line,11);txt(s,'固定规则能发现偏离、停止或重试；是否改变研究路径，需要根据化学证据作判断。',103,548,1074,65,24,C.navy,true,'center');
foot(s,'工作流与智能研判协作示意；相关背景：Young et al. 2021；ARCHE 2026',9);
note(s,'说明工作流与智能判断的互补：固定流程能处理常规异常；当计算偏离原假设时，需要根据化学证据研判是修正目标还是新开路径。',[U.auto,U.arche]);}
// 10 需要智能
{
let s=base('什么时候需要智能？当新证据改变了原来的问题','方法哲学');
const rows=[['已经确定的步骤','按规则执行、记录、校验','交给程序'],['出现多个合理候选','比较、取舍、决定资源投向','需要判断'],['结果偏离原假设','解释偏离，并决定修正还是新开路径','需要判断']];
rows.forEach((a,i)=>{let y=185+i*125;rect(s,68,y,1144,107,i===0?C.light:i===1?C.soft:'#FFF8EB',C.line,10);txt(s,a[0],91,y+19,298,59,24,C.navy,true);txt(s,a[1],410,y+18,575,61,21,C.ink);pill(s,a[2],1000,y+32,178,i===0?C.light:'#FFF0D9',i===0?C.navy:C.gold);});
txt(s,'智能的价值在于根据证据作选择，而不是替软件维持日常运行。',80,587,1120,49,25,C.navy,true,'center');
foot(s,'ARCHE 2026；CatDT 2026；项目原型架构（内部）',10);
note(s,'确立分工原则：确定性程序负责按规则执行与校验；智能体专注于候选评判、证据权衡与科学决断。',[U.arche,U.cat,'Cloudra项目原型（内部）']);}
// 11 ARCHE
{
let s=base('ARCHE 已展示智能体研究有机机理的闭环','近邻工作');
await addImg(s,'figref_arche_fig1_architecture.png',60,183,677,416,'ARCHE论文图1架构示意');
box(s,'它做到了什么','提出机理假设、组织计算，并根据计算结果修正解释。',765,186,447,112,C.blue);
box(s,'对我们的启发','智能体确实能在开放式机理问题中作科学判断。',765,322,447,105,C.green);
box(s,'我们的思考','怎样减少对模型知识与专门训练的依赖，兼顾通用与严谨？',765,453,447,105,C.gold);
foot(s,'Li et al., ARCHE, arXiv:2609.11147, Fig. 1；预印本',11,'论文图源');
note(s,'评述 ARCHE 的机理闭环成果，确立 Cloudra 的技术路线：不依赖高成本的专用模型微调，而是通过通用模型协同专业工具链推进机理研究。',[U.arche]);}
// 12 novelty 1
{
let s=base('创新一：让模型从“凭空猜结构”转为“在候选中选择”','Cloudra 方法一');
const q=[['生成候选','反应规则、结构搜索与化学工具先提出可能路径和三维姿态'],['智能选择','agent 结合任务目标与已有证据，决定哪些候选值得进一步计算'],['计算检验','保留竞争假设，用实际计算结果淘汰或修正']];
q.forEach((a,i)=>{let x=66+i*399;rect(s,x,190,374,310,C.soft,C.line,12);rect(s,x,190,374,63,i===1?C.gold:C.blue);txt(s,a[0],x+18,202,338,39,26,C.white,true,'center');txt(s,a[1],x+27,286,318,134,23,C.ink);});
rect(s,76,536,1129,86,'#FFF8EB',C.line,10);txt(s,'Harness 把没有边界的“猜”，转化为有候选、有依据、可被证伪的“选”。',102,553,1078,49,26,C.navy,true,'center');
foot(s,'参照：ARCHE 2026；CatDT 2026；Cloudra 研究方案（内部）',12,'创新论述');
note(s,'阐释创新一：突破大模型直接猜测分子三维坐标的局限，将无边界的“猜”，转化为物理工具生成候选空间中的“选”与“验”。',[U.arche,U.cat,'Cloudra研究方案（内部）']);}
// 13 novelty 2 against CatDT
{
let s=base('创新二：把日常运行负担继续移出 agent','Cloudra 方法二');
rect(s,65,181,551,409,C.soft,C.line,12);rect(s,663,181,551,409,C.soft,C.line,12);
txt(s,'CatDT 的重要启发',91,198,495,50,27,C.navy,true);
await addImg(s,'figref_catdt_fig2a_agent_architecture.png',82,266,516,235,'CatDT论文图2a多代理架构');
txt(s,'agent 与确定性工具分工，已有验证与记忆机制。',89,510,500,62,18,C.ink);
txt(s,'Cloudra 的进一步取舍',689,198,495,50,27,C.navy,true);
box(s,'程序常驻','任务调度、等待、日志解析、状态持久化与常规恢复。',691,262,494,98,C.blue);
box(s,'agent 按需介入','规则无法处理的异常，以及新的科学选择。',691,377,494,98,C.gold);
txt(s,'运行时不必依赖模型持续“记住”和盯守。',699,506,474,58,19,C.ink,true);
foot(s,'Song et al., CatDT 2026, Fig. 2a；Cloudra 原型设计（内部）',13,'论文图源与方案');
note(s,'阐释创新二：构建分工协同的运行架构，将任务调度、等待、状态持久化与常规恢复交给程序；智能体专注于开放科学判断。',[U.cat,'Cloudra原型设计（内部）']);}
// 14 novelty 2 how
{
let s=base('工作流不只是步骤清单，而是能长期运行的研究过程','Cloudra 方法二');
const a=[['发起任务','agent 选择目标与候选'],['自动执行','系统安排计算、等待完成、收集数据'],['程序先验收','检查格式、几何、频率及阶段要求'],['遇到断点再判断','agent 解释意外，选择修正或改走新路径']];
a.forEach((v,i)=>{let y=184+i*105;rect(s,108,y,1060,83,i===3?'#FFF8EB':C.soft,C.line,9);rect(s,124,y+14,48,48,i===3?C.gold:C.blue);txt(s,String(i+1),124,y+19,48,34,22,C.white,true,'center');txt(s,v[0],195,y+13,235,54,24,C.navy,true);txt(s,v[1],453,y+13,675,54,22,C.ink);});
foot(s,'Cloudra 原型设计（内部）；相关系统先例：CatDT 2026',14,'设计主张');
note(s,'展示长程科研任务的四步推进流程：从目标设定到自动化管线执行，前置检查，在关键断点处触发智能体重新评估。',[U.cat,'Cloudra原型设计（内部）']);}
// 15 novelty 3
{
let s=base('创新三：把科学问题和证据保存在机理图中','Cloudra 方法三');
await addImg(s,'fig_p13_mechanism_evidence_green_v3.svg',61,176,721,427,'Cloudra机理图和多代理闭环示意');
box(s,'图记录“研究什么”','每个物种、每条路径、竞争假设及其证据都可追溯。',804,184,406,103,C.blue);
box(s,'工具帮助“怎样建模”','专业工具提出并检查三维结构与过渡态候选。',804,309,406,103,C.blue);
box(s,'规则核查“能否相信”','程序依据计算证据判断结果能否进入结论。',804,434,406,103,C.gold);
foot(s,'Cloudra 原型设计（内部）；相关背景：ARCHE 2026；Unsleber & Reiher 2020',15,'方案与依据');
note(s,'阐释核心创新三：提出机理证据图，将反应物种拓扑与量化计算证据深度绑定，实现每个阶段结论均有物理数据可溯源、可复核。',[U.arche,U.network,'Cloudra原型设计（内部）']);}
// 16 validation example
{
let s=base('软件显示“成功”，科学问题仍可能没有被回答','为什么要校验');
rect(s,67,191,544,316,C.soft,C.line,12);rect(s,667,191,544,316,C.soft,C.line,12);
txt(s,'计算程序的回答',94,214,488,50,27,C.navy,true,'center');
txt(s,'结构优化结束\n输出文件正常\n得到一个稳定结构',105,290,466,174,28,C.green,true,'center');
txt(s,'机理研究还要问',694,214,488,50,27,C.navy,true,'center');
txt(s,'它还是目标物种吗？\n它通向预期产物吗？\n它支持所声称的反应路径吗？',703,284,467,183,27,C.red,true,'center');
rect(s,77,543,1125,73,'#FFF8EB',C.line,10);txt(s,'计算完成 ≠ 假设成立；未通过核查的结果不能直接写入机理结论。',99,557,1081,43,25,C.navy,true,'center');
foot(s,'Fukui 1970；Young et al. 2021；Cloudra 方法设计（内部）',16);
note(s,'强调物理核验的必要性：程序优化收敛不等于化学机理正确，必须通过结构、振动分析和反应路径实施多层物理核验。',[U.fukui,U.auto,'Cloudra方法设计（内部）']);}
// 17 方法与评价贡献总览
{
let s=base('三项方法创新，加上一套独立评价方法','Cloudra 的研究贡献');
const a=[['一｜智能选择','化学工具提出候选；Agent 根据证据决定算什么。'],['二｜自主运行','系统承担执行、等待与恢复；Agent 处理科学断点。'],['三｜证据机理','机理图记录每个结构、步骤与计算依据。'],['四｜独立评价','用交付图和计算日志检验科学成果。']];
a.forEach((v,i)=>{let x=61+i*304;rect(s,x,189,281,325,i===2?'#FFF8EB':C.soft,C.line,13);rect(s,x,189,281,8,i===2?C.gold:C.blue);txt(s,v[0],x+20,221,241,68,24,C.navy,true);txt(s,v[1],x+20,313,241,149,21,C.ink);});
txt(s,'前面解释了为什么需要这套方法；下面展示它如何落实为能运行、能核查的系统。',80,557,1121,67,24,C.navy,true,'center');
foot(s,'Cloudra 方法设计与实现；相关对照：CatDT 2026、ARCHE 2026',17,'研究贡献');
note(s,'总结项目的四大核心贡献（智能选择、自主运行、证据机理、独立评价），并自然过渡到后续技术实现与体系验证环节。',[U.cat,U.arche,'Cloudra源码与测试']);}
// 18-26 技术论证：系统架构、多维协作与证据分层呈现
{
let s=base('中断不丢账：研究状态可恢复','创新二｜可靠运行');
await addImg(s,'fig_runtime_event_trace_v1.svg',61,171,1158,425,'根据Cloudra事件机制绘制的任务中断与恢复时间线');
txt(s,'关键状态变化记录为事件，重启后根据记录可完整恢复研究进度。',105,603,1065,43,22,C.navy,true,'center');
foot(s,'Cloudra 运行内核、状态持久化与恢复机制',18,'系统实现');
note(s,'介绍系统的可靠运行机制：关键状态先保存再生效，确保即使遭遇意外中断也能完整审计并恢复科研进度。代码：cloudra/runtime_v2/commands.py、events.py、apply.py、persistence.py。',['Cloudra源码与测试','图：基于内部实现绘制']);}
{
let s=base('AgentHub 让不同专长的 Agent 直接协作','创新一、二｜协作与知识');
await addImg(s,'fig_agenthub_gpt_green_v1.png',60,157,1160,486,'AgentHub 多智能体协作与知识检索体系架构示意');
txt(s,'公开讨论',81,221,302,40,24,C.navy,true);txt(s,'发现与问题留在项目中',81,263,308,40,18,C.ink);
txt(s,'同伴求助',81,335,302,40,24,C.navy,true);txt(s,'专长 Agent 彼此邀请',81,377,308,40,18,C.ink);
txt(s,'知识检索',81,449,302,40,24,C.navy,true);txt(s,'论文、计算与假设分级',81,491,308,40,18,C.ink);
foot(s,'Cloudra AgentHub 与知识检索机制',19,'系统实现');
note(s,'展示 AgentHub 多智能体协作与知识检索：支持同级专长 Agent 之间的自组织协作，并分层整合文献知识、计算数据与预测假设。代码：cloudra/runtime_v2/hub_bridge.py、knowledge.py；cloudra/knowledge/plugin.py。',['Cloudra源码与测试']);}
{
let s=base('化学工具覆盖从分子输入到科学解释','创新一｜候选与证据');
await addImg(s,'fig_conformers_gpt_green_v1.png',60,157,1160,486,'化学工具链与多维分子姿态候选生成示意');
const a=[['识别对象','结构与原子对应'],['生成候选','构象、反应与过渡态初猜'],['执行计算','输入、提交和追踪'],['解释结果','日志、电子与热化学']];
a.forEach((v,i)=>{let y=196+i*96;txt(s,v[0],81,y,324,37,24,C.navy,true);txt(s,v[1],81,y+36,331,48,18,C.ink);});
foot(s,'Cloudra 化学工具注册表与功能分组',20,'工具覆盖');
note(s,'展示专业化学工具覆盖：涵盖分子表示、三维构象搜索、过渡态初猜、量化计算调度与结果解释，为智能体提供扎实的操作能力。代码：cloudra/tools/registry.py。',['Cloudra源码：cloudra/tools/registry.py']);}
{
let s=base('程序推进常规步骤，Agent 处理科学断点','创新二｜工作流');
const a=[['1 设定目标','Agent 确定反应对象、候选路径和计算方法。'],['2 自动推进','系统准备结构与输入，提交计算并等待回报。'],['3 程序检查','结果解析与阶段条件由工具先行核查。'],['4 科学判断','当原子对应或结构假设需要修正时，Agent 决定下一步。']];
a.forEach((v,i)=>{let y=171+i*107;rect(s,91,y,1098,84,i===3?'#FFF8EB':C.soft,C.line,10);txt(s,v[0],115,y+13,229,55,23,C.navy,true);txt(s,v[1],358,y+11,794,58,22,C.ink);});
txt(s,'过渡态搜索有可恢复的过程状态：启动一次，在真正需要判断处继续。',79,605,1124,42,22,C.navy,true,'center');
foot(s,'Cloudra 过渡态流程、计算调度器与事件通知',21,'工作流设计');
note(s,'以过渡态搜索为例：流程推进建模、初猜和计算；在真正需要判断处请智能体介入研判，实现高效率的人机分工。代码：cloudra/tools/Chemtool/ts_search_process.py、cloudra/scheduler/。',['Cloudra源码与测试']);}
{
let s=base('机理图把每一步结论与计算依据绑定','创新三｜科学证据');
await addImg(s,'fig_dag_evidence_matrix_v1.svg',61,171,1158,425,'根据DAG阶段契约绘制的机理与证据关系示意');
txt(s,'完成由实际计算证据决定，未满足的阶段仍是研究缺口。',90,604,1100,42,22,C.navy,true,'center');
foot(s,'Cloudra 机理证据图、阶段契约与证据绑定测试',22,'核心科学贡献');
note(s,'说明机理证据图的阶段契约：每个基元反应步骤均绑定量化收敛、虚频单一性与 IRC 路径连通等物理证据，杜绝模型幻觉。代码：cloudra/dag/models.py、completion.py、evidence_ingest.py。',['Cloudra源码与测试','图：依据内部实现绘制']);}
{
let s=base('经验跨任务保留，下一次少走弯路','创新二｜可控记忆');
const a=[['记录经验','Agent 总结可复用的操作方法和失败教训。'],['跨任务使用','长期记忆在新任务中加载，过长内容压缩并保留归档。'],['与证据分层','经验帮助决定先尝试什么；科学结论仍依赖本次计算。']];
a.forEach((v,i)=>{let x=63+i*398;rect(s,x,191,373,316,i===2?'#FFF8EB':C.soft,C.line,12);rect(s,x,191,373,8,i===2?C.gold:C.blue);txt(s,v[0],x+23,229,326,62,26,C.navy,true);txt(s,v[1],x+23,317,326,130,22,C.ink);});
txt(s,'知识库保存有来源的研究材料；记忆保存跨任务可复用的做法。',80,561,1120,68,24,C.navy,true,'center');
foot(s,'Cloudra 长期记忆、记忆范围检查与知识层',23,'经验积累');
note(s,'介绍经验记忆机制：在严格隔离项目私有数据的前提下，实现通用操作经验与调试策略的跨任务复用。代码：cloudra/persistence/memory.py、cloudra/tools/core/memory_scope_guard.py。',['Cloudra源码与测试']);}
{
let s=base('一套考卷，检验四类不同的科学能力','创新四｜Benchmark 设计');
const a=[['基础','D1','一步反应'],['复杂','NQ1','多步与重排'],['立体选择','HH1','轴构型竞争'],['方法边界','IA1','电子结构边界']];
for(let i=0;i<a.length;i++){let x=60+i*300; if(i)rect(s,x-9,190,1,352,C.line);txt(s,a[i][0],x+12,187,260,53,25,i===3?C.gold:C.navy,true,'center');await addImg(s,`fig_benchmark_${a[i][1]}.svg`,x+10,253,265,216,`Benchmark ${a[i][1]} 题的真实底物二维结构`);txt(s,a[i][2],x+13,484,260,45,21,C.ink,false,'center');txt(s,a[i][1],x+13,532,260,37,17,C.muted,false,'center');}
txt(s,'四档题目以真实反应为载体，逐级考查计算、路径选择和方法边界。',80,605,1120,42,22,C.navy,true,'center');
foot(s,'Cloudra Benchmark 题目规范与四档题集',24,'评价设计');
note(s,'介绍评测基准设计：覆盖基础单步、多步重排、三维选择性及方法适用边界，全面评估科学智能体在真实反应中的解决能力。代码：cloudra/benchmark/schema.py、gen_*_tasks.py；ideapool/tasks/。',['Cloudra题目：ideapool/tasks/easy/D1.json','ideapool/tasks/normal/NQ1.json','ideapool/tasks/hard/HH1.json','ideapool/tasks/impossible/IA1.json']);}
{
let s=base('评价只读取交付图和计算日志','创新四｜Benchmark 评分');
txt(s,'从可追溯的交付物，提取三种不同的成绩',75,179,1119,45,24,C.navy,true,'center');
rect(s,79,268,1120,83,'#E4EEDC');rect(s,79,268,112,83,'#91BE92');rect(s,191,268,336,83,C.blue);rect(s,527,268,672,83,C.gold);
txt(s,'10%',81,281,108,49,28,C.navy,true,'center');txt(s,'30%',193,281,332,49,28,C.white,true,'center');txt(s,'60%',529,281,668,49,28,C.navy,true,'center');
const a=[['机理覆盖','物种与步骤是否对应参考机理？'],['证据自洽','结构、过渡态与路径有无计算支持？'],['结果准确','能垒、性质或选择性是否吻合？']];
a.forEach((v,i)=>{let x=78+i*381;txt(s,v[0],x,381,360,52,25,C.navy,true,'center');txt(s,v[1],x+7,447,346,74,19,C.ink,false,'center');});
txt(s,'输入：机理交付图＋计算日志；不读取 Agent 的结论性文字。',90,578,1100,60,22,C.navy,true,'center');
foot(s,'Cloudra 独立评分器：图结构、自洽性、准确性与运行溯源',25,'评价方法');
note(s,'介绍独立评分体系：完全以交付图和量化日志为输入，通过机理覆盖、证据自洽与结果准确三层严密打分，确保评价客观公正。代码：cloudra/benchmark/runner.py、graph_similarity.py、selfconsistency.py、accuracy.py。',['Cloudra源码与测试']);}
{
let s=base('从复杂有机机理出发，迈向通用化学 Agent','研究路径');
await addImg(s,'fig_evidence_gpt_green_v1.png',60,157,1160,486,'绿色与黄色插图：知识、计算和证据层次演进');
txt(s,'已有基础',83,225,321,43,24,C.navy,true);txt(s,'运行、协作、工具与机理证据图',83,268,354,57,18,C.ink);
txt(s,'当前局限',83,350,321,43,24,C.navy,true);txt(s,'项目处于推进期，正在全面完善形式化 Benchmark',83,393,354,57,18,C.ink);
txt(s,'未来展望',83,475,321,43,24,C.navy,true);txt(s,'在轴手性体系深入验证，逐步迈向通用化学 Agent',83,518,354,57,18,C.ink);
foot(s,'Cloudra 体系演进与省自科项目研究规划',26,'研究展望');
note(s,'总结研发推进与演进展望：当前已打通运行底座、工具矩阵与机理证据图闭环；项目目前处于系统推进期，正在全面完善形式化 Benchmark 评测题集；未来将依托轴手性等复杂机理攻关，逐步拓展复用，最终迈向通用的化学 Agent。',['Cloudra源码与项目研究计划']);}
// 18 为什么轴手性
{
let s=base('为什么用轴手性检验这套方法？','目标体系');
await addImg(s,'fig_p11_central_vs_axial_nb.v1.png',57,175,694,423,'中心手性与轴手性示意');
box(s,'“手性”不总是一个固定标签','轴构型依赖三维排列与受阻旋转，普通二维连接关系不足以自动判定。',776,183,437,113,C.blue);
box(s,'姿态决定反应','同一分子可能摆出多个构象，进入不同过渡态与产物通道。',776,322,437,113,C.gold);
box(s,'因此适合压测','候选生成、智能选择与物理核验必须同时工作。',776,461,437,104,C.red);
foot(s,'RDKit Book；Hansen et al. 2016；Zhang, Yang et al. 2026',27);
note(s,'解释选择轴手性体系的原因：阻转异构由整段分子的三维空间受阻旋转决定，无法单纯依赖二维平面结构，最能检验系统的三维建模与立体选择性辨别能力。',[U.rdkit,U.q2mm,U.cjc]);}
// 20 轴手性问题本身的研究价值
{
let s=base('轴手性不仅是压测题，也是药物与催化中的真实问题','研究价值');
const a=[
['药物分子','部分轴手性分子的两种空间形式，生物活性可能明显不同。'],
['手性催化','轴手性骨架也常用于手性配体和有机催化剂，帮助控制产物的空间形状。'],
['关键科学问题','要选择性制得目标形式，必须理解哪一种反应姿态和路径占优势。']
];
a.forEach((v,i)=>{let x=63+i*399;rect(s,x,188,374,328,i===2?'#FFF8EB':C.soft,C.line,13);rect(s,x,188,374,8,i===2?C.gold:C.blue);txt(s,v[0],x+23,219,328,61,27,C.navy,true,'center');txt(s,v[1],x+28,316,318,145,23,C.ink,false,'center');});
rect(s,71,548,1138,77,C.light,C.line,10);txt(s,'因此，弄清“哪条路生成哪一种轴构型”，才能为选择性合成与催化剂设计提供依据。',95,561,1091,50,23,C.navy,true,'center');
foot(s,'Xiang et al., Nat. Catal. 2024；Bioactive atropisomers review, 2024',28);
note(s,'阐明轴手性体系的应用价值：阻转异构骨架广泛见于药物、手性配体和催化剂，理解空间姿态与竞争路径对高选择性不对称催化合成具有重要意义。',[U.atropo,U.bioactive,U.cjc]);}
// 19 研究基础
{
let s=base('已有研究表明：轴手性的关键差别藏在三维结构中','申请人基础');
await addImg(s,'cjc_toc_graphic.png',57,187,674,406,'申请人共同一作N-N轴手性论文TOC图');
box(s,'已有论文','申请人共同一作工作研究了金字塔化 N–N 轴手性体系。',763,190,449,103,C.blue);
box(s,'对本项目的启发','轴旋转、氮反转和反应姿态可能共同影响选择性。',763,315,449,103,C.gold);
box(s,'本项目的检验','用系统自动提出关键候选，并用计算证据区分竞争路径。',763,440,449,103,C.green);
foot(s,'Zhang, Yang et al., Chin. J. Chem. 2026, 44, 3033–3042；图源：论文 TOC',29,'论文图源');
note(s,'介绍申请人前期研究基础：申请人共同一作工作深入研究了 N–N 轴手性体系，具备扎实的化学体系基础，为本项目智能体系统的构建提供了真实的科学依据。',[U.cjc]);}
// 20 模型策略
{
let s=base('Fine-Tuning is not Magic：能力应放在合适的位置','模型与系统的取舍');
rect(s,67,184,547,343,C.soft,C.line,12);rect(s,664,184,547,343,C.soft,C.line,12);
txt(s,'ARCHE：专用化学模型',91,202,495,51,27,C.navy,true);
box(s,'潜在优势','针对特定软件和常见计算任务强化输入、解读与诊断。',89,275,500,101,C.blue);
box(s,'需要付出','训练数据、训练与后续版本维护；可靠性仍需工具验证。',89,399,500,101,C.gold);
txt(s,'Cloudra：通用模型 + 专业工具',689,202,495,51,27,C.navy,true);
box(s,'当前选择','不以专门微调为前提，把候选生成和例行工序交给系统。',686,275,500,101,C.blue);
box(s,'方法优势','用专业工具保证计算可靠性，通用模型专注科学判断。',686,399,500,101,C.gold);
txt(s,'把例行执行交给系统，把高阶判断交给模型，兼顾可靠性与灵活性。',75,558,1129,66,24,C.navy,true,'center');
foot(s,'ARCHE 2026；Cloudra 项目方案与原型（内部）',30,'策略对照');
note(s,'阐明技术选型的科学性：专用模型微调维护成本高；Cloudra 路线通过通用模型协同专业工具链，将物理规律落实于工具核验中，兼顾严谨性与通用性。',[U.arche,'Cloudra项目方案与原型（内部）']);}
// 21 项目原型案例：不重复使用存在问题的旧能量剖面
{
let s=base('原型案例：把一个机理任务交付为路径与计算证据','项目案例');
rect(s,76,184,1128,394,C.soft,C.line,13);
txt(s,'甲醛 + 甲胺 → 亚胺',105,204,1071,61,32,C.navy,true,'center');
const steps=[['研究对象','反应物与产物'],['提出路径','可能的中间体与反应步骤'],['运行计算','形成结构与能量记录'],['检查交付','核对路径及其证据']];
steps.forEach((a,i)=>{let x=97+i*276;rect(s,x,301,255,196,i===3?'#FFF8EB':C.white,C.line,10);rect(s,x,301,255,8,i===3?C.gold:C.blue);txt(s,a[0],x+13,331,229,46,23,C.navy,true,'center');txt(s,a[1],x+17,401,221,67,19,C.ink,false,'center');});
txt(s,'原型任务展示了完整的自主探索过程：从提出路径到计算交付均有证据支持。',100,515,1080,46,21,C.muted,false,'center');
foot(s,'项目原型的机理任务交付；方法依据：Fukui 1970；Young et al. 2021',31,'项目案例');
note(s,'以甲醛加甲胺生成亚胺的原型任务为例，展示 Cloudra 组织机理研究的标准化闭环：从提出反应步骤到完成量化计算，并最终形成可核验的交付图。',[U.fukui,U.auto,'项目原型（内部）']);}
// 22 案例与费用
{
let s=base('少让模型盯流程，把成本留给真正的判断','原型案例');
rect(s,75,184,1129,368,C.soft,C.line,14);
txt(s,'一次原型任务的模型调用费',112,210,1050,54,29,C.navy,true,'center');
txt(s,'约 ¥2',118,273,1040,145,82,C.gold,true,'center');
txt(s,'常规计算与状态管理由系统承担，模型仅在关键判断时调用。',109,432,1065,62,21,C.muted,false,'center');
rect(s,78,572,1124,63,C.light,C.line,10);txt(s,'“四两拨千金”的来源：候选生成、长期调度和证据核查主要由工具与系统承担。',101,584,1080,40,22,C.navy,true,'center');
foot(s,'原型任务的模型调用成本统计',32,'案例数据');
note(s,'说明任务成本的经济性：常规计算排队和数据提取由本地系统负责，大模型调用仅发生在需要科学选择的关键断点，单任务模型调用费仅约数元。',['申请人原型运行数据']);}
// 23 结论
{
let s=base('Cloudra：把机理研究变成可选择、可执行、可核验的闭环','总结');
const a=[['问题','复杂有机机理不只要计算，还要决定哪些三维候选值得计算。'],['方法','智能负责有依据的选择；系统负责运行、记录与验证。'],['检验','用轴手性这一高度依赖三维姿态的体系，检验方法的有效性与成本。']];
a.forEach((v,i)=>{let y=185+i*131;rect(s,87,y,1106,109,i===2?'#FFF8EB':C.soft,C.line,12);txt(s,v[0],112,y+18,155,65,28,i===2?C.gold:C.navy,true);txt(s,v[1],285,y+15,867,76,24,C.ink);});
txt(s,'从“自动执行计算”，走向“有证据约束的自主机理探索”。',93,589,1091,49,26,C.navy,true,'center');
foot(s,'基于上述论文、项目原型与申请人研究基础',33,'研究定位');
note(s,'总结全篇：通过智能选择、自主运行与机理图物理证据核验，以轴手性催化为攻关抓手，构建有证据约束的自主机理探索闭环。',[U.cat,U.arche,U.cjc,'项目申请书（内部）']);}
// 35 备份页：化学工具覆盖细目
{
let s=base('化学工具覆盖清单：从输入到核查','备份材料｜工具覆盖');
const a=[
['分子输入','name_to_structure · image_to_smiles · smiles_to_mol\nformat_converter · cdxml_to_graph','把名称、图片或结构文件变成可计算的分子表示'],
['结构展示','molecule_drawer · pymol_render','展示二维连接与三维形状，便于研究者核对'],
['反应识别','reaction_mapping · internal_coordinates','对应反应前后原子，检查关键键、距离和角度'],
['候选生成','conformer_search · mechanism_predict · ts_guess','寻找空间姿态、反应假设与过渡态初猜'],
['过渡态流程','ts_prepare · ts_resume','推进搜索，在科学断点处请 Agent 修正声明'],
['量化计算','qm_input_writer · submit_compute_job\nquery_compute_job · query_compute_queue','准备、提交并追踪计算任务与资源'],
['结果解释','log_parser · electronic_analysis · thermo_analysis','读取日志，解释结构、电子性质和能量'],
['实验资料','ir_processor · nmr_processor','整理红外与核磁谱图，为实验对照提供材料']
];
a.forEach((v,i)=>{let y=151+i*61;rect(s,60,y,1160,55,i%2===0?C.soft:C.white,C.line,5);txt(s,v[0],70,y+8,160,36,18,C.navy,true);txt(s,v[1],228,y+8,575,39,15,C.ink);txt(s,v[2],812,y+6,395,43,16,C.muted);});
foot(s,'Cloudra 化学工具注册表与各工具实现；按科研环节分组',34,'备份材料');
note(s,'备用材料：已注册化学工具的科研环节映射，供答辩问答交流。代码清单以 cloudra/tools/registry.py 为准。',['Cloudra源码：cloudra/tools/registry.py']);}
// 36 参考文献
{
let s=base('主要论文与数据出处','参考文献');
const refs=[
'1  Morán-González et al., ACS Catalysis 2025, AI Approaches to Homogeneous Catalysis. DOI: 10.1021/acscatal.5c01202',
'2  Song et al., CatDT, arXiv:2606.05050 (2026).',
'3  Li et al., ARCHE, arXiv:2609.11147 (2026).',
'4  Young et al., autodE, Angew. Chem. Int. Ed. 2021. DOI: 10.1002/anie.202011941',
'5  Martínez-Núñez et al., AutoMeKin, J. Comput. Chem. 2021. DOI: 10.1002/jcc.26734',
'6  Maeda & Morokuma, AFIR, Acc. Chem. Res. 2016. DOI: 10.1021/acs.accounts.6b00023',
'7  Unsleber & Reiher, Annu. Rev. Phys. Chem. 2020. DOI: 10.1146/annurev-physchem-071119-040123',
'8  Steiner & Reiher, Top. Catal. 2022. DOI: 10.1007/s11244-021-01543-9',
'9  Fukui, J. Phys. Chem. 1970. DOI: 10.1021/j100717a029',
'10 Hansen et al., Acc. Chem. Res. 2016. DOI: 10.1021/acs.accounts.6b00037',
'11 Zhang, Yang et al., Chin. J. Chem. 2026. DOI: 10.1002/cjoc.70691',
'12 RDKit Book, Atropisomeric Bonds, rdkit.org/docs/RDKit_Book.html',
'13 Xiang et al., Nat. Catal. 2024, Catalytic atroposelective synthesis. DOI: 10.1038/s41929-024-01138-z',
'14 Bioactive atropisomers: design and synthesis for drug discovery, 2024. PMID: 38515232'
];refs.forEach((v,i)=>{let y=155+i*34;rect(s,65,y,1150,31,i%2?C.white:C.soft,C.line,4);txt(s,v,77,y+2,1122,27,15,C.ink);});
foot(s,'逐页完整出处及讲述提示见演讲者备注',35);
note(s,'主要参考文献与数据出处，涵盖催化、反应网络探索与 AI 智能体前沿工作。',Object.values(U));}

const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
await Promise.all(pending);
const candidate=path.join(work,'candidate_story_v24.pptx');
await (await PresentationFile.exportPptx(P)).save(candidate);
await fs.rm(out, {force: true});
await fs.rm(path.join(work, 'validation_story_v24.json'), {force: true});
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:out,pythonExecutable:py,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],requiredNativeTableOwnerSlides:[],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(work,'validation_story_v24.json')});
console.log(JSON.stringify(result));
