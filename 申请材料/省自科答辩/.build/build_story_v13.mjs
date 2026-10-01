import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
import sharp from 'sharp';

const root='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/申请材料/省自科答辩';
const fig=path.join(root,'figures');
const work=path.join(root,'.build');
const out=path.join(root,'修订版','Cloudra_省自科答辩_故事重构版_v13.pptx');
const skill='/Users/cloudrayyy/.codex/plugins/cache/openai-primary-runtime/presentations/26.921.11914/skills/presentations';
const py='/Users/cloudrayyy/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const P=Presentation.create({slideSize:{width:1280,height:720}});
const C={navy:'#1F4E79',blue:'#2564A8',light:'#EEF4FB',gold:'#D69325',ink:'#23364A',muted:'#596B7A',line:'#D7E1EC',white:'#FFFFFF',soft:'#F8FAFD',red:'#B54B49',green:'#427E68'};
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
el:'https://arxiv.org/abs/2505.02484'
};
// 01 封面
{
let s=P.slides.add();s.background.fill=C.white;rect(s,0,0,1280,15,C.navy);rect(s,72,168,10,356,C.gold);
txt(s,'基于智能代理的轴手性体系\n过渡态自动化搜索与催化模型研究',108,170,1080,188,48,C.navy,true);
txt(s,'Cloudra：面向复杂有机反应机理计算的自主科学智能体',110,397,1055,60,27,C.gold,true);
txt(s,'杨程驿  ｜  长沙理工大学 化学与医药工程学院',109,553,970,42,22,C.muted);
note(s,'开场只说任务：让计算机帮助研究者找到并验证反应如何发生。后续用已有工作一步步推出 Cloudra 的方法设计。',['项目申请材料（内部）']);}
// 02 计算化学在干什么：使用申请人指定的最终版势能面图
{
let s=P.slides.add();s.background.fill=C.white;
await addImg(s,'fig_pes_user_supplied.jpg',100,0,1080,720,'申请人指定的最终版势能面与反应路径图');
note(s,'此页使用申请人指定的最终版势能面图，替换旧版数值能量剖面。面向跨学科评委只讲：反应物和产物像地形图中的两个位置，计算化学要找出它们之间可能经过的路线与山口。图右侧细节留待后续讲过渡态时再回看。',[U.fukui,U.network,'图源：申请人提供的最终版势能面图']);}
// 03 领域分布
{
let s=base('自动化研究已经很多，但研究对象分布并不均衡','现有工作');
rect(s,65,179,1145,400,C.soft,C.line,12);
txt(s,'AI 与自动化计算正在进入催化研究',93,200,1080,50,27,C.navy,true,'center');
const a=[['异相催化','固体表面上的反应','已有专门的智能体综述与完整系统实例'],['均相催化','分子在溶液等同一相中反应','相关 AI 研究存在，但复杂机理闭环仍需深入'],['本报告聚焦','复杂有机均相机理','尤其关注三维建模与过渡态验证']];
a.forEach((v,i)=>{let x=91+i*371;rect(s,x,275,346,231,i===2?'#FFF8EB':C.white,C.line,10);txt(s,v[0],x+18,291,310,40,25,i===2?C.gold:C.navy,true);txt(s,v[1],x+18,347,310,46,21,C.ink);txt(s,v[2],x+18,416,310,60,18,C.muted);});
txt(s,'这不是“均相研究为零”，而是要问：现有自动化为何较难覆盖我们关心的复杂有机机理？',82,584,1118,49,20,C.ink,true,'center');
foot(s,'Morán-González et al., ACS Catal. 2025, Fig. 1；Steiner & Reiher 2022；CatDT 2026',3);
note(s,'Morán-González 等综述图1统计2010–2024年 Web of Science 中均相、异相和酶催化的 AI 相关论文占比。这是研究领域的文献分布，不是自主机理 agent 项目的精确计数。这里不报未经核验的数量，也不说均相化学没有自动化。',[U.review,U.steiner,U.cat]);}
// 04 CatDT 实例
{
let s=base('CatDT：把反应机理当作一张可以探索的路径网','对照实例');
await addImg(s,'figref_catdt_fig3_unimech_benchmark.png',59,180,718,429,'CatDT论文图3：候选反应网络、筛选与搜索');
box(s,'节点是什么？','一种可能的物质或表面状态。',799,183,409,104,C.blue);
box(s,'边是什么？','从一种状态走到另一种状态的反应步骤。',799,307,409,104,C.blue);
box(s,'怎样避免全算？','规则生成候选，智能筛选，再按能量剪枝。',799,431,409,104,C.gold);
foot(s,'Song et al., CatDT 2026, Fig. 3；论文中的 UniMech 采用候选生成、筛选和图搜索',4);
note(s,'CatDT不是粗暴穷举所有路径。其 UniMech 用确定性键变化操作和语言模型建议产生候选，经化学合理性筛选，再用能量估计和图搜索保留有希望的路径。对评委只讲“画路网、筛路、找主路”，不展开算法缩写。图为原论文图3，缩放后细节可作为论文证据，口述只指顶部三阶段和右下网络。',[U.cat]);}
// 05 CatDT 的方法为何不能直接搬用
{
let s=base('把“路径网”搬到复杂有机反应，还缺少三维这一层','第一个转折');
await addImg(s,'fig_p4_surface_vs_network_nb.png',60,180,690,401,'表面反应网络与复杂有机反应空间对照示意');
box(s,'网络可描述“变了哪些键”','但同一键连关系，分子可以摆出许多不同形状。',777,189,438,105,C.blue);
box(s,'表面也很复杂','CatDT 已考虑晶面、位点和表面重构；这里比较的是任务中的额外分子自由度。',777,314,438,105,C.gold);
box(s,'有机机理还要问','哪些分子姿态真的能够靠近并发生目标反应？',777,439,438,105,C.red);
foot(s,'CatDT 2026；Steiner & Reiher 2022；Young et al. 2021',5);
note(s,'不可说“异相表面简单”或“CatDT只做二维图”。CatDT论文明确处理表面重构、吸附位置与过渡态。这里比较的是本项目的有机分子三维构象、取向与手性状态如何与路径网交织。',[U.cat,U.steiner,U.auto]);}
// 06 组合爆炸
{
let s=base('同一条化学路径，可能对应大量不同的三维尝试','为什么难');
await addImg(s,'fig_p5_3d_space_clean.svg',54,179,678,420,'原创SVG：同一路径对应多种三维反应姿态');
box(s,'选哪条路线？','可能有多种成键、断键或竞争反应。',760,184,455,103,C.blue);
box(s,'分子怎样摆？','催化剂与底物有多种相对位置和构象。',760,310,455,103,C.blue);
box(s,'从哪里开始找？','计算需要一个接近目标的三维初始结构。',760,436,455,103,C.gold);
foot(s,'Young et al. 2021；Hansen et al. 2016；Steiner & Reiher 2022',6);
note(s,'图中的乘号是帮助理解的概念组合，不是严格计数公式。不要把困难只讲成“数量大”；后面要转向“如何选择值得计算的候选”。',[U.auto,U.q2mm,U.steiner]);}
// 07 用户提供势能面
{
let s=P.slides.add();s.background.fill=C.white;await addImg(s,'fig_pes_user_supplied.jpg',100,0,1080,720,'申请人提供的势能面与反应路径图');
note(s,'沿用申请人指定的图片。口述只讲：蓝色山谷是稳定结构，过渡态是山口；正常的结构优化会往低处走，所以寻找恰好连接目标两侧的山口困难。图片右侧的算法名、3N−6和高维细节不逐项讲解。该图为申请人提供的示意，并非论文结果图。',[U.fukui,'图源：申请人提供']);}
// 08 传统人工计算
{
let s=base('传统机理计算：程序会算，研究者反复决定算什么','人工循环');
await addImg(s,'fig_p3_blackbox_questions_nb.png',60,183,686,414,'计算程序黑箱与计算前后人工判断示意');
box(s,'计算之前','研究者提出路径、选构象、构建起始结构。',774,183,438,105,C.blue);
box(s,'计算运行','软件优化结构并求取能量等物理量。',774,309,438,105,C.blue);
box(s,'计算之后','研究者辨认结果、否定错误假设、决定下一步。',774,435,438,105,C.gold);
foot(s,'Young et al. 2021；ARCHE 2026；CatDT 2026',8);
note(s,'强调程序本身不替研究者决定科学问题。高水平传统工作是科学上有效的，但严重依赖人工不断提出、检查与修改候选。',[U.auto,U.arche,U.cat]);}
// 09 传统工作流
{
let s=base('固定工作流解决了大量重复劳动','自动化的基础');
await addImg(s,'fig_p6_workflow_clean.svg',77,177,1125,438,'原创SVG：固定工作流与开放机理探索对照');
rect(s,95,614,1090,42,C.light,C.line,10);txt(s,'autodE、AutoMeKin、AFIR 等证明：许多路径搜索与重复计算可以自动化。',119,619,1042,31,20,C.navy,true,'center');
foot(s,'Young et al. 2021；Martínez-Núñez et al. 2021；Maeda & Morokuma 2016',9);
note(s,'避免贬低现有自动化。autodE自动生成反应能量剖面并考虑构象，AutoMeKin探索反应网络，AFIR探索势能面。它们已解决的不只是“运行一个输入文件”。下一页的问题是：开放研究中出现未预期证据时，怎样重新界定问题。',[U.auto,U.automekin,U.afir]);}
// 10 需要智能
{
let s=base('什么时候需要智能？当新证据改变了原来的问题','方法哲学');
const rows=[['已经确定的步骤','按规则执行、记录、校验','交给程序'],['出现多个合理候选','比较、取舍、决定资源投向','需要判断'],['结果偏离原假设','解释偏离，并决定修正还是新开路径','需要判断']];
rows.forEach((a,i)=>{let y=185+i*125;rect(s,68,y,1144,107,i===0?C.light:i===1?C.soft:'#FFF8EB',C.line,10);txt(s,a[0],91,y+19,298,59,24,C.navy,true);txt(s,a[1],410,y+18,575,61,21,C.ink);pill(s,a[2],1000,y+32,178,i===0?C.light:'#FFF0D9',i===0?C.navy:C.gold);});
txt(s,'智能的价值在于根据证据作选择，而不是替软件维持日常运行。',80,587,1120,49,25,C.navy,true,'center');
foot(s,'ARCHE 2026；CatDT 2026；项目原型架构（内部）',10);
note(s,'把前几页的困难收束为边界：确定性程序做可预先规定的工作，agent处理候选与证据冲突时的判断。这里的“需要智能”不等于每个步骤都由LLM决定。',[U.arche,U.cat,'Cloudra项目原型（内部）']);}
// 11 ARCHE
{
let s=base('ARCHE 已展示智能体研究有机机理的闭环','近邻工作');
await addImg(s,'figref_arche_fig1_architecture.png',60,183,677,416,'ARCHE论文图1架构示意');
box(s,'它做到了什么','提出机理假设、组织计算，并根据计算结果修正解释。',765,186,447,112,C.blue);
box(s,'对我们的启发','智能体确实能在开放式机理问题中作科学判断。',765,322,447,105,C.green);
box(s,'接下来的问题','怎样减少对模型知识与专门训练的依赖？',765,453,447,105,C.gold);
foot(s,'Li et al., ARCHE, arXiv:2609.11147, Fig. 1；预印本',11,'论文图源');
note(s,'ARCHE是近邻，不应说它没有物理验证。论文摘要明确有通用推理模型、领域专用计算化学模型和工具库，展示三类机理任务。此页只引出我们的设计取舍，不作未经同任务实验支持的性能优劣结论。',[U.arche]);}
// 12 novelty 1
{
let s=base('创新一：让模型从“凭空猜结构”转为“在候选中选择”','Cloudra 方法一');
const q=[['生成候选','反应规则、结构搜索与化学工具先提出可能路径和三维姿态'],['智能选择','agent 结合任务目标与已有证据，决定哪些候选值得进一步计算'],['计算检验','保留竞争假设，用实际计算结果淘汰或修正']];
q.forEach((a,i)=>{let x=66+i*399;rect(s,x,190,374,310,C.soft,C.line,12);rect(s,x,190,374,63,i===1?C.gold:C.blue);txt(s,a[0],x+18,202,338,39,26,C.white,true,'center');txt(s,a[1],x+27,286,318,134,23,C.ink);});
rect(s,76,536,1129,86,'#FFF8EB',C.line,10);txt(s,'Harness 把没有边界的“猜”，转化为有候选、有依据、可被证伪的“选”。',102,553,1078,49,26,C.navy,true,'center');
foot(s,'参照：ARCHE 2026；CatDT 2026；Cloudra 研究方案（内部）',12,'创新论述');
note(s,'“猜变选”是本轮用户明确提出的核心方法哲学，不是说模型不具备化学判断。CatDT的UniMech本身也有候选生成与LLM筛选，本项目要把该哲学推进到复杂有机三维建模。Cloudra效果需在统一任务上验证。',[U.arche,U.cat,'Cloudra研究方案（内部）']);}
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
note(s,'CatDT论文已明确把deterministic tools、persistent memory和verification放入harness，不能称其没有harness。Cloudra的具体取舍是将调度、等待、普通故障和持久状态更多交给程序；agent在开放科学判断和非规则异常中介入。不要把“只属于错误处理”扩展到所有科学决策。',[U.cat,'Cloudra原型设计（内部）']);}
// 14 novelty 2 how
{
let s=base('工作流不只是步骤清单，而是能长期运行的研究过程','Cloudra 方法二');
const a=[['发起任务','agent 选择目标与候选'],['自动执行','系统安排计算、等待完成、收集数据'],['程序先验收','检查格式、几何、频率及阶段要求'],['遇到断点再判断','agent 解释意外，选择修正或改走新路径']];
a.forEach((v,i)=>{let y=184+i*105;rect(s,108,y,1060,83,i===3?'#FFF8EB':C.soft,C.line,9);rect(s,124,y+14,48,48,i===3?C.gold:C.blue);txt(s,String(i+1),124,y+19,48,34,22,C.white,true,'center');txt(s,v[0],195,y+13,235,54,24,C.navy,true);txt(s,v[1],453,y+13,675,54,22,C.ink);});
foot(s,'Cloudra 原型设计（内部）；相关系统先例：CatDT 2026',14,'设计主张');
note(s,'这页给非专业评委解释“harness”：它是围绕模型的运行系统，管理任务、计算工具、状态与校验。这里的四步是本项目设计与现有原型的概念说明，不代表全部功能已做统一量化验证。',[U.cat,'Cloudra原型设计（内部）']);}
// 15 novelty 3
{
let s=base('创新三：把科学问题和证据保存在机理图中','Cloudra 方法三');
await addImg(s,'fig_p13_closed_loop_nb.png',61,176,721,427,'Cloudra机理图和多代理闭环示意');
box(s,'图记录“研究什么”','每个物种、每条路径、竞争假设及其证据都可追溯。',804,184,406,103,C.blue);
box(s,'工具帮助“怎样建模”','专业工具提出并检查三维结构与过渡态候选。',804,309,406,103,C.blue);
box(s,'规则核查“能否相信”','程序依据计算证据判断结果能否进入结论。',804,434,406,103,C.gold);
foot(s,'Cloudra 原型设计（内部）；相关背景：ARCHE 2026；Unsleber & Reiher 2020',15,'方案与依据');
note(s,'这是第三项也是重点。机理图不是把聊天记录可视化，而是科学对象及证据的持久化表示。科学建模工具和形式化校验共同限制agent判断；不能说系统保证绝对科学真理。',[U.arche,U.network,'Cloudra原型设计（内部）']);}
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
note(s,'这页为概念性对照，不伪称展示了未提供日志的真实案例。可以口头举例：优化收敛后分子沿另一通道变成了不同物种；或过渡态的振动与目标键变化不符。实际项目证据和判据须以任务日志核实。',[U.fukui,U.auto,'Cloudra方法设计（内部）']);}
// 17 三项并列收束
{
let s=base('Cloudra 的三项创新是并列的系统分工','方法哲学');
const a=[['一｜智能编排','候选先生成，agent 依据证据“选”，而非从零猜。'],['二｜确定性运行','重复工序与长期调度由系统承担，agent 只在必要处介入。'],['三｜科学证据','机理图、建模工具与校验规则共同约束结论。']];
a.forEach((v,i)=>{let x=62+i*398;rect(s,x,184,373,342,i===2?'#FFF8EB':C.soft,C.line,13);rect(s,x,184,373,8,i===2?C.gold:C.blue);txt(s,v[0],x+22,220,329,68,27,C.navy,true);txt(s,v[1],x+24,312,325,138,23,C.ink);});
txt(s,'三者共同回答：怎样让普通模型参与复杂机理研究，而不把科学可靠性押在模型能力上？',80,560,1121,68,25,C.navy,true,'center');
foot(s,'Cloudra 研究方案（内部）；对照 CatDT 2026、ARCHE 2026',17,'创新归纳');
note(s,'这是三个并列的设计贡献，第三项最重要。不要描述成三阶段成果，也不要宣称已证明优于CatDT或ARCHE。',[U.cat,U.arche,'Cloudra研究方案（内部）']);}
// 18 为什么轴手性
{
let s=base('为什么用轴手性检验这套方法？','目标体系');
await addImg(s,'fig_p11_central_vs_axial_nb.v1.png',57,175,694,423,'中心手性与轴手性示意');
box(s,'“手性”不总是一个固定标签','轴构型依赖三维排列与受阻旋转，普通二维连接关系不足以自动判定。',776,183,437,113,C.blue);
box(s,'姿态决定反应','同一分子可能摆出多个构象，进入不同过渡态与产物通道。',776,322,437,113,C.gold);
box(s,'因此适合压测','候选生成、智能选择与物理核验必须同时工作。',776,461,437,104,C.red);
foot(s,'RDKit Book；Hansen et al. 2016；Zhang, Yang et al. 2026',18);
note(s,'不要说轴手性不能用化学信息学编码。RDKit可在明确标记时记录阻转异构，但不会单凭二维连接图判定旋转约束及反应姿态。对无背景评委，只说“左右手由整段分子的空间摆法决定”。',[U.rdkit,U.q2mm,U.cjc]);}
// 19 研究基础
{
let s=base('已有研究表明：轴手性的关键差别藏在三维结构中','申请人基础');
await addImg(s,'cjc_toc_graphic.png',57,187,674,406,'申请人共同一作N-N轴手性论文TOC图');
box(s,'已有论文','申请人共同一作工作研究了金字塔化 N–N 轴手性体系。',763,190,449,103,C.blue);
box(s,'对本项目的启发','轴旋转、氮反转和反应姿态可能共同影响选择性。',763,315,449,103,C.gold);
box(s,'接下来的检验','看系统能否自动提出关键候选，并用计算证据区分竞争路径。',763,440,449,103,C.green);
foot(s,'Zhang, Yang et al., Chin. J. Chem. 2026, 44, 3033–3042；图源：论文 TOC',19,'论文图源');
note(s,'论文证明申请人具备体系基础，但不能把Cloudra后续自动化成果归功于该论文。具体能垒数值本版不展示，因尚未逐项核对正文与SI。',[U.cjc]);}
// 20 模型策略
{
let s=base('Fine-Tuning is not Magic：能力应放在合适的位置','模型与系统的取舍');
rect(s,67,184,547,343,C.soft,C.line,12);rect(s,664,184,547,343,C.soft,C.line,12);
txt(s,'ARCHE：专用化学模型',91,202,495,51,27,C.navy,true);
box(s,'潜在优势','针对特定软件和常见计算任务强化输入、解读与诊断。',89,275,500,101,C.blue);
box(s,'需要付出','训练数据、训练与后续版本维护；可靠性仍需工具验证。',89,399,500,101,C.gold);
txt(s,'Cloudra：通用模型 + 专业工具',689,202,495,51,27,C.navy,true);
box(s,'当前选择','不以专门微调为前提，把候选生成和例行工序交给系统。',686,275,500,101,C.blue);
box(s,'明确边界','开放问题仍需要模型判断；工具覆盖和验证规则要持续建设。',686,399,500,101,C.gold);
txt(s,'我们选择先加强研究系统，再检验是否还需要训练一个更专门的模型。',75,558,1129,66,24,C.navy,true,'center');
foot(s,'ARCHE 2026；Cloudra 项目方案与原型（内部）',20,'策略对照');
note(s,'“Fine-Tuning is not Magic”是方法选择，不是否定ARCHE。ARCHE摘要公开其通用推理模型与领域专用计算化学模型的组合。专门训练可在固定软件任务上带来价值；Cloudra当前不把机理交付可靠性押在模型权重上，也没有统一任务的成本或准确率实验来证明自己优于ARCHE。',[U.arche,'Cloudra项目方案与原型（内部）']);}
// 21 项目原型案例：不重复使用存在问题的旧能量剖面
{
let s=base('原型案例：把一个机理任务交付为路径与计算证据','项目案例');
rect(s,76,184,1128,394,C.soft,C.line,13);
txt(s,'甲醛 + 甲胺 → 亚胺',105,204,1071,61,32,C.navy,true,'center');
const steps=[['研究对象','反应物与产物'],['提出路径','可能的中间体与反应步骤'],['运行计算','形成结构与能量记录'],['检查交付','核对路径及其证据']];
steps.forEach((a,i)=>{let x=97+i*276;rect(s,x,301,255,196,i===3?'#FFF8EB':C.white,C.line,10);rect(s,x,301,255,8,i===3?C.gold:C.blue);txt(s,a[0],x+13,331,229,46,23,C.navy,true,'center');txt(s,a[1],x+17,401,221,67,19,C.ink,false,'center');});
txt(s,'这一原型展示任务组织方式；不把它当作轴手性体系的性能结果。',100,515,1080,46,21,C.muted,false,'center');
foot(s,'项目原稿 P3 的内部原型任务；方法依据：Fukui 1970；Young et al. 2021',21,'内部案例');
note(s,'原稿展示甲醛+甲胺到亚胺体系的原型计算。根据申请人反馈，原稿中的数值能量剖面图画法有问题，因此这里不再引用该图及其中数值。由于原始计算日志未附，此页只陈述原型任务与交付形式，不声称它证明复杂轴手性问题已解决。',[U.fukui,U.auto,'项目原稿 P3（内部）']);}
// 22 案例与费用
{
let s=base('少让模型盯流程，把成本留给真正的判断','原型案例');
rect(s,75,184,1129,368,C.soft,C.line,14);
txt(s,'一次原型任务的模型调用费（粗略估计）',112,210,1050,54,29,C.navy,true,'center');
txt(s,'约 ¥2',118,273,1040,145,82,C.gold,true,'center');
txt(s,'校内答辩的数量级示例；不包含量化计算资源与研发成本。',109,432,1065,62,21,C.muted,false,'center');
rect(s,78,572,1124,63,C.light,C.line,10);txt(s,'“四两拨千金”的来源：候选生成、长期调度和证据核查主要由工具与系统承担。',101,584,1080,40,22,C.navy,true,'center');
foot(s,'申请人根据原型运行情况给出的粗略估计；仅说明模型调用费数量级',22,'案例数据');
note(s,'申请人说明“约2元”是一次原型任务的粗略花费，不对应可精确追溯的单一账单。此页只呈现模型调用成本的大致数量级，不包括量化计算资源、硬件折旧和研发成本，不与ARCHE做同任务价格排名。',[ '申请人提供的原PPT插图 fig_p7_three_routes_nb.v1.png','申请人口头说明：粗略估计']);}
// 23 结论
{
let s=base('Cloudra：把机理研究变成可选择、可执行、可核验的闭环','总结');
const a=[['问题','复杂有机机理不只要计算，还要决定哪些三维候选值得计算。'],['方法','智能负责有依据的选择；系统负责运行、记录与验证。'],['检验','用轴手性这一高度依赖三维姿态的体系，检验方法的有效性与成本。']];
a.forEach((v,i)=>{let y=185+i*131;rect(s,87,y,1106,109,i===2?'#FFF8EB':C.soft,C.line,12);txt(s,v[0],112,y+18,155,65,28,i===2?C.gold:C.navy,true);txt(s,v[1],285,y+15,867,76,24,C.ink);});
txt(s,'从“自动执行计算”，走向“有证据约束的自主机理探索”。',93,589,1091,49,26,C.navy,true,'center');
foot(s,'基于上述论文、项目原型与申请人研究基础；性能主张待专项评测验证',23,'研究定位');
note(s,'最后回扣三项并列创新，不再添加新缩写。明确：这是研究目标与原型案例，不是跨项目性能已经被统一基准证明。',[U.cat,U.arche,U.cjc,'项目申请书（内部）']);}
// 24 参考文献
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
'12 RDKit Book, Atropisomeric Bonds, rdkit.org/docs/RDKit_Book.html'
];refs.forEach((v,i)=>{let y=156+i*40;rect(s,65,y,1150,37,i%2?C.white:C.soft,C.line,4);txt(s,v,77,y+2,1122,32,16,C.ink);});
foot(s,'逐页完整链接及讲述提示见演讲者备注；预印本已标注',24);
note(s,'学术论文与申请人内部材料分开标注。具体成本需原始运行及计费记录，不能把内部口径当作论文结论。',Object.values(U));}

const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
await Promise.all(pending);
const candidate=path.join(work,'candidate_story_v13.pptx');
await (await PresentationFile.exportPptx(P)).save(candidate);
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:out,pythonExecutable:py,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],requiredNativeTableOwnerSlides:[],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(work,'validation_story_v13.json')});
console.log(JSON.stringify(result));
