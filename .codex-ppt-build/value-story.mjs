import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const build='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/.codex-ppt-build';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Desktop/Cloudra_LLM_Automated_Workflow.pptx'));
const rows=(await p.inspect({kind:'slide,textbox,shape,image,table',maxChars:500000})).ndjson.trim().split('\n').map(x=>JSON.parse(x));
const slides=p.slides.items.slice();
function edit(i,start,text,size=29,pos,align='left',bold){
 const r=rows.find(r=>r.slideIndex===i-1&&r.kind==='textbox'&&r.text.startsWith(start));if(!r)throw Error(`${i} ${start}`);
 const s=p.resolve(r.id);s.text=text;s.text.style={typeface:'Noto Sans CJK SC',fontSize:size,lineSpacing:1.05,alignment:align,autoFit:'none',verticalAlignment:'top',insets:{top:0,left:0,bottom:0,right:0},...(bold===undefined?{}:{bold})};if(pos)s.position=pos;return s;
}
function title(i,start,text){edit(i,start,text,38,{left:65,top:76,width:1150,height:68},'left',true)}
function removeText(i,start){const r=rows.find(r=>r.slideIndex===i-1&&r.kind==='textbox'&&r.text.startsWith(start));if(r)slides[i-1].shapes.deleteById(p.resolve(r.id).id);}
function add(i,text,pos,size=30,color='#155C44',bold=false,align='left'){
 const s=slides[i-1].shapes.add({geometry:'textbox',position:pos,fill:'none',line:{fill:'none',width:0}});s.text=text;s.text.style={typeface:'Noto Sans CJK SC',fontSize:size,color,bold,alignment:align,lineSpacing:1.05,autoFit:'none',insets:{top:0,left:0,bottom:0,right:0}};return s;
}
function removeImages(i){for(const r of rows.filter(r=>r.slideIndex===i-1&&r.kind==='image'))p.resolve(r.id).delete();}
function notes(i,secs,script,source=''){
 slides[i-1].speakerNotes.textFrame.setText(`建议用时：${secs}秒。\n\n${script}\n\n资料来源：用户提供的原稿第${i}页。${source}`);
}
edit(1,'CLOUDRA','CLOUDRA：AI 自动计算药物研发工作流\n探索计算、设计与实验协同的新范式',31,undefined,'right',true);
edit(1,'申 请 人','申 请 人：杨程驿（2025级本科生 · 化学生物学专业）\n指导老师：罗维纬 副教授、喻林萍 教授\n依托单位：长沙理工大学  化学与医药工程学院',23,undefined,'right',false);
notes(1,20,'各位老师好，我是杨程驿。我们正在做 Cloudra，一个由 AI 自动组织计算的药物研发工作流。我们想解决的问题是：怎样让研究者在大量候选方案中，更有依据地决定下一步做什么，并让每一轮实验都帮助下一轮设计。');

title(5,'计算会算','药物研发的难点：下一步做谁，往往要反复试错');
edit(5,'药物分子','一个研发目标，可能对应许多分子与实验方案。\n研究者需要不断比较、筛选，再决定下一步。\n\n计算能提供线索，但组织计算、解释结果、安排实验仍需大量人工接力。\n\n我们希望让更多方案先在计算中比较，把实验优先用于更值得验证的候选。',29,{left:75,top:190,width:720,height:420},'left',false);
edit(5,'谁来选择','哪些方案值得做？\n为什么优先做它？\n结果不理想怎么改？',28,{left:866,top:236,width:330,height:205},'center',true);
edit(5,'大模型补上','项目目标\n减少人工接力与无效试错',25,{left:864,top:562,width:330,height:70},'center',false);
notes(5,45,'药物研发需要连续做选择。面对一个研发目标，研究者可能有很多分子、很多改造方案，也有不同实验路线。真正困难的是，下一步优先做哪个，为什么值得做，失败以后怎样调整。计算可以帮助比较方案，但从准备计算到解释结果，再到安排实验，中间仍有许多人工工作。我们的目标是，让更多候选先在计算中接受比较，帮助研究者把有限的实验投入到更有依据的方案上。');

title(6,'从人工串联','研发方式的变化：AI 开始组织整个研究过程');
edit(6,'人工串联研究','人工主导研发',28,undefined,'center',true);
edit(6,'研究者凭','人工安排计算与实验。\n\n候选筛选与方案调整，\n都由研究者逐步组织。',25,{left:93,top:322,width:315,height:249},'left',false);
edit(6,'固定脚本自动化','局部自动化',28,undefined,'center',true);
edit(6,'脚本批量','软件加快单项任务。\n\n如何连接任务，\n如何安排下一步，\n仍需研究者决定。',25,{left:492,top:322,width:315,height:249},'left',false);
edit(6,'Cloudra 大模型','AI 组织研发工作流',28,undefined,'center',true);
edit(6,'大模型理解','AI 围绕目标组织计算。\n提出候选建议。\n根据实验反馈更新方案。\n\n工作流持续推进研究。',25,{left:888,top:322,width:315,height:249},'left',false);
edit(6,'创新不止','新范式的核心：AI 把计算结果接到研发决策，再把实验反馈接回设计。',24,undefined,'right',true);
notes(6,50,'这页解释我们所说的新范式。过去，研究者把查资料、计算和实验一步一步串起来。后来软件和脚本提高了单项任务的效率，但任务之间怎样连接，仍要靠人持续安排。Cloudra 希望进一步让 AI 围绕目标组织这整个过程：计算之后形成候选建议，实验之后根据结果修订方案。变化发生在研究流程的组织方式上。每个环节都服务于下一步研发决策，实验得到的新信息也能直接进入下一轮设计。');

title(7,'Cloudra：','Cloudra：AI 自动计算驱动的药物研发工作流');
edit(7,'AI 大模型','AI 围绕研发目标，组织计算筛选、提出建议并持续修订方案',25,undefined,'center',true);
edit(7,'大模型规划','明确研发目标\n提出候选方案',27,undefined,'center',true);
edit(7,'自动计算','AI 自动计算\n比较并筛选候选',27,undefined,'center',true);
edit(7,'课题组合成','实验验证\n检验候选效果',27,undefined,'center',true);
edit(7,'大模型归因','读取实验反馈\n优化下一轮方案',27,undefined,'center',true);
edit(7,'实验反馈触发','每一轮实验，都为下一轮设计提供新依据',24,undefined,'center',true);
edit(7,'Cloudra 把','研究者提出目标，Cloudra 组织计算与候选比较。\n系统给出优先验证的方案和理由，研究者据此开展实验。\n\n实验结果返回系统，推动下一轮设计，形成持续迭代的研发闭环。',29,{left:75,top:445,width:1120,height:193},'left',false);
notes(7,65,'Cloudra 的工作方式可以用这四步说明。第一步，研究者提出研发目标和候选方案。第二步，AI 自动组织计算，比较不同候选，寻找更值得验证的方向。第三步，系统给出实验建议和选择理由，由研究者开展验证。第四步，实验结果返回系统，AI 结合新信息重新安排下一轮设计。我们希望让计算更早参与决策，让实验获得明确的问题和候选清单，再让反馈持续积累。完整闭环是本项目要继续建设和验证的目标。');

title(16,'从计算到','它有什么用：帮助研究者决定下一步实验');
removeImages(16);removeText(16,'催化剂结合');
edit(16,'以 N–N','研究者的需求：\n“我有一些候选方案，下一轮优先验证谁？”\n\nCloudra 拟交付：\n优先验证的候选清单及选择理由。\n可能影响效果的问题与改进方向。\n\n实验之后，结合反馈更新候选与建议。',29,{left:75,top:188,width:720,height:391},'left',false);
add(16,'先比较候选\n再提出实验建议\n用反馈改进设计',{left:885,top:248,width:315,height:250},34,'#155C44',true);
edit(16,'大模型组织','预期价值：更早筛选候选，让每轮实验更有针对性。',27,undefined,'right',true);
notes(16,60,'我们用一个研究者真正会提出的问题说明它有什么用：我现在有一些候选方案，下一轮应该优先验证谁？Cloudra 要交付的就是优先候选清单、选择理由，以及可能影响效果的问题。研究者看到的应该是能帮助安排下一步实验的建议。实验完成后，系统结合新的结果更新候选和改进方向。这里讲的是预期使用场景，尚不是已经完成的药效验证。价值在于更早筛选候选，提高实验的针对性，并把失败实验提供的信息保留下来，用于下一轮决策。');

title(8,'一区共一','前期基础：已有真实科研成果支持项目起步');
removeImages(8);
for(const x of ['29.8','2.6','kcal/mol','氮原子','计算表明','化合物 3al'])removeText(8,x);
// Both unit labels share the same prefix.
for(const r of rows.filter(r=>r.slideIndex===7&&r.kind==='textbox'&&r.text.startsWith('kcal/mol'))) {try{slides[7].shapes.deleteById(p.resolve(r.id).id)}catch{}}
add(8,'共同第一作者完成\nN–N 轴手性体系研究',{left:720,top:203,width:472,height:112},33,'#155C44',true);
add(8,'申请人承担机理计算辨识，\n用计算解释实验现象。\n\n这项经历让我们理解：\n计算怎样参与真实研究决策。',{left:720,top:350,width:472,height:235},29,'#2D3C32');
add(8,'已发表成果为后续工作提供研究基础',{left:75,top:500,width:545,height:115},29,'#155C44',true);
notes(8,40,'项目有真实科研工作作为基础。我以共同第一作者发表 N–N 轴手性体系研究，承担机理计算辨识，用计算解释实验现象。这里不展开具体化学细节，想强调的是，我们已经经历过计算与实验协同研究的过程，理解研究者怎样提出问题、怎样根据结果调整判断。这些经验为后续研发工作流的设计提供真实的问题来源。','论文：Chinese Journal of Chemistry 2026, 44, 3033–3042；DOI:10.1002/cjoc.70691。论文标题与信息沿用原稿。');

title(11,'从机理成果','前期基础：已开发计算原型，下一步连接研发决策');
edit(11,'已有机理成果','已完成\n机理研究与计算原型\n\n下一步\n贯通研发工作流',32,undefined,'center',true);
edit(11,'科学认知','真实研究经验\n支持工作流设计',22,undefined,'center',false);
edit(11,'前期机理研究','已自主开发 Cloudra 计算原型，具备组织计算任务和汇总结果的基础。\n\n本项目进一步把计算结果转为候选建议，连接设计与实验反馈。\n\n活性预测、分子优化和多轮实验反馈属于后续研究内容。',30,{left:481,top:189,width:723,height:389},'left',false);
notes(11,40,'在研究经验之外，我们也已经自主开发 Cloudra 的计算原型，具备组织计算任务和汇总结果的基础。项目下一步要把这份基础往研发决策延伸：从计算结果中形成候选建议，连接分子设计和实验反馈。已有成果与后续研究要区分清楚。原型已经提供起点，活性预测、分子优化和多轮反馈则是本项目需要继续推进和验证的内容。');

title(12,'大模型组织','研究内容：构建工作流、评价效果、完成应用示范');
for(const [x,t]of [['整合目标','明确研发目标'],['规划并','自动计算筛选'],['比较证据','生成候选建议'],['合成与','开展实验验证'],['诊断冲突','反馈优化设计']])edit(12,x,t,25,undefined,'center',true);
edit(12,'大模型读取','计算、设计与实验在同一工作流中持续迭代',24,undefined,'center',true);
edit(12,'研究内容一','构建工作流：让 AI 连续组织候选筛选与方案更新。\n\n评价实际效果：检验建议质量、效率和人工投入。\n\n完成应用示范：从已有手性体系起步，验证计算建议，\n进一步探索分子优化与活性预测。',29,{left:75,top:370,width:1128,height:244},'left',false);
notes(12,50,'研究内容分成三个部分。第一是构建工作流，让 AI 能连续组织计算筛选和方案更新。第二是评价实际效果，检验建议是否有依据，是否能够提高效率，是否减少人工投入。第三是完成应用示范，从我们已有研究基础的手性体系起步，验证计算建议，再进一步探索分子优化和活性预测。这三个部分共同回答，新范式能否成为实际可用的研究方法。');

title(15,'大模型的','如何证明有用：比较建议质量、研发效率与人工投入');
edit(15,'评价大模型','在相同研究问题与投入下，与现有工作方式进行比较。',27,{left:75,top:172,width:1120,height:58},'left',false);
for(const [x,t]of [['覆盖度','建议质量'],['自洽性','研发效率'],['准确度','人工投入']])edit(15,x,t,30,undefined,'left',true);
edit(15,'通过图同构','候选建议是否有依据？\n能否指导下一步验证？',27,{left:278,top:262,width:459,height:94},'left',false);
edit(15,'逐项核对','从提出目标到形成建议，\n是否缩短了研究周期？',27,{left:278,top:388,width:459,height:94},'left',false);
edit(15,'将能垒','是否减少重复操作，\n让研究者更专注于科学问题？',27,{left:278,top:514,width:459,height:94},'left',false);
edit(15,'题库覆盖','工作流的价值\n\n用实际任务比较，\n用实验反馈检验，\n用研究记录证明。',29,{left:833,top:276,width:352,height:248},'left',false);
edit(15,'无人自愈','改善幅度由项目评测给出',24,{left:820,top:575,width:373,height:68},'center',true);
notes(15,45,'新范式是否有用，需要用实际结果回答。我们会在相同研究问题和投入下，与现有工作方式比较。先看建议质量，候选建议是否有依据，能否帮助安排验证。再看研发效率，从提出目标到形成建议需要多长时间。最后看人工投入，研究者是否减少重复操作，有更多时间思考科学问题。改善多少要由项目评测给出，应用价值还需要结合实验反馈检验。');

title(19,'化学家','研究团队与申请人的交叉积累');
edit(19,'长期从事','不对称催化\n手性药物与轴手性分子合成',27,{left:75,top:282,width:525,height:129},'left',false);
edit(19,'具有深厚','电解电极设计与应用\n锰资源利用与电化学研究',27,{left:670,top:282,width:525,height:129},'left',false);
edit(19,'课题组研究','申请人的交叉积累\n共同第一作者完成真实体系研究，在香港科技大学参与化学智能体研究。\n自主开发 Cloudra 计算原型，连接化学问题与 AI 工作流设计。',28,{left:95,top:508,width:1090,height:130},'left',false);
notes(19,35,'两位指导老师为项目提供科研指导，研究方向按学校官网资料列出。申请人的经历连接了化学研究和 AI 系统开发：既参与真实体系研究，也曾在香港科技大学参与化学智能体研究，并自主开发计算原型。这些交叉积累帮助我们理解研发问题，也为把问题转成可运行的工作流提供基础。','导师方向核对来源：https://www.csust.edu.cn/hxhgxy/info/1189/7613.htm 和 https://www.csust.edu.cn/hxhgxy/info/1189/7605.htm 。核对日期2026-10-01。');

title(21,'两年验证','两年交付：系统、评测与药物研发应用示范');
edit(21,'实施周期','实施周期：2027.01—2028.12，每阶段形成可检查的成果',24,undefined,'left',false);
for(const [x,t,pos]of [
 ['完善大模型','完善 AI 自动计算\n与候选建议。\n交付工作流 v1.0。',{left:76,top:353,width:252,height:182}],
 ['在四档','比较建议质量、\n效率与人工投入。\n交付评测结果。',{left:374,top:353,width:252,height:182}],
 ['进入 N–N','进入真实研究场景。\n验证计算建议，\n开展反馈迭代。',{left:668,top:353,width:252,height:182}],
 ['提炼大模型','整理应用成果。\n发表研究方法，\n开源工作流系统。',{left:968,top:353,width:242,height:182}]])edit(21,x,t,27,pos,'left',false);
edit(21,'药物研发闭环','研发应用示范',23,undefined,'center',true);
notes(21,50,'两年内我们希望交付三类成果：一套 AI 自动计算工作流，一组能够评价它是否有用的研究结果，以及真实场景中的应用示范。2027年先完善系统，并比较建议质量、效率和人工投入。2028年进入实际研究问题，验证计算建议，把反馈用于下一轮设计，最后整理研究方法并开源系统。这样，项目的贡献既包含可使用的工具，也包含对这种研发组织方式的验证。');

edit(22,'让 AI','AI 自动计算药物研发工作流新范式\n让计算更早参与研发决策',40,{left:90,top:122,width:970,height:169},'right',true);
edit(22,'Cloudra 以','AI 组织计算，帮助研究者筛选候选、选择下一步实验。\n实验反馈进入新一轮设计，让研究持续迭代。\n\n项目目标：减少人工接力与无效试错，提高研发决策效率。',29,{left:80,top:370,width:1115,height:182},'left',false);
notes(22,20,'Cloudra 要探索的是 AI 自动计算药物研发工作流新范式。让计算更早参与研发决策，让实验更有针对性，让反馈持续改进设计。我们希望减少人工接力和无效试错，提高研发决策效率。感谢各位老师。');

title(10,'大模型可以','前期基础：自主开发计算原型，推进真实研究任务');
edit(10,'量子化学','已自主开发 Cloudra 计算原型，\n并在真实化学计算任务中开展测试。',30,{left:75,top:190,width:730,height:107},'left',false);
edit(10,'丙二酸脱羧','自动组织计算\n把研究问题转成连续推进的计算任务。',29,{left:75,top:365,width:732,height:93},'left',false);
edit(10,'水接力双','逐步连接研发决策\n进一步把计算结果转成候选建议与实验方案。',29,{left:75,top:488,width:732,height:92},'left',false);
edit(10,'NI1 水','原型计算案例\n水接力质子转移结构',19,{left:949,top:565,width:259,height:49},'center',false);
for(const [x,t]of [['振动方向','提出研究任务'],['双向 IRC','自动开展计算'],['端点结构','整理计算结果'],['机理接受','支持下一步研究']])edit(10,x,t,22,undefined,'center',true);
notes(10,40,'我们已经自主开发计算原型，也已经在真实化学任务中开展测试。原稿包括脱羧和质子转移等计算案例，右侧保留的是水接力质子转移的分子结构图。这些测试给工作流提供了实际起点。本项目会进一步把计算结果连接到研发决策，让研究者得到候选建议和下一步实验方案。活性预测与多轮实验反馈属于后续要推进的内容。','右图沿用原稿第10页，原始图注为NI1水接力转移结构。该图不是脱羧结构，保留准确标注。图示为计算结构。');

const order=[1,5,6,7,16,8,10,12,15,19,21,22];
p.slides.keep(order.map(i=>i-1));p.slides.reorder(order.map(i=>rows.find(r=>r.kind==='slide'&&r.slideIndex===i-1).id));
for(let j=0;j<12;j++){
 const i=order[j];const pg=rows.find(r=>r.slideIndex===i-1&&r.kind==='textbox'&&/^\d{2} \/ 22$/.test(r.text));if(pg)p.resolve(pg.id).text=String(j+1).padStart(2,'0')+' / 12';
 const hd=rows.find(r=>r.slideIndex===i-1&&r.kind==='textbox'&&/^\d{2}  /.test(r.text));if(hd)p.resolve(hd.id).text=j<5?'01  问题、方案与价值':j<7?'02  前期基础':'03  研究与交付';
}
await(await PresentationFile.exportPptx(p)).save(build+'/value-candidate.pptx');
console.log('value story exported, 12 slides');
