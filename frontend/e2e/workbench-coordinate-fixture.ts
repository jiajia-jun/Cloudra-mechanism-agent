import { expect, type Page } from '@playwright/test';
import type { DocumentView, GeometryView } from '../src/workbenchTypes';

export const geometry: GeometryView = {
  molecule: 'four-atoms', xyz: '', graph_status: 'declared',
  atoms: [
    { index: 1, symbol: 'C', x: 1, y: 0, z: 0 },
    { index: 2, symbol: 'C', x: 0, y: 0, z: 0 },
    { index: 3, symbol: 'C', x: 0, y: 1, z: 0 },
    { index: 4, symbol: 'H', x: 0, y: 1, z: 1 },
  ],
  bonds: [1, 2, 3].map(atom1 => ({ atom1, atom2: atom1 + 1, order: 1 })),
};
const document: DocumentView = { document_id: 'edit', title: 'Editable molecule', geometry, frames: [{ index: 0, step: 0 }], selected_frame: 0, modes: [], settings: {}, warnings: [] };

export async function openCoordinateWorkbench(page: Page, capture = false) {
  await page.route('**/workbench/fragments', route => route.fulfill({ json: { fragments: [] } }));
  await page.route('**/workbench/open', route => route.fulfill({ json: document }));
  const edits: unknown[] = [];
  await page.route('**/workbench/edit', route => {
    edits.push(route.request().postDataJSON());
    return route.fulfill({ json: { ...geometry, molecule: 'adjusted' } });
  });
  await page.goto('/e2e/workbench-builder.html' + (capture ? '?capture' : ''));
  const workbench = page.getByRole('dialog', { name: '分子工作台', exact: true });
  await workbench.getByLabel('结构来源').fill('CCCC');
  await workbench.getByRole('button', { name: '新建／打开', exact: true }).click();
  const atoms = workbench.getByLabel('原子列表', { exact: true });
  await expect(atoms.getByRole('button', { name: 'C1', exact: true })).toBeVisible();
  return { workbench, atoms, edits };
}
