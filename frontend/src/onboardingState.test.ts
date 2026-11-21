import assert from 'node:assert/strict';
import {
  ONBOARDING_STARTERS,
  groupDiagnosticsChecks,
  readDismissedUpdateVersion,
  readOnboardingDismissed,
  shouldAutoOpenOnboarding,
  shouldShowUpdateNotice,
  writeDismissedUpdateVersion,
  writeOnboardingDismissed,
  type StorageLike,
} from './onboardingState.ts';
import type { DiagnosticCheck, UpdateCheckResult } from './types.ts';

function memoryStorage(): StorageLike {
  const map = new Map<string, string>();
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => {
      map.set(key, value);
    },
    removeItem: (key) => {
      map.delete(key);
    },
  };
}

// Onboarding auto-open rules: only when projects are loaded, empty, and not dismissed.
assert.equal(shouldAutoOpenOnboarding({ projectsLoaded: false, projectsCount: 0, dismissed: false }), false);
assert.equal(shouldAutoOpenOnboarding({ projectsLoaded: true, projectsCount: 2, dismissed: false }), false);
assert.equal(shouldAutoOpenOnboarding({ projectsLoaded: true, projectsCount: 0, dismissed: true }), false);
assert.equal(shouldAutoOpenOnboarding({ projectsLoaded: true, projectsCount: 0, dismissed: false }), true);

// Onboarding dismiss persistence.
const store = memoryStorage();
assert.equal(readOnboardingDismissed(store), false);
writeOnboardingDismissed(store, true);
assert.equal(readOnboardingDismissed(store), true);
writeOnboardingDismissed(store, false);
assert.equal(readOnboardingDismissed(store), false);

// Update notice visibility & dismiss-by-version.
const baseUpdate: UpdateCheckResult = {
  status: 'update_available',
  current_version: '0.1.1',
  latest_version: '0.1.2',
  release_url: 'https://github.com/yyywaa/Cloudra-mechanism-agent/releases/tag/v0.1.2',
  release_notes: 'Bug fixes',
  published_at: '2026-11-21T00:00:00Z',
  install_mode: 'macos_app',
  active_compute_jobs: 0,
  checked_at: '2026-11-21T00:00:00Z',
  error: '',
};

assert.equal(shouldShowUpdateNotice(null, ''), false);
assert.equal(shouldShowUpdateNotice({ ...baseUpdate, status: 'up_to_date' }, ''), false);
assert.equal(shouldShowUpdateNotice({ ...baseUpdate, status: 'unavailable' }, ''), false);
assert.equal(shouldShowUpdateNotice(baseUpdate, ''), true);
assert.equal(shouldShowUpdateNotice(baseUpdate, '0.1.2'), false);
assert.equal(shouldShowUpdateNotice(baseUpdate, '0.1.1'), true);

writeDismissedUpdateVersion(store, '0.1.2');
assert.equal(readDismissedUpdateVersion(store), '0.1.2');

// Diagnostics grouping follows canonical capability order and skips empty buckets.
const checks: DiagnosticCheck[] = [
  { id: 'data_dir', group: 'storage', status: 'ready', optional: false, summary: 'ok', detail: '/tmp', hint: '' },
  { id: 'llm_config', group: 'llm', status: 'warning', optional: false, summary: 'warn', detail: 'no key', hint: 'open_global_settings_llm' },
  { id: 'xtb_binary', group: 'chemistry', status: 'optional_missing', optional: true, summary: 'opt', detail: 'missing', hint: '' },
];
const grouped = groupDiagnosticsChecks(checks);
assert.deepEqual(grouped.map((g) => g.group), ['llm', 'chemistry', 'storage']);
assert.equal(grouped[0].items[0].id, 'llm_config');

// Starters have bilingual titles and prompts.
assert.ok(ONBOARDING_STARTERS.length >= 3);
for (const starter of ONBOARDING_STARTERS) {
  assert.ok(starter.titleZh.length > 0 && starter.titleEn.length > 0);
  assert.ok(starter.promptZh.length > 0 && starter.promptEn.length > 0);
}
