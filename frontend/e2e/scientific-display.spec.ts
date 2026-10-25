import { test, expect } from '@playwright/test';
import { installApiMocks, openSpa, PROJECT_ACTIVE } from './fixtures';

for (const state of ['proposed', 'supported', 'vetoed', 'missing-frequency']) {
  test(`TS display uses evidence: ${state}`, async ({ page }, testInfo) => {
    await installApiMocks(page, { jobs: [] });
    const xyz = '2\nillustrative geometry\nH 0 0 0\nH 0 0 0.74';
    await page.route('**/api/v2/projects/*/dag/delivery', route => route.fulfill({
      json: { mode: 'dag_guided', graph: {
        nodes: [{ node_id: 'a', label: 'Reactant', metadata: { xyz } }, { node_id: 'b', label: 'Product' }],
        edges: [{ edge_id: 'ts', label: 'Candidate step', source_node_id: 'a', target_node_id: 'b',
          evidence_level: state === 'proposed' ? 'proposed' : 'saddle_supported',
          evidence_vetoed: state === 'vetoed', metadata: { xyz, imaginary_frequency: 420.5 },
          stages: [{ kind: 'ts_opt', status: 'supported' }, { kind: 'frequency', status: state === 'missing-frequency' ? 'pending' : 'supported' }],
        }],
      } },
    }));
    await openSpa(page);
    await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
    await page.getByRole('button', { name: '控制台', exact: true }).click();
    await page.getByRole('button', { name: '机理 DAG', exact: true }).click();
    await page.locator('.dag-edge-hit').click({ force: true });
    const viewer = page.locator('.molecule-3d-container');
    await expect(viewer).toContainText(state === 'supported' ? '鞍点证据已支持' : '候选 TS · 未确证');
    await expect(viewer).toContainText('虚频未知');
    await expect(viewer).not.toContainText('420.5');
    await expect(viewer).toContainText('当前显示几何未与科学证据绑定');
    await expect(viewer.locator('canvas')).toBeVisible();
    await viewer.getByRole('button', { name: '示意振动', exact: true }).click();
    await expect(viewer).toContainText('示意动画：非计算简正模，不作为虚频证据');
    await page.screenshot({ path: testInfo.outputPath(`ts-${state}.png`), fullPage: true });
    await page.locator('.dag-node-rect').first().click();
    await expect(viewer.locator('.badge-ts-marker')).toHaveCount(0);
    await expect(viewer.getByRole('button', { name: '示意振动', exact: true })).toBeVisible();
  });
}
