import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { parseSync, transformSync } from 'rolldown/utils';
import * as annotations from './workbenchAnnotations.ts';
import * as helpers from './molecularWorkbench.ts';
import type { DocumentView, GeometryView, WorkbenchShot } from './workbenchTypes.ts';

// Exercise the real component's callbacks and Viewer/Curve inputs without WebGL
// or a running API. Keep hooks local to this component, as App.actions.test.ts
// does for application callbacks; no copies of the production transitions.
const source = readFileSync(new URL('./MolecularWorkbench.tsx', import.meta.url), 'utf8');
const program = parseSync('MolecularWorkbench.tsx', source, { lang: 'tsx' }).program;
const body = program.body.filter(node => node.type !== 'ImportDeclaration')
  .map(node => node.type === 'ExportNamedDeclaration' ? node.declaration : node)
  .filter(Boolean).map(node => source.slice(node!.start, node!.end)).join('\n');
const compiled = transformSync('Workbench.tsx', body, { lang: 'tsx', jsx: { runtime: 'classic' } }).code;

const geometry: GeometryView = {
  molecule: 'original', xyz: '2\noriginal\nH 0 0 0\nH 1 0 0',
  atoms: [{ index: 1, symbol: 'H', x: 0, y: 0, z: 0 }, { index: 2, symbol: 'H', x: 1, y: 0, z: 0 }],
  bonds: [{ atom1: 1, atom2: 2, order: 1 }],
};
const edited: GeometryView = { ...geometry, molecule: 'edited', atoms: geometry.atoms.map(atom => ({ ...atom, x: atom.x * 1.5 })) };
const document: DocumentView = {
  document_id: 'first', title: 'First', geometry, selected_frame: 0, settings: {}, warnings: [],
  frames: [
    { index: 0, step: 0, energy_hartree: -1, scan_coordinates: [100, 200] },
    { index: 1, step: 1, energy_hartree: -2, scan_coordinates: [100, 201] },
  ],
  modes: [{ frequency_cm: 123, displacements: [[1, 0, 0], [-1, 0, 0]] }],
  modes_reference_geometry: { ...geometry, molecule: 'mode-reference' },
};
const nextDocument: DocumentView = { ...document, document_id: 'second', title: 'Second', modes: [], frames: [
  { index: 0, step: 0, energy_hartree: -3, scan_coordinates: [300] },
  { index: 1, step: 1, energy_hartree: -4, scan_coordinates: [301] },
] };

interface Element { type: string | ((...args: any[]) => unknown); props: Record<string, any> }
const text = (value: any): string => typeof value === 'string' || typeof value === 'number' ? String(value)
  : Array.isArray(value) ? value.map(text).join('') : value?.props ? text(value.props.children) : '';
function descendants(value: any, predicate: (node: Element) => boolean, found: Element[] = []): Element[] {
  if (Array.isArray(value)) value.forEach(node => descendants(node, predicate, found));
  else if (value?.props) {
    if (predicate(value)) found.push(value);
    descendants(value.props.children, predicate, found);
  }
  return found;
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function mount(onLaunch: (shot: WorkbenchShot) => Promise<void> = async () => {}) {
  const slots: any[] = [];
  let cursor = 0, dirty = true;
  let effects: (() => void)[] = [];
  let tree: Element;
  const errors: string[] = [];
  const calls = { closed: 0, saves: 0 };
  const api = {
    open: async (..._args: any[]) => document,
    frame: async (..._args: any[]) => edited,
    fragments: async (..._args: any[]) => ({ fragments: [] as any[] }),
    edit: async (..._args: any[]) => edited,
    save: async () => { calls.saves++; return { geometry: edited, path: 'saved.json', message: '已保存' }; },
    previewFragment: async (..._args: any[]) => geometry,
  };
  const props = { project: { id: 'project', name: 'Project' }, source: { path: '/first' },
    onClose() { calls.closed++; }, onSaved() {}, onLaunch, onError: (error: string) => errors.push(error) };
  const component = vm.runInNewContext(`${compiled}\nMolecularWorkbench`, {
    ...helpers, ...annotations, workbenchApi: api, useMemo: (compute: () => unknown) => compute(),
    React: { createElement: (type: Element['type'], props: object, ...children: unknown[]) => ({ type, props: { ...props, children } }) },
    Molecule3DViewer: 'Molecule3DViewer', MoleculeBuilder: 'MoleculeBuilder', WorkbenchCoordinateDialog: 'WorkbenchCoordinateDialog',
    useState(initial: any) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { value: typeof initial === 'function' ? initial() : initial };
      return [slots[index].value, (update: any) => {
        const next = typeof update === 'function' ? update(slots[index].value) : update;
        if (!Object.is(next, slots[index].value)) { slots[index].value = next; dirty = true; }
      }];
    },
    useRef(initial: unknown) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { value: { current: initial } };
      return slots[index].value;
    },
    useEffect(callback: () => (() => void) | void, deps: unknown[]) {
      const index = cursor++, previous = slots[index];
      if (!previous || deps.some((dep, i) => !Object.is(dep, previous.deps[i]))) {
        slots[index] = { deps, cleanup: previous?.cleanup };
        effects.push(() => { slots[index].cleanup?.(); slots[index].cleanup = callback(); });
      }
    },
    window: Object.assign(new EventTarget(), { setInterval, clearInterval, setTimeout }),
  });
  const render = () => {
    cursor = 0; dirty = false; tree = component(props);
    const pending = effects; effects = [];
    for (const effect of pending) effect();
  };
  const settle = async () => {
    for (let iteration = 0; iteration < 20; iteration++) {
      if (dirty) render();
      await new Promise(resolve => setImmediate(resolve));
      if (!dirty) return;
    }
    throw new Error('component did not settle');
  };
  const all = (predicate: (node: Element) => boolean) => descendants(tree, predicate);
  const find = (predicate: (node: Element) => boolean) => {
    const matches = all(predicate); assert.equal(matches.length, 1); return matches[0];
  };
  const button = (label: string) => find(node => node.type === 'button' && text(node) === label);
  const select = (label: string) => find(node => node.type === 'select' && node.props['aria-label'] === label);
  const input = (label: string) => {
    const field = find(node => node.type === 'label' && text(node) === label);
    return descendants(field, node => node.type === 'input')[0];
  };
  await settle();
  return { api, calls, errors, settle, all, find, button, select, input,
    changeSource(path: string) { props.source = { path }; dirty = true; },
  };
}

test('preoptimization is immediately editable, undoable, and disposable on close', async () => {
  const page = await mount();
  const builder = () => page.find(node => node.type === 'MoleculeBuilder');
  const viewer = () => page.find(node => node.type === 'Molecule3DViewer');
  const optimize = () => builder().props.onEdit({ action: 'preoptimize', force_field: 'MMFF94' });
  let inputMolecule = '';
  page.api.edit = async (_id, body) => {
    inputMolecule = body.molecule;
    return { ...edited, molecule: body.action === 'preoptimize' ? 'optimized' : 'hand-edited' };
  };
  viewer().props.onAtomPick(2); await page.settle();
  optimize(); await page.settle();
  assert.equal(inputMolecule, 'original');
  assert.equal(viewer().props.geometry.molecule, 'optimized');
  assert.deepEqual(Array.from(builder().props.selection), [2]);
  assert.equal(builder().props.disabled, false);
  page.button('撤销').props.onClick(); await page.settle();
  assert.equal(viewer().props.geometry.molecule, 'original');
  optimize(); await page.settle();
  builder().props.onModeChange('edit'); await page.settle();
  viewer().props.onAtomPick(1); await page.settle();
  assert.equal(inputMolecule, 'optimized');
  assert.equal(viewer().props.geometry.molecule, 'hand-edited');
  page.button('撤销').props.onClick(); await page.settle();
  assert.equal(viewer().props.geometry.molecule, 'optimized');
  page.button('关闭 ✕').props.onClick(); await page.settle();
  assert.deepEqual(page.calls, { closed: 1, saves: 0 });
});

test('preoptimization preserves earlier unsaved edits and failed optimization preserves coordinates', async () => {
  const page = await mount();
  const builder = () => page.find(node => node.type === 'MoleculeBuilder');
  const viewer = () => page.find(node => node.type === 'Molecule3DViewer');
  const optimize = () => builder().props.onEdit({ action: 'preoptimize', force_field: 'UFF' });
  builder().props.onModeChange('edit'); await page.settle();
  viewer().props.onAtomPick(1); await page.settle();
  page.api.edit = async () => { throw new Error('missing parameters'); };
  optimize(); await page.settle();
  assert.equal(viewer().props.geometry.molecule, 'edited');
  assert.ok(page.errors.some(message => message.includes('missing parameters')));
  page.api.edit = async () => ({ ...edited, molecule: 'optimized' });
  optimize(); await page.settle();
  page.button('关闭 ✕').props.onClick(); await page.settle();
  assert.deepEqual(page.calls, { closed: 0, saves: 0 });
  page.button('继续并放弃修改').props.onClick(); await page.settle();
  assert.deepEqual(page.calls, { closed: 1, saves: 0 });
});

test('pending edits and previews cannot apply native normal modes to edited coordinates', async () => {
  const page = await mount();
  const edit = deferred<GeometryView>();
  page.api.edit = async () => edit.promise;
  page.button('预览整分子镜像').props.onClick(); await page.settle();
  assert.equal(page.select('实际简正模').props.disabled, true, 'mode selection must wait for the edit response');
  edit.resolve(edited); await page.settle();
  assert.equal(page.select('实际简正模').props.disabled, true, 'resolve the preview before selecting a native mode');
  assert.equal(page.find(node => node.type === 'Molecule3DViewer').props.geometry.molecule, 'edited');
  assert.equal(page.find(node => node.type === 'Molecule3DViewer').props.modeDisplacements, undefined);
  page.button('取消预览').props.onClick(); await page.settle();
  assert.equal(Boolean(page.select('实际简正模').props.disabled), false);
  page.select('实际简正模').props.onChange({ target: { value: '0' } }); await page.settle();
  const viewer = page.find(node => node.type === 'Molecule3DViewer');
  assert.equal(viewer.props.geometry.molecule, 'mode-reference');
  assert.deepEqual(structuredClone(viewer.props.modeDisplacements), [[1, 0, 0], [-1, 0, 0]]);
});

for (const outcome of ['success', 'failure'] as const) {
  test(`changed fragment ignores a late preview ${outcome}`, async () => {
    const page = await mount();
    const preview = deferred<GeometryView>();
    page.api.previewFragment = async () => preview.promise;
    page.input('基团 SMILES').props.onChange({ target: { value: 'CCO' } }); await page.settle();
    page.button('预览基团／选择连接原子').props.onClick(); await page.settle();
    page.input('基团连接原子编号（有标记时可空）').props.onChange({ target: { value: '2' } });
    page.input('基团 SMILES').props.onChange({ target: { value: 'CO' } }); await page.settle();
    if (outcome === 'success') preview.resolve({ ...geometry, molecule: 'CCO-preview' });
    else preview.reject(new Error('old CCO request failed'));
    await page.settle();
    assert.equal(page.input('基团 SMILES').props.value, 'CO');
    assert.equal(page.input('基团连接原子编号（有标记时可空）').props.value, '', 'atom indices belong to one fragment input');
    assert.equal(page.all(node => node.type === 'Molecule3DViewer' && node.props.title === '基团连接位置').length, 0);
    assert.deepEqual(page.errors, [], 'stale errors must not be attributed to the new fragment');
    assert.equal(Boolean(page.button('预览基团／选择连接原子').props.disabled), false, 'discarded responses still release busy state');

    page.api.previewFragment = async () => ({ ...geometry, molecule: 'CO-preview' });
    page.button('预览基团／选择连接原子').props.onClick(); await page.settle();
    page.find(node => node.type === 'Molecule3DViewer' && node.props.title === '基团连接位置').props.onAtomPick(2);
    for (const label of ['H1', 'H2']) {
      page.find(node => node.type === 'button' && node.props['aria-label'] === label).props.onClick(); await page.settle();
    }
    let request: any;
    page.api.edit = async (_project, body) => { request = body; return edited; };
    page.button('预览替换结果').props.onClick(); await page.settle();
    assert.equal(request.smiles, 'CO');
    assert.equal(request.attachment_atom, 2, 'the new preview selection is submitted with its own fragment');
  });
}

test('choosing fragment history invalidates a pending preview and installs its own attachment', async () => {
  const page = await mount();
  const saved = { id: 'saved', name: 'Saved fragment', smiles: 'CO', use_count: 1,
    project_use_count: 1, attachment_atom: 1, geometry: { ...geometry, molecule: 'saved-CO' } };
  page.api.fragments = async () => ({ fragments: [saved] });
  page.changeSource('/reload'); await page.settle();
  const preview = deferred<GeometryView>();
  page.api.previewFragment = async () => preview.promise;
  page.input('基团 SMILES').props.onChange({ target: { value: 'CCO' } }); await page.settle();
  page.button('预览基团／选择连接原子').props.onClick(); await page.settle();
  page.find(node => node.type === 'button' && node.props.className === 'wb-fragment-entry').props.onClick(); await page.settle();
  preview.resolve({ ...geometry, molecule: 'old-CCO' }); await page.settle();
  assert.equal(page.input('基团 SMILES').props.value, 'CO');
  assert.equal(page.input('基团连接原子编号（有标记时可空）').props.value, '1');
  assert.equal(page.find(node => node.type === 'Molecule3DViewer' && node.props.title === '基团连接位置').props.geometry.molecule, 'saved-CO');
});

test('multidimensional scans only draw a connecting line within an explicitly fixed slice', async () => {
  const page = await mount();
  const scan = () => page.all(node => typeof node.type === 'function' && node.type.name === 'Curve')[1];
  const renderPlot = () => {
    const { type, props } = scan();
    assert.ok(typeof type === 'function');
    return type(props);
  };
  assert.equal(descendants(renderPlot(), node => node.type === 'polyline').length, 0);
  assert.equal(descendants(renderPlot(), node => node.type === 'circle').length, 2);
  page.find(node => node.type === 'select' && text(node) === '坐标 1坐标 2').props.onChange({target: {value: '1'}});
  await page.settle();
  page.find(node => node.type === 'select' && text(node) === '所有采样100').props.onChange({target: {value: '100'}});
  await page.settle();
  assert.equal(descendants(renderPlot(), node => node.type === 'polyline').length, 1);
});

for (const entry of ['source', 'import'] as const) {
  test(`opening a new scan through ${entry} clears old axis and slice filters`, async () => {
    const page = await mount();
    page.find(node => node.type === 'select' && text(node) === '坐标 1坐标 2').props.onChange({ target: { value: '1' } });
    await page.settle();
    page.find(node => node.type === 'select' && text(node) === '所有采样100').props.onChange({ target: { value: '100' } });
    await page.settle();
    page.api.open = async () => nextDocument;
    if (entry === 'source') page.changeSource('/second');
    else {
      page.select('来源类型').props.onChange({ target: { value: 'path' } });
      page.find(node => node.type === 'textarea' && node.props['aria-label'] === '结构来源').props.onChange({ target: { value: '/second' } });
      await page.settle();
      page.button('新建／打开').props.onClick();
    }
    await page.settle();
    assert.equal(page.find(node => node.type === 'select' && text(node) === '坐标 1').props.value, 0);
    const curves = page.all(node => typeof node.type === 'function' && node.type.name === 'Curve');
    assert.equal(curves[1].props.scanAxis, 0);
    assert.deepEqual(structuredClone(curves[1].props.frames.map((frame: any) => [frame.index, frame.scan_coordinates[0]])), [[0, 300], [1, 301]]);
  });
}

test('canvas picks preserve the coordinate order and only committed picks affect a mirror', async () => {
  const page = await mount();
  const viewer = () => page.find(node => node.type === 'Molecule3DViewer');
  const editor = () => page.find(node => node.type === 'WorkbenchCoordinateDialog');
  const atom = async (index: number) => { viewer().props.onAtomPick(index); await page.settle(); };
  const click = async (name: string) => { page.button(name).props.onClick(); await page.settle(); };
  await atom(2); await atom(1);
  await click('编辑距离');
  editor().props.onPickMoving(); await page.settle();
  await atom(1);
  viewer().props.onBackgroundClick([0,0,0]); await page.settle();
  assert.deepEqual(Array.from(viewer().props.selectedAtoms), [2,1]);
  assert.deepEqual(Array.from(viewer().props.movingAtoms), [1]);
  await click('使用所选原子');
  assert.deepEqual(Array.from(editor().props.selection.movingAtoms), [1]);
  editor().props.onClose(); await page.settle();
  await click('画布选择镜像原子');
  assert.deepEqual(Array.from(viewer().props.movingAtoms), []);
  assert.deepEqual(Array.from(viewer().props.selectedAtoms), []);
  await atom(2); await click('使用所选原子');
  await click('画布选择镜像原子'); await atom(1); await click('取消选组');
  let request: any;
  page.api.edit = async (_id, body) => {
    request = body;
    return {...edited, changes:{moved_atoms:[2],deleted_atoms:[],deleted_atom_ids:[],index_map:{}}};
  };
  await click('预览指定原子镜像');
  assert.deepEqual(Array.from(request.moving_atoms), [2]);
  assert.deepEqual(Array.from(viewer().props.movingAtoms), [2]);
  assert.deepEqual(Array.from(viewer().props.selectedAtoms), []);
  assert.match(text(page.find(node => node.props.className === 'wb-preview')), /移动组（1）：2/);
});

test('canvas selection, growth, independent placement and undo follow the active tool', async () => {
  const page = await mount();
  const viewer = () => page.find(node => node.type === 'Molecule3DViewer');
  const builder = () => page.find(node => node.type === 'MoleculeBuilder');
  const requests: any[] = [];
  page.api.edit = async (_id, body) => { requests.push(JSON.parse(JSON.stringify(body))); return edited; };
  assert.equal(builder().props.editing, false);
  viewer().props.onAtomPick(2); await page.settle();
  assert.deepEqual(Array.from(builder().props.selection), [2]);
  assert.equal(requests.length, 0);
  builder().props.onModeChange('edit'); await page.settle();
  builder().props.onBrushChange('[*]O'); await page.settle();
  viewer().props.onAtomPick(1);
  viewer().props.onAtomPick(1);
  await page.settle();
  assert.deepEqual(requests, [{ action: 'add_group', smiles: '[*]O', atoms: [1], molecule: 'original' }]);
  assert.deepEqual(Array.from(builder().props.selection), []);
  assert.equal(viewer().props.preserveView, true);
  viewer().props.onBackgroundClick([1,2,3]); await page.settle();
  assert.deepEqual(requests[1], { action: 'add_group', smiles: '[*]O', atoms: [], position:[1,2,3], molecule:'edited' });
  page.button('撤销').props.onClick(); await page.settle();
  page.button('撤销').props.onClick(); await page.settle();
  assert.equal(viewer().props.geometry.molecule, 'original');
  builder().props.onModeChange('select'); await page.settle();
  viewer().props.onAtomPick(1); await page.settle();
  viewer().props.onBackgroundClick([0,0,0]); await page.settle();
  assert.deepEqual(Array.from(builder().props.selection), []);
  assert.equal(requests.length, 2);
});

test('draft and source-frame notes keep separate markers and survive save, and closing asks before discarding them', async () => {
  const page = await mount();
  const instruction = () => page.find(n => n.props['aria-label'] === '给 Agent 的图上指令');
  const write = async (value: string) => { instruction().props.onChange({target:{value}}); await page.settle(); };
  const frame = async (value: number) => {
    page.find(n => n.props['aria-label'] === '来源帧').props.onChange({target:{value}});
    await page.settle();
  };
  const markerCount = () => page.all(n => n.props['aria-label'] === '移除标记 A').length;
  page.find(n => n.type === 'Molecule3DViewer').props.onAtomPick(1); await page.settle();
  page.button('标记原子').props.onClick(); await page.settle();
  await write('draft A');
  const save = page.button('保存编辑稿到项目');
  save.props.onClick(); save.props.onClick(); await page.settle();
  assert.equal(page.calls.saves, 1);
  assert.equal(page.button('已保存到项目').props.disabled, true);
  page.button('已保存到项目').props.onClick(); await page.settle();
  assert.equal(page.calls.saves, 1);
  assert.equal(instruction().props.value, 'draft A');
  assert.equal(markerCount(), 1);
  page.button('来源帧').props.onClick(); await page.settle();
  assert.equal(instruction().props.value, '');
  assert.equal(markerCount(), 0);
  await write('source 1'); await frame(1); await write('source 2'); await frame(0);
  assert.equal(instruction().props.value, 'source 1');
  await frame(1); assert.equal(instruction().props.value, 'source 2');
  page.button('返回编辑稿').props.onClick(); await page.settle();
  assert.equal(instruction().props.value, 'draft A');
  assert.equal(markerCount(), 1);
  page.button('关闭 ✕').props.onClick(); await page.settle();
  assert.equal(page.calls.closed, 0);
  assert.match(text(page.find(n => n.props.role === 'alert')), /未发送/);
  page.button('保留编辑稿').props.onClick(); await page.settle();
  assert.equal(instruction().props.value, 'draft A');
  page.button('关闭 ✕').props.onClick(); await page.settle();
  page.button('继续并放弃修改').props.onClick(); await page.settle();
  assert.equal(page.calls.closed, 1);
});

test('a coordinate preview blocks frame navigation and playback until it is accepted or cancelled', async () => {
  const page = await mount();
  for (const index of [1,2]) {
    page.find(n => n.type === 'Molecule3DViewer').props.onAtomPick(index);
    await page.settle();
  }
  page.button('编辑距离').props.onClick(); await page.settle();
  await page.find(n => n.type === 'WorkbenchCoordinateDialog').props.onPreview({action:'coordinate', atoms:[1,2], value:1.5});
  await page.settle();
  const slider = () => page.find(n => n.props['aria-label'] === '来源帧');
  assert.equal(slider().props.disabled, true);
  assert.equal(page.button('播放各帧').props.disabled, true);
  assert.ok(page.all(n => typeof n.type === 'function' && n.type.name === 'Curve').every(curve => curve.props.disabled));
  slider().props.onChange({target:{value:1}}); page.button('播放各帧').props.onClick(); await page.settle();
  assert.equal(slider().props.value, 0);
  page.button('关闭 ✕').props.onClick(); await page.settle();
  assert.match(text(page.find(n => n.props.role === 'alert')), /未确认的结构预览/);
  page.button('保留编辑稿').props.onClick(); await page.settle();
  page.button('取消预览').props.onClick(); await page.settle();
  slider().props.onChange({target:{value:1}}); await page.settle();
  assert.equal(slider().props.value, 1);
});

test('a delayed send clears only its source-frame note and keeps the next frame editable', async () => {
  const receipt = deferred<void>();
  const shots: WorkbenchShot[] = [];
  const page = await mount(async shot => { shots.push(shot); await receipt.promise; });
  const viewer = () => page.find(n => n.type === 'Molecule3DViewer');
  viewer().props.captureRef.current = {capture:async () => ({image:new Blob(), camera:[]})};
  const instruction = () => page.find(n => n.props['aria-label'] === '给 Agent 的图上指令');
  const write = async (value: string) => { instruction().props.onChange({target:{value}}); await page.settle(); };
  const frame = async (value: number) => {
    page.find(n => n.props['aria-label'] === '来源帧').props.onChange({target:{value}});
    await page.settle();
  };
  page.button('来源帧').props.onClick(); await page.settle();
  viewer().props.onAtomPick(1); await page.settle();
  page.button('标记原子').props.onClick(); await page.settle();
  await write('send A');
  page.button('发射给 Agent').props.onClick(); await page.settle();
  await frame(1); await write('keep frame 2');
  receipt.resolve(); await page.settle();
  assert.equal(shots.length, 1);
  assert.equal(shots[0].snapshot.source_frame, 0);
  assert.equal(shots[0].snapshot.markers[0].atoms[0].index, 1);
  assert.equal(instruction().props.value, 'keep frame 2');
  await write(''); await frame(0);
  assert.equal(instruction().props.value, '');
  assert.equal(page.all(n => n.props['aria-label'] === '移除标记 A').length, 1);
  await write('temporary'); await write('');
  page.button('关闭 ✕').props.onClick(); await page.settle();
  assert.equal(page.calls.closed, 1);
});

for (const withInput of [false, true]) {
  test(`reopening a saved record restores its native-input option (${withInput}) and avoids an identical save`, async () => {
    const page = await mount();
    page.api.open = async () => ({...document, saved_with_input:withInput});
    page.changeSource('/project/record'); await page.settle();
    assert.equal(page.input('同时生成原生计算输入').props.checked, withInput);
    assert.equal(page.button('已保存到项目').props.disabled, true);
    page.button('已保存到项目').props.onClick(); await page.settle();
    assert.equal(page.calls.saves, 0);
    page.input('结构名称').props.onChange({target:{value:'另一个名称'}}); await page.settle();
    assert.equal(page.button('保存编辑稿到项目').props.disabled, false);
  });
}

test('an XYZ can retain its current charge or explicitly declare an ionic charge for perception', async () => {
  const page = await mount();
  page.api.open = async () => ({ ...document, geometry: { ...geometry, total_charge: 0, graph_status: 'unresolved' } });
  page.changeSource('/ion.xyz'); await page.settle();
  const bodies: Record<string, unknown>[] = [];
  page.api.edit = async (_project, body) => { bodies.push(structuredClone(body)); return edited; };
  const perceive = () => page.button('明确感知连接关系');
  assert.equal(perceive().props.disabled, false);
  perceive().props.onClick(); await page.settle();
  assert.deepEqual(bodies[0], { action: 'resolve_bonds', molecule: 'original' });
  page.button('取消预览').props.onClick(); await page.settle();
  page.input('感知键级所用总电荷').props.onChange({ target: { value: '1' } }); await page.settle();
  perceive().props.onClick(); await page.settle();
  assert.deepEqual(bodies[1], { action: 'resolve_bonds', charge: 1, molecule: 'original' });
});
