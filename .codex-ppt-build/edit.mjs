import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const root='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master';
const build=root+'/.codex-ppt-build';
const skill='/Users/cloudrayyy/.codex/plugins/cache/openai-primary-runtime/presentations/26.929.10730/skills/presentations';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Desktop/Cloudra_LLM_Automated_Workflow.pptx'));
const rows=(await p.inspect({kind:'slide,textbox,shape,image,table,layout',maxChars:500000})).ndjson.trim().split('\n').map(x=>JSON.parse(x));
const slides=p.slides.items.slice();
function edit(i,start,text,size=28,pos,align='left'){
 const r=rows.find(r=>r.slideIndex===i-1&&r.kind==='textbox'&&r.text.startsWith(start));
 if(!r)throw new Error(`missing ${i} ${start}`);
 const s=p.resolve(r.id);s.text=text;
 s.text.style={typeface:'Noto Sans CJK SC',fontSize:size,alignment:align,verticalAlignment:'top',autoFit:'none',wrap:'square',lineSpacing:1.05,insets:{top:0,left:0,right:0,bottom:0}};
 if(pos)s.position=pos;
 return s;
}
function title(i,old,t){edit(i,old,t,38,{left:65,top:76,width:1150,height:65},'left');}
function notes(i,timing,script,extra=''){
 slides[i-1].speakerNotes.textFrame.setText(`【十分钟答辩】本页建议 ${timing} 秒。全稿主讲约 9 分钟，预留 1 分钟切页与停顿。\n\n【讲述稿】\n${script}\n\n【资料依据】用户提供的 Cloudra_LLM_Automated_Workflow.pptx 第 ${i} 页。${extra}`);
}
edit(1,'CLOUDRA','CLOUDRA：用 AI 组织计算研究\n以轴手性体系验证药物研发工作流',32,undefined,'right');
edit(1,'申 请 人','申 请 人：杨程驿（2025级本科生 · 化学生物学专业）\n指导老师：罗维纬 副教授、喻林萍 教授\n依托单位：长沙理工大学  化学与医药工程学院',23,undefined,'right');
notes(1,20,'各位老师好，我是杨程驿。我们正在开发 Cloudra，一个由 AI 大模型组织计算研究的系统。项目以轴手性体系为切入点，希望把计算结果转成可验证的分子与催化剂优化建议。今天重点介绍我们在做什么、已经做到哪一步，以及两年内怎样验证它。');

title(4,'轴手性构型','研究起点：轴手性分子如何稳定、如何选择性形成');
edit(4,'新药创制','轴手性分子的空间构型，是分子设计需要关注的问题。\n\n我们要回答两个问题：\n构型能否保持稳定？\n怎样选择性地形成目标构型？\n\n以轴手性体系为切入，比较反应路径，\n为催化剂优化提供依据。',29,{left:75,top:183,width:552,height:395});
edit(4,'计算提供','计算先回答“为什么”，再为下一步实验提供依据。',24,undefined,'right');
notes(4,40,'我们的研究从一个具体化学问题出发：轴手性分子的构型怎样保持稳定，又怎样选择性地形成？右边是轴手性药物结构的背景示例，项目实际验证对象是我们已有研究基础的 N–N 轴手性体系。我们希望把计算前置，在安排下一轮实验之前，先比较构型稳定性和竞争反应路径，形成催化剂优化的依据。','右图沿用原稿 Sotorasib 结构，仅作为背景示例，不代表本项目已有靶点或药效验证。');

title(5,'计算会算','核心问题：计算过程仍需要研究者逐步接力');
edit(5,'药物分子','研究者需要持续决定：\n算哪条路径、遇到失败怎么办、下一步优化谁。\n\n固定脚本能批量计算，但出现新路径或结果冲突时，仍需人工重新判断。\n\n系统将研究判断接入工作流，\n根据计算证据安排下一步任务。',30,{left:75,top:183,width:720,height:415});
edit(5,'谁来选择','选择研究路径\n诊断计算异常\n安排下一轮任务',30,undefined,'center');
edit(5,'大模型补上','AI 组织研究判断\n程序执行与核验',26,undefined,'center');
notes(5,40,'现在的计算软件已经能完成结构与能量计算，但研究者还要不断做决定：先算哪条路径，失败后怎样调整，以及结果出来以后下一步研究谁。固定脚本可以提高执行效率，却很难覆盖开放的研究问题。我们要解决的是这段持续人工接力的过程，让 AI 读取证据、诊断问题，再安排新的计算任务。');

title(7,'Cloudra：','我们在做什么：把计算判断接成可持续运行的工作流');
edit(7,'AI 大模型','AI 负责规划与修订，程序负责计算执行与证据核验',26,undefined,'center');
edit(7,'课题组合成','拟开展实验验证\n形成研究反馈',27,undefined,'center');
edit(7,'大模型规划','输入研究问题\n规划候选与机理',27,undefined,'center');
edit(7,'自动计算','运行计算\n核验物理证据',27,undefined,'center');
edit(7,'大模型归因','读取反馈\n更新下一轮方案',27,undefined,'center');
edit(7,'Cloudra 把','输入：候选结构、研究目标和已有数据。\n输出：经核验的机理证据、候选排序与实验建议。\n\n当前基础是自动化机理计算原型。项目拟进一步接入分子优化与实验反馈，逐步验证药物研发工作流。',29,{left:75,top:450,width:1128,height:193});
notes(7,65,'这页是 Cloudra 的整体工作方式。输入是候选结构、研究目标和已有数据。大模型先规划机理路径，程序运行计算并检查结果是否有物理依据，随后形成候选排序和实验建议。后续开展实验验证，把反馈送回系统，组织下一轮研究。大模型负责需要判断的环节，程序负责执行和验收。目前我们已经有机理计算原型，完整的药物研发闭环是本项目要继续验证的目标。我们希望交付的是能持续推进研究的工作流，以及每一步都可以追溯的计算证据。');

title(8,'一区共一','已有研究基础：完成 N–N 轴手性机理研究');
edit(8,'计算表明','计算解释了 N–N 轴的构型稳定性，\n以及氮反转为何不改变轴手性。\n\n这项机理研究为系统提供真实验证场景。',24,{left:75,top:522,width:545,height:123});
notes(8,50,'我们已经在真实化学问题上完成前期研究。我以共同第一作者在 Chinese Journal of Chemistry 发表 N–N 轴手性研究成果，并承担机理计算辨识。计算得到轴旋转势垒为 29.8 kcal/mol，氮反转能垒为 2.6 kcal/mol，解释了构型稳定性以及氮反转不改变轴手性的原因。这项工作为我们提供了熟悉的研究对象，也为后续自动化系统提供可检验的机理基础。','论文：Chinese Journal of Chemistry 2026, 44, 3033–3042；DOI: 10.1002/cjoc.70691。图沿用原稿 Scheme 3。');

title(10,'大模型可以','已有系统原型：计算结果经过程序核验');
edit(10,'量子化学','原型已实现任务调度与结果核验。\n\n程序核对反应路径与端点结构。\n证据不足时，大模型调整方案并安排补算。',30,{left:75,top:180,width:742,height:147});
edit(10,'丙二酸脱羧','计算案例一：丙二酸脱羧\n已得到候选过渡态，为验收流程提供测试对象。',26,{left:75,top:360,width:740,height:82});
edit(10,'水接力双','计算案例二：水接力质子转移\n已完成双向反应路径与端点核对。',26,{left:75,top:477,width:740,height:82});
edit(10,'NI1 水','NI1 水接力转移结构\n原型计算案例',20,undefined,'center');
edit(10,'振动方向','振动方向核对',22,undefined,'center');
edit(10,'双向 IRC','反应路径连通',22,undefined,'center');
edit(10,'端点结构','端点结构核对',22,undefined,'center');
edit(10,'机理接受','通过后接受',22,undefined,'center');
notes(10,40,'除了论文基础，我们已经自主开发计算原型，把任务调度和结果核验接入实际计算流程。这里保留两个案例：丙二酸脱羧得到候选过渡态，水接力质子转移完成了双向反应路径和端点核对。它们验证的是计算与验收流程。程序发现证据不足时，把问题返回大模型，模型再调整计算方案，确保下一步判断有可追溯的依据。','备答细节：NB1 作业515，单一虚频408.61i cm⁻¹，能垒27.94 kcal/mol；NI1 作业476，虚频921.24i cm⁻¹，原稿记录已完成双向IRC和零虚频端点验证。以上均为计算结果，不是湿实验实测。');

title(12,'大模型组织','接下来做三件事：完善系统、证明有效、验证应用');
edit(12,'合成与活性','拟开展实验验证',25,undefined,'center');
edit(12,'研究内容一','一、完善系统\n让机理规划、自动计算和异常修订连续运行。\n\n二、证明有效\n在相同题目与计算预算下，比较 AI 工作流和固定脚本。\n\n三、验证应用\n以 N–N 轴手性催化优化为案例，形成建议并检验反馈。',28,{left:75,top:350,width:1130,height:301});
notes(12,60,'项目接下来围绕三项研究展开。第一是完善系统，让机理规划、自动计算和异常修订连续运行，减少研究者在各步骤间接力。第二是证明它确实有效，在同一题目和相同计算预算下，与固定脚本比较，避免仅凭演示效果判断系统能力。第三是验证实际应用，回到我们熟悉的 N–N 轴手性体系，看看系统能否提出有计算依据的催化剂优化建议，并通过后续实验反馈修订方案。活性预测属于进一步拓展内容，先完成可验证的机理与催化优化工作。');

title(16,'从计算到','具体应用：为 N–N 轴手性催化剂提出优化建议');
edit(16,'以 N–N','研究问题：怎样提高目标构型的选择性？\n\n1. 比较竞争反应路径，寻找选择性不足的原因。\n2. 提出催化剂修饰假设，计算并筛选候选。\n3. 输出候选排序和需要验证的实验清单。\n4. 以产率和选择性反馈检验并修订方案。\n\n拟拓展：分子优化与活性预测。',27,{left:75,top:185,width:715,height:385});
edit(16,'催化剂结合','竞争反应路径示意\n用于解释候选筛选依据',20,undefined,'center');
edit(16,'大模型组织','项目要验证：计算建议能否帮助选择下一步实验。',26,undefined,'right');
notes(16,65,'用一个具体例子说明系统最终要做什么：我们希望提高某个 N–N 轴手性反应对目标构型的选择性。系统首先比较竞争路径，判断选择性不足来自哪些相互作用。然后提出催化剂修饰假设，例如改变位阻环境，再组织计算，对候选进行排序。最后交付的是建议优先验证哪些候选，以及为什么。后续我们用产率和选择性检验这些建议。如果结果与预测不一致，反馈就成为下一轮核查和计算的输入。这是计划验证的应用过程，尚不能把催化优化或活性提升写成已经实现的成果。','催化剂3,3′-位修饰属于原稿中的研究假设，尚无本稿可支持的优化实测结果。活性评价不列为当前已有能力。');

title(15,'大模型的','如何证明有效：结果可靠，并且减少人工介入');
edit(15,'评价大模型','同题目、同预算，对比固定脚本与 Cloudra。以计算记录和物理证据评分。',26,{left:75,top:166,width:1130,height:60});
edit(15,'覆盖度','路径完整',30,undefined);
edit(15,'通过图同构','关键步骤和竞争路径是否遗漏？',26,{left:278,top:263,width:455,height:70});
edit(15,'自洽性','证据可靠',30,undefined);
edit(15,'逐项核对','结构和反应路径是否通过物理核验？',26,{left:278,top:389,width:455,height:80});
edit(15,'准确度','结果准确',30,undefined);
edit(15,'将能垒','能垒与文献基准是否一致？',26,{left:278,top:514,width:455,height:70});
edit(15,'题库覆盖','同时记录：\n人工介入次数\n任务完成率\n计算耗时与开销\n\n主动注入异常，检验系统能否恢复。',28,{left:835,top:266,width:350,height:263});
edit(15,'无人自愈','目标：异常自主恢复率 >90%\n需通过基准评测验证',23,{left:818,top:555,width:381,height:74},'center');
notes(15,45,'有效性要用可检验的证据证明。我们在相同题目和计算预算下对比固定脚本与 Cloudra。科学上检查关键路径是否完整、计算证据是否可靠、能垒与文献基准是否一致。效率上记录人工介入次数、任务完成率和计算开销。同时主动注入异常，检查系统能否恢复。异常自主恢复率超过百分之九十是研究目标，需要评测验证。不能为了减少人工介入而接受错误的计算结果。');

title(19,'化学家','研究保障：化学研究积累与自主系统研发');
edit(19,'罗维纬','罗维纬  副教授',32,undefined,'center');
edit(19,'喻林萍','喻林萍  教授',32,undefined,'center');
edit(19,'长期从事','不对称催化与天然产物合成\n手性药物及生物活性化合物合成\n新颖轴向手性分子的不对称合成',26,{left:75,top:282,width:525,height:143},'left');
edit(19,'具有深厚','电解电极元件设计及产业化应用\n锰资源利用与锰基电池材料开发\n金属电化学腐蚀与防护',26,{left:670,top:282,width:525,height:143},'left');
edit(19,'课题组研究','申请人的交叉积累\n共同第一作者完成 N–N 轴手性机理研究。\n在香港科技大学参与化学智能体研究，自主开发 Cloudra 计算原型。',28,{left:95,top:508,width:1090,height:130});
notes(19,45,'项目的保障主要来自已有研究积累和系统研发基础。罗维纬老师的研究涉及不对称催化、手性药物与新颖轴手性分子合成；喻林萍老师主要研究电解电极、锰资源利用和电化学腐蚀防护。两位老师担任项目指导教师。申请人已完成真实轴手性体系的机理研究，也曾在香港科技大学参与化学智能体研究，并自主开发 Cloudra 计算原型。这些经历为从化学问题走向系统研发提供基础。','导师方向已根据长沙理工大学官网核对：罗维纬 https://www.csust.edu.cn/hxhgxy/info/1189/7613.htm ；喻林萍 https://www.csust.edu.cn/hxhgxy/info/1189/7605.htm 。核对日期2026-10-01。删除原稿第18页资源条件介绍及第19页未经支持的方向、设施、授权与机时声明。实验验证保留为研究计划。');

title(21,'两年验证','两年交付：工作流系统、评测证据与应用示范');
edit(21,'实施周期','实施周期：2027.01—2028.12，每阶段交付可检查的成果',24,undefined,'left');
edit(21,'完善大模型','完善自动计算\n与异常修订。\n交付工作流 v1.0。',27,{left:76,top:353,width:252,height:182},'left');
edit(21,'在四档','完成对照评测。\n公开结果与\n完整任务轨迹。',27,{left:374,top:353,width:252,height:182},'left');
edit(21,'进入 N–N','进入轴手性体系。\n检验候选方案，\n形成应用示范。',27,{left:668,top:353,width:252,height:182},'left');
edit(21,'提炼大模型','整理应用结果。\n撰写方法论文，\n开源可复用系统。',27,{left:968,top:353,width:242,height:182},'left');
edit(21,'药物研发闭环','轴手性应用验证',23,undefined,'center');
notes(21,50,'项目按两年、四个阶段推进。2027年上半年完善自动计算与异常修订，交付工作流第一版；下半年完成对照评测，保留完整任务轨迹。2028年上半年进入轴手性体系，验证候选优化建议；下半年整理方法和应用结果，撰写论文并开源系统。最终交付包括一套可运行的工作流、能够检验其能力的评测证据，以及轴手性体系中的应用示范。各阶段保留可追溯的研究记录。');

edit(22,'让 AI','Cloudra：用 AI 组织计算研究\n以可追溯证据支持下一步实验',42,{left:95,top:120,width:960,height:167},'right');
edit(22,'Cloudra 以','已有：N–N 轴手性机理成果与自动计算原型。\n本项目：完善系统，评测增益，验证催化优化建议。\n预期交付：可运行、可核验、可复用的研发工作流。',29,{left:80,top:366,width:1115,height:194},'left');
notes(22,20,'总结来说，我们已有真实机理研究和计算原型。接下来要把系统完善起来，用评测证明自动化增益，并在轴手性体系中验证优化建议，交付一套可运行、可核验、可复用的研发工作流。感谢各位老师，恳请批评指正。');

const order=[1,4,5,7,8,10,12,16,15,19,21,22];
const kept=order.map(i=>slides[i-1]);
// Collection methods accept slide objects, as defined by the runtime facade.
p.slides.keep(order.map(i=>i-1));
p.slides.reorder(order.map(i=>rows.find(r=>r.kind==='slide'&&r.slideIndex===i-1).id));
for(let j=0;j<kept.length;j++){
 const original=order[j];
 const page=rows.find(r=>r.slideIndex===original-1&&r.kind==='textbox'&&/^\d{2} \/ 22$/.test(r.text));
 if(page)p.resolve(page.id).text=String(j+1).padStart(2,'0')+' / 12';
 const head=rows.find(r=>r.slideIndex===original-1&&r.kind==='textbox'&&/^\d{2}  /.test(r.text));
 if(head){const t=j<4?'01  问题与方案':j<6?'02  已有基础':j<9?'03  研究与验证':'04  实施与交付';p.resolve(head.id).text=t;}
 await fs.writeFile(`${build}/final-${j+1}.png`,new Uint8Array(await (await kept[j].export({format:'png',scale:1})).arrayBuffer()));
 await fs.writeFile(`${build}/final-${j+1}.layout.json`,await (await kept[j].export({format:'layout'})).text());
}
const candidate=build+'/candidate.pptx';
await(await PresentationFile.exportPptx(p)).save(candidate);
await fs.writeFile(build+'/final-inspect.ndjson',(await p.inspect({kind:'slide,textbox,notes',maxChars:300000})).ndjson);
console.log('Exported',p.slides.items.length,candidate);
