import {Presentation,PresentationFile} from '@oai/artifact-tool';
const p=Presentation.create({slideSize:{width:1278.667,height:720}}),s=p.slides.add();
const G='#155C44',Y='#F4D54B',B='#2D3C32';
function sh(geo,x,y,w,h,fill='none',line='none',lw=0){return s.shapes.add({geometry:geo,position:{left:x,top:y,width:w,height:h},fill,line:{fill:line,width:lw}})}
function t(text,x,y,w,h,size=24,c=B,bold=false,al='left'){let a=sh('textbox',x,y,w,h);a.text=text;a.text.style={typeface:'Hiragino Sans GB',fontSize:size,color:c,bold,alignment:al,verticalAlignment:'top',autoFit:'none',wrap:'square',insets:{left:0,right:0,top:0,bottom:0}};return a;}
function line(x,y,w,h,c=G,lw=2){return sh('line',x,y,w,h,'none',c,lw)}
sh('rect',0,0,1278.667,5,Y);t('02  研究背景',65,24,850,25,17,G,true);t('CLOUDRA',1100,24,115,25,17,G,false,'right');t('创新药物的研发过程',65,76,1150,72,40,'#19362B',true);
t('Cloudra / 湖南省自然科学基金青年学生基础研究项目',65,691,1020,23,12,'#62756B');t('05 / 20',1120,691,95,23,13.33,'#62756B',false,'right');
const xs=[65,361,657,953],heads=['新药发现','临床前研究','临床研究','新药申请'];
xs.forEach((x,k)=>{sh('rect',x,174,260,54,k%2?Y:G);t(heads[k],x+14,184,232,37,28,k%2?G:'#FFFFFF',true,'center');t(`0${k+1}`,x+8,242,55,37,24,'#9C7B00',true);if(k<3)sh('chevron',x+269,188,20,25,Y);});
// Native target icon, with live labels; scientific protein image is retained separately.
[64,42,18].forEach(d=>sh('ellipse',287-d/2,294-d/2,d,d,'none',G,2));line(287,251,0,86,G,1.5);line(244,294,86,0,G,1.5);
t('先导化合物 · 寻找靶点',74,403,244,34,21,G,true,'center');t('COX-2',74,369,244,29,18,G,false,'center');
t('天然产物化学\n合成化学\n药物化学',80,449,230,102,24,B,false,'center');
t('动物模型',373,385,236,34,24,G,true,'center');t('毒理学\n药理学\n制剂配方',375,435,232,102,24,B,false,'center');
// Vector capsule and approval document, replacing hand-drawn pictures.
sh('roundRect',724,278,126,49,'none',G,3);line(787,279,0,46,G,2);sh('roundRect',790,283,55,39,Y);t('临床试验',669,370,236,34,24,G,true,'center');t('工艺化学 · 发酵工程\n基因工程 · 人体试验',662,433,250,82,23,B,false,'center');
sh('rect',1040,260,86,100,'#FFFFFF',G,2.5);line(1055,285,56,0,G,2);line(1055,303,43,0,G,2);line(1055,321,29,0,G,2);sh('ellipse',1099,326,36,36,Y);t('✓',1101,328,32,30,24,G,true,'center');t('FDA 审批',965,383,236,34,24,G,true,'center');t('审核流程',965,440,236,40,24,B,false,'center');
line(65,573,556,0,G,1.5);line(657,573,556,0,G,1.5);t('Drug discovery',65,581,556,35,25,'#9C7B00',true,'center');t('Development',657,581,556,35,25,'#9C7B00',true,'center');t('总花费: ＄500 million and rising    ｜    总费时: 5-10 Years and falling',65,633,1148,31,19,B,false,'center');
await (await PresentationFile.exportPptx(p)).save('.deck-work/redraw-slide.pptx');
