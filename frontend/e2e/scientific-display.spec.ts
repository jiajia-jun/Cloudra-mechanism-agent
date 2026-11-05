import { test, expect } from '@playwright/test';
import { installApiMocks, openSpa, PROJECT_ACTIVE } from './fixtures';

for (const state of ['proposed', 'supported', 'vetoed', 'missing-frequency']) {
  test(`TS display uses evidence: ${state}`, async ({ page }, testInfo) => {
    await installApiMocks(page, { jobs: [], projects: [{ ...PROJECT_ACTIVE, settings: { ...PROJECT_ACTIVE.settings, orchestration_mode: 'dag_guided' } }] });
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
    await page.getByRole('button', { name: '结构、计算与机理', exact: true }).click();
    const edge = page.locator('.dag-edge-line');
    const edgeStyle = await edge.getAttribute('style');
    expect(edgeStyle).toContain(state === 'proposed' ? 'stroke: var(--border-strong)' : 'stroke: var(--green-soft)');
    if (state === 'vetoed') expect(edgeStyle).toContain('stroke-dasharray: 5, 3');
    else expect(edgeStyle).not.toContain('stroke-dasharray');
    await page.locator('.dag-edge-hit').click({ force: true });
    await expect(page.locator('.dag-open-structure')).toContainText('Candidate step');
    await expect(page.getByRole('button', { name: '打开记录中的结构' })).toBeVisible();
    await expect(page.locator('.molecule-3d-container')).toHaveCount(0);
    await page.getByRole('button', { name: '频率确证' }).click();
    await expect(page.locator('.evidence-stage-card')).toContainText(state === 'missing-frequency' ? 'PENDING' : 'SUPPORTED');
    await expect(page.locator('.evidence-stage-card')).not.toContainText('420.5');
    await page.screenshot({ path: testInfo.outputPath(`ts-${state}.png`), fullPage: true });
    await page.locator('.dag-node-rect').first().click();
    await expect(page.locator('.dag-open-structure')).toContainText('Reactant');
  });
}
