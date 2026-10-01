import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const build='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/.codex-ppt-build';
const source='/Users/cloudrayyy/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_wdx9ijs1uncp12_5ae6/temp/RWTemp/2026-09/4300553b027ff358ce63514ee57c6af0/Cloudra答辩20页 2(1).pptx';
const p=await PresentationFile.importPptx(await FileBlob.load(source));
const rows=(await p.inspect({kind:'slide,textbox,shape,image',maxChars:500000})).ndjson.trim().split('\n').map(JSON.parse);
const ss=p.slides.items.slice(),order=[1,3,5,7,13,14,15,6,12,2,19,20];
for(const r of rows.filter(r=>r.kind==='textbox'&&order.includes(r.slideIndex+1)))ss[r.slideIndex].shapes.deleteById(p.resolve(r.id).id);
const G='#155C44',D='#19362B',M='#52645A',F='Hiragino Sans GB';
const repl=new Map([
['药物研发需要在大量候选中做选择','药物研发中的候选选择'],
['研究目标：AI 自动计算药物研发工作流','AI 自动计算药物研发工作流'],
['分子的空间结构不同，性质和作用也可能不同。','分子结构不同，性质和作用也可能不同'],
['计算与实验之间仍需人工衔接','计算与实验仍需人工衔接'],
['优先合成和验证哪些候选？\n怎样改造分子，才更值得尝试？','哪些候选值得优先验证？\n怎样改造分子？'],
['准备计算、比较结果、安排实验，\n往往需要研究者反复组织。','组织计算、比较结果、安排实验，\n都需要研究者持续推进。'],
['项目关注：让计算更早参与候选筛选，减少反复试错。','让计算更早参与筛选，减少反复试错'],
['AI 围绕研究目标组织计算与候选比较。\n研究者审核建议并开展实验。\n实验反馈用于更新下一轮方案。','AI 组织计算，比较候选。\n研究者审核建议并开展实验。\n实验反馈更新下一轮方案。'],
['计算结果形成候选建议，实验反馈进入下一轮设计。','计算形成建议，实验反馈更新设计'],
['01  明确目标与候选','01  目标与候选'],
['02  AI 组织计算','02  自动计算'],
['03  验证与更新','03  验证与更新'],
['研究者提出问题和初始方案','提出研究问题\n与初始方案'],
['比较候选，形成建议和理由','比较候选\n形成建议和理由'],
['实验检验后，更新下一轮方案','开展实验检验\n更新下一轮方案'],
['应用场景：下一轮实验优先做什么','下一轮实验优先做什么'],
['形成优先验证的候选清单。\n说明选择理由和仍需验证的问题。','给出优先候选清单。\n说明理由与待验证问题。'],
['结合计算和实验反馈，\n提出下一轮分子或方案修改建议。','结合计算与实验反馈，\n提出下一轮修改建议。'],
['预期作用：帮助研究者安排实验，提高每轮验证的针对性。','帮助研究者安排实验，提高验证的针对性'],
['Organocatalytic Enantioselective\nConstruction of Pyramidalized\nN–N Atropisomers','Organocatalytic\nEnantioselective Construction\nof Pyramidalized\nN–N Atropisomers'],
['Chinese Journal of Chemistry\n2026, 44, 3033–3042','Chinese Journal of Chemistry\n2026, 44, 3033–3042'],
['已在简单反应上测试计算流程，后续将扩展并验证研发建议。','已有简单反应计算原型，后续验证研发建议'],
['计算得到的关键结构','计算关键结构'],
['让 AI 连续组织计算、候选比较与方案更新。','AI 连续组织计算，\n比较候选并更新方案。'],
['检验建议是否可靠，以及效率和人工投入。','评价建议质量，\n比较效率与人工投入。'],
['从已有手性体系起步，形成可复查的研究案例。','从已有手性体系起步，\n形成可复查案例。'],
['在相同问题与投入下，与现有研究方式比较。','相同问题与投入，与现有方式比较'],
['得到可用建议需要多久？\n计算投入是否合理？','建议生成需要多久？\n计算投入是否合理？'],
['需要多少人工整理与干预？\n异常后能否继续推进？','人工投入是否减少？\n异常后能否继续？'],
['统一记录建议、计算结果和实验反馈，检验实际改进。','记录计算与实验结果，检验实际改进'],
['化学生物学专业，2025级本科生','化学生物学专业\n2025级本科生'],
['参与轴手性研究并发表共同一作论文。\n自主开发 Cloudra 计算原型。','发表轴手性共同一作论文。\n自主开发 Cloudra 原型。'],
['指导老师：罗维纬 副教授、喻林萍 教授','指导老师：罗维纬 副教授\n喻林萍 教授'],
['交付：建议质量、效率与人工投入的评价报告','交付：建议质量与使用效果评价报告'],
['交付：工作流软件、案例资料与研究论文','交付：软件、案例资料与研究论文']
]);
function t(i,text,x,y,w,h,size=26,color=D,bold=false,alignment='left'){
 const original=text;text=repl.get(text)??text;
 if(size>=35)size=Math.round(size*1.18);else if(size>=23)size=bold?38:34;else if(size>=20)size=30;else size=Math.max(size,21);
 h=Math.max(h,size*1.35);
 if(i===1){if(y===38){size=22;}if(y===336){x=315;w=875;size=34;h=60;}if(y===481){y=475;h=90;size=30;}if(y===548){y=588;size=28;h=50;}}
 if(i===3){if(y===178){size=34;h=50;}if(y===244){size=32;}if(y===264){size=38;}if(y===325){h=118;}if(y===468){y=452;size=35;}if(y===529){y=521;h=116;}if(y===646){y=660;size=32;}}
 if(i===5){if(y===197){y=190;}if(y===261){y=253;h=125;}if(y===403){y=397;}if(y===468){y=462;h=185;}}
 if(i===7){if(y===171){size=34;}if(y===248){size=36;}if(y===305){h=105;size=32;}}
 if(i===13){if(y===462){y=490;h=123;size=34;}if(y===621){y=637;size=32;}}
 if(i===14){if(y===193){y=182;size=38;}if(y===263){y=246;h=191;size=30;}if(y===430){y=444;h=92;size=28;}if(y===539){y=553;h=104;size=32;}if(y===674){size=20;}}
 if(i===15){if(y===450){size=36;}if(y===517){size=32;}if(y===622){y=644;size=32;}}
 if(i===6){if(x===188){w=665;h=y===254||y===420||y===586?104:55;}if(size===34)size=33;}
 if(i===12){if(y===198){y=202;size=35;}if(y===407){y=450;size=40;}if(y===476){y=515;h=122;size=32;}if(y===634){y=667;size=26;}}
 if(i===2){if(x===77&&y===280){text='长沙理工大学\n化学与医药工程学院\n化学生物学专业\n2025级本科生';h=175;size=32;}if(y===477)y=493;if(y===542){y=557;h=110;size=31;}if(x===565&&y===265){h=122;size=32;}if(x===565&&y===419)y=429;if(x===565&&y===487){y=499;h=106;size=32;}if(y===623){y=616;size=29;h=90;}}
 if(i===19){if(x===85)size=33;if(x===360&&bold)size=36;if(x===360&&!bold){size=31;h=58;}}
 if(i===20){if(y===352){size=38;h=135;}if(y===622){size=32;}}

const q=ss[i-1].shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});q.text=text;q.text.style={typeface:F,fontSize:size,color,bold,alignment,verticalAlignment:'top',autoFit:'none',lineSpacing:1.08,insets:{top:0,bottom:0,left:0,right:0}};return q;}
function head(i,title){const j=order.indexOf(i)+1;t(i,j<6?'01  研究目标与应用':j<8?'02  前期基础':'03  研究计划',77,27,1070,34,16,G,true,'right');t(i,String(j).padStart(2,'0'),1185,27,45,31,16,M,false,'right');t(i,title,77,80,1130,67,35,D,true,'right');}
function note(i,sec,body,extra=''){ss[i-1].speakerNotes.textFrame.setText(`建议用时：${sec}秒。\n\n${body}\n\n资料来源：用户提供的参考演示文稿。${extra}`);}
// Quiet cover follows the reference's alignment, rule and original university logo.
t(1,'2027年度湖南省自然科学基金青年学生基础研究项目答辩',70,38,1140,36,18,M,false,'right');
t(1,'基于智能代理的自动化轴手性体系',70,125,1140,68,43,D,true,'right');
t(1,'药物计算驱动研发系统',70,203,1140,68,43,D,true,'right');
t(1,'Cloudra：AI 自动计算药物研发工作流',345,336,845,48,29,G,true,'right');
t(1,'答辩人：杨程驿',360,421,830,44,28,G,true,'right');
t(1,'指导老师：罗维纬 副教授、喻林萍 教授',360,481,830,43,24,D,false,'right');
t(1,'长沙理工大学  化学与医药工程学院',360,548,830,38,20,M,false,'right');
note(1,20,'各位老师好，我是杨程驿。我们正在做 Cloudra，一个由 AI 自动组织计算的药物研发工作流。希望通过计算帮助研究者决定下一步优先做什么，并让实验反馈进入下一轮设计。');
head(3,'药物研发需要在大量候选中做选择');
t(3,'分子的空间结构不同，性质和作用也可能不同。',80,178,1120,50,27,G,true,'right');
t(3,'药物分子的真实实例',80,244,520,45,26,G,true);
t(3,'研究者需要决定',665,264,540,45,28,G,true);
t(3,'优先合成和验证哪些候选？\n怎样改造分子，才更值得尝试？',665,325,540,107,26);
t(3,'计算与实验之间仍需人工衔接',665,468,540,44,27,G,true);
t(3,'准备计算、比较结果、安排实验，\n往往需要研究者反复组织。',665,529,540,98,25);
t(3,'项目关注：让计算更早参与候选筛选，减少反复试错。',80,646,1120,47,26,G,true,'right');
note(3,45,'药物研发需要在大量候选中做选择。图中是参考稿中的药物分子实例，我们不展开化学结构。想说明的是，分子怎样设计和改造，会影响下一步实验的选择。计算能够提供线索，但从准备计算到解释结果，再到安排实验，仍有大量人工衔接。项目希望让更多候选先在计算中比较。','图沿用参考稿第3页。原稿来源：Lanman et al., Acc. Chem. Res. 2022,55,2892–2903。');
head(5,'研究目标：AI 自动计算药物研发工作流');
t(5,'当前研究方式',77,197,800,47,29,G,true);
t(5,'研究者逐项安排计算、整理结果，\n再决定下一步实验。',77,261,780,108,28);
t(5,'拟探索的新范式',77,403,800,47,29,G,true);
t(5,'AI 围绕研究目标组织计算与候选比较。\n研究者审核建议并开展实验。\n实验反馈用于更新下一轮方案。',77,468,800,154,28);
note(5,50,'我们要探索的变化，是研发流程如何组织。现有软件已经能完成单项计算，但研究者仍需串联整个过程。Cloudra 希望让 AI 围绕目标组织计算、比较候选并提出建议，由研究者审核并开展实验。再把实验结果用于修订下一轮设计。完整闭环是本项目要建设和验证的目标。');
head(7,'Cloudra 工作流');
t(7,'计算结果形成候选建议，实验反馈进入下一轮设计。',80,171,1120,50,27,G,true,'right');
for(const [x,h,b]of [[105,'01  明确目标与候选','研究者提出问题和初始方案'],[490,'02  AI 组织计算','比较候选，形成建议和理由'],[875,'03  验证与更新','实验检验后，更新下一轮方案']]){t(7,h,x,248,340,46,26,G,true);t(7,b,x,305,340,59,23,M);}
note(7,60,'工作流分为三个环节。研究者提出研发目标和初始候选，AI 组织计算和比较，形成优先建议及理由。研究者开展实验后，系统结合反馈更新下一轮方案。图是概念示意，完整工作流仍需要建设和验证。');
head(13,'应用场景：下一轮实验优先做什么');
t(13,'比较候选',77,184,520,46,28,G,true);
t(13,'提出改进建议',680,184,535,46,28,G,true);
t(13,'形成优先验证的候选清单。\n说明选择理由和仍需验证的问题。',77,462,520,114,26);
t(13,'结合计算和实验反馈，\n提出下一轮分子或方案修改建议。',680,462,530,114,26);
t(13,'预期作用：帮助研究者安排实验，提高每轮验证的针对性。',77,621,1130,47,26,G,true,'right');
note(13,55,'研究者最关心的问题是，下一轮实验优先做什么。Cloudra 拟交付候选清单、选择理由和需要实验验证的问题。实验之后，根据反馈更新方案。我们从已有手性体系开始验证，再探索分子优化等应用。这里展示预期使用方式，尚未完成药效验证。');
head(14,'前期基础：已发表轴手性研究论文');
// Original paper figure remains in place. Replace technical numbers with significance.
t(14,'共同第一作者',710,193,495,48,29,G,true);
t(14,'Organocatalytic Enantioselective\nConstruction of Pyramidalized\nN–N Atropisomers',710,263,495,149,24,D,true);
t(14,'Chinese Journal of Chemistry\n2026, 44, 3033–3042',710,430,495,86,22,M);
t(14,'申请人参与理论计算，\n解释分子构型与实验现象。',710,539,495,98,25,G,true);
t(14,'论文原图：分子构型与计算路径   DOI: 10.1002/cjoc.70691',70,674,1140,28,15,M,false,'right');
note(14,40,'项目有真实研究成果作为基础。我以共同第一作者发表轴手性研究论文，参与理论计算，解释分子构型和实验现象。左侧是论文原图。不展开具体能垒，重点是我们已有计算与实验协同研究的经验，为工作流提供真实问题。','原图为论文Scheme 3。DOI:10.1002/cjoc.70691。');
head(15,'前期基础：计算流程已有原型');
for(const [x,h,b]of [[95,'丙二酸','反应起点'],[490,'脱羧过渡态','计算得到的关键结构'],[925,'烯醇 + CO₂','反应产物']]){t(15,h,x,450,300,47,27,G,true,'center');t(15,b,x,517,300,56,23,M,false,'center');}
t(15,'已在简单反应上测试计算流程，后续将扩展并验证研发建议。',80,622,1120,45,25,G,true,'right');
note(15,40,'这页保留脱羧反应的计算结构，展示原型已经能处理具体化学任务。它从反应起点寻找关键结构并整理产物结果。现阶段只是简单反应模型上的测试，不能据此声称药物研发闭环已经完成。下一步是将计算结果连接到候选建议，并验证其用途。','结构及数据来自参考稿第15页。原稿计算条件：ORCA5.0.2，气相B3LYP-D3(BJ)/def2-SVP。');
head(6,'研究内容与交付');
for(const [n,y,h,b]of [['01',192,'构建工作流','让 AI 连续组织计算、候选比较与方案更新。'],['02',358,'评价使用效果','检验建议是否可靠，以及效率和人工投入。'],['03',524,'完成应用示范','从已有手性体系起步，形成可复查的研究案例。']]){t(6,n,82,y,85,51,32,G,true);t(6,h,188,y,620,49,28,G,true);t(6,b,188,y+62,640,96,25);}
for(const id of ['im/up0zqx4j','im/vq90z2lo','im/4vihwrml']){const im=p.resolve(id);im.position={...im.position,top:399,height:290};}
p.resolve('im/6xwj2lk7').position={left:862,top:312,width:320,height:220};
note(6,45,'研究内容包括构建工作流、评价效果和完成应用示范。先让 AI 连续组织候选比较与方案更新，再检验建议质量、效率和人工投入，最后在已有手性研究基础上形成可复查案例。分子优化和活性预测属于后续探索。');
head(12,'效果评价');
for(const c of ss[11].charts.items.slice())ss[11].charts.deleteById(c.id);
t(12,'在相同问题与投入下，与现有研究方式比较。',75,198,1130,50,28,G,true,'center');
for(const [x,h,b]of [[75,'建议质量','候选建议是否有依据？\n是否得到实验支持？'],[473,'研发效率','得到可用建议需要多久？\n计算投入是否合理？'],[871,'人工投入','需要多少人工整理与干预？\n异常后能否继续推进？']]){t(12,h,x,407,334,43,28,G,true,'center');t(12,b,x,476,334,102,24,D,false,'center');}
t(12,'统一记录建议、计算结果和实验反馈，检验实际改进。',75,634,1130,47,25,G,true,'right');
note(12,45,'怎样判断项目有用，需要对照。我们在相同问题和投入下，与现有研究方式比较。看候选建议是否有依据、是否得到实验支持，获得建议需要多久，以及人工整理和干预是否减少。不能只展示系统运行过程，而要记录实际结果。');
head(2,'申请人及研究积累');
t(2,'杨程驿',77,193,380,59,38,G,true);
t(2,'长沙理工大学\n化学与医药工程学院\n化学生物学专业，2025级本科生',77,280,430,137,25);
t(2,'化学训练',77,477,430,43,27,G,true);
t(2,'第38届中国化学奥林匹克\n决赛银牌',77,542,430,95,25);
t(2,'理论计算与研究实践',565,197,640,45,28,G,true);
t(2,'参与轴手性研究并发表共同一作论文。\n自主开发 Cloudra 计算原型。',565,265,640,112,26);
t(2,'AI4S 科研经历',565,419,640,45,28,G,true);
t(2,'HKUST 程立雪组 RA 经历。\n参与 AI4S 相关研究。',565,487,640,105,26);
t(2,'指导老师：罗维纬 副教授、喻林萍 教授',565,623,640,42,23,M);
note(2,35,'申请人具有化学训练、理论计算和 AI4S 交叉实践。参与轴手性研究并发表共同一作论文，也自主开发了 Cloudra 原型。HKUST 科研经历为项目提供相关研究经验。后续我将负责工作流开发、计算与效果评价。教师只列姓名及指导角色。');
head(19,'两年实施计划');
for(const [y,date,h,b]of [[190,'2027 上半年','完善计算工作流','交付：可用原型与规范化结果记录'],[305,'2027 下半年','开展效果对照评价','交付：建议质量、效率与人工投入的评价报告'],[420,'2028 上半年','开展手性体系应用示范','交付：候选建议与验证案例'],[535,'2028 下半年','整理研究成果','交付：工作流软件、案例资料与研究论文']]){t(19,date,85,y,235,47,26,G,true);t(19,h,360,y,830,48,28,D,true);t(19,b,360,y+54,835,49,24,M);}
note(19,35,'前一年完善工作流并开展效果评价，后一年在手性体系中完成应用示范并整理研究成果。交付包括可用软件、对照评价和案例资料。先验证能否提供可靠建议，再逐步扩展应用范围。');
head(20,'Cloudra');
t(20,'AI 自动计算药物研发工作流',185,239,990,65,40,G,true,'right');
t(20,'以计算支持候选选择，\n以实验反馈更新下一轮设计。',185,352,990,120,31,D,false,'right');
t(20,'感谢各位老师聆听',185,548,990,51,29,G,true,'right');
t(20,'答辩人：杨程驿',185,622,990,42,24,M,false,'right');
note(20,20,'我们希望探索 AI 自动计算药物研发工作流的新范式。已有论文和原型是起点，下一步通过评价和案例验证，让计算真正帮助候选选择，让实验反馈推动下一轮设计。谢谢各位老师。');
for(let j=0;j<3;j++)ss[11].images.add({blob:new Uint8Array(await fs.readFile(build+`/art/reference-11-${j}.png`)),contentType:'image/png',position:{left:110+j*398,top:285,width:265,height:157},fit:'contain',alt:'参考稿中的计算示意插图，仅用于说明评价维度'});
p.resolve('im/4n6tc7y9').position={left:825,top:270,width:420,height:280};
p.resolve('im/v6p8j29k').position={left:155,top:241,width:360,height:240};
p.resolve('im/a5grqxsf').position={left:758,top:241,width:360,height:240};
p.resolve('im/xgzi9wzu').position={left:100,top:379,width:260,height:260};
ss[19].images.add({blob:new Uint8Array(await fs.readFile(build+'/art/reference-17-0.png')),contentType:'image/png',position:{left:95,top:280,width:390,height:330},fit:'contain',alt:'参考稿中的分子计算概念插图'});
p.resolve('im/6xwj2lk7').position={left:875,top:313,width:390,height:260};
ss[11].speakerNotes.textFrame.setText('建议用时：45秒。\n在相同问题与投入下比较建议质量、研发效率和人工投入。配图沿用用户参考稿第11页，作为概念性评价示意。');
ss[19].speakerNotes.textFrame.setText('建议用时：20秒。\n以计算支持候选选择，以实验反馈更新下一轮设计。配图沿用用户参考稿第17页，仅为分子计算概念示意。');
p.slides.keep(order.map(i=>i-1));p.slides.reorder(order.map(i=>rows.find(r=>r.kind==='slide'&&r.slideIndex===i-1).id));
await(await PresentationFile.exportPptx(p)).save(build+'/large-type-candidate.pptx');
console.log('12 slides exported');
