import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { parseSync, transformSync } from 'rolldown/utils';

// Load the actual API module without browser bootstrap or a network connection.
const source = readFileSync(new URL('./api.ts', import.meta.url), 'utf8');
const tree = parseSync('api.ts', source, { lang: 'ts' }).program;
const body = tree.body.filter(node => node.type !== 'ImportDeclaration').map(
  (node: any) => node.type === 'ExportNamedDeclaration' ? node.declaration : node,
).filter((node: any) => !(node.type === 'VariableDeclaration' && node.declarations.some(
  (declaration: any) => ['runtimeUrl', 'apiToken'].includes(declaration.id.name),
))).map(node => source.slice(node.start, node.end)).join('\n');
let response: unknown;
const exports = vm.runInNewContext(transformSync('api.ts', `${body}\n({api, request});`, { lang: 'ts' }).code, {
  runtimeUrl: '', apiToken: '',
  fetch: async () => ({ ok: true, json: async () => response }),
});

for (const command of [
  () => exports.api.createProject('bad', 'relative-folder'),
  () => exports.api.patchProject('P', { workspace_dir: 'relative-folder' }),
  () => exports.api.archiveProject('P'),
  () => exports.api.patchSettings('A', { yolo: true }),
  () => exports.api.compactAgent('A'),
]) {
  response = { command_id: 'rejected', accepted: false, event_id: '', data: {
    error: { code: 'invalid_request', message: 'workspace must be absolute' },
  } };
  await assert.rejects(command, (error: any) => error.code === 'invalid_request' && error.message === 'workspace must be absolute');
}
response = { command_id: 'accepted', accepted: true, event_id: 'event', data: { id: 'P' } };
assert.equal((await exports.api.createProject('ok')).data.id, 'P');
// A domain result is not a command rejection envelope.
response = { accepted: false, issues: ['evidence needs review'] };
assert.equal((await exports.request('/domain-result')).accepted, false);
console.log('api.test.ts: ok');
