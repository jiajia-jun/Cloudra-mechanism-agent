import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';
import { parseSync, transformSync } from 'rolldown/utils';

const source = readFileSync(new URL('./ComposerModelPicker.tsx', import.meta.url), 'utf8');
const program = parseSync('ComposerModelPicker.tsx', source, { lang: 'tsx' }).program;
const exportDecl = program.body.find(
  (node: any) => node.type === 'ExportNamedDeclaration' && node.declaration?.id?.name === 'buildModelPickerPatch',
);
assert.ok(exportDecl, 'buildModelPickerPatch must be exported');
const fnSource = source.slice(exportDecl.declaration.start, exportDecl.declaration.end);
const buildModelPickerPatch = vm.runInThisContext(
  `(() => {\n${transformSync('picker.ts', fnSource, { lang: 'ts' }).code}\nreturn buildModelPickerPatch;\n})()`,
) as (params: {
  model?: string;
  effort?: string;
  slotModel: string;
  slotProviderModels: string[];
}) => Record<string, unknown>;

test('choosing the current global slot default model clears per-agent overrides to inherit global slot', () => {
  assert.deepEqual(
    buildModelPickerPatch({
      model: 'glm-5.3',
      slotModel: 'glm-5.3',
      slotProviderModels: ['glm-5.3', 'glm-5.3-flash'],
    }),
    { model: '', base_url: '', api_key: '', context_window: 0 },
  );
});

test('choosing another model in the global slot provider clears stale endpoint/key overrides', () => {
  assert.deepEqual(
    buildModelPickerPatch({
      model: 'glm-5.3-flash',
      slotModel: 'glm-5.3',
      slotProviderModels: ['glm-5.3', 'glm-5.3-flash'],
    }),
    { model: 'glm-5.3-flash', base_url: '', api_key: '', context_window: 0 },
  );
});

test('changing reasoning effort only patches reasoning_effort without pinning model', () => {
  assert.deepEqual(
    buildModelPickerPatch({
      effort: 'high',
      slotModel: 'glm-5.3',
      slotProviderModels: ['glm-5.3', 'glm-5.3-flash'],
    }),
    { reasoning_effort: 'high' },
  );
});

test('re-selecting a custom model outside global provider preserves custom endpoint', () => {
  assert.deepEqual(
    buildModelPickerPatch({
      model: 'custom-local-model',
      slotModel: 'glm-5.3',
      slotProviderModels: ['glm-5.3', 'glm-5.3-flash'],
    }),
    { model: 'custom-local-model' },
  );
});
