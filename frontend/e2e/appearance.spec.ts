import { expect, test, type Page } from '@playwright/test';
import { AGENT, JOB, PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

async function mockAppearanceSettings(page: Page) {
  const slot = { provider: 'custom', model: 'test-model', url: 'https://llm.example/v1', key_set: true, context_window: 200000, timeout: 300, supports_vision: true, reasoning_effort: 'high' };
  await page.route('**/api/v2/runtime/config', (route) => route.fulfill({ json: {
    config_file: '/tmp/config.yaml', coordinator: slot, follower: slot,
    search_provider: 'deepseek', deepseek_api_key_set: false,
    tool_document_loading: {
      strategy: 'llm', semantic_backend: 'jev',
      jev: { endpoint: '', model: '', key_set: false, min_probability: null, max_tools: null },
      reranker: { endpoint: '', model: '', key_set: false, min_score: null, max_tools: null },
    },
  } }));
  await page.route('**/api/v2/runtime/providers', (route) => route.fulfill({ json: [] }));
  const patches: string[] = [];
  page.on('request', (request) => {
    if (request.method() === 'PATCH' && new URL(request.url()).pathname.startsWith('/api/v2/')) patches.push(request.url());
  });
  return patches;
}

test('appearance controls apply immediately and preserve the saved choice after reload', async ({ page }) => {
  await installApiMocks(page, { jobs: [] });
  const patches = await mockAppearanceSettings(page);
  await openSpa(page);
  await page.getByRole('button', { name: '全局设置', exact: true }).click();
  const styles = page.getByRole('group', { name: '界面风格', exact: true });
  await expect(styles).toBeVisible({ timeout: 1500 });
  await expect(styles.getByRole('button', { name: '原版工作台', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await styles.getByRole('button', { name: '浅蓝玻璃', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'glass');
  expect(await page.evaluate(() => localStorage.getItem('cloudra.appearance'))).toBe('glass');
  await page.screenshot({ path: '/tmp/cloudra-appearance-settings.png', fullPage: true, animations: 'disabled' });
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'glass');
  await page.getByRole('button', { name: '全局设置', exact: true }).click();
  await expect(styles.getByRole('button', { name: '浅蓝玻璃', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await styles.getByRole('button', { name: '原版工作台', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'original');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'original');
  expect(await page.evaluate(() => localStorage.getItem('cloudra.appearance'))).toBe('original');
  expect(patches).toEqual([]);
});

test('all appearances preserve the selected project, agent, DAG and compute workbench', async ({ page }) => {
  const project = { ...PROJECT_ACTIVE, name: '机理研究工作台', settings: { orchestration_mode: 'dag_guided', defaults: {} } };
  await installApiMocks(page, { projects: [project], jobs: [JOB] });
  const patches = await mockAppearanceSettings(page);
  await page.route('**/api/v2/chem/render-smiles?*', (route) => {
    const smiles = new URL(route.request().url()).searchParams.get('smiles') ?? '';
    return route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="180" height="40"><text x="90" y="26" text-anchor="middle" fill="#cbd5e1" font-size="18">${smiles}</text></svg>` });
  });
  await page.route('**/api/v2/projects/*/dag/delivery', (route) => route.fulfill({ json: {
    mode: 'dag_guided', graph: {
      nodes: [
        { node_id: 'complex', label: '结合物种', smiles: ['[Na+].[Cl-]'] },
        { node_id: 'separated', label: '分离产物', smiles: ['[Na+]', '[Cl-]'], metadata: { xyz: '2\nIllustrative separated-pair display\nNa 0 0 0\nCl 5 0 0' } },
      ],
      edges: [{ edge_id: 'release', label: '候选解离步骤（示例）', source_node_id: 'complex', target_node_id: 'separated', evidence_level: 'proposed' }],
    },
  } }));
  await openSpa(page);
  await page.getByTitle(`选择项目: ${project.name}`, { exact: true }).click();
  await expect(page.locator('.breadcrumb-agent-name')).toHaveText(AGENT.display_name);
  await page.locator('.view-mode-btn').filter({ hasText: '控制台' }).click();
  await page.getByRole('button', { name: '机理 DAG', exact: true }).click();
  await expect(page.locator('.dag-node-rect')).toHaveCount(2);
  await page.locator('.dag-node-rect').nth(1).click();
  const backgrounds: string[] = [];
  const renderedColors: Array<Record<string, unknown>> = [];
  let originalDrawing: { viewerBackground: string; nodeFills: string[]; graphText: string } | undefined;
  for (const [appearance, label] of [['original', '原版工作台'], ['glass', '浅蓝玻璃'], ['emerald', '暗绿终端']]) {
    await page.getByRole('button', { name: '全局设置', exact: true }).click();
    const styles = page.getByRole('group', { name: '界面风格', exact: true });
    await styles.getByRole('button', { name: label, exact: true }).click();
    await expect(styles.getByRole('button', { name: label, exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('html')).toHaveAttribute('data-appearance', appearance);
    await page.locator('.modal').getByRole('button', { name: 'close', exact: true }).click();
    await expect(page.locator('.breadcrumb-project')).toHaveText(project.name);
    await expect(page.locator('.breadcrumb-agent-name')).toHaveText(AGENT.display_name);
    await expect(page.locator('.dag-node-label')).toHaveText(['结合物种', '分离产物']);
    await expect(page.locator('.dag-edge-hit')).toHaveCount(1);
    await expect(page.locator('.dag-sel .dag-node-label')).toHaveText('分离产物');
    await expect(page.locator('.view-mode-switcher').getByRole('button', { name: '控制台', exact: false })).toBeVisible();
    await expect(page.getByPlaceholder('新建项目名…')).toBeVisible();
    for (const name of ['机理 DAG', '计算调度', '交付产物', '审计日志']) {
      await expect(page.locator('.console-subnav-bar').getByRole('button', { name, exact: false })).toBeVisible();
    }
    await expect(page.locator('.molecule-3d-container canvas')).toBeVisible();
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    const renderedAtoms = await page.locator('.viewer-3d-canvas').evaluate((element) => {
      const canvas = element as HTMLCanvasElement;
      const pixels = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height).data;
      let green = false;
      let purple = false;
      for (let index = 0; index < pixels.length; index += 4) {
        const [red, grn, blue] = pixels.subarray(index, index + 3);
        green ||= grn > 50 && grn > red && grn > blue;
        purple ||= red > 50 && blue > red && red > grn;
      }
      return { green, purple };
    });
    expect(renderedAtoms).toEqual({ green: true, purple: true });
    await page.screenshot({ path: `/tmp/cloudra-appearance-${appearance}.png`, fullPage: true, animations: 'disabled' });
    const colors = await page.evaluate(() => {
      const style = (selector: string) => getComputedStyle(document.querySelector(selector)!);
      return {
        viewerBackground: style('.molecule-3d-container').backgroundColor,
        graphBackground: style('.dag-canvas-compact').backgroundColor,
        graphText: style('.dag-node-label').fill,
        nodeFills: [...document.querySelectorAll('.dag-node-rect')].map((node) => getComputedStyle(node).fill),
        workspaceBackground: style('.ws-group-header').backgroundColor,
        workspaceText: style('.ws-group-header').color,
        activeConsoleBackground: style('.view-mode-btn.active').backgroundColor,
        activeConsoleText: style('.view-mode-btn.active').color,
        activeDagBackground: style('.console-subnav-btn.active').backgroundColor,
        activeDagText: style('.console-subnav-btn.active').color,
        layer: style('.ws-group-header').getPropertyValue('--bg-layer'),
      };
    });
    renderedColors.push({ appearance, ...colors });
    if (appearance === 'original') originalDrawing = colors;
    else {
      expect(colors.viewerBackground).toBe(originalDrawing!.viewerBackground);
      expect(colors.graphBackground).toBe(originalDrawing!.viewerBackground);
      expect(colors.graphText).toBe(originalDrawing!.graphText);
      expect(colors.nodeFills).toEqual(originalDrawing!.nodeFills);
    }
    backgrounds.push(await page.evaluate(() => getComputedStyle(document.body).backgroundColor));
  }
  await test.info().attach('appearance-rendered-colors', { body: JSON.stringify(renderedColors, null, 2), contentType: 'application/json' });
  expect(new Set(backgrounds).size).toBe(3);
  await page.getByRole('button', { name: '计算调度', exact: false }).click();
  await expect(page.locator('.ops-dashboard-root')).toBeVisible();
  await expect(page.locator('.ops-table tbody tr').filter({ hasText: '#7' })).toContainText('running');
  await page.getByRole('button', { name: '全局设置', exact: true }).click();
  await page.getByRole('group', { name: '界面风格', exact: true }).getByRole('button', { name: '原版工作台', exact: true }).click();
  await page.locator('.modal').getByRole('button', { name: 'close', exact: true }).click();
  await expect(page.locator('.ops-dashboard-root')).toBeVisible();
  await page.getByRole('button', { name: '机理 DAG', exact: true }).click();
  await expect(page.locator('.dag-node-rect')).toHaveCount(2);
  expect(patches).toEqual([]);
});
