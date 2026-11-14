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
  await expect(dialog.getByLabel('引擎')).toHaveCount(0);
  const save = dialog.getByRole('button', { name: '保存编辑稿到项目' });
  await expect(save).toBeInViewport();
  await save.click();
  await expect.poll(() => saved).toMatchObject([{ molecule: 'frame-a', generate_input: false }]);
  await dialog.getByLabel('同时生成原生计算输入').check();
  await expect(dialog.getByLabel('引擎')).toBeVisible();
  await dialog.getByLabel('同时生成原生计算输入').uncheck();
  await expect(dialog.getByLabel('引擎')).toHaveCount(0);
});
test('source is read-only and save follows the explicit editing draft', async ({ page }) => {
  const { dialog, saved } = await open(page);
  const save = dialog.getByRole('button', { name: '保存编辑稿到项目' });
  await dialog.getByRole('slider', { name: '来源帧' }).press('ArrowRight');
  await expect(dialog.getByRole('button', { name: '以此帧建立编辑稿' })).toBeEnabled();
  await expect(save).toBeDisabled();
  await expect(dialog.getByRole('button', { name: '添加原子', exact: true })).toBeDisabled();
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
  const { dialog } = await open(page);
  const edits: unknown[] = [];
  await page.route('**/workbench/edit', route => { edits.push(route.request().postDataJSON()); return route.fulfill({ json: a }); });
  await dialog.locator('summary').filter({ hasText: '调整内坐标、冻结与扫描' }).click();
  await dialog.getByLabel('手动指定移动原子').fill('2');
  await dialog.locator('summary').filter({ hasText: '连接感知与镜像' }).click();
  await dialog.getByRole('button', { name: '预览整分子镜像' }).click();
  await expect.poll(() => edits).toEqual([{ action: 'mirror', plane: 'yz', molecule: 'frame-a' }]);
  await dialog.getByRole('button', { name: '取消预览' }).click();
  await dialog.getByLabel('镜像原子（逗号分隔，留空为整分子）', { exact: true }).fill('1');
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

test('save and return appends the saved path without sending or replacing the conversation draft', async ({ page }) => {
  await installApiMocks(page);
  await page.route('**/workbench/open', route => route.fulfill({ json: document }));
  await page.route('**/workbench/save', route => route.fulfill({ json: { path: 'structures/saved.json', files: [], geometry: a, message: '已保存' } }));
  const sent: string[] = [];
  page.on('request', request => {
    if (request.method() === 'POST' && /\/(messages|agents|response|submit)$/.test(new URL(request.url()).pathname)) sent.push(request.url());
  });
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await page.getByTestId('composer-input').fill('保留我的问题');
  await page.getByRole('button', { name: '分子工作台', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '分子工作台' });
  await dialog.getByLabel('结构来源').fill('[H][H]');
  await dialog.getByRole('button', { name: '新建／打开', exact: true }).click();
  await dialog.getByRole('button', { name: '保存并带回当前对话' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByTestId('composer-input')).toHaveValue('保留我的问题\n\n结构已保存至：structures/saved.json');
  await expect(page.getByTestId('composer-input')).toBeFocused();
  expect(sent).toEqual([]);
});
