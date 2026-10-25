import { expect, test } from '@playwright/test';
import { RUNTIME_CONFIG, installApiMocks, openModelSettings, openSpa } from './fixtures';

async function mockSettings(page: import('@playwright/test').Page) {
  await installApiMocks(page);
  const slot = { model: 'existing-model', url: 'https://llm.example/v1', key_set: true, context_window: 200000, timeout: 300 };
  let selection = {
    strategy: 'llm', semantic_backend: 'jev',
    jev: { endpoint: '', model: '', key_set: false, min_probability: null as number | null, max_tools: null as number | null },
    reranker: { endpoint: '', model: '', key_set: false, min_score: null as number | null, max_tools: null as number | null },
  };
  const saved: Array<Record<string, unknown>> = [];
  let reject = false;
  await page.route('**/api/v2/runtime/**', async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (path.endsWith('/providers')) return route.fulfill({ json: [] });
    if (path.endsWith('/tool-document-loading')) {
      const body = req.postDataJSON();
      saved.push(body);
      if (reject) return route.fulfill({ status: 422, json: { detail: 'Invalid selection boundary' } });
      const next = { ...selection, ...body };
      for (const backend of ['jev', 'reranker'] as const) {
        const patch = body[backend];
        if (!patch) { next[backend] = selection[backend]; continue; }
        const { key, ...publicPatch } = patch;
        next[backend] = { ...selection[backend], ...publicPatch,
          key_set: key === undefined ? selection[backend].key_set : Boolean(key) };
      }
      selection = next;
    } else if (!path.endsWith('/config')) return route.fallback();
    return route.fulfill({ json: { ...RUNTIME_CONFIG, coordinator: slot, follower: slot, tool_document_loading: selection } });
  });
  await openSpa(page);
  await openModelSettings(page);
  return { saved, reject: () => { reject = true; } };
}

test('default uses current model; semantic settings keep credentials write-only and restore after refresh', async ({ page }) => {
  const state = await mockSettings(page);
  let panel = page.getByRole('region', { name: '工具说明加载' });
  await expect(panel.getByLabel('选择方式')).toHaveValue('llm');
  await expect(panel.locator('input[type=password]')).toHaveCount(0);
  await panel.getByRole('button', { name: '保存工具说明设置', exact: true }).click();
  await expect.poll(() => state.saved.length).toBe(1);
  expect(state.saved[0]).toEqual({ strategy: 'llm', semantic_backend: 'jev' });
  await panel.getByLabel('选择方式').selectOption('semantic');
  await panel.getByLabel('服务地址').fill('https://jev.example/api');
  await panel.getByLabel('模型名称').fill('jev-model');
  await panel.getByLabel('最低概率').fill('0.6');
  await panel.getByLabel('API 凭据').fill('SECRET_NEW_KEY');
  await panel.getByRole('button', { name: '保存工具说明设置', exact: true }).click();
  await expect.poll(() => state.saved.length).toBe(2);
  await expect(panel.getByLabel('API 凭据')).toHaveValue('');
  await panel.getByLabel('最多预加载工具数').fill('4');
  await panel.getByRole('button', { name: '保存工具说明设置', exact: true }).click();
  await expect.poll(() => state.saved.length).toBe(3);
  expect(state.saved[2]).toMatchObject({ jev: { max_tools: 4 } });
  expect((state.saved[2].jev as Record<string, unknown>).key).toBeUndefined();
  await page.reload();
  await openModelSettings(page);
  panel = page.getByRole('region', { name: '工具说明加载' });
  await expect(panel.getByLabel('选择方式')).toHaveValue('semantic');
  await expect(panel.getByLabel('最低概率')).toHaveValue('0.6');
  await expect(panel.getByLabel('API 凭据')).toHaveValue('');
  await panel.getByRole('button', { name: '清除凭据并使用现有模型' }).click();
  await expect.poll(() => state.saved.length).toBe(4);
  expect(state.saved[3]).toMatchObject({ strategy: 'llm', jev: { key: '' } });
  await expect(panel.getByLabel('选择方式')).toHaveValue('llm');
});

test('reranker has an independent score boundary and reports rejected saves', async ({ page }) => {
  const state = await mockSettings(page);
  const panel = page.getByRole('region', { name: '工具说明加载' });
  await panel.getByLabel('选择方式').selectOption('semantic');
  await panel.getByLabel('语义服务').selectOption('reranker');
  await expect(panel.getByLabel('最低概率')).toHaveCount(0);
  await panel.getByLabel('服务地址').fill('http://127.0.0.1:9997/v1/rerank');
  await panel.getByLabel('模型名称').fill('bge-reranker-v2-m3');
  await panel.getByLabel('最低相关分数').fill('-2');
  await panel.getByRole('button', { name: '保存工具说明设置', exact: true }).click();
  await expect.poll(() => state.saved.length).toBe(1);
  expect(state.saved[0]).toMatchObject({ semantic_backend: 'reranker', reranker: { min_score: -2 } });
  expect(state.saved[0].jev).toBeUndefined();
  state.reject();
  await panel.getByLabel('最低相关分数').fill('3');
  await panel.getByRole('button', { name: '保存工具说明设置', exact: true }).click();
  await expect(panel.getByRole('alert')).toContainText('Invalid selection boundary');
});
