import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const build='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/.codex-ppt-build';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Desktop/Cloudra_研发新范式版_仅排版修订.pptx'));
const rows=(await p.inspect({kind:'textbox,shape,image',maxChars:500000})).ndjson.trim().split('\n').map(JSON.parse);
function find(i,start){const r=rows.find(r=>r.kind==='textbox'&&r.slideIndex===i-1&&r.text.startsWith(start));if(!r)throw Error(start);return p.resolve(r.id);}
function place(i,start,position,alignment){const s=find(i,start);s.position=position;if(alignment)s.text.alignment=alignment;}
async function img(i,name,position,alt){return p.slides.items[i-1].images.add({blob:new Uint8Array(await fs.readFile(build+'/art/'+name)),contentType:'image/png',position,fit:'contain',alt});}
// Spread the cover across the canvas, retain its complete title and original text.
place(1,'2027年度',{left:80,top:53,width:1020,height:40},'left');
place(1,'基于智能代理',{left:80,top:130,width:1120,height:74},'center');
place(1,'药物计算驱动',{left:80,top:211,width:1120,height:74},'center');
place(1,'CLOUDRA：',{left:97,top:313,width:1100,height:103},'center');
place(1,'申 请 人',{left:80,top:481,width:795,height:169},'left');
for(const r of rows.filter(r=>r.kind==='image'&&r.slideIndex===0))p.resolve(r.id).position={left:1123,top:43,width:77,height:77};
await img(1,'reference-17-0.png',{left:884,top:446,width:326,height:219},'参考稿中的分子计算品牌示意');
// Two complementary illustrations occupy the actual unused area below the problem statement.
find(2,'一个研发目标').position={left:75,top:188,width:720,height:285};
await img(2,'reference-5-0.png',{left:87,top:478,width:335,height:187},'参考稿中的候选与计算结果示意');
await img(2,'reference-7-0.png',{left:488,top:474,width:277,height:187},'参考稿中的候选比较和结果记录示意');
// Each delivery stage receives one illustration with the same scale and baseline.
for(const r of rows.filter(r=>r.kind==='image'&&r.slideIndex===10))p.resolve(r.id).delete();
const arts=['reference-11-0.png','reference-11-1.png','reference-13-0.png','reference-11-2.png'];
for(let j=0;j<4;j++)await img(11,arts[j],{left:105+j*296,top:498,width:200,height:100},'参考稿中的工作流交付概念插图');
const notes=JSON.parse(await fs.readFile(build+'/visual-source-notes.json','utf8'));
for(const [i,n]of [[1,'17'],[2,'5、7'],[11,'11、13']])p.slides.items[i-1].speakerNotes.textFrame.setText(notes[i-1]+`\n新增配图来源：用户提供的Cloudra答辩20页参考稿第${n}页，仅作概念示意。`);
await(await PresentationFile.exportPptx(p)).save(build+'/visual-balance-candidate.pptx');
console.log('Cover and slides 2,11 updated; original copy retained');
