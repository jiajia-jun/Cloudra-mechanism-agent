import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const build='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/.codex-ppt-build';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Desktop/Cloudra_十分钟答辩_研发新范式版.pptx'));
const rows=(await p.inspect({kind:'textbox,shape,image',maxChars:500000})).ndjson.trim().split('\n').map(JSON.parse),nodes=new Map();
const FONT='Hiragino Sans GB';
function add(i,text,pos,size,bold,color,alignment='left'){
 const s=p.slides.items[i-1].shapes.add({geometry:'textbox',position:pos,fill:'none',line:{fill:'none',width:0}});s.text=text;s.text.style={typeface:FONT,fontSize:size,bold,color,alignment,verticalAlignment:'top',autoFit:'none',lineSpacing:1.05,insets:{top:0,bottom:0,left:0,right:0}};return s;
}
for(const r of rows.filter(x=>x.kind==='textbox')){
 const i=r.slideIndex+1,old=p.resolve(r.id);p.slides.items[i-1].shapes.deleteById(old.id);
 let size=r.style.fontSize,align='left',pos={...r.position};
 if(i===1){align='right';if(size>=23&&size<40)size+=4;pos.height+=20;}
 else if(pos.top<50||pos.top>=680){align=r.text==='CLOUDRA'||/\d{2} \/ 12/.test(r.text)?'right':'left';pos.height=Math.max(pos.height,22);}
 else if(pos.top>=70&&pos.top<140){size=Math.max(size,40);pos.height=Math.max(pos.height,72);}
 else {size=Math.max(size,Math.min(32,size+4));pos.height=Math.max(pos.height,size*1.25);if(r.style.alignment==='center')align='center';}
 const s=add(i,r.text,pos,size,r.style.bold??false,r.style.color,align);nodes.set(r.id,s);
}
function get(i,prefix){const r=rows.find(r=>r.kind==='textbox'&&r.slideIndex===i-1&&r.text.startsWith(prefix));if(!r)throw Error(prefix);return nodes.get(r.id);}
function place(i,prefix,pos,size,align){const s=get(i,prefix);s.position=pos;if(size)s.text.fontSize=size;if(align)s.text.alignment=align;return s;}
async function image(i,file,pos,alt){p.slides.items[i-1].images.add({blob:new Uint8Array(await fs.readFile(file)),contentType:'image/png',position:pos,fit:'contain',alt});}
// Preserve all slide copy, order, diagrams, color panels and original scientific visuals.
place(1,'CLOUDRA：',{left:295,top:321,width:888,height:113},35,'right');
place(1,'申 请 人',{left:295,top:479,width:888,height:137},27,'right');
place(2,'一个研发目标',{left:75,top:188,width:720,height:460},32);
place(2,'哪些方案',{left:882,top:233,width:304,height:229},32,'left');
place(2,'项目目标',{left:873,top:549,width:326,height:96},29,'center');
for(const [x,num,h,b]of [[93,'1.0','人工主导','人工安排'],[466,'2.0','局部自动','软件加快'],[840,'3.0','AI 组织','AI 围绕']]){
 place(3,num,{left:x,top:207,width:330,height:59},46);
 place(3,h,{left:x,top:283,width:340,height:49},32);
 place(3,b,{left:x,top:350,width:num==='3.0'?352:320,height:243},29);
}
place(3,'新范式的核心',{left:85,top:621,width:1115,height:56},27);
place(4,'AI 围绕研发',{left:95,top:187,width:1095,height:46},29,'center');
for(const start of ['明确研发','AI 自动','实验验证','读取实验']){const s=get(4,start);s.text.alignment='center';s.position={...s.position,top:280,height:84};s.text.fontSize=30;}
place(4,'每一轮实验',{left:350,top:377,width:580,height:39},26,'center');
place(4,'研究者提出',{left:75,top:444,width:1120,height:219},32);
place(5,'研究者的需求',{left:75,top:187,width:730,height:430},32);
place(5,'先比较候选',{left:865,top:203,width:336,height:164},36);
await image(5,build+'/art/reference-13-1.png',{left:849,top:379,width:353,height:231},'参考稿中的候选改进概念插图');
place(5,'预期价值',{left:85,top:630,width:1113,height:45},30);
// Add the requested actual article image in the existing left column.
p.resolve('sh/dsrqlsva').position={left:680,top:170,width:532,height:37};
place(6,'中科院一区',{left:680,top:173,width:532,height:34},23);
place(6,'Organocatalytic',{left:680,top:213,width:532,height:118},28);
place(6,'Chinese Journal',{left:680,top:337,width:532,height:81},22);
place(6,'共同第一作者完成',{left:680,top:431,width:532,height:85},33);
place(6,'申请人承担',{left:680,top:526,width:532,height:144},29);
get(6,'申请人承担').text=rows.find(r=>r.kind==='textbox'&&r.slideIndex===5&&r.text.startsWith('申请人承担')).text.replace('\n\n','\n');
place(6,'已发表成果',{left:75,top:636,width:550,height:39},29);
await image(6,build+'/art/original-8-0.png',{left:75,top:191,width:550,height:436},'论文Scheme 3原图，分子构型与计算路径');
for(const s of ['已自主开发','自动组织计算','逐步连接研发']){get(7,s).text.fontSize=32;get(7,s).position={...get(7,s).position,height:108};}
place(7,'原型计算案例',{left:949,top:558,width:259,height:61},23,'center');
for(const s of ['提出研究','自动开展','整理计算','支持下一']){get(7,s).text.fontSize=25;get(7,s).position={...get(7,s).position,height:35};}
for(const s of ['明确研发','自动计算','生成候选','开展实验','反馈优化']){get(8,s).text.fontSize=28;get(8,s).position={...get(8,s).position,height:37};}
place(8,'计算、设计',{left:340,top:295,width:605,height:37},26,'center');
const body=get(8,'构建工作流：');const paragraphs=body.text.toString().split('\n\n');p.slides.items[7].shapes.deleteById(body.id);
for(let j=0;j<3;j++)add(8,paragraphs[j],{left:75,top:358+j*99,width:840,height:j===2?110:89},32,false,'#2D3C32');
await image(8,build+'/art/reference-6-0.png',{left:945,top:397,width:265,height:204},'参考稿中的分子计算概念插图');
for(const s of ['建议质量','研发效率','人工投入']){get(9,s).position={...get(9,s).position,width:174,height:46};get(9,s).text.fontSize=32;}
for(const s of ['候选建议','从提出目标','是否减少']){get(9,s).text.fontSize=31;get(9,s).position={...get(9,s).position,left:274,width:470,height:103};}
place(9,'工作流的价值',{left:833,top:265,width:352,height:284},32);
place(9,'改善幅度',{left:820,top:580,width:373,height:64},28);
place(10,'申请人的交叉',{left:95,top:494,width:1090,height:161},32);
for(const start of ['2027 上','2027 下','2028 上','2028 下']){get(11,start).text.fontSize=32;get(11,start).position={...get(11,start).position,height:44};}
for(const start of ['完善 AI','比较建议','进入真实','整理应用']){get(11,start).text.fontSize=30;get(11,start).position={...get(11,start).position,width:start==='整理应用'?246:276,height:225};}
await image(11,build+'/art/reference-11-2.png',{left:76,top:522,width:180,height:80},'参考稿中的研究记录概念插图');
place(12,'AI 自动计算',{left:90,top:120,width:1110,height:183},44);
place(12,'AI 组织计算',{left:80,top:365,width:1115,height:209},32);
place(12,'感谢各位',{left:97,top:599,width:1085,height:47},32,'center');
const notes=JSON.parse(await fs.readFile(build+'/base-notes.json','utf8'));
for(const [i,n]of [[5,13],[8,6],[11,11]])p.slides.items[i-1].speakerNotes.textFrame.setText(notes[i-1]+`\n配图来源：用户提供的Cloudra答辩20页参考稿第${n}页，仅为概念示意。`);
await(await PresentationFile.exportPptx(p)).save(build+'/layout-only-candidate.pptx');
console.log('Base story preserved; layout edits exported');
