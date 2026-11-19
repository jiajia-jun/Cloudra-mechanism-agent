import { expect, test, type Page } from '@playwright/test';
import { installApiMocks, openSpa, PROJECT_ACTIVE } from './fixtures';
import type { DocumentView, GeometryView } from '../src/workbenchTypes';
test.use({ launchOptions: { args: ['--disable-webgl'] } });
const geometry = (molecule: string, x: number): GeometryView => ({ molecule, xyz: '', atoms: [{ index: 1, symbol: 'H', x: 0, y: 0, z: 0 }, { index: 2, symbol: 'H', x, y: 0, z: 0 }], bonds: [{ atom1: 1, atom2: 2, order: 1 }], graph_status: 'declared' });
const a = geometry('frame-a', 1), b = geometry('frame-b', 2);
const document: DocumentView = { document_id: 'trajectory', title: 'Two frames', source_path: 'trajectory.xyz', selected_frame: 0, geometry: a, frames: [{ index: 0, step: 0 }, { index: 1, step: 1 }], modes: [], settings: {}, warnings: [] };
async function open(page: Page) {
  await page.route('**/workbench/fragments', route => route.fulfill({ json: { fragments: [] } }));
  await page.route('**/workbench/open', route => route.fulfill({ json: document }));
  await page.route('**/workbench/documents/trajectory/frames/1', route => route.fulfill({ json: b }));
  const saved: { molecule: string; generate_input: boolean }[] = [];
  await page.route('**/workbench/save', route => {
    const request = route.request().postDataJSON(); saved.push(request);
    return route.fulfill({ json: { path: 'saved.json', files: [], geometry: request.molecule === b.molecule ? b : a, message: '已保存' } });
  });
  await page.goto('/e2e/workbench-builder.html');
  const dialog = page.getByRole('dialog', { name: '分子工作台' });
  await dialog.getByLabel('结构来源').fill('[H][H]');
  await dialog.getByRole('button', { name: '新建／打开', exact: true }).click();
  await expect(dialog.getByLabel('原子列表', { exact: true })).toContainText('H');
  return { dialog, saved };
}
test('basic save needs no advanced tools or calculation settings', async ({ page }) => {
  const { dialog, saved } = await open(page);
  await expect(dialog.getByLabel('内坐标目标值')).toBeHidden();
  await expect(dialog.getByLabel('基团 SMILES', { exact: true })).toBeHidden();
  await expect(dialog.getByLabel('引擎', { exact: true })).toHaveCount(0);
  const save = dialog.getByRole('button', { name: '保存编辑稿到项目' });
  await expect(save).toBeInViewport();
  await save.click();
  await expect.poll(() => saved).toMatchObject([{ molecule: 'frame-a', generate_input: false }]);
  await expect(dialog.getByRole('button', { name:'已保存到项目' })).toBeDisabled();
  await dialog.getByLabel('同时生成原生计算输入').check();
  await expect(save).toBeEnabled();
  await expect(dialog.getByLabel('引擎', { exact: true })).toBeVisible();
  await dialog.getByLabel('同时生成原生计算输入').uncheck();
  await expect(dialog.getByRole('button', { name:'已保存到项目' })).toBeDisabled();
  await expect(dialog.getByLabel('引擎', { exact: true })).toHaveCount(0);
});
test('source is read-only and save follows the explicit editing draft', async ({ page }) => {
  test.slow(); // Open, switch frames and complete three independent saves.
  const { dialog, saved } = await open(page);
  const save = dialog.getByRole('button', { name: '保存编辑稿到项目' });
  await dialog.getByRole('slider', { name: '来源帧' }).press('ArrowRight');
  await expect(dialog.getByRole('button', { name: '以此帧建立编辑稿' })).toBeEnabled();
  await expect(save).toBeDisabled();
  await expect(dialog.getByRole('button', { name: '编辑模式', exact: true })).toBeDisabled();
  await expect(dialog.getByLabel('结构名称', { exact: true })).toBeDisabled();
  await dialog.getByRole('button', { name: '返回编辑稿', exact: true }).click();
  await save.click();
  await expect.poll(() => saved).toMatchObject([{ molecule: 'frame-a' }]);
  await dialog.getByRole('button', { name: '来源帧', exact: true }).click();
  await dialog.getByRole('button', { name: '以此帧建立编辑稿' }).click();
  await save.click();
  await expect.poll(() => saved).toMatchObject([{ molecule: 'frame-a' }, { molecule: 'frame-b' }]);
  await dialog.getByRole('button', { name: '撤销', exact: true }).click();
  await save.click();
  await expect.poll(() => saved).toMatchObject([{ molecule: 'frame-a' }, { molecule: 'frame-b' }, { molecule: 'frame-a' }]);
});
test('mirror scope does not inherit the coordinate moving atom list', async ({ page }) => {
  test.slow(); // Exercise the coordinate dialog followed by two separate previews.
  const { dialog } = await open(page);
  const edits: unknown[] = [];
  await page.route('**/workbench/edit', route => { edits.push(route.request().postDataJSON()); return route.fulfill({ json: a }); });
  await dialog.getByLabel('原子列表', { exact: true }).getByRole('button', { name: 'H1', exact: true }).click();
  await dialog.getByLabel('原子列表', { exact: true }).getByRole('button', { name: 'H2', exact: true }).click();
  await dialog.getByRole('button', { name: '编辑距离', exact: true }).click();
  const editor = page.getByRole('dialog', { name: '调整距离', exact: true });
  await editor.getByRole('button', {name:'画布选择移动原子'}).click();
  await dialog.getByLabel('原子列表', {exact:true}).getByRole('button', {name:'H2',exact:true}).click();
  await dialog.getByRole('button', {name:'使用所选原子'}).click();
  await editor.getByRole('button', { name: '取消', exact: true }).click();
  await dialog.locator('summary').filter({ hasText: '连接感知与镜像' }).click();
  await dialog.getByRole('button', { name: '预览整分子镜像' }).click();
  await expect.poll(() => edits).toEqual([{ action: 'mirror', plane: 'yz', molecule: 'frame-a' }]);
  await dialog.getByRole('button', { name: '取消预览' }).click();
  await dialog.getByRole('button', {name:'画布选择镜像原子'}).click();
  await dialog.getByLabel('原子列表', {exact:true}).getByRole('button', {name:'H1',exact:true}).click();
  await dialog.getByRole('button', {name:'使用所选原子'}).click();
  await dialog.getByRole('button', { name: '预览指定原子镜像' }).click();
  await expect.poll(() => edits).toEqual([{ action: 'mirror', plane: 'yz', molecule: 'frame-a' }, { action: 'mirror', plane: 'yz', moving_atoms: [1], molecule: 'frame-a' }]);
});

test('overview offers research actions before optional runtime details', async ({ page }) => {
  await installApiMocks(page);
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await page.locator('.view-mode-btn').filter({ hasText: '控制台' }).click();
  const actions = page.getByRole('navigation', { name: '研究操作' });
  await expect(actions.getByRole('button', { name: '继续研究对话' })).toBeVisible();
  await expect(actions.getByRole('button', { name: '打开分子工作台' })).toBeVisible();
  await expect(page.locator('.portal-agent-section')).toBeHidden();
  await page.locator('.portal-details > summary').click();
  await expect(page.locator('.portal-agent-section')).toBeVisible();
  await actions.getByRole('button', { name: '查看研究结果' }).click();
  await expect(page.locator('.portal-task-actions')).toHaveCount(0);
});

test('local XYZ keeps its name and uses the charge that the user declares to perceive bonds', async ({ page }) => {
  const raw = { ...a, graph_status: 'unresolved', bonds: [], preoptimization_blocker: 'bond order required' };
  const fallback = { ...a, graph_status: 'distance-inferred', preoptimization_blocker: 'bond order required' };
  await page.route('**/workbench/fragments', route => route.fulfill({ json: { fragments: [] } }));
  let request: Record<string, unknown> = {};
  await page.route('**/workbench/open', route => {
    request = route.request().postDataJSON();
    return route.fulfill({ json: { ...document, geometry: raw, title: request.input_name } });
  });
  let edit: Record<string, unknown> = {};
  await page.route('**/workbench/edit', route => {
    edit = route.request().postDataJSON();
    return route.fulfill({ json: fallback });
  });
  await page.goto('/e2e/workbench-builder.html');
  const dialog = page.getByRole('dialog', { name: '分子工作台' });
  await dialog.getByLabel('本地结构／计算文件').setInputFiles({ name: 'ion.xyz', mimeType: 'text/plain', buffer: Buffer.from('2\nion\nH 0 0 0\nH 0 0 1') });
  await dialog.getByRole('button', { name: '新建／打开' }).click();
  expect(request).toMatchObject({ input_name: 'ion.xyz', input_format: 'xyz' });
  await expect(dialog.getByLabel('结构名称', { exact: true })).toHaveValue('ion.xyz');
  const optimize = dialog.getByRole('button', { name: '力场预优化' });
  await expect(optimize).toBeDisabled();
  await dialog.locator('summary').filter({ hasText: '连接感知与镜像' }).click();
  const resolve = dialog.getByRole('button', { name: '明确感知连接关系' });
  await expect(resolve).toBeEnabled();
  await resolve.click();
  await expect.poll(() => edit).toEqual({ action: 'resolve_bonds', molecule: raw.molecule });
  await dialog.getByRole('button', { name: '取消预览' }).click();
  await dialog.getByLabel('感知键级所用总电荷').fill('1');
  await resolve.click();
  await expect.poll(() => edit).toMatchObject({ charge: 1, action: 'resolve_bonds' });
  await dialog.getByRole('button', { name: '确认修改' }).click();
  await expect(dialog.locator('.viewer-3d-atomcount')).toContainText('按距离推断连接，键级未知');
  await expect(optimize).toBeDisabled();
});

test('completed compute job opens its exact result with separate raw and input actions', async ({ page }) => {
  await installApiMocks(page, { jobs: [{ id: 17, state: 'done', jobtype: 'xtb', path: '/project/water.xyz', session_id: null }] });
  const urls: URL[] = [];
  await page.route('**/workbench/products?**', route => {
    urls.push(new URL(route.request().url()));
    return route.fulfill({json:{objects:[],total:1,offset:0,products:[{
      id:'job:17',job_id:17,kind:'calculation',job_type:'xtb',title:'water',state:'done',
      path:'/project/water.out',can_open:true,associations:[],files:[
        {role:'input',path:'/project/water.xyz',can_open:true}, {role:'output',path:'/project/water.out'},
      ],
    }]}});
  });
  await page.route('**/workbench/preview', route=>route.fulfill({status:400,json:{detail:'该 xTB 日志没有完整的原生末帧结构'}}));
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, {exact:true}).click();
  await page.locator('.view-mode-btn').filter({hasText:'控制台'}).click();
  await page.locator('.console-subnav-btn').filter({hasText:'调度'}).click();
  await page.getByRole('button',{name:'最近 100 条'}).click();
  await page.getByRole('button',{name:'查看作业 #17 的结果'}).click();
  await expect(page.getByLabel('搜索结构与计算')).toHaveValue('#17');
  const card = page.locator('.research-product-card');
  await expect(card).toContainText('没有完整的原生末帧结构');
  await expect(card.getByRole('button',{name:'打开结果结构'})).toHaveCount(0);
  await expect(card.getByRole('button',{name:'打开输入结构'})).toBeVisible();
  await expect(card.getByRole('link',{name:'查看原始日志'})).toHaveAttribute('href',/jobs\/17\/files\/output\?download=false/);
  await card.getByText('本记录文件').click();
  await expect(card.getByRole('link',{name:'下载 water.out'})).toHaveAttribute('href',/jobs\/17\/files\/output\?download=true/);
  expect(urls.at(-1)?.searchParams.get('query')).toBe('#17');
});
