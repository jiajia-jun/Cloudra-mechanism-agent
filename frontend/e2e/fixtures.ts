import type { Page, Route } from '@playwright/test';

export const PROJECT_ACTIVE = {
  id: 'proj_live',
  name: 'Live Demo',
  workspace_dir: '/tmp/live',
  archived: false,
  settings: { orchestration_mode: 'standard', defaults: { yolo: false, visual_mode: true } },
};

export const PROJECT_ARCHIVED = {
  id: 'proj_old',
  name: 'Old Archived',
  workspace_dir: '/tmp/old',
  archived: true,
  settings: { orchestration_mode: 'standard', defaults: {} },
};

export const AGENT = {
  id: 'agent_coord',
  project_id: PROJECT_ACTIVE.id,
  role_id: 'coordinator',
  display_name: 'Main Coordinator',
  state: 'succeeded',
  parent_session_id: null,
  settings: {
    orchestration_mode: 'standard',
    yolo: false,
    visual_mode: true,
    schedule_mode: false,
    invocation_protocol: 'javascript',
  },
};

export const JOB = {
  id: 7,
  project_id: PROJECT_ACTIVE.id,
  session_id: AGENT.id,
  state: 'running',
  jobtype: 'xtb',
  path: '/tmp/live/job.xyz',
  node_id: 'local',
  start_timestamp: Math.floor(Date.now() / 1000) - 30,
};

type MockOpts = {
  projects?: object[];
  agents?: object[];
  jobs?: object[];
  interactions?: object[];
  approvals?: object[];
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

/** Stub the SPA's /api/v2 surface so Vite never needs a live Cloudra API. */
export async function installApiMocks(page: Page, opts: MockOpts = {}) {
  const projects = opts.projects ?? [PROJECT_ACTIVE, PROJECT_ARCHIVED];
  const agents = opts.agents ?? [AGENT];
  const jobs = opts.jobs ?? [JOB];
  const interactions = opts.interactions ?? [];
  const approvals = opts.approvals ?? [];

  const cancelAllHits: object[] = [];
  const deleteHits: string[] = [];
  const respondHits: object[] = [];

  await page.route('**/api/v2/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();

    if (method === 'GET' && path === '/api/v2/projects') {
      const includeArchived = url.searchParams.get('include_archived') === 'true';
      const rows = includeArchived ? projects : projects.filter((p) => !(p as { archived?: boolean }).archived);
      return json(route, rows);
    }
    if (method === 'GET' && path.endsWith('/view')) {
      return json(route, { agents, cursor: 0 });
    }
    if (method === 'GET' && path === '/api/v2/roles') {
      return json(route, [{ role_id: 'coordinator', display_name: 'Coordinator' }]);
    }
    if (method === 'GET' && path.match(/^\/api\/v2\/projects\/[^/]+\/agents$/)) {
      return json(route, agents);
    }
    if (method === 'GET' && path.match(/^\/api\/v2\/agents\/[^/]+$/)) {
      return json(route, agents.find((agent) => (agent as { id?: string }).id === path.split('/').pop()) ?? AGENT);
    }
    // Must be before the /context catch-all: Inspector calls this on agent select
    // and crashes on undefined tokens if we return a goal-shaped stub.
    if (method === 'GET' && path.match(/^\/api\/v2\/agents\/[^/]+\/context$/)) {
      return json(route, {
        session_id: (agents[0] as { id?: string } | undefined)?.id ?? AGENT.id,
        messages: 0,
        tokens: 0,
        by_role: {},
        last_prompt_tokens: null,
      });
    }
    if (method === 'GET' && path.includes('/events')) {
      return json(route, []);
    }
    if (method === 'GET' && path.includes('/compute/jobs')) {
      return json(route, jobs);
    }
    if (method === 'GET' && path === '/api/v2/compute/nodes') {
      return json(route, []);
    }
    if (method === 'GET' && path.includes('/reminders/pending')) {
      return json(route, []);
    }
    if (method === 'GET' && path.includes('/approvals')) {
      return json(route, approvals);
    }
    if (method === 'GET' && path.includes('/interactions')) {
      return json(route, interactions);
    }
    if (method === 'GET' && path.includes('/artifacts')) {
      return json(route, []);
    }
    if (method === 'GET' && path.endsWith('/workbench/products')) {
      return json(route, { products: [], objects: [] });
    }
    if (method === 'GET' && path.endsWith('/workbench/fragments')) {
      return json(route, { fragments: [] });
    }
    if (method === 'GET' && (path.includes('/dag/') || path.includes('/goal'))) {
      return json(route, path.includes('/projection')
        ? { mode: 'standard', pending_reviews: [], frontier: [] }
        : path.includes('/reviews')
          ? { pending: [], recent: [] }
          : path.includes('/draft')
            ? { mechanism_accepted: false, draft: null }
            : path.includes('/delivery')
              ? { mode: 'standard', graph: { nodes: [], edges: [] } }
              : { goal: null });
    }
    if (method === 'GET' && path === '/api/v2/skills') {
      return json(route, []);
    }
    if (method === 'GET' && path.includes('/stream')) {
      // EventSource — fulfill with empty stream body; SPA reconnects on close.
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'event: project.synced\ndata: {"type":"project.synced","seq":0,"data":{"replayed_through":0}}\n\n',
      });
    }
    if (method === 'POST' && path === '/api/v2/compute/cancel-all') {
      const body = { ready_cancelled: 1, cancel_requested: 1 };
      cancelAllHits.push(body);
      return json(route, body);
    }
    if (method === 'DELETE' && path.match(/^\/api\/v2\/projects\/[^/]+$/)) {
      deleteHits.push(path + (url.search || ''));
      return json(route, {
        command_id: 'cmd_del',
        accepted: true,
        event_id: 'ev_del',
        data: { id: path.split('/').pop() },
      });
    }
    if (method === 'POST' && path.includes('/interactions/') && path.endsWith('/response')) {
      const payload = req.postDataJSON();
      respondHits.push({ path, payload });
      return json(route, { ok: true });
    }
    if (method === 'POST' && path.includes('/messages')) {
      return json(route, {
        command_id: 'cmd_msg',
        accepted: true,
        event_id: 'ev_msg',
        data: agents[0] ?? AGENT,
      });
    }
    // Default: empty success so unknown GETs don't toast-spam.
    if (method === 'GET') return json(route, Array.isArray(approvals) ? [] : {});
    return json(route, { accepted: true, command_id: 'cmd_x', event_id: 'ev_x', data: {} });
  });

  return { cancelAllHits, deleteHits, respondHits };
}

export async function openSpa(page: Page, hash = '') {
  await page.goto(`/${hash}`);
  // Acid keeps project creation collapsed until the user asks for it.
  await page.locator('.left-sidebar-title').waitFor({
    state: 'visible',
    timeout: 15_000,
  });
}
