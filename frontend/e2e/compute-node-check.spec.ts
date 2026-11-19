import { expect, test } from '@playwright/test';
import { installApiMocks, openSpa, PROJECT_ACTIVE } from './fixtures';

test('registered nodes can be checked on demand and a broken registry stays visible', async ({ page }) => {
  await installApiMocks(page);
  const resources = { cpus: 1, max_concurrent: 1, memory_mb: 2048 };
  let broken = false;
  let probes = 0;
  await page.route('**/api/v2/compute/nodes', route => broken
    ? route.fulfill({ status: 503, json: { detail: 'invalid registry fixture' } })
    : route.fulfill({ json: [{ node_id: 'ssh1', display_name: 'SSH1', state: 'online',
      connection: 'ssh', remote: 'chem@test.invalid:22', scheduler: 'slurm',
      capacity: { registered: resources, effective: resources, os_available: {} },
      in_flight: { slots: 0, cpus: 0, memory_mb: 0 }, free: { slots: 1, cpus: 1, memory_mb: 2048 } }] }));
  await page.route('**/api/v2/compute/nodes/ssh1/check', route => {
    probes++;
    return route.fulfill({ json: { ok: false, detail: 'test SSH connection refused' } });
  });
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await page.locator('.view-mode-btn').filter({ hasText: '控制台' }).click();
  await page.getByRole('button', { name: '计算调度', exact: false }).click();
  await expect(page.getByText('SSH / rsync · Slurm CLI · 尚未检查')).toBeVisible();
  expect(probes).toBe(0);
  await page.getByRole('button', { name: '检查执行环境' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'connection refused' })).toBeVisible();
  broken = true;
  await page.getByRole('button', { name: '刷新节点' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'invalid registry fixture' })).toBeVisible();
  await expect(page.getByRole('button', { name: '检查执行环境' })).toHaveCount(0);
  expect(probes).toBe(1);
});
