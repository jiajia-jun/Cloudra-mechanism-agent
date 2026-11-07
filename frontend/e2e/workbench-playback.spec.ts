import { expect, test, type Page } from '@playwright/test';
import type { DocumentView, GeometryView } from '../src/workbenchTypes';
import { PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

// These tests need real WebGL; keep software rendering local to this file.
test.use({ launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] } });
test.describe.configure({ mode: 'default' });

const geometries: Record<number, GeometryView> = Object.fromEntries([0, 1, 3].map((index) => {
  const x = 1 + index * 0.1;
  const xyz = `2\nFrame ${index}\nH 0 0 0\nH ${x} 0 0`;
  return [index, { molecule: xyz, xyz, atoms: [{ index: 1, symbol: 'H', x: 0, y: 0, z: 0 }, { index: 2, symbol: 'H', x, y: 0, z: 0 }], bonds: [{ atom1: 1, atom2: 2, order: 1 }], graph_status: 'declared' }];
}));
const document: DocumentView = {
  document_id: 'trajectory', title: 'Optimization trajectory', source_path: '/tmp/trajectory.log', task_type: 'opt',
  frames: [0, 1, 2, 3].map((index) => ({ index, step: index, has_geometry: index !== 2, energy_hartree: -10 - index / 10 })),
  selected_frame: 0, geometry: geometries[0], modes: [], settings: {}, warnings: [],
};

async function openTrajectory(page: Page, holdFirstFrame = false) {
  await installApiMocks(page, { jobs: [] });
  const requests: number[] = [];
  let release = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route('**/workbench/open', (route) => route.fulfill({ json: document }));
  await page.route('**/workbench/documents/trajectory/frames/*', async (route) => {
    const index = Number(new URL(route.request().url()).pathname.split('/').pop());
    requests.push(index);
    await Promise.all([new Promise((resolve) => setTimeout(resolve, 500)), holdFirstFrame && index === 1 ? gate : Promise.resolve()]);
    await route.fulfill({ status: geometries[index] ? 200 : 422, json: geometries[index] ?? { detail: 'This sampling point has no geometry' } });
  });
  await openSpa(page);
  await page.getByTitle(`选择项目: ${PROJECT_ACTIVE.name}`, { exact: true }).click();
  await page.getByRole('button', { name: '分子工作台', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '分子工作台' });
  await dialog.getByLabel('来源类型').selectOption('path');
  await dialog.getByLabel('结构来源').fill('trajectory.log');
  await dialog.getByRole('button', { name: '新建／打开', exact: true }).click();
  await expect(dialog.locator('.wb-viewer canvas').first()).toBeVisible();
  return { dialog, requests, release };
}

test('manual frame changes retain the canvas during a slow fetch and reuse loaded coordinates', async ({ page }) => {
  const { dialog, requests, release } = await openTrajectory(page, true);
  const canvas = await dialog.locator('.wb-viewer canvas').first().elementHandle();
  const slider = dialog.getByRole('slider', { name: '来源帧' });
  await slider.press('ArrowRight');
  await expect.poll(() => requests).toEqual([1]);
  try {
    expect(await canvas!.evaluate((node) => !!node.closest('.wb-viewer'))).toBe(true);
    await expect(dialog.locator('.wb-empty')).toHaveCount(0);
  } finally { release(); }
  await expect(slider).toBeEnabled();
  await expect(slider).toHaveValue('1');
  await slider.press('ArrowLeft');
  await expect(slider).toHaveValue('0');
  await expect(slider).toBeEnabled();
  await slider.press('ArrowRight');
  await expect(slider).toHaveValue('1');
  await expect(slider).toBeEnabled();
  expect(requests).toEqual([1]);
  expect(await canvas!.evaluate((node) => node === document.querySelector('.wb-viewer canvas'))).toBe(true);

  await slider.press('ArrowRight');
  await expect(slider).toHaveValue('2');
  await expect(dialog.locator('.wb-empty')).toBeVisible();
  await expect(dialog.getByRole('status')).toContainText('未输出几何');
  expect(requests).toEqual([1]);
});

test('playback prepares coordinates once then loops locally without blank frames or canvas replacement', async ({ page }) => {
  // Check playback ticks independently of the software WebGL rendering speed.
  await page.clock.install();
  const { dialog, requests } = await openTrajectory(page);
  await page.clock.pauseAt(Date.now() + 1000);
  await dialog.getByRole('button', { name: '播放各帧', exact: true }).click();
  await expect.poll(() => requests.includes(1) && requests.includes(3)).toBe(true);
  await expect(dialog.getByRole('slider', { name: '来源帧' })).toBeEnabled();
  const sample = async (playing = true) => {
    if (playing) await expect(dialog.getByRole('button', { name: '暂停帧播放', exact: true })).toBeEnabled();
    const slider = dialog.getByRole('slider', { name: '来源帧' });
    let expectedFrame = await slider.inputValue();
    const nextFrame: Record<string, string> = { '0': '1', '1': '3', '3': '0' };
    const observation = await page.evaluateHandle(() => {
      const canvas = document.querySelector('.wb-viewer canvas');
      const slider = document.querySelector<HTMLInputElement>('input[aria-label="来源帧"]')!;
      const sample = { values: [slider.value], intact: !!canvas };
      const observer = new MutationObserver(() => {
        sample.intact &&= canvas === document.querySelector('.wb-viewer canvas');
        if (sample.values.at(-1) !== slider.value) sample.values.push(slider.value);
      });
      observer.observe(document.querySelector('.molecular-workbench')!, { childList: true, attributes: true, attributeFilter: ['value'], subtree: true });
      return { sample, observer };
    });
    for (let tick = 0; tick < 6; tick++) {
      if (playing) expectedFrame = nextFrame[expectedFrame];
      await page.clock.runFor(100);
      await expect(slider).toHaveValue(expectedFrame);
    }
    const result = await observation.evaluate(({ sample, observer }) => { observer.disconnect(); return sample; });
    await observation.dispose();
    return result;
  };
  const firstLoop = await sample();
  expect(firstLoop.intact).toBe(true);
  expect(firstLoop.values.length).toBeGreaterThanOrEqual(7);
  expect(new Set(firstLoop.values)).toEqual(new Set(['0', '1', '3']));
  expect(firstLoop.values.slice(0, 3)).toEqual(firstLoop.values.slice(3, 6));
  expect(requests.slice().sort()).toEqual([1, 3]);

  await dialog.getByRole('button', { name: '暂停帧播放', exact: true }).click();
  const paused = await sample(false);
  expect(paused.values).toHaveLength(1);
  await dialog.getByRole('button', { name: '播放各帧', exact: true }).click();
  const resumed = await sample();
  expect(resumed.intact).toBe(true);
  expect(resumed.values.length).toBeGreaterThanOrEqual(7);
  expect(new Set(resumed.values)).toEqual(new Set(['0', '1', '3']));
  expect(requests.slice().sort()).toEqual([1, 3]);
});

test('reopening a source invalidates frame coordinates even when its document id stays the same', async ({ page }) => {
  const { dialog, requests } = await openTrajectory(page);
  const slider = dialog.getByRole('slider', { name: '来源帧' });
  await slider.press('ArrowRight');
  await expect(slider).toBeEnabled();
  await expect(slider).toHaveValue('1');
  expect(requests).toEqual([1]);
  await dialog.getByRole('button', { name: '新建／打开', exact: true }).click();
  await dialog.getByRole('button', { name: '继续并放弃修改', exact: true }).click();
  await expect(slider).toHaveValue('0');
  await expect(slider).toBeEnabled();
  await slider.press('ArrowRight');
  await expect(slider).toBeEnabled();
  await expect(slider).toHaveValue('1');
  expect(requests).toEqual([1, 1]);
});
