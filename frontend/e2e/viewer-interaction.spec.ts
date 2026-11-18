import { expect, test, type Page } from '@playwright/test';

test.use({ hasTouch: true, launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] } });
// Real software WebGL rendering and pointer gestures exceed 30 s on CI.
test.setTimeout(60_000);

async function openViewer(page: Page) {
  await page.goto('/e2e/viewer-interaction.html');
  await expect.poll(() => page.locator('.viewer-webgl-host').evaluate(host => host.getBoundingClientRect().height)).toBeGreaterThan(250);
  await expect(page.locator('.viewer-webgl-host canvas')).toBeVisible();
  await expect.poll(() => page.evaluate(() => !!(window as any).observed.viewer?.getModel(0)?.molObj)).toBe(true);
}

async function pick(page: Page, serial: number) {
  const point = await page.evaluate(serial => {
    const viewer = (window as any).observed.viewer;
    const atom = viewer.getModel(0).selectedAtoms({ serial })[0];
    const point = viewer.modelToScreen(atom);
    return { x: point.x - window.scrollX, y: point.y - window.scrollY };
  }, serial);
  await page.mouse.click(point.x, point.y);
}

async function rememberModel(page: Page) {
  await page.evaluate(() => {
    const observed = (window as any).observed;
    observed.original = {
      model: observed.viewer.getModel(0),
      geometry: observed.viewer.getModel(0).molObj,
      view: observed.viewer.getView(),
      clears: observed.clears, animations: observed.animations, stops: observed.stops,
    };
  });
}

async function expectRetained(page: Page, animated = false) {
  await expect.poll(() => page.evaluate(animated => {
    const { viewer, original, clears, animations, stops } = (window as any).observed;
    return {
      model: viewer.getModel(0) === original.model,
      geometry: animated || viewer.getModel(0).molObj === original.geometry,
      view: viewer.getView(), clears: clears - original.clears,
      animations: animations - original.animations, stops: stops - original.stops,
    };
  }, animated)).toEqual({ model: true, geometry: true, view: await page.evaluate(() => (window as any).observed.original.view), clears: 0, animations: 0, stops: 0 });
}

test('atom selection and parent inputs keep the rendered molecule and camera', async ({ page }) => {
  await openViewer(page);
  await rememberModel(page);
  await pick(page, 1);
  await expect(page.getByLabel('选择顺序')).toHaveText('1');
  await expectRetained(page);
  await pick(page, 2);
  await expect(page.getByLabel('选择顺序')).toHaveText('1,2');
  await expectRetained(page);
  await page.getByLabel('标题').fill('Edited without rebuilding');
  await page.getByRole('button', { name: '高亮坐标', exact: true }).click();
  await page.getByRole('button', { name: '编号', exact: true }).click();
  await page.getByRole('button', { name: '外观', exact: true }).click();
  await expectRetained(page);
  expect(await page.evaluate(() => (window as any).observed.backgrounds)).toBe(0);
});

test('only a blank primary mouse tap clears the selected atoms', async ({ page }) => {
  await openViewer(page);
  await pick(page, 1);
  await expect(page.getByLabel('选择顺序')).toHaveText('1');
  const canvas = page.locator('.viewer-webgl-host canvas');
  const bounds = (await canvas.boundingBox())!;
  const x = bounds.x + 15, y = bounds.y + 15;
  // 3Dmol uses left to rotate, middle to pan, and right to zoom.
  for (const button of ['left', 'middle', 'right'] as const) {
    await page.mouse.move(x, y);
    await page.mouse.down({ button });
    await page.mouse.move(x + 60, y + 35, { steps: 4 });
    await page.mouse.move(x, y, { steps: 4 });
    await page.mouse.up({ button });
    await expect(page.getByLabel('选择顺序')).toHaveText('1');
  }
  await page.mouse.wheel(0, 50);
  await page.getByRole('button', { name: 'XYZ', exact: true }).click();
  await expect(page.getByLabel('选择顺序')).toHaveText('1');
  await page.getByRole('button', { name: 'XYZ', exact: true }).click();
  await page.touchscreen.tap(x, y);
  await expect(page.getByLabel('选择顺序')).toHaveText('1');
  expect(await page.evaluate(() => (window as any).observed.backgrounds)).toBe(0);
  await page.mouse.click(x, y);
  await expect(page.getByLabel('选择顺序')).toHaveText('');
  expect(await page.evaluate(() => (window as any).observed.backgrounds)).toBe(1);
});

test('selection overlays follow vibration frames without restarting playback', async ({ page }) => {
  await openViewer(page);
  await page.getByRole('button', { name: '振动模式', exact: true }).click();
  await pick(page, 1);
  await expect(page.getByLabel('选择顺序')).toHaveText('1');
  await page.getByRole('button', { name: '振动播放', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).observed.viewer.isAnimated())).toBe(true);
  await rememberModel(page);
  await pick(page, 2);
  await expect(page.getByLabel('选择顺序')).toHaveText('1,2');
  await page.getByLabel('标题').fill('Playing');
  await page.getByRole('button', { name: '高亮坐标', exact: true }).click();
  await expectRetained(page, true);
  await expect.poll(() => page.evaluate(() => {
    const viewer = (window as any).observed.viewer;
    const model = viewer.getModel(0), selection = viewer.getModel(1);
    // getModel falls back to the last model for an absent ID, so require a
    // distinct overlay before comparing positions.
    if (!selection || selection === model) return false;
    const main = model.selectedAtoms({ serial: 1 })[0];
    const overlay = selection.selectedAtoms({ serial: 1 })[0];
    return !!overlay && main.x === overlay.x && main.y === overlay.y && main.z === overlay.z;
  })).toBe(true);
});

test('enabling view preservation without changing geometry keeps the first subsequent frame in place', async ({ page }) => {
  await openViewer(page);
  const bounds = (await page.locator('.viewer-webgl-host canvas').boundingBox())!;
  const initialView = await page.evaluate(() => (window as any).observed.viewer.getView());
  await page.mouse.move(bounds.x + 15, bounds.y + 15);
  await page.mouse.wheel(0, 180);
  await expect.poll(() => page.evaluate(() => (window as any).observed.viewer.getView())).not.toEqual(initialView);
  await page.mouse.down({ button: 'middle' });
  await page.mouse.move(bounds.x + 50, bounds.y + 40, { steps: 4 });
  await page.mouse.up({ button: 'middle' });
  await expect.poll(() => page.evaluate(() => (window as any).observed.viewer.getView().slice(0, 3))).not.toEqual(initialView.slice(0, 3));
  await rememberModel(page);
  await page.getByRole('button', { name: '保持视角', exact: true }).click();
  await expectRetained(page);
  await page.getByRole('button', { name: '下一帧', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).observed.viewer.getModel(0).selectedAtoms({ serial: 1 })[0].x)).toBe(-1);
  await expect.poll(() => page.evaluate(() => (window as any).observed.viewer.getView())).toEqual(await page.evaluate(() => (window as any).observed.original.view));
});

test('drawing on the blank workbench anchors the atom at the click and the next click grows a single bond', async ({page}) => {
  await page.route('**/workbench/fragments', route => route.fulfill({json:{fragments:[]}}));
  const edits: any[] = [];
  const atoms: {index:number;symbol:string;x:number;y:number;z:number}[] = [];
  await page.route('**/workbench/edit', route => {
    const edit = route.request().postDataJSON();
    edits.push(edit);
    const [x,y,z] = edit.position ?? [atoms[0].x + 1.4, atoms[0].y, atoms[0].z];
    atoms.push({index:atoms.length+1,symbol:edit.element ?? 'O',x,y,z});
    return route.fulfill({json:{atoms,bonds:atoms.length>1?[{atom1:1,atom2:2,order:1}]:[],molecule:'draft'+atoms.length,xyz:''}});
  });
  await page.goto('/e2e/workbench-builder.html');
  const canvas = page.locator('.viewer-webgl-host canvas');
  await expect(canvas).toBeVisible();
  const bounds = (await canvas.boundingBox())!;
  const x = bounds.x + 0.6*bounds.width, y = bounds.y + 0.4*bounds.height;
  await page.mouse.click(x,y);
  await expect(page.getByRole('button',{name:'C1',exact:true})).toBeVisible();
  expect(edits[0]).toMatchObject({action:'add_atom',element:'C',atoms:[],position:[expect.any(Number),expect.any(Number),expect.any(Number)]});
  await page.getByLabel('添加内容').selectOption('[*]O');
  // Scrolling to the palette can move the canvas in a small viewport.
  await canvas.scrollIntoViewIfNeeded();
  const next = (await canvas.boundingBox())!;
  await page.mouse.click(next.x+0.6*next.width,next.y+0.4*next.height);
  await expect(page.getByRole('button',{name:'O2',exact:true})).toBeVisible();
  expect(edits[1]).toMatchObject({action:'add_group',smiles:'[*]O',atoms:[1],molecule:'draft1'});
  await page.getByRole('button',{name:'选择模式'}).click();
  await page.getByRole('button',{name:'O2',exact:true}).click();
  await expect(page.getByRole('button',{name:'替换元素'})).toBeEnabled();
  expect(edits).toHaveLength(2);
});
