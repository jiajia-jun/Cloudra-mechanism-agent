import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const root='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master';
const build=root+'/.codex-ppt-build';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Desktop/Cloudra_十分钟答辩_研发新范式版.pptx'));
const rows=(await p.inspect({kind:'slide,textbox,shape,image',maxChars:400000})).ndjson.trim().split('\n').map(x=>JSON.parse(x));
const FONT='Hiragino Sans GB';const green='#155C44',dark='#19362B';
const nodes=new Map();
function txt(i,text,pos,size=28,bold=false,color=dark,align='left',name=''){
 const s=p.slides.items[i-1].shapes.add({name,geometry:'textbox',position:pos,fill:'none',line:{fill:'none',width:0}});
 s.text=text;s.text.style={typeface:FONT,fontSize:size,bold,color,alignment:align,verticalAlignment:'top',wrap:'square',autoFit:'none',lineSpacing:1.08,insets:{left:0,right:0,top:0,bottom:0}};return s;
}
// Reset inherited paragraph formatting to fresh editable text, using a verified macOS Chinese font.
for(const r of rows.filter(r=>r.kind==='textbox')){
 const i=r.slideIndex+1;let size=r.style?.fontSize??28;let align=r.style?.alignment??'left';
 const header=/^0[1-3]  /.test(r.text);const footer=r.text.startsWith('Cloudra  /');const page=/^\d{2} \/ 12$/.test(r.text);
 if(header){size=16;align='left'}else if(footer){size=12;align='left'}else if(page){size=12;align='right'}
 else if(i>1&&r.position.top>=70&&r.position.top<145){size=38;align='left'}
 const original=p.resolve(r.id);p.slides.items[i-1].shapes.deleteById(original.id);
 const s=txt(i,r.text,r.position,size,r.style?.bold??false,r.style?.color??dark,align,r.name);
 nodes.set(r.id,s);
}
function find(i,start){const r=rows.find(r=>r.slideIndex===i-1&&r.kind==='textbox'&&r.text.startsWith(start));if(!r)throw Error(`Missing ${i} ${start}`);return nodes.get(r.id)}
function del(i,start){const s=find(i,start);p.slides.items[i-1].shapes.deleteById(s.id)}
function change(i,start,text,pos,size=28,bold=false,color=dark,align='left'){
 const s=find(i,start);s.text=text;if(pos)s.position=pos;s.text.style={typeface:FONT,fontSize:size,bold,color,alignment:align,lineSpacing:1.08,autoFit:'none',insets:{left:0,right:0,top:0,bottom:0}};return s;
}
async function img(i,path,pos,alt){return p.slides.items[i-1].images.add({blob:new Uint8Array(await fs.readFile(path)),contentType:'image/png',position:pos,fit:'contain',alt});}
const art=JSON.parse(await fs.readFile(build+'/art/generated.json','utf8'));
// Cover: clear reading order and an illustration beneath the long official project title.
for(const r of rows.filter(r=>r.slideIndex===0&&r.kind==='shape'&&r.position.top>10))p.slides.items[0].shapes.deleteById(p.resolve(r.id).id);
change(1,'2027年度','2027年度湖南省自然科学基金青年学生基础研究项目答辩',{left:78,top:52,width:1100,height:32},18,true,green);
change(1,'基于智能代理','基于智能代理的自动化轴手性体系',{left:78,top:142,width:1110,height:64},42,true,dark);
change(1,'药物计算驱动','药物计算驱动研发系统',{left:78,top:216,width:1000,height:62},42,true,dark);
change(1,'CLOUDRA：','CLOUDRA',{left:80,top:336,width:600,height:54},38,true,green);
txt(1,'AI 自动计算药物研发工作流新范式',{left:80,top:400,width:745,height:55},29,true,green);
for(const r of rows.filter(r=>r.slideIndex===0&&r.kind==='image'))p.resolve(r.id).position={left:79,top:558,width:90,height:90};
change(1,'申 请 人','申请人：杨程驿（2025级本科生 · 化学生物学专业）\n指导老师：罗维纬 副教授、喻林萍 教授\n依托单位：长沙理工大学 化学与医药工程学院',{left:202,top:555,width:880,height:107},21,false,'#45574D');
change(1,'CLOUDRA  /','CLOUDRA  /  AI-AUTOMATED DRUG DISCOVERY WORKFLOW',{left:79,top:682,width:950,height:16},11,false,'#62756B');
await img(1,art[0],{left:822,top:288,width:390,height:250},'Cloudra品牌概念插图：AI组织分子计算，装饰性示意');
// Problem slide: separate aligned paragraphs; equal widths and a consistent baseline.
del(2,'一个研发目标');
txt(2,'一个研发目标，可能对应许多分子与实验方案。\n研究者需要不断比较、筛选，再决定下一步。',{left:76,top:198,width:714,height:100},27);
txt(2,'计算能提供线索，但组织计算、解释结果、\n安排实验仍需大量人工接力。',{left:76,top:347,width:714,height:99},27);
txt(2,'我们希望让更多方案先在计算中比较，\n把实验优先用于更值得验证的候选。',{left:76,top:499,width:714,height:100},27);
change(2,'哪些方案','哪些方案值得做？\n为什么优先做它？\n结果不理想怎么改？',{left:892,top:241,width:294,height:169},27,true,'#FFFFFF','left');
change(2,'项目目标','项目目标\n减少人工接力与无效试错',{left:882,top:550,width:306,height:74},22,false,'#FFFFFF','left');
// Three phases: identical text grids and stable font sizes.
const phases=[['1.0','人工主导研发','人工安排计算与实验。\n\n候选筛选与方案调整，\n都由研究者逐步组织。',93,dark],['2.0','局部自动化','软件加快单项任务。\n\n连接任务、安排下一步，\n仍需研究者持续推进。',485,dark],['3.0','AI 组织研发工作流','AI 围绕目标组织计算。\n提出候选建议。\n根据实验反馈更新方案。\n\n工作流持续推进研究。',883,'#FFFFFF']];
for(const [num,heading,body,x,col]of phases){
 change(3,num,num,{left:x,top:200,width:306,height:60},44,true,'#AF7631');
 change(3,heading,heading,{left:x,top:284,width:306,height:48},27,true,col);
 const prefix=num==='1.0'?'人工安排':num==='2.0'?'软件加快':'AI 围绕';
 change(3,prefix,body,{left:x,top:354,width:306,height:223},24,false,col);
}
change(3,'新范式的核心','新范式的核心：计算支持研发决策，实验反馈推动下一轮设计。',{left:76,top:629,width:1128,height:39},24,true,green);
// Use-case page: candidate illustration supports the actual output, rather than empty quotation text.
for(const start of ['研究者的需求','先比较候选'])del(5,start);
txt(5,'研究者提出需求',{left:76,top:196,width:610,height:40},24,true,green);
txt(5,'“下一轮优先验证哪些候选？”',{left:76,top:248,width:670,height:47},29);
txt(5,'Cloudra 拟给出',{left:76,top:336,width:610,height:40},24,true,green);
txt(5,'候选清单与选择理由。\n可能影响效果的问题和改进方向。\n结合实验反馈，更新下一轮建议。',{left:76,top:389,width:650,height:161},27);
await img(5,art[1],{left:795,top:192,width:410,height:368},'候选筛选与实验建议的概念插图，非真实分子或实验结果');
change(5,'预期价值','预期价值：更早筛选候选，让每轮实验更有针对性。',{left:76,top:625,width:1110,height:41},25,true,green);
// Article evidence: bring back the actual published figure without expanding technical explanation.
for(const start of ['共同第一作者完成','申请人承担','已发表成果'])del(6,start);
change(6,'中科院一区','中科院一区 · 共同第一作者',{left:83,top:174,width:360,height:30},18,true,green);
change(6,'Organocatalytic','Organocatalytic Enantioselective\nConstruction of Pyramidalized\nN–N Atropisomers',{left:76,top:239,width:532,height:144},27,true,green);
change(6,'Chinese Journal','Chinese Journal of Chemistry\n2026, 44, 3033–3042\nDOI: 10.1002/cjoc.70691',{left:76,top:401,width:528,height:92},20,false,dark);
txt(6,'用计算解释分子构型与实验现象，\n为后续 AI 工作流提供真实研究基础。',{left:76,top:547,width:520,height:99},24,false,dark);
await img(6,build+'/art/original-8-0.png',{left:690,top:180,width:513,height:427},'原论文Scheme 3：化合物3al的轴旋转与氮反转计算路径');
txt(6,'论文原图：分子的空间构型与计算研究',{left:690,top:628,width:513,height:30},17,false,'#62756B','center');
// Research content: precise text rows with a small complementary feedback visual.
del(8,'构建工作流：');
for(const [heading,body,y]of [['构建工作流','AI 连续组织候选筛选与方案更新。',368],['评价实际效果','检验建议质量、效率和人工投入。',462],['完成应用示范','从已有体系验证建议，探索分子优化与活性预测。',556]]){
 txt(8,heading,{left:76,top:y,width:720,height:35},24,true,green);
 txt(8,body,{left:76,top:y+42,width:780,height:54},24);
}
await img(8,art[2],{left:890,top:383,width:305,height:239},'计算、实验与反馈迭代的概念插图');
// A small original brand illustration balances the delivery timeline.
await img(11,build+'/art/original-18-0.png',{left:1035,top:480,width:146,height:110},'原稿品牌风格分子计算插图，仅作装饰');
// Standardize statement sizes on remaining slides and leave scientific visuals intact.
for(let i=1;i<=12;i++){
 const s=p.slides.items[i-1];
 const current=(await p.inspect({kind:'textbox',maxChars:400000})).ndjson.trim().split('\n').map(x=>JSON.parse(x)).filter(x=>x.slideIndex===i-1);
 for(const r of current){if(/^\d{2} \/ 12$/.test(r.text))p.resolve(r.id).text.alignment='right';}
}
for(const i of [1,5,8,11]){
 const s=p.slides.items[i-1];const previous=s.speakerNotes.textFrame.text;
 s.speakerNotes.textFrame.setText(String(previous??'')+'\n\n配图说明：新增品牌插图由内置图像生成工具制作，仅为概念性示意，不代表真实结构、实验数据或已有设施。');
}
await(await PresentationFile.exportPptx(p)).save(build+'/polish-candidate.pptx');
console.log('Polished deck exported');
