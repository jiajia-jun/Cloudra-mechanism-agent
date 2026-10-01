import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
import sharp from 'sharp';
const root='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/申请材料/省自科答辩';
const fig=path.join(root,'figures');
const work=path.join(root,'.build');
const out=path.join(root,'修订版','Cloudra_省自科答辩_学术论证版_v8.pptx');
const skill='/Users/cloudrayyy/.codex/plugins/cache/openai-primary-runtime/presentations/26.921.11914/skills/presentations';
const py='/Users/cloudrayyy/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const P=Presentation.create({slideSize:{width:1280,height:720}});
const C={navy:'#1F4E79',blue:'#2564A8',light:'#EEF4FB',gold:'#D69325',ink:'#23364A',muted:'#596B7A',line:'#D7E1EC',white:'#FFFFFF',soft:'#F8FAFD'};
const font='Arial Unicode MS';
const pendingText=[];
function esc(v){return String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\"','&quot;');}
function unit(ch){return /[\u2E80-\u9FFF\uF900-\uFAFF]/u.test(ch)?1:/[A-Z0-9]/u.test(ch)?0.63:ch===' '?0.31:0.57;}
function wrapLine(line,maxUnits){let out=[],cur='',n=0;for(const ch of [...line]){let u=unit(ch);if(cur&&n+u>maxUnits){out.push(cur);cur='';n=0;}cur+=ch;n+=u;}out.push(cur);return out;}
function rasterText(t,w,h,size,color,bold,align){let lines=[];let fs=size;for(;fs>=12;fs--){lines=String(t).split('\n').flatMap(line=>wrapLine(line,Math.max(1,(w-4)/fs)));if(lines.length*fs*1.26<=h-2)break;}let scale=2,W=Math.max(1,Math.ceil(w*scale)),H=Math.max(1,Math.ceil(h*scale));let lineH=fs*1.26*scale,total=lines.length*lineH;let top=(H-total)/2+fs*scale;let anchor=align==='center'?'middle':align==='right'?'end':'start',x=align==='center'?W/2:align==='right'?W-2:2;let spans=lines.map((line,i)=>`<text x="${x}" y="${top+i*lineH}" fill="${color}" font-family="Arial Unicode MS" font-size="${fs*scale}" font-weight="${bold?'bold':'normal'}" text-anchor="${anchor}">${esc(line)}</text>`).join('');let svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">${spans}</svg>`;return sharp(Buffer.from(svg)).png().toBuffer();}
function rect(s,x,y,w,h,fill=C.white,stroke='none',radius=0){return s.shapes.add({geometry:radius?'roundRect':'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:stroke,width:stroke==='none'?0:1},borderRadius:radius||undefined});}
function txt(s,t,x,y,w,h,size=24,color=C.ink,bold=false,align='left'){pendingText.push(rasterText(t,w,h,size,color,bold,align).then(buf=>s.images.add({blob:new Uint8Array(buf),contentType:'image/png',alt:String(t),fit:'contain',position:{left:x,top:y,width:w,height:h}})));}

function base(title,kicker='研究背景'){let s=P.slides.add();s.background.fill=C.white;rect(s,0,0,1280,12,C.navy);txt(s,kicker,60,32,300,24,16,C.gold,true);txt(s,title,60,63,1160,68,34,C.navy,true);rect(s,60,139,1160,2,C.gold);return s;}
function foot(s,source,num,tag='文献依据'){rect(s,0,665,1280,55,C.soft);rect(s,60,665,1160,1,C.line);txt(s,tag+'｜'+source,60,674,1100,29,14,C.muted);txt(s,String(num).padStart(2,'0'),1162,674,58,29,14,C.muted,false,'right');}
function note(s,body,refs){s.speakerNotes.textFrame.setText(body+'\n\n参考文献 / 图源：\n'+refs.join('\n'));}
function bullet(s,head,body,x,y,w,idx){rect(s,x,y,w,102,C.soft,C.line,10);rect(s,x,y,5,102,idx===0?C.gold:C.blue);txt(s,head,x+20,y+12,w-35,30,21,C.navy,true);txt(s,body,x+20,y+45,w-35,46,17,C.ink);}
async function addImg(s,file,x,y,w,h,alt='论文图示'){let bytes=await fs.readFile(path.join(fig,file));s.images.add({blob:new Uint8Array(bytes),contentType:file.endsWith('.jpg')?'image/jpeg':'image/png',alt,fit:'contain',position:{left:x,top:y,width:w,height:h}});}
function tag(s,t,x,y,w,color=C.blue){rect(s,x,y,w,35,C.light,C.line,8);txt(s,t,x+8,y+2,w-16,30,16,color,true,'center');}
const U={
 rdkit:'https://www.rdkit.org/docs/RDKit_Book.html#atropisomeric-bonds', houk:'https://doi.org/10.1126/science.3945819', q2mm:'https://doi.org/10.1021/acs.accounts.6b00037',
 cos:'https://doi.org/10.1038/s41586-023-06792-0', crow:'https://doi.org/10.1038/s42256-024-00832-8',
 auto:'https://doi.org/10.1002/anie.202011941', afir:'https://doi.org/10.1021/acs.accounts.6b00023',
 automekin:'https://doi.org/10.1002/jcc.26734', kinbot:'https://doi.org/10.1016/j.cpc.2019.106947',
 crest:'https://doi.org/10.1063/5.0197592', fukui:'https://doi.org/10.1021/j100717a029',
 irc:'https://doi.org/10.1002/qua.24757', el:'https://arxiv.org/abs/2505.02484',
 cat:'https://arxiv.org/abs/2606.05050', arche:'https://arxiv.org/abs/2609.11147',
 chemgraph:'https://doi.org/10.1038/s42004-025-01776-9', cjc:'https://doi.org/10.1002/cjoc.70691',
 curtin:'https://doi.org/10.1039/D4CS00868E', rmg:'https://rmg.mit.edu/'
};
// 1
{
let s=P.slides.add();s.background.fill=C.white;rect(s,0,0,1280,15,C.navy);rect(s,70,170,10,340,C.gold);txt(s,'基于智能代理的轴手性体系\n过渡态自动化搜索与催化模型研究',105,178,1080,180,48,C.navy,true);txt(s,'省自然科学基金答辩 · 学术论证版',107,390,700,43,25,C.gold,true);txt(s,'杨程驿  ｜  长沙理工大学 化学与医药工程学院',107,548,950,42,22,C.muted);note(s,'研究主线：为什么复杂有机机理需要可验证的自主探索；已有工作做到了什么；本项目聚焦的轴手性挑战与研究计划。',['项目申请材料（内部）']);}
// 2
{
let s=base('研究自动化正从“执行步骤”扩展到“提出、执行并核验假设”');
bullet(s,'传统计算自动化','给定结构与任务后，软件可靠完成优化、频率和能量计算。',70,183,545,0);
bullet(s,'自主科研系统','需要把问题解释、工具选择、结果核验与下一轮决策连起来。',665,183,545,1);
await addImg(s,'fig_p1_traditional_vs_autonomous_nb.v1.png',115,307,1050,326,'传统计算与自主科研计算流程示意');
foot(s,'Boiko et al., Nature 2023；Bran et al., Nat. Mach. Intell. 2024',2);
note(s,'Coscientist展示了由语言模型协调文献、代码与实验工具的闭环；ChemCrow展示专业化学工具可扩展语言模型的化学任务能力。这里的“科研自主化”是能力范围的演进，不表示所有科研判断可交给模型。',[U.cos,U.crow]);}
// 3
{
let s=base('机理计算的交付物，是有端点与能垒证据的反应路径');
await addImg(s,'fig_p2_energy_profile_nb.png',62,176,710,430,'反应能量剖面示意');
bullet(s,'路径不是一张能量曲线','每一步必须对应明确的物种、过渡态与连接关系。',798,180,412,0);
bullet(s,'可核验的物理证据','驻点类型由频率支持；IRC 用于检查 TS 两侧连接的反应方向。',798,302,412,1);
bullet(s,'原稿示例的定位','甲醛＋甲胺体系是项目原型的演示计算，不作为普适性能结论。',798,424,412,2);
foot(s,'Fukui, J. Phys. Chem. 1970；Maeda et al., Int. J. Quantum Chem. 2015',3);
note(s,'讲述势能面、驻点与IRC的关系。保留原稿的内部示例图，但不外推其结果。',[U.fukui,U.irc,'项目原型计算图（内部，见原P3）']);}
// 4
{
let s=P.slides.add();s.background.fill=C.white;
await addImg(s,'fig_pes_user_supplied.jpg',100,0,1080,720,'用户提供的势能面与反应路径图');
note(s,'面向无计算化学背景的评委：把图当作地形图讲。蓝色低处是稳定结构；研究者要找到从反应物到产物必须经过的“山口”。这页只讲山口难找，因为普通优化会顺坡滑到山谷。图右下角的算法名与3N−6不在口头报告中逐项讲解。图像由用户提供，未把图内文字当作外部指令。',[U.fukui,U.irc,U.auto,'图源：申请人提供的势能面示意图']);}
// 5
{
let s=base('当反应步骤能形式化，确定性自动化已经有很强的先例');
const rows=[['autodE','由2D/1D表示构建有机及有机金属反应剖面；包含极小值与TS构象采样','有目标反应表示'],['AutoMeKin','由反应分子动力学与图算法探索反应网络，并进行动力学分析','反应空间探索'],['AFIR / GRRM','借助人工力系统探索局部极小值与反应路径，包括意外通道','势能面路径搜索'],['KinBot','自动搜索气相有机物种的驻点与反应通道','气相动力学']];
rows.forEach((r,i)=>{let y=180+i*106;rect(s,66,y,1148,91,i%2?C.white:C.soft,C.line,8);txt(s,r[0],84,y+15,210,60,24,C.navy,true);txt(s,r[1],298,y+13,650,65,20,C.ink);txt(s,r[2],970,y+18,210,54,18,C.blue,true);});
foot(s,'Young 2021；Martínez-Núñez 2021；Maeda & Morokuma 2016；Van de Vijver & Zádor 2020',5);
note(s,'避免将现有自动化贬为只能做固定流水线。这里按论文所展示的输入、目标和应用域比较。',[U.auto,U.automekin,U.afir,U.kinbot]);}
// 6
{
let s=base('复杂有机体系的搜索空间同时包含路径、构象与初猜');
await addImg(s,'fig_p5_3d_chemical_space_nb.png',66,183,646,410,'三维化学空间示意');
const points=[['路径','竞争反应与中间体改变拓扑。'],['构象','同一键连关系可对应多个低能三维结构。'],['初猜','不同取向会导向不同驻点或失败模式。']];points.forEach((p,i)=>bullet(s,p[0],p[1],742,183+i*124,470,i));
foot(s,'Young et al. 2021；Pracht et al., J. Chem. Phys. 2024（CREST）',6);
note(s,'“路径×构象×初猜”是概念分解而非严格数学乘积。autodE论文明确涉及极小值与TS构象采样；CREST用于低能构象空间探索。',[U.auto,U.crest]);}
// 7
{
let s=base('机理探索需要依据新证据改变下一步，而非只执行既定流程');
await addImg(s,'fig_p6_workflow_vs_exploration_nb.png',55,178,680,430,'固定流程与运行中改变路径示意');
bullet(s,'固定工作流','适合已定义输入、目标和搜索规则的任务；autodE、KinBot已有成熟实践。',770,184,441,0);
bullet(s,'开放式机理问题','可能出现计划外中间体、错误虚频模式或多条竞争路径。',770,313,441,1);
bullet(s,'可核验的决策','新假设必须回到计算证据，而不是仅由语言模型叙述。',770,442,441,2);
foot(s,'Young 2021；Van de Vijver & Zádor 2020；Li et al., ARCHE 2026（预印本）',7);
note(s,'这页强调任务类型差异，不构成对已有自动化系统能力的否定。ARCHE预印本公开展示了机理假设、计算与迭代验证。',[U.auto,U.kinbot,U.arche]);}
// 8
{
let s=base('化学智能体已有三类路线，差异首先在任务与证据层');
const cols=[
['工具增强的语言模型','ChemCrow / ChemGraph','将语言推理与化学工具、分子模拟工作流连接。','论文主要演示多领域任务执行与计算流程。'],
['特定领域的多代理系统','CatDT','围绕异相催化数字孪生，联合表面、路径、TS与动力学计算。','论文证据集中于气固/液固催化案例。'],
['机理研究闭环','ARCHE','提出机理假设、协调计算，并依据结果迭代修正。','预印本给出三个机理研究场景。']];
cols.forEach((c,i)=>{let x=60+i*395;rect(s,x,178,370,431,C.soft,C.line,12);rect(s,x,178,370,8,i===1?C.gold:C.blue);txt(s,c[0],x+20,202,330,58,23,C.navy,true);tag(s,c[1],x+20,274,330);txt(s,c[2],x+22,331,326,120,20,C.ink);txt(s,'论文展示范围：'+c[3],x+22,465,326,105,17,C.muted);});
foot(s,'Bran 2024；ChemGraph 2025；Song et al. 2026；Li et al. 2026',8);
note(s,'按论文展示范围分类，不代表这些系统的完整能力边界。CatDT是异相催化；ARCHE是2026年9月预印本。',[U.crow,U.chemgraph,U.cat,U.arche]);}
// 9
{
let s=base('对比要落到同一组问题：输入、探索、证据与适用体系');
const cols=[64,256,508,758,1009],widths=[192,252,250,251,205];
['项目','论文输入','探索对象','验证证据','演示体系'].forEach((v,i)=>{rect(s,cols[i],178,widths[i],54,C.navy);txt(s,v,cols[i]+8,185,widths[i]-16,38,17,C.white,true,'center');});
const data=[
['autodE','反应物/产物表示','目标反应能量剖面','TS、极小值与构象','有机/有机金属'],
['AutoMeKin','起始结构','反应网络','路径与动力学','分子反应网络'],
['CatDT','晶体＋反应描述','催化表面路径','TS、动力学、实验对照','异相催化'],
['ARCHE','机理研究问题','假设与计算迭代','案例级计算核验','有机/催化案例'],
['Cloudra（本项目）','反应体系＋研究目标','复杂三维机理图','拟用分层物理证据门禁','轴手性有机反应']];
data.forEach((row,r)=>{let y=232+r*76;row.forEach((v,i)=>{rect(s,cols[i],y,widths[i],76,r===4?'#FFF8EB':r%2?C.white:C.soft,C.line);txt(s,v,cols[i]+8,y+7,widths[i]-16,61,i===0?17:16,i===0?C.navy:C.ink,i===0);});});
foot(s,'依据各项目原始论文；Cloudra 栏为本项目研究设计，尚非跨项目实验结论',9);
note(s,'该表比较论文任务设计与证据形式，不进行未做统一基准时的性能排名。',[U.auto,U.automekin,U.cat,U.arche,'项目申请书与系统原型（内部）']);}
// 10 original P11 moved forward
{
let s=base('研究脉络：从工具编排到机理假设的计算闭环','相关工作');
const items=[['2020–21','autodE / AutoMeKin','反应剖面与反应网络自动化'],['2024–25','ChemCrow / ChemGraph / El Agente','语言模型编排化学与量化工具'],['2026','CatDT / ARCHE','多代理系统推进路径探索与机制验证']];
items.forEach((a,i)=>{let y=190+i*136;rect(s,65,y,1148,112,C.soft,C.line,10);rect(s,65,y,155,112,i===2?C.gold:C.blue);txt(s,a[0],80,y+31,126,46,25,C.white,true,'center');txt(s,a[1],246,y+15,905,39,26,C.navy,true);txt(s,a[2],246,y+57,905,38,21,C.ink);});
foot(s,'Young 2021；Martínez-Núñez 2021；Bran 2024；Zou 2025；Song 2026；Li 2026',10);
note(s,'原P11提前至Cloudra论断之前。时间轴按代表论文发表/预印本时间，不表示线性技术继承。',[U.auto,U.automekin,U.crow,U.chemgraph,U.el,U.cat,U.arche]);}
// 11 paper figures from primary sources
{
let s=base('论文原图对照：CatDT 与 ARCHE 面向不同的机理研究对象','相关工作');
rect(s,58,174,561,442,C.soft,C.line,10);rect(s,659,174,561,442,C.soft,C.line,10);
txt(s,'CatDT｜异相催化数字孪生',78,190,520,40,23,C.navy,true);
txt(s,'ARCHE｜机理假设与计算验证闭环',679,190,520,40,23,C.navy,true);
await addImg(s,'figref_catdt_fig1_digital_twin_overview.png',73,237,528,285,'CatDT论文Fig. 1异相催化数字孪生图');
await addImg(s,'figref_arche_fig1_architecture.png',674,237,528,285,'ARCHE预印本Fig. 1系统架构图');
txt(s,'论文展示：表面状态、路径、TS 与动力学联动。',79,538,520,52,18,C.ink);
txt(s,'论文展示：假设提出、工具执行与证据反馈。',679,538,520,52,18,C.ink);
foot(s,'左图：Song et al., CatDT 2026, Fig. 1；右图：Li et al., ARCHE 2026, Fig. 1',11,'论文图源');
note(s,'两幅图均取自各自原始预印本，分别说明论文研究对象与系统结构。它们是有力的相关工作，不应被表述为缺乏验证。',[U.cat,U.arche]);}
// 11 explicit gap
{
let s=base('本项目切入点：让轴手性机理的建模与证据可追溯、可复核','研究定位');
const q=[['现有基础','自动化搜索、工具编排和多代理机理研究已有实证。'],['待检验的研究问题','如何显式记录轴构型，并从构象集合中找到有化学意义的反应姿态？'],['本项目拟验证','用明确任务集比较路径覆盖、证据闭合与计算成本；不预设优于所有现有系统。']];
q.forEach((a,i)=>{let y=185+i*132;rect(s,70,y,1139,112,i===2?'#FFF8EB':C.soft,C.line,11);txt(s,a[0],95,y+20,240,65,26,i===2?C.gold:C.navy,true);txt(s,a[1],345,y+15,830,78,23,C.ink);});
foot(s,'研究依据：Young 2021；Song 2026；Li 2026；轴手性实例见 Zhang & Yang 2026',12);
note(s,'Cloudra在本页才首次作为本项目研究方案提出。普通二维连接图不能自动给出轴构型及反应姿态；现有软件可在明确标记时编码部分阻转异构体。Cloudra性能需后续实验验证。',[U.auto,U.cat,U.arche,U.cjc,U.rdkit]);}
// 12 architecture
{
let s=base('Cloudra 的设计：模型做选择与异常处理，计算和验收走确定性工具','研究方案');
await addImg(s,'fig_p8_select_plan_recover_nb.png',65,192,1145,355,'Cloudra生成选择规划执行验证恢复流程');
rect(s,70,568,1140,68,C.light,C.line,8);txt(s,'研究假设：把机理状态与证据留在可查询的图和日志中，可减少对单次模型上下文的依赖。',92,578,1100,49,20,C.navy,true);
foot(s,'Cloudra 原型设计（内部）；相关背景：ChemGraph 2025；CatDT 2026',13,'方案与依据');
note(s,'这里是系统设计与待检验假设，不应表述为已经完成的跨项目性能结论。',[U.chemgraph,U.cat,'Cloudra 系统原型与项目申请书（内部）']);}
// 13 mechanism graph
{
let s=base('机理图承担“科学状态”：物种、路径、能量与证据绑定','研究方案');
await addImg(s,'fig_p13_closed_loop_nb.png',65,175,730,430,'Cloudra机理图和多代理闭环示意');
bullet(s,'可追溯','每个节点与边保留计算来源、方法、几何与验证状态。',817,184,390,0);
bullet(s,'可比较','竞争路径和构象并存；失败记录不直接写成结论。',817,309,390,1);
bullet(s,'可恢复','状态保存在系统中，后续任务可从已验证证据继续。',817,434,390,2);
foot(s,'Cloudra 原型设计（内部）；相关背景：AutoMeKin 2021；ARCHE 2026',14,'方案与依据');
note(s,'这些是Cloudra设计目标及原型架构。AutoMeKin和ARCHE是有关反应网络与机理闭环的先例，不应说它们没有状态管理。',[U.automekin,U.arche,'Cloudra 系统原型（内部）']);}
// 14 evidence
{
let s=base('计算终止、驻点类型与目标路径是三层不同的判断','方法学');
const levels=[['01 计算层','程序正常结束、产物文件完整','只能说明作业执行完成'],['02 驻点层','极小值零虚频；TS 一阶鞍点','确认局部势能面类型'],['03 机理层','核查 IRC 方向与端点身份','确认是否支持目标反应边']];
levels.forEach((a,i)=>{let x=62+i*398;rect(s,x,183,373,346,C.soft,C.line,12);rect(s,x,183,373,72,i===2?C.gold:C.blue);txt(s,a[0],x+20,196,333,45,26,C.white,true);txt(s,a[1],x+22,276,329,102,23,C.navy,true);txt(s,a[2],x+22,407,329,76,19,C.ink);});
rect(s,65,558,1148,76,'#FFF8EB',C.line,10);txt(s,'严格验证的研究目标：不把“优化收敛＋一个虚频”直接等同于目标反应已被证明。',88,572,1105,48,22,C.ink,true);
foot(s,'Fukui 1970；Maeda et al. 2015；Young et al. 2021',15);
note(s,'原稿P12的演示截图尚未提供，本版以方法学证据链替代占位。IRC用于核查路径方向；具体准入阈值以研究方案和实验设置为准，不能暗示所有工作流都必须双侧端点重优化。',[U.fukui,U.irc,U.auto]);}
// 15 chirality
{
let s=base('已有 N–N 轴手性研究显示构型与构象的复杂耦合','研究对象');
await addImg(s,'cjc_toc_graphic.png',65,189,680,420,'张与杨等2026年N-N轴手性论文图示');
bullet(s,'已有研究基础','申请人共同一作论文报道了金字塔化 N–N 阻转异构体的有机催化对映选择性构建。',772,187,438,0);
bullet(s,'关键机理变量','需要区分轴旋转与氮反转等构型转化通道，比较其相对能垒。',772,319,438,1);
bullet(s,'研究延伸','本项目把这类三维构象与TS竞争作为自主机理探索的压力测试。',772,451,438,2);
foot(s,'Zhang, Yang et al., Chin. J. Chem. 2026, 44, 3033–3042；图源：该论文 TOC',16);
note(s,'原P13的29.8与2.6 kcal/mol数字需从正文或支持信息逐项核对后再用于正式答辩。本版暂不展示未经单独核验的具体数值。图源为论文TOC。',[U.cjc]);}
// 16a axial stereochemical representation
{
let s=base('第一难关：二维连接图不足以自动确定轴构型','科学问题');
await addImg(s,'fig_p11_central_vs_axial_nb.v1.png',60,178,687,420,'中心手性与轴手性示意');
bullet(s,'中心手性','常规分子表示可在局部原子上附加四面体手性标记。',772,178,437,0);
bullet(s,'轴手性','同一连接关系可对应两种轴构型；须显式标记手性轴或核查三维几何。',772,302,437,1);
bullet(s,'可编码 ≠ 可判定','RDKit 能记录部分阻转异构体，但不会仅由标记判断旋转是否真正受阻。',772,426,437,2);
foot(s,'RDKit Book, “Atropisomeric Bonds”；Zhang, Yang et al., Chin. J. Chem. 2026',17);
note(s,'核心论断要避免绝对化：轴手性不是不能用化学信息学表示，而是普通二维连接图不足以直接给出构型、构型稳定性或反应姿态。RDKit支持Mol/MRV/CXSMILES中的轴手性标记，但文档明确不自动判断真实的旋转受阻。申请人论文中的金字塔化N–N体系展示了轴旋转与氮中心构型判别的复杂性。',[U.rdkit,U.cjc]);}
// 16 axial problem
{
let s=base('第二难关：构象决定反应姿态与可达的竞争过渡态','科学问题');
await addImg(s,'fig_p12_2d_pes_nb.png',67,181,691,430,'构象与反应坐标耦合势能面示意');
bullet(s,'不是只找最低构象','低能静态构象未必就是进入低能反应通道的姿态。',791,183,420,0);
bullet(s,'需要化学假设','催化剂—底物取向、进攻面与质子转移路径需被提出并筛选。',791,310,420,1);
bullet(s,'压测点','漏掉关键构象或反应姿态，就可能漏掉决定选择性的 TS。',791,437,420,2);
foot(s,'Houk et al., Science 1986；Hansen et al., Acc. Chem. Res. 2016；Zhang & Yang 2026',18);
note(s,'Houk等讨论了立体选择性反应过渡态的构象分析。Q2MM综述明确指出准确预测选择性需要充分采样决定选择性的过渡态。这里的“化学直觉”具体指提出值得计算的结合方式、进攻方向和转移路径；研究目标是将其显式化并用物理证据筛选。',[U.houk,U.q2mm,U.cjc]);}
// 17 proposed work
{
let s=base('研究内容按“立体状态—构象假设—物理验证”递进','研究计划');
const stages=[['一','轴构型建模','显式表示手性轴及三维状态；在结构变换后核查构型。'],['二','构象与反应姿态','生成并筛选催化剂—底物取向、进攻面与竞争路径。'],['三','TS 证据与选择性','核查驻点和路径；比较不同通道的能垒与构象贡献。']];
stages.forEach((a,i)=>{let x=62+i*397;rect(s,x,190,374,375,C.soft,C.line,13);rect(s,x+20,210,58,58,i===0?C.gold:C.blue);txt(s,a[0],x+20,216,58,45,26,C.white,true,'center');txt(s,a[1],x+92,215,250,48,25,C.navy,true);txt(s,a[2],x+30,297,315,154,22,C.ink);});
rect(s,63,588,1147,50,'#FFF8EB',C.line,8);txt(s,'预期交付：可复核的机理图、计算日志、竞争路径与选择性分析，而非仅有叙述性答案。',85,594,1100,37,20,C.ink,true);
foot(s,'方法依据：RDKit Book；Hansen 2016；Young 2021；Zhang & Yang 2026',19,'研究计划');
note(s,'三项研究内容按轴构型表征、构象与反应姿态、TS证据与选择性递进。预期交付是研究计划而非完成结果。',[U.rdkit,U.q2mm,U.auto,U.cjc,'项目申请书（内部）']);}
// 18 references
{
let s=base('主要参考文献与图示来源','参考文献');
const refs=[
'1  Fukui, J. Phys. Chem. 1970, 74, 4161–4163. DOI: 10.1021/j100717a029',
'2  Young et al., Angew. Chem. Int. Ed. 2021, 60, 4266–4274. DOI: 10.1002/anie.202011941',
'3  Martínez-Núñez et al., J. Comput. Chem. 2021. DOI: 10.1002/jcc.26734',
'4  Maeda & Morokuma, Acc. Chem. Res. 2016, 49, 763–773. DOI: 10.1021/acs.accounts.6b00023',
'5  Bran et al., Nat. Mach. Intell. 2024, 6, 525–535. DOI: 10.1038/s42256-024-00832-8',
'6  Zou et al., El Agente Q, arXiv:2505.02484 (2025).',
'7  Song et al., CatDT, arXiv:2606.05050 (2026).',
'8  Li et al., ARCHE, arXiv:2609.11147 (2026).',
'9  Zhang, Yang et al., Chin. J. Chem. 2026, 44, 3033–3042. DOI: 10.1002/cjoc.70691',
'10 RDKit Book, Atropisomeric Bonds, rdkit.org/docs/RDKit_Book.html',
'11 Hansen et al., Acc. Chem. Res. 2016, 49, 996–1005. DOI: 10.1021/acs.accounts.6b00037'
];
refs.forEach((v,i)=>{let y=160+i*44;rect(s,64,y,1150,40,i%2?C.white:C.soft,C.line,4);txt(s,v,79,y+4,1114,32,16,C.ink);});
foot(s,'完整链接与逐页讲稿见每页演讲者备注；预印本已明确标注',20);
note(s,'以上为主文献，逐页备注中另列ChemGraph、KinBot、CREST、IRC综述等来源。',Object.values(U));}
// finalize
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
await Promise.all(pendingText);
const candidate=path.join(work,'candidate_academic.pptx');
await (await PresentationFile.exportPptx(P)).save(candidate);
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:out,pythonExecutable:py,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],requiredNativeTableOwnerSlides:[],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(work,'validation_v8.json')});
console.log(JSON.stringify(result));
