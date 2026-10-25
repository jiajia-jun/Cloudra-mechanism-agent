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


async function sampleMolecule(page: Page) {
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  return page.locator('.viewer-3d-canvas').evaluate((element) => {
    const canvas = element as HTMLCanvasElement;
    const pixels = canvas.getContext('2d')!.getImageData(0, 0, canvas.width, canvas.height).data;
    const green = { count: 0, x: 0, y: 0 };
    const purple = { count: 0, x: 0, y: 0 };
    for (let index = 0; index < pixels.length; index += 4) {
      const red = pixels[index], grn = pixels[index + 1], blue = pixels[index + 2];
      const point = grn > 80 && grn > red * 1.35 && grn > blue * 1.35 ? green
        : blue > 90 && red > 45 && blue > grn * 1.5 && red > grn * 1.15 ? purple : null;
      if (point) { point.count++; point.x += (index / 4) % canvas.width; point.y += Math.floor(index / 4 / canvas.width); }
    }
    return {
      green: green.count > 0, purple: purple.count > 0,
      angle: Math.atan2(green.y / green.count - purple.y / purple.count, green.x / green.count - purple.x / purple.count),
      background: Array.from(pixels.slice((canvas.width * 2 + 2) * 4, (canvas.width * 2 + 2) * 4 + 3)),
    };
  });
}

test('appearance controls apply immediately and preserve the saved choice after reload', async ({ page }) => {
  await installApiMocks(page, { jobs: [] });
  const patches = await mockAppearanceSettings(page);
  await openSpa(page);
  await page.getByRole('button', { name: '全局设置', exact: true }).click();
  const styles = page.getByRole('group', { name: '界面风格', exact: true });
  await expect(styles).toBeVisible({ timeout: 1500 });
  await expect(styles.getByRole('button', { name: '现代主义', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await styles.getByRole('button', { name: 'Acid', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'acid');
  expect(await page.evaluate(() => localStorage.getItem('cloudra.appearance'))).toBe('acid');
  await page.screenshot({ path: '/tmp/cloudra-appearance-settings.png', fullPage: true, animations: 'disabled' });
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'acid');
  await page.getByRole('button', { name: '全局设置', exact: true }).click();
  await expect(styles.getByRole('button', { name: 'Acid', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await styles.getByRole('button', { name: '现代主义', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'modernism');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-appearance', 'modernism');
  expect(await page.evaluate(() => localStorage.getItem('cloudra.appearance'))).toBe('modernism');
  expect(patches).toEqual([]);
});

test('all appearances preserve the selected project, agent, DAG and compute workbench', async ({ page }) => {
  const project = { ...PROJECT_ACTIVE, name: '机理研究工作台', settings: { orchestration_mode: 'dag_guided', defaults: {} } };
  await installApiMocks(page, { projects: [project], jobs: [JOB] });
  const patches = await mockAppearanceSettings(page);
  await page.route('**/api/v2/chem/render-smiles?*', (route) => {
    const params = new URL(route.request().url()).searchParams;
    const smiles = params.get('smiles') ?? '';
    const ink = params.get('theme') === 'light' ? '#1f2937' : '#cbd5e1';
    return route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="180" height="40"><text x="90" y="26" text-anchor="middle" fill="${ink}" font-size="18">${smiles}</text></svg>` });
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
  await page.getByRole('button', { name: '填充', exact: true }).click();
  const originalCamera = await sampleMolecule(page);
  const canvasBox = (await page.locator('.viewer-3d-canvas').boundingBox())!;
  await page.mouse.move(canvasBox.x + canvasBox.width / 2, canvasBox.y + canvasBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(canvasBox.x + canvasBox.width / 2 + 60, canvasBox.y + canvasBox.height / 2 + 35, { steps: 4 });
  await page.mouse.up();
  const cameraAngle = (await sampleMolecule(page)).angle;
  expect(Math.abs(cameraAngle - originalCamera.angle)).toBeGreaterThan(0.1);
  const canvasBackgrounds: string[] = [];
  const backgrounds: string[] = [];
  const renderedColors: Array<Record<string, unknown>> = [];

  for (const [appearance, label, svgTheme] of [['modernism', '现代主义', 'dark'], ['punk', '朋克', 'dark'], ['acid', 'Acid', 'light']]) {
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
    const rendered = await sampleMolecule(page);
    expect(rendered.green).toBe(true);
    expect(rendered.purple).toBe(true);
    if (appearance === 'acid') expect(Math.min(...rendered.background)).toBeGreaterThan(180);
    else expect(Math.max(...rendered.background)).toBeLessThan(100);
    expect(Math.abs(rendered.angle - cameraAngle)).toBeLessThan(0.08);
    expect(await page.getByRole('button', { name: '填充', exact: true }).evaluate((element) => element.classList.contains('active'))).toBe(true);
    const imageThemes = await page.locator('.dag-canvas-compact image').evaluateAll((images) => images.map((image) => new URL(image.getAttribute('href')!, location.origin).searchParams.get('theme')));
    expect([...new Set(imageThemes)]).toEqual([svgTheme]);
    canvasBackgrounds.push(rendered.background.join(','));
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
    backgrounds.push(await page.evaluate(() => getComputedStyle(document.body).backgroundColor));
  }
  await test.info().attach('appearance-rendered-colors', { body: JSON.stringify(renderedColors, null, 2), contentType: 'application/json' });
  expect(new Set(backgrounds).size).toBe(3);
  expect(new Set(canvasBackgrounds).size).toBe(3);
  await page.getByRole('button', { name: '计算调度', exact: false }).click();
  await expect(page.locator('.ops-dashboard-root')).toBeVisible();
  await expect(page.locator('.ops-table tbody tr').filter({ hasText: '#7' })).toContainText('running');
  await page.getByRole('button', { name: '全局设置', exact: true }).click();
  await page.getByRole('group', { name: '界面风格', exact: true }).getByRole('button', { name: '现代主义', exact: true }).click();
  await page.locator('.modal').getByRole('button', { name: 'close', exact: true }).click();
  await expect(page.locator('.ops-dashboard-root')).toBeVisible();
  await page.getByRole('button', { name: '机理 DAG', exact: true }).click();
  await expect(page.locator('.dag-node-rect')).toHaveCount(2);
  expect(patches).toEqual([]);
});

test('themes change message, tool and composer forms while preserving their content and input', async ({ page }) => {
  await installApiMocks(page, { jobs: [] });
  const patches = await mockAppearanceSettings(page);
  const envelope = (seq: number, type: string, data: object) => ({
    event_id: `appearance-event-${seq}`, type, stream: 'agent',
    project_id: PROJECT_ACTIVE.id, session_id: AGENT.id, run_id: null,
    seq, session_seq: seq, created_at: '2026-10-25T00:00:00Z', data,
  });
  const events = [
    envelope(1, 'agent.message_injected', { sender: 'user', content: '请核对本轮结构与计算记录。' }),
    envelope(2, 'tool.started', { tool_name: 'log_parser', tool_call_id: 'appearance-call', arguments_summary: { path: '/tmp/example.log' } }),
    envelope(3, 'tool.finished', { tool_name: 'log_parser', tool_call_id: 'appearance-call', status: 'completed', is_success: true, result_summary: '示例结构记录已经读入。', duration_ms: 18 }),
    envelope(4, 'agent.message_emitted', { sender: 'coordinator', content: '继续在DAG和计算工作台中查看证据。' }),
  ];
  await page.route('**/api/v2/agents/*/events?*', (route) => route.fulfill({ json: events }));
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await expect(page.locator('.msg.user .msg-bubble')).toHaveText('请核对本轮结构与计算记录。');
  await page.locator('.tool-row').filter({ hasText: 'log_parser' }).click();
  await expect(page.locator('.tool-detail')).toBeVisible();
  await page.getByTestId('composer-input').fill('保留这段工作台输入');
  const profiles: Record<string, Record<string, unknown>> = {};
  for (const [appearance, label] of [['modernism', '现代主义'], ['punk', '朋克'], ['acid', 'Acid']]) {
    await page.getByRole('button', { name: '全局设置', exact: true }).click();
    await page.getByRole('group', { name: '界面风格', exact: true }).getByRole('button', { name: label, exact: true }).click();
    await page.locator('.modal').getByRole('button', { name: 'close', exact: true }).click();
    await expect(page.getByTestId('composer-input')).toHaveValue('保留这段工作台输入');
    await expect(page.locator('.msg.user .msg-bubble')).toHaveText('请核对本轮结构与计算记录。');
    await expect(page.locator('.tool-detail')).toContainText('示例结构记录已经读入。');
    await expect(page.locator('.breadcrumb-agent-name')).toHaveText(AGENT.display_name);
    await page.screenshot({ path: `/tmp/cloudra-surfaces-${appearance}.png`, fullPage: true, animations: 'disabled' });
    profiles[appearance] = await page.evaluate(() => {
      const form = (selector: string) => {
        const style = getComputedStyle(document.querySelector(selector)!);
        return {
          corners: [style.borderTopLeftRadius, style.borderTopRightRadius, style.borderBottomRightRadius, style.borderBottomLeftRadius],
          padding: [style.paddingTop, style.paddingRight, style.paddingBottom, style.paddingLeft],
          borders: [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth],
          borderStyles: [style.borderTopStyle, style.borderRightStyle, style.borderBottomStyle, style.borderLeftStyle],
          raised: style.boxShadow !== 'none',
        };
      };
      return { message: form('.msg.user .msg-bubble'), tool: form('.tool-row'), detail: form('.tool-detail'), composer: form('.composer') };
    });
  }
  for (const surface of ['message', 'tool', 'detail', 'composer']) {
    expect(profiles.punk[surface], `punk ${surface} form`).not.toEqual(profiles.modernism[surface]);
    expect(profiles.acid[surface], `acid ${surface} form`).not.toEqual(profiles.modernism[surface]);
    expect(profiles.acid[surface], `acid and punk ${surface} forms`).not.toEqual(profiles.punk[surface]);
  }
  expect(patches).toEqual([]);
});
