import { expect, test } from '@playwright/test';
import { geometry, openCoordinateWorkbench } from './workbench-coordinate-fixture';

test.use({ launchOptions: { args: ['--disable-webgl'] } });
// Each case opens, previews, cancels and reopens the dialog on hosted runners.
test.setTimeout(60_000);

for (const { count, label, current } of [
  { count: 2, label: '距离', current: '1.00000' },
  { count: 3, label: '键角', current: '90.00000' },
  { count: 4, label: '二面角', current: '-90.00000' },
]) {
  test(`${label} popup starts with the actual coordinate and previews ordered atoms`, async ({ page }) => {
    const { workbench, atoms, edits } = await openCoordinateWorkbench(page);
    for (let i = 1; i <= count; i++) await atoms.getByRole('button', { name: `${i === 4 ? 'H' : 'C'}${i}`, exact: true }).click();
    const trigger = workbench.getByRole('button', { name: `编辑${label}`, exact: true });
    await expect(trigger).toBeVisible();
    expect(await trigger.evaluate(node => !!node.closest('.wb-main'))).toBe(true);
    await trigger.click();
    const editor = page.getByRole('dialog', { name: `调整${label}`, exact: true });
    await expect(editor).toBeVisible();
    await expect(editor.getByLabel('内坐标目标值')).toHaveValue(current);
    await expect(editor.getByLabel('内坐标目标值')).toBeFocused();
    await editor.getByText('冻结与扫描', { exact: true }).click();
    await expect(editor.getByLabel('扫描起点', { exact: true })).toHaveValue(current);
    await editor.getByLabel('内坐标目标值').fill(count === 2 ? '1.5' : '120');
    await editor.getByRole('button', { name: '预览结构调整' }).click();
    await expect(editor).toHaveCount(0);
    await expect.poll(() => edits).toEqual([{ action: 'coordinate', molecule: 'four-atoms', atoms: Array.from({ length: count }, (_, i) => i + 1), value: count === 2 ? 1.5 : 120, fixed_side: 'first' }]);
    await workbench.getByRole('button', { name: '取消预览' }).click();
    await trigger.click();
    await expect(page.getByRole('dialog', { name: `调整${label}`, exact: true }).getByLabel('内坐标目标值')).toHaveValue(current);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: `调整${label}`, exact: true })).toHaveCount(0);
    await expect(trigger).toBeFocused();
  });
}

test('coordinate errors stay in the popup and cancelling changes no draft', async ({ page }) => {
  const { workbench, atoms } = await openCoordinateWorkbench(page);
  await atoms.getByRole('button', { name: 'C1', exact: true }).click();
  await atoms.getByRole('button', { name: 'C2', exact: true }).click();
  await workbench.getByRole('button', { name: '编辑距离', exact: true }).click();
  const editor = page.getByRole('dialog', { name: '调整距离', exact: true });
  await page.route('**/workbench/edit', route => route.fulfill({ status: 400, json: { detail: '请选择环中的移动原子' } }));
  await editor.getByRole('button', { name: '预览结构调整' }).click();
  await expect(editor.getByRole('alert')).toContainText('请选择环中的移动原子');
  await editor.getByRole('button', { name: '取消', exact: true }).click();
  await expect(workbench.getByRole('button', { name: '撤销', exact: true })).toBeDisabled();
});

test('saved freeze and scan values reopen separately from the measured coordinate', async ({ page }) => {
  const { workbench, atoms, edits } = await openCoordinateWorkbench(page);
  await atoms.getByRole('button', { name: 'C1', exact: true }).click();
  await atoms.getByRole('button', { name: 'C2', exact: true }).click();
  await workbench.getByRole('button', { name: '编辑距离', exact: true }).click();
  const editor = page.getByRole('dialog', { name: '调整距离', exact: true });
  await editor.getByLabel('内坐标目标值').fill('1.7');
  await editor.getByText('冻结与扫描', { exact: true }).click();
  await editor.getByRole('button', { name: '定义冻结坐标', exact: true }).click();
  await expect(editor).toHaveCount(0);
  expect(edits).toEqual([]);
  await expect(workbench.getByRole('button', { name: '力场预优化', exact: true })).toBeDisabled();
  await workbench.locator('summary').filter({ hasText: '已定义的冻结与扫描' }).click();
  await workbench.locator('.wb-def-content').filter({ hasText: '冻结' }).click();
  await expect(editor.getByLabel('内坐标目标值')).toHaveValue('1.7');
  await expect(editor).toContainText('1.00000 Å');
  await editor.getByLabel('扫描起点', { exact: true }).fill('1.2');
  await editor.getByLabel('终点', { exact: true }).fill('2.2');
  await editor.getByLabel('步数', { exact: true }).fill('5');
  await editor.getByRole('button', { name: '添加独立扫描坐标', exact: true }).click();
  await workbench.locator('.wb-def-content').filter({ hasText: '扫描' }).click();
  await expect(editor.getByLabel('扫描起点', { exact: true })).toHaveValue('1.2');
  await expect(editor.getByLabel('终点', { exact: true })).toHaveValue('2.2');
  await expect(editor.getByLabel('步数', { exact: true })).toHaveValue('5');
});

test('force field optimization applies to the draft immediately and saving is optional', async ({ page }) => {
  const { workbench } = await openCoordinateWorkbench(page);
  const edits: unknown[] = [], saved: unknown[] = [];
  await page.route('**/workbench/edit', route => {
    const body = route.request().postDataJSON(); edits.push(body);
    return route.fulfill({ json: { ...geometry, molecule: 'optimized', optimization: {
      force_field: body.force_field, converged: false, initial_energy: 12.3, final_energy: 4.5, energy_unit: 'kcal/mol',
    } } });
  });
  await page.route('**/workbench/save', route => {
    saved.push(route.request().postDataJSON());
    return route.fulfill({ json: { path: 'saved.json', files: [], geometry, message: '已保存' } });
  });
  await expect(workbench.getByLabel('预优化力场', { exact: true })).toHaveValue('MMFF94');
  await workbench.getByLabel('预优化力场', { exact: true }).selectOption('UFF');
  await workbench.getByRole('button', { name: '力场预优化', exact: true }).click();
  await expect.poll(() => edits).toEqual([{ action: 'preoptimize', force_field: 'UFF', molecule: 'four-atoms' }]);
  await expect(workbench.locator('.wb-optimization')).toContainText('UFF · 未收敛');
  await expect(workbench.locator('.wb-optimization')).toContainText('12.3000 → 4.5000 kcal/mol');
  await expect(workbench.getByRole('button', { name: '确认修改', exact: true })).toHaveCount(0);
  expect(saved).toEqual([]);
  await expect(workbench.getByRole('button', { name: '保存编辑稿到项目' })).toBeEnabled();
  await workbench.getByRole('button', { name: '撤销', exact: true }).click();
  await expect(workbench.locator('.wb-optimization')).toHaveCount(0);
  expect(saved).toEqual([]);
  await workbench.getByRole('button', { name: '力场预优化', exact: true }).click();
  await expect(workbench.locator('.wb-optimization')).toBeVisible();
  await workbench.getByRole('button', { name: '保存编辑稿到项目' }).click();
  await expect.poll(() => saved).toMatchObject([{ molecule: 'optimized' }]);
});

test('manual hybridization and clearing its override use the shared atom state action', async ({ page }) => {
  const { workbench, atoms } = await openCoordinateWorkbench(page);
  const edits: unknown[] = [];
  await page.route('**/workbench/edit', route => {
    const body = route.request().postDataJSON(); edits.push(body);
    return route.fulfill({ json: { ...geometry, atoms: geometry.atoms.map((atom, index) => index ? atom : { ...atom, hybridization: body.hybridization ?? 'sp3', hybridization_override: body.hybridization, lone_pairs: 0 }) } });
  });
  await atoms.getByRole('button', { name: 'C1', exact: true }).click();
  const builder = workbench.getByRole('region', { name: '分子建模' });
  await builder.getByLabel('杂化方式', { exact: true }).selectOption('sp2');
  await builder.getByRole('button', { name: '应用价态', exact: true }).click();
  await expect(builder).toContainText('当前 sp2 · 孤对电子 0 对');
  await builder.getByLabel('杂化方式', { exact: true }).selectOption('');
  await builder.getByRole('button', { name: '应用价态', exact: true }).click();
  await expect.poll(() => edits).toEqual(['sp2', null].map(hybridization => ({ action: 'atom_state', atoms: [1], formal_charge: 0, valence: null, hybridization, molecule: 'four-atoms' })));
});
