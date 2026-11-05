import { expect, test } from '@playwright/test';
import { JOB, PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

test('workbench keeps explicit project creation and global controls in its persistent sidebar', async ({ page }) => {
  await installApiMocks(page, { jobs: [] });
  await openSpa(page);
  await expect(page.locator('.view-mode-switcher').getByRole('button', { name: '控制台', exact: true })).toBeVisible();
  const sidebar = page.locator('aside.left-sidebar');
  await expect(sidebar.getByRole('button', { name: '全局设置', exact: true })).toBeVisible({ timeout: 1500 });
  await expect(sidebar.getByPlaceholder('新建项目名…')).toBeHidden();
  await sidebar.getByRole('button', { name: '新建项目', exact: true }).click();
  await expect(sidebar.getByPlaceholder('新建项目名…')).toBeVisible();
  await expect(sidebar.getByPlaceholder('项目地址 (留空使用默认工作区)…')).toBeVisible();
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await expect(page.locator('.view-mode-btn').filter({ hasText: '控制台' })).toBeVisible();
  await page.locator('.view-mode-btn').filter({ hasText: '控制台' }).click();
  for (const name of ['结构、计算与机理', '计算调度', '审计日志']) {
    await expect(page.getByRole('button', { name, exact: true })).toBeVisible();
  }
});

test('research results combine the mechanism graph and products while the molecular workbench opens independently', async ({ page }) => {
  const project = { ...PROJECT_ACTIVE, name: '机理研究工作台', settings: { orchestration_mode: 'dag_guided', defaults: {} } };
  await installApiMocks(page, { projects: [project], jobs: [JOB] });
  await page.route('**/api/v2/chem/render-smiles?*', (route) => {
    const smiles = new URL(route.request().url()).searchParams.get('smiles') ?? '';
    return route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="180" height="40"><rect width="180" height="40" rx="4" fill="#eaf3f3"/><text x="90" y="26" text-anchor="middle" fill="#243443" font-size="18">${smiles}</text></svg>` });
  });
  await page.route('**/api/v2/projects/*/dag/delivery', (route) => route.fulfill({ json: {
    mode: 'dag_guided', graph: {
      nodes: [
        { node_id: 'complex', label: '结合物种', smiles: ['[Na+].[Cl-]'], metadata: { xyz: '2\nIllustrative NaCl display\nNa 0 0 0\nCl 2.4 0 0' } },
        { node_id: 'separated', label: '分离产物', smiles: ['[Na+]', '[Cl-]'] },
      ],
      edges: [{ edge_id: 'release', label: '候选解离步骤（示例）', source_node_id: 'complex', target_node_id: 'separated', evidence_level: 'proposed' }],
    },
  } }));
  await openSpa(page);
  await page.getByTitle(`选择项目: ${project.name}`, { exact: true }).click();
  await page.locator('.view-mode-btn').filter({ hasText: '控制台' }).click();
  await page.getByRole('button', { name: '结构、计算与机理', exact: true }).click();
  await expect(page.locator('.dag-node-rect')).toHaveCount(2);
  await expect(page.locator('.dag-edge-hit')).toHaveCount(1);
  await expect(page.locator('.dag-canvas-compact')).toContainText('结合物种');
  await expect(page.locator('.dag-canvas-compact')).toContainText('分离产物');
  await page.getByRole('button', { name: '计算调度', exact: false }).click();
  await expect(page.locator('.ops-dashboard-root')).toBeVisible();
  await expect(page.locator('.ops-table tbody tr').filter({ hasText: '#7' })).toContainText('running');
  await page.getByRole('button', { name: '结构、计算与机理', exact: true }).click();
  await expect(page.locator('.dag-node-rect')).toHaveCount(2);
  await expect(page.locator('.dag-open-structure')).toBeVisible();
  await expect(page.locator('.molecule-3d-container')).toHaveCount(0);
  await page.getByRole('button', { name: '分子工作台', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '分子工作台' })).toBeVisible();
  await page.screenshot({ path: '/tmp/cloudra-workbench-restored.png', fullPage: true });
});

test('a project starts through the explicit sidebar form without automatically launching an agent', async ({ page }) => {
  const projects: object[] = [];
  await installApiMocks(page, { projects, agents: [], jobs: [] });
  const created = { ...PROJECT_ACTIVE, id: 'proj_explicit', name: '显式研究项目', workspace_dir: '/tmp/mechanism-workbench' };
  const creations: unknown[] = [];
  const spawns: string[] = [];
  page.on('request', (request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/agents')) spawns.push(request.url());
  });
  await page.route('**/api/v2/projects', (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    creations.push(route.request().postDataJSON());
    projects.push(created);
    return route.fulfill({ status: 201, json: { command_id: 'cmd_create', event_id: 'ev_create', accepted: true, data: created } });
  });
  await openSpa(page);
  await expect(page.getByTestId('composer-input')).toBeDisabled();
  await page.getByRole('button', { name: '新建项目', exact: true }).click();
  await page.getByPlaceholder('新建项目名…').fill(' 显式研究项目 ');
  await page.getByPlaceholder('项目地址 (留空使用默认工作区)…').fill('/tmp/mechanism-workbench');
  expect(creations).toEqual([]);
  await page.getByTitle('新建项目', { exact: true }).click();
  await expect(page.getByTitle(`选择项目: ${created.name}`, { exact: true })).toBeVisible();
  await expect(page.getByTestId('composer-input')).toBeEnabled();
  expect(creations).toEqual([{ name: '显式研究项目', workspace_dir: '/tmp/mechanism-workbench' }]);
  expect(spawns).toEqual([]);
  await expect(page.getByPlaceholder('新建项目名…')).toHaveValue('');
});
