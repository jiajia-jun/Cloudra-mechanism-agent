import { expect, test } from '@playwright/test';
import { AGENT, installApiMocks, openSpa, PROJECT_ACTIVE } from './fixtures';
import type { GeometryView } from '../src/workbenchTypes';
import type { EventEnvelope } from '../src/types';

test.use({ launchOptions:{args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']} });

test('a source frame sends annotated pixels and its structure in one message and preserves the chat draft', async ({page}) => {
  test.slow();
  const molecule = (x:number):GeometryView => ({molecule:'frame-'+x, xyz:'', bonds:[],
    atoms:[{index:1,symbol:'O',x,y:0,z:0},{index:2,symbol:'H',x:x+1,y:0,z:0}]});
  const a = molecule(0), b = molecule(1);
  await installApiMocks(page);
  await page.route('**/workbench/open', route=>route.fulfill({json:{
    document_id:'traj',title:'IRC',source_path:'irc.log',selected_frame:0,geometry:a,
    frames:[{index:0,step:0},{index:1,step:1}],modes:[],warnings:[],settings:{}}}));
  await page.route('**/workbench/documents/traj/frames/1',route=>route.fulfill({json:b}));
  const snapshots:any[] = [], messages:any[] = [];
  let saves=0, pngBytes=0, failFirst=true;
  await page.route('**/workbench/save', route=>{saves++;return route.abort();});
  await page.route('**/workbench/snapshots', route=>{
    snapshots.push(route.request().postDataJSON());
    return route.fulfill({json:{structure_path:'shot/structure.json', annotations_path:'shot/annotations.json',
      markers:[{label:'A',kind:'atoms',atoms:[{index:1,element:'O',image:[0,0,0]}]}]}});
  });
  await page.route('**/uploads', route=>{
    const bytes=route.request().postDataBuffer()!;
    const signature=bytes.indexOf(Buffer.from([137,80,78,71,13,10,26,10]));
    pngBytes=signature<0?0:bytes.length-signature;
    return route.fulfill({json:{path:'shot/view.png',artifact_id:'png-id'}});
  });
  await page.route('**/agents/*/messages', route=>{
    if (failFirst) {failFirst=false;return route.fulfill({status:503,body:'offline'});}
    messages.push(route.request().postDataJSON());
    return route.fulfill({json:{accepted:true,command_id:'send-shot',event_id:'ev-shot',data:AGENT}});
  });
  await page.route('**/agents/*/events/ev-shot', route=>{
    const event:EventEnvelope = {
      stream:'agent',type:'agent.message_injected',event_id:'ev-shot',project_id:PROJECT_ACTIVE.id,
      session_id:AGENT.id,run_id:null,seq:1,session_seq:1,created_at:'2026-10-17T00:00:00Z',
      data:{sender:'user',...messages.at(-1)},
    };
    return route.fulfill({json:event});
  });
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`,{exact:true}).click();
  await page.getByTestId('composer-input').fill('保留我的聊天草稿');
  await page.getByRole('button',{name:'分子工作台',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'分子工作台'});
  await dialog.getByLabel('结构来源').fill('O');
  await dialog.getByRole('button',{name:'新建／打开',exact:true}).click();
  await dialog.getByRole('slider',{name:'来源帧'}).press('ArrowRight');
  await dialog.getByLabel('原子列表',{exact:true}).getByRole('button',{name:'O1',exact:true}).click();
  await dialog.getByRole('button',{name:'标记原子',exact:true}).click();
  await expect(dialog.getByRole('button',{name:'移除标记 A'})).toBeVisible();
  await expect(dialog.locator('.viewer-webgl-host canvas')).toBeVisible();
  const instruction=dialog.getByLabel('给 Agent 的图上指令');
  await instruction.fill('看 A 的位置');
  const fire=dialog.getByRole('button',{name:'发射给 Agent',exact:true});
  await fire.click();
  await expect(dialog.locator('.wb-error')).toBeVisible();
  await expect(instruction).toHaveValue('看 A 的位置');
  await fire.click();
  await expect(instruction).toHaveValue('');
  await expect(page.locator('.msg-body, .msg-bubble').filter({hasText:'看 A 的位置'})).toHaveCount(1);
  await expect(dialog).toBeVisible();
  expect(saves).toBe(0);
  expect(snapshots.at(-1)).toMatchObject({view:'source',source_frame:1,source_path:'irc.log',molecule:'frame-1',
    markers:[{label:'A',atoms:[{index:1,image:[0,0,0]}]}]});
  expect(snapshots.at(-1).camera).toHaveLength(8);
  expect(pngBytes).toBeGreaterThan(500);
  expect(messages).toHaveLength(1);
  expect(messages[0]).toMatchObject({images:['shot/view.png'],image_artifact_ids:['png-id']});
  expect(messages[0].content).toContain('看 A 的位置');
  expect(messages[0].content).toContain('A = O1');
  expect(messages[0].content).toContain('shot/structure.json');
  await expect(page.getByTestId('composer-input')).toHaveValue('保留我的聊天草稿');
});

test('picking across a cell edge dispatches both images and changes the screenshot pixels', async ({page}) => {
  test.slow();
  const geometry:GeometryView = {molecule:'', xyz:'', extxyz:'periodic native text', bonds:[], graph_status:'periodic',
    cell:[[3,0,0],[1,4,0],[0,0,7]],pbc:[true,false,false],atoms:[{index:1,symbol:'Ag',x:0,y:0,z:0}]};
  await page.route('**/workbench/fragments',route=>route.fulfill({json:{fragments:[]}}));
  await page.route('**/workbench/open',route=>route.fulfill({json:{
    document_id:'slab',title:'Ag',source_path:'Ag.extxyz',selected_frame:0,geometry,frames:[{index:0,step:0}],settings:{},modes:[],warnings:[]}}));
  await page.goto('/e2e/workbench-builder.html?capture');
  const dialog=page.getByRole('dialog',{name:'分子工作台'});
  await dialog.getByLabel('结构来源').fill('Ag');
  await dialog.getByRole('button',{name:'新建／打开',exact:true}).click();
  await dialog.getByLabel('显示相邻晶胞').check();
  await expect.poll(()=>page.evaluate(()=> (window as any).testViewer?.getModel(0)?.selectedAtoms({}).length)).toBe(3);
  const text=dialog.getByLabel('给 Agent 的图上指令'), fire=dialog.getByRole('button',{name:'发射给 Agent'});
  await text.fill('原视角'); await fire.click(); await expect(text).toHaveValue('');
  await dialog.locator('.viewer-webgl-host').scrollIntoViewIfNeeded();
  for (const serial of [1,3]) {
    const p=await page.evaluate(serial=>{
      const viewer=(window as any).testViewer;
      const point=viewer.modelToScreen(viewer.getModel(0).selectedAtoms({serial})[0]);
      return {x:point.x-scrollX,y:point.y-scrollY};
    },serial);
    await page.mouse.click(p.x,p.y);
  }
  await dialog.getByRole('button',{name:'标记中心位点'}).click();
  await text.fill('检查 A'); await fire.click(); await expect(text).toHaveValue('');
  const result=await page.evaluate(()=>{
    const [before,after]=(window as any).testShots;
    let changed=0;
    for(let i=0;i<before.pixels.length;i+=4) {
      if (Math.abs(before.pixels[i]-after.pixels[i])+Math.abs(before.pixels[i+1]-after.pixels[i+1])+Math.abs(before.pixels[i+2]-after.pixels[i+2])>50) changed++;
    }
    return {changed,markers:after.snapshot.markers,extxyz:after.snapshot.extxyz};
  });
  expect(result.changed).toBeGreaterThan(35);
  expect(result.extxyz).toBe('periodic native text');
  expect(result.markers).toEqual([{label:'A',kind:'site',atoms:[{index:1,image:[0,0,0]},{index:1,image:[1,0,0]}]}]);
});

test('saving the draft keeps its unsent instruction and markers, while source frames keep their own notes', async ({page}) => {
  const geometry:GeometryView = {molecule:'structure',xyz:'',bonds:[],atoms:[{index:1,atom_id:'oxygen-id',symbol:'O',x:0,y:0,z:0}]};
  let saves = 0;
  await page.route('**/workbench/fragments', route=>route.fulfill({json:{fragments:[]}}));
  await page.route('**/workbench/open', route=>route.fulfill({json:{document_id:'example',title:'Example',selected_frame:0,geometry,
    frames:[{index:0,step:0}], settings:{}, warnings:[], modes:[]}}));
  await page.route('**/workbench/save', route=>{
    saves++;
    return route.fulfill({json:{geometry,path:'structure.json',files:[],message:'已保存'}});
  });
  await page.goto('/e2e/workbench-builder.html?capture');
  const dialog = page.getByRole('dialog',{name:'分子工作台'});
  await dialog.getByLabel('结构来源').fill('O');
  await dialog.getByRole('button',{name:'新建／打开'}).click();
  await dialog.getByLabel('原子列表',{exact:true}).getByRole('button',{name:'O1',exact:true}).click();
  await dialog.getByRole('button',{name:'标记原子',exact:true}).click();
  const note = dialog.getByLabel('给 Agent 的图上指令');
  await note.fill('检查 A');
  await dialog.getByRole('button',{name:'保存编辑稿到项目'}).click();
  await expect(dialog.getByRole('button',{name:'已保存到项目'})).toBeDisabled();
  await expect(dialog.getByRole('button',{name:'移除标记 A'})).toBeVisible();
  await expect(note).toHaveValue('检查 A');
  await dialog.getByRole('button',{name:'来源帧',exact:true}).click();
  await expect(note).toHaveValue('');
  await note.fill('来源帧的指令');
  await dialog.getByRole('button',{name:'返回编辑稿'}).click();
  await expect(note).toHaveValue('检查 A');
  await dialog.getByRole('button',{name:'关闭 ✕'}).click();
  await expect(dialog.getByRole('alert')).toContainText('未发送');
  expect(saves).toBe(1);
});
