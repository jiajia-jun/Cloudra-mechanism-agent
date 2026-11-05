import { test, expect } from '@playwright/test';
import { installApiMocks, openSpa, PROJECT_ACTIVE } from './fixtures';

test('DAG keeps complexes distinct from separated products and preserves component charges', async ({ page }, testInfo) => {
  await installApiMocks(page, { jobs: [], projects: [{ ...PROJECT_ACTIVE, settings: { ...PROJECT_ACTIVE.settings, orchestration_mode: 'dag_guided' } }] });
  await page.route('**/api/v2/chem/render-smiles?*', route => {
    const smiles = new URL(route.request().url()).searchParams.get('smiles') ?? '';
    return route.fulfill({
      contentType: 'image/svg+xml',
      body: `<svg xmlns="http://www.w3.org/2000/svg" width="180" height="40"><text x="90" y="26" text-anchor="middle" fill="#e4ebf5" font-size="18">${smiles}</text></svg>`,
    });
  });
  await page.route('**/api/v2/projects/*/dag/delivery', route => route.fulfill({
    json: { mode: 'dag_guided', graph: {
      nodes: [
        { node_id: 'complex', label: 'Bound pair', smiles: ['[Na+].[Cl-]'] },
        { node_id: 'separated', label: 'Released pair', smiles: ['[Na+]', '[Cl-]'] },
      ],
      edges: [{ edge_id: 'release', source_node_id: 'complex', target_node_id: 'separated' }],
    } },
  }));
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await page.getByRole('button', { name: '控制台', exact: true }).click();
  await page.getByRole('button', { name: '结构、计算与机理', exact: true }).click();

  const complex = page.locator('.dag-canvas-compact g').filter({ has: page.locator('text.dag-node-label', { hasText: 'Bound pair' }) });
  const separated = page.locator('.dag-canvas-compact g').filter({ has: page.locator('text.dag-node-label', { hasText: 'Released pair' }) });
  await expect(complex).toContainText('络合物');
  await expect(complex.locator('image')).toHaveCount(1);
  await expect(separated).toContainText('[Na+] + [Cl-]');
  await expect(separated.locator('image')).toHaveCount(2);
  expect(new URL(await complex.locator('image').getAttribute('href') ?? '', 'http://localhost').searchParams.get('smiles')).toBe('[Na+].[Cl-]');
  expect(await separated.locator('image').evaluateAll(images => images.map(image => new URL(image.getAttribute('href') ?? '', location.origin).searchParams.get('smiles')))).toEqual(['[Na+]', '[Cl-]']);
  await page.locator('.dag-canvas-compact').screenshot({ path: testInfo.outputPath('separated-species.png') });

  await separated.locator('rect').click();
  await page.getByRole('button', { name: '图操作与审计', exact: true }).click();
  const editForm = page.locator('.dag-form').filter({ hasText: '编辑反应节点' });
  await expect(editForm.locator('textarea')).toHaveValue('[Na+]\n[Cl-]');
  const saved = page.waitForRequest(request => request.url().endsWith('/dag/mutations') && request.method() === 'POST');
  await editForm.getByRole('button', { name: '保存更改', exact: true }).click();
  expect((await saved).postDataJSON().operations[0].changes.smiles).toEqual(['[Na+]', '[Cl-]']);
});
