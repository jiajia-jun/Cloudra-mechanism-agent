import { expect, test } from '@playwright/test';
import { geometry, openCoordinateWorkbench } from './workbench-coordinate-fixture';

test.use({launchOptions:{args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']}});
test.setTimeout(90_000);

test('canvas group picking preserves the coordinate, target and scan range through cancellation and preview', async ({page}) => {
  const {workbench, atoms} = await openCoordinateWorkbench(page, true);
  const edits: unknown[] = [];
  await page.route('**/workbench/edit', route => {
    edits.push(route.request().postDataJSON());
    return route.fulfill({json:{...geometry, changes:{moved_atoms:[2,4],deleted_atoms:[],deleted_atom_ids:[],index_map:{}}}});
  });
  await atoms.getByRole('button',{name:'C1',exact:true}).click();
  await atoms.getByRole('button',{name:'C2',exact:true}).click();
  await workbench.getByRole('button',{name:'编辑距离',exact:true}).click();
  const editor = page.getByRole('dialog',{name:'调整距离',exact:true});
  await editor.getByLabel('内坐标目标值').fill('1.625');
  await editor.getByText('冻结与扫描',{exact:true}).click();
  await editor.getByLabel('终点',{exact:true}).fill('2.5');
  await editor.getByRole('button',{name:'画布选择移动原子'}).click();
  const picker = workbench.getByRole('region',{name:'画布选组'});
  await expect(editor).toBeHidden();
  await expect(picker).toContainText('坐标定义：1 → 2');
  await expect(picker.getByRole('button',{name:'使用所选原子'})).toBeDisabled();
  const canvas = workbench.locator('.viewer-webgl-host canvas');
  await expect(canvas).toBeVisible();
  await canvas.scrollIntoViewIfNeeded();
  const point = await page.evaluate(() => {
    const viewer = (window as any).testViewer;
    const {x,y} = viewer.modelToScreen(viewer.getModel(0).selectedAtoms({serial:2})[0]);
    return {x:x-scrollX, y:y-scrollY};
  });
  await page.mouse.click(point.x,point.y);
  await expect(atoms.getByRole('button',{name:'C2',exact:true})).toHaveAttribute('aria-pressed','true');
  await atoms.getByRole('button',{name:'H4',exact:true}).click();
  await picker.getByRole('button',{name:'使用所选原子'}).click();
  await expect(editor.getByLabel('内坐标目标值')).toHaveValue('1.625');
  await expect(editor.getByLabel('终点',{exact:true})).toHaveValue('2.5');
  await editor.getByRole('button',{name:'画布选择移动原子'}).click();
  await atoms.getByRole('button',{name:'C3',exact:true}).click();
  await picker.getByRole('button',{name:'取消选组'}).click();
  await editor.getByRole('button',{name:'预览结构调整'}).click();
  await expect(workbench.locator('.wb-preview')).toContainText('移动组（2）：2、4');
  expect(edits).toEqual([{action:'coordinate',molecule:'four-atoms',atoms:[1,2],fixed_side:'first',value:1.625,moving_atoms:[2,4]}]);
});
