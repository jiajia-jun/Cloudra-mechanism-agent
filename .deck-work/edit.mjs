import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from '@oai/artifact-tool';
const p=await PresentationFile.importPptx(await FileBlob.load('/Users/cloudrayyy/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_wdx9ijs1uncp12_5ae6/temp/drag/Cloudra_省自科(2).pptx'));
const rec=JSON.parse('['+(await fs.readFile('.deck-work/inspect.ndjson','utf8')).trim().split('\n').join(',')+']');
const font='Hiragino Sans GB',green='#155C44',ink='#19362B',body='#2D3C32',muted='#62756B',gold='#AF7631';
function objs(i){return rec.filter(r=>r.slideIndex===i&&r.position)}
function obj(r){return p.resolve(r.id)}
function del(r){const s=p.slides.items[r.slideIndex];if(r.kind==='image')s.images.deleteById(obj(r).id);else s.shapes.deleteById(obj(r).id)}
function add(s,text,x,y,w,h,size=32,color=body,bold=false,align='left') {const sh=s.shapes.add({geometry:'textbox',name:text.slice(0,24),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});sh.text=text;sh.text.style={typeface:font,fontSize:size,color,bold,alignment:align,verticalAlignment:'top',autoFit:'none',wrap:'square',insets:{left:0,right:0,top:0,bottom:0}};return sh;}
function move(id,x,y,w,h,size,color,align){const sh=p.resolve(id);sh.position={left:x,top:y,width:w,height:h};if(size)sh.text.fontSize=size;if(color)sh.text.color=color;if(align)sh.text.alignment=align;sh.text.autoFit='none';sh.text.insets={left:0,right:0,top:0,bottom:0};return sh;}
function title(s,t){return add(s,t,65,76,1150,72,40,ink,true)}
const cmap={'#4F81BD':green,'#0064C8':green,'#0C55A1':green,'#01C7FF':green,'#FF0000':gold,'#FFC000':green,'#000000':body,'#143B2D':ink};
// Apply a single typeface while retaining emphasis, superscripts and scientific images.
for(const r of rec.filter(r=>['textbox','shape'].includes(r.kind)&&r.position)) {
 const sh=obj(r);
 if(r.text) {sh.text.typeface=font;if(cmap[r.style?.color])sh.text.color=cmap[r.style.color];}
 if(cmap[r.fillColor]&&r.fillColor!=='#000000')sh.fill=cmap[r.fillColor];
 if(cmap[r.lineColor])sh.line={fill:cmap[r.lineColor],width:r.lineWidth??1};
 if(r.fillColor==='#155C44'&&r.position.top<8){sh.position={left:0,top:0,width:1278.667,height:5};sh.line={fill:'none',width:0}}
}
const sections=i=>i===1?'汇报提纲':i<=3?'01  个人简介':i<=12?'02  研究背景':i<=15?'03  前期工作':i<=18?'04  研究内容':i<=20?'05  预期成果':'研究总结';
let outputIndex=0;
for(let i=0;i<22;i++) {
 if(i===9||i===10)continue;outputIndex++;
 const s=p.slides.items[i];
 if(i===0||i===21) continue;
 for(const r of objs(i)) {
  const t=(r.text??'').trim(),pos=r.position;
  if((pos.top<78&&['个人简介','研究背景','前期工作','研究内容','预期成果'].includes(t))||(pos.top<78&&(/^(0[123])\s/.test(t)||t==='CLOUDRA'))||r.name==='test'||/灯片编号/.test(r.name??'')||(pos.top>680&&r.kind==='textbox'))del(r);
 }
 add(s,sections(i),65,24,850,25,17,green,true);
 add(s,'CLOUDRA',1100,24,115,25,17,green,false,'right');
 add(s,'Cloudra / 湖南省自然科学基金青年学生基础研究项目',65,691,1020,23,12,muted);
 add(s,`${String(outputIndex).padStart(2,'0')} / 20`,1120,691,95,23,13.33,muted,false,'right');
 // Normalize existing main headings.
 for(const r of objs(i).filter(r=>r.kind==='textbox'&&r.position.top>75&&r.position.top<110&&r.position.width>800)) {
  const sh=obj(r);sh.position={left:65,top:76,width:1150,height:72};sh.text.fontSize=40;sh.text.color=ink;sh.text.bold=true;sh.text.insets={left:0,right:0,top:0,bottom:0};
 }
}
// Cover.
move('sh/87mhgbex',125,236,1040,182,55,ink,'center');
move('sh/na9gvmd8',210,548,930,100,28,body,'left');
move('sh/k3yl0zql',175,32,1030,70,25,green,'left');
// Agenda: remove the crossing line and oversized vertical title.
const agenda=p.slides.items[1];for(const r of objs(1))if(!(r.position.top<8&&r.fillColor===green)) {try{del(r)}catch{}}
title(agenda,'汇报提纲');
['个人简介','研究背景','前期工作','研究内容','预期成果'].forEach((t,k)=>{add(agenda,`0${k+1}`,190,191+k*88,100,55,36,gold,true);add(agenda,t,350,191+k*88,650,55,36,green,true)});
// Personal background.
move('sh/n6ls3alk',65,76,175,64,40,ink,'left');p.resolve('sh/n6ls3alk').shadow='shadow-none';
move('sh/943mhgre',270,99,650,40,23,muted,'left');
for(const id of ['sh/i9w3u58v','sh/re9g7yxo']) {const sh=p.resolve(id);sh.text.fontSize=25;sh.text.bold=false;sh.text.color=body;}
move('sh/a5c3ql8z',95,228,280,45,25,green,'left');
move('sh/w7ulsvqp',95,280,280,45,25,green,'left');
move('sh/x8nml0ra',400,228,810,45,25,body,'left');
move('sh/ja54na9g',400,280,810,45,25,body,'left');
// Publications keep all citations and author emphasis.
move('sh/0ba143al',65,76,600,70,40,ink,'left');
const pub=objs(3).find(r=>r.text?.includes('Organocatalytic'));if(pub){const sh=obj(pub);sh.position={left:72,top:180,width:1135,height:478};sh.text.typeface='Arial';sh.text.fontSize=25;sh.text.alignment='left';sh.text.autoFit='none';}
// Drug-development timeline: fit all original content above footer.
for(const r of objs(4)) {if(r.position.top>165&&!(r.text?.trim()==='5')){const sh=obj(r);sh.position={...r.position,top:178+(r.position.top-178)*0.87,height:r.position.height*0.87};}}
const dt=objs(4).find(r=>r.text?.includes('创新药物的研发过程'));move(dt.id,65,76,900,72,40,ink,'left');
// Difficulties: clear the decorative rings that were covering labels.
for(const r of objs(5)){if(['椭圆 35','圆: 空心 36','椭圆 37','椭圆 39','椭圆 42','图形 40','图形 44','图形 45'].includes(r.name))del(r);}
move('sh/u907axkf',945,207,255,255);
move('sh/m5076xkj',755,188,450,77,27,green,'left');
move('sh/ep0b6lg7',755,306,450,77,27,green,'left');
move('sh/of2tcvy9',755,430,450,124,27,green,'left');
// Photo moved down and reduced so it remains present without touching labels.
move('sh/u907axkf',945,540,145,145);
move('sh/c7md0zi5',80,630,650,45,18.67,muted,'left');
// Synthesis review figure with a consistent heading and readable citation.
title(p.slides.items[6],'合成方法演进与药物发现');
move('im/9gvqpcj2',143,162,990,476);
move('sh/p8fih03e',690,642,520,32,23,muted,'right');
// Project motivation.
title(p.slides.items[8],'项目目标：减少人工接力与无效试错');
move('sh/0ru1ozyp',490,258,710,310,32,body,'left');
// Align the paired prediction headings.
move('sh/7atgbepc',65,76,535,72,40,ink,'left');
move('sh/c3e1gjyd',688,76,520,72,40,ink,'left');
// Research foundation: make space for title, citation and concluding paragraph.
move('sh/361gvilk',65,76,1150,72,40,ink,'left');
move('sh/it4rm5wv',680,176,532,34,23,green,'left');
move('sh/0z29cbyh',680,219,532,114,28,green,'left');
move('sh/1kjyt83e',680,341,532,85,22,body,'left');
move('sh/fi1grylo',680,437,532,88,30,green,'left');
move('sh/p8jyx83q',680,539,532,132,25,body,'left');
// Outcomes: replace heavy cards with an open three-column composition, retain source photos.
for(const r of objs(20)){if(r.geometry==='roundRect'&&!r.text)del(r);}
title(p.slides.items[20],'预期成果与能力提升');
move('sh/2l0vypkn',65,188,340,77,28,green,'center');
move('sh/ipcjmhw7',467,188,340,77,28,green,'center');p.resolve('sh/ipcjmhw7').fill='none';p.resolve('sh/ipcjmhw7').line={fill:'none',width:0};p.resolve('sh/ipcjmhw7').shadow='shadow-none';
move('sh/vml0b2dw',868,188,340,77,28,green,'center');
move('im/9cvehwry',95,284,294,205);
move('im/y5kvihsb',491,294,295,181);
move('im/z6tcbm9w',911,288,294,188);
move('sh/ehgvu5kr',65,512,340,96,26,body,'center');
move('sh/ho3idcvm',467,512,340,96,26,body,'center');
move('sh/fi5kn6d0',868,512,340,96,26,body,'center');
move('sh/zalgjyhg',65,631,1145,40,26,green,'center');
// Closing slide keeps the source logo and summary, uses the same font family.
for(const r of objs(21).filter(r=>r.text)) {obj(r).text.typeface=font;}
// Remove truly empty source slides, and keep all other content slides in order.
p.slides.remove(10);p.slides.remove(9);
await (await PresentationFile.exportPptx(p)).save('.deck-work/candidate.pptx');
for(let i=0;i<p.slides.items.length;i++){const b=await p.slides.items[i].export({format:'png',scale:1});await fs.writeFile(`.deck-work/after-${i+1}.png`,new Uint8Array(await b.arrayBuffer()));console.log('render',i+1)}
await fs.writeFile('.deck-work/after.ndjson',(await p.inspect({kind:'slide,textbox,shape,image',maxChars:500000})).ndjson);
