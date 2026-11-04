/** One-shot filter host. Only projected records cross into the guest. */
import { readFileSync } from 'node:fs';
import { Sandbox } from './sandbox.mjs';

const { expression, entries, limits } = JSON.parse(readFileSync(0, 'utf8'));
const sandbox = await Sandbox.create({ limits, isTerminal: () => false });
try {
  process.stdout.write(JSON.stringify({ matches: sandbox.filterEntries(expression, entries) }));
} catch (error) {
  process.stdout.write(JSON.stringify({ error: error.message }));
} finally {
  sandbox.dispose();
}
