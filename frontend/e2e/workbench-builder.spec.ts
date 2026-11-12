import { expect, test } from '@playwright/test';
import type { GeometryView } from '../src/workbenchTypes';
import { installApiMocks, openSpa, PROJECT_ACTIVE } from './fixtures';

// Exercise the accessible atom list on a machine without WebGL.
test.use({ launchOptions: { args: ['--disable-webgl'] } });

test('builds a molecule from blank with the atom list and saves the native draft', async ({ page }) => {
  test.slow();
  await installApiMocks(page, { jobs: [] });
  const carbon = { index: 1, symbol: 'C', atom_id: 'c', x: 0, y: 0, z: 0, formal_charge: 0, target_valence: null, bond_valence: 0 };
  const oxygen = { index: 2, symbol: 'O', atom_id: 'o', x: 1.3, y: 0, z: 0, formal_charge: 0, target_valence: null, bond_valence: 0 };
  const charged = { ...carbon, formal_charge: 1, target_valence: 3 };
  const geometry = (molecule: string, atoms: GeometryView['atoms'], order = 0): GeometryView => ({
    molecule, xyz: '', atoms, graph_status: 'edited',
    bonds: order ? [{ atom1: 1, atom2: 2, order }] : [],
  });
  const steps = [
    { action: { action: 'add_atom', element: 'C', atoms: [], order: 1 }, result: geometry('seed-c', [carbon]) },
    { action: { action: 'atom_state', molecule: 'seed-c', atoms: [1], formal_charge: 1, valence: 3 }, result: geometry('charged-c', [charged]) },
    { action: { action: 'add_atom', molecule: 'charged-c', element: 'O', atoms: [1], order: 1 }, result: geometry('co', [
      { ...charged, bond_valence: 1 }, { ...oxygen, bond_valence: 1 },
    ], 1) },
    { action: { action: 'bond', molecule: 'co', atoms: [2, 1], order: 2 }, result: geometry('co-double', [
      { ...charged, bond_valence: 2 }, { ...oxygen, bond_valence: 2 },
    ], 2) },
    { action: { action: 'bond', molecule: 'co-double', atoms: [2, 1], order: 0 }, result: geometry('co-fragments', [charged, oxygen]) },
    { action: { action: 'delete_atom', molecule: 'co-fragments', atoms: [2] }, result: {
      ...geometry('final-c', [charged]),
      changes: { deleted_atoms: [2], deleted_atom_ids: ['o'], index_map: { '1': 1 }, moved_atoms: [] },
    } },
  ];
  const edits: unknown[] = [];
  await page.route('**/workbench/edit', async route => {
    const step = steps[edits.length];
    edits.push(route.request().postDataJSON());
    if (!step) return route.fulfill({ status: 400, json: { detail: 'Unexpected molecule edit' } });
    await route.fulfill({ json: step.result });
  });
  const saved: unknown[] = [];
  await page.route('**/workbench/save', async route => {
    saved.push(route.request().postDataJSON());
    await route.fulfill({ json: { path: 'structure.json', files: [], geometry: steps[5].result, message: '已保存' } });
  });

  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await page.getByRole('button', { name: '分子工作台', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '分子工作台' });
  const builder = dialog.getByRole('region', { name: '分子建模' });
  const atoms = dialog.getByLabel('原子列表', { exact: true });
  await test.step('Add the first atom and apply its target valence', async () => {
    await expect(builder.getByLabel('元素', { exact: true })).toHaveValue('C');
    await builder.getByRole('button', { name: '添加原子', exact: true }).click();
    await expect(atoms.getByRole('button', { name: 'C1', exact: true })).toBeVisible();
    await builder.getByLabel('形式电荷').fill('1');
    await builder.getByLabel('目标价数').fill('3');
    await builder.getByRole('button', { name: '应用价态' }).click();
    await expect(builder.getByRole('button', { name: '补氢至目标价数' })).toBeEnabled();
  });
  await test.step('Attach an atom and change the bond through the atom list', async () => {
    await builder.getByLabel('元素', { exact: true }).fill('O');
    await builder.getByRole('button', { name: '添加原子', exact: true }).click();
    await expect(atoms.getByRole('button', { name: 'O2', exact: true })).toBeVisible();
    await atoms.getByRole('button', { name: 'C1', exact: true }).click();
    const order = builder.getByLabel('键级');
    await expect(order).toBeEnabled();
    await order.selectOption('2');
    await builder.getByRole('button', { name: '设置键', exact: true }).click();
    await expect(builder).toContainText('当前双键');
    await builder.getByRole('button', { name: '断开键', exact: true }).click();
    await expect(builder).toContainText('两原子未成键');
  });
  await test.step('Remove the selected atom, save and start another blank draft', async () => {
    await atoms.getByRole('button', { name: 'C1', exact: true }).click();
    await builder.getByRole('button', { name: '删除所选原子' }).click();
    await expect(atoms.getByRole('button', { name: 'O2', exact: true })).toHaveCount(0);
    await dialog.getByRole('button', { name: '保存编辑稿到项目' }).click();
    await expect.poll(() => saved).toMatchObject([{ molecule: 'final-c', generate_input: false }]);
    await expect(dialog.locator('.wb-message')).toContainText('已保存');
    await dialog.getByRole('button', { name: '新建空白分子', exact: true }).click();
    await expect(dialog.locator('.wb-empty')).toBeVisible();
    await expect(dialog.getByRole('button', { name: '撤销', exact: true })).toBeDisabled();
  });
  expect(edits).toEqual(steps.map(step => step.action));
});
