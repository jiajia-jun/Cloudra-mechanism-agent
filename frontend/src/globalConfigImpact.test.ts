import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  buildImpactResolutionPatch,
  findImpactedAgents,
} from './globalConfigImpact.ts';
import type { Agent } from './types.ts';

function makeAgent(id: string, role_id: string, settings: Partial<Agent['settings']>): Agent {
  return {
    id,
    project_id: 'p1',
    role_id,
    display_name: id,
    state: 'idle',
    parent_session_id: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    settings_revision: 1,
    settings: {
      model: '',
      base_url: '',
      api_key_set: false,
      temperature: 1,
      max_tokens: 32768,
      context_window: 0,
      timeout: 0,
      yolo: false,
      unattended: false,
      schedule_mode: false,
      visual_mode: true,
      clean_context: false,
      orchestration_mode: 'standard',
      invocation_protocol: 'javascript',
      ...settings,
    },
    capabilities: { permissions: {}, can_spawn: false, tools: [] },
  };
}

const OLD_SLOT = {
  url: 'https://api.deepseek.com',
  model: 'deepseek-v4-flash',
  key_set: true,
  context_window: 128000,
  timeout: 300,
};

test('finds only incomplete overrides affected by endpoint change', () => {
  const inheriting = makeAgent('a-inherit', 'coordinator', {});
  const modelOnly = makeAgent('a-model-only', 'coordinator', { model: 'deepseek-v4-pro' });
  const oldUrlNoKey = makeAgent('a-url-nokey', 'coordinator', {
    model: 'deepseek-v4-flash',
    base_url: 'https://api.deepseek.com/',
    api_key_set: false,
  });
  const completeCustom = makeAgent('a-complete', 'coordinator', {
    model: 'deepseek-v4-pro',
    base_url: 'https://api.deepseek.com',
    api_key_set: true,
  });
  const otherProvider = makeAgent('a-other', 'coordinator', {
    model: 'gpt-6-astra',
    base_url: 'https://api.openai.com/v1',
    api_key_set: false,
  });
  const followerModelOnly = makeAgent('a-follower', 'researcher', { model: 'deepseek-chat' });

  const impacted = findImpactedAgents({
    slot: 'coordinator',
    oldSlot: OLD_SLOT,
    newUrl: 'https://open.bigmodel.cn/api/coding/paas/v4',
    projects: [{ id: 'p1', name: 'Demo' }],
    agentsByProject: {
      p1: [inheriting, modelOnly, oldUrlNoKey, completeCustom, otherProvider, followerModelOnly],
    },
  });

  assert.deepEqual(
    impacted.map((x) => ({ id: x.agent.id, missing: x.missingFields })),
    [
      { id: 'a-model-only', missing: ['base_url', 'api_key'] },
      { id: 'a-url-nokey', missing: ['api_key'] },
    ],
  );
});

test('returns empty when endpoint does not change', () => {
  const modelOnly = makeAgent('a-model-only', 'coordinator', { model: 'deepseek-v4-pro' });
  const impacted = findImpactedAgents({
    slot: 'coordinator',
    oldSlot: OLD_SLOT,
    newUrl: 'https://api.deepseek.com/',
    projects: [{ id: 'p1', name: 'Demo' }],
    agentsByProject: { p1: [modelOnly] },
  });
  assert.deepEqual(impacted, []);
});

test('builds correct patches for use_new_global, complete_old, and keep_as_is', () => {
  const modelOnly = makeAgent('a-model-only', 'coordinator', { model: 'deepseek-v4-pro' });
  const [item] = findImpactedAgents({
    slot: 'coordinator',
    oldSlot: OLD_SLOT,
    newUrl: 'https://open.bigmodel.cn/api/coding/paas/v4',
    projects: [{ id: 'p1', name: 'Demo' }],
    agentsByProject: { p1: [modelOnly] },
  });

  assert.deepEqual(
    buildImpactResolutionPatch({ item, decision: 'use_new_global', oldSlot: OLD_SLOT }),
    { model: '' },
  );
  assert.deepEqual(
    buildImpactResolutionPatch({
      item,
      decision: 'complete_old',
      oldSlot: OLD_SLOT,
      manualApiKey: 'sk-old-manual',
    }),
    {
      base_url: 'https://api.deepseek.com',
      context_window: 128000,
      timeout: 300,
      api_key: 'sk-old-manual',
    },
  );
  assert.equal(
    buildImpactResolutionPatch({ item, decision: 'keep_as_is', oldSlot: OLD_SLOT }),
    null,
  );
});
