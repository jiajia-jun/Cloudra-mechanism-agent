import {Presentation,PresentationFile} from '@oai/artifact-tool';
const p=Presentation.create({slideSize:{width:1278.667,height:720}});let s;
const G='#155C44',Y='#F4D54B',L='#D5E2D9';
function sh(g,x,y,w,h,fill='none',c=G,lw=2){return s.shapes.add({geometry:g,position:{left:x,top:y,width:w,height:h},fill,line:{fill:c,width:lw}})}
function line(x1,y1,x2,y2,c=G,lw=2){if(x2<x1){[x1,x2]=[x2,x1];[y1,y2]=[y2,y1]}const a=sh('line',x1,Math.min(y1,y2),x2-x1,Math.abs(y2-y1),'none',c,lw);if(y2<y1)a.position={left:x1,top:y2,width:x2-x1,height:y1-y2,rotation:0};return a;}
function dot(x,y,d=18,fill=L){sh('ellipse',x-d/2,y-d/2,d,d,fill,G,1.5)}
function edge(a,b,c=G,lw=2){const x=Math.min(a[0],b[0]),y=Math.min(a[1],b[1]),w=Math.abs(a[0]-b[0]),h=Math.abs(a[1]-b[1]);let r=sh('line',x,y,w,h,'none',c,lw);if((b[0]-a[0])*(b[1]-a[1])<0)r.position={left:x,top:y,width:w,height:h,rotation:0,verticalFlip:true};}
function molecule(cx,cy,rad,subs=1){let pts=Array.from({length:6},(_,k)=>[cx+Math.cos(k*Math.PI/3)*rad,cy+Math.sin(k*Math.PI/3)*rad]);pts.forEach((a,k)=>edge(a,pts[(k+1)%6]));pts.forEach(a=>dot(...a,18));for(let k=0;k<subs;k++){let a=pts[k*2],b=[a[0]+(a[0]-cx)*.55,a[1]+(a[1]-cy)*.55];edge(a,b);dot(...b,18,Y)}}
function arrow(x,y,w){sh('rightArrow',x,y,w,13,Y,G,1)}
s=p.slides.add();molecule(928,490,38,1);molecule(1126,490,38,2);arrow(1000,483,57);dot(992,538,17,Y);
s=p.slides.add();molecule(979,495,20,1);molecule(1152,458,20,1);molecule(1152,549,20,2);edge([1010,495],[1087,458],G,2);edge([1010,495],[1087,549],G,2);arrow(1085,452,26);arrow(1085,543,26);
s=p.slides.add();let a=[[145,548],[172,523],[202,548],[230,523],[265,548],[230,575],[173,575]];a.forEach((q,k)=>{if(k<a.length-1)edge(q,a[k+1])});a.forEach((q,k)=>dot(...q,11,k===2||k===4?Y:L));
s=p.slides.add();sh('rect',445,548,21,39,L,'none',0);sh('rect',480,530,21,57,G,'none',0);sh('rect',515,510,21,77,Y,'none',0);edge([437,589],[550,589]);edge([438,589],[438,508]);arrow(449,516,58);
s=p.slides.add();sh('rect',767,509,12,22,L,G,1.5);sh('rect',751,529,44,38,'#FFFFFF',G,2);sh('rect',755,547,36,16,Y,'none',0);dot(815,531,12,Y);dot(833,554,12);edge([797,548],[810,535]);edge([820,537],[829,549]);sh('ellipse',813,575,17,17,Y,'none',0);edge([729,589],[856,589],G,1.5);
s=p.slides.add();sh('rect',1033,509,66,76,'#FFFFFF',G,2);[530,545,560].forEach((y,k)=>edge([1044,y],[1087-k*5,y],G,1.5));sh('ellipse',1080,544,34,34,Y,G,2);edge([1108,573],[1133,594],G,4);edge([1044,574],[1061,574],G,1.5);
await (await PresentationFile.exportPptx(p)).save('.deck-work/icons.pptx');
